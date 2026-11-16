"""AI 직접 병합 '검사 전용(dry-run)' 도구 — 병합 가지가 정책이 허용하는 병합 후보인지 **판정만** 한다. 이 도구에는 푸시·병합 기능이 없다.
(운영자 이슈 #198 '논의·준비까지만' — 준비물. 켜는 것은 운영자 결정 뒤 별도 승인.)

사용:
  python -X utf8 merge_guard.py <저장소 작업 폴더> <가지 ref> [--base origin/main] [--allow A|A,A+|A,A+,B] [--ci success|unknown] [--list N]
  --list N : origin/main 의 최근 병합 N건을 (병합 커밋 vs 부모) 로 분류만 한다(과거에 이 정책이 몇 건을 자동 처리했을지 가늠).
등급: A 문서만 · A+ 문서·시험 · B 코드 포함(.github·광고 표면·레지스트리 값·글·설정·의존성 제외) · C 운영자 전용 경로 포함(어떤 정책에서도 AI 병합 금지).
판정 ELIGIBLE 이려면: 가지 이름 규칙·부모 위 한 커밋(빨리감기 가능)·제목 `[M###]` 일치·등급이 --allow 안·비밀 모양 0·검사 초록(--ci success)·'독립 검증' 기록 문구.
종료 코드: 0 ELIGIBLE · 1 NOT ELIGIBLE · 2 사용법 오류."""
import argparse
import re
import subprocess
import sys

DOC_ALLOW = [r"^인수인계/.*\.md$", r"^WORKLOG\.md$", r"^docs/.*\.md$", r"^(README|AGENTS|CLAUDE|HANDLER|AI_COLLAB|GEMINI)\.md$"]
TEST_ALLOW = [r"^tests/"]
PROTECT = [r"^\.github/", r"^index\.html$", r"^_config\.yml$", r"^_layouts/", r"^_includes/", r"^ads\.txt$",
           r"^pipeline/(blogs|source_registry)\.json$", r"^_posts/", r"^requirements", r"^vendor/", r"^about\.md$", r"^contact\.md$",
           r"^pages\.json$", r"^(history|blogger_history|blogger_ko_history|naver_history)\.json$", r"^feed\.xml$", r"^assets/"]
SECRET_RES = [r"AIza[0-9A-Za-z_\-]{20,}", r"ghp_[0-9A-Za-z]{20,}", r"github_pat_[0-9A-Za-z_]{20,}", r"\bsk-[A-Za-z0-9]{20,}",
              r"ca-pub-\d{6,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"\bbot\d{8,}:[A-Za-z0-9_\-]{30,}", r"(?i)\b(token|secret|api[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{24,}"]
BRANCH_RE = re.compile(r"^(?:origin/)?ai/claude/M(\d{3,4})-[A-Za-z0-9._\-]+$")
TITLE_RE = re.compile(r"^\[M(\d{3,4})\] ")
RANK = {"A": 0, "A+": 1, "B": 2, "C": 3}


def git(repo, *args):
    done = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8")
    return done.stdout.strip(), done.returncode


def tier(paths):
    if not paths:
        return "A"
    if any(any(re.match(p, x) for p in PROTECT) for x in paths):
        return "C"
    if all(any(re.match(p, x) for p in DOC_ALLOW) for x in paths):
        return "A"
    if all(any(re.match(p, x) for p in DOC_ALLOW + TEST_ALLOW) for x in paths):
        return "A+"
    return "B"


def inspect(repo, base, head, branch_name=None, allow="A", ci="unknown", quiet=False):
    reasons, notes = [], []
    if branch_name is not None:
        m = BRANCH_RE.match(branch_name)
        if not m:
            reasons.append("가지 이름이 ai/claude/M###-슬러그 규칙이 아님")
        branch_no = m.group(1) if m else None
    else:
        branch_no = None
    ahead, rc = git(repo, "rev-list", "--count", f"{base}..{head}")
    if rc or ahead != "1":
        reasons.append(f"부모(기준) 위 한 커밋이 아님(앞선 커밋 {ahead or '?'})")
    _, ff = git(repo, "merge-base", "--is-ancestor", base, head)
    if ff != 0:
        reasons.append("빨리감기(fast-forward) 불가 — 기준이 앞서 나갔음")
    title, _ = git(repo, "log", "-1", "--format=%s", head)
    tm = TITLE_RE.match(title)
    if not tm:
        reasons.append("커밋 제목이 [M###] 로 시작하지 않음")
    elif branch_no and tm.group(1) != branch_no:
        reasons.append("제목의 M 번호와 가지 이름의 M 번호가 다름")
    files_out, _ = git(repo, "diff", "--name-only", base, head)
    files = [f for f in files_out.split("\n") if f]
    t = tier(files)
    allowed_top = allow.split(",")[-1]
    if RANK[t] > RANK[allowed_top]:
        reasons.append(f"변경 등급 {t} 는 허용 등급({allow}) 밖")
    if t == "C":
        bad = [f for f in files if any(re.match(p, f) for p in PROTECT)]
        reasons.append("운영자 전용 경로 포함: " + ", ".join(bad[:4]))
    diff, _ = git(repo, "diff", "-U0", base, head)
    added = [l[1:] for l in diff.split("\n") if l.startswith("+") and not l.startswith("+++")]
    hits = [r for r in SECRET_RES if any(re.search(r, l) for l in added)]
    if hits:
        reasons.append("비밀 모양 낱말 발견(패턴 %d개)" % len(hits))
    if ci != "success":
        reasons.append("가지 검사 결과가 초록으로 확인되지 않음(--ci success 필요)")
    msg, _ = git(repo, "log", "-1", "--format=%B", head)
    if "독립 검증" not in msg:
        reasons.append("커밋 본문에 '독립 검증' 기록 문구가 없음")
    elif re.search(r"필수\s*[1-9]", msg) and not re.search(r"필수\s*0", msg):
        notes.append("본문에 필수 지적이 남았다는 표현이 있음 — 사람이 확인")
    return {"title": title[:60], "files": len(files), "tier": t, "ok": not reasons, "reasons": reasons, "notes": notes}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("branch", nargs="?")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--allow", default="A")
    ap.add_argument("--ci", default="unknown")
    ap.add_argument("--list", type=int, default=0)
    a = ap.parse_args()
    if a.list:
        out, _ = git(a.repo, "log", "origin/main", "--first-parent", "-n", str(a.list * 2), "--format=%H|%ad|%s", "--date=format:%m-%d %H:%M")
        shown = 0
        counts = {}
        for line in out.split("\n"):
            h, when, subj = line.split("|", 2)
            if not subj.startswith("[M") or shown >= a.list:
                continue
            r = inspect(a.repo, h + "^", h, None, "A,A+,B", "success")
            counts[r["tier"]] = counts.get(r["tier"], 0) + 1
            shown += 1
            print(f"{when} | {r['title']:60s} | 파일 {r['files']:3d} | 등급 {r['tier']}")
        print("등급별 건수:", counts)
        return 0
    if not a.branch:
        print("가지 ref 가 필요합니다", file=sys.stderr)
        return 2
    r = inspect(a.repo, a.base, a.branch, a.branch, a.allow, a.ci)
    print(f"{r['title']} | 파일 {r['files']} | 등급 {r['tier']} | 허용 {a.allow}")
    for reason in r["reasons"]:
        print("  ✗", reason)
    for n in r["notes"]:
        print("  ·", n)
    print("판정:", "ELIGIBLE" if r["ok"] else "NOT ELIGIBLE")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
