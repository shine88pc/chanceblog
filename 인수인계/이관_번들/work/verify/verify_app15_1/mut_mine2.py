"""AP14 2차 독립 검증 변이 실행기 — 새 머리(4692990)의 복사본 tree2 의 사본(mut_copy2)에서만 코드를 일부러 틀리게 한다. 작업 폴더는 읽지도 않는다.
사용: python -X utf8 mut_mine2.py <id> [<id> ...]    (V.. = 지난 점검의 생존 변이를 같은 원문으로 다시, X.. = 이번에 새로 설계)
- 시험은 3.12(Qt 없음)로 한 번에 한 프로세스, 시작 전 memfree. TEMP/TMP 도 verify_app15_1/tmp2 안으로 돌린다.
- 각 변이 뒤 파일을 원복하고 tree2 의 같은 파일과 sha256 이 같은지 확인한다. 앵커가 한 번만 나오지 않으면 그 변이만 '앵커 불일치'로 적고 이어 간다.
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
TREE = HERE / "tree2"
COPY = HERE / "mut_copy2"
LOG = HERE / "mut_mine2_log.jsonl"
TMP = HERE / "tmp2"
PY = "C:/ccgui/dev/Scripts/python.exe"
MEMFREE = ["python", "-X", "utf8", "C:/work/ai/audit6/n2/tools/memfree.py", "0.7"]
CR, LF = chr(13).encode(), chr(10).encode()

ERR = "src/chanceblog_desktop/security/errorlog.py"
BND = "src/chanceblog_desktop/security/boundary.py"
ENTRY = "packaging/gui_entry.py"
JOBS = "src/chanceblog_desktop/ui/core/jobs.py"
MINE = ["test_security_errorlog"]
BOTH = ["test_security_errorlog", "test_security_boundary"]
D = {}


def add(mid, what, file, old, new, modules=MINE):
    D[mid] = {"what": what, "file": file, "old": old, "new": new, "modules": modules}


# ---- 지난 점검의 생존 변이(같은 원문) ------------------------------------------------------------------------------------------------------------------
add("V01", "파일 이름 글자표에 한 글자(@) 더 허용", ERR, '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-]{0,63}")', '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-@]{0,63}")')
add("V02", "클래스 이름 글자표에 공백 허용", ERR, '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")', '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_ ]{0,63}")')
add("V03", "클래스 이름 검사를 fullmatch 에서 match 로", ERR, 'return name if isinstance(name, str) and _CLASS.fullmatch(name) else "UnknownError"', 'return name if isinstance(name, str) and _CLASS.match(name) else "UnknownError"')
add("V11", "코드 위치를 가장 안쪽 여섯이 아니라 가장 바깥 여섯으로", ERR, "    return found[-MAX_FRAMES:][::-1]", "    return found[:MAX_FRAMES][::-1]")
add("V12", "코드 위치 수 상수 6 을 10 으로", ERR, "MAX_FRAMES = 6 ", "MAX_FRAMES = 10 ")
add("V13", "잠금 기다림 1초를 1000초로", ERR, "LOCK_WAIT = 1.0 ", "LOCK_WAIT = 1000.0 ")
add("V14", "시각을 UTC 로 바꾸지 않음(시계가 준 시간대 그대로)", ERR, "            moment = moment.astimezone(timezone.utc)\n", "            pass\n")
add("V18", "처리 중인 오류의 추적을 종류 확인 없이 붙임", ERR, "    if current[0] is not None and isinstance(kind, type) and issubclass(current[0], kind):", "    if current[0] is not None:")
add("V22", "Qt 분류 이름을 글자표 검사 없이 그대로 적음", ERR, "if isinstance(category, str) and _FILE.fullmatch(category):", "if isinstance(category, str):")
add("V23", "Qt 치명 줄 번호를 범위 검사 없이 적음", ERR, "places.append(f\"{_short_file(file_name)}:{_line_number(getattr(context, 'line', 0))}\")", "places.append(f\"{_short_file(file_name)}:{getattr(context, 'line', 0)}\")")

# ---- 이번에 새로 설계한 변이(새 시험의 틈 찾기) -----------------------------------------------------------------------------------------------------
add("X01", "파일 글자표에 U+2212(마이너스 기호) 하나만 더 허용 — 전수 범위(U+024F) 밖의 한 글자", ERR, '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-]{0,63}")', '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-\u2212]{0,63}")'.replace(chr(92) + "u2212", chr(0x2212)))
add("X02", "클래스 글자표에 전각 영문 대문자(Ａ-Ｚ) 허용 — 전수 범위 밖의 비슷한 글자", ERR, '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")', '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_' + chr(0xFF21) + "-" + chr(0xFF3A) + ']{0,63}")')
add("X03", "추적을 읽는 단계 상한을 10000 에서 100 으로(깊은 추적은 가장 바깥 쪽만 봄)", ERR, "while trace is not None and steps < 10_000:", "while trace is not None and steps < 100:")
add("X04", "돌려쓰기가 가장 오래된 파일을 먼저 지움(2차 지적 S4 의 옛 동작)", ERR, "        for index in range(len(names) - 2, -1, -1):\n",
    "        oldest = folder / names[-1]\n        if oldest.exists():\n            oldest.unlink()\n        for index in range(len(names) - 2, -1, -1):\n")
add("X05", "돌려쓰기 순서를 뒤집음(현재 파일부터 밀어 .1 을 덮어씀)", ERR, "        for index in range(len(names) - 2, -1, -1):\n", "        for index in range(0, len(names) - 1):\n")
add("X06", "옛 파일 0개 설정에서 현재 파일을 비우지 않음(그냥 돌아감)", ERR, "            (folder / names[0]).unlink(missing_ok=True)\n            return\n", "            return\n")
add("X07", "돌려쓰는 기준에 5바이트 여유(한도를 5바이트까지 넘길 수 있음)", ERR, "if size > 0 and size + len(data) > self._max_bytes:", "if size > 0 and size + len(data) > self._max_bytes + 5:")
add("X08", "속도 제한 구간 경계를 '이상'에서 '초과'로(정확히 60초일 때)", ERR, "now - self._window_start >= self._rate_seconds", "now - self._window_start > self._rate_seconds")
add("X09", "기본 속도 제한 줄 수를 30 대신 100만으로(시험은 값을 직접 넘김)", ERR, "rate=(RATE_COUNT, RATE_SECONDS)", "rate=(10 ** 6, RATE_SECONDS)")
add("X10", "돌려쓰기가 권한 오류를 삼키고 계속 씀(막혀도 한도를 넘김)", ERR, "                os.replace(source, folder / names[index + 1])\n",
    "                try:\n                    os.replace(source, folder / names[index + 1])\n                except PermissionError:\n                    pass\n")
add("X11", "묶음 시작 파일(start_gui)이 경계의 기록을 직접 부름(글자 errorlog 없이) — 문서의 한계가 거짓이 되는데 한계 시험이 잡는가", ENTRY,
    "        say(START_FAILED.format(kind=type(error).__name__), error=True)\n",
    "        from chanceblog_desktop.security import boundary as _b\n        _b._record(\"main\", type(error), error, error.__traceback__)\n        say(START_FAILED.format(kind=type(error).__name__), error=True)\n", ["test_security_errorlog", "test_packaging_entry"])
add("X12", "작업 스레드(Job._run)가 경계의 기록을 직접 부름(글자 errorlog 없이)", JOBS,
    "            self._finish(self.FAILED, \"error\", JobFailure(T[\"job_failed\"], code=type(error).__name__), self.payload)\n",
    "            from ...security import boundary as _b\n            _b._record(\"thread\", type(error), error, error.__traceback__)\n            self._finish(self.FAILED, \"error\", JobFailure(T[\"job_failed\"], code=type(error).__name__), self.payload)\n", ["test_security_errorlog", "test_ui_core"])
add("X14", "추적 줄 번호를 tb_lineno 가 아니라 프레임의 지금 줄(f_lineno)로", ERR, "_line_number(trace.tb_lineno)", "_line_number(trace.tb_frame.f_lineno)")
add("X15", "줄 끝을 LF 가 아니라 CRLF 로", ERR, 'data = (line + "\\n").encode("utf-8")', 'data = (line + "\\r\\n").encode("utf-8")')
add("X16", "GeneratorExit 도 기록(제외 목록에서 뺌)", ERR, "_NOT_RECORDED = (KeyboardInterrupt, SystemExit, GeneratorExit)", "_NOT_RECORDED = (KeyboardInterrupt, SystemExit)")
add("X17", "줄 번호 상한 9,999,999 를 99,999,999 로", ERR, "_MAX_LINE = 9_999_999", "_MAX_LINE = 99_999_999")
add("X18", "잠금 기다림 시간을 무시하고 끝없이 기다림", ERR, "if not self._lock.acquire(timeout=LOCK_WAIT):", "if not self._lock.acquire(timeout=-1):")
add("X19", "클래스 이름을 '클래스일 때만' 읽는 확인을 뺌(함수·모듈 같은 것의 __name__ 도 읽음)", ERR, 'name = getattr(kind, "__name__", None) if isinstance(kind, type) else None', 'name = getattr(kind, "__name__", None)')
add("X20", "기본 한도(max_bytes) 기본값을 4배로(시험은 값을 직접 넘기기도 함)", ERR, "max_bytes=MAX_BYTES, backups=BACKUPS", "max_bytes=MAX_BYTES * 4, backups=BACKUPS")
add("X21", "기본 보관 수(backups)를 2 대신 3 으로(파일 넷)", ERR, "max_bytes=MAX_BYTES, backups=BACKUPS", "max_bytes=MAX_BYTES, backups=BACKUPS + 1")
add("X22", "mask 호출 제거(완성한 줄을 가리지 않고 그대로 씀)", ERR, '        return mask(f"{self._stamp()} {label} {name} " + (" < ".join(places) if places else "-"))',
    '        return f"{self._stamp()} {label} {name} " + (" < ".join(places) if places else "-")')
add("X23", "mask 를 부르지만 결과를 버림(가리지 않은 줄을 씀)", ERR, '        return mask(f"{self._stamp()} {label} {name} " + (" < ".join(places) if places else "-"))',
    '        line = f"{self._stamp()} {label} {name} " + (" < ".join(places) if places else "-")' + chr(10) + '        mask(line)' + chr(10) + '        return line')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fresh_copy():
    if COPY.exists():
        shutil.rmtree(COPY)
    shutil.copytree(TREE, COPY, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))


def apply(rel, old, new):
    path = COPY / rel
    data = path.read_bytes()
    crlf = CR + LF in data
    old_b, new_b = old.encode("utf-8"), new.encode("utf-8")
    if crlf:
        old_b, new_b = old_b.replace(LF, CR + LF), new_b.replace(LF, CR + LF)
    count = data.count(old_b)
    if count != 1:
        raise ValueError(f"{rel}: 옛 글이 {count}번 나온다(정확히 한 번이어야 한다): {old[:70]!r}")
    path.write_bytes(data.replace(old_b, new_b))
    return data


def run_modules(modules, timeout=420):
    subprocess.run(MEMFREE, check=False, capture_output=True)
    started = time.time()
    TMP.mkdir(exist_ok=True)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": os.pathsep.join([str(COPY / "src"), str(COPY / "tests"), str(COPY / "packaging"), str(COPY)]),
           "TEMP": str(TMP), "TMP": str(TMP), "TMPDIR": str(TMP)}
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
    return {"ran": int(ran.group(1)) if ran else 0, "ok": bool(re.search(r"^OK", text, re.M)) and not hung, "hung": hung, "summary": failed.group(1) if failed else "", "reds": [f"{m.split('.')[0]}:{n}" for n, m in names[:6]],
            "n_reds": len(names), "seconds": round(time.time() - started, 1), "tail": text[-300:] if not re.search(r"^OK", text, re.M) and not names else ""}


def run(mid):
    spec = D[mid]
    try:
        original = apply(spec["file"], spec["old"], spec["new"])
    except ValueError as error:
        print(f"{mid} 앵커 불일치 — {error}", flush=True)
        return False
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
