"""AP14 소스 고치기 — 정확히 한 곳씩 바꾼다(옛 글이 정확히 한 번 나오지 않으면 실패). 줄 끝은 `doc_edit.py` 가 파일에 맞춘다.
사용: python -X utf8 apply_ap14_src.py <작업 폴더>"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1])
HERE = Path(__file__).resolve().parent
EDIT = HERE / "doc_edit.py"
SEC = "src/chanceblog_desktop/security/"

PAIRS = [
    # ---- boundary.py ----
    (SEC + "boundary.py",
     "import traceback\n\nfrom .mask import MAX_MASK_INPUT, mask\n",
     "import traceback\n\nfrom . import errorlog\nfrom .mask import MAX_MASK_INPUT, mask\n"),
    (SEC + "boundary.py",
     "가린 글**로 표준 오류에 남긴다(`--debug` 의 되던지기도 여기서 가려진다).",
     "가린 글**로 표준 오류에 남긴다(`--debug` 의 되던지기도 여기서 가려진다). 화면(GUI) 진입점이 오류 기록(`security/errorlog.py`, `arm_error_log`)을 켰다면 **오류 이름과 코드 위치만** 데이터 폴더의 작은 파일에도 남긴다(AP14 — 메시지 글은 읽지도 않는다)."),
    (SEC + "boundary.py",
     "같은 필터를 단다(로그 파일 핸들러는 만들지 않는다 — 없는 기능이다).",
     "같은 필터를 단다(`logging` 에 파일 핸들러를 달지 않는다 — 오류 기록 파일은 `logging` 을 쓰지 않는 `security/errorlog.py` 가 따로 쓴다)."),
    (SEC + "boundary.py",
     "(PySide6 는 그 함수 안에서만 불러온다 — 이 모듈을 불러온다고 Qt 가 필요하지 않다).",
     "(PySide6 는 그 함수 안에서만 불러온다 — 이 모듈을 불러온다고 Qt 가 필요하지 않다). 치명적(Critical·Fatal) 메시지는 종류·분류 이름만 오류 기록에도 남긴다(메시지 글은 읽지 않는다)."),
    (SEC + "boundary.py",
     "# ---- 처리하지 못한 예외 ---------------------------------------------------------------------------------------------------------------------\n"
     "def _excepthook(kind, value, trace):\n"
     "    report_exception(kind, value, trace)\n",
     "# ---- 처리하지 못한 예외 ---------------------------------------------------------------------------------------------------------------------\n"
     "def _record(source, kind, value, trace):\n"
     "    \"\"\"처리하지 못한 오류를 오류 기록 파일에도 남긴다(`arm_error_log` 로 켜졌을 때만 — 꺼져 있으면 아무 일도 없다). 오류를 처리하는 중에 불리므로 어떤 오류도 다시 내지 않는다.\"\"\"\n"
     "    try:\n"
     "        return errorlog.record_exception(source, kind, value, trace)\n"
     "    except Exception:\n"
     "        return False\n"
     "\n"
     "\n"
     "def _record_qt(message_type, context):\n"
     "    try:\n"
     "        return errorlog.record_qt(message_type, context)\n"
     "    except Exception:\n"
     "        return False\n"
     "\n"
     "\n"
     "def _excepthook(kind, value, trace):\n"
     "    _record(\"main\", kind, value, trace)\n"
     "    report_exception(kind, value, trace)\n"),
    (SEC + "boundary.py",
     "    if args.exc_type is SystemExit:                       # 기본 훅도 스레드의 SystemExit 는 조용히 넘긴다\n"
     "        return\n"
     "    name = getattr(args.thread, \"name\", None) or \"(이름 없는 스레드)\"\n",
     "    if args.exc_type is SystemExit:                       # 기본 훅도 스레드의 SystemExit 는 조용히 넘긴다\n"
     "        return\n"
     "    _record(\"thread\", args.exc_type, args.exc_value, getattr(args, \"exc_traceback\", None))\n"
     "    name = getattr(args.thread, \"name\", None) or \"(이름 없는 스레드)\"\n"),
    (SEC + "boundary.py",
     "def _unraisablehook(unraisable):\n"
     "    try:\n",
     "def _unraisablehook(unraisable):\n"
     "    _record(\"unraisable\", getattr(unraisable, \"exc_type\", None), getattr(unraisable, \"exc_value\", None), getattr(unraisable, \"exc_traceback\", None))\n"
     "    try:\n"),
    (SEC + "boundary.py",
     "def _qt_handler(message_type, context, message):\n"
     "    try:\n"
     "        shown = mask_block(message)\n",
     "def _qt_handler(message_type, context, message):\n"
     "    _record_qt(message_type, context)                      # 종류·분류 이름·C++ 쪽 파일:줄만 — 메시지 글은 기록 쪽으로 넘기지 않는다\n"
     "    try:\n"
     "        shown = mask_block(message)\n"),
    (SEC + "boundary.py",
     "__all__ = [\"BLOCK_LIMIT\", \"HOLD_LINE_LIMIT\", \"Installed\", \"PENDING_HARD_LIMIT\", \"PENDING_LIMIT\", \"QtHandle\", \"RedactingStream\", \"active\", \"format_exception_masked\", \"install\", \"install_gui\", \"install_qt_message_handler\",\n"
     "           \"mask_block\", \"mask_deep\", \"report_exception\"]\n",
     "def arm_error_log(resolve_folder):\n"
     "    \"\"\"화면(GUI) 진입점이 부른다 — 지금 깔린 경계에 오류 기록(`security/errorlog.py`)을 이어 붙인다(AP14, D-488). `resolve_folder` 는 처음 쓸 때 부를 '데이터 폴더 알려 주기' 함수다 — 켜는 것만으로는 아무것도 읽거나 만들지 않는다.\n"
     "    경계가 깔려 있지 않으면 아무것도 하지 않고 False. 경계를 되돌리면(`uninstall`) 오류 기록도 함께 꺼진다. 명령줄 진입점과 예시 화면은 부르지 않는다.\"\"\"\n"
     "    with _LOCK:\n"
     "        installed = _ACTIVE\n"
     "        if installed is None:\n"
     "            return False\n"
     "        log = errorlog.arm(resolve_folder)\n"
     "        installed._undo.append(lambda: errorlog.disarm(log))\n"
     "        return True\n"
     "\n"
     "\n"
     "__all__ = [\"BLOCK_LIMIT\", \"HOLD_LINE_LIMIT\", \"Installed\", \"PENDING_HARD_LIMIT\", \"PENDING_LIMIT\", \"QtHandle\", \"RedactingStream\", \"active\", \"arm_error_log\", \"format_exception_masked\", \"install\", \"install_gui\", \"install_qt_message_handler\",\n"
     "           \"mask_block\", \"mask_deep\", \"report_exception\"]\n"),
    # ---- app_state.py ----
    ("src/chanceblog_desktop/ui/core/app_state.py",
     "에서는 남길 곳이 없어 False 를 돌려준다(`print(file=None)` 은 표준 출력으로 가므로 그대로 두면 아무것도 안 남았는데 True 가 된다) — 이 묶음은 파일을 쓰지 않는다(읽기 전용);\n"
     "    로그 파일은 설치 파일 묶음에서 정한다.\"\"\"\n"
     "    target = stream if stream is not None else sys.stderr\n"
     "    if target is None:\n"
     "        return False\n",
     "에서는 표준 오류에 남길 곳이 없어 False 를 돌려준다(`print(file=None)` 은 표준 출력으로 가므로 그대로 두면 아무것도 안 남았는데 True 가 된다) — 대신 **작은 오류 기록 파일**(`security/errorlog.py` — 화면 진입점이 켰을 때만,\n"
     "    오류 이름과 코드 위치뿐, AP14·D-488)에 한 줄이 남는다. 그 파일을 쓰지 못해도 이 함수의 한 줄 출력과 앱은 그대로다.\"\"\"\n"
     "    try:\n"
     "        from ...security import errorlog                                                   # 늦게 — 오류를 처리하는 중에만 필요하다. 표준 오류가 없어도 파일에는 남긴다\n"
     "        errorlog.record_exception(\"slot\", kind, value)\n"
     "    except Exception:                                                                       # 기록이 안 돼도 아래 한 줄 출력과 앱은 그대로다(이 함수는 오류를 처리하는 중에 불린다)\n"
     "        pass\n"
     "    target = stream if stream is not None else sys.stderr\n"
     "    if target is None:\n"
     "        return False\n"),
    # ---- launcher.py ----
    ("src/chanceblog_desktop/ui/launcher.py",
     "종료 코드는 명령줄의 사용법 오류와 같은 2 이다.\n\"\"\"\n",
     "종료 코드는 명령줄의 사용법 오류와 같은 2 이다.\n\n"
     "**처리하지 못한 오류는 작은 기록 파일에도 남는다**(AP14, `security/errorlog.py`) — 내 데이터 화면만(`--sample` 은 아무것도 저장하지 않으므로 켜지 않는다) 켜고, 앱을 켜기만 해서는 파일을 만들지 않으며 첫 오류가 날 때 데이터 폴더의 `logs/errors.log` 를 처음 만든다.\n\"\"\"\n"),
    ("src/chanceblog_desktop/ui/launcher.py",
     "def main(argv=None, *, out=None):\n",
     "def _data_folder_of(data_dir):\n"
     "    \"\"\"오류 기록이 **처음 쓸 때** 부를 '데이터 폴더 알려 주기' — 앱이 쓰는 해석 함수(`Workspace.resolve`) 그대로다(새 경로 계산이 없다). 부르기 전에는 아무것도 읽거나 만들지 않고, 안쪽에서 서비스를 늦게 가져온다.\"\"\"\n"
     "    def resolve():\n"
     "        from ..service.context import Workspace\n"
     "        return Workspace.resolve(data_dir).root\n"
     "    return resolve\n"
     "\n"
     "\n"
     "def main(argv=None, *, out=None):\n"),
    # ---- backup_note.py ----
    (SEC + "backup_note.py",
     "    (\"로그·디버그 기록\", \"이 앱은 로그 파일을 만들지 않고, 있어도 담지 않아요\"),\n",
     "    (\"logs/\", \"앱이 처리하지 못한 오류가 났을 때만 처음 만들어지는 작은 기록이에요(오류 이름과 코드 위치뿐). 이 PC 에서 문제를 살필 때 쓰는 것이라 담지 않아요\"),\n"),
]


def run(*args):
    done = subprocess.run([sys.executable, "-X", "utf8", str(EDIT), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    print(done.stdout.strip() or done.stderr.strip())
    if done.returncode:
        raise SystemExit(done.returncode)


shutil.copyfile(HERE / "draft" / "errorlog.py", ROOT / SEC / "errorlog.py")
print("errorlog.py 복사")
with tempfile.TemporaryDirectory() as folder:
    for index, (rel, old, new) in enumerate(PAIRS):
        old_file, new_file = Path(folder) / f"old{index}.txt", Path(folder) / f"new{index}.txt"
        old_file.write_text(old, encoding="utf-8", newline="\n")
        new_file.write_text(new, encoding="utf-8", newline="\n")
        run("replace", ROOT / rel, old_file, new_file)
