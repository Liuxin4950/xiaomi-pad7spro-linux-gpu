/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 Xiaomi Pad 7S Pro Linux GPU contributors
 * Public AHardwareBuffer entry points resolved through libhybris.
 */
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <dlfcn.h>
#include <hybris/common/dlfcn.h>
#include "ahb-api.h"

typedef struct native_handle native_handle_t;

static pthread_once_t symbols_once = PTHREAD_ONCE_INIT;
static void *nativewindow;
static void (*release_buffer)(AHardwareBuffer *);
static int (*send_buffer)(const AHardwareBuffer *, int);
static int (*allocate_buffer)(const AHardwareBuffer_Desc *, AHardwareBuffer **);
static const native_handle_t *(*get_handle)(const AHardwareBuffer *);
static void (*acquire_buffer)(AHardwareBuffer *);
static void (*describe_buffer)(const AHardwareBuffer *, AHardwareBuffer_Desc *);
static int (*receive_buffer)(int, AHardwareBuffer **);
static int (*lock_buffer)(AHardwareBuffer *, uint64_t, int32_t, const ARect *, void **);
static int (*unlock_buffer)(AHardwareBuffer *, int32_t *);

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
    acquire_buffer = (void (*)(AHardwareBuffer *))
        hybris_dlsym(nativewindow, "AHardwareBuffer_acquire");
    describe_buffer = (void (*)(const AHardwareBuffer *, AHardwareBuffer_Desc *))
        hybris_dlsym(nativewindow, "AHardwareBuffer_describe");
    receive_buffer = (int (*)(int, AHardwareBuffer **))
        hybris_dlsym(nativewindow, "AHardwareBuffer_recvHandleFromUnixSocket");
    lock_buffer = (int (*)(AHardwareBuffer *, uint64_t, int32_t, const ARect *, void **))
        hybris_dlsym(nativewindow, "AHardwareBuffer_lock");
    unlock_buffer = (int (*)(AHardwareBuffer *, int32_t *))
        hybris_dlsym(nativewindow, "AHardwareBuffer_unlock");
    if (!release_buffer || !send_buffer || !allocate_buffer || !get_handle)
        fprintf(stderr, "[pad-gpu] Required AHardwareBuffer symbols missing\n");
    /* Keep the Android DSO mapped while any driver-owned buffer may be alive. */
}

void AHardwareBuffer_acquire(AHardwareBuffer *buffer)
{
    if (!pthread_once(&symbols_once, load_symbols) && acquire_buffer && buffer)
        acquire_buffer(buffer);
}

void AHardwareBuffer_describe(const AHardwareBuffer *buffer, AHardwareBuffer_Desc *description)
{
    if (!description)
        return;
    *description = (AHardwareBuffer_Desc){0};
    if (!pthread_once(&symbols_once, load_symbols) && describe_buffer && buffer)
        describe_buffer(buffer, description);
}

int AHardwareBuffer_recvHandleFromUnixSocket(int socket, AHardwareBuffer **buffer)
{
    if (socket < 0 || !buffer)
        return -EINVAL;
    *buffer = NULL;
    if (pthread_once(&symbols_once, load_symbols) || !receive_buffer)
        return -ENOSYS;
    return receive_buffer(socket, buffer);
}

int AHardwareBuffer_lock(AHardwareBuffer *buffer, uint64_t usage, int32_t fence,
                        const ARect *rectangle, void **address)
{
    if (!buffer || !address)
        return -EINVAL;
    *address = NULL;
    if (pthread_once(&symbols_once, load_symbols) || !lock_buffer)
        return -ENOSYS;
    return lock_buffer(buffer, usage, fence, rectangle, address);
}

int AHardwareBuffer_unlock(AHardwareBuffer *buffer, int32_t *fence)
{
    if (fence)
        *fence = -1;
    if (!buffer)
        return -EINVAL;
    if (pthread_once(&symbols_once, load_symbols) || !unlock_buffer)
        return -ENOSYS;
    return unlock_buffer(buffer, fence);
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
