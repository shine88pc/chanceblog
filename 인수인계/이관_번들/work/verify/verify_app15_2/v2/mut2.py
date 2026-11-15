"""Independent mutation runner v2 (verifier's own) for the new head 4692990 (final2). Mutates a COPY (v2/mut_copy2), runs given test modules, restores, compares sha256 with the pristine final2.
usage: python mut2.py <defs.py path> <py: dev|qt|py310> <id> [<id> ...]      ('list' prints definitions, 'all' runs every id)
Definitions: MUTATIONS = {id: {what, file, old, new, modules, regex?}} or {id: {what, edits:[{file,old,new}...], modules}} for multi-file edits.
Env MUT_MODULES="a,b" overrides every definition's module list. Never touches the real worktree. One process at a time; memfree before each run.
"""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
H = Path("C:/work/ai/verify_app15_2")
PRISTINE = H / "final2"
COPY = H / "v2" / f"mut_copy2_{os.getpid()}"       # one private copy per runner process (two runners must never share a folder)
LOG = H / "v2" / "mut_log2.jsonl"
PYTHONS = {"dev": "C:/ccgui/dev/Scripts/python.exe", "qt": "C:/ccgui/v/Scripts/python.exe", "py310": "C:/ccgui/v310/Scripts/python.exe"}
NEED = {"dev": "0.7", "qt": "1.5", "py310": "0.7"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_defs(path):
    spec = importlib.util.spec_from_file_location("defs_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MUTATIONS


def fresh_copy():
    if COPY.exists():
        def force(func, p, _exc):
            os.chmod(p, 0o666)
            func(p)
        shutil.rmtree(COPY, onexc=force)
    shutil.copytree(PRISTINE, COPY, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def apply(rel, old, new, regex=False):
    path = COPY / rel
    data = path.read_bytes()
    if regex:
        pattern = re.compile(old.encode("utf-8"), re.S)
        found = pattern.findall(data)
        if len(found) != 1:
            raise SystemExit(f"{rel}: regex matches {len(found)} times (need exactly 1): {old[:70]!r}")
        path.write_bytes(pattern.sub(new.encode("utf-8"), data, count=1))
        return data
    old_b, new_b = old.encode("utf-8"), new.encode("utf-8")
    count = data.count(old_b)
    if count != 1:
        raise SystemExit(f"{rel}: old text appears {count} times (need exactly 1): {old[:70]!r}")
    path.write_bytes(data.replace(old_b, new_b))
    return data


def edits_of(spec):
    return spec["edits"] if "edits" in spec else [{"file": spec["file"], "old": spec["old"], "new": spec["new"], "regex": spec.get("regex", False)}]


def run_modules(modules, python_key, timeout=900):
    subprocess.run(["python", "-X", "utf8", "C:/work/ai/audit6/n2/tools/memfree.py", NEED[python_key]], capture_output=True)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": f"{COPY}\\src;{COPY}\\tests;{COPY}"}
    started = time.time()
    proc = subprocess.Popen([PYTHONS[python_key], "-B", "-X", "utf8", "-m", "unittest", *modules], cwd=COPY / "tests", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", env=env)
    hung = False
    try:
        text, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        text, _ = proc.communicate()
        hung = True
    ran = re.search(r"Ran (\d+) tests?", text)
    summary = re.findall(r"^(OK.*|FAILED.*)$", text, re.M)
    reds = re.findall(r"^(?:FAIL|ERROR): (\S+)", text, re.M)
    return {"ran": int(ran.group(1)) if ran else 0, "ok": bool(re.search(r"^OK", text, re.M)) and not hung, "hung": hung, "summary": summary[-1] if summary else "", "reds": reds[:8], "sec": round(time.time() - started, 1)}


def main():
    defs_path, python_key, ids = sys.argv[1], sys.argv[2], sys.argv[3:]
    mutations = load_defs(defs_path)
    if ids == ["list"]:
        for key, spec in mutations.items():
            print(key, "-", spec["what"])
        return 0
    if ids == ["all"]:
        ids = list(mutations)
    override = [m for m in os.environ.get("MUT_MODULES", "").split(",") if m]
    fresh_copy()
    exit_code = 0
    import atexit

    def cleanup():
        def force(func, p, _exc):
            os.chmod(p, 0o666)
            func(p)
        shutil.rmtree(COPY, onexc=force, ignore_errors=True)
    atexit.register(cleanup)
    for mutation_id in ids:
        spec = mutations[mutation_id]
        edits = edits_of(spec)
        originals = {}
        try:
            for edit in edits:
                before = apply(edit["file"], edit["old"], edit["new"], edit.get("regex", False))
                originals.setdefault(edit["file"], before)
            modules = override or spec["modules"]
            result = run_modules(modules, python_key)
        finally:
            for rel, data in originals.items():
                (COPY / rel).write_bytes(data)
        restored = all(sha(COPY / rel) == sha(PRISTINE / rel) for rel in originals)
        caught = (not result["ok"]) and not result["hung"]
        line = {"id": mutation_id, "py": python_key, "modules": modules, "caught": caught, "hung": result["hung"], "restored": restored, "what": spec["what"], "ts": time.strftime("%H:%M:%S"), **result}
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        verdict = "HUNG" if result["hung"] else ("RED" if caught else "GREEN")
        print(f"{mutation_id} [{python_key}] {verdict} ran={result['ran']} {result['summary']} restored={'same' if restored else 'DIFFERENT'} reds={result['reds'][:3]} -- {spec['what']}", flush=True)
        if not restored:
            exit_code = 2
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
