"""이 PC 의 AI 기억 폴더 가운데 새 세션이 알아야 할 운영자 상시 지시·정책 사본을 저장소용으로 다듬어 스테이징한다(읽기만 — 저장소는 건드리지 않는다).
- 공개 저장소에 둘 것이므로 윈도 계정 이름·메일·회사 계정 세부·세션 번호는 바꾼다.
- 블로그·앱 프로젝트와 무관한 개인 업무 기억과 옛 인수 스냅샷은 넣지 않는다.
사용: py -3.12 -X utf8 scratch/memcopy_stage.py <AI 기억 폴더> [옮길 파일 이름 …]
  - <AI 기억 폴더> 는 그 PC 의 Claude 프로젝트 기억 폴더 안의 `memory` 폴더다 — 경로에 윈도 계정 이름이 들어 있어 코드에 적지 않고 인자로 받는다(2026-11-23 MIG1 이 옛 PC 판의 고정 경로를 이렇게 바꿨다).
  - 옮길 파일 이름을 안 주면 INCLUDE 목록(2026-11-23 사본의 9개)을 쓴다. 새로 쌓인 기억은 이름을 주어 고른다.
  - 가릴 낱말(계정 이름 말고도 회사·개인을 알아볼 수 있는 낱말)은 환경 변수 STAGE_FORBID(쉼표로 구분)로 준다 — 코드에는 적지 않는다.
  → W/scratch/memcopy_stage/ 에 파일을 쓰고 요약을 출력한다(W = 이 파일이 있는 폴더의 위 폴더). 금지 글이 남으면 종료 코드 1 이다."""
import os
import re
import sys
from pathlib import Path

W = Path(__file__).resolve().parent.parent
OUT = W / "scratch" / "memcopy_stage"
INCLUDE = [
    "approval-answers-need-valid-form.md",
    "blog-slots-limit-on-hold.md",
    "low-ai-cost-operations.md",
    "operator-merges-on-pr-open.md",
    "operator-reports-via-messages-not-chat.md",
    "operator-wants-fewer-confirmations.md",
    "parallel-wave-2026-11-22.md",
    "pc-shared-moderate-performance.md",
    "photo-analysis-local-only-directive.md",
]
SESSION_LINE = re.compile(r"(?m)^(\s*originSessionId:)\s*\S+\s*$")
USER_FOLDER = re.compile("[A-Za-z]:[" + chr(92) + "/]+Users[" + chr(92) + "/]+[^" + chr(92) + "/\\s`'\"]+")
MAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:[.][A-Za-z0-9-]+)+")
TOKENS = re.compile(r"ghp_|github_pat|Bearer |sk-[A-Za-z0-9]{10}")


def extra_words():
    """환경 변수 STAGE_FORBID(쉼표 구분)의 낱말 — 계정 이름 말고 회사·개인을 알아볼 수 있는 낱말."""
    return [word.strip() for word in os.environ.get("STAGE_FORBID", "").split(",") if word.strip()]


def forbidden_words():
    """그 PC 의 계정 이름과 환경 변수 STAGE_FORBID 의 낱말 — 남아 있으면 실패로 센다."""
    return [word for word in [Path.home().name] + extra_words() if word]


def clean(text):
    """(다듬은 글, 가린 세션 번호 수) — 세션 번호와 사용자 폴더 경로를 일반 말로 바꾼다."""
    text, sessions = SESSION_LINE.subn(r"\1 (세션 번호)", text)
    return USER_FOLDER.sub("<사용자 폴더>", text), sessions


def leftovers(text, words):
    """다듬은 글에 남은 금지 글(계정 이름·낱말·메일 모양·토큰 모양) 목록."""
    hits = [word for word in words if word.lower() in text.lower()]
    hits += MAIL.findall(text)
    hits += TOKENS.findall(text)
    return hits


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    src = Path(argv[0])
    names = argv[1:] or INCLUDE
    words = forbidden_words()
    if not extra_words():
        print("!!! 경고: STAGE_FORBID 가 비어 있다 — 계정 이름·메일 모양·토큰 모양만 걸러진다. 회사·개인을 알아볼 수 있는 낱말(요금제·회사 이름 등)은 걸러지지 않으니 사본을 눈으로 한 번 더 훑고, 공개할 글이면 STAGE_FORBID=낱말,낱말 로 다시 돌린다.", file=sys.stderr)
    OUT.mkdir(parents=True, exist_ok=True)
    bad = 0
    for name in names:
        raw = (src / name).read_bytes().decode("utf-8")
        text, sessions = clean(raw)
        hits = leftovers(text, words)
        if hits:
            (OUT / name).unlink(missing_ok=True)                                # 앞선 실행이 쓴 같은 이름의 사본이 남아 쓰이지 않게 지운다
            print(f"[실패] {name}: 금지 글 {len(hits)}곳 남음 — 사본을 쓰지 않고 앞선 사본도 지웠다(손으로 말을 바꾼 뒤 다시)")
            bad += 1
            continue
        (OUT / name).write_bytes(text.encode("utf-8"))
        print(f"{name}: {len(raw.encode('utf-8'))} -> {len(text.encode('utf-8'))} 바이트, 세션 번호 {sessions}곳 가림")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
