/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 Xiaomi Pad 7S Pro Linux GPU contributors
 * Linux Vulkan ICD entry points forwarding to Android's public Vulkan HAL.
 */
#include <hardware/hwvulkan.h>
#include <pthread.h>
#include <stdio.h>

static pthread_once_t hal_once = PTHREAD_ONCE_INIT;
static hwvulkan_device_t *hal;

static void open_hal(void)
{
    const hw_module_t *module = NULL;
    hw_device_t *device = NULL;
    int status = hw_get_module(HWVULKAN_HARDWARE_MODULE_ID, &module);
    if (status || !module || !module->methods || !module->methods->open) {
        fprintf(stderr, "[pad-gpu] Android Vulkan HAL unavailable: %d\n", status);
        return;
    }
    status = module->methods->open(module, HWVULKAN_DEVICE_0, &device);
    if (status || !device) {
        fprintf(stderr, "[pad-gpu] Cannot open Vulkan HAL: %d\n", status);
        return;
    }
    hal = (hwvulkan_device_t *)device;
    /* Android specifies one HAL device per process, retained for its lifetime. */
}

VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
vk_icdGetInstanceProcAddr(VkInstance instance, const char *name)
{
    if (!name || pthread_once(&hal_once, open_hal) || !hal || !hal->GetInstanceProcAddr)
        return NULL;
    return hal->GetInstanceProcAddr(instance, name);
}

VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
vk_icdGetPhysicalDeviceProcAddr(VkInstance instance, const char *name)
{
    /* Interface 5 is only for unknown physical-device extension commands.
     * Android's generic instance dispatch cannot classify those commands.
     * Core commands continue through vk_icdGetInstanceProcAddr. */
    (void)instance;
    (void)name;
    return NULL;
}

VKAPI_ATTR VkResult VKAPI_CALL
vk_icdNegotiateLoaderICDInterfaceVersion(uint32_t *version)
{
    if (!version || *version < 1)
        return VK_ERROR_INITIALIZATION_FAILED;
    if (*version > 5)
        *version = 5;
    return VK_SUCCESS;
}
