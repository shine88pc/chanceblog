"""병합완료 확인(`kind: merged`) 시험 공용 도구 — 요청 파일 글 만들기와 가짜 git 으로 알림 실행 돌리기. 네트워크·실제 GitHub·실제 텔레그램은 쓰지 않는다."""
import html
import re
import sys
import tempfile
from pathlib import Path

import _bootstrap
import operator_loop_helpers as oh
from notice_helpers import name_of, notice_text
from pipeline import operator_loop as ol

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

SUMMARY_BAD = "main 검사가 빨강입니다"
BLOB = "https://github.com/shine88pc/chanceblog/blob/"


def merged_text(number=266, no="M050", result="정상", title=None, summary=None, created="2026-11-12", extra=(), drop=(), body="병합 확인 결과 한 줄\n"):
    """병합완료 확인 요청 파일 글. None 인 칸은 줄 자체를 빼고 drop 은 뺄 키, extra 는 앞머리에 더할 줄들이다."""
    title = f"[{no}] 병합완료 확인 - {result}" if title is None else title
    summary = ("정상" if result == "정상" else SUMMARY_BAD) if summary is None else summary
    pairs = [("id", f"R-{number:03d}"), ("kind", "merged"), ("title", title), ("summary", summary), ("created", created), ("no", no), ("result", result)]
    lines = [f"{key}: {value}" for key, value in pairs if value is not None and key not in drop] + list(extra)
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def merge_text(number=264, no="M050"):
    """짝이 되는 병합 부탁(`kind: merge`) 요청 파일 글."""
    return notice_text(number=number, no=no, title="[M050] 병합 부탁 — 시험", summary="병합 부탁입니다")


def merged_name(number=266, no="M050"):
    return name_of(number, f"merged-{no.lower()}")


def phone(text):
    """폰 글에서 굵은 글씨·코드 표시를 걷고 문자 참조를 푼 모양."""
    return html.unescape(re.sub(r"</?(?:b|code)>", "", text))


def req_errors(files):
    """검증기 REQ-1(check_request_files)을 요청함 폴더 하나(파일들 {이름: 글})에 돌려 오류 줄들을 돌려준다."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, text in files.items():
            path = root / ol.REQUEST_DIR / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        return vr.check_request_files(root, sorted(f"{ol.REQUEST_DIR}/{name}" for name in files))


def run_requests(files, git=None, **kwargs):
    """알림 실행(`pipeline.operator_loop requests`)을 가짜 git(요청 파일 {이름: 글})·가짜 텔레그램으로 돌린다 → (종료 코드, 로그 줄들, 가짜 net, 가짜 git)."""
    git = git if git is not None else oh.RequestGit.with_requests(files)
    with tempfile.TemporaryDirectory() as tmp:
        code, lines, net, _ = oh.run_cli("requests", environ=oh.requests_env(**kwargs), runner=git, root=Path(tmp))
    return code, lines, net, git


def buttons_of(net, index=0):
    markup = net.bodies()[index].get("reply_markup")
    return [(item["text"], item["url"]) for item in markup["inline_keyboard"][0]] if markup else []
