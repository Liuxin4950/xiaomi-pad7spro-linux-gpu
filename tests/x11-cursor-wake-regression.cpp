// SPDX-License-Identifier: MIT
#include <cassert>
#include <cstdint>
#include <cstdio>
#include "frame-pacing.h"
using Bool = bool;
static void pthread_spin_lock(int*) {}
static void pthread_spin_unlock(int*) {}
static bool xorg_list_is_empty(int* list) { return *list == 0; }
struct State {
    struct { uint32_t readIndex=0, writeIndex=0; } gpuCopyQueue;
    struct { int x=100, y=100; bool moved=true, updated=false; } cursor;
    uint64_t rootWindowTextureID=1;
    bool surfaceAvailable=true, drawRequested=false;
    volatile uint8_t waitForNextFrame=1;
};
struct Renderer {
    State shared; State* state=&shared;
    bool stateChanged=false, windowChanged=false, viewportChanged=false;
    int bufferLock=0, addedBuffers=0, removedBuffers=0;
    uint64_t lastRequestedBufferId=1;
    float sourceWidth=800, sourceHeight=600, panSourceLeft=0, panSourceTop=0;
    bool overlayAvailable=true, panRequired=false;
    bool cursorOverlayUsable() { return overlayAvailable; }
    void computePan(float,float,float* left,float* top) const { *left=panRequired ? 10 : panSourceLeft; *top=panSourceTop; }
    bool canUpdateCursorOverlayOnly();
    bool shouldWait(bool*);
};
#include "production-wait.h"
int main() {
    Renderer r; bool waiting=false;
    // A desktop submission is still awaiting its next frame, but the pointer
    // neither reads the root buffer nor needs to move the crop.
    assert(!r.shouldWait(&waiting));
    r.overlayAvailable=false; assert(r.shouldWait(&waiting)); r.overlayAvailable=true;
    r.shared.drawRequested=true; assert(!r.shouldWait(&waiting));
    r.shared.cursor.moved=false; assert(r.shouldWait(&waiting));
    r.shared.cursor.moved=true; r.shared.drawRequested=false;
    r.panRequired=true; assert(r.shouldWait(&waiting)); r.panRequired=false;
    r.shared.cursor.moved=false; assert(r.shouldWait(&waiting));
    r.shared.cursor.updated=true; assert(!r.shouldWait(&waiting)); r.shared.cursor.updated=false;
    r.shared.cursor.moved=true;
    waiting=true; assert(!r.shouldWait(&waiting));
    r.shared.cursor.moved=false; assert(r.shouldWait(&waiting));
    r.shared.cursor.moved=true; waiting=false;
    r.shared.surfaceAvailable=false; assert(r.shouldWait(&waiting)); r.shared.surfaceAvailable=true;
    r.state=nullptr; assert(r.shouldWait(&waiting)); r.state=&r.shared;
    r.shared.gpuCopyQueue.writeIndex=1; assert(!r.shouldWait(&waiting)); r.shared.gpuCopyQueue.writeIndex=0;
    r.shared.drawRequested=true; r.shared.waitForNextFrame=0; assert(!r.shouldWait(&waiting));
    r.shared.waitForNextFrame=1; r.viewportChanged=true; waiting=true;
    assert(!r.shouldWait(&waiting) && !waiting && !r.viewportChanged);
    puts("CURSOR_WAKE_OK: independent cursor gate, preserved root/copy/pan/surface/buffer waits; no busy-loop eligibility");
}
