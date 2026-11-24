"""Qt 시험(오프스크린)을 이 PC 에서 한 번에 하나만 돌리게 하는 공용 잠금 — 구현자·검증자가 서로의 시험과 겹치지 않도록 감싸서 쓴다(S 검증자 제안, 2026-11-17).
사용: py -3.12 -X utf8 C:/work/ai/qt_lock.py [--max-wait 3600] -- <실행할 명령과 인자...>
  - 잠금 파일 C:/work/ai/qt.lock 을 만들 수 있을 때까지 기다린다(60초마다 누가 잡고 있는지 한 줄 알림).
  - 잠근 프로세스가 죽었거나 잠금이 150분 넘게 묵었으면 낡은 잠금으로 보고 치운다.
  - 명령이 끝나면(성공·실패·중단 모두) 잠금을 푼다. 종료 코드는 명령의 것을 그대로 돌려준다(시간 초과로 못 잡으면 75).
예: py -3.12 -X utf8 C:/work/ai/qt_lock.py -- C:/work/ai/venv_qt/Scripts/python.exe -X utf8 -m unittest test_ui_qt_polish1"""
import json
import os
import subprocess
import sys
import time

LOCK = "C:/work/ai/qt.lock"
STALE_SECONDS = 150 * 60


def pid_alive(pid):
    """프로세스가 아직 살아 있는지(윈도 API). 권한이 모자라 못 열면 살아 있는 것으로 본다(잠금을 함부로 치우지 않는다)."""
    if not pid:
        return False
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5                      # 접근 거부 = 살아 있음, 그 밖(없는 PID)은 죽음
    code = ctypes.c_ulong()
    ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel32.CloseHandle(handle)
    return bool(ok) and code.value == 259                        # STILL_ACTIVE


def read_holder():
    try:
        with open(LOCK, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 — 막 만들어지는 중이거나 깨진 잠금
        return None


def try_acquire(cmd_text):
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "since": time.time(), "cmd": cmd_text[:160]}, f, ensure_ascii=False)
    return True


def main(argv):
    if "--" not in argv:
        print(__doc__)
        return 2
    split = argv.index("--")
    opts, cmd = argv[:split], argv[split + 1:]
    max_wait = 3600
    if "--max-wait" in opts:
        max_wait = int(opts[opts.index("--max-wait") + 1])
    if "--name" in opts:                        # 잠금 이름(기본 qt) — 'heavy' 는 전체 시험 같은 무거운 실행용(11-22 추가: CPU 100% 포화 완화)
        name = opts[opts.index("--name") + 1]
        if not name.isalnum():
            print("--name 은 영문·숫자만")
            return 2
        global LOCK
        LOCK = f"C:/work/ai/{name}.lock"
    if not cmd:
        print(__doc__)
        return 2
    started = time.time()
    last_note = 0.0
    cmd_text = " ".join(cmd)
    while not try_acquire(cmd_text):
        holder = read_holder()
        if holder:
            stale = time.time() - holder.get("since", 0) > STALE_SECONDS or not pid_alive(holder.get("pid", 0))
            if stale:
                try:
                    os.remove(LOCK)
                    print("낡은 잠금을 치웠습니다.", flush=True)
                except OSError:
                    pass
                continue
        if time.time() - started > max_wait:
            print("잠금을 못 잡아 그만둡니다(시간 초과).", flush=True)
            return 75
        if time.time() - last_note > 60:
            last_note = time.time()
            print("다른 Qt 시험이 돌고 있어 기다립니다:", (holder or {}).get("cmd", "?")[:80], flush=True)
        time.sleep(5)
    try:
        return subprocess.run(cmd).returncode
    finally:
        holder = read_holder()
        if holder and holder.get("pid") == os.getpid():
            try:
                os.remove(LOCK)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
