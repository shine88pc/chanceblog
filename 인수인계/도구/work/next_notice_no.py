"""다음에 쓸 알림 번호를 구한다 — 읽기만 하는 도구(TG-STD, 운영자 승인 2026-11-06 계획 R-165).

알림 번호는 요청 번호 R-nnn 과 별개이고 유형마다 따로 늘어난다: 진행 현황 `P001`, 병합 요청 `M001`, 확인 요청은 숫자만 `001`(세 자리 0 채움, 999 다음은 네 자리, 000 은 없다).
요청 번호(J3)를 정하는 것과 같은 방법으로 읽는다 — 블로그 저장소의 `refs/remotes/origin/main` 과 `refs/remotes/origin/ai/*` 모든 가지의 `인수인계/요청함/` **바로 아래**
`R-nnn_슬러그.md` 파일 앞머리(`---` 사이)의 `no:` 줄을 모아 유형별 최댓값 + 1 을 낸다. `--local` 이면 로컬 가지(`refs/heads/*`)도, `--dir` 이면 그 작업 폴더의
`인수인계/요청함/` 파일(아직 커밋·push 전인 파일)도 읽는다. 세지 않는 것: 하위 폴더의 파일·`README.md`·앞머리 밖(본문)의 `no:`·번호 모양이 아닌 값·
`kind: merged`(병합완료 확인 — 확인하는 병합 요청의 M 번호를 다시 쓴 것이라 새 번호를 먹지 않는다) 파일. 번호는 9999 를 넘지 못한다(넘으면 오류).

사용: python -X utf8 next_notice_no.py [--repo <git 저장소, 기본 현재 폴더>] [--dir <작업 폴더>]... [--local] [--type P|M|ask]
  기본 출력은 세 줄이다:  P 다음 번호: P012 (지금 최댓값 P011 — R-168_progress-p011.md @ origin/main)
                          M 다음 번호: M007 (…)
                          확인 다음 번호: 003 (…)        — 한 유형이 아직 없으면 `P001`·`M001`·`001` (아직 없음)
  `--type` 을 주면 그 유형의 번호 하나만 출력한다(예: `P012` — 다른 스크립트가 쓰기 쉽게). 종료 코드: 0 정상, 1 읽기 실패·번호 소진, 2 사용법 오류.
  이 도구는 네트워크를 쓰지 않는다 — 읽기 전에 `git fetch origin` 을 먼저 한다(가져오지 않은 가지의 번호는 모른다). 같은 번호를 두 주체가 고를 수 있으니 push 직전에 한 번 더 부른다.

효율: 가지가 100개를 넘고 git 호출이 느리므로 가지마다 부르지 않는다 — `git for-each-ref` 한 번과 `git cat-file --batch` 두 번(요청함 폴더 → 파일 내용)으로 읽고 같은 파일(오브젝트)은 한 번만 읽는다.
라이브러리로도 쓴다: scan(repo, dirs, local) → {"progress": (최댓값, 출처), "merge": …, "ask": …} · next_numbers(결과) → {"progress": "P012", …} · format_no(유형, 순번).
앞머리 읽기·번호 판정·다음 번호 계산은 git 없이 시험할 수 있는 순수 함수이고, 읽는 규칙은 pipeline/operator_loop.parse_request 와 같다(첫 줄이 `---`, 닫는 `---` 가 첫 41줄 안).
표준 라이브러리만 쓴다(Python 3.10 이상).
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REQUEST_DIR = "인수인계/요청함"
NAME_RE = re.compile(r"R-[0-9]{3}_[a-z0-9]+(?:-[a-z0-9]+)*\.md")               # 요청 파일 이름(operator_loop.REQUEST_NAME_RE 와 같은 꼴, 슬러그 길이 상한은 두지 않는다 — 더 많이 세는 쪽이 안전하다)
KEY_LINE_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)[ \t]*:[ \t]*(.*)")        # 앞머리의 `키: 값` 한 줄(operator_loop._KEY_LINE_RE 와 같다)
NO_RE = re.compile(r"[PM][0-9]{3,4}|[0-9]{3,4}")                                # 읽기용 — ASCII 숫자만(전각·원문자·다른 나라 숫자는 번호가 아니다). pipeline/notify.NOTICE_NO_RE(표준 표기만)보다 일부러 넓다: 앞 0 이 붙은 `P0012` 도 12 로 센다(더 많이 세는 쪽이 안전하고, 만들 때는 format_no 가 늘 표준 표기를 낸다)
NO_MAX = 9999                                                                   # 번호는 네 자리를 넘지 않는다
KINDS = ("progress", "merge", "ask")                                            # 진행 현황 P · 병합 요청 M · 확인 요청(숫자만)
PREFIX = {"progress": "P", "merge": "M", "ask": ""}
LABEL = {"progress": "P", "merge": "M", "ask": "확인"}
TYPE_ALIASES = {"p": "progress", "progress": "progress", "m": "merge", "merge": "merge", "ask": "ask"}
FRONT_LINES = 40                    # 닫는 `---` 는 첫 41줄 안(operator_loop.MAX_FRONT_LINES)
READ_LIMIT = 400000                 # 파일 하나에서 읽는 바이트 수의 상한(앞머리는 이보다 훨씬 작다)
GIT_TIMEOUT = 120
MAIN_REF = "refs/remotes/origin/main"
BOM = chr(0xFEFF)


class ScanError(RuntimeError):
    """읽는 일을 더 할 수 없는 오류(git 이 없음·저장소가 아님·git 출력을 읽지 못함)."""


class NumberExhausted(ValueError):
    """한 유형의 번호가 상한(9999)에 닿아 다음 번호를 만들 수 없을 때."""


# ---- 순수 계산(git 없이 시험한다) ---------------------------------------------------------------
def unquote(raw):
    """양 끝이 같은 따옴표(`"` 또는 `'`)면 벗긴다(이스케이프는 풀지 않는다) — operator_loop._unquote 와 같다."""
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def front_close(lines):
    """줄 목록에서 앞머리를 닫는 `---` 줄의 위치. 첫 줄이 `---` 가 아니거나 닫는 줄이 첫 41줄 안에 없으면 None."""
    if not lines or lines[0].rstrip() != "---":
        return None
    return next((index for index in range(1, min(len(lines), FRONT_LINES + 1)) if lines[index].rstrip() == "---"), None)


def front_lines(text):
    """앞머리(맨 앞 `---` 줄과 닫는 `---` 줄 사이)의 줄들. 앞머리가 아니면 None. 줄은 `\\n` 으로만 나누고(U+2028 같은 문자로 줄을 위조하지 못하게) 맨 앞 BOM·CRLF 는 받아 준다."""
    lines = str(text).lstrip(BOM).replace("\r\n", "\n").split("\n")
    close = front_close(lines)
    return None if close is None else lines[1:close]


def front_values(text, key="no"):
    """앞머리에서 `key: 값` 줄의 값들(앞뒤 공백을 자르고 양 끝 따옴표를 벗긴 글, 나온 순서대로). 본문의 같은 글·들여쓴 줄·다른 키는 보지 않는다."""
    found = []
    for line in front_lines(text) or ():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = KEY_LINE_RE.fullmatch(line)
        if match is not None and match.group(1) == key:
            found.append(unquote(match.group(2).strip()))
    return found


def parse_no(value):
    """알림 번호 글 → (유형, 순번) 또는 None. `P012`·`M007`·`003` 꼴이어야 하고(숫자 3~4자리, ASCII) 순번이 0 이면 번호가 아니다. 앞뒤 공백·줄 바꿈이 있어도 번호가 아니다.
    읽기는 일부러 넓다 — 표준 표기가 아닌 `P0012`(앞 0 이 붙은 네 자리)도 12 로 센다(그런 파일은 검증기 REQ-1 이 거절하지만 가지에 남아 있으면 그 번호를 피해 가는 쪽이 안전하다)."""
    text = value if isinstance(value, str) else ""
    if NO_RE.fullmatch(text) is None:
        return None
    number = int(text.lstrip("PM"))
    if number < 1:
        return None
    return {"P": "progress", "M": "merge"}.get(text[0], "ask"), number


def front_numbers(text):
    """파일 글 하나의 앞머리 `no:` 값들 중 번호 모양인 것들 — [(유형, 순번), …]. 나머지 값은 무시한다.
    병합완료 확인(`kind: merged`, 2026-11-12)의 `no` 는 확인하는 병합 요청의 번호를 다시 쓴 것이라 세지 않는다 — 새 번호를 먹지 않고 다음 M 번호 계산에도 들어가지 않는다."""
    if "merged" in front_values(text, "kind"):
        return []
    return [found for found in (parse_no(value) for value in front_values(text)) if found is not None]


def format_no(kind, number):
    """유형·순번 → 번호 글자(세 자리 0 채움, 1000 부터 네 자리). 유형을 모르거나 순번이 1~9999 밖이면 ValueError."""
    if kind not in PREFIX or isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= NO_MAX:
        raise ValueError(f"번호를 만들 수 없다: {kind!r} {number!r}")
    return f"{PREFIX[kind]}{number:03d}"


def fold(best, name, where, numbers):
    """한 파일의 번호들을 유형별 최댓값에 합친다. 같은 값이면 먼저 본 출처를 남긴다. best: {유형: (최댓값, 출처)}."""
    for kind, number in numbers:
        if number > best[kind][0]:
            best[kind] = (number, f"{name} @ {where}")


def next_number(result, kind):
    """한 유형의 다음 번호 글자(최댓값 + 1). 이미 9999 면 NumberExhausted."""
    top = result[kind][0]
    if top >= NO_MAX:
        raise NumberExhausted(f"{LABEL[kind]} 번호가 상한 {NO_MAX} 에 닿았다(지금 최댓값 {format_no(kind, top)}) — 더 만들 수 없다")
    return format_no(kind, top + 1)


def next_numbers(result):
    """세 유형의 다음 번호 — {"progress": "P012", "merge": "M007", "ask": "003"}. 하나라도 9999 에 닿았으면 NumberExhausted."""
    return {kind: next_number(result, kind) for kind in KINDS}


def describe(result, kind, text):
    """출력 한 줄 — `P 다음 번호: P012 (지금 최댓값 P011 — 파일 이름 @ 가지)`, 아직 없으면 `(아직 없음)`."""
    top, source = result[kind]
    detail = f"지금 최댓값 {format_no(kind, top)} — {source}" if top else "아직 없음"
    return f"{LABEL[kind]} 다음 번호: {text} ({detail})"


# ---- git 읽기 ----------------------------------------------------------------------------------
def _warn_stderr(message):
    print(message, file=sys.stderr)


def _git_env():
    return dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")          # 물어보는 창·필요한 오브젝트를 몰래 가져오는 일(네트워크)을 막는다


def _git(repo, *args, data=None):
    """git 을 한 번 부르고 출력(바이트)을 돌려준다. 실패하면 ScanError. data 가 있으면 표준 입력으로 준다."""
    options = {"capture_output": True, "timeout": GIT_TIMEOUT, "env": _git_env()}
    if data is None:
        options["stdin"] = subprocess.DEVNULL
    else:
        options["input"] = data
    try:
        done = subprocess.run(["git", "-c", "core.quotePath=false", "-C", str(repo), *args], check=False, **options)
    except FileNotFoundError:
        raise ScanError("git 을 찾을 수 없다") from None
    except subprocess.TimeoutExpired:
        raise ScanError(f"git {args[0]} 이 {GIT_TIMEOUT}초 안에 끝나지 않았다") from None
    if done.returncode:
        raise ScanError(f"git {args[0]} 실패(종료 {done.returncode}): {done.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return done.stdout


def list_refs(repo, local=False):
    """읽을 ref 목록 [(해시, 오브젝트 종류, ref 이름)]. origin/main 과 origin/ai 아래 모든 가지(접두사 — 끝에 `/*` 를 붙이면 `ai/claude/주제` 두 단계 이름을 못 찾는다), local 이면 refs/heads 도."""
    patterns = [MAIN_REF, "refs/remotes/origin/ai"] + (["refs/heads"] if local else [])
    raw = _git(repo, "for-each-ref", "--format=%(objectname) %(objecttype) %(refname)", *patterns).decode("utf-8", "replace")
    refs = []
    for line in raw.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3:
            refs.append((parts[0], parts[1], parts[2]))
    return refs


def display_ref(refname):
    """출처에 보일 ref 이름 — `refs/remotes/origin/ai/x` → `origin/ai/x`, `refs/heads/x` → `heads/x`."""
    for prefix in ("refs/remotes/", "refs/"):
        if refname.startswith(prefix):
            return refname[len(prefix):]
    return refname


def _ref_order(item):
    refname = item[2]
    return (0 if refname == MAIN_REF else 1 if refname.startswith("refs/remotes/") else 2, refname)


def batch_read(repo, queries):
    """`git cat-file --batch` 한 프로세스로 오브젝트 이름 여러 개를 읽는다. 돌려주는 목록은 이름과 같은 순서이고 항목은 (종류, 내용 바이트) — 없는 오브젝트는 (None, None)."""
    if not queries:
        return []
    raw = _git(repo, "cat-file", "--batch", data="".join(f"{query}\n" for query in queries).encode("utf-8"))
    out, pos = [], 0
    try:
        for _query in queries:
            eol = raw.index(b"\n", pos)
            parts = raw[pos:eol].decode("utf-8", "replace").split(" ")
            pos = eol + 1
            if len(parts) >= 3 and parts[-1].isdigit():
                size = int(parts[-1])
                body = raw[pos:pos + size]
                if len(body) != size:
                    raise ValueError("잘린 출력")
                pos += size + 1                                   # 내용 뒤의 줄 바꿈 하나
                out.append((parts[-2], body))
            else:
                out.append((None, None))                          # `<이름> missing`
    except ValueError:
        raise ScanError("git cat-file 출력을 읽지 못했다") from None
    return out


def tree_files(body, raw_len):
    """git 트리 오브젝트(이진) → [(이름, 파일 오브젝트 해시)] — 일반 파일(모드 100…)만. 오브젝트 해시 길이(raw_len)는 20(sha1) 또는 32(sha256). 모양이 틀리면 ValueError."""
    files, pos = [], 0
    while pos < len(body):
        space = body.index(b" ", pos)
        nul = body.index(b"\0", space)
        mode, name = body[pos:space], body[space + 1:nul]
        digest = body[nul + 1:nul + 1 + raw_len]
        if len(digest) != raw_len:
            raise ValueError("잘린 트리")
        pos = nul + 1 + raw_len
        if mode.startswith(b"100"):
            files.append((name.decode("utf-8", "replace"), digest.hex()))
    return files


def read_git(repo, local=False, warn=None):
    """git 저장소에서 읽은 번호들 — [(파일 이름, 가지 이름, [(유형, 순번), …]), …]. 읽을 수 없는 ref 는 건너뛰고 warn 에 한 줄 남긴다."""
    warn = warn or _warn_stderr
    refs = list_refs(repo, local)
    if not any(refname == MAIN_REF for _sha, _kind, refname in refs):
        warn(f"{display_ref(MAIN_REF)} 가 없다 — `git fetch origin` 을 먼저 하지 않으면 번호가 실제보다 작게 나올 수 있다")
    groups = {}                                                       # 커밋 해시 → ref 이름들(같은 커밋을 가리키는 가지는 한 번만 읽는다)
    for sha, kind, refname in sorted(refs, key=_ref_order):
        if kind != "commit":
            warn(f"읽을 수 없는 ref(커밋이 아니다): {display_ref(refname)}")
            continue
        groups.setdefault(sha, []).append(display_ref(refname))
    commits = list(groups)
    entries, names = {}, {}                                           # 커밋 → [(이름, 파일 해시)], 파일 해시 → 처음 본 (이름, 가지)
    for sha, (kind, body) in zip(commits, batch_read(repo, [f"{sha}:{REQUEST_DIR}" for sha in commits]), strict=True):
        if kind is None:
            continue                                                  # 이 가지에는 요청함 폴더가 없다(오래된 가지) — 읽을 것이 없을 뿐 문제가 아니다
        if kind != "tree":
            warn(f"{REQUEST_DIR} 가 폴더가 아니다: {groups[sha][0]}")
            continue
        try:
            files = [(name, digest) for name, digest in tree_files(body, len(sha) // 2) if NAME_RE.fullmatch(name)]
        except ValueError:
            warn(f"읽을 수 없는 ref(트리가 잘렸다): {groups[sha][0]}")
            continue
        entries[sha] = files
        for name, digest in files:
            names.setdefault(digest, (name, groups[sha][0]))
    digests = sorted(names)
    numbers = {}
    for digest, (kind, body) in zip(digests, batch_read(repo, digests), strict=True):
        if kind != "blob":
            warn(f"읽을 수 없는 파일: {names[digest][0]} @ {names[digest][1]}")
            numbers[digest] = []
        else:
            numbers[digest] = front_numbers(body[:READ_LIMIT].decode("utf-8", "replace"))
    return [(name, groups[sha][0], numbers[digest]) for sha in commits for name, digest in sorted(entries.get(sha, ())) if numbers[digest]]


def read_dir(directory, warn=None):
    """작업 폴더의 `인수인계/요청함/` 바로 아래 파일(커밋·push 전인 것 포함)에서 읽은 번호들 — read_git 과 같은 꼴."""
    warn = warn or _warn_stderr
    folder = Path(directory) / "인수인계" / "요청함"
    if not folder.is_dir():
        warn(f"작업 폴더에 {REQUEST_DIR} 가 없다: {directory}")
        return []
    found = []
    for path in sorted(folder.iterdir()):
        if not NAME_RE.fullmatch(path.name) or not path.is_file():
            continue
        try:
            with open(path, "rb") as handle:
                text = handle.read(READ_LIMIT).decode("utf-8", "replace")
        except OSError as exc:
            warn(f"읽을 수 없는 파일: {path} ({exc.__class__.__name__})")
            continue
        numbers = front_numbers(text)
        if numbers:
            found.append((path.name, f"폴더 {directory}", numbers))
    return found


def scan(repo=".", dirs=(), local=False, warn=None):
    """유형별 지금 최댓값과 그 출처 — {"progress": (최댓값, "파일 이름 @ 가지"), "merge": …, "ask": …}, 하나도 없으면 (0, ""). repo 가 None 이면 git 은 읽지 않는다(dirs 만).
    git 이 없거나 저장소가 아니면 ScanError. 읽을 수 없는 ref·파일은 건너뛰고 warn(기본: 표준 오류) 에 한 줄 남긴다."""
    warn = warn or _warn_stderr
    best = {kind: (0, "") for kind in KINDS}
    sources = list(read_git(repo, local, warn)) if repo is not None else []
    for directory in dirs:
        sources.extend(read_dir(directory, warn))
    for name, where, numbers in sources:
        fold(best, name, where, numbers)
    return best


# ---- 명령 줄 -----------------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(prog="next_notice_no.py", description="다음에 쓸 알림 번호(진행 현황 P·병합 요청 M·확인 요청 숫자)를 구한다 — 읽기만 한다. 읽기 전에 git fetch origin 을 먼저 한다.")
    parser.add_argument("--repo", default=".", help="git 저장소 경로(기본: 현재 폴더)")
    parser.add_argument("--dir", action="append", default=[], dest="dirs", metavar="작업폴더", help="이 폴더의 인수인계/요청함/ 파일도 읽는다(여러 번 줄 수 있다)")
    parser.add_argument("--local", action="store_true", help="로컬 가지(refs/heads/*)도 읽는다")
    parser.add_argument("--type", dest="kind", metavar="P|M|ask", help="그 유형의 번호 하나만 출력한다")
    args = parser.parse_args(argv)
    kind = None
    if args.kind is not None:
        kind = TYPE_ALIASES.get(args.kind.strip().lower())
        if kind is None:
            parser.error(f"--type 은 P, M, ask 중 하나여야 한다(지금 {args.kind!r})")
    if not Path(args.repo).is_dir():
        parser.error(f"--repo 가 폴더가 아니다: {args.repo}")
    try:
        result = scan(args.repo, args.dirs, args.local)
    except ScanError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    code = 0
    for each in ((kind,) if kind else KINDS):
        try:
            text = next_number(result, each)
        except NumberExhausted as exc:
            print(f"오류: {exc}", file=sys.stderr)
            code = 1
            continue
        print(text if kind else describe(result, each, text))
    return code


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
