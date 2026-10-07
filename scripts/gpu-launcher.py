#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Desktop command picker for gpu-run. Programs run as argv, never through a shell."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


LINUX_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'


def installation_prefix():
    script = Path(__file__).resolve()
    inferred = script.parent.parent if script.parent.name == 'bin' else Path('/opt/pad7spro-gpu')
    selected = os.environ.get('PAD_GPU_PREFIX') or str(inferred)
    if not re.fullmatch(r'/opt/[A-Za-z0-9_.-]+', selected) or selected in ('/opt/.', '/opt/..'):
        raise ValueError('GPU 前缀必须是 /opt 下的专用单级目录。')
    prefix = Path(selected).resolve()
    if not re.fullmatch(r'/opt/[A-Za-z0-9_.-]+', str(prefix)):
        raise ValueError('GPU 前缀解析后超出专用 /opt 目录。')
    return prefix


def zenity_path():
    return shutil.which('zenity', path=LINUX_PATH)


def request_command(software):
    zenity = zenity_path()
    if not zenity:
        raise OSError('未安装 zenity；请安装后使用桌面入口，或传入 --command。')
    mode = 'CPU 软件渲染' if software else 'GPU 硬件渲染'
    result = subprocess.run(
        [zenity, '--entry', '--title=启动 Linux 图形应用', '--width=560',
         '--text=输入程序及参数，例如 chromium 或 glxgears。\n当前模式：' + mode,
         '--entry-text=chromium'], text=True, capture_output=True, check=False)
    if result.returncode == 1:
        return None
    if result.returncode:
        raise OSError('无法打开程序选择对话框：' + result.stderr.strip())
    return result.stdout.rstrip('\n')


def report_error(message, interactive):
    print('[pad-gpu] ' + message, file=sys.stderr)
    zenity = zenity_path() if interactive else None
    if zenity:
        try:
            subprocess.run([zenity, '--error', '--title=GPU 应用启动失败', '--width=560',
                            '--text=' + message], check=False)
        except OSError:
            pass  # The same error has already been reported on stderr.


def private_log():
    state = os.environ.get('XDG_STATE_HOME')
    if state and not Path(state).is_absolute():
        raise ValueError('XDG_STATE_HOME 必须是绝对路径。')
    directory = (Path(state) if state else Path.home() / '.local/state') / 'pad-gpu/launches'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink():
        raise ValueError('日志目录不能是符号链接。')
    directory.chmod(0o700)
    descriptor, filename = tempfile.mkstemp(
        prefix=datetime.now().strftime('launch-%Y%m%d-%H%M%S-'), suffix='.log', dir=directory)
    return os.fdopen(descriptor, 'w', encoding='utf-8'), Path(filename)


def launch(command, software, interactive):
    arguments = shlex.split(command)
    if not arguments:
        raise ValueError('请输入程序名称或完整路径。')
    prefix = installation_prefix()
    runner = prefix / 'bin/gpu-run'
    if not runner.is_file() or not os.access(runner, os.X_OK):
        raise OSError('缺少可执行的 GPU 入口：' + str(runner))
    argv = [str(runner)] + (['--software'] if software else []) + ['auto', *arguments]
    environment = dict(os.environ, PAD_GPU_PREFIX=str(prefix), PATH=LINUX_PATH)
    with_log, filename = private_log()
    with with_log as output:
        output.write('mode=' + ('software' if software else 'hardware') + '\n')
        output.write('prefix=' + str(prefix) + '\ncommand=' + shlex.join(arguments) + '\n')
        output.flush()
        print('[pad-gpu] log=' + str(filename), file=sys.stderr)
        try:
            process = subprocess.Popen(argv, env=environment, stdout=output,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            status = process.wait()
        except OSError as error:
            output.write('launch failed: ' + str(error) + '\n')
            raise OSError(str(error) + '\n日志：' + str(filename)) from error
        output.write('\nexit_status=' + str(status) + '\n')
    if status:
        report_error('程序退出，状态码 ' + str(status) + '。\n日志：' + str(filename), interactive)
    return status if status >= 0 else 128 - status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--command', help='程序及参数；省略时显示输入对话框')
    parser.add_argument('--software', action='store_true', help='显式使用 CPU 软件渲染')
    args = parser.parse_args(argv)
    interactive = args.command is None
    try:
        command = request_command(args.software) if interactive else args.command
        if command is None:
            return 0
        return launch(command, args.software, interactive)
    except ValueError as error:
        report_error(str(error), interactive)
        return 64
    except OSError as error:
        report_error(str(error), interactive)
        return 78


if __name__ == '__main__':
    sys.exit(main())
