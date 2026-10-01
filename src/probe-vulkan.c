/* SPDX-License-Identifier: MIT */
#include <stdio.h>
#include <stdlib.h>
#include <vulkan/vulkan.h>

int main(void)
{
    VkInstance instance = VK_NULL_HANDLE;
    VkInstanceCreateInfo create = { .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO };
    VkResult result = vkCreateInstance(&create, NULL, &instance);
    if (result != VK_SUCCESS) {
        fprintf(stderr, "vkCreateInstance failed: %d\n", result);
        return 1;
    }
    uint32_t count = 0;
    result = vkEnumeratePhysicalDevices(instance, &count, NULL);
    if (result != VK_SUCCESS || !count) {
        fprintf(stderr, "No Vulkan devices: result=%d count=%u\n", result, count);
        vkDestroyInstance(instance, NULL);
        return 1;
    }
    VkPhysicalDevice *devices = calloc(count, sizeof(*devices));
    if (!devices) {
        vkDestroyInstance(instance, NULL);
        return 1;
    }
    result = vkEnumeratePhysicalDevices(instance, &count, devices);
    int hardware = 0;
    if (result == VK_SUCCESS) {
        for (uint32_t i = 0; i < count; ++i) {
            VkPhysicalDeviceProperties properties;
            vkGetPhysicalDeviceProperties(devices[i], &properties);
            printf("device=%s type=%u vendor=0x%x api=%u.%u.%u\n", properties.deviceName,
                   properties.deviceType, properties.vendorID,
                   VK_VERSION_MAJOR(properties.apiVersion), VK_VERSION_MINOR(properties.apiVersion),
                   VK_VERSION_PATCH(properties.apiVersion));
            if (properties.vendorID == 0x13b5 && properties.deviceType != VK_PHYSICAL_DEVICE_TYPE_CPU)
                hardware = 1;
        }
    }
    free(devices);
    vkDestroyInstance(instance, NULL);
    return result == VK_SUCCESS && hardware ? 0 : 1;
}
