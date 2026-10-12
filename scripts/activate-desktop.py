#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Migrate this device's known desktop entries and Termux startup script."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OLD = '/opt/mali-bridge-canary/bin/gpu-app.sh'
RUNNER = '/usr/local/bin/gpu-run'


def desktop_text(path, text):
    updated = text.replace(OLD, RUNNER)
    lines = []
    is_cc = path.name in ('CC Switch.desktop', 'cc-switch-handler.desktop')
    for line in updated.splitlines():
        if path.name in ('trae-cn.desktop', 'trae-cn-url-handler.desktop') and line.startswith('Exec=/usr/share/trae-cn/trae-cn'):
            suffix = line[len('Exec=/usr/share/trae-cn/trae-cn'):]
            if not suffix or suffix.startswith(' '):
                line = 'Exec=' + RUNNER + ' trae' + suffix
        if line.startswith('Exec=') and (path.name.startswith('libreoffice-') or path.name in ('启动Word.desktop','启动Excel.desktop','启动PPT.desktop')):
            for command in ('soffice','libreoffice','/usr/bin/soffice','/usr/bin/libreoffice'):
                if line[5:] == command or line[5:].startswith(command+' '):
                    line = 'Exec=' + RUNNER + ' auto /usr/bin/libreoffice' + line[5+len(command):]
                    break
        if is_cc and line.startswith('Exec='):
            # Only replace the known entry points; preserve all URL placeholders.
            for command in ('env GALLIUM_DRIVER=llvmpipe cc-switch', '"/usr/bin/cc-switch"', '/usr/bin/cc-switch'):
                if line[5:] == command or line[5:].startswith(command + ' '):
                    line = 'Exec=' + RUNNER + ' cc-switch' + line[5 + len(command):]
                    break
        if path.parent.name == 'helpers' and path.name == 'chatgpt.desktop':
            if line == 'X-XFCE-Commands=' + RUNNER:
                line += ' chatgpt'
        lines.append(line)
    return '\n'.join(lines) + '\n'


def atomic_write(path, data):
    previous = path.stat()
    try:
        selinux = os.getxattr(path, 'security.selinux')
    except OSError:
        selinux = None
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chown(temporary, previous.st_uid, previous.st_gid)
        os.chmod(temporary, stat.S_IMODE(previous.st_mode))
        if selinux is not None:
            os.setxattr(temporary, 'security.selinux', selinux)
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            Path(temporary).unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--termux-home', type=Path, default=Path('/proc/1/root/data/data/com.termux/files/home'))
    args = parser.parse_args()
    runner = Path(RUNNER)
    if not runner.is_file() or not os.access(runner, os.X_OK):
        raise SystemExit('Install and verify /usr/local/bin/gpu-run first')
    changes = {}
    locations = [Path('/root/Desktop'), Path('/usr/share/applications'),
                 Path('/root/.local/share/applications'), Path('/root/.local/share/xfce4/helpers'),
                 Path('/root/.config/xfce4/panel')]
    for directory in locations:
        for path in directory.rglob('*.desktop') if directory.exists() else ():
            original = path.read_text()
            updated = desktop_text(path, original)
            if updated != original:
                # Do not reformat unrelated desktop files.
                if OLD not in original and path.name not in ('CC Switch.desktop', 'cc-switch-handler.desktop', 'trae-cn.desktop', 'trae-cn-url-handler.desktop'):
                    if not path.name.startswith('libreoffice-') and path.name not in ('启动Word.desktop','启动Excel.desktop','启动PPT.desktop'):
                        continue
                changes[path] = updated.encode()
    fixed = {
        Path('/opt/mali-bridge-canary/bin/gpu-app.sh'): ROOT / 'reference/chroot/gpu-app.sh',
        args.termux_home / 'mali-work/desktop-zink.sh': ROOT / 'reference/termux/desktop-zink.sh',
        args.termux_home / 'debian-desktop.sh': ROOT / 'reference/termux/debian-desktop.sh',
        args.termux_home / '.shortcuts/debian-zink.sh': ROOT / 'reference/termux/debian-zink-widget.sh',
    }
    for path, source in fixed.items():
        if not path.is_file():
            raise SystemExit('Expected existing device entry missing: ' + str(path))
        data = source.read_bytes()
        if path.read_bytes() != data:
            changes[path] = data
    # Validate every changed desktop entry before mutating any entry.
    with tempfile.TemporaryDirectory(prefix='pad-gpu-desktop-') as temp:
        for index, (path, data) in enumerate(changes.items()):
            if path.suffix != '.desktop' or path.parent.name == 'helpers':
                continue
            proposed = Path(temp) / (str(index) + '.desktop')
            proposed.write_bytes(data)
            check = subprocess.run(['desktop-file-validate', str(proposed)], capture_output=True, text=True)
            if check.returncode:
                raise SystemExit('Desktop validation failed for ' + str(path) + '\n' + check.stdout + check.stderr)
    report = []
    for path, data in changes.items():
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        if args.apply:
            atomic_write(path, data)
        report.append({'path': str(path), 'before_sha256': before,
                       'after_sha256': hashlib.sha256(data).hexdigest()})
    print(json.dumps({'applied': args.apply, 'entries': report}, ensure_ascii=False, indent=2))
    if args.apply:
        for directory in ('/usr/share/applications', '/root/.local/share/applications'):
            subprocess.run(['update-desktop-database', directory], check=True)
        for path in changes:
            if path.parent == Path('/root/Desktop'):
                subprocess.run(['gio', 'set', str(path), 'metadata::trusted', 'true'], capture_output=True)


if __name__ == '__main__':
    main()
