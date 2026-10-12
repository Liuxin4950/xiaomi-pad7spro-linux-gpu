#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One explicitly authorized graceful ChatGPT restart; never force-kill.

The agent may lose its UI connection during restart. Run detached after saving
its report. Configuration and application data are retained without editing.
"""
import argparse,json,os,signal,subprocess,time
from pathlib import Path

def identity(pid):
 try:
  stat=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
  return int(stat[19])
 except (OSError,ValueError,IndexError):return None

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pid',type=int,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--apply',action='store_true');p.add_argument('--delay',type=int,default=15);a=p.parse_args()
 if not 0<=a.delay<=60:p.error('delay must be 0..60 seconds')
 cmd=Path(f'/proc/{a.pid}/cmdline').read_bytes().split(b'\0');exe=Path(f'/proc/{a.pid}/exe').resolve()
 if str(exe)!='/usr/lib/chatgpt/ChatGPT' or any(x.startswith(b'--type=') for x in cmd):raise RuntimeError('expected ChatGPT main process')
 old_start=identity(a.pid)
 gui_keys={'DBUS_SESSION_BUS_ADDRESS','DISPLAY','XDG_RUNTIME_DIR','PULSE_SERVER','LANG','LC_ALL','LC_CTYPE','GTK_IM_MODULE','QT_IM_MODULE','XMODIFIERS','XAUTHORITY','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CURRENT_DESKTOP','XDG_SESSION_TYPE','PATH','HOME','TMPDIR','USER','LOGNAME','SHELL'}
 environment={k:v for k,v in os.environ.items() if k in gui_keys}
 # Electron can clear procfs' original environ. Recover the desktop session
 # rather than starting a new bus or changing the profile/keyring context.
 for item in Path('/proc').iterdir():
  if not item.name.isdigit():continue
  try:
   if (item/'comm').read_text().strip() not in ('xfce4-session','xfce4-panel'):continue
   for field in (item/'environ').read_bytes().split(b'\0'):
    if b'=' in field:
     key,value=field.split(b'=',1)
     if key.decode() in gui_keys:environment.setdefault(key.decode(),value.decode(errors='surrogateescape'))
  except OSError:pass
 for field in Path(f'/proc/{a.pid}/environ').read_bytes().split(b'\0'):
  if b'=' in field:
   key,value=field.split(b'=',1)
   if key.decode() in gui_keys:environment[key.decode()]=value.decode(errors='surrogateescape')
 environment.update(HOME='/root',TMPDIR='/tmp')
 environment.pop('PAD_GPU_PREFIX',None)
 environment.update(DISPLAY=':1',XDG_RUNTIME_DIR='/run/user/0')
 if not a.apply:print('Prepared graceful restart; no process changed.');return
 a.output.mkdir(parents=True,exist_ok=False);a.output.chmod(0o700)
 report=dict(old_pid=a.pid,old_start_ticks=old_start,default_runner=str(Path('/usr/local/bin/gpu-run').resolve()),state='prepared')
 def save(): (a.output/'restart-result.json').write_text(json.dumps(report,indent=2)+'\n')
 save();time.sleep(a.delay)
 if identity(a.pid)!=old_start:report.update(state='aborted_identity_changed');save();return
 os.kill(a.pid,signal.SIGTERM)
 deadline=time.monotonic()+12
 while identity(a.pid)==old_start and time.monotonic()<deadline:time.sleep(.2)
 if identity(a.pid)==old_start:report.update(state='aborted_app_did_not_exit_gracefully');save();return
 with (a.output/'chatgpt.log').open('w') as log:
  app=subprocess.Popen(['/usr/local/bin/gpu-run','chatgpt'],env=environment,stdout=log,stderr=log,start_new_session=True)
 report.update(new_pid=app.pid,state='launched');save()
 deadline=time.monotonic()+40
 while app.poll() is None and time.monotonic()<deadline:
  for item in Path('/proc').iterdir():
   if not item.name.isdigit():continue
   try:
    data=(item/'cmdline').read_bytes()
    fields=(item/'stat').read_text().rsplit(')',1)[1].split()
    if '--type=gpu-process'.encode() not in data or int(fields[1])!=app.pid:continue
    maps=(item/'maps').read_text()
    if '/vendor/lib64/hw/vulkan.mali.so' in maps and '/opt/pad7spro-gpu-observe-20261012/' in maps:
     report.update(state='mali_bridge_loaded',gpu_pid=int(item.name),gpu_start_ticks=identity(int(item.name)))
     (a.output/'gpu.maps').write_text(maps);save();return
   except (OSError,ValueError,IndexError):pass
  time.sleep(.25)
 report.update(state='hardware_not_verified',app_exit=app.poll());save()
if __name__=='__main__':main()
