"""워크플로 이름·run-name·Chance 이미지 교체 분리(chance-fix-images.yml) 구조 테스트.

실제 `.github/workflows/*.yml` 과 문서를 읽어 확인한다. GitHub Actions 를 실행할 수 없는 환경에서도
(1) 이름·입력 설명·단계 이름이 한글이고 문서의 대응표와 같은지,
(2) run-name 표현식이 정기·수동·이슈 이벤트에서 의도한 제목을 내고 외부 유래 문자열을 담지 않는지,
(3) chanceblog.yml 에서 분리한 chance-fix-images.yml 이 같은 권한·동시성·커밋·배포 단계를 유지하는지,
(4) 모든 워크플로 name·run-name 이 `[구분] ` 접두사(채널 라벨·공통·내부)로 시작하고 그 이름을 인용하는 안내가 접두사를 빠뜨리지 않았는지
구조로 증명한다.
"""
import os
import re
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap  # noqa: F401
from pipeline import registry

REAL = _bootstrap.ROOT
WORKFLOWS = REAL / ".github" / "workflows"
HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")


def workflow_paths():
    return sorted(p for p in WORKFLOWS.iterdir() if p.suffix in (".yml", ".yaml"))


def load(name):
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    if True in data and "on" not in data:  # YAML 1.1 은 키 on 을 True 로 읽는다
        data["on"] = data.pop(True)
    return data


# ----------------------------------------------------------------------------
# 옛 영문 워크플로 이름 검색(안내 문서·워크플로·이슈 양식·코드)
# ----------------------------------------------------------------------------
OLD_NAMES = {
    "Chance_Blog Full-Auto Engine": "[Chance] 글 자동 작성·게시",
    "Blogger Generate": "[Blogger] 글 자동 작성(초안함 업로드)",
    "Deploy GitHub Pages": "[공통] 사이트 자동 배포",
    "Guardrails": "[공통] 저장소 규칙·테스트 자동 검사",
    "PR Scope Check": "[공통] PR 변경 범위 검사",
    "Sync Issue Form": "[공통] 이슈 양식 페이지 목록 갱신",
    "Issue Edit": "[Chance] 이슈 수정 요청 처리(수정안 PR 만들기)",
}  # 'Watchdog' 은 일부러 뺐다: 이슈 제목 접두어 [Watchdog]·라벨 watchdog 은 식별자이고 문서에서는 감시 장치 자체를 가리키기도 한다
OLD_NAME_SUFFIXES = (".md", ".yml", ".yaml", ".py")
OLD_NAME_SKIP_DIRS = {"_posts", "_blogger_drafts", ".git", "assets", ".design", "__pycache__", "node_modules", ".venv", "venv"}
# 옛 이름이 일부러 남아 있는 파일(이유를 적는다). 늘리기 전에 정말 과거 기록이나 대응표 상수인지 확인한다.
OLD_NAME_ALLOWED_FILES = {
    "WORKLOG.md": "과거 사실의 기록(이력)이라 고치지 않는다",
    "tests/test_workflow_names.py": "옛 이름 → 새 이름 대응표 상수(OLD_NAMES)와 이 검색의 시험 자료가 이 파일에 있다",
}


def find_old_names(root, allowed=OLD_NAME_ALLOWED_FILES):
    """root 아래 안내 문서·워크플로·이슈 양식·코드(.md .yml .yaml .py)에서 옛 영문 이름이 새 이름 없이 쓰인 줄을 찾는다.
    알림문·요약 제목·독스트링·주석을 가리지 않고 줄 단위로 본다. 한 줄에 새 이름이 같이 있으면(대응표·'옛 이름 …' 설명) 허용한다."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in OLD_NAME_SKIP_DIRS)
        for name in sorted(filenames):
            if not name.endswith(OLD_NAME_SUFFIXES):
                continue
            path = Path(dirpath, name)
            rel = path.relative_to(root).as_posix()
            if rel in allowed:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                for old, new in OLD_NAMES.items():
                    if old in line and new not in line:
                        found.append(f"{rel}:{lineno}: {old}")
    return found


# ----------------------------------------------------------------------------
# GitHub 표현식(run-name 에 쓰는 부분집합) 해석기 — 정기 실행처럼 inputs 가 비는 경우의 결과를 확인하려는 용도
# ----------------------------------------------------------------------------
class ExprError(ValueError):
    pass


_TOKEN = re.compile(
    r"\s*(?:(?P<op>\|\||&&|==|!=|[()!])|'(?P<str>(?:[^']|'')*)'|(?P<id>[A-Za-z_][A-Za-z0-9_.\-]*)|(?P<num>\d+))")


def _tokens(src):
    src, pos, out = src.strip(), 0, []
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m:
            raise ExprError(f"읽을 수 없는 표현식: {src[pos:pos + 30]!r}")
        pos = m.end()
        if m.group("op") is not None:
            out.append(("op", m.group("op")))
        elif m.group("str") is not None:
            out.append(("val", m.group("str").replace("''", "'")))
        elif m.group("id") is not None:
            out.append(("id", m.group("id")))
        else:
            out.append(("val", int(m.group("num"))))
    return out


def _truthy(value):
    return not (value is None or value is False or value == 0 or value == "")


class _Parser:
    """`||` < `&&` < `==`·`!=` < `!` 순서의 우선순위. `a && b`·`a || b` 는 GitHub 처럼 피연산자 값을 돌려준다."""

    def __init__(self, src, ctx):
        self.toks, self.i, self.ctx = _tokens(src), 0, ctx

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self):
        value = self.or_()
        if self.i != len(self.toks):
            raise ExprError("표현식 끝에 남은 토큰이 있습니다")
        return value

    def or_(self):
        value = self.and_()
        while self.peek() == ("op", "||"):
            self.take()
            right = self.and_()
            value = value if _truthy(value) else right
        return value

    def and_(self):
        value = self.eq()
        while self.peek() == ("op", "&&"):
            self.take()
            right = self.eq()
            value = right if _truthy(value) else value
        return value

    def eq(self):
        # 한계(독립 검증 V-09): GitHub 는 종류가 다른 두 값을 `==`·`!=` 로 비교할 때 둘을 숫자로 바꿔 비교한다(문서: "If the types do not
        # match, GitHub coerces the type to a number" — 예: '1' == 1, true == 1, null == 0, '' == 0, '0' == false). 이 해석기는 같은 종류끼리만
        # GitHub 처럼 비교하고(문자열은 대소문자 무시), 종류가 다르면 파이썬의 `==` 를 써서 그 형 변환을 구현하지 않았다 — 검증자의 대조에서
        # 144쌍 중 20쌍이 GitHub 와 다르다. 지금 워크플로의 식은 문자열 비교(`github.event_name == '…'`·`… == 'true'`)뿐이라 영향이 없다.
        # 숫자·불리언을 `==` 로 비교하는 식을 새로 쓰게 되면 그 전에 이 해석기에 형 변환을 구현한다.
        value = self.unary()
        while self.peek() in (("op", "=="), ("op", "!=")):
            op = self.take()[1]
            right = self.unary()
            if isinstance(value, str) and isinstance(right, str):
                same = value.casefold() == right.casefold()  # GitHub 은 문자열 비교에서 대소문자를 구분하지 않는다
            else:
                same = value == right
            value = same if op == "==" else not same
        return value

    def unary(self):
        if self.peek() == ("op", "!"):
            self.take()
            return not _truthy(self.unary())
        return self.primary()

    def primary(self):
        kind, text = self.take()
        if (kind, text) == ("op", "("):
            value = self.or_()
            if self.take() != ("op", ")"):
                raise ExprError("닫는 괄호가 없습니다")
            return value
        if kind == "val":
            return text
        if kind == "id":
            consts = {"true": True, "false": False, "null": None}
            return consts[text] if text in consts else self.lookup(text)
        raise ExprError(f"예상하지 못한 토큰: {kind} {text}")

    def lookup(self, path):
        node = self.ctx
        for part in path.split("."):
            if not isinstance(node, dict):
                return None  # 없는 값은 null (정기 실행의 inputs 가 이 경우다)
            node = node.get(part)
        return node


def render(template, ctx):
    def one(match):
        value = _Parser(match.group(1), ctx).parse()
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    return re.sub(r"\$\{\{(.*?)\}\}", one, template)


def context(event, inputs=None, issue=None):
    """정기 실행(schedule)은 inputs 가 비어 있고, 이슈 이벤트만 github.event.issue 가 있다."""
    payload = {"issue": {"number": issue}} if issue is not None else {}
    return {"github": {"event_name": event, "event": payload}, "inputs": inputs or {}}


class ExpressionHelperTest(unittest.TestCase):
    """해석기 자체가 GitHub 의 규칙(피연산자 반환, 문자열 truthy, null 전파)을 따르는지."""

    def ev(self, text, ctx=None):
        return _Parser(text, ctx or {}).parse()

    def test_and_or_return_operands_like_github(self):
        self.assertEqual(self.ev("true && 'a' || 'b'"), "a")
        self.assertEqual(self.ev("false && 'a' || 'b'"), "b")
        self.assertEqual(self.ev("null && 'a' || 'b'"), "b")
        self.assertEqual(self.ev("'false' && 'a' || 'b'"), "a")  # 문자열 'false' 는 참이다
        self.assertEqual(self.ev("1 == 1 && ('x' || 'y')"), "x")

    def test_missing_context_values_are_null(self):
        self.assertIsNone(self.ev("inputs.dry_run", {"inputs": {}}))
        self.assertIsNone(self.ev("github.event.issue.number", {"github": {"event": {}}}))
        self.assertEqual(self.ev("inputs.a || 'none'", {"inputs": {}}), "none")

    def test_string_equality_ignores_case_and_negation_works(self):
        self.assertTrue(self.ev("github.event_name == 'Schedule'", {"github": {"event_name": "schedule"}}))
        self.assertFalse(self.ev("!true"))
        self.assertTrue(self.ev("'a' != 'b'"))

    def test_bad_expressions_raise(self):
        for bad in ("a &&", "(a", "a b", "'unclosed"):
            with self.assertRaises(ExprError):
                self.ev(bad, {"a": 1, "b": 2})


# ----------------------------------------------------------------------------
# 1) 이름: 워크플로·입력 설명·단계 이름은 한글, 문서 대응표와 일치
# ----------------------------------------------------------------------------
class KoreanNamesTest(unittest.TestCase):
    def test_workflow_dispatch_input_descriptions_are_korean(self):
        checked = 0
        for path in workflow_paths():
            inputs = (load(path.name)["on"].get("workflow_dispatch") or {}).get("inputs") or {}
            for key, spec in inputs.items():
                checked += 1
                self.assertRegex(spec.get("description", ""), HANGUL, f"{path.name}: 입력 {key} 의 description 에 한글이 없습니다")
        self.assertGreaterEqual(checked, 8)

    def test_explicit_step_names_are_not_english_only(self):
        for path in workflow_paths():
            for job_id, job in load(path.name)["jobs"].items():
                for step in job.get("steps", []):
                    if "name" in step:
                        self.assertRegex(step["name"], HANGUL, f"{path.name} {job_id}: 영어로만 된 단계 이름 {step['name']!r}")

    def test_every_run_name_is_korean(self):
        seen = 0
        for path in workflow_paths():
            run_name = load(path.name).get("run-name")
            if run_name is not None:
                seen += 1
                self.assertRegex(run_name, HANGUL, path.name)
        self.assertGreaterEqual(seen, 5)  # chanceblog · chance-fix-images · blogger · watchdog · issue-edit

    def test_blogger_dry_run_description_says_what_unchecking_it_does(self):
        """blogger.yml 의 dry_run 은 기본이 켜짐이다(2026-10-25 수동 실행 기본값 변경, D-51). 체크를 풀면 실제 Gemini 로 초안을 만들어 저장소에
        커밋하고 하루 상한을 쓴다 — Run workflow 대화상자의 입력 설명이 그 사실을 알려야 한다(기본값 자체는 test_manual_run_defaults.py 가 고정한다)."""
        description = load("blogger.yml")["on"]["workflow_dispatch"]["inputs"]["dry_run"]["description"]
        self.assertIn("체크를 풀면", description)
        self.assertIn("커밋", description)
        self.assertIn("하루 상한", description)

    def test_docs_tables_list_every_workflow_with_its_current_name(self):
        """워크플로 이름을 바꾸거나 새 워크플로를 만들면 두 문서의 대응표(`파일`과 `이름`이 같은 줄)도 고쳐야 한다."""
        for doc in ("docs/ARCHITECTURE.md", "docs/REQUEST_BRIEFING.md"):
            lines = (REAL / doc).read_text(encoding="utf-8").splitlines()
            for path in workflow_paths():
                name = load(path.name)["name"]
                rows = [ln for ln in lines if ln.lstrip().startswith("|") and f"`{path.name}`" in ln and f"`{name}`" in ln]
                self.assertTrue(rows, f"{doc} 표에 {path.name} 행(이름 `{name}`)이 없습니다")

    def test_operator_docs_do_not_use_the_old_english_names(self):
        """옛 영문 이름이 남아 있으면 운영자가 Actions 화면에서 찾지 못하고, 알림문이 없는 이름을 가리킨다(워치독이 'Deploy GitHub
        Pages' 를 찾으라고 안내하던 사례). 안내 문서뿐 아니라 워크플로·이슈 양식·코드의 알림문·요약 제목·독스트링·주석도 본다.
        옛 이름과 새 이름이 한 줄에 같이 있는 대응표는 허용하고, 과거 기록인 WORKLOG.md 는 보지 않는다(OLD_NAME_ALLOWED_FILES)."""
        self.assertEqual(find_old_names(REAL), [])

    def test_old_name_scan_covers_docs_workflows_issue_forms_and_code(self):
        """위 검색이 실제로 .md 뿐 아니라 .yml(주석 포함)·.py(문자열·독스트링)도 보고, 허용 항목은 건너뛰는지."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "docs/a.md": "Actions → Blogger Generate 실행\n",
                ".github/workflows/w.yml": "# 옛 이름 Issue Edit\nname: x\n",
                ".github/ISSUE_TEMPLATE/f.yml": "description: PR Scope Check 코멘트\n",
                "pipeline/h.py": 'MSG = "성공한 \'Deploy GitHub Pages\' 실행이 없습니다"\n',
                "scripts/s.py": '"""Sync Issue Form 이 부른다."""\n',
                "docs/ok.md": "| Guardrails | `[공통] 저장소 규칙·테스트 자동 검사` | `guardrails.yml` |\n",  # 대응표: 새 이름이 같은 줄
                "WORKLOG.md": "Blogger Generate (과거 기록)\n",  # 허용 파일
                "data.json": '{"x": "Blogger Generate"}\n',  # 검사하지 않는 확장자
                "_posts/p.md": "Blogger Generate\n",  # 글 폴더는 건너뜀
            }
            for rel, content in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            self.assertEqual(sorted(find_old_names(root)), [
                ".github/ISSUE_TEMPLATE/f.yml:1: PR Scope Check",
                ".github/workflows/w.yml:1: Issue Edit",
                "docs/a.md:1: Blogger Generate",
                "pipeline/h.py:1: Deploy GitHub Pages",
                "scripts/s.py:1: Sync Issue Form",
            ])
            self.assertEqual(sorted(find_old_names(root, allowed={})), [
                ".github/ISSUE_TEMPLATE/f.yml:1: PR Scope Check",
                ".github/workflows/w.yml:1: Issue Edit",
                "WORKLOG.md:1: Blogger Generate",
                "docs/a.md:1: Blogger Generate",
                "pipeline/h.py:1: Deploy GitHub Pages",
                "scripts/s.py:1: Sync Issue Form",
            ])


# ----------------------------------------------------------------------------
# 2) run-name: 정기·수동·연습 표시, 외부 유래 문자열 금지
# ----------------------------------------------------------------------------
class RunNameTest(unittest.TestCase):
    def title(self, workflow, event, inputs=None, issue=None):
        return render(load(workflow)["run-name"], context(event, inputs, issue))

    def test_chance_posting_titles(self):
        self.assertEqual(self.title("chanceblog.yml", "schedule"), "[Chance] 글 작성·게시 · 정기")
        self.assertEqual(self.title("chanceblog.yml", "workflow_dispatch", {"dry_run": True}),
                         "[Chance] 글 작성·게시 · 수동(연습: 저장 안 함)")
        self.assertEqual(self.title("chanceblog.yml", "workflow_dispatch", {"dry_run": False}), "[Chance] 글 작성·게시 · 수동")
        self.assertEqual(self.title("chanceblog.yml", "workflow_dispatch", {"dry_run": True, "real_ai": True}),
                         "[Chance] 글 작성·게시 · 수동(연습: 실제 AI 호출·저장 안 함)")
        self.assertEqual(self.title("chanceblog.yml", "workflow_dispatch", {"dry_run": False, "real_ai": True}), "[Chance] 글 작성·게시 · 수동")

    def test_chance_fix_images_titles(self):
        self.assertEqual(self.title("chance-fix-images.yml", "workflow_dispatch", {"dry_run": True}),
                         "[Chance] 기존 글 이미지 교체 · 연습(저장 안 함)")
        self.assertEqual(self.title("chance-fix-images.yml", "workflow_dispatch", {"dry_run": False}),
                         "[Chance] 기존 글 이미지 교체 · 실제 교체")
        self.assertEqual(self.title("chance-fix-images.yml", "workflow_dispatch", {"dry_run": True, "real_ai": True}),
                         "[Chance] 기존 글 이미지 교체 · 연습(실제 AI 호출·저장 안 함)")

    def test_blogger_titles(self):
        self.assertEqual(self.title("blogger.yml", "schedule"), "[Blogger] 글 작성 · 정기")
        # 수동 실행의 publish 는 3택(off=저장소 파일만, draft=Blogger 초안함 업로드, publish=즉시 게시)이다
        manual = {"dry_run": False, "publish": "draft"}
        self.assertEqual(self.title("blogger.yml", "workflow_dispatch", manual), "[Blogger] 글 작성 · 수동(Blogger 초안함 업로드)")
        self.assertEqual(self.title("blogger.yml", "workflow_dispatch", {**manual, "publish": "off"}),
                         "[Blogger] 글 작성 · 수동(저장소 파일만 저장)")
        self.assertEqual(self.title("blogger.yml", "workflow_dispatch", {**manual, "publish": "publish"}),
                         "[Blogger] 글 작성 · 수동(즉시 게시)")
        self.assertEqual(self.title("blogger.yml", "workflow_dispatch", {"dry_run": True, "publish": "off"}),
                         "[Blogger] 글 작성 · 수동(연습: 저장·게시 안 함)")
        # 연습이면 선택과 무관하게 아무것도 올리지 않는다(blogger.yml 의 DRY_RUN 이 우선)
        for choice in ("off", "draft", "publish"):
            self.assertEqual(self.title("blogger.yml", "workflow_dispatch", {"dry_run": True, "publish": choice}),
                             "[Blogger] 글 작성 · 수동(연습: 저장·게시 안 함)")
        # '인증 점검만 실행'은 글을 만들지 않으므로 다른 선택(연습·publish)보다 제목에 먼저 드러난다
        for dry_run in (False, True):
            for choice in ("off", "draft", "publish"):
                self.assertEqual(self.title("blogger.yml", "workflow_dispatch",
                                            {"auth_check": True, "dry_run": dry_run, "publish": choice}),
                                 "[Blogger] 글 작성 · 수동(인증 점검만: 글 안 만듦)")
        self.assertEqual(self.title("blogger.yml", "workflow_dispatch", {"auth_check": False, "dry_run": False, "publish": "draft"}),
                         "[Blogger] 글 작성 · 수동(Blogger 초안함 업로드)")
        self.assertEqual(self.title("blogger.yml", "schedule", {"auth_check": True}), "[Blogger] 글 작성 · 정기")

    def test_watchdog_titles(self):
        self.assertEqual(self.title("watchdog.yml", "schedule"), "[공통] 발행 중단 감시 · 정기")
        self.assertEqual(self.title("watchdog.yml", "workflow_dispatch"), "[공통] 발행 중단 감시 · 수동")

    def test_ops_inbox_titles(self):
        self.assertEqual(self.title("ops-inbox.yml", "schedule"), "[공통] 확인 필요 모음 갱신 · 정기")
        self.assertEqual(self.title("ops-inbox.yml", "workflow_dispatch", {"dry_run": False}), "[공통] 확인 필요 모음 갱신 · 수동")
        self.assertEqual(self.title("ops-inbox.yml", "workflow_dispatch", {"dry_run": True}),
                         "[공통] 확인 필요 모음 갱신 · 수동(연습: 이슈·코멘트 안 씀)")

    def test_issue_edit_titles_show_the_issue_number(self):
        self.assertEqual(self.title("issue-edit.yml", "issues", issue=12), "[Chance] 이슈 #12 수정 요청 처리 · 자동(이슈 등록 시)")
        self.assertEqual(self.title("issue-edit.yml", "workflow_dispatch", {"issue_number": "7", "dry_run": True}),
                         "[Chance] 이슈 #7 수정 요청 처리 · 수동(연습: PR·코멘트 안 만듦)")
        self.assertEqual(self.title("issue-edit.yml", "workflow_dispatch", {"issue_number": "7", "dry_run": False}),
                         "[Chance] 이슈 #7 수정 요청 처리 · 수동")

    ALLOWED_REFS = {"github.event_name", "github.event.issue.number", "inputs.dry_run", "inputs.publish", "inputs.issue_number",
                    "inputs.auth_check", "inputs.real_ai"}

    def test_run_names_only_use_event_kind_numbers_and_booleans(self):
        """run-name 에는 이슈 제목·PR 제목·브랜치명·자유 입력(blog, topic) 같은 외부 유래 문자열을 넣지 않는다."""
        for path in workflow_paths():
            run_name = load(path.name).get("run-name")
            if run_name is None:
                continue
            for body in re.findall(r"\$\{\{(.*?)\}\}", run_name):
                code = re.sub(r"'(?:[^']|'')*'", "''", body)  # 문자열 리터럴(제목 조각)은 값 참조가 아니다
                refs = set(re.findall(r"[A-Za-z_][A-Za-z0-9_\-]*(?:\.[A-Za-z0-9_\-]+)+", code))
                self.assertLessEqual(refs, self.ALLOWED_REFS, f"{path.name}: run-name 이 허용되지 않은 값을 참조합니다")


# ----------------------------------------------------------------------------
# 3) chanceblog.yml 에서 chance-fix-images.yml 로 분리: 동작은 그대로
# ----------------------------------------------------------------------------
class ChanceSplitTest(unittest.TestCase):
    def setUp(self):
        self.chance = load("chanceblog.yml")
        self.fix = load("chance-fix-images.yml")

    @staticmethod
    def steps(workflow):
        return workflow["jobs"]["build"]["steps"]

    @staticmethod
    def normalized(step, drop_env=()):
        """사람이 읽는 이름과 FIX_IMAGES 스위치만 빼고 단계가 같은지 비교하려고 정규화한다."""
        step = dict(step)
        step.pop("name", None)
        if "env" in step:
            step["env"] = {k: v for k, v in step["env"].items() if k not in drop_env}
        if isinstance(step.get("run"), str):
            step["run"] = "\n".join(line.rstrip() for line in step["run"].strip().splitlines())
        return step

    def test_chanceblog_no_longer_has_the_fix_images_switch(self):
        inputs = self.chance["on"]["workflow_dispatch"]["inputs"]
        self.assertEqual(list(inputs), ["dry_run", "real_ai"])        # 이미지 교체 입력은 없고, 연습에서 실제 AI 를 켜는 real_ai 만 더해졌다
        self.assertEqual((inputs["dry_run"]["type"], inputs["dry_run"]["default"]), ("boolean", True))
        self.assertEqual((inputs["real_ai"]["type"], inputs["real_ai"]["default"]), ("boolean", False))
        for step in self.steps(self.chance):
            self.assertNotIn("FIX_IMAGES", step.get("env", {}))
        text = (WORKFLOWS / "chanceblog.yml").read_text(encoding="utf-8").lower()
        self.assertNotIn("fix_images", text)

    def test_chanceblog_keeps_its_schedule_and_posting_flow(self):
        # 2026-10-26 운영자 승인(D-59): 매시 17분에 47분 틱을 더했다(게시는 슬롯 규칙이 하루 2편으로 지킨다)
        self.assertEqual(self.chance["on"]["schedule"], [{"cron": "17 * * * *"}, {"cron": "47 * * * *"}])
        gen = next(s for s in self.steps(self.chance) if s.get("run") == "python generator.py")
        self.assertEqual(gen["env"]["EVENT_NAME"], "${{ github.event_name }}")
        self.assertIn("inputs.dry_run", gen["env"]["DRY_RUN"])
        self.assertIn("PIPELINE_PAUSE", gen["env"])

    def test_fix_images_workflow_is_manual_only_with_dry_run_on_by_default(self):
        self.assertEqual(list(self.fix["on"]), ["workflow_dispatch"])
        inputs = self.fix["on"]["workflow_dispatch"]["inputs"]
        self.assertEqual(list(inputs), ["dry_run", "real_ai"])
        self.assertEqual((inputs["dry_run"]["type"], inputs["dry_run"]["default"]), ("boolean", True))
        self.assertEqual((inputs["real_ai"]["type"], inputs["real_ai"]["default"]), ("boolean", False))

    def test_fix_images_workflow_sets_the_mode_and_passes_the_pause_switch(self):
        gen = next(s for s in self.steps(self.fix) if s.get("run") == "python generator.py")
        env = gen["env"]
        self.assertEqual(env["FIX_IMAGES"], "1")
        self.assertEqual(env["DRY_RUN"], "${{ github.event_name == 'workflow_dispatch' && inputs.dry_run && '1' || '0' }}")
        self.assertEqual(env["PIPELINE_PAUSE"], "${{ vars.PIPELINE_PAUSE }}")
        # 연습 실행의 기본은 가짜 AI 응답이라 real_ai 를 체크하지 않으면 키를 넘기지 않는다(식의 평가는 test_manual_run_defaults.py)
        self.assertEqual(env["GEMINI_API_KEY"], "${{ (github.event_name != 'workflow_dispatch' || !inputs.dry_run || inputs.real_ai) "
                                                "&& secrets.GEMINI_API_KEY || '' }}")
        self.assertEqual(env["UNSPLASH_ACCESS_KEY"], "${{ secrets.UNSPLASH_ACCESS_KEY }}")

    def test_permissions_concurrency_and_job_limits_are_the_same(self):
        # 승인 흐름(publish_flow: pr)이 PR 을 열려고 chanceblog.yml 만 pull-requests: write 를 더 가진다(이미지 교체는 PR 을 열지 않는다)
        self.assertEqual(self.fix["permissions"], {"contents": "write", "actions": "write"})
        self.assertEqual(self.chance["permissions"], {**self.fix["permissions"], "pull-requests": "write"})
        # 같은 그룹이라 글 작성 실행과 이미지 교체 실행이 동시에 돌아 커밋이 겹치는 일이 없다
        self.assertEqual(self.fix["concurrency"], self.chance["concurrency"])
        self.assertEqual(self.fix["concurrency"], {"group": "chanceblog", "cancel-in-progress": False})
        self.assertEqual(list(self.fix["jobs"]), list(self.chance["jobs"]))
        for key in ("runs-on", "timeout-minutes"):
            self.assertEqual(self.fix["jobs"]["build"][key], self.chance["jobs"]["build"][key], key)

    @staticmethod
    def direct_path(step):
        """chanceblog.yml 의 직접 게시(direct) 경로 비교용: 커밋 단계 조건에서 승인 흐름 한 조각을 뗀다(그 조각이 direct 에서 참이라는 것은
        test_chance_draft_workflow.py 가 모든 조합으로 대조한다)."""
        step = dict(step)
        if isinstance(step.get("if"), str):
            step["if"] = step["if"].replace(" && steps.flow.outputs.flow != 'pr'", "")
        return step

    def chance_direct_steps(self):
        """승인 흐름이 더한 두 단계('발행 흐름 확인'·'초안 올리기')를 뺀 chanceblog.yml 단계."""
        return [self.direct_path(s) for s in self.steps(self.chance)
                if s.get("id") != "flow" and "pipeline.draft_flow" not in s.get("run", "")]

    def test_steps_are_identical_except_the_fix_images_switch(self):
        a = [self.normalized(s) for s in self.chance_direct_steps()]
        b = [self.normalized(s, drop_env=("FIX_IMAGES",)) for s in self.steps(self.fix)]
        self.assertEqual(len(a), 6)  # checkout · setup-python · 의존성 · 생성기 · 커밋 · Pages 배포 요청
        self.assertEqual(a, b)

    def test_the_draft_flow_added_exactly_two_steps_to_chanceblog(self):
        added = [s for s in self.steps(self.chance) if s.get("id") == "flow" or "pipeline.draft_flow" in s.get("run", "")]
        self.assertEqual(len(added), 2)
        self.assertEqual(len(self.steps(self.chance)), 8)
        self.assertEqual(len(self.steps(self.fix)), 6)                  # 이미지 교체 워크플로는 승인 흐름과 무관하다(새 글을 만들지 않는다)

    def test_fix_images_workflow_still_commits_and_requests_the_pages_deploy(self):
        commit = next(s for s in self.steps(self.fix) if s.get("id") == "commit")
        self.assertIn("git push", commit["run"])
        self.assertIn("GITHUB_STEP_SUMMARY", commit["run"])
        self.assertIn("inputs.dry_run", commit["if"])  # 연습 실행은 커밋하지 않는다
        deploy = self.steps(self.fix)[-1]
        self.assertIn("gh workflow run pages.yml", deploy["run"])
        self.assertEqual(deploy["if"], "steps.commit.outputs.pushed == 'true'")


# ----------------------------------------------------------------------------
# 4) 이름 접두사 `[구분] `: 채널 라벨(레지스트리 channel.label)·공통·내부
# ----------------------------------------------------------------------------
PREFIX_LABELS = set(registry.CHANNEL_LABELS) | {"공통", "내부"}
QUOTE_MARKS = ("`", "'", '"', "**")
# 접두사를 붙이기 전(2026-10-25 한글화 이후 ~ 2026-10-27)의 워크플로 이름 → 지금 이름. 안내 문서·코드가 옛 이름을 따옴표·백틱·굵게로 인용하면
# 운영자가 Actions 목록에서 그 이름을 찾지 못한다(목록에는 새 이름이 보인다). 이름을 또 바꾸면 지금 이름을 여기 옛 이름으로 옮겨 적는다.
PREVIOUS_NAMES = {
    "Chance 글 자동 작성·게시": "[Chance] 글 자동 작성·게시",
    "Chance 기존 글 이미지 교체(수동)": "[Chance] 기존 글 이미지 교체(수동)",
    "이슈 수정 요청 처리(수정안 PR 만들기)": "[Chance] 이슈 수정 요청 처리(수정안 PR 만들기)",
    "Blogger 글 자동 작성": "[Blogger] 글 자동 작성(초안함 업로드)",
    "사이트 자동 배포": "[공통] 사이트 자동 배포",
    "저장소 규칙·테스트 자동 검사": "[공통] 저장소 규칙·테스트 자동 검사",
    "PR 변경 범위 검사": "[공통] PR 변경 범위 검사",
    "이슈 양식 페이지 목록 갱신": "[공통] 이슈 양식 페이지 목록 갱신",
    "발행 중단 감시·알림": "[공통] 발행 중단 감시·알림",
    "확인 필요 모음": "[공통] 확인 필요 모음",
    # 새로 만든 채널 워크플로(2026-10-27)는 접두사 없던 시절이 없다. 문서가 `[구분]` 을 빼고 인용하지 않게 접두사 없는 모양을 같은 표에 둔다
    "티스토리 초안 패키지 만들기": "[티스토리] 초안 패키지 만들기",
    "네이버 초안 패키지 만들기": "[네이버] 초안 패키지 만들기",
}
# 이전 이름 인용 검색(find_previous_name_quotes)에서 빼는 곳(이유를 적는다). 안내 문서·코드·워크플로는 지금 이름으로 인용해야 하고,
# 아래는 날짜가 붙은 기록이거나 총괄이 따로 갱신하는 현황·브리핑 문서이거나 시험 자료다. '/' 로 끝나면 폴더 전체다.
PREVIOUS_NAME_QUOTE_ALLOWED = {
    "WORKLOG.md": "과거 사실의 기록(이력)이라 고치지 않는다",
    "docs/DEFECT_REGISTER.md": "날짜가 붙은 결함 기록이라 당시 이름 그대로 둔다",
    "docs/analysis/": "날짜가 붙은 분석 보고라 당시 이름 그대로 둔다",
    "docs/SESSION_START.md": "총괄이 갱신하는 현황 문서",
    "docs/REQUEST_BRIEFING.md": "총괄이 갱신하는 브리핑 문서(이름 표는 test_docs_tables_list_every_workflow_with_its_current_name 이 따로 본다)",
    "인수인계/": "작업 현황·요청서 기록",
    "tests/": "시험 자료(가짜 이름·옛 이름 시나리오를 일부러 담는다)",
}


def current_names():
    return {path.name: load(path.name)["name"] for path in workflow_paths()}


def find_previous_name_quotes(root, previous=PREVIOUS_NAMES, allowed=PREVIOUS_NAME_QUOTE_ALLOWED):
    """root 아래 안내 문서·워크플로·코드(.md .yml .yaml .py)에서 이전 이름이 백틱·따옴표·굵게(**)로 감싸여 인용됐는데 지금 이름이 같은 줄에 없는 곳을
    찾는다. 이름만 접두사로 바뀐 것(`사이트 자동 배포` → `[공통] 사이트 자동 배포`)도 이전 이름이 따옴표째 남으면 걸린다.
    따옴표 없이 문장 속에 풀어 쓴 언급은 보지 않는다. 한 줄에 지금 이름이 같이 있으면(옛 이름 → 새 이름 대응표) 허용한다."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in OLD_NAME_SKIP_DIRS)
        for name in sorted(filenames):
            if not name.endswith(OLD_NAME_SUFFIXES):
                continue
            path = Path(dirpath, name)
            rel = path.relative_to(root).as_posix()
            if any(rel == skip or (skip.endswith("/") and rel.startswith(skip)) for skip in allowed):
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                for old, new in previous.items():
                    if new not in line and any(mark + old + mark in line for mark in QUOTE_MARKS):
                        found.append(f"{rel}:{lineno}: {old}")
    return found


class NamePrefixTest(unittest.TestCase):
    EXPECTED = {
        "chanceblog.yml": "[Chance] 글 자동 작성·게시",
        "chance-fix-images.yml": "[Chance] 기존 글 이미지 교체(수동)",
        "issue-edit.yml": "[Chance] 이슈 수정 요청 처리(수정안 PR 만들기)",
        "blogger.yml": "[Blogger] 글 자동 작성(초안함 업로드)",
        "pages.yml": "[공통] 사이트 자동 배포",
        "guardrails.yml": "[공통] 저장소 규칙·테스트 자동 검사",
        "pr-scope-check.yml": "[공통] PR 변경 범위 검사",
        "sync-issue-form.yml": "[공통] 이슈 양식 페이지 목록 갱신",
        "watchdog.yml": "[공통] 발행 중단 감시·알림",
        "ops-inbox.yml": "[공통] 확인 필요 모음",
        "tistory.yml": "[티스토리] 초안 패키지 만들기",
        "naver.yml": "[네이버] 초안 패키지 만들기",
    }

    def test_every_workflow_has_its_approved_name(self):
        """운영자가 승인한 이름(2026-10-27, 계획 보고 §3)이다. 이름을 바꾸거나 워크플로를 더하면 이 표와 문서 대응표를 함께 고친다."""
        self.assertEqual(current_names(), self.EXPECTED)

    def test_every_name_starts_with_an_allowed_label(self):
        for file, name in current_names().items():
            self.assertIn(registry.name_label(name), PREFIX_LABELS, f"{file}: {name!r}")

    def test_run_name_starts_with_the_same_prefix_as_name(self):
        seen = 0
        for file, name in current_names().items():
            run_name = load(file).get("run-name")
            if run_name is None:
                continue
            seen += 1
            self.assertEqual(registry.name_label(run_name), registry.name_label(name), f"{file}: {run_name!r}")
        self.assertEqual(seen, 8)  # chanceblog · chance-fix-images · issue-edit · blogger · watchdog · ops-inbox · tistory · naver

    def test_registered_blog_workflows_use_their_channel_label(self):
        """레지스트리 channel.label 과 그 블로그 워크플로 이름의 접두사는 같은 글자다(레지스트리 검증도 같은 것을 본다)."""
        blogs = registry.load_registry()["blogs"]
        self.assertGreaterEqual(len(blogs), 2)
        for raw in blogs:
            name = load(Path(raw["workflow"]).name)["name"]
            self.assertEqual(registry.name_label(name), raw["channel"]["label"], f"{raw['key']}: {name!r}")

    def test_job_and_step_names_do_not_get_the_prefix(self):
        """접두사는 워크플로 name·run-name 에만 붙인다. job 이름은 PR 검사 화면의 이름이고 단계 이름은 실행 화면의 줄 이름이라 그대로 둔다."""
        checked = 0
        for file in current_names():
            for job_id, job in load(file)["jobs"].items():
                self.assertIsNone(registry.name_label(job.get("name")), f"{file} job {job_id}")
                for step in job.get("steps", []):
                    checked += 1
                    self.assertIsNone(registry.name_label(step.get("name")), f"{file} {job_id}: {step.get('name')!r}")
        self.assertGreater(checked, 40)

    def test_same_label_workflows_are_adjacent_in_name_order(self):
        """Actions 왼쪽 목록은 이름순이라 접두사가 같은 워크플로끼리 붙어 보인다(이 시험은 파이썬 기본 정렬로 그 성질을 확인한다)."""
        labels = [registry.name_label(name) for name in sorted(current_names().values())]
        groups = [label for index, label in enumerate(labels) if index == 0 or label != labels[index - 1]]
        self.assertEqual(len(groups), len(set(groups)), f"같은 구분이 떨어져 있습니다: {groups}")
        self.assertEqual(set(groups), {"Blogger", "Chance", "공통", "티스토리", "네이버"})

    def test_operator_guide_lists_every_current_name(self):
        guide = (REAL / "docs" / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")
        for file, name in current_names().items():
            self.assertIn(f"`{name}`", guide, f"docs/ACTIONS_GUIDE.md 에 {file} 의 현재 이름 `{name}` 이 없습니다")

    def test_previous_names_map_to_exactly_the_current_names(self):
        """PREVIOUS_NAMES 가 현재 이름과 어긋나면 아래 검색이 엉뚱한 이름을 기준으로 삼는다 — 이름을 바꾸면 이 표도 같이 고친다."""
        self.assertEqual(sorted(PREVIOUS_NAMES.values()), sorted(current_names().values()))
        for old, new in PREVIOUS_NAMES.items():
            self.assertNotEqual(old, new)

    def test_living_docs_and_code_never_quote_a_previous_name(self):
        """접두사를 붙이기 전의 이름(예: `사이트 자동 배포`)을 인용한 안내가 남으면 운영자가 Actions 목록에서 그 이름을 찾지 못한다."""
        self.assertEqual(find_previous_name_quotes(REAL), [])

    def test_previous_name_scan_finds_quotes_and_skips_allowed_places(self):
        previous = {"사이트 자동 배포": "[공통] 사이트 자동 배포", "Chance 글 자동 작성·게시": "[Chance] 글 자동 작성·게시"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "docs/a.md": "Actions → `사이트 자동 배포` 를 누른다\n",
                "docs/b.md": "**사이트 자동 배포**와 'Chance 글 자동 작성·게시' 를 본다\n",
                "docs/c.md": 'MSG = "사이트 자동 배포"\n',
                "pipeline/h.py": "MSG = \"성공한 '사이트 자동 배포' 실행이 없습니다\"\n",
                ".github/workflows/w.yml": "# 주석: `Chance 글 자동 작성·게시` 워크플로\n",
                "docs/ok.md": "Actions → `[공통] 사이트 자동 배포` 를 누른다\n",
                "docs/table.md": "| 옛 `사이트 자동 배포` | `[공통] 사이트 자동 배포` |\n",             # 대응표: 지금 이름이 같은 줄
                "docs/prose.md": "사이트 자동 배포가 돌고 Chance 글 자동 작성·게시가 끝난다\n",         # 따옴표 없는 문장 속 언급
                "docs/other.md": "`사이트 자동 배포 상태`와 'Chance 글 자동 작성·게시 기록' 은 다른 말이다\n",   # 이름이 더 긴 문구의 일부
                "docs/summary.md": "요약 제목 `### 사이트 자동 배포` 는 제목 줄 전체를 인용한 것이다\n",       # 이름 앞뒤에 다른 글자가 붙은 인용
                "WORKLOG.md": "`사이트 자동 배포` (과거 기록)\n",
                "tests/t.py": "NAME = '사이트 자동 배포'\n",
                "인수인계/n.md": "`사이트 자동 배포`\n",
                "docs/analysis/r.md": "`사이트 자동 배포`\n",
                "data.json": '{"x": "`사이트 자동 배포`"}\n',                                         # 검사하지 않는 확장자
                "_posts/p.md": "`사이트 자동 배포`\n",                                                 # 글 폴더는 건너뜀
            }
            for rel, content in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            self.assertEqual(sorted(find_previous_name_quotes(root, previous)), [
                ".github/workflows/w.yml:1: Chance 글 자동 작성·게시",
                "docs/a.md:1: 사이트 자동 배포",
                "docs/b.md:1: Chance 글 자동 작성·게시",
                "docs/b.md:1: 사이트 자동 배포",
                "docs/c.md:1: 사이트 자동 배포",
                "pipeline/h.py:1: 사이트 자동 배포",
            ])
            self.assertEqual(len(find_previous_name_quotes(root, previous, allowed={})), 6 + 4)   # 허용 목록을 비우면 WORKLOG·tests·인수인계·analysis 도 걸린다




if __name__ == "__main__":
    unittest.main()
