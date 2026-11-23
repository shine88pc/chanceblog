"""개인 정보 표현 정리(AP17 — 확인 015 의 12번, F127·F129) 시험 — 이 파일에는 운영자의 이름·메일 값을 적지 않는다.
값은 프로그램이 저장소의 정본(도구의 고정 작성자 상수·공개 설정의 연락처 메일)에서 읽어 비교에만 쓰고, 실패 메시지에는 파일 경로와 종류만 쓴다(파일 내용을 메시지에 싣지 않는다).
여기서 보는 것: ① 공개 설정의 연락처 메일이 문서·기억 사본·시험 값에 다시 나오지 않는다 ② 도구의 고정 작성자(이름·메일)가 문서·기억 사본·옛 지시서·시험 값에 나오지 않는다 —
단 AP18 에서 따로 정할 곳은 아래 EXEMPT_UNTIL_AP18 에 '경로와 허용하는 값의 종류'로 적었고, 그 목록은 실제로 값이 든 파일만 담는다(공개 설정은 email 키 한 줄뿐, 고정 작성자를 기대하는 시험은 이름뿐)
③ 문서(.md)의 메일 모양은 허용 목록(example.com·보낸이 전용 noreply 주소·기관 대표 메일)에서만 통과한다 ④ 기억 사본 안내 문서에 '사람 이름·메일은 쓰지 않고 역할 말로 쓴다' 규칙이 있다
⑤ 검사기 자체가 나쁜 표본을 잡는다 ⑥ 결함 대장 행.
독립 검증(2026-11-22)의 권고를 받아 좁히고 넓힌 것: noreply 허용을 '지역 부분이 정확히 noreply 이거나 GitHub 의 가림 도메인'으로 좁힘(SP-3) · 훑는 파일을 확장자 목록에서 '이진 파일만 빼고 모두'로 넓힘(SP-1) ·
면제를 파일 통째에서 값의 종류로 좁힘(SP-2) · 값 비교에서 대소문자·전각 글자·풀어 쓴 한글·보이지 않는 글자·메일의 '+별칭'을 같은 값으로 봄(SP-4) · 훑는 폴더 범위와 '효과는 앞으로의 파일에만' 문구를 못박음(QP-1) ·
ssh 주소·버전 표기·그림 이름을 메일로 오해하지 않음(QP-2) · test_validate_repo 의 글자 모양 대신 구문 트리로 읽음(QP-6).
이름은 값 없이 모양만으로 막을 수 없어서(②) 도구의 고정 작성자 상수에서 읽어 오는 방식을 쓴다 — AP18 이 도구가 로컬 설정을 쓰게 바꾸면 상수가 사라져 ②의 이름 검사는 건너뛴다.
못 막는 것(정직하게): 이름을 일부러 쪼개 쓰거나 뒷글자만 쓰는 것, 메일 모양 검사가 .md 에만 걸리는 것(시험 파일의 URL 사용자 정보 표본 때문 — 코드·설정은 값 비교로만 막는다).
이 시험은 공개 이력의 과거분을 지우지 못한다 — 효과는 앞으로의 파일에만 있다."""
import ast
import functools
import os
import re
import unicodedata
import unittest

import _bootstrap

ROOT = _bootstrap.ROOT
MAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:[.][A-Za-z0-9-]+)+")

# 허용 목록 — 문서(.md)에 있어도 되는 메일 모양. 기관의 대표 연락처는 개인 메일이 아니므로 주소를 이름으로 적는다(새 기관 주소를 문서에 쓰려면 여기에 더한다).
ALLOWED_DOMAINS = frozenset({"example.com"})
NOREPLY_LOCALS = frozenset({"noreply", "no-reply", "donotreply", "do-not-reply"})           # 지역 부분이 '정확히' 이 글자인 보낸이 전용 주소(앞뒤에 글자가 붙은 별칭은 안 된다)
NOREPLY_DOMAINS = ("noreply.github.com",)                                                   # GitHub 의 가림 주소(users.noreply.github.com) — 이 도메인이거나 그 하위 도메인
INSTITUTION_MAILS = frozenset({"unnews@un.org"})                                            # UN News 의 이용 확인 연락처(기관 대표 메일)
SSH_REMOTE_USERS = frozenset({"git@github.com"})                                            # `git@github.com:주인/저장소.git` 같은 ssh 주소는 편지함이 아니다
IMAGE_TLDS = frozenset({"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp", "avif"})  # `icon@2x.png` 같은 그림 이름은 메일이 아니다

# AP18 에서 따로 정할 곳(아직 안 물음) — {경로: 허용하는 값의 종류}. 종류: 이름 = 도구의 고정 작성자 이름, 메일 = 고정 작성자·공개 연락처 메일.
# 여기 적힌 파일은 허용한 종류의 값이 실제로 들어 있어야 하고(없으면 목록에서 뺀다) 허용하지 않은 종류가 늘면 빨강이다. 그 밖의 파일에는 값이 없어야 한다.
EXEMPT_UNTIL_AP18 = {
    "인수인계/도구/work/commit_as_author.py": ("이름", "메일"),     # 도구의 고정 작성자(상수 원본)
    "인수인계/도구/work/mk_merge_branch.py": ("이름", "메일"),
    "인수인계/도구/work/scratch/mk_lane_merge.py": ("이름", "메일"),
    "인수인계/도구/work/scratch/mk_lane_merge_desktop.py": ("이름", "메일"),
    "tests/test_handoff_tools.py": ("이름",),                      # 고정 작성자를 기대하는 시험(도구와 한 쌍) — 이름만, 메일은 안 된다
    "_config.yml": ("메일",),                                      # 공개 사이트 연락처(F078 후보 — 광고 표면·공개 설정이라 이번 승인 밖) — 그것도 email 키 한 줄에만
}
CONFIG = "_config.yml"

SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", "_posts", "assets", "_blogger_drafts", "_blogger_ko_drafts", "_naver_drafts"})
TREES = (".design", ".github", "_includes", "_layouts", "docs", "pipeline", "scripts", "tests", "인수인계")
BINARY_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".avif", ".pdf", ".zip", ".gz", ".tar", ".7z", ".woff", ".woff2", ".ttf", ".otf", ".eot",
                   ".mp3", ".mp4", ".mov", ".pyc", ".db", ".sqlite", ".bin", ".exe", ".dll", ".so", ".whl", ".figcraft")
TOP_GENERATED_SUFFIXES = (".json", ".xml")                    # 저장소 맨 위의 .json·.xml 은 글·이력을 담은 생성 자료라 뺀다(공개 글 폴더를 뺀 것과 같은 이유)
TOOL = "인수인계/도구/work/commit_as_author.py"
README = "인수인계/AI_기억/README.md"
MEMORY_DIR = "인수인계/AI_기억"
INVISIBLE = "".join(chr(code) for code in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD))   # 폭 없는 글자·부드러운 하이픈
INVISIBLE_TABLE = {ord(char): None for char in INVISIBLE}


@functools.lru_cache(maxsize=None)
def _read(rel):
    return (ROOT / rel).read_bytes().decode("utf-8", errors="replace")


def _relative(dirpath, name):
    return os.path.relpath(os.path.join(dirpath, name), ROOT).replace(os.sep, "/")


def _is_text(path):
    """이진 파일이 아닌가 — 이진 확장자가 아니고 처음 8KB 에 NUL 이 없다."""
    if path.name.lower().endswith(BINARY_SUFFIXES):
        return False
    with open(path, "rb") as handle:
        return b"\0" not in handle.read(8192)


@functools.lru_cache(maxsize=None)
def scope_files():
    """값을 찾아볼 글 파일 — 저장소 맨 위의 글 파일(생성 자료 .json·.xml 은 뺀다)과 사람이 쓰는 폴더들의 이진이 아닌 모든 파일(.sh·.ps1·확장자 없는 파일 포함). 공개 글·생성물 폴더는 뺀다."""
    found = []
    for name in sorted(os.listdir(ROOT)):
        path = ROOT / name
        if path.is_file() and not name.endswith(TOP_GENERATED_SUFFIXES) and _is_text(path):
            found.append(name)
    for top in TREES:
        for dirpath, dirnames, filenames in os.walk(ROOT / top):
            dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
            found.extend(_relative(dirpath, name) for name in sorted(filenames) if _is_text(ROOT / _relative(dirpath, name)))
    return found


@functools.lru_cache(maxsize=None)
def markdown_files():
    """허용 목록으로 보는 문서 — 공개 글·생성물·시험 폴더를 뺀 모든 .md."""
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS and name != "tests")
        found.extend(_relative(dirpath, name) for name in sorted(filenames) if name.endswith(".md"))
    return found


@functools.lru_cache(maxsize=None)
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
    return tuple(sorted(set(MAIL_RE.findall(_read(CONFIG)))))


def identity_names():
    author = fixed_author()
    return (author[0],) if author else ()


def identity_mails():
    author = fixed_author()
    return tuple(sorted(set(public_mails()) | ({author[1]} if author else set())))


def fold(text):
    """비교용 — 호환 정규화(전각 글자·풀어 쓴 한글 자모)·소문자·보이지 않는 글자 제거."""
    return unicodedata.normalize("NFKC", text).translate(INVISIBLE_TABLE).casefold()


def canonical_mail(address):
    """'+별칭' 을 뗀 메일 — 같은 편지함으로 가는 별칭을 같은 값으로 본다."""
    local, _, domain = fold(address).partition("@")
    return local.split("+", 1)[0] + "@" + domain


def folded_has(folded, names=(), mails=()):
    """fold 한 글에 이름(글자 그대로)이나 메일(글자 그대로 또는 '+별칭' 을 뗀 꼴)이 있는가."""
    if any(fold(name) in folded for name in names):
        return True
    if mails:
        wanted = {canonical_mail(mail) for mail in mails}
        return any(fold(mail) in folded for mail in mails) or any(canonical_mail(found) in wanted for found in MAIL_RE.findall(folded))
    return False


def text_has(text, names=(), mails=()):
    return folded_has(fold(text), names, mails)


@functools.lru_cache(maxsize=None)
def _folded(rel):
    return fold(_read(rel))


@functools.lru_cache(maxsize=None)
def file_has(rel, names=(), mails=()):
    return folded_has(_folded(rel), names, mails)


def kinds_of(folded):
    """fold 한 글에 든 값의 종류 {'이름', '메일'} — 고정 작성자 이름 / 고정 작성자·공개 연락처 메일."""
    kinds = set()
    if folded_has(folded, names=identity_names()):
        kinds.add("이름")
    if folded_has(folded, mails=identity_mails()):
        kinds.add("메일")
    return kinds


def without_email_key_lines(text):
    """공개 설정에서 `email:` 키 줄만 뺀 글 — 그 줄이 공개 연락처 메일이 있어도 되는 유일한 자리다(키로 찾고 줄 번호는 안 쓴다)."""
    return "\n".join(line for line in text.splitlines() if not re.match(r"^\s*email\s*:", line))


def is_mailbox(address):
    """편지함 모양인가 — `액션@v5.1.0`(끝 칸이 숫자)·`icon@2x.png`(그림 이름)은 메일이 아니다."""
    last = address.rsplit("@", 1)[1].lower().rsplit(".", 1)[-1]
    return last.isalpha() and len(last) >= 2 and last not in IMAGE_TLDS


def is_allowed(address):
    lower = address.lower()
    local, domain = lower.rsplit("@", 1)
    return (lower in INSTITUTION_MAILS or lower in SSH_REMOTE_USERS or domain in ALLOWED_DOMAINS or local in NOREPLY_LOCALS
            or any(domain == suffix or domain.endswith("." + suffix) for suffix in NOREPLY_DOMAINS))


def not_allowed(text):
    """text 의 메일 모양 중 허용 목록에 없는 것(주소 그대로)."""
    return [address for address in MAIL_RE.findall(text) if is_mailbox(address) and not is_allowed(address)]


def masked(address):
    """메시지용 — 앞부분 글자 수와 도메인만."""
    local, _, domain = address.partition("@")
    return f"(앞부분 {len(local)}자)@{domain}"


class Base(unittest.TestCase):
    def has(self, text, phrase, label):
        """assertIn 대신 — 실패해도 파일 내용을 메시지에 싣지 않는다."""
        self.assertTrue(phrase in text, f"{label} 에 '{phrase}' 가 없다")


class IdentityValuesTest(Base):
    def offenders(self, names, mails, kind):
        """값이 든 파일 [(경로, 종류)] — 면제 목록의 파일은 뺀다. 값은 쓰지 않는다. 비교는 대소문자·전각·풀어 쓴 한글·보이지 않는 글자·'+별칭' 을 같은 값으로 본다."""
        return [(rel, kind) for rel in scope_files() if rel not in EXEMPT_UNTIL_AP18 and file_has(rel, tuple(names), tuple(mails))]

    def test_the_public_contact_mail_does_not_come_back_into_documents_memory_copies_or_test_values(self):
        values = public_mails()
        self.assertEqual(self.offenders((), values, "공개 연락처 메일"), [])

    def test_the_fixed_author_of_the_tools_is_not_in_documents_memory_copies_old_briefs_or_test_values(self):
        author = fixed_author()
        if author is None:
            self.skipTest("도구에 고정 작성자 상수가 없다 — 이름 검사는 건너뜀(AP18 뒤)")
        name, mail = author
        self.assertEqual(self.offenders((), (mail,), "작성자 메일"), [])
        self.assertEqual(self.offenders((name,), (), "작성자 이름"), [])

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

    def test_the_exempt_files_hold_only_the_kinds_of_values_listed_for_them(self):
        """SP-2 — 면제는 파일 통째가 아니라 '허용하는 값의 종류'다. 고정 작성자를 기대하는 시험에 공개 메일이 새로 들어오거나 도구 밖 면제 파일에 허용하지 않은 종류가 늘면 빨강."""
        if not identity_names() and not identity_mails():
            self.skipTest("비교할 값이 없다(AP18·F078 뒤)")
        for rel, allowed in EXEMPT_UNTIL_AP18.items():
            if rel == CONFIG:
                continue                                                           # 공개 설정은 아래 시험이 email 키 줄로 따로 본다
            present = kinds_of(_folded(rel))
            extra = sorted(present - set(allowed))
            self.assertEqual(extra, [], f"{rel}: 허용하지 않은 종류의 값이 있다({', '.join(extra)}) — 허용: {', '.join(allowed)}")
            self.assertTrue(present, f"{rel}: 값이 더는 없다 — 면제 목록에서 뺀다")

    def test_the_public_config_holds_the_contact_mail_only_on_its_email_key_line(self):
        """SP-2 — 공개 설정(_config.yml)은 연락처 메일 한 줄(email 키)이 유일하게 허용된 자리다. 다른 키나 줄에 이름이나 메일이 들어오면 빨강."""
        if not public_mails():
            self.skipTest("공개 설정에 연락처 메일이 없다 — 면제 목록에서 _config.yml 을 뺀다(F078 뒤)")
        text = _read(CONFIG)
        lines = [line for line in text.splitlines() if re.match(r"^\s*email\s*:", line)]
        self.assertEqual(len(lines), 1, "공개 설정의 email 키 줄이 하나가 아니다")
        self.assertEqual(sorted(kinds_of(fold(without_email_key_lines(text)))), [], "공개 설정의 email 키 한 줄 밖에 이름이나 메일이 있다")
        self.assertIn("메일", kinds_of(fold(lines[0])), "email 키 줄에 연락처 메일이 없다 — 면제 목록에서 _config.yml 을 뺀다")

    def test_the_email_key_rule_finds_the_line_by_key_not_by_number(self):
        """검사기 자체(가짜 설정) — 줄 번호가 아니라 키로 찾는다: 키 줄은 어디에 있어도 빠지고, 다른 키 아래 있는 같은 값은 남는다."""
        fake = "title: x\nlang: ko\n  email: someone@example.net\nnote: someone@example.net\n"
        rest = without_email_key_lines(fake)
        self.assertNotIn("email:", rest)
        self.assertIn("note: someone@example.net", rest)
        self.assertTrue(text_has(rest, mails=("someone@example.net",)))
        moved = "email: someone@example.net\ntitle: x\n"
        self.assertEqual(without_email_key_lines(moved), "title: x")
        self.assertFalse(text_has(without_email_key_lines(moved), mails=("someone@example.net",)))

    def test_the_scope_really_covers_the_memory_copies_the_old_briefs_and_the_test_values(self):
        scope = set(scope_files())
        for rel in (README, f"{MEMORY_DIR}/user-profile.md", f"{MEMORY_DIR}/dev-environment-notes.md", f"{MEMORY_DIR}/desktop-repo-chanceblog-desktop.md", "docs/SESSION_START.md",
                    "인수인계/도구/README.md", "인수인계/도구/work/p24nv_brief.md", "인수인계/도구/work/p25p0_report.md", "tests/test_validate_repo.py", "AGENTS.md"):
            self.assertTrue(rel in scope, f"훑는 범위에 없다: {rel}")
        self.assertGreater(len(scope), 300)                                       # 훑는 파일 목록이 비어 거짓 통과하지 않는다
        for rel in scope:
            self.assertFalse(rel.startswith(("_posts/", "assets/")), rel)

    def test_the_scope_covers_scripts_and_files_without_a_listed_extension(self):
        """SP-1 — 확장자 목록에 없던 종류(.sh 도구 스크립트·확장자 없는 파일·점 파일)도 훑는다. 이진 파일만 뺀다."""
        scope = set(scope_files())
        for rel in ("인수인계/도구/work/scratch/watch_heads2.sh", ".github/CODEOWNERS", ".github/skills/humanize/LICENSE", ".gitignore"):
            self.assertTrue(rel in scope, f"훑는 범위에 없다: {rel}")
        self.assertFalse(any(rel.endswith(BINARY_SUFFIXES) for rel in scope))
        for rel in (".design/chanceblog-editorial-landing.figcraft",):
            self.assertFalse(rel in scope, f"이진 파일은 뺀다: {rel}")
        for suffix in (".sh", ".ps1", ".bat", ".cmd", ".toml", ".cfg", ".ini", ".csv", ".xml"):
            self.assertFalse(suffix in BINARY_SUFFIXES, suffix)

    def test_the_scope_covers_every_top_level_folder_except_the_named_generated_ones(self):
        """QP-1 — 훑지도 빼지도 않은 최상위 폴더가 없다(새 폴더는 TREES 나 SKIP_DIRS 에 이름으로 적어야 한다). TREES 에서 폴더를 빼면 빨강."""
        folders = {name for name in os.listdir(ROOT) if (ROOT / name).is_dir()}
        self.assertEqual(sorted(folders - SKIP_DIRS - set(TREES)), [], "훑지도 빼지도 않은 최상위 폴더가 있다")
        self.assertEqual(sorted(set(TREES) - folders), [], "TREES 에 적힌 폴더가 없다")
        for name in ("docs", "인수인계", "tests", "scripts", "pipeline", ".github"):
            self.assertTrue(name in TREES, name)


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

    def test_a_personal_mailbox_alias_is_not_let_through_by_the_word_noreply(self):
        """SP-3 — 'noreply' 글자가 주소 어디에 있어도 통과시키던 구멍: 같은 편지함으로 가는 별칭(앞부분+noreply·noreply.앞부분 …)은 걸리고, 지역 부분이 정확히 noreply 인 보낸이 전용 주소와 GitHub 가림 주소는 통과한다."""
        local = "someone"
        for sample in (f"{local}+noreply@" + "gmail.com", f"noreply.{local}@" + "gmail.com", f"{local}.noreply@" + "gmail.com", f"noreply-{local}@" + "gmail.com", f"x{'noreply'}@" + "gmail.com",
                       f"{local}@" + "noreply-mail.example.org", f"{local}@" + "mynoreply.github.com", f"{local}@" + "noreply.github.com.evil.example"):
            with self.subTest(sample=masked(sample)):
                self.assertEqual(len(not_allowed(sample)), 1)
        for sample in ("noreply@" + "gmail.com", "no-reply@" + "service.test", "NoReply@" + "Anthropic.com", "donotreply@" + "service.test", f"12345+{local}@" + "users.noreply.github.com",
                       f"{local}@" + "noreply.github.com"):
            with self.subTest(sample=masked(sample)):
                self.assertEqual(not_allowed(sample), [])

    def test_ssh_remotes_action_versions_and_image_names_are_not_mistaken_for_mailboxes(self):
        """QP-2 — 문서에 흔한 비메일 표기가 시험을 헛빨갛게 하지 않는다(그래도 진짜 개인 메일은 그대로 걸린다)."""
        for sample in ("git clone git@" + "github.com:owner/repo.git", "uses: actions/checkout@" + "v5.1.0", "![로고](assets/icon@" + "2x.png)", "pages@" + "v4", "tool@" + "1.2.3"):
            with self.subTest(sample=sample[:14]):
                self.assertEqual(not_allowed(sample), [])
        self.assertEqual(len(not_allowed("문의 someone@" + "gmail.com 으로 git@" + "github.com:o/r.git")), 1)


class ValueComparisonTest(Base):
    """SP-4 — 값 비교의 정밀도(가짜 값으로 검사기 자체를 시험한다 — 진짜 값은 쓰지 않는다)."""

    NAME = "가나다"
    MAIL = "alias.test@example.net"

    def test_the_comparison_sees_through_case_plus_aliases_full_width_and_invisible_characters(self):
        for label, text in (("그대로", f"문의 {self.MAIL} 로"), ("대소문자", "문의 Alias.Test@Example.NET 로"), ("+별칭", "문의 alias.test+news@example.net 로"),
                            ("대문자 별칭", "문의 ALIAS.TEST+X@EXAMPLE.NET 로"), ("전각", "문의 ａｌｉａｓ．ｔｅｓｔ＠ｅｘａｍｐｌｅ．ｎｅｔ 로"),
                            ("폭 없는 글자", "문의 alias" + chr(0x200B) + ".test@example.net 로")):
            with self.subTest(label=label):
                self.assertTrue(text_has(text, mails=(self.MAIL,)), label)
        for label, text in (("그대로", f"이름 {self.NAME} 님"), ("폭 없는 글자", "이름 가" + chr(0x200B) + "나다 님"), ("폭 없는 글자 둘", "이름 " + chr(0x200D) + "가나" + chr(0xFEFF) + "다 님"),
                            ("풀어 쓴 자모", "이름 " + unicodedata.normalize("NFD", self.NAME) + " 님")):
            with self.subTest(label=label):
                self.assertTrue(text_has(text, names=(self.NAME,)), label)

    def test_the_comparison_does_not_match_other_people(self):
        for text in ("문의 alias.testx@example.net 로", "문의 alias.test@example.org 로", "문의 other.alias@example.net 로", "문의 alias.tes+t@example.net 로"):
            with self.subTest(text=text[:10]):
                self.assertFalse(text_has(text, mails=(self.MAIL,)), text)
        for text in ("이름 가나라 님", "이름 가 나다 님", "이름 가나 님"):
            with self.subTest(text=text[:8]):
                self.assertFalse(text_has(text, names=(self.NAME,)), text)

    def test_the_real_file_scan_uses_the_same_comparison(self):
        """실제 파일 훑기(file_has)가 같은 비교를 쓴다 — 문서에 있는 예시 메일을 대문자·'+별칭' 꼴로 물어도 찾고, 글 비교(text_has)와 같은 답을 낸다."""
        rel = "docs/COPILOT_GUIDE.md"
        for asked in ("old@example.com", "OLD@Example.COM", "old+tag@example.com"):
            with self.subTest(asked=asked):
                self.assertTrue(file_has(rel, mails=(asked,)))
                self.assertEqual(file_has(rel, mails=(asked,)), text_has(_read(rel), mails=(asked,)))
        self.assertFalse(file_has(rel, mails=("nobody.here@example.com",)))


class NeutralWordsTest(Base):
    def test_the_memory_copy_readme_states_the_role_word_rule(self):
        text = _read(README)
        for phrase in ("사람 이름·메일은 쓰지 않고 역할 말로 쓴다", "'운영자'", "'저장소 소유자'", "'운영자 계정'", "공개 이력의 과거분은 지우지 못한다", "고치지 않는 기록 사본", "유일한 예외"):
            self.has(text, phrase, README)                                         # 옛 4번 규칙(고치지 않는 기록 사본)은 그대로 있고, 새 규칙은 그 유일한 예외라고 말한다
        self.has(text, "효과는 앞으로의 파일에만 있다", README)                         # QP-1 — 정직한 한계 문구도 못박는다

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
        """QP-6 — test_validate_repo 의 글자 모양(튜플 한 줄·다음 시험 이름)이 아니라 구문 트리로 읽는다: 그 시험은 반복문 둘이고 하나는 assertTrue·하나는 assertFalse,
        일반 쌍(Human Author·human@example.com)이 '에이전트가 아님' 목록(둘째 반복문)에 있다."""
        tree = ast.parse(_read("tests/test_validate_repo.py"))
        func = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "test_only_real_copilot_identities_count_as_agents")
        loops = sorted((node for node in ast.walk(func) if isinstance(node, ast.For)), key=lambda node: node.lineno)
        self.assertEqual(len(loops), 2)

        def asserts(loop):
            return [call.func.attr for call in ast.walk(loop) if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr in ("assertTrue", "assertFalse")]

        def pairs(loop):
            return [tuple(item.value for item in element.elts) for element in loop.iter.elts
                    if isinstance(element, ast.Tuple) and all(isinstance(item, ast.Constant) for item in element.elts)]

        self.assertEqual(asserts(loops[0]), ["assertTrue"])
        self.assertEqual(asserts(loops[1]), ["assertFalse"])                       # 사람은 에이전트로 세지 않는다 — 단언은 그대로
        humans = pairs(loops[1])
        self.assertTrue(("Human Author", "human@example.com") in humans, "일반 쌍이 '에이전트가 아님' 목록에 없다")
        self.assertTrue(("t", "t@example.com") in humans, "원래 있던 쌍이 '에이전트가 아님' 목록에 없다")
        self.assertGreaterEqual(len(humans), 6)


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
        for phrase in ("효과는 앞으로의 파일에만 있다", "허용하는 값의 종류", "쪼개"):                      # QP-1·SP-2·SP-4 — 한계를 정직하게 적는다
            self.has(row, phrase, "결함 대장 D-392 행")


if __name__ == "__main__":
    unittest.main()
