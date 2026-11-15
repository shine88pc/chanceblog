"""여유 메모리(GB)를 읽는다. 사용: python memfree.py [최소GB] — 최소GB 를 주면 그 값 이상이 될 때까지(최대 30분) 기다린 뒤 값을 적고 끝난다.
무거운 시험·빌드를 시작하기 전에 `python -X utf8 memfree.py 0.7` 처럼 부르면 메모리가 모자랄 때 기다려 준다(이 PC 에서 여러 작업이 동시에 돌 때 쓴 도구).
윈도(GlobalMemoryStatusEx)와 리눅스(/proc/meminfo)에서 값을 읽는다. 그 밖의 환경은 값을 읽지 못하므로 기다리지 않고 `free_gb=unknown` 을 적고 끝난다."""
import ctypes
import os
import sys
import time

WAIT_LIMIT_S = 1800          # 최대 30분
STEP_S = 10                  # 10초마다 다시 읽는다


class _Status(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]


def meminfo_available_gb(text):
    """리눅스 /proc/meminfo 글에서 MemAvailable(kB)을 GB 로 — 없으면 None."""
    for line in text.splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) / (1024 ** 2)
    return None


def free_gb():
    """여유 물리 메모리(GB). 읽을 수 없는 환경이면 None."""
    if os.name == "nt":
        status = _Status()
        status.dwLength = ctypes.sizeof(_Status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return status.ullAvailPhys / (1024 ** 3)
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            return meminfo_available_gb(handle.read())
    except OSError:
        return None


def wait_until(need, read=free_gb, sleep=time.sleep, limit=WAIT_LIMIT_S, step=STEP_S):
    """여유 메모리가 need(GB) 이상이 될 때까지(최대 limit 초) step 초마다 읽으며 기다린다 — (마지막으로 읽은 값, 기다린 초). 값을 읽을 수 없으면(None) 기다리지 않는다."""
    waited = 0
    value = read()
    while value is not None and value < need and waited < limit:
        sleep(step)
        waited += step
        value = read()
    return value, waited


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    need = float(argv[0]) if argv else 0.0
    value, waited = wait_until(need)
    print("free_gb=unknown waited_s=0" if value is None else f"free_gb={value:.2f} waited_s={waited}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
