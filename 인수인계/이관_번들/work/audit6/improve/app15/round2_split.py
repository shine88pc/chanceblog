"""2차 지시 커밋 나누기 도우미 — 두 항목이 함께 고친 문서(결정 기록·변경 이력)에서 **한 항목의 줄만** 담은 상태를 만들어 항목별 커밋을 따로 만들 수 있게 한다.
사용: python -X utf8 round2_split.py <작업 폴더> snapshot            마지막 모습(고친 파일 전부)을 보고서 폴더 `final_snapshot` 에 저장하고 sha256 목록을 적는다
      python -X utf8 round2_split.py <작업 폴더> ap15-state        DECISIONS.md·CHANGELOG.md 를 'AP15 것만 고친' 상태로 되돌린다(AP14 줄은 커밋 HEAD 의 것) — AP15 커밋 직전에 한다
      python -X utf8 round2_split.py <작업 폴더> restore           두 파일을 snapshot 의 마지막 모습으로 되돌린다 — AP14 커밋 직전에 한다
      python -X utf8 round2_split.py <작업 폴더> verify            작업 폴더의 고친 파일이 snapshot 과 글자 하나까지 같은지 본다(커밋이 끝난 뒤 — 없어지거나 달라진 것이 없어야 한다)
줄 단위로만 바꾼다(결정 기록의 한 행·변경 이력의 한 줄이 한 줄이다). 줄 끝(CRLF)은 보존한다."""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
HERE = Path("C:/work/ai/audit6/improve/app15")
SNAP = HERE / "final_snapshot"
MODE = sys.argv[2]
SHARED = ["docs/DECISIONS.md", "CHANGELOG.md"]
AP14_LINE = {"docs/DECISIONS.md": "| D-488 |", "CHANGELOG.md": "- 앱이 처리하지 못한 오류의 이름과 코드 위치만"}


def git(*args):
    done = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)
    if done.returncode:
        raise SystemExit(done.stderr.decode("utf-8", "replace"))
    return done.stdout


def changed_files():
    names = git("diff", "--name-only", "HEAD").decode("utf-8").split("\n")
    untracked = git("ls-files", "--others", "--exclude-standard").decode("utf-8").split("\n")
    return sorted(name for name in set(names + untracked) if name)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


if MODE == "snapshot":
    if SNAP.exists():
        import shutil
        shutil.rmtree(SNAP)
    lines = []
    for name in changed_files():
        target = SNAP / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
        lines.append(f"{sha(ROOT / name)}  {name}")
    (HERE / "final_snapshot.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("snapshot 저장:", len(lines), "개 파일")
    print("\n".join(lines))
elif MODE == "ap15-state":
    for name in SHARED:
        prefix = AP14_LINE[name].encode("utf-8")
        final = (SNAP / name).read_bytes()
        head = git("show", f"HEAD:{name}")
        eol = b"\r\n" if final.count(b"\r\n") * 2 >= final.count(b"\n") else b"\n"
        head_lines = [line.rstrip(b"\r") for line in head.split(b"\n")]
        head_hit = [line for line in head_lines if line.startswith(prefix)]
        final_lines = final.split(b"\n")
        hits = [index for index, line in enumerate(final_lines) if line.startswith(prefix)]
        if len(head_hit) != 1 or len(hits) != 1:
            raise SystemExit(f"{name}: AP14 줄이 하나가 아니다 head={len(head_hit)} final={len(hits)}")
        final_lines[hits[0]] = head_hit[0] + (b"\r" if eol == b"\r\n" else b"")
        (ROOT / name).write_bytes(b"\n".join(final_lines))
        print(f"{name}: AP14 줄을 HEAD 의 것으로 되돌림(AP15 것만 고친 상태)")
elif MODE == "restore":
    for name in SHARED:
        (ROOT / name).write_bytes((SNAP / name).read_bytes())
        print(f"{name}: snapshot 의 마지막 모습으로 되돌림")
elif MODE == "verify":
    bad = 0
    for line in (HERE / "final_snapshot.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        now = sha(ROOT / name) if (ROOT / name).exists() else "없음"
        if now != digest:
            bad += 1
            print("다름:", name)
    print("verify:", "모두 같음" if not bad else f"다른 파일 {bad}개")
    raise SystemExit(1 if bad else 0)
else:
    raise SystemExit(__doc__)
