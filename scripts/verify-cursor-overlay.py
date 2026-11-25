#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
from pathlib import Path
import importlib.util,subprocess,time,threading,json,os,datetime
from PIL import Image, ImageChops
import argparse
parser=argparse.ArgumentParser(description='Bounded, visible cursor-only live probe. Restores display and pointer.')
parser.add_argument('--probe',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True,help='NEW private output directory')
args=parser.parse_args()
if not args.probe.is_file() or not os.access(args.probe, os.X_OK):
 parser.error('--probe must be an executable file')
root=Path(__file__).resolve().parents[1];out=args.output.resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)

spec=importlib.util.spec_from_file_location('stall',root/'scripts/capture-x11-stall.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
pid=m.find_server();fd,base,shared,generation=m.identify(pid)
stop=threading.Event();phase='initial';rows=[];sampling_errors=[]
def collect():
 try:
  while not stop.is_set():
   row=m.sample(fd,base,shared);row.update(cursor_x=int.from_bytes(os.pread(fd,4,shared+0x584),'little',signed=True),cursor_y=int.from_bytes(os.pread(fd,4,shared+0x588),'little',signed=True),cursor_updated=os.pread(fd,1,shared+0x10059c)[0],cursor_moved=os.pread(fd,1,shared+0x10059d)[0]);row['phase']=phase;rows.append(row);stop.wait(.02)
 except (OSError,ValueError) as error:
  sampling_errors.append(str(error));stop.set()
thread=threading.Thread(target=collect);thread.start();results=[];switches=[]
log=(out/'launch.log').open('w');proc=subprocess.Popen(['/usr/local/bin/gpu-run','gl',str(args.probe.resolve())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1)
watchdog=threading.Timer(50,proc.kill);watchdog.start()
def command(text):
 proc.stdin.write(text+'\n');proc.stdin.flush();response=[]
 while True:
  line=proc.stdout.readline().strip()
  if not line:raise RuntimeError('probe exited: '+str(proc.poll()))
  response.append(line)
  if line=='done':return response

def screenshot(name):
 p=out/(name+'.png')
 with p.open('wb') as f:subprocess.run(['/opt/android-sdk/platform-tools/adb','exec-out','screencap','-p'],stdout=f,check=True,timeout=5)
 im=Image.open(p).convert('RGB');r,g,b=im.split();found={}
 for color in ['red','blue']:
  if color=='red':channels=[r.point(lambda v:255 if v>200 else 0),g.point(lambda v:255 if v<100 else 0),b.point(lambda v:255 if v<100 else 0)]
  else:channels=[r.point(lambda v:255 if v<100 else 0),g.point(lambda v:255 if v<120 else 0),b.point(lambda v:255 if v>180 else 0)]
  mask=ImageChops.multiply(ImageChops.multiply(channels[0],channels[1]),channels[2]);mask.paste(0,(0,0,im.width,90))
  found[color]=dict(count=mask.histogram()[255],bbox=list(mask.getbbox()) if mask.getbbox() else None)

 return found
try:
 ready=proc.stdout.readline().strip();assert ready.startswith('ready '),ready
 phase='settle';command('red 200 300');time.sleep(.5)
 phase='idle';start=m.sample(fd,base,shared);time.sleep(1);end=m.sample(fd,base,shared);results.append(dict(phase=phase,frames=end['rendered_frames']-start['rendered_frames']))
 phase='red-left';start=m.sample(fd,base,shared);reply=command('red 200 300');time.sleep(.2);pixels=screenshot(phase);end=m.sample(fd,base,shared);results.append(dict(phase=phase,frames=end['rendered_frames']-start['rendered_frames'],pixels=pixels,replies=reply))
 phase='motion';start=m.sample(fd,base,shared);reply=command('motion');end=m.sample(fd,base,shared);results.append(dict(phase=phase,frames=end['rendered_frames']-start['rendered_frames'],elapsed_s=(end['monotonic_ns']-start['monotonic_ns'])/1e9,replies=reply))
 for phase,text in [('red-right','red 1300 700'),('hidden','hide'),('blue-wide','blue 800 500')]:
  start=m.sample(fd,base,shared);reply=command(text);time.sleep(.2);pixels=screenshot(phase);end=m.sample(fd,base,shared);results.append(dict(phase=phase,frames=end['rendered_frames']-start['rendered_frames'],pixels=pixels,replies=reply))
 phase='surface-recovery';start=m.sample(fd,base,shared)
 for activity in ['com.termux/.app.TermuxActivity','com.termux.x11/com.termux.x11.MainActivity']:
  switched=subprocess.run(['/opt/android-sdk/platform-tools/adb','shell','am','start','-W','--user','0','-n',activity],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True,timeout=5,text=True)
  time.sleep(.5)
  windows=subprocess.check_output(['/opt/android-sdk/platform-tools/adb','shell','dumpsys','window','displays'],text=True,timeout=5)
  focus=[line.strip() for line in windows.splitlines() if 'mCurrentFocus=' in line]
  switches.append(dict(request=activity,output=switched.stdout,focus=focus))
  assert focus and activity.split('/')[0]+'/' in focus[0],switches[-1]
 reply=command('blue 800 500');time.sleep(.3);pixels=screenshot(phase);end=m.sample(fd,base,shared)
 results.append(dict(phase=phase,frames=end['rendered_frames']-start['rendered_frames'],pixels=pixels,replies=reply))
 table={r['phase']:r for r in results}
 offset=table['red-left']['pixels']['red']['bbox']
 assert offset and table['red-left']['pixels']['red']['count']==576
 ox=offset[0]-(200-5);oy=offset[1]-(300-7)
 for stage,color,position,size in [('red-left','red',(200,300),(24,24)),('red-right','red',(1300,700),(24,24)),('blue-wide','blue',(800,500),(48,16)),('surface-recovery','blue',(800,500),(48,16))]:
  match=table[stage]['pixels'][color];x,y=position;w,h=size
  assert match['count']==w*h and match['bbox']==[x-5+ox,y-7+oy,x-5+ox+w,y-7+oy+h],(stage,match)
  other='blue' if color=='red' else 'red';assert table[stage]['pixels'][other]['count']==0
 assert all(table['hidden']['pixels'][color]['count']==0 for color in ['red','blue'])
 assert all(table[stage]['frames']==0 for stage in ['idle','red-left','motion','red-right','hidden','blue-wide'])
 assert m.starttime(pid)==generation

finally:
 try:
  subprocess.run(['/opt/android-sdk/platform-tools/adb','shell','am','start','--user','0','-n','com.termux.x11/com.termux.x11.MainActivity'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
 except (OSError,subprocess.TimeoutExpired):pass
 try:proc.stdin.write('exit\n');proc.stdin.flush()
 except (BrokenPipeError,OSError):pass
 try:code=proc.wait(timeout=5)
 except subprocess.TimeoutExpired:proc.terminate();code=proc.wait(timeout=5)
 watchdog.cancel();stop.set();thread.join();os.close(fd);log.close()
 (out/'samples.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
 (out/'result.json').write_text(json.dumps(dict(server_pid=pid,server_starttime=generation,probe_exit=code,stages=results,activity_switches=switches,sampling_errors=sampling_errors,caveat='Internal renderer frames, not physical FPS or power. Cursor screenshot coordinates are physical pixels.'),indent=2)+'\n')
print(out);print(json.dumps(results,indent=2));print('probe_exit',code)
