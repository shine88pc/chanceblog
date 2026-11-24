"""작업 나무 하나에서 시험 모듈을 하나씩 따로 프로세스로 돌려 결과 한 줄씩만 낸다(읽기 전용 확인용, 총괄 전용).
사용: py -3.12 -X utf8 C:/work/ai/scratch/run_modules.py <작업 나무> <파이썬> <로그 파일> <모듈1> <모듈2> ...
각 모듈 결과: `모듈 OK n개 (t초)` 또는 `모듈 FAIL ...` 한 줄 + 실패 이름 몇 줄. 끝에 요약 한 줄.
PYTHONPATH=<나무>/src;<나무>/tests;<나무>, QT_QPA_PLATFORM=offscreen, LOCALAPPDATA 는 임시 폴더로 바꾼다."""
import os
import re
import subprocess
import sys
import tempfile
import time


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 2
    tree, py, log, *mods = argv
    sep = ";" if os.name == "nt" else ":"
    env = dict(os.environ)
    env["PYTHONPATH"] = sep.join([f"{tree}/src", f"{tree}/tests", tree])
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONUTF8"] = "1"
    tmp = tempfile.mkdtemp(prefix="runmods-")
    env["LOCALAPPDATA"] = tmp
    lines = []
    bad = 0
    total = 0
    for m in mods:
        t0 = time.time()
        done = subprocess.run([py, "-X", "utf8", "-m", "unittest", m], cwd=tree, env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        out = (done.stdout or "") + (done.stderr or "")
        ran = re.search(r"Ran (\d+) tests? in", out)
        n = int(ran.group(1)) if ran else 0
        total += n
        dt = time.time() - t0
        if done.returncode == 0:
            skipped = re.search(r"skipped=(\d+)", out)
            lines.append(f"{m} OK {n}개 ({dt:.0f}초)" + (f" 건너뜀 {skipped.group(1)}" if skipped else ""))
        else:
            bad += 1
            lines.append(f"{m} FAIL 종료코드 {done.returncode} ({n}개 실행, {dt:.0f}초)")
            for ln in re.findall(r"^(?:FAIL|ERROR): .*$", out, re.M)[:6]:
                lines.append("    " + ln[:200])
            tail = [l for l in out.strip().splitlines() if l.strip()][-3:]
            for ln in tail:
                lines.append("    | " + ln[:200])
        with open(log, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    lines.append(f"요약: 모듈 {len(mods)}개 중 실패 {bad}개 · 시험 {total}개 실행")
    with open(log, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
