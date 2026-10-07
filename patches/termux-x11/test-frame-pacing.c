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

int main(void)
{
    LorieFramePacer pacer = {0};
    uint32_t accepted = 0;

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

    puts("frame pacing timing cases passed");
    return 0;
}
