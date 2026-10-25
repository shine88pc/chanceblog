"""비밀 유출 방지(.gitignore·비밀 패턴·마스킹)와 CODEOWNERS 일관성 테스트.

배경: 2026-10-18 `123.txt`(구글 API 키 형식의 한 줄)가 공개 저장소에 올라갔다가 70초 뒤 지워졌지만 이력에 남았다(D-30).
어떤 이름의 파일이든 실수로 올라가지 않게 .gitignore 를 검증기(_FORBIDDEN_FILES)와 같은 범위로 맞추고,
새 키 형식을 비밀 패턴이 알아보게 한다. (실제 비밀처럼 보이는 문자열은 소스에 쓰지 않고 런타임에 조합한다.)
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
from pipeline.llm import mask
from pipeline.secret_patterns import SECRET_PATTERNS, find_secrets

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo  # noqa: E402

SHOULD_BE_IGNORED = [
    "client_secret.json", "client_secret_1234.apps.json", "token.json", "token.backup.json",
    ".env", ".env.local", ".env.production", "credentials.json", "my-credentials-prod.json",
    "gcp-service-account.json", "service_account.json", "server.pem", "private.key", "cert.p12", "cert.pfx",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
]
SHOULD_STAY_TRACKABLE = [".env.example", ".env.sample", ".env.template", "README.md", "generator.py",
                         "tokenizer.py", "keyboard.md", "pipeline/secret_patterns.py"]


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


class GitignoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        git(cls.root, "init", "-q")
        shutil.copy(ROOT / ".gitignore", cls.root / ".gitignore")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def ignored(self, name):
        return git(self.root, "check-ignore", "-q", name).returncode == 0

    def test_secret_looking_files_are_ignored_whatever_their_name(self):
        for name in SHOULD_BE_IGNORED:
            with self.subTest(name=name):
                self.assertTrue(self.ignored(name), f"{name} 가 .gitignore 에 걸리지 않습니다")

    def test_normal_files_and_env_examples_stay_trackable(self):
        for name in SHOULD_STAY_TRACKABLE:
            with self.subTest(name=name):
                self.assertFalse(self.ignored(name), f"{name} 이(가) 잘못 무시됩니다")

    def test_gitignore_and_validator_cover_the_same_files(self):
        """검증기가 '저장소에 있으면 오류'로 보는 이름은 모두 .gitignore 로도 막혀야 한다(둘이 어긋나지 않게)."""
        flagged = [n for n in SHOULD_BE_IGNORED
                   if validate_repo.check_forbidden_files([n])]
        self.assertEqual(sorted(flagged), sorted(SHOULD_BE_IGNORED))
        for name in SHOULD_STAY_TRACKABLE:
            self.assertEqual(validate_repo.check_forbidden_files([name]), [], name)


class NewKeyFormatTest(unittest.TestCase):
    @staticmethod
    def new_key():
        return "AQ." + "Ab8RN6" + "x" * 44          # 총 53자, 'AQ.' 접두사

    def test_new_google_key_format_is_detected(self):
        found = find_secrets("key = " + self.new_key())
        self.assertEqual([label for label, _ in found], ["Google API 키(새 형식)"])
        self.assertTrue(found[0][1].endswith("***"))      # 값 전체는 돌려주지 않는다

    def test_similar_text_is_not_flagged(self):
        for text in ("AQ.short", "an AQ. prefix alone", "prefixAQ." + "z" * 45, "tokenAQ" + "." * 3):
            with self.subTest(text=text):
                self.assertEqual(find_secrets(text), [])

    def test_pattern_list_has_the_new_format_once(self):
        labels = [label for label, _ in SECRET_PATTERNS]
        self.assertEqual(labels.count("Google API 키(새 형식)"), 1)

    def test_no_tracked_file_matches_the_new_pattern(self):
        listing = git(ROOT, "ls-files").stdout.splitlines()
        rx = dict(SECRET_PATTERNS)["Google API 키(새 형식)"]
        hits = []
        for rel in listing:
            path = ROOT / rel
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if rx.search(text):
                hits.append(rel)
        self.assertEqual(hits, [])


class MaskTest(unittest.TestCase):
    def test_mask_hides_every_shared_pattern(self):
        samples = [
            "AIza" + "x" * 35,
            "AQ." + "Ab8RN6" + "y" * 44,
            "GOCSPX-" + "z" * 24,
            "ghp_" + "a" * 36,
            "ya29." + "b" * 40,
            "1//0" + "c" * 45,
        ]
        for secret in samples:
            with self.subTest(prefix=secret[:6]):
                shown = mask(f"request failed: {secret} (retry later)")
                self.assertNotIn(secret, shown)
                self.assertIn("***", shown)

    def test_mask_keeps_ordinary_text_and_old_key_value_rule(self):
        self.assertEqual(mask("모델 호출 실패: 429 Too Many Requests"), "모델 호출 실패: 429 Too Many Requests")
        self.assertNotIn("abc123", mask("url?key=abc123&x=1"))

    def test_mask_accepts_exceptions(self):
        self.assertIn("boom", mask(RuntimeError("boom")))


class CodeownersTest(unittest.TestCase):
    PATH = ROOT / ".github" / "CODEOWNERS"
    REQUIRED = ["/.github/", "/pipeline/", "/scripts/", "/.github/editorial/edit-spec.yml", "/generator.py",
                "/tests/"]

    def rules(self):
        out = []
        for raw in self.PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            out.append(line.split())
        return out

    def test_file_exists_and_every_rule_has_a_valid_owner(self):
        self.assertTrue(self.PATH.exists())
        for parts in self.rules():
            with self.subTest(rule=parts[0]):
                self.assertGreaterEqual(len(parts), 2)
                self.assertTrue(all(re.fullmatch(r"@[A-Za-z0-9][A-Za-z0-9-]*", owner) for owner in parts[1:]))

    def test_required_paths_are_owned(self):
        owned = {parts[0] for parts in self.rules()}
        for path in self.REQUIRED:
            with self.subTest(path=path):
                self.assertIn(path, owned)

    def test_ad_surface_paths_match_the_registry(self):
        """광고 표면이 늘거나 줄면 CODEOWNERS 도 같이 고치게 한다(레지스트리와 어긋나지 않게)."""
        reg = json.loads((ROOT / "pipeline" / "blogs.json").read_text(encoding="utf-8"))
        protected = [b for b in reg["blogs"] if b.get("ad_surface")][0]["protected_paths"]
        owned = {parts[0] for parts in self.rules()}
        for path in protected:
            with self.subTest(path=path):
                self.assertIn("/" + path, owned)

    def test_no_liquid_syntax_in_codeowners_comments(self):
        text = self.PATH.read_text(encoding="utf-8")
        self.assertNotIn("{{", text)
        self.assertNotIn("{%", text)


if __name__ == "__main__":
    unittest.main()
