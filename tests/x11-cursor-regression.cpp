// SPDX-License-Identifier: MIT
// Execute production cursor geometry and transaction publication with Android stubs.
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cerrno>
#include <pthread.h>
using Bool = bool;
struct AHardwareBuffer { int references = 1; };
struct ASurfaceControl {};
struct LorieBuffer { AHardwareBuffer* buffer; };
static LorieBuffer* LorieBuffer_description(LorieBuffer* b) { return b; }
static void AHardwareBuffer_acquire(AHardwareBuffer* b) { ++b->references; }
struct ARect { int32_t left, top, right, bottom; };
struct ASurfaceTransaction {};
constexpr int ASURFACE_TRANSACTION_VISIBILITY_SHOW = 1, ASURFACE_TRANSACTION_VISIBILITY_HIDE = 0;
static int transactions = 0, visibility = -1, bufferSets = 0;
static ARect lastSource{}, lastDestination{};
static pthread_mutex_t* protectedLock;
static ASurfaceTransaction transaction;
static ASurfaceTransaction* ASurfaceTransaction_create() { return &transaction; }
static void ASurfaceTransaction_setVisibility(ASurfaceTransaction*, ASurfaceControl*, int value) { visibility = value; }
static void ASurfaceTransaction_setBuffer(ASurfaceTransaction*, ASurfaceControl*, AHardwareBuffer*, int fence) {
    assert(fence == -1); ++bufferSets;
}
static void ASurfaceTransaction_setGeometry(ASurfaceTransaction*, ASurfaceControl*, ARect a, ARect b, int rotation) {
    assert(rotation == 0); lastSource = a; lastDestination = b;
}
static void ASurfaceTransaction_apply(ASurfaceTransaction*) {
    // Teardown must not be able to release the surface during publication.
    assert(pthread_mutex_trylock(protectedLock) == EBUSY); ++transactions;
}
static void ASurfaceTransaction_delete(ASurfaceTransaction*) {}
static void AHardwareBuffer_release(AHardwareBuffer* buffer) { assert(buffer->references > 0); --buffer->references; }
static int surfacesReleased = 0;
static void ASurfaceControl_release(ASurfaceControl*) {
    assert(visibility == ASURFACE_TRANSACTION_VISIBILITY_HIDE);
    assert(pthread_mutex_trylock(protectedLock) == EBUSY); ++surfacesReleased;
}
struct Renderer {
    struct State { struct { int width=16, height=24, x=100, y=80, xhot=3, yhot=4; bool visible=true; } cursor; } shared;
    State* state = &shared;
    float sourceWidth=800, sourceHeight=600, sourceLeft=20, sourceTop=10;
    int renderViewportX=5, renderViewportY=9, renderViewportW=1600, renderViewportH=900;
    pthread_mutex_t cursorOverlayLock = PTHREAD_MUTEX_INITIALIZER;
    ASurfaceControl* cursorSurfaceControl = nullptr;
    bool cursorOverlayGeometryDirty=false, cursorOverlayBufferDirty=false, cursorOverlayVisible=false;
    AHardwareBuffer* cursorOverlayPendingBuffer=nullptr;
    int32_t cursorOverlayX=0, cursorOverlayY=0;
    uint32_t cursorOverlayW=0, cursorOverlayH=0;
    void computeCursorOverlayScale(float*, float*);
    bool computeCursorOverlayRect(int32_t*, int32_t*, uint32_t*, uint32_t*);
    LorieBuffer* cursorOverlayRenderTarget = nullptr;
    void wakeCursorOverlayIfIdle() {}
    void resendCursorOverlayBuffer();
    void teardownCursorOverlay();
    void applyCursorOverlayIfDirty();
};
#include "production-cursor.h"
int main() {
    Renderer r;
    int32_t x=0, y=0; uint32_t w=0, h=0;
    // Activity Surface can arrive before shared X server state. Both entry
    // points must remain silent, even if an old render target still exists.
    r.state=nullptr;
    assert(!r.computeCursorOverlayRect(&x,&y,&w,&h));
    r.resendCursorOverlayBuffer();
    AHardwareBuffer earlyBuffer; LorieBuffer earlyTarget{&earlyBuffer};
    r.cursorOverlayRenderTarget=&earlyTarget;
    r.resendCursorOverlayBuffer();
    assert(earlyBuffer.references==1 && !r.cursorOverlayPendingBuffer);
    assert(!r.cursorOverlayGeometryDirty && !r.cursorOverlayBufferDirty);
    r.state=&r.shared; r.cursorOverlayRenderTarget=nullptr;
    r.resendCursorOverlayBuffer();
    assert(!r.cursorOverlayGeometryDirty && !r.cursorOverlayBufferDirty);
    assert(r.computeCursorOverlayRect(&x,&y,&w,&h));
    assert(x==159 && y==108 && w==32 && h==36); // hotspot, crop and nonuniform viewport scaling
    r.shared.cursor.visible=false; assert(!r.computeCursorOverlayRect(&x,&y,&w,&h));
    r.shared.cursor.visible=true; r.sourceWidth=0; assert(!r.computeCursorOverlayRect(&x,&y,&w,&h));
    r.sourceWidth=800; r.shared.cursor.width=0; assert(!r.computeCursorOverlayRect(&x,&y,&w,&h));
    r.shared.cursor.width=16;
    ASurfaceControl surface; AHardwareBuffer buffer;
    protectedLock=&r.cursorOverlayLock;
    r.cursorSurfaceControl=&surface;
    r.cursorOverlayGeometryDirty=r.cursorOverlayBufferDirty=r.cursorOverlayVisible=true;
    r.cursorOverlayPendingBuffer=&buffer;
    r.cursorOverlayX=159; r.cursorOverlayY=108; r.cursorOverlayW=32; r.cursorOverlayH=36;
    // The overlay thread must consume only the immutable snapshot, even after
    // the renderer has detached/unmapped shared state.
    r.state=nullptr;
    r.applyCursorOverlayIfDirty();
    assert(transactions==1 && bufferSets==1 && visibility==ASURFACE_TRANSACTION_VISIBILITY_SHOW);
    assert(lastSource.right==32 && lastSource.bottom==36 && lastDestination.left==159 && lastDestination.bottom==144);
    assert(!r.cursorOverlayPendingBuffer && buffer.references==0);
    assert(!r.cursorOverlayGeometryDirty && !r.cursorOverlayBufferDirty);
    r.applyCursorOverlayIfDirty(); assert(transactions==1); // idle is silent
    r.cursorOverlayGeometryDirty=true; r.cursorOverlayVisible=false;
    r.applyCursorOverlayIfDirty(); assert(transactions==2 && visibility==ASURFACE_TRANSACTION_VISIBILITY_HIDE);
    AHardwareBuffer abandoned;
    r.cursorSurfaceControl=nullptr; r.cursorOverlayBufferDirty=true; r.cursorOverlayPendingBuffer=&abandoned;
    r.applyCursorOverlayIfDirty(); assert(abandoned.references==0 && transactions==2);
    assert(pthread_mutex_trylock(&r.cursorOverlayLock)==0); pthread_mutex_unlock(&r.cursorOverlayLock);
    r.state=&r.shared; r.cursorSurfaceControl=&surface;
    AHardwareBuffer fresh, replaced; LorieBuffer target{&fresh};
    r.cursorOverlayRenderTarget=&target; r.cursorOverlayPendingBuffer=&replaced;
    r.resendCursorOverlayBuffer();
    assert(replaced.references==0 && fresh.references==2);
    assert(r.cursorOverlayX==159 && r.cursorOverlayY==108 && r.cursorOverlayW==32 && r.cursorOverlayH==36);
    assert(r.cursorOverlayGeometryDirty && r.cursorOverlayBufferDirty && r.cursorOverlayVisible);
    r.teardownCursorOverlay();
    assert(surfacesReleased==1 && r.cursorSurfaceControl==nullptr && fresh.references==1);
    assert(!r.cursorOverlayPendingBuffer && !r.cursorOverlayGeometryDirty && !r.cursorOverlayBufferDirty);
    puts("X11_CURSOR_OVERLAY_OK: surface-before-shared-state/atomic-shape-geometry/hide-before-release/ hotspot/crop/scale/hidden/snapshot/transaction-lifetime/buffer-release/idle");
}
