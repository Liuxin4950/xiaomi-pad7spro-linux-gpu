#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify and atomically select a dedicated release, with exact entry backups."""
import argparse,hashlib,json,os,subprocess,tempfile
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('prefix',type=Path);p.add_argument('--apply',action='store_true');p.add_argument('--backup',type=Path,required=True);a=p.parse_args()
 prefix=a.prefix.resolve()
 if prefix.parent!=Path('/opt'):p.error('dedicated prefix directly below /opt required')
 m=json.loads((prefix/'install-manifest.json').read_text())
 if m['prefix']!=str(prefix):raise RuntimeError('manifest prefix mismatch')
 for name,digest in m['files'].items():
  f=prefix/name
  if not f.resolve().is_relative_to(prefix) or hashlib.sha256(f.read_bytes()).hexdigest()!=digest:raise RuntimeError('manifest mismatch: '+name)
 for name,target in m['symlinks'].items():
  f=prefix/name
  if not f.is_symlink() or str(f.readlink())!=target or not f.resolve().is_relative_to(prefix):raise RuntimeError('symlink mismatch: '+name)
 root=Path(__file__).resolve().parents[1];desktop=root/'scripts/activate-desktop.py'
 plan=json.loads(subprocess.check_output(['python3',str(desktop)],text=True))
 links={}
 for name in ('gpu-run','gpu-launcher'):
  link=Path('/usr/local/bin')/name
  if not link.is_symlink():raise RuntimeError('expected existing symlink: '+str(link))
  target=prefix/'bin'/name
  if not target.is_file() or not os.access(target,os.X_OK):raise RuntimeError('missing executable')
  links[str(link)]=dict(before=str(link.readlink()),after=str(target))
 report=dict(applied=a.apply,links=links,desktop=plan)
 if a.apply:
  a.backup.mkdir(parents=True,exist_ok=False);a.backup.chmod(0o700)
  for item in plan['entries']:
   path=Path(item['path']);saved=a.backup/path.relative_to('/');saved.parent.mkdir(parents=True,exist_ok=True)
   saved.write_bytes(path.read_bytes());saved.chmod(0o600)
  (a.backup/'restore-plan.json').write_text(json.dumps(report,indent=2)+'\n')
  for name,item in links.items():
   link=Path(name);temporary=link.with_name('.'+link.name+'.r3.1.'+str(os.getpid()))
   try:temporary.symlink_to(item['after']);os.replace(temporary,link)
   finally:
    if temporary.is_symlink():temporary.unlink()
  subprocess.run(['python3',str(desktop),'--apply'],check=True)
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
