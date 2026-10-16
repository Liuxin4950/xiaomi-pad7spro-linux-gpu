#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify/select a release with durable backups and recoverable entry migration."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

LINK_DIR = Path('/usr/local/bin')
DESKTOP_SCRIPT = Path(__file__).resolve().with_name('activate-desktop.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_report(directory, report):
    fd, name = tempfile.mkstemp(prefix='.restore-plan.', dir=directory)
    try:
        with os.fdopen(fd, 'w') as target:
            json.dump(report, target, ensure_ascii=False, indent=2)
            target.write('\n')
            target.flush()
            os.fsync(target.fileno())
        os.replace(name, directory / 'restore-plan.json')
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.lexists(name):
            os.unlink(name)


def replace_link(path, target):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    os.close(fd)
    os.unlink(name)
    try:
        os.symlink(target, name)
        os.replace(name, path)
    finally:
        if os.path.lexists(name):
            os.unlink(name)


def verify_release(prefix):
    prefix = prefix.resolve(strict=True)
    if prefix.parent != Path('/opt'):
        raise ValueError('dedicated prefix directly below /opt required')
    manifest = json.loads((prefix / 'install-manifest.json').read_text())
    if manifest['prefix'] != str(prefix):
        raise ValueError('manifest prefix mismatch')
    for name, expected in manifest['files'].items():
        path = prefix / name
        if not path.resolve().is_relative_to(prefix) or digest(path) != expected:
            raise ValueError('manifest mismatch: ' + name)
    for name, target in manifest['symlinks'].items():
        path = prefix / name
        if not path.is_symlink() or str(path.readlink()) != target or not path.resolve().is_relative_to(prefix):
            raise ValueError('symlink mismatch: ' + name)
    for name in ('gpu-run', 'gpu-launcher'):
        if not os.access(prefix / 'bin' / name, os.X_OK):
            raise ValueError('missing executable: ' + name)
    return prefix


def build_plan(prefix, termux_home=None):
    command = ['python3', str(DESKTOP_SCRIPT)]
    if termux_home is not None:
        command += ['--termux-home', str(termux_home)]
    desktop = json.loads(subprocess.check_output(command, text=True))
    links = {}
    for name in ('gpu-run', 'gpu-launcher'):
        link = LINK_DIR / name
        if not link.is_symlink():
            raise ValueError('expected existing symlink: ' + str(link))
        links[str(link)] = dict(before=str(link.readlink()), after=str(prefix / 'bin' / name))
    return dict(format=1, applied=False, state='planned', prefix=str(prefix), links=links,
                desktop=desktop, desktop_command=command, entries=[])


def snapshot(backup, report):
    backup.mkdir(parents=True, exist_ok=False, mode=0o700)
    backup.chmod(0o700)
    for index, item in enumerate(report['desktop']['entries']):
        path = Path(item['path'])
        previous = path.lstat()
        if not stat.S_ISREG(previous.st_mode):
            raise ValueError('migration entry must be a regular file: ' + str(path))
        if digest(path) != item['before_sha256']:
            raise ValueError('entry changed since planning: ' + str(path))
        saved = backup / f'entry-{index}'
        shutil.copy2(path, saved)
        saved.chmod(0o600)
        with saved.open('rb') as source:
            os.fsync(source.fileno())
        # copy2 retains xattrs; the original ownership/mode are recorded separately.
        xattrs = {name: base64.b64encode(os.getxattr(path, name)).decode('ascii')
                  for name in os.listxattr(path)}
        report['entries'].append(dict(**item, backup=saved.name, mode=stat.S_IMODE(previous.st_mode),
                                      uid=previous.st_uid, gid=previous.st_gid, xattrs=xattrs))
    report['state'] = 'prepared'
    write_report(backup, report)


def restore(backup, report, apply=False):
    # Validate every object before restoring any, including post-deploy user edits.
    for name, item in report['links'].items():
        link = Path(name)
        if not link.is_symlink() or str(link.readlink()) not in (item['before'], item['after']):
            raise ValueError('link changed outside this transaction: ' + name)
    for item in report['entries']:
        path, saved = Path(item['path']), backup / item['backup']
        if not saved.resolve().is_relative_to(backup.resolve()) or digest(saved) != item['before_sha256']:
            raise ValueError('backup missing or corrupted: ' + str(saved))
        if path.is_symlink() or not path.is_file() or digest(path) not in (item['before_sha256'], item['after_sha256']):
            raise ValueError('entry changed outside this transaction: ' + str(path))
    if not apply:
        return
    report['state'] = 'rolling-back'
    write_report(backup, report)
    for item in report['entries']:
        path = Path(item['path'])
        fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
        os.close(fd)
        try:
            shutil.copy2(backup / item['backup'], temporary)
            os.chown(temporary, item['uid'], item['gid'])
            os.chmod(temporary, item['mode'])
            for name, value in item.get('xattrs', {}).items():
                os.setxattr(temporary, name, base64.b64decode(value))
            with open(temporary, 'rb') as source:
                os.fsync(source.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.lexists(temporary):
                os.unlink(temporary)
    for name, item in report['links'].items():
        replace_link(Path(name), item['before'])
    directories = set()
    for item in report['entries']:
        path = Path(item['path'])
        if path.suffix == '.desktop':
            directories.update(parent for parent in path.parents if parent.name == 'applications')
    report['desktop_database_refresh_errors'] = []
    for directory in sorted(directories):
        try:
            subprocess.run(['update-desktop-database', str(directory)], check=True, capture_output=True, text=True)
        except (OSError, subprocess.SubprocessError) as error:
            report['desktop_database_refresh_errors'].append(str(error))
    report.update(state='rolled-back', applied=False)
    write_report(backup, report)


def activate(prefix, backup, termux_home=None):
    report = build_plan(prefix, termux_home)
    snapshot(backup, report)
    try:
        report['state'] = 'applying'
        write_report(backup, report)
        for name, item in report['links'].items():
            path = Path(name)
            if not path.is_symlink() or str(path.readlink()) != item['before']:
                raise ValueError('link changed since planning: ' + name)
            replace_link(path, item['after'])
        subprocess.run(report['desktop_command'] + ['--apply', '--expected-plan',
                       str(backup / 'restore-plan.json')], check=True, capture_output=True, text=True)
        for item in report['entries']:
            if digest(Path(item['path'])) != item['after_sha256']:
                raise ValueError('entry verification failed: ' + item['path'])
        report.update(state='activated', applied=True)
        write_report(backup, report)
    except Exception as error:
        report['activation_error'] = str(error)
        try:
            restore(backup, report, apply=True)
        except Exception as recovery:
            report.update(state='rollback-failed', rollback_error=str(recovery))
            write_report(backup, report)
            raise RuntimeError(f'activation failed; rollback needs attention: {recovery}; backup={backup}') from error
        raise RuntimeError(f'activation failed and restored original entries; backup={backup}') from error
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prefix', type=Path, nargs='?')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--termux-home', type=Path)
    parser.add_argument('--restore', type=Path, help='inspect recovery; add --apply to restore')
    args = parser.parse_args()
    try:
        if args.restore is not None:
            if args.prefix or args.backup or args.termux_home:
                parser.error('--restore cannot be combined with a release or migration options')
            backup = args.restore.resolve(strict=True)
            report = json.loads((backup / 'restore-plan.json').read_text())
            if report.get('format') != 1:
                raise ValueError('unsupported recovery report format')
            restore(backup, report, apply=args.apply)
            print(json.dumps(dict(restore_applied=args.apply, report=report), ensure_ascii=False, indent=2))
            return
        if args.prefix is None or (args.apply and args.backup is None):
            parser.error('provide a release prefix; --apply also requires --backup')
        prefix = verify_release(args.prefix)
        if args.apply:
            report = activate(prefix, args.backup.resolve(), args.termux_home)
        else:
            report = build_plan(prefix, args.termux_home)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
