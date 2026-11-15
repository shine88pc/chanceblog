"""최근 main 커밋 40개의 경로·바뀐 줄(추가+지움)을 classify_change 에 넣어 전후(WIP 5 대 지금)를 견주는 표를 만든다. 읽기 전용(git 읽기만), 파일은 임시 폴더에만 쓴다."""
import importlib.util
import os
import subprocess
import sys

REPO = "C:/work/ai/improve_wt_mergepol1"
SCRATCH = "<사용자폴더>/AppData/Local/Temp/claude/847eb01b1a8ad9f8/921b6032-bba9-4b52-8c2d-b24e5509c445/scratchpad/"
BASE = sys.argv[1] if len(sys.argv) > 1 else "4b22239"
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 40


def git(*args):
    out = subprocess.run(["git", "-C", REPO] + list(args), capture_output=True, check=True)
    return out.stdout.decode("utf-8", "replace")


def load(name, source):
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


old_source = SCRATCH + "merge_policy_wip5.py"
open(old_source, "w", encoding="utf-8", newline="").write(git("show", (sys.argv[3] if len(sys.argv) > 3 else "50a3450") + ":pipeline/merge_policy.py"))
old = load("mp_old", old_source)
new = load("mp_new", REPO + "/pipeline/merge_policy.py")


def commit_data(commit):
    status = git("diff-tree", "--no-commit-id", "-r", "-M", "--name-status", commit)
    paths = []
    for line in status.splitlines():
        parts = line.split("\t")
        paths += parts[1:]
    patch = git("diff-tree", "-p", "-M", "--no-commit-id", "--no-color", commit)
    texts, current = {}, None
    for line in patch.split("\n"):
        if line.startswith("diff --git "):
            current = None
        elif line.startswith("+++ "):
            name = line[4:].strip()
            current = name[2:] if name.startswith("b/") else None
        elif line.startswith("--- "):
            name = line[4:].strip()
            if current is None and name.startswith("a/"):
                current = "OLD:" + name[2:]
        elif current is not None and (line.startswith("+") or line.startswith("-")):
            key = current
            if key.startswith("OLD:"):
                key = key[4:]
            texts.setdefault(key, []).append(line[1:])
    return paths, {key: "\n".join(value) for key, value in texts.items()}


def summarize(result):
    return result.tier + ("" if result.tier == "ai_ok" else " " + "+".join(result.categories + result.extra_flags))


rows = []
declared = {code: False for code in old.DECLARED_REQUIRED}
for commit in git("rev-list", "--max-count=" + str(COUNT), BASE).split():
    subject = git("log", "-1", "--format=%s", commit).strip()
    paths, texts = commit_data(commit)
    if not paths:
        continue
    keys_ok = {path: texts.get(path, "") for path in set(paths)}                                   # 변경 파일마다 키(글이 없으면 빈 글)
    before = old.classify_change("blog", paths, keys_ok, declared)
    after = new.classify_change("blog", paths, keys_ok, declared)
    rows.append((commit[:7], subject[:70], len(paths), summarize(before), summarize(after)))
ok_before = sum(1 for row in rows if row[3] == "ai_ok")
ok_after = sum(1 for row in rows if row[4] == "ai_ok")
for row in rows:
    print("%s | %-70s | %3d | %s | %s" % row)
print("총 %d개: 전 ai_ok %d · 후 ai_ok %d" % (len(rows), ok_before, ok_after))
