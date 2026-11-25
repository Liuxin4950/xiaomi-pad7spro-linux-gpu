#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Archive an audited r3.6 candidate, its matching CLI and corresponding source; never install or publish."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def source_files(root):
    excluded = {'.git', '.gradle', '.cxx', '__pycache__', 'build', '.idea'}
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if excluded.intersection(rel.parts) or path.is_dir():
            continue
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('source symlink escapes export: ' + str(rel))
        elif path.suffix in ('.so', '.o', '.a', '.apk', '.jks', '.keystore', '.pyc'):
            continue
        yield path, rel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--x11-build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new directory')
    args = parser.parse_args()
    build = args.x11_build.resolve(strict=True)
    report = json.loads((build / 'build-report.json').read_text())
    lock = json.loads((ROOT / 'sources.lock.json').read_text())
    if report['state'] != 'apk-built-not-installed' or report['patches'] != lock['termux_x11']['patches']:
        raise ValueError('build does not match the current locked patches')
    for row in report['patches']:
        if sha(ROOT / row['path']) != row['sha256']:
            raise ValueError('locked patch drift: ' + row['path'])
    if sha(build / 'candidate.apk') != report['apk_sha256']:
        raise ValueError('APK checksum mismatch')
    companion = build / 'x11-companion'
    for name, expected in report['companion_sha256'].items():
        if sha(companion / name) != expected:
            raise ValueError('companion checksum mismatch: ' + name)
    for name, expected in report['native_source_sha256'].items():
        if sha(build / 'source/lorie/src/main/cpp' / name) != expected:
            raise ValueError('native source drift: ' + name)
    for name, expected in report['packaging_source_sha256'].items():
        if sha(build / 'source' / name) != expected:
            raise ValueError('Java/resource/build configuration drift: ' + name)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    # Git's inventory includes authorized uncommitted source changes, not ignored
    # output, user profiles, signing keys or unrelated directories on the device.
    names = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-c', '-o', '--exclude-standard', '-z']).split(b'\0')
    paths = sorted({Path(name.decode()) for name in names if name})
    allowed = {'src', 'scripts', 'tests', 'patches', 'reference', 'docs', 'evidence', 'vendor', '.github'}
    root_files = {'README.md', 'LICENSE', 'LICENSE-STATUS.md', 'THIRD_PARTY.md', 'RELEASE-CHECKLIST.md',
                  'sources.lock.json', 'CMakeLists.txt', 'AGENTS.md', '.gitignore', '.gitattributes'}
    inventory = {}
    with tarfile.open(output / 'pad-gpu-r3.6-rc1-termux.tar.gz', 'w:gz') as archive:
        base = 'pad-gpu-r3.6-rc1'
        for relative in paths:
            if relative.parts[0] not in allowed and relative.as_posix() not in root_files:
                continue
            path = ROOT / relative
            if path.is_symlink() or not path.is_file():
                raise ValueError('regular repository source required: ' + str(relative))
            if path.suffix in ('.apk', '.so', '.jks', '.keystore', '.pyc'):
                raise ValueError('unexpected binary or key in source inventory: ' + str(relative))
            inventory[relative.as_posix()] = sha(path)
            archive.add(path, arcname=base + '/' + relative.as_posix(), recursive=False)
        for path in sorted(companion.iterdir()):
            archive.add(path, arcname=base + '/artifacts/x11-companion/' + path.name, recursive=False)
        archive.add(build / 'candidate.apk', arcname=base + '/artifacts/termux-x11.apk', recursive=False)
    corresponding = output / 'termux-x11-corresponding-source.tar.gz'
    with tarfile.open(corresponding, 'w:gz') as archive:
        for path, relative in source_files(build / 'source'):
            archive.add(path, arcname='termux-x11/' + relative.as_posix(), recursive=False)
    (output / 'source-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    for name in ('build-report.json', 'dependency-artifacts.json'):
        (output / name).write_bytes((build / name).read_bytes())
    manifest = dict(format=1, release_id='r3.6-rc1', status='candidate-not-final',
                    installed=False, publicly_published=False, linux_binary_prefix_included=False,
                    version_name=report['version_name'], apk_sha256=report['apk_sha256'],
                    repository_base_commit=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                    source_scope='working tree inventory including uncommitted source; not a Git tag',
                    known_limits=['fast Bluetooth pointer motion not accepted',
                                  'new Termux on-device cold startup not verified',
                                  'fresh rootfs/OS4 keepcaps provisioning incomplete',
                                  'no physical 120FPS or whole-device power claim',
                                  'binary redistribution review incomplete; local candidate only'])
    (output / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
    sums = ''.join(sha(p) + '  ' + p.name + '\n' for p in sorted(output.iterdir()) if p.is_file())
    (output / 'SHA256SUMS').write_text(sums)
    print(json.dumps(dict(output=str(output), release=manifest, files=len(inventory)), indent=2))


if __name__ == '__main__':
    main()
