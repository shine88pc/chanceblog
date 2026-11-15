"""이관 번들 풀기 — 빈 PC 에서 작업 폴더(W)를 만든다(표준 라이브러리만, 파이썬 3.10 이상).
이 파일은 저장소 가지 `ai/claude/NO-MERGE-migration-bundle` 의 `인수인계/이관_번들/` 안에 있고, 같은 폴더의 `work/` 에 이 PC 에서 쓰던 도구·양식·지시서가 있다.

사용:
  python bootstrap.py --work C:/work/ai [--python <파이썬 3.12 실행 파일 경로>] [--clone] [--dry-run]
- --work     작업 폴더(W). 없으면 만든다. 기본 `C:/work/ai` — 이 경로면 도구를 고칠 필요가 없다. 다른 경로면 복사한 텍스트 파일 안의 `C:/work/ai` 를 새 경로로 바꾼다.
- --python   복사한 도구 안의 파이썬 3.12 경로 자리표(`<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe`)를 이 경로로 바꾼다.
- --clone    저장소를 복제한다: `W/wt_r30` = 블로그 저장소의 요청 가지 `ai/claude/NO-MERGE-operator-requests`(도구가 이 폴더를 요청 가지 작업 폴더로 쓴다 — 여기서 checkout 하지 않는다),
             `W/cd_repo` = 데스크톱 저장소 main. (읽기 전용 공개 저장소라 로그인 없이 된다. 푸시 권한은 따로 — 운영자가 이 PC 에서 직접 인증한다.)
- --dry-run  아무것도 쓰지 않고 무엇을 할지만 보인다.
끝나면 도구의 문법 검사(py_compile)를 하고 다음 할 일을 출력한다. 비밀·키는 다루지 않는다."""
import argparse
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "work"
DEFAULT_W = "C:/work/ai"
PY_PLACEHOLDER = "<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe"
TEXT_SUFFIX = {".py", ".sh", ".md", ".txt"}
BLOG = "https://github.com/shine88pc/chanceblog.git"
DESK = "https://github.com/shine88pc/chanceblog-desktop.git"
REQUEST_BRANCH = "ai/claude/NO-MERGE-operator-requests"


def run(cmd, dry):
    print("  $ " + " ".join(str(c) for c in cmd))
    if dry:
        return 0
    return subprocess.run(cmd).returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", default=DEFAULT_W)
    ap.add_argument("--python", default="")
    ap.add_argument("--clone", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    w = Path(a.work)
    new_w = str(w).replace("\\", "/")
    dry = a.dry_run
    if not SRC.is_dir():
        sys.exit(f"번들의 work 폴더가 없습니다: {SRC}")
    print(f"작업 폴더 W = {new_w}  (번들 {SRC})")
    copied = []
    for src in sorted(SRC.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(SRC)
        dst = w / rel
        text = None
        if src.suffix in TEXT_SUFFIX:
            text = src.read_text(encoding="utf-8")
            if new_w != DEFAULT_W:
                text = text.replace(DEFAULT_W, new_w)
            if a.python:
                text = text.replace(PY_PLACEHOLDER, a.python.replace("\\", "/"))
        print(f"  복사 {rel}")
        if not dry:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if text is not None:
                dst.write_text(text, encoding="utf-8", newline="")
            else:
                shutil.copyfile(src, dst)
        copied.append(dst)
    if a.clone:
        print("저장소 복제:")
        if not (w / "wt_r30").exists():
            run(["git", "clone", "--branch", REQUEST_BRANCH, BLOG, str(w / "wt_r30")], dry)
        else:
            print("  wt_r30 은 이미 있음 — 건너뜀")
        if not (w / "cd_repo").exists():
            run(["git", "clone", DESK, str(w / "cd_repo")], dry)
        else:
            print("  cd_repo 는 이미 있음 — 건너뜀")
    if not dry:
        bad = 0
        for p in copied:
            if p.suffix == ".py":
                try:
                    py_compile.compile(str(p), doraise=True, cfile=str(p.with_suffix(".pyc.tmp")))
                    p.with_suffix(".pyc.tmp").unlink(missing_ok=True)
                except py_compile.PyCompileError as e:
                    bad += 1
                    print(f"  문법 오류: {p} — {e.msg[:120]}")
        print(f"문법 검사: 파이썬 파일 {sum(1 for p in copied if p.suffix == '.py')}개 중 오류 {bad}개")
    print("\n다음 할 일:")
    print(" 1. README.md 의 '빈 PC 에서 시작하는 순서' 3번 이후(푸시 권한 점검 → state/COORDINATION.md 읽기 → 첫 보고)를 이어서 합니다.")
    print(" 2. 파이썬 경로가 맞지 않으면 복사된 도구 안의 `<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe` 를 이 PC 의 3.12 경로로 바꿉니다(--python 으로 다시 실행해도 됩니다).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
