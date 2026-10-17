/* Compile with -I /path/to/patched/lorie/src/main/cpp/lorie. */
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include "frame-pacing.h"

static void check_rate(uint32_t source_rate, uint32_t cap, uint32_t expected)
{
    LorieFramePacer pacer = {0};
    uint32_t accepted = 0;
    for (uint64_t i = 0; i < source_rate * 10; i++)
        accepted += lorieFramePacerAccept(&pacer, i * UINT64_C(1000000000) / source_rate, cap);
    assert(accepted == expected);
}

/* Interleave accepted ticks at each potentially blocking renderer stage.
 * The real gate helpers preserve a tick arriving during copy, fence or swap,
 * while coalescing multiple ticks instead of accumulating render credits. */
static void check_frame_gate(void)
{
    for (unsigned stage = 0; stage < 5; ++stage) {
        volatile uint8_t waiting = 0;
        assert(lorieFrameGateReady(&waiting));
        assert(lorieFrameGateBegin(&waiting));
        assert(!lorieFrameGateBegin(&waiting));
        for (unsigned step = 0; step < 5; ++step) {
            if (step == stage) {
                lorieFrameGateTick(&waiting);
                lorieFrameGateTick(&waiting);
            }
        }
        assert(lorieFrameGateReady(&waiting));
        assert(lorieFrameGateBegin(&waiting));
        assert(!lorieFrameGateReady(&waiting));
        assert(!lorieFrameGateBegin(&waiting));
    }
    volatile uint8_t waiting = 1;
    lorieFrameGateTick(&waiting);
    assert(lorieFrameGateBegin(&waiting));
    assert(!lorieFrameGateReady(&waiting));
    // No tick during a frame means it cannot immediately draw again.
    assert(!lorieFrameGateBegin(&waiting));
}

int main(void)
{
    LorieFramePacer pacer = {0};
    uint32_t accepted = 0;

    check_frame_gate();
    check_rate(120, 60, 600);
    check_rate(90, 60, 600);
    check_rate(240, 60, 600);
    check_rate(60, 60, 600);
    check_rate(30, 60, 300);
    check_rate(120, 120, 1200);
    check_rate(120, 240, 1200);
    check_rate(120, 0, 1200);
    check_rate(120, 1, 10);

    /* 119.94 Hz callbacks, with alternating 100 us scheduling jitter. */
    for (uint64_t i = 0; i < 11994; i++) {
        uint64_t timestamp = i * UINT64_C(100000000000) / 11994;
        if (i & 1)
            timestamp += 100000;
        accepted += lorieFramePacerAccept(&pacer, timestamp, 60);
    }
    assert(accepted >= 5999 && accepted <= 6001);

    /* A resume uses one newest callback, never a burst for missed deadlines. */
    assert(lorieFramePacerAccept(&pacer, UINT64_C(200000000000), 60));
    assert(!lorieFramePacerAccept(&pacer, UINT64_C(200000000000), 60));
    assert(!lorieFramePacerAccept(&pacer, UINT64_C(200000000001), 60));
    assert(lorieFramePacerAccept(&pacer, UINT64_C(200020000000), 60));

    /* A lower monotonic epoch or a changed cap reinitializes the deadline. */
    assert(lorieFramePacerAccept(&pacer, 42, 60));
    assert(!lorieFramePacerAccept(&pacer, 42, 60));
    assert(lorieFramePacerAccept(&pacer, 42, 120));
    assert(!lorieFramePacerAccept(&pacer, 42, 120));
    assert(lorieFramePacerAccept(&pacer, 42, 0));
    assert(lorieFramePacerAccept(&pacer, 42, 0));
    assert(lorieFramePacerAccept(&pacer, 42, 60));

    // No callback counting loop is needed to resume a ten-second idle MSC.
    assert(lorieFrameClockMSC(100, 100, 60, 0) == 1);
    assert(lorieFrameClockMSC(100, UINT64_C(10000000100), 60, 1) == 601);
    assert(lorieFrameClockMSC(100, 99, 60, 601) == 601);
    assert(lorieFrameClockMSC(100, 200, 60, 601) == 601);
    assert(lorieFrameClockMSC(100, 200, 0, 601) == 601);
    puts("frame pacing timing and idle MSC cases passed");
    return 0;
}
