"""AP14 문서 고치기 — 거짓이 된 문장을 정확히 한 곳씩 바꾸고(옛 글이 정확히 한 번 나오지 않으면 실패) 새 절을 끝에 덧붙인다. 줄 끝은 `doc_edit.py` 가 파일에 맞춘다.
사용: python -X utf8 apply_ap14_docs.py <작업 폴더>"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1])
HERE = Path(__file__).resolve().parent
EDIT = HERE / "doc_edit.py"
TEXT = HERE / "doc_text"

PAIRS = [
    ("docs/SECURITY.md",
     "- **로그 파일·내보내기**: 아직 없다. 만든다면 공통 경계가 이미 가린 기록을 쓴다.",
     "- **로그 파일·내보내기**: 작은 오류 기록 파일 하나가 있다(맨 끝 '오류 기록' 절 — 오류 이름과 코드 위치만 남기고 공통 가림 규칙을 거친다, D-488). 로그를 내보내는 기능은 아직 없다."),
    ("docs/UI_STATES.md",
     "어디에도 남지 않는다 — `report_unexpected` 가 `False` 를 돌려주고 화면에는 쉬운 안내만 보인다. 로그 파일은 설치 파일 묶음에서 정하고 이 묶음은 파일을 쓰지 않는다",
     "표준 오류에는 남지 않는다 — `report_unexpected` 가 `False` 를 돌려주고 화면에는 쉬운 안내만 보인다. 그 대신 **작은 오류 기록 파일**(`logs/errors.log` — 오류 이름과 코드 위치뿐, 첫 오류 때 처음 만들고 256 KB 짜리 세 개까지, AP14·D-488)에 한 줄이 남는다"),
    ("docs/UI_DESIGN_SPEC.md",
     "어디에도 남지 않는다(`False` 를 돌려주고 화면에는 쉬운 안내만 보인다) — '조용한 실패도 아니다' 는 **콘솔 실행 기준**이다. 로그 파일은 설치 파일 묶음에서 정한다(이 묶음은 파일을 쓰지 않는다 — 읽기 전용 원칙).",
     "표준 오류에는 남지 않는다(`False` 를 돌려주고 화면에는 쉬운 안내만 보인다) — '조용한 실패도 아니다' 는 **콘솔 실행 기준**이다. 그 대신 **작은 오류 기록 파일**(`logs/errors.log` — 오류 이름과 코드 위치뿐, 첫 오류 때 처음 만들고 256 KB 짜리 세 개까지, AP14·D-488)에 한 줄이 남는다."),
    ("docs/ARCHITECTURE.md",
     "본문 속 Secret 형태를 부르는 **공통 거절**(`refuse.py`) |",
     "본문 속 Secret 형태를 부르는 **공통 거절**(`refuse.py`), 처리하지 못한 오류의 **작은 오류 기록**(`errorlog.py` — 오류 이름과 코드 위치만, 첫 오류 때 처음 만드는 256 KB 세 개 돌려쓰기, AP14·D-488 — [`SECURITY.md`](SECURITY.md) 끝의 '오류 기록' 절) |"),
    ("docs/ARCHITECTURE.md",
     "·잠금 파일 `locks/`. 폴더는",
     "·잠금 파일 `locks/`·작은 오류 기록 `logs/errors.log`(처리하지 못한 오류가 났을 때 처음 만들어지는 256 KB 짜리 세 개 — 오류 이름과 코드 위치뿐, AP14·D-488). 폴더는"),
]


def run(*args):
    done = subprocess.run([sys.executable, "-X", "utf8", str(EDIT), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    print(done.stdout.strip() or done.stderr.strip())
    if done.returncode:
        raise SystemExit(done.returncode)


with tempfile.TemporaryDirectory() as folder:
    for index, (rel, old, new) in enumerate(PAIRS):
        old_file, new_file = Path(folder) / f"old{index}.txt", Path(folder) / f"new{index}.txt"
        old_file.write_text(old, encoding="utf-8")
        new_file.write_text(new, encoding="utf-8")
        run("replace", ROOT / rel, old_file, new_file)
run("replace", ROOT / "docs/TROUBLESHOOTING.md", TEXT / "trouble_old.txt", TEXT / "trouble_new.txt")
run("append", ROOT / "docs/SECURITY.md", TEXT / "security_ap14.md")
