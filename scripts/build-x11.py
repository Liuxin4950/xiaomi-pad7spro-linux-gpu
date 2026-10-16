#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rebuild X11 from pinned committed sources, with fresh native objects and optional APK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(command, **kwargs):
    subprocess.run([str(s) for s in command], check=True, **kwargs)


def text(command):
    return subprocess.check_output([str(s) for s in command], text=True).strip()


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def tree_hashes(path):
    return {p.relative_to(path).as_posix(): sha(p) for p in sorted(path.rglob('*')) if p.is_file()}


def export_tree(cache, commit, destination, revisions, relative='.'):
    # Export the declared commit, never working files or any .cxx/build objects.
    run(['git', '-C', cache, 'cat-file', '-e', commit + '^{commit}'])
    destination.mkdir(parents=True, exist_ok=True)
    archive = subprocess.Popen(['git', '-C', str(cache), 'archive', commit], stdout=subprocess.PIPE)
    try:
        run(['tar', '-xf', '-', '-C', destination], stdin=archive.stdout)
    finally:
        archive.stdout.close()
    if archive.wait():
        raise RuntimeError('source export failed: ' + str(cache))
    revisions[relative] = commit
    entries = subprocess.check_output(['git', '-C', str(cache), 'ls-tree', '-rz', commit]).split(b'\0')
    for entry in entries:
        if not entry:
            continue
        meta, name = entry.split(b'\t', 1)
        mode, kind, revision = meta.decode().split()
        if mode == '160000':
            name = name.decode()
            subcache = cache / name
            if not (subcache / '.git').exists():
                raise ValueError('missing committed submodule cache: ' + str(subcache))
            export_tree(subcache, revision, destination / name, revisions,
                        str(Path(relative) / name))


def replace_once(path, before, after):
    value = path.read_text()
    if value.count(before) != 1:
        raise ValueError('unexpected pinned build configuration: ' + str(path))
    path.write_text(value.replace(before, after, 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-cache', type=Path, required=True,
                        help='initialized Termux:X11 git cache including pinned submodules; never modified')
    parser.add_argument('--output', type=Path, required=True, help='new, nonexistent directory')
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--ndk-version', default='28.2.13676358', choices=['28.2.13676358'])
    parser.add_argument('--abis', default='arm64-v8a', help='comma-separated; only listed ABIs are packaged')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--reuse-native-build', type=Path,
                        help='reuse this tool\'s native output only after exact source/toolchain/hash checks')
    parser.add_argument('--gradle', type=Path, help='Gradle 9.3.1 executable, required for APK')
    parser.add_argument('--allow-downloads', action='store_true', help='allow Maven access; default Gradle offline')
    args = parser.parse_args()
    abis = args.abis.split(',')
    if not 1 <= args.jobs <= 16 or len(set(abis)) != len(abis) or any(
            abi not in ('arm64-v8a', 'armeabi-v7a', 'x86', 'x86_64') for abi in abis):
        parser.error('invalid jobs or ABI list')
    if not args.native_only and (not args.gradle or not os.access(args.gradle, os.X_OK)):
        parser.error('APK build requires --gradle pointing to Gradle 9.3.1')
    cache, sdk = args.source_cache.resolve(strict=True), args.sdk.resolve(strict=True)
    ndk = sdk / 'ndk' / args.ndk_version
    if not (ndk / 'build/cmake/android.toolchain.cmake').is_file():
        parser.error('declared NDK unavailable')
    # Record the host toolchain actually used, including arm64 custom SDK tools.
    host = 'linux-arm64' if platform.machine() in ('aarch64', 'arm64') else 'linux-x86_64'
    compiler = ndk / 'toolchains/llvm/prebuilt' / host / 'bin/clang'
    if not os.access(compiler, os.X_OK):
        parser.error('native host NDK compiler missing: ' + str(compiler))
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    lock = json.loads((ROOT / 'sources.lock.json').read_text())['termux_x11']
    source = args.output / 'source'
    revisions = {}
    export_tree(cache, lock['commit'], source, revisions)
    report = dict(format=1, state='sources-exported', base_commit=lock['commit'], submodules=revisions,
                  abis=abis, native_objects='fresh', host=host, ndk=args.ndk_version,
                  compiler_version=text([compiler, '--version']), compiler_sha256=sha(compiler),
                  toolchain_sha256=sha(ndk / 'build/cmake/android.toolchain.cmake'),
                  script_sha256=sha(Path(__file__)), patches=lock['patches'], native=[])
    report_path = args.output / 'build-report.json'
    def save():
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    save()
    for item in lock['patches']:
        patch = ROOT / item['path']
        if sha(patch) != item['sha256']:
            raise ValueError('patch checksum mismatch: ' + str(patch))
        run(['patch', '--batch', '--fuzz=0', '-p1', '-i', patch], cwd=source)
    cpp = source / 'lorie/src/main/cpp'
    # Apply all declared dependency patches before CMake. Its legacy patch helper
    # otherwise hides a nonzero patch status; checking here makes failure explicit.
    for recipe in sorted((cpp / 'recipes').glob('*.cmake')):
        for module, patch_name in re.findall(
                r'target_apply_patch\([^\s]+ "\$\{CMAKE_CURRENT_SOURCE_DIR\}/([^"]+)" '
                r'"\$\{CMAKE_CURRENT_SOURCE_DIR\}/([^"]+)"\)', recipe.read_text()):
            run(['patch', '--batch', '--fuzz=0', '-p1', '-i', cpp / patch_name], cwd=cpp / module)
    report['state'] = 'patched'
    report['native_source_sha256'] = tree_hashes(cpp)
    save()
    environment = dict(os.environ)
    for key in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'CC', 'CXX', 'CFLAGS', 'CXXFLAGS', 'LDFLAGS'):
        environment.pop(key, None)
    for abi in abis:
        build = args.output / 'native' / abi
        if args.reuse_native_build:
            previous = args.reuse_native_build.resolve(strict=True)
            prior = json.loads((previous / 'build-report.json').read_text())
            old_source = previous / 'source/lorie/src/main/cpp'
            if (prior['compiler_sha256'] != report['compiler_sha256']
                    or prior['toolchain_sha256'] != report['toolchain_sha256']
                    or prior['patches'] != report['patches']
                    or tree_hashes(old_source) != report['native_source_sha256']):
                raise ValueError('native reuse rejected: source/toolchain differs')
            record = next(n for n in prior['native'] if n['abi'] == abi)
            library = previous / 'native' / abi / 'libXlorie.so'
            if sha(library) != record['sha256']:
                raise ValueError('native reuse rejected: library checksum differs')
            build.mkdir(parents=True)
            shutil.copy2(library, build / library.name)
            library = build / library.name
            report.update(native_objects='verified reuse of prior declared build', reused_native_build=str(previous))
        else:
            run(['cmake', '-S', cpp, '-B', build, '-G', 'Ninja',
                 '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
                 '-DANDROID_ABI=' + abi, '-DANDROID_PLATFORM=android-24',
                 '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON'], env=environment)
            run(['cmake', '--build', build, '--target', 'Xlorie', '--parallel', str(args.jobs)], env=environment)
            library = build / 'libXlorie.so'
        destination = source / 'lorie/src/main/jniLibs' / abi
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(library, destination / library.name)
        report['native'].append(dict(abi=abi, sha256=sha(library), size=library.stat().st_size))
        report['state'] = 'native-built'
        save()
    if args.native_only:
        print('X11_NATIVE_BUILD_OK report=' + str(report_path))
        return
    version = text([args.gradle, '--version'])
    if not re.search(r'^Gradle 9\.3\.1$', version, re.M):
        raise ValueError('expected Gradle 9.3.1')
    report['gradle_version'] = version
    # Build-only adaptations are explicit and checked against the pinned source;
    # no runtime Java/native implementation is imported from a historic build.
    replace_once(source / 'build.gradle', 'com.android.tools.build:gradle:9.3.1', 'com.android.tools.build:gradle:9.1.0')
    replace_once(source / 'lorie/build.gradle', 'externalNativeBuild.cmake.path "src/main/cpp/CMakeLists.txt"',
                 '// Native libraries were built from fresh pinned sources by build-x11.py.')
    replace_once(source / 'shell-loader/build.gradle', "apply from: 'companion-package.gradle'",
                 '// APK-only build; companion packaging is a separate deliverable.')
    version_path = source / 'lorie/version.gradle'
    value = version_path.read_text()
    end = value.index('}()') + 3
    version_path.write_text("ext.termuxX11VersionName = '1.03.01-d55f1b7-gpu-r3.5-repro'" + value[end:])
    for relative in ('lorie/build.gradle', 'lorie-app/build.gradle', 'shell-loader/build.gradle', 'shell-loader/stub/build.gradle'):
        path = source / relative
        replace_once(path, 'compileSdkVersion 34', 'compileSdk 36')
        path.write_text(path.read_text() + '\nandroid.buildToolsVersion "37.0.0"\n')
        value = re.sub(r'^(.*buildConfigField "String", "COMMIT", ).*$',
                       lambda m: m[1] + json.dumps('"' + lock['commit'] + '"'), path.read_text(), flags=re.M)
        path.write_text(value)
    properties = source / 'gradle.properties'
    properties.write_text(properties.read_text() + '\nandroid.newDsl=false\n')
    (source / 'local.properties').write_text('sdk.dir=' + str(sdk) + '\n')
    build_tools = sdk / 'build-tools/37.0.0'
    report['android_tools_sha256'] = {name: sha(build_tools / name) for name in ('aapt2', 'aidl', 'zipalign')}
    report['state'] = 'packaging'
    save()
    # Inspect resolved graphs, not resolvedConfiguration.resolvedArtifacts:
    # requesting the latter can trigger a new, ambiguous Android variant resolve.
    init = args.output / 'dependency-provenance.gradle'
    init.write_text('''
import groovy.json.JsonOutput
import java.security.MessageDigest
gradle.buildFinished { result ->
    if (result.failure != null) return
    def rows = [], modules = [] as Set
    gradle.rootProject.allprojects.each { project ->
        [project.configurations, project.buildscript.configurations].each { configurations ->
            configurations.findAll { it.state.toString() == 'RESOLVED' }.each { configuration ->
                configuration.incoming.resolutionResult.allComponents.each { component ->
                    def id = component.id
                    if (id instanceof org.gradle.api.artifacts.component.ModuleComponentIdentifier) {
                        modules << [group: id.group, module: id.module, version: id.version]
                    }
                }
            }
        }
    }
    modules.each { module ->
        def folder = new File(gradle.gradleUserHomeDir,
            'caches/modules-2/files-2.1/' + module.group + '/' + module.module + '/' + module.version)
        if (folder.exists()) folder.eachFileRecurse { artifact ->
            if (artifact.isFile()) {
                def digest = MessageDigest.getInstance('SHA-256')
                artifact.withInputStream { stream ->
                    byte[] buffer = new byte[65536]; int count
                    while ((count = stream.read(buffer)) > 0) digest.update(buffer, 0, count)
                }
                rows << [coordinate: module.group + ':' + module.module + ':' + module.version,
                         file: artifact.name, sha256: digest.digest().encodeHex().toString()]
            }
        }
    }
    new File(System.getenv('PAD_GPU_DEPENDENCY_MANIFEST')).text =
        JsonOutput.prettyPrint(JsonOutput.toJson([scope: 'cached artifacts for resolved external modules; may include unused classifiers',
            artifacts: rows.unique().sort { a, b ->
            (a.coordinate + a.file) <=> (b.coordinate + b.file)
        }])) + '\\n'
}
''')
    environment['PAD_GPU_DEPENDENCY_MANIFEST'] = str(args.output / 'dependency-artifacts.json')
    command = [args.gradle, '--no-daemon', '--max-workers=' + str(args.jobs),
               '--init-script', init, '-Pandroid.aapt2FromMavenOverride=' + str(build_tools / 'aapt2'),
               ':lorie-app:assembleStandaloneDebug']
    if not args.allow_downloads:
        command.insert(1, '--offline')
    run(command, cwd=source, env=environment)
    apk = source / 'lorie-app/build/outputs/apk/standalone/debug/termux-x11-universal-debug.apk'
    run([build_tools / 'zipalign', '-c', '-P', '16', '4', apk])
    run([build_tools / 'apksigner', 'verify', '--verbose', '--print-certs', apk])
    shutil.copy2(apk, args.output / 'candidate.apk')
    report.update(state='apk-built-not-installed', apk_sha256=sha(apk),
                  dependency_manifest_sha256=sha(args.output / 'dependency-artifacts.json'),
                  reproducibility='fresh source and objects; byte identity not asserted')
    save()
    print('X11_APK_BUILD_OK report=' + str(report_path))


if __name__ == '__main__':
    main()
