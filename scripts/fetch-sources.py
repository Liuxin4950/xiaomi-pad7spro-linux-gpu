#!/usr/bin/env python3
"""Fetch fixed revisions and verified artifacts. No account credentials needed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def git(directory, *arguments):
    return subprocess.check_output(["git", "-C", str(directory), *arguments], stderr=subprocess.STDOUT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "build" / "sources")
    args = parser.parse_args()
    destination = args.directory.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
    for item in lock["git_sources"]:
        checkout = destination / item["name"]
        created = not checkout.exists()
        if created:
            subprocess.run(["git", "clone", "--no-checkout", item["url"], str(checkout)], check=True)
        git(checkout, "config", "core.autocrlf", "false")
        try:
            git(checkout, "cat-file", "-e", item["commit"] + "^{commit}")
        except subprocess.CalledProcessError:
            git(checkout, "fetch", "origin", item["commit"])
        if not created and git(checkout, "status", "--porcelain").strip():
            raise RuntimeError("Source cache has local changes; use another --directory: " + str(checkout))
        git(checkout, "checkout", "--detach", item["commit"])
        # Validate dependent patches in order without changing the source cache.
        with tempfile.TemporaryDirectory(prefix="gpu-patch-check-") as temporary:
            environment = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))
            def index_git(*arguments):
                subprocess.run(["git", "-C", str(checkout), *arguments],
                               env=environment, check=True)
            index_git("read-tree", item["commit"])
            for entry in item.get("patches", []):
                patch = ROOT / entry["path"]
                if hashlib.sha256(patch.read_bytes()).hexdigest() != entry["sha256"]:
                    raise RuntimeError("Patch checksum mismatch: " + str(patch))
                index_git("apply", "--cached", "--check", str(patch.resolve()))
                index_git("apply", "--cached", str(patch.resolve()))
        print(item["name"] + ": " + item["commit"] + " verified", flush=True)
    for item in lock["artifacts"]:
        path = destination / item["name"]
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            temporary = path.with_suffix(path.suffix + ".partial")
            request = urllib.request.Request(item["url"], headers={"User-Agent": "pad7spro-linux-gpu/0.1"})
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != item["sha256"]:
                temporary.unlink()
                raise RuntimeError("Artifact checksum mismatch: " + item["name"])
            temporary.replace(path)
        print(item["name"] + ": SHA-256 verified", flush=True)


if __name__ == "__main__":
    main()
