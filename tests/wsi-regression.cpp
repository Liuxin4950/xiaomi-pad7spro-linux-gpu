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
unsigned pools_created, pools_destroyed, blits_recorded, conversion_submits, blit_rects;
std::map<VkImage, VkFormat> image_formats;
std::map<VkCommandBuffer, VkCommandBufferUsageFlags> command_flags;
std::map<VkCommandBuffer, VkImageLayout> command_initial_layout;
std::map<VkCommandBuffer, VkImage> command_destination;
std::set<VkCommandBuffer> submitted_commands;
std::set<VkImage> initialized_presentation_images;
using pixels = std::array<uint32_t, 64 * 64>;
std::map<VkImage, pixels> image_pixels;
std::map<VkCommandBuffer, VkImage> command_source;
std::map<VkCommandBuffer, std::vector<VkRect2D>> command_rects;
std::map<xcb_pixmap_t, VkImage> pixmap_images;
VkImage exported_image{};
std::map<VkDeviceMemory, VkImage> memory_images;
pixels expected_pixels{};
bool verify_pixels = false;
bool verify_downstream = false;
std::map<xcb_xfixes_region_t, std::vector<xcb_rectangle_t>> update_regions;
pixels downstream_pixels{};
uint64_t downstream_copy_pixels = 0;
unsigned downstream_region_requests = 0;
std::array<uint32_t, 3> clock_capability{};
bool malformed_clock = false;
std::atomic<uint64_t> last_target_msc{0};
unsigned partial_submits;
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
   live_images.insert(*image); image_formats[*image] = info->format; image_pixels[*image] = {}; ++image_creates;
   return VK_SUCCESS;
}
VKAPI_ATTR void VKAPI_CALL destroy_image(VkDevice, VkImage image, const VkAllocationCallbacks *)
{
   require(live_images.erase(image) == 1, "image leaked, replaced or destroyed twice");
   image_formats.erase(image); image_pixels.erase(image); ++image_destroys;
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
   *memory = handle<VkDeviceMemory>();
   if (info->allocationSize == 0) {
      auto export_info = static_cast<const VkExportMemoryAllocateInfo *>(info->pNext);
      auto dedicated = static_cast<const VkMemoryDedicatedAllocateInfo *>(export_info->pNext);
      memory_images[*memory] = dedicated->image;
   }
   ++allocations; return VK_SUCCESS;
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
VKAPI_ATTR VkResult VKAPI_CALL begin_command(VkCommandBuffer command, const VkCommandBufferBeginInfo *info)
{
   command_flags[command] = info->flags;
   submitted_commands.erase(command);
   return VK_SUCCESS;
}
VKAPI_ATTR VkResult VKAPI_CALL end_command(VkCommandBuffer) { return VK_SUCCESS; }
VKAPI_ATTR void VKAPI_CALL pipeline_barrier(VkCommandBuffer command, VkPipelineStageFlags, VkPipelineStageFlags,
   VkDependencyFlags, uint32_t, const VkMemoryBarrier *, uint32_t, const VkBufferMemoryBarrier *,
   uint32_t count, const VkImageMemoryBarrier *barriers)
{
   require(count == 2 && image_formats[barriers[0].image] == VK_FORMAT_B8G8R8A8_UNORM &&
           image_formats[barriers[1].image] == VK_FORMAT_R8G8B8A8_UNORM, "conversion barriers target wrong images");
   if (barriers[0].oldLayout == VK_IMAGE_LAYOUT_PRESENT_SRC_KHR) {
      command_initial_layout[command] = barriers[1].oldLayout;
      command_destination[command] = barriers[1].image;
      require((barriers[1].oldLayout == VK_IMAGE_LAYOUT_UNDEFINED &&
               barriers[1].srcQueueFamilyIndex == VK_QUEUE_FAMILY_IGNORED) ||
              (barriers[1].oldLayout == VK_IMAGE_LAYOUT_GENERAL &&
               barriers[1].srcQueueFamilyIndex == VK_QUEUE_FAMILY_FOREIGN_EXT &&
               barriers[1].dstQueueFamilyIndex == 0), "cached command lost AHB ownership acquisition");
   }
}
VKAPI_ATTR void VKAPI_CALL blit_image(VkCommandBuffer command, VkImage source, VkImageLayout source_layout,
   VkImage destination, VkImageLayout destination_layout, uint32_t count, const VkImageBlit *blits, VkFilter filter)
{ require(image_formats[source] == VK_FORMAT_B8G8R8A8_UNORM && image_formats[destination] == VK_FORMAT_R8G8B8A8_UNORM &&
          source_layout == VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL && destination_layout == VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL &&
          count >= 1 && count <= wsi::present_damage::MAX_RECTS && filter == VK_FILTER_NEAREST,
          "BGRA conversion lost the real format contract");
  for (uint32_t i = 0; i < count; ++i)
     require(blits[i].srcOffsets[0].x == blits[i].dstOffsets[0].x && blits[i].srcOffsets[0].y == blits[i].dstOffsets[0].y &&
             blits[i].srcOffsets[0].x >= 0 && blits[i].srcOffsets[0].y >= 0 &&
             blits[i].srcOffsets[1].x <= 64 && blits[i].srcOffsets[1].y <= 64 &&
             blits[i].srcOffsets[0].x < blits[i].srcOffsets[1].x && blits[i].srcOffsets[0].y < blits[i].srcOffsets[1].y,
             "copy rect out of image bounds or degenerate");
  command_source[command] = source;
  auto &rects = command_rects[command]; rects.clear();
  for (uint32_t i = 0; i < count; ++i)
     rects.push_back({{blits[i].srcOffsets[0].x, blits[i].srcOffsets[0].y},
                     {static_cast<uint32_t>(blits[i].srcOffsets[1].x - blits[i].srcOffsets[0].x),
                      static_cast<uint32_t>(blits[i].srcOffsets[1].y - blits[i].srcOffsets[0].y)}});
  blit_rects += count; ++blits_recorded; }
VKAPI_ATTR void VKAPI_CALL copy_image(VkCommandBuffer command, VkImage source, VkImageLayout source_layout,
   VkImage destination, VkImageLayout destination_layout, uint32_t count, const VkImageCopy *copies)
{
   std::vector<VkImageBlit> blits(count);
   for (uint32_t i = 0; i < count; ++i) {
      require(copies[i].extent.depth == 1, "copy depth changed");
      blits[i].srcOffsets[0] = copies[i].srcOffset;
      blits[i].dstOffsets[0] = copies[i].dstOffset;
      blits[i].srcOffsets[1] = {copies[i].srcOffset.x + static_cast<int32_t>(copies[i].extent.width),
                              copies[i].srcOffset.y + static_cast<int32_t>(copies[i].extent.height), 1};
      blits[i].dstOffsets[1] = {copies[i].dstOffset.x + static_cast<int32_t>(copies[i].extent.width),
                              copies[i].dstOffset.y + static_cast<int32_t>(copies[i].extent.height), 1};
   }
   blit_image(command, source, source_layout, destination, destination_layout, count, blits.data(), VK_FILTER_NEAREST);
}
VKAPI_ATTR void VKAPI_CALL image_layout(VkDevice, VkImage, const VkImageSubresource *, VkSubresourceLayout *layout)
{ *layout = {}; layout->rowPitch = 64 * 4; }
VKAPI_ATTR VkResult VKAPI_CALL get_ahb(VkDevice, const VkMemoryGetAndroidHardwareBufferInfoANDROID *info, AHardwareBuffer **ahb)
{ exported_image = memory_images.at(info->memory); *ahb = reinterpret_cast<AHardwareBuffer *>(1); return VK_SUCCESS; }
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
      const auto command = info->pCommandBuffers[0];
      require(!submitted_commands.count(command) || !(command_flags[command] & VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT),
              "one-time command was submitted again without recording");
      const auto image = command_destination[command];
      require(command_initial_layout[command] == (initialized_presentation_images.count(image) ?
              VK_IMAGE_LAYOUT_GENERAL : VK_IMAGE_LAYOUT_UNDEFINED), "cached command used the wrong initial AHB layout");
      submitted_commands.insert(command);
      initialized_presentation_images.insert(image);
      for (uint32_t i = 0; i < info->waitSemaphoreCount; ++i)
         require(info->pWaitDstStageMask[i] == VK_PIPELINE_STAGE_TRANSFER_BIT, "blit did not wait for client rendering");
      unsigned pixels_copied = 0;
      for (const auto &rect : command_rects[command]) pixels_copied += rect.extent.width * rect.extent.height;
      if (pixels_copied < 64 * 64) ++partial_submits;
      for (const auto &rect : command_rects[command])
         for (uint32_t y = rect.offset.y; y < rect.offset.y + rect.extent.height; ++y)
            for (uint32_t x = rect.offset.x; x < rect.offset.x + rect.extent.width; ++x)
               image_pixels[image][y * 64 + x] = image_pixels[command_source[command]][y * 64 + x];
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
   PROC(CmdPipelineBarrier, pipeline_barrier); PROC(CmdBlitImage, blit_image); PROC(CmdCopyImage, copy_image);
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
xcb_get_geometry_cookie_t xcb_get_geometry(xcb_connection_t *, xcb_drawable_t) { return {1}; }
xcb_get_geometry_reply_t *xcb_get_geometry_reply(xcb_connection_t *, xcb_get_geometry_cookie_t, xcb_generic_error_t **) {
   auto r = static_cast<xcb_get_geometry_reply_t *>(calloc(1, sizeof(xcb_get_geometry_reply_t)));
   r->root = 99; return r;
}
xcb_intern_atom_cookie_t xcb_intern_atom(xcb_connection_t *, uint8_t, uint16_t, const char *) { return {1}; }
xcb_intern_atom_reply_t *xcb_intern_atom_reply(xcb_connection_t *, xcb_intern_atom_cookie_t, xcb_generic_error_t **) {
   auto r = static_cast<xcb_intern_atom_reply_t *>(calloc(1, sizeof(xcb_intern_atom_reply_t)));
   r->atom = clock_capability[0] ? 100 : 0; return r;
}
xcb_get_property_cookie_t xcb_get_property(xcb_connection_t *, uint8_t, xcb_window_t root, xcb_atom_t,
                                         xcb_atom_t, uint32_t, uint32_t) {
   require(root == 99, "clock queried on wrong root"); return {1};
}
xcb_get_property_reply_t *xcb_get_property_reply(xcb_connection_t *, xcb_get_property_cookie_t, xcb_generic_error_t **) {
   auto r = static_cast<xcb_get_property_reply_t *>(calloc(1, sizeof(xcb_get_property_reply_t) + 12));
   r->type = XCB_ATOM_CARDINAL; r->format = 32; r->value_len = malformed_clock ? 2 : 3;
   memcpy(r+1, clock_capability.data(), 12); return r;
}
xcb_void_cookie_t xcb_present_select_input(xcb_connection_t *, uint32_t, xcb_window_t, uint32_t) { return {1}; }
xcb_generic_error_t *xcb_request_check(xcb_connection_t *, xcb_void_cookie_t) { return nullptr; }
void xcb_discard_reply(xcb_connection_t *, unsigned int) {}
xcb_void_cookie_t xcb_free_pixmap(xcb_connection_t *, xcb_pixmap_t pixmap) { pixmap_images.erase(pixmap); return {1}; }
xcb_void_cookie_t xcb_dri3_pixmap_from_buffers_checked(xcb_connection_t *, xcb_pixmap_t pixmap, xcb_window_t,
   uint8_t, uint16_t, uint16_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t,
   uint32_t, uint32_t, uint8_t, uint8_t, uint64_t, const int32_t *buffers)
{ pixmap_images[pixmap] = exported_image; const char ack = 1; require(write(buffers[0], &ack, 1) == 1, "mock DRI3 handshake"); close(buffers[0]); return {1}; }
xcb_void_cookie_t xcb_xfixes_create_region_checked(xcb_connection_t *, xcb_xfixes_region_t region, uint32_t, const xcb_rectangle_t *) {
   update_regions[region] = {}; return {1};
}
xcb_void_cookie_t xcb_xfixes_set_region(xcb_connection_t *, xcb_xfixes_region_t region, uint32_t count, const xcb_rectangle_t *rects) {
   update_regions.at(region).assign(rects, rects + count); return {1};
}
xcb_void_cookie_t xcb_xfixes_destroy_region(xcb_connection_t *, xcb_xfixes_region_t region) {
   require(update_regions.erase(region) == 1, "update region leaked/destroyed twice"); return {1};
}
xcb_void_cookie_t xcb_present_pixmap_checked(xcb_connection_t *, xcb_window_t, xcb_pixmap_t pixmap, uint32_t serial,
   xcb_xfixes_region_t, xcb_xfixes_region_t update, int16_t, int16_t, xcb_randr_crtc_t,
   xcb_sync_fence_t, xcb_sync_fence_t, uint32_t, uint64_t target, uint64_t, uint64_t, uint32_t, const xcb_present_notify_t *)
{ require(gpu_complete, "X11 consumed an unfinished frame");
  if (verify_pixels)
     require(image_pixels.at(pixmap_images.at(pixmap)) == expected_pixels,
             "rotating-buffer presentation contains stale pixels");
  if (verify_downstream) {
     const auto &source = image_pixels.at(pixmap_images.at(pixmap));
     if (!update) { downstream_pixels = source; downstream_copy_pixels += 64 * 64; }
     else {
        ++downstream_region_requests;
        for (const auto &r : update_regions.at(update))
           for (unsigned y=r.y; y<unsigned(r.y)+r.height; ++y)
              for (unsigned x=r.x; x<unsigned(r.x)+r.width; ++x) {
                 require(x < 64 && y < 64, "downstream update out of bounds");
                 downstream_pixels[y*64+x] = source[y*64+x]; ++downstream_copy_pixels;
              }
     }
     require(downstream_pixels == expected_pixels, "downstream region resurrected stale/missing pixels");
     auto complete = static_cast<xcb_present_complete_notify_event_t *>(calloc(1, sizeof(xcb_present_complete_notify_event_t)));
     complete->event_type = XCB_PRESENT_EVENT_COMPLETE_NOTIFY; complete->kind = XCB_PRESENT_COMPLETE_KIND_PIXMAP;
     complete->serial = serial; complete->msc = presents.load() + 1;
     deliver_event(reinterpret_cast<xcb_generic_event_t *>(complete));
  }
  last_target_msc = target;
  last_present_pixmap = pixmap; last_present_serial = serial; ++presents; return {1}; }
}

int main()
{
   try {
      xcb_fd = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
      require(xcb_fd >= 0, "mock XCB fd");
      fixture f;
      // Negotiation must never mistake a reported RandR rate for an enforced
      // clock, or remove a user-requested lower cap on an incompatible server.
      setenv("PAD_GPU_MAX_FPS", "60", 1);
      for (auto capability : {std::array<uint32_t,3>{0,0,0}, {2,60,3}, {1,241,3}, {1,120,3}, {1,60,1}}) {
         clock_capability = capability;
         auto chain = f.create(false);
         require(chain->m_display_clock_fps == 0, "unsafe display-clock negotiation");
      }
      clock_capability = {1,60,7}; malformed_clock = true;
      require(f.create(false)->m_display_clock_fps == 0, "malformed clock property accepted");
      malformed_clock = false;
      setenv("PAD_GPU_MAX_FPS", "0", 1);
      require(f.create(false)->m_display_clock_fps == 0, "explicit uncapped WSI contract changed");
      setenv("PAD_GPU_MAX_FPS", "60", 1);
      setenv("PAD_GPU_PRESENT_CLOCK", "timer", 1);
      require(f.create(false)->m_display_clock_fps == 0, "timer rollback ignored");
      unsetenv("PAD_GPU_PRESENT_CLOCK");
      {
         auto chain = f.create(false);
         require(chain->m_display_clock_fps == 60, "cooperating display clock not selected");
         // A far-future timer must have no effect in negotiated mode.
         chain->m_next_present = std::chrono::steady_clock::now() + std::chrono::hours(1);
         VkPresentInfoKHR info{};
         wsi::swapchain_presentation_parameters params{};
         params.handle_present_frame_boundary_event = false;
         require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "first paced present");
         const auto serial = last_present_serial.load(), pixmap = last_present_pixmap.load();
         const auto before = presents.load();
         params.pending_present.image_index = 1;
         auto next = std::async(std::launch::async, [&] {
            return chain->queue_present(handle<VkQueue>(), &info, params);
         });
         require(next.wait_for(std::chrono::milliseconds(30)) == std::future_status::timeout && presents == before,
                 "paced MAILBOX accumulated downstream requests");
         auto idle = static_cast<xcb_present_idle_notify_event_t *>(calloc(1, sizeof(xcb_present_idle_notify_event_t)));
         idle->event_type = XCB_PRESENT_EVENT_IDLE_NOTIFY; idle->pixmap = pixmap; idle->serial = serial;
         deliver_event(reinterpret_cast<xcb_generic_event_t *>(idle));
         require(next.wait_for(std::chrono::milliseconds(30)) == std::future_status::timeout,
                 "Idle incorrectly substituted for display completion");
         auto complete = static_cast<xcb_present_complete_notify_event_t *>(calloc(1, sizeof(xcb_present_complete_notify_event_t)));
         complete->event_type = XCB_PRESENT_EVENT_COMPLETE_NOTIFY; complete->kind = XCB_PRESENT_COMPLETE_KIND_PIXMAP;
         complete->serial = serial; complete->msc = 42;
         deliver_event(reinterpret_cast<xcb_generic_event_t *>(complete));
         require(next.wait_for(std::chrono::seconds(1)) == std::future_status::ready && next.get() == VK_SUCCESS &&
                 presents == before+1 && last_target_msc == 43, "COPY must request the next tick without an extra period");
         params.pending_present.image_index = 2;
         const auto secondSerial = last_present_serial.load();
         auto flipNext = std::async(std::launch::async, [&] {
            return chain->queue_present(handle<VkQueue>(), &info, params);
         });
         require(flipNext.wait_for(std::chrono::milliseconds(30)) == std::future_status::timeout,
                 "FLIP did not wait for its completion");
         complete = static_cast<xcb_present_complete_notify_event_t *>(calloc(1, sizeof(xcb_present_complete_notify_event_t)));
         complete->event_type = XCB_PRESENT_EVENT_COMPLETE_NOTIFY; complete->kind = XCB_PRESENT_COMPLETE_KIND_PIXMAP;
         complete->serial = secondSerial; complete->msc = 43; complete->mode = XCB_PRESENT_COMPLETE_MODE_FLIP;
         deliver_event(reinterpret_cast<xcb_generic_event_t *>(complete));
         require(flipNext.wait_for(std::chrono::seconds(1)) == std::future_status::ready && flipNext.get() == VK_SUCCESS &&
                 last_target_msc == 44, "FLIP acquired an unnecessary second display tick");
         params.pending_present.image_index = 3;
         auto cancelled = std::async(std::launch::async, [&] {
            return chain->queue_present(handle<VkQueue>(), &info, params);
         });
         require(cancelled.wait_for(std::chrono::milliseconds(30)) == std::future_status::timeout, "missing pacing wait");
         { std::lock_guard<std::mutex> lock(chain->m_thread_status_lock);
           chain->m_present_event_thread_run = false; chain->m_thread_status_cond.notify_all(); }
         require(cancelled.wait_for(std::chrono::seconds(1)) == std::future_status::ready, "display wait cannot cancel");
         cancelled.get(); chain.reset();
      }
      {
         auto chain = f.create(false);
         VkPresentInfoKHR info{};
         wsi::swapchain_presentation_parameters params{}; params.handle_present_frame_boundary_event = false;
         require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "skip fallback present");
         auto complete = static_cast<xcb_present_complete_notify_event_t *>(calloc(1, sizeof(xcb_present_complete_notify_event_t)));
         complete->event_type = XCB_PRESENT_EVENT_COMPLETE_NOTIFY; complete->kind = XCB_PRESENT_COMPLETE_KIND_PIXMAP;
         complete->serial = last_present_serial; complete->msc = 50; complete->mode = XCB_PRESENT_COMPLETE_MODE_SKIP;
         deliver_event(reinterpret_cast<xcb_generic_event_t *>(complete));
         auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
         for (;;) {
            { std::lock_guard<std::mutex> lock(chain->m_thread_status_lock);
              if (!chain->m_display_clock_fps) break; }
            require(std::chrono::steady_clock::now() < deadline, "SKIP did not restore bounded timer pacing");
            std::this_thread::yield();
         }
      }
      {
         auto chain = f.create(false);
         VkPresentInfoKHR info{}; wsi::swapchain_presentation_parameters params{};
         params.handle_present_frame_boundary_event = false;
         require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "resume clock first present");
         auto deliverComplete = [&](uint8_t mode, uint64_t msc) {
            auto *event = static_cast<xcb_present_complete_notify_event_t *>(calloc(1,sizeof(xcb_present_complete_notify_event_t)));
            event->event_type=XCB_PRESENT_EVENT_COMPLETE_NOTIFY;event->kind=XCB_PRESENT_COMPLETE_KIND_PIXMAP;
            event->serial=last_present_serial;event->mode=mode;event->msc=msc;
            deliver_event(reinterpret_cast<xcb_generic_event_t *>(event));
         };
         deliverComplete(XCB_PRESENT_COMPLETE_MODE_SKIP, 60);
         auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(1);
         for (;;) {
            { std::lock_guard<std::mutex> lock(chain->m_thread_status_lock); if(!chain->m_display_clock_fps)break; }
            require(std::chrono::steady_clock::now()<deadline,"resume SKIP fallback");std::this_thread::yield();
         }
         params.pending_present.image_index=1;
         require(chain->queue_present(handle<VkQueue>(), &info, params)==VK_SUCCESS,"timer fallback present");
         deliverComplete(XCB_PRESENT_COMPLETE_MODE_COPY,61);
         deadline=std::chrono::steady_clock::now()+std::chrono::seconds(1);
         for (;;) {
            { std::lock_guard<std::mutex> lock(chain->m_thread_status_lock);
              if(chain->m_display_clock_fps==60) { require(chain->m_target_msc==62,"recovery added extra target tick");break; } }
            require(std::chrono::steady_clock::now()<deadline,"successful COPY did not recover negotiated clock");std::this_thread::yield();
         }
      }
      clock_capability = {}; unsetenv("PAD_GPU_MAX_FPS");
      // A spurious condition notification must not consume a semaphore token.
      {
         util::timed_semaphore semaphore;
         require(semaphore.init(0) == VK_SUCCESS, "semaphore init");
         auto waiter = std::async(std::launch::async, [&] { return semaphore.wait(UINT64_MAX); });
         std::this_thread::sleep_for(std::chrono::milliseconds(10));
         pthread_mutex_lock(&semaphore.m_mutex);
         pthread_cond_broadcast(&semaphore.m_cond);
         pthread_mutex_unlock(&semaphore.m_mutex);
         require(waiter.wait_for(std::chrono::milliseconds(30)) == std::future_status::timeout,
                 "spurious wake consumed a token");
         semaphore.post();
         require(waiter.get() == VK_SUCCESS && semaphore.wait(0) == VK_NOT_READY,
                 "semaphore token accounting changed");
      }
      // Shutdown must wake an idle FIFO worker, without a periodic timeout.
      {
         auto chain = f.create(false, VK_PRESENT_MODE_FIFO_KHR);
         std::this_thread::sleep_for(std::chrono::milliseconds(20));
         auto started = std::chrono::steady_clock::now();
         chain.reset();
         require(std::chrono::steady_clock::now() - started < std::chrono::milliseconds(100),
                 "idle FIFO shutdown did not explicitly wake the worker");
      }
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
         const unsigned before_images = image_creates, before_allocations = allocations;
         auto chain = f.create(false);
         require(image_creates == before_images + 4 && allocations == before_allocations + 4,
                 "eager allocation replaced an image");
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
      // Complete is also allowed to precede Idle. After all other buffers are
      // acquired, the event worker must keep listening for the final release.
      {
         auto chain = f.create(false);
         uint32_t index;
         require(chain->acquire_next_image(UINT64_MAX, VK_NULL_HANDLE, VK_NULL_HANDLE, &index) == VK_SUCCESS && index == 0,
                 "Complete-before-Idle initial acquire");
         VkPresentInfoKHR info{};
         wsi::swapchain_presentation_parameters params{}; params.handle_present_frame_boundary_event = false;
         require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "Complete-before-Idle present");
         for (unsigned i=0; i<3; ++i)
            require(chain->acquire_next_image(UINT64_MAX, VK_NULL_HANDLE, VK_NULL_HANDLE, &index) == VK_SUCCESS,
                    "Complete-before-Idle acquire remaining buffers");
         auto complete = static_cast<xcb_present_complete_notify_event_t *>(calloc(1, sizeof(xcb_present_complete_notify_event_t)));
         complete->event_type = XCB_PRESENT_EVENT_COMPLETE_NOTIFY;
         complete->kind = XCB_PRESENT_COMPLETE_KIND_PIXMAP;
         complete->serial = last_present_serial;
         complete->msc = 42;
         deliver_event(reinterpret_cast<xcb_generic_event_t *>(complete));
         const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
         for (;;) {
            { std::lock_guard<std::mutex> lock(chain->m_thread_status_lock);
              if (chain->m_last_present_msc == 42) break; }
            require(std::chrono::steady_clock::now() < deadline, "Complete notification not consumed");
            std::this_thread::yield();
         }
         std::this_thread::sleep_for(std::chrono::milliseconds(20));
         auto idle = static_cast<xcb_present_idle_notify_event_t *>(calloc(1, sizeof(xcb_present_idle_notify_event_t)));
         idle->event_type = XCB_PRESENT_EVENT_IDLE_NOTIFY;
         idle->pixmap = last_present_pixmap;
         idle->serial = last_present_serial;
         deliver_event(reinterpret_cast<xcb_generic_event_t *>(idle));
         uint64_t timeout = UINT64_C(500000000);
         require(chain->get_free_buffer(&timeout) == VK_SUCCESS,
                 "Complete-before-Idle was ignored: buffer acquisition blocked");
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
         for (unsigned i = 0; i < 8; ++i)
            require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "BGRA cached present failed");
         const char *reuse = std::getenv("PAD_GPU_WSI_REUSE_COMMANDS");
         const unsigned expected_recordings = reuse && !strcmp(reuse, "0") ? 10 : 2;
         require(blits_recorded == before_blits + expected_recordings && conversion_submits == before_submits + 10,
                 "BGRA caching changed copy submissions or re-recorded steady commands");
      }
      // The public Vulkan contract: rectangleCount == 0 means full damage.
      // Exercise the exact parser used by vkQueuePresentKHR, not a test-only flag.
      {
         VkPresentRegionKHR region{};
         require(wsi::present_damage::from_region(region).status == wsi::present_damage::UNKNOWN,
                 "empty region list must be full damage");
         VkRectLayerKHR rect{{4, 8}, {1, 1}, 0};
         region = {1, &rect};
         require(wsi::present_damage::from_region(region).status == wsi::present_damage::RECTS,
                 "valid rect was discarded");
         region.pRectangles = nullptr;
         require(wsi::present_damage::from_region(region).status == wsi::present_damage::UNKNOWN, "null rect fallback");
         region = {wsi::present_damage::MAX_RECTS + 1, &rect};
         require(wsi::present_damage::from_region(region).status == wsi::present_damage::UNKNOWN, "overflow fallback");
         region = {1, &rect}; rect.layer = 1;
         require(wsi::present_damage::from_region(region).status == wsi::present_damage::UNKNOWN, "unsupported layer fallback");
      }
      // Independent pixel oracle: each source contains the complete desired
      // frame; damage only covers changes relative to the previous present.
      // Cycling four AHBs must never resurrect a pixel from an older frame.
      // Check both the color-converting blit and live Xorg BGRA byte-copy path.
      for (bool byte_copy : {false, true}) {
         if (byte_copy) setenv("PAD_GPU_X11_COLOR_MODE", "bgra", 1);
         else unsetenv("PAD_GPU_X11_COLOR_MODE");
         auto chain = f.create(false, VK_PRESENT_MODE_MAILBOX_KHR, VK_NULL_HANDLE, VK_FORMAT_B8G8R8A8_UNORM);
         VkPresentInfoKHR info{};
         wsi::swapchain_presentation_parameters params{};
         params.handle_present_frame_boundary_event = false;
         params.use_image_present_semaphore = false;
         expected_pixels.fill(0); verify_pixels = true;
         for (unsigned i = 0; i < 4; ++i) {
            params.pending_present.image_index = i;
            image_pixels[chain->m_swapchain_images[i].image] = expected_pixels;
            require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "pixel prime failed");
         }
         auto &damage = params.pending_present.damage;
         const unsigned before_partial = partial_submits;
         for (unsigned frame = 0; frame < 32; ++frame) {
            const unsigned index = frame % 4, x = 4 + frame, y = 8;
            expected_pixels[y * 64 + x] = 0xff000000u | (frame + 1);
            image_pixels[chain->m_swapchain_images[index].image] = expected_pixels;
            params.pending_present.image_index = index;
            damage.status = wsi::present_damage::RECTS;
            damage.rect_count = 1; damage.rects[0] = {{static_cast<int32_t>(x), static_cast<int32_t>(y)}, {1, 1}};
            require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "pixel rotation failed");
         }
         require(partial_submits >= before_partial + 28, "small updates lost the partial-copy optimization");
         // A full update on an empty list must copy AND present each new color,
         // even after all four buffers have been initialized.
         const unsigned before_full = conversion_submits, before_presents = presents;
         for (unsigned frame = 0; frame < 8; ++frame) {
            const unsigned index = frame % 4;
            params.pending_present.image_index = index;
            expected_pixels.fill(0xff000100u | frame);
            image_pixels[chain->m_swapchain_images[index].image] = expected_pixels;
            damage = wsi::present_damage::from_region(VkPresentRegionKHR{});
            require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "empty-list present failed");
         }
         require(conversion_submits == before_full + 8 && presents == before_presents + 8,
                 "empty-list full updates were skipped");
         // Overflow, degenerate and out-of-bounds hints must preserve new pixels.
         for (unsigned kind = 0; kind < 4; ++kind) {
            params.pending_present.image_index = kind;
            expected_pixels.fill(0xff002000u | kind);
            image_pixels[chain->m_swapchain_images[kind].image] = expected_pixels;
            damage.status = wsi::present_damage::RECTS;
            damage.rect_count = kind == 0 ? wsi::present_damage::MAX_RECTS + 1 : 1;
            damage.rects[0] = kind == 1 ? VkRect2D{{0,0},{0,0}} :
                             kind == 2 ? VkRect2D{{-1,0},{2,2}} : VkRect2D{{63,0},{2,2}};
            require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "invalid-hint fallback failed");
         }
         // Overlapping old/new moving-bar regions across four AHBs must be
         // coalesced before measuring area; raw counts would force full copies.
         expected_pixels.fill(0);
         for (unsigned y=16; y<48; ++y)
            for (unsigned x=0; x<16; ++x) expected_pixels[y*64+x] = 0xff112233;
         for (unsigned index=0; index<4; ++index) {
            params.pending_present.image_index = index;
            image_pixels[chain->m_swapchain_images[index].image] = expected_pixels;
            damage = {};
            require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "coalescing prime failed");
         }
         const unsigned before_coalescing = partial_submits;
         for (unsigned frame=0; frame<24; ++frame) {
            const unsigned index=frame%4, old_x=(frame*2)%49, x=((frame+1)*2)%49;
            expected_pixels.fill(0);
            for (unsigned y=16; y<48; ++y)
               for (unsigned px=x; px<x+16; ++px) expected_pixels[y*64+px] = 0xff112233;
            image_pixels[chain->m_swapchain_images[index].image] = expected_pixels;
            params.pending_present.image_index = index;
            damage.status = wsi::present_damage::RECTS; damage.rect_count = 2;
            damage.rects[0] = {{static_cast<int32_t>(old_x),16},{16,32}};
            damage.rects[1] = {{static_cast<int32_t>(x),16},{16,32}};
            require(chain->queue_present(handle<VkQueue>(), &info, params) == VK_SUCCESS, "coalescing motion failed");
         }
         require(partial_submits >= before_coalescing + 20,
                 "overlapping damage forced unnecessary full copies");
         verify_pixels = false;
      }
      // The oracle applies the actual X11 update region to a separate consumer
      // image. Valid AHB pixels alone cannot detect a lost downstream update.
      clock_capability = {1, 60, 15}; setenv("PAD_GPU_MAX_FPS", "60", 1);
      for (bool byte_copy : {false, true}) {
         if (byte_copy) setenv("PAD_GPU_X11_COLOR_MODE", "bgra", 1);
         else unsetenv("PAD_GPU_X11_COLOR_MODE");
         auto chain = f.create(false, VK_PRESENT_MODE_MAILBOX_KHR, VK_NULL_HANDLE, VK_FORMAT_B8G8R8A8_UNORM);
         require(chain->m_region_present && chain->m_update_region, "consumer repair not negotiated");
         // Synthetic history exercises skips, future payloads, overflow and
         // invalid hints without depending on a specific FIFO thread schedule.
         auto &history = chain->m_damage_history;
         wsi::present_damage d{}; d.status=wsi::present_damage::RECTS; d.rect_count=1;
         d.rects[0]={{1,1},{1,1}}; history[2]={2,d};
         d.rects[0]={{3,1},{1,1}}; history[3]={3,d};
         d.rects[0]={{5,1},{1,1}}; history[4]={4,d};
         chain->m_last_update_sequence=1;
         require(chain->damage_since(3).rect_count==2, "skipped payload damage not unioned");
         chain->m_last_update_sequence=3;
         require(chain->damage_since(4).rect_count==1, "future payload damage consumed by older present");
         require(chain->damage_since(4+chain->DAMAGE_HISTORY).status==wsi::present_damage::UNKNOWN,
                 "history overflow did not force full");
         history[4].damage.rects[0].offset.x=-1;
         require(chain->damage_since(4).status==wsi::present_damage::UNKNOWN, "negative X11 coordinates accepted");
         chain->m_last_update_sequence=0;
         expected_pixels.fill(0); downstream_pixels.fill(0); verify_downstream=true; verify_pixels=true;
         const auto before_pixels=downstream_copy_pixels;
         VkPresentInfoKHR info{}; wsi::swapchain_presentation_parameters params{};
         params.handle_present_frame_boundary_event=false; params.use_image_present_semaphore=false;
         for (unsigned frame=0; frame<40; ++frame) {
            const unsigned index=frame%4, x=frame+2;
            if (frame==0 || frame==20) {
               expected_pixels.fill(0xff002000u | frame); params.pending_present.damage={};
            } else {
               expected_pixels[8*64+x]=0xff000000u | frame;
               auto &hint=params.pending_present.damage;
               hint.status=wsi::present_damage::RECTS; hint.rect_count=1;
               hint.rects[0]={{static_cast<int32_t>(x),8},{1,1}};
            }
            params.pending_present.image_index=index;
            image_pixels[chain->m_swapchain_images[index].image]=expected_pixels;
            require(chain->queue_present(handle<VkQueue>(), &info, params)==VK_SUCCESS, "downstream pixel present");
         }
         require(downstream_region_requests>=38, "region path not exercised");
         require(downstream_copy_pixels-before_pixels < 4*64*64, "downstream still copies whole frames");
         verify_downstream=false; verify_pixels=false;
      }
      require(update_regions.empty(), "swapchain retained an X11 region resource");
      clock_capability={}; unsetenv("PAD_GPU_MAX_FPS");
      unsetenv("PAD_GPU_X11_COLOR_MODE");
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
      std::cout << "WSI_REGRESSION_OK: eager/deferred/alias/failure/MAILBOX/FIFO/cancel/disconnect/oldSwapchain/BGRA/damage-pixel-rotation/empty-list-full/coalescing/display-clock/immediate-destroy\n";
      return 0;
   } catch (const std::exception &error) {
      std::cerr << "WSI_REGRESSION_FAILED: " << error.what() << '\n'; return 1;
   }
}
