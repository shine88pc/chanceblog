"""APP15 변이 시험 도구 — 작업 폴더의 사본에서 코드·문서를 일부러 틀리게 하고 지정한 시험 모듈이 빨개지는지 본다(SINGLEWIN 의 `mut_run.py` 와 같은 방식).

사용: python -X utf8 mut_run.py <정의 파일 이름(확장자 없이)> <변이 id> [<변이 id> ...]   (`all` 이면 그 파일의 전부, `list` 면 목록만)
동작: ① 작업 폴더(.git·__pycache__ 제외)를 사본 폴더 `mut_copy` 로 새로 복사 ② 사본의 한 파일에서 옛 글이 정확히 한 번 나오는 곳을 바꾼다(CRLF 파일은 줄바꿈을 맞춘다)
③ 시험 모듈을 하나씩(한 번에 한 프로세스) 돌려 통과·실패 수를 모은다 — 파이썬은 변이 정의의 `py`(`qt`=3.12 Qt 있음·offscreen, `dev`=3.12 Qt 없음) ④ 파일을 원복하고 sha256 이 작업 폴더의 같은 파일과 같은지 확인한다.
결과는 mut_log.jsonl 에 한 줄씩 남긴다. 작업 폴더 파일은 읽기만 한다.
"""
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORK = Path("C:/work/ai/improve_wt_app15")
HERE = Path("C:/work/ai/audit6/improve/app15")
COPY = HERE / "mut_copy"
LOG = HERE / "mut_log.jsonl"
PYTHONS = {"dev": "C:/ccgui/dev/Scripts/python.exe", "qt": "C:/ccgui/v/Scripts/python.exe", "py310": "C:/ccgui/v310/Scripts/python.exe"}
MEMFREE = ["python", "-X", "utf8", "C:/work/ai/audit6/n2/tools/memfree.py", "0.8"]
CR, LF = chr(13).encode(), chr(10).encode()

sys.path.insert(0, str(HERE))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fresh_copy():
    if COPY.exists():
        shutil.rmtree(COPY)
    shutil.copytree(WORK, COPY, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))


def apply(rel, old, new, regex=False):
    """사본의 파일을 바꾸고 원래 바이트를 돌려준다."""
    path = COPY / rel
    data = path.read_bytes()
    crlf = CR + LF in data
    if regex:
        pattern = re.compile(old.encode("utf-8"), re.S)
        found = pattern.findall(data)
        if len(found) != 1:
            raise SystemExit(f"{rel}: 정규식이 {len(found)}번 맞는다(정확히 한 번이어야 한다): {old[:70]!r}")
        path.write_bytes(pattern.sub(new.encode("utf-8"), data, count=1))
        return data
    old_b, new_b = old.encode("utf-8"), new.encode("utf-8")
    if crlf:
        old_b, new_b = old_b.replace(LF, CR + LF), new_b.replace(LF, CR + LF)
    count = data.count(old_b)
    if count != 1:
        raise SystemExit(f"{rel}: 옛 글이 {count}번 나온다(정확히 한 번이어야 한다): {old[:70]!r}")
    path.write_bytes(data.replace(old_b, new_b))
    return data


def run_module(module, python, timeout=420):
    """시험 모듈 하나를 한 프로세스로 돌린다. 시간이 넘으면 내가 띄운 프로세스 트리만 PID 로 끝내고 `hung` 으로 적는다(잡힌 것으로 세지 않는다)."""
    subprocess.run(MEMFREE, check=False, capture_output=True)
    started = time.time()
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "QT_QPA_PLATFORM": "offscreen"}
    process = subprocess.Popen([PYTHONS[python], "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-p", f"{module}.py"], cwd=COPY, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace", env=env)
    hung = False
    try:
        text, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        text, _ = process.communicate()
        hung = True
    ran = re.search(r"Ran (\d+) tests?", text)
    failed = re.search(r"FAILED \((.*?)\)", text)
    names = re.findall(r"^(?:FAIL|ERROR): (\S+)", text, re.M)
    return {"module": module, "ran": int(ran.group(1)) if ran else 0, "ok": bool(re.search(r"^OK", text, re.M)) and not hung, "hung": hung, "summary": failed.group(1) if failed else "", "reds": names[:6],
            "seconds": round(time.time() - started, 1)}


def run(mutations, mutation_id):
    spec = mutations[mutation_id]
    original = apply(spec["file"], spec["old"], spec["new"], spec["regex"])
    try:
        results = [run_module(module, spec["py"]) for module in spec["modules"]]
    finally:
        (COPY / spec["file"]).write_bytes(original)
    restored = sha(COPY / spec["file"]) == sha(WORK / spec["file"])
    caught = any(not item["ok"] and not item["hung"] for item in results)
    hung = any(item["hung"] for item in results)
    line = {"id": mutation_id, "item": spec["item"], "what": spec["what"], "file": spec["file"], "caught": caught, "hung": hung, "restored_same_sha256": restored, "results": results}
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    reds = sum(1 for item in results if not item["ok"])
    verdict = "멈춤!!" if hung else ("잡힘" if caught else "놓침!!")
    print(f"{mutation_id} [{spec['item']}] {verdict} 빨간 모듈 {reds}/{len(results)} 원복 sha256 {'같음' if restored else '다름!!'} — {spec['what']}", flush=True)
    for item in results:
        if not item["ok"]:
            print("    ", item["module"], item["summary"], item["reds"][:3], flush=True)
    return caught and restored and not hung


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    definitions = importlib.import_module(sys.argv[1])
    mutations = definitions.MUTATIONS
    if sys.argv[2] == "list":
        for key, spec in mutations.items():
            print(key, spec["item"], spec["file"], "—", spec["what"])
        raise SystemExit(0)
    ids = [item for item in sys.argv[2:] if item != "--keep"]
    if ids == ["all"]:
        ids = list(mutations)
    if not COPY.exists() or "--keep" not in sys.argv:
        fresh_copy()
    ok = all([run(mutations, mutation_id) for mutation_id in ids])
    raise SystemExit(0 if ok else 1)
