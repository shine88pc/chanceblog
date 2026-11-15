"""여유 메모리(GB)를 읽는다. 사용: python memfree.py [최소GB] — 최소GB 를 주면 그 값 이상이 될 때까지(최대 30분) 기다린 뒤 값을 적고 끝난다."""
import ctypes
import sys
import time


class _Status(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]


def free_gb():
    status = _Status()
    status.dwLength = ctypes.sizeof(_Status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.ullAvailPhys / (1024 ** 3)


if __name__ == "__main__":
    need = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    waited = 0
    while free_gb() < need and waited < 1800:
        time.sleep(10)
        waited += 10
    print(f"free_gb={free_gb():.2f} waited_s={waited}")
