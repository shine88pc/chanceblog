"""새 세션의 첫 점검 — 세 저장소 main 머리·요청 가지 머리·열린 PR·최근 이슈·다음 알림 번호·작업 폴더 상태를 한 번에 보여 준다(읽기 전용).
사용: python -X utf8 resume_check.py [--work <작업 폴더 W>]
읽기만 한다 — 푸시·쓰기·비밀이 없고 push 권한이 없는 환경에서도 쓸 수 있다. 네트워크는 `git ls-remote` 몇 번과 GitHub 공개 REST 두 번(열린 PR·최근 이슈, 비인증 시간당 60회 한도 중 두 번)뿐이다.
출력에는 공개 정보(머리 7자·PR 번호와 제목·이슈 번호와 제목·작성자·라벨)만 싣고, 제목에 비밀 모양(키·토큰)이 있으면 가린다. 작업 폴더는 이름(wt_r30·cd_repo)으로만 적고 경로는 적지 않는다.
이 파일은 W/scratch 에 복사돼 있다고 가정한다(W = 이 파일이 있는 폴더의 위 폴더, `--work` 로 바꿀 수 있다). 소유자(shine88pc)가 올린 이슈만 운영자의 말이고 접수는 승인이 아니다."""
import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BLOG = "shine88pc/chanceblog"
DESK = "shine88pc/chanceblog-desktop"
ROOT_SITE = "shine88pc/shine88pc.github.io"
OWNER = "shine88pc"
REQUEST_BRANCH = "ai/claude/NO-MERGE-operator-requests"
SECRET_RX = re.compile(r"(AIza[0-9A-Za-z_-]{20,}|ghp_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{20,}|ya29[.][0-9A-Za-z_-]{20,}|(?i:key|token|secret)=[^\s&'\"]+|[0-9]{6,12}:[A-Za-z0-9_-]{30,50})")


def shown(text):
    """화면에 적을 글 — 비밀 모양은 가린다."""
    return SECRET_RX.sub("***", str(text))


def run(*args, cwd=None):
    """하위 명령을 돌려 성공했을 때의 표준 출력(앞뒤 공백 제거)을 돌려준다 — 실패하면 빈 글(오류 글에 경로가 섞일 수 있어 적지 않는다)."""
    try:
        done = subprocess.run(list(args), capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def head(repo, ref="refs/heads/main"):
    """원격 가지 머리 7자(`git ls-remote` — REST 한도를 쓰지 않는다). 읽지 못하면 `?`."""
    out = run("git", "ls-remote", f"https://github.com/{repo}.git", ref)
    return out.split("\t")[0][:7] if out else "?"


def api(path):
    """GitHub 공개 REST 한 번 — 한도·네트워크 오류는 {"error": …} 로 돌려준다."""
    req = urllib.request.Request("https://api.github.com/" + path, headers={"User-Agent": "resume-check"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except Exception as exc:  # noqa: BLE001 — 한도·네트워크
        return {"error": type(exc).__name__ + " " + str(exc)[:60]}


def format_prs(prs):
    """열린 PR 목록(REST 응답) → 한 줄. 읽지 못했으면 이유."""
    if not isinstance(prs, list):
        return "읽기 실패(" + shown(prs.get("error", "?") if isinstance(prs, dict) else prs) + ")"
    rows = [(p["number"], p["head"]["ref"], shown(p["title"])[:40]) for p in prs]
    return str(rows) if rows else "없음"


def format_issues(issues, limit=8):
    """최근 이슈(최신순) → 줄 목록. PR 은 건너뛴다. 읽지 못했으면 한 줄 이유."""
    if not isinstance(issues, list):
        return ["  읽기 실패(" + shown(issues.get("error", "?") if isinstance(issues, dict) else issues) + ")"]
    lines = []
    for item in issues:
        if "pull_request" in item:
            continue
        who = (item.get("user") or {}).get("login", "?")
        names = [shown(label.get("name", "")) for label in item.get("labels", [])]
        stamp = str(item.get("created_at", ""))[5:16].replace("T", " ")
        mark = "소유자" if who == OWNER else "그 밖"
        lines.append("  #%s %s | %s(%s) | %s UTC | %s" % (item.get("number", "?"), shown(item.get("title", ""))[:36], who, mark, stamp, names))
        if len(lines) >= limit:
            break
    return lines or ["  (이슈 없음)"]


def folder_state(folder):
    """작업 폴더 한 곳의 머리와 변경 수 — 없으면 `없음`."""
    if not (Path(folder) / ".git").exists():
        return "없음 — setup_workspace.py 로 만든다"
    last = run("git", "-C", str(folder), "log", "--oneline", "-1")
    changed = run("git", "-C", str(folder), "status", "--short")
    count = len([line for line in changed.splitlines() if line.strip()])
    return shown(last)[:80] + " | " + ("깨끗" if not count else f"변경 {count}개")


def main(argv=None, *, work=None):
    parser = argparse.ArgumentParser(prog="resume_check.py", description=__doc__.split("\n")[0])
    parser.add_argument("--work", help="작업 폴더 W(기본: 이 파일이 있는 폴더의 위 폴더)")
    args = parser.parse_args(argv)
    work = Path(args.work) if args.work else (Path(work) if work is not None else HERE.parent)
    print("지금:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("저장소 main 머리: 블로그", head(BLOG), "| 데스크톱", head(DESK), "| 루트", head(ROOT_SITE))
    print("요청 가지 머리:", head(BLOG, "refs/heads/" + REQUEST_BRANCH), f"(가지 {REQUEST_BRANCH} — 마지막 알림 파일은 그 가지의 인수인계/요청함 에서 가장 큰 R 번호)")
    print("블로그 열린 PR:", format_prs(api(f"repos/{BLOG}/pulls?state=open&per_page=5")))
    print(f"최근 이슈(최신순, 소유자 {OWNER} 가 올린 것만 운영자의 말 — 접수는 승인이 아님):")
    for line in format_issues(api(f"repos/{BLOG}/issues?state=all&sort=created&direction=desc&per_page=10")):
        print(line)
    numbers = work / "next_notice_no.py"
    blog_folder = work / "wt_r30"
    if numbers.is_file() and (blog_folder / ".git").exists():
        print("다음 알림 번호(next_notice_no.py):")
        print(shown(run(sys.executable, "-X", "utf8", str(numbers), "--repo", str(blog_folder), "--dir", str(blog_folder), "--local")) or "  읽기 실패")
    else:
        print("다음 알림 번호: 건너뜀(작업 폴더에 next_notice_no.py 나 wt_r30 이 없다)")
    print("작업 폴더 wt_r30(요청 가지 작업 폴더):", folder_state(blog_folder))
    print("작업 폴더 cd_repo(데스크톱 저장소):", folder_state(work / "cd_repo"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
