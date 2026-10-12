/* SPDX-License-Identifier: MIT
 * Small real X11/Vulkan regression: present, destroy and recreate in one process.
 */
#define VK_USE_PLATFORM_XCB_KHR
#include <vulkan/vulkan.h>
#include <xcb/xcb.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <signal.h>

static volatile sig_atomic_t stop_requested;
static void request_stop(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

static unsigned number(const char *text)
{
    char *end;
    unsigned long n = strtoul(text, &end, 10);
    if (!*text || *end || !n || n > 100000) return 0;
    return (unsigned)n;
}

static uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + ts.tv_nsec;
}

static void pause_ms(unsigned ms)
{
    struct timespec pause = {.tv_sec = ms / 1000, .tv_nsec = (ms % 1000) * 1000000L};
    while (nanosleep(&pause, &pause) && errno == EINTR && !stop_requested) {}
}

int main(int argc, char **argv)
{
    unsigned cycles = 20, frames = 3;
    unsigned width = 256, height = 192, delay_ms = 20, idle_ms = 0;
    const char *timings_path = NULL;
    FILE *timings = NULL;
    int replace = 0, bgra = 0, solid_red = 0, resize = 0;
    VkPresentModeKHR mode = VK_PRESENT_MODE_FIFO_KHR;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--cycles") && i + 1 < argc) cycles = number(argv[++i]);
        else if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = number(argv[++i]);
        else if (!strcmp(argv[i], "--mailbox")) mode = VK_PRESENT_MODE_MAILBOX_KHR;
        else if (!strcmp(argv[i], "--replace")) replace = 1;
        else if (!strcmp(argv[i], "--bgra")) bgra = 1;
        else if (!strcmp(argv[i], "--solid-red")) solid_red = 1;
        else if (!strcmp(argv[i], "--resize")) resize = 1;
        else if (!strcmp(argv[i], "--width") && i + 1 < argc) width = number(argv[++i]);
        else if (!strcmp(argv[i], "--height") && i + 1 < argc) height = number(argv[++i]);
        else if (!strcmp(argv[i], "--delay-ms") && i + 1 < argc) {
            const char *value = argv[++i];
            delay_ms = !strcmp(value, "0") ? 0 : number(value);
            if (!delay_ms && strcmp(value, "0")) return 64;
        }
        else if (!strcmp(argv[i], "--idle-ms") && i + 1 < argc) {
            const char *value = argv[++i];
            idle_ms = !strcmp(value, "0") ? 0 : number(value);
            if (!idle_ms && strcmp(value, "0")) return 64;
        }
        else if (!strcmp(argv[i], "--timings") && i + 1 < argc) timings_path = argv[++i];
        else { fprintf(stderr, "usage: %s [--cycles N] [--frames N] [--mailbox] [--replace] [--bgra] [--solid-red] [--resize] [--width N] [--height N] [--delay-ms N] [--idle-ms N] [--timings CSV]\n", argv[0]); return 64; }
    }
    if (!cycles || !frames || !width || !height || width > 10000 || height > 10000 || delay_ms > 10000 ||
        (resize && (width < 32 || height < 32))) return 64;
    signal(SIGINT, request_stop);
    signal(SIGTERM, request_stop);
    if (timings_path) {
        int fd = open(timings_path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
        if (fd < 0 || !(timings = fdopen(fd, "w"))) {
            if (fd >= 0) close(fd);
            perror("timings"); return 73;
        }
        fputs("cycle,frame,start_ns,acquire_us,queue_present_us,host_frame_us\n", timings);
    }
    int exit_status = 1;
    VkResult status = VK_SUCCESS;
    VkInstance instance = VK_NULL_HANDLE;
    VkSurfaceKHR surface = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkSwapchainKHR swapchain = VK_NULL_HANDLE;
    VkSwapchainKHR old_swapchain = VK_NULL_HANDLE;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkSemaphore acquired = VK_NULL_HANDLE, *rendered = NULL;
    VkSemaphore *old_rendered = NULL;
    VkFence fence = VK_NULL_HANDLE;
    VkImage *images = NULL;
    VkImage *old_images = NULL;
    uint32_t image_count = 0;
    uint32_t old_image_count = 0;
    xcb_connection_t *connection = xcb_connect(NULL, NULL);
    xcb_window_t window = XCB_NONE;
    if (xcb_connection_has_error(connection)) goto done;
    xcb_screen_t *screen = xcb_setup_roots_iterator(xcb_get_setup(connection)).data;
    window = xcb_generate_id(connection);
    uint32_t values[] = {screen->black_pixel, XCB_EVENT_MASK_STRUCTURE_NOTIFY};
    xcb_create_window(connection, XCB_COPY_FROM_PARENT, window, screen->root,
                      24, 120, width, height, 0, XCB_WINDOW_CLASS_INPUT_OUTPUT, screen->root_visual,
                      XCB_CW_BACK_PIXEL | XCB_CW_EVENT_MASK, values);
    const char title[] = "GPU bridge validation";
    xcb_change_property(connection, XCB_PROP_MODE_REPLACE, window, XCB_ATOM_WM_NAME,
                         XCB_ATOM_STRING, 8, sizeof(title) - 1, title);
    xcb_map_window(connection, window);
    xcb_flush(connection);
#define CHECK(call) do { status = (call); if (status != VK_SUCCESS) { \
    fprintf(stderr, "%s failed: %d\n", #call, status); goto done; } } while (0)
    const char *extensions[] = {VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_XCB_SURFACE_EXTENSION_NAME,
                               VK_KHR_GET_PHYSICAL_DEVICE_PROPERTIES_2_EXTENSION_NAME};
    VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pApplicationName = "GPU bridge validation", .apiVersion = VK_API_VERSION_1_1};
    VkInstanceCreateInfo instance_create = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo = &app, .enabledExtensionCount = 3, .ppEnabledExtensionNames = extensions};
    CHECK(vkCreateInstance(&instance_create, NULL, &instance));
    uint32_t count = 0;
    CHECK(vkEnumeratePhysicalDevices(instance, &count, NULL));
    if (!count || count > 16) goto done;
    VkPhysicalDevice physicals[16], physical = VK_NULL_HANDLE;
    CHECK(vkEnumeratePhysicalDevices(instance, &count, physicals));
    for (unsigned i = 0; i < count; ++i) {
        VkPhysicalDeviceProperties properties;
        vkGetPhysicalDeviceProperties(physicals[i], &properties);
        if (properties.vendorID == 0x13b5 && properties.deviceType != VK_PHYSICAL_DEVICE_TYPE_CPU) {
            physical = physicals[i];
            printf("renderer=%s\n", properties.deviceName);
            break;
        }
    }
    if (!physical) goto done;
    VkXcbSurfaceCreateInfoKHR surface_create = {.sType = VK_STRUCTURE_TYPE_XCB_SURFACE_CREATE_INFO_KHR,
        .connection = connection, .window = window};
    CHECK(vkCreateXcbSurfaceKHR(instance, &surface_create, NULL, &surface));
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, NULL);
    if (!count || count > 64) goto done;
    VkQueueFamilyProperties families[64];
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, families);
    uint32_t family = UINT32_MAX;
    for (unsigned i = 0; i < count; ++i) {
        VkBool32 supported = VK_FALSE;
        CHECK(vkGetPhysicalDeviceSurfaceSupportKHR(physical, i, surface, &supported));
        if (families[i].queueCount && (families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) && supported) {
            family = i;
            break;
        }
    }
    if (family == UINT32_MAX) goto done;
    float priority = 1;
    VkDeviceQueueCreateInfo queue_create = {.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = family, .queueCount = 1, .pQueuePriorities = &priority};
    const char *device_extension = VK_KHR_SWAPCHAIN_EXTENSION_NAME;
    VkDeviceCreateInfo device_create = {.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount = 1, .pQueueCreateInfos = &queue_create,
        .enabledExtensionCount = 1, .ppEnabledExtensionNames = &device_extension};
    CHECK(vkCreateDevice(physical, &device_create, NULL, &device));
    VkQueue queue;
    vkGetDeviceQueue(device, family, 0, &queue);
    VkCommandPoolCreateInfo pool_create = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT, .queueFamilyIndex = family};
    CHECK(vkCreateCommandPool(device, &pool_create, NULL, &pool));
    VkCommandBuffer command;
    VkCommandBufferAllocateInfo command_allocate = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = pool, .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
    CHECK(vkAllocateCommandBuffers(device, &command_allocate, &command));
    VkSemaphoreCreateInfo semaphore_create = {.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};
    CHECK(vkCreateSemaphore(device, &semaphore_create, NULL, &acquired));
    VkFenceCreateInfo fence_create = {.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    CHECK(vkCreateFence(device, &fence_create, NULL, &fence));
    for (unsigned cycle = 0; cycle < cycles && !stop_requested; ++cycle) {
        if (resize) {
            uint32_t size[] = {width - ((cycle & 1) ? 16 : 0), height - ((cycle & 1) ? 16 : 0)};
            xcb_generic_error_t *error = xcb_request_check(connection,
                xcb_configure_window_checked(connection, window, XCB_CONFIG_WINDOW_WIDTH | XCB_CONFIG_WINDOW_HEIGHT, size));
            if (error) { free(error); goto done; }
            int resized = 0;
            for (unsigned attempt = 0; attempt < 50 && !stop_requested; ++attempt) {
                xcb_get_geometry_reply_t *geometry = xcb_get_geometry_reply(connection,
                    xcb_get_geometry(connection, window), NULL);
                if (geometry) resized = geometry->width == size[0] && geometry->height == size[1];
                free(geometry);
                if (resized) break;
                pause_ms(10);
            }
            if (!resized) { fprintf(stderr, "test window resize was not applied\n"); goto done; }
        }
        VkSurfaceCapabilitiesKHR caps;
        CHECK(vkGetPhysicalDeviceSurfaceCapabilitiesKHR(physical, surface, &caps));
        CHECK(vkGetPhysicalDeviceSurfaceFormatsKHR(physical, surface, &count, NULL));
        if (!count || count > 64) goto done;
        VkSurfaceFormatKHR formats[64];
        CHECK(vkGetPhysicalDeviceSurfaceFormatsKHR(physical, surface, &count, formats));
        VkSurfaceFormatKHR format = formats[0];
        int format_found = 0;
        for (unsigned i = 0; i < count; ++i)
            if (formats[i].format == (bgra ? VK_FORMAT_B8G8R8A8_UNORM : VK_FORMAT_R8G8B8A8_UNORM)) {
                format = formats[i]; format_found = 1;
            }
        if (!format_found && bgra) { fprintf(stderr, "requested BGRA surface format unavailable\n"); goto done; }
        VkExtent2D extent = caps.currentExtent;
        if (extent.width == UINT32_MAX) extent = (VkExtent2D){width, height};
        if (!(caps.supportedUsageFlags & VK_IMAGE_USAGE_TRANSFER_DST_BIT)) goto done;
        VkSwapchainCreateInfoKHR create = {.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR,
            .surface = surface, .minImageCount = caps.minImageCount, .imageFormat = format.format,
            .imageColorSpace = format.colorSpace, .imageExtent = extent, .imageArrayLayers = 1,
            .imageUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT,
            .imageSharingMode = VK_SHARING_MODE_EXCLUSIVE, .preTransform = caps.currentTransform,
            .compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR, .presentMode = mode, .clipped = VK_TRUE,
            .oldSwapchain = old_swapchain};
        CHECK(vkCreateSwapchainKHR(device, &create, NULL, &swapchain));
        if (old_swapchain) {
            vkDestroySwapchainKHR(device, old_swapchain, NULL);
            old_swapchain = VK_NULL_HANDLE;
            for (unsigned i = 0; i < old_image_count; ++i)
                vkDestroySemaphore(device, old_rendered[i], NULL);
            free(old_rendered); old_rendered = NULL;
            free(old_images); old_images = NULL;
        }
        CHECK(vkGetSwapchainImagesKHR(device, swapchain, &image_count, NULL));
        images = calloc(image_count, sizeof(*images));
        rendered = calloc(image_count, sizeof(*rendered));
        if (!images || !rendered) goto done;
        CHECK(vkGetSwapchainImagesKHR(device, swapchain, &image_count, images));
        for (unsigned i = 0; i < image_count; ++i)
            CHECK(vkCreateSemaphore(device, &semaphore_create, NULL, &rendered[i]));
        unsigned completed_frames = 0;
        for (unsigned frame = 0; frame < frames && !stop_requested; ++frame) {
            const uint64_t started = now_ns();
            uint32_t index;
            status = vkAcquireNextImageKHR(device, swapchain, UINT64_C(5000000000), acquired, VK_NULL_HANDLE, &index);
            if (status != VK_SUCCESS && status != VK_SUBOPTIMAL_KHR) goto done;
            const uint64_t acquired_at = now_ns();
            CHECK(vkResetCommandBuffer(command, 0));
            VkCommandBufferBeginInfo begin = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
            CHECK(vkBeginCommandBuffer(command, &begin));
            VkImageMemoryBarrier barrier = {.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
                .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT, .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED,
                .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .image = images[index], .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
            vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                                 0, 0, NULL, 0, NULL, 1, &barrier);
            VkClearColorValue color = {.float32 = {(cycle % 3) / 2.0f, 0.25f, (frame % 3) / 2.0f, 1.0f}};
            if (solid_red) color = (VkClearColorValue){.float32 = {1.0f, 0.0f, 0.0f, 1.0f}};
            vkCmdClearColorImage(command, images[index], VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                                &color, 1, &barrier.subresourceRange);
            barrier.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
            barrier.dstAccessMask = 0;
            barrier.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
            barrier.newLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
            vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT,
                                 0, 0, NULL, 0, NULL, 1, &barrier);
            CHECK(vkEndCommandBuffer(command));
            VkPipelineStageFlags stage = VK_PIPELINE_STAGE_TRANSFER_BIT;
            VkSubmitInfo submit = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
                .waitSemaphoreCount = 1, .pWaitSemaphores = &acquired, .pWaitDstStageMask = &stage,
                .commandBufferCount = 1, .pCommandBuffers = &command,
                .signalSemaphoreCount = 1, .pSignalSemaphores = &rendered[index]};
            CHECK(vkQueueSubmit(queue, 1, &submit, fence));
            VkPresentInfoKHR present = {.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR,
                .waitSemaphoreCount = 1, .pWaitSemaphores = &rendered[index],
                .swapchainCount = 1, .pSwapchains = &swapchain, .pImageIndices = &index};
            const uint64_t present_started = now_ns();
            status = vkQueuePresentKHR(queue, &present);
            if (status != VK_SUCCESS && status != VK_SUBOPTIMAL_KHR) goto done;
            const uint64_t presented_at = now_ns();
            CHECK(vkWaitForFences(device, 1, &fence, VK_TRUE, UINT64_C(5000000000)));
            CHECK(vkResetFences(device, 1, &fence));
            /* Bounded low load; this tool is for correctness, not peak FPS. */
            if (timings) fprintf(timings, "%u,%u,%llu,%.3f,%.3f,%.3f\n", cycle, frame,
                (unsigned long long)started, (acquired_at - started) / 1000.,
                (presented_at - present_started) / 1000., (now_ns() - started) / 1000.);
            ++completed_frames;
            pause_ms(delay_ms);
        }
        pause_ms(idle_ms);
        CHECK(vkDeviceWaitIdle(device));
        if (replace && cycle + 1 < cycles) {
            old_swapchain = swapchain;
            old_rendered = rendered;
            old_images = images;
            old_image_count = image_count;
            swapchain = VK_NULL_HANDLE; rendered = NULL; images = NULL;
        } else {
            vkDestroySwapchainKHR(device, swapchain, NULL);
            swapchain = VK_NULL_HANDLE;
            for (unsigned i = 0; i < image_count; ++i) vkDestroySemaphore(device, rendered[i], NULL);
            free(rendered); rendered = NULL;
            free(images); images = NULL;
        }
        printf("cycle=%u/%u frames=%u mode=%s images=%u format=%u replace=%d extent=%ux%u\n", cycle + 1, cycles, completed_frames,
               mode == VK_PRESENT_MODE_FIFO_KHR ? "fifo" : "mailbox", image_count, format.format, replace, extent.width, extent.height);
        fflush(stdout);
    }
    puts(stop_requested ? "VULKAN_PRESENT_STOPPED_CLEANLY" : "VULKAN_SWAPCHAIN_RECREATE_PRESENT_OK");
    exit_status = 0;
done:
    if (exit_status) fprintf(stderr, "Presentation regression failed: %d\n", status);
    if (device) vkDeviceWaitIdle(device);
    if (swapchain) vkDestroySwapchainKHR(device, swapchain, NULL);
    if (old_swapchain) vkDestroySwapchainKHR(device, old_swapchain, NULL);
    if (rendered) for (unsigned i = 0; i < image_count; ++i)
        if (rendered[i]) vkDestroySemaphore(device, rendered[i], NULL);
    free(rendered); free(images);
    if (old_rendered) for (unsigned i = 0; i < old_image_count; ++i)
        if (old_rendered[i]) vkDestroySemaphore(device, old_rendered[i], NULL);
    free(old_rendered); free(old_images);
    if (fence) vkDestroyFence(device, fence, NULL);
    if (acquired) vkDestroySemaphore(device, acquired, NULL);
    if (pool) vkDestroyCommandPool(device, pool, NULL);
    if (device) vkDestroyDevice(device, NULL);
    if (surface) vkDestroySurfaceKHR(instance, surface, NULL);
    if (instance) vkDestroyInstance(instance, NULL);
    if (window) { xcb_destroy_window(connection, window); xcb_flush(connection); }
    if (connection) xcb_disconnect(connection);
    if (timings) fclose(timings);
    return exit_status;
}
