"""HANDOFF2 — 저장소 `인수인계/도구/` 로 옮긴 도구 사본의 시험(정적·존재·순수 함수·끝에서 끝까지).

배경: 새 PC·새 세션이 첫 보고·병합 부탁·병합완료 확인·CI 확인·감시를 하려면 필요한 도구가 저장소에 최신으로 있어야 한다(운영자 이슈 #198 의 후속). 이 시험은 옮긴 도구가
(1) 이 PC 의 사용자 이름·사용자 폴더·고정 작업 폴더·실제 키·광고 번호가 없는 일반형인지(정적 — 2026-11-23 MIG1 이 옮긴 이 PC 현행판 사본 가운데 옛 PC 의 작업 폴더 이름을 상수로 쓰는 13개는 `W_PATH_COPIES` 에 이름을 올려 '고정 작업 폴더' 한 가지 모양만 허용하고 나머지 모양은 그대로 막는다),
(2) 안내 문서·복사 목록·감시 프롬프트가 말하는 파일이 실제로 저장소에 있는지(존재),
(3) 순수 함수와 가짜 응답으로 약속대로 도는지(`merge_guard` 는 판정만 하고 푸시·병합이 없다, `watch_issues` 는 10분 주기(한 주기에 이슈·이슈 코멘트 두 번 읽어 시간당 12회)이고 한도가 바닥나면 쉰다, `resume_check` 는 비밀·경로를 찍지 않는다 …),
(4) 복사본이 작업 폴더 W 안에서 실제 git 으로 끝까지 도는지(푸시하지 않는다)를 못박는다.
네트워크·실제 GitHub·텔레그램은 쓰지 않는다(가짜 응답 — 진짜 git 은 임시 폴더의 로컬 저장소뿐). 다른 묶음의 결정 번호·요청 번호·전체 최댓값은 못박지 않는다.
"""
import ast
import contextlib
import datetime
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tokenize
import types
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import _bootstrap
from pipeline import egress
from pipeline import operator_loop as ol

ROOT = _bootstrap.ROOT
TOOLS = ROOT / "인수인계" / "도구"
WORK = TOOLS / "work"
SCRATCH = WORK / "scratch"
FORMS = WORK / "양식"
README = TOOLS / "README.md"
SETUP = TOOLS / "setup_workspace.py"
PROMPT_V3 = TOOLS / "정기_현황_알림_프롬프트_v3.txt"
PROMPT_OLD = TOOLS / "정기_현황_알림_프롬프트.txt"
MODEL_DOC = TOOLS / "정기_현황_알림_본보기.md"
BS = chr(92)                                                                  # 역슬래시 — 편집 도구가 소스 안의 역슬래시 이스케이프를 망가뜨려서 글자로 만든다

# 시험용 가짜 비밀(조립 문자열 — 소스에 비밀 모양 글자가 그대로 있지 않다). 모두 CANARY 표지가 들어 있다.
FAKE_GOOGLE_KEY = "AI" + "za" + "CANARY_" + "k" * 24
FAKE_GITHUB_TOKEN = "gh" + "p_" + "CANARY" + "t" * 24
FAKE_GITHUB_PAT = "github" + "_pat_" + "CANARY_" + "p" * 24
FAKE_KEY_VALUE = "to" + "ken=CANARY_" + "v" * 8
FAKE_TELEGRAM = "123456789" + ":" + "CANARY_" + "T" * 28
FAKE_SK = "s" + "k-" + "CANARY" + "s" * 20
FAKE_AD = "ca-" + "pub-" + "1" * 10
FAKE_PEM = "-----" + "BEGIN " + "PRIVATE KEY" + "-----"

_loaded = [0]


def load_tool(path, extra_path=None):
    """도구 파일을 시험마다 새로 읽는다 — 도구가 sys.path·sys.modules 에 끼워 넣은 것(자기 폴더의 이웃 모듈)은 시험이 끝나면 되돌린다.
    extra_path: 도구가 `import 이웃모듈` 하는 폴더(읽는 동안만 import 경로 맨 앞에 올린다 — make_request·make_merged_notice 가 `work/` 의 이웃을 부른다)."""
    path = Path(path)
    _loaded[0] += 1
    name = f"handoff_tool_{path.stem}_{_loaded[0]}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    saved_path, saved_modules = list(sys.path), set(sys.modules)
    if extra_path is not None:
        sys.path.insert(0, str(extra_path))
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
        roots = (TOOLS.resolve(), path.resolve().parent)
        for key in list(sys.modules):
            if key in saved_modules or key == name:
                continue
            origin = getattr(sys.modules[key], "__file__", None)
            try:
                resolved = Path(origin).resolve() if origin else None
            except (OSError, ValueError):
                resolved = None
            if resolved is not None and any(root == resolved.parent or root in resolved.parents for root in roots):
                del sys.modules[key]
    return module


def capture(func, *args, **kwargs):
    """func 를 부르고 (돌려준 값, 표준 출력, 표준 오류)를 돌려준다."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        result = func(*args, **kwargs)
    return result, out.getvalue(), err.getvalue()


def read(path):
    return Path(path).read_text(encoding="utf-8")


def section(text, number):
    """README 의 `## N.` 절 하나(다음 `## ` 앞까지)."""
    match = re.search(r"^## %d[.] .*$" % number, text, re.M)
    assert match, f"{number}절이 없다"
    rest = text[match.end():]
    following = re.search(r"^## [0-9]+[.] ", rest, re.M)
    return text[match.start(): match.end() + (following.start() if following else len(rest))]


def table_row(text, name):
    """README 표에서 첫 칸이 `name` 으로 시작하는 행 한 줄."""
    rows = [line for line in text.splitlines() if line.startswith(f"| `{name}")]
    assert len(rows) == 1, (name, len(rows))
    return rows[0]


# ==== 이관한 파일 목록 =====================================================================
STRICT_FILES = sorted([*WORK.glob("*.py"), *SCRATCH.glob("*.py"), *SCRATCH.glob("*.sh"), *FORMS.glob("*.md"), SETUP, PROMPT_V3])
DOC_FILES = sorted([README, PROMPT_OLD, MODEL_DOC, *WORK.glob("*.md")])
PYTHON_FILES = sorted([*WORK.glob("*.py"), *SCRATCH.glob("*.py"), SETUP])

EXPECTED_WORK = {"commit_as_author.py", "make_info_request.py", "make_merged_notice.py", "make_request.py", "mk_merge_branch.py", "next_notice_no.py", "notice_tools.py", "pipsafe.py"}
EXPECTED_SCRATCH = {"check_notify.py", "ci_web.py", "memfree.py", "merge_guard.py", "mk_lane_merge.py", "mk_lane_merge_desktop.py", "resume_check.py", "run_annotations.py", "run_steps_times.py",
                    "run_times.py", "runs_by_sha.py", "shadow_check_1115.py", "shadow_table.py", "verify_live_counts.py", "wait_ci.py", "wait_ci_multi.py", "watch_desktop.py",
                    "watch_heads2.sh", "watch_issues.py", "watch_light.py", "web_runs.py"}
EXPECTED_FORMS = {"merge_request_template_v2.md", "progress_draft_template.md"}
# README 가 이름을 말하지만 이 저장소에 없는 파일 — 이유가 있는 것뿐이다(아래 시험이 '정말 없다'도 확인한다).
NOT_IN_REPO = {
    "bootstrap.py": "이관 번들 가지(`ai/claude/NO-MERGE-migration-bundle`)에만 있다",
    "update_resume_block.py": "처음 PC 의 Claude 기억 폴더 전용이라 옮기지 않았다",
    "insert_resume_entry.py": "처음 PC 의 Claude 기억 폴더 전용이라 옮기지 않았다",
    "fill_final_guide.py": "처음 PC 의 Claude 기억 폴더 전용이라 옮기지 않았다",
    "verify_pause.py": "일회성 도구라 옮기지 않았다(읽기 함수는 check_notify.py 가 품음)",
    "push_qtci.py": "앱 Qt 시험 임시 가지를 push 하는 도구 — 이 폴더의 시험이 '도구는 git push 를 하지 않는다' 를 못박아 옮기지 않았다(README 9-4)",
    "qtci_wait.sh": "push_qtci.py 의 짝 — qtci_status.py 가 저장소 밖이라 옮기지 않았다(README 9-4)",
    "qtci_web.py": "push_qtci.py 의 짝 — 임시 워크플로가 저장소 밖이라 옮기지 않았다(README 9-4)",
    "qtci_status.py": "옛 PC 의 W/scratch 에만 있는 Qt 시험 상태 읽기 도구 — 저장소에 없다(README 9-4)",
    "qtci_read.py": "옛 PC 의 W/scratch 에만 있는 Qt 시험 결과 읽기 도구 — 저장소에 없다(README 9-4)",
}

# ---- 정적 검사의 금지 모양 -----------------------------------------------------------------
DRIVE_SEP = "[" + BS * 2 + "/]"                                                # 정규식의 `[\\/]`
FORBIDDEN_STRICT = {
    "이 PC 사용자 이름": re.compile("SDI" + "_USER", re.I),
    "사용자 폴더 경로": re.compile("[A-Za-z]:" + DRIVE_SEP + "+Users" + DRIVE_SEP + "|/Users/"),
    "고정 작업 폴더": re.compile("[A-Za-z]:" + DRIVE_SEP + "+work" + DRIVE_SEP + "+ai", re.I),
    "Claude 기억 경로": re.compile("[.]claude"),
    "처음 PC 의 개발 도구 폴더": re.compile("ccg" + "ui", re.I),
    "구글 키 모양": re.compile("AI" + "za[0-9A-Za-z_-]{20,}"),
    "깃허브 토큰 모양": re.compile("gh" + "p_[0-9A-Za-z]{20,}|github" + "_pat_[0-9A-Za-z_]{20,}"),
    "sk 키 모양": re.compile("(?<![A-Za-z0-9_])s" + "k-[A-Za-z0-9]{20,}"),
    "텔레그램 토큰 모양": re.compile("[0-9]{6,12}:[A-Za-z0-9_-]{30,50}"),
    "구글 로그인 토큰 모양": re.compile("ya" + "29[.][0-9A-Za-z_-]{20,}"),
    "비밀 키 머리글": re.compile("-----" + "BEGIN [A-Z ]*PRIVATE KEY" + "-----"),
    "광고 번호 모양": re.compile("ca-" + "pub-[0-9]{6,}|(?<![A-Za-z0-9])pub-[0-9]{8,}"),
    "긴 숫자 번호(블로그·게시자 ID 모양)": re.compile("(?<![0-9A-Za-z_.-])[0-9]{16,}(?![0-9])"),
}
FORBIDDEN_DOCS = {key: value for key, value in FORBIDDEN_STRICT.items() if key != "처음 PC 의 개발 도구 폴더"}     # 안내 문서·지시서는 처음 PC 의 개발 도구 폴더를 '처음 PC 의 것'으로 말할 수 있다
EMAIL_RX = re.compile("[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:[.][A-Za-z0-9-]+)+")

# 2026-11-23 MIG1 — 이 PC 의 현행판을 그대로 옮긴 사본 가운데 옛 PC 의 작업 폴더 W 이름을 상수·사용 예로 쓰는 도구. 그 한 가지 모양('고정 작업 폴더')만 파일별로 허용하고
# 나머지 모든 금지 모양(계정 이름·사용자 폴더·키·광고 번호 …)은 이 파일들에도 그대로 막는다. 목록은 실제로 그 글이 든 파일만 담는다(아래 시험이 확인 — 없으면 목록에서 뺀다).
# 새 도구가 고정 작업 폴더를 쓰려면 이름을 여기에 더하고 README 9-2 표에 바꿀 곳을 적어야 한다(README 시험이 확인).
W_PATH_KEY = "고정 작업 폴더"
W_PATH_COPIES = frozenset({"build_blog_merge.py", "ci_wip_status.py", "combine_lanes_desktop.py", "keep_both.py", "lanes.py", "mkverify.py", "pc_load.py", "prepush_check.sh",
                           "qt_lock.py", "rehearse.py", "run_modules.py", "squash_onto.py", "watch_all.sh"})
# 개인 메일이 아닌 가짜 주소 — 파일별로 허용하고 그 주소가 실제로 들어 있어야 한다(고정 작성자 메일 말고 STRICT_FILES·DOC_FILES 에 있어도 되는 메일은 이것뿐).
NON_PERSONAL_MAILS = {"rehearse.py": {"x" + "@" + "example.invalid"}}


def problems(text, forbidden):
    return [name for name, rx in forbidden.items() if rx.search(text)]


# ==== 1. 정적 — 고정 경로·사용자·비밀·광고 번호가 없다 ===========================================
class StaticHygieneTest(unittest.TestCase):
    def test_the_moved_tools_forms_and_prompt_are_general_and_clean(self):
        self.assertGreaterEqual(len(STRICT_FILES), 30)                                   # 훑는 파일 목록이 비어 거짓 통과하지 않는다
        for path in STRICT_FILES:
            allowed = {W_PATH_KEY} if path.name in W_PATH_COPIES else set()                   # 옛 PC 의 W 이름을 상수로 쓰는 현행판 사본은 그 한 가지 모양만 허용
            self.assertEqual([name for name in problems(read(path), FORBIDDEN_STRICT) if name not in allowed], [], path.name)

    def test_the_guides_and_briefs_are_clean_too(self):
        self.assertIn(README, DOC_FILES)
        for path in DOC_FILES:
            self.assertEqual(problems(read(path), FORBIDDEN_DOCS), [], path.name)

    def test_the_only_email_is_the_fixed_author_that_commit_as_author_already_had(self):
        allowed = set(EMAIL_RX.findall(read(WORK / "commit_as_author.py")))
        self.assertEqual(len(allowed), 1, allowed)
        for path in STRICT_FILES + DOC_FILES:
            self.assertLessEqual(set(EMAIL_RX.findall(read(path))), allowed | NON_PERSONAL_MAILS.get(path.name, set()), path.name)

    def test_the_work_folder_and_fake_mail_exemptions_are_real_and_nothing_else_is_exempt(self):
        by_name = {path.name: path for path in STRICT_FILES + DOC_FILES}
        for name, mails in NON_PERSONAL_MAILS.items():
            self.assertLessEqual(mails, set(EMAIL_RX.findall(read(by_name[name]))), name)                  # 목록은 실제로 그 주소가 든 파일만 담는다
        for name in sorted(W_PATH_COPIES):
            self.assertIn(W_PATH_KEY, problems(read(by_name[name]), FORBIDDEN_STRICT), name)               # 목록은 실제로 그 글이 든 파일만 담는다
        for path in STRICT_FILES:
            if path.name not in W_PATH_COPIES:
                self.assertNotIn(W_PATH_KEY, problems(read(path), FORBIDDEN_STRICT), path.name)            # 목록 밖의 파일은 그대로 막힌다
        self.assertEqual(len(W_PATH_COPIES), 13)
        for path in DOC_FILES:
            self.assertNotIn(W_PATH_KEY, problems(read(path), FORBIDDEN_DOCS), path.name)                  # 안내 문서는 목록 없이 그대로 막힌다

    def test_the_scanner_itself_catches_known_bad_samples_and_passes_clean_text(self):
        user = "SDI" + "_USER"
        bad = {
            "이 PC 사용자 이름": [user, user.lower(), "x " + user + " y"],
            "사용자 폴더 경로": ["C:" + BS + "Users" + BS + "someone" + BS + "x.py", "D:/Users/someone/x", "/Users/someone/x"],
            "고정 작업 폴더": ["C:" + BS + "wo" + "rk" + BS + "ai" + BS + "wt_r30", "C:/" + "wo" + "rk/" + "ai/scratch", "d:/" + "WO" + "RK/" + "AI", "C:" + BS * 2 + "wo" + "rk" + BS * 2 + "ai"],
            "Claude 기억 경로": ["x/.claude/projects", "~/.claude"],
            "처음 PC 의 개발 도구 폴더": ["C:" + BS + "ccg" + "ui" + BS + "py310"],
            "구글 키 모양": [FAKE_GOOGLE_KEY],
            "깃허브 토큰 모양": [FAKE_GITHUB_TOKEN, FAKE_GITHUB_PAT],
            "sk 키 모양": [FAKE_SK],
            "텔레그램 토큰 모양": [FAKE_TELEGRAM],
            "구글 로그인 토큰 모양": ["ya" + "29." + "d" * 30],
            "비밀 키 머리글": [FAKE_PEM, "-----" + "BEGIN " + "RSA PRIVATE KEY" + "-----"],
            "광고 번호 모양": [FAKE_AD, "pub-" + "2" * 12],
            "긴 숫자 번호(블로그·게시자 ID 모양)": ["id " + "3" * 19, "blog_id=" + "4" * 16],
        }
        self.assertEqual(set(bad), set(FORBIDDEN_STRICT))
        for name, samples in bad.items():
            for sample in samples:
                self.assertIn(name, problems(sample, FORBIDDEN_STRICT), (name, sample[:12]))
        clean = ("python -X utf8 W/scratch/resume_check.py --work W", "scratch/watch_issues.py", "git -C W/wt_r30 push --dry-run", "task-" + "x" * 30, "12345 67890 run id 43330630209",
                 "a" * 30 + " sk", "AI" + "za 짧은 것", "public key 설명", "pipeline/blogs.json", "모양 `[0-9]{6,12}:` 설명")
        for text in clean:
            self.assertEqual(problems(text, FORBIDDEN_STRICT), [], text[:20])


# ==== 2. 존재 — 말하는 파일이 실제로 있다 ===================================================
class InventoryAndExistenceTest(unittest.TestCase):
    def test_every_expected_tool_form_and_prompt_is_in_the_repository(self):
        self.assertLessEqual(EXPECTED_WORK, {path.name for path in WORK.glob("*.py")})
        self.assertLessEqual(EXPECTED_SCRATCH, {path.name for path in SCRATCH.iterdir() if path.is_file()})
        self.assertLessEqual(EXPECTED_FORMS, {path.name for path in FORMS.glob("*.md")})
        for path in (SETUP, README, PROMPT_V3, PROMPT_OLD, MODEL_DOC):
            self.assertTrue(path.is_file(), path.name)

    def test_setup_workspace_copies_every_file_under_work_and_the_prompt(self):
        setup = load_tool(SETUP)
        plan = setup.plan_copy()
        sources = {source for source, _rel in plan}
        for source in sources:
            self.assertTrue(source.is_file(), source)
        targets = [rel.as_posix() for _source, rel in plan]
        self.assertEqual(len(targets), len(set(targets)), "복사 대상 이름이 겹치면 한 파일이 다른 파일을 덮는다")
        on_disk = {path for path in WORK.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
        self.assertEqual(on_disk - sources, set(), "work/ 아래에 복사되지 않고 남는 파일이 있다 — setup_workspace.plan_copy 가 그 종류를 모른다")
        self.assertIn((PROMPT_V3, Path(setup.PROMPT_TARGET)), plan)
        self.assertEqual(setup.PROMPT_SOURCE, PROMPT_V3.name)
        for name in EXPECTED_SCRATCH:
            self.assertIn("scratch/" + name, targets, name)
        for name in EXPECTED_FORMS | EXPECTED_WORK:
            self.assertIn(name, targets, name)
        self.assertIn("audit6/improve/LANE_RULES.md", targets)                                 # 갈래 지시서가 가리키는 공통 규칙(2026-11-23)
        self.assertEqual([t for t in targets if t.startswith("audit6/")], ["audit6/improve/LANE_RULES.md"])

    def test_the_readme_names_only_files_that_exist_or_are_listed_as_not_in_the_repository(self):
        text = read(README)
        known = [path for path in TOOLS.rglob("*") if path.is_file()]
        tokens = set(re.findall("(?<![A-Za-z0-9_.-])([A-Za-z0-9_가-힣][A-Za-z0-9_가-힣./-]*[.](?:py|sh))(?![A-Za-z0-9_])", text))
        self.assertGreater(len(tokens), 20)                                                   # 훑을 이름이 있다(정규식이 깨져 거짓 통과하지 않게)
        for token in sorted(tokens):
            probe = token.split("/", 1)[1] if token.split("/", 1)[0] in ("wt_r30", "cd_repo") and "/" in token else token
            found = (ROOT / probe).is_file() or any(path.as_posix().endswith("/" + probe) for path in known)
            self.assertTrue(found or probe in NOT_IN_REPO or probe.split("/")[-1] in NOT_IN_REPO, f"README 가 말하는 파일이 저장소에 없다: {token}")

    def test_the_files_the_readme_says_are_not_in_the_repository_really_are_not(self):
        known = {path.name for path in TOOLS.rglob("*") if path.is_file()}
        text = read(README)
        for name, reason in NOT_IN_REPO.items():
            self.assertNotIn(name, known, f"{name} 은 이제 저장소에 있다 — README 의 '옮기지 않은 도구' 문장을 고친다({reason})")
            self.assertIn(name, text, name)
        for name in ("update_resume_block.py", "insert_resume_entry.py", "fill_final_guide.py"):
            self.assertIn("`" + name + "`", text)

    def test_the_prompt_v3_only_calls_tools_that_exist(self):
        text = read(PROMPT_V3)
        setup = load_tool(SETUP)
        targets = {rel.name for _source, rel in setup.plan_copy()}
        names = set(re.findall("(?<![A-Za-z0-9_.-])([A-Za-z0-9_]+[.](?:py|md))(?![A-Za-z0-9_])", text)) - {"_progress_draft.md", "pNNN.md"}
        self.assertGreaterEqual(names, {"make_info_request.py", "next_notice_no.py", "progress_draft_template.md", "web_runs.py", "wait_ci.py", "run_times.py", "commit_as_author.py"})
        for name in names:
            self.assertTrue(name in targets or (ROOT / "scripts" / name).is_file() or name == "setup_workspace.py", f"프롬프트 v3 가 부르는 {name} 이 복사 목록에도 저장소에도 없다")

    def test_the_old_documents_point_at_the_current_prompt_on_their_first_line(self):
        first = read(PROMPT_OLD).splitlines()[0]
        self.assertIn("옛 판", first)
        self.assertIn(PROMPT_V3.name, first)
        first = read(MODEL_DOC).splitlines()[0]
        self.assertIn("옛 판", first)
        self.assertIn(PROMPT_V3.name, first)
        self.assertNotIn("=== 프롬프트 시작", read(PROMPT_V3))                          # v3 은 표지 없이 전문이 곧 프롬프트다

    def test_the_request_branch_name_is_the_current_one_everywhere_it_is_a_target(self):
        setup = load_tool(SETUP)
        resume = load_tool(SCRATCH / "resume_check.py")
        self.assertEqual(setup.REQUEST_BRANCH, "ai/claude/NO-MERGE-operator-requests")
        self.assertEqual(resume.REQUEST_BRANCH, setup.REQUEST_BRANCH)
        old = "desktop-bootstrap" + "-merge"
        for path in (SETUP, README, SCRATCH / "resume_check.py"):
            self.assertNotIn(old, read(path), path.name)
        self.assertIn(setup.REQUEST_BRANCH, read(README))
        self.assertIn("git push origin " + setup.REQUEST_BRANCH, read(README))

    def test_every_script_reads_in_the_python_3_10_grammar_and_ends_with_a_newline(self):
        for path in PYTHON_FILES + [Path(__file__)]:
            source = read(path)
            ast.parse(source, filename=path.name, feature_version=(3, 10))
            self.assertTrue(source.endswith("\n"), path.name)

    def test_only_notice_tools_names_the_root_repository_folder_so_no_tool_creates_it(self):
        """README(make_request 행)는 `W/root_repo` 를 어느 도구도 만들지 않으니 직접 clone 하라고 한다 — 이 폴더 이름을 입에 올리는 도구는 읽기만 하는 notice_tools 하나뿐이다.
        만드는 도구(setup_workspace 포함)가 생기면 이 시험이 빨개져 README 문장도 함께 고치게 한다."""
        users = sorted(path.name for path in [*WORK.glob("*.py"), *SCRATCH.glob("*.py"), SETUP] if "root_repo" in read(path))
        self.assertEqual(users, ["notice_tools.py"])
        self.assertIn("어느 도구도 만들지 않으니", table_row(read(README), "make_request.py"))


# ==== 3. 읽기 전용·푸시 없음 — 약속을 구조로 못박는다 =========================================
READ_ONLY_SCRIPTS = ("check_notify", "ci_web", "memfree", "merge_guard", "resume_check", "run_annotations", "run_steps_times", "run_times", "runs_by_sha", "shadow_check_1115",
                     "shadow_table", "verify_live_counts", "wait_ci", "wait_ci_multi", "watch_desktop", "watch_issues", "watch_light", "web_runs")
WRITE_CALLS = {"write_text", "write_bytes", "mkdir", "unlink", "rmtree", "rename", "touch", "copy2", "copyfile", "copytree", "rmdir", "makedirs", "remove", "truncate"}
READ_ONLY_GIT = {"rev-list", "merge-base", "log", "diff"}


def write_calls(source):
    """소스에서 파일을 만들거나 바꾸는 호출(쓰기 모드 open 포함)의 (줄, 이름) 목록."""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
        if name in WRITE_CALLS:
            hits.append((node.lineno, name))
        if name == "open":
            mode = node.args[1].value if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) else None
            for keyword in node.keywords:
                if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                    mode = keyword.value.value
            if mode and any(ch in str(mode) for ch in "wax+"):
                hits.append((node.lineno, f"open({mode})"))
    return hits


class ReadOnlyPromisesTest(unittest.TestCase):
    def test_the_read_tools_never_write_files(self):
        for name in READ_ONLY_SCRIPTS:
            self.assertEqual(write_calls(read(SCRATCH / f"{name}.py")), [], name)

    def test_the_write_scanner_catches_known_writes(self):
        samples = ("from pathlib import Path\nPath('x').write_text('a')\n", "open('x', 'w')\n", "open('x', mode='a')\n", "import shutil\nshutil.rmtree('x')\n", "import os\nos.remove('x')\n")
        for source in samples:
            self.assertTrue(write_calls(source), source)
        for source in ("open('x')\n", "open('x', 'r', encoding='utf-8')\n", "x = 'a'.replace('a', 'b')\n"):
            self.assertEqual(write_calls(source), [], source)

    def test_no_tool_runs_a_git_push_and_the_watch_shell_script_only_lists_remote_heads(self):
        for path in [*WORK.glob("*.py"), *SCRATCH.glob("*.py")]:
            pushes = [node.lineno for node in ast.walk(ast.parse(read(path))) if isinstance(node, ast.Constant) and node.value == "push"]
            allowed = [] if path.name != "wait_ci.py" else pushes                          # wait_ci.py 의 `"event": "push"` 는 실행 목록의 이벤트 종류를 거르는 글자다
            self.assertEqual(pushes, allowed, path.name)
        wait_ci = read(SCRATCH / "wait_ci.py")
        self.assertEqual(len(re.findall('"push"', wait_ci)), 1)
        self.assertIn('"event": "push"', wait_ci)
        shell = read(SCRATCH / "watch_heads2.sh")
        self.assertNotIn("git push", shell)
        for command in re.findall(r"(?<![A-Za-z0-9_.-])git\s+(\S+)", re.sub(r"(?m)^\s*#.*$", "", shell)):
            self.assertEqual(command, "ls-remote", command)

    def test_merge_guard_only_uses_read_only_git_subcommands(self):
        tree = ast.parse(read(SCRATCH / "merge_guard.py"))
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "git":
                used |= {arg.value for arg in node.args[1:] if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and not arg.value.startswith("-")}
        self.assertEqual(used & {"push", "merge", "commit", "checkout", "reset", "fetch", "pull", "rebase", "branch", "tag", "cherry-pick"}, set())
        self.assertEqual({sub for sub in used if sub in READ_ONLY_GIT}, READ_ONLY_GIT)
        runs = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run"]
        self.assertEqual(len(runs), 1)                                                     # 하위 프로세스는 git 읽기 도우미 한 곳뿐

    def test_the_two_lane_merge_tools_never_push(self):
        for name in ("mk_lane_merge.py", "mk_lane_merge_desktop.py"):
            source = read(SCRATCH / name)
            calls = [node.args for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "git"]
            subcommands = {args[0].value for args in calls if args and isinstance(args[0], ast.Constant)}
            self.assertEqual(subcommands, {"fetch", "rev-parse", "merge-base", "worktree", "branch", "merge", "status", "diff", "rev-list"}, name)
            self.assertNotIn("push", subcommands)
            self.assertIn("푸시·병합 부탁은 하지 않는다", source)


# ==== 4. merge_guard — 등급 판정과 검사 전용 ==================================================
class FakeGit:
    """merge_guard.git 대신 쓰는 가짜 — (표준 출력, 종료 코드)를 돌려주고 불린 하위 명령을 적어 둔다."""

    def __init__(self, ahead="1", rev_rc=0, ff_rc=0, title="[M073] 문서 정리", files=("docs/a.md",), diff="+++ b/docs/a.md\n+안전한 줄\n-지운 줄\n",
                 message="요약\n\n독립 검증: 통과 (필수 0, 권고 1)", listing=""):
        self.ahead, self.rev_rc, self.ff_rc, self.title, self.files, self.diff, self.message, self.listing = ahead, rev_rc, ff_rc, title, files, diff, message, listing
        self.calls = []

    def __call__(self, repo, *args):
        self.calls.append(args)
        sub = args[0]
        if sub == "rev-list":
            return self.ahead, self.rev_rc
        if sub == "merge-base":
            return "", self.ff_rc
        if sub == "log":
            if "--format=%s" in args:
                return self.title, 0
            if "--format=%B" in args:
                return self.message, 0
            return self.listing, 0
        if sub == "diff":
            return ("\n".join(self.files), 0) if "--name-only" in args else (self.diff, 0)
        raise AssertionError(f"예상 밖의 git 하위 명령: {args}")


class MergeGuardTest(unittest.TestCase):
    BRANCH = "ai/claude/M073-docs-cleanup"

    def setUp(self):
        self.mg = load_tool(SCRATCH / "merge_guard.py")

    def inspect(self, fake, allow="A", ci="success", branch=BRANCH):
        with mock.patch.object(self.mg, "git", fake):
            return self.mg.inspect("repo", "origin/main", branch, branch, allow, ci)

    def test_tier_orders_documents_tests_code_and_operator_only_paths(self):
        tier = self.mg.tier
        self.assertEqual(tier([]), "A")
        for paths in (["docs/a.md"], ["인수인계/작업내용.md"], ["WORKLOG.md"], ["docs/a.md", "인수인계/b.md"]):
            self.assertEqual(tier(paths), "A", paths)
        for paths in (["tests/test_x.py"], ["docs/a.md", "tests/test_x.py"]):
            self.assertEqual(tier(paths), "A+", paths)
        for paths in (["pipeline/run.py"], ["tests/test_x.py", "pipeline/run.py"], ["docs/a.md", "scripts/x.py"], ["notes/about.md"], ["docs/ads.txt"], ["pipeline/blogs_extra.json"]):
            self.assertEqual(tier(paths), "B", paths)
        for path in (".github/workflows/x.yml", "index.html", "_config.yml", "_layouts/default.html", "_includes/head.html", "ads.txt", "pipeline/blogs.json", "pipeline/source_registry.json",
                     "_posts/2026-01-01-x.md", "requirements.txt", "requirements-dev.txt", "vendor/lib.py", "about.md", "contact.md", "pages.json", "history.json", "blogger_history.json",
                     "feed.xml", "assets/img.png"):
            self.assertEqual(tier([path]), "C", path)
            self.assertEqual(tier(["docs/a.md", "tests/t.py", path]), "C", path)           # 운영자 전용 경로가 하나라도 있으면 다른 파일이 문서·시험이어도 C

    PROTECTION_GAP = ("privacy.md", "categories.md", "robots.txt", "posts.json", "pipeline/ai_processor_policy.json", "pipeline/ops_inbox_policy.json", "pipeline/egress.py", "scripts/validate_repo.py")

    def test_the_paths_the_readme_says_are_not_yet_operator_only_really_are_not(self):
        """README merge_guard 행의 '한계' 줄이 글자만이 아니라 코드와 묶인다 — 이 여덟 경로가 운영자 전용(C)이 되면 이 시험이 빨개져 README 줄과 이 목록을 함께 고치게 한다."""
        row = table_row(read(README), "merge_guard.py")
        for path in self.PROTECTION_GAP:
            self.assertEqual(self.mg.tier([path]), "B", f"{path} 가 이제 운영자 전용(C)이다 — README merge_guard 행의 '한계' 줄과 이 시험의 PROTECTION_GAP 을 함께 고친다")
            self.assertIn(f"`{path}`", row, path)
        for path in (".github/workflows/x.yml", "ads.txt", "index.html", "pipeline/blogs.json"):                 # 대조군: 지금도 운영자 전용인 것
            self.assertEqual(self.mg.tier([path]), "C", path)

    def test_a_clean_documents_only_branch_is_eligible(self):
        result = self.inspect(FakeGit())
        self.assertEqual((result["ok"], result["reasons"], result["tier"], result["files"]), (True, [], "A", 1))

    def test_every_condition_blocks_on_its_own(self):
        cases = (
            ("가지 이름이 ai/claude/M###-슬러그 규칙이 아님", dict(branch="ai/claude/docs-cleanup"), {}),
            ("가지 이름이 ai/claude/M###-슬러그 규칙이 아님", dict(branch="ai/claude/M73-x"), {}),                  # 세 자리 미만 번호도 규칙 밖
            ("가지 이름이 ai/claude/M###-슬러그 규칙이 아님", dict(branch="ai/claude/M12345-x"), {}),               # 다섯 자리도 규칙 밖
            ("가지 이름이 ai/claude/M###-슬러그 규칙이 아님", dict(branch="ai/claude/M073_x"), {}),                 # 하이픈이 아닌 구분자
            ("한 커밋이 아님", {}, dict(ahead="2")),
            ("한 커밋이 아님", {}, dict(ahead="0")),
            ("한 커밋이 아님", {}, dict(rev_rc=1)),
            ("빨리감기", {}, dict(ff_rc=1)),
            ("로 시작하지 않음", {}, dict(title="문서 정리")),
            ("M 번호가 다름", {}, dict(title="[M074] 문서 정리")),
            ("허용 등급", {}, dict(files=("tests/test_x.py",))),
            ("허용 등급", {}, dict(files=("pipeline/run.py",))),
            ("비밀 모양", {}, dict(diff="+++ b/docs/a.md\n+" + FAKE_GOOGLE_KEY + "\n")),
            ("초록으로 확인되지 않음", dict(ci="unknown"), {}),
            ("'독립 검증' 기록 문구가 없음", {}, dict(message="요약만 있다")),
        )
        for needle, call_kwargs, fake_kwargs in cases:
            result = self.inspect(FakeGit(**fake_kwargs), **call_kwargs)
            self.assertFalse(result["ok"], (needle, call_kwargs, fake_kwargs))
            self.assertTrue(any(needle in reason for reason in result["reasons"]), (needle, result["reasons"]))

    def test_allow_levels_open_tests_and_code_but_never_operator_only_paths(self):
        tests_only = FakeGit(files=("tests/test_x.py",))
        self.assertFalse(self.inspect(tests_only, allow="A")["ok"])
        self.assertTrue(self.inspect(tests_only, allow="A,A+")["ok"])
        code = FakeGit(files=("pipeline/run.py",))
        self.assertFalse(self.inspect(code, allow="A,A+")["ok"])
        self.assertTrue(self.inspect(code, allow="A,A+,B")["ok"])
        protected = self.inspect(FakeGit(files=("docs/a.md", ".github/workflows/x.yml")), allow="A,A+,B")
        self.assertFalse(protected["ok"])
        self.assertEqual(protected["tier"], "C")
        self.assertTrue(any("운영자 전용 경로 포함: .github/workflows/x.yml" in reason for reason in protected["reasons"]), protected["reasons"])

    def test_secret_shapes_are_found_in_added_lines_only(self):
        shapes = (FAKE_GOOGLE_KEY, FAKE_GITHUB_TOKEN, FAKE_GITHUB_PAT, FAKE_SK, FAKE_AD, FAKE_PEM, "bot" + FAKE_TELEGRAM, "api" + "_key = CANARY_" + "a" * 20, "sec" + "ret: CANARY_" + "b" * 24)
        for shape in shapes:
            added = self.inspect(FakeGit(diff="+++ b/docs/a.md\n+" + shape + "\n"))
            self.assertTrue(any("비밀 모양" in reason for reason in added["reasons"]), shape[:12])
            removed = self.inspect(FakeGit(diff="--- a/docs/a.md\n-" + shape + "\n"))
            self.assertFalse(any("비밀 모양" in reason for reason in removed["reasons"]), shape[:12])      # 지운 줄은 세지 않는다
            header = self.inspect(FakeGit(diff="+++ b/" + shape + "\n"))
            self.assertFalse(any("비밀 모양" in reason for reason in header["reasons"]), shape[:12])        # 파일 머리줄은 세지 않는다
        for harmless in ("tokenizer=fast", "key 설명", "monkey=banana", "AI" + "za 짧음", "ghp 설명"):
            self.assertTrue(self.inspect(FakeGit(diff="+++ b/docs/a.md\n+" + harmless + "\n"))["ok"], harmless)

    def test_a_remaining_must_fix_is_only_a_note_for_a_human(self):
        noted = self.inspect(FakeGit(message="요약\n\n독립 검증: 필수 1 남음"))
        self.assertTrue(noted["ok"])
        self.assertEqual(len(noted["notes"]), 1)
        self.assertEqual(self.inspect(FakeGit(message="독립 검증: 필수 0"))["notes"], [])
        self.assertEqual(self.inspect(FakeGit(message="독립 검증: 필수 1 이었으나 필수 0 으로 정리"))["notes"], [])

    def test_inspect_only_asks_git_to_read(self):
        fake = FakeGit()
        self.inspect(fake)
        self.assertEqual({call[0] for call in fake.calls}, {"rev-list", "merge-base", "log", "diff"})

    def test_main_prints_the_verdict_and_returns_the_exit_codes(self):
        argv = ["merge_guard.py", "repo", self.BRANCH, "--ci", "success"]
        with mock.patch.object(self.mg, "git", FakeGit()), mock.patch.object(sys, "argv", argv):
            code, out, _err = capture(self.mg.main)
        self.assertEqual(code, 0)
        self.assertIn("판정: ELIGIBLE", out)
        self.assertIn("등급 A", out)
        with mock.patch.object(self.mg, "git", FakeGit(files=("pipeline/run.py",))), mock.patch.object(sys, "argv", argv):
            code, out, _err = capture(self.mg.main)
        self.assertEqual(code, 1)
        self.assertIn("판정: NOT ELIGIBLE", out)
        self.assertIn("허용 등급(A)", out)
        with mock.patch.object(self.mg, "git", FakeGit()), mock.patch.object(sys, "argv", ["merge_guard.py", "repo"]):
            code, out, err = capture(self.mg.main)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("가지 ref 가 필요합니다", err)

    def test_main_list_classifies_only_the_recent_merges_by_tier(self):
        listing = "\n".join(["h1|11-15 10:42|[M072] 안내 정비", "h2|11-15 09:00|봇 커밋", "h3|11-14 22:00|[M071] 계산 글", "h4|11-14 20:00|[M070] 작업 기록", "h5|11-14 19:00|[M069] 더 옛것"])
        fake = FakeGit(listing=listing, files=("docs/a.md",))
        with mock.patch.object(self.mg, "git", fake), mock.patch.object(sys, "argv", ["merge_guard.py", "repo", "--list", "3"]):
            code, out, _err = capture(self.mg.main)
        self.assertEqual(code, 0)
        self.assertEqual(out.count("| 파일"), 3)                                           # 병합 3건만(봇 커밋·더 옛것은 센 개수에 안 든다)
        self.assertIn("등급별 건수: {'A': 3}", out)
        self.assertNotIn("M069", out)
        self.assertNotIn("봇 커밋", out)
        self.assertTrue(all(call[0] in READ_ONLY_GIT for call in fake.calls))


# ==== 5. watch_issues — 10분 주기(이슈·이슈 코멘트 두 곳), 한도가 바닥나면 쉰다 =============================
def issue(number, login="someone", labels=(), title="제목", pull_request=False, created_at="2026-11-15T01:02:03Z"):
    item = {"number": number, "title": title, "user": {"login": login}, "labels": [{"name": name} for name in labels], "created_at": created_at}
    if pull_request:
        item["pull_request"] = {"url": "x"}
    return item


def http_error(code, headers=None):
    return urllib.error.HTTPError("https://api.invalid/x", code, "msg", headers or {}, None)


class Stop(BaseException):
    """감시 반복을 끝내는 시험 신호 — BaseException 이라 도구의 `except Exception` 에 걸리지 않는다."""


class FakeResponse:
    def __init__(self, body, etag="etag-1"):
        self.body, self.headers = body, {"ETag": etag}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class WatchIssuesTest(unittest.TestCase):
    NOW = 1_700_000_000

    def setUp(self):
        self.wi = load_tool(SCRATCH / "watch_issues.py")

    def run_watch(self, steps, comment_steps=()):
        sleeps, queue, c_queue = [], list(steps), list(comment_steps)

        def fake_fetch(etag, url=None):
            if url == self.wi.COMMENTS_URL:                                                       # 이슈 코멘트 목록 조회(2026-11-17 추가) — 단계가 없으면 '변경 없음'
                if not c_queue:
                    return etag, None
                step = c_queue.pop(0)
                if isinstance(step, BaseException):
                    raise step
                return step
            if not queue:
                raise Stop()
            step = queue.pop(0)
            if isinstance(step, BaseException):
                raise step
            return step

        fake_time = types.SimpleNamespace(time=lambda: self.NOW, sleep=sleeps.append)
        out = io.StringIO()
        with mock.patch.object(self.wi, "fetch", side_effect=fake_fetch), mock.patch.object(self.wi, "time", fake_time), contextlib.redirect_stdout(out):
            with self.assertRaises(Stop):
                self.wi.main()
        return out.getvalue(), sleeps

    def test_relevant_keeps_operator_issues_and_skips_pull_requests_and_bot_issues(self):
        wi = self.wi
        self.assertTrue(wi.relevant(issue(1, labels=["텔레그램수신"])))
        self.assertTrue(wi.relevant(issue(2, labels=["운영자응답"])))
        self.assertTrue(wi.relevant(issue(3, login=wi.OPERATOR)))
        self.assertFalse(wi.relevant(issue(4, login="github-actions[bot]", labels=["bug"])))
        self.assertFalse(wi.relevant(issue(5, login=wi.OPERATOR, pull_request=True)))        # 소유자가 올린 PR 도 이슈 감시의 대상이 아니다
        self.assertFalse(wi.relevant({"number": 6}))                                          # 칸이 없어도 예외 없이 거짓
        self.assertFalse(wi.relevant({"number": 7, "user": None, "labels": []}))

    def test_line_is_one_short_line_without_the_body(self):
        wi = self.wi
        text = wi.line(issue(12, login="shine88pc", labels=["텔레그램수신", "x"], title="  [요청]\n   제목   " + "가" * 100))
        self.assertEqual(len(text.splitlines()), 1)
        self.assertTrue(text.startswith("[새 이슈] #12 [요청] 제목 "))
        shown_title = text.split(" | ")[0].split("#12 ", 1)[1]
        self.assertEqual(len(shown_title), 80)
        self.assertIn("| 작성 shine88pc | 라벨 텔레그램수신,x | 11-15 10:02 KST", text)
        self.assertIn("라벨 없음", wi.line(issue(13)))
        self.assertIn("작성 ?", wi.line({"number": 14, "title": "t", "created_at": "2026-11-15T01:02:03Z"}))
        self.assertNotIn("body", text)

    def test_fetch_sends_an_etag_without_credentials_and_treats_304_as_no_change(self):
        wi = self.wi
        seen = []

        def fake_urlopen(req, timeout=None):
            seen.append(req)
            return FakeResponse(b'[{"number": 1}]', "etag-2")

        with mock.patch.object(wi.urllib.request, "urlopen", fake_urlopen):
            etag, items = wi.fetch("etag-1")
        self.assertEqual((etag, items), ("etag-2", [{"number": 1}]))
        headers = {key.lower(): value for key, value in seen[0].header_items()}
        self.assertEqual(headers["if-none-match"], "etag-1")
        self.assertNotIn("authorization", headers)                                            # 비밀·토큰 없이 공개 REST 만
        self.assertTrue(seen[0].full_url.startswith("https://api.github.com/repos/"))
        self.assertIn("state=open", seen[0].full_url)
        with mock.patch.object(wi.urllib.request, "urlopen", side_effect=http_error(304)):
            self.assertEqual(wi.fetch("etag-9"), ("etag-9", None))
        with mock.patch.object(wi.urllib.request, "urlopen", side_effect=http_error(500)):
            with self.assertRaises(urllib.error.HTTPError):
                wi.fetch("etag-9")

    def test_the_loop_prints_only_new_operator_issues_and_waits_ten_minutes_between_reads(self):
        out, sleeps = self.run_watch([
            ("e1", [issue(10), issue(9)]),
            ("e2", [issue(12, login="stranger"), issue(11, labels=["텔레그램수신"], login="bot"), issue(10)]),
            ("e2", None),
        ])
        lines = out.splitlines()
        self.assertEqual(lines[0], "이슈 감시 시작: 지금 최신 이슈 #10 (이후에 생기는 운영자 관련 이슈를 알립니다)")
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(lines[1].startswith("[새 이슈] #11 "))
        self.assertEqual(sleeps, [600, 600, 600])
        self.assertEqual(self.wi.INTERVAL, 600)

    def test_when_the_rate_limit_is_spent_it_rests_until_the_reset_time_between_one_and_fifteen_minutes(self):
        for header, expected in ((str(self.NOW + 500), 500), (str(self.NOW + 5000), 900), (str(self.NOW + 5), 60), (None, 60), ("not-a-number", 300)):
            headers = {} if header is None else {"X-RateLimit-Reset": header}
            for code in (403, 429):
                out, sleeps = self.run_watch([http_error(code, headers)])
                self.assertEqual(sleeps, [expected], (code, header))                         # 쉬고 바로 다시 읽는다(주기 대기를 더하지 않는다)
                self.assertEqual(out, "", (code, header))                                     # 쉬는 동안 알림 글을 찍지 않는다

    def test_a_failed_first_read_is_announced_once_and_retried(self):
        out, sleeps = self.run_watch([urllib.error.URLError("x"), urllib.error.URLError("y"), http_error(500), ("e1", [issue(5)])])
        lines = out.splitlines()
        self.assertEqual(lines[0], "이슈 감시: 첫 조회 실패(URLError) — 다시 시도합니다")
        self.assertEqual(lines[1], "이슈 감시 시작: 지금 최신 이슈 #5 (이후에 생기는 운영자 관련 이슈를 알립니다)")
        self.assertEqual(len(lines), 2, lines)                                                # 실패 알림은 한 번뿐
        self.assertEqual(sleeps, [600, 600, 600, 600])

    LIFETIME_STOP_AFTER = 20                                                                   # 가짜 쉼이 이만큼 넘게 불리면 끝 조건이 깨진 것 — 멈추지 않고 실패하게 한다
    LIFETIME_READS_MAX = 60                                                                    # 가짜 읽기가 이만큼 넘게 불려도 마찬가지(정상 실행의 읽기는 3주기×2곳=6번 안팎)

    def lifetime_run(self, fetch):
        """자기 종료 시험 공용: 가짜 시계(쉬면 그만큼 흐름)로 main() 이 **스스로 돌아오는지** 본다. 끝 조건이 깨져 반복이 이어지면 Stop 으로 끊고 실패시킨다(무한 루프·메모리 폭증 방지)."""
        clock, sleeps = [self.NOW], []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            clock[0] += seconds
            if len(sleeps) > self.LIFETIME_STOP_AFTER:
                raise Stop()

        fake_time = types.SimpleNamespace(time=lambda: clock[0], sleep=fake_sleep)
        out = io.StringIO()
        reads = [0]

        def counted_fetch(etag, url=None):
            reads[0] += 1
            if reads[0] > self.LIFETIME_READS_MAX:
                raise Stop()                                                                  # 쉬지 않고 계속 읽는 회귀(쉼 호출이 없어 쉼 횟수 가드가 못 잡는 모양)도 멈추지 않고 실패하게
            return fetch(clock, etag, url)

        with mock.patch.object(self.wi, "fetch", side_effect=counted_fetch), mock.patch.object(self.wi, "time", fake_time), contextlib.redirect_stdout(out):
            try:
                self.wi.main()
            except Stop:
                self.fail("끝 시각이 지나도 반복한다 — 자기 종료가 깨졌다(쉼 %d번·읽기 %d번 넘게)" % (self.LIFETIME_STOP_AFTER, self.LIFETIME_READS_MAX))
        return out.getvalue(), sleeps

    def test_the_loop_ends_by_itself_after_the_lifetime_so_it_cannot_become_an_orphan(self):
        """Monitor 를 다시 걸 때마다 이 프로세스가 고아로 남아 19개가 비인증 한도를 갉아먹은 사고(2026-11-23) 뒤 — 약 29분 뒤 스스로 끝난다(마지막 쉼은 남은 시간만큼으로 줄인다)."""
        out, sleeps = self.lifetime_run(lambda clock, etag, url: (etag, None))
        self.assertEqual(self.wi.LIFETIME, 1750)
        self.assertEqual(sleeps, [600, 600, 550])
        self.assertEqual(sum(sleeps), self.wi.LIFETIME)
        self.assertEqual(out, "")                                                                 # 끝 줄을 내지 않는다(Monitor 가 깨어나는 알림을 늘리지 않는다)

    def test_a_long_rest_for_the_issue_read_limit_is_cut_to_the_time_that_is_left(self):
        header = {"X-RateLimit-Reset": str(self.NOW + 5000)}                                       # 한 번에 900초(상한)씩 쉬려 한다

        def fetch(clock, etag, url):
            raise http_error(429, header)

        out, sleeps = self.lifetime_run(fetch)
        self.assertEqual(sleeps, [900, 850])                                                       # 둘째 쉼은 남은 850초로 줄어 끝에 맞는다
        self.assertEqual(out, "")

    def test_a_long_rest_for_the_comment_read_limit_is_cut_to_the_time_that_is_left_too(self):
        header = {"X-RateLimit-Reset": str(self.NOW + 5000)}

        def fetch(clock, etag, url):
            if url == self.wi.COMMENTS_URL:
                raise http_error(429, header)
            return etag, None                                                                      # 이슈 목록은 '변경 없음'

        out, sleeps = self.lifetime_run(fetch)
        self.assertEqual(sleeps, [900, 850])                                                       # 코멘트 쪽 쉼도 같은 규칙(끝 시각을 넘기지 않는다)
        self.assertEqual(out, "")

    def test_a_read_that_runs_past_the_end_time_never_asks_for_a_negative_rest(self):
        """읽는 데 오래 걸려 끝 시각을 넘긴 뒤의 쉼은 0 이다 — 음수로 부르면 실제 time.sleep 이 ValueError 로 프로세스를 죽인다."""
        def fetch(clock, etag, url):
            clock[0] += 2000                                                                       # 읽기가 끝 시각(1750초)을 넘겨 걸렸다
            return etag, None

        out, sleeps = self.lifetime_run(fetch)
        self.assertTrue(sleeps and min(sleeps) >= 0, sleeps)
        self.assertEqual(sleeps, [0])

    def test_the_documented_numbers_match_the_code(self):
        row = table_row(read(README), "watch_issues.py")
        for needle in ("600초(10분)", "이슈 코멘트", "시간당 12회", "304", "시간당 60회 한도에 센다", "2026-11-15 실측", "한도가 바닥나면(403·429)", "최소 60초·최대 15분", "1750초(약 29분) 뒤 스스로 끝난다"):
            self.assertIn(needle, row, needle)
        source = read(SCRATCH / "watch_issues.py")
        self.assertIn("max(60, min(900,", source)
        self.assertIn("2026-11-15 실측", source)
        self.assertEqual(3600 // self.wi.INTERVAL * 2, 12)                                    # 한 주기에 두 번(이슈·코멘트) 읽어 시간당 12회
        self.assertEqual(source.count("fetch("), 3)                                            # 정의 하나와 호출 둘 — 읽는 곳이 늘면 이 숫자와 README 를 함께 고친다


    def test_the_loop_also_announces_new_operator_comments_without_the_body(self):
        wi = self.wi

        def comment(number, login, issue_no):
            return {"id": number, "user": {"login": login}, "issue_url": f"https://api.invalid/repos/o/r/issues/{issue_no}", "created_at": "2026-11-17T01:02:03Z", "body": "CANARY_COMMENT_BODY"}

        out, sleeps = self.run_watch(
            [("e1", [issue(5)]), ("e2", None), ("e3", None)],
            [("c1", [comment(100, wi.OPERATOR, 7)]), ("c2", [comment(102, "stranger", 8), comment(101, wi.OPERATOR, 7), comment(100, wi.OPERATOR, 7)]), ("c2", None)])
        lines = out.splitlines()
        self.assertEqual(len(lines), 2, lines)                                                # 시작 한 줄 + 운영자 새 코멘트 한 줄(첫 읽기의 것·낯선 사람의 것은 알리지 않는다)
        self.assertTrue(lines[1].startswith(f"[새 코멘트] #7 | 작성 {wi.OPERATOR} | "), lines[1])
        self.assertIn("본문은 싣지 않음", lines[1])
        self.assertNotIn("CANARY", out)                                                       # 본문은 싣지 않는다
        self.assertEqual(sleeps, [600, 600, 600])

    def test_a_spent_rate_limit_on_the_comment_read_rests_like_the_issue_read(self):
        out, sleeps = self.run_watch([("e1", [issue(5)])], [http_error(429, {"X-RateLimit-Reset": str(self.NOW + 500)})])
        self.assertEqual(sleeps, [500])
        self.assertEqual(len(out.splitlines()), 1, out)                                       # 시작 줄뿐 — 쉬는 동안 알림 글을 찍지 않는다

    def test_fetch_reads_the_comment_list_with_the_same_etag_rule_and_no_credentials(self):
        wi = self.wi
        seen = []

        def fake_urlopen(req, timeout=None):
            seen.append(req)
            return FakeResponse(b"[]", "etag-c")

        with mock.patch.object(wi.urllib.request, "urlopen", fake_urlopen):
            self.assertEqual(wi.fetch("etag-0", wi.COMMENTS_URL), ("etag-c", []))
        headers = {key.lower(): value for key, value in seen[0].header_items()}
        self.assertEqual(headers["if-none-match"], "etag-0")
        self.assertNotIn("authorization", headers)
        self.assertTrue(seen[0].full_url.startswith("https://api.github.com/repos/") and "/issues/comments" in seen[0].full_url)


# ==== 6. resume_check — 비밀·경로를 찍지 않는다 ===============================================
class ResumeCheckTest(unittest.TestCase):
    def setUp(self):
        self.rc = load_tool(SCRATCH / "resume_check.py")

    def test_shown_masks_every_secret_shape_and_keeps_plain_text(self):
        for secret in (FAKE_GOOGLE_KEY, FAKE_GITHUB_TOKEN, FAKE_GITHUB_PAT, FAKE_KEY_VALUE, FAKE_TELEGRAM, "ya" + "29." + "CANARY_" + "y" * 24, "sec" + "ret=CANARY_zzzz", "KEY=CANARY_1"):
            masked = self.rc.shown("앞 " + secret + " 뒤")
            self.assertNotIn("CANARY", masked, secret[:10])
            self.assertEqual(masked, "앞 *** 뒤", secret[:10])
        for plain in ("[M073] 문서 정리", "monkey 설명", "tokenizer 설명", "https 주소 없음", "12345:abc"):
            self.assertEqual(self.rc.shown(plain), plain)

    def test_format_prs_and_issues_mask_titles_and_say_why_a_read_failed(self):
        rc = self.rc
        prs = [{"number": 7, "head": {"ref": "ai/claude/M073-x"}, "title": "[M073] " + FAKE_GITHUB_TOKEN + " 끝" + "x" * 80}]
        text = rc.format_prs(prs)
        self.assertIn("7", text)
        self.assertIn("ai/claude/M073-x", text)
        self.assertNotIn("CANARY", text)
        self.assertIn("***", text)
        self.assertEqual(rc.format_prs([]), "없음")
        self.assertEqual(rc.format_prs({"error": "HTTPError 403 " + FAKE_KEY_VALUE}), "읽기 실패(HTTPError 403 ***)")
        self.assertEqual(rc.format_prs("뜻밖의 값"), "읽기 실패(뜻밖의 값)")
        items = [issue(201, login="shine88pc", labels=["운영자응답"], title="[요청] " + FAKE_KEY_VALUE),
                 issue(202, pull_request=True), issue(203, login="stranger", title="낯선 이슈")] + [issue(300 + n) for n in range(12)]
        lines = rc.format_issues(items)
        self.assertEqual(len(lines), 8)                                                       # 기본 상한 여덟 줄
        self.assertIn("#201", lines[0])
        self.assertIn("소유자", lines[0])
        self.assertIn("11-15 01:02 UTC", lines[0])
        self.assertNotIn("CANARY", "\n".join(lines))
        self.assertTrue(all("#202" not in line for line in lines))                            # PR 은 건너뛴다
        self.assertIn("그 밖", lines[1])
        self.assertEqual(rc.format_issues([]), ["  (이슈 없음)"])
        self.assertEqual(rc.format_issues({"error": "URLError"}), ["  읽기 실패(URLError)"])

    def test_head_run_and_api_degrade_quietly_without_the_network(self):
        rc = self.rc
        with mock.patch.object(rc, "run", return_value="0123456789abcdef\trefs/heads/main") as run:
            self.assertEqual(rc.head("owner/repo"), "0123456")
        self.assertEqual(run.call_args[0][:2], ("git", "ls-remote"))
        with mock.patch.object(rc, "run", return_value=""):
            self.assertEqual(rc.head("owner/repo"), "?")
        with mock.patch.object(rc.subprocess, "run", side_effect=OSError("없음")):
            self.assertEqual(rc.run("git", "x"), "")
        fail = types.SimpleNamespace(returncode=1, stdout="경로가 섞인 오류 글")
        with mock.patch.object(rc.subprocess, "run", return_value=fail):
            self.assertEqual(rc.run("git", "x"), "")                                           # 실패하면 출력(경로가 섞일 수 있음)을 돌려주지 않는다
        seen = []

        def fake_urlopen(req, timeout=None):
            seen.append(req)
            return FakeResponse(b'[{"number": 1}]')

        with mock.patch.object(rc.urllib.request, "urlopen", fake_urlopen):
            self.assertEqual(rc.api("repos/o/r/pulls"), [{"number": 1}])
        self.assertTrue(seen[0].full_url.startswith("https://api.github.com/repos/o/r/pulls"))
        self.assertNotIn("authorization", {key.lower() for key, _value in seen[0].header_items()})
        with mock.patch.object(rc.urllib.request, "urlopen", side_effect=urllib.error.URLError("boom")):
            self.assertIn("URLError", rc.api("repos/o/r/pulls")["error"])

    def test_folder_state_names_a_missing_folder_and_reads_a_real_repository(self):
        rc = self.rc
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            self.assertIn("없음", rc.folder_state(Path(tmp) / "nothing"))
            self.assertIn("setup_workspace.py", rc.folder_state(Path(tmp) / "nothing"))
            repo = Path(tmp) / "repo"
            repo.mkdir()
            env = git_env()
            for args in (["init", "-q"], ["-c", "core.autocrlf=false", "commit", "--allow-empty", "-q", "-m", "첫 커밋 " + FAKE_KEY_VALUE]):
                subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)
            clean = rc.folder_state(repo)
            self.assertTrue(clean.endswith("| 깨끗"), clean)
            self.assertNotIn("CANARY", clean)                                                  # 커밋 제목의 비밀 모양도 가린다
            (repo / "x.txt").write_text("x", encoding="utf-8")
            self.assertTrue(rc.folder_state(repo).endswith("| 변경 1개"))

    def test_main_prints_only_public_information_and_never_the_work_folder_path(self):
        rc = self.rc
        prs = [{"number": 7, "head": {"ref": "ai/claude/M073-x"}, "title": "[M073] " + FAKE_GITHUB_TOKEN}]
        issues = [issue(201, login="shine88pc", labels=["운영자응답"], title="[요청] " + FAKE_KEY_VALUE), issue(202, pull_request=True)]

        def fake_api(path):
            return prs if "/pulls" in path else issues

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            work = Path(tmp) / "W"
            (work / "wt_r30").mkdir(parents=True)
            with mock.patch.object(rc, "head", return_value="abc1234"), mock.patch.object(rc, "api", side_effect=fake_api):
                code, out, err = capture(rc.main, ["--work", str(work)])
            self.assertEqual((code, err), (0, ""))
            for needle in ("지금:", "저장소 main 머리: 블로그 abc1234 | 데스크톱 abc1234 | 루트 abc1234", "요청 가지 머리: abc1234", "블로그 열린 PR:", "최근 이슈(최신순", "#201",
                           "다음 알림 번호: 건너뜀", "작업 폴더 wt_r30(요청 가지 작업 폴더): 없음", "작업 폴더 cd_repo(데스크톱 저장소): 없음"):
                self.assertIn(needle, out, needle)
            self.assertNotIn("CANARY", out)
            self.assertIn("***", out)
            for forbidden in (str(work), work.as_posix(), str(tmp), Path(tmp).as_posix()):
                self.assertNotIn(forbidden, out)
            for rx in FORBIDDEN_STRICT.values():                                              # 출력이 이 PC 의 사용자·고정 경로·비밀 모양을 담지 않는다
                self.assertIsNone(rx.search(out.replace(Path(tmp).as_posix(), "").replace(str(tmp), "")), rx.pattern[:20])

    def test_main_asks_the_number_tool_only_when_it_and_the_blog_clone_exist(self):
        rc = self.rc
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            work = Path(tmp) / "W"
            (work / "wt_r30" / ".git").mkdir(parents=True)
            (work / "next_notice_no.py").write_text("# 가짜\n", encoding="utf-8")
            calls = []

            def fake_run(*args, cwd=None):
                calls.append(args)
                if args[:2] == ("git", "-C") and "log" in args:
                    return "abc1234 첫 줄"
                if args[:2] == ("git", "-C") and "status" in args:
                    return ""
                return "P 다음 번호: P012 (가짜)"

            with mock.patch.object(rc, "head", return_value="?"), mock.patch.object(rc, "api", return_value={"error": "URLError x"}), mock.patch.object(rc, "run", fake_run):
                code, out, _err = capture(rc.main, ["--work", str(work)])
            self.assertEqual(code, 0)
            self.assertIn("P 다음 번호: P012 (가짜)", out)
            numbered = [call for call in calls if "next_notice_no.py" in " ".join(str(part) for part in call)]
            self.assertEqual(len(numbered), 1)
            self.assertEqual([part for part in numbered[0] if part.startswith("--")], ["--repo", "--dir", "--local"])
            self.assertIn("읽기 실패(URLError x)", out)
            self.assertIn("작업 폴더 wt_r30(요청 가지 작업 폴더): abc1234 첫 줄 | 깨끗", out)

    def test_the_default_work_folder_is_the_folder_above_the_scripts_folder(self):
        self.assertEqual(self.rc.HERE.parent, SCRATCH.parent)
        self.assertEqual(self.rc.HERE, SCRATCH)

    def test_main_without_a_work_option_reads_the_folders_next_to_the_scripts_folder(self):
        rc = self.rc
        seen = []

        def fake_state(folder):
            seen.append(Path(folder))
            return "없음"

        with mock.patch.object(rc, "head", return_value="abc1234"), mock.patch.object(rc, "api", return_value=[]), mock.patch.object(rc, "folder_state", fake_state):
            code, _out, _err = capture(rc.main, [])
            self.assertEqual(code, 0)
            self.assertEqual(seen, [SCRATCH.parent / "wt_r30", SCRATCH.parent / "cd_repo"])      # 고정 폴더가 아니라 스크립트 위치 기준
            seen.clear()
            capture(rc.main, [], work="어딘가")                                                    # 불러 쓰는 쪽이 키워드로 W 를 줄 수도 있다
            self.assertEqual(seen, [Path("어딘가") / "wt_r30", Path("어딘가") / "cd_repo"])
            seen.clear()
            capture(rc.main, ["--work", "다른곳"], work="어딘가")                                     # 명령줄 --work 가 이긴다
            self.assertEqual(seen, [Path("다른곳") / "wt_r30", Path("다른곳") / "cd_repo"])


# ==== 7. memfree — 기다림과 읽기 ==============================================================
class MemfreeTest(unittest.TestCase):
    def setUp(self):
        self.mf = load_tool(SCRATCH / "memfree.py")

    def test_meminfo_available_reads_memavailable_in_gigabytes(self):
        text = "MemTotal:       16384000 kB\nMemFree:         1024000 kB\nMemAvailable:    8388608 kB\nBuffers: 1 kB\n"
        self.assertEqual(self.mf.meminfo_available_gb(text), 8.0)
        for bad in ("", "MemTotal: 1 kB\n", "MemAvailable: abc kB\n", "MemAvailable:\n"):
            self.assertIsNone(self.mf.meminfo_available_gb(bad), bad)

    def test_wait_until_waits_in_steps_up_to_the_limit_and_never_waits_when_it_cannot_read(self):
        mf = self.mf
        sleeps = []
        reads = iter([0.1, 0.2, 0.9])
        self.assertEqual(mf.wait_until(0.6, read=lambda: next(reads), sleep=sleeps.append, limit=100, step=10), (0.9, 20))
        self.assertEqual(sleeps, [10, 10])
        sleeps.clear()
        self.assertEqual(mf.wait_until(0.6, read=lambda: 0.1, sleep=sleeps.append, limit=30, step=10), (0.1, 30))      # 끝내 모자라면 한도에서 멈춘다
        self.assertEqual(sleeps, [10, 10, 10])
        sleeps.clear()
        self.assertEqual(mf.wait_until(0.6, read=lambda: 2.0, sleep=sleeps.append), (2.0, 0))                           # 충분하면 기다리지 않는다
        self.assertEqual(mf.wait_until(0.0, read=lambda: 0.0, sleep=sleeps.append), (0.0, 0))
        self.assertEqual(mf.wait_until(0.6, read=lambda: None, sleep=sleeps.append), (None, 0))                         # 읽을 수 없는 환경은 기다리지 않는다
        self.assertEqual(sleeps, [])
        self.assertEqual((mf.WAIT_LIMIT_S, mf.STEP_S), (1800, 10))

    def test_main_prints_the_value_and_the_wait_or_unknown(self):
        mf = self.mf
        with mock.patch.object(mf, "wait_until", return_value=(3.14159, 20)) as wait:
            code, out, _err = capture(mf.main, ["0.5"])
        self.assertEqual((code, out), (0, "free_gb=3.14 waited_s=20\n"))
        self.assertEqual(wait.call_args[0], (0.5,))
        with mock.patch.object(mf, "wait_until", return_value=(None, 0)):
            self.assertEqual(capture(mf.main, [])[1], "free_gb=unknown waited_s=0\n")
        with mock.patch.object(mf, "wait_until", return_value=(1.0, 0)) as wait:
            capture(mf.main, [])
        self.assertEqual(wait.call_args[0], (0.0,))                                           # 최소값을 주지 않으면 기다리지 않는다

    def test_free_gb_is_a_positive_number_here_and_none_where_nothing_can_be_read(self):
        value = self.mf.free_gb()
        self.assertTrue(value is None or value > 0)
        stand_in = types.SimpleNamespace(name="posix")
        with mock.patch.object(self.mf, "os", stand_in), mock.patch("builtins.open", side_effect=OSError("없음")):
            self.assertIsNone(self.mf.free_gb())
        with mock.patch.object(self.mf, "os", stand_in), mock.patch("builtins.open", mock.mock_open(read_data="MemAvailable: 2097152 kB\n")):
            self.assertEqual(self.mf.free_gb(), 2.0)

    def test_the_documented_numbers_match(self):
        row = table_row(read(README), "memfree.py")
        for needle in ("최대 30분", "10초 간격", "free_gb=… waited_s=…", "free_gb=unknown", "윈도와 리눅스"):
            self.assertIn(needle, row, needle)


# ==== 8. check_notify — 공개 웹으로만, 끝나면 한 줄 ============================================
def run_page(*runs):
    """GitHub 워크플로 페이지의 내장 JSON 조각 — (실행 번호, id, 제목, 상태, 결론|None, 걸린 시간)."""
    parts = []
    for number, ident, title, status, conclusion, timing in runs:
        tail = "" if conclusion is None else ',"conclusion":"%s"' % conclusion
        parts.append('{"runNumber":%d,"id":"%s","title":"%s","status":"%s"%s,"timing":{"kind":"DURATION","text":"%s"}}' % (number, ident, title, status, tail, timing))
    return "<html>" + ",".join(parts) + "</html>"


DONE = "WORKFLOW_RUN_STATUS_COMPLETED"
RUNNING = "WORKFLOW_RUN_STATUS_IN_PROGRESS"
OK = "WORKFLOW_RUN_CONCLUSION_SUCCESS"


class CheckNotifyTest(unittest.TestCase):
    def setUp(self):
        self.cn = load_tool(SCRATCH / "check_notify.py")

    def test_find_run_picks_the_first_run_whose_title_has_the_tag(self):
        cn = self.cn
        page = run_page((310, "9001", "[R-210] 다른 요청", DONE, OK, "9s"), (311, "9002", "[R-211] 진행 현황", DONE, OK, "10s"), (312, "9003", "[R-211] 다시", RUNNING, None, "2s"))
        self.assertEqual(cn.find_run(page, "R-211"), ("9002", DONE, OK, "10s", "311"))
        self.assertEqual(cn.find_run(page, "R-210")[0], "9001")
        self.assertIsNone(cn.find_run(page, "R-999"))
        self.assertIsNone(cn.find_run("", "R-211"))
        running = cn.find_run(run_page((313, "9004", "[R-212] 진행", RUNNING, None, "1s")), "R-212")
        self.assertEqual(running, ("9004", RUNNING, None, "1s", "313"))

    def test_summary_line_drops_the_fixed_prefixes_and_cuts_the_notes(self):
        line = self.cn.summary_line(("9002", DONE, OK, "10s", "311"), "가" * 300)
        self.assertEqual(line, "run #311 COMPLETED SUCCESS 10s | annotations: " + "가" * 160)
        unfinished = self.cn.summary_line(("1", RUNNING, None, "", "5"), "")                  # 결론이 없어도 예외 없이 한 줄
        self.assertTrue(unfinished.startswith("run #5 IN_PROGRESS "), unfinished)
        self.assertTrue(unfinished.endswith("| annotations: "), unfinished)

    def test_annotations_are_read_from_the_public_partial_page_and_cleaned(self):
        html_text = "<div> Show more <span>검사 요약</span> &amp; 경고 없음 Show less</div> \"The ubuntu-latest label will migrate to 24\""
        with mock.patch.object(self.cn, "fetch", return_value=html_text) as fetch:
            self.assertEqual(self.cn.annotations("9002"), "검사 요약 & 경고 없음")
        self.assertIn("/actions/runs/9002/annotations_partial", fetch.call_args[0][0])
        self.assertTrue(fetch.call_args[1].get("ajax"))

    def test_fetch_returns_an_error_text_instead_of_raising(self):
        with mock.patch.object(self.cn.urllib.request, "urlopen", side_effect=OSError("x")):
            self.assertTrue(self.cn.fetch("https://example.invalid/").startswith("__ERR__ OSError"))
        with mock.patch.object(self.cn.urllib.request, "urlopen", return_value=FakeResponse("본문".encode("utf-8"))):
            self.assertEqual(self.cn.fetch("https://example.invalid/"), "본문")

    def run_main(self, pages, notes="notes ok", argv=("R-211",)):
        clock = {"t": 1000.0}
        calls = []
        state = {"i": 0}

        def fake_fetch(url, ajax=False, timeout=40):
            calls.append(url)
            if "annotations_partial" in url:
                return notes
            page = pages[min(state["i"], len(pages) - 1)]
            state["i"] += 1
            return page

        def sleep(seconds):
            clock["t"] += seconds

        with mock.patch.object(self.cn, "fetch", fake_fetch):
            code, out, _err = capture(self.cn.main, list(argv), now=lambda: clock["t"], sleep=sleep)
        return code, out, calls, clock["t"] - 1000.0

    def test_main_waits_until_the_run_is_complete_then_prints_one_line_using_no_rest_calls(self):
        pages = [run_page(), run_page((311, "9002", "[R-211] 진행", RUNNING, None, "1s")), run_page((311, "9002", "[R-211] 진행", DONE, OK, "9s"))]
        code, out, calls, waited = self.run_main(pages)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "run #311 COMPLETED SUCCESS 9s | annotations: notes ok")
        self.assertEqual(waited, 16)                                                          # 8초 간격으로 두 번 기다렸다
        self.assertTrue(all(url.startswith("https://github.com/") for url in calls))
        self.assertFalse(any("api.github.com" in url for url in calls))                       # REST 호출 0회
        self.assertTrue(any("/actions/workflows/ai-request.yml" in url for url in calls))

    def test_main_gives_up_after_the_wait_and_keeps_the_old_exit_code_zero(self):
        code, out, _calls, waited = self.run_main([run_page((1, "1", "[R-1] 다른", DONE, OK, "9s"))])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "아직 끝나지 않음: None")
        self.assertGreaterEqual(waited, self.cn.WAIT_SECONDS)
        self.assertEqual((self.cn.WAIT_SECONDS, self.cn.POLL_SECONDS), (110, 8))
        code, out, _calls, _waited = self.run_main([""], argv=())
        self.assertEqual(code, 2)
        self.assertIn("사용:", out)

    def test_the_documented_numbers_match(self):
        row = table_row(read(README), "check_notify.py")
        for needle in ("REST 호출 0회", "최대 110초", "8초마다", "8–11초", "읽기 전용"):
            self.assertIn(needle, row, needle)


# ==== 9. verify_live_counts — 읽기와 fetch 뿐 =================================================
class VerifyLiveCountsTest(unittest.TestCase):
    def setUp(self):
        self.vlc = load_tool(SCRATCH / "verify_live_counts.py")

    def test_paths_come_from_the_script_location_not_from_a_fixed_folder(self):
        self.assertEqual(self.vlc.HERE, SCRATCH)
        self.assertEqual(self.vlc.WORK, SCRATCH.parent)
        self.assertEqual(self.vlc.BLOG_REPO, SCRATCH.parent / "wt_r30")

    def test_expected_counts_default_and_override_in_order(self):
        vlc = self.vlc
        self.assertEqual(vlc.expected_counts([]), vlc.DEFAULT_COUNTS)
        self.assertEqual(vlc.DEFAULT_COUNTS, (38, 45, 38))
        self.assertEqual(vlc.expected_counts(["40"]), (40, 45, 38))
        self.assertEqual(vlc.expected_counts(["40", "50"]), (40, 50, 38))
        self.assertEqual(vlc.expected_counts(["40", "50", "41", "99"]), (40, 50, 41))

    def test_main_needs_the_branch_and_the_head_and_a_blog_clone(self):
        vlc = self.vlc
        code, out, _err = capture(vlc.main, ["only-one"])
        self.assertEqual(code, 2)
        self.assertIn("사용:", out)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            with mock.patch.object(vlc, "BLOG_REPO", Path(tmp) / "wt_r30"):
                code, out, _err = capture(vlc.main, ["ai/claude/M073-x", "abc1234"])
        self.assertEqual(code, 2)
        self.assertIn("setup_workspace.py", out)

    def test_main_reports_the_counts_from_fake_answers_and_only_fetches_and_reads(self):
        vlc = self.vlc
        git_calls = []

        def fake_git(*args):
            git_calls.append(args)
            answers = {("rev-parse", "--short=7", "origin/main"): "abc1234", ("log", "-1", "--format=%s", "origin/main"): "[M073] 제목", ("rev-list", "--count", "old1234..origin/main"): "1",
                       ("rev-parse", "origin/main^{tree}"): "t" * 40, ("rev-parse", "origin/ai/claude/M073-x^{tree}"): "t" * 40}
            return answers.get(args, "")

        pages = {"": (200, "<script>adsbygoogle</script>"), "posts.json": (200, '{"absoluteUrl":1}{"absoluteUrl":2}{"absoluteUrl":3}'),
                 "sitemap.xml": (200, "<loc>a</loc><loc>b</loc>"), "feed.xml": (200, "<item>1</item>" * 4)}
        runs = [{"name": "[공통] 저장소 규칙·테스트 자동 검사 · 정기", "status": "completed", "conclusion": "success"}]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            blog = Path(tmp) / "wt_r30"
            (blog / ".git").mkdir(parents=True)
            with mock.patch.object(vlc, "BLOG_REPO", blog), mock.patch.object(vlc, "git", fake_git), mock.patch.object(vlc, "get", side_effect=lambda path: pages[path]), \
                    mock.patch.object(vlc.wait_ci, "runs_for", return_value=runs) as runs_for:
                code, out, _err = capture(vlc.main, ["ai/claude/M073-x", "old1234", "3", "2", "4"])
        self.assertEqual(code, 0)
        for needle in ("main 머리 abc1234 [M073] 제목", "앞으로 간 커밋 수: 1 (기대 1)", "트리 일치: True", "adsbygoogle 줄 수: 1 (기준 1)", "posts.json 200 글 3 (기대 3)", "sitemap 200 주소 2 (기대 2)", "feed 200 항목 4 (기대 4)"):
            self.assertIn(needle, out, needle)
        self.assertEqual(runs_for.call_args[0], (vlc.BLOG, "main", "abc1234"))
        self.assertEqual(git_calls[0], ("fetch", "-q", "origin", "main", "ai/claude/M073-x"))
        self.assertEqual({call[0] for call in git_calls}, {"fetch", "rev-parse", "log", "rev-list"})       # 푸시·병합·체크아웃 없이 읽기와 fetch 뿐


# ==== 9-b. shadow_table(그림자 실행 결과 표)의 순수 함수와 watch_heads2.sh ===================
class ShadowTableTest(unittest.TestCase):
    def setUp(self):
        self.st = load_tool(SCRATCH / "shadow_table.py")

    def test_tables_reads_markdown_tables_and_skips_the_separator_row(self):
        md = "머리 글\n\n| 날짜 | 값 |\n|---|---:|\n| 11월 14일 | 12 |\n| 11월 13일 | 7 |\n\n끝\n| 둘째 | 표 |\n|:---:|:---:|\n| a | b |\n"
        self.assertEqual(self.st.tables(md), [[["날짜", "값"], ["11월 14일", "12"], ["11월 13일", "7"]], [["둘째", "표"], ["a", "b"]]])
        self.assertEqual(self.st.tables("표가 없는 글\n"), [])

    def test_num_reads_signed_numbers_with_the_unicode_minus_and_thousand_separators(self):
        minus = chr(0x2212)
        self.assertEqual(self.st.num("값 " + minus + "1,234.5 개"), -1234.5)
        self.assertEqual(self.st.num("+2"), 2.0)
        self.assertEqual(self.st.num("7"), 7.0)
        self.assertIsNone(self.st.num("없음"))
        self.assertEqual(self.st.MINUS, minus)

    def test_dates_months_means_and_tolerances(self):
        st = self.st
        self.assertEqual(st.kdate("2026년 11월 14일 맑음"), datetime.date(2026, 11, 14))
        self.assertIsNone(st.kdate("11월 14일"))
        self.assertEqual(st.kmonth("2026년 11월 평균"), (2026, 11))
        self.assertIsNone(st.kmonth("2026년 11월 14일"))                                       # 일까지 적힌 글은 월 표기가 아니다
        self.assertEqual(st.mean([1, 2, 6]), 3.0)
        self.assertAlmostEqual(st.tol("12.34"), 0.005, places=6)                               # 소수 둘째 자리까지 적힌 숫자는 반올림 오차 0.005
        self.assertAlmostEqual(st.tol("12"), 0.5, places=6)
        self.assertEqual(st.body_of("---\n제목: x\n---\n본문"), "본문")
        self.assertEqual(st.body_of("머리 글 없음"), "머리 글 없음")

    def test_the_summary_counts_matches_and_names_the_mismatches(self):
        checks = self.st.Checks()
        checks.add("원본", "a", True)
        checks.add("원본", "b", False, "기대 3 / 4")
        checks.add("내부", "c", True)
        self.assertEqual(checks.summary(), "원본 재계산 1/2 · 글 안 계산식 1/1 — 불일치: b(기대 3 / 4)")
        ok = self.st.Checks()
        ok.add("원본", "a", True)
        self.assertEqual(ok.summary(), "원본 재계산 1/1 — 모두 일치")


class WatchHeadsShellTest(unittest.TestCase):
    def test_the_script_ends_itself_and_only_reads_the_two_repositories_heads(self):
        text = read(SCRATCH / "watch_heads2.sh")
        self.assertTrue(text.startswith("#!/bin/bash"))
        self.assertIn("END=$((SECONDS+1750))", text)                                           # 스스로 끝난다(고아가 되어 GitHub 를 계속 부르지 않게)
        self.assertIn('while [ "$SECONDS" -lt "$END" ]', text)
        self.assertEqual(text.count("sleep 60"), 1)
        self.assertEqual(text.count("refs/heads/main"), 1)
        self.assertEqual(len(re.findall("https://github[.]com/[A-Za-z0-9-]+/[A-Za-z0-9-]+[.]git", text)), 2)         # 블로그·데스크톱 두 저장소
        self.assertNotIn("curl", text)
        self.assertNotIn("api.github.com", text)

    @unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "리눅스·맥에서만 bash -n 으로 문법을 본다")
    def test_the_script_has_no_shell_syntax_errors(self):
        done = subprocess.run(["bash", "-n", str(SCRATCH / "watch_heads2.sh")], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)


# ==== 10. 복사본이 작업 폴더 W 안에서 도는지 =================================================
def git_env():
    env = dict(os.environ)
    env.update(GIT_AUTHOR_NAME="Test Author", GIT_AUTHOR_EMAIL="author@example.invalid", GIT_COMMITTER_NAME="Test Author", GIT_COMMITTER_EMAIL="author@example.invalid",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    return env


def run_git(*args, cwd):
    """진짜 git 을 한 번 부르고 출력(앞뒤 공백 제거)을 돌려준다 — 로컬 임시 저장소에서만 쓴다(원격·네트워크 없음)."""
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=git_env(), check=True).stdout.strip()


def make_origin(folder, extra_branch=None):
    """푸시를 받지 않는 로컬 '원격' 저장소 — main 에 커밋 하나(HEAD 는 main), extra_branch 가 있으면 그 가지에 요청함 안내 커밋 하나를 더 둔다."""
    folder.mkdir(parents=True)
    run_git("init", "-q", cwd=folder)
    run_git("symbolic-ref", "HEAD", "refs/heads/main", cwd=folder)
    (folder / "README.md").write_text("기준\n", encoding="utf-8", newline="\n")
    run_git("add", "-A", cwd=folder)
    run_git("commit", "-q", "-m", "기준", cwd=folder)
    if extra_branch:
        run_git("checkout", "-q", "-b", extra_branch, cwd=folder)
        (folder / "인수인계" / "요청함").mkdir(parents=True)
        (folder / "인수인계" / "요청함" / "README.md").write_text("요청함 안내\n", encoding="utf-8", newline="\n")
        run_git("add", "-A", cwd=folder)
        run_git("commit", "-q", "-m", "요청 가지의 첫 커밋", cwd=folder)
        run_git("checkout", "-q", "main", cwd=folder)


def fake_branch_reader(output="", returncode=0, error=None):
    """setup_workspace.current_branch 가 부르는 하위 프로세스(subprocess.run) 자리에 끼우는 가짜 — 불린 (명령, 옵션)을 calls 에 적고 (출력, 종료 코드)를 돌려주거나 error 를 던진다."""
    calls = []

    def fake(command, **kwargs):
        calls.append((list(command), kwargs))
        if error is not None:
            raise error
        return types.SimpleNamespace(returncode=returncode, stdout=output, stderr="")

    return fake, calls


class SetupWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.setup = load_tool(SETUP)

    def run_main_with_existing_clones(self, reader):
        """블로그·데스크톱 clone 이 모두 이미 있는 W 에서 main 을 돌린다(clone 은 False, 하위 프로세스는 reader) → (setup.run 으로 부른 명령들, 출력, 블로그 clone 폴더)."""
        setup = self.setup
        commands = []
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            target = Path(tmp) / "W"
            with mock.patch.object(setup, "run", side_effect=lambda *args, cwd=None: commands.append((args, cwd))), mock.patch.object(setup, "clone", return_value=False), \
                    mock.patch.object(setup.subprocess, "run", reader), mock.patch.object(setup.shutil, "which", return_value="git"), mock.patch.object(sys, "argv", ["setup_workspace.py", str(target)]):
                _result, out, _err = capture(setup.main)
            return commands, out, target.resolve() / "wt_r30"

    def test_copy_tools_puts_every_file_where_the_readme_says_and_overwrites_a_stale_copy(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            target = Path(tmp) / "W"
            _result, out, _err = capture(self.setup.copy_tools, target)
            self.assertIn("도구·문서·양식 복사:", out)
            for source, rel in self.setup.plan_copy():
                self.assertEqual((target / rel).read_bytes(), source.read_bytes(), rel.as_posix())
            self.assertTrue((target / "scratch" / "watch_heads2.sh").is_file())
            self.assertTrue((target / "audit6" / "improve" / "LANE_RULES.md").is_file())
            self.assertEqual((target / "cron_status_prompt_v3.txt").read_bytes(), PROMPT_V3.read_bytes())
            self.assertTrue((target / "merge_request_template_v2.md").is_file() and (target / "progress_draft_template.md").is_file())
            (target / "scratch" / "merge_guard.py").write_text("낡은 사본\n", encoding="utf-8")
            capture(self.setup.copy_tools, target)
            self.assertEqual((target / "scratch" / "merge_guard.py").read_bytes(), (SCRATCH / "merge_guard.py").read_bytes())     # 저장소가 진실이다

    def test_the_copied_tools_find_the_work_folder_from_where_they_were_copied_to(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            target = Path(tmp) / "W"
            capture(self.setup.copy_tools, target)
            for name in ("resume_check", "verify_live_counts", "mk_lane_merge", "mk_lane_merge_desktop"):
                module = load_tool(target / "scratch" / f"{name}.py")
                self.assertEqual(module.HERE, (target / "scratch").resolve(), name)
                work = getattr(module, "WORK", module.HERE.parent)
                self.assertEqual(Path(work).resolve(), target.resolve(), name)
            lane = load_tool(target / "scratch" / "mk_lane_merge.py")
            self.assertEqual((Path(lane.REPO), Path(lane.COMMIT_TOOL)), (target.resolve() / "wt_r30", target.resolve() / "commit_as_author.py"))
            desktop = load_tool(target / "scratch" / "mk_lane_merge_desktop.py")
            self.assertEqual((Path(desktop.REPO), desktop.WT_PREFIX, lane.WT_PREFIX), (target.resolve() / "cd_repo", "cd_wt_", "wt_"))
            for path in sorted(target.rglob("*.py")):
                compile(path.read_text(encoding="utf-8"), str(path), "exec")                    # 복사본이 이 파이썬으로 읽힌다

    def test_no_clone_runs_from_a_fresh_checkout_with_no_network_and_no_git(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            target = Path(tmp) / "새 작업 폴더"
            done = subprocess.run([sys.executable, "-X", "utf8", str(SETUP), str(target), "--no-clone"], capture_output=True, text=True, encoding="utf-8", cwd=tmp,
                                  env=dict(os.environ, PATH=os.path.dirname(sys.executable)))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(done.stdout.startswith("도구·문서·양식 복사:"), done.stdout)
            self.assertEqual(len(done.stdout.splitlines()), 1)
            self.assertFalse((target / "wt_r30").exists() or (target / "cd_repo").exists())

    def test_the_clone_path_uses_the_current_request_branch_and_never_pushes(self):
        """방금 새로 clone 했을 때(clone 이 True)만 요청 가지로 전환한다 — fetch 뒤 checkout -B 순서이고 둘 다 블로그 clone 폴더 안에서 돈다."""
        setup = self.setup
        commands = []
        cloned = []

        def fake_clone(url, folder):
            cloned.append((url, folder.name))
            return True                                                                       # 방금 새로 만들었다

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            target = Path(tmp) / "W"
            with mock.patch.object(setup, "run", side_effect=lambda *args, cwd=None: commands.append((args, cwd))), \
                    mock.patch.object(setup, "clone", side_effect=fake_clone), \
                    mock.patch.object(setup.shutil, "which", return_value="git"), mock.patch.object(sys, "argv", ["setup_workspace.py", str(target)]):
                _result, out, _err = capture(setup.main)
            blog_folder = target.resolve() / "wt_r30"
        self.assertEqual([name for _url, name in cloned], ["wt_r30", "cd_repo"])
        self.assertTrue(all(url.startswith("https://github.com/") and url.endswith(".git") and "@" not in url for url, _name in cloned))   # 비밀 없는 공개 주소
        git = [args for args, _cwd in commands]
        self.assertEqual(git, [("git", "fetch", "origin"), ("git", "checkout", "-B", setup.REQUEST_BRANCH, "origin/" + setup.REQUEST_BRANCH)])      # 이 둘뿐 — 순서도 fetch 가 먼저
        self.assertEqual({Path(cwd) for _args, cwd in commands}, {blog_folder})
        self.assertFalse(any("push" in args for args in git))
        self.assertIn("요청 가지로 전환", out)
        self.assertNotIn("가지 전환 건너뜀", out)
        self.assertIn("다음:", out)
        for tool in ("scratch/resume_check.py", "cron_status_prompt_v3.txt", "watch_issues.py", "watch_heads2.sh"):
            self.assertIn(tool, out)

    def test_an_existing_blog_clone_is_neither_fetched_nor_switched(self):
        """필수-1(독립 검증): 이미 있는 wt_r30 에서 다시 돌리면 예전에는 `checkout -B` 가 요청 가지를 원격 머리로 되돌려 푸시 전 요청 커밋이 사라졌다 —
        이미 있는 clone 이면 fetch·checkout·reset 어떤 git 명령도 부르지 않고 건너뛴다고 알린다(새로 받는 데스크톱 저장소와는 따로 본다)."""
        setup = self.setup
        commands, cloned = [], []
        reader, reads = fake_branch_reader(setup.REQUEST_BRANCH + "\n")

        def fake_clone(url, folder):
            cloned.append(folder.name)
            return folder.name != "wt_r30"                                                    # 블로그 clone 은 이미 있고 데스크톱은 새로 받는다

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            target = Path(tmp) / "W"
            with mock.patch.object(setup, "run", side_effect=lambda *args, cwd=None: commands.append((args, cwd))), \
                    mock.patch.object(setup, "clone", side_effect=fake_clone), mock.patch.object(setup.subprocess, "run", reader), \
                    mock.patch.object(setup.shutil, "which", return_value="git"), mock.patch.object(sys, "argv", ["setup_workspace.py", str(target)]):
                _result, out, _err = capture(setup.main)
            blog_folder = target.resolve() / "wt_r30"
        self.assertEqual(cloned, ["wt_r30", "cd_repo"])
        self.assertEqual(commands, [], "이미 있는 clone 에는 어떤 git 명령도 부르지 않는다(fetch 도 checkout 도)")
        self.assertEqual([command for command, _options in reads], [["git", "-C", str(blog_folder), "rev-parse", "--abbrev-ref", "HEAD"]], "부른 것은 현재 가지를 읽는 읽기 전용 명령 하나뿐")
        self.assertIn("이미 있음 — 가지 전환 건너뜀", out)
        self.assertNotIn("요청 가지로 전환", out)
        self.assertIn("다음:", out)

    def test_a_workspace_with_both_clones_already_there_is_left_exactly_as_it_is(self):
        reader, reads = fake_branch_reader(self.setup.REQUEST_BRANCH + "\n")
        commands, out, _blog = self.run_main_with_existing_clones(reader)
        self.assertEqual(commands, [])
        self.assertEqual(len(reads), 1)                                                       # 읽기 전용 명령 하나(블로그 clone 의 현재 가지)뿐
        self.assertEqual(out.count("가지 전환 건너뜀"), 1)

    def test_an_existing_clone_on_the_request_branch_is_read_with_one_read_only_command_and_gets_no_advice(self):
        """권고-A(독립 재검증): 건너뛸 때 현재 가지를 읽기 전용 명령 하나로 알린다 — 요청 가지면 한 줄뿐이고 안내·경고가 없다."""
        setup = self.setup
        reader, reads = fake_branch_reader(setup.REQUEST_BRANCH + "\n")
        commands, out, blog = self.run_main_with_existing_clones(reader)
        self.assertEqual(commands, [])
        self.assertEqual([command for command, _options in reads], [["git", "-C", str(blog), "rev-parse", "--abbrev-ref", "HEAD"]])
        self.assertNotIn("shell", reads[0][1])
        self.assertEqual(reads[0][1]["timeout"], 60)                                          # git 이 멈춰도 무한정 기다리지 않는다
        self.assertIn("현재 가지: " + setup.REQUEST_BRANCH, out)
        for absent in ("checkout", "주의", "읽지 못했다", "분리된"):
            self.assertNotIn(absent, out, absent)
        self.assertIn("다음:", out)

    def test_an_existing_clone_on_another_branch_gets_the_one_line_command_to_switch_and_is_not_switched(self):
        """권고-A: 새 clone 은 됐는데 요청 가지로 못 옮긴 폴더(또는 손으로 main 에 받아 둔 폴더)를 다시 돌리면 현재 가지를 알리고 직접 옮기는 명령을 안내한다 — 자동으로 옮기지는 않는다."""
        setup = self.setup
        reader, reads = fake_branch_reader("main\n")
        commands, out, blog = self.run_main_with_existing_clones(reader)
        self.assertEqual(commands, [], "자동으로 옮기지 않는다 — 어떤 git 명령도 setup.run 으로 부르지 않는다")
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0][0], ["git", "-C", str(blog), "rev-parse", "--abbrev-ref", "HEAD"])
        self.assertEqual(reads[0][1]["timeout"], 60)
        self.assertIn("현재 가지: main", out)
        self.assertIn(f"푸시 전 변경이 없으면 `git -C {blog} checkout {setup.REQUEST_BRANCH}`", out)
        self.assertIn("자동으로 옮기지 않는다", out)
        self.assertEqual(out.count("checkout"), 1)                                            # 안내는 한 번 — 실행하지 않고 글로만
        self.assertNotIn("요청 가지로 전환", out)
        self.assertIn("다음:", out)

    def test_a_branch_that_cannot_be_read_is_said_loudly_and_does_not_stop_the_run(self):
        """권고-A·C: git 이 현재 가지를 못 읽으면(오류·빈 출력·git 이 안 뜸·시간 초과·커밋 없는 저장소의 HEAD+종료 코드 128) 크게 말하고(분리된 HEAD 는 따로 말한다) 죽지는 않는다 — 나머지(속보 자료·데스크톱 clone·다음 안내)는 계속 돈다."""
        cases = (
            ("git 오류(종료 코드 128)", dict(output="", returncode=128), "현재 가지: 읽지 못했다", "status"),
            ("종료 코드 128 인데 출력은 HEAD(커밋 없는 저장소)", dict(output="HEAD\n", returncode=128), "현재 가지: 읽지 못했다", "status"),
            ("출력이 비었다", dict(output="\n"), "현재 가지: 읽지 못했다", "status"),
            ("git 을 띄우지 못함", dict(error=OSError("없음")), "현재 가지: 읽지 못했다", "status"),
            ("시간 초과", dict(error=subprocess.TimeoutExpired("git", 60)), "현재 가지: 읽지 못했다", "status"),
            ("분리된 HEAD", dict(output="HEAD\n"), "현재 가지: 없음(분리된 HEAD)", "checkout"),
        )
        for label, options, said, advice in cases:
            with self.subTest(label):
                reader, reads = fake_branch_reader(**options)
                commands, out, _blog = self.run_main_with_existing_clones(reader)            # 예외 없이 끝까지 돈다
                self.assertEqual(commands, [])
                self.assertEqual(len(reads), 1)
                self.assertIn(said, out)
                if said.startswith("현재 가지: 읽지 못했다"):
                    self.assertIn("(git 오류·시간 초과·저장소가 아니거나 커밋이 없다)", out)          # 원인을 한 가지로 단정하지 않는다
                    self.assertNotIn("분리된", out)                                                # 종료 코드가 0 이 아니면 HEAD 가 찍혀도 분리된 HEAD 로 알리지 않는다
                else:
                    self.assertNotIn("읽지 못했다", out)
                self.assertIn("주의:", out)
                self.assertIn(advice, out)
                self.assertIn("다음:", out)

    def test_rerunning_in_a_real_workspace_with_unpushed_work_keeps_the_commit_and_the_files(self):
        """진짜 git(로컬 임시 저장소 둘 — 네트워크 없음)으로: 처음 실행은 clone·요청 가지 전환을 하고, 푸시 전 요청 커밋과 커밋 전 파일을 둔 뒤 다시 돌려도 그대로 남는다.
        (고치기 전 코드는 두 번째 실행의 `checkout -B` 가 가지를 원격 머리로 되돌려 커밋은 reflog 에만 남고 요청 파일은 작업 폴더에서 사라졌다.)"""
        setup = self.setup
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            blog, desktop, work = tmp / "blog-origin", tmp / "desktop-origin", tmp / "W"
            make_origin(blog, setup.REQUEST_BRANCH)
            make_origin(desktop)
            wt = work / "wt_r30"

            def run_setup():
                with mock.patch.object(setup, "BLOG", str(blog)), mock.patch.object(setup, "DESKTOP", str(desktop)), mock.patch.dict(os.environ, git_env()), \
                        mock.patch.object(sys, "argv", ["setup_workspace.py", str(work)]):
                    return capture(setup.main)[1]

            first = run_setup()
            self.assertIn("요청 가지로 전환", first)
            self.assertEqual(run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt), setup.REQUEST_BRANCH)
            self.assertTrue((wt / "인수인계" / "요청함" / "README.md").is_file())               # 요청 가지의 내용이 나왔다(기본 가지 main 에는 없다)
            self.assertTrue((work / "cd_repo" / ".git").exists())
            request_file = wt / "인수인계" / "요청함" / "R-900_unpushed.md"
            request_file.write_text("푸시 전 요청 파일\n", encoding="utf-8", newline="\n")
            run_git("add", "-A", cwd=wt)
            run_git("commit", "-q", "-m", "푸시 전 요청 커밋", cwd=wt)
            (wt / "memo.txt").write_text("커밋 전 메모\n", encoding="utf-8", newline="\n")
            before = run_git("rev-parse", "HEAD", cwd=wt)
            second = run_setup()
            self.assertEqual(run_git("rev-parse", "HEAD", cwd=wt), before, "다시 돌렸더니 푸시 전 커밋이 사라졌다")
            self.assertEqual(run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt), setup.REQUEST_BRANCH)
            self.assertEqual(request_file.read_text(encoding="utf-8"), "푸시 전 요청 파일\n")
            self.assertEqual((wt / "memo.txt").read_text(encoding="utf-8"), "커밋 전 메모\n")
            self.assertIn("이미 있음 — 가지 전환 건너뜀", second)
            self.assertNotIn("요청 가지로 전환", second)
            self.assertIn("현재 가지: " + setup.REQUEST_BRANCH, second)                          # 요청 가지 위라는 것만 알리고 경고·안내는 없다
            self.assertNotIn("주의", second)

    def test_current_branch_reads_a_real_repository_a_detached_head_and_something_that_is_not_a_repository(self):
        setup = self.setup
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            repo = tmp / "repo"
            make_origin(repo, setup.REQUEST_BRANCH)
            self.assertEqual(setup.current_branch(repo), "main")
            run_git("checkout", "-q", setup.REQUEST_BRANCH, cwd=repo)
            self.assertEqual(setup.current_branch(repo), setup.REQUEST_BRANCH)
            run_git("checkout", "-q", "--detach", cwd=repo)
            self.assertEqual(setup.current_branch(repo), "HEAD")                                 # 분리된 HEAD 는 가지 이름이 없다
            unborn = tmp / "unborn"
            unborn.mkdir()
            run_git("init", "-q", cwd=unborn)
            self.assertIsNone(setup.current_branch(unborn))                                      # 커밋이 없으면 git 은 HEAD 를 찍고 종료 코드 128 — 분리된 HEAD 로 잘못 알리면 안 된다
            plain = tmp / "plain"
            plain.mkdir()
            with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(tmp)}):             # 위 폴더의 저장소를 찾아 올라가지 않게 한다
                self.assertIsNone(setup.current_branch(plain))
            self.assertIsNone(setup.current_branch(tmp / "없는 폴더"))

    def test_a_clone_left_on_main_is_not_touched_says_so_and_the_advised_command_works(self):
        """권고-A: 손으로 main 에 받아 둔(복제가 도중에 끊겨 요청 가지로 못 옮긴 폴더도 같은 모양) wt_r30 를 다시 돌리면 예전 글은 종료 코드 0 과 '이미 있음' 뿐이었다 —
        이제는 현재 가지와 직접 옮기는 명령을 알린다. 가지·커밋·파일·reflog 는 그대로이고 안내한 명령은 실제로 먹는다(진짜 임시 git 저장소 둘 — 네트워크 없음)."""
        setup = self.setup
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            blog, desktop, work = tmp / "blog-origin", tmp / "desktop-origin", tmp / "W"
            make_origin(blog, setup.REQUEST_BRANCH)
            make_origin(desktop)
            wt = work / "wt_r30"

            def run_setup():
                with mock.patch.object(setup, "BLOG", str(blog)), mock.patch.object(setup, "DESKTOP", str(desktop)), mock.patch.dict(os.environ, git_env()), \
                        mock.patch.object(sys, "argv", ["setup_workspace.py", str(work)]):
                    return capture(setup.main)[1]

            run_setup()                                                                          # 새 W — 요청 가지로 전환됨
            run_git("checkout", "-q", "main", cwd=wt)                                            # 손으로 main 으로 옮긴 모양
            (wt / "main-work.txt").write_text("main 위의 푸시 전 작업\n", encoding="utf-8", newline="\n")
            run_git("add", "-A", cwd=wt)
            run_git("commit", "-q", "-m", "main 위의 푸시 전 커밋", cwd=wt)
            (wt / "memo.txt").write_text("커밋 전 메모\n", encoding="utf-8", newline="\n")

            def state():
                return (run_git("rev-parse", "HEAD", cwd=wt), run_git("branch", "--list", cwd=wt), run_git("reflog", cwd=wt))

            before = state()
            second = run_setup()
            self.assertEqual(state(), before, "읽기만 해야 한다 — 커밋·가지·reflog 가 그대로여야 한다")
            self.assertEqual(run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt), "main")
            self.assertEqual((wt / "main-work.txt").read_text(encoding="utf-8"), "main 위의 푸시 전 작업\n")
            self.assertEqual(run_git("status", "--porcelain", cwd=wt), "?? memo.txt")
            self.assertIn("이미 있음 — 가지 전환 건너뜀", second)
            self.assertIn("현재 가지: main", second)
            self.assertNotIn("요청 가지로 전환", second)
            found = re.search(r"푸시 전 변경이 없으면 `git -C (.+?) checkout " + re.escape(setup.REQUEST_BRANCH) + "`", second)
            self.assertIsNotNone(found, second)
            self.assertEqual(Path(found.group(1)).resolve(), wt.resolve())                       # 안내한 폴더가 바로 그 clone 이다
            run_git("-C", found.group(1), "checkout", setup.REQUEST_BRANCH, cwd=tmp)             # 안내한 명령 그대로 — 실제로 먹는다
            self.assertEqual(run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt), setup.REQUEST_BRANCH)
            self.assertEqual(run_git("log", "main", "-1", "--format=%s", cwd=wt), "main 위의 푸시 전 커밋")      # main 위 커밋은 main 에 그대로

    def test_the_documents_tell_the_truth_about_rerunning_in_an_existing_workspace(self):
        doc = self.setup.__doc__
        for needle in ("이미 clone 돼 있으면 clone 도 가지 전환도 하지 않고 그대로 둔다", "이미 만든 W 에서 다시 돌릴 때는 `--no-clone`", "푸시 전 요청 파일·커밋이 사라지지 않게",
                       "읽기 전용 `git rev-parse --abbrev-ref HEAD` 로 현재 가지를 한 줄 알리고", "직접 옮기는 명령을 안내한다(자동으로 옮기지 않는다)"):
            self.assertIn(needle, doc, needle)
        self.assertNotIn("이미 clone 돼 있으면 건너뛴다", doc)                                    # 가지 전환까지 건너뛴다는 오해를 부르던 옛 문장
        readme = read(README)
        s8 = section(readme, 8)
        prime = s8[s8.index("**②′ 번들 없이 시작할 때**"): s8.index("**③ 푸시 권한 점검**")]
        for needle in ("이미 만든 `<W>` 에서 다시 돌릴 때는 `--no-clone` 으로만 다시 돌립니다", "이미 있음 — 가지 전환 건너뜀", "푸시 전 요청 파일·커밋이 사라지지 않게",
                       "git -C <W>/wt_r30 status", "git -C <W>/wt_r30 pull --ff-only origin ai/claude/NO-MERGE-operator-requests",
                       "`현재 가지: …` 한 줄로 보입니다", "git -C <W>/wt_r30 checkout ai/claude/NO-MERGE-operator-requests", "자동으로 옮기지는 않습니다", "git -C <W>/wt_r30 fetch origin",
                       "**가지가 요청 가지인지 먼저 확인**", "git -C <W>/wt_r30 rev-parse --abbrev-ref HEAD", "다른 가지 위에서 `pull` 하면 그 가지가 요청 가지 머리로 빨리 감깁니다"):
            self.assertIn(needle, prime, needle)
        self.assertLess(prime.index("**가지가 요청 가지인지 먼저 확인**"), prime.index("git -C <W>/wt_r30 pull --ff-only"))      # pull 보다 가지 확인이 먼저 나온다
        last = s8[s8.index("**두 PC 를 동시에 가동하지 않습니다.**"):]
        for needle in ("이미 만든 `<W>` 는 지우거나 다시 만들지 말고", "`--no-clone` 으로만 다시 돌립니다"):
            self.assertIn(needle, last, needle)
        self.assertNotIn("이 순서를 처음부터 따르되 이미 끝난 단계는 건너뜁니다.", readme)           # 마침표로 끝나던 옛 문장(재실행을 권하는 꼴)은 고쳤다
        section_one = section(readme, 1)
        self.assertIn("이미 만든 `W` 를 다시 돌릴 때", section_one)
        self.assertIn("`--no-clone`", section_one)

    def test_main_without_the_folder_prints_the_usage_and_stops(self):
        with mock.patch.object(sys, "argv", ["setup_workspace.py"]):
            with self.assertRaises(SystemExit) as stop:
                self.setup.main()
        self.assertIn("사용:", str(stop.exception.code))

    def test_an_existing_clone_is_skipped_without_running_git(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            (Path(tmp) / ".git").mkdir()
            with mock.patch.object(self.setup, "run", side_effect=AssertionError("git 을 부르면 안 된다")):
                self.assertFalse(capture(self.setup.clone, "https://example.invalid/x.git", Path(tmp))[0])


def logic_dump(name):
    """도구 소스의 구조(독스트링을 뺀 AST) — 두 병합 가지 도구가 저장소 이름·작업 폴더 접두어만 빼고 같은 코드인지 견주는 데 쓴다."""
    tree = ast.parse(read(SCRATCH / name))
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
        tree.body = tree.body[1:]
    dump = ast.dump(tree)
    for old, new in (("'wt_r30'", "'<REPO>'"), ("'cd_repo'", "'<REPO>'"), ("'cd_wt_'", "'<PREFIX>'"), ("'wt_'", "'<PREFIX>'")):
        dump = dump.replace(old, new)
    return dump


class LaneMergeEndToEndTest(unittest.TestCase):
    """복사본(`W/scratch/mk_lane_merge.py`)을 W 안에서 진짜 git 으로 돌린다 — 로컬 임시 저장소뿐이고 원격에는 아무것도 올라가지 않는다."""

    def git(self, *args, cwd):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=self.env, check=True).stdout.strip()

    def build(self, tool="mk_lane_merge.py", clone_name="wt_r30"):
        """'원격' 저장소(main 한 커밋) · W/<clone_name>(그 clone 에 작업 가지 lane1 한 커밋) · W/scratch 의 도구 사본 · W 의 커밋 도구를 만든다."""
        tmp = Path(self._tmp.name)
        self.env = git_env()
        self.origin = origin = tmp / "origin"                                              # 푸시를 받지 않는 로컬 저장소 — 원격 구실만 한다(푸시하면 가지가 생겨 보인다)
        origin.mkdir()
        self.git("init", "-q", cwd=origin)
        self.git("symbolic-ref", "HEAD", "refs/heads/main", cwd=origin)
        (origin / "README.md").write_text("기준\n", encoding="utf-8", newline="\n")
        self.git("add", "-A", cwd=origin)
        self.git("commit", "-q", "-m", "기준", cwd=origin)
        work = tmp / "W"
        (work / "scratch").mkdir(parents=True)
        shutil.copy2(SCRATCH / tool, work / "scratch" / tool)
        shutil.copy2(WORK / "commit_as_author.py", work / "commit_as_author.py")
        self.git("clone", "-q", str(origin), str(work / clone_name), cwd=tmp)
        repo = work / clone_name
        self.git("checkout", "-q", "-b", "lane1", cwd=repo)
        (repo / "lane.txt").write_text("작업\n", encoding="utf-8", newline="\n")
        self.git("add", "-A", cwd=repo)
        self.git("commit", "-q", "-m", "작업 가지의 커밋", cwd=repo)
        (tmp / "msg.txt").write_text("[M900] 시험용 병합 가지 [대상: 공통]\n\n본문 한 줄\n", encoding="utf-8", newline="\n")
        return tmp, work, repo

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)

    def run_tool(self, tmp, work, tool, *args):
        return subprocess.run([sys.executable, "-X", "utf8", str(work / "scratch" / tool), *args], cwd=tmp, capture_output=True, text=True, encoding="utf-8", env=self.env)

    def test_the_two_tools_are_the_same_code_apart_from_the_repository_folder_and_the_prefix(self):
        self.assertEqual(logic_dump("mk_lane_merge.py"), logic_dump("mk_lane_merge_desktop.py"))
        self.assertNotEqual(read(SCRATCH / "mk_lane_merge.py"), read(SCRATCH / "mk_lane_merge_desktop.py"))

    def test_the_blog_tool_builds_a_one_commit_branch_in_a_new_work_folder_and_does_not_push(self):
        tmp, work, repo = self.build()
        usage = self.run_tool(tmp, work, "mk_lane_merge.py", "M903")                         # 인자가 모자라면 사용법을 끝 메시지로 하고 아무것도 만들지 않는다
        self.assertNotEqual(usage.returncode, 0)
        self.assertIn("사용:", usage.stderr)
        self.assertFalse((work / "wt_m903").exists())
        done = self.run_tool(tmp, work, "mk_lane_merge.py", "M900", "lane-test", "lane1", "msg.txt")                # 메시지 파일은 상대 경로여도 된다
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        wt = work / "wt_m900"
        self.assertTrue((wt / ".git").exists())
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt), "ai/claude/M900-lane-test")
        self.assertEqual(self.git("rev-list", "--count", "origin/main..HEAD", cwd=wt), "1")
        self.assertEqual(self.git("log", "-1", "--format=%an", cwd=wt), "강병수")                                         # 작성자 고정
        self.assertEqual(self.git("log", "-1", "--format=%s", cwd=wt), "[M900] 시험용 병합 가지 [대상: 공통]")
        self.assertEqual(self.git("rev-parse", "HEAD^{tree}", cwd=wt), self.git("rev-parse", "lane1^{tree}", cwd=repo))     # 트리는 작업 가지와 같다
        self.assertIn("lane 이 바꾼 경로 1개 중 병합 결과가 lane 머리와 다른 것 0개", done.stdout)
        self.assertIn("main 위 커밋 수: 1", done.stdout)
        self.assertEqual(self.git("for-each-ref", "--format=%(refname)", cwd=self.origin), "refs/heads/main")             # 원격 구실의 저장소에는 아무것도 올리지 않았다
        self.assertEqual(self.git("rev-parse", "origin/main", cwd=repo), self.git("rev-parse", "main", cwd=self.origin))
        self.assertEqual(self.git("branch", "--list", "ai/claude/M900-lane-test", cwd=repo).count("M900"), 1)

    def test_a_conflict_stops_the_tool_says_so_and_leaves_no_commit(self):
        tmp, work, repo = self.build()
        (repo / "README.md").write_text("작업 가지가 바꾼 줄\n", encoding="utf-8", newline="\n")
        self.git("add", "-A", cwd=repo)
        self.git("commit", "-q", "-m", "같은 줄을 바꿈", cwd=repo)
        (self.origin / "README.md").write_text("main 이 따로 바꾼 줄\n", encoding="utf-8", newline="\n")
        self.git("add", "-A", cwd=self.origin)
        self.git("commit", "-q", "-m", "main 이 먼저 바뀜", cwd=self.origin)
        done = self.run_tool(tmp, work, "mk_lane_merge.py", "M902", "conflict", "lane1", str(tmp / "msg.txt"))
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("충돌", done.stderr)
        self.assertIn("직접 해소하세요", done.stderr)
        self.assertEqual(self.git("rev-list", "--count", "origin/main..HEAD", cwd=work / "wt_m902"), "0")                  # 커밋은 만들지 않았다
        self.assertEqual(self.git("for-each-ref", "--format=%(refname)", cwd=self.origin), "refs/heads/main")

    def test_no_commit_keeps_the_changes_staged_and_the_desktop_copy_uses_its_own_folders(self):
        tmp, work, repo = self.build("mk_lane_merge_desktop.py", "cd_repo")
        done = self.run_tool(tmp, work, "mk_lane_merge_desktop.py", "M901", "lane-test", "lane1", str(tmp / "msg.txt"), "--no-commit")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        wt = work / "cd_wt_m901"
        self.assertTrue((wt / ".git").exists())
        self.assertFalse((work / "wt_m901").exists())
        self.assertIn("(--no-commit) 커밋하지 않음", done.stdout)
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=wt), self.git("rev-parse", "origin/main", cwd=repo))           # 커밋은 만들지 않았다
        self.assertEqual(self.git("diff", "--cached", "--name-only", cwd=wt), "lane.txt")
        self.assertEqual(self.git("for-each-ref", "--format=%(refname)", cwd=self.origin), "refs/heads/main")


class CommitAsAuthorTest(unittest.TestCase):
    def test_it_commits_as_the_fixed_author_with_a_utf8_message_and_only_adds_what_it_is_told(self):
        source = read(WORK / "commit_as_author.py")
        email = re.search('GIT_AUTHOR_EMAIL="([^"]+)"', source).group(1)
        env = git_env()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, env=env)
            (repo / "a.txt").write_text("a\n", encoding="utf-8", newline="\n")
            (repo / "b.txt").write_text("b\n", encoding="utf-8", newline="\n")
            message = Path(tmp) / "msg.txt"
            message.write_text("[WIP] 한글 제목\n\n본문\n\nCo-Authored-By: 시험 <test@example.invalid>\n", encoding="utf-8", newline="\n")
            done = subprocess.run([sys.executable, "-X", "utf8", str(WORK / "commit_as_author.py"), str(repo), str(message), "--only", "a.txt"], capture_output=True, text=True, encoding="utf-8", env=env)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            log = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%an|%ae|%cn|%ce|%s"], capture_output=True, text=True, encoding="utf-8", env=env, check=True).stdout.strip()
            self.assertEqual(log, f"강병수|{email}|강병수|{email}|[WIP] 한글 제목")
            status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, encoding="utf-8", env=env, check=True).stdout
            self.assertEqual(status.strip(), "?? b.txt")                                       # --only 에 없는 파일은 add 하지 않는다
            body = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%B"], capture_output=True, text=True, encoding="utf-8", env=env, check=True).stdout
            self.assertIn("Co-Authored-By: 시험", body)


# ==== 11. 안내 문서(README 8절·5절·3절)가 도구와 어긋나지 않는다 ===============================
class ReadmeFirstStartSectionTest(unittest.TestCase):
    def setUp(self):
        self.text = read(README)
        self.s8 = section(self.text, 8)

    def test_the_section_walks_through_the_steps_in_order_and_each_step_has_a_normal_and_a_not_normal_line(self):
        marks = ["**0. 프로그램 확인**", "**① 이관 번들 받기**", "**② 작업 폴더 만들기와 읽기 점검**", "**②′ 번들 없이 시작할 때**", "**③ 푸시 권한 점검**", "**④ 인수 신호와 첫 보고**", "**⑤ 크론과 감시기 켜기**"]
        positions = [self.s8.index(mark) for mark in marks]
        self.assertEqual(positions, sorted(positions))
        self.assertGreaterEqual(self.s8.count("이렇게 나오면 정상"), len(marks) + 1)         # 단계마다 하나씩(읽기 점검 하나 더)
        self.assertGreaterEqual(self.s8.count("- 아니면:"), len(marks) + 1)
        self.assertIn("두 PC 를 동시에 가동하지 않습니다", self.s8)

    def test_the_commands_are_the_ones_that_were_run_for_real(self):
        for needle in (
            "git clone --branch ai/claude/NO-MERGE-migration-bundle --single-branch <저장소 주소> <임시 폴더>",
            "py -3.12 -X utf8 bootstrap.py --work <W> --python <3.12 경로> --clone",
            "GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=false git -C <W>/wt_r30 push --dry-run --porcelain origin HEAD:refs/heads/ai/claude/preflight-test",
            '$env:GIT_TERMINAL_PROMPT = "0"; $env:GCM_INTERACTIVE = "false"; git -C <W>/wt_r30 push --dry-run --porcelain origin HEAD:refs/heads/ai/claude/preflight-test; Remove-Item Env:GIT_TERMINAL_PROMPT, Env:GCM_INTERACTIVE',
            "py -3.12 -X utf8 인수인계/도구/setup_workspace.py <W>",
            "py -3.12 -X utf8 <W>/scratch/resume_check.py --work <W>",
            "`could not read Username`", "종료 코드가 128", "종료 코드 0", "`[new branch]`", "Git Credential Manager",
            "`NEW_PC_ACK.json`", "`STARTED`", "`TOOK_OVER`", "제목에 `이관 완료` 를 넣고", "`HANDED_OVER`",
            "`7 * * * *`", "<W>/cron_status_prompt_v3.txt", "watch_heads2.sh", "watch_issues.py", "watch_light.py", "watch_desktop.py", "`READY_TO_HAND_OVER`", "`PREPARING`",
        ):
            self.assertIn(needle, self.s8, needle)

    def test_the_section_keeps_secrets_with_the_operator_and_shows_no_secret_or_link(self):
        for needle in ("AI 는 비밀번호·토큰을 입력하지 않으며", "설치와 GitHub 로그인은 운영자 몫", "절대 checkout·커밋하지 않습니다", "주소는 이 문서에 적지 않습니다"):
            self.assertIn(needle, self.s8, needle)
        self.assertNotIn("http", self.s8)
        self.assertNotIn("~", self.s8)
        self.assertEqual(problems(self.s8, FORBIDDEN_DOCS), [])

    def test_the_readme_has_no_ascii_tilde_no_web_address_and_no_template_marks(self):
        self.assertNotIn("~", self.text)
        self.assertIsNone(re.search("https?://", self.text))
        for mark in ("{{", "{%"):
            self.assertNotIn(mark, self.text)

    def test_every_table_row_has_as_many_columns_as_its_header(self):
        """GitHub 는 코드 안의 세로선도 칸을 가른다(이스케이프한 것만 예외) — 표 칸에 세로선을 쓰면 줄이 어긋나 렌더링이 깨진다."""
        pipe = re.compile(r"(?<!\\)\|")
        tables, block = 0, []

        def check(rows):
            nonlocal tables
            if len(rows) >= 2:
                tables += 1
                header = len(pipe.findall(rows[0][1]))
                for number, text in rows:
                    self.assertEqual(len(pipe.findall(text)), header, f"README {number}줄: 표 칸 수가 머리 줄과 다르다 — {text[:50]}")

        for number, text in enumerate(self.text.splitlines(), 1):
            if text.startswith("|"):
                block.append((number, text))
            else:
                check(block)
                block = []
        check(block)
        self.assertGreaterEqual(tables, 4)                                                    # 1절·2절·3절·7절 표를 훑었다

    def test_the_new_tools_are_described_with_their_limits(self):
        merge_guard = table_row(self.text, "merge_guard.py")
        for needle in ("**검사 전용**", "**판정만**", "병합·푸시 기능이 없고", "병합은 지금도 운영자만", "병합의 근거로 쓰지 않는다", "종료 코드 0 ELIGIBLE · 1 NOT ELIGIBLE · 2 사용법 오류"):
            self.assertIn(needle, merge_guard, needle)
        for stale in ("직접 병합하려면", "병합해도 된다", "ELIGIBLE 이면 병합"):
            self.assertNotIn(stale, merge_guard)
        read_only = next(line for line in self.text.splitlines() if line.startswith("**푸시 권한이 없는 환경에서 쓸 수 있는 도구**"))
        for needle in ("`resume_check.py`", "`verify_live_counts.py`", "`git fetch` 만", "푸시하지 않습니다", "`could not read Username`"):
            self.assertIn(needle, read_only, needle)
        lane = next(line for line in self.text.splitlines() if line.startswith("**로컬에 쓰기가 있는 도구(푸시는 하지 않음)**"))
        for needle in ("`mk_lane_merge.py`", "`mk_lane_merge_desktop.py`", "`W/wt_<m번호>`", "`W/cd_wt_<m번호>`", "푸시·병합 부탁은 하지 않습니다"):
            self.assertIn(needle, lane, needle)
        notes = next(line for line in self.text.splitlines() if line.startswith("**옮기지 않은 도구**"))
        for needle in ("`update_resume_block.py`", "`insert_resume_entry.py`", "`fill_final_guide.py`", "인수인계/작업내용.md", "§0-1", "`verify_pause.py`"):
            self.assertIn(needle, notes, needle)

    def test_the_documented_times_match_the_scripts(self):
        heads = read(SCRATCH / "watch_heads2.sh")
        self.assertIn("1750", heads)
        self.assertIn("sleep 60", heads)
        for name in ("watch_light.py", "watch_desktop.py"):
            self.assertIsNotNone(re.search(r"DEADLINE = time\.time\(\) \+ 29 \* 60", read(SCRATCH / name)), name)
        row = table_row(self.text, "watch_heads2.sh")
        for needle in ("60초 간격", "1750초(약 29분)", "스스로 끝난다", "`git ls-remote` 만"):
            self.assertIn(needle, row, needle)
        self.assertIn("한 번 켜면 29분 뒤 끝나므로", table_row(self.text, "watch_light.py"))
        self.assertIn("(38·45·38)", table_row(self.text, "verify_live_counts.py"))

    def test_the_cron_section_points_at_the_current_prompt_and_marks_the_old_summary(self):
        s5 = section(self.text, 5)
        for needle in ("정기_현황_알림_프롬프트_v3.txt", "2시간 주기", "110분 이상", "cron_status_prompt_v3.txt", "옛 판", "v3 맨 위 단락이 우선한다", "230분", "M004 발송"):
            self.assertIn(needle, s5, needle)
        v3 = read(PROMPT_V3)
        for needle in ("110분", "열린 PR", "병합 부탁", "progress_draft_template.md"):
            self.assertIn(needle, v3, needle)

    def test_every_command_is_given_for_a_shell_it_works_in(self):
        """권고-3(a): `VAR=값 명령`·`$(date +%s)` 은 PowerShell 에서 '용어를 인식할 수 없다' 로 실패한다 — 쓰려면 'Git Bash 에서' 라고 밝히고 PowerShell 형을 병기한다. WATCH_SINCE 는 어느 스크립트도 읽지 않는다."""
        self.assertNotIn("WATCH_SINCE", self.text)
        self.assertNotIn("$(", self.s8)
        bash_form = "GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=false git -C <W>/wt_r30 push --dry-run"
        self.assertEqual(len(re.findall(r"(?m)^[A-Z][A-Z_]*=\S+ ", self.s8)), 1)                  # `VAR=값 명령` 줄은 이 한 곳뿐이고
        self.assertEqual(re.findall(r"`[A-Z][A-Z_]*=\S+ [a-z]", self.s8), [])                      # 문장 속 코드로도 없다
        self.assertIn("Git Bash 에서", self.s8[: self.s8.index(bash_form)][-120:])                  # 그 줄 바로 앞에 쉘 이름을 밝혔다
        after = self.s8[self.s8.index(bash_form):]
        self.assertIn("PowerShell 에서", after[:600])
        self.assertIn('$env:GIT_TERMINAL_PROMPT = "0"; $env:GCM_INTERACTIVE = "false"; git -C <W>/wt_r30 push --dry-run', after[:900])
        self.assertIn("Remove-Item Env:GIT_TERMINAL_PROMPT, Env:GCM_INTERACTIVE", after[:900])      # 같은 창의 다음 명령에 환경 변수가 남지 않게 되돌린다
        self.assertIn("`$LASTEXITCODE`", self.s8)                                                    # PowerShell 의 종료 코드 보는 법
        row = table_row(self.text, "watch_light.py")
        self.assertNotIn("WATCH_SINCE", row)
        self.assertNotIn("&&", row)                                                                  # PowerShell 5.1 은 `&&` 도 모른다
        step = self.s8[self.s8.index("**⑤ 크론과 감시기 켜기**"):]
        for needle in ("py -3.12 -X utf8 -u <W>/scratch/watch_issues.py", "py -3.12 -X utf8 -u <W>/scratch/watch_light.py", "py -3.12 -X utf8 -u <W>/scratch/watch_desktop.py", "bash <W>/scratch/watch_heads2.sh"):
            self.assertIn(needle, step, needle)

    def test_no_command_in_the_first_start_section_uses_a_bare_python_and_each_python_command_carries_utf8(self):
        """권고-3(b)(f): 0단계가 '맨 python 은 쓰지 않는다' 고 하니 명령도 `py -3.12` 로 적고, 한글이 깨지지 않게 `-X utf8` 를 붙인다(파이프로 출력을 받을 때 특히)."""
        self.assertEqual([line for line in self.s8.splitlines() if re.match(r"\s*python3?\s", line)], [])
        self.assertEqual(re.findall(r"`(python3?\s[^`]*)`", self.s8), [])
        commands = re.findall(r"py -3\.1[02] ((?!--version)[^`\n]*)", self.s8)
        self.assertGreaterEqual(len(commands), 8)
        for command in commands:
            self.assertTrue(command.startswith("-X utf8"), command)
        self.assertIn("py -3.12 -X utf8 bootstrap.py --work <W> --python <3.12 경로> --clone", self.s8)
        self.assertIn("py -3.10 -X utf8 bootstrap.py", self.s8)                                      # 3.12 가 아직 없을 때의 길
        top = self.text[: self.text.index("## 1. ")]
        self.assertIn("맨 `python` 은 8절 0단계에서 확인한 3.12", top)                                   # 표의 `python` 이 무엇인지 첫머리에서 밝힌다
        one = section(self.text, 1)
        self.assertIn("py -3.12 -X utf8 인수인계/도구/setup_workspace.py <작업 폴더 W>", one)             # 1절의 첫 명령도 맨 python 이 아니다
        self.assertEqual([line for line in one.splitlines() if re.match(r"\s*python3?\s", line)], [])

    def test_the_first_signal_step_gives_the_exact_commit_command(self):
        """권고-3(c): `--only` 가 없으면 commit_as_author.py 는 `git add -A` 라 임시 폴더의 모든 변경이 들어간다 — 정확한 명령을 적는다."""
        step = self.s8[self.s8.index("1. **시작 신호**"): self.s8.index("2. **첫 보고**")]
        self.assertIn("py -3.12 -X utf8 <W>/commit_as_author.py <임시 폴더> <메시지 파일 절대 경로> --only 인수인계/이관_번들/state/NEW_PC_ACK.json", step)
        self.assertIn("`--only` 가 없으면 `git add -A`", step)
        self.assertIn("git -C <임시 폴더> push origin ai/claude/NO-MERGE-migration-bundle", step)

    def test_step_two_prime_names_where_the_clone_comes_from_and_that_it_is_the_main_way_once_the_bundle_is_gone(self):
        """권고-3(g): ②′ 는 새 세션이 시작된 저장소 clone(main) 에서 돌린다 — 번들이 정리되면 이 길이 정본이다."""
        head = self.s8[self.s8.index("**②′ 번들 없이 시작할 때**"):].splitlines()[0]
        for needle in ("새 세션이 시작된 저장소 clone(main)", "번들이 정리되면 이 길이 정본"):
            self.assertIn(needle, head, needle)

    def test_section_six_records_the_tar_and_the_crlf_mutation_traps(self):
        """권고-3(d): 윈도 `tar.exe` 는 한글 파일명을 못 풀고, CRLF 작업 폴더에서는 여러 줄 변이 도구가 SPEC INVALID 로 멈춘다 — 둘 다 함정 절에 한 줄씩."""
        s6 = section(self.text, 6)
        bullets = [line for line in s6.splitlines() if line.startswith("- ")]
        tar = [line for line in bullets if "tar.exe" in line]
        crlf = [line for line in bullets if "SPEC INVALID" in line]
        self.assertEqual((len(tar), len(crlf)), (1, 1))
        for needle in ("한글 파일명", "`git archive", "git -C <저장소> -c core.autocrlf=false worktree add --detach <새 폴더> <커밋>", "git -C <저장소> worktree remove <새 폴더>",
                       "`git -C <저장소> -c core.autocrlf=false archive --format=zip HEAD -o <파일>.zip`", "파이썬 `zipfile`", "한글 파일명이 맞게 풀립니다"):
            self.assertIn(needle, tar[0], needle)
        self.assertNotIn("`git worktree remove", tar[0])                                         # 저장소 폴더 밖에서 부르면 어느 저장소의 작업 폴더인지 모른다
        for needle in ("CRLF", "변이", "LF 로 체크아웃한 폴더", "`sha256`"):
            self.assertIn(needle, crlf[0], needle)

    def test_the_ci_web_row_does_not_contradict_the_web_runs_row(self):
        """권고-3(e): ci_web.py 가 읽던 내장 JSON 은 2026-11-05 에 사라졌다 — 표의 두 행이 같은 말을 한다."""
        ci_web = table_row(self.text, "ci_web.py")
        for needle in ("옛 판", "내장 JSON", "2026-11-05", "사라져", "`내장 JSON 을 찾지 못했다`", "`web_runs.py`"):
            self.assertIn(needle, ci_web, needle)
        self.assertNotIn("내장 JSON 만 읽어", ci_web)
        self.assertIn("2026-11-05", table_row(self.text, "web_runs.py"))

    def test_the_make_request_row_names_the_one_gate_exemption(self):
        """권고-2: 검사 관문의 면제는 자동 검사가 없는 루트 홈 저장소 한 곳뿐이다 — '초록이어야 파일이 만들어진다' 를 절대 규칙처럼 쓰지 않는다."""
        row = table_row(self.text, "make_request.py")
        for needle in ("예외 한 곳", "`shine88pc/shine88pc.github.io`", "루트 홈 저장소", "검사 실행이 하나도 없어도", "블로그·데스크톱 저장소는 예외가 없고", "실행이 하나라도 있으면 모두 초록",
                       "사람이 요청 본문에 적고", "`W/root_repo`", "머리 커밋 제목은 `W/root_repo` 에서 읽는다",
                       "실행 목록을 읽다가 실패해도", "네트워크 오류", "같은 이유로 통과시킨다", "어느 도구도 만들지 않으니", "`W/root_repo` 에 직접 clone 해 둔다"):
            self.assertIn(needle, row, needle)

    def test_the_limits_the_verifier_found_are_written_in_the_tool_rows(self):
        """정보-3·4·6: 고치지 않고 알려 두는 한계는 도구 표에 한 줄씩 적는다(코드는 바꾸지 않았다)."""
        merge_guard = table_row(self.text, "merge_guard.py")
        for needle in ("운영자 전용(C 등급) 경로 목록은 아직 정책 문서의 운영자 전용 목록과 같지 않다", "`privacy.md`", "`categories.md`", "`robots.txt`", "`posts.json`", "`pipeline/ai_processor_policy.json`",
                       "`pipeline/ops_inbox_policy.json`", "`pipeline/egress.py`", "`scripts/validate_repo.py`", "켜는 변경 전에 정책 문서와 맞춘다"):
            self.assertIn(needle, merge_guard, needle)
        resume = table_row(self.text, "resume_check.py")
        for needle in ("다음 알림 번호는 `git fetch` 전의 값일 수 있다", "낯선 작성자가 올린 이슈·PR 제목도 그대로 찍으니 데이터로만 읽고"):
            self.assertIn(needle, resume, needle)
        self.assertIn("네트워크가 실패해도 `아직 끝나지 않음: None`", table_row(self.text, "check_notify.py"))
        self.assertIn("30분이 지나도 모자라면", table_row(self.text, "memfree.py"))
        self.assertIn("종료 코드는 0", table_row(self.text, "memfree.py"))
        for name in ("commit_as_author.py", "make_info_request.py"):
            row = table_row(self.text, name)
            self.assertIn("인자가 모자라면 사용법 글이 아니라 파이썬 오류", row, name)

    def test_the_readme_lists_the_forms_and_the_old_two_documents_keep_their_names(self):
        s7 = section(self.text, 7)
        quoted = "AI 병합 기능이 꺼져 있어 운영자께서 직접 병합해 주세요"
        for needle in ("양식/merge_request_template_v2.md", "양식/progress_draft_template.md", quoted):
            self.assertIn(needle, s7, needle)
        forms = {path.name: read(path) for path in FORMS.glob("*.md")}
        self.assertEqual(set(forms), EXPECTED_FORMS)
        self.assertIn(quoted, forms["merge_request_template_v2.md"].replace("**", ""))                                    # README 가 인용한 문구는 양식의 실제 문구다


# ==== 12. make_merged_notice — 병합완료 확인 요청 파일 만들기의 동작(권고-1) ==================================
MERGE_FILE = "R-264_merge-m050.md"
MERGED_NAME = "R-265_merged-m050.md"
MERGE_REQUEST = """---
id: R-264
kind: merge
title: [M050] 병합 부탁 — 시험
summary: 병합 부탁입니다
created: 2026-11-12
no: M050
repo: shine88pc/chanceblog
target: 시험용 병합
pr_title: [M050] 시험용 병합 [대상: 공통]
verify: 검사 3칸 초록
---
본문
"""
GOOD_PAIRING = "def merged_pairing_problems(entries):\n    return []\n"


def fake_loop(labels='{"merged": "병합완료 확인", "merge": "병합 부탁"}', parse="    pass", pairing=GOOD_PAIRING, head=""):
    """가짜 `pipeline/operator_loop.py` 글 — make_merged_notice.VERIFY_SCRIPT 가 쓰는 이름(notify.REQUEST_KIND_LABELS·parse_request·RequestError·problem_text·merged_pairing_problems)만 흉내 낸다."""
    return head + (
        "class RequestError(Exception):\n"
        "    def __init__(self, code):\n"
        "        super().__init__(code)\n"
        "        self.code = code\n\n\n"
        "class _Notify:\n"
        f"    REQUEST_KIND_LABELS = {labels}\n\n\n"
        "notify = _Notify()\n\n\n"
        "class _Request:\n"
        '    kind = "merged"\n'
        '    no = "M050"\n'
        '    fields = (("result", "정상"),)\n'
        '    notice_error = ""\n\n\n'
        "def problem_text(code):\n"
        '    return "설명 " + code\n\n\n'
        "def parse_request(name, text, strict=False):\n"
        f"{parse}\n"
        "    return _Request()\n\n\n"
    ) + pairing


class MakeMergedNoticePureTest(unittest.TestCase):
    """순수 함수 — reason_problem(사유를 요청 파일·폰에 쓸 수 있는가)·decide_request_number(새 요청 번호)·build_text(파일 글)."""

    def setUp(self):
        self.mm = load_tool(WORK / "make_merged_notice.py", extra_path=WORK)

    def test_reason_problem_names_each_unusable_reason_on_its_own(self):
        problem = self.mm.reason_problem
        cases = (
            ("비어 있다", ("", "   ", None, 5)),
            ("앞뒤에 공백이 있다", (" 앞공백", "뒤공백 ", chr(0xA0) + "x")),
            ("U+000A", ("줄\n바꿈",)),
            ("U+0009", ("탭\t문자",)),
            ("U+200B", ("보이지" + chr(0x200B) + "않는 글자",)),
            ("같은 따옴표", ("\"따옴표로 감쌈\"", "'따옴표로 감쌈'")),
            ("물결표(~)가 있다", ("범위 3~5", "~", "앞~")),
            ("링크 주소가 있다", ("http://x.invalid/a", "https://x.invalid", "HTTPS://X.INVALID", "ftp://x.invalid", "tg://resolve", "www.example.invalid")),
            ("병합완료 확인", ("병합완료 확인 결과가 이상합니다", "병합완료확인", "병합 완료  확인", "[M050] 병합완료 확인 - 정상", "앞 병합완료" + chr(0xA0) + "확인 뒤")),
            ("비밀(키·토큰)", (FAKE_GOOGLE_KEY, FAKE_KEY_VALUE, "앞 " + FAKE_PEM + " 뒤")),
        )
        for needle, texts in cases:
            for text in texts:
                with self.subTest(needle=needle, text=str(text)[:20]):
                    found = problem(text, 100)
                    self.assertTrue(found, text)
                    self.assertIn(needle, found)

    def test_reason_problem_accepts_plain_reasons_up_to_the_limit_and_names_the_overflow(self):
        problem = self.mm.reason_problem
        for text in ("main 검사가 빨강입니다", "정상", "병합완료 뒤 사이트 빌드가 실패했습니다", "병합 확인 중 실패", "tokenizer 설명", "http 라는 낱말", "범위 3–5", "따옴표 하나\"만"):
            self.assertEqual(problem(text, 100), "", text)
        self.assertEqual(problem("가" * 100, 100), "")
        self.assertEqual(problem("가" * 60, 60), "")
        self.assertEqual(problem("가" * 101, 100), "101자라 100자를 넘는다")
        self.assertEqual(problem("가" * 61, 60), "61자라 60자를 넘는다")
        self.assertEqual((self.mm.SUMMARY_LIMITS, self.mm.RESULTS), ({"정상": 60, "이상": 100}, ("정상", "이상")))

    def test_decide_request_number_auto_takes_the_largest_of_the_folder_and_every_branch_plus_one(self):
        decide = self.mm.decide_request_number
        folder = [("R-250_merge-m050.md", ["merge"], ["M050"]), ("R-251_progress-p001.md", ["info"], ["P001"]), ("README.md", [], [])]
        refs = [("R-299_merge-m060.md", "origin/ai/claude/x", ["merge"], ["M060"])]
        self.assertEqual(decide("auto", folder, refs), ("R-300", "요청함 폴더와 모든 가지의 최댓값 R-299 + 1"))
        self.assertEqual(decide("auto", folder, []), ("R-252", "요청함 폴더와 모든 가지의 최댓값 R-251 + 1"))                  # 번호 칸이 없는 README.md 는 세지 않는다
        self.assertEqual(decide("auto", [], refs), ("R-300", "요청함 폴더와 모든 가지의 최댓값 R-299 + 1"))
        self.assertEqual(decide("auto", [], []), ("R-001", "요청함 폴더와 모든 가지의 최댓값 R-000 + 1"))
        self.assertEqual(decide("auto", [("R-998_x.md", [], [])], [])[0], "R-999")
        with self.assertRaises(self.mm.Refuse) as caught:
            decide("auto", [("R-999_x.md", [], [])], [])
        self.assertIn("상한(R-999)", str(caught.exception))

    def test_decide_request_number_checks_a_number_the_caller_gives(self):
        decide = self.mm.decide_request_number
        folder = [("R-250_merge-m050.md", ["merge"], ["M050"])]
        refs = [("R-299_merge-m060.md", "origin/ai/claude/x", ["merge"], ["M060"])]
        self.assertEqual(decide("R-300", folder, refs), ("R-300", "직접 준 번호(요청함 폴더와 모든 가지에 없음, 지금 최댓값 R-299)"))
        self.assertEqual(decide("R-001", folder, refs)[0], "R-001")
        for taken, where in (("R-250", "폴더"), ("R-299", "가지")):
            with self.subTest(where=where), self.assertRaises(self.mm.Refuse) as caught:
                decide(taken, folder, refs)
            self.assertIn("쓸 수 없다", str(caught.exception))
        for bad in ("R-30", "R-3000", "r-300", "300", "R-300 ", " R-300", "", "auto ", "AUTO", "R-3a0"):
            with self.subTest(bad=bad), self.assertRaises(self.mm.Refuse) as caught:
                decide(bad, folder, refs)
            self.assertIn("꼴이 아니다", str(caught.exception))
        with self.assertRaises(self.mm.Refuse) as caught:
            decide("R-000", folder, refs)
        self.assertIn("범위 밖", str(caught.exception))

    def test_build_text_is_exactly_the_seven_field_file_and_the_real_strict_reader_accepts_it(self):
        build = self.mm.build_text
        self.assertEqual(build("R-266", "M050", "정상", "정상", "2026-11-15"),
                         "---\nid: R-266\nkind: merged\ntitle: [M050] 병합완료 확인 - 정상\nsummary: 정상\ncreated: 2026-11-15\nno: M050\nresult: 정상\n---\n\n정상 — 병합이 제대로 됐습니다(폰에는 위 제목 한 줄만 갑니다).\n")
        self.assertEqual(build("R-266", "M051", "이상", "main 검사가 빨강입니다", "2026-11-15"),
                         "---\nid: R-266\nkind: merged\ntitle: [M051] 병합완료 확인 - 이상\nsummary: main 검사가 빨강입니다\ncreated: 2026-11-15\nno: M051\nresult: 이상\n---\n\n이상 — main 검사가 빨강입니다\n")
        self.assertEqual(self.mm.title_of("M050", "정상"), "[M050] 병합완료 확인 - 정상")
        for no, result, summary in (("M050", "정상", "정상"), ("M1234", "이상", "main 검사가 빨강입니다")):
            text = build("R-266", no, result, summary, "2026-11-15")
            self.assertNotIn("~", text)
            self.assertNotIn("\r", text)
            request = ol.parse_request(f"R-266_merged-{no.lower()}.md", text, strict=True)
            self.assertEqual((request.kind, request.no, request.title, dict(request.fields)), ("merged", no, f"[{no}] 병합완료 확인 - {result}", {"result": result, "summary": summary}))
            self.assertEqual(request.notice_error, "")

    def test_the_number_shapes_are_the_standard_notice_numbers_of_a_merge_request(self):
        for good in ("M001", "M050", "M999", "M1000", "M9999"):
            self.assertIsNotNone(self.mm.NO_RE.fullmatch(good), good)
        for bad in ("M50", "M0500", "M000", "M10000", "m050", "M 050", "P050", "050", "M-050", "M０５０"):
            self.assertIsNone(self.mm.NO_RE.fullmatch(bad), bad)
        self.assertEqual(self.mm.request_number("R-266_merged-m050.md"), 266)
        self.assertEqual(self.mm.request_number("README.md"), 0)
        self.assertEqual(self.mm.MAIN_FIRST, "요청 가지에 main 을 합치기 전입니다 — 먼저 합치세요")


class MakeMergedNoticeTest(unittest.TestCase):
    """make(...) — 검사를 모두 통과해야 파일을 쓴다. 거절하면 파일은 하나도 만들어지지 않는다(네트워크·git 없이 — repo=None, code_root=None)."""

    def setUp(self):
        self.mm = load_tool(WORK / "make_merged_notice.py", extra_path=WORK)
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.folder = self.tmp / "요청함"
        self.folder.mkdir()
        (self.folder / MERGE_FILE).write_text(MERGE_REQUEST, encoding="utf-8", newline="\n")

    def make(self, request="auto", no="M050", result="정상", reason=None, created="2026-11-15", code_root=None, repo=None, folder=None):
        return self.mm.make(request, no, result, reason, folder or self.folder, repo, created, code_root)

    def refuse(self, *args, **kwargs):
        with self.assertRaises(self.mm.Refuse) as caught:
            self.make(*args, **kwargs)
        return str(caught.exception)

    def names(self):
        return sorted(path.name for path in self.folder.iterdir())

    def test_a_normal_file_is_written_with_lf_and_the_run_is_described_line_by_line(self):
        target, lines = self.make()
        self.assertEqual(target, self.folder / MERGED_NAME)
        raw = target.read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertEqual(raw.decode("utf-8"), self.mm.build_text("R-265", "M050", "정상", "정상", "2026-11-15"))
        self.assertEqual(len(lines), 6)
        self.assertEqual(lines[0], f"파일 {MERGED_NAME} | 줄 수 {raw.count(bytes([10]))} | summary 2자")
        self.assertEqual(lines[1], f"짝 병합 부탁: {MERGE_FILE} (kind: merge, no: M050)")
        self.assertEqual(lines[2], "요청 번호: R-265 (요청함 폴더와 모든 가지의 최댓값 R-264 + 1)")
        self.assertEqual(lines[3], "제목: [M050] 병합완료 확인 - 정상")
        self.assertEqual(lines[4], "엄격하게 읽기 건너뜀(--no-verify — 시험 전용)")
        self.assertTrue(lines[5].startswith("다음: 이 파일만 따로 commit·push 한다"))
        self.assertEqual(self.names(), [MERGE_FILE, MERGED_NAME])

    def test_an_abnormal_file_carries_the_reason_and_a_given_request_number_is_used(self):
        target, lines = self.make(request="R-300", result="이상", reason="main 검사가 빨강입니다")
        self.assertEqual(target.name, "R-300_merged-m050.md")
        self.assertEqual(target.read_text(encoding="utf-8"), self.mm.build_text("R-300", "M050", "이상", "main 검사가 빨강입니다", "2026-11-15"))
        self.assertIn("직접 준 번호", lines[2])

    def test_a_normal_result_may_carry_a_short_reason_but_not_a_long_one(self):
        target, _lines = self.make(reason="가" * 60)
        self.assertIn("summary: " + "가" * 60 + "\n", target.read_text(encoding="utf-8"))
        folder = self.tmp / "요청함-둘째"
        folder.mkdir()
        (folder / MERGE_FILE).write_text(MERGE_REQUEST, encoding="utf-8", newline="\n")
        message = self.refuse(reason="가" * 61, folder=folder)
        self.assertIn("summary(사유) 를 쓸 수 없다", message)
        self.assertIn("61자라 60자를 넘는다", message)
        self.assertEqual(sorted(path.name for path in folder.iterdir()), [MERGE_FILE])

    def test_every_bad_input_is_refused_with_its_reason_and_nothing_is_written(self):
        cases = (
            ("M 번호 모양이 아니다", dict(no="M50")), ("M 번호 모양이 아니다", dict(no="M0500")), ("M 번호 모양이 아니다", dict(no="m050")), ("M 번호 모양이 아니다", dict(no="")),
            ("결과는 `정상` 또는 `이상` 이어야 한다", dict(result="OK")), ("결과는 `정상` 또는 `이상` 이어야 한다", dict(result="")),
            ("날짜 모양이 아니다", dict(created="2026/11/15")), ("날짜 모양이 아니다", dict(created="20261115")), ("없는 날짜다", dict(created="2026-13-40")), ("없는 날짜다", dict(created="2026-02-30")),
            ("사유 한 줄이 필요하다", dict(result="이상")), ("사유 한 줄이 필요하다", dict(result="이상", reason="   ")),
            ("summary(사유) 를 쓸 수 없다", dict(result="이상", reason="범위 3~5 가 이상")),
            ("물결표", dict(result="이상", reason="범위 3~5 가 이상")),
            ("링크 주소", dict(result="이상", reason="http://x.invalid 이 이상")),
            ("병합완료 확인", dict(result="이상", reason="병합완료 확인 결과 이상")),
            ("비밀(키·토큰)", dict(result="이상", reason="값 " + FAKE_GOOGLE_KEY)),
            ("꼴이 아니다", dict(request="R-26")), ("꼴이 아니다", dict(request="266")),
            ("범위 밖", dict(request="R-000")),
            ("쓸 수 없다", dict(request=MERGE_FILE[:5])),                                            # 요청함에 이미 있는 번호(R-264)
        )
        for needle, kwargs in cases:
            with self.subTest(needle=needle, kwargs=str(kwargs)[:40]):
                self.assertIn(needle, self.refuse(**kwargs))
                self.assertEqual(self.names(), [MERGE_FILE])
        message = self.refuse(folder=self.tmp / "없는폴더")
        self.assertIn("요청함 폴더가 없다", message)

    def test_a_file_is_made_only_when_exactly_one_pair_exists_and_no_twin_does(self):
        message = self.refuse(no="M051")                                                       # M051 짝 병합 부탁이 폴더에 없다
        self.assertIn("짝이 되는 병합 부탁(`kind: merge`, `no: M051`)이 요청함 폴더에 없다", message)
        self.assertIn("짝 없는 병합완료 확인은 만들지 않는다", message)
        self.assertEqual(self.names(), [MERGE_FILE])
        (self.folder / "R-270_progress-p001.md").write_text(MERGE_REQUEST.replace("kind: merge", "kind: info").replace("no: M050", "no: P001"), encoding="utf-8", newline="\n")
        self.assertIn("짝이 되는 병합 부탁", self.refuse(no="M051"))                                  # 종류가 다른 파일은 짝이 아니다
        (self.folder / "R-271_merge-m050-again.md").write_text(MERGE_REQUEST, encoding="utf-8", newline="\n")
        message = self.refuse()
        self.assertIn("`no: M050` 인 병합 부탁이 요청함 폴더에 둘 이상이다", message)
        self.assertIn(MERGE_FILE, message)
        self.assertNotIn(MERGED_NAME, self.names())
        (self.folder / "R-271_merge-m050-again.md").unlink()
        (self.folder / "R-272_merged-m050.md").write_text(self.mm.build_text("R-272", "M050", "정상", "정상", "2026-11-15"), encoding="utf-8", newline="\n")
        message = self.refuse()
        self.assertIn("M050 의 병합완료 확인이 이미 있다(R-272_merged-m050.md)", message)
        self.assertIn("둘째는 만들지 않는다", message)
        self.assertNotIn(MERGED_NAME, self.names())

    def test_a_file_that_cannot_be_read_as_a_request_does_not_count_and_does_not_crash(self):
        (self.folder / "R-266_broken-bytes.md").write_bytes(bytes([0xFF, 0xFE, 0x00, 0x80]))
        (self.folder / "README.md").write_text("안내\n", encoding="utf-8")
        (self.folder / "R-267_nokind.md").write_text("앞머리가 없는 글\n", encoding="utf-8")
        target, lines = self.make()
        self.assertEqual(target.name, "R-268_merged-m050.md")                                     # 읽지 못한 R-266 은 예외 없이 건너뛰고, 앞머리가 없는 R-267 은 번호만 센다(최댓값 + 1)
        self.assertEqual(lines[1], f"짝 병합 부탁: {MERGE_FILE} (kind: merge, no: M050)")

    def test_the_default_check_with_the_real_request_branch_code_reads_the_file_strictly(self):
        for result, reason in (("정상", None), ("이상", "main 검사가 빨강입니다")):
            folder = self.tmp / f"요청함-{result}"
            folder.mkdir()
            (folder / MERGE_FILE).write_text(MERGE_REQUEST, encoding="utf-8", newline="\n")
            target, lines = self.make(result=result, reason=reason, code_root=ROOT, folder=folder)
            self.assertEqual(lines[4], f"요청 가지 코드로 엄격하게 읽기({ROOT.name}): merged M050 {result} -")
            self.assertTrue(target.is_file())

    def test_a_code_folder_that_does_not_know_merged_stops_before_any_file_is_written(self):
        code = self.tmp / "code"
        (code / "pipeline").mkdir(parents=True)
        (code / "pipeline" / "__init__.py").write_text("", encoding="utf-8")
        (code / "pipeline" / "operator_loop.py").write_text(fake_loop(labels='{"merge": "병합 부탁"}'), encoding="utf-8", newline="\n")
        message = self.refuse(code_root=code)
        self.assertIn(self.mm.MAIN_FIRST, message)
        self.assertEqual(self.names(), [MERGE_FILE])
        (code / "pipeline" / "operator_loop.py").write_text(fake_loop(), encoding="utf-8", newline="\n")
        target, lines = self.make(code_root=code)
        self.assertEqual(lines[4], "요청 가지 코드로 엄격하게 읽기(code): merged M050 정상 -")
        self.assertTrue(target.is_file())


class VerifyWithTest(unittest.TestCase):
    """verify_with — 요청 가지 작업 폴더의 코드를 별도 프로세스로 불러 방금 만든 파일을 엄격하게 읽어 본다. 가짜 코드 폴더(가짜 pipeline/operator_loop.py)로 분기를 하나씩 본다."""

    def setUp(self):
        self.mm = load_tool(WORK / "make_merged_notice.py", extra_path=WORK)
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.folder = self.tmp / "요청함"
        self.folder.mkdir()
        (self.folder / MERGE_FILE).write_text(MERGE_REQUEST, encoding="utf-8", newline="\n")
        self.text = self.mm.build_text("R-265", "M050", "정상", "정상", "2026-11-15")

    def code_root(self, source=None):
        root = self.tmp / "code"
        (root / "pipeline").mkdir(parents=True, exist_ok=True)
        (root / "pipeline" / "__init__.py").write_text("", encoding="utf-8")
        if source is not None:
            (root / "pipeline" / "operator_loop.py").write_text(source, encoding="utf-8", newline="\n")
        return root

    def verify(self, source):
        return self.mm.verify_with(self.code_root(source), self.folder, MERGED_NAME, self.text)

    def refusal(self, source):
        with self.assertRaises(self.mm.Refuse) as caught:
            self.verify(source)
        return str(caught.exception)

    def test_a_good_reading_returns_what_the_request_branch_code_made_of_the_file(self):
        self.assertEqual(self.verify(fake_loop()), "merged M050 정상 -")

    def test_a_code_folder_without_the_loop_module_is_refused_before_anything_runs(self):
        with mock.patch.object(self.mm.subprocess, "run", side_effect=AssertionError("프로세스를 띄우면 안 된다")):
            message = self.refusal(None)
        self.assertIn("요청 가지 작업 폴더의 코드를 찾지 못했다", message)
        self.assertIn("--verify-with", message)

    def test_a_code_that_does_not_know_merged_stops_with_the_merge_main_first_message(self):
        for label, source in (("종류 이름표에 merged 가 없음", fake_loop(labels='{"merge": "병합 부탁"}')), ("짝 규칙 함수가 없음", fake_loop(pairing="")), ("종류 이름표가 아예 없음", fake_loop(labels="{}"))):
            message = self.refusal(source)
            self.assertIn(self.mm.MAIN_FIRST, message, label)
            self.assertIn("병합완료 확인 `kind: merged` 를 모른다", message, label)
            self.assertIn("알림이 조용히 사라진다", message, label)

    def test_a_file_the_strict_reader_refuses_stops_with_the_reason_code(self):
        message = self.refusal(fake_loop(parse='    if "merged-m050" in name:\n        raise RequestError("fake_parse")'))
        self.assertIn("엄격하게 읽지 못했다", message)
        self.assertIn("PARSE fake_parse 설명 fake_parse", message)
        self.assertNotIn(self.mm.MAIN_FIRST, message)

    def test_a_pairing_problem_stops_with_the_reason_code(self):
        message = self.refusal(fake_loop(pairing='def merged_pairing_problems(entries):\n    return [(name, "fake_pair") for name, _ in entries if "merged-m050" in name]\n'))
        self.assertIn("엄격하게 읽지 못했다", message)
        self.assertIn("PAIR fake_pair 설명 fake_pair", message)
        self.assertNotIn(self.mm.MAIN_FIRST, message)

    def test_problems_of_other_files_are_not_this_files_problems(self):
        parse_other = '    if "merge-m050" in name:\n        raise RequestError("fake_other")'
        pair_other = 'def merged_pairing_problems(entries):\n    return [(name, "fake_pair") for name, _ in entries if "merge-m050" in name]\n'
        self.assertEqual(self.verify(fake_loop(parse=parse_other)), "merged M050 정상 -")
        self.assertEqual(self.verify(fake_loop(pairing=pair_other)), "merged M050 정상 -")

    def test_the_existing_request_files_are_handed_to_the_pairing_rule_together_with_the_new_one(self):
        alone = 'def merged_pairing_problems(entries):\n    return [] if len(entries) == 2 else [(name, "fake_alone") for name, _ in entries]\n'
        self.assertEqual(self.verify(fake_loop(pairing=alone)), "merged M050 정상 -")             # 기존 병합 부탁 + 새 파일 = 둘
        (self.folder / MERGE_FILE).unlink()
        self.assertIn("PAIR fake_alone", self.refusal(fake_loop(pairing=alone)))                  # 기존 파일이 없으면 새 파일 하나뿐

    def test_an_unreadable_neighbour_and_a_non_request_file_are_skipped_not_fatal(self):
        (self.folder / "R-266_broken-bytes.md").write_bytes(bytes([0xFF, 0xFE, 0x00, 0x80]))
        (self.folder / "README.md").write_text("안내\n", encoding="utf-8")
        self.assertEqual(self.verify(fake_loop()), "merged M050 정상 -")

    def test_an_import_failure_in_the_code_is_a_refusal_with_the_error_not_a_crash(self):
        message = self.refusal(fake_loop(head='raise ImportError("boom")\n'))
        self.assertIn("엄격하게 읽지 못했다", message)
        self.assertIn("IMPORT ImportError: boom", message)
        self.assertNotIn(self.mm.MAIN_FIRST, message)

    def test_a_process_that_cannot_start_or_takes_too_long_is_a_refusal(self):
        for error in (OSError("없음"), subprocess.TimeoutExpired("x", 120)):
            with self.subTest(error=type(error).__name__), mock.patch.object(self.mm.subprocess, "run", side_effect=error):
                with self.assertRaises(self.mm.Refuse) as caught:
                    self.mm.verify_with(self.code_root(fake_loop()), self.folder, MERGED_NAME, self.text)
            self.assertIn(f"요청 가지 코드로 읽어 보지 못했다({type(error).__name__})", str(caught.exception))

    def test_the_code_runs_in_its_own_process_without_a_shell_from_the_code_folder_with_the_files_on_stdin(self):
        calls = []
        real_run = subprocess.run

        def spy(command, **kwargs):
            calls.append((command, kwargs))
            return real_run(command, **kwargs)

        with mock.patch.object(self.mm.subprocess, "run", spy):
            self.verify(fake_loop())
        self.assertEqual(len(calls), 1)
        command, kwargs = calls[0]
        self.assertEqual(command[:4], [sys.executable, "-X", "utf8", "-B"])
        self.assertNotIn("shell", kwargs)                                                         # 셸을 거치지 않는다
        self.assertEqual(kwargs["cwd"], str(self.tmp / "code"))
        self.assertEqual(kwargs["timeout"], 120)
        payload = json.loads(kwargs["input"].decode("utf-8"))
        self.assertEqual((payload["name"], payload["text"], sorted(payload["files"])), (MERGED_NAME, self.text, [MERGE_FILE]))


class MakeMergedNoticeMainTest(unittest.TestCase):
    """main — 명령 줄을 종료 코드(0 만들었다·1 만들지 않았다·2 사용법 오류)와 기본 폴더로 바꾼다."""

    def setUp(self):
        self.mm = load_tool(WORK / "make_merged_notice.py", extra_path=WORK)
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.work = self.tmp / "W"
        self.folder = self.work / "wt_r30" / "인수인계" / "요청함"
        self.folder.mkdir(parents=True)
        (self.folder / MERGE_FILE).write_text(MERGE_REQUEST, encoding="utf-8", newline="\n")
        self.argv = ["auto", "M050", "정상", "--repo", "none", "--no-verify", "--date", "2026-11-15"]

    def test_a_good_run_exits_zero_prints_the_lines_and_a_second_run_is_refused_on_stderr(self):
        code, out, err = capture(self.mm.main, self.argv, workspace=self.work)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual((self.folder / MERGED_NAME).read_text(encoding="utf-8"), self.mm.build_text("R-265", "M050", "정상", "정상", "2026-11-15"))
        self.assertIn("엄격하게 읽기 건너뜀(--no-verify — 시험 전용)", out)
        code, out, err = capture(self.mm.main, self.argv, workspace=self.work)
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("만들지 않았다: "), err)
        self.assertIn("이미 있다", err)

    def test_usage_errors_exit_two_and_the_two_check_options_exclude_each_other(self):
        for bad in ([], ["auto", "M050"], ["auto", "M050", "정상", "--no-verify", "--verify-with", "x"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
                self.mm.main(bad, workspace=self.work)
            self.assertEqual(stop.exception.code, 2, bad)
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), [MERGE_FILE])

    def test_the_strict_reading_is_on_by_default_and_looks_for_the_code_in_the_request_branch_work_folder(self):
        code, out, err = capture(self.mm.main, ["auto", "M050", "정상", "--repo", "none", "--date", "2026-11-15"], workspace=self.work)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("요청 가지 작업 폴더의 코드를 찾지 못했다", err)
        self.assertIn(str(self.work / "wt_r30"), err)                                              # 기본 코드 폴더는 W 아래 wt_r30
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), [MERGE_FILE])

    def test_options_choose_the_folder_the_repository_and_the_code_to_read_with(self):
        other = self.tmp / "다른 요청함"
        other.mkdir()
        (other / MERGE_FILE).write_text(MERGE_REQUEST, encoding="utf-8", newline="\n")
        code, _out, err = capture(self.mm.main, ["auto", "M050", "정상", "--folder", str(other), "--repo", "none", "--no-verify", "--date", "2026-11-15"], workspace=self.work)
        self.assertEqual((code, err), (0, ""))
        self.assertTrue((other / MERGED_NAME).is_file())
        self.assertFalse((self.folder / MERGED_NAME).exists())
        code, _out, err = capture(self.mm.main, ["auto", "M050", "정상", "--repo", str(self.tmp / "없는저장소"), "--no-verify"], workspace=self.work)
        self.assertEqual(code, 1)
        self.assertIn("git 저장소 폴더가 없다", err)
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.tmp.parent)}):                                              # 위 폴더의 저장소를 찾아 올라가지 않게 한다
            code, _out, err = capture(self.mm.main, ["auto", "M050", "정상", "--no-verify", "--date", "2026-11-15"], workspace=self.work)     # 기본 저장소 wt_r30 은 git 저장소가 아니다
        self.assertEqual(code, 1)
        self.assertIn("git 에서 가지의 요청 파일을 읽지 못했다", err)
        fake = self.tmp / "code"
        (fake / "pipeline").mkdir(parents=True)
        (fake / "pipeline" / "__init__.py").write_text("", encoding="utf-8")
        (fake / "pipeline" / "operator_loop.py").write_text(fake_loop(), encoding="utf-8", newline="\n")
        code, out, err = capture(self.mm.main, ["R-300", "M050", "이상", "main 검사가 빨강입니다", "--repo", "none", "--verify-with", str(fake), "--date", "2026-11-15"], workspace=self.work)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("요청 가지 코드로 엄격하게 읽기(code): merged M050 정상 -", out)
        self.assertTrue((self.folder / "R-300_merged-m050.md").is_file())


class MakeMergedNoticeGitTest(unittest.TestCase):
    """모든 가지의 요청함 파일을 읽는 부분(scan_refs)을 진짜 git(로컬 임시 저장소 — 네트워크 없음)으로 본다: 짝이 다른 가지에만 있을 때의 안내·다른 가지의 쌍둥이·가지를 넘는 번호.
    이 PC 는 git 한 번이 0.5초 안팎이라 저장소는 클래스에서 한 번만 만든다(가지 둘: 로컬 lane 에 병합 부탁, 원격 모양 ref 에 같은 번호의 병합완료 확인)."""

    REMOTE_REF = "refs/remotes/origin/ai/claude/NO-MERGE-operator-requests"
    REMOTE_NAME = "origin/ai/claude/NO-MERGE-operator-requests"
    TWIN_NAME = "R-270_merged-m050.md"

    @classmethod
    def setUpClass(cls):
        cls._shared = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(cls._shared.cleanup)
        cls.repo = Path(cls._shared.name) / "repo"
        make_origin(cls.repo)
        twin_text = "---\nid: R-270\nkind: merged\ntitle: [M050] 병합완료 확인 - 정상\nsummary: 정상\ncreated: 2026-11-15\nno: M050\nresult: 정상\n---\n\n정상\n"
        cls.commit_files("lane", {MERGE_FILE: MERGE_REQUEST})
        cls.commit_files("other", {cls.TWIN_NAME: twin_text}, ref=cls.REMOTE_REF)

    @classmethod
    def commit_files(cls, branch, files, ref=None):
        run_git("checkout", "-q", "-B", branch, "main", cwd=cls.repo)
        for name, text in files.items():
            path = cls.repo / "인수인계" / "요청함" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        run_git("add", "-A", cwd=cls.repo)
        run_git("commit", "-q", "-m", f"{branch} 의 요청 파일", cwd=cls.repo)
        if ref:
            run_git("update-ref", ref, "HEAD", cwd=cls.repo)
        run_git("checkout", "-q", "main", cwd=cls.repo)

    def setUp(self):
        self.mm = load_tool(WORK / "make_merged_notice.py", extra_path=WORK)
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name) / "요청함"
        self.folder.mkdir()

    def make(self, request="auto", no="M050"):
        return self.mm.make(request, no, "정상", None, self.folder, self.repo, "2026-11-15", None)

    def test_scan_refs_lists_every_branchs_request_files_with_their_kind_and_number(self):
        found = {(name, ref): (kinds, nos) for name, ref, kinds, nos in self.mm.scan_refs(self.repo)}
        self.assertEqual(found, {(MERGE_FILE, "heads/lane"): (["merge"], ["M050"]), (self.TWIN_NAME, self.REMOTE_NAME): (["merged"], ["M050"])})

    def test_a_pair_that_exists_only_on_another_branch_is_refused_with_a_hint_where_it_is(self):
        with self.assertRaises(self.mm.Refuse) as caught:
            self.make(no="M050")
        message = str(caught.exception)
        self.assertIn("짝이 되는 병합 부탁(`kind: merge`, `no: M050`)이 요청함 폴더에 없다", message)
        self.assertIn(f"다른 가지에는 있다: {MERGE_FILE} @ heads/lane", message)
        self.assertIn("요청 가지를 그 가지와 합친 뒤 다시 한다", message)
        self.assertEqual(list(self.folder.iterdir()), [])
        with self.assertRaises(self.mm.Refuse) as caught:
            self.make(no="M051")                                                                   # 어느 가지에도 짝이 없으면 안내 없이 거절한다
        self.assertNotIn("다른 가지에는 있다", str(caught.exception))

    def test_a_twin_on_another_branch_blocks_a_second_confirmation(self):
        (self.folder / MERGE_FILE).write_text(MERGE_REQUEST, encoding="utf-8", newline="\n")
        with self.assertRaises(self.mm.Refuse) as caught:
            self.make(no="M050")
        self.assertIn(f"M050 의 병합완료 확인이 이미 있다({self.TWIN_NAME} @ {self.REMOTE_NAME})", str(caught.exception))
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), [MERGE_FILE])

    def test_the_request_number_is_chosen_over_every_branch(self):
        (self.folder / "R-261_merge-m060.md").write_text(MERGE_REQUEST.replace("M050", "M060").replace("R-264", "R-261"), encoding="utf-8", newline="\n")
        with self.assertRaises(self.mm.Refuse) as caught:
            self.make(request="R-270", no="M060")                                                  # 다른 가지에 있는 요청 번호는 직접 줘도 못 쓴다
        self.assertIn("R-270 를 쓸 수 없다", str(caught.exception))
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), ["R-261_merge-m060.md"])
        target, lines = self.make(no="M060")
        self.assertEqual(target.name, "R-271_merged-m060.md")
        self.assertEqual(lines[2], "요청 번호: R-271 (요청함 폴더와 모든 가지의 최댓값 R-270 + 1)")


# ==== 13. make_request — 검사 관문의 면제(루트 홈 저장소 한 곳)와 물결표 거절(권고-2) ======================
ROOT_HOME_REPO = "shine88pc/shine88pc.github.io"
BLOG_REPO = "shine88pc/chanceblog"
DESKTOP_REPO = "shine88pc/chanceblog-desktop"
GATE_SHA = "c" * 40
INFO_DRAFT_TEXT = """---
id: R-198
kind: info
title: [R-198] 안내
summary: 안내입니다
urgency: 보통
created: 2026-11-06
---
시험: @TESTS@
"""


def gate_run(ident, conclusion="success", status="completed", name="[공통] 저장소 규칙·테스트 자동 검사", timing="2m 36s"):
    return {"id": ident, "name": name, "event": "push", "status": status, "conclusion": conclusion, "timing": timing}


class MakeRequestGateExemptionTest(unittest.TestCase):
    """검사 관문(default_gate)의 면제 집합은 자동 검사(워크플로)가 없는 루트 홈 저장소 한 곳뿐이다 — 블로그·데스크톱은 면제가 없고, 면제도 실행 목록이 비었을 때만이다."""

    def setUp(self):
        self.mr = load_tool(WORK / "make_request.py", extra_path=WORK)
        self.wc = load_tool(SCRATCH / "wait_ci.py")

    def gate(self, repo, runs=(), branch="main", remote=None, error=None):
        """default_gate 를 가짜 `git ls-remote`(remote: 출력 글, 기본은 머리 해시 한 줄)와 가짜 실행 목록 읽기로 부른다 → (돌려준 값, 멈춤 글·None, 출력, 읽기 가짜)."""
        remote = f"{GATE_SHA}\trefs/heads/{branch}\n" if remote is None else remote
        reader = mock.Mock(side_effect=error) if error is not None else mock.Mock(return_value=list(runs))
        out = io.StringIO()
        with mock.patch.dict(sys.modules, {"wait_ci": self.wc}), mock.patch.object(sys, "path", list(sys.path)), mock.patch.object(self.wc, "runs_for", reader), \
                mock.patch.object(self.mr.subprocess, "run", return_value=types.SimpleNamespace(stdout=remote, stderr="", returncode=0)), contextlib.redirect_stdout(out):
            try:
                result, message = self.mr.default_gate(f"{repo}:{branch}", WORK), None
            except SystemExit as stop:
                result, message = None, str(stop.code)
        return result, message, out.getvalue(), reader

    def test_the_exemption_set_is_exactly_the_root_home_repository(self):
        self.assertEqual(set(self.mr.NO_CI_REPOS), {ROOT_HOME_REPO})
        for repo in (BLOG_REPO, DESKTOP_REPO, "someone/else", "shine88pc/chanceblog-desktop-2"):
            self.assertNotIn(repo, self.mr.NO_CI_REPOS, repo)

    def test_the_root_home_repository_without_any_run_passes_with_an_empty_run_list(self):
        result, message, out, reader = self.gate(ROOT_HOME_REPO, runs=[])
        self.assertIsNone(message, message)
        self.assertEqual(result, (GATE_SHA, []))
        self.assertIn(f"검사 없는 저장소({ROOT_HOME_REPO}) — 자동 검사(워크플로)가 없어 관문을 면제한다: 가지 머리 {GATE_SHA[:8]}", out)
        self.assertIn("증거는 요청 본문에 사람이 적는다", out)
        reader.assert_called_once_with(ROOT_HOME_REPO, "main", GATE_SHA[:12])                      # 면제 전에 실행 목록을 읽어 본다
        self.assertNotIn("검사 관문 통과", out)

    def test_the_root_home_repository_whose_run_list_cannot_be_read_is_exempt_too(self):
        result, message, out, _reader = self.gate(ROOT_HOME_REPO, error=RuntimeError("목록을 읽을 수 없다"))
        self.assertIsNone(message, message)
        self.assertEqual(result, (GATE_SHA, []))
        self.assertIn("관문을 면제한다", out)

    def test_the_blog_and_the_desktop_repositories_are_never_exempt(self):
        for repo in (BLOG_REPO, DESKTOP_REPO):
            for label, kwargs in (("실행 목록이 비었다", dict(runs=[])), ("실행 목록을 읽지 못했다", dict(error=RuntimeError("읽기 실패")))):
                with self.subTest(repo=repo, label=label):
                    result, message, out, _reader = self.gate(repo, **kwargs)
                    self.assertIsNone(result)
                    self.assertIn("의 자동 검사 실행이 목록에 없다", message)
                    self.assertIn(GATE_SHA[:8], message)
                    self.assertNotIn("면제", out)

    def test_the_exemption_is_only_for_an_empty_list_so_real_runs_of_the_root_home_repository_still_have_to_be_green(self):
        result, message, out, _reader = self.gate(ROOT_HOME_REPO, runs=[gate_run(7, conclusion="failure")])
        self.assertIsNone(result)
        self.assertIn("검사가 아직 끝나지 않았거나 초록이 아니다", message)
        self.assertIn("7(completed/failure)", message)
        self.assertNotIn("면제", out)
        result, message, out, _reader = self.gate(ROOT_HOME_REPO, runs=[gate_run(8, status="in_progress", conclusion="")])
        self.assertIsNone(result)
        self.assertIn("8(in_progress/-)", message)
        runs = [gate_run(9), gate_run(10, timing="9s")]
        result, message, out, _reader = self.gate(ROOT_HOME_REPO, runs=runs)
        self.assertIsNone(message, message)
        self.assertEqual(result, (GATE_SHA, runs))
        self.assertIn("검사 관문 통과", out)
        self.assertNotIn("면제", out)

    def test_a_missing_remote_branch_stops_even_for_the_root_home_repository(self):
        result, message, _out, reader = self.gate(ROOT_HOME_REPO, remote="")
        self.assertIsNone(result)
        self.assertIn("원격에 브랜치가 없다", message)
        reader.assert_not_called()

    def test_each_repository_has_its_own_local_clone_folder_for_the_head_title(self):
        nt_module = load_tool(WORK / "notice_tools.py", extra_path=WORK)
        self.assertEqual(nt_module.repo_folder(ROOT_HOME_REPO), "root_repo")
        self.assertEqual(nt_module.repo_folder(BLOG_REPO), "wt_r30")
        self.assertEqual(nt_module.repo_folder(DESKTOP_REPO), "cd_repo")


class MakeRequestTildeTest(unittest.TestCase):
    """요청 파일에 물결표를 쓰지 않는다 — 마크다운(GFM)이 물결표 한 쌍을 취소선으로 처리해 '15–20·30–40' 같은 범위가 '1520·3040' 처럼 붙어 보인다(2026-11-09 운영자 지적)."""

    def setUp(self):
        self.mr = load_tool(WORK / "make_request.py", extra_path=WORK)
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name) / "W"
        self.folder = self.work / "wt_r30" / "인수인계" / "요청함"
        self.folder.mkdir(parents=True)
        (self.work / "draft.md").write_text(INFO_DRAFT_TEXT, encoding="utf-8", newline="\n")

    def run_main(self, tests):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                self.mr.main(["R-198", "note", "draft.md", tests, "", ""], workspace=self.work)
                code = None
            except SystemExit as stop:
                code = stop.code
        return code, out.getvalue()

    def test_check_draft_refuses_a_tilde_and_names_the_place_and_passes_the_en_dash(self):
        text = INFO_DRAFT_TEXT.replace("@TESTS@", "범위 15~20 입니다")
        with self.assertRaises(SystemExit) as stop:
            self.mr.check_draft(text, "R-198")
        message = str(stop.exception.code)
        self.assertIn("요청 파일에 물결표(~)를 쓰지 않는다", message)
        self.assertIn("범위 15~20 입니다"[:8], message)                                             # 어디쯤인지 앞뒤 12자를 보인다
        fields = self.mr.check_draft(INFO_DRAFT_TEXT.replace("@TESTS@", "범위 15–20 입니다"), "R-198")
        self.assertEqual((fields["id"], fields["kind"]), ("R-198", "info"))

    def test_a_tilde_anywhere_in_the_filled_draft_stops_the_run_and_no_file_is_made(self):
        code, _out = self.run_main("범위 15~20")                                                    # 명령 줄 인자로 들어온 물결표도 채운 뒤에 걸린다
        self.assertIsInstance(code, str)
        self.assertIn("물결표(~)", code)
        self.assertEqual(list(self.folder.iterdir()), [])
        (self.work / "draft.md").write_text(INFO_DRAFT_TEXT.replace("summary: 안내입니다", "summary: 30~40 안내"), encoding="utf-8", newline="\n")
        code, _out = self.run_main("시험 통과")
        self.assertIn("물결표(~)", code)
        self.assertEqual(list(self.folder.iterdir()), [])
        (self.work / "draft.md").write_text(INFO_DRAFT_TEXT, encoding="utf-8", newline="\n")
        code, out = self.run_main("범위 15–20")
        self.assertIsNone(code, code)
        self.assertEqual([path.name for path in self.folder.iterdir()], ["R-198_note.md"])
        self.assertIn("파일 R-198_note.md", out)

    def test_the_comment_beside_the_tilde_check_explains_in_words_why_digits_looked_glued(self):
        """en dash 로 고친 뒤 주석의 예시('15–20')가 '왜 숫자가 붙어 보였나' 와 어긋나 보였다 — 이유를 글로 풀어 쓴다(새 물결표를 만들지 않는다)."""
        found = re.search(r'^\s*if "' + chr(126) + r'" in text:\s*#\s*(.*)$', read(WORK / "make_request.py"), re.M)
        self.assertIsNotNone(found)
        comment = found.group(1)
        for needle in ("마크다운(GFM)이 물결표 한 쌍을 취소선으로 처리", "물결표로 범위를 쓴 두 곳", "숫자가 붙어 보였다", "확인 요청 006"):
            self.assertIn(needle, comment, needle)
        self.assertNotIn(chr(126), comment)
        self.assertIsNone(re.search("[0-9]" + chr(0x2013) + "[0-9]", comment), "en dash 예시는 '붙어 보인 이유' 설명과 어긋난다")

    def test_the_link_refusal_comes_before_the_tilde_one_and_both_are_plain_exits(self):
        with self.assertRaises(SystemExit) as stop:
            self.mr.check_draft(INFO_DRAFT_TEXT.replace("@TESTS@", "http://x.invalid ~"), "R-198")
        self.assertIn("링크 주소", str(stop.exception.code))


# ==== 14. 물결표 — 이 묶음이 새로 만든·고친 문서·프롬프트·양식·주석에 없다(권고-4) =========================
TILDE_TEXT_FILES = [README, PROMPT_V3, *FORMS.glob("*.md"), SCRATCH / "watch_heads2.sh"]
TILDE_PY_FILES = [WORK / "make_merged_notice.py", WORK / "make_request.py", SETUP, *SCRATCH.glob("*.py")]


def python_tilde_lines(source):
    """파이썬 소스에서 물결표가 있는 줄 번호 — 주석·독스트링은 모두 걸고, 그 밖의 글자 상수는 물결표를 '말하는' 것(물결표 한 글자만 든 비교 글자·`물결표(` 로 시작하는 설명 글)만 봐 준다."""
    tree = ast.parse(source)
    hits, docstrings = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body and isinstance(node.body[0], ast.Expr) \
                and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            doc = node.body[0].value
            docstrings.add(id(doc))
            hits.update(doc.lineno + offset for offset, line in enumerate(doc.value.splitlines()) if "~" in line)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings and "~" in node.value and node.value != "~" and "물결표(~)" not in node.value:
            hits.add(node.lineno)
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT and "~" in token.string:
            hits.add(token.start[0])
    return sorted(hits)


class NoAsciiTildeTest(unittest.TestCase):
    def test_the_new_documents_prompt_forms_and_script_have_no_ascii_tilde(self):
        self.assertGreaterEqual(len(TILDE_TEXT_FILES), 5)
        for path in TILDE_TEXT_FILES:
            lines = [number for number, line in enumerate(read(path).splitlines(), 1) if "~" in line]
            self.assertEqual(lines, [], f"{path.name}: 물결표가 있는 줄 — 범위는 en dash(–)로 쓴다")

    def test_the_lines_this_work_added_to_the_two_old_documents_have_none(self):
        for path in (PROMPT_OLD, MODEL_DOC):
            self.assertNotIn("~", read(path).splitlines()[0], path.name)

    def test_the_tool_sources_have_no_tilde_in_comments_or_docstrings_and_only_the_checks_name_it_in_strings(self):
        self.assertGreaterEqual(len(TILDE_PY_FILES), 20)
        for path in TILDE_PY_FILES:
            self.assertEqual(python_tilde_lines(read(path)), [], f"{path.name}: 주석·독스트링·글자 상수의 물결표")

    def test_the_two_prompt_numbers_that_had_tildes_use_the_en_dash(self):
        text = read(PROMPT_V3)
        self.assertIn("1–2분", text)
        self.assertIn("8–11초", text)

    def test_the_scanner_itself_catches_known_bad_samples_and_passes_the_checks_that_name_the_tilde(self):
        tilde = chr(126)
        bad = ("x = 1  # 범위 3" + tilde + "5\n", '"""독스트링 3' + tilde + '5"""\n', 'def f():\n    """둘째 줄에\n    3' + tilde + '5"""\n', 'message = "범위 3' + tilde + '5"\n', 'raise ValueError(f"`001`' + tilde + '`999` 꼴")\n')
        for source in bad:
            self.assertTrue(python_tilde_lines(source), source)
        good = ('if "' + tilde + '" in text:\n    pass\n', 'return "물결표(' + tilde + ')가 있다 — 이렇게 쓴다"\n', "x = chr(126)\n", "# 범위 3" + chr(0x2013) + "5\n", 'y = text.index("' + tilde + '")\n')
        for source in good:
            self.assertEqual(python_tilde_lines(source), [], source)


# ==== 15. egress 등록 이유 문장이 사실대로다(권고-5) ==============================================
def egress_entry(file, function):
    matches = [entry for entry in egress.EGRESS_EXCEPTIONS if (entry.file, entry.function) == (file, function)]
    assert len(matches) == 1, (file, function, len(matches))
    return matches[0]


class EgressReasonsAreTruthfulTest(unittest.TestCase):
    """등록 이유는 읽는 사람이 '이 지점이 무엇을 하는가' 를 믿고 넘어가는 문장이다 — 도구가 실제로 하는 일(불러 실행하는 코드·git 하위 명령·읽는 저장소)과 어긋나지 않게 못박는다. 항목의 개수·모양은 test_egress 와 정책 문서의 숫자가 지킨다."""

    def test_verify_with_says_it_runs_the_code_of_the_folder_it_is_given(self):
        reason = egress_entry("인수인계/도구/work/make_merged_notice.py", "verify_with").reason
        for needle in ("저장소 코드", "pipeline/operator_loop.py", "불러 실행", "믿는 작업 폴더만", "--verify-with", "네트워크를 쓰지 않는다"):
            self.assertIn(needle, reason, needle)

    def test_resume_check_run_names_every_command_it_really_starts(self):
        reason = egress_entry("인수인계/도구/work/scratch/resume_check.py", "run").reason
        for needle in ("git ls-remote", "git log", "git status", "next_notice_no.py"):
            self.assertIn(needle, reason, needle)
        source = read(SCRATCH / "resume_check.py")
        for command in ('"ls-remote"', '"log"', '"status"', "next_notice_no.py"):
            self.assertIn(command, source, command)                                              # 이유가 말하는 명령이 도구에 정말 있다

    def test_tools_that_take_a_repository_argument_say_which_one_is_the_default_and_that_other_public_repositories_can_be_read(self):
        for file, function, default in (("인수인계/도구/work/scratch/run_times.py", "<module>", "기본은 자기 저장소"), ("인수인계/도구/work/scratch/web_runs.py", "<module>", "기본은 자기 저장소"),
                                        ("인수인계/도구/work/scratch/wait_ci.py", "fetch", "첫 인자로 주며 보통 자기 저장소")):          # wait_ci 는 저장소 인자가 필수라 '기본' 이 없다
            reason = egress_entry(file, function).reason
            for needle in (default, "인자로 준 다른 공개 저장소도 읽는다", "사람이나 AI 세션이 실행"):
                self.assertIn(needle, reason, f"{file}: {needle}")
        for name in ("run_times.py", "web_runs.py", "wait_ci.py"):
            self.assertIn("sys.argv", read(SCRATCH / name), name)                                # 저장소를 인자로 받는다는 사실이 코드에 있다
        self.assertIn('"shine88pc/chanceblog"', read(SCRATCH / "run_times.py"))                  # 기본값이 자기 저장소라는 사실도 코드에 있다
        self.assertIn('"shine88pc/chanceblog"', read(SCRATCH / "web_runs.py"))

    def test_the_source_policy_document_calls_the_tools_what_the_tool_gate_text_calls_them(self):
        """docs/SOURCE_POLICY.md 7절은 '사람이 실행하는 도구' 라고 적었는데 등록 장부의 관문 문구는 AI 세션도 직접 실행한다고 고쳤다 — 두 곳이 같은 말을 한다(숫자 줄은 test_source_policy_docs 가 지킨다)."""
        phrase = "사람이나 AI 세션이 직접 실행하는 도구"
        self.assertIn(phrase, egress._G_TOOL)
        doc = read(ROOT / "docs" / "SOURCE_POLICY.md")
        self.assertIn(phrase + "(`인수인계/도구/`의 `urlopen`", doc)
        self.assertNotIn("사람이 실행하는 도구", doc)

    def test_the_tool_gate_text_does_not_claim_that_nothing_calls_the_tools_but_people(self):
        gate = egress._G_TOOL
        for needle in ("사람이나 AI 세션이 직접 실행하는 도구", "저장소의 워크플로·예약이 부르지 않는다", "AI 세션 안의 크론 프롬프트는 일부를 부른다"):
            self.assertIn(needle, gate, needle)
        self.assertNotIn("사람이 실행하는 도구(워크플로·예약이 부르지 않는다)", gate)
        tool_entries = [entry for entry in egress.EGRESS_EXCEPTIONS if entry.file.startswith("인수인계/도구/")]
        self.assertGreaterEqual(len([entry for entry in tool_entries if entry.gate == gate]), 20)  # 도구 항목의 관문 칸은 이 문구를 쓴다
        self.assertEqual([entry.function for entry in tool_entries if entry.gate.startswith("막는 장치 없음 — 사람") and entry.gate != gate], [])      # 옛 문구가 남은 항목이 없다
        prompt = read(PROMPT_V3)
        for name in ("web_runs.py", "run_times.py", "wait_ci.py"):
            self.assertIn(name, prompt, name)                                                    # 문구가 말하는 '크론 프롬프트가 부르는 도구' 가 실제로 프롬프트에 있다


# ==== 16. 이 PC 현행판 도구 사본(2026-11-23 MIG1) — 복사 목록·README 9절·스테이징 도구 ==============================
MIG1_NEW_ROOT = {"lowprio.py", "qt_lock.py"}
MIG1_NEW_DOCS = {"agent_common_rules.md", "operator_delegation_rules.md"}
MIG1_NEW_SCRATCH = {"badge_wait.sh", "build_blog_merge.py", "ci_main.py", "ci_wip_status.py", "combine_lanes_desktop.py", "jk_read.py", "keep_both.py", "lanes.py", "main_runs_wait.sh",
                    "mkverify.py", "note.sh", "pc_load.py", "prepush_check.sh", "rehearse.py", "run_modules.py", "squash_onto.py", "tools_stage.py", "memcopy_stage.py", "watch_all.sh"}
MIG1_NOT_COPIED = {"push_qtci.py", "qtci_wait.sh", "qtci_web.py"}


class MigrationCopiesTest(unittest.TestCase):
    def test_the_new_copies_are_in_the_repository_and_the_qt_runner_trio_is_not(self):
        self.assertLessEqual(MIG1_NEW_ROOT, {path.name for path in WORK.glob("*.py")})
        self.assertLessEqual(MIG1_NEW_DOCS, {path.name for path in WORK.glob("*.md")})
        self.assertLessEqual(MIG1_NEW_SCRATCH, {path.name for path in SCRATCH.iterdir() if path.is_file()})
        self.assertTrue((WORK / "audit6" / "improve" / "LANE_RULES.md").is_file())
        present = {path.name for path in TOOLS.rglob("*") if path.is_file()}
        self.assertEqual(MIG1_NOT_COPIED & present, set())                                    # 시험이 '도구는 git push 를 하지 않는다' 를 못박아 옮기지 않았다

    def test_no_copied_tool_has_a_git_push_and_the_lane_merge_tools_added_here_never_push(self):
        for name in sorted(MIG1_NEW_ROOT | (MIG1_NEW_SCRATCH - {"badge_wait.sh", "main_runs_wait.sh", "note.sh", "prepush_check.sh", "watch_all.sh"})):
            path = WORK / name if name in MIG1_NEW_ROOT else SCRATCH / name
            pushes = [node.lineno for node in ast.walk(ast.parse(read(path))) if isinstance(node, ast.Constant) and node.value == "push"]
            self.assertEqual(pushes, [], name)
        for name in ("badge_wait.sh", "main_runs_wait.sh", "note.sh", "prepush_check.sh", "watch_all.sh"):
            body = re.sub(r"(?m)^\s*#.*$", "", read(SCRATCH / name))
            self.assertIsNone(re.search(r"git\s+(?:-\S+\s+)*push", body), name)

    def test_the_readme_nine_section_names_every_new_tool_every_work_folder_copy_and_why_the_qt_trio_is_missing(self):
        s9 = section(read(README), 9)
        for name in sorted(MIG1_NEW_ROOT | MIG1_NEW_SCRATCH | MIG1_NEW_DOCS | W_PATH_COPIES | MIG1_NOT_COPIED | {"LANE_RULES.md"}):
            self.assertIn(name, s9, name)
        for needle in ("`W_PATH_COPIES`", "git push 를 하지 않는다", "`qt-ci-tmp.yml`", "번호 있는 확인 요청", "STAGE_FORBID", "`mk_merge_branch.py` 는 `scratch/` 가 아니라 W 바로 아래",
                       "`INTERVAL = 600`", "저장소 판을 유지", "환경 4개 × 조각 3개 = 작업 12개"):
            self.assertIn(needle, s9 + read(README), needle)

    def test_every_new_tool_has_a_row_or_mention_in_the_tables_of_sections_two_and_three(self):
        text = read(README)
        for name in sorted((MIG1_NEW_ROOT | MIG1_NEW_SCRATCH) - {"keep_both.py"}):
            self.assertIn("`" + name + "`", text, name)
        self.assertIn("`lowprio.py`", table_row(text, "lowprio.py"))
        self.assertIn("낮은 우선순위", table_row(text, "lowprio.py"))
        self.assertIn("종료 코드 75", table_row(text, "qt_lock.py"))

    def test_the_three_merge_tools_read_the_fixed_author_from_commit_as_author_and_carry_none_themselves(self):
        author = read(WORK / "commit_as_author.py")
        name, mail = (re.search("GIT_AUTHOR_" + key + '="([^"]+)"', author).group(1) for key in ("NAME", "EMAIL"))
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            work = Path(tmp) / "W"
            (work / "scratch").mkdir(parents=True)
            shutil.copy2(WORK / "commit_as_author.py", work / "commit_as_author.py")
            for tool in ("build_blog_merge.py", "combine_lanes_desktop.py", "squash_onto.py"):
                source = read(SCRATCH / tool)
                self.assertNotIn(name, source, tool)                                          # 이름·메일 값이 사본에 없다
                self.assertNotIn(mail, source, tool)
                shutil.copy2(SCRATCH / tool, work / "scratch" / tool)
                module = load_tool(work / "scratch" / tool)
                self.assertEqual({module.ENV["GIT_AUTHOR_NAME"], module.ENV["GIT_COMMITTER_NAME"]}, {name}, tool)
                self.assertEqual({module.ENV["GIT_AUTHOR_EMAIL"], module.ENV["GIT_COMMITTER_EMAIL"]}, {mail}, tool)

class StageScriptsTest(unittest.TestCase):
    """tools_stage.py·memcopy_stage.py — 옛 PC 판을 고쳐 넣은 스테이징 도구: 계정 이름이 든 경로·낱말 목록을 코드에 두지 않고 인자·환경 변수로 받으며,
    가린 사본만 만들고, 금지 글이 남으면 쓰지 않고 멈춘다(종료 코드 1)."""

    def copy_into_work_folder(self, tmp, name):
        scratch = Path(tmp) / "W" / "scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCRATCH / name, scratch / name)
        return scratch / name

    def test_memcopy_clean_masks_session_numbers_and_user_folder_paths(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mod = load_tool(self.copy_into_work_folder(tmp, "memcopy_stage.py"))
            fake_home = "C:" + chr(47) + "Users" + chr(47) + "someone"
            text, sessions = mod.clean("---\n  originSessionId: abc-123\n---\n폴더 `" + fake_home + "/Desktop/x` 안\n")
            self.assertEqual(sessions, 1)
            self.assertIn("originSessionId: (세션 번호)", text)
            self.assertIn("`<사용자 폴더>/Desktop/x`", text)
            self.assertNotIn("someone", text)

    def test_memcopy_writes_clean_files_and_refuses_files_with_forbidden_words_mails_or_tokens(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            script = self.copy_into_work_folder(tmp, "memcopy_stage.py")
            mod = load_tool(script)
            src = Path(tmp) / "memory"
            src.mkdir()
            (src / "good.md").write_text("---\noriginSessionId: s-1\n---\n운영자 지시 한 줄\n", encoding="utf-8")
            (src / "word.md").write_text("회사 ACMEWORD 이름이 남음\n", encoding="utf-8")
            (src / "mail.md").write_text("연락 " + "x" + "@" + "example.com 입니다\n", encoding="utf-8")
            (src / "token.md").write_text("키 " + "gh" + "p_" + "CANARY" + "\n", encoding="utf-8")
            mod.OUT.mkdir(parents=True)
            for name in ("word.md", "mail.md", "token.md"):
                (mod.OUT / name).write_text("앞선 실행이 쓴 옛 사본\n", encoding="utf-8")        # 같은 이름의 앞선 사본이 남아 쓰이면 안 된다
            with mock.patch.dict(os.environ, {"STAGE_FORBID": "ACMEWORD"}):
                code, out, _err = capture(mod.main, [str(src), "good.md", "word.md", "mail.md", "token.md"])
            self.assertEqual(code, 1)
            self.assertTrue((mod.OUT / "good.md").is_file())
            self.assertIn("(세션 번호)", (mod.OUT / "good.md").read_text(encoding="utf-8"))
            for name in ("word.md", "mail.md", "token.md"):
                self.assertFalse((mod.OUT / name).exists(), name)                              # 금지 글이 남은 파일은 쓰지 않고 앞선 사본도 지운다
            self.assertEqual(out.count("[실패]"), 3)
            self.assertNotIn("ACMEWORD", out)                                                  # 실패 글에 금지 낱말 값을 싣지 않는다
            self.assertEqual(mod.OUT.resolve(), (Path(tmp) / "W" / "scratch" / "memcopy_stage").resolve())

    def test_memcopy_without_arguments_prints_the_usage_and_changes_nothing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mod = load_tool(self.copy_into_work_folder(tmp, "memcopy_stage.py"))
            code, out, _err = capture(mod.main, [])
            self.assertEqual(code, 2)
            self.assertIn("사용:", out)
            self.assertFalse(mod.OUT.exists())

    def test_tools_stage_copies_masks_python_paths_and_stops_on_forbidden_text(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            script = self.copy_into_work_folder(tmp, "tools_stage.py")
            mod = load_tool(script)
            work = Path(tmp) / "W"
            fake_python = "C:" + chr(47) + "Users" + chr(47) + "someone" + chr(47) + "AppData" + chr(47) + "Local" + chr(47) + "Programs" + chr(47) + "Python" + chr(47) + "Python312" + chr(47) + "python.exe"
            (work / "a.py").write_text("PY = '" + fake_python + "'\n", encoding="utf-8")
            (work / "r.md").write_text("규칙 한 줄\n", encoding="utf-8")
            (work / "scratch" / "s.sh").write_text("echo ok\n# 메일 " + "o" + "ther" + "@" + "example.com 은 허용 목록 밖\n", encoding="utf-8")
            (work / "commit_as_author.py").write_text('GIT_AUTHOR_EMAIL="' + "a" + "@" + 'example.com"\n', encoding="utf-8")
            with mock.patch.object(mod, "ROOT_TOOLS", ["a.py"]), mock.patch.object(mod, "RULE_DOCS", [("r.md", "r.md")]), mock.patch.object(mod, "SCRATCH_TOOLS", ["s.sh"]):
                code, out, _err = capture(mod.main)
            self.assertEqual(code, 1)                                                            # s.sh 에 허용 목록 밖 메일 모양이 남았다
            self.assertIn("금지 글 남은 파일 1개", out)
            self.assertIn("금지 글 1곳", out)
            self.assertNotIn("other", out.replace("work/", ""))                                  # 값을 싣지 않고 곳 수만 적는다
            staged = (work / "scratch" / "mig1_stage" / "인수인계" / "도구" / "work")
            self.assertEqual((staged / "a.py").read_text(encoding="utf-8"), "PY = 'py -3.12'\n")
            self.assertTrue((staged / "r.md").is_file())
            self.assertFalse((staged / "scratch" / "s.sh").exists())                             # 금지 글이 남은 파일은 사본을 쓰지 않는다
            (work / "scratch" / "s.sh").write_text("echo ok\n", encoding="utf-8")
            with mock.patch.object(mod, "ROOT_TOOLS", ["a.py"]), mock.patch.object(mod, "RULE_DOCS", [("r.md", "r.md")]), mock.patch.object(mod, "SCRATCH_TOOLS", ["s.sh"]):
                code, out, _err = capture(mod.main)
            self.assertEqual(code, 0, out)
            self.assertIn("금지 글 남은 파일 0개", out)

    def test_tools_stage_removes_an_earlier_copy_of_a_file_that_now_fails(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mod = load_tool(self.copy_into_work_folder(tmp, "tools_stage.py"))
            source = Path(tmp) / "W" / "s.sh"
            source.write_text("# 메일 " + "o" + "ther" + "@" + "example.com 은 허용 목록 밖\n", encoding="utf-8")
            rx, allowed = mod.forbidden(set())
            stale = mod.OUT / "scratch" / "s.sh"
            stale.parent.mkdir(parents=True)
            stale.write_text("앞선 실행이 쓴 옛 사본\n", encoding="utf-8")
            bad = []
            mod.stage(source, "scratch/s.sh", bad, rx, allowed)
            self.assertEqual([rel for rel, _hits in bad], ["scratch/s.sh"])
            self.assertFalse(stale.exists())                                                     # 옛 사본이 남아 쓰이지 않는다

    def test_both_stage_scripts_warn_on_stderr_when_stage_forbid_is_empty_and_keep_their_exit_codes(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            memcopy = load_tool(self.copy_into_work_folder(tmp, "memcopy_stage.py"))
            tools = load_tool(self.copy_into_work_folder(tmp, "tools_stage.py"))
            src = Path(tmp) / "memory"
            src.mkdir()
            (src / "good.md").write_text("운영자 지시 한 줄\n", encoding="utf-8")
            (Path(tmp) / "W" / "a.py").write_text("X = 1\n", encoding="utf-8")
            for value, warned in (("", True), ("ACMEWORD", False)):
                with mock.patch.dict(os.environ, {"STAGE_FORBID": value}):
                    code, _out, err = capture(memcopy.main, [str(src), "good.md"])
                self.assertEqual(code, 0, value)                                                 # 종료 코드는 그대로 — 경고만 더한다
                self.assertEqual("STAGE_FORBID" in err and "경고" in err, warned, value)
                with mock.patch.dict(os.environ, {"STAGE_FORBID": value}), mock.patch.object(tools, "ROOT_TOOLS", ["a.py"]), \
                        mock.patch.object(tools, "RULE_DOCS", []), mock.patch.object(tools, "SCRATCH_TOOLS", []):
                    code, _out, err = capture(tools.main)
                self.assertEqual(code, 0, value)
                self.assertEqual("STAGE_FORBID" in err and "경고" in err, warned, value)

    def test_the_stage_scripts_derive_the_work_folder_from_their_own_location(self):
        for name in ("tools_stage.py", "memcopy_stage.py"):
            source = read(SCRATCH / name)
            self.assertIn("Path(__file__).resolve().parent.parent", source, name)
            self.assertEqual(problems(source, FORBIDDEN_STRICT), [], name)                       # 고정 작업 폴더·계정 이름·사용자 폴더가 코드에 없다


if __name__ == "__main__":
    unittest.main()
