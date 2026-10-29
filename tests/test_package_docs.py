"""초안 패키지(티스토리·네이버) 코드와 문서의 일치 시험: 코드표·분류표·크론·한도·원칙이 문서와 어긋나면 실패한다."""
import re
import unittest

import yaml

import _bootstrap  # noqa: F401
from pipeline import registry
from pipeline import run as run_mod
from pipeline.publishers import issue_package as ip

REAL = _bootstrap.ROOT


def read(rel):
    return (REAL / rel).read_text(encoding="utf-8")


def section(text, start, end):
    return text[text.index(start):text.index(end, text.index(start) + len(start))]


def cron_of(name):
    data = yaml.safe_load(read(f".github/workflows/{name}.yml"))
    return (data.get("on") or data.get(True))["schedule"][0]["cron"]


class ResultCodeDocsTest(unittest.TestCase):
    CODES = ("PACKAGE_BACKLOG", "PACKAGE_FAILED", "AUTH_CHECK_UNSUPPORTED")
    ALSO_IN_THE_GUIDE = ("HISTORY_WRITE_FAILED",)          # package 경로도 내는 기존 코드(이슈는 만들어졌는데 이력 쓰기 실패)

    def test_every_new_code_is_emitted_by_the_runner(self):
        source = read("pipeline/run.py")
        for code in self.CODES + self.ALSO_IN_THE_GUIDE:
            self.assertRegex(source, rf'skip_line\("{code}"', code)

    def test_the_architecture_table_puts_each_code_on_the_right_level(self):
        text = section(read("docs/ARCHITECTURE.md"), "## 4-1.", "## 4-2.")
        rows = {line.split("|")[1].strip(): line for line in text.splitlines() if line.startswith("| ") and re.match(r"^\| (정상 건너뜀|경고|실패|설정 오류) \|", line)}
        self.assertIn("`PACKAGE_BACKLOG`", rows["정상 건너뜀"])
        self.assertRegex(rows["정상 건너뜀"], r"\|\s*0\s*\|")
        self.assertIn("`PACKAGE_FAILED`", rows["실패"])
        self.assertRegex(rows["실패"], r"\|\s*1\s*\|")
        for code in ("`PACKAGE_FAILED`", "`AUTH_CHECK_UNSUPPORTED`", "`SECRETS_MISSING`", "`INVALID_PUBLISH`"):
            self.assertIn(code, rows["설정 오류"])
        self.assertRegex(rows["설정 오류"], r"\|\s*\*\*2\*\*\s*\|")

    def test_the_failure_table_matches_the_runner_classification(self):
        text = section(read("docs/ARCHITECTURE.md"), "| 초안 패키지 실패 분류(`reason=`)", "**이슈 만들기 요청은 한 번만 보낸다")
        documented = {}
        for line in text.splitlines():
            match = re.match(r"^\| `(\w+)` \|.*\|\s*(\d)\s*\|[^|]*\|$", line)
            if match:
                documented[match.group(1)] = int(match.group(2))
        self.assertEqual(documented, {code: run_mod._package_exit(code) for code in run_mod.PACKAGE_FAILURES})
        self.assertEqual(set(documented), {"auth_failed", "too_long", "invalid_draft", "network", "bad_response", "api_error", "unexpected"})
        self.assertEqual(run_mod.PACKAGE_CONFIG_CODES, {"auth_failed", "too_long", "invalid_draft"})
        self.assertEqual(run_mod.PACKAGE_BUILD_CODES, {"too_long", "invalid_draft"})

    def test_the_operator_guide_lists_every_code_for_both_workflows(self):
        guide = read("docs/ACTIONS_GUIDE.md")
        part = section(guide, "### 6-12.", "### 6-13.")
        for code in self.CODES + self.ALSO_IN_THE_GUIDE + ("TOPIC_BLOCKED", "SECRETS_MISSING", "INVALID_PUBLISH", "DAILY_CAP", "MODE_OFF", "PAUSED", "GATE_REJECTED", "NO_TOPIC"):
            self.assertIn(f"`{code}`", part, code)
        for reason in run_mod.PACKAGE_FAILURES:
            self.assertIn(f"`{reason}`", part, reason)
        self.assertIn("6-12", section(guide, "### 6-13.", "## 7."))

    def test_the_idempotency_and_create_once_rules_are_described_as_they_are(self):
        """검증 지적 N1·N2: 이슈 만들기는 한 번만 보내고 모호하면 멈춘다(바깥에서 확인 뒤 다시 만들지 않는다). 표지 멱등은 같은 글의 재시도만 막는다
        (이력 파일이 사라진 날의 다른 글까지 막는다는 낡은 문장이 없어야 한다)."""
        arch = read("docs/ARCHITECTURE.md")
        self.assertNotIn("이력 파일이 사라진 날의 재실행도 막는다", arch)
        self.assertNotIn("없을 때만 다시 만든다", arch)
        self.assertIn("같은 글을 다시 올리려는 재시도만 막는다", section(arch, "## 5.", "## 6."))
        part = section(arch, "**이슈 만들기 요청은 한 번만 보낸다", "글을 어디까지 보내는지")
        for needle in ("모호하면 멈춘다", "한 번만", "만들어졌을 수 있으니", "4xx", "같은 글을 다시 올리려는"):
            self.assertIn(needle, part, needle)
        guard = next(line for line in read("docs/SECURITY_GUARDRAILS.md").splitlines() if line.startswith("| G-L9 |"))
        for needle in ("자동 재시도하지 않는다", "다시 만들지 않고 멈춘다", "제어"):
            self.assertIn(needle, guard, needle)
        register = read("docs/DEFECT_REGISTER.md")
        self.assertIn("모호한 실패는 다시 만들지 않고 멈춘다", register)

    def test_the_new_status_is_documented_and_counted(self):
        arch = read("docs/ARCHITECTURE.md")
        self.assertIn("`package_issued`", section(arch, "## 5.", "## 6."))
        self.assertIn("package_issued", run_mod.COUNTED_STATUSES)


class LimitsAndPolicyDocsTest(unittest.TestCase):
    def test_the_documented_limits_are_the_codes_limits(self):
        arch = read("docs/ARCHITECTURE.md")
        self.assertEqual(ip.OPEN_DRAFT_LIMIT, 3)
        self.assertEqual((ip.BODY_LIMIT, ip.BODY_BUDGET, ip.TITLE_SHOWN), (65536, 60000, 60))
        self.assertIn("3건 이상", arch)
        self.assertIn("65,536자", arch)
        self.assertIn("60,000자", arch)
        self.assertIn("글 제목 60자", arch)
        guide = read("docs/ACTIONS_GUIDE.md")
        self.assertIn("3건 이상", section(guide, "### 3-19.", "## 4."))

    def test_the_documented_crons_are_the_workflows_crons(self):
        arch = section(read("docs/ARCHITECTURE.md"), "### B-2.", "### C. 또 하나의 Jekyll")
        guide = read("docs/ACTIONS_GUIDE.md")
        self.assertEqual((cron_of("tistory"), cron_of("naver")), ("20 5 * * *", "20 6 * * *"))
        for cron in (cron_of("tistory"), cron_of("naver")):
            self.assertIn(f"`{cron}`", arch)
        for name, hour in (("tistory", "05:20"), ("naver", "06:20")):
            self.assertRegex(guide, rf"\| \[{registry.PACKAGE_PLATFORMS[name]}\] 초안 패키지 만들기 \| 매일 {hour} \|")
        self.assertIn("cron `20 5 * * *`(UTC)", guide)
        self.assertIn("cron `20 6 * * *`(UTC)", guide)

    def test_the_account_information_principle_is_written_where_the_operator_and_the_next_ai_look(self):
        guard = read("docs/SECURITY_GUARDRAILS.md")
        row = next(line for line in guard.splitlines() if line.startswith("| G-S7 |"))
        for word in registry.ACCOUNT_SECRET_WORDS:
            self.assertIn(word, row, word)
        self.assertIn("저장하지도 처리하지도 않는다", row)
        # N7: 구조적 보장은 역할 제한이고 이름 검사는 보조(포함 검사라 우회 철자는 통과한다)
        self.assertIn("구조적 보장은 이 채널의 시크릿 역할이 `llm_api_key` **뿐**", row)
        self.assertIn("보조", row)
        self.assertIn("우회 철자", row)
        self.assertNotIn("구조로 보장한다", row)
        self.assertIn("| G-L9 |", guard)
        for needle in ("영(0)폭 공백", "펜스", "gates.sanitize_html", "too_long", "자동 재시도하지 않는다"):
            self.assertIn(needle, next(line for line in guard.splitlines() if line.startswith("| G-L9 |")), needle)
        self.assertIn("REG-1(초안 패키지)", guard)
        self.assertIn("G-S7", read("docs/ARCHITECTURE.md"))
        self.assertIn("G-S7", read("HANDLER.md"))

    def test_the_registry_checklist_for_the_operator_exists_and_names_the_real_files(self):
        arch = section(read("docs/ARCHITECTURE.md"), "### B-2.", "### C. 또 하나의 Jekyll")
        self.assertIn("블로그 주소·주제를 받으면 해야 할 일 체크리스트", arch)
        for needle in ("프로필", "프롬프트", "`channel`", "`entrypoint: pipeline/run.py`", "연습 실행", "비공개 시험 글", "`ads: \"off\"`"):
            self.assertIn(needle, arch, needle)
        # N9: 첫 실제 항목을 넣을 때 함께 고칠 시험, 새 이력 파일의 공개 방지
        for needle in ("test_the_real_registry_has_exactly_the_two_package_blogs", "tests/test_registry.py", "`_config.yml`", "`exclude`", "T3",
                       "새 블로그의 이력 파일(`state.history`, 루트의 `*.json`)을 `_config.yml`의 `exclude`에 더한다"):         # 지시 문장 자체를 못 박는다(변이 EXT527)
            self.assertIn(needle, arch, needle)
        real = (REAL / "tests" / "test_package_registry.py").read_text(encoding="utf-8")
        self.assertIn("def test_the_real_registry_has_exactly_the_two_package_blogs", real)         # 문서가 가리키는 시험이 실제로 있다
        # N11: 공개 저장소의 이슈는 공개 페이지, 주소는 소독하지 않는다
        for needle in ("공개 저장소", "검색 색인", "주소(URL)는 소독하지 않는다"):
            self.assertIn(needle, arch, needle)

    def test_the_defects_and_the_observation_list_are_recorded(self):
        register = read("docs/DEFECT_REGISTER.md")
        self.assertRegex(register, r"(?m)^\| \*\*D-73\*\* \|")
        self.assertRegex(register, r"(?m)^\| \*\*D-74\*\* \|")
        self.assertIn("초안 패키지(D-73·D-74) 병합 직후", register)

    def test_the_operator_guide_has_the_copy_and_publish_steps(self):
        part = section(read("docs/ACTIONS_GUIDE.md"), "### 3-19.", "## 4.")
        for needle in ("복사용 제목", "HTML", "직접 겪은 일·판단", "이슈를 닫습니다", "`폐기`", "미확인", "G-C10"):
            self.assertIn(needle, part, needle)

    def test_the_two_workflow_names_are_in_the_architecture_workflow_table(self):
        arch = section(read("docs/ARCHITECTURE.md"), "### 2-1.", "### 외부 소비자 계약")
        for file, name in (("tistory.yml", "[티스토리] 초안 패키지 만들기"), ("naver.yml", "[네이버] 초안 패키지 만들기")):
            self.assertTrue(any(f"`{file}`" in line and f"`{name}`" in line and line.startswith("|") for line in arch.splitlines()), file)


if __name__ == "__main__":
    unittest.main()
