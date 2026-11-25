/* SPDX-License-Identifier: MIT
 * Negative robustness probe: intentionally supplies XCB_NONE. Run only with
 * the isolated candidate layer. This is not valid Vulkan application usage.
 */
#define VK_USE_PLATFORM_XCB_KHR
#include <vulkan/vulkan.h>
#include <xcb/xcb.h>
#include <stdio.h>
int main(void) {
    xcb_connection_t *c = xcb_connect(NULL, NULL);
    if (xcb_connection_has_error(c)) return 1;
    const char *extensions[] = {VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_XCB_SURFACE_EXTENSION_NAME,
                               VK_KHR_GET_PHYSICAL_DEVICE_PROPERTIES_2_EXTENSION_NAME};
    VkApplicationInfo app = {.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO, .apiVersion=VK_API_VERSION_1_1};
    VkInstanceCreateInfo info = {.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo=&app,
                                .enabledExtensionCount=3, .ppEnabledExtensionNames=extensions};
    VkInstance instance = VK_NULL_HANDLE;
    VkSurfaceKHR surface = VK_NULL_HANDLE;
    int result = 1;
    if (vkCreateInstance(&info, NULL, &instance) != VK_SUCCESS) goto done;
    uint32_t count = 1;
    VkPhysicalDevice physical;
    if (vkEnumeratePhysicalDevices(instance, &count, &physical) != VK_SUCCESS || !count) goto done;
    VkPhysicalDeviceProperties props;
    vkGetPhysicalDeviceProperties(physical, &props);
    if (props.vendorID != 0x13b5 || props.deviceType == VK_PHYSICAL_DEVICE_TYPE_CPU) goto done;
    VkXcbSurfaceCreateInfoKHR create = {.sType=VK_STRUCTURE_TYPE_XCB_SURFACE_CREATE_INFO_KHR,
                                      .connection=c, .window=XCB_NONE};
    if (vkCreateXcbSurfaceKHR(instance, &create, NULL, &surface) != VK_SUCCESS) goto done;
    VkSurfaceCapabilitiesKHR caps;
    VkResult status = vkGetPhysicalDeviceSurfaceCapabilitiesKHR(physical, surface, &caps);
    printf("renderer=%s missing_window_result=%d\n", props.deviceName, status);
    result = status == VK_ERROR_SURFACE_LOST_KHR ? 0 : 1;
done:
    if (surface) vkDestroySurfaceKHR(instance, surface, NULL);
    if (instance) vkDestroyInstance(instance, NULL);
    xcb_disconnect(c);
    return result;
}
