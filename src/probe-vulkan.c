/* SPDX-License-Identifier: MIT */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>
#include <vulkan/vulkan_android.h>

/* Submit real device work and verify it through host-visible memory. */
static int check_device_work(VkPhysicalDevice physical)
{
    VkDevice device = VK_NULL_HANDLE;
    VkBuffer buffer = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkFence fence = VK_NULL_HANDLE;
    void *mapped = NULL;
    int success = 0;
    VkResult status = VK_SUCCESS;
    uint32_t count = 0, family = UINT32_MAX;
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, NULL);
    VkQueueFamilyProperties *families = calloc(count, sizeof(*families));
    if (!families) return 0;
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, families);
    for (uint32_t i = 0; i < count; ++i)
        if (families[i].queueCount && (families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT)) {
            family = i;
            break;
        }
    free(families);
    if (family == UINT32_MAX) return 0;
    float priority = 1.0f;
    VkDeviceQueueCreateInfo queue_create = {.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = family, .queueCount = 1, .pQueuePriorities = &priority};
    VkDeviceCreateInfo create = {.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount = 1, .pQueueCreateInfos = &queue_create};
#define CHECK(call) do { status = (call); if (status != VK_SUCCESS) goto done; } while (0)
    CHECK(vkCreateDevice(physical, &create, NULL, &device));
    VkQueue queue;
    vkGetDeviceQueue(device, family, 0, &queue);
    VkBufferCreateInfo buffer_create = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = 4096, .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE};
    CHECK(vkCreateBuffer(device, &buffer_create, NULL, &buffer));
    VkMemoryRequirements requirements;
    vkGetBufferMemoryRequirements(device, buffer, &requirements);
    VkPhysicalDeviceMemoryProperties properties;
    vkGetPhysicalDeviceMemoryProperties(physical, &properties);
    uint32_t type = UINT32_MAX;
    for (uint32_t i = 0; i < properties.memoryTypeCount; ++i)
        if ((requirements.memoryTypeBits & (1u << i)) &&
            (properties.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT)) {
            type = i;
            break;
        }
    if (type == UINT32_MAX) goto done;
    VkMemoryAllocateInfo allocate = {.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = requirements.size, .memoryTypeIndex = type};
    CHECK(vkAllocateMemory(device, &allocate, NULL, &memory));
    CHECK(vkBindBufferMemory(device, buffer, memory, 0));
    VkCommandPoolCreateInfo pool_create = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .queueFamilyIndex = family};
    CHECK(vkCreateCommandPool(device, &pool_create, NULL, &pool));
    VkCommandBuffer command;
    VkCommandBufferAllocateInfo command_allocate = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = pool, .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
    CHECK(vkAllocateCommandBuffers(device, &command_allocate, &command));
    VkCommandBufferBeginInfo begin = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    CHECK(vkBeginCommandBuffer(command, &begin));
    vkCmdFillBuffer(command, buffer, 0, 4096, UINT32_C(0x51a7c0de));
    VkBufferMemoryBarrier barrier = {.sType = VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER,
        .srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT, .dstAccessMask = VK_ACCESS_HOST_READ_BIT,
        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .buffer = buffer, .size = VK_WHOLE_SIZE};
    vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT,
                         0, 0, NULL, 1, &barrier, 0, NULL);
    CHECK(vkEndCommandBuffer(command));
    VkFenceCreateInfo fence_create = {.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    CHECK(vkCreateFence(device, &fence_create, NULL, &fence));
    VkSubmitInfo submit = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .commandBufferCount = 1, .pCommandBuffers = &command};
    CHECK(vkQueueSubmit(queue, 1, &submit, fence));
    CHECK(vkWaitForFences(device, 1, &fence, VK_TRUE, UINT64_C(5000000000)));
    CHECK(vkMapMemory(device, memory, 0, VK_WHOLE_SIZE, 0, &mapped));
    VkMappedMemoryRange range = {.sType = VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE,
        .memory = memory, .size = VK_WHOLE_SIZE};
    CHECK(vkInvalidateMappedMemoryRanges(device, 1, &range));
    for (unsigned i = 0; i < 4096 / sizeof(uint32_t); ++i)
        if (((uint32_t *)mapped)[i] != UINT32_C(0x51a7c0de)) goto done;
    puts("VULKAN_DEVICE_SUBMIT_READBACK_OK");
    success = 1;
done:
    if (!success) fprintf(stderr, "Vulkan device submit/readback failed: %d\n", status);
    if (device) vkDeviceWaitIdle(device);
    if (mapped) vkUnmapMemory(device, memory);
    if (fence) vkDestroyFence(device, fence, NULL);
    if (pool) vkDestroyCommandPool(device, pool, NULL);
    if (buffer) vkDestroyBuffer(device, buffer, NULL);
    if (memory) vkFreeMemory(device, memory, NULL);
    if (device) vkDestroyDevice(device, NULL);
    return success;
#undef CHECK
}

/* Capability gate for a direct shared color-attachment image. A successful
 * query is necessary, not proof of byte order, ownership or screen correctness. */
static void ahb_formats(VkPhysicalDevice physical)
{
    const VkFormat formats[] = {VK_FORMAT_R8G8B8A8_UNORM, VK_FORMAT_B8G8R8A8_UNORM};
    const VkImageTiling tilings[] = {VK_IMAGE_TILING_LINEAR, VK_IMAGE_TILING_OPTIMAL};
    for (unsigned f=0; f<2; ++f) for (unsigned t=0; t<2; ++t) {
        VkPhysicalDeviceExternalImageFormatInfo external = {
            .sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_EXTERNAL_IMAGE_FORMAT_INFO,
            .handleType=VK_EXTERNAL_MEMORY_HANDLE_TYPE_ANDROID_HARDWARE_BUFFER_BIT_ANDROID};
        VkPhysicalDeviceImageFormatInfo2 info = {.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_IMAGE_FORMAT_INFO_2,
            .pNext=&external, .format=formats[f], .type=VK_IMAGE_TYPE_2D, .tiling=tilings[t],
            .usage=VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT};
        VkAndroidHardwareBufferUsageANDROID usage = {.sType=VK_STRUCTURE_TYPE_ANDROID_HARDWARE_BUFFER_USAGE_ANDROID};
        VkExternalImageFormatProperties properties = {.sType=VK_STRUCTURE_TYPE_EXTERNAL_IMAGE_FORMAT_PROPERTIES,.pNext=&usage};
        VkImageFormatProperties2 output = {.sType=VK_STRUCTURE_TYPE_IMAGE_FORMAT_PROPERTIES_2,.pNext=&properties};
        VkResult result=vkGetPhysicalDeviceImageFormatProperties2(physical,&info,&output);
        printf("AHB_COLOR_ATTACHMENT format=%s tiling=%s result=%d external_features=0x%x usage=0x%llx max=%ux%u\n",
            f ? "BGRA8" : "RGBA8", t ? "optimal" : "linear", result,
            properties.externalMemoryProperties.externalMemoryFeatures,
            (unsigned long long)usage.androidHardwareBufferUsage,
            output.imageFormatProperties.maxExtent.width,output.imageFormatProperties.maxExtent.height);
    }
}

int main(int argc, char **argv)
{
    int formats_only = argc==2 && !strcmp(argv[1], "--ahb-formats");
    if (argc!=1 && !formats_only) { fprintf(stderr,"usage: %s [--ahb-formats]\n",argv[0]); return 64; }
    VkInstance instance = VK_NULL_HANDLE;
    VkApplicationInfo app = {.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,.apiVersion=VK_API_VERSION_1_1};
    VkInstanceCreateInfo create = { .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pApplicationInfo=&app };
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
            {
                if (formats_only) { ahb_formats(devices[i]); hardware=1; }
                else hardware = check_device_work(devices[i]);
            }
        }
    }
    free(devices);
    vkDestroyInstance(instance, NULL);
    return result == VK_SUCCESS && hardware ? 0 : 1;
}
