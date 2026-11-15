"""AP14 누출 시도(적대적) — 복사본의 security/errorlog.py 를 직접 불러 줄 생성을 시도한다.
사용: python -B -X utf8 probe_leak.py <tree 폴더> <임시 작업 폴더>
가짜 비밀은 모양만 같은 가짜 문자열(런타임 조립)이다. 줄이 '좁은 형식'이 아니거나 금지 조각이 들어 있으면 LEAK 로 센다.
"""
import datetime as dt
import os
import re
import sys
import threading
import types

TREE = sys.argv[1]
WORK = sys.argv[2]
sys.path.insert(0, os.path.join(TREE, "src"))
sys.path.insert(0, os.path.join(TREE, "tests"))
sys.path.insert(0, TREE)
from chanceblog_desktop.security import errorlog  # noqa: E402

UTC = dt.timezone.utc
FIXED = dt.datetime(2026, 11, 15, 7, 41, 5, tzinfo=UTC)

GKEY = "AI" + "za" + "Sy" + "CANARY" + "x" * 27            # 구글 키 모양(AIza + 35자)
GTOK = "gh" + "p_" + "CANARY" + "a" * 30                      # 깃허브 토큰 모양
PW = "password" + "=" + "CANARY_hunter2_pw"
PW_KO = "비밀번호는 CANARY_pw9 입니다"
UPATH = "C:/Users/CANARY_jane.doe/Desktop/secret plans.txt"
UPATH_BS = "C:\\Users\\CANARY_jane\\AppData\\Local\\Temp\\note.txt"
EMAIL = "<이메일>"
FORBIDDEN = ["CANARY", "Users", "AIza", "ghp_", "assword", "hunter", "비밀", "@", "example.com", "jane", "Desktop", "secret plans", "\\", "C:", "/", "\n\n", "\x1b", "\x00"]

NAME = r"[A-Za-z_][A-Za-z0-9_]{0,63}"
FILE = r"[A-Za-z0-9_?][A-Za-z0-9_.\-]{0,63}"
PLACE = FILE + r":\d+"
STRICT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z (?:main|thread|unraisable|slot) " + NAME + r" (?:-|" + PLACE + r"(?: < " + PLACE + r"){0,5})")
STRICT_QT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z qt (?:QtCriticalMsg|QtFatalMsg) (?:-|(?:" + FILE + r")?(?: < )?(?:" + PLACE + r")?)")

counter = [0]
results = []


def fresh(**options):
    counter[0] += 1
    root = os.path.join(WORK, "c%03d" % counter[0])
    options.setdefault("clock", lambda: FIXED)
    options.setdefault("rate", (10 ** 9, 60.0))
    return errorlog.ErrorLog(lambda: root, **options), root


def read_lines(root):
    path = os.path.join(root, "logs", "errors.log")
    if not os.path.exists(path):
        return []
    with open(path, "rb") as handle:
        raw = handle.read()
    return raw.decode("utf-8", "replace").split("\n")[:-1] if raw.endswith(b"\n") else raw.decode("utf-8", "replace").split("\n")


def judge(case, how, lines, returned, qt=False):
    verdict = "OK"
    notes = []
    if len(lines) > 1:
        verdict = "LEAK"
        notes.append("줄이 둘 이상(%d)" % len(lines))
    for line in lines:
        if not (STRICT_QT if qt else STRICT).fullmatch(line):
            if "[가림" in line:
                notes.append("가림 표지가 줄에 들어옴")
                verdict = "MASKED" if verdict == "OK" else verdict
            else:
                verdict = "LEAK"
                notes.append("좁은 형식 밖")
        for piece in FORBIDDEN:
            if piece in line:
                verdict = "LEAK"
                notes.append("금지 조각 %r" % piece)
    results.append((case, how, returned, lines, verdict, notes))


def raise_and_catch(kind, *args, **kwargs):
    try:
        raise kind(*args, **kwargs)
    except BaseException as error:  # noqa: BLE001
        return error


def run(case, how, build, source="main", qt=False):
    """build() -> (kind, value, trace) 또는 qt 면 (message_type, context). 반환값 returned 와 파일 줄을 판정."""
    log, root = fresh()
    try:
        args = build()
        if qt:
            returned = log.record_qt(*args)
        else:
            returned = log.record(source, *args)
    except BaseException as error:  # noqa: BLE001
        results.append((case, how, "EXC:" + type(error).__name__, [], "RAISED", ["기록기 밖으로 예외가 나옴"]))
        return
    judge(case, how, read_lines(root), returned, qt=qt)


# ---- A. 메시지 ------------------------------------------------------------------------------------------------------------------------
def msg_case(case, how, message, kind=ValueError):
    def build():
        error = raise_and_catch(kind, message)
        return type(error), error, error.__traceback__
    run(case, how, build)


msg_case("A01", "메시지에 구글 키 모양", "bad key " + GKEY + " rejected")
msg_case("A02", "메시지에 깃허브 토큰 모양", "token " + GTOK)
msg_case("A03", "메시지에 password=… 문구", "login failed " + PW)
msg_case("A04", "메시지에 한국어 비밀번호 문구", PW_KO)
msg_case("A05", "메시지에 개인 경로(슬래시)", "cannot open " + UPATH)
msg_case("A06", "메시지에 개인 경로(역슬래시)", "cannot open " + UPATH_BS)
msg_case("A07", "메시지에 이메일", "mail to " + EMAIL)
msg_case("A08", "메시지에 개행으로 가짜 줄 위조", "x\n2026-11-15T07:41:05Z main FakeError fake.py:1\n" + GKEY)
msg_case("A09", "메시지에 CR LF ANSI 이스케이프", "a\r\nb\x1b[31mred\x1b[0m " + GKEY)
msg_case("A10", "메시지에 NUL BEL 제어 문자", "a\x00b\x07c " + GKEY)
msg_case("A11", "메시지에 방향 제어·폭 없는 글자로 쪼갠 키", "".join(ch + chr(0x200B) for ch in GKEY) + chr(0x202E) + "gnp.txt")
msg_case("A12", "메시지 10 MB", "A" * (10 * 1024 * 1024) + GKEY)
msg_case("A13", "메시지 인자가 dict(키 포함)", {"api_key": GKEY, "path": UPATH})
msg_case("A14", "메시지 인자가 bytes", GKEY.encode())


def multi_args():
    error = raise_and_catch(ValueError, GKEY, UPATH, EMAIL, PW)
    return type(error), error, error.__traceback__


run("A15", "예외 인자 여러 개(키·경로·이메일·문구)", multi_args)


def chained():
    try:
        try:
            raise KeyError("inner " + GKEY)
        except KeyError as inner:
            raise RuntimeError("outer " + UPATH) from inner
    except RuntimeError as error:
        if hasattr(error, "add_note"):
            error.add_note("note " + GTOK)
        return type(error), error, error.__traceback__


run("A16", "원인 사슬(__cause__)과 add_note 에 비밀", chained)

# ---- B. 클래스 이름 ---------------------------------------------------------------------------------------------------------------------


def class_case(case, how, name, base=Exception):
    def build():
        kind = type(name, (base,), {})
        error = raise_and_catch(kind, "m " + GKEY)
        return kind, error, error.__traceback__
    run(case, how, build)


class_case("B01", "클래스 이름에 공백", "Bad Name")
class_case("B02", "클래스 이름에 따옴표", "Bad'Name\"")
class_case("B03", "한글 클래스 이름", "한글오류")
class_case("B04", "클래스 이름 200자", "E" * 200)
class_case("B05", "클래스 이름에 개행", "Evil\nName 2026-11-15T07:41:05Z main X y.py:1")
class_case("B06", "클래스 이름 64자(경계)", "E" * 64)
class_case("B07", "클래스 이름 65자(경계 밖)", "E" * 65)
class_case("B08", "구글 키 모양인 식별자 이름", GKEY)
class_case("B09", "깃허브 토큰 모양인 식별자 이름", GTOK)
class_case("B10", "비ASCII 식별자 이름", "Ünïcode")
class_case("B11", "이메일 모양을 흉내 낸 식별자 이름", "CANARY_jane_doe_at_example_com")
class_case("B12", "클래스 이름에 탭·유니코드 공백", "A\tB" + chr(0x00A0) + "C")


class MetaProp(type):
    @property
    def __name__(cls):  # noqa: A003
        return "secret value here " + GKEY


class MetaRaise(type):
    @property
    def __name__(cls):  # noqa: A003
        raise RuntimeError("이름을 못 줌")


class MetaInt(type):
    @property
    def __name__(cls):  # noqa: A003
        return 12345


def meta_case(case, how, meta):
    def build():
        kind = meta("X", (Exception,), {})
        error = raise_and_catch(kind, "m")
        return kind, error, error.__traceback__
    run(case, how, build)


meta_case("B13", "메타클래스 __name__ 이 공백·키가 든 글", MetaProp)
meta_case("B14", "메타클래스 __name__ 이 예외를 던짐", MetaRaise)
meta_case("B15", "메타클래스 __name__ 이 숫자", MetaInt)

# ---- C. 이상한 예외 ---------------------------------------------------------------------------------------------------------------------


class StrBoom(Exception):
    def __str__(self):
        raise RuntimeError("str 이 터짐 " + GKEY)

    def __repr__(self):
        raise RuntimeError("repr 도 터짐")


def strboom():
    error = raise_and_catch(StrBoom, GKEY)
    return type(error), error, error.__traceback__


run("C01", "__str__·__repr__ 이 예외를 던지는 예외", strboom)


class TbBoom(Exception):
    @property
    def __traceback__(self):
        raise RuntimeError("tb 속성이 터짐")

    @__traceback__.setter
    def __traceback__(self, value):
        pass


def tbboom():
    error = TbBoom(GKEY)
    return TbBoom, error, None


run("C02", "__traceback__ 속성이 예외를 던지는 예외", tbboom)


def recursion_error():
    def f():
        f()
    try:
        f()
    except RecursionError as error:
        return type(error), error, error.__traceback__


run("C03", "진짜 RecursionError(얕은 곳에서 기록)", recursion_error)


def recursion_in_deep_stack():
    log, root = fresh()
    holder = {}

    def f(depth):
        try:
            f(depth + 1)
        except RecursionError as error:
            if "r" not in holder:
                holder["r"] = True
                try:
                    holder["ret"] = log.record("main", type(error), error, error.__traceback__)
                except BaseException as exc:  # noqa: BLE001
                    holder["exc"] = type(exc).__name__
            raise

    try:
        f(0)
    except RecursionError:
        pass
    if "exc" in holder:
        results.append(("C04", "RecursionError 직후 스택이 거의 가득 찬 곳에서 기록", "EXC:" + holder["exc"], [], "RAISED", ["예외가 밖으로 나옴"]))
    else:
        judge("C04", "RecursionError 직후 스택이 거의 가득 찬 곳에서 기록", read_lines(root), holder.get("ret"))


recursion_in_deep_stack()


def depth_1000():
    def down(count):
        if count == 0:
            raise ValueError("깊다 " + GKEY)
        down(count - 1)
    try:
        down(900)
    except ValueError as error:
        return type(error), error, error.__traceback__


run("C05", "트레이스백 깊이 900", depth_1000)


def synthetic_chain():
    frame = sys._getframe()
    tb = None
    for number in range(1, 30001):
        tb = types.TracebackType(tb, frame, 0, number)
    return ValueError, ValueError("x"), tb


run("C06", "합성 트레이스백 30000 단계(상한 10000)", synthetic_chain)


def bad_tb():
    class FakeTb:
        @property
        def tb_frame(self):
            raise RuntimeError("프레임 없음")
    return ValueError, ValueError("x"), FakeTb()


run("C07", "tb_frame 이 예외를 던지는 가짜 추적", bad_tb)


def tb_junk_values():
    class FakeCode:
        co_filename = GKEY + "/" + UPATH
    class FakeFrame:
        f_code = FakeCode()
    class FakeTb:
        tb_frame = FakeFrame()
        tb_lineno = "12; DROP TABLE"
        tb_next = None
    return ValueError, ValueError("x"), FakeTb()


run("C08", "가짜 추적: 줄 번호가 글, 파일 이름이 키+경로", tb_junk_values)


def exception_group():
    if "ExceptionGroup" not in dir(__builtins__) and not hasattr(__builtins__, "ExceptionGroup"):
        return ValueError, ValueError("(이 파이썬에는 ExceptionGroup 없음)"), None
    try:
        raise ExceptionGroup("grp " + GKEY, [ValueError("a " + UPATH), KeyError(EMAIL)])  # noqa: F821
    except BaseException as error:  # noqa: BLE001
        return type(error), error, error.__traceback__


run("C09", "ExceptionGroup(하위 예외 메시지에 비밀)", exception_group)

# ---- D. 코드 위치(파일 이름) -----------------------------------------------------------------------------------------------------------


def foreign(filename, message="m"):
    namespace = {}
    exec(compile("def boom(message):\n    raise ValueError(message)\n", filename, "exec"), namespace)  # noqa: S102
    try:
        namespace["boom"](message)
    except ValueError as error:
        return type(error), error, error.__traceback__


def file_case(case, how, filename):
    run(case, how, lambda: foreign(filename))


file_case("D01", "공백이 든 파일 이름", "C:/Users/CANARY_jane/proj dir/inner mod.py")
file_case("D02", "구글 키 모양 파일 이름", "C:/x/" + GKEY + ".py")
file_case("D03", "깃허브 토큰 모양 파일 이름", "/home/CANARY_jane/" + GTOK + ".py")
file_case("D04", "한글 파일 이름", "C:/x/내파일.py")
file_case("D05", "<string>", "<string>")
file_case("D06", "<frozen importlib._bootstrap>", "<frozen importlib._bootstrap>")
file_case("D07", "파일 이름에 개행", "C:/x/a\nb.py")
file_case("D08", "파일 이름 200자", "C:/x/" + "f" * 200 + ".py")
file_case("D09", "빈 파일 이름", "")
file_case("D10", "'..' 와 끝 슬래시", "C:/Users/CANARY_jane/..")
file_case("D11", "끝이 슬래시", "C:/Users/CANARY_jane/")
file_case("D12", "UNC 경로", "\\\\CANARY_server\\share\\folder\\x.py")
file_case("D13", "대체 스트림·드라이브 상대 표기", "C:foo.py::$DATA")
file_case("D14", "파일 이름에 따옴표", "C:/x/x\"y.py")
file_case("D15", "파일 이름 password-hunter2.py(좁은 글자표 안)", "C:/x/password-hunter2.py")
file_case("D16", "파일 이름 64자(경계)", "C:/x/" + "f" * 61 + ".py")
file_case("D17", "파일 이름 65자(경계 밖)", "C:/x/" + "f" * 62 + ".py")
file_case("D18", "파일 이름이 숫자·밑줄로 시작", "C:/x/_1-2.3.py")

# ---- E. 갈래·종류 이상 -----------------------------------------------------------------------------------------------------------------


def odd_source(source):
    def build():
        error = raise_and_catch(ValueError, GKEY)
        return type(error), error, error.__traceback__
    return build


for number, source in enumerate(["main\nFAKE", None, ["main"], b"main", "qt", "MAIN", "main "], start=1):
    run("E%02d" % number, "갈래 값 %r" % (source,), odd_source(source), source=source)


def kind_string():
    return "AI" + "za" + "Sy" + "CANARY" + "x" * 27, None, None


run("E10", "kind 가 키 모양 글(클래스 아님)", kind_string)


def kind_instance():
    return ValueError(GKEY), None, None


run("E11", "kind 자리에 예외 인스턴스", kind_instance)


def kind_instance_with_value():
    return ValueError(GKEY), ValueError(UPATH), None


run("E12", "kind 인스턴스 + value 예외", kind_instance_with_value)

# ---- F. 시각 이상 ----------------------------------------------------------------------------------------------------------------------


def clock_case(case, how, clock):
    log, root = fresh(clock=clock)
    try:
        returned = log.record("main", ValueError, raise_and_catch(ValueError, "x"))
    except BaseException as error:  # noqa: BLE001
        results.append((case, how, "EXC:" + type(error).__name__, [], "RAISED", ["밖으로 예외"]))
        return
    judge(case, how, read_lines(root), returned)


KST = dt.timezone(dt.timedelta(hours=9))
clock_case("F01", "시계가 맨몸(naive) datetime", lambda: dt.datetime(2026, 1, 2, 3, 4, 5))
clock_case("F02", "시계가 KST(+9) aware", lambda: dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=KST))
clock_case("F03", "시계가 year 1 aware +14시간(UTC 변환 중 넘침)", lambda: dt.datetime(1, 1, 1, 0, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=14))))
clock_case("F04", "시계가 year 9999 aware -14시간(넘침)", lambda: dt.datetime(9999, 12, 31, 23, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=-14))))
clock_case("F05", "시계가 예외를 던짐", lambda: (_ for _ in ()).throw(RuntimeError("시계 고장")))
clock_case("F06", "시계가 글을 돌려줌", lambda: GKEY)
clock_case("F07", "시계가 None", lambda: None)
clock_case("F08", "시계가 strftime 이 엉뚱한 글을 주는 객체", lambda: types.SimpleNamespace(tzinfo=None, strftime=lambda fmt: GKEY + " " + UPATH))
clock_case("F09", "시계가 year 1 naive(윈도 strftime)", lambda: dt.datetime(1, 1, 1))

# ---- G. Qt ----------------------------------------------------------------------------------------------------------------------------


def qt_case(case, how, message_type, context):
    run(case, how, lambda: (message_type, context), qt=True)


CRIT = types.SimpleNamespace(name="QtCriticalMsg")
FATAL = types.SimpleNamespace(name="QtFatalMsg")
qt_case("G01", "Qt Critical, 분류에 경로·키", CRIT, types.SimpleNamespace(category="qt.qpa; " + UPATH, file=UPATH, line=5))
qt_case("G02", "Qt Fatal, 분류가 64자 넘는 글", FATAL, types.SimpleNamespace(category="q" * 80, file="x.cpp", line=1))
qt_case("G03", "Qt Fatal, 파일이 키 모양, 줄이 글", FATAL, types.SimpleNamespace(category="qt.qpa.fonts", file=GKEY + ".cpp", line="7; --"))
qt_case("G04", "Qt Fatal, 비str 값들", FATAL, types.SimpleNamespace(category=b"qt.qpa", file=12345, line=None))
qt_case("G05", "Qt Critical, 줄 번호 음수·거대", CRIT, types.SimpleNamespace(category="qt.x", file="a.cpp", line=-9))
qt_case("G06", "Qt Critical, 줄 번호 1e12", CRIT, types.SimpleNamespace(category="qt.x", file="a.cpp", line=10 ** 12))
qt_case("G07", "Qt 종류가 번호 2(Critical)", 2, types.SimpleNamespace(category="qt.x", file=None, line=0))
qt_case("G08", "Qt 종류 이름이 'QtCriticalMsg' 인 가짜 + 컨텍스트 None", CRIT, None)

# ---- H. 동시 오류(여러 스레드) -----------------------------------------------------------------------------------------------------------


def threads_case():
    log, root = fresh()
    flags = []

    def work(kind):
        for _ in range(100):
            error = raise_and_catch(kind, "m " + GKEY)
            flags.append(log.record("thread", kind, error, error.__traceback__))
    threads = [threading.Thread(target=work, args=(kind,)) for kind in (ValueError, KeyError, OSError, TypeError, IndexError, RuntimeError, ZeroDivisionError, AttributeError)]
    orig = errorlog.LOCK_WAIT
    errorlog.LOCK_WAIT = 60.0
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        errorlog.LOCK_WAIT = orig
    lines = read_lines(root)
    bad = [line for line in lines if not STRICT.fullmatch(line)]
    notes = []
    verdict = "OK"
    if len(lines) != sum(1 for f in flags if f) or len(lines) != 800:
        verdict = "LEAK"
        notes.append("줄 수 %d, True 수 %d" % (len(lines), sum(1 for f in flags if f)))
    if bad:
        verdict = "LEAK"
        notes.append("형식 밖 줄 %d" % len(bad))
    results.append(("H01", "스레드 8개 x 100 동시 오류", "%d/%d True" % (sum(1 for f in flags if f), len(flags)), lines[:1], verdict, notes))


threads_case()

# ---- 결과 출력 -------------------------------------------------------------------------------------------------------------------------
worst = {"OK": 0, "MASKED": 1, "LEAK": 3, "RAISED": 3}
summary = {}
for case, how, returned, lines, verdict, notes in results:
    summary[verdict] = summary.get(verdict, 0) + 1
    shown = lines[0] if lines else "(줄 없음)"
    if len(shown) > 150:
        shown = shown[:150] + "...(%d자)" % len(shown)
    print("%s | %s | ret=%s | %s | %s %s" % (case, how, returned, shown, verdict, ";".join(notes)))
print("SUMMARY", summary, "total", len(results))
