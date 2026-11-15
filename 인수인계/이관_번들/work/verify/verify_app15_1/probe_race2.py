"""AP14 2차 — 같은 폴더에서 기록기 둘(자물쇠가 서로 다름)이 동시에 돌려쓸 때 한 파일이 한도를 넘는 일이 얼마나 자주 나는가 — 옛 머리와 새 머리를 같은 방법으로 견준다. 기록기 하나(대조)는 넘지 않아야 한다.
사용: python -B -X utf8 probe_race2.py <tree 폴더> <임시 작업 폴더> [시도 횟수]
"""
import datetime as dt
import os
import sys
import threading

TREE, WORK = sys.argv[1], sys.argv[2]
TRIALS = int(sys.argv[3]) if len(sys.argv) > 3 else 12
assert WORK.replace("\\", "/").startswith("C:/work/ai/verify_app15_1/")
sys.path.insert(0, os.path.join(TREE, "src"))
from chanceblog_desktop.security import errorlog  # noqa: E402

FIXED = dt.datetime(2026, 11, 15, 7, 41, 5, tzinfo=dt.timezone.utc)
LIMIT = 4000


def boom():
    try:
        raise ValueError("m")
    except ValueError as error:
        return error


def trial(number, instances):
    root = os.path.join(WORK, "race_i%d_t%02d" % (instances, number))
    logs = [errorlog.ErrorLog(lambda: root, clock=lambda: FIXED, max_bytes=LIMIT, rate=(10 ** 9, 60.0)) for _ in range(instances)]
    errors = []

    def work(log):
        for _ in range(250):
            try:
                error = boom()
                log.record("main", type(error), error, error.__traceback__)
            except BaseException as exc:  # noqa: BLE001
                errors.append(type(exc).__name__)

    threads = [threading.Thread(target=work, args=(logs[i % instances],)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    folder = os.path.join(root, "logs")
    sizes = {n: os.path.getsize(os.path.join(folder, n)) for n in sorted(os.listdir(folder))}
    return errors, sizes


orig = errorlog.LOCK_WAIT
errorlog.LOCK_WAIT = 60.0
try:
    for instances in (1, 2):
        over, many, errs, biggest = 0, 0, 0, 0
        for number in range(TRIALS):
            errors, sizes = trial(number, instances)
            errs += len(errors)
            biggest = max(biggest, max(sizes.values()))
            over += 1 if max(sizes.values()) > LIMIT else 0
            many += 1 if len(sizes) > 3 else 0
        print("기록기 %d개 x 스레드 8개, 한도 %d B, %d번: 한도를 넘은 시도 %d번, 가장 큰 파일 %d B, 파일 4개 이상인 시도 %d번, 예외 %d" % (instances, LIMIT, TRIALS, over, biggest, many, errs))
finally:
    errorlog.LOCK_WAIT = orig
