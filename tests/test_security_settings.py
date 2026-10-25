"""비밀 유출 방지(.gitignore·비밀 패턴·마스킹)와 CODEOWNERS 일관성 테스트.

배경: 2026-10-18 `123.txt`(구글 API 키 형식의 한 줄)가 공개 저장소에 올라갔다가 70초 뒤 지워졌지만 이력에 남았다(D-30).
.gitignore 가 검증기(_FORBIDDEN_FILES)가 금지하는 파일 이름 규칙과 같은 범위를 막게 맞추고, 새 키 형식을 비밀 패턴이
알아보게 한다. (실제 비밀처럼 보이는 문자열은 소스에 쓰지 않고 런타임에 조합한다.)

한계: 이름 규칙은 `123.txt` 같은 임의 이름의 파일을 막지 못한다. 그런 파일은 이름이 아니라 내용을 보는 SEC-2(CI가 푸시 뒤에
잡는다)와 GitHub Secret scanning·Push protection(사용자 설정, docs/SECURITY_GUARDRAILS.md §5)에 기댄다.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
import pipeline.secret_patterns as secret_patterns
from pipeline.llm import mask
from pipeline.secret_patterns import SECRET_PATTERNS, find_secrets

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo  # noqa: E402

SHOULD_BE_IGNORED = [
    "client_secret.json", "client_secret_1234.apps.json", "token.json", "token.backup.json",
    ".env", ".env.local", ".env.production", ".env.staging", "credentials.json", "my-credentials-prod.json",
    "gcp-service-account.json", "service_account.json", "serviceAccountKey.json", "serviceaccount.json",
    "ServiceAccount.json", "server.pem", "private.key", "cert.p12", "cert.pfx",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
]
SHOULD_STAY_TRACKABLE = [".env.example", ".env.sample", ".env.template", "README.md", "generator.py",
                         "tokenizer.py", "keyboard.md", "pipeline/secret_patterns.py",
                         # 이름이 비슷하지만 검증기가 막지 않는 파일 — .gitignore 가 검증기보다 넓어지면 여기서 잡는다
                         ".envrc", "id_rsa.pub", "id_ed25519.pub", "cert.pem.txt", "private.key.md",
                         "client_secret_setup.md", "credentials-guide.md"]

# 검증기 _FORBIDDEN_FILES 항목(정규식 원문) -> 그 항목이 막는 대표 파일 이름(OR 의 갈래마다 하나 이상).
# 검증기에 항목이 추가·변경되면 여기에도 대표 이름을 적어야 테스트가 통과한다. 이름은 대소문자를 구분하는 Linux 기준으로 고른다.
FORBIDDEN_REPRESENTATIVES = {
    # OAuth 클라이언트 시크릿 파일
    r"^client_secret.*\.json$": ["client_secret.json", "client_secret_1234.apps.json"],
    # 토큰 파일
    r"^token.*\.json$": ["token.json", "token.backup.json"],
    # .env 파일(예시·샘플·템플릿 제외)
    r"^\.env(?!\.(?:example|sample|template)$)(\..+)?$": [".env", ".env.local", ".env.production", ".env.staging",
                                                          ".env.example.local"],
    # 키/인증서 파일
    r".*\.(pem|key|p12|pfx)$": ["server.pem", "private.key", "cert.p12", "cert.pfx"],
    # SSH 개인 키
    r"^id_(?:rsa|dsa|ecdsa|ed25519)$": ["id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"],
    # 자격 증명 JSON(Firebase 표준 이름 serviceAccountKey.json 포함)
    r".*(?:credentials|service[-_]?account).*\.json$": [
        "credentials.json", "my-credentials-prod.json", "gcp-service-account.json", "service_account.json",
        "serviceAccountKey.json", "serviceaccount.json", "ServiceAccount.json"],
}

# 자동 발행 봇이 만들어 `git add -A` 로 커밋하는 산출물의 대표 경로(실제 형식: _posts/<블로그 폴더>/<날짜>-<KR|EN>-<시각>.md 등)
BOT_OUTPUT_PATHS = [
    "_posts/KR - x/2026-10-25-KR-000000.md", "_posts/EN - x/2026-10-25-EN-000000.md", "_posts/2026-10-25-AI.md",
    "_posts/KR - 테크 이야기/2026-10-25-KR-000000.md",
    "_blogger_drafts/2026-10-25-0000-x.md", "_blogger_drafts/2026-10-25-0000-잠들기-전-3분.md",
    "assets/images/2026-10-25-x.png", "assets/x.jpg", "assets/x.svg",
    "history.json", "blogger_history.json", "posts.json", "pages.json", "feed.xml",
]


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def tracked_files():
    """저장소가 추적하는 파일 경로 전체. -z 로 읽어 한글 경로도 따옴표·이스케이프 없이 온전히 얻는다. 비면 실패로 본다."""
    res = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True)
    names = [n for n in res.stdout.decode("utf-8", "replace").split("\0") if n]
    if not names:
        raise AssertionError("git ls-files 결과가 비었습니다(git 저장소 안에서 실행해야 합니다): "
                             + res.stderr.decode("utf-8", "replace"))
    return names


def load_registry():
    return json.loads((ROOT / "pipeline" / "blogs.json").read_text(encoding="utf-8"))


def registry_output_paths():
    """레지스트리의 블로그 상태 경로(이력 파일·콘텐츠 폴더)로 봇 산출물 경로를 만든다 — 블로그가 늘면 자동으로 포함된다."""
    out = []
    for blog in load_registry()["blogs"]:
        state = blog.get("state") or {}
        if state.get("history"):
            out.append(state["history"])
        if state.get("content_dir"):
            out.append(state["content_dir"].rstrip("/") + "/sample/2026-10-25-sample.md")
    return out


def fake_tail(n):
    """새 형식 키의 꼬리 n자 가짜 값: 앞 6자는 어느 실제 키와도 무관한 임의 문자, 나머지는 x."""
    return ("Zq3xVw" + "x" * n)[:n]


class GitignoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        git(cls.root, "init", "-q")
        # 판정이 PC·파일시스템·전역 설정에 따라 달라지지 않게 고정한다.
        # - core.ignorecase=false: 대소문자를 구분하는 쪽(자동 발행이 도는 Linux 러너)의 의미로 판정한다. 기본값(true)인
        #   Windows·macOS 에서는 `Credentials.json` 같은 변형까지 걸려 플랫폼마다 결과가 갈린다. 그런 대소문자 변형은
        #   이 테스트의 범위 밖이다(검증기는 대소문자를 무시하지만 .gitignore 는 Linux 에서 구분한다).
        # - core.excludesFile: 사용자 전역 ignore 규칙이 섞이지 않게 빈 파일로 돌린다.
        empty = cls.root / ".git" / "empty_excludes"
        empty.write_text("", encoding="utf-8")
        git(cls.root, "config", "core.ignorecase", "false")
        git(cls.root, "config", "core.excludesFile", empty.as_posix())
        shutil.copy(ROOT / ".gitignore", cls.root / ".gitignore")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def ignored_among(self, names):
        """names 중 .gitignore 에 걸리는 것(입력 순서). NUL 구분 입출력이라 공백·한글 경로도 안전하다.
        --no-index: 추적 여부와 상관없이 '규칙만' 본다(추적 중인 파일도 규칙에 대 볼 수 있다)."""
        data = ("\0".join(names) + "\0").encode("utf-8")
        res = subprocess.run(["git", "check-ignore", "--no-index", "-z", "--stdin"], cwd=self.root,
                             input=data, capture_output=True)
        self.assertIn(res.returncode, (0, 1), res.stderr.decode("utf-8", "replace"))   # 128 = git 오류
        return [n for n in res.stdout.decode("utf-8").split("\0") if n]

    def test_files_matching_the_secret_name_rules_are_ignored(self):
        """검증기가 금지하는 이름 규칙(확장자·접두사)에 해당하는 비밀 파일은 .gitignore 에 걸린다.
        임의 이름의 파일(`123.txt` 등)은 이 방법으로 막을 수 없다 — 모듈 독스트링의 '한계' 참고."""
        ignored = set(self.ignored_among(SHOULD_BE_IGNORED))
        for name in SHOULD_BE_IGNORED:
            with self.subTest(name=name):
                self.assertIn(name, ignored, f"{name} 가 .gitignore 에 걸리지 않습니다")

    def test_normal_files_and_env_examples_stay_trackable(self):
        ignored = set(self.ignored_among(SHOULD_STAY_TRACKABLE))
        for name in SHOULD_STAY_TRACKABLE:
            with self.subTest(name=name):
                self.assertNotIn(name, ignored, f"{name} 이(가) 잘못 무시됩니다")

    def test_gitignore_and_validator_cover_the_same_files(self):
        """검증기가 '저장소에 있으면 오류'로 보는 이름은 모두 .gitignore 로도 막혀야 한다(둘이 어긋나지 않게)."""
        flagged = [n for n in SHOULD_BE_IGNORED
                   if validate_repo.check_forbidden_files([n])]
        self.assertEqual(sorted(flagged), sorted(SHOULD_BE_IGNORED))
        for name in SHOULD_STAY_TRACKABLE:
            self.assertEqual(validate_repo.check_forbidden_files([name]), [], name)

    def test_every_validator_forbidden_rule_has_representatives_that_gitignore_blocks(self):
        """검증기 _FORBIDDEN_FILES 의 항목마다 대표 파일 이름을 두고, .gitignore 가 그 이름을 실제로 무시하는지 대조한다.
        검증기에 항목이 추가·변경되면 FORBIDDEN_REPRESENTATIVES 에도 대표 이름을 적어야 통과한다(둘이 어긋나지 않게 강제)."""
        patterns = [rx.pattern for rx, _label in validate_repo._FORBIDDEN_FILES]
        self.assertEqual(sorted(patterns), sorted(FORBIDDEN_REPRESENTATIVES),
                         "검증기 _FORBIDDEN_FILES 와 이 테스트의 FORBIDDEN_REPRESENTATIVES 가 어긋납니다. 항목을 추가·변경했다면 "
                         "대표 파일 이름을 적고 .gitignore 에도 같은 범위의 규칙을 넣으세요")
        ignored = set(self.ignored_among([n for names in FORBIDDEN_REPRESENTATIVES.values() for n in names]))
        for rx, label in validate_repo._FORBIDDEN_FILES:
            names = FORBIDDEN_REPRESENTATIVES[rx.pattern]
            self.assertTrue(names, f"{label}: 대표 파일 이름이 없습니다")
            for name in names:
                with self.subTest(rule=label, name=name):
                    self.assertTrue(rx.match(name), f"{name} 은(는) 검증기 규칙 '{label}' 에 해당하지 않습니다")
                    self.assertIn(name, ignored, f"검증기가 막는 '{label}' 의 {name} 을(를) .gitignore 가 무시하지 않습니다")

    def test_tracked_files_are_not_ignored(self):
        """과도한 무시 규칙(`*.json`, `assets/`, `_posts/`, `.env*` 등)을 막는다. chanceblog.yml 은 `git add -A` 로 커밋하므로
        봇이 만드는 파일이 무시되면 오류 없이 '커밋할 변경 없음'으로 끝나 자동 발행이 조용히 멈춘다.
        추적 중인 파일 전체가 규칙에 걸리지 않아야 한다."""
        self.assertEqual(self.ignored_among(tracked_files()), [])

    def test_bot_output_paths_are_not_ignored(self):
        """봇이 앞으로 만들 산출물의 대표 경로(새 파일이라 추적 목록에 아직 없을 수 있다)가 무시되지 않아야 한다."""
        from_registry = registry_output_paths()
        self.assertTrue(from_registry, "pipeline/blogs.json 에서 상태 경로를 얻지 못했습니다")
        self.assertEqual(self.ignored_among(BOT_OUTPUT_PATHS + from_registry), [])


class NewKeyFormatTest(unittest.TestCase):
    LABEL = "Google API 키(새 형식)"

    @staticmethod
    def new_key():
        return "AQ." + fake_tail(50)                    # 꼬리 50자(총 53자), 'AQ.' 접두사

    def labels(self, text):
        return [label for label, _ in find_secrets(text)]

    def test_new_google_key_format_is_detected(self):
        found = find_secrets("key = " + self.new_key())
        self.assertEqual(found, [(self.LABEL, "AQ.Z***")])      # 값 전체는 돌려주지 않는다(앞 4자 + ***)

    def test_tail_length_boundary(self):
        """꼬리 39자는 놓치고 40자부터 탐지한다(너무 느슨하거나 엄격해지면 실패)."""
        for n, expected in ((39, False), (40, True), (41, True), (100, True)):
            with self.subTest(tail=n):
                self.assertEqual(self.labels("AQ." + fake_tail(n)), [self.LABEL] if expected else [])

    def test_tail_may_contain_hyphen_and_underscore(self):
        for name, tail in (("중간에 -·_", "Zq3xVw" + "-" * 3 + "_" * 3 + "x" * 38), ("전부 -", "-" * 40),
                           ("전부 _", "_" * 40), ("-_ 반복", "-_" * 20)):
            with self.subTest(tail=name):
                self.assertEqual(self.labels("AQ." + tail), [self.LABEL])

    def test_prefix_dot_is_literal(self):
        for sep in ("x", "_", "-", "0"):
            with self.subTest(sep=sep):
                self.assertEqual(self.labels("AQ" + sep + fake_tail(50)), [])

    def test_similar_text_is_not_flagged(self):
        for text in ("AQ.short", "an AQ. prefix alone", "prefixAQ." + "z" * 45, "tokenAQ" + "." * 3):
            with self.subTest(text=text):
                self.assertEqual(find_secrets(text), [])

    def test_character_just_before_the_prefix(self):
        """앞 글자가 영문자·숫자면 단어의 일부(FAQ. 등)라 제외하고, 한글·밑줄·기호 바로 뒤에 붙은 키는 탐지한다."""
        tail = fake_tail(50)
        for text, expected in (("key=AQ." + tail, True), ("(AQ." + tail + ")", True), ("my-AQ." + tail, True),
                               ("키는AQ." + tail, True), ("my_AQ." + tail, True),
                               ("FAQ." + tail, False), ("xAQ." + tail, False), ("1AQ." + tail, False)):
            with self.subTest(before=text[:text.index("AQ.")]):
                self.assertEqual(self.labels(text), [self.LABEL] if expected else [])

    def test_pattern_list_has_the_new_format_once(self):
        labels = [label for label, _ in SECRET_PATTERNS]
        self.assertEqual(labels.count(self.LABEL), 1)

    def test_no_tracked_file_matches_the_new_pattern(self):
        """오탐 점검: 추적 중인 모든 파일(한글 경로 포함)에서 새 패턴이 적중하지 않아야 한다."""
        rx = dict(SECRET_PATTERNS)[self.LABEL]
        hits, unread = [], []
        for rel in tracked_files():
            path = ROOT / rel
            try:
                if path.stat().st_size > 2_000_000:       # 검증기(MAX_TEXT_BYTES)도 건너뛰는 크기
                    continue
                text = path.read_bytes().decode("utf-8", "ignore")
            except OSError:
                unread.append(rel)
                continue
            if rx.search(text):
                hits.append(rel)
        self.assertEqual(unread, [], "추적 중인데 읽지 못한 파일이 있어 점검이 불완전합니다")
        self.assertEqual(hits, [])


class MaskTest(unittest.TestCase):
    @staticmethod
    def samples():
        """SECRET_PATTERNS 의 라벨마다 표본 1개. 실제 비밀과 무관한 가짜 값을 런타임에 조합한다."""
        return {
            "Google API 키": "AIza" + "x" * 35,
            "Google API 키(새 형식)": "AQ." + fake_tail(50),
            "Google OAuth 클라이언트 시크릿": "GOCSPX-" + "z" * 24,
            "Google refresh token": "1//0" + "c" * 45,
            "Google access token": "ya29." + "b" * 40,
            "GitHub 토큰": "ghp_" + "a" * 36,
            "GitHub PAT": "github_pat_" + "a" * 40,
            "개인 키 블록": "-----BEGIN " + "RSA PRIVATE KEY" + "-----",
            "Slack 토큰": "xox" + "b-" + "1" * 12,
            "AWS 액세스 키": "AKIA" + "Q" * 16,
            "sk- 형식 API 키": "sk-" + "a" * 40,
            "client_secret JSON 값": '"client_' + 'secret": "' + "k" * 12 + '"',
            "키/토큰 할당": 'password: "' + "k" * 24 + '"',
        }

    def test_every_pattern_label_has_a_sample_and_mask_hides_it_exactly(self):
        samples = self.samples()
        # 패턴이 늘거나 이름이 바뀌면 표본도 맞춰야 통과한다(일부만 확인하고 넘어가지 못하게)
        self.assertEqual(sorted(samples), sorted(label for label, _ in SECRET_PATTERNS))
        for label, secret in samples.items():
            with self.subTest(label=label):
                self.assertIn(label, [found for found, _ in find_secrets(secret)])    # 표본이 정말 그 패턴에 걸린다
                # 값이 조금이라도 남으면(앞·뒤 일부만 가려지면) 실패하도록 결과 전체를 비교한다
                self.assertEqual(mask(f"request failed: {secret} (retry later)"), "request failed: *** (retry later)")

    def test_new_format_key_is_masked_completely_whatever_its_shape(self):
        for name, tail in (("40자", fake_tail(40)), ("50자", fake_tail(50)), ("100자", fake_tail(100)),
                           ("-·_ 포함", "Zq3xVw" + "-" * 3 + "_" * 3 + "x" * 38)):
            with self.subTest(tail=name):
                self.assertEqual(mask(f"request failed: AQ.{tail} (retry later)"), "request failed: *** (retry later)")
        self.assertEqual(mask(f"키는AQ.{fake_tail(50)}. 끝"), "키는***. 끝")      # 한글 바로 뒤, 뒤따르는 마침표는 남긴다

    def test_mask_leaves_near_misses_unchanged(self):
        for text in ("AQ." + fake_tail(39), "FAQ." + fake_tail(50), "AQx" + fake_tail(50)):
            with self.subTest(text=text[:8]):
                self.assertEqual(mask(text), text)

    def test_mask_keeps_ordinary_text_and_old_key_value_rule(self):
        self.assertEqual(mask("모델 호출 실패: 429 Too Many Requests"), "모델 호출 실패: 429 Too Many Requests")
        self.assertNotIn("abc123", mask("url?key=abc123&x=1"))

    def test_mask_accepts_exceptions(self):
        self.assertIn("boom", mask(RuntimeError("boom")))


def codeowners_match(pattern, path):
    """CODEOWNERS 줄의 경로 패턴이 저장소 안 파일 경로 path 에 해당하는지. 이 저장소가 쓰는 문법(앞 '/', 끝 '/', '*')만 지원한다."""
    body = re.escape(pattern.strip("/")).replace(r"\*\*", ".*").replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
    head = "" if pattern.startswith("/") else "(?:.*/)?"
    tail = "/.*" if pattern.endswith("/") else "(?:/.*)?"
    return re.fullmatch(head + body + tail, path) is not None


class CodeownersTest(unittest.TestCase):
    PATH = ROOT / ".github" / "CODEOWNERS"
    OWNER = "@shine88pc"
    # 자동화·보안 경계(T2, docs/CHARTER.md §5). 하나라도 빠지면 실패한다(광고 표면은 아래에서 레지스트리와 대조한다).
    REQUIRED = ["/.github/", "/.github/editorial/edit-spec.yml", "/pipeline/", "/scripts/", "/generator.py",
                "/blogger_generator.py", "/requirements*.txt", "/tests/", "/AGENTS.md", "/CLAUDE.md", "/GEMINI.md",
                "/.gitignore", "/docs/SECURITY_GUARDRAILS.md", "/docs/CHARTER.md", "/posts.json", "/feed.xml"]

    def rules(self):
        out = []
        for raw in self.PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            out.append(line.split())
        return out

    def test_file_exists_and_every_rule_is_owned_by_the_repository_owner(self):
        """소유자는 저장소 소유자 하나로 고정한다(오타·다른 사람·소유자 없는 줄을 모두 잡는다)."""
        self.assertTrue(self.PATH.exists())
        owners = set()
        for parts in self.rules():
            with self.subTest(rule=parts[0]):
                self.assertEqual(parts[1:], [self.OWNER], f"{parts[0]} 의 소유자는 {self.OWNER} 하나여야 합니다")
            owners.update(parts[1:])
        self.assertEqual(owners, {self.OWNER})

    def test_required_paths_are_owned(self):
        owned = {parts[0] for parts in self.rules()}
        for path in self.REQUIRED:
            with self.subTest(path=path):
                self.assertIn(path, owned)

    def test_ad_surface_paths_match_the_registry(self):
        """광고 표면이 늘거나 줄면 CODEOWNERS 도 같이 고치게 한다(레지스트리와 어긋나지 않게)."""
        reg = load_registry()
        protected = [b for b in reg["blogs"] if b.get("ad_surface")][0]["protected_paths"]
        owned = {parts[0] for parts in self.rules()}
        for path in protected:
            with self.subTest(path=path):
                self.assertIn("/" + path, owned)

    def test_no_pattern_is_listed_twice(self):
        """같은 패턴을 두 번 쓰면 마지막으로 일치한 줄이 이긴다 — 앞 줄의 소유자를 덮어쓰는 통로가 된다."""
        paths = [parts[0] for parts in self.rules()]
        self.assertEqual(sorted({p for p in paths if paths.count(p) > 1}), [])

    def test_no_syntax_that_github_does_not_support(self):
        """GitHub CODEOWNERS 가 지원하지 않는 문법(부정 '!', 문자 범위 '[ ]', 이스케이프 '\\#')은 쓰지 않는다.
        써도 오류 없이 무시되거나 다른 뜻이 되어 소유자 지정이 조용히 빠진다."""
        for parts in self.rules():
            path = parts[0]
            with self.subTest(rule=path):
                self.assertFalse(path.startswith("!"), "부정(!) 규칙은 지원되지 않습니다")
                self.assertNotIn("[", path)
                self.assertNotIn("]", path)
                self.assertNotIn("\\", path)

    def test_path_matcher_helper(self):
        """아래 '존재' 검사가 쓰는 도우미가 CODEOWNERS 의 의미(루트 기준·디렉터리·와일드카드)대로 동작하는지."""
        for pattern, path, expected in (
                ("/requirements*.txt", "requirements-dev.txt", True), ("/requirements*.txt", "docs/requirements-x.txt", False),
                ("/pipeline/", "pipeline/llm.py", True), ("/pipeline/", "pipelines/llm.py", False),
                ("/.gitignore", ".gitignore", True), ("/.gitignore", "docs/.gitignore", False),
                ("/docs/CHARTER.md", "docs/CHARTER.md", True), ("/docs/CHARTER.md", "docs/CHARTER.mdx", False),
                ("/.github/editorial/edit-spec.yml", ".github/editorial/edit-spec.yml", True)):
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(codeowners_match(pattern, path), expected)

    def test_every_rule_points_at_something_that_exists(self):
        """저장소에 없는 경로를 가리키는 줄(오타·삭제된 파일)을 잡는다. 와일드카드는 1개 이상 일치해야 한다.
        예외: 레지스트리의 광고 표면은 아직 없는 파일(ads.txt)도 미리 지정해 둘 수 있다."""
        tracked = tracked_files()
        reserved = {"/" + p for b in load_registry()["blogs"] for p in b.get("protected_paths", [])}
        for parts in self.rules():
            path = parts[0]
            if path in reserved:
                continue
            with self.subTest(rule=path):
                self.assertTrue(any(codeowners_match(path, f) for f in tracked),
                                f"CODEOWNERS 의 {path} 에 해당하는 추적 파일이 없습니다(오타이거나 지워진 경로)")

    def test_documents_mentioned_in_comments_exist(self):
        text = self.PATH.read_text(encoding="utf-8")
        mentioned = sorted(set(re.findall(r"docs/[A-Za-z0-9_./-]+\.md", text)))
        self.assertIn("docs/SECURITY_GUARDRAILS.md", mentioned)
        for rel in mentioned:
            with self.subTest(doc=rel):
                self.assertTrue((ROOT / rel).is_file(), f"CODEOWNERS 주석이 존재하지 않는 문서를 가리킵니다: {rel}")

    def test_header_comment_states_the_conditions_for_enforcement(self):
        """주석이 사실과 어긋나지 않게: 봇 우회 조건과 '미검증' 표시가 있고, 단정('켜는 순간 멈춘다')이 없으며,
        1인 소유 저장소에서 본인 PR을 본인이 승인할 수 없다는 한계를 적는다."""
        text = self.PATH.read_text(encoding="utf-8")
        for needle in ("github-actions", "우회", "미검증", "본인이 연 PR을 본인이 승인할 수 없"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        self.assertNotIn("켜는 순간", text)

    def test_no_liquid_syntax_in_codeowners_comments(self):
        text = self.PATH.read_text(encoding="utf-8")
        self.assertNotIn("{{", text)
        self.assertNotIn("{%", text)


class SecretPatternsDocTest(unittest.TestCase):
    IMPORT_RX = re.compile(
        r"^\s*(?:from\s+pipeline\.secret_patterns\s+import\b|import\s+pipeline\.secret_patterns\b"
        r"|from\s+pipeline\s+import\b[^\n]*\bsecret_patterns\b|from\s+\.secret_patterns\s+import\b"
        r"|from\s+\.\s+import\b[^\n]*\bsecret_patterns\b)", re.M)

    def test_docstring_lists_exactly_the_modules_that_import_it(self):
        """독스트링의 소비처 목록이 실제 import 와 같아야 한다(소비처가 늘면 독스트링도 고치게)."""
        sources = [*ROOT.glob("*.py"), *(ROOT / "pipeline").rglob("*.py"), *(ROOT / "scripts").rglob("*.py")]
        consumers = sorted(
            rel for rel in (p.relative_to(ROOT).as_posix() for p in sources)
            if rel != "pipeline/secret_patterns.py"
            and self.IMPORT_RX.search((ROOT / rel).read_text(encoding="utf-8")))
        self.assertGreaterEqual(len(consumers), 3, consumers)      # 검증기, 이슈 수정 사후 검증, mask()
        mentioned = sorted(set(re.findall(r"(?:scripts|pipeline)/[\w./]+\.py", secret_patterns.__doc__)))
        self.assertEqual(mentioned, consumers)


if __name__ == "__main__":
    unittest.main()
