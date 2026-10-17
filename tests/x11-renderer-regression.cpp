// Execute the production redraw function with deterministic GL/ownership stubs.
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>
#include "frame-pacing.h"

using GLuint = unsigned;
using GLsizei = int;
using EGLSync = void*;
using EGLuint64KHR = uint64_t;
using EGLBoolean = int;
constexpr int GL_SCISSOR_TEST = 1, GL_COLOR_BUFFER_BIT = 2, GL_TEXTURE_2D = 3;
constexpr int GL_RGBA = 4, GL_UNSIGNED_BYTE = 5, EGL_SYNC_FENCE_KHR = 6;
constexpr int EGL_TRUE = 1, LORIEBUFFER_FD = 2, CVT_H_GRANULARITY = 8;
#define FALSE false
#define log(...) ((void)0)

static std::vector<std::string> events;
static bool missingBuffer, tickDuringWait;
struct LorieBuffer_Desc { int width = 800, height = 600, stride = 800, type = 1; };
struct LorieBuffer { LorieBuffer_Desc desc; } root;
struct SharedState {
    uint64_t rootWindowTextureID = 20;
    volatile uint8_t waitForNextFrame = 0;
    bool drawRequested = true;
    int lock = 0, lockingPid = 0, renderedFrames = 0;
    struct {
        int x = 10, y = 10, lock = 0, lockingPid = 0, width = 16, height = 16;
        bool updated = false, moved = true;
        uint8_t bits[16 * 16 * 4]{};
    } cursor;
} shared;
static void event(const char* name) { events.emplace_back(name); }
static void pthread_spin_lock(int*) {}
static void pthread_spin_unlock(int*) {}
static LorieBuffer* LorieBufferList_findById(int*, uint64_t) {
    return missingBuffer ? nullptr : &root;
}
static const LorieBuffer_Desc* LorieBuffer_description(LorieBuffer* b) { return &b->desc; }
static int ANativeWindow_getHeight(int) { return 600; }
static int ANativeWindow_getWidth(int) { return 800; }
static void glDisable(int) {}
static void glViewport(int, int, int, int) {}
static void glClearColor(float, float, float, float) {}
static void glClear(int) { event("clear"); }
static void LorieBuffer_bindTexture(LorieBuffer*) { event("bind-root"); }
static uint8_t LorieBuffer_isRgba(LorieBuffer*) { return 0; }
static EGLSync eglCreateSyncKHR(int, int, void*) { event("fence"); return &shared; }
static void glFlush() { event("flush"); }
static void glTexImage2D(int, int, int, int, int, int, int, int, void*) { event("cursor-upload"); }
static void lorie_mutex_lock(int* lock, int*) {
    assert(!*lock); *lock = 1;
    if (lock == &shared.lock) event("root-lock");
}
static void lorie_mutex_unlock(int* lock, int*) {
    assert(*lock); *lock = 0;
    if (lock == &shared.lock) event("root-unlock");
}
static void lorieTraceEvent(const char*, uint64_t, uint64_t) {}
static void lorieTraceTriple(const char*, uint64_t, uint64_t, uint64_t) {}
static uint64_t lorieTraceSurface(int, int) { return 1; }
static void ATrace_beginSection(const char*) {}
static void ATrace_endSection() {}
static EGLBoolean eglSwapBuffers(int, int) {
    assert(!shared.lock); event("swap"); return EGL_TRUE;
}
static void printEglError(const char*, int) { assert(false); }
static float panToCursor(float offset, float, float, float) { return offset; }

struct Renderer {
    SharedState* state = &shared;
    int bufferLock = 0, buffers = 0, removedBuffers = 0;
    int expectedW = 800, expectedH = 600, win = 1, egl_display = 1, sfc = 1;
    int viewportX = 0, viewportY = 0, viewportW = 800, viewportH = 600;
    int zoomPercent = 100, hiddenBottom = 0;
    bool bottomWasHidden = false, followCursorPan = true;
    float hiddenPanSourceTop = -1, panSourceTop = 0, panSourceLeft = 0;
    float pinchAnchorSourceX = -1, pinchAnchorSourceY = -1;
    float pinchAnchorFracX = .5f, pinchAnchorFracY = .5f;
    struct { GLuint id = 1; } cursor;
    void redrawLocked(bool*);
    void applyPendingGpuCopies() { event("standalone-copy"); }
    uint64_t applyPendingGpuCopiesLocked() {
        assert(shared.lock); event("copy"); return 42;
    }
    void finishGpuCopiesLocked(EGLSync fence, uint64_t serial) {
        assert(fence && serial == 42 && shared.lock); event("wait");
        if (tickDuringWait) lorieFrameGateTick(&shared.waitForNextFrame);
    }
    void reportViewport(int, int, int, int, float, float, float, float) {}
    void drawRegion(GLuint, float, float, float, float, float, float, float, float, uint8_t) {
        assert(shared.lock); event("root-draw");
    }
    void bindTexture(GLuint) {}
    void drawCursor(float, float, float, float, float, float) {
        assert(shared.lock); event("cursor-draw");
    }
};

#include "production-redraw.h"

static void reset() {
    shared = SharedState{}; root = LorieBuffer{};
    missingBuffer = tickDuringWait = false; events.clear();
}

int main() {
    for (bool tick : {false, true}) {
        reset(); Renderer renderer; bool waiting = false;
        shared.cursor.updated = true; tickDuringWait = tick;
        renderer.redrawLocked(&waiting);
        const std::vector<std::string> expected = {"root-lock", "copy", "clear", "bind-root",
            "root-draw", "cursor-upload", "cursor-draw", "fence", "flush", "wait",
            "root-unlock", "swap"};
        assert(events == expected);
        assert(!waiting && !shared.lock && shared.renderedFrames == 1);
        assert(lorieFrameGateReady(&shared.waitForNextFrame) == tick);
        // A tick during ownership wait permits the next draw. Without a tick,
        // repeated wakeups must not render or submit another frame.
        events.clear(); tickDuringWait = false;
        renderer.redrawLocked(&waiting);
        assert(shared.renderedFrames == (tick ? 2 : 1));
        if (!tick) assert(events.empty());
    }
    reset(); Renderer renderer; bool waiting = false;
    missingBuffer = true; renderer.redrawLocked(&waiting);
    assert(waiting && lorieFrameGateReady(&shared.waitForNextFrame));
    assert(events == std::vector<std::string>{"standalone-copy"});
    reset(); root.desc.height = 599; waiting = false;
    renderer.redrawLocked(&waiting);
    assert(waiting && lorieFrameGateReady(&shared.waitForNextFrame));
    assert(events == std::vector<std::string>{"standalone-copy"});
    puts("X11_RENDERER_FRAME_OK: copy before clear, one final flush, fence before unlock, tick retained, invalid-root drain");
}
