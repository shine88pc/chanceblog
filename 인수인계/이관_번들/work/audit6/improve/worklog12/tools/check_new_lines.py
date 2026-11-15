"""새로 들어간 줄 점검 — 기준 커밋의 두 문서와 root 의 두 문서를 줄 단위로 견줘 추가된 줄만 훑어 금지 패턴과 표 칸 수를 본다(읽기 전용).

사용: python -X utf8 check_new_lines.py <root(작업 폴더나 변이 시험 사본)> [기준 커밋(기본 d503c1b)]
점검: ASCII 물결표·웹 주소(http)·역슬래시·Liquid 구문·광고 번호 모양·비밀 모양·실제 블로그 이름·옛 영문 워크플로 이름·이 PC 경로(C:/work)·자리표(@@)·표 칸 수 불일치(기준에 없던 것)
"""
import difflib
import re
import subprocess
import sys

ROOT = sys.argv[1]
BASE = sys.argv[2] if len(sys.argv) > 2 else "d503c1b"
GIT_REPO = "C:/work/ai/improve_wt_worklog12"
FILES = ["인수인계/작업내용.md", "WORKLOG.md"]
OLD_NAMES = ["Chance_Blog Full-Auto Engine", "Blogger Generate", "Deploy GitHub Pages", "Guardrails", "PR Scope Check", "Sync Issue Form", "Issue Edit"]
CHECKS = [
    ("물결표", re.compile(r"~")),
    ("웹 주소", re.compile(r"https?://", re.I)),
    ("역슬래시", re.compile(r"\\")),
    ("Liquid", re.compile(r"\{\{|\{%")),
    ("광고 번호 모양", re.compile(r"ca-pub-\d|pub-\d{8,}|adsbygoogle|googlesyndication", re.I)),
    ("비밀 모양", re.compile(r"AIza[0-9A-Za-z_\-]{20,}|ghp_[0-9A-Za-z]{20,}|github_pat_|-----BEGIN|xox[bp]-|sk-[A-Za-z0-9]{20,}|\b\d{8,10}:[A-Za-z0-9_-]{30,}")),
    ("실제 블로그 이름", re.compile(r"macat0722|kcyoon", re.I)),
    ("이 PC 경로", re.compile(r"C:/work|C:/Users|/c/work")),
    ("자리표", re.compile(r"@@")),
]


def base_text(name):
    r = subprocess.run(["git", "-C", GIT_REPO, "-c", "core.quotepath=false", "show", BASE + ":" + name], capture_output=True)
    return r.stdout.decode("utf-8").replace("\r\n", "\n")


def table_problems(text):
    problems = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if lines[i].startswith("|"):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            block = lines[i:j]
            want = block[0].count("|")
            for k, row in enumerate(block):
                if row.count("|") != want:
                    problems.append((i + k + 1, row.count("|"), want, row[:60]))
            i = j
        else:
            i += 1
    return problems


bad = 0
for name in FILES:
    with open(ROOT + "/" + name, "r", encoding="utf-8", newline="") as h:
        now = h.read().replace("\r\n", "\n")
    before = base_text(name)
    a, b = before.split("\n"), now.split("\n")
    added = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            added += b[j1:j2]
    print("==", name, "추가·바뀐 줄", len(added))
    for label, rx in CHECKS:
        hits = [line for line in added if rx.search(line)]
        if hits:
            bad += len(hits)
            print("  [%s] %d 줄:" % (label, len(hits)))
            for line in hits[:3]:
                m = rx.search(line)
                s = max(0, m.start() - 30)
                print("     ...%s..." % line[s:m.end() + 30])
    if name != "WORKLOG.md":
        for old in OLD_NAMES:
            hits = [line for line in added if old in line]
            if hits:
                bad += len(hits)
                print("  [옛 영문 이름 %s] %d 줄" % (old, len(hits)))
    new_p, old_p = table_problems(now), table_problems(before)
    old_keys = {(p[2], p[3]) for p in old_p}
    fresh = [p for p in new_p if (p[2], p[3]) not in old_keys]
    print("  표 칸 수 불일치: 지금 %d 건 / 기준 %d 건 / 새로 생긴 것 %d 건" % (len(new_p), len(old_p), len(fresh)))
    for p in fresh[:5]:
        bad += 1
        print("     줄 %d: 칸 구분 %d 개(기대 %d) %s" % p)
    crlf_lines = open(ROOT + "/" + name, "rb").read().count(b"\r\n")
    print("  줄 끝 CRLF %d 줄" % crlf_lines)
print("TOTAL 문제 줄:", bad)
sys.exit(1 if bad else 0)
