"""운영자 요청함의 파일 구조 시험 — 워크플로 둘(ai-request.yml·operator-reply.yml)·이슈 양식 둘과 config.yml·검증기 규칙(WF-14·REQ-1·FORM-1)·기존 것이 그대로인지·문서와 코드의 일치.

실제 `.github/` 파일을 읽어 확인한다(GitHub 를 실행할 수 없는 환경에서도 구조로 증명한다). 검증기 규칙은 실제 파일을 한 군데씩 망가뜨린 사본으로 '잡히는지'를 확인한다.
"""
import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap
import operator_loop_helpers as oh
from edits_helpers import make_edit_root
from pipeline import operator_loop as ol
from pipeline.edits import forms, pages, spec as spec_mod
from test_ops_inbox_drafts import job_runs
from test_workflow_names import load

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

WORKFLOWS = ROOT / ".github" / "workflows"
TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"
AI_REQUEST, OPERATOR_REPLY = vr.AI_REQUEST_WORKFLOW, vr.OPERATOR_REPLY_WORKFLOW
REPLY_FORM, TASK_FORM, CONFIG = vr.REPLY_FORM, vr.TASK_FORM, vr.ISSUE_CONFIG
TELEGRAM_ENV = {"TELEGRAM_BOT_TOKEN": "${{ secrets.TELEGRAM_BOT_TOKEN }}", "TELEGRAM_CHAT_ID": "${{ secrets.TELEGRAM_CHAT_ID }}"}
OWNER = oh.OWNER


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


# ----------------------------------------------------------------------------
# GitHub 표현식(job `if` 에 쓰는 부분집합) 해석기 — contains·startsWith·fromJSON 을 더했다
# ----------------------------------------------------------------------------
class Gh:
    TOKEN = re.compile(r"\s*(?:(?P<op>\|\||&&|==|!=|[(),!])|'(?P<str>(?:[^']|'')*)'|(?P<id>[A-Za-z_][A-Za-z0-9_.*\-]*))")

    def __init__(self, source, context):
        self.tokens, pos, text = [], 0, source.strip()
        while pos < len(text):
            match = self.TOKEN.match(text, pos)
            if not match:
                raise ValueError(f"읽을 수 없는 식: {text[pos:pos + 30]!r}")
            pos = match.end()
            if match.group("op"):
                self.tokens.append(("op", match.group("op")))
            elif match.group("str") is not None:
                self.tokens.append(("val", match.group("str").replace("''", "'")))
            else:
                self.tokens.append(("id", match.group("id")))
        self.i, self.context = 0, context

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        self.i += 1
        return token

    @staticmethod
    def truthy(value):
        return not (value is None or value is False or value == 0 or value == "" or value == [])

    def parse(self):
        value = self.or_()
        if self.i != len(self.tokens):
            raise ValueError("식 끝에 남은 토큰이 있습니다")
        return value

    def or_(self):
        value = self.and_()
        while self.peek() == ("op", "||"):
            self.take()
            right = self.and_()
            value = value if self.truthy(value) else right
        return value

    def and_(self):
        value = self.eq()
        while self.peek() == ("op", "&&"):
            self.take()
            right = self.eq()
            value = right if self.truthy(value) else value
        return value

    def eq(self):
        value = self.unary()
        while self.peek() in (("op", "=="), ("op", "!=")):
            op = self.take()[1]
            right = self.unary()
            same = value.casefold() == right.casefold() if isinstance(value, str) and isinstance(right, str) else value == right
            value = same if op == "==" else not same
        return value

    def unary(self):
        if self.peek() == ("op", "!"):
            self.take()
            return not self.truthy(self.unary())
        return self.primary()

    def primary(self):
        kind, text = self.take()
        if (kind, text) == ("op", "("):
            value = self.or_()
            assert self.take() == ("op", ")")
            return value
        if kind == "val":
            return text
        if kind == "id" and self.peek() == ("op", "("):
            self.take()
            args = [self.or_()]
            while self.peek() == ("op", ","):
                self.take()
                args.append(self.or_())
            assert self.take() == ("op", ")")
            return self.call(text, args)
        if kind == "id":
            return {"true": True, "false": False, "null": None}[text] if text in ("true", "false", "null") else self.lookup(text)
        raise ValueError(f"예상하지 못한 토큰 {kind} {text}")

    @staticmethod
    def call(name, args):
        if name == "fromJSON":
            return json.loads(args[0])
        if name == "startsWith":
            return isinstance(args[0], str) and isinstance(args[1], str) and args[0].casefold().startswith(args[1].casefold())
        if name == "contains":
            haystack, needle = args
            if isinstance(haystack, list):
                return any(isinstance(item, str) and isinstance(needle, str) and item.casefold() == needle.casefold() for item in haystack)
            return isinstance(haystack, str) and isinstance(needle, str) and needle.casefold() in haystack.casefold()
        raise ValueError(f"지원하지 않는 함수: {name}")

    def lookup(self, path):
        nodes = [self.context]
        for part in path.split("."):
            nxt = []
            for node in nodes:
                if part == "*":
                    nxt += node if isinstance(node, list) else []
                elif isinstance(node, dict):
                    nxt.append(node.get(part))
                else:
                    nxt.append(None)
            nodes = nxt
        return nodes if ".*." in path else (nodes[0] if nodes else None)


def issue_context(login=OWNER, association="OWNER", title="[답변] ", labels=(), owner=OWNER, event="issues"):
    return {"github": {"event_name": event, "repository_owner": owner,
                       "event": {"issue": {"user": {"login": login}, "author_association": association, "title": title, "labels": [{"name": name} for name in labels]}}}}


def job_condition(workflow, job):
    return load(workflow)["jobs"][job]["if"]


class GhSelfTest(unittest.TestCase):
    """아래 시험이 기대는 해석기가 GitHub 규칙을 따르는지."""

    def ev(self, source, context=None):
        return Gh(source, context or {}).parse()

    def test_functions_and_operators(self):
        self.assertTrue(self.ev("startsWith('[답변] 글', '[답변]')"))
        self.assertFalse(self.ev("startsWith('x [답변]', '[답변]')"))
        self.assertEqual(self.ev("fromJSON('[\"OWNER\",\"MEMBER\"]')"), ["OWNER", "MEMBER"])
        self.assertTrue(self.ev("contains(fromJSON('[\"OWNER\",\"MEMBER\"]'), 'owner')"))
        self.assertFalse(self.ev("contains(fromJSON('[\"OWNER\"]'), 'NONE')"))
        self.assertTrue(self.ev("'A' == 'a' && !false"))
        self.assertEqual(self.ev("false || 'x'"), "x")
        self.assertTrue(self.ev("contains(a.labels.*.name, 'k')", {"a": {"labels": [{"name": "k"}]}}))
        with self.assertRaises(ValueError):
            self.ev("unknown(1)")


# ----------------------------------------------------------------------------
# 워크플로 둘의 구조(정확한 모양)
# ----------------------------------------------------------------------------
class AiRequestWorkflowTest(unittest.TestCase):
    EXPECTED = {
        "name": "[공통] AI 요청 텔레그램 알림",
        "on": {"push": {"branches": ["ai/claude/**"]}},
        "permissions": {"contents": "read"},
        "concurrency": {"group": "ai-request-${{ github.sha }}", "cancel-in-progress": False},
        "jobs": {"notify": {"name": "요청 알림 보내기", "runs-on": "ubuntu-latest", "timeout-minutes": 5, "steps": [
            {"uses": "actions/checkout@v4", "with": {"fetch-depth": 0, "persist-credentials": False}},
            {"uses": "actions/setup-python@v5", "with": {"python-version": "3.12"}},
            {"name": "새 요청 파일 알리기", "env": {"BEFORE_SHA": "${{ github.event.before }}", "AFTER_SHA": "${{ github.sha }}",
                                              "DEFAULT_BRANCH": "${{ github.event.repository.default_branch }}", **TELEGRAM_ENV},
             "run": "python -m pipeline.operator_loop requests"}]}},
    }

    def test_the_workflow_is_exactly_this(self):
        self.assertEqual(load("ai-request.yml"), self.EXPECTED)

    def test_only_a_push_to_the_ai_branches_triggers_it_and_there_is_no_path_filter(self):
        on = load("ai-request.yml")["on"]
        self.assertEqual(list(on), ["push"])
        self.assertEqual(on["push"], {"branches": ["ai/claude/**"]})
        for forbidden in ("paths", "paths-ignore", "tags", "branches-ignore"):
            self.assertNotIn(forbidden, on["push"])
        for event in ("pull_request", "pull_request_target", "issue_comment", "issues", "workflow_run", "workflow_dispatch", "schedule", "repository_dispatch"):
            self.assertNotIn(event, on)

    def test_the_only_run_line_is_the_python_command_and_has_no_github_expression(self):
        runs = [step["run"] for step in load("ai-request.yml")["jobs"]["notify"]["steps"] if "run" in step]
        self.assertEqual(runs, ["python -m pipeline.operator_loop requests"])
        self.assertNotIn("${{", runs[0])

    def test_the_secrets_are_only_in_the_last_steps_env_under_their_own_names(self):
        data = load("ai-request.yml")
        text = json.dumps(data, ensure_ascii=False)
        self.assertEqual(text.count("secrets."), 2)
        env = data["jobs"]["notify"]["steps"][-1]["env"]
        for name, value in TELEGRAM_ENV.items():
            self.assertEqual(env[name], value)
        self.assertEqual(vr.check_telegram_secrets(ROOT, vr.list_files(ROOT)), [])

    def test_the_concurrency_group_differs_per_push_and_never_cancels(self):
        concurrency = load("ai-request.yml")["concurrency"]
        self.assertIn("github.sha", concurrency["group"])
        self.assertNotIn("github.ref", concurrency["group"])                         # 브랜치 단위 그룹이면 대기 중인 실행이 취소돼 요청 파일을 놓친다
        self.assertIs(concurrency["cancel-in-progress"], False)

    def test_it_needs_the_full_history_and_leaves_no_credentials_in_the_checkout(self):
        checkout = load("ai-request.yml")["jobs"]["notify"]["steps"][0]
        self.assertEqual(checkout["with"], {"fetch-depth": 0, "persist-credentials": False})

    def test_it_never_writes_anything(self):
        text = (WORKFLOWS / "ai-request.yml").read_text(encoding="utf-8")
        for needle in ("git push", "git commit", "gh pr", "gh issue", "gh api", "gh workflow", "write"):
            self.assertNotIn(needle, text.replace("읽기만 하고 아무것도 쓰지 않는다", ""), needle)

    def test_the_header_comment_states_the_limits(self):
        header = (WORKFLOWS / "ai-request.yml").read_text(encoding="utf-8").split("on:")[0]
        for needle in ("한계", "paths", "미확인", "대기 중인 실행", "얕은 복제", "중복·도배", "`[공통] 텔레그램 알림 시험`"):
            self.assertIn(needle, header, needle)


class OperatorReplyWorkflowTest(unittest.TestCase):
    CONDITION = "github.event.issue.user.login == github.repository_owner && github.event.issue.author_association == 'OWNER'"
    EXPECTED = {
        "name": "[공통] 운영자 응답 접수",
        "run-name": "[공통] 운영자 응답 접수 · 이슈 #${{ github.event.issue.number }}",
        "on": {"issues": {"types": ["opened"]}},
        "permissions": {"contents": "read", "issues": "write"},
        "concurrency": {"group": "operator-reply-${{ github.event.issue.number }}", "cancel-in-progress": False},
        "jobs": {"ack": {"name": "응답 이슈 접수", "if": CONDITION, "runs-on": "ubuntu-latest", "timeout-minutes": 5, "steps": [
            {"uses": "actions/checkout@v4", "with": {"persist-credentials": False}},
            {"uses": "actions/setup-python@v5", "with": {"python-version": "3.12"}},
            {"name": "접수 확인(코멘트·라벨·텔레그램)", "env": {"GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}", **TELEGRAM_ENV},
             "run": "python -m pipeline.operator_loop ack"}]}},
    }

    def test_the_workflow_is_exactly_this(self):
        self.assertEqual(load("operator-reply.yml"), self.EXPECTED)

    def test_only_a_newly_opened_issue_triggers_it(self):
        on = load("operator-reply.yml")["on"]
        self.assertEqual(on, {"issues": {"types": ["opened"]}})
        for event in ("issue_comment", "pull_request", "pull_request_target", "workflow_run", "push", "workflow_dispatch", "schedule"):
            self.assertNotIn(event, on)

    def test_the_job_runs_only_for_an_issue_the_owner_opened(self):
        condition = job_condition("operator-reply.yml", "ack")
        cases = ((OWNER, "OWNER", OWNER, True), ("stranger", "NONE", OWNER, False), ("stranger", "OWNER", OWNER, False), (OWNER, "MEMBER", OWNER, False),
                 (OWNER, "COLLABORATOR", OWNER, False), (OWNER, "OWNER", "someone-else", False), ("Shine88PC", "OWNER", OWNER, True), ("github-actions[bot]", "NONE", OWNER, False),
                 ("", "OWNER", OWNER, False))
        for login, association, owner, expected in cases:
            self.assertEqual(bool(Gh(condition, issue_context(login=login, association=association, owner=owner)).parse()), expected, (login, association, owner))

    def test_the_condition_reads_only_the_event_authors_login_and_association_and_the_owner(self):
        condition = job_condition("operator-reply.yml", "ack")
        self.assertEqual(set(re.findall(r"github\.[A-Za-z_.*]+", condition)), {"github.event.issue.user.login", "github.repository_owner", "github.event.issue.author_association"})
        for forbidden in ("title", "body", "labels", "||"):
            self.assertNotIn(forbidden, condition)

    def test_no_run_line_has_a_github_expression_and_the_issue_text_is_not_passed_anywhere(self):
        data = load("operator-reply.yml")
        steps = data["jobs"]["ack"]["steps"]
        for step in steps:
            if "run" in step:
                self.assertNotIn("${{", step["run"])
            for value in (step.get("env") or {}).values():
                self.assertNotRegex(str(value), r"github\.event\.issue")
            for value in (step.get("with") or {}).values():
                self.assertNotRegex(str(value), r"github\.event")
        text = (WORKFLOWS / "operator-reply.yml").read_text(encoding="utf-8")
        body = text.split("jobs:")[1]
        for forbidden in ("issue.title", "issue.body", "comment.body", "head_ref", "head.ref"):
            self.assertNotIn(forbidden, body, forbidden)

    def test_the_code_is_the_default_branchs_and_the_checkout_cannot_be_redirected(self):
        checkout = load("operator-reply.yml")["jobs"]["ack"]["steps"][0]
        self.assertEqual(checkout["with"], {"persist-credentials": False})            # ref·repository·token 을 바꾸지 않는다(issues 이벤트는 기본 브랜치를 내려받는다)

    def test_the_run_title_shows_only_the_issue_number(self):
        from test_workflow_names import context, render
        template = load("operator-reply.yml")["run-name"]
        self.assertEqual(render(template, context("issues", issue=21)), "[공통] 운영자 응답 접수 · 이슈 #21")
        refs = set(re.findall(r"github\.[A-Za-z_.]+", template))
        self.assertEqual(refs, {"github.event.issue.number"})

    def test_it_writes_only_issue_labels_and_comments_through_the_code(self):
        text = (WORKFLOWS / "operator-reply.yml").read_text(encoding="utf-8")
        for needle in ("git push", "git commit", "gh pr", "gh api", "gh workflow", "contents: write", "pull-requests: write", "actions: write"):
            self.assertNotIn(needle, text, needle)

    def test_the_header_comment_states_the_trust_rule_and_the_limits(self):
        header = (WORKFLOWS / "operator-reply.yml").read_text(encoding="utf-8").split("\non:")[0]
        for needle in ("소유자", "author_association", "pull_request_target", "한 번만", "G-S9"):
            self.assertIn(needle, header, needle)


class NewWorkflowsInTheRepositoryTest(unittest.TestCase):
    def test_the_two_names_use_the_common_prefix_and_korean_job_names(self):
        for name, label in (("ai-request.yml", "공통"), ("operator-reply.yml", "공통")):
            data = load(name)
            self.assertEqual(data["name"].split("]")[0], f"[{label}")
            for job in data["jobs"].values():
                self.assertRegex(job["name"], r"[가-힣]")
        self.assertEqual([f.line() for f in vr.check_workflow_names(ROOT, vr.list_files(ROOT)) + vr.check_workflow_prefixes(ROOT, vr.list_files(ROOT))], [])

    def test_workflow_count_and_the_other_workflows_are_untouched_by_name(self):
        names = sorted(path.name for path in WORKFLOWS.glob("*.yml"))
        self.assertEqual(len(names), 17)
        self.assertIn("ai-request.yml", names)
        self.assertIn("operator-reply.yml", names)

    def test_the_actionable_validator_rules_pass_on_the_real_repository(self):
        files = vr.list_files(ROOT)
        self.assertEqual(vr.check_operator_workflows(ROOT, files), [])
        self.assertEqual(vr.check_request_files(ROOT, files), [])
        self.assertEqual(vr.check_operator_forms(ROOT, files), [])


# ----------------------------------------------------------------------------
# 기존 것이 그대로이고 새 양식이 기존 자동화를 일으키지 않는다
# ----------------------------------------------------------------------------
class NothingExistingReactsTest(unittest.TestCase):
    ISSUE_EDIT_IF = ("github.event_name == 'workflow_dispatch' || (contains(fromJSON('[\"OWNER\",\"MEMBER\",\"COLLABORATOR\"]'), github.event.issue.author_association) && "
                     "(contains(github.event.issue.labels.*.name, 'blog-control') || startsWith(github.event.issue.title, '[페이지 수정]') || startsWith(github.event.issue.title, '[이미지 변경]')))")

    def test_the_issue_edit_condition_is_still_this_string(self):
        self.assertEqual(" ".join(job_condition("issue-edit.yml", "edit").split()), self.ISSUE_EDIT_IF)

    def test_the_issue_edit_job_does_not_run_for_the_new_forms_even_from_the_owner(self):
        condition = job_condition("issue-edit.yml", "edit")
        for form, title, label in (("답변", ol.REPLY_TITLE_PREFIX, ol.LABEL_REPLY), ("요청", ol.TASK_TITLE_PREFIX, ol.LABEL_TASK)):
            for association in ("OWNER", "MEMBER", "COLLABORATOR"):
                for labels in ((), (label,), (label, "운영자요청")):
                    context = issue_context(association=association, title=title + "아무 글", labels=labels)
                    self.assertFalse(Gh(condition, context).parse(), (form, association, labels))

    def test_the_condition_is_alive_it_does_run_for_the_forms_it_is_meant_for(self):
        condition = job_condition("issue-edit.yml", "edit")
        self.assertTrue(Gh(condition, issue_context(title="[페이지 수정] 소개", labels=["blog-control", "edit:page"])).parse())
        self.assertTrue(Gh(condition, issue_context(title="[이미지 변경] x", labels=())).parse())
        self.assertTrue(Gh(condition, issue_context(title="아무 글", labels=["blog-control"])).parse())
        self.assertFalse(Gh(condition, issue_context(title="[페이지 수정] 소개", association="NONE")).parse())

    def test_the_inbox_job_does_not_run_for_the_new_forms(self):
        for labels in ([ol.LABEL_REPLY], [ol.LABEL_TASK], []):
            self.assertFalse(job_runs("issues", issue_labels=labels), labels)

    def test_the_new_labels_are_not_used_by_any_other_workflow(self):
        for path in WORKFLOWS.glob("*.yml"):
            if path.name == "operator-reply.yml":
                continue
            text = path.read_text(encoding="utf-8")
            for label in (ol.LABEL_REPLY, ol.LABEL_TASK):
                self.assertNotIn(label, text, path.name)

    def test_no_other_workflow_runs_the_operator_loop(self):
        for path in WORKFLOWS.glob("*.yml"):
            if path.name in ("ai-request.yml", "operator-reply.yml"):
                continue
            self.assertNotIn("operator_loop", path.read_text(encoding="utf-8"), path.name)

    def test_the_sync_script_and_the_form_loader_do_not_touch_or_confuse_the_new_forms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_edit_root(tmp)
            for name in ("ai-reply.yml", "ai-task.yml", "config.yml"):
                shutil.copy(TEMPLATES / name, root / ".github" / "ISSUE_TEMPLATE" / name)
            before = {name: (root / ".github" / "ISSUE_TEMPLATE" / name).read_bytes() for name in ("ai-reply.yml", "ai-task.yml", "config.yml")}
            spec = spec_mod.load_spec(root)
            forms.sync_page_form(root, spec, pages.load_registry(root), write=True)
            after = {name: (root / ".github" / "ISSUE_TEMPLATE" / name).read_bytes() for name in before}
            self.assertEqual(before, after)
            templates = forms.load_templates(root)
            by_file = {template["file"]: template for template in templates}
            self.assertEqual(by_file["ai-reply.yml"]["labels"], [ol.LABEL_REPLY])
            self.assertEqual(by_file["ai-task.yml"]["labels"], [ol.LABEL_TASK])
            self.assertNotIn("config.yml", by_file)                                       # 본문이 없는 설정 파일은 양식이 아니다
            self.assertEqual(sorted(template["file"] for template in forms.control_templates(templates)), ["blog_control.yml", "page-edit.yml"])
            self.assertEqual(sorted(forms.label_map(templates).values()), sorted(["target_page", "edit_type", "before", "after", "target_post", "user_prompt"]))

    def test_the_real_repository_edit_system_check_and_the_form_sync_check_still_pass(self):
        findings = [f.line() for f in vr.check_edit_system(ROOT, vr.list_files(ROOT)) if f.level == "ERROR"]
        self.assertEqual(findings, [])
        import sync_issue_form
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sync_issue_form.main(["--check"]), 0)

    def test_the_existing_forms_and_workflows_keep_their_triggers(self):
        self.assertEqual(load("issue-edit.yml")["on"]["issues"], {"types": ["opened"]})
        self.assertEqual(load("sync-issue-form.yml")["on"]["push"]["branches"], ["main"])
        self.assertEqual(sorted(path.name for path in TEMPLATES.iterdir()), ["ai-reply.yml", "ai-task.yml", "blog_control.yml", "config.yml", "page-edit.yml"])


# ----------------------------------------------------------------------------
# 이슈 양식
# ----------------------------------------------------------------------------
def form(name):
    return yaml.safe_load((TEMPLATES / name).read_text(encoding="utf-8"))


class IssueFormTest(unittest.TestCase):
    FIELD_TYPES = {"markdown", "input", "textarea", "dropdown", "checkboxes"}

    def check_schema(self, data):
        """GitHub 이슈 양식 스키마 중 이 저장소가 확인할 수 있는 규칙: name·description·body 필수, 항목 id 는 영숫자·-·_ 이고 겹치지 않음, 라벨 필수, 드롭다운 선택지는 겹치지 않는 비지 않은 글."""
        for key in ("name", "description", "body"):
            self.assertTrue(data.get(key), key)
        ids = []
        for item in data["body"]:
            self.assertIn(item["type"], self.FIELD_TYPES)
            if item["type"] == "markdown":
                self.assertTrue(item["attributes"]["value"].strip())
                continue
            self.assertRegex(item["id"], r"^[A-Za-z0-9_-]+$")
            ids.append(item["id"])
            self.assertTrue(item["attributes"]["label"].strip())
            if item["type"] == "dropdown":
                options = item["attributes"]["options"]
                self.assertEqual(len(options), len(set(options)))
                self.assertTrue(all(isinstance(option, str) and option.strip() for option in options))
                self.assertLess(item["attributes"].get("default", 0), len(options))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(isinstance(label, str) and label for label in data.get("labels", [])))

    def test_both_forms_follow_the_issue_form_schema(self):
        for name in ("ai-reply.yml", "ai-task.yml"):
            self.check_schema(form(name))

    def test_the_answer_form_is_what_the_code_reads(self):
        data = form("ai-reply.yml")
        self.assertEqual((data["name"], data["title"], data["labels"]), ("AI 요청에 답하기(결정·확인)", ol.REPLY_TITLE_PREFIX, [ol.LABEL_REPLY]))
        fields = {item["id"]: item for item in data["body"][1:]}
        self.assertEqual({field_id: item["attributes"]["label"] for field_id, item in fields.items()}, dict(ol.REPLY_FIELDS))
        self.assertEqual({field_id: item["type"] for field_id, item in fields.items()}, ol.REPLY_FIELD_TYPES)
        self.assertEqual({field_id for field_id, item in fields.items() if (item.get("validations") or {}).get("required")}, set(ol.REPLY_REQUIRED))
        self.assertEqual(fields["answer"]["attributes"]["options"], [full for _, full in ol.ANSWER_OPTIONS])
        self.assertEqual(list(fields), ["request_id", "answer", "choice", "memo"])

    def test_the_task_form_is_what_the_code_reads(self):
        data = form("ai-task.yml")
        self.assertEqual((data["name"], data["title"], data["labels"]), ("AI 에게 새 일 맡기기(작업 요청)", ol.TASK_TITLE_PREFIX, [ol.LABEL_TASK]))
        fields = {item["id"]: item for item in data["body"][1:]}
        self.assertEqual({field_id: item["attributes"]["label"] for field_id, item in fields.items()}, dict(ol.TASK_FIELDS))
        self.assertEqual({field_id: item["type"] for field_id, item in fields.items()}, ol.TASK_FIELD_TYPES)
        self.assertEqual({field_id for field_id, item in fields.items() if (item.get("validations") or {}).get("required")}, set(ol.TASK_REQUIRED))
        self.assertEqual(fields["urgency"]["attributes"]["options"], list(ol.TASK_URGENCY_OPTIONS))
        self.assertEqual(fields["approval"]["attributes"]["options"], [full for _, full in ol.TASK_APPROVAL_OPTIONS])
        self.assertEqual(fields["urgency"]["attributes"]["default"], 0)                       # 기본은 '보통'

    def test_neither_form_carries_the_blog_control_label_or_an_edit_title(self):
        for name in ("ai-reply.yml", "ai-task.yml"):
            data = form(name)
            self.assertNotIn("blog-control", data["labels"])
            self.assertFalse(any(label.startswith("edit:") for label in data["labels"]))
            self.assertFalse(data["title"].startswith(("[페이지 수정]", "[이미지 변경]")))

    def test_both_forms_open_with_the_secret_warning_and_the_owner_only_note(self):
        for name in ("ai-reply.yml", "ai-task.yml"):
            notice = form(name)["body"][0]
            self.assertEqual(notice["type"], "markdown")
            value = notice["attributes"]["value"]
            for needle in (ol.FORM_NOTICE, "공개", "저장소 소유자 계정", "T3"):
                self.assertIn(needle, value, (name, needle))

    def test_the_rendered_body_of_every_option_is_read_back_by_the_parser(self):
        """양식 파일의 라벨·선택지로 GitHub 가 만드는 본문(`### 라벨` 아래에 값)을 그대로 지어 파서에 넣으면 값이 되돌아온다."""
        data = form("ai-reply.yml")
        fields = {item["id"]: item for item in data["body"][1:]}
        for option in fields["answer"]["attributes"]["options"]:
            body = (f"### {fields['request_id']['attributes']['label']}\n\nR-123\n\n### {fields['answer']['attributes']['label']}\n\n{option}\n\n"
                    f"### {fields['choice']['attributes']['label']}\n\n_No response_\n\n### {fields['memo']['attributes']['label']}\n\n_No response_")
            result = ol.parse_reply(data["title"] + "x", body, OWNER, "OWNER", OWNER)
            self.assertEqual((result.kind, result.request_id, dict(ol.ANSWER_OPTIONS)[result.answer]), ("reply", "R-123", option))
        task = form("ai-task.yml")
        fields = {item["id"]: item for item in task["body"][1:]}
        for urgency in fields["urgency"]["attributes"]["options"]:
            for approval in fields["approval"]["attributes"]["options"]:
                body = (f"### {fields['what']['attributes']['label']}\n\n무엇\n\n### {fields['done']['attributes']['label']}\n\n_No response_\n\n"
                        f"### {fields['urgency']['attributes']['label']}\n\n{urgency}\n\n### {fields['approval']['attributes']['label']}\n\n{approval}")
                result = ol.parse_reply(task["title"], body, OWNER, "OWNER", OWNER)
                self.assertEqual((result.kind, result.urgency, dict(ol.TASK_APPROVAL_OPTIONS)["yes" if result.approval_yes else "no"]), ("task", urgency, approval))

    def test_the_issue_config_keeps_blank_issues_and_points_to_the_guide(self):
        config = yaml.safe_load((TEMPLATES / "config.yml").read_text(encoding="utf-8"))
        self.assertIs(config["blank_issues_enabled"], True)
        self.assertEqual(len(config["contact_links"]), 1)
        link = config["contact_links"][0]
        self.assertEqual(set(link), {"name", "url", "about"})
        self.assertTrue(link["url"].startswith("https://github.com/shine88pc/chanceblog/blob/main/"))
        self.assertTrue(link["url"].isascii())
        from urllib.parse import unquote
        self.assertEqual(unquote(link["url"].split("/blob/main/")[1]), ol.GUIDE_PATH)
        self.assertTrue((ROOT / ol.GUIDE_PATH).is_file())

    def test_the_guide_button_of_the_telegram_message_and_the_config_link_point_to_the_same_file(self):
        link = yaml.safe_load((TEMPLATES / "config.yml").read_text(encoding="utf-8"))["contact_links"][0]["url"]
        button = ol.blob_url("main", ol.GUIDE_PATH)
        self.assertEqual(link, button)


# ----------------------------------------------------------------------------
# 검증기 규칙: 사본을 한 군데씩 망가뜨려 잡히는지
# ----------------------------------------------------------------------------
def rule_root(tmp, mutate=None):
    """실제 운영자 요청함 파일(워크플로·양식·config)을 임시 폴더에 복사한다. mutate({상대 경로: 글})로 글을 바꿔 쓴다."""
    root = Path(tmp)
    texts = {rel: (ROOT / rel).read_text(encoding="utf-8") for rel in (AI_REQUEST, OPERATOR_REPLY, REPLY_FORM, TASK_FORM, CONFIG)}
    if mutate:
        mutate(texts)
    for rel, text in texts.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return root, sorted(texts)


def swap(texts, rel, old, new, count=1):
    assert texts[rel].count(old) == count, (rel, texts[rel].count(old), old)
    texts[rel] = texts[rel].replace(old, new)


class WorkflowRuleTest(unittest.TestCase):
    def errors(self, mutate=None):
        with tempfile.TemporaryDirectory() as tmp:
            root, files = rule_root(tmp, mutate)
            return [f for f in vr.check_operator_workflows(root, files)]

    def test_the_real_files_pass(self):
        self.assertEqual(self.errors(), [])

    def test_a_missing_file_is_not_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, files = rule_root(tmp)
            self.assertEqual(vr.check_operator_workflows(root, [f for f in files if f != AI_REQUEST]), [])

    REQUEST_MUTATIONS = {
        "paths 필터를 더함": (AI_REQUEST, "      - 'ai/claude/**'\n", "      - 'ai/claude/**'\n    paths:\n      - '인수인계/요청함/**'\n"),
        "다른 브랜치를 더함": (AI_REQUEST, "      - 'ai/claude/**'\n", "      - 'ai/claude/**'\n      - 'main'\n"),
        "모든 브랜치": (AI_REQUEST, "'ai/claude/**'", "'**'"),
        "tags 를 더함": (AI_REQUEST, "      - 'ai/claude/**'\n", "      - 'ai/claude/**'\n    tags:\n      - 'v*'\n"),
        "pull_request_target": (AI_REQUEST, "permissions:\n  contents: read\n", "  pull_request_target:\n    types: [opened]\n\npermissions:\n  contents: read\n"),
        "workflow_dispatch": (AI_REQUEST, "permissions:\n  contents: read\n", "  workflow_dispatch:\n\npermissions:\n  contents: read\n"),
        "issue_comment": (AI_REQUEST, "permissions:\n  contents: read\n", "  issue_comment:\n    types: [created]\n\npermissions:\n  contents: read\n"),
        "쓰기 권한": (AI_REQUEST, "permissions:\n  contents: read\n", "permissions:\n  contents: write\n"),
        "이슈 쓰기 권한 추가": (AI_REQUEST, "permissions:\n  contents: read\n", "permissions:\n  contents: read\n  issues: write\n"),
        "job 권한": (AI_REQUEST, "    timeout-minutes: 5\n", "    timeout-minutes: 5\n    permissions:\n      contents: write\n"),
        "job env": (AI_REQUEST, "    timeout-minutes: 5\n", "    timeout-minutes: 5\n    env:\n      X: '1'\n"),
        "job if": (AI_REQUEST, "    timeout-minutes: 5\n", "    timeout-minutes: 5\n    if: github.actor != 'x'\n"),
        "워크플로 env": (AI_REQUEST, "\njobs:\n", "\nenv:\n  X: '1'\n\njobs:\n"),
        "단계 추가": (AI_REQUEST, "        run: python -m pipeline.operator_loop requests\n", "        run: python -m pipeline.operator_loop requests\n\n      - run: echo hi\n"),
        "단계 if": (AI_REQUEST, "      - name: 새 요청 파일 알리기\n", "      - name: 새 요청 파일 알리기\n        if: always()\n"),
        "continue-on-error": (AI_REQUEST, "      - name: 새 요청 파일 알리기\n", "      - name: 새 요청 파일 알리기\n        continue-on-error: true\n"),
        "자격 증명 남김": (AI_REQUEST, "          persist-credentials: false\n", "          persist-credentials: true\n"),
        "얕은 복제": (AI_REQUEST, "          fetch-depth: 0\n", "          fetch-depth: 1\n"),
        "run 바꿈": (AI_REQUEST, "python -m pipeline.operator_loop requests", "python -m pipeline.operator_loop requests --commit HEAD"),
        "run 에 표현식": (AI_REQUEST, "python -m pipeline.operator_loop requests", "python -m pipeline.operator_loop requests ${{ github.event.head_commit.message }}"),
        "env 키 추가": (AI_REQUEST, "          DEFAULT_BRANCH:", "          EXTRA: x\n          DEFAULT_BRANCH:"),
        "env 값 바꿈": (AI_REQUEST, "BEFORE_SHA: ${{ github.event.before }}", "BEFORE_SHA: ${{ github.event.head_commit.message }}"),
        "env 키 이름 바꿈": (AI_REQUEST, "TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}", "TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_BOT_TOKEN }}"),
        "그룹이 브랜치 단위": (AI_REQUEST, "group: ai-request-${{ github.sha }}", "group: ai-request-${{ github.ref }}"),
        "취소함": (AI_REQUEST, "cancel-in-progress: false", "cancel-in-progress: true"),
        "그룹 없음": (AI_REQUEST, "concurrency:\n  group: ai-request-${{ github.sha }}\n  cancel-in-progress: false\n\n", ""),
        "제한 시간": (AI_REQUEST, "timeout-minutes: 5", "timeout-minutes: 60"),
        "자체 러너": (AI_REQUEST, "runs-on: ubuntu-latest", "runs-on: self-hosted"),
        "job 둘": (AI_REQUEST, "\njobs:\n  notify:\n", "\njobs:\n  other:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n  notify:\n"),
    }

    REPLY_MUTATIONS = {
        "수정 이벤트": (OPERATOR_REPLY, "types: [opened]", "types: [opened, edited]"),
        "issue_comment": (OPERATOR_REPLY, "permissions:\n  contents: read\n  issues: write\n", "  issue_comment:\n    types: [created]\n\npermissions:\n  contents: read\n  issues: write\n"),
        "pull_request_target": (OPERATOR_REPLY, "permissions:\n  contents: read\n  issues: write\n", "  pull_request_target:\n    types: [opened]\n\npermissions:\n  contents: read\n  issues: write\n"),
        "workflow_run": (OPERATOR_REPLY, "permissions:\n  contents: read\n  issues: write\n", "  workflow_run:\n    workflows: ['x']\n\npermissions:\n  contents: read\n  issues: write\n"),
        "push": (OPERATOR_REPLY, "permissions:\n  contents: read\n  issues: write\n", "  push:\n    branches: [main]\n\npermissions:\n  contents: read\n  issues: write\n"),
        "PR 쓰기 권한": (OPERATOR_REPLY, "  issues: write\n\nconcurrency", "  issues: write\n  pull-requests: write\n\nconcurrency"),
        "내용 쓰기 권한": (OPERATOR_REPLY, "  contents: read\n  issues: write\n\nconcurrency", "  contents: write\n  issues: write\n\nconcurrency"),
        "이슈 쓰기 권한 없음": (OPERATOR_REPLY, "  issues: write\n\nconcurrency", "\nconcurrency"),
        "소유자 조건 뺌": (OPERATOR_REPLY, " && github.event.issue.author_association == 'OWNER'", ""),
        "OWNER 조건 뺌": (OPERATOR_REPLY, "github.event.issue.user.login == github.repository_owner && ", ""),
        "조건을 넓힘": (OPERATOR_REPLY, "== 'OWNER'", "== 'OWNER' || github.event.issue.author_association == 'MEMBER'"),
        "조건을 뒤집음": (OPERATOR_REPLY, "github.event.issue.user.login == github.repository_owner", "github.event.issue.user.login != github.repository_owner"),
        "조건 없음": (OPERATOR_REPLY, "    if: github.event.issue.user.login == github.repository_owner && github.event.issue.author_association == 'OWNER'\n", ""),
        "checkout ref": (OPERATOR_REPLY, "      - uses: actions/checkout@v4\n        with:\n          persist-credentials: false\n",
                         "      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.issue.title }}\n          persist-credentials: false\n"),
        "자격 증명 남김": (OPERATOR_REPLY, "          persist-credentials: false\n", "          persist-credentials: true\n"),
        "run 에 표현식": (OPERATOR_REPLY, "python -m pipeline.operator_loop ack", "python -m pipeline.operator_loop ack ${{ github.event.issue.title }}"),
        "env 에 이슈 제목": (OPERATOR_REPLY, "          GITHUB_TOKEN:", "          ISSUE_TITLE: ${{ github.event.issue.title }}\n          GITHUB_TOKEN:"),
        "토큰 값 바꿈": (OPERATOR_REPLY, "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}", "GITHUB_TOKEN: ${{ secrets.OTHER_TOKEN }}"),
        "그룹이 고정": (OPERATOR_REPLY, "group: operator-reply-${{ github.event.issue.number }}", "group: operator-reply"),
        "취소함": (OPERATOR_REPLY, "cancel-in-progress: false", "cancel-in-progress: true"),
        "단계 추가": (OPERATOR_REPLY, "        run: python -m pipeline.operator_loop ack\n", "        run: python -m pipeline.operator_loop ack\n\n      - run: echo hi\n"),
        "단계 앞에 추가": (OPERATOR_REPLY, "      - uses: actions/setup-python@v5\n", "      - run: echo first\n      - uses: actions/setup-python@v5\n"),
        "continue-on-error": (OPERATOR_REPLY, "      - name: 접수 확인(코멘트·라벨·텔레그램)\n", "      - name: 접수 확인(코멘트·라벨·텔레그램)\n        continue-on-error: true\n"),
        "job env": (OPERATOR_REPLY, "    timeout-minutes: 5\n", "    timeout-minutes: 5\n    env:\n      X: '1'\n"),
        "다른 워크플로 호출": (OPERATOR_REPLY, "    runs-on: ubuntu-latest\n", "    uses: ./.github/workflows/other.yml\n    runs-on: ubuntu-latest\n"),
        "제한 시간 없음": (OPERATOR_REPLY, "    timeout-minutes: 5\n", ""),
    }

    def test_every_mutation_of_the_push_workflow_is_caught(self):
        for label, (rel, old, new) in self.REQUEST_MUTATIONS.items():
            with self.subTest(label):
                found = self.errors(lambda texts: swap(texts, rel, old, new))
                self.assertTrue(found, f"WF-14 가 잡지 못했다: {label}")
                self.assertTrue(all(f.check == "WF-14" and f.level == "ERROR" and f.path == rel for f in found), [f.line() for f in found])

    def test_every_mutation_of_the_issue_workflow_is_caught(self):
        for label, (rel, old, new) in self.REPLY_MUTATIONS.items():
            with self.subTest(label):
                found = self.errors(lambda texts: swap(texts, rel, old, new))
                self.assertTrue(found, f"WF-14 가 잡지 못했다: {label}")
                self.assertTrue(all(f.check == "WF-14" and f.level == "ERROR" and f.path == rel for f in found), [f.line() for f in found])

    def test_the_two_workflows_are_judged_independently(self):
        rel, old, new = self.REQUEST_MUTATIONS["쓰기 권한"]
        found = self.errors(lambda texts: swap(texts, rel, old, new))
        self.assertEqual({f.path for f in found}, {AI_REQUEST})

    def test_messages_fold_values_from_the_file_into_one_plain_line(self):
        evil = "evil\n::error::forged ##[group]x"

        def make(texts):
            swap(texts, AI_REQUEST, "group: ai-request-${{ github.sha }}", "group: \"" + evil.replace("\n", "\\n") + "\"")
        found = self.errors(make)
        self.assertTrue(found)
        for finding in found:
            for text in (finding.message, finding.line()):
                self.assertEqual(len(text.splitlines()), 1, text)
                self.assertNotIn("::", text)
                self.assertNotIn("##[", text)

    def test_a_yaml_syntax_error_is_left_to_the_other_rule_and_never_crashes(self):
        found = self.errors(lambda texts: swap(texts, AI_REQUEST, "jobs:\n", "jobs: [\n"))
        self.assertEqual(found, [])                                                          # WF-0 가 알린다
        self.assertEqual(self.errors(lambda texts: texts.update({AI_REQUEST: "- 목록\n- 최상위\n"})), [])

    def test_the_rule_does_not_apply_without_pyyaml(self):
        saved = vr.yaml
        vr.yaml = None
        try:
            self.assertEqual(vr.check_operator_workflows(ROOT, [AI_REQUEST, OPERATOR_REPLY]), [])
        finally:
            vr.yaml = saved

    def test_the_real_repository_workflows_still_pass_the_telegram_secret_rule(self):
        self.assertEqual(vr.check_telegram_secrets(ROOT, vr.list_files(ROOT)), [])

    def test_a_changed_telegram_secret_position_is_caught_by_the_existing_rule_too(self):
        def make(texts):
            swap(texts, AI_REQUEST, "run: python -m pipeline.operator_loop requests", "run: echo ${{ secrets.TELEGRAM_BOT_TOKEN }}")
        with tempfile.TemporaryDirectory() as tmp:
            root, files = rule_root(tmp, make)
            self.assertTrue(vr.check_telegram_secrets(root, files))
            self.assertTrue(vr.check_operator_workflows(root, files))


class RequestFileRuleTest(unittest.TestCase):
    def errors(self, files, extra=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
            return vr.check_request_files(root, sorted(files))

    def one(self, name, text):
        return self.errors({ol.REQUEST_DIR + "/" + name: text})

    def test_a_good_file_the_readme_and_unrelated_files_pass(self):
        files = {ol.REQUEST_DIR + "/R-001_merge-pr57.md": oh.request_text(), ol.REQUEST_DIR + "/README.md": "설명", "docs/R-002_x.md": "아무 글", "인수인계/요청함_옛.md": "x"}
        self.assertEqual(self.errors(files), [])

    def test_every_problem_the_parser_names_is_an_error_with_its_sentence(self):
        cases = {"bad_name": ("r-001_x.md", oh.request_text()), "no_front_matter": ("R-001_x.md", "제목 없음\n"), "unclosed": ("R-001_x.md", "---\nid: R-001\n"),
                 "bad_line": ("R-001_x.md", oh.request_text(extra="이상한 줄")), "duplicate_key": ("R-001_x.md", oh.request_text(extra="id: R-001")),
                 "unknown_key": ("R-001_x.md", oh.request_text(extra="owner: x")), "bad_id": ("R-001_x.md", oh.request_text(id="R-1")),
                 "id_mismatch": ("R-002_x.md", oh.request_text()), "bad_kind": ("R-001_x.md", oh.request_text(kind="zzz")), "missing_title": ("R-001_x.md", oh.request_text(title=None)),
                 "missing_summary": ("R-001_x.md", oh.request_text(summary=None)), "bad_urgency": ("R-001_x.md", oh.request_text(urgency="높음")),
                 "bad_pr": ("R-001_x.md", oh.request_text(pr="0")), "bad_created": ("R-001_x.md", oh.request_text(created="어제")),
                 "long_title": ("R-001_x.md", oh.request_text(title="가" * 81)), "long_summary": ("R-001_x.md", oh.request_text(summary="나" * 301)),
                 "long_line": ("R-001_x.md", oh.request_text(title="x" * 2100))}
        for code, (name, text) in cases.items():
            with self.subTest(code):
                found = self.one(name, text)
                self.assertEqual(len(found), 1, [f.line() for f in found])
                self.assertEqual((found[0].check, found[0].level, found[0].path), ("REQ-1", "ERROR", ol.REQUEST_DIR + "/" + name))
                self.assertEqual(found[0].message, ol.problem_text(code))

    def test_a_request_file_in_a_subfolder_is_an_error_because_no_alert_would_go_out(self):
        found = self.errors({ol.REQUEST_DIR + "/sub/R-001_x.md": oh.request_text(), ol.REQUEST_DIR + "/sub/notes.md": "메모"})
        self.assertEqual([(f.check, f.level) for f in found], [("REQ-1", "ERROR")])

    def test_a_file_that_is_not_a_request_name_is_a_warning(self):
        found = self.one("메모.md", "x")
        self.assertEqual([(f.check, f.level) for f in found], [("REQ-1", "WARN")])

    def test_two_files_with_the_same_number_are_an_error(self):
        files = {ol.REQUEST_DIR + "/R-001_a.md": oh.request_text(), ol.REQUEST_DIR + "/R-001_b.md": oh.request_text()}
        found = self.errors(files)
        self.assertEqual(len(found), 1)
        self.assertIn("요청 번호 R-001 가", found[0].message)
        self.assertEqual(found[0].path, ol.REQUEST_DIR + "/R-001_b.md")

    def test_an_unreadable_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / ol.REQUEST_DIR / "R-001_x.md"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"x" * (vr.MAX_TEXT_BYTES + 1))
            found = vr.check_request_files(root, [ol.REQUEST_DIR + "/R-001_x.md"])
            self.assertEqual([(f.check, f.level) for f in found], [("REQ-1", "ERROR")])

    def test_messages_are_one_plain_line(self):
        for found in (self.one("R-001_x.md", oh.request_text(extra="이상한 줄")), self.one("R-001_x.md", "---\nid: R-001\n::error::x\n---\n")):
            for finding in found:
                self.assertEqual(len(finding.line().splitlines()), 1)
                self.assertNotIn("::", finding.message)


class FormRuleTest(unittest.TestCase):
    def errors(self, mutate=None):
        with tempfile.TemporaryDirectory() as tmp:
            root, files = rule_root(tmp, mutate)
            return vr.check_operator_forms(root, files)

    def test_the_real_forms_pass(self):
        self.assertEqual(self.errors(), [])

    MUTATIONS = {
        "답 양식 제목": (REPLY_FORM, 'title: "[답변] "', 'title: "[질문] "'),
        "답 양식 라벨": (REPLY_FORM, 'labels: ["운영자응답"]', 'labels: ["운영자응답", "blog-control"]'),
        "답 양식에 편집 라벨": (REPLY_FORM, 'labels: ["운영자응답"]', 'labels: ["blog-control", "edit:page"]'),
        "답 양식 라벨 없음": (REPLY_FORM, 'labels: ["운영자응답"]\n', ""),
        "요청 번호 필수 아님": (REPLY_FORM, "      placeholder: \"R-001\"\n    validations:\n      required: true\n", "      placeholder: \"R-001\"\n    validations:\n      required: false\n"),
        "메모를 필수로": (REPLY_FORM, "      description: \"AI 에게 전할 말(선택). 화면에 보인 문구는 적어도 되지만 비밀번호·토큰·키 값은 쓰지 마세요.\"\n    validations:\n      required: false\n",
                    "      description: \"AI 에게 전할 말(선택). 화면에 보인 문구는 적어도 되지만 비밀번호·토큰·키 값은 쓰지 마세요.\"\n    validations:\n      required: true\n"),
        "항목 제목 바꿈": (REPLY_FORM, 'label: "요청 번호"', 'label: "번호"'),
        "항목 id 바꿈": (REPLY_FORM, "id: request_id", "id: req"),
        "항목 id 겹침": (REPLY_FORM, "id: memo", "id: choice"),
        "항목 종류 바꿈": (REPLY_FORM, "  - type: textarea\n    id: memo\n", "  - type: input\n    id: memo\n"),
        "항목 하나 없음": (REPLY_FORM, "  - type: input\n    id: choice\n    attributes:\n      label: \"선택\"\n", "  - type: input\n    id: choice_x\n    attributes:\n      label: \"선택\"\n"),
        "선택지 문구 바꿈": (REPLY_FORM, '- "승인 — 제안한 대로 진행해 주세요"', '- "승인 - 제안한 대로 진행해 주세요"'),
        "선택지 추가": (REPLY_FORM, '        - "문제 — 아래 메모를 보세요"\n', '        - "문제 — 아래 메모를 보세요"\n        - "그냥 통과"\n'),
        "선택지 순서": (REPLY_FORM, '        - "거절 — 하지 마세요"\n        - "보류 — 나중에 다시 물어 주세요"\n', '        - "보류 — 나중에 다시 물어 주세요"\n        - "거절 — 하지 마세요"\n'),
        "안내 글 문장 뺌": (REPLY_FORM, "**비밀번호·토큰·키 값은 절대 쓰지 마세요.**", "**비밀 값에 주의하세요.**"),
        "안내 글 없음": (REPLY_FORM, "  - type: markdown\n    attributes:\n      value: |\n", "  - type: markdown\n    attributes:\n      x: |\n"),
        "요청 양식 제목": (TASK_FORM, 'title: "[요청] "', 'title: "[페이지 수정] "'),
        "요청 양식 라벨": (TASK_FORM, 'labels: ["운영자요청"]', 'labels: ["blog-control"]'),
        "승인 범위 필수 아님": (TASK_FORM, "승인합니다(T3 포함)\"\n    validations:\n      required: true\n", "승인합니다(T3 포함)\"\n    validations:\n      required: false\n"),
        "작업 내용 필수 아님": (TASK_FORM, "      description: \"무엇을 왜 하고 싶은지 쉬운 말로 적어 주세요. 길어도 됩니다.\"\n    validations:\n      required: true\n",
                         "      description: \"무엇을 왜 하고 싶은지 쉬운 말로 적어 주세요. 길어도 됩니다.\"\n    validations:\n      required: false\n"),
        "긴급도 선택지": (TASK_FORM, '        - "천천히"\n', '        - "아주 천천히"\n'),
        "승인 범위 문구": (TASK_FORM, '- "아니요 — 논의·준비까지만"', '- "아니요"'),
        "요청 양식 안내": (TASK_FORM, "비밀번호·토큰·키 값은 절대 쓰지 마세요", "주의하세요"),
        "빈 이슈 막음": (CONFIG, "blank_issues_enabled: true", "blank_issues_enabled: false"),
        "빈 이슈 항목 없음": (CONFIG, "blank_issues_enabled: true\n", ""),
        "안내 링크가 다른 저장소": (CONFIG, "https://github.com/shine88pc/chanceblog/", "https://github.com/other/repo/"),
        "안내 링크 둘": (CONFIG, "    about:", "  - name: 둘째\n    url: \"https://github.com/shine88pc/chanceblog/x\"\n    about: 둘째 링크\n  - name: 셋째\n    url: \"https://github.com/shine88pc/chanceblog/y\"\n    about:"),
    }

    def test_every_mutation_is_caught(self):
        for label, (rel, old, new) in self.MUTATIONS.items():
            with self.subTest(label):
                found = self.errors(lambda texts: swap(texts, rel, old, new))
                self.assertTrue(found, f"FORM-1 이 잡지 못했다: {label}")
                self.assertTrue(all(f.check == "FORM-1" and f.level == "ERROR" and f.path == rel for f in found), [f.line() for f in found])

    def test_a_yaml_error_is_reported_and_missing_files_are_skipped(self):
        found = self.errors(lambda texts: texts.update({REPLY_FORM: "name: [\n"}))
        self.assertEqual([(f.check, f.path) for f in found], [("FORM-1", REPLY_FORM)])
        with tempfile.TemporaryDirectory() as tmp:
            root, files = rule_root(tmp)
            self.assertEqual(vr.check_operator_forms(root, [name for name in files if name not in (REPLY_FORM, TASK_FORM, CONFIG)]), [])

    def test_the_rule_does_not_apply_without_pyyaml(self):
        saved = vr.yaml
        vr.yaml = None
        try:
            self.assertEqual(vr.check_operator_forms(ROOT, [REPLY_FORM]), [])
        finally:
            vr.yaml = saved

    def test_messages_fold_values_from_the_file(self):
        found = self.errors(lambda texts: swap(texts, REPLY_FORM, 'title: "[답변] "', 'title: "x\\n::error::forged"'))
        self.assertTrue(found)
        for finding in found:
            self.assertEqual(len(finding.line().splitlines()), 1)
            self.assertNotIn("::", finding.message)


class WholeValidatorTest(unittest.TestCase):
    def test_the_run_checks_registers_the_three_rules(self):
        source = Path(vr.__file__).read_text(encoding="utf-8")
        for call in ("check_operator_workflows(root, files)", "check_request_files(root, files)", "check_operator_forms(root, files)"):
            self.assertIn("findings += " + call, source)

    def test_a_pull_request_that_breaks_a_rule_fails_the_whole_validator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / ".github", root / ".github")
            text = (root / AI_REQUEST).read_text(encoding="utf-8")
            (root / AI_REQUEST).write_text(text.replace("contents: read", "contents: write"), encoding="utf-8", newline="\n")
            findings = vr.run_checks(root)
            self.assertIn("WF-14", {f.check for f in findings if f.level == "ERROR"})


if __name__ == "__main__":
    unittest.main()
