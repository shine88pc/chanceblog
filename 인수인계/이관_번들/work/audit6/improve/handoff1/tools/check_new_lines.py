"""새로 들어간 줄 점검 - 기준 커밋과 작업 폴더의 9개 문서를 줄 단위로 견줘 추가·바뀐 줄만 훑는다(읽기 전용).

사용: python -X utf8 check_new_lines.py <작업 폴더> [기준 커밋(기본 4b22239)]
오류(종료 코드 1): ASCII 물결표·웹 주소(카드의 git ls-remote 한 줄만 허용)·역슬래시·Liquid·광고 번호·비밀 모양·실제 블로그 이름·이 PC 경로·자리표(@@)·표 칸 수 불일치(기준에 없던 것)
참고(사람이 읽고 판단): 입구 문서·카드에 들어간 바뀌는 값(해시·R/M/P 번호·시각) 모양
"""
import difflib
import re
import subprocess
import sys

ROOT = sys.argv[1]
BASE = sys.argv[2] if len(sys.argv) > 2 else "4b22239"
FILES = ["AGENTS.md", "CLAUDE.md", "GEMINI.md", "AI_COLLAB.md", "HANDLER.md", "docs/SESSION_START.md", "docs/AGENT_RUNBOOK.md", "인수인계/작업내용.md", "WORKLOG.md", "인수인계/AI_기억/README.md"]
LOG_FILES = ("인수인계/작업내용.md", "WORKLOG.md")
LS_REMOTE_OK = "git ls-remote https://github.com/shine88pc/"
CHECKS = [
    ("물결표", re.compile(r"~")),
    ("웹 주소", re.compile(r"https?://", re.I)),
    ("역슬래시", re.compile(r"\\")),
    ("Liquid", re.compile(r"\{\{|\{%")),
    ("광고 번호 모양", re.compile(r"ca-pub-\d|pub-\d{8,}|adsbygoogle|googlesyndication", re.I)),
    ("비밀 모양", re.compile(r"AIza[0-9A-Za-z_\-]{20,}|ghp_[0-9A-Za-z]{20,}|github_pat_|-----BEGIN|xox[bp]-|sk-[A-Za-z0-9]{20,}|[0-9]{8,10}:[A-Za-z0-9_-]{30,}")),
    ("실제 블로그 이름", re.compile(r"macat0722|kcyoon", re.I)),
    ("이 PC 경로", re.compile(r"C:/work|C:/Users|/c/work|<사용자>")),
    ("자리표", re.compile(r"@@")),
]
VOLATILE = [
    ("해시 모양", re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,40}(?![0-9A-Za-z])")),
    ("R 번호", re.compile(r"R-[0-9]{3}")),
    ("M 번호", re.compile(r"(?<![A-Za-z])M[0-9]{3}")),
    ("P 번호", re.compile(r"(?<![A-Za-z])P[0-9]{3}")),
    ("시각", re.compile(r"(?<![0-9])[0-9]{1,2}:[0-9]{2}(?![0-9])")),
]


def base_text(name):
    result = subprocess.run(["git", "-C", ROOT, "-c", "core.quotepath=false", "show", BASE + ":" + name], capture_output=True)
    if result.returncode != 0:
        raise SystemExit("기준 커밋에서 못 읽음: " + name)
    return result.stdout.decode("utf-8").replace("\r\n", "\n")


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
info = 0
for name in FILES:
    with open(ROOT + "/" + name, "r", encoding="utf-8", newline="") as handle:
        raw = handle.read()
    now = raw.replace("\r\n", "\n")
    before = base_text(name)
    old_lines, new_lines = before.split("\n"), now.split("\n")
    added = []
    removed = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            added += new_lines[j1:j2]
        if tag in ("replace", "delete"):
            removed += i2 - i1
    print("==", name, "추가·바뀐 줄", len(added), "/ 빠진·바뀐 옛 줄", removed)
    for label, rx in CHECKS:
        hits = [line for line in added if rx.search(line)]
        if label == "웹 주소":
            hits = [line for line in hits if LS_REMOTE_OK not in line]
        if hits:
            bad += len(hits)
            print("  [오류 %s] %d 줄:" % (label, len(hits)))
            for line in hits[:3]:
                m = rx.search(line)
                s = max(0, m.start() - 30)
                print("     ...%s..." % line[s:m.end() + 30])
    if name not in LOG_FILES:
        for label, rx in VOLATILE:
            hits = [(line, m.group(0)) for line in added for m in rx.finditer(line)]
            hits = [(line, tok) for line, tok in hits if tok not in ("M###",)]
            if hits:
                info += len(hits)
                print("  [참고 %s] %d 개: %s" % (label, len(hits), ", ".join(sorted(set(tok for _, tok in hits)))[:140]))
    new_p, old_p = table_problems(now), table_problems(before)
    old_keys = {(p[2], p[3]) for p in old_p}
    fresh = [p for p in new_p if (p[2], p[3]) not in old_keys]
    if "|" in "".join(added):
        print("  표 칸 수 불일치: 지금 %d 건 / 기준 %d 건 / 새로 생긴 것 %d 건" % (len(new_p), len(old_p), len(fresh)))
    for p in fresh[:5]:
        bad += 1
        print("     줄 %d: 칸 구분 %d 개(기대 %d) %s" % p)
    crlf_lines = raw.count("\r\n")
    lf_only = raw.count("\n") - crlf_lines
    if lf_only:
        bad += 1
        print("  [오류] 줄 끝이 섞임: CRLF %d 줄 / LF 만 %d 줄" % (crlf_lines, lf_only))
print("TOTAL 오류 줄:", bad, "| 참고 항목:", info)
sys.exit(1 if bad else 0)
