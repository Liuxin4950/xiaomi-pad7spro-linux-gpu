#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded real display checks. SF presents and client submissions stay separate."""
import argparse,csv,json,os,subprocess,time,threading
from pathlib import Path

def android(*args):
 return subprocess.check_output(['/usr/sbin/chroot','/proc/1/root','/system/bin/'+args[0],*args[1:]],text=True,timeout=5)
def clocks():
 return dict(monotonic_ns=time.monotonic_ns(),boottime_ns=time.clock_gettime_ns(7),realtime_ns=time.time_ns())
def proc_cpu(pid):
 try:
  f=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split();return (int(f[19]),int(f[11])+int(f[12]))
 except (OSError,ValueError,IndexError):return None
def percent(v):
 v=sorted(v);return {f'p{q}':v[int((len(v)-1)*q/100)] for q in (50,95,99)} if v else {}
def run_case(label,cmd,out,env,seconds):
 case=out/label;case.mkdir();before=clocks()
 conditions_before=device_conditions()
 pids=[];server=None
 for item in Path('/proc').iterdir():
  if not item.name.isdigit():continue
  try:
   executable=(item/'cmdline').read_bytes().split(b'\0')[0].split(b' ')[0].split(b'/')[-1]
   if executable in (b'termux-x11',b'com.termux.x11',b'com.miui.daemon'):
    pids.append(int(item.name))
    if executable==b'termux-x11':server=int(item.name)
  except OSError:pass
 if server is None:raise RuntimeError('live X11 server missing')
 groups=Path(f'/proc/{server}/cgroup').read_text().splitlines()
 unified=next((g.split(':',2)[2] for g in groups if g.startswith('0::')),None)
 freeze_path=Path('/proc/1/root/sys/fs/cgroup'+unified+'/cgroup.freeze') if unified else None
 cpu_before={p:proc_cpu(p) for p in pids}
 sf=[];stop=threading.Event();visibility=[]
 def collect():
  while not stop.is_set():
   anchor=clocks()
   try:
    layers=android('dumpsys','SurfaceFlinger','--list').splitlines()
    raw=next(s for s in layers if 'SurfaceView[com.termux.x11/' in s and '(BLAST)' in s)
    layer=raw.split(' parentId=')[0].removeprefix('RequestedLayerState{')
    data=android('dumpsys','SurfaceFlinger','--latency',layer)
    sf.append(dict(**anchor,layer=layer,raw=data))
   except Exception as e:sf.append(dict(**anchor,error=str(e)))
   stop.wait(.4)
 worker=threading.Thread(target=collect);worker.start();
 cmd=cmd+['--timings',str((case/'client.csv').resolve())]
 with (case/'client.log').open('w') as log:
  p=subprocess.Popen(cmd,env=env,stdout=log,stderr=log)
  try:
   time.sleep(.5)
   maps=Path(f'/proc/{p.pid}/maps').read_text();(case/'client.maps').write_text(maps)
   last_cpu=proc_cpu(p.pid)
   idle_start=None; idle_end=None
   deadline=time.monotonic()+seconds+20
   while p.poll() is None:
    current=proc_cpu(p.pid)
    if current: last_cpu=current
    if time.monotonic_ns()-before['monotonic_ns']>1500000000 and current:
     if idle_start is None:idle_start=(time.monotonic_ns(),current)
     idle_end=(time.monotonic_ns(),current)
    if time.monotonic()>deadline:raise TimeoutError('client timeout')
    time.sleep(.025)
   rc=p.returncode
  finally:
   if p.poll() is None:
    p.terminate()
    try:p.wait(timeout=3)
    except subprocess.TimeoutExpired:p.kill();p.wait()
   stop.set();worker.join(timeout=7)
 after=clocks();
 conditions_after=device_conditions();
 (case/'sf.json').write_text(json.dumps(sf))
 power=android('dumpsys','power');freeze=freeze_path.read_text().strip() if freeze_path and freeze_path.exists() else 'unknown'
 cpu={}
 for pid,previous in cpu_before.items():
  current=proc_cpu(pid)
  cpu[str(pid)]=(current[1]-previous[1])/os.sysconf('SC_CLK_TCK') if current and previous and current[0]==previous[0] else None
 rows=list(csv.DictReader((case/'client.csv').open()));timestamps={}
 for sample in sf:
  for row in sample.get('raw','').splitlines()[1:]:
   fields=row.split()
   if len(fields)!=3:continue
   vals=list(map(int,fields));actual=vals[1]
   if before['monotonic_ns']<=actual<=after['monotonic_ns'] and actual!=9223372036854775807:timestamps[actual]=vals
 ts=sorted(timestamps);intervals=[(b-a)/1e6 for a,b in zip(ts,ts[1:])]
 moving='moving' in label
 summary=dict(label=label,rc=rc,start=before,end=after,screen_awake='mWakefulness=Awake' in power,freezer=freeze,
  client_frames=len(rows),client_cpu_s=last_cpu[1]/os.sysconf('SC_CLK_TCK') if last_cpu else None,
  client_cpu_method='last live proc stat; final exit ticks may be missed',
  steady_cpu_ms_per_s=(idle_end[1][1]-idle_start[1][1])*1000/os.sysconf('SC_CLK_TCK')/((idle_end[0]-idle_start[0])/1e9) if idle_start and idle_end and idle_end[0]>idle_start[0] else None,
  tracked_cpu_s=cpu,mali_mapped='/vendor/lib64/hw/vulkan.mali.so' in maps,
  actual_sf_presents=len(ts),actual_sf_interval_ms=percent(intervals),actual_sf_max_ms=max(intervals) if intervals else None,
  actual_sf_hz=(len(ts)-1)*1e9/(ts[-1]-ts[0]) if len(ts)>1 else None,
  acquire_us=percent([float(r['acquire_us']) for r in rows]),host_frame_us=percent([float(r['host_frame_us']) for r in rows]),
  clock_offset_change_ns=(after['boottime_ns']-after['monotonic_ns'])-(before['boottime_ns']-before['monotonic_ns']))
 summary['conditions_before']=conditions_before
 summary['conditions_after']=conditions_after
 summary['conditions_unchanged']='error' not in conditions_before and 'error' not in conditions_after and all(conditions_before.get(k) is not None for k in ('brightness_setting','active_mode','active_render_rate')) and all(conditions_before.get(k)==conditions_after.get(k) for k in ('brightness_setting','active_mode','active_render_rate'))
 summary['valid']=summary['conditions_unchanged'] and rc==0 and summary['screen_awake'] and freeze=='0' and abs(summary['clock_offset_change_ns'])<1000000 and (not moving or len(ts)>30)
 (case/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True);return summary

def device_conditions():
 import re
 try:
  display=android('dumpsys','display')
  def match(pattern):
   m=re.search(pattern,display);return m[1] if m else None
  battery=Path('/sys/class/power_supply/battery')
  return dict(brightness_setting=android('settings','get','system','screen_brightness').strip(),
   active_mode=match(r'mActiveModeId=(\d+)'),active_render_rate=match(r'mActiveRenderFrameRate=([\d.]+)'),
   brightness_actual=match(r'mCachedBrightnessInfo.brightness=([\d.]+)'),
   battery_status=(battery/'status').read_text().strip(),
   battery_temp_raw=(battery/'temp').read_text().strip())
 except Exception as error:return dict(error=str(error))

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--output',type=Path,required=True)
 p.add_argument('--seconds',type=int,default=8)
 p.add_argument('--width',type=int,default=3200)
 p.add_argument('--height',type=int,default=2054)
 p.add_argument('--runs',type=int,default=3)
 p.add_argument('--baseline',type=Path,default=Path('/opt/pad7spro-gpu-observe-20261012'))
 p.add_argument('--candidate',type=Path,default=Path('/opt/pad7spro-gpu-r3.4.2-display'))
 p.add_argument('--scenes',default='moving,static')
 p.add_argument('--trace',action='store_true')
 p.add_argument('--rate',type=int,default=0,help='0 lets Acquire/Present drive producer; optional independent workload clock')
 a=p.parse_args()
 if not 2<=a.seconds<=60 or not 64<=a.width<=10000 or not 32<=a.height<=10000 or not 1<=a.runs<=10 or not 0<=a.rate<=240:
  p.error('invalid dimensions/duration/runs/rate')
 for scene in a.scenes.split(','):
  if scene not in ('static','moving'):p.error('invalid scene')
 a.output.mkdir(exist_ok=False,parents=True)
 client=a.candidate/'bin/probe-present'
 if not client.is_file():p.error('build and install candidate first')
 variants=[('r33',a.baseline,'auto'),('candidate-timer',a.candidate,'timer'),('candidate-display',a.candidate,'auto')]
 all=[]
 for iteration in range(a.runs):
  for variant,prefix,policy in (variants if iteration%2==0 else variants[::-1]):
   for scene in a.scenes.split(','):
    label=f'{iteration}-{variant}-{scene}'
    env=dict(os.environ,DISPLAY=os.environ.get('DISPLAY',':1'),XDG_RUNTIME_DIR='/run/user/0',
     PAD_GPU_MAX_FPS='60',PAD_GPU_PRESENT_CLOCK=policy,PAD_GPU_WSI_TRACE='1' if a.trace else '0')
    # Every variant uses the identical client executable. Only library prefix/policy vary.
    cmd=[str(prefix/'bin/gpu-run'),'vulkan',str(client),'--bgra','--motion','--cycles','1',
     '--width',str(a.width),'--height',str(a.height),'--fullscreen','--delay-ms','0',
     '--rate',str(a.rate),'--frames',str(a.seconds*60 if scene=='moving' else 1)]
    if scene=='static':cmd+=['--idle-ms',str(a.seconds*1000)]
    if a.trace:
     timeline=(a.output/(label+'-timeline')).resolve();timeline.mkdir()
     env['PAD_GPU_WSI_TIMELINE_DIR']=str(timeline)
    result=run_case(label,cmd,a.output,env,a.seconds)
    result.update(prefix=str(prefix),clock_policy=policy,run=iteration,producer_rate=a.rate,
     sf_measurement='distinct Surface presents; content uniqueness and input causality require frame IDs',
     trace_enabled=a.trace)
    # auto is a negotiation request, never proof that display pacing was selected.
    if a.trace:
     events=[]
     for path in timeline.glob('*.csv'):events+=list(csv.DictReader(path.open()))
     clocks_selected=[int(e['value']) for e in events if e['stage']=='display_clock_fps']
     result['negotiated_clock_fps']=clocks_selected
     if variant=='candidate-display' and not any(clocks_selected):result['display_clock_validation_pending']=True
    all.append(result)
    (a.output/label/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    (a.output/'summary.json').write_text(json.dumps(all,indent=2)+'\n')
if __name__=='__main__':main()
