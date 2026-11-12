"""그림자 실행(SHADOW_RUN) — 정지(PIPELINE_PAUSE)를 유지한 채 실제 후보 글을 읽기 전용으로 만들어 평가하는 실행 경로.

배경: PIPELINE_PAUSE 가 켜져 있으면 모든 실행이 건너뛴다. 제한 재개 조건(그림자 모드 3회·초안 10개 이상 평가)을 정지를 유지한 채 얻으려면 쓰기 권한이 없는 별도 실행이 필요하다.
generator.py 는 환경 변수 SHADOW_RUN=1 일 때 main() 에서 이 모듈의 run() 으로 넘어온다(정지 검사를 건너뛰는 것은 이 모드 안에서만이고 정지 변수는 그대로다).

읽기 전용은 약속이 아니라 코드로 강제된다:
- 이 모듈은 저장소 파일(_posts·history.json 등)을 쓰는 함수를 부르지 않는다. 결과는 SHADOW_OUT 아래에만 쓰며, 쓰는 길은 ShadowWriter 하나(경로가 SHADOW_OUT 밖이면 거절)뿐이다.
- 이 모듈은 subprocess 를 부르지 않고(git·gh 를 막으려고 Popen 을 바꿔 끼울 뿐이다) git·gh·승인 흐름 실행부(git 을 부르는 모듈)를 읽지도 않는다.
- run() 이 도는 동안 read_only() 가 generator 의 쓰기 함수(write_text_atomic·write_history·write_step_summary·trigger_download·fix_images·pick_images)를 '부르면 ShadowViolation' 으로 바꾸고,
  git·gh 를 부르는 프로세스(subprocess.Popen·os.system·os.popen)를 같은 예외로 막는다. SHADOW_OUT 밖의 파일을 만들거나 바꾸거나 지우는 일은 open·pathlib·os·shutil·tempfile 어느 길로
  하든 파이썬 감사 훅(sys.addaudithook)이 같은 예외로 막는다(어기면 실행이 빨강으로 끝난다).
- 하루 상한·슬롯 규칙은 보지 않고 SHADOW_COUNT(기본 3, 상한 5)건의 후보만 시도한다.

이 모듈은 오프라인 측정 도구를 불러오지 않는다 — 측정은 워크플로가 두 번째 단계에서 별도 프로세스로 한다(연결 금지, 시험이 소스를 읽어 확인한다).
출력 형식과 설정은 docs/QUALITY_GATE.md 에 있다.

구조화 Fact 분기(레지스트리 chance.content_source: facts, S2b): 같은 읽기 전용 구간 안에서 `run_facts` 가 후보를 **AI 없이** 만든다 — 일반 실행과 같은 함수(`g.fact_prepare`: 이력의 발행일로 차례를 정하는 공급 함수 →
어댑터 → 조립기)를 쓰고 Gemini·피드·사진을 부르지 않는다(Gemini 키도 필요 없다). 만든 글은 최소 품질 Gate 를 **항상** 돌려 평가하고(일반 그림자 실행과 같다) 결과는 같은 모양(`result.json`·`run.json`)으로 SHADOW_OUT 아래에만 쓴다.
네트워크 읽기는 허용 목록 관문·호출 예산을 거치는 읽기뿐이다(저장소·git·gh 에는 쓰지 않는다 — 읽기 전용 구간의 방어 코드가 그대로 감시한다). 설명: docs/FACT_PATH.md §15
"""
import contextlib
import copy
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pipeline import quality_gate, registry, source_policy

SCHEMA = 1
DEFAULT_COUNT = 3
MAX_COUNT = 5
POST_KIND = {"ko": "KR", "en": "EN"}          # 글 파일 이름의 종류 칸. 이름은 `YYYY-MM-DD-KR-HHMMSS.md` / `-EN-` 모양이다(생성기의 글 파일 이름 규칙과 같다 — 측정 도구가 변환 없이 읽는다)
RESULT_FILE = "result.json"
RUN_FILE = "run.json"
FORBIDDEN_PROGRAMS = ("git", "gh")
PLACEHOLDER_THUMBNAIL = re.compile(r"(?m)^!\[Thumbnail\]\(https://example\.invalid/[^)\n]*\)[ \t]*\n?")
PLACEHOLDER_IMAGE_LINE = re.compile(r"(?m)^image:[ \t]*\"?https://example\.invalid/[^\n]*\n")      # 머리말의 자리표시 대표 사진 줄(검증용 가짜 주소)
_WRITE_MODE = re.compile(r"[wax+]")
_BACKSLASH = chr(92)       # 역슬래시(경로 문자열을 소스에 적지 않으려고 글자 코드로 만든다)


class ShadowConfigError(ValueError):
    """SHADOW_OUT·SHADOW_COUNT 가 올바르지 않을 때(종료 코드 2)."""


class ShadowViolation(RuntimeError):
    """그림자 실행 안에서 쓰기·git·gh 를 시도했을 때. 이 예외는 삼키지 않는다 — 실행이 빨강으로 끝난다."""


# ----------------------------------------------------------------------------
# 설정 읽기(순수 — 환경 변수는 호출하는 쪽이 사전으로 넘긴다)
# ----------------------------------------------------------------------------
def resolve_count(environ):
    """SHADOW_COUNT → (후보 수, 안내 문구 목록). 비었으면 기본 3, 숫자가 아니면 기본 3, 1 미만이면 기본 3, 5 를 넘으면 5."""
    raw = str((environ or {}).get("SHADOW_COUNT", "")).strip()
    notes = []
    if not raw:
        return DEFAULT_COUNT, notes
    try:
        count = int(raw)
    except ValueError:
        return DEFAULT_COUNT, [f"SHADOW_COUNT 가 숫자가 아니라 기본 {DEFAULT_COUNT}건을 씁니다"]
    if count < 1:
        return DEFAULT_COUNT, [f"SHADOW_COUNT 가 1 미만이라 기본 {DEFAULT_COUNT}건을 씁니다"]
    if count > MAX_COUNT:
        return MAX_COUNT, [f"SHADOW_COUNT 가 상한을 넘어 {MAX_COUNT}건으로 줄입니다"]
    return count, notes


def resolve_out_dir(environ, repo_roots=()):
    """SHADOW_OUT → 결과를 쓸 폴더(Path). 안전 조건: 절대 경로여야 하고, 저장소 작업 폴더(repo_roots)의 안이나 그 위(조상)가 아니어야 하며, 파일이 아니고 비어 있거나 없는 폴더여야 한다.
    조건을 어기면 ShadowConfigError — 저장소 안에 결과를 쓰면 이후 단계가 그 파일을 커밋할 수 있어 막는다."""
    raw = str((environ or {}).get("SHADOW_OUT", "")).strip()
    if not raw:
        raise ShadowConfigError("SHADOW_OUT(결과를 쓸 임시 폴더)이 없습니다.")
    if "\x00" in raw:
        raise ShadowConfigError("SHADOW_OUT 에 올바르지 않은 글자가 있습니다.")
    if raw.startswith((_BACKSLASH * 2, "//")):          # Windows 확장 경로 접두사(역슬래시 둘 + ? 또는 .)와 UNC 공유 경로 — 접두사가 붙은 경로는 실경로를 풀어도 저장소 안인지 가릴 수 없어 통째로 거절한다
        raise ShadowConfigError("SHADOW_OUT 은 로컬 절대 경로여야 합니다(Windows 확장 경로 접두사와 UNC 경로는 거절).")
    path = Path(raw)
    if not path.is_absolute():
        raise ShadowConfigError("SHADOW_OUT 은 절대 경로여야 합니다.")
    resolved = Path(os.path.realpath(raw))        # 심볼릭 링크·정션·8.3 짧은 이름을 풀어 실경로로 견준다
    if resolved.parent == resolved or len(resolved.parts) < 2:
        raise ShadowConfigError("SHADOW_OUT 이 디스크의 맨 위 폴더입니다.")
    out_key = _normal(resolved)
    for root in repo_roots:
        root_key = _normal(root)
        if out_key == root_key or out_key.startswith(root_key + os.sep) or root_key.startswith(out_key + os.sep):
            raise ShadowConfigError("SHADOW_OUT 은 저장소 작업 폴더 밖의 임시 폴더여야 합니다(안이거나 그 위 폴더면 거절).")
    if resolved.exists():
        if not resolved.is_dir():
            raise ShadowConfigError("SHADOW_OUT 이 폴더가 아닙니다.")
        if any(resolved.iterdir()):
            raise ShadowConfigError("SHADOW_OUT 이 비어 있지 않습니다(이전 결과와 섞이지 않게 비어 있거나 없는 폴더를 쓰세요).")
    return resolved


# ----------------------------------------------------------------------------
# 쓰기 — SHADOW_OUT 아래로만
# ----------------------------------------------------------------------------
class ShadowWriter:
    """결과 파일을 쓰는 유일한 길. 상대 경로를 SHADOW_OUT 아래로만 풀고(밖이면 ShadowViolation), 임시 파일을 거쳐 교체한다."""

    def __init__(self, root):
        self.root = Path(root).resolve()

    def ensure_root(self):
        """결과 폴더 자체를 만든다(없으면). 읽기 전용 구간에 들어가기 전에 한 번 부른다 — 구간 안에서는 SHADOW_OUT 밖(그 위 폴더)을 만들 수 없다."""
        self.root.mkdir(parents=True, exist_ok=True)

    def target(self, relative):
        rel = Path(str(relative))
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise ShadowViolation(f"결과 파일 경로가 올바르지 않습니다: {str(relative)[:60]!r}")
        target = (self.root / rel).resolve()
        if self.root not in target.parents:
            raise ShadowViolation("결과 파일이 SHADOW_OUT 밖입니다.")
        return target

    def write(self, relative, text):
        target = self.target(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(target)
        return target

    def write_json(self, relative, value):
        return self.write(relative, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


_COMMAND_SPLIT = re.compile(r"[\s;&|<>()\"'`,\[\]{}=]+")


def _command_tokens(value):
    """명령(문자열·바이트·경로·낱말 목록)을 프로그램 이름 후보 낱말들로 쪼갠다: 경로는 마지막 조각, .exe 는 뗀다, 소문자."""
    if isinstance(value, (list, tuple)):
        return [token for item in value for token in _command_tokens(item)]
    try:
        text = os.fsdecode(value)
    except (TypeError, ValueError):
        return []
    tokens = []
    for piece in _COMMAND_SPLIT.split(text):
        name = piece.replace(_BACKSLASH, "/").rsplit("/", 1)[-1].lower()
        if name.endswith(".exe"):
            name = name[:-4]
        if name:
            tokens.append(name)
    return tokens


def _forbidden_command(*values):
    """실행하려는 명령에 git·gh 프로그램 이름이 낱말로 있나(첫 낱말만이 아니라 모든 낱말 — `cmd /c git …`·셸 한 줄 안의 `echo x && git …` 도 막는다). 이름 기반의 근사다:
    파이썬 -c 나 다른 프로그램을 거쳐 하는 일은 이 방식으로 알 수 없다(docs/QUALITY_GATE.md 한계)."""
    return any(token in FORBIDDEN_PROGRAMS for value in values for token in _command_tokens(value))


# ----------------------------------------------------------------------------
# 파일 쓰기 차단 — 파이썬 감사 훅(sys.addaudithook)
# ----------------------------------------------------------------------------
# open·os.open·pathlib·os·shutil·tempfile 어느 길로 부르든 파이썬은 같은 감사 이벤트를 낸다. 그래서 함수를 바꿔 끼우는 대신 이벤트에서 막는다 — 바꿔 끼우는 방식은
# 함수를 미리 쥐고 있는 코드를 놓친다(Python 3.10 의 pathlib 은 io.open 을 클래스를 만들 때 쥐고 있어 Path.write_text 가 빠져나갔다).
# 감사 훅은 한 번 달면 뗄 수 없다. 그래서 read_only() 구간이 끝나면 _GUARDS 가 비어 훅이 아무 일도 하지 않게 한다(구간 안에서만 켜져 있다).
_GUARDS = []            # 켜져 있는 읽기 전용 구간의 출력 폴더(_normal 로 고른 문자열) 스택
_HOOK = []              # 훅을 달았는지(한 번만 단다)
# O_TEMPORARY(Windows 에만 있다)는 읽기로 열어도 닫을 때 파일을 지운다 — 쓰기·삭제 깃발이므로 함께 본다.
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC | getattr(os, "O_EXCL", 0) | getattr(os, "O_TEMPORARY", 0)
# 이벤트 이름 → 쓰기·변경으로 보는 경로 인자의 위치. os.rename 은 두 경로 모두, os.symlink 는 새로 만드는 링크(심볼릭 링크는 열 때 실경로로 풀려 밖이면 막힌다), os.link 는 **원본과 새 경로 모두**
# (하드링크는 같은 파일의 다른 이름이라 실경로 비교로 알 수 없다 — 저장소 파일에 SHADOW_OUT 안의 이름을 붙인 뒤 쓰면 저장소 파일이 바뀐다), sqlite3.connect 는 데이터베이스 파일.
# 그 자리의 값이 정수(이미 열린 파일 번호)·None 이면 검사하지 않는다.
_PATH_EVENTS = {
    "os.mkdir": (0,), "os.remove": (0,), "os.rmdir": (0,), "os.truncate": (0,), "os.chmod": (0,), "os.chown": (0,), "os.utime": (0,), "os.mkfifo": (0,), "os.mknod": (0,),
    "os.setxattr": (0,), "os.removexattr": (0,), "os.rename": (0, 1), "os.symlink": (1,), "os.link": (0, 1), "sqlite3.connect": (0,),
    "shutil.copyfile": (1,), "shutil.copymode": (1,), "shutil.copystat": (1,), "shutil.copytree": (1,), "shutil.move": (0, 1), "shutil.rmtree": (0,), "shutil.chown": (0,),
    "shutil.make_archive": (0,), "shutil.unpack_archive": (1,),
}
# 폴더 번호(dir_fd)를 받는 이벤트 → `_PATH_EVENTS` 의 경로 위치와 같은 순서로 짝지은 dir_fd 인자 위치. 리눅스의 shutil.rmtree 는 `os.rmdir(이름, dir_fd=번호)`·`os.remove(이름, dir_fd=번호)` 처럼
# **열린 폴더 번호 + 짧은 이름**으로 지운다 — 짧은 이름은 현재 폴더가 아니라 그 번호가 가리키는 폴더 기준이다. 그래서 그 폴더의 실경로를 풀어 이름 앞에 붙인 뒤 비교한다(풀지 못하면 막는다 — fail closed).
# 열기 이벤트 `open` 에는 dir_fd 가 실리지 않는다 — 상대 경로로 dir_fd 를 써서 여는 쓰기는 이 방식으로 알 수 없다(docs/QUALITY_GATE.md 한계).
_DIR_FD_POSITIONS = {
    "os.rmdir": (1,), "os.remove": (1,), "os.mkdir": (2,), "os.chmod": (2,), "os.chown": (3,), "os.utime": (3,), "os.mkfifo": (2,), "os.mknod": (3,),
    "os.rename": (2, 3), "os.link": (2, 3), "os.symlink": (2,),
}
_NULL_DEVICES = frozenset({os.devnull.lower()})          # 자식 프로세스의 stdin/stdout 을 버릴 때 파이썬이 여는 장치(Windows 는 'nul', 그 밖은 '/dev/null' — Linux 에서 상대 경로 'nul' 은 일반 파일이다)
_MEMORY_DATABASES = frozenset({":memory:", ""})            # sqlite3 의 메모리·임시 데이터베이스는 파일이 아니다
_BYTECODE_FILE = re.compile(r"\.pyc(?:\.\d+)?$")
_BYTECODE_TEMP = re.compile(r"\.pyc\.\d+$")


def _normal(path):
    """경로를 비교하기 좋은 한 모양(절대·심볼릭 링크 해석·대소문자 규칙)으로 고른다. 없는 경로도 된다."""
    return os.path.normcase(os.path.realpath(os.fsdecode(path)))


def _bytecode_ok(event, resolved):
    """파이썬이 모듈을 처음 읽을 때 스스로 하는 일인가 — 막지 않는 것은 이것뿐이다: `__pycache__` 폴더를 새로 만들기(os.mkdir), 그 안에 .pyc(또는 임시 .pyc.숫자) 파일 쓰기(open),
    임시 파일을 .pyc 로 바꾸기(os.rename), 쓰다 만 임시 .pyc.숫자 파일 지우기(os.remove). 폴더 삭제·다른 이름의 파일·캐시 밖의 .pyc 는 막는다."""
    parts = resolved.split(os.sep)
    name = parts[-1]
    in_cache = len(parts) >= 2 and parts[-2] == "__pycache__"
    if event == "os.mkdir":
        return name == "__pycache__"
    if event in ("open", "os.rename"):
        return in_cache and bool(_BYTECODE_FILE.search(name))
    if event == "os.remove":
        return in_cache and bool(_BYTECODE_TEMP.search(name))
    return False


def _outside(value, root, event=""):
    """경로 value 가 root 밖이면 보여 줄 짧은 문구를, 안이거나 허용 예외(널 장치·메모리 데이터베이스·파이썬의 바이트코드 캐시 쓰기)면 None 을 돌려준다. 읽을 수 없는 경로는 밖으로 본다(fail closed)."""
    try:
        raw = os.fsdecode(value)
        if raw.lower() in _NULL_DEVICES or (event == "sqlite3.connect" and raw in _MEMORY_DATABASES):
            return None
        resolved = _normal(raw)
    except (TypeError, ValueError, OSError):
        return f"<{type(value).__name__}>"
    if resolved == root or resolved.startswith(root + os.sep) or _bytecode_ok(event, resolved):
        return None
    return raw[:80]


def _dir_fd_base(fd):
    """열린 폴더 번호 fd 가 가리키는 폴더의 실경로를 돌려준다. 리눅스는 /proc/self/fd/번호 로 푼다(그 밖의 운영체제·이미 닫힌 번호는 None — 호출한 쪽이 막는다)."""
    try:
        return os.readlink("/proc/self/fd/%d" % fd)
    except (OSError, ValueError, OverflowError):
        return None


def _with_dir_fd(value, dir_fd):
    """상대 경로 value 가 열린 폴더 번호(dir_fd)를 기준으로 쓰였다면 그 폴더의 실경로를 앞에 붙여 돌려준다. 절대 경로와 번호 없음(None·-1·True)은 그대로 돌려주고,
    폴더를 풀 수 없으면 None(막는다)을 돌려준다."""
    if not isinstance(dir_fd, int) or isinstance(dir_fd, bool) or dir_fd < 0:
        return value
    try:
        raw = os.fsdecode(value)
    except (TypeError, ValueError):
        return value                  # 이어지는 _outside 가 같은 이유로 '밖' 으로 본다
    if os.path.isabs(raw):
        return value
    base = _dir_fd_base(dir_fd)
    return None if base is None else os.path.join(base, raw)


def write_violation(event, args, root):
    """파이썬 감사 이벤트 하나가 root(= SHADOW_OUT, _normal 로 고른 문자열) 밖의 파일을 만들거나 바꾸거나 지우는 일이면 이유 문구를, 아니면 None 을 돌려준다.
    순수 함수다 — 시험이 이벤트를 직접 넣어 본다. 읽기(열기만 하는 open)와 감시 대상이 아닌 이벤트는 None."""
    dir_fds = []
    if event == "open":
        path, mode, flags = (tuple(args) + (None, None, None))[:3]
        writing = (isinstance(flags, int) and bool(flags & _WRITE_FLAGS)) or (isinstance(mode, str) and bool(_WRITE_MODE.search(mode)))
        targets = [path] if writing else []
    elif event in _PATH_EVENTS:
        try:
            targets = [args[index] for index in _PATH_EVENTS[event]]
            dir_fds = [args[index] for index in _DIR_FD_POSITIONS.get(event, ())]
        except (IndexError, TypeError):
            return f"{event}: 이벤트 인자를 읽지 못해 막습니다"
    else:
        return None
    for position, value in enumerate(targets):
        if value is None or isinstance(value, int):          # 경로가 아니거나 이미 열린 파일 번호
            continue
        value = _with_dir_fd(value, dir_fds[position] if position < len(dir_fds) else None)
        if value is None:
            return f"{event}: 폴더 번호가 가리키는 폴더를 알 수 없어 막습니다"
        problem = _outside(value, root, event)
        if problem is not None:
            return f"{event}: {problem}"
    return None


# 프로세스를 만드는 이벤트와 프로그램 이름·인자가 든 위치(subprocess.Popen: 실행 파일·인자 목록, os.system: 명령 문자열, os.exec·os.posix_spawn: 경로·인자, os.spawn: 경로·인자).
# subprocess.Popen 이름을 바꿔 끼운 것(from subprocess import Popen 으로 미리 쥔 것)도 이벤트에서 잡는다.
_PROCESS_EVENTS = {"subprocess.Popen": (0, 1), "os.system": (0,), "os.exec": (0, 1), "os.posix_spawn": (0, 1), "os.spawn": (1, 2)}


def process_violation(event, args):
    """프로세스를 만드는 이벤트가 git·gh 를 부르는 일이면 이유 문구를, 아니면 None 을 돌려준다(순수 함수). 프로그램 이름은 첫 낱말만이 아니라 모든 낱말에서 찾는다(cmd /c git …·셸 한 줄 안의 git)."""
    positions = _PROCESS_EVENTS.get(event)
    if positions is None:
        return None
    try:
        values = [args[index] for index in positions]
    except (IndexError, TypeError):
        return f"{event}: 이벤트 인자를 읽지 못해 막습니다"
    return f"{event}: git·gh 호출" if _forbidden_command(*values) else None


def _audit(event, args):
    """sys.addaudithook 에 거는 훅. 읽기 전용 구간 밖(_GUARDS 가 빔)에서는 아무 일도 하지 않는다."""
    if not _GUARDS:
        return
    message = write_violation(event, args, _GUARDS[-1])
    if message is not None:
        raise ShadowViolation(f"그림자 실행은 SHADOW_OUT 밖의 파일을 만들거나 바꾸거나 지울 수 없습니다(읽기 전용) — {message}")
    message = process_violation(event, args)
    if message is not None:
        raise ShadowViolation(f"그림자 실행은 git·gh 를 부를 수 없습니다(읽기 전용) — {message}")


def _install_hook():
    if not _HOOK:
        sys.addaudithook(_audit)
        _HOOK.append(True)


@contextlib.contextmanager
def read_only(g, out_dir):
    """그림자 실행이 도는 동안 쓰기·git·gh 를 코드로 막는다. generator 의 쓰기 함수는 부르면 ShadowViolation, subprocess/os.system/os.popen 은 git·gh 일 때,
    SHADOW_OUT 밖의 파일을 만들거나 바꾸거나 지우는 일(open·pathlib·os·shutil·tempfile 어느 길이든)은 감사 훅이 ShadowViolation. 빠져나올 때(예외로 빠져나와도) 모두 원래대로 돌려놓는다."""
    root = _normal(out_dir)
    names = ("write_text_atomic", "write_history", "write_step_summary", "trigger_download", "fix_images", "pick_images")
    saved = {name: getattr(g, name) for name in names if hasattr(g, name)}
    real_popen, real_system, real_popen_os = subprocess.Popen, os.system, os.popen
    real_copy2 = shutil.copy2

    def guarded_copy2(src, dst, *, follow_symlinks=True):
        # Windows 의 Python 3.12 는 shutil.copy2 가 copyfile 을 거치지 않고 CopyFile2 를 바로 불러 감사 이벤트가 빠진다 — 같은 이벤트를 대신 내서 같은 판정을 받게 한다.
        sys.audit("shutil.copyfile", src, dst)
        return real_copy2(src, dst, follow_symlinks=follow_symlinks)

    def denied(name):
        def blocked(*args, **kwargs):
            raise ShadowViolation(f"그림자 실행은 {name} 을(를) 부를 수 없습니다(읽기 전용).")
        return blocked

    class GuardedPopen(real_popen):
        def __init__(self, args, *rest, **kwargs):
            if _forbidden_command(args):
                raise ShadowViolation("그림자 실행은 git·gh 를 부를 수 없습니다(읽기 전용).")
            super().__init__(args, *rest, **kwargs)

    def guarded_system(command):
        if _forbidden_command(command):
            raise ShadowViolation("그림자 실행은 git·gh 를 부를 수 없습니다(읽기 전용).")
        return real_system(command)

    def guarded_os_popen(command, *rest, **kwargs):
        if _forbidden_command(command):
            raise ShadowViolation("그림자 실행은 git·gh 를 부를 수 없습니다(읽기 전용).")
        return real_popen_os(command, *rest, **kwargs)

    for name in saved:
        setattr(g, name, denied(name))
    subprocess.Popen, os.system, os.popen = GuardedPopen, guarded_system, guarded_os_popen
    shutil.copy2 = guarded_copy2
    _install_hook()
    _GUARDS.append(root)
    try:
        yield
    finally:
        _GUARDS.pop()
        shutil.copy2 = real_copy2
        subprocess.Popen, os.system, os.popen = real_popen, real_system, real_popen_os
        for name, function in saved.items():
            setattr(g, name, function)


# ----------------------------------------------------------------------------
# 결과 만들기(순수)
# ----------------------------------------------------------------------------
def post_filename(lang, stamp):
    """글 파일 이름: 날짜-종류(KR·EN)-시각 6자리 .md. 같은 시도의 국문·영문은 같은 날짜·시각을 써서 측정 도구(번역 복제 쌍 만들기)가 한 쌍으로 읽는다. 종류가 없는 언어면 ValueError."""
    return f"{stamp:%Y-%m-%d}-{POST_KIND[lang]}-{stamp:%H%M%S}.md"


def attempt_stamp(now, attempt):
    """시도 번호마다 서로 다른 시각(시작 시각 + 번호 - 1 초)을 돌려준다 — 한 번의 실행 안에서 쌍 키(날짜·시각)가 겹치지 않는다(최대 5건)."""
    return now + datetime.timedelta(seconds=int(attempt) - 1)


def attempt_folder(number):
    """결과 폴더 이름: 시도 번호 두 자리(01·02 …)."""
    return f"{int(number):02d}"


def _line(text, limit=200):
    return quality_gate._safe(text, limit)


def build_result(attempt, outcome, hold_reasons, validation_reason, gate_input, gate_facts, evidence_chars, model, lane, item, titles, languages, files, generated_at):
    """한 후보의 result.json 내용. 모델·피드에서 온 글(제목·이유)은 한 줄로 소독한다. passed 는 '본문 검증을 통과했고 Gate 보류가 없다' 일 때만 참이다."""
    item = item if isinstance(item, dict) else {}
    published = item.get("published")
    reasons = [_line(r, 300) for r in hold_reasons]
    return {
        "schema": SCHEMA,
        "attempt": int(attempt),
        "passed": outcome == "PASSED",
        "outcome": outcome,
        "hold_reasons": reasons,
        "hold_codes": [r.split(" ", 1)[0].rstrip(":") for r in reasons],
        "validation": {"ok": outcome in ("PASSED", "HELD"), "reason": _line(validation_reason, 300)},      # 본문 검증(분량·원문 링크·머리말)까지 통과했나 — 모델이 건너뛰거나 응답 형식·제목이 걸린 후보는 거짓
        "gate": {"input": gate_input, "facts": gate_facts or {}},
        "source_text_chars": int(evidence_chars),
        "model": _line(model, 80) or "unknown",
        "lane": _line(lane, 40),
        "source_url": _line(item.get("link"), 400),
        "source_name": _line(item.get("source"), 120),
        "source_domain": _line(item.get("publisher_domain"), 120),
        "title_ko": _line(titles.get("ko"), 200),
        "title_en": _line(titles.get("en"), 200),
        "languages": list(languages),
        "files": dict(files),
        "published": published.isoformat() if hasattr(published, "isoformat") else "",
        "generated_at": generated_at,
    }


def _served_model(g, before):
    """이번 호출의 요청 기록(CallLog)에서 응답한 모델 이름. 기록이 없으면(가짜 응답·연습) 빈 문자열."""
    for record in reversed(getattr(getattr(g, "CALL_LOG", None), "records", [])[before:]):
        if getattr(record, "outcome", "") == "ok":
            return getattr(record, "served_model", "") or getattr(record, "model", "")
    return ""


def _finished_text(g, checked, item, prefix):
    """파일이 될 모양의 글: add_discovery_metadata(설명·출처 세 줄·출처 목록·고지문)를 더하고 자리표시 대표 사진 줄은 뺀다(사진은 평가 대상이 아니다)."""
    try:
        text = g.add_discovery_metadata(checked[f"{prefix}_content"], item)
    except Exception:    # noqa: BLE001 - 파일 만들기에 실패해도 평가 결과는 남긴다(검증된 글 그대로)
        text = checked[f"{prefix}_content"]
    return PLACEHOLDER_IMAGE_LINE.sub("", PLACEHOLDER_THUMBNAIL.sub("", text)).rstrip() + "\n"


def _evaluate(g, item, lane, attempt, ctx):
    """후보 하나: 모델 호출 → 읽기 → 건너뜀·제목 유사도·본문 검증 → Gate. 돌려주는 값: (result dict, 파일 {상대 경로: 글})."""
    languages, lang_args = ctx["languages"], ctx["lang_args"]
    prefixes = ("kr", "en") if tuple(languages) == ("ko", "en") else ("kr",)
    folder = attempt_folder(attempt)
    stamp = attempt_stamp(ctx["now"], attempt)
    topic = item.get("title")
    ctx["out"](f"[그림자 {folder}] 후보: {_line(topic or '(자동 선정)', 120)} [{_line(item.get('source'), 40)}] 분야 {lane}")
    candidate, model = None, ""
    if g.STUB_GEMINI:
        candidate = g.stub_post_data(topic, item.get("link"))
        model = "stub"
    else:
        prompt = g.build_post_prompt(item, ctx["recent_titles"], "", allow_skip=True, editorial_lane=lane, **lang_args)
        before = len(getattr(getattr(g, "CALL_LOG", None), "records", []))
        response = g.call_gemini_with_fallback(prompt)          # 모든 모델이 실패하면 RuntimeError 가 그대로 올라간다(인프라 장애 = 빨강, 일반 실행과 같다)
        model = _served_model(g, before)
        try:
            candidate = g.extract_json_object(response.text)
        except ValueError as exc:
            reason = f"REJECT-FORMAT: 응답 형식 오류 — {type(exc).__name__}"
            return _result(attempt, "REJECTED_FORMAT", [reason], str(exc).split(":", 1)[0], "none", None, item, lane, model, {}, languages, {}, ctx), {}
    titles = {"ko": str(candidate.get("kr_title", "")), "en": str(candidate.get("en_title", "")) if len(prefixes) == 2 else ""}
    files = {"ko": candidate.get("kr_content"), "en": candidate.get("en_content") if len(prefixes) == 2 else None}
    if candidate.get("skip") is True:
        reason = f"REJECT-SKIP: 모델이 건너뜀 — {_line(candidate.get('reason', ''), 120)}"
        return _result(attempt, "REJECTED_SKIP", [reason], "모델이 건너뜀(skip)", "none", None, item, lane, model, titles, languages, {}, ctx), {}
    if any(g.is_similar_to_any(title, ctx["titles"], 0.7) for title in (titles["ko"], titles["en"]) if title):
        reason = "REJECT-SIMILAR: 생성된 제목이 기존 글과 비슷함(유사도 0.70 이상)"
        return _result(attempt, "REJECTED_SIMILAR", [reason], "제목이 기존 글과 비슷", "none", None, item, lane, model, titles, languages, {}, ctx), {}
    validation_reason, checked, gate_input = "", None, "none"
    try:
        checked = g.validate_post_data(copy.deepcopy(candidate), "https://example.invalid/kr.jpg", "https://example.invalid/en.jpg",
                                       verified_source_url=item.get("link"), **lang_args)
        g.check_final_front_matter(checked, item, **lang_args)
    except ValueError as exc:
        validation_reason = _line(exc, 300)
    gate_data = checked if checked is not None else candidate        # 검증에 실패한 글도 Gate 를 돌려 '모든 규칙을 적용하면 어떤가'를 본다(원본 그대로)
    gate_input = "validated" if checked is not None else "raw"
    report = quality_gate.check_candidate(gate_data, item, ctx["history"], ctx["config"], as_of=ctx["as_of"])
    reasons = ([f"REJECT-BODY: {validation_reason}"] if validation_reason else []) + report.lines()
    outcome = "REJECTED_BODY" if validation_reason else ("HELD" if report.holds else "PASSED")
    out_files = {}
    for lang, prefix in (("ko", "kr"), ("en", "en")):
        if prefix not in prefixes:
            continue
        if checked is not None and not validation_reason:
            text = _finished_text(g, checked, item, prefix)
        else:
            text = files[lang] if isinstance(files[lang], str) else None
        if text is not None:
            out_files[f"{folder}/{post_filename(lang, stamp)}"] = text
    names = {lang: post_filename(lang, stamp) for lang in ("ko", "en") if f"{folder}/{post_filename(lang, stamp)}" in out_files}
    result = _result(attempt, outcome, reasons, validation_reason, gate_input, report.facts, item, lane, model, titles, languages, names, ctx, evidence_chars=report.facts.get("source_text_chars"))
    return result, out_files


def _result(attempt, outcome, reasons, validation_reason, gate_input, facts, item, lane, model, titles, languages, names, ctx, evidence_chars=None):
    if evidence_chars is None:
        evidence_chars = quality_gate.evidence_text(item).summary_chars
    return build_result(attempt, outcome, reasons, validation_reason, gate_input, facts, evidence_chars, model, lane, item, titles, languages, names, ctx["generated_at"])


# ----------------------------------------------------------------------------
# 구조화 Fact 분기(AI 없음)
# ----------------------------------------------------------------------------
def facts_branch_on():
    """레지스트리 content_source 가 facts 인가. 읽지 못하거나 값이 올바르지 않으면 False — 기본(feed)은 이전과 같고, 뒤이은 `registry.chance_settings()` 가 같은 이유로 멈춘다."""
    try:
        return source_policy.chance_content_source() == source_policy.CONTENT_FACTS
    except Exception:       # noqa: BLE001 — 값을 알 수 없으면 Fact 분기로 가지 않는다
        return False


def run_facts(g, config, languages, writer, out, count, notes):
    """그림자 실행의 구조화 Fact 분기(읽기 전용 구간 안에서 부른다). 켜기 전 안전장치(`g.fact_context` — 하나라도 아니면 후보 0건으로 끝)를 지나면 `g.fact_prepare`(일반 실행과 같은 공급 함수)로 후보를 count 건까지
    만들고, 후보마다 최소 품질 Gate 를 돌려 결과를 SHADOW_OUT 아래에 쓴다(형식은 일반 그림자 실행과 같다: 번호 폴더의 글 파일·result.json, 맨 위 run.json). AI 는 부르지 않는다. 돌려주는 값: run.json 내용."""
    history = g.read_history()
    now = g.now_kst()
    problems, sources, provider, access = g.fact_context(now)
    out(f"[그림자] 구조화 Fact 분기를 시작합니다(후보 {count}건까지, AI 호출 없음, 결과 폴더는 저장소 밖 임시 폴더).")
    prepared, fact_notes = [], []
    if problems:
        out("::notice::[그림자] 구조화 Fact 분기를 시작하지 않습니다 — " + _line(" / ".join(problems), 300))
    else:
        prepared, supplied = g.fact_prepare(now, history, sources, provider, access, limit=count, gate_config=None)
        fact_notes = g.fact_notes(supplied)
    for note in fact_notes:
        out(f"[그림자] {_line(note, 200)}")
    summaries = []
    for attempt, item in enumerate(prepared, start=1):
        folder, stamp, post = attempt_folder(attempt), attempt_stamp(now, attempt), item.post
        report = quality_gate.check_candidate({"kr_title": post.title, "kr_content": item.content}, item.gate_source, history, config, as_of=now.date())
        outcome = "HELD" if report.holds else "PASSED"
        name = post_filename("ko", stamp)
        feed_shaped = {"link": post.source_url, "source": post.source_name, "publisher_domain": post.source_domain}
        result = build_result(attempt, outcome, report.lines(), "", "validated", report.facts, len(item.gate_source["evidence_text"]), "rule", "facts", feed_shaped,
                              {"ko": post.title, "en": ""}, languages, {"ko": name}, now.isoformat())
        writer.write(f"{folder}/{name}", item.marked)
        writer.write_json(f"{folder}/{RESULT_FILE}", result)
        summaries.append({"attempt": attempt, "passed": result["passed"], "outcome": outcome, "hold_codes": result["hold_codes"], "lane": result["lane"]})
        out(f"[그림자 {folder}] {'통과' if result['passed'] else '보류'}" + (f" [{', '.join(dict.fromkeys(result['hold_codes']))}]" if result["hold_codes"] else "") + f" — {_line(post.title, 80)}")
    attempts = len(prepared)
    passed = sum(1 for summary in summaries if summary["passed"])
    run_info = {"schema": SCHEMA, "requested": count, "attempts": attempts, "passed": passed, "held_or_rejected": attempts - passed, "languages": list(languages),
                "outcome": "COMPLETED" if attempts else "NO_CANDIDATES", "lanes_tried": [g.FACT_LANE_LABEL], "notes": list(notes) + [_line(text, 200) for text in problems + fact_notes],
                "generated_at": now.isoformat(), "attempts_summary": summaries}
    writer.write_json(RUN_FILE, run_info)
    out(f"SHADOW_DONE attempts={attempts} passed={passed} held_or_rejected={attempts - passed}")
    if not attempts:
        out(f"::warning::그림자 실행: 평가할 후보가 없었습니다({run_info['outcome']}).")
    return run_info


# ----------------------------------------------------------------------------
# 진입점
# ----------------------------------------------------------------------------
def run(g, environ=None, out=print):
    """그림자 실행 한 번. g 는 generator 모듈(후보 수집·프롬프트·검증 함수를 그대로 쓴다). 결과는 SHADOW_OUT 아래에만 쓴다.
    종료 정책: 정상(후보가 하나도 통과하지 못해도)은 반환, 설정 오류는 SystemExit(2), 모든 모델 실패·소스 접속 실패·쓰기 시도는 예외·SystemExit(1)."""
    environ = os.environ if environ is None else environ
    roots = [Path(g.__file__).resolve().parent, Path.cwd().resolve()]
    try:
        out_dir = resolve_out_dir(environ, roots)
    except ShadowConfigError as exc:
        out(f"::error::그림자 실행 설정 오류: {_line(exc, 200)}")
        raise SystemExit(2)
    count, notes = resolve_count(environ)
    for note in notes:
        out(f"::notice::{note}")
    if str(environ.get("PIPELINE_PAUSE", "")).strip().lower() in {"1", "true", "yes", "on"}:
        out("::notice::PIPELINE_PAUSE 가 켜져 있지만 그림자 실행은 읽기 전용이라 건너뛰지 않습니다(정지 변수는 그대로 둡니다).")
    facts_mode = facts_branch_on()
    if g.STUB_GEMINI and not g.DRY_RUN and not facts_mode:
        raise RuntimeError("GEMINI_API_KEY 환경 변수가 없습니다. 그림자 실행은 실제 모델로 후보 글을 만듭니다.")
    settings = registry.chance_settings()
    languages = settings.languages
    profiles = tuple(registry.load_profile(name) for name in quality_gate.HEALTH_PROFILE_NAMES)
    config = quality_gate.GateConfig(health_profiles=profiles, languages=languages)     # 그림자 실행은 레지스트리의 quality_gate 값과 상관없이 Gate 를 항상 적용한다
    writer = ShadowWriter(out_dir)
    writer.ensure_root()
    with read_only(g, out_dir):
        if facts_mode:      # 구조화 Fact 분기: 후보를 공급 함수로만 만들고(AI 없음) 아래 피드 후보 반복문으로 내려가지 않는다 — 읽기 전용 구간은 그대로 지켜진다
            return run_facts(g, config, languages, writer, out, count, notes)
        history = g.read_history()
        posts = g.load_posts()
        now = g.now_kst()
        lane_order = g.editorial_lane_order(None, history, now)
        titles = g.existing_titles(history, posts)
        ctx = {"languages": languages, "lang_args": {} if tuple(languages) == ("ko", "en") else {"languages": languages}, "config": config, "out": out,
               "history": history, "titles": titles, "recent_titles": titles[-30:], "as_of": now.date(), "now": now, "generated_at": now.isoformat()}
        report, summaries, attempts, seen_links = {"lanes": []}, [], 0, set()
        out(f"[그림자] 읽기 전용 실행을 시작합니다(후보 {count}건, 언어 {'·'.join(languages)}, 결과 폴더는 저장소 밖 임시 폴더).")
        for lane, found in g.iter_candidate_lanes(titles, False, lane_order, report):
            for item in found:
                if attempts >= count:
                    break
                link = str(item.get("link") or "")
                if link and link in seen_links:       # 같은 기사가 두 분야에 오르면 한 번만 평가한다
                    continue
                seen_links.add(link)
                attempts += 1
                result, files = _evaluate(g, item, lane, attempts, ctx)
                for relative, text in files.items():
                    writer.write(relative, text)
                writer.write_json(f"{attempt_folder(attempts)}/{RESULT_FILE}", result)
                summaries.append({"attempt": attempts, "passed": result["passed"], "outcome": result["outcome"], "hold_codes": result["hold_codes"], "lane": result["lane"]})
                out(f"[그림자 {attempt_folder(attempts)}] {'통과' if result['passed'] else '보류·탈락'}"
                    + (f" [{', '.join(dict.fromkeys(result['hold_codes']))}]" if result["hold_codes"] else "") + f" — {_line(result['title_ko'] or result['source_url'], 80)}")
            if attempts >= count:
                break
        passed = sum(1 for s in summaries if s["passed"])
        run_info = {"schema": SCHEMA, "requested": count, "attempts": attempts, "passed": passed, "held_or_rejected": attempts - passed, "languages": list(languages),
                    "outcome": "COMPLETED" if attempts else ("SOURCES_UNREACHABLE" if report.get("sources_unreachable") else "NO_CANDIDATES"),
                    "lanes_tried": [lane.get("label") for lane in report.get("lanes", [])], "notes": notes, "generated_at": ctx["generated_at"], "attempts_summary": summaries}
        writer.write_json(RUN_FILE, run_info)
    out(f"SHADOW_DONE attempts={attempts} passed={passed} held_or_rejected={attempts - passed}")
    if not attempts:
        out(f"::warning::그림자 실행: 평가할 후보가 없었습니다({run_info['outcome']}).")
        if run_info["outcome"] == "SOURCES_UNREACHABLE":
            raise SystemExit(1)
    return run_info
