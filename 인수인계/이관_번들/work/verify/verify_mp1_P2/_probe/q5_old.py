import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P2/_probe")
import json
import subprocess
import sys as _s
_s.path.insert(0, 'C:/work/ai/verify_mp1_P')
_s.dont_write_bytecode = True
from pipeline import merge_policy as mp
rec = lambda *a, **k: None
summary = lambda: None

REPO = "C:/work/ai/improve_wt_mergepol1"
CLEAN = {k: False for k in mp.DECLARED_REQUIRED}


def git(*args):
    p = subprocess.run(["git", "-c", "core.quotepath=false", "-C", REPO] + list(args), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace"))
    return p.stdout


hashes = git("log", "-40", "--format=%H", "4b22239").decode().split()
assert len(hashes) == 40, len(hashes)


def paths_of(sha):
    raw = git("diff-tree", "-r", "-M", "--no-commit-id", "--name-status", "-z", sha).decode("utf-8", "replace").split("\0")
    raw = [x for x in raw if x != ""]
    paths, i = [], 0
    while i < len(raw):
        status = raw[i]
        if status.startswith(("R", "C")):
            paths += [raw[i + 1], raw[i + 2]]
            i += 3
        else:
            paths.append(raw[i + 1])
            i += 2
    return paths


def text_of(sha):
    out = git("show", "--format=", "-U0", "-M", "--no-color", sha).decode("utf-8", "replace").replace("\r\n", "\n").split("\n")
    files, cur_old, cur_new, cur = {}, None, None, None
    for line in out:
        if line.startswith("--- "):
            name = line[4:].split("\t")[0]
            cur_old = None if name == "/dev/null" else name[2:] if name.startswith("a/") else name
            continue
        if line.startswith("+++ "):
            name = line[4:].split("\t")[0]
            cur_new = None if name == "/dev/null" else name[2:] if name.startswith("b/") else name
            cur = cur_new or cur_old
            files.setdefault(cur, [])
            continue
        if line.startswith("diff --git"):
            cur = None
            continue
        if cur is not None and line.startswith("+"):
            files[cur].append(line)
    return {k: "\n".join(v) for k, v in files.items() if k is not None}


rows = []
for sha in hashes:
    subj = git("log", "-1", "--format=%s", sha).decode("utf-8", "replace").strip()
    paths = paths_of(sha)
    texts = text_of(sha)
    # keys must be inside paths (renames: new path is in paths)
    stray = [k for k in texts if k not in paths]
    r = mp.classify_change("blog", paths, texts, CLEAN)
    rows.append({"sha": sha[:7], "subject": subj, "n": len(paths), "tier": r.tier, "cats": list(r.categories), "extra": list(r.extra_flags), "stray_keys": stray,
                 "reasons": list(r.reasons)[:6], "paths": paths})
json.dump(rows, open("C:/work/ai/verify_mp1_P2/_probe/q5_rows_old.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
n_ok = sum(1 for r in rows if r["tier"] == "ai_ok")
print("commits: %d  ai_ok: %d  operator_only: %d" % (len(rows), n_ok, len(rows) - n_ok))
for r in rows:
    print("%s %-13s files=%-3d %s | %s%s" % (r["sha"], r["tier"], r["n"], (",".join(r["cats"] + r["extra"]))[:70], r["subject"][:46], "  STRAYKEYS=%s" % r["stray_keys"] if r["stray_keys"] else ""))
mnum = lambda s: s.split("]")[0].lstrip("[") if s.startswith("[M") else s[:6]
ok_ids = sorted(mnum(r["subject"]) for r in rows if r["tier"] == "ai_ok")
print("ai_ok ids:", ok_ids)
rec("C1", "ai_ok count is 5", 5, n_ok)
rec("C2", "ai_ok set == {M057, M063, M069, M070, M071}", ["M057", "M063", "M069", "M070", "M071"], ok_ids)
m48 = [r for r in rows if r["subject"].startswith("[M048]")][0]
rec("C3", "M048 is operator_only (quality_gate.py)", "operator_only", m48["tier"], note=",".join(m48["cats"] + m48["extra"]))
summary()
