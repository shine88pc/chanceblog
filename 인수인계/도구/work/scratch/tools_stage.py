"""저장소(블로그 main)의 `인수인계/도구/work/` 에 넣을 이 PC 의 현행 도구·규칙 문서를 스테이징한다(읽기만 — 저장소는 건드리지 않는다).
- 결과: W/scratch/mig1_stage/인수인계/도구/work/… (저장소 안 경로와 같은 모양). 윈도 계정 이름이 든 경로는 일반 말로 바꾸고, 금지 글이 남으면 실패로 센다.
- 이 세션 전용 분석 스크립트·일회용 갈래 스크립트는 넣지 않는다 — 넣을 목록은 아래 세 목록(ROOT_TOOLS·RULE_DOCS·SCRATCH_TOOLS)이고 새 도구는 거기에 더한다.
- W = 이 파일이 있는 폴더의 위 폴더(2026-11-23 MIG1 이 옛 PC 판의 고정 경로를 이렇게 바꿨다). 도구들이 옛 PC 의 W 이름을 상수로 쓰는 것은 그대로 옮긴다(도구 README 의 W 경로 절).
- 가릴 낱말(계정 이름 말고 회사·개인을 알아볼 수 있는 낱말)은 환경 변수 STAGE_FORBID(쉼표로 구분)로 준다 — 코드에는 적지 않는다.
사용: py -3.12 -X utf8 scratch/tools_stage.py"""
import os
import re
import shutil
import sys
from pathlib import Path

W = Path(__file__).resolve().parent.parent
OUT = W / "scratch" / "mig1_stage" / "인수인계" / "도구" / "work"

ROOT_TOOLS = ["lowprio.py", "qt_lock.py", "make_request.py", "make_info_request.py", "make_merged_notice.py",
              "next_notice_no.py", "notice_tools.py", "commit_as_author.py", "mk_merge_branch.py"]
RULE_DOCS = [("operator_delegation_rules.md", "operator_delegation_rules.md"),
             ("agent_common_rules.md", "agent_common_rules.md"),
             ("audit6/improve/LANE_RULES.md", "audit6/improve/LANE_RULES.md")]
SCRATCH_TOOLS = ["badge_wait.sh", "build_blog_merge.py", "ci_main.py", "ci_wip_status.py", "combine_lanes_desktop.py",
                 "jk_read.py", "keep_both.py", "lanes.py", "main_runs_wait.sh", "mkverify.py", "note.sh", "pc_load.py",
                 "prepush_check.sh", "rehearse.py", "run_modules.py", "squash_onto.py", "watch_all.sh", "watch_heads2.sh", "watch_issues.py"]
SEP = "[" + chr(92) + "/]"
USERS = "[A-Za-z]:" + SEP + "+Users" + SEP + "+"
# (정규식, 바꿀 글) — 윈도 계정 폴더 아래의 파이썬 경로와 AI 세션 기록 폴더 경로를 일반 말로
SUBS = [
    (re.compile(USERS + "[^/\\s`'\"]+/AppData/Local/Programs/Python/Python312/python[.]exe"), "py -3.12"),
    (re.compile(USERS + "[^/\\s`'\"]+/[.]claude[^\\s`'\"]*"), "<AI 세션 기록 폴더>"),
]
TOKENS = re.compile(r"ghp_|github_pat|Bearer [A-Za-z0-9]|sk-[A-Za-z0-9]{10}")
MAIL = re.compile(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+[.](?:com|net|kr)\b")
AUTHOR_MAIL = re.compile(r'GIT_AUTHOR_EMAIL="([^"]+)"')
STANDARD_MAILS = {"noreply" + chr(64) + "anthropic.com"}   # 표준 공동 작성 줄의 보낸이 전용 주소(소스에 메일 모양을 그대로 두지 않는다)


def author_mail():
    """저장소 도구가 이미 갖고 있는 고정 작성자 메일(commit_as_author.py 의 상수) — 허용한다. 없으면 빈 집합."""
    path = W / "commit_as_author.py"
    found = AUTHOR_MAIL.search(path.read_text(encoding="utf-8")) if path.is_file() else None
    return {found.group(1)} if found else set()


def extra_words():
    """환경 변수 STAGE_FORBID(쉼표 구분)의 낱말 — 계정 이름 말고 회사·개인을 알아볼 수 있는 낱말."""
    return [word.strip() for word in os.environ.get("STAGE_FORBID", "").split(",") if word.strip()]


def forbidden(extra_allowed):
    """(금지 낱말 정규식, 허용 메일 집합) — 계정 이름·계정 폴더 경로·AppData·환경 변수 STAGE_FORBID 의 낱말."""
    words = [re.escape(word) for word in [Path.home().name, "AppData"] + extra_words() if word]
    return re.compile("|".join(words + [USERS]), re.I), STANDARD_MAILS | extra_allowed


def stage(src, rel, bad, rx, allowed):
    raw = src.read_bytes().decode("utf-8")
    text = raw
    for pattern, new in SUBS:
        text = pattern.sub(new, text)
    hits = [m.group(0) for m in rx.finditer(text)] + [m.group(0) for m in TOKENS.finditer(text)]
    hits += [m.group(0) for m in MAIL.finditer(text) if m.group(0) not in allowed]
    dst = OUT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if hits:
        dst.unlink(missing_ok=True)                                              # 금지 글이 남은 파일은 쓰지 않는다(같은 이름의 앞선 사본이 있어도 지운다)
        bad.append((rel, hits[:3]))
    else:
        dst.write_bytes(text.encode("utf-8"))
    return len(raw.encode("utf-8")), len(text.encode("utf-8")), len(hits)


def main():
    if OUT.exists():
        assert OUT.name == "work" and OUT.parent.name == "도구" and "mig1_stage" in OUT.parts   # 안전 장치: 스테이징 폴더 밖은 지우지 않는다
        shutil.rmtree(OUT)
    if not extra_words():
        print("!!! 경고: STAGE_FORBID 가 비어 있다 — 계정 이름·AppData·메일 모양·토큰 모양만 걸러진다. 회사·개인을 알아볼 수 있는 낱말(요금제·회사 이름 등)은 걸러지지 않으니 사본을 눈으로 한 번 더 훑고, 공개할 글이면 STAGE_FORBID=낱말,낱말 로 다시 돌린다.", file=sys.stderr)
    rx, allowed = forbidden(author_mail())
    bad, rows = [], []
    for name in ROOT_TOOLS:
        rows.append((f"work/{name}", *stage(W / name, name, bad, rx, allowed)))
    for src_rel, dst_rel in RULE_DOCS:
        rows.append((f"work/{dst_rel}", *stage(W / src_rel, dst_rel, bad, rx, allowed)))
    for name in SCRATCH_TOOLS:
        rows.append((f"work/scratch/{name}", *stage(W / "scratch" / name, f"scratch/{name}", bad, rx, allowed)))
    for rel, before, after, hits in rows:
        mark = "" if before == after else f" (바뀜 {before}->{after})"
        print(f"{rel}: {after}바이트{mark}{' [금지 글 ' + str(hits) + ']' if hits else ''}")
    print(f"총 {len(rows)}개, 금지 글 남은 파일 {len(bad)}개")
    for rel, hits in bad:
        print(f"  실패: {rel} — 금지 글 {len(hits)}곳")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
