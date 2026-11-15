"""AP14 추가 확인 — 한글·공백이 든 데이터 폴더, 아주 긴 폴더 이름, 기록 파일의 바이트(ASCII·개행) 모양.
사용: python -B -X utf8 probe_extra.py <tree 폴더> <임시 작업 폴더>
"""
import datetime as dt
import os
import sys

tree, work = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(tree, "src"))
from chanceblog_desktop.security import errorlog  # noqa: E402

FIXED = dt.datetime(2026, 11, 15, 7, 41, 5, tzinfo=dt.timezone.utc)


def boom():
    try:
        raise ValueError("m")
    except ValueError as error:
        return error


def rec(log):
    error = boom()
    return log.record("main", type(error), error, error.__traceback__)


# 1) 한글·공백이 든 폴더(윈도 한글 사용자 이름 모양)
root = os.path.join(work, "한글 사용자", "내 데이터 폴더")
log = errorlog.ErrorLog(lambda: root, clock=lambda: FIXED)
ok = rec(log)
path = os.path.join(root, "logs", "errors.log")
raw = open(path, "rb").read() if os.path.exists(path) else b""
print("한글·공백 폴더: record=%r, 파일 있음=%r, 바이트 %d, ASCII만=%r, 끝이 LF 한 개=%r, CR 포함=%r" % (ok, os.path.exists(path), len(raw), raw.isascii(), raw.endswith(b"\n") and raw.count(b"\n") == 1, b"\r" in raw))

# 2) 아주 긴 폴더 이름(윈도 260자 근처)
long_root = os.path.join(work, "x" * 120, "y" * 120, "z" * 60)
log2 = errorlog.ErrorLog(lambda: long_root, clock=lambda: FIXED)
ok2 = rec(log2)
print("260자 넘는 경로: record=%r (윈도 긴 경로 제한이면 False 로 삼킴, 예외 없음)" % ok2)

# 3) 경로에 줄에 들어갈 만한 글이 있어도 줄에는 없다(기록 파일 자신의 위치는 적지 않는다)
text = raw.decode("utf-8")
print("줄에 폴더 이름 조각이 있나:", any(piece in text for piece in ("한글", "사용자", "데이터", work.replace('\\', '/').split('/')[-1])))


# 4) 가장 긴 줄(큰 줄) — 클래스 이름 64자, 파일 이름 64자·줄 번호 7자리 위치 여섯 개
import types
frame = sys._getframe()
class LongCode:
    co_filename = "C:/x/" + "f" * 64
class LongFrame:
    f_code = LongCode()
tb = None
for number in range(6):
    tb = types.TracebackType(tb, frame, 0, 9999999)
# TracebackType 은 진짜 프레임이 필요하므로 파일 이름은 가짜 추적 객체로 따로 만든다
class FakeTb:
    def __init__(self, nxt):
        self.tb_frame = LongFrame()
        self.tb_lineno = 9999999
        self.tb_next = nxt
chain = None
for _ in range(6):
    chain = FakeTb(chain)
Long = type("E" * 64, (Exception,), {})
log3 = errorlog.ErrorLog(lambda: os.path.join(work, "longline"), clock=lambda: FIXED)
ok3 = log3.record("unraisable", Long, Long("m"), chain)
text3 = open(os.path.join(work, "longline", "logs", "errors.log"), "rb").read()
print("가장 긴 줄: record=%r, 바이트 %d (한도 %d 의 %.3f%%)" % (ok3, len(text3), errorlog.MAX_BYTES, 100.0 * len(text3) / errorlog.MAX_BYTES))

# 5) 공개 write() 에 한도보다 큰 줄을 직접 넣으면(record 경로로는 만들 수 없다)
log4 = errorlog.ErrorLog(lambda: os.path.join(work, "biglineapi"), clock=lambda: FIXED)
ok4 = log4.write("x" * 300000)
print("write() 에 300000자를 직접: 반환 %r, 파일 %d 바이트(한도 %d)" % (ok4, os.path.getsize(os.path.join(work, "biglineapi", "logs", "errors.log")), errorlog.MAX_BYTES))
