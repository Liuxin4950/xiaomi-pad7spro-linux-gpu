/* Exercise production queue publication, exact clipping, ownership and failure grouping. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "production-types.h"

typedef int Bool;
#define TRUE 1
#define FALSE 0
#define LORIEBUFFER_AHARDWAREBUFFER 1
#define min(a,b) ((a) < (b) ? (a) : (b))
typedef struct { int16_t x1, y1, x2, y2; } BoxRec, *BoxPtr;
typedef struct { int count; BoxPtr rects; } RegionRec, *RegionPtr;
#define RegionNumRects(r) ((r)->count)
#define RegionRects(r) ((r)->rects)
typedef struct { uint64_t id; } LorieBuffer_Desc;
typedef struct { LorieBuffer_Desc desc; int refs, pending, sampleable; } LorieBuffer;
typedef struct { LorieBuffer *buffer; void *mem, *locked; } LoriePixmapPriv;
typedef struct { struct { unsigned width, height; } drawable; LoriePixmapPriv priv; } PixmapRec, *PixmapPtr;
#define LORIE_PIXMAP_PRIV_FROM_PIXMAP(p) (&(p)->priv)
static struct test_server_state state;
static struct {
    int gpuPresentDisabled;
    struct { int legacyDrawing; } root;
    struct test_server_state *state;
    uint64_t gpuCopySerialCounter;
    int rootGpuCopyPending;
} server, *pvfb = &server;
static struct { PixmapPtr devPrivate; } screen, *pScreenPtr = &screen;
static unsigned gpuCopyAttempts, gpuCopyOffloads, signals, registrations;
static unsigned fallback_reason;
static void *rendererCond;
static int lorieConnectionAlive(void) { return 1; }
static int lorieRendererAvailable(void) { return 1; }
static LorieBuffer *lorieEnsureGpuSampleable(PixmapPtr p, int type) {
    assert(type == LORIEBUFFER_AHARDWAREBUFFER);
    return p->priv.buffer->sampleable ? p->priv.buffer : NULL;
}
static const LorieBuffer_Desc *LorieBuffer_description(LorieBuffer *b) { return &b->desc; }
static void LorieBuffer_unlock(LorieBuffer *b) { (void)b; }
static int LorieBuffer_lock(LorieBuffer *b, void **locked) { *locked = b; return 0; }
static void LorieBuffer_acquire(LorieBuffer *b) { ++b->refs; }
static void LorieBuffer_release(LorieBuffer *b) { assert(b->refs > 1); --b->refs; }
static void LorieBuffer_gpuCopyPendingInc(LorieBuffer *b) { ++b->pending; }
static void LorieBuffer_gpuCopyPendingDec(LorieBuffer *b) { assert(b->pending > 0); --b->pending; }
static void lorieRegisterBuffer(LorieBuffer *b) { assert(b); ++registrations; }
static void lorieTraceEvent(const char *stage, uint64_t a, uint64_t b) {
    (void)b;
    if (!strcmp(stage, "CopyFallback")) fallback_reason = (unsigned)a;
}
static void FatalError(const char *format, int status) { (void)format; (void)status; abort(); }
static int signal_renderer(void *condition) { (void)condition; ++signals; return 0; }
#define pthread_cond_signal signal_renderer
#include "production-copy.h"

static BoxRec boxes[129];
static LorieBuffer src, dst;
static PixmapRec source, destination;
static void reset(uint32_t read, uint32_t write, int redirected) {
    memset(&state, 0x5a, sizeof(state));
    state.gpuCopyQueue.readIndex = read;
    state.gpuCopyQueue.writeIndex = write;
    state.gpuCopyQueue.completedSerial = state.gpuCopyQueue.failedSerial = 0;
    memset(&server, 0, sizeof(server));
    server.state = &state;
    server.gpuCopySerialCounter = 50;
    src = (LorieBuffer){{7},1,0,1}; dst = (LorieBuffer){{8},1,0,1};
    source = (PixmapRec){{96,96},{&src,NULL,NULL}};
    destination = (PixmapRec){{96,96},{&dst,NULL,NULL}};
    screen.devPrivate = redirected ? &source : &destination;
    signals = registrations = gpuCopyAttempts = gpuCopyOffloads = fallback_reason = 0;
    /* Disjoint tiles leave protected holes that must never become a bounding-box copy. */
    for (unsigned i=0; i<129; ++i)
        boxes[i] = (BoxRec){(i%16)*4,(i/16)*4,(i%16)*4+2,(i/16)*4+2};
}

static void accepted(unsigned count, uint32_t base, int redirected) {
    reset(base, base, redirected);
    RegionRec region = {(int)count,boxes}; uint64_t serial = 0; void *held = NULL;
    assert(lorieTryScheduleGpuCopy(&source,&destination,&region,3,4,&serial,&held));
    unsigned chunks = (count+15)/16;
    assert(state.gpuCopyQueue.writeIndex == (uint32_t)(base+chunks));
    assert(serial==51 && signals==1 && gpuCopyOffloads==1);
    assert(src.refs==2 && src.pending==1);
    assert(redirected ? (dst.refs==2 && dst.pending==1 && held==&dst) :
                       (dst.refs==1 && held==NULL && server.rootGpuCopyPending==1));
    unsigned copied=0; uint8_t actual[96*96]={0}, expected[96*96]={0};
    for (unsigned i=0;i<count;++i)
        for (int y=boxes[i].y1;y<boxes[i].y2;++y)
            for (int x=boxes[i].x1;x<boxes[i].x2;++x) expected[(y+4)*96+x+3]=1;
    for (unsigned c=0;c<chunks;++c) {
        LorieGpuCopyEntry *entry=&state.gpuCopyQueue.entries[(base+c)%LORIE_GPU_COPY_QUEUE_CAPACITY];
        assert(entry->serial==serial && entry->srcBufferId==7 && entry->dstBufferId==8);
        assert(entry->xOff==3 && entry->yOff==4 && entry->numRects>0 && entry->numRects<=16);
        for (unsigned i=0;i<entry->numRects;++i) {
            assert(!memcmp(&entry->rects[i],&boxes[copied++],sizeof(BoxRec)));
            LorieGpuCopyRect r=entry->rects[i];
            for (int y=r.y1;y<r.y2;++y) for (int x=r.x1;x<r.x2;++x) actual[(y+4)*96+x+3]=1;
        }
        /* Draining an early chunk cannot release ownership before the common fence. */
        assert(!lorieGpuCopyIsDone(serial) && src.pending==1);
    }
    assert(copied==count && !memcmp(actual,expected,sizeof(actual)));
    /* A failure in the FIRST chunk must be visible when Present checks its final serial. */
    state.gpuCopyQueue.failedSerial=state.gpuCopyQueue.entries[base%LORIE_GPU_COPY_QUEUE_CAPACITY].serial;
    assert(lorieGpuCopyFailed(serial));
    state.gpuCopyQueue.completedSerial=serial;
    assert(lorieGpuCopyIsDone(serial));
    lorieGpuCopyAck(&source,held);
    assert(src.refs==1 && src.pending==0 && dst.refs==1 && dst.pending==0 && server.rootGpuCopyPending==0);
}

static void capacity(void) {
    reset(0,7,0);
    RegionRec region={25,boxes}; uint64_t serial=999; void *held=(void*)(uintptr_t)1;
    struct test_server_state before=state;
    assert(!lorieTryScheduleGpuCopy(&source,&destination,&region,0,0,&serial,&held));
    assert(!memcmp(&state,&before,sizeof(state)) && fallback_reason==5);
    assert(serial==999 && held==(void*)(uintptr_t)1 && signals==0 && registrations==0);
    assert(src.refs==1 && src.pending==0 && server.rootGpuCopyPending==0);
    reset(0,6,0);
    LorieGpuCopyEntry untouched[6]; memcpy(untouched,state.gpuCopyQueue.entries,sizeof(untouched));
    assert(lorieTryScheduleGpuCopy(&source,&destination,&region,0,0,&serial,&held));
    assert(state.gpuCopyQueue.writeIndex==8 && !memcmp(untouched,state.gpuCopyQueue.entries,sizeof(untouched)));
    lorieGpuCopyAck(&source,held);
    reset(0,0,0); region.count=129;
    assert(!lorieTryScheduleGpuCopy(&source,&destination,&region,0,0,&serial,&held));
    assert(fallback_reason==4 && state.gpuCopyQueue.writeIndex==0 && src.refs==1);
}

int main(void) {
    const unsigned counts[]={1,16,17,25,32,127,128};
    for (unsigned i=0;i<sizeof(counts)/sizeof(counts[0]);++i)
        for (int redirected=0;redirected<2;++redirected) accepted(counts[i],0,redirected);
    accepted(25,UINT32_MAX-1,0); accepted(128,UINT32_MAX-3,1);
    capacity();
    puts("X11_COPY_CHUNKS_REGRESSION_OK: exact clipping, wrap, atomic capacity, grouped failure, root/redirected ownership");
    return 0;
}
