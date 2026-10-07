/* SPDX-License-Identifier: MIT
 * Tests the real WSI implementation against deterministic Vulkan/XCB mocks.
 * No Vulkan loader, Android driver or X11 server is contacted.
 */
#include <bits/stdc++.h>
#include <poll.h>
#include <sys/eventfd.h>
#include <unistd.h>
#include <xcb/dri3.h>
// Expose only layer internals to construct an isolated mock dispatch fixture.
#define private public
#define protected public
#include "wsi/x11/swapchain.hpp"
#undef protected
#undef private

struct wsi::x11::surface::init_parameters
{
   const util::allocator &allocator;
   xcb_connection_t *connection;
   xcb_window_t window;
};

namespace {
std::set<VkImage> live_images;
unsigned image_creates, image_destroys, allocations, frees;
unsigned pools_created, pools_destroyed, blits_recorded, conversion_submits;
std::map<VkImage, VkFormat> image_formats;
bool fail_command_allocation;
void *instance_key = reinterpret_cast<void *>(0x1234);
VkInstance instance_handle = reinterpret_cast<VkInstance>(&instance_key);
VkPhysicalDevice physical_handle = reinterpret_cast<VkPhysicalDevice>(&instance_key);
std::atomic<unsigned> presents{0};
extern int xcb_fd;
void require(bool value, const char *message);
std::atomic<bool> connection_error{false};
std::atomic<uint32_t> last_present_serial{0}, last_present_pixmap{0};
std::mutex events_lock;
std::deque<xcb_generic_event_t *> events;
void deliver_event(xcb_generic_event_t *event)
{
   { std::lock_guard<std::mutex> lock(events_lock); events.push_back(event); }
   const uint64_t wakeup = 1;
   require(write(xcb_fd, &wakeup, sizeof(wakeup)) == sizeof(wakeup), "event notification");
}
bool fail_allocation;
int xcb_fd;
uintptr_t next_handle = 100;
std::mutex fence_lock;
std::condition_variable fence_condition;
bool gpu_complete = true;
bool submitted = false;
bool waiting_for_current_frame = false;

template <class T> T handle() { return reinterpret_cast<T>(++next_handle); }
void require(bool value, const char *message)
{
   if (!value) throw std::runtime_error(message);
}
void unused_entrypoint() { throw std::runtime_error("unexpected Vulkan entrypoint"); }
VKAPI_ATTR VkResult VKAPI_CALL create_image(VkDevice, const VkImageCreateInfo *info,
                                          const VkAllocationCallbacks *, VkImage *image)
{
   if (info->format == VK_FORMAT_B8G8R8A8_UNORM)
      require(info->tiling == VK_IMAGE_TILING_OPTIMAL && info->pNext == nullptr &&
              (info->usage & VK_IMAGE_USAGE_TRANSFER_SRC_BIT) && (info->flags & VK_IMAGE_CREATE_ALIAS_BIT),
              "BGRA render/alias image contract changed");
   else
   {
      require(info->format == VK_FORMAT_R8G8B8A8_UNORM && info->tiling == VK_IMAGE_TILING_LINEAR,
              "unexpected presentation format/tiling");
      auto external = static_cast<const VkExternalMemoryImageCreateInfo *>(info->pNext);
      require(external && external->sType == VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_IMAGE_CREATE_INFO,
              "invalid image pNext lifetime");
      require(external->pNext == nullptr && external->handleTypes ==
              VK_EXTERNAL_MEMORY_HANDLE_TYPE_ANDROID_HARDWARE_BUFFER_BIT_ANDROID,
              "broken AHB extension chain");
   }
   *image = handle<VkImage>();
   live_images.insert(*image); image_formats[*image] = info->format; ++image_creates;
   return VK_SUCCESS;
}
VKAPI_ATTR void VKAPI_CALL destroy_image(VkDevice, VkImage image, const VkAllocationCallbacks *)
{
   require(live_images.erase(image) == 1, "image leaked, replaced or destroyed twice");
   image_formats.erase(image); ++image_destroys;
}
VKAPI_ATTR VkResult VKAPI_CALL allocate_memory(VkDevice, const VkMemoryAllocateInfo *info,
                                              const VkAllocationCallbacks *, VkDeviceMemory *memory)
{
   if (info->allocationSize == 0)
   {
      auto export_info = static_cast<const VkExportMemoryAllocateInfo *>(info->pNext);
      auto dedicated = static_cast<const VkMemoryDedicatedAllocateInfo *>(export_info->pNext);
      require(live_images.count(dedicated->image) && image_formats[dedicated->image] == VK_FORMAT_R8G8B8A8_UNORM,
              "AHB export must use the RGBA presentation image");
   }
   else
      require(info->allocationSize == 16384 && info->pNext == nullptr, "ordinary BGRA memory allocation");
   if (fail_allocation) return VK_ERROR_OUT_OF_DEVICE_MEMORY;
   *memory = handle<VkDeviceMemory>(); ++allocations; return VK_SUCCESS;
}
VKAPI_ATTR void VKAPI_CALL free_memory(VkDevice, VkDeviceMemory, const VkAllocationCallbacks *) { ++frees; }
VKAPI_ATTR VkResult VKAPI_CALL bind_memory(VkDevice, VkImage image, VkDeviceMemory, VkDeviceSize)
{ require(live_images.count(image), "binding replaced image"); return VK_SUCCESS; }
VKAPI_ATTR void VKAPI_CALL image_requirements(VkDevice, VkImage image, VkMemoryRequirements *requirements)
{ require(image_formats[image] == VK_FORMAT_B8G8R8A8_UNORM, "requirements queried before AHB bind");
  *requirements = {16384, 4, 1}; }
VKAPI_ATTR VkResult VKAPI_CALL create_pool(VkDevice, const VkCommandPoolCreateInfo *info,
                                         const VkAllocationCallbacks *, VkCommandPool *pool)
{ require(info->queueFamilyIndex == 0, "conversion used an unknown queue family");
  *pool = handle<VkCommandPool>(); ++pools_created; return VK_SUCCESS; }
VKAPI_ATTR void VKAPI_CALL destroy_pool(VkDevice, VkCommandPool, const VkAllocationCallbacks *) { ++pools_destroyed; }
VKAPI_ATTR VkResult VKAPI_CALL allocate_commands(VkDevice, const VkCommandBufferAllocateInfo *, VkCommandBuffer *command)
{ if (fail_command_allocation) return VK_ERROR_OUT_OF_HOST_MEMORY;
  *command = handle<VkCommandBuffer>(); return VK_SUCCESS; }
VKAPI_ATTR VkResult VKAPI_CALL reset_command(VkCommandBuffer, VkCommandBufferResetFlags) { return VK_SUCCESS; }
VKAPI_ATTR VkResult VKAPI_CALL begin_command(VkCommandBuffer, const VkCommandBufferBeginInfo *) { return VK_SUCCESS; }
VKAPI_ATTR VkResult VKAPI_CALL end_command(VkCommandBuffer) { return VK_SUCCESS; }
VKAPI_ATTR void VKAPI_CALL pipeline_barrier(VkCommandBuffer, VkPipelineStageFlags, VkPipelineStageFlags,
   VkDependencyFlags, uint32_t, const VkMemoryBarrier *, uint32_t, const VkBufferMemoryBarrier *,
   uint32_t count, const VkImageMemoryBarrier *barriers)
{ require(count == 2 && image_formats[barriers[0].image] == VK_FORMAT_B8G8R8A8_UNORM &&
          image_formats[barriers[1].image] == VK_FORMAT_R8G8B8A8_UNORM, "conversion barriers target wrong images"); }
VKAPI_ATTR void VKAPI_CALL blit_image(VkCommandBuffer, VkImage source, VkImageLayout source_layout,
   VkImage destination, VkImageLayout destination_layout, uint32_t count, const VkImageBlit *, VkFilter filter)
{ require(image_formats[source] == VK_FORMAT_B8G8R8A8_UNORM && image_formats[destination] == VK_FORMAT_R8G8B8A8_UNORM &&
          source_layout == VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL && destination_layout == VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL &&
          count == 1 && filter == VK_FILTER_NEAREST, "BGRA conversion lost the real format contract"); ++blits_recorded; }
VKAPI_ATTR void VKAPI_CALL image_layout(VkDevice, VkImage, const VkImageSubresource *, VkSubresourceLayout *layout)
{ *layout = {}; layout->rowPitch = 64 * 4; }
VKAPI_ATTR VkResult VKAPI_CALL get_ahb(VkDevice, const VkMemoryGetAndroidHardwareBufferInfoANDROID *, AHardwareBuffer **ahb)
{ *ahb = reinterpret_cast<AHardwareBuffer *>(1); return VK_SUCCESS; }
VKAPI_ATTR VkResult VKAPI_CALL create_fence(VkDevice, const VkFenceCreateInfo *, const VkAllocationCallbacks *, VkFence *fence)
{ *fence = handle<VkFence>(); return VK_SUCCESS; }
VKAPI_ATTR void VKAPI_CALL destroy_fence(VkDevice, VkFence, const VkAllocationCallbacks *) {}
VKAPI_ATTR VkResult VKAPI_CALL reset_fences(VkDevice, uint32_t, const VkFence *) { return VK_SUCCESS; }
VKAPI_ATTR VkResult VKAPI_CALL wait_fences(VkDevice, uint32_t, const VkFence *, VkBool32, uint64_t)
{
   std::unique_lock<std::mutex> lock(fence_lock);
   require(submitted, "wait occurred before queue submission");
   waiting_for_current_frame = true; fence_condition.notify_all();
   fence_condition.wait(lock, [] { return gpu_complete; });
   return VK_SUCCESS;
}
VKAPI_ATTR VkResult VKAPI_CALL queue_submit(VkQueue, uint32_t count, const VkSubmitInfo *info, VkFence)
{
   require(count == 1, "submission count");
   if (info->commandBufferCount)
   {
      require(info->commandBufferCount == 1 && info->pCommandBuffers, "conversion command not submitted");
      for (uint32_t i = 0; i < info->waitSemaphoreCount; ++i)
         require(info->pWaitDstStageMask[i] == VK_PIPELINE_STAGE_TRANSFER_BIT, "blit did not wait for client rendering");
      ++conversion_submits;
   }
   std::lock_guard<std::mutex> lock(fence_lock); submitted = true; return VK_SUCCESS;
}
VKAPI_ATTR VkResult VKAPI_CALL queue_idle(VkQueue) { return VK_SUCCESS; }
VKAPI_ATTR VkResult VKAPI_CALL create_semaphore(VkDevice, const VkSemaphoreCreateInfo *, const VkAllocationCallbacks *, VkSemaphore *semaphore)
{ *semaphore = handle<VkSemaphore>(); return VK_SUCCESS; }
VKAPI_ATTR void VKAPI_CALL destroy_semaphore(VkDevice, VkSemaphore, const VkAllocationCallbacks *) {}
VKAPI_ATTR void VKAPI_CALL get_queue(VkDevice, uint32_t, uint32_t, VkQueue *queue) { *queue = handle<VkQueue>(); }
VKAPI_ATTR VkResult VKAPI_CALL loader_data(VkDevice, void *) { return VK_SUCCESS; }
VKAPI_ATTR void VKAPI_CALL memory_properties(VkPhysicalDevice, VkPhysicalDeviceMemoryProperties2 *properties)
{
   require(properties->sType == VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MEMORY_PROPERTIES_2 && !properties->pNext,
           "uninitialized memory property query");
   properties->memoryProperties.memoryTypeCount = 1;
   properties->memoryProperties.memoryTypes[0].propertyFlags = VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT;
}
VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL device_proc(VkDevice, const char *name)
{
#define PROC(suffix, fn) if (!strcmp(name, "vk" #suffix)) return reinterpret_cast<PFN_vkVoidFunction>(fn)
   PROC(CreateImage, create_image); PROC(DestroyImage, destroy_image);
   PROC(AllocateMemory, allocate_memory); PROC(FreeMemory, free_memory); PROC(BindImageMemory, bind_memory);
   PROC(GetImageMemoryRequirements, image_requirements);
   PROC(CreateCommandPool, create_pool); PROC(DestroyCommandPool, destroy_pool);
   PROC(AllocateCommandBuffers, allocate_commands); PROC(ResetCommandBuffer, reset_command);
   PROC(BeginCommandBuffer, begin_command); PROC(EndCommandBuffer, end_command);
   PROC(CmdPipelineBarrier, pipeline_barrier); PROC(CmdBlitImage, blit_image);
   PROC(GetImageSubresourceLayout, image_layout); PROC(GetMemoryAndroidHardwareBufferANDROID, get_ahb);
   PROC(CreateFence, create_fence); PROC(DestroyFence, destroy_fence); PROC(ResetFences, reset_fences);
   PROC(WaitForFences, wait_fences); PROC(QueueSubmit, queue_submit); PROC(QueueWaitIdle, queue_idle);
   PROC(CreateSemaphore, create_semaphore); PROC(DestroySemaphore, destroy_semaphore); PROC(GetDeviceQueue, get_queue);
#undef PROC
   return reinterpret_cast<PFN_vkVoidFunction>(unused_entrypoint);
}
VKAPI_ATTR void VKAPI_CALL queue_properties(VkPhysicalDevice, uint32_t *count, VkQueueFamilyProperties2 *families)
{ *count = 1; if (families) families->queueFamilyProperties.queueFlags = VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_TRANSFER_BIT; }
VKAPI_ATTR void VKAPI_CALL format_properties(VkPhysicalDevice, VkFormat, VkFormatProperties2 *properties)
{ properties->formatProperties.linearTilingFeatures = properties->formatProperties.optimalTilingFeatures =
     VK_FORMAT_FEATURE_BLIT_SRC_BIT | VK_FORMAT_FEATURE_BLIT_DST_BIT; }
VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL instance_proc(VkInstance, const char *name)
{
   if (!strcmp(name, "vkGetPhysicalDeviceQueueFamilyProperties2KHR"))
      return reinterpret_cast<PFN_vkVoidFunction>(queue_properties);
   if (!strcmp(name, "vkGetPhysicalDeviceFormatProperties2KHR"))
      return reinterpret_cast<PFN_vkVoidFunction>(format_properties);
   if (!strcmp(name, "vkGetPhysicalDeviceMemoryProperties2KHR"))
      return reinterpret_cast<PFN_vkVoidFunction>(memory_properties);
   return reinterpret_cast<PFN_vkVoidFunction>(unused_entrypoint);
}

struct fixture
{
   util::allocator allocator = util::allocator::get_generic();
   layer::instance_private_data &instance;
   layer::device_private_data device;
   wsi::x11::surface surface;
   static layer::instance_dispatch_table instance_table(const util::allocator &allocator)
   { auto table = layer::instance_dispatch_table::create(allocator); require(table.has_value(), "instance table allocation");
     require(table->populate(nullptr, instance_proc) == VK_SUCCESS, "instance table population"); return std::move(*table); }
   static layer::device_dispatch_table device_table(const util::allocator &allocator)
   { auto table = layer::device_dispatch_table::create(allocator); require(table.has_value(), "device table allocation");
     require(table->populate(nullptr, device_proc) == VK_SUCCESS, "device table population"); return std::move(*table); }
   static layer::instance_private_data &create_instance(const util::allocator &allocator)
   {
      require(layer::instance_private_data::associate(instance_handle, instance_table(allocator), nullptr, {},
              VK_API_VERSION_1_1, allocator) == VK_SUCCESS, "mock instance association");
      return layer::instance_private_data::get(instance_handle);
   }
   fixture() : instance(create_instance(allocator)),
      device(instance, physical_handle, nullptr, device_table(allocator), loader_data, allocator),
      surface(wsi::x11::surface::init_parameters{allocator, reinterpret_cast<xcb_connection_t *>(1), 1}) {}
   std::unique_ptr<wsi::x11::swapchain> create(bool deferred, VkPresentModeKHR mode = VK_PRESENT_MODE_MAILBOX_KHR,
                                                VkSwapchainKHR ancestor = VK_NULL_HANDLE, VkFormat format = VK_FORMAT_R8G8B8A8_UNORM)
   {
      connection_error = false;
      auto chain = std::make_unique<wsi::x11::swapchain>(device, nullptr, &surface);
      VkSwapchainCreateInfoKHR info{};
      info.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR;
      info.surface = reinterpret_cast<VkSurfaceKHR>(1);
      info.minImageCount = 4; info.imageFormat = format;
      info.imageExtent = {64, 64}; info.imageArrayLayers = 1;
      info.imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;
      info.presentMode = mode; info.oldSwapchain = ancestor;
      if (deferred) info.flags = VK_SWAPCHAIN_CREATE_DEFERRED_MEMORY_ALLOCATION_BIT_EXT;
      require(chain->init(handle<VkDevice>(), &info) == VK_SUCCESS, "swapchain init");
      return chain;
   }
};
}

extern "C" {
void AHardwareBuffer_release(AHardwareBuffer *) {}
int AHardwareBuffer_sendHandleToUnixSocket(AHardwareBuffer *, int) { return 0; }
uint32_t xcb_generate_id(xcb_connection_t *) { return ++next_handle; }
int xcb_flush(xcb_connection_t *) { return 1; }
int xcb_get_file_descriptor(xcb_connection_t *) { return xcb_fd; }
int xcb_connection_has_error(xcb_connection_t *) { return connection_error ? 1 : 0; }
xcb_special_event_t *xcb_register_for_special_xge(xcb_connection_t *, xcb_extension_t *, uint32_t, uint32_t *)
{ return reinterpret_cast<xcb_special_event_t *>(1); }
void xcb_unregister_for_special_event(xcb_connection_t *, xcb_special_event_t *) {}
xcb_generic_event_t *xcb_poll_for_special_event(xcb_connection_t *, xcb_special_event_t *)
{
   std::lock_guard<std::mutex> lock(events_lock);
   if (events.empty()) return nullptr;
   auto event = events.front(); events.pop_front();
   uint64_t wakeup; (void)read(xcb_fd, &wakeup, sizeof(wakeup));
   return event;
}
xcb_void_cookie_t xcb_present_select_input(xcb_connection_t *, uint32_t, xcb_window_t, uint32_t) { return {1}; }
xcb_generic_error_t *xcb_request_check(xcb_connection_t *, xcb_void_cookie_t) { return nullptr; }
void xcb_discard_reply(xcb_connection_t *, unsigned int) {}
xcb_void_cookie_t xcb_free_pixmap(xcb_connection_t *, xcb_pixmap_t) { return {1}; }
xcb_void_cookie_t xcb_dri3_pixmap_from_buffers_checked(xcb_connection_t *, xcb_pixmap_t, xcb_window_t,
   uint8_t, uint16_t, uint16_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t,
   uint32_t, uint32_t, uint8_t, uint8_t, uint64_t, const int32_t *buffers)
{ const char ack = 1; require(write(buffers[0], &ack, 1) == 1, "mock DRI3 handshake"); close(buffers[0]); return {1}; }
xcb_void_cookie_t xcb_present_pixmap_checked(xcb_connection_t *, xcb_window_t, xcb_pixmap_t pixmap, uint32_t serial,
   xcb_xfixes_region_t, xcb_xfixes_region_t, int16_t, int16_t, xcb_randr_crtc_t,
   xcb_sync_fence_t, xcb_sync_fence_t, uint32_t, uint64_t, uint64_t, uint64_t, uint32_t, const xcb_present_notify_t *)
{ require(gpu_complete, "X11 consumed an unfinished frame");
  last_present_pixmap = pixmap; last_present_serial = serial; ++presents; return {1}; }
}

int main()
{
   try {
      xcb_fd = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
      require(xcb_fd >= 0, "mock XCB fd");
      fixture f;
      // The advertised format must agree with every image actually created.
      uint32_t format_count = 0;
      require(f.surface.get_properties().get_surface_formats(physical_handle, &format_count, nullptr, nullptr) == VK_SUCCESS &&
              format_count == 2, "surface format count");
      VkSurfaceFormatKHR formats[2]{};
      require(f.surface.get_properties().get_surface_formats(physical_handle, &format_count, formats, nullptr) == VK_SUCCESS &&
              std::any_of(std::begin(formats), std::end(formats), [](auto format) { return format.format == VK_FORMAT_R8G8B8A8_UNORM; }) &&
              std::any_of(std::begin(formats), std::end(formats), [](auto format) { return format.format == VK_FORMAT_B8G8R8A8_UNORM; }),
              "surface format declaration mismatch");
      require(formats[0].format == VK_FORMAT_R8G8B8A8_UNORM, "RGBA direct path is not preferred");
      {
         auto chain = f.create(false);
         require(image_creates == 4 && allocations == 4, "eager allocation replaced an image");
      }
      require(live_images.empty() && image_creates == image_destroys && allocations == frees, "eager image leak");
      {
         auto chain = f.create(true);
         const unsigned before = image_creates;
         uint32_t image_count = 4;
         VkImage exposed_images[4]{};
         require(chain->get_swapchain_images(&image_count, exposed_images) == VK_SUCCESS, "deferred handles not exposed");
         for (uint32_t i = 0; i < image_count; ++i)
         {
            uint32_t acquired = UINT32_MAX;
            require(chain->acquire_next_image(UINT64_MAX, VK_NULL_HANDLE, VK_NULL_HANDLE, &acquired) == VK_SUCCESS,
                    "deferred acquisition failed");
            require(chain->m_swapchain_images[acquired].image == exposed_images[acquired],
                    "acquisition changed an already exposed VkImage handle");
         }
         require(image_creates == before, "deferred allocation replaced an exposed handle");
         // Exercise the retained pNext after allocation returned and its stack was reused.
         volatile char overwrite_stack[16384]{}; (void)overwrite_stack;
         VkImage alias{};
         require(chain->create_aliased_image_handle(&alias) == VK_SUCCESS, "alias image creation");
         destroy_image(nullptr, alias, nullptr);
      }
      require(live_images.empty() && image_creates == image_destroys && allocations == frees, "deferred image leak");
      {
         auto chain = f.create(true);
         const VkImage exposed = chain->m_swapchain_images[0].image;
         fail_allocation = true;
         require(chain->allocate_and_bind_swapchain_image(chain->m_image_create_info, chain->m_swapchain_images[0]) ==
                 VK_ERROR_OUT_OF_DEVICE_MEMORY, "allocation failure not propagated");
         fail_allocation = false;
         require(chain->m_swapchain_images[0].image == exposed && !chain->m_swapchain_images[0].data &&
                 chain->get_error_state() == VK_ERROR_OUT_OF_DEVICE_MEMORY,
                 "failed deferred allocation invalidated an exposed image or left the chain reusable");
      }
      require(live_images.empty() && allocations == frees, "failure cleanup leak");
      {
         auto chain = f.create(false);
         gpu_complete = false; submitted = waiting_for_current_frame = false;
         const unsigned before = presents;
         VkPresentInfoKHR info{}; info.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
         wsi::swapchain_presentation_parameters params{};
         params.handle_present_frame_boundary_event = false;
         auto result = std::async(std::launch::async, [&] { return chain->queue_present(handle<VkQueue>(), &info, params); });
         {
            std::unique_lock<std::mutex> lock(fence_lock);
            require(fence_condition.wait_for(lock, std::chrono::seconds(1), [] { return waiting_for_current_frame; }),
                    "MAILBOX did not wait for this frame's fence");
            require(presents == before, "MAILBOX presented before the fence completed");
            gpu_complete = true;
         }
         fence_condition.notify_all();
         require(result.get() == VK_SUCCESS && presents == before + 1, "MAILBOX submission failed");
         // No Complete/Idle event will ever arrive: destruction must interrupt poll.
         auto started = std::chrono::steady_clock::now(); chain.reset();
         require(std::chrono::steady_clock::now() - started < std::chrono::milliseconds(500),
                 "destroy blocked waiting for an absent X11 event");
      }
      {
         auto chain = f.create(false);
         VkPresentInfoKHR info{};
         wsi::swapchain_presentation_parameters params{}; params.handle_present_frame_boundary_event = false;
         require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "disconnect test present");
         connection_error = true;
         const uint64_t wakeup = 1; require(write(xcb_fd, &wakeup, sizeof(wakeup)) == sizeof(wakeup), "wake connection error");
         auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
         for (;;) {
            { std::lock_guard<std::mutex> lock(chain->m_thread_status_lock);
              if (!chain->m_present_event_thread_run) break; }
            require(std::chrono::steady_clock::now() < deadline, "event thread did not exit on connection error");
            std::this_thread::yield();
         }
         // Already-exited threads must still be joined, otherwise std::terminate runs.
         chain.reset();
         uint64_t wakeup_value; (void)read(xcb_fd, &wakeup_value, sizeof(wakeup_value));
      }
      {
         auto chain = f.create(false, VK_PRESENT_MODE_FIFO_KHR);
         VkPresentInfoKHR info{};
         wsi::swapchain_presentation_parameters params{}; params.handle_present_frame_boundary_event = false;
         const unsigned before = presents;
         require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "FIFO test present");
         auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
         while (presents == before)
         {
            require(std::chrono::steady_clock::now() < deadline, "FIFO worker did not present");
            std::this_thread::yield();
         }
         auto started = std::chrono::steady_clock::now(); chain.reset();
         require(std::chrono::steady_clock::now() - started < std::chrono::milliseconds(750),
                 "FIFO destroy blocked waiting for a Present completion");
      }
      // X11 can emit Idle before Complete. Recreate the chain after the image
      // became FREE, while the FIFO presenter is still waiting on its data.
      for (unsigned iteration = 0; iteration < 12; ++iteration)
      {
         auto old_chain = f.create(false, VK_PRESENT_MODE_FIFO_KHR);
         VkPresentInfoKHR info{};
         wsi::swapchain_presentation_parameters params{}; params.handle_present_frame_boundary_event = false;
         const unsigned before = presents;
         require(old_chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "old chain present");
         auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
         while (presents == before)
         {
            require(std::chrono::steady_clock::now() < deadline, "old chain did not present");
            std::this_thread::yield();
         }
         auto idle = static_cast<xcb_present_idle_notify_event_t *>(calloc(1, sizeof(xcb_present_idle_notify_event_t)));
         idle->event_type = XCB_PRESENT_EVENT_IDLE_NOTIFY; idle->pixmap = last_present_pixmap;
         deliver_event(reinterpret_cast<xcb_generic_event_t *>(idle));
         for (;;)
         {
            { std::lock_guard<std::mutex> lock(old_chain->m_thread_status_lock);
              if (old_chain->m_free_buffer_pool.size()) break; }
            require(std::chrono::steady_clock::now() < deadline, "old chain did not receive Idle");
            std::this_thread::yield();
         }
         uint64_t timeout = 0;
         require(old_chain->get_free_buffer(&timeout) == VK_SUCCESS, "Idle did not free the old image");
         require(old_chain->m_swapchain_images[0].status == wsi::swapchain_image::FREE, "old image not FREE");

         // Deterministically hold the same lock used by the event worker while
         // it reads image data. deprecate must not destroy it under this lock.
         std::unique_lock<std::mutex> event_access(old_chain->m_thread_status_lock);
         auto replacement = std::async(std::launch::async, [&] {
            return f.create(true, VK_PRESENT_MODE_MAILBOX_KHR, reinterpret_cast<VkSwapchainKHR>(old_chain.get()));
         });
         require(replacement.wait_for(std::chrono::milliseconds(20)) == std::future_status::timeout,
                 "oldSwapchain deprecate freed data concurrently with the event worker");
         event_access.unlock();
         require(replacement.wait_for(std::chrono::seconds(1)) == std::future_status::ready,
                 "oldSwapchain lock order deadlocked");
         auto new_chain = replacement.get();
         require(old_chain->m_swapchain_images[0].data == nullptr, "deprecate did not retire the FREE image");
         new_chain.reset(); old_chain.reset();
      }
      {
         const unsigned before_images = image_creates, before_allocations = allocations;
         auto chain = f.create(false, VK_PRESENT_MODE_MAILBOX_KHR, VK_NULL_HANDLE, VK_FORMAT_B8G8R8A8_UNORM);
         require(image_creates == before_images + 8 && allocations == before_allocations + 8,
                 "BGRA must use separate render and AHB images");
         VkImage alias{};
         require(chain->create_aliased_image_handle(&alias) == VK_SUCCESS, "BGRA alias contract failed");
         destroy_image(nullptr, alias, nullptr);
         VkPresentInfoKHR info{}; VkSemaphore client_wait = handle<VkSemaphore>();
         info.waitSemaphoreCount = 1; info.pWaitSemaphores = &client_wait;
         wsi::swapchain_presentation_parameters params{};
         params.handle_present_frame_boundary_event = false; params.use_image_present_semaphore = false;
         const unsigned before_blits = blits_recorded, before_submits = conversion_submits;
         require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "BGRA present failed");
         require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "BGRA repeat present failed");
         require(blits_recorded == before_blits + 2 && conversion_submits == before_submits + 2,
                 "BGRA conversion was not part of the fenced submission");
      }
      {
         auto chain = f.create(true, VK_PRESENT_MODE_MAILBOX_KHR, VK_NULL_HANDLE, VK_FORMAT_B8G8R8A8_UNORM);
         const unsigned before = image_creates;
         const VkImage exposed = chain->m_swapchain_images[0].image;
         require(chain->allocate_and_bind_swapchain_image(chain->m_image_create_info, chain->m_swapchain_images[0]) == VK_SUCCESS &&
                 chain->m_swapchain_images[0].image == exposed && image_creates == before + 1,
                 "BGRA deferred binding replaced the exposed render image");
         fail_command_allocation = true;
         require(chain->allocate_and_bind_swapchain_image(chain->m_image_create_info, chain->m_swapchain_images[1]) ==
                 VK_ERROR_OUT_OF_HOST_MEMORY, "BGRA command allocation failure not propagated");
         fail_command_allocation = false;
      }
      require(pools_created == pools_destroyed && live_images.empty() && allocations == frees,
              "BGRA conversion failure/lifetime leaked resources");
      for (unsigned i = 0; i < 25; ++i) { auto chain = f.create(true); }
      require(live_images.empty() && image_creates == image_destroys && allocations == frees, "final resource imbalance");
      close(xcb_fd);
      std::cout << "WSI_REGRESSION_OK: eager/deferred/alias/failure/MAILBOX/FIFO/cancel/disconnect/oldSwapchain/BGRA/immediate-destroy\n";
      return 0;
   } catch (const std::exception &error) {
      std::cerr << "WSI_REGRESSION_FAILED: " << error.what() << '\n'; return 1;
   }
}
