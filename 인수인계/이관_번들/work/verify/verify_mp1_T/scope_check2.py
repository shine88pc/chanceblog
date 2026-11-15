"""Second scope check: unusual unicode, other tilde-like chars, web-address-like text in docs, existing-repo precedent for names."""
import re
import subprocess
import unicodedata

REPO = "C:/work/ai/improve_wt_mergepol1"
FILES = ["docs/AI_MERGE_POLICY.md", "pipeline/merge_policy.py", "tests/test_merge_policy.py", "tests/test_merge_policy_docs.py"]


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True).stdout


for path in FILES + ["docs/DEFECT_REGISTER.md"]:
    blob = git("show", "HEAD:" + path).decode("utf-8")
    if path == "docs/DEFECT_REGISTER.md":
        base = git("show", "origin/main:" + path).decode("utf-8").split("\n")
        new = blob.split("\n")
        blob = "\n".join(l for l in new if l not in set(base))
    odd = {}
    for i, line in enumerate(blob.split("\n"), 1):
        for ch in line:
            cat = unicodedata.category(ch)
            if cat in ("Cf", "Cc", "Co", "Cs", "Cn") or (cat.startswith("Z") and ch != " ") or ch in "\u301c\uff5e\u223c\u02dc\u2053":
                odd.setdefault((hex(ord(ch)), unicodedata.name(ch, "?"), cat), []).append(i)
    print("==", path, "odd chars:", {k: v[:5] for k, v in odd.items()} or "none")

# doc: web-address-like text
doc = git("show", "HEAD:docs/AI_MERGE_POLICY.md").decode("utf-8").split("\n")
rx = re.compile(r"(https?:|www\.|\b[a-z0-9-]+\.(com|org|net|io|kr|dev|app)\b)", re.I)
for i, line in enumerate(doc, 1):
    if rx.search(line):
        print("doc web-like @%d: %s" % (i, line[:160]))
print("doc web-like scan done")

# precedent for names
for needle in ("shine88pc", "chanceblog_desktop"):
    out = subprocess.run(["git", "-C", REPO, "grep", "-l", needle, "origin/main", "--", "docs", "tests", "pipeline", "AGENTS.md", "README.md"], capture_output=True).stdout.decode("utf-8", "replace")
    print("precedent for", needle, "in origin/main:", len(out.splitlines()), "files; sample:", out.splitlines()[:5])
