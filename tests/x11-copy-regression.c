/* Exercise production queue publication, exact clipping, ownership and failure grouping. */
#define _GNU_SOURCE
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
typedef struct { uint64_t id; int type; } LorieBuffer_Desc;
typedef struct { LorieBuffer_Desc desc; int refs, pending, sampleable, cpu_locked; } LorieBuffer;
typedef struct { LorieBuffer *buffer; void *mem, *locked; int wasLocked; } LoriePixmapPriv;
typedef struct { struct { unsigned width, height; } drawable; LoriePixmapPriv priv;
                 struct { void *ptr; } devPrivate; } PixmapRec, *PixmapPtr;
#define LORIE_PIXMAP_PRIV_FROM_PIXMAP(p) (&(p)->priv)
static struct test_server_state state;
static struct {
    int gpuPresentDisabled;
    struct { int legacyDrawing; } root;
    struct test_server_state *state;
    uint64_t gpuCopySerialCounter;
    int rootGpuCopyPending;
} server, *pvfb = &server;
static struct TestScreen { PixmapPtr devPrivate;
    PixmapPtr (*GetScreenPixmap)(struct TestScreen *);
} screen, *pScreenPtr = &screen;
static unsigned gpuCopyAttempts, gpuCopyOffloads, signals, registrations;
static unsigned fallback_reason;
static unsigned map_begins, map_ends;
static int gpu_lock_depth, flush_requires_gpu_lock, fail_next_mapping;
static void *rendererCond;
static int lorieConnectionAlive(void) { return 1; }
static int lorieRendererAvailable(void) { return 1; }
static LorieBuffer *lorieEnsureGpuSampleable(PixmapPtr p, int type) {
    assert(type == LORIEBUFFER_AHARDWAREBUFFER);
    return p->priv.buffer->sampleable ? p->priv.buffer : NULL;
}
static const LorieBuffer_Desc *LorieBuffer_description(LorieBuffer *b) { return &b->desc; }
static int LorieBuffer_unlock(LorieBuffer *b) {
    assert(b->cpu_locked);
    if (flush_requires_gpu_lock) assert(gpu_lock_depth==1);
    b->cpu_locked=0; ++map_ends; return 0;
}
static int LorieBuffer_lock(LorieBuffer *b, void **locked) {
    if (fail_next_mapping) { fail_next_mapping=0; *locked=NULL; return -1; }
    assert(!b->cpu_locked); b->cpu_locked=1; ++map_begins; *locked=b; return 0;
}
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
#ifdef TEST_SCOPED_CPU_ACCESS
#define EXA_PREPARE_DEST 1
#define EXA_PREPARE_SRC 0
static LoriePixmapPriv *exaGetPixmapDriverPrivate(PixmapPtr p) { return &p->priv; }
static int LorieBuffer_hasGpuCopyPending(LorieBuffer *b) { return b->pending!=0; }
static PixmapPtr get_screen_pixmap(struct TestScreen *s) { return s->devPrivate; }
static void lorie_mutex_lock(void *lock, void *owner) {
    (void)lock; (void)owner; assert(!gpu_lock_depth); ++gpu_lock_depth;
}
static void lorie_mutex_unlock(void *lock, void *owner) {
    (void)lock; (void)owner; assert(gpu_lock_depth==1); --gpu_lock_depth;
}
#endif
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
    src = (LorieBuffer){{7,1},1,0,1,0}; dst = (LorieBuffer){{8,1},1,0,1,0};
    source = (PixmapRec){.drawable={96,96},.priv={.buffer=&src}};
    destination = (PixmapRec){.drawable={96,96},.priv={.buffer=&dst}};
    screen.devPrivate = redirected ? &source : &destination;
    signals = registrations = gpuCopyAttempts = gpuCopyOffloads = fallback_reason = 0;
    map_begins=map_ends=0;
    gpu_lock_depth=flush_requires_gpu_lock=fail_next_mapping=0;
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

#ifdef TEST_SCOPED_CPU_ACCESS
static void scoped_cpu_access(void) {
    reset(0,0,0); screen.GetScreenPixmap=get_screen_pixmap;
    /* Publish initial CPU content once; pure GPU frames must not remap the root. */
    assert(!LorieBuffer_lock(&dst,&destination.priv.locked));
    lorieReleaseCpuMapping(&destination.priv);
    assert(!destination.priv.locked && !dst.cpu_locked && map_begins==1 && map_ends==1);
    for (int i=0;i<100;++i) lorieReleaseCpuMapping(&destination.priv);
    assert(map_begins==1 && map_ends==1);
    /* A real CPU write still maps the root and flushes it before releasing GPU ownership. */
    assert(loriePrepareAccess(&destination,EXA_PREPARE_DEST));
    assert(gpu_lock_depth==1 && dst.cpu_locked && !destination.priv.wasLocked);
    assert(destination.devPrivate.ptr==destination.priv.locked);
    flush_requires_gpu_lock=1;
    lorieFinishAccess(&destination,EXA_PREPARE_DEST);
    assert(!gpu_lock_depth && !dst.cpu_locked && !destination.priv.locked);
    /* CPU reads while a root/redirected GPU write is pending use the same ownership lock. */
    server.rootGpuCopyPending=1;
    assert(loriePrepareAccess(&destination,EXA_PREPARE_SRC));
    assert(gpu_lock_depth==1); lorieFinishAccess(&destination,EXA_PREPARE_SRC);
    server.rootGpuCopyPending=0; src.pending=1;
    assert(loriePrepareAccess(&source,EXA_PREPARE_SRC));
    assert(gpu_lock_depth==1); lorieFinishAccess(&source,EXA_PREPARE_SRC);
    src.pending=0; flush_requires_gpu_lock=0;
    /* A failed CPU mapping must not strand the shared GPU lock. */
    fail_next_mapping=1;
    assert(!loriePrepareAccess(&destination,EXA_PREPARE_DEST));
    assert(!gpu_lock_depth && !dst.cpu_locked);
    /* Existing persistent regular/FD CPU mappings retain their old ownership policy. */
    src.desc.type=0;
    assert(!LorieBuffer_lock(&src,&source.priv.locked));
    assert(loriePrepareAccess(&source,EXA_PREPARE_SRC) && source.priv.wasLocked);
    lorieFinishAccess(&source,EXA_PREPARE_SRC);
    assert(src.cpu_locked && source.priv.locked && !gpu_lock_depth);
    lorieReleaseCpuMapping(&source.priv);
}
#endif

int main(void) {
    const unsigned counts[]={1,16,17,25,32,127,128};
    for (unsigned i=0;i<sizeof(counts)/sizeof(counts[0]);++i)
        for (int redirected=0;redirected<2;++redirected) accepted(counts[i],0,redirected);
    accepted(25,UINT32_MAX-1,0); accepted(128,UINT32_MAX-3,1);
    capacity();
#ifdef TEST_SCOPED_CPU_ACCESS
    scoped_cpu_access();
    puts("X11_SCOPED_CPU_ACCESS_OK: lazy root mapping, CPU writes/reads, flush before GPU release, mapping failure unlock");
#endif
    puts("X11_COPY_CHUNKS_REGRESSION_OK: exact clipping, wrap, atomic capacity, grouped failure, root/redirected ownership");
    return 0;
}
