#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Audit saved cursor-probe screenshots and internal counters; never operates UI."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageChops


def pixels(path):
    image = Image.open(path).convert('RGB')
    red, green, blue = image.split()
    channels = {
        'red': [red.point(lambda v: 255 if v > 200 else 0),
                green.point(lambda v: 255 if v < 100 else 0), blue.point(lambda v: 255 if v < 100 else 0)],
        'blue': [red.point(lambda v: 255 if v < 100 else 0),
                 green.point(lambda v: 255 if v < 120 else 0), blue.point(lambda v: 255 if v > 180 else 0)],
    }
    result = {}
    for color, masks in channels.items():
        mask = ImageChops.multiply(ImageChops.multiply(masks[0], masks[1]), masks[2])
        mask.paste(0, (0, 0, image.width, 90))  # exclude Android status bar, not desktop pixels
        box = mask.getbbox()
        result[color] = {'count': mask.histogram()[255], 'bbox': list(box) if box else None}
    return result


def audit(directory):
    record = json.loads((directory / 'result.json').read_text())
    if record.get('sampling_errors'):
        raise ValueError('counter sampling failed')
    stages = {row['phase']: row for row in record['stages']}
    if record['probe_exit'] != 0:
        raise ValueError('probe did not exit normally')
    for stage in ['red-left', 'red-right', 'hidden', 'blue-wide', 'surface-recovery']:
        actual = pixels(directory / (stage + '.png'))
        if actual != stages[stage]['pixels']:
            raise ValueError('screenshot differs from recorded pixels: ' + stage)
    first = stages['red-left']['pixels']['red']
    if first['count'] != 576 or first['bbox'] is None:
        raise ValueError('red calibration square missing or damaged')
    ox, oy = first['bbox'][0] - 195, first['bbox'][1] - 293
    for stage, color, x, y, width, height in [
            ('red-left', 'red', 200, 300, 24, 24), ('red-right', 'red', 1300, 700, 24, 24),
            ('blue-wide', 'blue', 800, 500, 48, 16), ('surface-recovery', 'blue', 800, 500, 48, 16)]:
        expected = {'count': width * height,
                    'bbox': [x - 5 + ox, y - 7 + oy, x - 5 + ox + width, y - 7 + oy + height]}
        if stages[stage]['pixels'][color] != expected:
            raise ValueError('cursor size/hotspot/position mismatch: ' + stage)
        other = 'blue' if color == 'red' else 'red'
        if stages[stage]['pixels'][other]['count']:
            raise ValueError('old cursor shape remained: ' + stage)
        if f'pointer {x} {y}' not in stages[stage].get('replies', []):
            raise ValueError('X11 pointer was not read back: ' + stage)
    if any(stages['hidden']['pixels'][color]['count'] for color in ['red', 'blue']):
        raise ValueError('cursor remained visible while hidden')
    zero_draw = ['idle', 'red-left', 'motion', 'red-right', 'hidden', 'blue-wide']
    if any(stages[name]['frames'] != 0 for name in zero_draw):
        raise ValueError('cursor-only stage triggered a main-surface draw')
    warps = [int(line.split()[1]) for line in stages['motion']['replies'] if line.startswith('warps ')]
    if len(warps) != 1 or warps[0] < 100 or not 1.8 <= stages['motion']['elapsed_s'] <= 3:
        raise ValueError('motion workload is missing or incomplete')
    samples = [json.loads(line) for line in (directory / 'samples.jsonl').read_text().splitlines()]
    motion = [row for row in samples if row['phase'] == 'motion']
    if len({(row['cursor_x'], row['cursor_y']) for row in motion}) < 20:
        raise ValueError('shared-state samples do not show cursor movement')
    switches = record.get('activity_switches', [])
    foreground_verified = len(switches) == 2 and all(
        row['request'].split('/')[0] + '/' in ' '.join(row.get('focus', [])) and
        'Status: ok' in row.get('output', '') for row in switches)
    if switches and not foreground_verified:
        raise ValueError('foreground switch was requested but not verified')
    surface_unavailable_observed = any(not row['surface_available'] for row in samples
                                      if row['phase'] == 'surface-recovery')
    return dict(accepted=True,scope='cursor-only motion/shape/hide/hotspot and one foreground recovery',
                motion_commands=warps[0], main_surface_draws_during_motion=0,
                physical_cursor_pixels={'red': 576, 'blue': 768}, viewport_offset=[ox, oy],
                recovery_main_surface_draws=stages['surface-recovery']['frames'],
                foreground_switch_verified=foreground_verified,
                surface_unavailable_observed=surface_unavailable_observed,
                limits='Not physical FPS, input latency, whole-device power, zoom, rotation or cold-start acceptance.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.directory), indent=2))
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit('CURSOR_ACCEPTANCE_REJECTED: ' + str(error))


if __name__ == '__main__':
    main()
