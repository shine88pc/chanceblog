"""Scope / forbidden-pattern check on the NEW lines of the diff 4b22239..efda93e (read-only git)."""
import re
import subprocess
import sys

REPO = "C:/work/ai/improve_wt_mergepol1"


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True).stdout


diff = git("diff", "--unified=0", "4b22239..efda93e").decode("utf-8", "replace")
cur = None
added = {}
for line in diff.split("\n"):
    if line.startswith("+++ b/"):
        cur = line[6:]
        added.setdefault(cur, [])
    elif line.startswith("+") and not line.startswith("+++"):
        added.setdefault(cur, []).append(line[1:])

patterns = {
    "ascii_tilde": re.compile(r"~"),
    "AIza": re.compile(r"AIza"),
    "ghp_": re.compile(r"ghp_"),
    "BEGIN": re.compile(r"-----BEGIN"),
    "C:/work": re.compile(r"C:[/\\]+work", re.I),
    "C:/Users": re.compile(r"C:[/\\]+Users", re.I),
    "<사용자>": re.compile(r"<사용자>"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "url_http": re.compile(r"https?://", re.I),
    "www": re.compile(r"\bwww\.", re.I),
    "chanceblog": re.compile(r"chanceblog", re.I),
    "shine88pc": re.compile(r"shine88pc", re.I),
    "kcyoon": re.compile(r"kcyoon", re.I),
    "ca-pub-digits": re.compile(r"ca-pub-[0-9]"),
    "pub-digits": re.compile(r"pub-[0-9]{6,}"),
    "AKIA": re.compile(r"AKIA[0-9A-Z]{8,}"),
    "sk-": re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    "xox": re.compile(r"xox[baprs]-"),
    "github_pat": re.compile(r"github_pat_"),
    "naver_id": re.compile(r"naver[0-9a-f]{20,}"),
    "tab": re.compile(r"\t"),
}
for path, lines in added.items():
    print("==", path, "added lines:", len(lines))
    for name, rx in patterns.items():
        hits = [(i + 1, l) for i, l in enumerate(lines) if rx.search(l)]
        if hits:
            print("  [%s] %d hit(s)" % (name, len(hits)))
            for i, l in hits[:12]:
                print("     +%d: %s" % (i, l[:200]))

# committed blob byte checks
for path in ["docs/AI_MERGE_POLICY.md", "pipeline/merge_policy.py", "tests/test_merge_policy.py", "tests/test_merge_policy_docs.py", "docs/DEFECT_REGISTER.md"]:
    blob = git("show", "efda93e:" + path)
    crlf = blob.count(b"\r\n")
    cr = blob.count(b"\r")
    lf = blob.count(b"\n")
    bom = blob.startswith(b"\xef\xbb\xbf")
    ends_nl = blob.endswith(b"\n")
    try:
        blob.decode("utf-8")
        utf8 = True
    except UnicodeDecodeError:
        utf8 = False
    trailing = sum(1 for l in blob.split(b"\n") if l.endswith(b" ") or l.endswith(b"\t"))
    print("blob %-36s bytes=%d LF=%d CRLF=%d CR=%d BOM=%s ends_with_newline=%s utf8=%s trailing_ws_lines=%d" % (path, len(blob), lf, crlf, cr, bom, ends_nl, utf8, trailing))
    if path == "docs/DEFECT_REGISTER.md":
        base = git("show", "4b22239:" + path)
        print("   base CRLF=%d LF=%d" % (base.count(b"\r\n"), base.count(b"\n")))
