"""CI 조각(scripts/ci_shard.py)과 같은 방식으로 — 한 프로세스에서 여러 시험 모듈을 이름 순으로 이어서 돌린다(시험 사이 오염 확인용).
사용: python -X utf8 run_shard_like.py <파이썬> <작업 폴더> <조각 번호> <조각 수> [--skip=모듈,모듈,…] [--only=모듈,모듈,…]
  조각의 모듈 목록은 작업 폴더의 `scripts/ci_shard.py <번호> <수> --list` 가 알려 준다. --skip 은 느린 모듈(git·프로세스를 진짜로 쓰는 것)을 빼는 데 쓴다.
  결과는 실패·오류 줄과 요약만 보여 준다(앞 N줄)."""
import os
import subprocess
import sys
import time
from pathlib import Path

python, root, shard, total = sys.argv[1:5]
opts = dict(a.split("=", 1) for a in sys.argv[5:] if a.startswith("--") and "=" in a)
skip = set(filter(None, opts.get("--skip", "").split(",")))
only = list(filter(None, opts.get("--only", "").split(",")))
env = dict(os.environ)
env.update({"PYTHONPATH": f"{root}\\src;{root}\\tests;{root}", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "CI_SHARD": shard, "CI_SHARD_TOTAL": total})
listing = subprocess.run([python, "-X", "utf8", str(Path(root) / "scripts" / "ci_shard.py"), shard, total, "--list"], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
mods = [m.strip() for m in listing.stdout.splitlines() if m.strip().startswith("test_")]
if only:
    mods = [m for m in mods if m in only]
mods = [m for m in mods if m not in skip]
print(f"조각 {shard}/{total}: {len(mods)}개 모듈(건너뜀 {len(skip)}) 한 프로세스로 이름 순 실행", flush=True)
started = time.time()
done = subprocess.run([python, "-B", "-X", "utf8", "-m", "unittest", *mods], cwd=str(Path(root) / "tests"), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3000)
out = (done.stdout + done.stderr).splitlines()
print(f"exit={done.returncode} {time.time() - started:.0f}s", flush=True)
shown = 0
for i, line in enumerate(out):
    if line.startswith(("FAIL:", "ERROR:")):
        print("\n".join(out[i:i + 40]), flush=True)
        shown += 1
        if shown >= 8:
            break
print("\n".join(l for l in out if l.startswith(("Ran ", "OK", "FAILED"))), flush=True)
print("DONE", flush=True)
