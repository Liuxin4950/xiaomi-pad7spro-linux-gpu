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
 summary['valid']=rc==0 and summary['screen_awake'] and freeze=='0' and abs(summary['clock_offset_change_ns'])<1000000 and (not moving or len(ts)>30)
 (case/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True);return summary

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=8);p.add_argument('--width',type=int,default=1280);p.add_argument('--height',type=int,default=800);p.add_argument('--variants',default='r2,r3,fixed');p.add_argument('--scenes',default='moving,static');a=p.parse_args()
 if not 2<=a.seconds<=60 or not 64<=a.width<=10000 or not 32<=a.height<=10000:p.error('invalid dimensions/duration')
 a.output.mkdir(exist_ok=False,parents=True);base=Path(__file__).resolve().parents[1];client=base/'build/root-cause-20261012/probe-motion-vulkan';x11=base/'build/root-cause-20261012/probe-x11-motion'
 prefixes={'r2':'/opt/pad7spro-gpu-dev-20261007-r2','r3':'/opt/pad7spro-gpu-dev-20261012-r3','fixed':'/opt/pad7spro-gpu-observe-20261012','fixed-uncapped':'/opt/pad7spro-gpu-observe-20261012'};all=[]
 for variant in a.variants.split(','):
  for scene in a.scenes.split(','):
   if scene not in ('static','moving'):p.error('invalid scene')
   env=dict(os.environ,DISPLAY=':1',XDG_RUNTIME_DIR='/run/user/0',PAD_GPU_MAX_FPS='0' if variant=='fixed-uncapped' else '60')
   cmd=[str(x11)] if variant=='x11' else [prefixes[variant]+'/bin/gpu-run','vulkan',str(client),'--bgra','--motion','--cycles','1']
   cmd+=['--width',str(a.width),'--height',str(a.height),'--fullscreen','--rate','60','--frames',str(a.seconds*60 if scene=='moving' else 1)]
   if scene=='static':cmd+=['--idle-ms',str(a.seconds*1000)]
   all.append(run_case(variant+'-'+scene,cmd,a.output,env,a.seconds))
   (a.output/'summary.json').write_text(json.dumps(all,indent=2))
if __name__=='__main__':main()
