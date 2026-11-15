"""AP14(작은 로그 파일) 2차 지시 변이 정의 — mut_run.py 가 읽는다.
V.. = 검증자 1 의 변이 원문(C:/work/ai/verify_app15_1/mut_mine.py 의 V01–V24, 읽기만 하고 같은 글을 여기 옮겼다 — 검증자 생존 V01·V02·V03·V11·V12·V13·V14·V18·V22·V23 이 이제 빨개져야 한다)
N.. = 새 규칙(식별자 글자표 전수·안쪽 여섯 위치·돌려쓰기에서 지우지 않음·한계 문서)마다 내가 더한 변이(규칙마다 둘 이상).
각 항목: id → {item, what, file, old, new(글 치환), modules, py, regex}. 기존 L01–L24 는 mut_ap14.py 에 그대로 있다."""

SEC = "src/chanceblog_desktop/security/"
ERR = SEC + "errorlog.py"
BND = SEC + "boundary.py"
MINE = ["test_security_errorlog"]
BOTH = ["test_security_errorlog", "test_security_boundary"]

MUTATIONS = {}


def add(mid, what, file, old, new, modules=MINE, py="dev", regex=False):
    MUTATIONS[mid] = {"item": "AP14", "what": what, "file": file, "old": old, "new": new, "modules": modules, "regex": regex, "py": py}


# ---- 검증자 1 의 변이 원문(V) -------------------------------------------------------------------------------------------------------------------
add("V01", "파일 이름 글자표에 한 글자(@) 더 허용", ERR, '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-]{0,63}")', '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-@]{0,63}")')
add("V02", "클래스 이름 글자표에 공백 허용", ERR, '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")', '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_ ]{0,63}")')
add("V03", "클래스 이름 검사를 fullmatch 에서 match 로(앞부분만 맞으면 통과)", ERR, 'return name if isinstance(name, str) and _CLASS.fullmatch(name) else "UnknownError"', 'return name if isinstance(name, str) and _CLASS.match(name) else "UnknownError"')
add("V04", "파일 이름 검사를 fullmatch 에서 match 로", ERR, 'return last if _FILE.fullmatch(last) else "?"', 'return last if _FILE.match(last) else "?"')
add("V05", "한도 256 KB 를 512 KB 로 늘림", ERR, "MAX_BYTES = 256 * 1024 ", "MAX_BYTES = 512 * 1024 ")
add("V06", "속도 제한 값을 30 에서 3000 으로", ERR, "RATE_COUNT = 30 ", "RATE_COUNT = 3000 ")
add("V07", "KeyboardInterrupt 도 기록(제외 목록에서 뺌)", ERR, "_NOT_RECORDED = (KeyboardInterrupt, SystemExit, GeneratorExit)", "_NOT_RECORDED = (SystemExit, GeneratorExit)")
add("V08", "돌려쓰기가 막혀도 줄을 버리지 않고 한도를 넘겨 씀", ERR, "        if size > 0 and size + len(data) > self._max_bytes:\n            self._rotate(folder)\n",
    "        if size > 0 and size + len(data) > self._max_bytes:\n            try:\n                self._rotate(folder)\n            except OSError:\n                pass\n")
add("V09", "켜는 순간(생성자)에 폴더 해석 함수를 부름", ERR, "        self._folder = None\n", "        self._folder = Path(self._resolve()) / FOLDER_NAME\n")
add("V10", "스레드 훅이 기록으로 이어지지 않음(훅 하나 연결 끊기)", BND, '    _record("thread", args.exc_type, args.exc_value, getattr(args, "exc_traceback", None))\n', "", BOTH)
add("V11", "코드 위치를 가장 안쪽 여섯이 아니라 가장 바깥 여섯으로", ERR, "    return found[-MAX_FRAMES:][::-1]", "    return found[:MAX_FRAMES][::-1]")
add("V12", "코드 위치 수 상수 6 을 10 으로", ERR, "MAX_FRAMES = 6 ", "MAX_FRAMES = 10 ")
add("V13", "잠금 기다림 1초를 1000초로", ERR, "LOCK_WAIT = 1.0 ", "LOCK_WAIT = 1000.0 ")
add("V14", "시각을 UTC 로 바꾸지 않음(시계가 준 시간대 그대로)", ERR, "            moment = moment.astimezone(timezone.utc)\n", "            pass\n")
add("V17", "가림 결과를 버리고 가리지 않은 줄을 씀", ERR, '        return mask(f"{self._stamp()} {label} {name} " + (" < ".join(places) if places else "-"))',
    '        line = f"{self._stamp()} {label} {name} " + (" < ".join(places) if places else "-")\n        mask(line)\n        return line')
add("V18", "처리 중인 오류의 추적을 종류 확인 없이 붙임", ERR, "    if current[0] is not None and isinstance(kind, type) and issubclass(current[0], kind):", "    if current[0] is not None:")
add("V19", "Qt 치명 기록이 C++ 파일의 폴더를 떼지 않음", ERR, """places.append(f"{_short_file(file_name)}:{_line_number(getattr(context, 'line', 0))}")""", """places.append(f"{file_name}:{_line_number(getattr(context, 'line', 0))}")""")
add("V22", "Qt 분류 이름을 글자표 검사 없이 그대로 적음", ERR, "if isinstance(category, str) and _FILE.fullmatch(category):", "if isinstance(category, str):")
add("V23", "Qt 치명 줄 번호를 범위 검사 없이 적음", ERR, "places.append(f\"{_short_file(file_name)}:{_line_number(getattr(context, 'line', 0))}\")", "places.append(f\"{_short_file(file_name)}:{getattr(context, 'line', 0)}\")")
add("V24", "한 줄 만들기에서 시각 글을 가림 없이 그대로(mask 가 줄 뒤쪽만 거침)", ERR, '        return mask(f"{self._stamp()} {label} {name} " + (" < ".join(places) if places else "-"))',
    '        return self._stamp() + " " + mask(f"{label} {name} " + (" < ".join(places) if places else "-"))')

# ---- 새 규칙마다 내 변이(N) ---------------------------------------------------------------------------------------------------------------------
# S1 식별자 글자표 전수
add("N01", "클래스 이름의 첫 글자에 숫자를 허용", ERR, '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")', '_CLASS = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_]{0,63}")')
add("N02", "파일 이름의 첫 글자에 점을 허용(.hidden)", ERR, '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-]{0,63}")', '_FILE = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.\\-]{0,63}")')
add("N03", "폴더 구분자로 역슬래시를 못 가름(윈도 경로의 앞부분이 남음)", ERR, '_SEPARATORS = re.compile(r"[\\\\/]")', '_SEPARATORS = re.compile(r"[/]")')
add("N04", "파일 이름 길이 한도 64 → 128", ERR, '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-]{0,63}")', '_FILE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\\-]{0,127}")')
add("N05", "클래스 이름 길이 한도 64 → 128", ERR, '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")', '_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")')
add("N06", "줄 번호 상한 9,999,999 → 99,999,999", ERR, "_MAX_LINE = 9_999_999", "_MAX_LINE = 99_999_999")
add("N07", "줄 번호에 참/거짓 값을 허용(True 가 1 로 적힘)", ERR, "return number if isinstance(number, int) and not isinstance(number, bool) and 0 <= number <= _MAX_LINE else 0", "return number if isinstance(number, int) and 0 <= number <= _MAX_LINE else 0")
add("N08", "줄 번호에 -1 을 허용", ERR, "0 <= number <= _MAX_LINE else 0", "-1 <= number <= _MAX_LINE else 0")
add("N09", "Qt 분류 이름 글자표가 점을 못 받음(qt.qpa.plugin 이 사라짐)", ERR, "if isinstance(category, str) and _FILE.fullmatch(category):", "if isinstance(category, str) and re.fullmatch(r'[A-Za-z0-9_]{1,64}', category):")
# S2 가장 안쪽 여섯 위치
add("N10", "코드 위치를 안쪽이 먼저가 아니라 바깥이 먼저로(뒤집기 빠짐)", ERR, "    return found[-MAX_FRAMES:][::-1]", "    return found[-MAX_FRAMES:]")
add("N11", "코드 위치 수 상수 6 을 5 로", ERR, "MAX_FRAMES = 6 ", "MAX_FRAMES = 5 ")
# S4 돌려쓰기는 이름 바꾸기뿐
add("N12", "돌려쓰기가 가장 오래된 파일을 먼저 지움(옛 동작)", ERR, "        if len(names) == 1:", "        (folder / names[-1]).unlink(missing_ok=True)\n        if len(names) == 1:")
add("N13", "돌려쓰는 순서가 거꾸로(현재 → .1 부터 밀어 옛 .1 을 덮어씀)", ERR, "        for index in range(len(names) - 2, -1, -1):", "        for index in range(0, len(names) - 1):")
add("N14", "옛 파일을 안 남기는 설정의 특별 처리가 빠짐(현재 파일이 한도 없이 커짐)", ERR, "        if len(names) == 1:                                            # 옛 파일을 하나도 안 남기는 설정 — 현재 파일을 비운다\n            (folder / names[0]).unlink(missing_ok=True)\n            return\n", "")
add("N15", "옛 파일을 안 남기는 설정에서 현재 파일을 비우지 않음", ERR, "            (folder / names[0]).unlink(missing_ok=True)\n            return\n", "            return\n")
# 잠금 기다림·시각
add("N16", "잠금 기다림 1초를 0.1초로", ERR, "LOCK_WAIT = 1.0 ", "LOCK_WAIT = 0.1 ")
add("N17", "시각을 UTC 가 아닌 한국 시각(+9)으로 바꿔 적음", ERR, "            moment = moment.astimezone(timezone.utc)\n", "            moment = moment.astimezone(timezone(__import__(\"datetime\").timedelta(hours=9)))\n")
add("N18", "처리 중인 오류의 추적을 빌릴 때 종류가 클래스인지 확인하지 않음", ERR, "if current[0] is not None and isinstance(kind, type) and issubclass(current[0], kind):", "if current[0] is not None and issubclass(current[0], kind):")
# S3·S5·I8 문서와 한계
add("N19", "SECURITY.md 의 한계 줄이 사라짐(제목을 바꿔 한계가 안 보임)", "docs/SECURITY.md", "- **한계(기록이 닿지 않는 길)**:", "- **기타**:")
add("N20", "TROUBLESHOOTING.md 에서 폴더 여는 법(Win+R)이 사라짐", "docs/TROUBLESHOOTING.md", "키보드의 `Win` 키와 `R` 키를 함께 눌러 나오는 '실행' 창에", "탐색기 주소창에")
add("N21", "SECURITY.md 가 다시 '1분에 30줄까지만' 이라고 적음", "docs/SECURITY.md", "**정해진 1분 구간마다 30줄까지만** 쓴다", "1분에 30줄까지만 쓴다")
add("N22", "errorlog.py 의 설명이 다시 '시험은 켜지 않는다' 고 적음", ERR, "`--sample` 없이 `launcher.main` 을 끝까지 부르는 기존 시험은 켜지지만, 켜기만으로는 아무것도 읽거나 만들지 않고 시험의 뒷정리가 끈다", "시험은 켜지 않는다")
add("N23", "묶음 실행 파일의 시작 실패 길(start_gui)이 기록기를 부르게 이음 — 문서의 한계가 거짓이 됨", "packaging/gui_entry.py", "        say(START_FAILED.format(kind=type(error).__name__), error=True)\n", "        __import__(\"chanceblog_desktop.security.errorlog\", fromlist=[\"x\"]).record_exception(\"main\", type(error), error)\n        say(START_FAILED.format(kind=type(error).__name__), error=True)\n")
add("N24", "작업 스레드 길(Job._run)이 기록기를 부르게 이음 — 문서의 한계가 거짓이 됨", "src/chanceblog_desktop/ui/core/jobs.py", "            self._finish(self.FAILED, \"error\", JobFailure(T[\"job_failed\"], code=type(error).__name__), self.payload)\n",
    "            __import__(\"chanceblog_desktop.security.errorlog\", fromlist=[\"x\"]).record_exception(\"thread\", type(error), error)\n            self._finish(self.FAILED, \"error\", JobFailure(T[\"job_failed\"], code=type(error).__name__), self.payload)\n")
