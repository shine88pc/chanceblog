"""HANDOFF2 — 저장소 `인수인계/도구/` 로 옮긴 도구 사본의 시험(정적·존재·순수 함수·끝에서 끝까지).

배경: 새 PC·새 세션이 첫 보고·병합 부탁·병합완료 확인·CI 확인·감시를 하려면 필요한 도구가 저장소에 최신으로 있어야 한다(운영자 이슈 #198 의 후속). 이 시험은 옮긴 도구가
(1) 이 PC 의 사용자 이름·사용자 폴더·고정 작업 폴더·실제 키·광고 번호가 없는 일반형인지(정적),
(2) 안내 문서·복사 목록·감시 프롬프트가 말하는 파일이 실제로 저장소에 있는지(존재),
(3) 순수 함수와 가짜 응답으로 약속대로 도는지(`merge_guard` 는 판정만 하고 푸시·병합이 없다, `watch_issues` 는 5분 주기이고 한도가 바닥나면 쉰다, `resume_check` 는 비밀·경로를 찍지 않는다 …),
(4) 복사본이 작업 폴더 W 안에서 실제 git 으로 끝까지 도는지(푸시하지 않는다)를 못박는다.
네트워크·실제 GitHub·텔레그램은 쓰지 않는다(가짜 응답 — 진짜 git 은 임시 폴더의 로컬 저장소뿐). 다른 묶음의 결정 번호·요청 번호·전체 최댓값은 못박지 않는다.
"""
import ast
import contextlib
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import _bootstrap

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


def load_tool(path):
    """도구 파일을 시험마다 새로 읽는다 — 도구가 sys.path·sys.modules 에 끼워 넣은 것(자기 폴더의 이웃 모듈)은 시험이 끝나면 되돌린다."""
    path = Path(path)
    _loaded[0] += 1
    name = f"handoff_tool_{path.stem}_{_loaded[0]}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    saved_path, saved_modules = list(sys.path), set(sys.modules)
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


def problems(text, forbidden):
    return [name for name, rx in forbidden.items() if rx.search(text)]


# ==== 1. 정적 — 고정 경로·사용자·비밀·광고 번호가 없다 ===========================================
class StaticHygieneTest(unittest.TestCase):
    def test_the_moved_tools_forms_and_prompt_are_general_and_clean(self):
        self.assertGreaterEqual(len(STRICT_FILES), 30)                                   # 훑는 파일 목록이 비어 거짓 통과하지 않는다
        for path in STRICT_FILES:
            self.assertEqual(problems(read(path), FORBIDDEN_STRICT), [], path.name)

    def test_the_guides_and_briefs_are_clean_too(self):
        self.assertIn(README, DOC_FILES)
        for path in DOC_FILES:
            self.assertEqual(problems(read(path), FORBIDDEN_DOCS), [], path.name)

    def test_the_only_email_is_the_fixed_author_that_commit_as_author_already_had(self):
        allowed = set(EMAIL_RX.findall(read(WORK / "commit_as_author.py")))
        self.assertEqual(len(allowed), 1, allowed)
        for path in STRICT_FILES + DOC_FILES:
            self.assertLessEqual(set(EMAIL_RX.findall(read(path))), allowed, path.name)

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

    def test_a_clean_documents_only_branch_is_eligible(self):
        result = self.inspect(FakeGit())
        self.assertEqual((result["ok"], result["reasons"], result["tier"], result["files"]), (True, [], "A", 1))

    def test_every_condition_blocks_on_its_own(self):
        cases = (
            ("가지 이름", dict(branch="ai/claude/docs-cleanup"), {}),
            ("가지 이름", dict(branch="ai/claude/M73-x"), {}),
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


# ==== 5. watch_issues — 5분 주기, 한도가 바닥나면 쉰다 =========================================
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

    def run_watch(self, steps):
        sleeps, queue = [], list(steps)

        def fake_fetch(etag):
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

    def test_the_loop_prints_only_new_operator_issues_and_waits_five_minutes_between_reads(self):
        out, sleeps = self.run_watch([
            ("e1", [issue(10), issue(9)]),
            ("e2", [issue(12, login="stranger"), issue(11, labels=["텔레그램수신"], login="bot"), issue(10)]),
            ("e2", None),
        ])
        lines = out.splitlines()
        self.assertEqual(lines[0], "이슈 감시 시작: 지금 최신 이슈 #10 (이후에 생기는 운영자 관련 이슈를 알립니다)")
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(lines[1].startswith("[새 이슈] #11 "))
        self.assertEqual(sleeps, [300, 300, 300])
        self.assertEqual(self.wi.INTERVAL, 300)

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
        self.assertEqual(sleeps, [300, 300, 300, 300])

    def test_the_documented_numbers_match_the_code(self):
        row = table_row(read(README), "watch_issues.py")
        for needle in ("300초(5분)", "시간당 12회", "304", "시간당 60회 한도에 센다", "2026-11-15 실측", "한도가 바닥나면(403·429)", "최소 60초·최대 15분", "스스로 끝나지 않는다"):
            self.assertIn(needle, row, needle)
        source = read(SCRATCH / "watch_issues.py")
        self.assertIn("max(60, min(900,", source)
        self.assertIn("2026-11-15 실측", source)
        self.assertEqual(3600 // self.wi.INTERVAL, 12)


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


# ==== 10. 복사본이 작업 폴더 W 안에서 도는지 =================================================
def git_env():
    env = dict(os.environ)
    env.update(GIT_AUTHOR_NAME="Test Author", GIT_AUTHOR_EMAIL="author@example.invalid", GIT_COMMITTER_NAME="Test Author", GIT_COMMITTER_EMAIL="author@example.invalid",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    return env


class SetupWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.setup = load_tool(SETUP)

    def test_copy_tools_puts_every_file_where_the_readme_says_and_overwrites_a_stale_copy(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            target = Path(tmp) / "W"
            _result, out, _err = capture(self.setup.copy_tools, target)
            self.assertIn("도구·문서·양식 복사:", out)
            for source, rel in self.setup.plan_copy():
                self.assertEqual((target / rel).read_bytes(), source.read_bytes(), rel.as_posix())
            self.assertTrue((target / "scratch" / "watch_heads2.sh").is_file())
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
        setup = self.setup
        commands = []
        cloned = []
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            target = Path(tmp) / "W"
            with mock.patch.object(setup, "run", side_effect=lambda *args, cwd=None: commands.append((args, cwd))), \
                    mock.patch.object(setup, "clone", side_effect=lambda url, folder: cloned.append((url, folder.name))), \
                    mock.patch.object(setup.shutil, "which", return_value="git"), mock.patch.object(sys, "argv", ["setup_workspace.py", str(target)]):
                _result, out, _err = capture(setup.main)
        self.assertEqual([name for _url, name in cloned], ["wt_r30", "cd_repo"])
        self.assertTrue(all(url.startswith("https://github.com/") and url.endswith(".git") and "@" not in url for url, _name in cloned))   # 비밀 없는 공개 주소
        git = [args for args, _cwd in commands]
        self.assertIn(("git", "fetch", "origin"), git)
        self.assertIn(("git", "checkout", "-B", setup.REQUEST_BRANCH, "origin/" + setup.REQUEST_BRANCH), git)
        self.assertFalse(any("push" in args for args in git))
        self.assertIn("다음:", out)
        for tool in ("scratch/resume_check.py", "cron_status_prompt_v3.txt", "watch_issues.py", "watch_heads2.sh"):
            self.assertIn(tool, out)

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
            "python bootstrap.py --work <W> --python <3.12 경로> --clone",
            "GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=false git -C <W>/wt_r30 push --dry-run --porcelain origin HEAD:refs/heads/ai/claude/preflight-test",
            "python -X utf8 인수인계/도구/setup_workspace.py <W>",
            "python -X utf8 <W>/scratch/resume_check.py --work <W>",
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

    def test_the_readme_lists_the_forms_and_the_old_two_documents_keep_their_names(self):
        s7 = section(self.text, 7)
        quoted = "AI 병합 기능이 꺼져 있어 운영자께서 직접 병합해 주세요"
        for needle in ("양식/merge_request_template_v2.md", "양식/progress_draft_template.md", quoted):
            self.assertIn(needle, s7, needle)
        forms = {path.name: read(path) for path in FORMS.glob("*.md")}
        self.assertEqual(set(forms), EXPECTED_FORMS)
        self.assertIn(quoted, forms["merge_request_template_v2.md"].replace("**", ""))                                    # README 가 인용한 문구는 양식의 실제 문구다


if __name__ == "__main__":
    unittest.main()
