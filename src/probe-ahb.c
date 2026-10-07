/* SPDX-License-Identifier: MIT */
#include "ahb-api.h"
#include <stdio.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

int main(void)
{
    const uint64_t cpu_read = 2, cpu_write = 0x30;
    AHardwareBuffer_Desc description = {
        .width = 64, .height = 64, .layers = 1, .format = 1,
        .usage = cpu_read | cpu_write | UINT64_C(0x200)
    }, received_description = {0};
    AHardwareBuffer *buffer = NULL, *received = NULL;
    int sockets[2] = {-1, -1}, result = 1, locked = 0;
    uint32_t *pixels = NULL;
    int status = AHardwareBuffer_allocate(&description, &buffer);
    if (status || !buffer) {
        fprintf(stderr, "AHardwareBuffer_allocate failed: %d\n", status);
        goto done;
    }
    AHardwareBuffer_describe(buffer, &description);
    if (description.width != 64 || description.height != 64 || description.stride < 64)
        goto done;
    status = AHardwareBuffer_lock(buffer, cpu_write, -1, NULL, (void **)&pixels);
    if (status || !pixels) goto done;
    locked = 1;
    for (unsigned y = 0; y < 64; ++y)
        for (unsigned x = 0; x < 64; ++x)
            pixels[y * description.stride + x] = UINT32_C(0xff000000) | (y << 8) | x;
    status = AHardwareBuffer_unlock(buffer, NULL);
    locked = 0;
    if (status) goto done;
    if (socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, sockets)) goto done;
    struct timeval timeout = {.tv_sec = 3};
    if (setsockopt(sockets[1], SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout))) goto done;
    status = AHardwareBuffer_sendHandleToUnixSocket(buffer, sockets[0]);
    if (status) goto done;
    status = AHardwareBuffer_recvHandleFromUnixSocket(sockets[1], &received);
    if (status || !received) goto done;
    /* The receiver owns its own reference, independently of the sender. */
    AHardwareBuffer_release(buffer);
    buffer = NULL;
    AHardwareBuffer_describe(received, &received_description);
    if (received_description.width != 64 || received_description.height != 64 ||
        received_description.format != 1 || received_description.stride < 64) goto done;
    status = AHardwareBuffer_lock(received, cpu_read, -1, NULL, (void **)&pixels);
    if (status || !pixels) goto done;
    locked = 2;
    for (unsigned y = 0; y < 64; ++y)
        for (unsigned x = 0; x < 64; ++x)
            if (pixels[y * received_description.stride + x] !=
                (UINT32_C(0xff000000) | (y << 8) | x)) goto done;
    status = AHardwareBuffer_unlock(received, NULL);
    locked = 0;
    if (status) goto done;
    puts("AHB_ALLOCATE_SEND_RECEIVE_READBACK_RELEASE_OK");
    result = 0;
done:
    if (result) fprintf(stderr, "AHB round-trip failed (last status=%d)\n", status);
    if (locked) AHardwareBuffer_unlock(locked == 1 ? buffer : received, NULL);
    if (buffer) AHardwareBuffer_release(buffer);
    if (received) AHardwareBuffer_release(received);
    if (sockets[0] >= 0) close(sockets[0]);
    if (sockets[1] >= 0) close(sockets[1]);
    return result;
}
