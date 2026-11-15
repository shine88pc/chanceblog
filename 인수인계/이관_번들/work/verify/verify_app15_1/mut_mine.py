"""AP14 독립 검증 변이 실행기 — 복사본(tree)의 사본(mut_copy)에서만 코드를 일부러 틀리게 한다. 원본(작업 폴더)은 읽지도 않는다.
사용: python -X utf8 mut_mine.py <id> [<id> ...]    (L.. = 구현자 정의 재실행, V.. = 내가 새로 설계한 것)
- 시험은 3.12(Qt 없음)로 한 번에 한 프로세스, 시작 전 memfree.
- 각 변이 뒤 파일을 원복하고 tree 의 같은 파일과 sha256 이 같은지 확인한다.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path("C:/work/ai/verify_app15_1")
TREE = HERE / "tree"
COPY = HERE / "mut_copy"
LOG = HERE / "mut_mine_log.jsonl"
PY = "C:/ccgui/dev/Scripts/python.exe"
MEMFREE = ["python", "-X", "utf8", "C:/work/ai/audit6/n2/tools/memfree.py", "0.7"]
CR, LF = chr(13).encode(), chr(10).encode()

sys.path.insert(0, "C:/work/ai/audit6/improve/app15")
import mut_ap14  # noqa: E402  (구현자 정의 — 읽기만)

ERR = "src/chanceblog_desktop/security/errorlog.py"
BND = "src/chanceblog_desktop/security/boundary.py"
MINE = ["test_security_errorlog"]
BOTH = ["test_security_errorlog", "test_security_boundary"]
V = {}


def addv(mid, what, file, old, new, modules=MINE):
    V[mid] = {"what": what, "file": file, "old": old, "new": new, "modules": modules, "regex": False}


addv("V01", "파일 이름 글자표에 한 글자(@) 더 허용", ERR, '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-]{0,63}")', '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-@]{0,63}")')
addv("V02", "클래스 이름 글자표에 공백 허용", ERR, '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")', '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_ ]{0,63}")')
addv("V03", "클래스 이름 검사를 fullmatch 에서 match 로(앞부분만 맞으면 통과)", ERR, 'return name if isinstance(name, str) and _CLASS.fullmatch(name) else "UnknownError"', 'return name if isinstance(name, str) and _CLASS.match(name) else "UnknownError"')
addv("V04", "파일 이름 검사를 fullmatch 에서 match 로", ERR, 'return last if _FILE.fullmatch(last) else "?"', 'return last if _FILE.match(last) else "?"')
addv("V05", "한도 256 KB 를 512 KB 로 늘림", ERR, "MAX_BYTES = 256 * 1024 ", "MAX_BYTES = 512 * 1024 ")
addv("V06", "속도 제한 값을 30 에서 3000 으로", ERR, "RATE_COUNT = 30 ", "RATE_COUNT = 3000 ")
addv("V07", "KeyboardInterrupt 도 기록(제외 목록에서 뺌)", ERR, "_NOT_RECORDED = (KeyboardInterrupt, SystemExit, GeneratorExit)", "_NOT_RECORDED = (SystemExit, GeneratorExit)")
addv("V08", "돌려쓰기가 막혀도 줄을 버리지 않고 한도를 넘겨 씀", ERR, "        if size > 0 and size + len(data) > self._max_bytes:\n            self._rotate(folder)\n",
     "        if size > 0 and size + len(data) > self._max_bytes:\n            try:\n                self._rotate(folder)\n            except OSError:\n                pass\n")
addv("V09", "켜는 순간(생성자)에 폴더 해석 함수를 부름", ERR, "        self._folder = None\n", "        self._folder = Path(self._resolve()) / FOLDER_NAME\n")
addv("V10", "스레드 훅이 기록으로 이어지지 않음(훅 하나 연결 끊기)", BND, '    _record("thread", args.exc_type, args.exc_value, getattr(args, "exc_traceback", None))\n', "", BOTH)
addv("V11", "코드 위치를 가장 안쪽 여섯이 아니라 가장 바깥 여섯으로", ERR, "    return found[-MAX_FRAMES:][::-1]", "    return found[:MAX_FRAMES][::-1]")
addv("V12", "코드 위치 수 상수 6 을 10 으로", ERR, "MAX_FRAMES = 6 ", "MAX_FRAMES = 10 ")
addv("V13", "잠금 기다림 1초를 1000초로", ERR, "LOCK_WAIT = 1.0 ", "LOCK_WAIT = 1000.0 ")
addv("V14", "시각을 UTC 로 바꾸지 않음(시계가 준 시간대 그대로)", ERR, "            moment = moment.astimezone(timezone.utc)\n", "            pass\n")
addv("V17", "가림 결과를 버리고 가리지 않은 줄을 씀", ERR, '        return mask(f"{self._stamp()} {label} {name} " + (" < ".join(places) if places else "-"))',
     '        line = f"{self._stamp()} {label} {name} " + (" < ".join(places) if places else "-")\n        mask(line)\n        return line')
addv("V18", "처리 중인 오류의 추적을 종류 확인 없이 붙임", ERR, "    if current[0] is not None and isinstance(kind, type) and issubclass(current[0], kind):", "    if current[0] is not None:")
addv("V19", "Qt 치명 기록이 C++ 파일의 폴더를 떼지 않음", ERR, """places.append(f"{_short_file(file_name)}:{_line_number(getattr(context, 'line', 0))}")""", """places.append(f"{file_name}:{_line_number(getattr(context, 'line', 0))}")""")
addv("V22", "Qt 분류 이름을 글자표 검사 없이 그대로 적음", ERR, "if isinstance(category, str) and _FILE.fullmatch(category):", "if isinstance(category, str):")
addv("V23", "Qt 치명 줄 번호를 범위 검사 없이 적음", ERR, "places.append(f\"{_short_file(file_name)}:{_line_number(getattr(context, 'line', 0))}\")", "places.append(f\"{_short_file(file_name)}:{getattr(context, 'line', 0)}\")")
addv("V24", "한 줄 만들기에서 시각 글을 가림 없이 그대로(mask 가 줄 뒤쪽만 거침)", ERR, '        return mask(f"{self._stamp()} {label} {name} " + (" < ".join(places) if places else "-"))',
     '        return self._stamp() + " " + mask(f"{label} {name} " + (" < ".join(places) if places else "-"))')


def definition(mid):
    if mid in V:
        return V[mid]
    spec = mut_ap14.MUTATIONS[mid]
    return {"what": spec["what"], "file": spec["file"], "old": spec["old"], "new": spec["new"], "modules": spec["modules"], "regex": spec.get("regex", False)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fresh_copy():
    if COPY.exists():
        shutil.rmtree(COPY)
    shutil.copytree(TREE, COPY, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))


def apply(rel, old, new, regex=False):
    path = COPY / rel
    data = path.read_bytes()
    crlf = CR + LF in data
    if regex:
        pattern = re.compile(old.encode("utf-8"), re.S)
        found = pattern.findall(data)
        if len(found) != 1:
            raise SystemExit(f"{rel}: 정규식이 {len(found)}번 맞는다: {old[:60]!r}")
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


def run_modules(modules, timeout=420):
    subprocess.run(MEMFREE, check=False, capture_output=True)
    started = time.time()
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": os.pathsep.join([str(COPY / "src"), str(COPY / "tests"), str(COPY)])}
    process = subprocess.Popen([PY, "-B", "-X", "utf8", "-m", "unittest", *modules], cwd=COPY / "tests", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env)
    hung = False
    try:
        text, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        text, _ = process.communicate()
        hung = True
    ran = re.search(r"Ran (\d+) tests?", text)
    failed = re.search(r"FAILED \((.*?)\)", text)
    names = re.findall(r"^(?:FAIL|ERROR): (\S+) \((\S+)\)", text, re.M)
    return {"ran": int(ran.group(1)) if ran else 0, "ok": bool(re.search(r"^OK", text, re.M)) and not hung, "hung": hung, "summary": failed.group(1) if failed else "", "reds": [f"{n}" for n, _ in names[:5]],
            "n_reds": len(names), "seconds": round(time.time() - started, 1), "tail": text[-400:] if not re.search(r"^OK", text, re.M) and not names else ""}


def run(mid):
    spec = definition(mid)
    original = apply(spec["file"], spec["old"], spec["new"], spec["regex"])
    try:
        result = run_modules(spec["modules"])
    finally:
        (COPY / spec["file"]).write_bytes(original)
    restored = sha(COPY / spec["file"]) == sha(TREE / spec["file"])
    caught = (not result["ok"]) and not result["hung"]
    line = {"id": mid, "what": spec["what"], "file": spec["file"], "modules": spec["modules"], "caught": caught, "restored_same_sha256": restored, **result}
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    verdict = "멈춤!!" if result["hung"] else ("잡힘(빨강)" if caught else "생존(초록)")
    print(f"{mid} {verdict} ran={result['ran']} reds={result['n_reds']} {result['reds'][:3]} sha256복원={'같음' if restored else '다름!!'} {result['seconds']}s — {spec['what']}", flush=True)
    if result["tail"]:
        print("   TAIL:", result["tail"].replace("\n", " | ")[:300], flush=True)
    return caught and restored


if __name__ == "__main__":
    ids = sys.argv[1:]
    fresh_copy()
    for mutation_id in ids:
        run(mutation_id)
    print("DONE", len(ids))
