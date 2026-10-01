/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 Xiaomi Pad 7S Pro Linux GPU contributors
 * Public AHardwareBuffer entry points resolved through libhybris.
 */
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <dlfcn.h>
#include <hybris/common/dlfcn.h>

typedef struct AHardwareBuffer AHardwareBuffer;
typedef struct AHardwareBuffer_Desc AHardwareBuffer_Desc;
typedef struct native_handle native_handle_t;

static pthread_once_t symbols_once = PTHREAD_ONCE_INIT;
static void *nativewindow;
static void (*release_buffer)(AHardwareBuffer *);
static int (*send_buffer)(const AHardwareBuffer *, int);
static int (*allocate_buffer)(const AHardwareBuffer_Desc *, AHardwareBuffer **);
static const native_handle_t *(*get_handle)(const AHardwareBuffer *);

static void load_symbols(void)
{
    nativewindow = hybris_dlopen("libnativewindow.so", RTLD_LAZY | RTLD_LOCAL);
    if (!nativewindow) {
        fprintf(stderr, "[pad-gpu] libnativewindow: %s\n", hybris_dlerror());
        return;
    }
    release_buffer = (void (*)(AHardwareBuffer *))
        hybris_dlsym(nativewindow, "AHardwareBuffer_release");
    send_buffer = (int (*)(const AHardwareBuffer *, int))
        hybris_dlsym(nativewindow, "AHardwareBuffer_sendHandleToUnixSocket");
    allocate_buffer = (int (*)(const AHardwareBuffer_Desc *, AHardwareBuffer **))
        hybris_dlsym(nativewindow, "AHardwareBuffer_allocate");
    get_handle = (const native_handle_t *(*)(const AHardwareBuffer *))
        hybris_dlsym(nativewindow, "AHardwareBuffer_getNativeHandle");
    if (!release_buffer || !send_buffer || !allocate_buffer || !get_handle)
        fprintf(stderr, "[pad-gpu] Required AHardwareBuffer symbols missing\n");
    /* Keep the Android DSO mapped while any driver-owned buffer may be alive. */
}

void AHardwareBuffer_release(AHardwareBuffer *buffer)
{
    if (!pthread_once(&symbols_once, load_symbols) && release_buffer && buffer)
        release_buffer(buffer);
}

int AHardwareBuffer_sendHandleToUnixSocket(const AHardwareBuffer *buffer, int socket)
{
    if (!buffer || socket < 0)
        return -EINVAL;
    if (pthread_once(&symbols_once, load_symbols) || !send_buffer)
        return -ENOSYS;
    return send_buffer(buffer, socket);
}

int AHardwareBuffer_allocate(const AHardwareBuffer_Desc *description, AHardwareBuffer **buffer)
{
    if (!description || !buffer)
        return -EINVAL;
    *buffer = NULL;
    if (pthread_once(&symbols_once, load_symbols) || !allocate_buffer)
        return -ENOSYS;
    return allocate_buffer(description, buffer);
}

const native_handle_t *AHardwareBuffer_getNativeHandle(const AHardwareBuffer *buffer)
{
    if (!buffer || pthread_once(&symbols_once, load_symbols) || !get_handle)
        return NULL;
    return get_handle(buffer);
}
