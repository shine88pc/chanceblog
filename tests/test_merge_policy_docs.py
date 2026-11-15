"""조건부 승인형 AI 병합 정책의 문서·정적 시험 — `docs/AI_MERGE_POLICY.md` 와 `pipeline/merge_policy.py` 가 서로, 그리고 운영자 원문의 목록과 어긋나지 않는지.

문서의 글이 옳은지는 시험이 알 수 없어 사람이 본다. 여기서는 낱말·번호·표·예시 글·이름을 코드와 대조하고(문서의 목록 = 시험에 글자 그대로 적어 둔 운영자 원문 = 모듈 상수), 문서 규칙(물결표·웹 주소·Liquid·
로컬 경로 없음)과 모듈의 성질 — 표준 라이브러리 `re`·`dataclasses` 만, 네트워크·파일 쓰기·환경 변수·시간·난수 없음, 어디서도 import 되지 않음(지금은 꺼져 있음) — 을 정적으로 지킨다. 미연결은 파일 이름 글자 검색으로 지키고, 이름 글자만 허용된 한 파일(품질 Gate 연결 격리 시험)은 줄이 아니라 구문 트리(ast)로 지킨다.
또 블로그 저장소의 기본 거부 목록(SITE_INTERNAL_ENTRIES)을 실제 `_config.yml` 의 exclude 와 사이트 정리 시험의 상수에 맞춰 보고(읽기만 한다), 사이트로 내보내지는 실제 파일이 하나도 AI 병합 대상이 아닌지 본다.
이 시험은 네트워크·파일 쓰기를 하지 않는다.
"""
import ast
import fnmatch
import re
import unittest

import _bootstrap
from pipeline import merge_policy as mp
from pipeline.secret_patterns import find_secrets

ROOT = _bootstrap.ROOT
DOC_PATH = ROOT / "docs" / "AI_MERGE_POLICY.md"
MODULE_PATH = ROOT / "pipeline" / "merge_policy.py"
TEST_PATHS = (ROOT / "tests" / "test_merge_policy.py", ROOT / "tests" / "test_merge_policy_docs.py")
DOC = DOC_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")
REGISTER = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8").replace("\r\n", "\n")

# ---- 운영자 결정 원문의 목록(글자 그대로 — 모듈 상수와 별개로 적어 둔다) -----------------------------------------------------------------------------------
OPERATOR_ONLY_12 = ("GitHub Actions Workflow", "광고·AdSense·ads.txt", "공개 게시물과 고정 페이지", "PIPELINE_PAUSE", "발행 모드와 발행 재개", "Provider 활성화",
                    "API Key·Secret·Credential", "의존성 추가", "데이터 삭제·Migration", "자동 게시 활성화", "외부 비용 발생 기능", "Main Branch 보호 설정")
PRECONDITIONS_8 = ("승인된 병합 번호와 PR 일치", "승인 이후 Commit 추가 없음", "검사 전체 통과", "독립 검증 통과", "충돌 없음", "변경 범위가 승인 설명과 일치", "비밀정보 노출 없음", "원복 방법 확인")
REJECTED_5 = ("확인했습니다", "진행하세요", "좋아 보입니다", "기본값대로", "다음 단계 진행")
SCOPES_7 = ("일반 프로그램 코드", "일반 UI", "시험", "문서", "로컬 저장·조회", "오류 수정", "접근성·성능 개선")
EXPLANATION_6 = ("무엇을 바꾸나요?", "왜 필요한가요?", "사용할 때 무엇이 달라지나요?", "위험은 무엇인가요?", "검사 결과", "되돌리기")
COMPLETION_7 = ("병합 번호", "PR 번호", "병합된 Commit", "실제 반영된 변화", "main 검사 결과", "이상 유무", "원복 Commit 또는 원복 방법")
TRIAL_6 = ("승인받은 PR만 병합", "승인 후 변경 없음", "main 검사 전체 통과", "원복 발생 0건", "다른 PR 오병합 0건", "운영자 전용 경로 변경 0건")
SECTION_TITLES = ("상태와 한눈에", "운영자 결정 요지", "흐름 7단계", "쉬운 병합 설명 양식", "승인 방식", "병합 직전 재확인 8조건", "범위", "병합 방식 제한", "사후 처리", "첫 운영 3건 시험과 즉시 중지",
                  "켜는 방법", "이 문서를 바꾸는 법")
FLOW = "AI 가 PR 작성 → 검사와 독립 검증 → 쉬운 병합 설명 발송 → 운영자가 병합 번호를 명시해 승인 → AI 가 승인된 PR 병합 → main 사후 검사 → 병합 완료 알림"
ANSWERS = ("앱을 닫아도 작성 중인 초안을 다시 열 수 있도록 저장 기능을 추가합니다.", "현재는 앱을 닫으면 초안이 사라집니다.", "저장 버튼과 저장된 초안 목록이 추가됩니다.",
           "저장 실패나 손상 가능성을 막기 위해 원자적 저장과 복구 시험을 수행했습니다.", "전체 검사와 독립 검증을 통과했고 기존 복사 기능에는 변화가 없습니다.",
           "문제가 발생하면 M075 병합만 되돌리면 이전 상태로 복구됩니다.")
EXAMPLE_PATHS = ["src/chanceblog_desktop/content/drafts_store.py", "tests/test_drafts_store.py"]
URL_RX = re.compile("https?" + ":" + "//")
INVISIBLE = [chr(code) for code in list(range(0x200B, 0x2010)) + list(range(0x202A, 0x202F)) + list(range(0x2060, 0x2065)) + list(range(0x2066, 0x206A)) + [0xFEFF]]
ATTRIBUTION = "총괄(AI)의 보수적 판단 D-347 — 운영자 확인 대기"


def sections():
    """번호 → 절의 글(`## n. 제목` 줄부터 다음 `## ` 앞까지)."""
    found = {}
    for part in re.split(r"(?m)^(?=## \d+\. )", DOC):
        head = re.match(r"## (\d+)\. (.+)", part)
        if head:
            found[int(head.group(1))] = part
    return found


SECTIONS = sections()


def subsection(label):
    """`### 5-2. …` 소절의 글(다음 `## `·`### ` 앞까지)."""
    start = DOC.index("### " + label + ". ")
    following = re.search(r"(?m)^#{2,3} ", DOC[start + 5:])
    return DOC[start:start + 5 + following.start()] if following else DOC[start:]


def table_rows(text):
    """글 안의 첫 표의 본문 행들(머리·구분 행은 뺀다)."""
    rows = []
    for line in text.split("\n"):
        if re.match(r"^\|[-| ]+\|$", line):                                   # 머리 아래 구분 행은 건너뛴다
            continue
        if line.startswith("|"):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        elif rows:
            break
    return rows[1:]


def bullets(text, indent=r""):
    return re.findall(r"(?m)^" + indent + r"- (.+)$", text)


def example_classification():
    return mp.classify_change("desktop", EXAMPLE_PATHS, "", dict.fromkeys(mp.DECLARED_REQUIRED, False))


class DocShapeTest(unittest.TestCase):
    def test_the_title_and_the_twelve_sections_are_in_order(self):
        self.assertTrue(DOC.startswith("# 조건부 승인형 AI 병합 정책\n"))
        heads = re.findall(r"(?m)^## (\d+)\. (.+)$", DOC)
        self.assertEqual([int(number) for number, _title in heads], list(range(1, 13)))
        self.assertEqual(tuple(title for _number, title in heads), SECTION_TITLES)
        self.assertEqual(set(SECTIONS), set(range(1, 13)))

    def test_the_status_is_off_and_turning_it_on_is_a_separate_operator_merge(self):
        quote = DOC.split("\n## 1.")[0]
        self.assertIn("꺼져 있음", quote)
        self.assertIn("꺼져 있음", SECTIONS[1])
        self.assertIn("**상태: 꺼져 있음.**", SECTIONS[1])
        self.assertIn("AI 는 아무것도 병합하지 않습니다", SECTIONS[1])
        for number in (1, 2, 11):
            self.assertIn("별도 병합 요청", SECTIONS[number], number)
        for number in (1, 2, 11, 12):
            self.assertIn("운영자가 직접 병합", SECTIONS[number], number)
        for number in (1, 8):
            self.assertIn("main 직접 push 금지", SECTIONS[number], number)
        self.assertIn("지금(꺼져 있음)은 4·5단계 대신 운영자가 PR 화면에서 직접 병합합니다", SECTIONS[3])

    def test_the_flow_is_the_operators_seven_steps(self):
        self.assertIn(FLOW, SECTIONS[3])
        rows = table_rows(SECTIONS[3])
        self.assertEqual(len(rows), 7)
        self.assertEqual([row[0].split(".")[0] for row in rows], [str(number) for number in range(1, 8)])
        self.assertEqual(len(re.findall(r"(?m)^\d+\. ", SECTIONS[2])), 10)

    def test_the_text_follows_the_document_rules(self):
        self.assertNotIn(chr(126), DOC)
        self.assertIsNone(URL_RX.search(DOC))
        self.assertNotIn("{{", DOC)
        self.assertNotIn("{%", DOC)
        self.assertNotIn("](", DOC)                                                            # 링크 없이 백틱으로 이름만 적는다
        self.assertNotRegex(DOC, r"[A-Za-z]:[/\\]")                                            # 로컬 경로 없음
        self.assertNotIn("SDI" + "_USER", DOC)
        self.assertNotIn("\r", DOC)
        self.assertIsNone(re.search("[" + "".join(INVISIBLE) + "]", DOC))                                           # 보이지 않는 글자 없음
        self.assertEqual(find_secrets(DOC), [])

    def test_the_tables_have_equal_columns(self):
        for block in re.findall(r"((?:^\|.*\|\n)+)", DOC, re.M):
            counts = {line.count("|") for line in block.splitlines()}
            self.assertEqual(len(counts), 1, block[:80])


class ListsMatchTest(unittest.TestCase):
    """문서의 목록 = 운영자 원문(이 파일에 글자 그대로) = 모듈 상수 — 셋 모두 같다."""

    def test_the_explanation_table_has_the_six_items(self):
        labels = tuple(row[0] for row in table_rows(subsection("4-1")))
        self.assertEqual(labels, EXPLANATION_6)
        self.assertEqual(labels, mp.EXPLANATION_ITEMS)

    def test_the_rejected_phrases_are_the_five_in_section_five(self):
        listed = tuple(bullets(subsection("5-2")))
        self.assertEqual(listed, REJECTED_5)
        self.assertEqual(listed, mp.REJECTED_PHRASES)
        self.assertIn("M075 승인", subsection("5-1"))

    def test_the_precondition_table_has_the_eight_in_order(self):
        rows = table_rows(SECTIONS[6])
        self.assertEqual([row[0] for row in rows], [str(number) for number in range(1, 9)])
        self.assertEqual(tuple(row[1] for row in rows), PRECONDITIONS_8)
        self.assertEqual(tuple(row[1] for row in rows), tuple(label for _code, label in mp.PRECONDITIONS))

    def test_the_allowed_scope_list_is_the_seven(self):
        listed = tuple(bullets(subsection("7-1")))
        self.assertEqual(listed, SCOPES_7)
        self.assertEqual(listed, mp.AI_MERGE_SCOPES)

    def test_the_operator_only_table_has_the_twelve_in_order(self):
        rows = table_rows(subsection("7-2"))
        self.assertEqual([row[0] for row in rows], [str(number) for number in range(1, 13)])
        self.assertEqual(tuple(row[1] for row in rows), OPERATOR_ONLY_12)
        self.assertEqual(tuple(row[1] for row in rows), mp.OPERATOR_ONLY_LABELS)

    def test_the_completion_notice_items_are_the_seven_in_section_nine(self):
        listed = tuple(bullets(SECTIONS[9], r"[ \t]+"))
        self.assertEqual(listed, COMPLETION_7)
        self.assertEqual(listed, mp.COMPLETION_ITEMS)

    def test_the_trial_criteria_are_the_six_in_section_ten(self):
        listed = tuple(bullets(SECTIONS[10]))
        self.assertEqual(listed, TRIAL_6)
        self.assertEqual(listed, tuple(label for _key, label in mp.TRIAL_CRITERIA))
        self.assertIn("즉시 중지", SECTIONS[10])
        self.assertIn("기록이 3건 미만이어도", SECTIONS[10])
        for word in (mp.TRIAL_CONTINUE, mp.TRIAL_PENDING, mp.TRIAL_STOP):
            self.assertIn("`" + word + "`", SECTIONS[10])

    def test_the_rule_words_of_the_classification_are_all_in_the_scope_section(self):
        for word in mp.DOCUMENTED_RULE_WORDS:
            with self.subTest(word=word):
                self.assertIn("`" + word + "`", SECTIONS[7])

    def test_the_safety_and_external_connection_rules_are_documented_in_full(self):
        """총괄(AI)의 보수적 판단(결함 D-347)으로 더한 두 표시의 규칙 낱말·이름 목록·모듈·스킴·예시 주소·문서 확장자·도메인·셸 확장자가 §7-6 에 빠짐없이 있다."""
        section = subsection("7-6")
        words = (mp.SAFETY_GUARD_WORDS + mp.SAFETY_GUARD_DOCS + mp.SAFETY_GUARD_FILES + mp.SAFETY_GUARD_DIRS + mp.EXTERNAL_MODULES + mp.EXTERNAL_SCHEMES + mp.EXAMPLE_HOSTS + mp.DOC_SUFFIXES
                 + mp.GENERIC_TLDS + mp.FILE_NAME_TLDS + mp.SHELL_SUFFIXES + tuple("." + name for name in mp.EXAMPLE_TOP_LEVELS))
        for word in words:
            with self.subTest(word=word):
                self.assertIn("`" + word + "`", section)
        self.assertEqual(len(mp.EXTERNAL_MODULES), 51)

    def test_the_site_default_deny_entries_are_documented_in_full(self):
        section = subsection("7-8")
        for name in mp.SITE_INTERNAL_ENTRIES:
            with self.subTest(name=name):
                self.assertIn("`" + name + "`", section)
        self.assertIn("21개", section)

    def test_the_extra_flags_and_the_policy_files_are_named(self):
        for code in mp.EXTRA_CODES:
            self.assertIn("`" + code + "`", SECTIONS[7])
        for name in mp.POLICY_SELF_FILES[1:]:
            self.assertIn("`" + name + "`", DOC)
            self.assertTrue((ROOT / name).is_file(), name)
        self.assertTrue((ROOT / mp.POLICY_SELF_FILES[0]).is_file())
        self.assertIn("이 정책의 문서·모듈·시험 자체", SECTIONS[7])

    def test_the_fact_keys_and_the_verification_keys_are_listed(self):
        rows = table_rows(SECTIONS[6][SECTIONS[6].index("확인에 쓰는 값"):])
        self.assertEqual(tuple(row[0].strip("`") for row in rows), mp.FACT_KEYS)
        self.assertEqual(len(rows), 23)
        for key in mp.VERIFICATION_KEYS:
            self.assertIn("`" + key + "`", SECTIONS[6])

    def test_each_fact_key_names_the_condition_that_uses_it(self):
        owners = {"approved_number": 1, "approved_pr_number": 1, "pr_number": 1, "pr_title_label": 1, "consumed_numbers": 1, "approved_head_sha": 2, "current_head_sha": 2, "current_tree": 4,
                  "approved_paths": 6, "current_paths": 6, "checks": 3, "independent_verification": 4, "has_conflict": 5, "classification": 6, "secret_findings": 7, "rollback_method": 8,
                  "repo_kind": 6, "changed_text": 6, "head_sha_at_approval": 2, "required_checks": 3, "pr_state": 1, "pr_draft": 1, "previous_merge_main_check": 3}
        rows = table_rows(SECTIONS[6][SECTIONS[6].index("확인에 쓰는 값"):])
        self.assertEqual({row[0].strip("`"): int(row[2]) for row in rows}, owners)

    def test_the_merge_methods_are_listed(self):
        for word in (mp.ALLOWED_MERGE_METHOD,) + mp.FORBIDDEN_MERGE_METHODS:
            self.assertIn("`" + word + "`", SECTIONS[8])

    def test_the_declared_items_are_named_in_the_operators_words(self):
        for code in mp.DECLARED_REQUIRED:
            self.assertIn(dict(mp.OPERATOR_ONLY_ITEMS)[code], subsection("7-3"))

    def test_the_approval_example_and_guidance_are_the_modules(self):
        self.assertEqual(mp.APPROVAL_EXAMPLE, "M075 승인")
        self.assertIn(mp.AI_MERGE_OFF_NOTICE, DOC)
        self.assertIn(mp.AI_MERGE_ON_NOTICE, DOC)
        self.assertIn(mp.APPROVAL_OFF_LINE, DOC)
        sentence = "병합 승인은 병합 번호와 함께 한 줄로 M075 승인 처럼 보내 주세요."
        self.assertIn(sentence, mp.check_approval_text("확인했습니다").guidance.replace("`", ""))
        self.assertIn(sentence, DOC.replace("`", ""))

    def test_the_post_merge_states_and_actions_are_documented(self):
        for state in mp.POST_MERGE_STATES:
            self.assertIn("`" + state + "`", SECTIONS[9])
        for name in ("evaluate_post_merge", "PostMergeDecision", "previous_merge_main_check"):
            self.assertIn("`" + name + "`", SECTIONS[9])
        for name in ("ApprovalRecord", "explained_head_sha", "head_sha_at_approval", "approved_head_sha"):
            self.assertIn("`" + name + "`", subsection("5-4"))


class OperatorStatementsPinnedTest(unittest.TestCase):
    """운영자 결정의 문장 단위 약속이 문서에서 빠지지 않았다 — 낱말만이 아니라 약속(누가·무엇을·언제)을 못박는다."""

    PINS = (
        (1, "지금까지처럼 병합은 운영자만 합니다"),
        (2, "독자 판단 자동 병합이 아닙니다"),
        (2, "전문용어가 아니라 사용자가 체감할 변화 중심으로"),
        (4, "항목마다 8자 이상의 한글 문장(한글 4자 이상)이어야 하고"),
        (5, "이 절은 켜진 뒤의 동작이며 지금은 꺼져 있어 승인 글을 보내도 AI 는 병합하지 않습니다"),
        (5, "앞뒤 공백과 줄 바꿈, 끝의 마침표 하나는 허용합니다"),
        (5, "`m075 승인` 처럼 M 이 소문자여도 `M075` 로 읽습니다"),
        (5, "같은 승인으로 다른 PR 을 병합하거나"),
        (5, "새 커밋이 더해지거나 변경 파일 목록이 달라지거나 번호가 맞지 않으면 기존 승인은 **무효**"),
        (5, "새 설명과 새 승인을 받아야 합니다"),
        (5, "**승인 때의 머리 커밋(`approved_head_sha`)은 쉬운 병합 설명을 보냈을 때의 머리 커밋**"),
        (5, "옛 설명을 승인한 셈이라 그 승인은 **무효**"),
        (6, "빠진 값은 실패"),
        (6, "이 함수가 스스로 다시 계산하는 것은 변경 분류와 머리 커밋 일치뿐이고 나머지 값은 모양만 확인합니다"),
        (6, "그래서 값은 GitHub 에서 직접 읽는 신뢰할 수 있는 워크플로가 만든 것이어야 합니다(§11-3)"),
        (6, "하나라도 실패하면 병합하지 않고"),
        (6, "건너뜀·중립·취소는 통과가 아님"),
        (6, "10자 이상의 구체적인 문장"),
        (6, "넘겨받은 분류를 믿지 않고 지금 변경 파일과 바뀐 줄로 분류를 다시 계산해도 걸리지 않음"),
        (6, "쉬운 설명을 보냈을 때·승인 글이 도착했을 때·지금의 머리 커밋(40자 해시) 셋이 모두 같음"),
        (6, "필수 검사)의 이름 목록이 비어 있지 않고 모두 결과에 있으며 `success`"),
        (7, "12항목에 하나도 안 걸리고"),
        (7, "하나라도 참이거나 미응답이면 운영자 전용"),
        (7, "선언이 거짓이어도 운영자 전용"),
        (7, "**바뀐 줄의 글(`changed_text`)은 추가된 줄과 지운 줄을 둘 다** 넣습니다"),
        (7, "12항목 목록을 넓힌 것이 아니라 **12항목 밖의 표시**"),
        (7, "**이 목록은 저장소가 바뀔 때마다 유지가 필요하다.**"),
        (7, "AI 가 읽고 따르는 규칙 문서 18개도 운영자 전용입니다"),
        (7, "(줄 끝의 줄 바꿈만 떼고 경로 자체는 다듬지 않습니다)"),
        (7, "용어 사전(`docs/GLOSSARY.md`)은 규칙이 아니라 사전이라 넣지 않았습니다"),
        (7, "- **운영자 확인 대기 항목**: 용어 사전 `docs/GLOSSARY.md` 를 규칙 문서 목록에 넣을지"),
        (7, "`openssl s_client`·`socat`·`aria2c`·`npm publish`·`docker push`·`pip install` 같은 것도 따로 잡지 않습니다"),
        (7, "'모름' 문구는 목록에 있는 문구와 **정확히 같을 때만** 거절합니다"),
        (7, "**어느 구간이든 앞뒤에 공백(유니코드 공백 포함)이 있는 경로**"),
        (7, "맨 앞의 공백 한 칸이 `docs` 같은 내부 폴더 이름처럼 보이게 하던 우회를 이렇게 막습니다"),
        (7, "**키가 모두 변경 파일 목록에 있어야 하고 변경 파일마다 키가 있어야**"),
        (7, "이름 안에 `requirements` 가 든 `dev-requirements.txt`·`pip-requirements.in` 도"),
        (7, "**문서 파일의 낱말 규칙(총괄(AI)의 판단 — 운영자 확인 대기)**"),
        (7, "문서 파일(`.md`·`.rst`·`.txt`·`.adoc`)의 바뀐 줄에는 낱말 규칙(키·토큰·비밀번호 낱말·`secrets.` 참조·`Authorization` 헤더·`PIPELINE_PAUSE`·삭제 명령과 마이그레이션 낱말·접속 낱말)을 적용하지 않습니다"),
        (7, "**강한 비밀 모양**"),
        (7, "**시험 폴더도 면제하지 않습니다.**"),
        (7, "**예시 주소는 걸리지 않습니다**"),
        (7, "바뀐 파일이 **모두** 시험·문서일 때만 건너뜁니다"),
        (7, "루프백(`localhost`)은 걸립니다"),
        (7, "**AI 병합 가능 7종은 목록이 아니라 '12항목과 표시에 안 걸리면' 이라는 거절 목록으로 구현했습니다.**"),
        (7, "이름은 대소문자까지 같아야 내부 항목입니다"),
        (7, "- **가져오는 순간 실행되는 파일**(`conftest.py`·`sitecustomize.py`·`tests/_bootstrap.py`·`pipeline/__init__.py`)은 안전 장치 목록에 넣지 않았습니다"),
        (8, "운영자 PC 의 Git 자격 증명"),
        (8, "강제 push 도 금지입니다"),
        (9, "아래 7가지를 반드시 담습니다"),
        (9, "추가 변경을 자동 병합하지 않습니다"),
        (9, "되돌리기 위한 요청과 쉬운 원인 설명을 **먼저**"),
        (9, "되돌리는 PR 도 운영자가 병합합니다"),
        (10, "**즉시 중지 규칙:** 문제가 한 건이라도 발생하면 AI 병합을 **즉시 중지**하고"),
        (10, "기존 운영자 직접 병합 방식으로 돌아갑니다"),
        (10, "위반은 없지만 3건 미만이거나, main 검사 결과를 아직 모름"),
        (11, "워크플로 파일(`.github/`)"),
        (11, "**독립 검증 기록의 출처와 위조 방지**(켜기 전의 필수 조건)"),
        (11, "`parse_explanation` 은 **지금 만들지 않았습니다**"),
        (11, "**필수 검사의 이름 집합**(`required_checks`)"),
        (11, "**이름을 바꾼 파일의 옛 경로와 새 경로를 모두**, **지운 파일**까지 넣습니다"),
        (11, "**추가된 줄과 지운 줄을 둘 다** 넣습니다"),
        (11, "**쉬운 설명을 보냈을 때의 것**(`approved_head_sha`)과 **승인 글이 도착했을 때의 것**(`head_sha_at_approval`)"),
        (11, "**병합을 호출하기 직전마다** 병합 이력 전체로 `evaluate_trial` 을 돌려"),
        (11, "- **값의 출처**(켜기 전의 필수 조건):"),
        (11, "`repo_kind`·`changed_text`·`checks`·`required_checks`·`independent_verification`·`has_conflict`·`secret_findings`·`pr_state`·`pr_draft`·`previous_merge_main_check` 는 GitHub 에서 직접 읽는 신뢰할 수 있는 워크플로가 만든 값이어야 합니다"),
        (11, "PR 작성자나 PR 쪽 파일이 채울 수 있으면 안 됩니다"),
        (12, "운영자 결정으로만"),
        # ---- 5차(WIP 10): P3 재검증 반영 — 읽지 못한 파일의 글·첫 3건의 범위·정직하게 고친 한계 ----
        (4, "표준 양식 글을 만드는 `render_explanation` 에서는 사람이 손으로 `아니오` 를 적을 수 없고"),
        (4, "**다만 손으로 쓴 설명 글을 `explanation_problems` 로 점검하는 경로에서는**"),
        (4, "그 경로의 마지막 방어선은 독립 검증자입니다"),
        (5, "번호와 `승인` 사이는 공백(칸) 또는 탭 하나 이상입니다"),
        (7, "(§7-8 의 내부 항목 목록과 §7-6 의 `tests/` 면제만 대소문자까지 같아야 합니다)"),
        (7, "**빈 글은 바뀐 줄이 정말 없는 파일(이름만 바뀐 파일·빈 파일 등)에만** 넣습니다"),
        (7, "**바뀐 줄을 읽지 못한 파일**(diff 가 너무 커서 GitHub 가 내용을 주지 않는 파일·바이너리 파일 등)의 글은 빈 글이 아니라 **`None` 으로** 넘기고"),
        (7, "`None` 이나 키가 없는 것은 입력 오류라 운영자 전용입니다"),
        (7, "읽지 못한 코드 파일을 빈 글로 넘기면 그 파일의 내용 규칙"),
        (7, "**낱말·이름 목록에 걸린 시험만 막습니다.**"),
        (7, "목록의 장치를 지키는 전용 시험이라도 이름에 낱말이 없고 목록에도 없으면 걸리지 않습니다"),
        (7, "특히 `pipeline/__init__.py` 는 pipeline 의 다른 모든 파일보다 먼저 실행되므로"),
        (7, "하위 폴더의 `AGENTS.md`·`CLAUDE.md`·`GEMINI.md`(예: `pipeline/CLAUDE.md`·`tests/AGENTS.md`)도 지금은 걸리지 않습니다"),
        (7, "검증자 P 의 권고는 `pipeline/drafts.py` 와 `pipeline/shadow_run.py` 를 운영자 전용으로 두는 쪽입니다"),
        (7, "- **목록의 장치를 지키는 전용 시험은 걸리지 않습니다.**"),
        (7, "이름 목록에 올라 있는 시험은 `tests/test_site_cleanup.py` 하나뿐이고"),
        (7, "- `explanation_problems` 는 사람이 손으로 쓴 설명 글의 점검표가 실제 분류와 같은지 알지 못합니다."),
        (7, "- 경로의 역슬래시는 `/` 로 바꿔 읽습니다."),
        (7, "역슬래시가 든 경로를 입력 오류로 처리하는 편이 더 단단하다는 것이 검증자 P 의 의견입니다"),
        (7, "`runpy.run_path`·`compile`·`subprocess`·`os.system`·`ctypes`·`pickle.loads`"),
        (7, "`render_explanation` 은 `ai_merge_enabled` 가 정확히 참(`True`)이 아니어도"),
        (7, "점검은 대문자 `M` 만 봅니다"),
        (7, "`ValueError` 를 낼 수 있고"),
        (7, "`RuntimeError` 를 내는 특이한 객체를 넘기면"),
        (7, "결함 번호 `D-346`(문서 머리)과 `D-347` 이 이 문서·모듈 주석·시험 상수에 글자로 적혀 있습니다"),
        (7, "병합할 때 다른 묶음과 번호가 겹쳐 번호를 바꿔야 하면 정책 파일(운영자가 직접 병합하는 변경)도 함께 고쳐야 합니다"),
        (7, "이 파일은 줄이 아니라 **구문 트리**(코드를 문법 구조로 풀어 읽은 것)로 지킵니다"),
        (7, "정책 모듈과 같은 이름의 파일이 다른 폴더에 하나라도 있으면 실패합니다"),
        (7, "`%`·`format`·`join` 으로 이은 글자와, 이미 불러온 모듈을 `sys.modules` 에서 찾는 식의 우회는 정적으로 못 막습니다"),
        (11, "변경 파일마다 키가 있어야 합니다. **읽지 못한 파일(너무 큰 diff·바이너리라 GitHub 가 내용을 주지 않는 파일 등)의 글은 `None` 으로 넘깁니다**"),
        (11, '**빈 글(`""`)은 바뀐 줄이 정말 없을 때만** 넣습니다'),
        (11, "**변경 파일 목록은 모든 페이지를 읽어 PR 의 변경 파일 수와 같을 때만 씁니다.**"),
        (11, "파일 수가 맞지 않거나 상한을 넘으면 운영자 전용으로 둡니다"),
        (11, "(확인 필요 — AI 가 GitHub 에 직접 접속해 확인하지 못했습니다)"),
        (11, "- **켜기 전 필수 결정**(운영자와 정할 것 — 정하기 전에는 켜지 않습니다):"),
        (11, "첫 3건은 경로가 모두 `.py`·`.md`·`tests/` 인 변경으로 한정합니다"),
        (11, "이 한정은 코드가 확인하지 않으므로 켜는 변경이 지켜야 합니다"),
        (11, "**켜는 변경 전에 운영자와 정합니다**"),
        (11, "(검증자 P 의 권고는 운영자 전용)"),
        (7, "코드가 입력 오류로 돌려주는 '글이 없으면 빈 글을 넣어야 합니다' 문구도 바뀐 줄이 정말 없는 파일을 뜻하며 읽지 못한 파일을 가리키지 않습니다"),
        (7, "정책 모듈과 그 시험 두 개 밖에는 이름을 쓰는 파일이 없게 합니다"),
        (7, "그런 시험을 AI 가 약하게 고친 채 병합될 수 있다는 뜻입니다"),
        (7, "이 빈틈을 닫을지는 켜기 전에 운영자와 정합니다"),
        (7, "기본값을 어떻게 둘지는 켜기 전에 운영자와 정합니다"),
        (7, "이 사실에 기대고 있습니다"),
        (7, "영향은 설명 글의 병합 방식 문구뿐이고"),
        (7, "손으로 쓴 글의 `아니오` 가 맞는지는 독립 검증자가 분류와 대조해야 합니다"),
        (7, "코드는 빈 글을 '읽어 보니 바뀐 줄이 없다' 는 결과로만 믿습니다"),
        (11, "코드도 문서도 아닌 파일(예: `pipeline/profiles/` 의 설정 파일)도 통과할 수 있고"),
        (11, "시험 기록(`evaluate_trial`)에도 PR 종류 칸이 없습니다"),
        (11, "정하지 않았으므로 지금은 §7-7 에 적은 대로 걸리지 않습니다"),
    )

    def test_the_conservative_judgement_is_attributed_to_the_ai_and_waits_for_the_operator(self):
        """두 표시와 이 절의 규칙은 운영자 결정이 아니라 총괄(AI)의 판단이고 운영자 확인을 기다린다 — 운영자가 정한 것처럼 읽히는 표현이 없다."""
        self.assertGreaterEqual(SECTIONS[7].count(ATTRIBUTION), 3)
        self.assertIn(ATTRIBUTION, subsection("7-6").split("\n")[0])
        for code in ("safety_guard", "external_connection"):
            rows = [line for line in subsection("7-5").split("\n") if line.startswith("| `" + code + "`")]
            self.assertEqual(len(rows), 1, code)
            self.assertIn(ATTRIBUTION, rows[0])
        for old in ("운영자 결정 " + "D-347", "총괄 " + "11-15", "운영자 결정의 " + "보수적"):                       # 이 시험 파일 자신이 낡은 표현을 담지 않게 이어 붙여 적는다
            self.assertNotIn(old, DOC)
        for old in ("총괄의 " + "보수적 판단", "운영자 결정 " + "D-347"):
            self.assertNotIn(old, MODULE_SOURCE)
            for path in TEST_PATHS:
                self.assertNotIn(old, path.read_text(encoding="utf-8"), path.name)
        self.assertIn("총괄(AI)의 보수적 판단", MODULE_SOURCE)
        self.assertIn("운영자 확인 대기", MODULE_SOURCE)

    def test_the_intro_names_the_one_test_file_that_may_name_the_module(self):
        """머리 인용문의 '어디서도 쓰이지 않습니다'는 구문 트리 시험이 지키는 한 파일의 예외(품질 Gate 연결 격리 시험)를 숨기지 않고 적는다(I10)."""
        quote = DOC.split("\n## 1.")[0]
        self.assertIn("어디서도 쓰이지 않습니다. 예외는 하나뿐입니다:", quote)
        for rel in NAMED_ONLY_EXPECTED:
            self.assertIn("`" + rel + "`", quote)
        self.assertIn("**글자로만** 적습니다(가져오지도 부르지도 않으며, 시험이 그 파일의 코드 구조를 읽어 지킵니다 — §7-7)", quote)

    def test_the_reading_guide_tells_the_operator_which_sections_to_read(self):
        quote = DOC.split("\n## 1.")[0]
        self.assertIn("**운영자가 읽을 곳:** §1·§4·§5-1에서 §5-3까지·§7-5에서 §7-7까지(운영자 확인 대기 항목이 있는 곳)·§10·§11-3 의 '켜기 전 필수 결정' 만 읽으시면 됩니다.", quote)
        for label in ("5-1", "5-2", "5-3"):
            self.assertIn("### " + label + ". ", DOC)

    def test_section_five_says_first_that_it_is_the_behaviour_after_turning_it_on(self):
        lines = SECTIONS[5].split("\n")
        self.assertEqual(lines[0], "## 5. 승인 방식")
        self.assertEqual(lines[2], "이 절은 켜진 뒤의 동작이며 지금은 꺼져 있어 승인 글을 보내도 AI 는 병합하지 않습니다.")

    def test_sections_six_eight_nine_and_ten_say_first_that_they_describe_the_behaviour_after_turning_it_on(self):
        """§5 처럼 §6·§8·§9·§10 도 머리에 '켜진 뒤의 동작이며 지금은 꺼져 있다' 한 줄을 둔다(I-N7)."""
        for number, title in ((6, "병합 직전 재확인 8조건"), (8, "병합 방식 제한"), (9, "사후 처리"), (10, "첫 운영 3건 시험과 즉시 중지")):
            with self.subTest(section=number):
                lines = SECTIONS[number].split("\n")
                self.assertEqual(lines[0], "## %d. %s" % (number, title))
                self.assertEqual(lines[1], "")
                self.assertTrue(lines[2].startswith("이 절은 켜진 뒤의 동작이며 지금은 꺼져 있습니다."), (number, lines[2]))
        self.assertIn("main 에 직접 push 하지 않는다는 원칙은 꺼져 있는 지금도 그대로입니다", SECTIONS[8].split("\n")[2])

    def test_the_first_tree_word_is_explained(self):
        first = DOC.index("트리")
        self.assertTrue(DOC[first:].startswith("트리 — 변경 내용 전체의 지문)"), DOC[first:first + 30])

    def test_each_promise_is_in_its_section(self):
        for number, phrase in self.PINS:
            with self.subTest(section=number, phrase=phrase):
                self.assertIn(phrase, SECTIONS[number])

    def test_the_design_memo_names_the_constraints_of_the_workflow_way(self):
        memo = subsection("11-2")
        for phrase in ("AI 세션은 병합 자격 증명을 갖지 않습니다", "승인 시점의 머리 SHA", "후속 워크플로", "`workflow_dispatch`", "소유자 계정의 글에서만", "기본 가지의 것만 실행하고 PR 쪽 파일은 읽기만",
                       "병합된 PR 이력", "트리 해시", "확인 필요"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, memo)

    def test_the_known_limits_name_what_the_rules_cannot_know(self):
        limits = subsection("7-7")
        for phrase in ("거절 목록으로 구현했습니다", "글의 **모양**만 봅니다", "`pipeline/profiles/`", "`conftest.py`", "`sitecustomize.py`", "`tests/_bootstrap.py`", "`pipeline/__init__.py`",
                       "문자열을 쪼개 붙이거나", "선언 6항목은 사람이 정하는 값", "하나를 지워도 결과가 같습니다", "총괄(AI)의 판단 — 운영자 확인 대기", "`docs/GLOSSARY.md`", "`pipeline/shadow_run.py`",
                       "`pipeline/drafts.py`", "`openssl s_client`", "`docker push`", "`'row.id'`", "`'pipeline.store'`", "정확히 같을 때만", "이름 없는 무작위 문자열 모양의 비밀",
                       "`pipeline/usercustomize.py`", "하위 폴더의 `AGENTS.md`", "전용 시험은 걸리지 않습니다", "`tests/test_site_cleanup.py` 하나뿐", "역슬래시", "`runpy.run_path`", "`pickle.loads`",
                       "`ai_merge_enabled`", "`m076 승인`", "`ValueError`", "`RuntimeError`", "`D-347`", "구문 트리", "`sys.modules`", "검증자 P 의 권고"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, limits)


class ExamplesMatchCodeTest(unittest.TestCase):
    EXPLANATION = mp.render_explanation("M075", 198, "a1b2c3d" + "0" * 33, EXAMPLE_PATHS, *ANSWERS, classification=example_classification())
    NOTICE = mp.render_completion_notice("M075", 198, "e4f5a6b8c9d0e1f2a3b4c5d6e7f8091a2b3c4d5e", "저장 버튼과 저장된 초안 목록이 앱에 반영되었습니다.", "전체 통과", "이상 없음",
                                         "병합 커밋 한 개를 되돌리는 PR 을 만들어 운영자께 보냅니다.")

    def block(self, text):
        found = re.findall(r"```text\n(.*?)```", text, re.S)
        self.assertEqual(len(found), 1)
        return found[0]

    def test_the_explanation_example_is_exactly_what_the_module_renders_and_passes_its_own_check(self):
        example = self.block(subsection("4-2"))
        self.assertEqual(example, self.EXPLANATION)
        self.assertEqual(mp.explanation_problems(example, pr_title="[M075] 초안 저장 기능"), [])
        for answer in ANSWERS:
            self.assertIn(answer, example)
        for label in OPERATOR_ONLY_12:
            self.assertIn("- " + label + ": 아니오", example)
        self.assertIn(mp.APPROVAL_OFF_LINE + "\n", example)

    def test_the_notice_example_is_exactly_what_the_module_renders_and_passes_its_own_check(self):
        example = self.block(SECTIONS[9])
        self.assertEqual(example, self.NOTICE)
        self.assertEqual(mp.completion_notice_problems(example), [])
        for item in COMPLETION_7:
            self.assertIn(item + ": ", example)

    def test_the_example_numbers_are_consistent(self):
        text = self.block(subsection("4-2"))
        self.assertEqual(text.split("\n")[0], "병합 요청 M075")
        self.assertIn("승인 예: M075 승인", text)
        self.assertEqual(mp.parse_approval("M075 승인"), "M075")

    def test_the_example_classification_is_the_real_one_for_the_example_files(self):
        classification = example_classification()
        self.assertEqual((classification.tier, classification.categories, classification.extra_flags), ("ai_ok", (), ()))
        self.assertEqual(classification.paths, tuple(sorted(EXAMPLE_PATHS)))


class PostMergeTableTest(unittest.TestCase):
    """문서 §9 의 전이표가 evaluate_post_merge 의 실제 결과와 같다(S8)."""

    def rows(self):
        text = SECTIONS[9][SECTIONS[9].index("| 직전 병합의 main 검사 |"):]
        return table_rows(text)

    def test_the_table_has_one_row_per_state_and_one_for_everything_else(self):
        rows = self.rows()
        states = [re.match(r"`([a-z]+)`", row[0]) for row in rows[:4]]
        self.assertTrue(all(states))
        self.assertEqual({match.group(1) for match in states}, set(mp.POST_MERGE_STATES))
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[4][0], "그 밖의 값")

    def test_each_row_says_what_the_function_does(self):
        for row in self.rows():
            state = re.match(r"`([a-z]+)`", row[0])
            decision = mp.evaluate_post_merge(state.group(1) if state else "unknown value")
            with self.subTest(state=row[0]):
                self.assertEqual(row[1].startswith("가능"), decision.may_merge_next, row)
                self.assertEqual(row[1].startswith("불가"), not decision.may_merge_next, row)
                if decision.only_actions is None:
                    self.assertEqual(row[2], "제한 없음")
                elif decision.only_actions == ():
                    self.assertTrue(row[2].startswith("없음"), row)
                else:
                    self.assertEqual(decision.only_actions, mp.POST_MERGE_REVERT_ACTIONS)
                    self.assertIn("되돌리기 요청과 쉬운 원인 설명", row[2])


class CorrespondenceTableTest(unittest.TestCase):
    def rows(self):
        start = DOC.index("### 코드와 시험의 대응")
        return table_rows(DOC[start:])

    def test_every_name_in_the_table_exists(self):
        test_source = TEST_PATHS[0].read_text(encoding="utf-8")
        rows = self.rows()
        self.assertEqual(len(rows), 14)
        for policy, section, code, tests in rows:
            with self.subTest(policy=policy):
                number = re.fullmatch(r"§(\d+)", section)
                self.assertIsNotNone(number, section)
                self.assertIn(int(number.group(1)), SECTIONS)
                for name in re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", code):
                    self.assertTrue(hasattr(mp, name), name)
                names = re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", tests)
                self.assertTrue(names, tests)
                for name in names:
                    self.assertIn("class " + name + "(", test_source, name)

    def test_the_table_covers_every_test_class_of_the_policy_tests(self):
        tree = ast.parse(TEST_PATHS[0].read_text(encoding="utf-8"))
        classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
        listed = set()
        for _policy, _section, _code, tests in self.rows():
            listed |= set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", tests))
        self.assertEqual(listed, classes)

    def test_every_public_function_of_the_module_is_in_the_document(self):
        tree = ast.parse(MODULE_SOURCE)
        public = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and not node.name.startswith("_")}
        public -= {"ApprovalCheck", "Decision", "Classification", "Failure", "Verdict", "TrialReport"}               # 결과를 담는 값 객체 — 이름은 함수 설명에 따라 나온다
        for name in sorted(public):
            with self.subTest(name=name):
                self.assertIn("`" + name + "`", DOC)


class SiteConfigMatchTest(unittest.TestCase):
    """블로그 저장소의 기본 거부 목록(SITE_INTERNAL_ENTRIES)이 실제 사이트 설정과 어긋나지 않는다(M1) — `_config.yml` 과 `tests/test_site_cleanup.py` 를 읽기만 한다.
    목록이 사이트로 내보내는 항목을 내부로 잘못 보면 공개 파일이 AI 병합으로 새므로, 설정의 exclude 와 정확히 같아야 한다(더 많아도 안 되고 더 적어도 안 된다)."""

    CONFIG = (ROOT / "_config.yml").read_text(encoding="utf-8").replace("\r\n", "\n")
    CLEANUP = (ROOT / "tests" / "test_site_cleanup.py").read_text(encoding="utf-8")
    NAMES = ("PUBLIC_ROOT", "MUST_EXCLUDE", "STATIC_EXPOSED")

    @classmethod
    def exclude_entries(cls):
        lines = cls.CONFIG.split("\n")
        start = lines.index("exclude:")
        found = []
        for line in lines[start + 1:]:
            match = re.match(r"^\s+-\s+(.+?)\s*$", line)
            if match is None:
                break
            found.append(match.group(1).split(" #")[0].strip().strip("'" + chr(34)))
        return found

    @classmethod
    def constants(cls):
        found = {}
        for node in ast.parse(cls.CLEANUP).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in cls.NAMES:
                found[node.targets[0].id] = ast.literal_eval(node.value)
        return found

    @staticmethod
    def jekyll_excluded(path, excluded):
        """Jekyll 3.10 의 exclude 판정(사이트 정리 시험과 같은 규칙) + 점·밑줄·#·물결표로 시작하는 구간은 기본으로 내보내지 않는다."""
        if any(part.startswith((".", "_", "#", chr(126))) for part in path.split("/")):
            return True
        return any(fnmatch.fnmatchcase(path, entry) or path.startswith(entry) for entry in excluded)

    def exported_files(self):
        excluded = self.exclude_entries()
        files = []
        for entry in sorted(ROOT.iterdir()):
            if self.jekyll_excluded(entry.name, excluded):
                continue
            if entry.is_file():
                files.append(entry.name)
            elif entry.is_dir():
                for path in sorted(entry.rglob("*")):
                    if path.is_file():
                        relative = path.relative_to(ROOT).as_posix()
                        if not self.jekyll_excluded(relative, excluded):
                            files.append(relative)
                    if len(files) > 5000:                                                       # 추적하지 않는 큰 폴더가 있어도 오래 걸리지 않게 한다
                        return files
        return files

    def test_the_internal_list_is_exactly_the_real_exclude_list(self):
        excluded = self.exclude_entries()
        self.assertGreaterEqual(len(excluded), 15)
        self.assertEqual(len(set(excluded)), len(excluded))
        self.assertEqual(set(mp.SITE_INTERNAL_ENTRIES), set(excluded), "사이트 설정의 exclude 와 병합 정책의 내부 항목 목록이 다릅니다 — 한 묶음으로 같이 고쳐야 합니다")
        self.assertEqual(len(mp.SITE_INTERNAL_ENTRIES), len(set(mp.SITE_INTERNAL_ENTRIES)))

    def test_the_site_cleanup_constants_are_covered_and_never_counted_as_internal(self):
        constants = self.constants()
        self.assertEqual(set(constants), set(self.NAMES))
        internal = set(mp.SITE_INTERNAL_ENTRIES)
        self.assertEqual(sorted(constants["MUST_EXCLUDE"] - internal), [], "사이트에 내보내면 안 되는 항목을 내부 목록이 덮지 못합니다")
        self.assertEqual(sorted(constants["PUBLIC_ROOT"] & internal), [], "사이트가 쓰는 항목을 내부로 잘못 보고 있습니다")
        self.assertEqual(sorted(constants["STATIC_EXPOSED"] & internal), [], "사이트에 열어 둔 정적 파일을 내부로 잘못 보고 있습니다")
        self.assertIn("README.md", constants["STATIC_EXPOSED"])

    def test_every_public_root_and_static_name_is_operator_only(self):
        constants = self.constants()
        for name in sorted(constants["PUBLIC_ROOT"] | constants["STATIC_EXPOSED"]):
            path = name + "/x.svg" if "." not in name else name
            with self.subTest(path=path):
                result = mp.classify_change("blog", [path], "", dict.fromkeys(mp.DECLARED_REQUIRED, False))
                self.assertEqual(result.tier, "operator_only", path)

    def test_every_internal_entry_exists_so_a_typo_cannot_hide_a_public_file(self):
        for name in mp.SITE_INTERNAL_ENTRIES:
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).exists(), name)

    def test_every_file_the_site_exports_is_operator_only(self):
        """실제 저장소에서 사이트로 내보내지는 파일(예: README.md·index.html·about.md·assets/*)은 하나도 AI 병합 대상(ai_ok)이 아니다."""
        files = self.exported_files()
        self.assertGreaterEqual(len(files), 10)
        self.assertIn("index.html", files)
        self.assertIn("README.md", files)
        declared = dict.fromkeys(mp.DECLARED_REQUIRED, False)
        for path in files:
            with self.subTest(path=path):
                self.assertEqual(mp.classify_change("blog", [path], "", declared).tier, "operator_only", path)
        for path, code in (("README.md", "public_content"), ("about.md", "public_content"), ("index.html", "ads"), ("robots.txt", "public_content"), ("assets/x.svg", "public_content")):
            self.assertIn(code, mp.classify_change("blog", [path], "", declared).categories, path)

    def test_every_post_and_draft_is_operator_only_too(self):
        declared = dict.fromkeys(mp.DECLARED_REQUIRED, False)
        checked = 0
        for folder in ("_posts", "_blogger_drafts", "_blogger_ko_drafts", "_naver_drafts"):
            for path in sorted((ROOT / folder).rglob("*")):
                if path.is_file():
                    relative = path.relative_to(ROOT).as_posix()
                    checked += 1
                    with self.subTest(path=relative):
                        self.assertEqual(mp.classify_change("blog", [relative], "", declared).categories, ("public_content",), relative)
        self.assertGreater(checked, 5)


class NamedSafetyFilesExistTest(unittest.TestCase):
    """이름으로 적은 안전 장치 목록의 파일·폴더가 실제로 있다 — 이름이 바뀌거나 지워지면 목록을 고치라고 실패한다(S1b)."""

    def test_every_listed_file_exists(self):
        for name in mp.SAFETY_GUARD_FILES + mp.SAFETY_GUARD_DOCS + mp.POLICY_SELF_FILES:
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file(), name)

    def test_every_listed_folder_exists_and_holds_code(self):
        for name in mp.SAFETY_GUARD_DIRS:
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_dir(), name)
                self.assertTrue(list((ROOT / name).glob("*.py")), name)

    def test_the_names_that_do_not_exist_in_this_repository_are_not_listed(self):
        for name in ("pipeline/generator.py", "pipeline/blogger_generator.py"):
            self.assertNotIn(name, mp.SAFETY_GUARD_FILES)
            self.assertFalse((ROOT / name).exists(), name)
        for name in ("generator.py", "blogger_generator.py"):
            self.assertIn(name, mp.SAFETY_GUARD_FILES)

    def test_the_lists_have_no_duplicates_and_no_policy_file(self):
        for names in (mp.SAFETY_GUARD_FILES, mp.SAFETY_GUARD_DOCS, mp.SAFETY_GUARD_DIRS, mp.SITE_INTERNAL_ENTRIES):
            self.assertEqual(len(set(names)), len(names))
        self.assertEqual(set(mp.SAFETY_GUARD_FILES) & set(mp.POLICY_SELF_FILES), set())
        self.assertEqual(set(mp.SAFETY_GUARD_DOCS) & set(mp.POLICY_SELF_FILES), set())


class DocumentedBlindSpotsTest(unittest.TestCase):
    """문서 §7-7·§11-3 이 '지금은 걸리지 않는다'고 적은 빈틈이 코드의 지금 동작과 같다(R2·R3·R4). 빈틈을 닫으려고 목록을 넓히면 이 시험이 빨개져 문서도 한 묶음으로 고치게 한다 — 운영자가 직접 병합하는 변경이다.
    파일이 실제로 있는지는 보지 않는다(경로 글자만 분류한다) — 이름이 바뀌어도 이 시험이 무관한 변경을 막지 않게."""

    DECLARED = dict.fromkeys(mp.DECLARED_REQUIRED, False)
    RUNS_AT_IMPORT = ("pipeline/__init__.py", "tests/_bootstrap.py", "tests/conftest.py", "scripts/sitecustomize.py", "pipeline/usercustomize.py")
    SUBFOLDER_RULE_DOCS = ("pipeline/CLAUDE.md", "tests/AGENTS.md", "docs/CLAUDE.md", "scripts/GEMINI.md")
    DEDICATED_TESTS = ("tests/test_publish_lock.py", "tests/test_gates.py", "tests/test_quality_gate.py", "tests/test_auth_check.py", "tests/test_registry.py", "tests/test_health.py",
                       "tests/test_draft_flow.py", "tests/test_publisher_blogger.py", "tests/test_generator_quality_gate.py", "tests/quality_gate_helpers.py", "tests/lock_helpers.py")
    CONFIRMATION_WAITING = ("pipeline/drafts.py", "pipeline/shadow_run.py")

    def verdict(self, path):
        return mp.classify_change("blog", [path], {path: ""}, dict(self.DECLARED))

    def test_the_files_the_document_says_are_not_caught_are_ai_ok_today(self):
        for group in (self.RUNS_AT_IMPORT, self.SUBFOLDER_RULE_DOCS, self.DEDICATED_TESTS, self.CONFIRMATION_WAITING):
            for path in group:
                with self.subTest(path=path):
                    result = self.verdict(path)
                    self.assertEqual((result.tier, result.categories, result.extra_flags), ("ai_ok", (), ()), result.reasons)

    def test_the_top_level_files_that_run_at_import_are_caught_by_the_default_deny(self):
        for path in ("conftest.py", "sitecustomize.py"):
            with self.subTest(path=path):
                result = self.verdict(path)
                self.assertEqual((result.tier, result.categories), ("operator_only", ("public_content",)))

    def test_one_test_is_in_the_name_list_and_the_rule_documents_are_only_the_listed_paths(self):
        self.assertEqual([name for name in mp.SAFETY_GUARD_FILES if name.startswith("tests/")], ["tests/test_site_cleanup.py"])
        self.assertIn("pipeline/draft_flow.py", mp.SAFETY_GUARD_FILES)                                             # 같은 흐름의 실행부는 목록에 있고
        for name in self.CONFIRMATION_WAITING:
            self.assertNotIn(name, mp.SAFETY_GUARD_FILES)                                                         # 운영자 확인 대기 둘은 없다
        for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            self.assertIn(name, mp.SAFETY_GUARD_DOCS)                                                             # 맨 위의 것만 목록에 있다
            self.assertEqual([item for item in mp.SAFETY_GUARD_DOCS if item.endswith("/" + name)], [])
        self.assertTrue(all(item.startswith("docs/") or "/" not in item for item in mp.SAFETY_GUARD_DOCS))
        self.assertEqual(len(mp.SAFETY_GUARD_DOCS), 18)


class ModulePurityTest(unittest.TestCase):
    TREE = ast.parse(MODULE_SOURCE)
    BANNED_CALLS = frozenset({"open", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals", "vars", "input", "print", "breakpoint", "exit", "quit"})
    BANNED_NAMES = frozenset({"os", "sys", "time", "datetime", "random", "secrets", "socket", "urllib", "subprocess", "pathlib", "shutil", "tempfile", "io", "json", "logging", "threading",
                              "multiprocessing", "importlib", "ctypes", "http", "requests", "ssl", "uuid", "platform", "signal", "asyncio", "builtins"})
    BANNED_ATTRS = frozenset({"write", "write_text", "write_bytes", "read_text", "read_bytes", "open", "environ", "getenv", "putenv", "now", "utcnow", "today", "time", "sleep", "monotonic",
                              "perf_counter", "random", "randint", "choice", "urandom", "uuid4", "urlopen", "urlretrieve", "connect", "system", "popen", "mkdir", "makedirs", "remove",
                              "unlink", "rename", "rmtree", "getcwd", "chdir", "listdir", "glob", "rglob", "iterdir", "walk", "exists", "is_file", "is_dir", "flush", "seek"})

    def test_only_re_and_dataclasses_are_imported(self):
        names = []
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.Import):
                names += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0)
                names.append(node.module)
        self.assertEqual(sorted(names), ["dataclasses", "re"])

    def test_no_io_environment_clock_randomness_or_dynamic_code(self):
        found = []
        for node in ast.walk(self.TREE):
            line = getattr(node, "lineno", 0)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in self.BANNED_CALLS:
                found.append((line, "call", node.func.id))
            if isinstance(node, ast.Name) and node.id in self.BANNED_NAMES:
                found.append((line, "name", node.id))
            if isinstance(node, ast.Attribute) and node.attr in self.BANNED_ATTRS:
                found.append((line, "attribute", node.attr))
            if isinstance(node, (ast.Global, ast.Nonlocal, ast.Await, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Yield, ast.YieldFrom)):
                found.append((line, "statement", type(node).__name__))
        self.assertEqual(found, [])

    def test_importing_the_module_runs_nothing_but_definitions(self):
        for node in self.TREE.body:
            with self.subTest(line=node.lineno):
                if isinstance(node, ast.Expr):
                    self.assertIsInstance(node.value, ast.Constant)                          # 모듈 설명(독스트링)뿐이다
                else:
                    self.assertIsInstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.FunctionDef, ast.ClassDef))

    def test_the_source_has_no_web_address_tilde_local_path_or_secret_shape(self):
        for path in (MODULE_PATH,) + TEST_PATHS:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn(chr(126), text)
                self.assertIsNone(URL_RX.search(text))
                self.assertNotIn("SDI" + "_USER", text)
                self.assertNotRegex(text, r"[A-Za-z]:(?:/|\\)[A-Za-z0-9_.-]{2,}")
                self.assertEqual(find_secrets(text), [])
                self.assertIsNone(re.search("[" + "".join(chr(code) for code in (0x08, 0x0B, 0x0C)) + "]", text))


# ---- 이름 글자만 허용된 한 파일을 줄이 아니라 구문 트리로 지킨다 --------------------------------------------------------------------------------------------------
# 품질 Gate 연결 격리 시험(tests/test_generator_quality_gate.py)은 허용 파일 목록·시험 이름·경로에 정책 모듈의 파일 이름을 글자로 적는다(연결이 아니다). 그 한 파일만 정책 모듈 이름의 글자 언급을 받는데,
# 줄 안 부분 문자열로 지키면 같은 줄 덧붙임(`; import …`)과 글자 쪼개기를 놓친다(P3-M1). 그래서 그 파일을 구문 트리(ast)로 읽어 줄 번호·줄 모양이 아니라 내용으로 지킨다.
NEEDLE = "merge_policy"
# 기대값은 그 파일의 최종 내용에서 계산해 못박았다: 글자 상수 중 merge_policy 가 든 것 4개(허용 파일 목록의 이름 한 곳·이름 비교 한 곳·상대 경로 한 곳·정책 모듈을 읽는 시험의 경로 한 곳)와
# 이름에 든 정의 1개(정책 모듈의 Gate 글자 시험). 다른 언급이 하나라도 늘면(같은 줄 덧붙임 포함) 다르다. 주석은 구문 트리에 없으므로 세지 않는다(실행되지 않는 글이다).
NAMED_ONLY_EXPECTED = {
    "tests/test_generator_quality_gate.py": (["merge_policy.py", "merge_policy.py", "merge_policy.py", "pipeline/merge_policy.py"],
                                             ["test_merge_policy_names_the_gate_only_as_data_in_its_safety_list"]),
}
IMPORT_TOOLS = frozenset({"importlib", "runpy", "imp", "pkgutil", "zipimport"})
DYNAMIC_NAMES = frozenset({"__import__", "import_module", "spec_from_file_location", "module_from_spec", "exec_module", "load_module", "run_path", "run_module", "exec", "eval", "builtins", "__builtins__"})
DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
IMPORTS = (ast.Import, ast.ImportFrom, ast.alias)


def string_constants(tree):
    """구문 트리의 모든 글자 상수(독스트링·f-string 의 글자 조각 포함, 바이트 글자는 latin-1 로 읽는다)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                yield node.value
            elif isinstance(node.value, bytes):
                yield node.value.decode("latin-1")


def fold_text(node):
    """상수 글자끼리의 `+` 이음(여러 번 이은 것 포함)과 상수만 든 f-string 을 접은 글. 접을 수 없으면 None."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return node.value
        return node.value.decode("latin-1") if isinstance(node.value, bytes) else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = fold_text(node.left), fold_text(node.right)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                if value.conversion != -1 or value.format_spec is not None:
                    return None
                value = value.value
            part = fold_text(value)
            if part is None:
                return None
            parts.append(part)
        return "".join(parts)
    return None


def name_strings(tree):
    """구문 트리의 이름 자리(변수·속성·정의·인자·가져오기 이름 …)에 적힌 글 — 글자 상수는 뺀다. (노드, 글) 쌍."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            continue
        for _field, value in ast.iter_fields(node):
            if isinstance(value, str):
                yield node, value
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        yield node, item


def named_only_problems(source, expected_constants, expected_functions):
    """이름 글자만 허용된 한 파일의 문제 목록 [(종류, 내용)] — 없으면 빈 목록.
    constants: 글자 상수 중 merge_policy(대소문자 무시)가 든 것의 정렬한 목록이 기대와 다름 · functions: 이름에 든 정의(함수·클래스)가 기대와 다름 · import: 정책 모듈을 가져옴 ·
    import_tool: importlib·runpy·imp·pkgutil 같은 가져오기 도구를 가져옴 · identifier: 변수·속성 이름 자리에 merge_policy · dynamic: 동적 가져오기·코드 실행 이름의 사용(호출이든 참조든) ·
    folded: 상수 글자를 `+` 나 f-string 으로 쪼개 이어 merge_policy 가 됨."""
    tree = ast.parse(source)
    problems = []

    def add(kind, detail):
        if (kind, detail) not in problems:
            problems.append((kind, detail))

    found = sorted(text for text in string_constants(tree) if NEEDLE in text.lower())
    if found != sorted(expected_constants):
        add("constants", found)
    defined = sorted(node.name for node in ast.walk(tree) if isinstance(node, DEFINITIONS) and NEEDLE in node.name.lower())
    if defined != sorted(expected_functions):
        add("functions", defined)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [name for alias in node.names for name in (alias.name, alias.asname or "")]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""] + [name for alias in node.names for name in (alias.name, alias.asname or "")]
        else:
            modules = []
        for module in modules:
            if NEEDLE in module.lower():
                add("import", module)
            if module.split(".")[0] in IMPORT_TOOLS:
                add("import_tool", module)
        if isinstance(node, (ast.BinOp, ast.JoinedStr)):
            folded = fold_text(node)
            if folded is not None and NEEDLE in folded.lower():
                add("folded", folded)
    for node, text in name_strings(tree):
        if NEEDLE in text.lower() and not isinstance(node, DEFINITIONS + IMPORTS):
            add("identifier", text)
        if text in DYNAMIC_NAMES or text in IMPORT_TOOLS:
            add("dynamic", text)
    return problems


class NotWiredTest(unittest.TestCase):
    """지금은 꺼져 있다 — 아무도 이 모듈을 부르지 않는다. 켜는 변경이 연결을 더할 때 이 시험도 같이 고쳐야 하고, 그 변경은 운영자가 직접 병합한다."""

    ALLOWED = {"pipeline/merge_policy.py", "tests/test_merge_policy.py", "tests/test_merge_policy_docs.py"}
    # 이름 글자만 허용된 한 파일 — 품질 Gate 연결 격리 시험이 허용 파일 목록에 정책 모듈의 파일 이름을 글자로 적는다(연결이 아니다). 이 파일은 줄이 아니라 구문 트리로 지킨다(위 NAMED_ONLY_EXPECTED·named_only_problems).
    NAMED_ONLY = set(NAMED_ONLY_EXPECTED)
    FUNCTION_NAMES = ("parse_approval", "check_approval_text", "check_preconditions", "classify_change", "evaluate_trial", "evaluate_post_merge", "merge_method_allowed", "ApprovalLedger",
                      "ApprovalRecord", "render_explanation", "explanation_problems")

    def scan_targets(self):
        files = [path for pattern in ("*.py", "*.json", "*.yml", "*.yaml", "*.toml", "*.cfg") for path in ROOT.glob(pattern)]
        for base in ("pipeline", "scripts", "tests", ".github"):
            files += [path for pattern in ("*.py", "*.yml", "*.yaml", "*.json", "*.sh", "*.toml", "*.txt", "*.cfg") for path in (ROOT / base).rglob(pattern)]
        return sorted(set(files))

    def test_nobody_outside_the_policy_files_names_the_module(self):
        targets = self.scan_targets()
        self.assertGreater(len(targets), 100)
        named = [path.relative_to(ROOT).as_posix() for path in targets if "merge_policy" in path.read_text(encoding="utf-8", errors="replace")]
        self.assertEqual(sorted(set(named) - self.ALLOWED - self.NAMED_ONLY), [])
        self.assertEqual(set(named), self.ALLOWED | self.NAMED_ONLY)

    def test_no_workflow_or_script_imports_the_policy_modules_functions(self):
        """다른 묶음이 같은 이름의 함수를 정의하거나 부르는 것은 괜찮다 — 이 모듈에서 가져오는 import 줄과 `merge_policy.` 참조만 막는다."""
        names = "|".join(self.FUNCTION_NAMES)
        imported = re.compile(r"(?m)^[ \t]*(?:from[ \t]+[A-Za-z_][A-Za-z0-9_.]*[ \t]+import[ \t]+|import[ \t]+)[^#\n]*(?<![A-Za-z0-9_])(?:" + names + r")(?![A-Za-z0-9_])")
        referenced = re.compile(r"merge_policy[ \t]*\.")
        for path in self.scan_targets():
            rel = path.relative_to(ROOT).as_posix()
            if rel in self.ALLOWED:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            with self.subTest(path=rel):
                self.assertIsNone(imported.search(text), rel)
                if rel not in self.NAMED_ONLY:               # 이름 글자만 허용된 한 파일은 아래 구문 트리 시험이 지킨다
                    self.assertIsNone(referenced.search(text), rel)

    def test_the_one_file_that_may_name_the_module_is_pinned_by_its_syntax_tree(self):
        """연결 격리 시험(test_generator_quality_gate)은 정책 모듈의 파일 이름을 글자로 적을 뿐이다 — 그 파일을 구문 트리로 읽어 (a) merge_policy 가 든 글자 상수의 정렬한 목록이 기대와 정확히 같고(언급이 하나라도 늘면
        같은 줄 덧붙임이라도 실패) (b) 이름에 든 정의가 기대한 한 개뿐이고 (c) 정책 모듈을 가져오는 import·가져오기 도구(importlib·runpy·imp·pkgutil) import 가 0 이고 (d) 이름 자리에 merge_policy 가 없고
        `__import__`·`import_module`·`spec_from_file_location`·`module_from_spec`·`exec_module`·`load_module`·`run_path`·`run_module`·`exec`·`eval` 의 호출·참조가 0 이고 (e) 상수 글자를 `+` 나 f-string 으로 쪼개 이어
        merge_policy 가 되는 조합이 0 임을 지킨다. 줄 번호·줄 모양에는 기대지 않는다."""
        for rel, (constants, functions) in sorted(NAMED_ONLY_EXPECTED.items()):
            source = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(path=rel):
                self.assertEqual(named_only_problems(source, constants, functions), [])
                self.assertEqual(len(constants), 4)
                self.assertEqual(len(functions), 1)

    def test_the_syntax_tree_check_catches_every_known_way_around_the_old_line_check(self):
        """검증자 P3 가 옛 줄 단위 시험을 통과한 다섯 우회(같은 줄 덧붙임 from-import·import as·`__import__`, 글자를 쪼갠 `__import__`·`importlib.import_module`)와 같은 부류 — 모두 잡힌다."""
        base = "ALLOWED = {'merge_policy.py'}\ndef test_merge_policy_one(self):\n    pass\n"
        self.assertEqual(named_only_problems(base, ["merge_policy.py"], ["test_merge_policy_one"]), [])
        cases = (
            ("같은 줄 덧붙임 from-import", "x = 1; from pipeline.merge_policy import classify_change\n", {"import"}),
            ("같은 줄 덧붙임 import as", "x = 1; import pipeline.merge_policy as _mp\n", {"import"}),
            ("같은 줄 덧붙임 __import__", "x = 1; __import__('pipeline.merge_policy')\n", {"constants", "dynamic"}),
            ("글자를 쪼갠 __import__", "__import__('pipeline.merge_' + 'policy')\n", {"folded", "dynamic"}),
            ("글자를 쪼갠 importlib.import_module", "importlib.import_module('pipeline.merge_poli' + 'cy')\n", {"folded", "dynamic"}),
            ("새 줄 from pipeline import merge_policy", "from pipeline import merge_policy\n", {"import"}),
            ("새 줄 from-import", "from pipeline.merge_policy import classify_change\n", {"import"}),
            ("새 줄 상대 import", "from . import merge_policy\n", {"import"}),
            ("새 줄 상대 from-import", "from .merge_policy import classify_change\n", {"import"}),
            ("새 줄 별표 import", "from pipeline.merge_policy import *\n", {"import"}),
            ("새 줄 import", "import pipeline.merge_policy\n", {"import"}),
            ("허용 언급 상수 하나 더", "NOTE = 'merge_policy.py'\n", {"constants"}),
            ("대문자로 적은 상수", "NOTE = 'MERGE_POLICY'\n", {"constants"}),
            ("글자 상수 두 조각을 붙여 쓴 것(파서가 하나로 합침)", "NOTE = 'merge_' 'policy'\n", {"constants"}),
            ("바이트 글자", "NOTE = b'merge_policy'\n", {"constants"}),
            ("세 조각 이음", "NOTE = 'a' + 'merge_' + 'policy'\n", {"folded"}),
            ("f-string 으로 쪼갠 글자", "NOTE = f\"pipeline.merge_{'policy'}\"\n", {"folded"}),
            ("속성으로 부름", "import pipeline\npipeline.merge_policy.classify_change({})\n", {"identifier"}),
            ("이름으로 부름", "merge_policy = None\n", {"identifier"}),
            ("getattr 로 찾음", "value = getattr(pipeline, 'merge_' + 'policy')\n", {"folded"}),
            ("이름에 든 정의 하나 더", "def merge_policy_helper():\n    pass\n", {"functions"}),
            ("이름에 든 클래스", "class merge_policy_box:\n    pass\n", {"functions"}),
            ("importlib 가져오기", "import importlib\n", {"import_tool", "dynamic"}),
            ("importlib 에서 함수 가져오기", "from importlib import import_module\n", {"import_tool", "dynamic"}),
            ("importlib.util 에서 가져오기", "from importlib.util import spec_from_file_location\n", {"import_tool", "dynamic"}),
            ("runpy 로 실행", "import runpy\nrunpy.run_path('x.py')\n", {"import_tool", "dynamic"}),
            ("pkgutil 가져오기", "import pkgutil\n", {"import_tool", "dynamic"}),
            ("imp 가져오기", "import imp\n", {"import_tool", "dynamic"}),
            ("exec 호출", "exec('x = 1')\n", {"dynamic"}),
            ("eval 호출", "eval('x')\n", {"dynamic"}),
            ("builtins 로 우회", "import builtins\nbuiltins.__import__('os')\n", {"dynamic"}),
            ("exec_module 호출", "spec.loader.exec_module(module)\n", {"dynamic"}),
        )
        for label, extra, kinds in cases:
            with self.subTest(label=label):
                found = {kind for kind, _detail in named_only_problems(base + extra, ["merge_policy.py"], ["test_merge_policy_one"])}
                self.assertTrue(kinds <= found, (kinds, found))

    def test_the_syntax_tree_check_accepts_the_expected_shape_and_ignores_comments(self):
        """기대한 모양은 통과하고, 주석(실행되지 않는 글)과 정책 모듈과 무관한 가져오기·글자 이음은 문제로 세지 않는다 — 시험이 너무 넓게 걸려 쓸모없어지지 않게."""
        base = "ALLOWED = {'merge_policy.py'}\ndef test_merge_policy_one(self):\n    pass\n"
        for label, extra in (("아무것도 더하지 않음", ""), ("같은 줄 끝 주석의 언급", "x = 1  # merge_policy import classify_change\n"),
                             ("주석 줄의 언급", "# from pipeline.merge_policy import classify_change\n"), ("무관한 가져오기", "import os\nfrom pathlib import Path\n"),
                             ("무관한 글자 이음", "NAME = 'quality' + '_gate'\n"), ("무관한 f-string", "NAME = f'{1}-{2}'\n"),
                             ("비슷하지만 다른 이름", "def merge_policies():\n    pass\npolicy = 1\nmerge = 2\n")):
            with self.subTest(label=label):
                self.assertEqual(named_only_problems(base + extra, ["merge_policy.py"], ["test_merge_policy_one"]), [])
        kinds = {kind for kind, _detail in named_only_problems(base, ["merge_policy.py", "merge_policy.py"], ["test_merge_policy_one"])}
        self.assertEqual(kinds, {"constants"})                                             # 기대한 상수가 빠져도(줄어도) 다르다 — 허용 목록을 몰래 줄이지 못한다
        kinds = {kind for kind, _detail in named_only_problems(base, ["merge_policy.py"], [])}
        self.assertEqual(kinds, {"functions"})
        with self.assertRaises(SyntaxError):
            named_only_problems("def broken(:\n", [], [])                                    # 읽을 수 없는 파일은 통과가 아니라 오류다

    def test_there_is_exactly_one_file_named_like_the_module(self):
        """같은 이름의 파일이 다른 폴더에 하나라도 있으면 실패한다 — 연결 격리 시험이 파일 이름만 보고 허용하던 틈(P3-M1 3·I9)을 정책 쪽에서도 막는다."""
        found = sorted(path.relative_to(ROOT).as_posix() for path in ROOT.rglob("merge_policy.py"))
        self.assertEqual(found, ["pipeline/merge_policy.py"])

    def test_the_name_scan_itself_catches_an_import_and_ignores_a_same_named_definition(self):
        names = "|".join(self.FUNCTION_NAMES)
        imported = re.compile(r"(?m)^[ \t]*(?:from[ \t]+[A-Za-z_][A-Za-z0-9_.]*[ \t]+import[ \t]+|import[ \t]+)[^#\n]*(?<![A-Za-z0-9_])(?:" + names + r")(?![A-Za-z0-9_])")
        for line in ("from pipeline.x import classify_change", "    from y import a, evaluate_trial", "import check_preconditions", "from pipeline.other import (parse_approval)"):
            with self.subTest(caught=line):
                self.assertIsNotNone(imported.search(line + "\n"))
        for line in ("def classify_change(items):", "result = classify_change(a, b)", "# from x import classify_change", "from pipeline.x import classify_changes", "from pipeline.x import my_parse_approval"):
            with self.subTest(ignored=line):
                self.assertIsNone(imported.search(line + "\n"))

    def test_the_policy_is_not_wired_to_the_operator_loop_or_the_validator(self):
        for rel in ("pipeline/operator_loop.py", "scripts/validate_repo.py", "pipeline/notify.py"):
            self.assertNotIn("merge_policy", (ROOT / rel).read_text(encoding="utf-8"), rel)


class DefectRegisterTest(unittest.TestCase):
    """공유 결함 대장의 두 행을 번호가 아니라 **제목 글**로 찾는다 — 다른 묶음과 번호가 겹쳐 번호를 고쳐도 이 시험은 그대로다."""

    TITLE_POLICY = "조건부 승인형 AI 병합 정책이 문서와 시험 가능한 코드로 없었다"
    TITLE_CONSERVATIVE = "조건부 승인형 AI 병합 정책의 보수적 해석 7가지"

    def rows(self):
        found = {}
        for key, title in (("policy", self.TITLE_POLICY), ("conservative", self.TITLE_CONSERVATIVE)):
            matches = [match.group(0) for match in re.finditer(r"(?m)^\| \*\*(D-\d+)\*\* \|.*$", REGISTER) if title in match.group(0)]
            self.assertEqual(len(matches), 1, title)
            found[key] = matches[0]
        return found

    def test_the_two_rows_exist_with_six_columns_and_different_numbers(self):
        rows = self.rows()
        numbers = {key: re.match(r"\| \*\*(D-\d+)\*\*", row).group(1) for key, row in rows.items()}
        self.assertEqual(len(set(numbers.values())), 2)
        for name, row in rows.items():
            with self.subTest(row=name):
                self.assertEqual(row.count("|"), 7)

    def test_the_policy_row_records_the_policy_work_and_that_it_is_off(self):
        row = self.rows()["policy"]
        for word in ("docs/AI_MERGE_POLICY.md", "pipeline/merge_policy.py", "tests/test_merge_policy.py", "tests/test_merge_policy_docs.py", "확인 016", "꺼져 있음", "별도 병합 요청", "운영자가 직접 병합",
                     "더 보수적으로", "**해결**"):
            self.assertIn(word, row)
        self.assertIn("main 직접 push 금지", row)

    def test_the_conservative_row_lists_the_seven_readings_and_attributes_the_judgement_to_the_ai(self):
        """보수적 해석 7가지는 총괄(AI)의 판단이고 운영자 확인을 기다린다 — ⑦ 은 문서 파일의 낱말 규칙 면제와 규칙 문서의 안전 장치 편입으로 다시 썼다."""
        row = self.rows()["conservative"]
        for mark in ("①", "②", "③", "④", "⑤", "⑥", "⑦"):
            self.assertIn(mark, row)
        self.assertIn("**해결**(총괄(AI)의 보수적 판단 2026-11-15 — 운영자 확인 대기", row)
        self.assertNotIn("**열림**", row)
        self.assertIn("규칙 문서 18개", row)                                                                          # 안전 목록의 규칙 문서 개수(WIP 7: 10개 → 18개)와 대장 행이 어긋나지 않게
        for old in ("총괄 2026-11-15" + ":", "운영자 결정 " + "D-347"):
            self.assertNotIn(old, row)
        for word in ("policy_self", "packaging_release", "invalid_input", "safety_guard", "external_connection", "승인 문구는 엄격하게 유지한다", "ClassifySafetyGuardTest",
                     "ClassifyExternalConnectionTest", "ClassifyDocumentTextTest", "ClassifySiteDefaultDenyTest", "§7-7", "문서 파일", "규칙 문서"):
            self.assertIn(word, row)
        seventh = row[row.index("⑦"):row.index("|", row.index("⑦"))]
        self.assertIn("낱말 규칙", seventh)
        self.assertIn("(총괄(AI)의 판단 — 운영자 확인 대기)", seventh)
        self.assertNotIn("문서 PR 도 운영자 전용이 된다", seventh.split("→")[-1])


class NewTestsAreOfflineTest(unittest.TestCase):
    def test_the_new_tests_do_not_touch_the_network_or_write_files(self):
        for path in TEST_PATHS:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            with self.subTest(path=path.name):
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                        for module in modules:
                            self.assertNotIn(module.split(".")[0], {"urllib", "socket", "requests", "http", "ssl", "subprocess", "shutil", "tempfile", "smtplib", "ftplib"}, module)
                    if isinstance(node, ast.Call):
                        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                        self.assertNotIn(name, {"urlopen", "create_connection", "getaddrinfo", "write_text", "write_bytes", "mkdir", "unlink", "rmtree", "open", "system", "Popen", "run"}, name)


if __name__ == "__main__":
    unittest.main()
