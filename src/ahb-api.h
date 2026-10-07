/* SPDX-License-Identifier: MIT
 * Public Android AHardwareBuffer ABI; no bionic libc headers in glibc clients.
 */
#ifndef PAD_GPU_AHB_API_H
#define PAD_GPU_AHB_API_H
#include <stdint.h>
typedef struct AHardwareBuffer AHardwareBuffer;
typedef struct AHardwareBuffer_Desc {
    uint32_t width, height, layers, format;
    uint64_t usage;
    uint32_t stride, reserved0;
    uint64_t reserved1;
} AHardwareBuffer_Desc;
typedef struct ARect { int32_t left, top, right, bottom; } ARect;
int AHardwareBuffer_allocate(const AHardwareBuffer_Desc *, AHardwareBuffer **);
void AHardwareBuffer_acquire(AHardwareBuffer *);
void AHardwareBuffer_release(AHardwareBuffer *);
void AHardwareBuffer_describe(const AHardwareBuffer *, AHardwareBuffer_Desc *);
int AHardwareBuffer_sendHandleToUnixSocket(const AHardwareBuffer *, int);
int AHardwareBuffer_recvHandleFromUnixSocket(int, AHardwareBuffer **);
int AHardwareBuffer_lock(AHardwareBuffer *, uint64_t, int32_t, const ARect *, void **);
int AHardwareBuffer_unlock(AHardwareBuffer *, int32_t *);
#endif
