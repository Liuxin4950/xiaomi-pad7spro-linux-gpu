#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Install current-release PATH entry points, with exact backups and no ELF edits."""
import argparse,hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('migration',Path(__file__).with_name('activate-desktop.py'));migration=module_from_spec(spec);spec.loader.exec_module(migration)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');p.add_argument('--backup',type=Path,required=True);a=p.parse_args()
 prefix=Path('/usr/local/bin/gpu-run').resolve().parents[1]
 if prefix.parent!=Path('/opt'):raise RuntimeError('unexpected active prefix')
 aliases={'chromium':'chromium','chatgpt':'chatgpt','ChatGPT':'chatgpt','trae':'trae','trae-cn':'trae','cc-switch':'cc-switch'}
 plan={'prefix':str(prefix),'aliases':{},'files':{}}
 for alias,mode in aliases.items():
  target=prefix/'bin'/('gpu-entry-'+mode);data=f'#!/bin/sh\n# pad-gpu entry: {mode}\nexec /usr/local/bin/gpu-run {mode} "$@"\n'
  plan['files'][str(target)]=data
  link=Path('/usr/local/bin')/alias
  plan['aliases'][str(link)]={'before_symlink':str(link.readlink()) if link.is_symlink() else None,'before_file':link.exists() and not link.is_symlink(),'after':str(target)}
 codex=Path('/usr/lib/chatgpt/codex-launcher');old=codex.read_text()
 if 'ChatGPT' not in old and '# pad-gpu entry: chatgpt' not in old:raise RuntimeError('unknown ChatGPT launcher; preserve custom behavior')
 plan['files'][str(codex)]='#!/bin/sh\n# pad-gpu entry: chatgpt\nexec /usr/local/bin/gpu-run chatgpt "$@"\n'
 if a.apply:
  a.backup.mkdir(parents=True,exist_ok=False);a.backup.chmod(0o700)
  for name,data in plan['files'].items():
   path=Path(name)
   if path.exists():
    saved=a.backup/path.relative_to('/');saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(path.read_bytes());saved.chmod(0o600)
    migration.atomic_write(path,data.encode())
   else:path.write_text(data);path.chmod(0o755)
  for name,entry in plan['aliases'].items():
   link=Path(name)
   if entry['before_file']:
    saved=a.backup/link.relative_to('/');saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(link.read_bytes());saved.chmod(0o600)
   temp=link.with_name('.'+link.name+'.padgpu.'+str(os.getpid()))
   temp.symlink_to(entry['after']);os.replace(temp,link)
  (a.backup/'restore-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 print(json.dumps({'applied':a.apply,**plan},indent=2))
if __name__=='__main__':main()
