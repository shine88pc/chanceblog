"""개인 정보 표현 정리(AP17 — 확인 015 의 12번, F127·F129) 시험 — 이 파일에는 운영자의 이름·메일 값을 적지 않는다.
값은 프로그램이 저장소의 정본(도구의 고정 작성자 상수·공개 설정의 연락처 메일)에서 읽어 비교에만 쓰고, 실패 메시지에는 파일 경로와 종류만 쓴다(파일 내용을 메시지에 싣지 않는다).
여기서 보는 것: ① 공개 설정의 연락처 메일이 문서·기억 사본·시험 값에 다시 나오지 않는다 ② 도구의 고정 작성자(이름·메일)가 문서·기억 사본·옛 지시서·시험 값에 나오지 않는다 —
단 AP18 에서 따로 정할 곳은 아래 EXEMPT_UNTIL_AP18 에 경로로 적었고, 그 목록은 실제로 값이 든 파일만 담는다 ③ 문서(.md)의 메일 모양은 허용 목록(example.com·noreply·기관 대표 메일)에서만
통과한다 ④ 기억 사본 안내 문서에 '사람 이름·메일은 쓰지 않고 역할 말로 쓴다' 규칙이 있다 ⑤ 검사기 자체가 나쁜 표본을 잡는다 ⑥ 결함 대장 행.
이름은 값 없이 모양만으로 막을 수 없어서(②) 도구의 고정 작성자 상수에서 읽어 오는 방식을 쓴다 — AP18 이 도구가 로컬 설정을 쓰게 바꾸면 상수가 사라져 ②의 이름 검사는 건너뛴다.
이 시험은 공개 이력의 과거분을 지우지 못한다 — 효과는 앞으로의 파일에만 있다."""
import functools
import os
import re
import unittest

import _bootstrap

ROOT = _bootstrap.ROOT
MAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:[.][A-Za-z0-9-]+)+")

# 허용 목록 — 문서(.md)에 있어도 되는 메일 모양. 기관의 대표 연락처는 개인 메일이 아니므로 주소를 이름으로 적는다(새 기관 주소를 문서에 쓰려면 여기에 더한다).
ALLOWED_DOMAINS = frozenset({"example.com"})
ALLOWED_MARKER = "noreply"                                       # 봇·공용 보낸이 주소(users.noreply.github.com 등)
INSTITUTION_MAILS = frozenset({"unnews@un.org"})                 # UN News 의 이용 확인 연락처(기관 대표 메일)

# AP18 에서 따로 정할 곳(아직 안 물음) — 경로로 적는다. 여기 적힌 파일은 값이 들어 있어야 하고(들어 있지 않으면 목록에서 뺀다), 그 밖의 파일에는 값이 없어야 한다.
EXEMPT_UNTIL_AP18 = (
    "인수인계/도구/work/commit_as_author.py",                      # 도구의 고정 작성자(상수 원본)
    "인수인계/도구/work/mk_merge_branch.py",
    "인수인계/도구/work/scratch/mk_lane_merge.py",
    "인수인계/도구/work/scratch/mk_lane_merge_desktop.py",
    "tests/test_handoff_tools.py",                                 # 고정 작성자를 기대하는 시험(도구와 한 쌍)
    "_config.yml",                                                 # 공개 사이트 연락처 메일(F078 후보 — 광고 표면·공개 설정이라 이번 승인 밖)
)

SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules", "_posts", "assets", "_blogger_drafts", "_blogger_ko_drafts", "_naver_drafts"})
TREES = ("docs", "인수인계", "tests", "scripts", "pipeline", ".github", "_includes", "_layouts")
TEXT_SUFFIXES = (".md", ".py", ".txt", ".yml", ".yaml", ".json", ".html")
TOP_SUFFIXES = (".md", ".py", ".txt", ".yml", ".yaml", ".html")             # 저장소 맨 위의 .json 은 글·이력을 담은 생성 자료라 뺀다(공개 글 폴더를 뺀 것과 같은 이유)
TOOL = "인수인계/도구/work/commit_as_author.py"
README = "인수인계/AI_기억/README.md"
MEMORY_DIR = "인수인계/AI_기억"


@functools.lru_cache(maxsize=None)
def _read(rel):
    return (ROOT / rel).read_bytes().decode("utf-8", errors="replace")


def _relative(dirpath, name):
    return os.path.relpath(os.path.join(dirpath, name), ROOT).replace(os.sep, "/")


@functools.lru_cache(maxsize=None)
def scope_files():
    """값을 찾아볼 글 파일 — 저장소 맨 위의 글 파일과 사람이 쓰는 폴더들(공개 글·생성물 폴더는 뺀다)."""
    found = [name for name in sorted(os.listdir(ROOT)) if (ROOT / name).is_file() and name.endswith(TOP_SUFFIXES)]
    for top in TREES:
        for dirpath, dirnames, filenames in os.walk(ROOT / top):
            dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
            found.extend(_relative(dirpath, name) for name in sorted(filenames) if name.endswith(TEXT_SUFFIXES))
    return found


@functools.lru_cache(maxsize=None)
def markdown_files():
    """허용 목록으로 보는 문서 — 공개 글·생성물·시험 폴더를 뺀 모든 .md."""
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS and name != "tests")
        found.extend(_relative(dirpath, name) for name in sorted(filenames) if name.endswith(".md"))
    return found


def fixed_author():
    """(이름, 메일) — 도구의 고정 작성자 상수에서 읽는다. 없으면 None(AP18 뒤)."""
    path = ROOT / TOOL
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    name, mail = re.search(r'GIT_AUTHOR_NAME="([^"]+)"', text), re.search(r'GIT_AUTHOR_EMAIL="([^"]+)"', text)
    return (name.group(1), mail.group(1)) if name and mail else None


@functools.lru_cache(maxsize=None)
def public_mails():
    """공개 설정(_config.yml)에 적힌 연락처 메일 모양들."""
    return sorted(set(MAIL_RE.findall(_read("_config.yml"))))


def not_allowed(text):
    """text 의 메일 모양 중 허용 목록에 없는 것(주소 그대로)."""
    bad = []
    for address in MAIL_RE.findall(text):
        lower = address.lower()
        if address in INSTITUTION_MAILS or ALLOWED_MARKER in lower or lower.rsplit("@", 1)[1] in ALLOWED_DOMAINS:
            continue
        bad.append(address)
    return bad


def masked(address):
    """메시지용 — 앞부분 글자 수와 도메인만."""
    local, _, domain = address.partition("@")
    return f"(앞부분 {len(local)}자)@{domain}"


class Base(unittest.TestCase):
    def has(self, text, phrase, label):
        """assertIn 대신 — 실패해도 파일 내용을 메시지에 싣지 않는다."""
        self.assertTrue(phrase in text, f"{label} 에 '{phrase}' 가 없다")


class IdentityValuesTest(Base):
    def offenders(self, values, kind):
        """values 가 든 파일 [(경로, 종류)] — 면제 목록의 파일은 뺀다. 값은 쓰지 않는다."""
        found = []
        for rel in scope_files():
            if rel in EXEMPT_UNTIL_AP18:
                continue
            text = _read(rel)
            if any(value in text for value in values):
                found.append((rel, kind))
        return found

    def test_the_public_contact_mail_does_not_come_back_into_documents_memory_copies_or_test_values(self):
        values = public_mails()
        self.assertEqual(self.offenders(values, "공개 연락처 메일"), [])

    def test_the_fixed_author_of_the_tools_is_not_in_documents_memory_copies_old_briefs_or_test_values(self):
        author = fixed_author()
        if author is None:
            self.skipTest("도구에 고정 작성자 상수가 없다 — 이름 검사는 건너뜀(AP18 뒤)")
        name, mail = author
        self.assertEqual(self.offenders((mail,), "작성자 메일"), [])
        self.assertEqual(self.offenders((name,), "작성자 이름"), [])

    def test_the_tool_constants_are_readable_while_the_tool_still_holds_them(self):
        """값을 읽는 정규식이 깨져 위 이름 검사가 조용히 건너뛰어지는 구멍을 막는다 — 도구에 고정 작성자 상수가 있으면 반드시 읽혀야 한다."""
        text = _read(TOOL)
        holds = "GIT_AUTHOR_NAME" in text or "GIT_AUTHOR_EMAIL" in text
        self.assertEqual(fixed_author() is not None, holds)

    def test_the_exempt_list_names_only_files_that_really_hold_a_value(self):
        author = fixed_author()
        values = set(public_mails()) | set(author or ())
        if not values:
            self.skipTest("비교할 값이 없다 — 도구의 고정 작성자도 공개 연락처 메일도 더는 없다(AP18·F078 뒤)")
        self.assertEqual(len(set(EXEMPT_UNTIL_AP18)), len(EXEMPT_UNTIL_AP18))
        for rel in EXEMPT_UNTIL_AP18:
            self.assertTrue((ROOT / rel).is_file(), f"면제 목록의 파일이 없다: {rel}")
            self.assertTrue(any(value in _read(rel) for value in values), f"값이 더는 없다 — 면제 목록에서 뺀다: {rel}")

    def test_the_scope_really_covers_the_memory_copies_the_old_briefs_and_the_test_values(self):
        scope = set(scope_files())
        for rel in (README, f"{MEMORY_DIR}/user-profile.md", f"{MEMORY_DIR}/dev-environment-notes.md", f"{MEMORY_DIR}/desktop-repo-chanceblog-desktop.md", "docs/SESSION_START.md",
                    "인수인계/도구/README.md", "인수인계/도구/work/p24nv_brief.md", "인수인계/도구/work/p25p0_report.md", "tests/test_validate_repo.py", "AGENTS.md"):
            self.assertTrue(rel in scope, f"훑는 범위에 없다: {rel}")
        self.assertGreater(len(scope), 300)                                       # 훑는 파일 목록이 비어 거짓 통과하지 않는다
        for rel in scope:
            self.assertFalse(rel.startswith(("_posts/", "assets/")), rel)


class MailShapeTest(Base):
    def test_every_mail_shape_in_the_documents_is_on_the_allow_list(self):
        files = markdown_files()
        self.assertGreater(len(files), 100)
        problems = []
        for rel in files:
            for address in not_allowed(_read(rel)):
                problems.append(f"{rel}: {masked(address)}")
        self.assertEqual(problems, [])

    def test_the_scan_really_sees_mail_shapes_in_the_documents(self):
        """훑기가 비어 거짓 통과하지 않는다 — 문서에 메일 모양이 실제로 있고(허용되는 것들), 그 가운데 허용 목록에서 오는 것이 하나 이상 있다."""
        seen = [address for rel in markdown_files() for address in MAIL_RE.findall(_read(rel))]
        self.assertGreater(len(seen), 0)

    def test_the_checker_catches_known_bad_samples_and_passes_clean_text(self):
        local = "someone"
        bad = [f"문의 {local}@" + "gmail.com 으로", f"{local}.kim@" + "naver.com", f"{local}@" + "example.org", "support@" + "un.org", f"{local}@" + "my-company.co.kr"]
        for sample in bad:
            with self.subTest(sample=masked(MAIL_RE.search(sample).group(0))):
                self.assertEqual(len(not_allowed(sample)), 1)
        good = ["old@example.com 으로 보내 주세요", "Co-Authored-By: Claude <noreply@" + "anthropic.com>", "198982749+bot@users.noreply.github.com", sorted(INSTITUTION_MAILS)[0],
                "메일 주소 없는 글", "a @ b"]
        for sample in good:
            with self.subTest(sample=sample[:12]):
                self.assertEqual(not_allowed(sample), [])
        self.assertEqual(masked("abcdef@" + "x.test"), "(앞부분 6자)@x.test")


class NeutralWordsTest(Base):
    def test_the_memory_copy_readme_states_the_role_word_rule(self):
        text = _read(README)
        for phrase in ("사람 이름·메일은 쓰지 않고 역할 말로 쓴다", "'운영자'", "'저장소 소유자'", "'운영자 계정'", "공개 이력의 과거분은 지우지 못한다", "고치지 않는 기록 사본", "유일한 예외"):
            self.has(text, phrase, README)                                         # 옛 4번 규칙(고치지 않는 기록 사본)은 그대로 있고, 새 규칙은 그 유일한 예외라고 말한다

    def test_the_old_briefs_and_reports_say_who_authored_in_role_words(self):
        for name in ("p24nv_brief", "p25p0_brief", "p26p1_brief", "p27p0b_brief"):
            self.has(_read(f"인수인계/도구/work/{name}.md"), "작성자는 운영자 계정(도구가 고정)", name)
        self.has(_read("인수인계/도구/work/p25p0_report.md"), "작성자는 운영자 계정(도구가 고정)", "p25p0_report")
        self.has(_read("인수인계/도구/work/p24nv_progress.md"), "작성자는 운영자 계정", "p24nv_progress")
        self.has(_read("인수인계/도구/work/p26p1_report.md"), "작성자·커미터는 운영자 계정", "p26p1_report")
        self.has(_read("인수인계/도구/README.md"), "운영자 계정의 이름·메일(도구 상수)", "도구 README")
        self.has(_read(f"{MEMORY_DIR}/user-profile.md"), "저장소 소유자", "user-profile")

    def test_the_session_start_example_is_a_placeholder_and_the_command_is_unchanged(self):
        lines = [item for item in _read("docs/SESSION_START.md").splitlines() if item.startswith("- 작성자 설정은 **clone 안에서만**")]
        self.assertEqual(len(lines), 1)
        self.has(lines[0], "`이름 <메일>` 모양", "SESSION_START 작성자 설정 줄")
        self.has(lines[0], 'git log -8 --format="%an <%ae> %s"', "SESSION_START 작성자 설정 줄")

    def test_the_test_value_is_a_generic_pair_and_the_assertion_keeps_its_meaning(self):
        text = _read("tests/test_validate_repo.py")
        self.has(text, '("Human Author", "human@example.com"), ("t", "t@example.com")):', "test_validate_repo")
        start = text.index("def test_only_real_copilot_identities_count_as_agents(self):")
        body = text[start:text.index("def test_a_marker_without_the_colon_is_not_an_approval", start)]
        self.assertEqual(body.count("assertTrue(vr._is_agent_commit"), 1)
        self.assertEqual(body.count("assertFalse(vr._is_agent_commit"), 1)          # 사람은 에이전트로 세지 않는다 — 단언은 그대로


class RegisterTest(Base):
    def test_the_register_row_is_in_the_main_table_names_the_scope_and_the_limits(self):
        register = _read("docs/DEFECT_REGISTER.md")
        self.assertEqual(len(re.findall(r"^\| \*\*D-392\*\* \|", register, re.M)), 1)
        row = next(line for line in register.splitlines() if line.startswith("| **D-392** |"))
        self.assertLess(register.index(row), register.index("## 운영 중 확인할 것"))
        parts = row.split("|")
        self.assertEqual(len(parts), 8)                                            # 여섯 칸
        self.assertTrue(parts[5].strip().startswith("**해결**"))
        for phrase in ("F127", "F129", "확인 015", "`tests/test_personal_expressions.py`", "공개 이력의 과거분", "AP18", "`_config.yml`"):
            self.has(row, phrase, "결함 대장 D-392 행")


if __name__ == "__main__":
    unittest.main()
