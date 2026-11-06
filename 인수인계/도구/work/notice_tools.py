"""요청 파일 만들기(make_request.py)의 부품 — 알림 번호 칸·병합 PR 제목·길이 검사(TG-STD, 운영자 승인 2026-11-06 계획 R-165).

make_request.py 는 실행하는 스크립트라 불러서 시험할 수 없는 부분이 많았다. 그래서 새 규칙은 여기 함수로 두고 make_request.py 가 가져다 쓴다(직접 실행하지 않는다).
네트워크는 쓰지 않는다. git 은 `head_subject` 한 곳에서만 부르고(실행 함수를 바꿔 끼울 수 있다) 나머지는 글만 다루는 순수 함수다. 표준 라이브러리만 쓴다(Python 3.10 이상).

값의 상한(`LIMITS`)·PR 제목 안전 규칙(`pr_title_problem` — 비밀 모양·보이지 않는 글자 포함)·알림 번호 모양(`no_problem`)은 pipeline/notify.py·pipeline/operator_loop.py(검증기 REQ-1)의 것을 그대로 옮긴 사본이다 —
작업 폴더 W 에는 pipeline 이 없어 불러 쓰지 못하므로, 두 곳이 어긋나지 않는지는 tests/test_notice_tools.py 가 비교한다(비밀 모양 판정은 llm.mask 와 같은 글을 같은 결론으로 가린다).
앞머리를 읽는 규칙(첫 줄 `---`, 닫는 `---` 가 첫 41줄 안, `키: 값` 한 줄)은 next_notice_no.py 의 것을 같이 쓴다.
"""
import re
import subprocess
import unicodedata

import next_notice_no as nn

# 요청 종류(kind) → 알림 번호 유형(pipeline/notify.NOTICE_KIND_TYPES 와 같다): info=P, merge=M, 그 밖(decision·confirm·run)=숫자만
NOTICE_TYPE_OF_KIND = {"info": "progress", "merge": "merge", "decision": "ask", "confirm": "ask", "run": "ask"}
# 앞머리 값의 글자 수 상한(unquote 한 값 기준, pr_title 은 따옴표까지 제목이라 그대로) — pipeline/notify.py 의 PROGRESS_ITEMS·CHECK_LIMIT 등과 같다
LIMITS = {"title": 80, "summary": 300, "now": 200, "changed": 200, "next": 200, "waiting": 200, "eta": 100, "check": 60, "target": 100, "verify": 120, "state": 40, "pr_title": 200}
OPTION_LIMIT = 60                         # 확인 요청의 보기 하나(`options` 를 ` / ` 로 나눈 조각)의 상한
OPTION_SEPARATOR = " / "
PR_TITLE_LIMIT = LIMITS["pr_title"]
PLACEHOLDERS = ("@TESTS@", "@VERIFY@", "@LINK@", "@PREVIOUS@", "@NO@", "@PR_TITLE@")      # 초안에 남아 있으면 안 되는 자리표시자
# 눈으로 같은지 볼 수 없는 글자(pipeline/console.INVISIBLE_CODEPOINTS 와 같다)와 제어·서식·짝 없는 서로게이트·줄·문단 구분 문자(Cc·Cf·Cs·Zl·Zp)
INVISIBLE_CODEPOINTS = (0x00AD, *range(0x200B, 0x2010), *range(0x202A, 0x202F), *range(0x2060, 0x2065), *range(0x2066, 0x206A), 0xFEFF)
# 글자처럼 보이지만 비어 보이는 문자(U+034F·한글 채움·크메르 고유 모음·점자 빈칸 …) — PR 제목에서만 거절한다(pipeline/notify.PR_TITLE_EXTRA_INVISIBLE_CODEPOINTS 와 같다)
PR_TITLE_EXTRA_INVISIBLE_CODEPOINTS = (0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x2800, 0x3164, 0xFFA0)
INVISIBLE = frozenset(chr(code) for code in (*INVISIBLE_CODEPOINTS, *PR_TITLE_EXTRA_INVISIBLE_CODEPOINTS))
BAD_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})
# 비밀 모양 — pipeline/llm.py 의 `_SECRET_RX`·`mask` 와 pipeline/secret_patterns.py 의 SECRET_PATTERNS 의 사본(런타임·검증기가 PR 제목을 거절하는 기준과 같다. tests/test_notice_tools.py 가 원본과 비교한다)
SECRET_RX = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|ya29\.[0-9A-Za-z_\-]{20,}|1//[0-9A-Za-z_\-]{20,}|"
                       r"(?i:key|token|secret)=[^\s&'\"]+)")
SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    re.compile(r"(?<![A-Za-z0-9])AQ\.[0-9A-Za-z_\-]{40,}"),
    re.compile(r"GOCSPX-[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\b1//0[0-9A-Za-z_\-]{40,}"),
    re.compile(r"\bya29\.[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}"),
    re.compile(r"\bgithub_pat_[0-9A-Za-z_]{40,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY(?: BLOCK)?-----"),
    re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"[0-9]{6,12}:[A-Za-z0-9_\-]{30,50}(?![A-Za-z0-9_\-])"),
    re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    re.compile(r'"client_secret"\s*:\s*"(?![A-Z][A-Z0-9_]*")[^"]{8,}"'),
    re.compile(r"""(?i)\b(?:api[_-]?key|secret|token|passwd|password)\b\s*[:=]\s*['"][A-Za-z0-9_\-/+=]{24,}['"]"""),
)
# 알림 번호의 표준 표기 — pipeline/notify.NOTICE_NO_RE 와 같다(`001`~`999` 세 자리·`1000`~`9999` 네 자리, 앞 0 없음). next_notice_no.NO_RE 는 읽기용이라 일부러 더 넓다(앞 0 이 붙은 옛 글도 세어 준다)
STRICT_NO_RE = re.compile(r"[PM]?(?:(?!000)[0-9]{3}|[1-9][0-9]{3})")
BRANCH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
SHA_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


class TitleError(ValueError):
    """병합 가지 머리 커밋의 제목을 읽지 못했을 때(가지가 없음·git 오류·글자 깨짐). 메시지는 그대로 사람에게 보인다."""


# ---- 앞머리 읽기·값 채우기 -----------------------------------------------------------------------
def read_front(text):
    """초안의 앞머리를 {키: 값} 으로(앞뒤 공백을 자르고 양 끝 따옴표를 벗긴 값 — 단 `pr_title` 은 따옴표까지 제목의 글자라 벗기지 않는다). 앞머리가 없으면 빈 사전.
    같은 키가 둘이면 먼저 나온 것이 이긴다(중복은 검증기가 잡는다). 모양이 틀린 줄은 건너뛴다(그것도 검증기 몫이다)."""
    fields = {}
    for line in nn.front_lines(text) or ():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = nn.KEY_LINE_RE.fullmatch(line)
        if match is None:
            continue
        key, raw = match.group(1), match.group(2).strip()
        fields.setdefault(key, raw if key == "pr_title" else nn.unquote(raw))
    return fields


def length_problems(fields):
    """상한을 넘은 칸 [(칸 이름, 글자 수, 상한), …] — 순서는 LIMITS, 그다음 확인 요청 보기(`options 보기 2번`). 없으면 빈 목록."""
    over = [(key, len(fields[key]), limit) for key, limit in LIMITS.items() if key in fields and len(fields[key]) > limit]
    options = fields.get("options", "")
    if options.strip():
        for index, part in enumerate((part.strip() for part in options.split(OPTION_SEPARATOR)), 1):
            if len(part) > OPTION_LIMIT:
                over.append((f"options 보기 {index}번", len(part), OPTION_LIMIT))
    return over


def no_front_value(no):
    """알림 번호를 앞머리 값으로 — 숫자만인 번호(확인 요청)는 `"003"` 처럼 따옴표로 감싼다(숫자로 읽혀 0 이 떨어지지 않게), P·M 번호는 그대로."""
    return f'"{no}"' if no.isdigit() else no


def fill_front_values(text, no=None, pr_title=None):
    """`@NO@`·`@PR_TITLE@` 를 채운다. 앞머리의 `no: @NO@` 줄은 `no: P012`(숫자만인 번호는 `no: "003"`)로, `pr_title: @PR_TITLE@` 줄은 `pr_title: <제목>`(따옴표 없이 글자 그대로)로 바꾸고,
    그 밖의 자리(본문·요약)에 있는 같은 자리표시자는 글자 그대로 바꾼다. no·pr_title 이 None 이면 그 자리표시자는 건드리지 않는다. 줄 바꿈은 그대로 둔다."""
    lines = text.split("\n")
    close = nn.front_close(lines)
    if close is not None:
        for index in range(1, close):
            match = nn.KEY_LINE_RE.fullmatch(lines[index])
            if match is None:
                continue
            key, raw = match.group(1), match.group(2).strip()
            if key == "no" and raw == "@NO@" and no is not None:
                lines[index] = f"no: {no_front_value(no)}"
            elif key == "pr_title" and raw == "@PR_TITLE@" and pr_title is not None:
                lines[index] = f"pr_title: {pr_title}"
    text = "\n".join(lines)
    if no is not None:
        text = text.replace("@NO@", no)
    if pr_title is not None:
        text = text.replace("@PR_TITLE@", pr_title)
    return text


def fill_placeholders(text, values):
    """`@이름@` 자리를 values({이름: 글}, 예 {"TESTS": "…"}) 로 한 번에 바꾼다 — 바꾼 글 안의 자리표시자를 다시 바꾸지 않고 역슬래시도 글자 그대로 둔다. values 에 없는 이름은 그대로 둔다."""
    if not values:
        return text
    pattern = re.compile("@(" + "|".join(re.escape(name) for name in values) + ")@")
    return pattern.sub(lambda match: values[match.group(1)], text)


def leftover_placeholders(text, ignore=()):
    """글에 남은 자리표시자(PLACEHOLDERS 의 순서). ignore 에 준 것은 아직 채우지 않아도 되는 것(예: 검사 관문 뒤에 채우는 `@VERIFY@`)."""
    return [token for token in PLACEHOLDERS if token in text and token not in ignore]


def auto_verify_text(run_count):
    """검증 문구 인자가 비었고 병합 부탁의 검사 관문을 통과했을 때 `verify` 에 채우는 글. 독립 검증을 했는지는 사람이 앞에 적어야 하므로 이 글에 쓰지 않는다."""
    return f"검사 {run_count}칸 초록"


# ---- 병합 PR 제목 ------------------------------------------------------------------------------
def mask(text):
    """pipeline/llm.mask 와 같은 사본 — 비밀로 보이는 값을 `***` 로 가린다(비밀 모양 판정에만 쓴다)."""
    out = SECRET_RX.sub("***", str(text))
    for rx in SECRET_PATTERNS:
        out = rx.sub("***", out)
    return out


def looks_secret(text):
    """글에 비밀 모양(`key=…`·`token=…`·`secret=…`·`AIza…` 같은 키·토큰)이 있는가 — 런타임(notify.pr_title_problem)·검증기(REQ-1 pr_title_secret)와 같은 판정(`mask` 가 글을 바꾸는지)이다.
    `monkey=banana` 처럼 낱말 경계가 없어 평범한 글이 걸리기도 한다(안전한 쪽)."""
    text = str(text)
    return mask(text) != text


def pr_title_problem(title):
    """PR 제목을 한 글자도 바꾸지 않고 요청 파일에 쓸 수 있는가 — 쓸 수 있으면 빈 글, 아니면 이유(한국어). 비었음·200자 초과·제어 문자·보이지 않거나 비어 보이는 글자(U+200B·U+3164 등)·
    비밀 모양·앞뒤 공백. 런타임·검증기와 같은 기준이라 여기서 통과한 제목은 폰에 간다(비밀 모양이면 알림이 '보내지 않음'이 되고 CI 검증기가 오류로 알리므로 만들기 전에 막는다).
    줄이거나 고쳐서 통과시키지 않는다(운영자는 GitHub 에서 글자까지 같은 제목을 찾아 병합한다)."""
    if not isinstance(title, str) or not title.strip():
        return "비어 있다"
    if len(title) > PR_TITLE_LIMIT:
        return f"{len(title)}자라 {PR_TITLE_LIMIT}자를 넘는다(줄여 쓰면 PR 제목과 달라지므로 PR 제목을 줄인다)"
    for position, char in enumerate(title, 1):
        if char in INVISIBLE or unicodedata.category(char) in BAD_CATEGORIES:
            return f"제어 문자·보이지 않거나 비어 보이는 글자가 있다(U+{ord(char):04X}, {position}번째 글자)"
    if looks_secret(title):
        return ("비밀(키·토큰)로 보이는 글이 있다 — `key=`·`token=`·`secret=` 꼴이나 `AIza…` 같은 키 모양이 걸린다(`monkey=banana` 처럼 낱말 일부여도 걸린다). "
                "이런 제목은 알림이 '보내지 않음'이 되고 CI 검증기가 오류로 알린다 — PR 제목(첫 커밋 제목)에서 그 글을 빼고 다시 한다")
    if title != title.strip():
        return "앞뒤에 공백이 있다(요청 파일은 앞뒤 공백을 자르므로 글자 그대로 쓸 수 없다)"
    return ""


# ---- 손으로 쓴 알림 번호 ------------------------------------------------------------------------
def folder_numbers(folder, skip=""):
    """요청함 폴더(작업 폴더의 요청 가지 사본)의 모든 요청 파일 앞머리 `no` 값에서 읽은 번호 [(유형, 순번), …] — skip 은 건너뛸 파일 이름(지금 만드는 파일). 읽을 수 없는 파일은 건너뛴다.
    읽기는 next_notice_no.parse_no 라 앞 0 이 붙은 옛 글도 세어 준다(더 많이 세는 쪽이 안전)."""
    found = []
    for path in sorted(folder.iterdir()):
        if path.name == skip or not path.is_file() or nn.NAME_RE.fullmatch(path.name) is None:
            continue
        try:
            found.extend(nn.front_numbers(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return found


def no_problem(no, kind, taken=()):
    """손으로 쓴 알림 번호 `no` 가 요청 파일에 쓸 수 있는 번호인가 — 쓸 수 있으면 빈 글, 아니면 이유(한국어). 표준 표기(`P012`·`M007`·`003`, 앞 0 없음 — `P0012`·`0003` 은 번호가 아니다)·
    요청 종류(kind)와 유형의 일치(info=P·merge=M·그 밖=숫자만)·이미 쓰인 번호가 아님(taken = folder_numbers 의 결과). 검증기 REQ-1 이 푸시 뒤에 잡을 것을 만들기 전에 미리 잡는다.
    번호는 되도록 `no: @NO@` 로 받는다(next_notice_no.py — 모든 원격 가지의 최댓값 + 1)."""
    if not isinstance(no, str) or STRICT_NO_RE.fullmatch(no) is None:
        return ("알림 번호 모양이 아니다 — 진행 현황 `P001`·병합 요청 `M001`·확인 요청은 숫자만 `001`, 숫자는 `001`~`999` 세 자리 또는 `1000`~`9999` 네 자리이고 "
                "앞에 0 을 더 붙인 `P0012`·`0003` 이나 000 은 없다(`no: @NO@` 로 두면 도구가 번호를 정한다)")
    wanted = NOTICE_TYPE_OF_KIND.get(kind)
    kind_type = {"P": "progress", "M": "merge"}.get(no[:1], "ask")
    if wanted is None:
        return f"요청 종류(kind)가 {kind!r} 라 번호 유형을 알 수 없다(info·merge·decision·confirm·run 중 하나여야 한다)"
    if kind_type != wanted:
        return f"번호 {no} 의 유형이 kind: {kind} 와 맞지 않는다(info 는 `P`, merge 는 `M`, decision·confirm·run 은 숫자만)"
    if (kind_type, int(no.lstrip("PM"))) in set(taken):
        return f"번호 {no} 는 이 요청함의 다른 요청 파일이 이미 쓰고 있다(같은 유형의 알림 번호는 파일마다 달라야 한다)"
    return ""


def notice_front_problem(fields, folder=None, skip=""):
    """채워진 앞머리 fields({키: 값})의 알림 번호·병합 PR 제목을 검사한다 — 문제가 없으면 빈 글, 있으면 이유(한국어). `no` 가 있으면 no_problem(폴더가 주어지면 이미 쓰인 번호도 본다),
    병합 요청(`kind: merge`)에 `pr_title` 이 있으면 pr_title_problem(손으로 쓴 제목도 자동으로 채운 제목과 같은 기준으로)."""
    kind = fields.get("kind", "")
    if "no" in fields:
        taken = folder_numbers(folder, skip) if folder is not None else ()
        problem = no_problem(fields["no"], kind, taken)
        if problem:
            return f"앞머리 no: {problem}"
    if kind == "merge" and "pr_title" in fields:
        problem = pr_title_problem(fields["pr_title"])
        if problem:
            return f"앞머리 pr_title 을 그대로 쓸 수 없다 — {problem}"
    return ""


def repo_folder(repo_name):
    """저장소 이름(`소유자/저장소`) → 작업 폴더 W 아래의 저장소 폴더 이름: 이름이 `-desktop` 으로 끝나면 `cd_repo`(데스크톱), 아니면 `wt_r30`(블로그)."""
    return "cd_repo" if repo_name.endswith("-desktop") else "wt_r30"


def _run_git(args):
    return subprocess.run(args, check=False, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)


def head_subject(repo_dir, branch, run=None):
    """병합 가지 머리 커밋의 제목을 글자 그대로 읽는다 — (제목, 커밋 전체 해시, 읽은 ref). `git -C <저장소 폴더> log -1 --format=%B <가지>`(커밋 메시지 전체)의 **첫 줄만** 제목으로 쓴다
    (`%s` 는 첫 문단이 두 줄이면 한 칸 띄어 이어 붙여 GitHub PR 제목(첫 줄)과 달라진다). 로컬에 가지가 없으면 `origin/<가지>`.
    앞뒤 줄 바꿈(·줄 끝 CR)만 떼고 고치지 않는다. 읽지 못하면 TitleError. run 은 git 을 부르는 함수(args → 종료 코드·stdout 이 있는 결과)로 시험에서 바꿔 끼운다."""
    run = run or _run_git
    if BRANCH_RE.fullmatch(branch) is None or ".." in branch:
        raise TitleError(f"브랜치 이름 모양이 이상하다: {branch!r}")
    tried = []
    for ref in (branch, f"origin/{branch}"):
        try:
            done = run(["git", "-C", str(repo_dir), "log", "-1", "--format=%H%x00%B", ref, "--"])
        except (OSError, subprocess.SubprocessError) as exc:
            raise TitleError(f"git 을 부르지 못했다({exc.__class__.__name__})") from None
        if done.returncode:
            tried.append(ref)
            continue
        try:
            raw = done.stdout.decode("utf-8")
        except UnicodeDecodeError:
            raise TitleError(f"{ref} 머리 커밋 제목이 UTF-8 이 아니다") from None
        sha, found, message = raw.strip("\r\n").partition("\0")
        if not found or SHA_RE.fullmatch(sha) is None:
            raise TitleError(f"{ref} 머리 커밋을 읽은 결과의 모양이 이상하다")
        return message.replace("\r\n", "\n").split("\n", 1)[0].rstrip("\r"), sha, ref
    raise TitleError(f"병합 가지의 머리 커밋을 읽지 못했다 — {repo_dir} 에 {' 도, '.join(tried)} 가 없다")
