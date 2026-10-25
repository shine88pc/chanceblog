"""이슈 한 건 처리: 인식 → 파싱 → 검증 → 대상 해석 → 수정 → 사후 검증 → (파일 쓰기) → 산출물.

git·PR 은 이 모듈이 하지 않는다(워크플로가 한다). 이 모듈은 작업 트리의 대상 파일 한 개를 고치고,
워크플로가 쓸 파일(result.json, files.txt, commit_msg.txt, pr_title.txt, pr_body.md, comment.md …)을 --out 폴더에 쓴다.
`resolve_request` 는 '요청이 무엇을 허용하는가'만 해석하므로 PR 범위 검증(scope_check)도 같은 기준을 쓴다.

CLI: python -m pipeline.edits.runner --issue-file issue.json --out DIR [--dry-run] [--remote-refs refs.txt]
     python -m pipeline.edits.runner --verify-staged DIR/files.txt   (스테이징 목록 == 허용 목록 확인)
     python -m pipeline.edits.runner --show-output DIR                (DRY_RUN: 산출물을 워크플로 명령이 먹히지 않게 로그에 출력)
로그 정책: 이슈를 처리하는 단계(--issue-file)가 내는 줄은 모두 `issue=#N author=@login(권한)` 으로 시작하고, 요청 원문·페이지 원문·프롬프트·비밀·예외 원문은 내지 않는다.
(이미지 선택기가 부르는 레거시 엔진 generator.py 는 검색어를 print 하므로 호출 동안 stdout·stderr 를 가두고 `image_search_notes` 의 요약만 이 형식으로 낸다.)

한 이슈는 한 번만 처리한다: --remote-refs 에 이 이슈 번호의 원격 브랜치가 있거나 이슈에 표식 라벨(issue-edit-done)이 있으면
새 브랜치·PR 없이 코멘트용 결과(duplicate)만 만든다(dry-run 은 예외).

종료 코드: 0 처리 끝(ok·rejected·ignored·duplicate 포함) / 1 인프라 실패(AI·네트워크)와 예상하지 못한 오류(`main` 이 잡아 status=error 로 남긴다) / 2 설정·명세 오류
"""
import argparse
import contextlib
import io
import json
import os
import posixpath
import re
import secrets
import subprocess
import sys
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote

from pipeline import registry as registry_mod
from pipeline.console import md_cell, safe_output
from pipeline.edits import checks, forms, frontmatter, ops, pages, safety, spec as spec_mod, targets
from pipeline.llm import CallLog, call_line

MAX_FIELD_CHARS = 5000
EXIT_OK, EXIT_INFRA, EXIT_CONFIG = 0, 1, 2
# 이슈 번호: 1~999999999, 앞자리 0 없음. 워크플로 첫 단계의 정규식(`^…$`)과 같아야 한다(테스트가 대조).
# 앞자리 0 을 허용하면 `012` 로는 브랜치 패턴 `issue-edit/012-*` 가 `issue-edit/12-…` 와 맞지 않아 재처리 확인을 우회한다.
ISSUE_NUMBER_PATTERN = r"[1-9][0-9]{0,8}"
DONE_LABEL = "issue-edit-done"         # 처리를 끝낸(브랜치·PR 을 만든) 이슈에 붙이는 표식 라벨(브랜치는 병합 뒤 지워질 수 있어 지속 표식)
REF_HEADS = "refs/heads/"
DEFAULT_BRANCH_PREFIX = "issue-edit/"


@dataclass
class Result:
    status: str                       # ok | rejected | ignored | error | duplicate(이미 처리한 이슈 — 코멘트만) | paused(정지 스위치 — 코멘트만)
    message: str = ""
    reasons: list = field(default_factory=list)
    exit_code: int = EXIT_OK
    files: list = field(default_factory=list)
    branch: str = ""
    edit_type: str = ""
    target: str = ""
    ad_surface: bool = False
    commit_message: str = ""
    pr_title: str = ""
    pr_body: str = ""
    summary: str = ""
    comment: str = ""
    notes: list = field(default_factory=list)   # 러너 로그에만 쓰는 참고 문장(공개 코멘트에는 쓰지 않는다)
    log_detail: str = ""                        # 러너 로그에만 쓰는 (마스킹된) 실패 원인. result.json 에도 쓰지 않는다


@dataclass(frozen=True)
class Processed:
    """이미 처리한 이슈라는 근거: 기존 브랜치 이름들과 표식 라벨 유무. 근거가 하나라도 있으면 참이다."""
    branches: tuple = ()
    labeled: bool = False

    def __bool__(self):
        return bool(self.branches) or self.labeled


@dataclass
class Request:
    """검증을 통과한 수정 요청: 무엇을·어디까지 고칠 수 있는가."""
    spec: dict
    number: int
    login: str
    assoc: str
    edit_key: str
    cfg: dict
    fields: dict
    target: dict                      # {path, title, id}
    patterns: list                    # 허용 경로(자리표시자 해석 후)
    ad_surface: bool


# ----------------------------------------------------------------------------
# 보조
# ----------------------------------------------------------------------------
def protected_paths(root):
    """광고 표면(ad_surface=true 블로그)의 보호 경로 목록. 레지스트리를 못 읽으면 RegistryError(호출부가 요청을 거부한다 — fail closed)."""
    reg = registry_mod.load_registry(Path(root) / "pipeline" / "blogs.json")
    out = []
    for raw in reg.get("blogs", []):
        blog = registry_mod.merged_blog(reg, raw)
        if blog.get("ad_surface"):
            out.extend(blog.get("protected_paths", []))
    return out


def is_protected(path, protected):
    """`./about.md`·`a//b` 같은 표기 차이로 비교를 우회하지 못하게 양쪽을 정규화한다."""
    path = posixpath.normpath(str(path).replace("\\", "/"))
    for p in protected:
        norm = posixpath.normpath(str(p).replace("\\", "/"))
        if path == norm or (str(p).endswith("/") and path.startswith(norm + "/")):
            return True
    return False


def _slug(text, limit=30):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:limit] or "x"


# 한 줄 접기·코드 스팬은 safety 모듈이 정의한다(ops·checks 도 같은 함수를 쓴다). 기존 이름은 그대로 둔다.
_one_line = safety.one_line
_code = safety.code


def _fence(text):
    """사용자 입력을 코드 펜스 안에 안전하게 넣는다(펜스 탈출·멘션 방지)."""
    clean = frontmatter.normalize_newlines(text).replace("~~~", "~ ~ ~").replace("@", "@\N{ZERO WIDTH SPACE}")
    return f"~~~~text\n{clean}\n~~~~"


def _reject(reasons, hint="", edit_type="", target=""):
    reasons = [_one_line(r, 400, markdown=True) for r in reasons]   # 코드 스팬 한가운데에서 잘려 닫는 백틱이 사라지지 않게(마크다운 코멘트)
    comment ="⚠️ **수정하지 않았습니다.**\n\n사유:\n" + "\n".join(f"- {r}" for r in reasons)
    if hint:
        comment += f"\n\n{hint}"
    comment += "\n\n(저장소는 변경되지 않았습니다. 내용을 고쳐 새 이슈로 올려 주세요.)"
    return Result("rejected", message=reasons[0], reasons=reasons, comment=comment, edit_type=edit_type, target=target)


def _error(message, exit_code=EXIT_INFRA, log_detail=""):
    """처리 오류. message 는 공개 코멘트에도 들어가므로 원인 상세(log_detail)는 따로 두고 러너 로그에만 낸다."""
    message = _one_line(message, 400, markdown=True)
    comment =f"❌ **처리 중 오류가 발생했습니다.**\n\n- {message}\n\n저장소는 변경되지 않았습니다. Actions 로그를 확인하세요."
    return Result("error", message=message, reasons=[message], comment=comment, exit_code=exit_code, log_detail=log_detail)


def _is_test_signal(exc):
    """시험(unittest)이 러너를 거치며 던지는 단언·건너뛰기·중단 신호인지. 이것까지 '처리 중 오류'로 바꾸면 시험이 실패·건너뜀을 보지 못한다.
    unittest 를 import 하지 않고 예외 클래스가 정의된 모듈로 알아본다(SkipTest·_ShouldStop·_UnexpectedSuccess 는 모두 unittest.case)."""
    return isinstance(exc, AssertionError) or type(exc).__module__ == "unittest.case"


def _crash_site(exc, root, limit=4):
    """예상하지 못한 예외가 난 곳: `예외종류 난 곳 파일:줄 함수 ← …`(가장 안쪽 limit 개 프레임). 러너 로그 전용이다.
    예외 문구는 요청 유래 텍스트가 섞일 수 있어 싣지 않는다 — 파일 경로·줄 번호·함수 이름은 소스 코드의 것이다."""
    sites = []
    for frame in reversed(traceback.extract_tb(exc.__traceback__)[-limit:]):
        try:
            where = Path(frame.filename).resolve().relative_to(Path(root).resolve()).as_posix()
        except (ValueError, OSError):    # 저장소 밖의 파일(표준 라이브러리 등)은 끝의 두 경로 조각만
            where = "/".join(Path(frame.filename).parts[-2:])
        sites.append(f"{where}:{frame.lineno} {frame.name}")
    return f"{type(exc).__name__} 난 곳 " + " ← ".join(sites)


def _clean_token(value, allowed, limit):
    """GitHub 이 정한 짧은 식별자(로그인·권한)에서 허용 문자만 남긴다(로그 줄 위조·워크플로 명령·트레일러 주입 방지)."""
    cleaned = re.sub(rf"[^{allowed}]", "", "" if value is None else str(value))[:limit]
    return cleaned or "?"


def _login(issue):
    user = issue.get("user") if isinstance(issue, dict) else None
    return _clean_token(user.get("login") if isinstance(user, dict) else None, r"A-Za-z0-9._\[\]-", 40)


def issue_tag(issue):
    """이슈 처리 단계(main --issue-file)가 내는 모든 로그 줄 머리에 붙는 `issue=#N author=@login(권한)`."""
    issue = issue if isinstance(issue, dict) else {}
    number = issue.get("number")
    n = str(number) if isinstance(number, int) and not isinstance(number, bool) and number > 0 else "?"
    return f"issue=#{n} author=@{_login(issue)}({_clean_token(issue.get('author_association'), 'A-Za-z_', 30).upper()})"


# ----------------------------------------------------------------------------
# 한 이슈는 한 번만 (재처리 방지)
# ----------------------------------------------------------------------------
def valid_issue_number(value):
    """이슈 번호 형식이 올바르면 정수, 아니면 None(정수 또는 숫자 문자열만, bool 불가)."""
    if isinstance(value, bool):
        return None
    text = str(value) if isinstance(value, int) else value
    if isinstance(text, str) and re.fullmatch(ISSUE_NUMBER_PATTERN, text):
        return int(text)
    return None


def already_processed(number, refs=(), labels=(), prefix=DEFAULT_BRANCH_PREFIX, done_label=DONE_LABEL):
    """이 이슈를 이미 처리했는지(순수 함수, I/O 없음) → Processed(참이면 이미 처리함).

    근거 둘 중 하나면 처리한 것이다: ① 원격 브랜치 `refs/heads/<prefix><번호>-…` 가 있다 ② 표식 라벨(done_label)이 붙어 있다
    (브랜치는 병합 뒤 지워질 수 있어 라벨이 지속 표식이다).
    refs 는 `git ls-remote --heads` 출력 줄(`<sha>\\t<ref>`) 또는 ref 이름의 목록(문자열 하나도 가능). 앞부분을 고정한 전체 접두사
    (`refs/heads/issue-edit/12-`)로만 비교하므로 번호 경계(1·12·120)와 다른 경로(`feature/issue-edit/12-…`·태그)를 구분한다."""
    n = valid_issue_number(number)
    if n is None:
        return Processed()
    if isinstance(refs, str):
        refs = refs.splitlines()
    wanted = f"{REF_HEADS}{prefix}{n}-"
    branches = set()
    for line in refs or ():
        parts = str(line).split()
        if parts and parts[-1].startswith(wanted):
            branches.add(parts[-1][len(REF_HEADS):])
    names = {(item.get("name") if isinstance(item, dict) else str(item)) for item in (labels or ())}
    return Processed(tuple(sorted(branches)), done_label in names)


def _branch_prefix(root):
    """명세의 브랜치 접두사(읽을 수 없으면 기본값 — 명세 오류는 이어지는 resolve_request 가 알린다)."""
    try:
        output = spec_mod.load_spec(root).get("output")
    except spec_mod.SpecError:
        output = None
    prefix = output.get("branch_prefix") if isinstance(output, dict) else None
    return prefix if isinstance(prefix, str) and prefix else DEFAULT_BRANCH_PREFIX


def _duplicate(issue, done, env):
    """이미 처리한 이슈: 새 브랜치·PR 없이 이슈에 알리는 결과(status=duplicate)."""
    items = []
    repo, base = str(env.get("GITHUB_REPOSITORY", "")), str(env.get("DEFAULT_BRANCH", ""))
    can_link = bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) and re.fullmatch(r"[A-Za-z0-9_./-]{1,100}", base))
    for branch in done.branches[:5]:
        item = f"- 기존 브랜치: {_code(branch, 120)}"
        if can_link:
            item += f" — [비교·PR 만들기](https://github.com/{repo}/compare/{base}...{quote(branch, safe='/-._~')}?expand=1)"
        items.append(item)
    if done.labeled:
        items.append(f"- 처리 표식 라벨 {_code(DONE_LABEL)} 이(가) 붙어 있습니다.")
    message = "같은 이슈를 두 번 처리하지 않으므로 새 브랜치·PR 을 만들지 않았습니다."
    comment = (f"ℹ️ **이미 처리한 이슈입니다.** {message}\n\n" + "\n".join(items) + "\n\n"
               "PR 은 이슈 화면의 연결된 PR 이나 Pull requests 탭에서 위 브랜치 이름으로 찾을 수 있습니다. "
               "이슈를 고쳐 쓰거나 다시 열어도 다시 처리되지 않습니다 — 수정이 더 필요하면 새 이슈로 올려 주세요.")
    return Result("duplicate", message=message, reasons=[message], comment=comment)


def _ignored(issue):
    """처리 대상이 아닌 이슈(PR·권한 없는 작성자)면 ignored 결과, 아니면 None."""
    if "pull_request" in issue:
        return Result("ignored", message="PR 은 처리하지 않습니다.")
    assoc = str(issue.get("author_association") or "").upper()
    if assoc not in spec_mod.ALLOWED_ASSOCIATIONS:
        return Result("ignored", message=f"작성자 권한({assoc or '알 수 없음'})이 없어 처리하지 않습니다.")
    return None


PAUSE_VALUES = {"1", "true", "yes", "on"}   # Blogger 러너(pipeline/run.py)·Chance(generator.py)의 PIPELINE_PAUSE 와 같은 값 집합


def pause_on(env):
    """킬 스위치(저장소 변수 PIPELINE_PAUSE)가 켜져 있는가. 다른 파이프라인과 같은 규칙(1/true/yes/on, 대소문자·앞뒤 공백 무시)."""
    return str(env.get("PIPELINE_PAUSE", "")).strip().lower() in PAUSE_VALUES


def _paused(req):
    """정지 스위치가 켜졌을 때의 결과: AI·이미지 검색을 부르지 않고 파일·PR 도 만들지 않으며 이슈 코멘트로만 알린다(종료 코드 0)."""
    comment = ("⏸️ **일시정지 중입니다.**\n\n저장소 변수 `PIPELINE_PAUSE` 가 켜져 있어 이 요청을 처리하지 않았습니다"
               "(AI·이미지 검색도 부르지 않았고 저장소는 변경되지 않았습니다).\n\n"
               "변수를 지운 뒤 Actions 의 `이슈 수정 요청 처리(수정안 PR 만들기)` 에서 이 이슈 번호로 다시 실행해 주세요.")
    note = ("저장소 변수 PIPELINE_PAUSE 가 켜져 있어 이슈 수정 요청을 처리하지 않았습니다. 계속 멈춰 둘 것이 아니라면 "
            "Settings > Secrets and variables > Actions > Variables 에서 PIPELINE_PAUSE 를 지우세요.")
    return Result("paused", message="PIPELINE_PAUSE 가 켜져 있어 처리하지 않았습니다.", comment=comment, notes=[note],
                  edit_type=req.edit_key, target=req.target["path"])


def build_llm(env, registry_models_, calls=None):
    """calls(CallLog)를 넘기면 이번 실행의 Gemini 요청 기록이 거기에 쌓인다(무료 한도 측정, 러너가 요약과 로그에 쓴다)."""
    key = (env.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return None
    from pipeline.llm import make_gemini_llm
    return make_gemini_llm(key, registry_models_, max_retries=2, log=calls)


def registry_models(root):
    try:
        reg = registry_mod.load_registry(Path(root) / "pipeline" / "blogs.json")
        return reg["defaults"]["llm"]["models"]
    except (registry_mod.RegistryError, KeyError):
        return ["gemini-3.8-flash"]


# 레거시 엔진(generator.py)이 이미지를 고르며 print 하는 줄 중 요청 유래 텍스트(검색어 = AI 가 만든 검색어이거나 AI 가 없으면 요청 원문) 없이
# 알릴 수 있는 것만 참고 문장으로 옮긴다. 이 문구 목록은 generator.py 의 출력과 같아야 한다(테스트가 대조).
_IMAGE_SEARCH_NOTES = (
    (re.compile(r"\s*Unsplash API 오류 (\d{3})\b"), "Unsplash API 오류 {0} (403·429 이면 시간당 호출 한도 초과일 수 있습니다)"),
    (re.compile(r"\s*Unsplash 호출 실패\b"), "Unsplash 호출 실패(원인은 검색어가 섞여 있어 로그에 내지 않았습니다)"),
    (re.compile(r"\s*UNSPLASH_ACCESS_KEY 없음"), "UNSPLASH_ACCESS_KEY 없음: 이미지 검색을 건너뛰었습니다"),
)


def image_search_notes(output):
    """이미지 선택기가 낸 출력에서 로그에 남길 참고 문장 목록. 알려진 줄만 요약하고, 나머지는 줄 수만 알린다(요청 유래 텍스트·`##[` 를 싣지 않는다)."""
    notes, others = [], 0
    for line in str(output).splitlines():
        if not line.strip():
            continue
        for rx, template in _IMAGE_SEARCH_NOTES:
            match = rx.match(line)
            if match:
                note = template.format(*match.groups())
                if note not in notes:
                    notes.append(note)
                break
        else:
            others += 1
    if others:
        notes.append(f"이미지 검색기가 낸 그 밖의 출력 {others}줄은 요청 유래 텍스트가 섞여 있어 로그에 내지 않았습니다")
    return notes


def default_image_picker(notes=None):
    """레거시 엔진의 Unsplash 검색을 재사용한다(Phase 3에서 pipeline 으로 이관).

    generator.py 는 검색어·후보 주소를 print 한다. 그 줄은 `issue=#N` 머리가 없고 `##[` 도 막지 못하며 검색어에 요청 원문이 그대로 들어갈 수
    있다(AI 가 없으면 검색어 = 요청문). 그래서 호출 동안 stdout·stderr 를 가두고(stderr 로 나가는 `::warning::` 같은 줄도 같은 경로), 로그에는
    `image_search_notes` 가 요약한 문장만 notes 로 넘긴다."""
    if not (os.environ.get("UNSPLASH_ACCESS_KEY") or "").strip():
        return None
    import generator  # noqa: PLC0415 - 환경변수를 읽는 모듈이라 키 확인 뒤에만 import

    def pick(queries, used):
        captured = io.StringIO()
        try:
            with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                picked = generator.pick_images(queries, set(used), 1, allow_pool=False)
                if picked:
                    generator.trigger_download(picked[0])
        finally:
            if notes is not None:
                notes.extend(image_search_notes(captured.getvalue()))
        return picked[0] if picked else None
    return pick


# ----------------------------------------------------------------------------
# 요청 해석 (수정은 하지 않는다)
# ----------------------------------------------------------------------------
def resolve_request(issue, root):
    """Request 또는 Result(ignored/rejected/error). 파일을 읽기만 하고 아무것도 쓰지 않는다."""
    root = Path(root)
    login = _login(issue)   # 허용 문자만 남긴 값(커밋·PR 본문·로그에 그대로 들어가므로)
    assoc = str(issue.get("author_association") or "").upper()
    skipped = _ignored(issue)
    if skipped:
        return skipped

    try:
        spec = spec_mod.load_spec(root)
        problems = spec_mod.validate_spec(spec)
        if problems:
            return _error("수정 명세가 올바르지 않습니다: " + "; ".join(problems), EXIT_CONFIG)
        templates = forms.load_templates(root)
        labels = forms.label_map(templates)
        flabels = forms.field_labels(templates)
    except (spec_mod.SpecError, forms.FormError) as exc:
        return _error(str(exc), EXIT_CONFIG)

    issue_label, why = forms.identify_issue_label(issue, spec, templates, labels)
    if not issue_label:
        return _reject([why], "제공된 이슈 양식('고정 페이지 수정' 또는 '기존 게시글 이미지 변경')으로 작성해 주세요.")
    fields, duplicates = forms.parse_issue_body(issue.get("body") or "", labels)
    if duplicates:
        return _reject([f"항목 제목이 중복되었습니다: {', '.join(duplicates)} (본문 안에 양식 제목과 같은 줄이 있으면 처리할 수 없습니다)"])
    too_long = [flabels.get(k, k) for k, v in fields.items() if len(v) > MAX_FIELD_CHARS]
    if too_long:
        return _reject([f"입력이 너무 깁니다(최대 {MAX_FIELD_CHARS}자): {', '.join(too_long)}"])

    candidates = spec_mod.edit_types_for_label(spec, issue_label)
    if issue_label == "edit:page":
        edit_key = forms.option_id(fields.get("edit_type"))
        if edit_key not in candidates:
            return _reject([f"알 수 없는 수정 항목입니다: {_code(edit_key, 60) if edit_key else '(없음)'}"], "양식의 '수정 항목' 목록에서 선택해 주세요.")
    elif len(candidates) == 1:
        edit_key = next(iter(candidates))
    else:
        return _error(f"{issue_label} 에 수정 항목이 여러 개라 양식만으로 정할 수 없습니다(명세 확인).", EXIT_CONFIG)
    cfg = candidates[edit_key]

    missing = [flabels.get(k, k) for k in cfg["required"] if not fields.get(k)]
    if missing:
        return _reject([f"필수 항목이 비어 있습니다: {', '.join(missing)}"], edit_type=edit_key)

    if cfg["target"] == "page":
        page_id = forms.option_id(fields["target_page"])
        try:
            entry = pages.find_page(pages.load_registry(root), page_id)
        except pages.PagesError as exc:
            return _error(str(exc), EXIT_CONFIG)
        if not entry:
            return _reject([f"pages.json 에 없는 페이지입니다: {_code(page_id, 60)}"],
                           "새 페이지라면 front matter 에 `editable: true` 를 넣고 동기화를 기다려 주세요.", edit_key)
        target = {"path": entry["path"], "title": entry["title"], "id": entry["id"]}
    else:
        hits, how = targets.match_post(fields["target_post"], targets.load_post_index(root))
        if how == "invalid":
            return _reject(["게시글 주소/제목이 올바르지 않습니다(한 줄, 300자 이하)."], edit_type=edit_key)
        if not hits:
            return _reject(["일치하는 게시글을 찾지 못했습니다."],
                           "블로그에서 글을 열어 주소창의 공개 URL 을 복사하거나, 글 제목을 정확히 입력해 주세요.", edit_key)
        if len(hits) > 1:
            return _reject([f"여러 글({len(hits)}건)이 일치해 대상을 정할 수 없습니다: " + " / ".join(_code(d, 120) for d in targets.describe(hits))],
                           "공개 URL 로 정확히 지정해 주세요.", edit_key)
        target = {"path": hits[0]["path"], "title": hits[0]["title"], "id": Path(hits[0]["path"]).stem}

    path = target["path"]
    try:
        patterns = spec_mod.resolve_allowed(cfg, path)
    except ValueError:  # 레지스트리·인덱스가 변조되어 올바르지 않은 경로가 들어온 경우
        return _reject([f"{path} 은(는) 올바르지 않은 경로라 고칠 수 없는 경로입니다."], edit_type=edit_key)
    if not spec_mod.path_allowed(path, patterns):
        return _reject([f"{path} 은(는) 이 수정 항목으로 고칠 수 없는 경로입니다."], edit_type=edit_key, target=path)

    try:
        protected = protected_paths(root)
    except registry_mod.RegistryError as exc:
        return _error(f"블로그 레지스트리를 읽을 수 없어 광고 표면 여부를 확인할 수 없습니다: {exc}", EXIT_CONFIG)
    ad_surface = is_protected(path, protected)
    if ad_surface and assoc != "OWNER":
        return _reject([f"{path} 는 광고 심사 대상 페이지라 저장소 소유자(OWNER)의 요청만 처리합니다."], edit_type=edit_key, target=path)

    return Request(spec=spec, number=issue.get("number"), login=login, assoc=assoc, edit_key=edit_key, cfg=cfg,
                   fields=fields, target=target, patterns=patterns, ad_surface=ad_surface)


def check_mode(cfg):
    return {"front_matter": "front_matter", "image": "image"}.get(cfg["method"], "body")


# ----------------------------------------------------------------------------
# 본 처리
# ----------------------------------------------------------------------------
def process_issue(issue, root, env=None, llm=None, image_picker=None, dry_run=False, remote_refs=None, calls=None):
    """이슈 한 건을 처리한다. 이미 처리한 이슈(기존 브랜치·표식 라벨)면 코멘트용 결과(duplicate)만 돌려주고 아무것도 만들지 않는다.
    dry_run 은 예외다(시험 반복용) — 처리는 계속하고 로그에 참고 문장만 남긴다. remote_refs: `git ls-remote --heads` 출력 줄 목록."""
    env = os.environ if env is None else env
    root = Path(root)
    skipped = _ignored(issue)
    if skipped:
        return skipped
    number = valid_issue_number(issue.get("number"))
    if number is None:
        return _error("이슈 번호가 올바르지 않습니다(1~999999999 의 숫자).", EXIT_CONFIG)
    done = already_processed(number, remote_refs, issue.get("labels"), prefix=_branch_prefix(root))
    if done and not dry_run:
        return _duplicate(issue, done, env)
    search_notes = []   # 이미지 선택기(레거시 엔진)가 낸 출력의 요약 — 결과의 참고 문장으로 러너 로그에 `issue=#N …` 머리를 달고 나간다
    result = _process(issue, root, env, llm, image_picker, dry_run, search_notes, calls)
    result.notes.extend(search_notes)
    if done:
        result.notes.append("이미 처리한 이슈이지만 dry-run 이라 처리를 계속했습니다"
                            + (f"(기존 브랜치: {', '.join(done.branches)})" if done.branches else "(표식 라벨)"))
    return result


def _process(issue, root, env, llm, image_picker, dry_run, search_notes, calls=None):
    req = resolve_request(issue, root)
    if isinstance(req, Result):
        return req
    if pause_on(env):   # 정지 스위치: 요청이 유효해도 AI·이미지 검색·파일 수정 없이 알리기만 한다(resolve_request 는 파일을 읽기만 한다)
        return _paused(req)
    cfg, fields, target, path = req.cfg, req.fields, req.target, req.target["path"]
    limits = req.spec["limits"]

    file_path = root / path
    try:
        text, newline = frontmatter.read_file(file_path, strict=True)
    except frontmatter.LineEndingError:
        # 줄 끝이 섞인 파일을 한 가지로 다시 쓰면 요청하지 않은 줄 끝 변경이 파일 전체에 생긴다 → 고치지 않는다(fail closed)
        return _error(f"{path} 의 줄 끝이 LF·CRLF 혼합(또는 CR 단독)이라 줄 끝을 보존한 채 고칠 수 없어 수정하지 않았습니다. "
                      "줄 끝을 한 가지로 통일하는 수정이 먼저 필요합니다(저장소 관리자에게 요청).", EXIT_CONFIG)
    except (OSError, UnicodeDecodeError) as exc:
        return _error(f"대상 파일을 읽을 수 없습니다: {path} ({type(exc).__name__})", EXIT_CONFIG)
    if len(text) > limits["max_file_chars"]:
        return _reject([f"{path} 파일이 너무 커서({len(text)}자) 자동 수정하지 않습니다."], edit_type=req.edit_key, target=path)

    method = cfg["method"]
    try:
        if method in ("text", "llm_patch", "image") and llm is None:
            llm = build_llm(env, registry_models(root), calls)
        if method == "image" and image_picker is None:
            image_picker = default_image_picker(search_notes)
        if method == "text":
            new_text, how = ops.op_text(text, fields, cfg, llm)
        elif method == "link":
            new_text, how = ops.op_link(text, fields)
        elif method == "front_matter":
            new_text, how = ops.op_front_matter(text, fields, cfg)
        elif method == "llm_patch":
            new_text, how = ops.op_llm_patch(text, fields, cfg, llm), "AI 최소 패치"
        else:
            new_text, how = ops.op_image(text, fields, {"path": path, "title": target["title"]}, root, llm, image_picker)
    except ops.EditError as exc:
        return _reject([str(exc)], edit_type=req.edit_key, target=path)
    except ops.InfraError as exc:
        return _error(str(exc), log_detail=exc.detail)   # 원인 상세는 러너 로그에만(공개 코멘트에는 예외 종류까지만)

    reasons = checks.verify_changes({path: (text, new_text)}, req.patterns, limits, mode=check_mode(cfg),
                                    only_fields=cfg.get("only_fields"), ai_patch=(how == "AI 최소 패치"))
    if method == "image":   # 대표 이미지 주소만 바뀌었는지(허용 호스트·주소 형식·본문 불변) — PR 범위 검사와 같은 함수
        reasons = reasons + checks.verify_image_change(text, new_text)
    if reasons:
        return _reject(reasons, edit_type=req.edit_key, target=path)

    if not dry_run:
        frontmatter.write_file(file_path, new_text, newline)
    number, login, assoc = req.number, req.login, req.assoc
    run_no = re.sub(r"[^0-9]", "", str(env.get("GITHUB_RUN_NUMBER", "")))
    branch = f"{req.spec['output']['branch_prefix']}{number}-{_slug(target['id'])}" + (f"-r{run_no}" if run_no else "")
    lines = checks.changed_line_count(text, new_text)
    diff = checks.unified_diff(text, new_text, path)
    summary = (f"- 대상: `{path}` ({_code(target['title'])})\n- 수정 항목: {cfg['label']} (`{req.edit_key}`, 방식: {_code(how, 120)})\n"
               f"- 바뀐 줄: {lines}줄")
    trailer = f"\nAd-Surface-Approved: 이슈 #{number} @{login}(OWNER) 요청 — {path}" if req.ad_surface else ""
    commit = (f"fix: [이슈 #{number}] {_one_line(target['title'], 40)} {cfg['label']} (issue-edit 봇) [대상: Chance_Blog]\n\n"
              f"{summary}\n\nRefs: #{number}\nRequested-By: @{login} ({assoc}){trailer}\n")
    pr_title = f"[이슈 #{number}] {_one_line(target['title'], 50)} — {cfg['label']}"
    ad_note = ("\n> ⚠️ **광고 표면 페이지**입니다. 소유자 요청에 따른 수정이며, **병합이 곧 승인**입니다. 병합 전에 변경 내용을 꼭 확인하세요.\n"
               if req.ad_surface else "")
    pr_body = (f"이슈 #{number} (@{login})의 수정 요청을 자동으로 처리한 PR 입니다.{ad_note}\n\n{summary}\n\n"
               f"### 요청 내용\n{_fence(fields.get('after') or fields.get('user_prompt') or '')}\n\n"
               f"### 변경 내용\n{safety.fenced(diff, 'diff')}\n\n"   # 내용 속 ``` 줄이 펜스를 닫지 못하게 틸드 펜스(내용보다 길게)
               "### 리뷰 체크리스트\n- [ ] 요청한 항목만 바뀌었다\n- [ ] 사실·수치·링크가 맞다\n- [ ] 광고 코드·레이아웃은 그대로다\n\n"
               f"Fixes #{number}\n")
    if req.ad_surface:
        pr_body += f"\nAd-Surface-Approved: 이슈 #{number} @{login}(OWNER) 요청 — {path}\n"
    return Result("ok", message=f"{path} 수정안 생성", files=[path], branch=branch, edit_type=req.edit_key, target=path,
                  ad_surface=req.ad_surface, commit_message=commit, pr_title=pr_title, pr_body=pr_body, summary=summary)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def write_outputs(result, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = asdict(result)
    data.pop("log_detail", None)   # 마스킹했더라도 실패 원인 상세는 러너 로그에만 남긴다(산출물 폴더는 다른 단계·job 으로 넘어갈 수 있다)
    (out / "result.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "status.txt").write_text(result.status + "\n", encoding="utf-8")
    (out / "branch.txt").write_text(result.branch + "\n", encoding="utf-8")
    (out / "files.txt").write_text("".join(f + "\n" for f in result.files), encoding="utf-8")
    (out / "commit_msg.txt").write_text(result.commit_message, encoding="utf-8")
    (out / "pr_title.txt").write_text(result.pr_title + "\n", encoding="utf-8")
    (out / "pr_body.md").write_text(result.pr_body, encoding="utf-8")
    (out / "summary.md").write_text(result.summary + "\n", encoding="utf-8")
    (out / "comment.md").write_text(result.comment + "\n" if result.comment else "", encoding="utf-8")


def verify_staged(files_txt, root=None):
    """git 스테이징 목록이 허용된 파일 목록과 정확히 같은지 확인한다(0: 같음)."""
    expected = {ln.strip() for ln in Path(files_txt).read_text(encoding="utf-8").splitlines() if ln.strip()}
    res = subprocess.run(["git", "-c", "core.quotepath=false", "diff", "--cached", "--name-only"], cwd=root,
                         capture_output=True, check=True)
    staged = {ln.strip() for ln in res.stdout.decode("utf-8", "replace").splitlines() if ln.strip()}
    if staged != expected:   # 파일 이름은 신뢰할 수 없는 문자열이다(`##[` 같은 워크플로 명령 모양이 들어 있을 수 있다)
        print(f"스테이징 목록이 허용 목록과 다릅니다. 허용={safety.log_text(sorted(expected), 400)} 스테이징={safety.log_text(sorted(staged), 400)}")
        return 1
    return 0


SHOWN_FILES = ("status.txt", "files.txt", "comment.md", "summary.md", "pr_body.md")


def show_output(out_dir, write=None, token=None):
    """DRY_RUN: 산출물을 로그에 보여 준다. 요청 원문이 섞여 있어 워크플로 명령으로 해석되지 않도록 이중으로 막는다.

    1) `::stop-commands::<무작위 토큰>` 과 `::<토큰>::` 사이에서만 내용을 출력한다(토큰은 내용을 읽은 뒤에 만든다).
    2) 그래도 모든 내용 줄에서 비밀 모양 문자열을 가리고 `##[`·줄 시작 `::` 를 무력화한다.
    write(줄 하나)·token 은 테스트가 바꿔 끼운다."""
    write = write or (lambda line: print(line, flush=True))
    out = Path(out_dir)
    blocks = []
    for name in SHOWN_FILES:
        path = out / name
        if path.is_file():
            try:
                blocks.append((name, path.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                blocks.append((name, "(읽을 수 없음)"))
    token = token or secrets.token_hex(16)
    write(f"::stop-commands::{token}")
    for name, text in blocks:
        write(f"----- {name}")
        for line in text.splitlines():   # splitlines: \r·\v·\f·U+2028 같은 줄바꿈 변형도 줄로 나눠 각각 무력화한다
            write(safety.neutralize(safety.redact(line)))
    write(f"::{token}::")
    return 0


def write_step_summary(markdown, on_error=print):
    """Actions 실행 화면의 요약 칸(GITHUB_STEP_SUMMARY)에 덧붙인다. 로컬 실행에서는 아무 일도 하지 않고, 쓰기에 실패해도 처리 결과는 바꾸지 않는다
    (on_error 에는 예외 종류만 넘긴다 — 예외 원문은 내지 않는다)."""
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(markdown.rstrip() + "\n\n")
    except OSError as exc:
        on_error(f"실행 요약 쓰기 실패(처리 결과에는 영향 없음): {type(exc).__name__}")


def main(argv=None):
    safe_output()
    parser = argparse.ArgumentParser(prog="python -m pipeline.edits.runner")
    parser.add_argument("--issue-file")
    parser.add_argument("--out")
    parser.add_argument("--root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-staged")
    parser.add_argument("--show-output")
    parser.add_argument("--remote-refs")   # `git ls-remote --heads origin 'refs/heads/issue-edit/<번호>-*'` 출력 파일(재처리 확인)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]

    if args.show_output:
        return show_output(args.show_output)
    if args.verify_staged:
        return verify_staged(args.verify_staged, root)
    if not (args.issue_file and args.out):
        parser.error("--issue-file 과 --out 이 필요합니다.")
    dry = args.dry_run or str(os.environ.get("DRY_RUN", "")).lower() in ("1", "true", "yes")
    calls = CallLog(label="issue-edit")   # 이번 실행의 Gemini 요청 기록(무료 한도 측정). 줄은 아래에서 `issue=#N …` 머리를 달아 한 번에 낸다
    issue = {}
    try:
        issue = json.loads(Path(args.issue_file).read_text(encoding="utf-8"))
        if not isinstance(issue, dict):
            raise ValueError("이슈 데이터가 객체가 아닙니다")
    except (OSError, ValueError) as exc:   # json.JSONDecodeError 와 UnicodeDecodeError 는 ValueError 의 하위 클래스
        issue = {}
        result = _error(f"이슈 데이터를 읽을 수 없습니다: {type(exc).__name__}", EXIT_CONFIG)
    else:
        try:
            refs = Path(args.remote_refs).read_text(encoding="utf-8").splitlines() if args.remote_refs else None
        except (OSError, UnicodeDecodeError) as exc:   # 목록을 못 읽으면 이미 처리했는지 알 수 없다 → 처리하지 않는다(fail closed)
            result = _error(f"원격 브랜치 목록을 읽을 수 없습니다: {type(exc).__name__}", EXIT_CONFIG)
        else:
            try:
                result = process_issue(issue, root, dry_run=dry, remote_refs=refs, calls=calls)
            except Exception as exc:  # noqa: BLE001 - 예상 못 한 입력으로 처리기가 죽어도 트레이스백 대신 오류 결과를 남긴다
                if _is_test_signal(exc):
                    raise    # 러너를 거치는 시험의 단언·건너뛰기는 오류 결과로 가리지 않는다
                # 트레이스백에는 요청 유래 문구(예: urlsplit 의 값)가 섞일 수 있고 status.txt 도 없어 워크플로가 코멘트를 남기지 못한다.
                # 예외 문구는 쓰지 않고 종류(클래스 이름)만 공개 코멘트에 내고, 난 곳(파일:줄 함수)은 러너 로그에만 낸다.
                result = _error(f"이슈를 처리하다 예상하지 못한 오류가 발생했습니다: {type(exc).__name__}", log_detail=_crash_site(exc, root))
    write_outputs(result, args.out)
    # 이슈 처리 단계가 내는 모든 줄은 `issue=#N author=@login(권한)` 으로 시작하고, 신뢰할 수 없는 문자열은 한 줄로 접어 비밀을 가리고
    # 워크플로 명령 모양(`::`·`##[`)을 무력화한 것만 쓴다.
    tag = f"[issue-edit] {issue_tag(issue)}"
    log = safety.log_text
    print(f"{tag} status={result.status} edit={log(result.edit_type or '-', 60)} target={log(result.target or '-', 120)} "
          f"{'(dry-run) ' if dry else ''}{log(result.message, 300)}")
    for r in result.reasons:
        print(f"{tag}   - {log(r, 300)}")
    for note in result.notes:
        print(f"{tag}   * {log(note, 300)}")
    if result.log_detail:   # AI 실패 원인: 마스킹하고 300자로 자른 것을 러너 로그에만 낸다(공개 코멘트·result.json 에는 없다)
        print(f"{tag}   ! 원인(로그 전용): {log(result.log_detail, 300)}")
    # Gemini 요청 기록: 요청마다 한 줄(다른 줄과 같은 머리·마스킹·300자 한도)과 호출 수 요약. AI 를 부르지 않은 처리(문자 그대로 교체·링크·SEO)는
    # 로그 줄을 늘리지 않고 실행 요약에만 `Gemini 호출: 0회` 를 남긴다.
    ai_lines = calls.summary_lines()
    if calls.attempts:
        for record in calls.records:
            print(f"{tag}   * {log(call_line(record), 300)}")
        for line in ai_lines:
            print(f"{tag}   * {log(line, 300)}")
    write_step_summary(f"### 이슈 수정 요청 처리 요약\n- 결과: **{md_cell(result.status, 30)}**" + "".join(f"\n- {line}" for line in ai_lines),
                       on_error=lambda message: print(f"{tag}   * {log(message, 300)}"))
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
