"""AP14(작은 로그 파일) 변이 정의 — mut_run.py 가 읽는다. 각 항목: id → {item, what, file, old, new(글 치환), modules, py}."""

SEC = "src/chanceblog_desktop/security/"
ERRLOG = SEC + "errorlog.py"
MINE = ["test_security_errorlog"]
MINE_AND_BOUNDARY = ["test_security_errorlog", "test_security_boundary"]

MUTATIONS = {}


def add(mid, what, file, old, new, modules=MINE, py="dev", regex=False):
    MUTATIONS[mid] = {"item": "AP14", "what": what, "file": file, "old": old, "new": new, "modules": modules, "regex": regex, "py": py}


add("L01", "오류 메시지를 그대로 줄에 기록(메시지 글이 위치 목록에 끼어듦)", ERRLOG,
    "return self.write(self._build(source, _class_name(kind, value), _frames(_trace_of(kind, value, trace))))",
    "return self.write(self._build(source, _class_name(kind, value), _frames(_trace_of(kind, value, trace)) + [str(value)]))")
add("L02", "공통 가림 경로 우회(완성한 줄이 mask 를 거치지 않음)", ERRLOG,
    "return mask(f\"{self._stamp()} {label} {name} \" + (\" < \".join(places) if places else \"-\"))",
    "return f\"{self._stamp()} {label} {name} \" + (\" < \".join(places) if places else \"-\")")
add("L03", "돌려쓰기 크기 확인 제거(파일이 한도 없이 커짐)", ERRLOG, "if size > 0 and size + len(data) > self._max_bytes:", "if False:")
add("L04", "백업의 담지 않는 것 목록에서 `logs/` 이름이 빠짐", SEC + "backup_note.py", '    ("logs/", "앱이 처리하지 못한', '    ("log-x/", "앱이 처리하지 못한')
add("L05", "켜기만 해도 폴더를 만듦(첫 오류 전에 파일·폴더가 생김)", ERRLOG,
    "        self._lock = threading.RLock()\n",
    "        self._lock = threading.RLock()\n        Path(self._resolve()).joinpath(FOLDER_NAME).mkdir(parents=True, exist_ok=True)\n")
add("L06", "쓰기 실패가 예외로 새어 나감(OSError 를 삼키지 않음)", ERRLOG,
    "            self._append(line)\n            return True\n        except Exception:\n            return False\n        finally:",
    "            self._append(line)\n            return True\n        except ZeroDivisionError:\n            return False\n        finally:")
add("L07", "KeyboardInterrupt·SystemExit 도 기록함", ERRLOG, "            if isinstance(kind, type) and issubclass(kind, _NOT_RECORDED):\n                return False\n", "            if False:\n                return False\n")
add("L08", "경계를 되돌려도 오류 기록이 꺼지지 않음", SEC + "boundary.py", "        installed._undo.append(lambda: errorlog.disarm(log))\n", "        pass\n", MINE_AND_BOUNDARY)
add("L09", "예시 화면도 오류 기록을 켬", "src/chanceblog_desktop/ui/launcher.py", "    if not args.sample:                                                               # 예시 화면은 아무것도 저장하지 않는다", "    if True:                                                               # 예시 화면은 아무것도 저장하지 않는다")
add("L10", "파일 이름 앞의 폴더를 떼지 않음(구분자를 못 가름)", ERRLOG, '_SEPARATORS = re.compile(r"[\\\\/]")', '_SEPARATORS = re.compile(r"[?]")')
add("L11", "속도 제한 제거(오류가 쏟아지면 계속 씀)", ERRLOG, "        if self._window_count >= self._rate_count:\n            return False\n", "")
add("L12", "처리하지 못한 예외 훅(main)이 기록으로 이어지지 않음", SEC + "boundary.py", '    _record("main", kind, value, trace)\n', "", MINE_AND_BOUNDARY)
add("L13", "Qt 경고도 오류 기록에 남김", ERRLOG, 'QT_RECORDED = ("QtCriticalMsg", "QtFatalMsg")', 'QT_RECORDED = ("QtCriticalMsg", "QtFatalMsg", "QtWarningMsg")')
add("L14", "화면의 한 줄 기록(report_unexpected)이 파일에 남기지 않음", "src/chanceblog_desktop/ui/core/app_state.py", '        errorlog.record_exception("slot", kind, value)\n', "        pass\n")
add("L15", "SECURITY.md 가 다시 '로그 파일은 아직 없다' 고 적음", "docs/SECURITY.md",
    "- **로그 파일·내보내기**: 작은 오류 기록 파일 하나가 있다(맨 끝 '오류 기록' 절 — 오류 이름과 코드 위치만 남기고 공통 가림 규칙을 거친다, D-488). 로그를 내보내는 기능은 아직 없다.",
    "- **로그 파일·내보내기**: 아직 없다. 만든다면 공통 경계가 이미 가린 기록을 쓴다.")
add("L16", "launcher 가 데이터 폴더를 새로 계산함(앱의 해석 함수를 쓰지 않음)", "src/chanceblog_desktop/ui/launcher.py", "        return Workspace.resolve(data_dir).root", "        return data_dir")
add("L17", "돌려쓰기 보관 수가 2 → 5(파일이 셋을 넘음)", ERRLOG, "BACKUPS = 2 ", "BACKUPS = 5 ")
add("L18", "한 줄에 위치를 여섯 대신 전부 적음(MAX_FRAMES 제한 제거)", ERRLOG, "    return found[-MAX_FRAMES:][::-1]", "    return found[::-1]")
add("L19", "Qt 메시지 핸들러가 오류 기록으로 이어지지 않음", SEC + "boundary.py", "    _record_qt(message_type, context)                      # 종류·분류 이름·C++ 쪽 파일:줄만 — 메시지 글은 기록 쪽으로 넘기지 않는다\n", "", MINE_AND_BOUNDARY)
add("L20", "잠금이 다시 들어오지 못함(RLock → Lock)", ERRLOG, "        self._lock = threading.RLock()\n", "        self._lock = threading.Lock()\n")
add("L21", "경계의 기록 연결(_record)이 기록기의 예외를 삼키지 않음", SEC + "boundary.py", "        return errorlog.record_exception(source, kind, value, trace)\n    except Exception:\n", "        return errorlog.record_exception(source, kind, value, trace)\n    except ZeroDivisionError:\n", MINE_AND_BOUNDARY)
add("L22", "화면의 한 줄 기록(report_unexpected)이 기록기의 예외를 삼키지 않음", "src/chanceblog_desktop/ui/core/app_state.py", '        errorlog.record_exception("slot", kind, value)\n    except Exception:', '        errorlog.record_exception("slot", kind, value)\n    except ZeroDivisionError:')
add("L23", "record 의 바깥 겹이 예외를 삼키지 않음(가림이 고장 나면 새어 나감)", ERRLOG, "_trace_of(kind, value, trace))))\n        except Exception:\n            return False", "_trace_of(kind, value, trace))))\n        except ZeroDivisionError:\n            return False")
add("L24", "경계의 Qt 기록 연결(_record_qt)이 기록기의 예외를 삼키지 않음", SEC + "boundary.py", "        return errorlog.record_qt(message_type, context)\n    except Exception:\n", "        return errorlog.record_qt(message_type, context)\n    except ZeroDivisionError:\n", MINE_AND_BOUNDARY)
