/* SPDX-License-Identifier: MIT
 * Targeted WebKitGTK adapter for applications that explicitly disable the GPU.
 * This glibc shim never participates in libhybris/Android library loading.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static pthread_once_t once = PTHREAD_ONCE_INIT;
static void (*set_policy)(void *, int);
static int (*get_policy)(void *);
static int force_gpu;

__attribute__((constructor)) static void initialize_mode(void)
{
    const char *mode = getenv("PAD_GPU_WEBKIT_POLICY");
    force_gpu = mode && strcmp(mode, "always") == 0;
    /* The ELF loader has already loaded this shim. Do not pass a glibc preload
     * to the Android linker or unrelated WebKit helper processes. */
    unsetenv("LD_PRELOAD");
}

static void resolve_policy(void)
{
    set_policy = (void (*)(void *, int))dlsym(RTLD_NEXT, "webkit_settings_set_hardware_acceleration_policy");
    get_policy = (int (*)(void *))dlsym(RTLD_NEXT, "webkit_settings_get_hardware_acceleration_policy");
}

void webkit_settings_set_hardware_acceleration_policy(void *settings, int policy)
{
    pthread_once(&once, resolve_policy);
    if (!set_policy) {
        fputs("[pad-gpu] WebKit policy adapter could not resolve the real setter\n", stderr);
        abort();
    }
    /* API 4.1: ON_DEMAND=0, ALWAYS=1, NEVER=2. */
    set_policy(settings, force_gpu ? 1 : policy);
    if (force_gpu) {
        const int actual = get_policy ? get_policy(settings) : -1;
        fprintf(stderr, "[pad-gpu] WebKit hardware policy=%d (always=1)\n", actual);
        if (actual != 1) {
            fputs("[pad-gpu] WebKit hardware acceleration unavailable; no silent CPU fallback\n", stderr);
            _Exit(78);
        }
    }
}
