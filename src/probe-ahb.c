/* SPDX-License-Identifier: MIT */
#include <stdint.h>
#include <stdio.h>
#include <sys/socket.h>
#include <unistd.h>

typedef struct AHardwareBuffer AHardwareBuffer;
typedef struct {
    uint32_t width, height, layers, format;
    uint64_t usage;
    uint32_t stride, reserved0;
    uint64_t reserved1;
} AHardwareBuffer_Desc;
extern int AHardwareBuffer_allocate(const AHardwareBuffer_Desc *, AHardwareBuffer **);
extern void AHardwareBuffer_release(AHardwareBuffer *);
extern int AHardwareBuffer_sendHandleToUnixSocket(const AHardwareBuffer *, int);

int main(void)
{
    /* RGBA8, CPU read/write and GPU framebuffer use, from Android's public API. */
    AHardwareBuffer_Desc description = {
        .width = 64, .height = 64, .layers = 1, .format = 1,
        .usage = UINT64_C(2) | UINT64_C(0x30) | UINT64_C(0x200)
    };
    AHardwareBuffer *buffer = NULL;
    int result = AHardwareBuffer_allocate(&description, &buffer);
    if (result || !buffer) {
        fprintf(stderr, "AHardwareBuffer_allocate failed: %d\n", result);
        return 1;
    }
    int sockets[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, sockets)) {
        AHardwareBuffer_release(buffer);
        return 1;
    }
    result = AHardwareBuffer_sendHandleToUnixSocket(buffer, sockets[0]);
    close(sockets[0]); close(sockets[1]);
    AHardwareBuffer_release(buffer);
    if (result) {
        fprintf(stderr, "AHardwareBuffer transport failed: %d\n", result);
        return 1;
    }
    puts("AHB_ALLOCATE_TRANSPORT_RELEASE_OK");
    return 0;
}
