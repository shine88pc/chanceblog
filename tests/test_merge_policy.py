"""조건부 승인형 AI 병합 정책(운영자 확인 016 답, 2026-11-15)의 순수 함수 시험 — `pipeline/merge_policy.py`.

이 시험은 모듈 상수를 믿지 않는다: 운영자 원문의 목록(운영자 전용 12항목·재확인 8조건·불허 문구 5개·병합 가능 7종·설명 6항목·완료 알림 7항목·시험 기준 6가지)을 아래에 글자 그대로 따로 적어 두고 모듈과 대조한다 —
상수에서 항목 하나를 지우는 변경도 빨개지게 한다. 시험의 가짜 비밀은 런타임에 조립한 문자열이고 `CANARY` 로 시작하는 본문을 쓴다(소스에 비밀 모양이 이어 붙어 있지 않다).
이 시험은 네트워크·파일 쓰기를 하지 않는다(모듈이 순수 함수라서 가짜가 필요 없다).
"""
import copy
import time
import unicodedata
import unittest

import _bootstrap
from pipeline import merge_policy as mp
from pipeline import notify

ROOT = _bootstrap.ROOT

# ---- 운영자 결정 원문의 목록(글자 그대로) -------------------------------------------------------------------------------------------------------------------
OPERATOR_ONLY_12 = ("GitHub Actions Workflow", "광고·AdSense·ads.txt", "공개 게시물과 고정 페이지", "PIPELINE_PAUSE", "발행 모드와 발행 재개", "Provider 활성화",
                    "API Key·Secret·Credential", "의존성 추가", "데이터 삭제·Migration", "자동 게시 활성화", "외부 비용 발생 기능", "Main Branch 보호 설정")
PRECONDITIONS_8 = ("승인된 병합 번호와 PR 일치", "승인 이후 Commit 추가 없음", "검사 전체 통과", "독립 검증 통과", "충돌 없음", "변경 범위가 승인 설명과 일치", "비밀정보 노출 없음", "원복 방법 확인")
REJECTED_5 = ("확인했습니다", "진행하세요", "좋아 보입니다", "기본값대로", "다음 단계 진행")
SCOPES_7 = ("일반 프로그램 코드", "일반 UI", "시험", "문서", "로컬 저장·조회", "오류 수정", "접근성·성능 개선")
EXPLANATION_6 = ("무엇을 바꾸나요?", "왜 필요한가요?", "사용할 때 무엇이 달라지나요?", "위험은 무엇인가요?", "검사 결과", "되돌리기")
COMPLETION_7 = ("병합 번호", "PR 번호", "병합된 Commit", "실제 반영된 변화", "main 검사 결과", "이상 유무", "원복 Commit 또는 원복 방법")
TRIAL_6 = ("승인받은 PR만 병합", "승인 후 변경 없음", "main 검사 전체 통과", "원복 발생 0건", "다른 PR 오병합 0건", "운영자 전용 경로 변경 0건")
FACT_KEYS_23 = ("approved_number", "approved_pr_number", "pr_number", "pr_title_label", "consumed_numbers", "approved_head_sha", "current_head_sha", "current_tree",
                "approved_paths", "current_paths", "checks", "independent_verification", "has_conflict", "classification", "secret_findings", "rollback_method",
                "repo_kind", "changed_text", "head_sha_at_approval", "required_checks", "pr_state", "pr_draft", "previous_merge_main_check")
VERIFICATION_KEYS_5 = ("verdict", "verifier", "implementer", "verified_tree", "open_required_findings")

# 가짜 비밀 — 소스에는 이어 붙은 비밀 모양이 없고 런타임에 조립한다
FAKE_SECRETS = {
    "google": "AI" + "za" + "CANARY_" + "A" * 28,
    "google_new": "A" + "Q." + "CANARY_" + "B" * 40,
    "oauth": "GOC" + "SPX-" + "CANARY_" + "C" * 20,
    "refresh": "1/" + "/0" + "CANARY_" + "D" * 40,
    "access": "ya" + "29." + "CANARY_" + "E" * 30,
    "github": "gh" + "p_" + "CANARY" + "F" * 30,
    "pat": "github" + "_pat_" + "CANARY_" + "G" * 40,
    "private_key": "-----BEGIN " + "PRIVATE KEY" + "-----",
    "private_key_rsa": "-----BEGIN " + "RSA PRIVATE KEY" + "-----",
    "slack": "xo" + "xb-" + "CANARY" + "-" + "H" * 12,
    "aws": "AK" + "IA" + "CANARY" + "I" * 10,
    "telegram": "123456789" + ":" + "CANARY_" + "J" * 30,
    "sk": "s" + "k-" + "CANARY" + "K" * 30,
}

COUNTRY_TLD_TEXT = (
    "ac ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bm bn bo br bs bt bw by bz ca cd cf cg ch ci ck cl cm cn co cr cu cv cw cx cy cz de dj dk dm do dz ec ee eg er es et eu "
    "fi fj fk fm fo fr ga gd ge gf gg gh gi gl gm gn gp gq gr gs gt gu gw gy hk hm hn hr ht hu id ie il im in io iq ir is it je jm jo jp ke kg kh ki km kn kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly "
    "ma mc md me mg mh mk ml mm mn mo mp mq mr ms mt mu mv mw mx my mz na nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr ps pt pw py qa re ro rs ru rw sa sb sc sd se sg sh si sk sl sm sn so "
    "sr ss st su sv sx sy sz tc td tf tg th tj tk tl tm tn to tr tt tv tw tz ua ug uk us uy uz va vc ve vg vi vn vu wf ws ye yt za zm zw")
SHA_A, SHA_B = "1" * 40, "2" * 40
TREE_A, TREE_B = "3" * 40, "4" * 40
GOOD_PATHS = ("pipeline/topics.py", "tests/test_topics.py")
DECLARED_OK = {code: False for code in mp.DECLARED_REQUIRED}
GOOD_TEXT = "def add(a, b):\n    return a + b\n"


def classify(kind, paths, text="", declared=None):
    return mp.classify_change(kind, list(paths), text, dict(DECLARED_OK) if declared is None else declared)


def url(host, scheme="https"):
    """주소 글을 런타임에 조립한다(소스에 웹 주소가 이어 붙어 있지 않게)."""
    return scheme + ":" + "//" + host


def good_facts():
    paths = list(GOOD_PATHS)
    return {
        "approved_number": "M075", "approved_pr_number": 198, "pr_number": 198, "pr_title_label": "M075", "consumed_numbers": [],
        "pr_state": "open", "pr_draft": False,
        "approved_head_sha": SHA_A, "head_sha_at_approval": SHA_A, "current_head_sha": SHA_A, "current_tree": TREE_A,
        "approved_paths": list(paths), "current_paths": list(paths),
        "repo_kind": "blog", "changed_text": GOOD_TEXT,
        "checks": [{"name": "저장소 규칙 검사", "conclusion": "success"}, {"name": "사이트 배포 미리 검사", "conclusion": "success"}],
        "required_checks": ["저장소 규칙 검사", "사이트 배포 미리 검사"], "previous_merge_main_check": "success",
        "independent_verification": {"verdict": "pass", "verifier": "검증자 갑", "implementer": "구현자 을", "verified_tree": TREE_A, "open_required_findings": 0},
        "has_conflict": False,
        "classification": classify("blog", paths, GOOD_TEXT).to_dict(),
        "secret_findings": 0,
        "rollback_method": "문제가 생기면 M075 병합 커밋 하나만 되돌리면 이전 상태로 돌아갑니다.",
    }


ANSWERS = ("앱을 닫아도 작성 중인 초안을 다시 열 수 있도록 저장 기능을 추가합니다.", "현재는 앱을 닫으면 초안이 사라집니다.", "저장 버튼과 저장된 초안 목록이 추가됩니다.",
           "저장 실패나 손상 가능성을 막기 위해 원자적 저장과 복구 시험을 수행했습니다.", "전체 검사와 독립 검증을 통과했고 기존 복사 기능에는 변화가 없습니다.",
           "문제가 발생하면 M075 병합만 되돌리면 이전 상태로 복구됩니다.")


def make_text(number="M075", enabled=False, classification=None, paths=("pipeline/drafts.py", "tests/test_drafts.py")):
    """표준 설명 글 — classification 을 주지 않으면 이 경로로 classify_change 를 돌려 얻은 결과로 점검표를 채운다."""
    if classification is None:
        classification = classify("blog", paths, GOOD_TEXT)
    return mp.render_explanation(number, 198, "c" * 40, list(paths), *ANSWERS, ai_merge_enabled=enabled, classification=classification)


def make_notice():
    return mp.render_completion_notice("M075", 198, "d" * 40, "초안 저장 기능이 사이트에 반영되었습니다.", "전체 통과", "이상 없음", "해당 병합 커밋 한 개를 되돌립니다.")


def drop_line(text, start):
    """start 로 시작하는 줄을 지운다(없으면 시험이 틀린 것이다)."""
    lines = text.split("\n")
    kept = [line for line in lines if not line.startswith(start)]
    assert len(kept) == len(lines) - 1, start
    return "\n".join(kept)


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


class ConstantsPinTest(unittest.TestCase):
    """운영자 원문의 목록이 줄거나 늘지 않았다 — 모듈 상수와 이 파일의 글자 그대로의 목록이 같다."""

    def test_the_operator_lists_are_exactly_the_original_words(self):
        self.assertEqual(mp.OPERATOR_ONLY_LABELS, OPERATOR_ONLY_12)
        self.assertEqual(tuple(label for _code, label in mp.PRECONDITIONS), PRECONDITIONS_8)
        self.assertEqual(mp.REJECTED_PHRASES, REJECTED_5)
        self.assertEqual(mp.AI_MERGE_SCOPES, SCOPES_7)
        self.assertEqual(mp.EXPLANATION_ITEMS, EXPLANATION_6)
        self.assertEqual(mp.COMPLETION_ITEMS, COMPLETION_7)
        self.assertEqual(tuple(label for _key, label in mp.TRIAL_CRITERIA), TRIAL_6)

    def test_the_counts_are_twelve_eight_five_seven_six_seven_six(self):
        self.assertEqual([len(mp.OPERATOR_ONLY_ITEMS), len(mp.PRECONDITIONS), len(mp.REJECTED_PHRASES), len(mp.AI_MERGE_SCOPES), len(mp.EXPLANATION_ITEMS),
                          len(mp.COMPLETION_ITEMS), len(mp.TRIAL_CRITERIA)], [12, 8, 5, 7, 6, 7, 6])
        self.assertEqual(mp.TRIAL_SIZE, 3)

    def test_codes_are_unique_and_the_declared_six_are_among_the_twelve(self):
        for codes in (mp.OPERATOR_ONLY_CODES, tuple(code for code, _ in mp.PRECONDITIONS), tuple(key for key, _ in mp.TRIAL_CRITERIA), mp.EXTRA_CODES):
            self.assertEqual(len(set(codes)), len(codes))
        self.assertEqual(len(mp.DECLARED_REQUIRED), 6)
        self.assertLessEqual(set(mp.DECLARED_REQUIRED), set(mp.OPERATOR_ONLY_CODES))
        self.assertEqual(set(mp.EXTRA_CODES) & set(mp.OPERATOR_ONLY_CODES), set())
        self.assertEqual(mp.EXTRA_CODES, ("policy_self", "packaging_release", "invalid_input", "safety_guard", "external_connection"))
        self.assertEqual(dict(mp.EXTRA_FLAGS)["safety_guard"], "안전 장치 파일")
        self.assertEqual(dict(mp.EXTRA_FLAGS)["external_connection"], "새 외부 접속 코드")

    def test_the_fact_keys_and_verification_keys_are_pinned(self):
        self.assertEqual(mp.FACT_KEYS, FACT_KEYS_23)
        self.assertEqual(mp.VERIFICATION_KEYS, VERIFICATION_KEYS_5)
        self.assertEqual(set(good_facts()), set(FACT_KEYS_23))
        self.assertEqual(len(mp.FACT_KEYS), len(set(mp.FACT_KEYS)))

    def test_the_safety_and_external_connection_rule_lists_are_pinned(self):
        """총괄(AI)의 보수적 판단(결함 D-347, 운영자 확인 대기)으로 더한 두 표시의 규칙 목록을 글자 그대로 못박는다 — 낱말·모듈 하나를 지우면 빨개진다."""
        self.assertEqual(mp.SAFETY_GUARD_WORDS, ("validate_repo", "guardrail", "guard", "security", "secret", "egress", "policy", "safety", "sandbox", "ai_flow"))
        self.assertEqual(mp.SAFETY_GUARD_DOCS, ("docs/SECURITY_GUARDRAILS.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md", "AI_COLLAB.md", "HANDLER.md", "docs/CHARTER.md", "docs/ACTIONS_GUIDE.md",
                                                "docs/AGENT_RUNBOOK.md", "docs/SESSION_START.md", "docs/ENGINEERING_GUIDE.md", "docs/AGENT_DELEGATION.md", "docs/COPILOT_GUIDE.md", "docs/AI_FLOW.md",
                                                "docs/AI_MODEL_GUIDE.md", "docs/SOURCE_POLICY.md", "docs/QUALITY_GATE.md", "docs/REQUEST_BRIEFING.md"))
        self.assertEqual(mp.DOC_SUFFIXES, (".md", ".rst", ".txt", ".adoc"))
        self.assertEqual(mp.NETWORK_MODULES, ("urllib.request", "urllib3", "requests", "httpx", "aiohttp", "http.client", "http.server", "socket", "socketserver", "ssl", "ftplib", "smtplib",
                                              "telnetlib", "poplib", "imaplib", "nntplib", "xmlrpc", "websockets", "websocket", "paramiko", "asyncssh", "pycurl", "httplib2", "feedparser",
                                              "webbrowser", "grpc"))
        self.assertEqual(mp.SERVICE_SDK_MODULES, ("google.genai", "google.generativeai", "google.cloud", "google.oauth2", "google.auth", "googleapiclient", "google_auth_oauthlib", "openai",
                                                  "anthropic", "vertexai", "cohere", "mistralai", "litellm", "langchain", "huggingface_hub", "transformers", "ollama", "groq", "replicate",
                                                  "boto3", "botocore", "tweepy", "slack_sdk", "telebot", "gspread"))
        self.assertEqual(mp.EXTERNAL_MODULES, mp.NETWORK_MODULES + mp.SERVICE_SDK_MODULES)
        self.assertEqual(len(mp.EXTERNAL_MODULES), 51)
        self.assertEqual(mp.EXTERNAL_SCHEMES, ("http", "https", "ws", "wss", "ftp", "ftps", "sftp", "ssh", "git", "tg", "smtp", "smtps", "ldap", "ldaps", "redis", "rediss", "mqtt", "mqtts", "amqp",
                                               "amqps", "gopher"))
        self.assertEqual(mp.EXAMPLE_HOSTS, ("example.com", "example.net", "example.org"))
        self.assertEqual(mp.EXAMPLE_TOP_LEVELS, ("example", "test", "invalid"))

    def test_the_site_default_deny_and_safety_file_lists_are_pinned(self):
        """블로그 저장소의 기본 거부(사이트로 내보내지 않는 맨 위 항목 21개)와 이름으로 적은 안전 장치 파일·폴더 — 하나를 지우면 빨개진다."""
        self.assertEqual(mp.SITE_INTERNAL_ENTRIES, ("AGENTS.md", "AI_COLLAB.md", "CLAUDE.md", "GEMINI.md", "HANDLER.md", "WORKLOG.md", "docs", "인수인계", "generator.py", "blogger_generator.py",
                                                    "pipeline", "scripts", "tests", "history.json", "blogger_history.json", "blogger_ko_history.json", "naver_history.json", "pages.json",
                                                    "requirements-dev.txt", "requirements-edits.txt", "requirements-pipeline.txt"))
        self.assertEqual(len(mp.SITE_INTERNAL_ENTRIES), 21)
        self.assertEqual(mp.SAFETY_GUARD_FILES, ("pipeline/publish_lock.py", "pipeline/quality_gate.py", "pipeline/gates.py", "pipeline/auth_check.py", "pipeline/registry.py",
                                                 "pipeline/source_registry.py", "pipeline/health.py", "pipeline/draft_flow.py", "pipeline/edits/runner.py", "generator.py", "blogger_generator.py",
                                                 "scripts/get_blogger_token.py", "scripts/watchdog.py", "tests/test_site_cleanup.py", "pipeline/run.py", "pipeline/operator_loop.py",
                                                 "pipeline/telegram_inbox.py"))
        self.assertEqual(mp.SAFETY_GUARD_DIRS, ("pipeline/publishers",))

    def test_the_host_domain_and_shell_lists_are_pinned(self):
        self.assertEqual(mp.FILE_NAME_TLDS, ("py", "sh", "md", "rs", "pl", "so", "cc", "ps", "pm", "ml"))
        self.assertEqual(mp.GENERIC_TLDS, ("com", "net", "org", "dev", "app", "info", "biz", "gov", "edu", "mil", "int", "cloud", "xyz", "site", "online", "tech", "store", "shop", "blog", "club", "pro",
                                           "asia", "mobi", "live", "link", "top", "vip"))
        self.assertEqual(mp.COUNTRY_TLDS, tuple(COUNTRY_TLD_TEXT.split()))
        self.assertEqual(len(mp.COUNTRY_TLDS), 244)
        self.assertTrue(all(len(name) == 2 and name.islower() and name.isalpha() for name in mp.COUNTRY_TLDS))
        self.assertEqual(len(set(mp.COUNTRY_TLDS)), len(mp.COUNTRY_TLDS))
        self.assertEqual(mp.HOST_TLDS, frozenset(mp.COUNTRY_TLDS + mp.GENERIC_TLDS) - frozenset(mp.FILE_NAME_TLDS))
        self.assertEqual(len(mp.HOST_TLDS), 262)
        for name in ("py", "sh", "md", "js", "ts", "db", "txt", "html", "json", "yml", "path", "name", "notify", "attr"):
            self.assertNotIn(name, mp.HOST_TLDS, name)
        self.assertEqual(mp.SHELL_SUFFIXES, (".sh", ".bash", ".ps1", ".bat", ".cmd"))

    def test_the_post_merge_and_pull_request_state_constants_are_pinned(self):
        self.assertEqual(mp.POST_MERGE_STATES, ("success", "failure", "pending", "none"))
        self.assertEqual(mp.POST_MERGE_REVERT_ACTIONS, ("send_revert_request", "send_cause_explanation"))
        self.assertEqual(mp.PR_STATES, ("open", "closed", "merged"))
        self.assertEqual(mp.ROLLBACK_MIN_CHARS, 10)
        self.assertEqual(mp.ROLLBACK_PLACEHOLDERS, ("to be decided", "not applicable", "해당 사항이 없습니다", "되돌릴 필요가 없습니다", "원복 방법이 없습니다", "원복 방법 확인 불가", "추후 결정 예정입니다",
                                                    "별도로 정하지 않았습니다"))
        self.assertTrue(all(len(" ".join(text.split())) >= mp.ROLLBACK_MIN_CHARS for text in mp.ROLLBACK_PLACEHOLDERS))     # 길이 규칙에 가려지지 않는 문구만 담는다

    def test_the_merge_method_constants(self):
        self.assertEqual(mp.ALLOWED_MERGE_METHOD, "pr_merge")
        self.assertEqual(mp.FORBIDDEN_MERGE_METHODS, ("push_main", "direct_push", "force_push"))

    def test_the_merge_number_rule_is_the_notify_standard_with_the_m_prefix(self):
        """새로 만들지 않고 같은 값 — 숫자 부분이 pipeline.notify.NOTICE_NO_RE 와 글자 그대로 같고, 행동도 모든 숫자·표기에서 같다."""
        self.assertEqual(notify.NOTICE_NO_RE.pattern, "[PM]?" + mp.MERGE_NUMBER_DIGITS)
        different, accepted = [], 0
        for number in range(0, 10006):
            for text in ("M%03d" % number, "M%04d" % number, "M%d" % number, "m%03d" % number, "P%03d" % number, "%03d" % number, "M%05d" % number):
                mine = mp.MERGE_NUMBER_RE.fullmatch(text) is not None
                accepted += mine
                if mine != (notify.notice_type(text) == "merge"):
                    different.append(text)
        self.assertEqual(different, [])
        self.assertEqual(accepted, 9999 + 9000 + 9900)           # 세 자리 0 채움(M001–M999)·네 자리(M1000–M9999)·0 을 채우지 않은 쓰기 — 앞에 0 을 더 붙인 네 자리와 다섯 자리는 번호가 아니다
        self.assertIsNotNone(mp.MERGE_NUMBER_RE.fullmatch("M001"))
        self.assertIsNotNone(mp.MERGE_NUMBER_RE.fullmatch("M999"))
        self.assertIsNotNone(mp.MERGE_NUMBER_RE.fullmatch("M1000"))
        self.assertIsNotNone(mp.MERGE_NUMBER_RE.fullmatch("M9999"))
        for text in ("M000", "M0075", "M10000", "m075", "M75", "M07", "P075", "075", "M075\n", " M075", "M０７５"):
            self.assertIsNone(mp.MERGE_NUMBER_RE.fullmatch(text), text)

    def test_the_public_functions_exist(self):
        for name in ("parse_approval", "check_approval_text", "approval_matches", "approval_still_valid", "pr_title_label", "classify_change", "check_preconditions",
                     "merge_method_allowed", "explanation_problems", "render_explanation", "completion_notice_problems", "render_completion_notice", "evaluate_trial", "trial_report",
                     "evaluate_post_merge", "normalize_repo_path", "check_approval_text"):
            self.assertTrue(callable(getattr(mp, name)), name)
        for cls in (mp.ApprovalLedger, mp.ApprovalRecord, mp.PostMergeDecision, mp.Classification, mp.Verdict, mp.Failure, mp.TrialReport, mp.ApprovalCheck, mp.Decision):
            self.assertTrue(callable(cls), cls)


class ApprovalParseTest(unittest.TestCase):
    VALID = (("M075 승인", "M075"), ("M075 승인.", "M075"), ("  M075 승인  ", "M075"), ("\tM075 승인\r\n", "M075"), ("m075 승인", "M075"), ("M075   승인", "M075"),
             ("M075\t승인", "M075"), ("M1000 승인", "M1000"), ("M999 승인", "M999"), ("M001 승인", "M001"), ("M9999 승인.", "M9999"), (" m1234 승인. \n", "M1234"))

    def test_the_exact_form_is_an_approval_and_the_number_is_returned_in_capitals(self):
        for text, number in self.VALID:
            with self.subTest(text=text):
                self.assertEqual(mp.parse_approval(text), number)
                result = mp.check_approval_text(text)
                self.assertEqual((result.number, result.reason, result.guidance), (number, "ok", ""))

    def test_each_rejected_phrase_alone_is_not_an_approval(self):
        for phrase in REJECTED_5:
            for text in (phrase, phrase + ".", "  " + phrase + "  ", "네, " + phrase, phrase + " 감사합니다"):
                with self.subTest(text=text):
                    self.assertIsNone(mp.parse_approval(text))
                    self.assertEqual(mp.check_approval_text(text).reason, "rejected_phrase")

    def test_a_phrase_next_to_a_number_is_not_an_approval_either(self):
        for text in ("M075 확인했습니다", "확인했습니다 M075 승인", "M075 승인 확인했습니다", "진행하세요 M075", "M075 기본값대로", "좋아 보입니다 M075 승인"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))

    def test_an_approval_word_without_a_number_is_not_an_approval(self):
        for text in ("승인", "승인합니다", "승인.", "M 승인", "M승인", "네 승인", "승인 부탁드립니다"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))
                self.assertEqual(mp.check_approval_text(text).reason, "no_number")

    def test_two_or_more_numbers_are_ambiguous(self):
        for text in ("M075 M076 승인", "M075 승인 M076 승인", "M075 승인\nM076 승인", "M075, M076 승인", "M075 승인 (M074 다음)"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))
                self.assertEqual(mp.check_approval_text(text).reason, "several_numbers")

    def test_words_after_the_approval_make_it_not_an_approval(self):
        for text in ("M075 승인하되 이름은 바꿔 주세요", "M075 승인합니다", "M075 승인 합니다", "M075 승인 (보류)", "M075 승인 취소", "M075 승인 안 함", "M075 승인 감사합니다",
                     "M075 승인 아님", "M075 승인 부탁", "M075 승인 확인했습니다"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))
                self.assertEqual(mp.check_approval_text(text).reason, "not_exact_form")

    def test_a_number_inside_another_sentence_is_not_an_approval(self):
        for text in ("오늘 M075 승인", "안녕하세요 M075 승인", "M075 승인 이라고 쓰면 됩니다", "회의에서 M075 승인 얘기가 나왔습니다", "참고: M075 승인", "- M075 승인 -"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))

    def test_the_form_is_exact_number_first_then_one_word(self):
        for text in ("승인 M075", "M075승인", "M075, 승인", "M075: 승인", "M075 - 승인", "[M075] 승인", "(M075 승인)", "M075 승인!", "M075 승인..", "M075 승인 .", "M075 승인?"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))

    def test_quotes_and_formatting_characters_are_not_stripped(self):
        for text in ("'M075 승인'", '"M075 승인"', "`M075 승인`", "*M075 승인*", "> M075 승인", "M075 승인</p>"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))

    def test_the_number_must_be_the_standard_three_or_four_digits(self):
        for text in ("M75 승인", "M0075 승인", "M000 승인", "M00075 승인", "M12345 승인", "M7 승인", "M10000 승인", "M-75 승인", "M+75 승인", "M075.5 승인", "M 075 승인"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))
        for text in ("M75 승인", "M0075 승인", "M000 승인", "M12345 승인"):
            self.assertEqual(mp.check_approval_text(text).reason, "bad_number")

    def test_other_prefixes_and_forms_are_not_merge_numbers(self):
        for text in ("P075 승인", "075 승인", "R-075 승인", "#075 승인", "N075 승인", "MM075 승인", "M075a 승인", "xM075 승인"):
            with self.subTest(text=text):
                self.assertIsNone(mp.parse_approval(text))

    def test_look_alike_and_invisible_characters_are_not_accepted(self):
        zero_width, nbsp, ideographic = chr(0x200B), chr(0xA0), chr(0x3000)
        for text in (chr(0xFF2D) + "075 승인",                                                                                        # 전각 M
                     "M" + chr(0xFF10) + chr(0xFF17) + chr(0xFF15) + " 승인",                                                            # 전각 숫자
                     "M07" + zero_width + "5 승인", "M075" + zero_width + " 승인", "M075 승" + zero_width + "인",
                     "M075" + nbsp + "승인", nbsp + "M075 승인", "M075 승인" + nbsp, "M075" + ideographic + "승인", chr(0xFEFF) + "M075 승인",
                     "M075 " + unicodedata.normalize("NFD", "승인"), chr(0x202E) + "M075 승인"):
            with self.subTest(text=repr(text)):
                self.assertIsNone(mp.parse_approval(text))

    def test_other_punctuation_and_edge_spaces_are_not_an_approval(self):
        """R5(T3 — AP01·AP03): 전각 마침표·전각 점·앞뒤 U+3000 공백처럼 겉모습만 비슷한 입력은 승인이 아니다 — 승인 인정은 좁게(끝의 마침표는 ASCII 하나, 앞뒤 공백은 ASCII 공백류만)."""
        for text in ("M075 승인" + chr(0x3002), chr(0x3000) + "M075 승인", "M075 승인" + chr(0x3000), "M075 승인" + chr(0xFF0E), chr(0xA0) + "M075 승인" + chr(0xA0)):
            with self.subTest(text=repr(text)):
                self.assertIsNone(mp.parse_approval(text))
                self.assertIsNone(mp.check_approval_text(text).number)

    def test_a_newline_inside_is_not_an_approval(self):
        for text in ("M075\n승인", "M075 \n승인", "M075\r\n승인", "\n\nM075\n\n승인"):
            with self.subTest(text=repr(text)):
                self.assertIsNone(mp.parse_approval(text))

    def test_empty_and_non_text_input_is_not_an_approval(self):
        for value in ("", "   ", "\n", None, 75, 7.5, True, "M075 승인".encode(), ["M075 승인"], ("M075", "승인"), {"M075": "승인"}, object()):
            with self.subTest(value=repr(value)):
                self.assertIsNone(mp.parse_approval(value))
                self.assertEqual(mp.check_approval_text(value).reason, "empty")

    def test_a_very_long_text_is_not_an_approval(self):
        self.assertIsNone(mp.parse_approval("M075 승인" + " 가" * 3000))
        self.assertIsNone(mp.parse_approval(" " * 5000 + "승인"))
        self.assertEqual(mp.check_approval_text("M075 승인" + " 가" * 3000).reason, "not_exact_form")

    def test_every_refusal_carries_the_exact_form_again(self):
        for text in ("확인했습니다", "승인", "M075 M076 승인", "M75 승인", "M075 승인하되", "", "그냥 좋아요"):
            with self.subTest(text=text):
                result = mp.check_approval_text(text)
                self.assertIsNone(result.number)
                self.assertIn(result.reason, mp.APPROVAL_REASONS)
                self.assertNotEqual(result.reason, "ok")
                self.assertIn("M075 승인", result.guidance)
                self.assertIn("병합 번호", result.guidance)

    def test_the_reason_codes_are_the_documented_seven(self):
        self.assertEqual(mp.APPROVAL_REASONS, ("ok", "empty", "rejected_phrase", "no_number", "several_numbers", "bad_number", "not_exact_form"))

    def test_the_result_is_immutable(self):
        result = mp.check_approval_text("M075 승인")
        with self.assertRaises(Exception):
            result.number = "M076"


class ApprovalValidityTest(unittest.TestCase):
    def test_the_approved_number_must_equal_the_pr_number_exactly(self):
        self.assertTrue(mp.approval_matches("M075", "M075"))
        self.assertTrue(mp.approval_matches("M1000", "M1000"))
        for approved, label in (("M075", "M076"), ("M075", "M750"), ("M75", "M75"), ("M0075", "M0075"), ("m075", "M075"), ("M075", "m075"), ("M075", None), (None, "M075"), (None, None),
                                ("M075", "[M075]"), ("M075 ", "M075"), ("M075", "M075 "), ("M075", ""), ("", ""), (75, 75), ("M000", "M000"), ("P075", "P075")):
            with self.subTest(approved=approved, label=label):
                self.assertFalse(mp.approval_matches(approved, label))

    def test_the_pr_title_number_is_the_leading_single_tag(self):
        for title, label in (("[M075] 앱을 닫아도 초안 저장", "M075"), ("[M1000] x", "M1000"), ("[M075]", "M075"), ("[M075]x", "M075")):
            with self.subTest(title=title):
                self.assertEqual(mp.pr_title_label(title), label)
        for title in (" [M075] x", "제목 [M075]", "[M075] [M076] x", "[M075] 제목 (이전 [M074] 이후)", "[R-175] 제목", "[M75] x", "[m075] x", "[M0075] x", "[M000] x", "제목", "", None, 75, ["[M075]"]):
            with self.subTest(title=title):
                self.assertIsNone(mp.pr_title_label(title))

    def test_a_commit_added_after_the_approval_voids_it(self):
        paths = ["pipeline/a.py", "tests/test_a.py"]
        self.assertTrue(mp.approval_still_valid(SHA_A, SHA_A, paths, paths))
        self.assertFalse(mp.approval_still_valid(SHA_A, SHA_B, paths, paths))
        self.assertFalse(mp.approval_still_valid(SHA_B, SHA_A, paths, paths))
        self.assertTrue(mp.approval_still_valid(SHA_A.upper().replace("1", "A"), SHA_A.replace("1", "a"), paths, paths))     # 대소문자만 다른 같은 해시

    def test_a_changed_file_list_voids_the_approval(self):
        base = ["pipeline/a.py", "tests/test_a.py"]
        for current in (base + ["docs/x.md"], ["pipeline/a.py"], ["pipeline/a.py", "tests/test_b.py"], ["pipeline/b.py", "tests/test_a.py"], ["pipeline/a.py", "tests/test_a.py", "pipeline/a2.py"]):
            with self.subTest(current=current):
                self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, base, current))
                self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, current, base))

    def test_the_file_list_is_compared_as_a_set_of_normalized_paths(self):
        self.assertTrue(mp.approval_still_valid(SHA_A, SHA_A, ["a.py", "b.py"], ["b.py", "a.py"]))
        self.assertTrue(mp.approval_still_valid(SHA_A, SHA_A, ["a.py"], ["./a.py"]))
        self.assertTrue(mp.approval_still_valid(SHA_A, SHA_A, ["pipeline\\a.py"], ["pipeline/a.py"]))
        self.assertTrue(mp.approval_still_valid(SHA_A, SHA_A, ["a.py", "a.py"], ["a.py"]))
        self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, ["A.py"], ["a.py"]))                       # 이름은 대소문자를 구분해 비교한다

    def test_missing_or_malformed_values_void_the_approval(self):
        paths = ["a.py"]
        for sha in ("abc1234", "", None, 123, "g" * 40, "1" * 39, "1" * 41, [SHA_A], b"1" * 40):
            with self.subTest(sha=sha):
                self.assertFalse(mp.approval_still_valid(sha, sha, paths, paths))
                self.assertFalse(mp.approval_still_valid(SHA_A, sha, paths, paths))
                self.assertFalse(mp.approval_still_valid(sha, SHA_A, paths, paths))
        for bad in ([], None, "a.py", ["../x.py"], [None], [1], ["/abs.py"], 5, [""]):
            with self.subTest(paths=bad):
                self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, bad, bad))
                self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, paths, bad))
                self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, bad, paths))

    def test_a_space_a_tab_and_a_hyphen_in_a_name_are_fine_but_control_characters_are_not(self):
        for good in ("a b/c d.py", "a-b/c_d.py", "한글/파일.md", "a" + chr(32) + "b"):
            self.assertEqual(mp.normalize_repo_path(good), good)
        for control in (0, 1, 8, 9, 10, 13, 27, 31, 127):
            with self.subTest(code=control):
                self.assertIsNone(mp.normalize_repo_path("a" + chr(control) + "b" if control not in (9, 10, 13) else "a/b" + chr(control) + "c"), control)

    SPACE_PATHS = (" docs/x.html", chr(0xA0) + "tests/page.html", chr(0x3000) + "tests/x.html", chr(0x2003) + "인수인계/x.html", "  pipeline/page.html", " WORKLOG.md", " scripts/x.js",
                   chr(0x85) + "docs/x.html", chr(0x2028) + "docs/x.html", chr(0x1F) + "docs/x", chr(9) + "tests/x.html", chr(0x2029) + "docs/x", chr(0x202F) + "docs/x", chr(0x1680) + "docs/x")

    def test_a_path_whose_segment_has_whitespace_around_it_is_refused(self):
        """맨 앞의 공백이 구간 이름을 바꿔 내부 폴더(docs·tests·인수인계)처럼 보이게 하던 우회를 막는다(N-M1) — 어느 구간이든 앞뒤 공백이면 확인할 수 없는 입력이다."""
        for path in self.SPACE_PATHS + ("docs /x", "docs/x ", "docs/ x", "docs/x" + chr(9), "docs" + chr(0xA0) + "/x", "a/" + chr(0x3000) + "/b", " ", "a/ /b", "./ docs/x", "docs/./ x",
                                         " " + chr(92) + "docs" + chr(92) + "x", "docs" + chr(92) + " x"):
            with self.subTest(path=repr(path)):
                self.assertIsNone(mp.normalize_repo_path(path))

    def test_every_unicode_whitespace_is_refused_in_front_in_the_middle_and_at_the_end(self):
        spaces = [chr(code) for code in range(0x30000) if chr(code).isspace()]
        self.assertGreater(len(spaces), 20)
        for space in spaces:
            for path in (space + "docs/x.html", "docs" + space + "/x.html", "docs/" + space + "x.html", "docs/x.html" + space):
                with self.subTest(code=hex(ord(space)), path=repr(path)):
                    if path == "docs/x.html" + space and space in (chr(10), chr(13)):
                        self.assertEqual(mp.normalize_repo_path(path), "docs/x.html")               # 줄 끝의 줄 바꿈만 뗀다
                    else:
                        self.assertIsNone(mp.normalize_repo_path(path))

    def test_only_the_line_end_is_trimmed(self):
        for path in ("docs/x.html", "docs/x.html" + chr(10), "docs/x.html" + chr(13) + chr(10), "docs/x.html" + chr(10) + chr(10), "docs/x.html" + chr(13)):
            self.assertEqual(mp.normalize_repo_path(path), "docs/x.html", repr(path))
        for path in ("docs/x.html " + chr(10), "docs/x.html" + chr(10) + " ", chr(10) + "docs/x.html", "docs/" + chr(10) + "x.html", chr(13) + "docs/x.html"):
            self.assertIsNone(mp.normalize_repo_path(path), repr(path))

    def test_control_characters_anywhere_refuse_the_path_including_del_and_the_c1_range(self):
        for code in list(range(0, 32)) + list(range(127, 160)):
            with self.subTest(code=hex(code)):
                self.assertIsNone(mp.normalize_repo_path("a" + chr(code) + "b/c.py"))
                self.assertIsNone(mp.normalize_repo_path("a/b" + chr(code) + "c.py"))
                self.assertIsNone(mp.normalize_repo_path("a/b/c.py" + chr(code) + "x"))
        for code in (160, 173, 0x200B, 0x200E, 0x202E, 0xFEFF):                                    # 제어 문자가 아닌 것(보이지 않는 글자 등)은 이름 일부라 정규화는 그대로 두고 분류가 공개 파일로 막는다
            path = "a/b" + chr(code) + "c.py"
            self.assertEqual(mp.normalize_repo_path(path), path)

    def test_only_a_plain_str_is_a_path(self):
        class Path(str):
            pass

        self.assertIsNone(mp.normalize_repo_path(Path("docs/x.html")))
        self.assertEqual(mp.normalize_repo_path(str(Path("docs/x.html"))), "docs/x.html")

    def test_a_refused_path_voids_an_approval(self):
        for path in self.SPACE_PATHS:
            self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, [path], [path]), repr(path))
            self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, ["pipeline/a.py", path], ["pipeline/a.py", path]), repr(path))

    def test_normalize_path(self):
        self.assertEqual(mp.normalize_repo_path("a/b.py"), "a/b.py")
        self.assertEqual(mp.normalize_repo_path("./a//b.py"), "a/b.py")
        self.assertEqual(mp.normalize_repo_path("a" + chr(92) + "b.py" + chr(10)), "a/b.py")                                         # 줄 끝의 줄 바꿈만 뗀다
        for bad in ("", " ", ".", "./", "..", "a/../b", "../a", "/a", "\\a", "C" + ":/a", "C" + ":\\a", "a\x00b", "a\x1bb", "a\x7fb", "a" + chr(127), None, 5, b"a", ["a"]):
            with self.subTest(bad=repr(bad)):
                self.assertIsNone(mp.normalize_repo_path(bad))


class ApprovalLedgerTest(unittest.TestCase):
    def test_an_approval_is_used_once(self):
        ledger = mp.ApprovalLedger()
        first = ledger.consume("M075", 198)
        self.assertTrue(first.ok)
        self.assertEqual(first.reason, "")
        again = ledger.consume("M075", 198)
        self.assertFalse(again.ok)
        self.assertIn("한 번 쓴 승인", again.reason)
        self.assertEqual(ledger.consumed_numbers, ("M075",))

    def test_one_approval_cannot_be_reused_for_another_pr(self):
        ledger = mp.ApprovalLedger()
        self.assertTrue(ledger.consume("M075", 198).ok)
        other = ledger.consume("M075", 199)
        self.assertFalse(other.ok)
        self.assertIn("다른 PR", other.reason)

    def test_one_pr_cannot_be_merged_under_a_second_approval(self):
        ledger = mp.ApprovalLedger()
        self.assertTrue(ledger.consume("M075", 198).ok)
        second = ledger.consume("M076", 198)
        self.assertFalse(second.ok)
        self.assertIn("이미 다른 승인", second.reason)
        self.assertEqual(ledger.consumed_numbers, ("M075",))                                  # 거절은 기록을 바꾸지 않는다
        self.assertTrue(ledger.consume("M076", 200).ok)                                         # 새 번호·새 PR 은 된다

    def test_malformed_input_is_refused_without_a_record(self):
        ledger = mp.ApprovalLedger()
        for number, pr_number in (("M75", 1), ("m075", 1), (None, 1), ("M075", 0), ("M075", -3), ("M075", True), ("M075", "198"), ("M075", None), ("M075", 1.0), (75, 75)):
            with self.subTest(number=number, pr_number=pr_number):
                self.assertFalse(ledger.consume(number, pr_number).ok)
        self.assertEqual(ledger.consumed_numbers, ())

    def test_the_ledger_can_start_from_the_merged_history(self):
        ledger = mp.ApprovalLedger([("M070", 190), ("M071", 191)])
        self.assertEqual(ledger.consumed_numbers, ("M070", "M071"))
        self.assertFalse(ledger.consume("M070", 300).ok)
        self.assertFalse(ledger.consume("M072", 191).ok)
        self.assertTrue(ledger.consume("M072", 192).ok)

    def test_consumed_numbers_are_sorted_whatever_the_order_they_were_given(self):
        """I3(T4 — NW18): consumed_numbers 는 번호 순으로 정렬해 돌려준다 — 번호 12개를 거꾸로 넣어도 같다(번호 둘짜리 예시만으로는 해시 순서가 우연히 맞아 정렬을 지운 변이가 해시 시드에 따라 살아남는다)."""
        numbers = ["M%03d" % (80 - 3 * step) for step in range(12)]                                  # M080, M077, ... M047 — 거꾸로
        ledger = mp.ApprovalLedger([(number, 300 + index) for index, number in enumerate(numbers)])
        self.assertEqual(ledger.consumed_numbers, tuple(sorted(numbers)))
        ledger = mp.ApprovalLedger()
        for index, number in enumerate(numbers):
            self.assertTrue(ledger.consume(number, 300 + index).ok)
        self.assertEqual(ledger.consumed_numbers, tuple(sorted(numbers)))
        self.assertNotEqual(list(ledger.consumed_numbers), numbers)                                   # 넣은 순서와 다르다 = 정말 정렬해서 돌려준다

    def test_a_malformed_history_is_an_error_not_a_silent_start(self):
        for bad in ([("M75", 1)], [("M070", 0)], [("M070",)], [5], 5, [("M070", 190, 1)]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    mp.ApprovalLedger(bad)

    def test_two_ledgers_do_not_share_state(self):
        first, second = mp.ApprovalLedger(), mp.ApprovalLedger()
        self.assertTrue(first.consume("M075", 198).ok)
        self.assertTrue(second.consume("M075", 198).ok)


class ClassifyAllowedTest(unittest.TestCase):
    """AI 병합 가능 7종의 대표 입력은 운영자 전용 12항목에 걸리지 않아 ai_ok 다."""

    CASES = (
        ("일반 프로그램 코드", "blog", ["pipeline/topics.py", "pipeline/ranker.py"],"def pick(items):\n    return items[0]\n"),
        ("일반 UI", "desktop", ["src/chanceblog_desktop/ui/pages/home.py"], "self.title.setText('홈')\n"),
        ("시험", "blog", ["tests/test_topics.py"], "self.assertEqual(1, 1)\n"),
        ("문서", "blog", ["docs/GLOSSARY.md"], "용어 설명을 한 줄 더합니다.\n"),
        ("로컬 저장·조회", "desktop", ["src/chanceblog_desktop/content/store.py"], "path.write_text(data, encoding='utf-8')\n"),
        ("오류 수정", "blog", ["pipeline/rounding.py"], "if value is None:\n    return 0\n"),
        ("접근성·성능 개선", "desktop", ["src/chanceblog_desktop/ui/core/focus.py"], "widget.setAccessibleName('저장')\n@cache\n"),
    )

    def test_the_seven_scopes_are_ai_ok(self):
        self.assertEqual(tuple(case[0] for case in self.CASES), SCOPES_7)
        for scope, kind, paths, text in self.CASES:
            with self.subTest(scope=scope):
                result = classify(kind, paths, text)
                self.assertEqual((result.tier, result.categories, result.extra_flags, result.reasons), ("ai_ok", (), (), ()))
                self.assertFalse(result.operator_only)

    def test_ai_ok_needs_no_answer_for_the_six_machine_checked_items(self):
        result = mp.classify_change("blog", ["pipeline/topics.py"], GOOD_TEXT, dict(DECLARED_OK))
        self.assertEqual(result.tier, "ai_ok")
        result = mp.classify_change("blog", ["pipeline/topics.py"], GOOD_TEXT, dict(DECLARED_OK, **{code: False for code in mp.OPERATOR_ONLY_CODES}))
        self.assertEqual(result.tier, "ai_ok")

    def test_common_words_that_only_look_like_the_watched_ones_stay_ai_ok(self):
        for text in ("tokens = []\n", "max_tokens = 100\n", "tokenizer.encode(text)\n", "detokenize(x)\n", "sort_key = lambda r: r.key\n", "for key in table:\n", "keyboard.press()\n",
                     "docs/about.md 를 읽습니다\n", "Ads 대시보드는 읽기 전용입니다\n"):
            with self.subTest(text=text):
                self.assertEqual(classify("blog", ["pipeline/topics.py"], text).tier, "ai_ok")

    def test_paths_that_only_look_like_the_watched_ones_stay_ai_ok(self):
        for kind, path in (("blog", "docs/about.md"), ("blog", "tests/fixtures/page.html"), ("blog", "docs/assets/x.png"), ("blog", "pipeline/tokenizer.py"), ("blog", "docs/GLOSSARY.md"),
                           ("blog", "인수인계/작업내용.md"), ("blog", "pipeline/VERSION"), ("desktop", "README.md"), ("desktop", "index.html"), ("desktop", "_posts/x.md"), ("desktop", "src/x/version.py"),
                           ("desktop", "docs/RELEASE.md"), ("blog", "pipeline/blogs.py"), ("blog", "tests/fixtures/_config.json")):
            with self.subTest(path=path):
                self.assertEqual(classify(kind, [path]).tier, "ai_ok", path)

    def test_the_result_knows_whether_it_is_operator_only(self):
        """I1(T3 — NW33): Classification.operator_only 는 tier 가 운영자 전용일 때만 참이다 — 호출하는 쪽이 이 속성으로 가른다."""
        self.assertFalse(classify("blog", ["pipeline/a.py"], GOOD_TEXT).operator_only)
        self.assertTrue(classify("blog", [".github/workflows/x.yml"], "").operator_only)
        self.assertTrue(classify("blog", ["pipeline/a.py"], "adsbygoogle").operator_only)

    def test_the_result_is_deterministic_and_order_free(self):
        paths = ["pipeline/b.py", "pipeline/a.py", "tests/test_a.py"]
        first = classify("blog", paths, GOOD_TEXT)
        self.assertEqual(first, classify("blog", list(reversed(paths)), GOOD_TEXT))
        self.assertEqual(first.paths, ("pipeline/a.py", "pipeline/b.py", "tests/test_a.py"))
        self.assertEqual(first["tier"], "ai_ok")
        self.assertEqual(first.to_dict()["paths"], list(first.paths))
        with self.assertRaises(Exception):
            first.tier = "operator_only"


class ClassifyOperatorOnlyTest(unittest.TestCase):
    """운영자 전용 12항목 각각이 걸리는 대표 입력 — 경로·내용·선언 참·선언 미응답."""

    def assert_flags(self, result, code):
        self.assertEqual(result.tier, "operator_only")
        self.assertIn(code, result.categories)
        self.assertTrue(result.reasons)

    def test_workflow_any_line_under_dot_github(self):
        for path in (".github/workflows/ci.yml", ".github/CODEOWNERS", ".github/ISSUE_TEMPLATE/x.yml", "sub/.github/x.yml", ".GitHub/Workflows/X.yml", "./.github/workflows/ci.yml",
                     ".github\\workflows\\ci.yml", ".github/a.md"):
            with self.subTest(path=path):
                self.assert_flags(classify("blog", [path]), "workflow")
                self.assert_flags(classify("desktop", [path]), "workflow")

    def test_a_single_workflow_line_among_many_files_still_flags(self):
        paths = ["pipeline/a.py", "tests/test_a.py", "docs/a.md", ".github/workflows/ci.yml"]
        result = classify("blog", paths, GOOD_TEXT)
        self.assertEqual(result.categories, ("workflow",))
        self.assertTrue(any(".github/workflows/ci.yml" in reason for reason in result.reasons))

    def test_ads_by_path(self):
        for path in ("index.html", "ads.txt", "app-ads.txt", "_config.yml", "_layouts/default.html", "_includes/ad.html", "sub/index.html", "INDEX.HTML", "sub/ads.txt", "x/_layouts/a.html"):
            with self.subTest(path=path):
                self.assert_flags(classify("blog", [path]), "ads")

    def test_ads_by_added_text(self):
        for text in ('<ins class="adsbygoogle"></ins>\n', "AdsByGoogle", 'data-ad-client="ca-pub-"', "CA-PUB-", "x = 'adsbygoogle'"):
            with self.subTest(text=text):
                self.assert_flags(classify("blog", ["pipeline/x.py"], text), "ads")
                self.assert_flags(classify("desktop", ["src/x.py"], text), "ads")

    def test_public_content_by_path(self):
        for path in ("_posts/2026-11-15-a.md", "sub/_posts/b.md", "about.md", "contact.md", "privacy.md", "categories.md", "pages.json", "posts.json", "feed.xml", "robots.txt", "assets/x.png",
                     "assets/css/a.css", "404.html", "googleabc.html", "_blogger_drafts/a.md", "_blogger_ko_drafts/a.md", "_naver_drafts/a.md", "history.json", "blogger_history.json",
                     "naver_history.json", "ABOUT.MD"):
            with self.subTest(path=path):
                self.assert_flags(classify("blog", [path]), "public_content")

    def test_publish_settings_files_map_to_their_items(self):
        expected = {"pipeline/blogs.json": {"publish_mode", "auto_publish", "ads"}, "pipeline/source_registry.json": {"provider_activation"},
                    "pipeline/ops_inbox_policy.json": {"pipeline_pause", "publish_mode"}}
        for path, codes in expected.items():
            with self.subTest(path=path):
                result = classify("blog", [path])
                self.assertEqual(result.tier, "operator_only")
                self.assertEqual(set(result.categories), codes)

    def test_case_variants_of_the_publish_settings_files_are_still_operator_only(self):
        """R4(T3 — DD02): 발행 설정 파일 이름의 대소문자 변형도 같은 항목들로 걸린다 — 접지 않은 경로로 찾으면 맨 위가 pipeline 이라 기본 거부도 안 걸려 ai_ok 가 된다."""
        blogs, registry, inbox = {"publish_mode", "auto_publish", "ads"}, {"provider_activation"}, {"pipeline_pause", "publish_mode"}
        for path, codes in (("pipeline/Blogs.json", blogs), ("Pipeline/Blogs.json", blogs), ("PIPELINE/BLOGS.JSON", blogs), ("pipeline/Source_Registry.json", registry),
                            ("pipeline/OPS_INBOX_POLICY.JSON", inbox)):
            with self.subTest(path=path):
                result = classify("blog", [path])
                self.assertEqual(result.tier, "operator_only")
                self.assertEqual(set(result.categories), codes)

    def test_pipeline_pause_by_text_and_declaration(self):
        self.assert_flags(classify("blog", ["pipeline/x.py"], "if PIPELINE_PAUSE:\n    return\n"), "pipeline_pause")
        self.assert_flags(classify("blog", ["pipeline/x.py"], "pipeline_pause = 1"), "pipeline_pause")
        self.assert_flags(classify("desktop", ["src/x.py"], "PIPELINE_PAUSE"), "pipeline_pause")

    def test_dependencies_by_path(self):
        for path in ("requirements.txt", "requirements-dev.txt", "sub/requirements-edits.txt", "constraints.txt", "vendor/pipeline/x.py", "src/vendor/a.py", "package.json", "package-lock.json",
                     "pyproject.toml", "Pipfile", "Pipfile.lock", "poetry.lock", "yarn.lock", "uv.lock", "setup.py", "setup.cfg", "Gemfile", "Gemfile.lock", "node_modules/x.js", "REQUIREMENTS.TXT"):
            with self.subTest(path=path):
                self.assert_flags(classify("blog", [path]), "dependencies")
                self.assert_flags(classify("desktop", [path]), "dependencies")

    def test_credentials_by_path(self):
        for path in (".env", ".env.example", ".env.local", "sub/.env", "certs/server.pem", "a/id.key", "x.p12", "x.pfx", "x.jks", "x.keystore", "client_secret_1.json", "token.json", "token-gmail.json",
                     "service-account.json", "my_service_account_key.json", "my_credentials.txt", "pipeline/secret_patterns.py", "tests/test_secret_invisible.py", "src/security/keystore.py",
                     "src/x/security/mask.py", "keyring/a.py", "id_rsa", "id_ed25519.pub", ".npmrc", ".pypirc", ".netrc"):
            with self.subTest(path=path):
                self.assert_flags(classify("blog", [path]), "credentials")
                self.assert_flags(classify("desktop", [path]), "credentials")

    def test_credentials_by_secret_shaped_values_never_echo_the_value(self):
        for name, value in FAKE_SECRETS.items():
            with self.subTest(name=name):
                result = classify("blog", ["pipeline/x.py"], "note " + value + " end\n")
                self.assert_flags(result, "credentials")
                joined = " ".join(result.reasons)
                self.assertIn("비밀 모양의 값이 있습니다", joined)
                self.assertNotIn(value, joined)
                self.assertNotIn("CANARY", joined)
                self.assert_flags(classify("desktop", ["src/x.py"], "note " + value + " end\n"), "credentials")

    def test_credentials_by_a_long_quoted_assignment(self):
        value = "pass" + "word = '" + "CANARY_" + "L" * 20 + "'"
        result = classify("blog", ["pipeline/x.py"], value)
        self.assert_flags(result, "credentials")
        self.assertNotIn("CANARY", " ".join(result.reasons))

    def test_credentials_by_secrets_reference_and_names(self):
        for text in ("secrets.SOME_NAME", "uses secrets . FOO", "secrets['FOO']", "GEMINI_API_KEY = os", "api_key = 1", "API-KEY", "ApiKey", "apikey", "my secret", "Password", "passwd", "credentials", "private key",
                     "private_key", "access-key", "TELEGRAM_BOT_TOKEN", "token", "bot_token", "accessToken", "mytoken", "비밀번호", "시크릿", "API 키", "자격 증명", "봇 토큰", "인증 정보"):
            with self.subTest(text=text):
                self.assert_flags(classify("blog", ["pipeline/x.py"], text), "credentials")

    def test_data_deletion_or_migration_by_text(self):
        for text in ("DROP TABLE drafts;", "drop   database x", "delete from drafts where id = 1", "TRUNCATE TABLE x", "shutil.rmtree(path)", "rmtree(path)", "마이그레이션 계획", "def migrate():", "Migration", "migrated rows",
                     "migrating"):
            with self.subTest(text=text):
                self.assert_flags(classify("blog", ["pipeline/x.py"], text), "data_deletion_migration")

    def test_each_of_the_twelve_items_is_flagged_when_declared_true(self):
        for code, label in mp.OPERATOR_ONLY_ITEMS:
            with self.subTest(code=code):
                declared = dict(DECLARED_OK)
                declared[code] = True
                result = classify("blog", ["pipeline/topics.py"], GOOD_TEXT, declared)
                self.assert_flags(result, code)
                self.assertTrue(any(label in reason for reason in result.reasons))

    def test_each_of_the_six_declared_items_is_flagged_when_unanswered(self):
        for code in mp.DECLARED_REQUIRED:
            for how in ("missing", None, "아니오", "no", 0, 1, [], "", object()):
                with self.subTest(code=code, how=repr(how)):
                    declared = dict(DECLARED_OK)
                    if how == "missing":
                        del declared[code]
                    else:
                        declared[code] = how
                    self.assert_flags(classify("blog", ["pipeline/topics.py"], GOOD_TEXT, declared), code)

    def test_an_unanswered_declaration_is_operator_only_for_all_six(self):
        for declared in (None, {}):
            result = mp.classify_change("blog", ["pipeline/topics.py"], GOOD_TEXT, declared)
            self.assertEqual(result.tier, "operator_only")
            self.assertEqual(set(result.categories), set(mp.DECLARED_REQUIRED))
        self.assertEqual(mp.classify_change("blog", ["pipeline/topics.py"], GOOD_TEXT).tier, "operator_only")

    def test_the_other_six_items_are_flagged_when_declared_with_anything_but_false_or_none(self):
        others = [code for code in mp.OPERATOR_ONLY_CODES if code not in mp.DECLARED_REQUIRED]
        self.assertEqual(len(others), 6)
        for code in others:
            for value in (True, "예", 1, "no"):
                with self.subTest(code=code, value=value):
                    self.assert_flags(classify("blog", ["pipeline/topics.py"], GOOD_TEXT, dict(DECLARED_OK, **{code: value})), code)
            for value in (False, None):
                with self.subTest(code=code, value=value):
                    self.assertEqual(classify("blog", ["pipeline/topics.py"], GOOD_TEXT, dict(DECLARED_OK, **{code: value})).tier, "ai_ok")

    def test_a_false_declaration_never_overrides_a_path_or_content_rule(self):
        everything_false = {code: False for code in mp.OPERATOR_ONLY_CODES}
        for kind, path, text, code in (("blog", ".github/workflows/ci.yml", "", "workflow"), ("blog", "index.html", "", "ads"), ("blog", "_posts/a.md", "", "public_content"),
                                       ("blog", "pipeline/blogs.json", "", "publish_mode"), ("blog", "pipeline/source_registry.json", "", "provider_activation"),
                                       ("blog", "requirements.txt", "", "dependencies"), ("blog", ".env", "", "credentials"), ("blog", "pipeline/x.py", "PIPELINE_PAUSE", "pipeline_pause"),
                                       ("blog", "pipeline/x.py", "adsbygoogle", "ads"), ("blog", "pipeline/x.py", "DROP TABLE x", "data_deletion_migration")):
            with self.subTest(path=path, text=text):
                self.assert_flags(mp.classify_change(kind, [path], text, dict(everything_false)), code)

    def test_every_documented_rule_word_triggers_something(self):
        samples = {
            ".github/": ("blog", [".github/x.yml"], ""), "index.html": ("blog", ["index.html"], ""), "_layouts/": ("blog", ["_layouts/a.html"], ""), "_includes/": ("blog", ["_includes/a.html"], ""),
            "_config.yml": ("blog", ["_config.yml"], ""), "ads.txt": ("blog", ["ads.txt"], ""), "adsbygoogle": ("blog", ["a.py"], "adsbygoogle"), "ca-pub-": ("blog", ["a.py"], "ca-pub-"),
            "_posts/": ("blog", ["_posts/a.md"], ""), "about.md": ("blog", ["about.md"], ""), "contact.md": ("blog", ["contact.md"], ""), "privacy.md": ("blog", ["privacy.md"], ""),
            "categories.md": ("blog", ["categories.md"], ""), "pages.json": ("blog", ["pages.json"], ""), "assets/": ("blog", ["assets/a.png"], ""),
            "pipeline/blogs.json": ("blog", ["pipeline/blogs.json"], ""), "pipeline/source_registry.json": ("blog", ["pipeline/source_registry.json"], ""),
            "pipeline/ops_inbox_policy.json": ("blog", ["pipeline/ops_inbox_policy.json"], ""), "requirements*.txt": ("blog", ["requirements-x.txt"], ""), "vendor/": ("desktop", ["vendor/a.py"], ""),
            "package*.json": ("blog", ["package-lock.json"], ""), "pyproject.toml": ("blog", ["pyproject.toml"], ""), "Pipfile*": ("blog", ["Pipfile.lock"], ""), "*.lock": ("blog", ["a.lock"], ""),
            ".env*": ("blog", [".env.x"], ""), "secrets.": ("blog", ["a.py"], "secrets.X"), "PIPELINE_PAUSE": ("blog", ["a.py"], "PIPELINE_PAUSE"), "VERSION": ("desktop", ["VERSION"], ""),
            "README.md": ("blog", ["README.md"], ""), "CNAME": ("blog", ["CNAME"], ""), ".nojekyll": ("blog", [".nojekyll"], ""), "requirements*.in": ("blog", ["requirements-x.in"], ""),
            "requirements/": ("blog", ["requirements/base.txt"], ""), "constraints*": ("blog", ["constraints-x.txt"], ""), "node_modules/": ("blog", ["node_modules/x.js"], ""),
            "pnpm-lock.yaml": ("blog", ["pnpm-lock.yaml"], ""), ".gitmodules": ("blog", [".gitmodules"], ""), "environment*.yml": ("blog", ["environment-x.yml"], ""),
            "conda": ("blog", ["conda/env.yml"], ""), "os.remove": ("blog", ["a.py"], "os.remove(p)"), "unlink(": ("blog", ["a.py"], "p.unlink()"), "rm -rf": ("blog", ["a.sh"], "rm -rf x"),
            "DROP COLUMN": ("blog", ["a.py"], "DROP COLUMN c"), "DROP INDEX": ("blog", ["a.py"], "DROP INDEX i"), "Authorization": ("blog", ["a.py"], "Authorization: Bearer x"),
            "sk_live_": ("blog", ["a.py"], "k = '" + "sk_live_" + "CANARY" + "a" * 18 + "'"), "sk_test_": ("blog", ["a.py"], "k = '" + "sk_test_" + "CANARY" + "a" * 18 + "'"),
            "deps.txt": ("blog", ["deps.txt"], ""), "Dockerfile": ("blog", ["Dockerfile"], ""), "Makefile": ("blog", ["Makefile"], ""),
        }
        self.assertEqual(set(samples), set(mp.DOCUMENTED_RULE_WORDS))
        for word, (kind, paths, text) in samples.items():
            with self.subTest(word=word):
                self.assertEqual(classify(kind, paths, text).tier, "operator_only")

    def test_the_policy_files_themselves_are_operator_only(self):
        self.assertEqual(mp.POLICY_SELF_FILES, ("docs/AI_MERGE_POLICY.md", "pipeline/merge_policy.py", "tests/test_merge_policy.py", "tests/test_merge_policy_docs.py"))
        for kind in ("blog", "desktop"):
            for path in mp.POLICY_SELF_FILES + ("DOCS/ai_merge_policy.md", "./pipeline/merge_policy.py"):
                with self.subTest(kind=kind, path=path):
                    result = classify(kind, [path])
                    self.assertEqual(result.tier, "operator_only")
                    self.assertEqual(result.extra_flags, ("policy_self",))
                    self.assertEqual(result.categories, ())

    def test_several_items_are_listed_in_policy_order(self):
        result = classify("blog", ["requirements.txt", ".github/workflows/ci.yml", "index.html", "_posts/a.md"], "secrets.X")
        order = [code for code in mp.OPERATOR_ONLY_CODES if code in result.categories]
        self.assertEqual(list(result.categories), order)
        self.assertEqual(set(result.categories), {"workflow", "ads", "public_content", "dependencies", "credentials"})

    def test_many_files_are_summarized_not_listed_one_by_one(self):
        paths = ["_posts/2026-11-15-%03d.md" % number for number in range(100)]
        result = classify("blog", paths)
        self.assertEqual(result.categories, ("public_content",))
        self.assertLessEqual(len(result.reasons), 40)
        self.assertTrue(any("외 97개" in reason for reason in result.reasons))
        self.assertEqual(len(result.paths), 100)

    def test_a_path_with_a_secret_shape_is_masked_in_the_reasons(self):
        value = FAKE_SECRETS["google"]
        result = classify("blog", [".github/workflows/" + value + ".yml"])
        self.assertEqual(result.categories, ("workflow",))
        joined = " ".join(result.reasons)
        self.assertNotIn(value, joined)
        self.assertIn("가렸습니다", joined)


class ClassifyDesktopTest(unittest.TestCase):
    def test_desktop_rules(self):
        for path, categories, extras in (
                (".github/workflows/ci.yml", ("workflow",), ()), ("requirements.txt", ("dependencies",), ()), ("vendor/pipeline/console.py", ("dependencies",), ()),
                ("VERSION", (), ("packaging_release",)), ("app.spec", (), ("packaging_release",)), ("installer/setup.iss", (), ("packaging_release",)), ("build/x.py", (), ("packaging_release",)),
                ("packaging/a.py", (), ("packaging_release",)), ("src/chanceblog_desktop/security/mask.py", ("credentials",), ("safety_guard",)), (".env.example", ("credentials",), ()),
                ("pyproject.toml", ("dependencies",), ())):
            with self.subTest(path=path):
                result = classify("desktop", [path])
                self.assertEqual((result.tier, result.categories, result.extra_flags), ("operator_only", categories, extras))

    def test_blog_only_rules_do_not_apply_to_the_desktop_and_the_reverse(self):
        self.assertEqual(classify("desktop", ["index.html", "_posts/a.md", "about.md", "pipeline/blogs.json"]).tier, "ai_ok")
        for path in ("pipeline/VERSION", "pipeline/app.spec", "pipeline/installer/setup.iss", "pipeline/build/x.py"):                  # 패키징 규칙은 앱 저장소에만 적용된다
            self.assertEqual(classify("blog", [path]).tier, "ai_ok", path)
        for path in ("VERSION", "app.spec", "installer/setup.iss", "build/x.py"):                                                 # 블로그 저장소의 이런 맨 위 파일은 기본 거부(공개 파일)로 걸리지만 패키징 표시는 아니다
            result = classify("blog", [path])
            self.assertEqual((result.categories, result.extra_flags), (("public_content",), ()), path)


class ClassifyInvalidInputTest(unittest.TestCase):
    def assert_invalid(self, result):
        self.assertEqual(result.tier, "operator_only")
        self.assertIn("invalid_input", result.extra_flags)
        self.assertTrue(result.reasons)

    def test_an_unknown_repo_kind_is_not_ai_ok(self):
        for kind in ("web", "", "Blog", "BLOG", None, 3, ["blog"]):
            with self.subTest(kind=kind):
                self.assert_invalid(mp.classify_change(kind, ["pipeline/a.py"], "", dict(DECLARED_OK)))

    def test_a_bad_path_list_is_not_ai_ok(self):
        for paths in (None, [], "pipeline/a.py", ["a/../.github/x"], ["../a.py"], ["/etc/a.py"], ["C" + ":/a.py"], [None], [1], [""], ["a\x00b"], 5, ("a.py", None), ["a" + chr(127) + "b"]):
            with self.subTest(paths=paths):
                self.assert_invalid(mp.classify_change("blog", paths, "", dict(DECLARED_OK)))

    def test_a_drive_relative_path_is_not_ai_ok(self):
        """I1(T3 — PA12): 드라이브 글자만 붙고 '/' 가 없는 경로(`C:x`)도 저장소 안의 경로가 아니다 — 입력 오류다(`C:/x` 만 거르던 시험의 틈)."""
        for path in ("C:x", "c:foo/bar.py", "Z:a"):
            with self.subTest(path=path):
                self.assertIsNone(mp.normalize_repo_path(path))
                self.assert_invalid(mp.classify_change("blog", [path], "", dict(DECLARED_OK)))
                self.assert_invalid(mp.classify_change("desktop", ["pipeline/a.py", path], "", dict(DECLARED_OK)))

    def test_a_tilde_is_an_ordinary_path_character_but_delete_is_a_control_character(self):
        """I1(T3 — AU0048): 경로의 물결표(0x7e)는 평범한 글자라 거절하지 않고 DEL(0x7f)부터 제어 문자로 거절한다 — 제어 문자 범위의 아래쪽 끝."""
        tilde, delete = chr(126), chr(127)
        ok = mp.classify_change("blog", ["pipeline/a" + tilde + "b.py"], "", dict(DECLARED_OK))
        self.assertEqual((ok.tier, ok.extra_flags), ("ai_ok", ()))
        self.assertEqual(mp.normalize_repo_path("pipeline/a" + tilde + "b.py"), "pipeline/a" + tilde + "b.py")
        self.assert_invalid(mp.classify_change("blog", ["pipeline/a" + delete + "b.py"], "", dict(DECLARED_OK)))

    def test_a_mapping_is_not_a_path_list(self):
        """사전을 경로 목록으로 넘기면 키만 읽혀 값이 숨는다 — 경로 목록으로 보지 않는다(Q13)."""
        class MappingLike:
            def keys(self):
                return ["pipeline/a.py"]

            def __iter__(self):
                return iter(["pipeline/a.py"])

        for paths in ({"pipeline/a.py": 1}, {".github/x.yml": "x"}, {"pipeline/a.py": None}, MappingLike(), {}):
            with self.subTest(paths=repr(paths)):
                self.assert_invalid(mp.classify_change("blog", paths, "", dict(DECLARED_OK)))
                self.assert_invalid(mp.classify_change("desktop", paths, "", dict(DECLARED_OK)))
        for paths in (("pipeline/a.py",), {"pipeline/a.py"}, frozenset(["pipeline/a.py"]), iter(["pipeline/a.py"])):
            with self.subTest(paths=repr(paths)):
                self.assertEqual(mp.classify_change("blog", paths, "", dict(DECLARED_OK)).tier, "ai_ok")

    def test_a_path_with_whitespace_around_a_segment_is_not_ai_ok(self):
        """기본 거부·시험 면제·문서 면제를 공백 한 칸으로 속이지 못한다(N-M1) — 내부 폴더처럼 보이는 경로라도 입력 오류다."""
        for path in ApprovalValidityTest.SPACE_PATHS + ("docs /x.html", "docs/x.html "):
            for kind in ("blog", "desktop"):
                with self.subTest(path=repr(path), kind=kind):
                    self.assert_invalid(mp.classify_change(kind, [path], "", dict(DECLARED_OK)))
                    self.assert_invalid(mp.classify_change(kind, ["pipeline/a.py", path], "", dict(DECLARED_OK)))
                    self.assert_invalid(mp.classify_change(kind, [path], {path: "import requests" + chr(10)}, dict(DECLARED_OK)))
        self.assert_invalid(mp.classify_change("blog", [chr(0xA0) + "tests/page.html"], {"tests/page.html": ""}, dict(DECLARED_OK)))        # 키는 정상이어도 경로가 정상이 아니다
        self.assertEqual(mp.classify_change("blog", ["docs/x.html"], "", dict(DECLARED_OK)).tier, "ai_ok")

    def test_a_mapping_must_have_a_key_for_every_changed_file(self):
        """변경 파일 중 키가 빠진 파일의 바뀐 줄은 보이지 않는다 — 코드 파일의 키가 빠져도 통과하던 구멍(S-N2). 글이 없는 파일은 빈 글을 넣어야 한다."""
        paths = ["docs/x.md", "pipeline/y.py"]
        for given in ({"docs/x.md": "문서 한 줄" + chr(10)}, {"pipeline/y.py": "x = 1" + chr(10)}, {}, {"docs/x.md": "", "pipeline/z.py": ""}):
            with self.subTest(given=sorted(given)):
                result = mp.classify_change("blog", paths, given, dict(DECLARED_OK))
                self.assert_invalid(result)
        result = mp.classify_change("blog", paths, {"docs/x.md": "문서 한 줄" + chr(10)}, dict(DECLARED_OK))
        self.assertTrue(any("글이 없는 파일" in reason and "pipeline/y.py" in reason for reason in result.reasons), result.reasons)
        self.assertFalse(any("docs/x.md" in reason and "글이 없는 파일" in reason for reason in result.reasons))
        for given in ({"docs/x.md": "", "pipeline/y.py": ""}, {"docs/x.md": "문서", "pipeline/y.py": GOOD_TEXT}, {"./docs/x.md": "", "pipeline/y.py": ""},
                      {"docs/x.md": "", "pipeline" + chr(92) + "y.py": ""}):
            with self.subTest(ok=sorted(given)):
                self.assertEqual(mp.classify_change("blog", paths, given, dict(DECLARED_OK)).tier, "ai_ok")
        self.assert_invalid(mp.classify_change("blog", ["tests/t.py", "pipeline/y.py"], {"pipeline/y.py": ""}, dict(DECLARED_OK)))                         # 시험 파일의 키가 빠져도 마찬가지다(시험의 낱말 규칙이 안 보이지 않게)
        self.assert_invalid(mp.classify_change("blog", ["docs/x.md", "pipeline/y.py"], {"pipeline/y.py": ""}, dict(DECLARED_OK)))                          # 문서의 키가 빠져도 마찬가지다(문서의 비밀 모양이 안 보이지 않게)
        self.assertEqual(mp.classify_change("blog", ["tests/t.py", "docs/x.md"], {"tests/t.py": "", "docs/x.md": ""}, dict(DECLARED_OK)).tier, "ai_ok")
        self.assert_invalid(mp.classify_change("blog", ["old/a.py", "new/a.py"], {"new/a.py": "x = 1" + chr(10)}, dict(DECLARED_OK)))                  # 이름 바꾸기는 옛 경로의 키도 필요하다
        self.assertEqual(mp.classify_change("blog", ["pipeline/old_a.py", "pipeline/new_a.py"], {"pipeline/old_a.py": "", "pipeline/new_a.py": "x = 1" + chr(10)}, dict(DECLARED_OK)).tier, "ai_ok")

    def test_the_hidden_code_lines_attack_is_closed(self):
        """P 의 재현: 문서 키만 주고 코드 파일의 바뀐 줄(비밀 모양·외부 접속)을 숨기던 입력."""
        for hidden in ("import requests" + chr(10), FAKE_SECRETS["google"] + chr(10), "if PIPELINE_PAUSE:" + chr(10) + "    return" + chr(10)):
            result = mp.classify_change("blog", ["docs/x.md", "pipeline/y.py"], {"docs/x.md": "문서 한 줄" + chr(10)}, dict(DECLARED_OK))
            self.assert_invalid(result)
            self.assertEqual(mp.classify_change("blog", ["docs/x.md", "pipeline/y.py"], {"docs/x.md": "문서 한 줄" + chr(10), "pipeline/y.py": hidden}, dict(DECLARED_OK)).tier, "operator_only")

    def test_a_bad_changed_text_is_not_ai_ok(self):
        for text in (None, 5, ["x"], b"x", object()):
            with self.subTest(text=repr(text)):
                self.assert_invalid(mp.classify_change("blog", ["pipeline/a.py"], text, dict(DECLARED_OK)))
        self.assertEqual(mp.classify_change("blog", ["pipeline/a.py"], "", dict(DECLARED_OK)).tier, "ai_ok")
        self.assert_invalid(mp.classify_change("blog", ["pipeline/a.py"]))                                       # 글을 아예 안 주면 확인할 수 없는 입력이다

    def test_a_file_whose_changed_lines_could_not_be_read_is_none_and_never_an_empty_text(self):
        """R1(§7-2·§11-3): GitHub 가 너무 큰 diff·바이너리의 내용을 주지 않아 바뀐 줄을 읽지 못한 파일의 글은 빈 글이 아니라 None 으로 넘긴다 — None 도, 키가 없는 것도 입력 오류라 운영자 전용이다.
        빈 글은 바뀐 줄이 정말 없을 때(이름만 바뀐 파일·빈 파일 등)만 통과한다. 코드는 빈 글을 '읽어 보니 바뀐 줄이 없다'는 결과로 믿으므로(읽지 못한 코드 파일을 빈 글로 넘기면 그 파일의 내용 규칙을 통째로
        건너뛴다) 읽지 못한 파일을 None 으로 넘기는 약속은 호출자가 지킨다(문서 §11-3)."""
        paths = ["pipeline/a.py", "tests/test_a.py"]
        for label, given in (("한 파일만 None", {"pipeline/a.py": None, "tests/test_a.py": ""}), ("다른 파일만 None", {"pipeline/a.py": "", "tests/test_a.py": None}),
                             ("모두 None", {"pipeline/a.py": None, "tests/test_a.py": None}), ("글 전체가 None", None)):
            with self.subTest(label=label):
                result = mp.classify_change("blog", paths, given, dict(DECLARED_OK))
                self.assert_invalid(result)
                self.assertTrue(any("바뀐 줄의 글을 읽을 수 없습니다" in reason for reason in result.reasons), result.reasons)
        for label, given in (("읽지 못한 코드 파일의 키가 없음", {"tests/test_a.py": ""}), ("읽지 못한 시험 파일의 키가 없음", {"pipeline/a.py": ""}), ("키가 모두 없음", {})):
            with self.subTest(label=label):
                result = mp.classify_change("blog", paths, given, dict(DECLARED_OK))
                self.assert_invalid(result)
                self.assertTrue(any("바뀐 줄의 글이 없는 파일이 있습니다" in reason for reason in result.reasons), result.reasons)
                self.assertTrue(any("바뀐 줄이 정말 없는 파일은 빈 글, 읽지 못한 파일은 None 으로 넘기면 운영자 전용이 됩니다" in reason for reason in result.reasons), result.reasons)
                self.assertFalse(any("글이 없으면 빈 글을 넣어야 합니다" in reason for reason in result.reasons), result.reasons)                  # P4-3: 읽지 못한 파일에 빈 글을 넣으라는 말로 읽히지 않는다
        for label, given in (("글 전체가 빈 글", ""), ("파일마다 빈 글", {"pipeline/a.py": "", "tests/test_a.py": ""})):
            with self.subTest(label=label):
                result = mp.classify_change("blog", paths, given, dict(DECLARED_OK))
                self.assertEqual((result.tier, result.categories, result.extra_flags), ("ai_ok", (), ()))
        result = mp.classify_change("blog", paths, {"pipeline/a.py": None, "tests/test_a.py": ""}, dict(DECLARED_OK))
        self.assertEqual(result.tier, "operator_only")                                                         # 한 파일이라도 읽지 못했으면 나머지가 깨끗해도 통과하지 못한다

    def test_the_text_is_the_added_and_the_removed_lines_and_either_name_is_accepted(self):
        """바뀐 줄 전체(추가 + 지움)를 받는다 — 지운 줄에 들어 있던 광고 코드·PIPELINE_PAUSE·삭제 낱말도 걸린다. 예전 이름 added_text 도 받고 두 이름을 함께 쓰면 입력 오류다."""
        removed = "if PIPELINE_PAUSE:\n    return\n"                                                          # 이 줄을 지우는 변경의 지운 줄
        for how in ("positional", "changed_text", "added_text"):
            with self.subTest(how=how):
                if how == "positional":
                    result = mp.classify_change("blog", ["pipeline/draft_flow_x.py"], removed, dict(DECLARED_OK))
                elif how == "changed_text":
                    result = mp.classify_change("blog", ["pipeline/draft_flow_x.py"], changed_text=removed, declared=dict(DECLARED_OK))
                else:
                    result = mp.classify_change("blog", ["pipeline/draft_flow_x.py"], added_text=removed, declared=dict(DECLARED_OK))
                self.assertEqual((result.tier, result.categories, result.extra_flags), ("operator_only", ("pipeline_pause",), ()))
        for how in ("changed_text", "added_text"):
            with self.subTest(clean=how):
                self.assertEqual(mp.classify_change("blog", ["pipeline/a.py"], declared=dict(DECLARED_OK), **{how: GOOD_TEXT}).tier, "ai_ok")
        self.assert_invalid(mp.classify_change("blog", ["pipeline/a.py"], GOOD_TEXT, dict(DECLARED_OK), added_text=GOOD_TEXT))
        self.assert_invalid(mp.classify_change("blog", ["pipeline/a.py"], "", dict(DECLARED_OK), added_text=GOOD_TEXT))
        self.assert_invalid(mp.classify_change("blog", ["pipeline/a.py"], GOOD_TEXT, dict(DECLARED_OK), added_text=""))
        for what, line in (("광고", "adsbygoogle"), ("삭제", "DROP TABLE x"), ("키", "api_key = 1")):
            with self.subTest(removed=what):
                self.assertEqual(mp.classify_change("blog", ["pipeline/a.py"], "-" + line + "\n+x = 1\n", dict(DECLARED_OK)).tier, "operator_only")

    def test_changed_text_may_be_a_mapping_from_path_to_text(self):
        self.assertEqual(mp.classify_change("blog", ["pipeline/a.py", "tests/t.py"], {"pipeline/a.py": GOOD_TEXT, "tests/t.py": "pass\n"}, dict(DECLARED_OK)).tier, "ai_ok")
        flagged = mp.classify_change("blog", ["pipeline/a.py", "docs/x.md"], {"pipeline/a.py": GOOD_TEXT, "docs/x.md": "adsbygoogle"}, dict(DECLARED_OK))
        self.assertEqual(flagged.categories, ("ads",))
        self.assert_invalid(mp.classify_change("blog", ["pipeline/a.py"], {"pipeline/a.py": 5}, dict(DECLARED_OK)))

    def test_a_mapping_key_that_is_not_a_changed_path_is_not_ai_ok(self):
        """글을 변경 파일 목록에 없는 경로 아래에 두면 시험·문서 면제를 흉내 낼 수 있다 — 확인할 수 없는 입력이다(S2b)."""
        for key in ("tests/t.py", "docs/x.md", "pipeline/other.py", "", "../x.md", "/abs.md"):
            with self.subTest(key=key):
                self.assert_invalid(mp.classify_change("blog", ["pipeline/a.py"], {"pipeline/a.py": GOOD_TEXT, key: "x = 1\n"}, dict(DECLARED_OK)))
        for key in (None, 1, ("a",)):
            with self.subTest(key=repr(key)):
                self.assert_invalid(mp.classify_change("blog", ["pipeline/a.py"], {key: "x = 1\n"}, dict(DECLARED_OK)))
        for key in ("pipeline/a.py", "./pipeline/a.py", "pipeline" + chr(92) + "a.py"):                                    # 같은 경로를 다르게 적어도 같은 경로로 읽는다
            with self.subTest(same=key):
                self.assertEqual(mp.classify_change("blog", ["pipeline/a.py"], {key: GOOD_TEXT}, dict(DECLARED_OK)).tier, "ai_ok")
        self.assertEqual(mp.classify_change("blog", ["pipeline/a.py", "pipeline/b.py"], {"pipeline/a.py": GOOD_TEXT, "pipeline/b.py": ""}, dict(DECLARED_OK)).tier, "ai_ok")    # 글이 없는 파일은 빈 글
        self.assert_invalid(mp.classify_change("blog", [], {"pipeline/a.py": GOOD_TEXT}, dict(DECLARED_OK)))

    def test_a_bad_declaration_is_not_ai_ok(self):
        for declared in ("no", ["x"], 5, dict(DECLARED_OK, unknown_item=False), {1: False}):
            with self.subTest(declared=declared):
                self.assert_invalid(mp.classify_change("blog", ["pipeline/a.py"], "", declared))

    def test_the_function_never_raises(self):
        weird = (None, 5, "x", [], {}, object(), b"x", ["x"], {"a": 1}, float("nan"), True)
        for kind in ("blog", "desktop", None, 3):
            for paths in weird:
                for text in weird:
                    for declared in (None, 5, {}, dict(DECLARED_OK)):
                        result = mp.classify_change(kind, paths, text, declared)
                        self.assertIn(result.tier, ("ai_ok", "operator_only"))
                        if result.tier == "ai_ok":
                            self.assertEqual(result.categories + result.extra_flags, ())


class ClassifySafetyGuardTest(unittest.TestCase):
    """총괄(AI)의 보수적 판단(2026-11-15, 결함 D-347, 운영자 확인 대기) — 안전 장치 파일은 승인해도 운영자 직접 병합이다(12항목 밖 표시 safety_guard). 문서는 이름이 정해진 한 파일만 걸린다."""

    PATHS = ("scripts/validate_repo.py", "tests/test_validate_repo.py", "tests/test_guardrails.py", "tests/test_guardrails_precheck.py", "tests/test_security_settings.py",
             "tests/test_egress.py", "tests/test_egress_budget.py", "tests/egress_scan.py", "tests/ai_flow_scan.py", "tests/test_ai_flow.py", "tests/test_ai_guard.py",
             "tests/test_source_policy.py", "tests/test_secret_invisible.py", "tests/test_quality_shadow_guards.py", "tests/source_policy_scenarios.py", "pipeline/egress.py",
             "pipeline/source_policy.py", "pipeline/inbox_policy.py", "pipeline/ai_guard.py", "pipeline/edits/safety.py", "pipeline/secret_patterns.py",
             "pipeline/ai_processor_policy.json", "docs/SECURITY_GUARDRAILS.md", "src/chanceblog_desktop/security/mask.py", "src/chanceblog_desktop/security/shape.py")

    def assert_guard(self, kind, path):
        result = classify(kind, [path])
        self.assertEqual(result.tier, "operator_only", path)
        self.assertIn("safety_guard", result.extra_flags, path)
        self.assertTrue(any("안전 장치 파일" in reason and path.split("/")[-1] in reason for reason in result.reasons), path)

    def test_each_representative_safety_file_is_operator_only_in_both_repositories(self):
        for kind in ("blog", "desktop"):
            for path in self.PATHS:
                with self.subTest(kind=kind, path=path):
                    self.assert_guard(kind, path)

    def test_every_safety_word_alone_is_enough(self):
        for word in mp.SAFETY_GUARD_WORDS:
            for template in ("pipeline/x_{}_y.py", "tests/test_{}.py", "src/{}/module.py", "scripts/{}.json"):
                with self.subTest(word=word, template=template):
                    self.assert_guard("blog", template.format(word))
                    self.assert_guard("desktop", template.format(word))

    def test_the_tests_folder_is_not_exempt(self):
        for path in ("tests/test_guardrails.py", "tests/test_security_settings.py", "tests/test_egress.py", "tests/test_validate_repo.py", "tests/fixtures/security_cases.json",
                     "tests/egress_scan.py", "tests/helpers/guard_helper.py"):
            with self.subTest(path=path):
                self.assert_guard("blog", path)

    def test_documents_are_covered_only_when_they_are_the_named_file(self):
        for path in ("docs/SECURITY_GUARDRAILS.md", "DOCS/security_guardrails.md", "./docs/SECURITY_GUARDRAILS.md", "docs\\SECURITY_GUARDRAILS.md"):
            with self.subTest(path=path):
                result = classify("blog", [path])
                self.assertEqual((result.tier, result.categories, result.extra_flags), ("operator_only", (), ("safety_guard",)))
        for kind, path in (("blog", "docs/GLOSSARY.md"), ("blog", "docs/FACT_PATH.md"), ("blog", "docs/OPS_INBOX.md"), ("blog", "docs/ARCHITECTURE.md"), ("blog", "docs/security_notes.md"),
                           ("blog", "docs/egress_notes.rst"), ("blog", "docs/policy.txt"), ("blog", "docs/notes/guard.adoc"), ("desktop", "README.md"), ("blog", "인수인계/작업내용.md"),
                           ("desktop", "docs/DECISIONS.md"), ("desktop", "docs/security_review.md")):
            with self.subTest(path=path):
                self.assertEqual(classify(kind, [path]).tier, "ai_ok", path)

    def test_files_that_only_share_a_few_letters_are_not_flagged(self):
        for path in ("pipeline/topics.py", "pipeline/regarding.py", "pipeline/regardless.py", "pipeline/guided_tour.py", "pipeline/safe_mode.py", "pipeline/secrecy.py", "pipeline/secure_mode.py",
                     "pipeline/policing.py", "pipeline/sandy.py", "tests/test_topics.py", "tests/test_guides.py"):
            with self.subTest(path=path):
                self.assertEqual(classify("blog", [path]).tier, "ai_ok", path)
        self.assertEqual(classify("desktop", ["src/chanceblog_desktop/ui/pages/home.py"]).tier, "ai_ok")

    def test_case_variants_of_the_safe_folder_are_still_flagged(self):
        """R4 덤(T3 — SG04): 안전 장치 폴더(pipeline/publishers)의 대소문자 변형도 이름 목록의 폴더 규칙으로 걸린다 — 이름 비교는 대소문자를 가리지 않는다(문서 §7-6)."""
        for path in ("pipeline/Publishers/x.py", "PIPELINE/PUBLISHERS/x.py", "pipeline/PUBLISHERS/deep/y.py"):
            with self.subTest(path=path):
                result = classify("blog", [path])
                self.assertEqual(result.tier, "operator_only")
                self.assertIn("safety_guard", result.extra_flags)

    def test_it_is_a_flag_outside_the_twelve_items(self):
        result = classify("blog", ["pipeline/egress.py"])
        self.assertEqual((result.categories, result.extra_flags), ((), ("safety_guard",)))

    def test_the_policy_files_keep_only_their_own_flag(self):
        for path in mp.POLICY_SELF_FILES:
            with self.subTest(path=path):
                self.assertEqual(classify("blog", [path]).extra_flags, ("policy_self",))

    def test_flags_are_listed_in_the_declared_order(self):
        result = classify("blog", ["scripts/validate_repo.py", "pipeline/merge_policy.py", "pipeline/fetcher.py"], "import requests\n")
        self.assertEqual(result.extra_flags, ("policy_self", "safety_guard", "external_connection"))
        self.assertEqual(list(result.extra_flags), [code for code in mp.EXTRA_CODES if code in result.extra_flags])

    def test_a_safety_guard_change_fails_the_scope_condition_even_with_everything_declared_false(self):
        paths = ["scripts/validate_repo.py", "tests/test_validate_repo.py"]
        facts = good_facts()
        facts["approved_paths"] = list(paths)
        facts["current_paths"] = list(paths)
        facts["classification"] = classify("blog", paths, GOOD_TEXT, {code: False for code in mp.OPERATOR_ONLY_CODES})
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("scope_matches",))
        self.assertIn("안전 장치 파일", verdict.failures[0].reason)


class ClassifyExternalConnectionTest(unittest.TestCase):
    """총괄(AI)의 보수적 판단(2026-11-15, 결함 D-347, 운영자 확인 대기) — 시험·문서가 아닌 파일의 바뀐 줄에 새 외부 접속 코드(네트워크·외부 서비스 import, 호출 모양, 새 호스트 주소, 네트워크 명령)가
    들어오면 운영자 직접 병합이다(12항목 밖 표시 external_connection). 시험·문서 안의 주소와 예시는 걸리지 않는다. 주소 글은 런타임에 조립한다."""

    CODE = "pipeline/fetcher.py"
    SAMPLE = "import requests\nu = '" + url("api.service.org") + "'\ncmd = ['curl', u]\n"
    IMPORTS = ("import requests", "import urllib.request", "import urllib.request as ur", "from urllib.request import urlopen", "from urllib import request", "from urllib import parse, request",
               "import socket", "import ssl", "import http.client", "from http import client", "from http.client import HTTPSConnection", "import http.server", "import socketserver",
               "import aiohttp", "import httpx as hx", "import os, requests", "import json; import socket", "    import requests", "from requests.adapters import HTTPAdapter",
               "import smtplib", "import ftplib", "import websockets", "import paramiko", "import urllib3", "import xmlrpc.client", "import webbrowser", "from google import genai",
               "import google.generativeai as genai", "from google.cloud import storage", "import googleapiclient.discovery", "import openai", "import anthropic", "from openai import OpenAI",
               "import boto3", "import transformers", "from langchain.llms import Model")
    NOT_IMPORTS = ("import urllib.parse", "from urllib.parse import quote, urlparse", "from urllib import parse", "import urllib", "import json", "import re, os", "import requests_mock",
                   "import socket_utils", "import sslutil", "import google", "from .requests import helper", "from . import requests", "from my.requests import helper", "import subprocess",
                   "import transformers_local", "import asyncio")
    CALLS = ("response = urlopen(address)", "urlretrieve(a, b)", "conn = HTTPSConnection(host)", "conn = HTTPConnection (host)", "requests.get(address)", "requests . post (address)",
             "session = requests.Session()", "httpx.get(address)", "client = aiohttp.ClientSession()", "sock = socket.socket(socket.AF_INET)", "socket.create_connection((host, 1))",
             "sock = create_connection(address)", "getaddrinfo(host, 80)", "server = HTTPServer(address, handler)", "server.serve_forever()", "importlib.import_module(name)",
             "module = __import__('module_name')", "exec(code)", "result = eval(expression)")
    NOT_CALLS = ("value = ast.literal_eval(text)", "model.eval()", "self.exec(command)", "cursor.execute(sql)", "executor.submit(job)", "def fetch_data(address):", "fetch(address)",
                 "my_import_module(name)", "reimport_module(name)", "urlopener(address)", "create_connection_pool(size)", "start_server_time = 3", "result = evaluate(expression)")
    NET_CALL_NAMES = ("urlopen", "urlretrieve", "create_connection", "create_server", "start_server", "serve_forever", "getaddrinfo", "gethostbyname", "gethostbyaddr", "HTTPConnection",
                      "HTTPSConnection", "HTTPServer", "ThreadingHTTPServer", "TCPServer", "UDPServer", "build_opener", "install_opener", "wrap_socket", "open_connection",
                      "open_unix_connection", "start_tls")
    SCHEMES = ("https", "http", "wss", "ws", "ftp", "ftps", "sftp", "ssh", "git", "tg", "smtp", "smtps", "ldap", "ldaps", "redis", "rediss", "mqtt", "mqtts", "amqp", "amqps", "gopher")
    FLAGGED_ADDRESSES = (("api.service.org/v1", "https"), ("data.go.kr/x", "http"), ("stream.net/ws", "wss"), ("files.net/a", "ftp"), ("resolve?x=1", "tg"), ("git@host.org/repo.git", "ssh"),
                         ("host.org/x", "git"), ("UPPER.ORG/x", "HTTPS"), ("[2001:db8::1]:8080/x", "http"), ("localhost:8080/x", "http"), ("127.0.0.1:5000/x", "http"),
                         ("192.0.2.10/x", "https"), ("example.com.evil.org/x", "https"), ("notexample.com/x", "https"), ("evil.org/example.com", "https"), ("example.company/x", "https"))
    EXAMPLE_ADDRESSES = ("example.com/x", "www.example.org", "a.b.example.net/x", "foo.example/x", "host.test/x", "x.invalid", "EXAMPLE.COM/x", "user:pw@example.com/x")
    TLDS = ("com", "net", "org", "io", "ai", "dev", "app", "co", "kr", "jp", "cn", "de", "uk", "fr", "eu", "gov", "edu", "info", "me", "tv", "cloud", "xyz", "site", "online", "biz", "int", "mil")
    KNOWN_HOSTS = ("googleapis.com", "googleusercontent.com", "telegram.org", "githubusercontent.com", "github.com", "unsplash.com", "openai.com", "anthropic.com")
    QUOTED_FLAGGED = ("api." + "telegram.org", "data.nasa.gov", "images." + "unsplash.com/photo", "service.example-corp.io:8443/path", "svc.example.co")
    QUOTED_CLEAN = ("pipeline.notify", "index.html", "setup.py", "file.name.txt", "a.b.c", "README.md", "module.attr", "x.com.py", "user@host.com", "www.example.com", "report.org.txt",
                    "my.example", "a.test")
    CLI_TOOLS = ("curl", "wget", "nslookup", "telnet", "scp", "sftp", "rsync", "ssh")
    CLI_FLAGGED = ("cmd = ['curl', '-s', address]", "cmd = 'wget -q ' + address", "cmd = \"ssh host\"", "cmd = ['gh', 'api', 'x']", "cmd = ['git', 'push', 'origin']", "cmd = ['git', 'fetch']",
                   "cmd = 'git pull --rebase'", "cmd = ['git', 'clone', address]", "cmd = ['git', 'ls-remote', address]", "cmd = 'scp a b'", "cmd = ['rsync', '-a']",
                   "cmd = ['nslookup', host]", "cmd = ['telnet', host]")
    CLI_CLEAN = ("cmd = ['git', 'status']", "cmd = ['git', 'log', '-1']", "# curl is not used", "curl_helper = 1", "name = 'curly'", "cmd = ['sshd']", "name = 'ghost'",
                 "# git push is forbidden", "cmd = ['git', 'diff', '--stat']", "cmd = ['git', 'rev-parse', 'HEAD']")
    JS_PATHS = ("scripts/ui/app.js", "scripts/ui/app.mjs", "scripts/ui/app.cjs", "scripts/ui/app.jsx", "scripts/ui/app.ts", "scripts/ui/app.tsx", "scripts/ui/app.vue", "scripts/ui/page.html",
                "scripts/ui/app.htm")
    JS_FLAGGED = ("fetch(address)", "const r = await fetch (address)", "new WebSocket(address)", "var x = new XMLHttpRequest()", "navigator.sendBeacon(a, b)", "sendBeacon(a)", "new EventSource(address)")
    JS_CLEAN = ("refetch(address)", "obj.fetch(address)", "prefetchData()", "const fetcher = 1", "socket.on('message', f)")
    EXEMPT_PATHS = ("tests/test_fetcher.py", "tests/fixtures/data.json", "tests/helpers/net_stub.py", "docs/notes.md", "docs/notes.rst", "docs/README.md", "docs/notes.txt", "인수인계/작업내용.md",
                    "docs/design.adoc", "docs/NOTES.MD")
    NOT_EXEMPT_PATHS = ("src/app/tests/test_fetcher.py", "pipeline/attestation.py", "pipeline/test_helper.py", "tests_extra/helper.py", "docs/tool.py", "notes.md.py", "Tests/helper.py",
                        "TESTS/helper.py", "tests", "docs/notes.json")

    def assert_external(self, text, path=None, kind="blog"):
        result = classify(kind, [path or self.CODE], text)
        self.assertEqual(result.tier, "operator_only", text)
        self.assertIn("external_connection", result.extra_flags, text)
        self.assertTrue(any(reason.startswith("[새 외부 접속 코드]") for reason in result.reasons), text)
        return result

    def assert_clean(self, text, path=None, kind="blog"):
        result = classify(kind, [path or self.CODE], text)
        self.assertEqual((result.tier, result.categories, result.extra_flags), ("ai_ok", (), ()), text)

    def test_network_and_service_imports_are_flagged_in_both_repositories(self):
        for line in self.IMPORTS:
            for kind in ("blog", "desktop"):
                with self.subTest(line=line, kind=kind):
                    self.assert_external(line + "\n", kind=kind)

    def test_every_listed_module_alone_is_enough(self):
        for name in mp.EXTERNAL_MODULES:
            with self.subTest(module=name):
                self.assert_external("import " + name + "\n")
                self.assert_external("from " + name + " import something\n")
        for name in ("urllib.request", "http.client", "google.genai"):
            base, _dot, last = name.rpartition(".")
            self.assert_external("from " + base + " import " + last + "\n")

    def test_imports_that_only_look_alike_are_not_flagged(self):
        for line in self.NOT_IMPORTS:
            with self.subTest(line=line):
                self.assert_clean(line + "\n")

    def test_call_shapes_are_flagged(self):
        for line in self.CALLS:
            with self.subTest(line=line):
                self.assert_external(line + "\n")
        for name in self.NET_CALL_NAMES:
            with self.subTest(name=name):
                self.assert_external("x = " + name + "(argument)\n")

    def test_calls_that_only_look_alike_are_not_flagged(self):
        for line in self.NOT_CALLS:
            with self.subTest(line=line):
                self.assert_clean(line + "\n")

    def test_addresses_with_a_scheme_are_flagged_for_every_scheme(self):
        self.assertEqual(set(self.SCHEMES), set(mp.EXTERNAL_SCHEMES))
        for scheme in self.SCHEMES:
            with self.subTest(scheme=scheme):
                self.assert_external("u = '" + url("service.org/path", scheme) + "'\n")
                self.assert_external("u = '" + url("service.org/path", scheme.upper()) + "'\n")
        for host, scheme in self.FLAGGED_ADDRESSES:
            with self.subTest(host=host, scheme=scheme):
                self.assert_external("u = '" + url(host, scheme) + "'\n")
                self.assert_external("# " + url(host, scheme) + "\n")

    def test_example_addresses_and_empty_hosts_are_not_flagged(self):
        for host in self.EXAMPLE_ADDRESSES:
            with self.subTest(host=host):
                self.assert_clean("u = '" + url(host) + "'\n")
        self.assert_clean("import re\nrx = re.compile(r'https?" + ":" + "//')\n")
        self.assert_clean("prefix = '" + url("") + "'\n")
        self.assert_clean("template = '" + url("{host}/path") + "'\n")

    def test_quoted_domain_names_are_flagged_for_every_top_level_domain(self):
        for tld in self.TLDS:
            with self.subTest(tld=tld):
                self.assert_external("host = 'svc.provider." + tld + "'\n")
                self.assert_external('host = "svc.provider.' + tld + ':8443/path"\n')
        for host in self.QUOTED_FLAGGED:
            with self.subTest(host=host):
                self.assert_external("host = '" + host + "'\n")

    def test_quoted_names_that_are_not_domains_are_not_flagged(self):
        for name in self.QUOTED_CLEAN:
            with self.subTest(name=name):
                self.assert_clean("name = '" + name + "'\n")

    def test_well_known_service_domains_are_flagged_even_without_quotes(self):
        for host in self.KNOWN_HOSTS:
            with self.subTest(host=host):
                self.assert_external("see api." + host + " for details\n")
                self.assert_external("remote: " + host + "\n")
        for text in ("see notgithub.com for details", "see github.company for details", "see mygithub.com", "see telegram.organization"):
            with self.subTest(text=text):
                self.assert_clean(text + "\n")

    def test_network_commands_are_flagged_when_quoted_as_commands(self):
        for line in self.CLI_FLAGGED:
            with self.subTest(line=line):
                self.assert_external(line + "\n")
        for tool in self.CLI_TOOLS:
            with self.subTest(tool=tool):
                self.assert_external("cmd = ['" + tool + "', 'x']\n")
                self.assert_external("cmd = '" + tool + " x'\n")

    def test_commands_that_only_look_alike_are_not_flagged(self):
        for line in self.CLI_CLEAN:
            with self.subTest(line=line):
                self.assert_clean(line + "\n")

    def test_javascript_network_calls_are_flagged_only_in_javascript_files(self):
        for path in self.JS_PATHS:
            for line in self.JS_FLAGGED:
                with self.subTest(path=path, line=line):
                    self.assert_external(line + "\n", path=path)
            for line in self.JS_CLEAN:
                with self.subTest(path=path, line=line):
                    self.assert_clean(line + "\n", path=path)
        for line in self.JS_FLAGGED:
            with self.subTest(python_file=line):
                self.assert_clean(line + "\n", path="pipeline/fetcher.py")
        self.assert_external("fetch(address)\n", path="src/ui/app.js", kind="desktop")

    def test_tests_and_documents_are_not_looked_at(self):
        for path in self.EXEMPT_PATHS:
            with self.subTest(path=path):
                self.assert_clean(self.SAMPLE, path=path)
                self.assert_clean(self.SAMPLE, path=path, kind="desktop")

    def test_only_the_top_level_tests_folder_and_real_document_files_are_exempt(self):
        for path in self.NOT_EXEMPT_PATHS:
            with self.subTest(path=path):
                self.assert_external(self.SAMPLE, path=path)

    def test_a_plain_text_is_skipped_only_when_every_changed_file_is_a_test_or_a_document(self):
        text = "import requests\n"
        self.assertEqual(classify("blog", ["docs/a.md", "tests/test_a.py"], text).tier, "ai_ok")
        self.assertIn("external_connection", classify("blog", ["docs/a.md", "tests/test_a.py", "pipeline/a.py"], text).extra_flags)
        self.assertIn("external_connection", classify("blog", ["pipeline/a.py"], text).extra_flags)
        self.assertIn("external_connection", classify("blog", ["tests/test_a.py", "docs/notes.json"], text).extra_flags)

    def test_a_mapping_is_read_file_by_file(self):
        paths = ["docs/a.md", "tests/test_a.py", "pipeline/a.py"]
        clean = {"docs/a.md": self.SAMPLE, "tests/test_a.py": self.SAMPLE, "pipeline/a.py": "value = 1\n"}
        self.assertEqual(classify("blog", paths, clean).tier, "ai_ok")
        dirty = dict(clean, **{"pipeline/a.py": "import requests\n"})
        self.assertIn("external_connection", classify("blog", paths, dirty).extra_flags)
        self.assertIn("external_connection", classify("blog", ["docs/a.md"], {"pipeline/other.py": "import requests\n"}).extra_flags)
        for key in ("", 1, "../x.md", "/abs.md", None):
            with self.subTest(key=key):
                self.assertIn("external_connection", classify("blog", ["docs/a.md"], {key: "import requests\n"}).extra_flags)

    def test_the_reasons_name_modules_and_hosts_but_never_echo_the_line(self):
        text = "import requests\nu = '" + url("user:CANARY_pw@host.org/x") + "'\n"
        result = classify("blog", [self.CODE], text)
        joined = " ".join(result.reasons)
        for word in ("[새 외부 접속 코드]", "requests", "host.org"):
            self.assertIn(word, joined)
        for leak in ("CANARY", "user:", "pw@", "u = "):
            self.assertNotIn(leak, joined)
        self.assertEqual(result.categories, ())

    def test_it_combines_with_the_twelve_items(self):
        result = classify("blog", [self.CODE], "import requests\nTELEGRAM_BOT_TOKEN = 1\n")
        self.assertEqual((result.tier, result.categories, result.extra_flags), ("operator_only", ("credentials",), ("external_connection",)))

    def test_odd_inputs_never_raise_and_stay_conservative(self):
        for added in ({1: "import requests"}, {"a.py": ""}, {}, "", "\n\n", "import", "from", "import ,", "from x import", "from x import (", "import a as", "import  \t "):
            result = mp.classify_change("blog", ["pipeline/a.py"], added, dict(DECLARED_OK))
            self.assertIn(result.tier, ("ai_ok", "operator_only"))

    ADVERSARIAL = (
        ("점과 글자 반복", lambda n: "a." * n), ("긴 따옴표 글", lambda n: "'" + "a" * n + "'"), ("긴 import 목록", lambda n: "import " + "a," * n), ("긴 호스트", lambda n: url("a" * n)),
        ("따옴표 git 반복", lambda n: "'git " * n), ("따옴표 속 점 이름", lambda n: "'" + "a." * n + "x'"), ("긴 from 경로", lambda n: "from " + "a." * n + " import b"),
        ("fetch( 반복", lambda n: "fetch(" * n), ("스킴 반복", lambda n: "https?" + ":" + "//" * n), ("스킴 없는 주소", lambda n: "'//" + "a." * n), ("curl 반복", lambda n: "curl " * n),
        ("git 반복", lambda n: "git " * n), ("rm 뒤 긴 옵션", lambda n: "rm " + "-a " * n), ("rm 반복", lambda n: "rm -a " * n), ("authorization 뒤 긴 글", lambda n: "authorization" + "a" * n),
        ("authorization 반복", lambda n: "authorization " * n), ("Bearer 뒤 긴 값", lambda n: "Bearer " + "a" * n), ("bearer 반복", lambda n: "bearer " * n),
        ("sk_live_ 뒤 긴 값", lambda n: "sk_live_" + "a" * n), ("drop 반복", lambda n: "drop " * n), ("os 반복", lambda n: "os." * n), ("migrat 반복", lambda n: "migrat" * n),
        ("api key 반복", lambda n: "api " * n), ("password 뒤 긴 글", lambda n: "password = '" + "a" * n))

    def timed(self, text):
        paths = ["scripts/a.py", "scripts/b.js", "scripts/c.sh", "docs/d.md"]               # 한 번에 JS·셸 규칙까지 모두 돌아가게 한다
        best = None
        for _ in range(2):
            started = time.perf_counter()
            classify("blog", paths, text)
            spent = time.perf_counter() - started
            best = spent if best is None else min(best, spent)
        return best

    def test_long_adversarial_text_is_classified_in_linear_time(self):
        """입력을 8배로 키웠을 때 걸리는 시간이 8배에 가깝다(제곱이면 64배) — 실제 시간의 상한이 아니라 비율을 본다(느린 PC·추적 실행에서도 흔들리지 않게). 너무 빨라 재기 어려우면 20초 상한만 본다."""
        for name, make in self.ADVERSARIAL:
            with self.subTest(family=name):
                small, big = self.timed(make(2500)), self.timed(make(20000))
                self.assertLess(big, 20.0 if small < 0.01 else 25 * small, (name, small, big))


class PreconditionsTest(unittest.TestCase):
    def failed(self, facts):
        return mp.check_preconditions(facts).failed_codes

    def test_complete_good_facts_pass_all_eight(self):
        verdict = mp.check_preconditions(good_facts())
        self.assertTrue(verdict.ok)
        self.assertEqual(verdict.failures, ())
        self.assertEqual(verdict.explain(), [])

    def test_the_condition_names_are_the_operators_words_in_order(self):
        verdict = mp.check_preconditions({})
        self.assertEqual(tuple(item.name for item in verdict.failures), PRECONDITIONS_8)
        self.assertEqual(verdict.failed_codes, tuple(code for code, _ in mp.PRECONDITIONS))
        self.assertEqual(len(verdict.failures), 8)

    def test_condition_1_the_approved_number_must_match_the_pr(self):
        for key, value in (("approved_number", "M076"), ("pr_title_label", "M076"), ("approved_pr_number", 199), ("pr_number", 199), ("approved_number", "M75"), ("approved_number", "m075"),
                           ("pr_title_label", "[M075]"), ("approved_pr_number", True), ("pr_number", "198"), ("consumed_numbers", ["M074", "M075"]), ("consumed_numbers", "M075"),
                           ("consumed_numbers", {"M075": 1})):
            with self.subTest(key=key, value=value):
                facts = good_facts()
                facts[key] = value
                self.assertEqual(self.failed(facts), ("number_match",))

    def test_condition_1_the_pull_request_must_be_open_and_not_a_draft(self):
        """닫힌 PR·이미 병합된 PR·초안 PR·상태를 모르는 PR 은 병합하지 않는다(I7)."""
        for state, word in (("closed", "closed"), ("merged", "merged")):
            facts = good_facts()
            facts["pr_state"] = state
            verdict = mp.check_preconditions(facts)
            self.assertEqual(verdict.failed_codes, ("number_match",), state)
            self.assertIn("열려 있지 않습니다", verdict.failures[0].reason)
            self.assertIn(word, verdict.failures[0].reason)
        for state in ("OPEN", "Open", " open", "open ", "opened", "draft", "", 5, True, ["open"], "open" + chr(10), object()):
            with self.subTest(state=repr(state)):
                facts = good_facts()
                facts["pr_state"] = state
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("number_match",))
                self.assertIn("PR 상태를 알 수 없습니다", verdict.failures[0].reason)
        for draft in (True, 0, 1, "false", "False", "", [], 0.0, object()):
            with self.subTest(draft=repr(draft)):
                facts = good_facts()
                facts["pr_draft"] = draft
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("number_match",))
                self.assertIn("초안", verdict.failures[0].reason)
        facts = good_facts()
        facts["pr_state"], facts["pr_draft"] = "open", False
        self.assertTrue(mp.check_preconditions(facts).ok)

    def test_condition_1_a_pr_number_that_is_an_int_subclass_fails_even_when_only_one_side_is(self):
        """R3(T3 — AU0479·AU0480·AU0481): 승인 때 PR 번호와 지금 PR 번호 중 한쪽만 int 하위 형식이어도 실패한다 — 양쪽이 모두 그럴 때만 보던 시험의 틈."""
        for key in ("approved_pr_number", "pr_number"):
            with self.subTest(key=key):
                facts = good_facts()
                facts[key] = StrSubclassTest.EvilInt(5)
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("number_match",))
                self.assertIn("양의 정수", verdict.failures[0].reason)

    def test_condition_1_a_used_approval_cannot_be_reused(self):
        facts = good_facts()
        facts["consumed_numbers"] = ("M070", "M075")
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("number_match",))
        self.assertIn("한 번 쓴 승인", verdict.failures[0].reason)
        facts["consumed_numbers"] = ["M070", "M071"]
        self.assertTrue(mp.check_preconditions(facts).ok)

    def test_condition_2_a_commit_after_the_approval_fails(self):
        for current in (SHA_B, "f" * 40):
            facts = good_facts()
            facts["current_head_sha"] = current
            self.assertEqual(self.failed(facts), ("no_new_commit",))
        for bad in ("abc1234", "", "g" * 40, 5):
            facts = good_facts()
            facts["approved_head_sha"] = bad
            self.assertEqual(self.failed(facts), ("no_new_commit",))

    def test_condition_2_the_head_when_the_approval_arrived_must_be_the_head_that_was_explained(self):
        """쉬운 설명을 보낸 머리 커밋(approved_head_sha)과 승인 글이 도착했을 때의 머리 커밋(head_sha_at_approval)과 지금의 머리 커밋이 모두 같아야 한다(S5)."""
        facts = good_facts()
        facts["head_sha_at_approval"] = SHA_B                                  # 설명을 보낸 뒤 승인이 오기 전에 커밋이 더해졌다 — 지금은 설명 때와 같아져도 승인은 무효다
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("no_new_commit",))
        self.assertIn("승인 글이 도착하기 전에", verdict.failures[0].reason)
        self.assertIn("1111111", verdict.failures[0].reason)
        self.assertIn("2222222", verdict.failures[0].reason)
        facts["current_head_sha"] = SHA_B                                      # 설명 때만 다르고 승인 때와 지금이 같아도 마찬가지다
        self.assertEqual(self.failed(facts), ("no_new_commit",))
        facts = good_facts()
        facts["current_head_sha"] = SHA_B                                      # 승인 뒤에 커밋이 더해졌다
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("no_new_commit",))
        self.assertIn("커밋이 더해지거나", verdict.failures[0].reason)
        for bad in ("abc1234", "", "g" * 40, 5, "1" * 39):
            facts = good_facts()
            facts["head_sha_at_approval"] = bad
            verdict = mp.check_preconditions(facts)
            self.assertEqual(verdict.failed_codes, ("no_new_commit",), repr(bad))
            self.assertIn("40자 해시", verdict.failures[0].reason)
        facts = good_facts()
        facts["head_sha_at_approval"] = SHA_A.upper().replace("1", "A")        # 대소문자만 다른 같은 해시는 같은 것이다
        facts["approved_head_sha"] = SHA_A.replace("1", "a")
        facts["current_head_sha"] = SHA_A.replace("1", "a")
        self.assertTrue(mp.check_preconditions(facts).ok)

    def test_condition_3_every_check_must_have_succeeded(self):
        broken = (
            [{"name": "a", "conclusion": "failure"}], [{"name": "a", "conclusion": "success"}, {"name": "b", "conclusion": "skipped"}], [{"name": "a", "conclusion": "neutral"}],
            [{"name": "a", "conclusion": "cancelled"}], [{"name": "a", "conclusion": "timed_out"}], [{"name": "a", "conclusion": "action_required"}], [{"name": "a", "conclusion": None}],
            [{"name": "a", "conclusion": "SUCCESS"}], [{"name": "a", "conclusion": "pending"}], [{"name": "a"}], [{"name": "", "conclusion": "success"}], [{"conclusion": "success"}],
            [], "success", None, [None], ["success"], 5, [{"name": "a", "conclusion": "success"}, "x"])
        for checks in broken:
            with self.subTest(checks=checks):
                facts = good_facts()
                facts["checks"] = checks
                self.assertEqual(self.failed(facts), ("checks_pass",))
            if isinstance(checks, list) and checks:                                              # 필수 검사는 모두 통과한 채 이 항목 하나만 문제여도 통과가 아니다(필수 검사 규칙이 가리지 못하게)
                with self.subTest(isolated=checks):
                    facts = good_facts()
                    facts["checks"] = list(checks) + [{"name": "필수 검사 하나", "conclusion": "success"}]
                    facts["required_checks"] = ["필수 검사 하나"]
                    self.assertEqual(self.failed(facts), ("checks_pass",))
        facts = good_facts()
        facts["checks"] = [{"name": "필수 검사 하나", "conclusion": "success"}, {"name": "참고 검사", "conclusion": "success"}]
        facts["required_checks"] = ["필수 검사 하나"]
        self.assertTrue(mp.check_preconditions(facts).ok)

    def test_condition_3_a_check_without_a_real_name_fails_even_when_the_required_ones_passed(self):
        """공백뿐인 이름·이름 없는 항목이 끼어 있으면 필수 검사가 모두 통과했어도 통과가 아니다."""
        for extra in ({"name": "   ", "conclusion": "success"}, {"name": "", "conclusion": "success"}, {"name": None, "conclusion": "success"}, {"conclusion": "success"},
                      {"name": 5, "conclusion": "success"}, {"name": "\t\n", "conclusion": "success"}):
            with self.subTest(extra=repr(extra)):
                facts = good_facts()
                facts["checks"] = facts["checks"] + [extra]
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("checks_pass",))
                self.assertIn("(이름 없는 검사)", verdict.failures[0].reason)

    def test_condition_3_a_check_name_with_extra_spaces_does_not_satisfy_a_required_check(self):
        """R3(T3 — PC08): 앞뒤 공백이 붙은 검사 이름은 같은 이름의 필수 검사를 채우지 못한다 — 공백을 지워 맞춰 주지 않는다."""
        for padded in (" 저장소 규칙 검사 ", "저장소 규칙 검사 ", " 저장소 규칙 검사", "\t저장소 규칙 검사", "저장소 규칙 검사\n"):
            with self.subTest(name=repr(padded)):
                facts = good_facts()
                facts["checks"] = [{"name": padded, "conclusion": "success"}, {"name": "사이트 배포 미리 검사", "conclusion": "success"}]
                self.assertEqual(self.failed(facts), ("checks_pass",))

    def test_condition_3_every_required_check_must_be_in_the_result_and_succeeded(self):
        """필수 검사의 이름 목록을 모르면 시작도 안 한 검사가 보이지 않는다 — 목록은 비어 있으면 안 되고 하나라도 결과에 없거나 success 가 아니면 실패다(S2c)."""
        names = ["저장소 규칙 검사", "사이트 배포 미리 검사"]
        facts = good_facts()
        facts["required_checks"] = names + ["시작도 안 한 검사"]
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("checks_pass",))
        self.assertIn("필수 검사가 결과에 없거나 통과하지 않았습니다", verdict.failures[0].reason)
        self.assertIn("시작도 안 한 검사", verdict.failures[0].reason)
        self.assertNotIn("저장소 규칙 검사", verdict.failures[0].reason)
        facts = good_facts()
        facts["checks"] = [{"name": "저장소 규칙 검사", "conclusion": "success"}, {"name": "사이트 배포 미리 검사", "conclusion": "failure"}]
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("checks_pass",))
        self.assertIn("사이트 배포 미리 검사", verdict.failures[0].reason)
        for required in ([], (), set(), frozenset(), "저장소 규칙 검사", b"x", {"저장소 규칙 검사": 1}, [""], ["   "], [5], [None], [["저장소 규칙 검사"]], names + [""], 5, True):
            with self.subTest(required=repr(required)):
                facts = good_facts()
                facts["required_checks"] = required
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("checks_pass",))
                self.assertIn("필수 검사 이름 목록이 올바르지 않거나 비어 있습니다", verdict.failures[0].reason)
        for required in (names, tuple(names), set(names), frozenset(names), names[:1], [names[1], names[0]], names + names):
            with self.subTest(ok=repr(required)):
                facts = good_facts()
                facts["required_checks"] = required
                self.assertTrue(mp.check_preconditions(facts).ok)
        facts = good_facts()                                                   # 필수 목록에 없는 검사가 더 있고 통과했으면 괜찮다
        facts["checks"] = facts["checks"] + [{"name": "참고용 검사", "conclusion": "success"}]
        self.assertTrue(mp.check_preconditions(facts).ok)
        facts["checks"] = facts["checks"] + [{"name": "참고용 검사", "conclusion": "failure"}]          # 참고용이라도 하나가 실패면 통과가 아니다
        self.assertEqual(self.failed(facts), ("checks_pass",))
        facts = good_facts()                                                   # 같은 이름이 두 번 — 하나라도 success 가 아니면 필수 검사는 통과로 세지 않는다
        facts["checks"] = facts["checks"] + [{"name": "저장소 규칙 검사", "conclusion": "failure"}]
        self.assertEqual(self.failed(facts), ("checks_pass",))
        facts = good_facts()                                                   # 이름은 한 글자도 다르면 다른 검사다
        facts["required_checks"] = ["저장소 규칙 검사 ", "사이트 배포 미리 검사"]
        self.assertEqual(self.failed(facts), ("checks_pass",))

    def test_condition_3_the_previous_merges_main_check_must_not_be_red_or_unfinished(self):
        """직전 병합의 main 검사가 실패했거나 끝나지 않았거나 모르는 값이면 병합하지 않는다 — 첫 병합(none)은 괜찮다(S8)."""
        for state in ("success", "none"):
            facts = good_facts()
            facts["previous_merge_main_check"] = state
            self.assertTrue(mp.check_preconditions(facts).ok, state)
        for state in ("failure", "pending", "SUCCESS", "Success", " success", "", "unknown", "passed", 5, True, False, ["success"], object()):
            with self.subTest(state=repr(state)):
                facts = good_facts()
                facts["previous_merge_main_check"] = state
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("checks_pass",))
                self.assertIn("직전 병합의 main 검사가 통과하지 않아", verdict.failures[0].reason)
        facts = good_facts()
        facts["previous_merge_main_check"] = "failure"
        self.assertIn("되돌리기 요청", mp.check_preconditions(facts).failures[0].reason)
        facts["previous_merge_main_check"] = "pending"
        self.assertIn("기다립니다", mp.check_preconditions(facts).failures[0].reason)
        facts["checks"] = [{"name": "저장소 규칙 검사", "conclusion": "failure"}, {"name": "사이트 배포 미리 검사", "conclusion": "success"}]
        reason = mp.check_preconditions(facts).failures[0].reason
        self.assertIn("저장소 규칙 검사", reason)                                # 이유가 여럿이면 모두 알린다
        self.assertIn("직전 병합의 main 검사", reason)
        self.assertIn(" / ", reason)

    def test_condition_3_names_the_failed_checks(self):
        facts = good_facts()
        facts["checks"] = [{"name": "빨간 검사", "conclusion": "failure"}, {"name": "초록 검사", "conclusion": "success"}]
        reason = mp.check_preconditions(facts).failures[0].reason
        self.assertIn("빨간 검사", reason)
        self.assertNotIn("초록 검사", reason)

    def test_condition_4_the_independent_verification_must_have_passed(self):
        def with_record(**changes):
            facts = good_facts()
            facts["independent_verification"] = dict(facts["independent_verification"], **changes)
            return facts

        for changes in ({"verdict": "fail"}, {"verdict": "Pass"}, {"verdict": True}, {"verifier": "구현자 을"}, {"verifier": " 구현자 을 "}, {"verifier": ""}, {"implementer": ""}, {"verifier": 5},
                        {"open_required_findings": 2}, {"open_required_findings": True}, {"open_required_findings": False}, {"open_required_findings": 0.0}, {"open_required_findings": -1},
                        {"open_required_findings": "0"}, {"verified_tree": TREE_B},
                        {"verified_tree": "abc"}, {"verified_tree": None}, {"verdict": None}):
            with self.subTest(changes=changes):
                self.assertEqual(self.failed(with_record(**changes)), ("independent_verified",))
        for key in VERIFICATION_KEYS_5:
            facts = good_facts()
            del facts["independent_verification"][key]
            self.assertEqual(self.failed(facts), ("independent_verified",), key)
        for bad in ("pass", ["pass"], None, 5, {}):
            facts = good_facts()
            facts["independent_verification"] = bad
            self.assertEqual(self.failed(facts), ("independent_verified",))

    def test_condition_4_exactly_one_open_required_finding_fails(self):
        """R3(T3 — PC13): 남은 필수 지적이 정확히 1건일 때도 실패한다 — 0 이 아니면 모두 실패이고 2건 이상만 막지 않는다."""
        for count in (1, 2, 7):
            with self.subTest(count=count):
                facts = good_facts()
                facts["independent_verification"] = dict(facts["independent_verification"], open_required_findings=count)
                self.assertEqual(self.failed(facts), ("independent_verified",))

    def test_condition_4_equal_but_malformed_tree_hashes_do_not_verify(self):
        """R3(T3 — AU0620): 검증한 트리와 지금 트리가 둘 다 40자 해시가 아니면서 서로 같은 글자일 때도 실패한다 — 같기만 하면 통과로 읽지 않는다."""
        for tree in ("unknown", "abc", "g" * 40, "1" * 39, "1" * 41):
            with self.subTest(tree=tree):
                facts = good_facts()
                facts["current_tree"] = tree
                facts["independent_verification"] = dict(facts["independent_verification"], verified_tree=tree)
                self.assertEqual(self.failed(facts), ("independent_verified",))

    def test_condition_4_the_verified_content_must_be_the_content_being_merged(self):
        facts = good_facts()
        facts["current_tree"] = TREE_B
        self.assertEqual(self.failed(facts), ("independent_verified",))

    def test_condition_5_no_conflict(self):
        for value in (True, None, "false", "False", 0, 1, "", "no", [], object()):
            with self.subTest(value=repr(value)):
                facts = good_facts()
                facts["has_conflict"] = value
                self.assertEqual(self.failed(facts), ("no_conflict",))

    def test_condition_6_the_changed_files_must_match_the_approved_explanation(self):
        for current in (list(GOOD_PATHS) + ["docs/new.md"], [GOOD_PATHS[0]], ["pipeline/other.py", GOOD_PATHS[1]], [], None, "pipeline/topics.py", ["../x"]):
            with self.subTest(current=current):
                facts = good_facts()
                facts["current_paths"] = current
                self.assertEqual(self.failed(facts), ("scope_matches",))
        facts = good_facts()
        facts["approved_paths"] = list(GOOD_PATHS) + ["docs/old.md"]
        self.assertEqual(self.failed(facts), ("scope_matches",))

    def test_condition_6_an_operator_only_change_cannot_be_merged_by_ai(self):
        paths = list(GOOD_PATHS) + [".github/workflows/ci.yml"]
        facts = good_facts()
        facts["approved_paths"] = list(paths)
        facts["current_paths"] = list(paths)
        facts["classification"] = classify("blog", paths, GOOD_TEXT).to_dict()
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("scope_matches",))
        self.assertIn("GitHub Actions Workflow", verdict.failures[0].reason)
        facts["classification"] = classify("blog", paths, GOOD_TEXT)                              # 결과 객체를 그대로 넣어도 같다
        self.assertEqual(self.failed(facts), ("scope_matches",))

    def test_condition_6_a_forged_classification_is_caught_by_recomputing_it(self):
        """호출자가 넘긴 분류가 ai_ok 라고 해도 이 함수가 현재 변경 파일과 바뀐 줄로 다시 계산해 운영자 전용이면 실패다(S2a — W10)."""
        for repo_kind, path, text, word in (("blog", ".github/workflows/ci.yml", GOOD_TEXT, "GitHub Actions Workflow"), ("blog", "index.html", GOOD_TEXT, "광고"),
                                            ("blog", "_posts/2026-11-15-a.md", GOOD_TEXT, "공개 게시물"), ("blog", "pipeline/blogs.json", GOOD_TEXT, "발행 모드"),
                                            ("blog", "pipeline/a.py", "if PIPELINE_PAUSE:\n    return\n", "PIPELINE_PAUSE"), ("blog", "pipeline/a.py", "DROP TABLE x", "데이터 삭제"),
                                            ("blog", "pipeline/a.py", "import requests\n", "새 외부 접속 코드"), ("blog", "scripts/validate_repo.py", GOOD_TEXT, "안전 장치 파일"),
                                            ("blog", "pipeline/merge_policy.py", GOOD_TEXT, "병합 정책 자체"), ("desktop", "VERSION", GOOD_TEXT, "패키징"),
                                            ("blog", "pipeline/a.py", FAKE_SECRETS["google"], "API Key"), ("blog", "info/faq.md", GOOD_TEXT, "공개 게시물")):
            with self.subTest(path=path, text=text[:20]):
                facts = good_facts()
                facts["repo_kind"], facts["changed_text"] = repo_kind, text
                facts["approved_paths"] = facts["current_paths"] = [path]
                facts["classification"] = {"tier": "ai_ok", "categories": [], "extra_flags": [], "reasons": [], "paths": [path]}             # 위조: 아무것도 안 걸렸다고 적은 분류
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("scope_matches",))
                self.assertIn("다시 계산하니", verdict.failures[0].reason)
                self.assertIn(word, verdict.failures[0].reason)
        facts = good_facts()
        self.assertTrue(mp.check_preconditions(facts).ok)                                                           # 진짜 ai_ok 인 변경은 그대로 통과한다
        facts["repo_kind"] = "desktop"
        facts["approved_paths"] = facts["current_paths"] = ["src/chanceblog_desktop/ui/x.py"]
        facts["classification"] = classify("desktop", ["src/chanceblog_desktop/ui/x.py"], GOOD_TEXT)
        self.assertTrue(mp.check_preconditions(facts).ok)

    def test_condition_6_the_recomputation_needs_the_kind_and_the_changed_lines(self):
        for key in ("repo_kind", "changed_text"):
            facts = good_facts()
            del facts[key]
            verdict = mp.check_preconditions(facts)
            self.assertEqual(verdict.failed_codes, ("scope_matches",), key)
            self.assertIn(key, verdict.failures[0].reason)
        for repo_kind in ("web", "", "Blog", None, 3, ["blog"]):
            with self.subTest(repo_kind=repr(repo_kind)):
                facts = good_facts()
                facts["repo_kind"] = repo_kind
                self.assertEqual(self.failed(facts), ("scope_matches",))
        for text in (5, ["x"], b"x", object(), {"pipeline/other.py": GOOD_TEXT}, {"tests/test_topics.py": 5}):
            with self.subTest(text=repr(text)):
                facts = good_facts()
                facts["changed_text"] = text
                self.assertEqual(self.failed(facts), ("scope_matches",))
        facts = good_facts()
        facts["changed_text"] = {path: GOOD_TEXT for path in GOOD_PATHS}                                                # 경로마다 나눠 넘기는 모양도 된다
        self.assertTrue(mp.check_preconditions(facts).ok)
        facts["changed_text"] = ""
        self.assertTrue(mp.check_preconditions(facts).ok)
        facts["changed_text"] = {path: "" for path in GOOD_PATHS}                                                       # 글이 없는 파일은 빈 글(키는 변경 파일마다 있어야 한다)
        self.assertTrue(mp.check_preconditions(facts).ok)
        for given in ({}, {GOOD_PATHS[0]: GOOD_TEXT}, {GOOD_PATHS[1]: GOOD_TEXT}):                                       # 키가 빠진 사전은 바뀐 줄을 다 볼 수 없어 분류를 다시 계산할 수 없다
            with self.subTest(given=sorted(given)):
                facts["changed_text"] = given
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("scope_matches",))
                self.assertIn("다시 계산하니", verdict.failures[0].reason)

    def test_condition_6_an_unread_file_is_none_and_fails_while_a_truly_empty_text_passes(self):
        """R1(§7-2·§11-3): 바뀐 줄을 읽지 못한 파일의 글이 None 이면(딕셔너리 값·키 없음·글 전체) 조건 6 이 실패하고, 바뀐 줄이 정말 없는 빈 글만 통과한다."""
        for label, given in (("한 파일만 None", {GOOD_PATHS[0]: None, GOOD_PATHS[1]: ""}), ("모두 None", {path: None for path in GOOD_PATHS}), ("한 파일의 키가 없음", {GOOD_PATHS[0]: ""})):
            with self.subTest(label=label):
                facts = good_facts()
                facts["changed_text"] = given
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("scope_matches",))
                self.assertIn("다시 계산하니", verdict.failures[0].reason)
                self.assertIn("입력을 확인할 수 없음", verdict.failures[0].reason)
        facts = good_facts()
        facts["changed_text"] = None
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("scope_matches",))
        self.assertIn("필요한 값이 없습니다: changed_text", verdict.failures[0].reason)
        for label, given in (("글 전체가 빈 글", ""), ("파일마다 빈 글", {path: "" for path in GOOD_PATHS})):
            with self.subTest(label=label):
                facts = good_facts()
                facts["changed_text"] = given
                verdict = mp.check_preconditions(facts)
                self.assertTrue(verdict.ok, verdict.failures)

    def test_condition_6_the_declared_items_cannot_be_recomputed_so_the_callers_classification_is_followed(self):
        facts = good_facts()
        facts["classification"] = classify("blog", list(GOOD_PATHS), GOOD_TEXT, dict(DECLARED_OK, auto_publish=True))      # 사람이 '자동 게시 활성화' 를 참으로 선언한 분류
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("scope_matches",))
        self.assertIn("자동 게시 활성화", verdict.failures[0].reason)
        facts["classification"] = mp.classify_change("blog", list(GOOD_PATHS), GOOD_TEXT)                                   # 선언을 안 한(미응답) 분류도 통과하지 못한다
        self.assertEqual(self.failed(facts), ("scope_matches",))

    def test_condition_6_a_policy_file_change_cannot_be_merged_by_ai(self):
        paths = ["pipeline/merge_policy.py"]
        facts = good_facts()
        facts["approved_paths"] = facts["current_paths"] = list(paths)
        facts["classification"] = classify("blog", paths, GOOD_TEXT)
        self.assertEqual(self.failed(facts), ("scope_matches",))

    def test_condition_6_a_stale_or_malformed_classification_fails(self):
        stale = classify("blog", ["pipeline/other.py"], GOOD_TEXT).to_dict()
        for value in (stale, {"tier": "ai_ok"}, {"tier": "maybe", "categories": [], "extra_flags": [], "paths": list(GOOD_PATHS)}, "ai_ok", 5, None,
                      {"tier": "ai_ok", "categories": [], "extra_flags": [], "paths": [1]}, {"tier": "ai_ok", "categories": ["workflow"], "extra_flags": [], "paths": list(GOOD_PATHS)},
                      {"tier": "ai_ok", "categories": [], "extra_flags": ["invalid_input"], "paths": list(GOOD_PATHS)},
                      {"tier": "operator_only", "categories": [], "extra_flags": [], "paths": list(GOOD_PATHS)}):
            with self.subTest(value=value):
                facts = good_facts()
                facts["classification"] = value
                self.assertEqual(self.failed(facts), ("scope_matches",))

    def test_condition_7_no_secret_findings(self):
        for value in (1, 3, True, False, "0", 0.0, -1, [], object()):
            with self.subTest(value=repr(value)):
                facts = good_facts()
                facts["secret_findings"] = value
                self.assertEqual(self.failed(facts), ("no_secret_exposure",))

    def test_condition_8_the_rollback_method_must_be_concrete(self):
        for text in ("", "   ", "없음", "해당 없음", "미정", "TBD", "n/a", "-", "되돌림", "짧은 문장", "가나다라마바사아자", "  가나다   라마바사아  ", None, 5, ["되돌리기"]):         # 열 자 미만(공백은 접어서 센다 — 뒤의 것은 접으면 아홉 자)
            with self.subTest(text=text):
                facts = good_facts()
                facts["rollback_method"] = text
                self.assertEqual(self.failed(facts), ("rollback_confirmed",))
        for text in ("이 병합 커밋 하나를 되돌리는 PR 을 만듭니다.", "가나다라마바사아자차", "가나다라 마바사아자차"):                                                         # 열 자부터는 통과
            with self.subTest(text=text):
                facts = good_facts()
                facts["rollback_method"] = text
                self.assertTrue(mp.check_preconditions(facts).ok)

    def test_condition_8_a_long_sentence_that_only_says_nothing_is_not_concrete_either(self):
        """길이 규칙(열 자)에 걸리지 않을 만큼 긴 '모름' 문구도 거절한다 — 짧은 문구는 길이 규칙이 이미 거절하므로 목록에는 긴 것만 있다."""
        for text in mp.ROLLBACK_PLACEHOLDERS:
            for variant in (text, text.upper(), "  " + text + "  ", text.replace(" ", "   ")):
                with self.subTest(text=variant):
                    facts = good_facts()
                    facts["rollback_method"] = variant
                    verdict = mp.check_preconditions(facts)
                    self.assertEqual(verdict.failed_codes, ("rollback_confirmed",))
                    self.assertIn("해당 사항이 없습니다", verdict.failures[0].reason)
        facts = good_facts()
        facts["rollback_method"] = "해당 사항이 없습니다 그래서 이 병합 하나를 되돌리는 PR 을 만듭니다"           # 모름 문구가 문장 속에 있기만 하면 괜찮다(정확히 같을 때만 거절)
        self.assertTrue(mp.check_preconditions(facts).ok)

    def test_a_missing_value_is_a_failure_of_the_condition_that_needs_it(self):
        owner = {"approved_number": "number_match", "approved_pr_number": "number_match", "pr_number": "number_match", "pr_title_label": "number_match", "consumed_numbers": "number_match",
                 "approved_head_sha": "no_new_commit", "current_head_sha": "no_new_commit", "current_tree": "independent_verified", "approved_paths": "scope_matches",
                 "current_paths": "scope_matches", "checks": "checks_pass", "independent_verification": "independent_verified", "has_conflict": "no_conflict",
                 "classification": "scope_matches", "secret_findings": "no_secret_exposure", "rollback_method": "rollback_confirmed", "repo_kind": "scope_matches",
                 "changed_text": "scope_matches", "head_sha_at_approval": "no_new_commit", "required_checks": "checks_pass", "pr_state": "number_match", "pr_draft": "number_match",
                 "previous_merge_main_check": "checks_pass"}
        self.assertEqual(set(owner), set(FACT_KEYS_23))
        special = {"has_conflict": "알 수 없습니다", "secret_findings": "결과가 없습니다", "rollback_method": "문장이 없습니다"}      # 값이 없을 때 이 세 조건이 쓰는 쉬운 말
        for key in FACT_KEYS_23:
            for how in ("missing", "none"):
                with self.subTest(key=key, how=how):
                    facts = good_facts()
                    if how == "missing":
                        del facts[key]
                    else:
                        facts[key] = None
                    verdict = mp.check_preconditions(facts)
                    self.assertFalse(verdict.ok)
                    self.assertEqual(verdict.failed_codes, (owner[key],))
                    reason = verdict.failures[0].reason
                    if key in special:
                        self.assertIn(special[key], reason)
                    else:                                                                     # 값이 없다고 말하고, 어느 값인지 이름을 댄다
                        self.assertIn("필요한 값이 없습니다", reason)
                        self.assertIn(key, reason)

    def test_an_empty_or_non_dictionary_facts_fails_every_condition(self):
        for facts in ({}, None, [], "facts", 5, [("approved_number", "M075")]):
            with self.subTest(facts=repr(facts)):
                verdict = mp.check_preconditions(facts)
                self.assertFalse(verdict.ok)
                self.assertEqual(len(verdict.failures), 8)

    def test_several_failures_are_reported_together(self):
        facts = good_facts()
        facts["current_head_sha"] = SHA_B
        facts["has_conflict"] = True
        facts["secret_findings"] = 2
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("no_new_commit", "no_conflict", "no_secret_exposure"))
        self.assertEqual(len(verdict.explain()), 3)
        self.assertTrue(all(": " in line for line in verdict.explain()))

    def test_weird_values_never_raise_and_never_pass(self):
        weird = (object(), [], {}, 0, "", -1, float("nan"), True, False, "x", (), {"a": 1}, [object()], b"x")
        valid_values = (("has_conflict", False), ("secret_findings", 0), ("consumed_numbers", []), ("consumed_numbers", ()), ("pr_draft", False), ("changed_text", ""), ("changed_text", "x"))                                                                                         # 값 자체가 올바른 것(통과해도 되는 것)
        for key in FACT_KEYS_23:
            for value in weird:
                with self.subTest(key=key, value=repr(value)):
                    facts = good_facts()
                    facts[key] = value
                    verdict = mp.check_preconditions(facts)
                    if any(key == name and type(value) is type(ok) and value == ok for name, ok in valid_values):
                        continue
                    self.assertFalse(verdict.ok)

    def test_the_input_is_not_modified(self):
        facts = good_facts()
        before = copy.deepcopy(facts)
        mp.check_preconditions(facts)
        self.assertEqual(facts, before)

    def test_extra_keys_are_ignored_but_the_result_is_the_same(self):
        facts = good_facts()
        facts["note"] = "참고"
        self.assertTrue(mp.check_preconditions(facts).ok)

    def test_a_broken_check_function_closes_instead_of_passing(self):
        class Exploding(dict):
            def get(self, key, default=None):
                raise RuntimeError("boom")

        verdict = mp.check_preconditions(Exploding(good_facts()))
        self.assertFalse(verdict.ok)


class MergeMethodTest(unittest.TestCase):
    def test_only_a_pr_merge_is_allowed(self):
        self.assertTrue(mp.merge_method_allowed("pr_merge"))

    def test_direct_pushes_and_force_pushes_are_refused(self):
        for method in ("push_main", "direct_push", "force_push"):
            with self.subTest(method=method):
                self.assertFalse(mp.merge_method_allowed(method))
        self.assertEqual(set(mp.FORBIDDEN_MERGE_METHODS), {"push_main", "direct_push", "force_push"})

    def test_unknown_or_differently_written_values_are_refused(self):
        for method in ("squash", "merge", "rebase", "PR_MERGE", "Pr_Merge", " pr_merge", "pr_merge ", "pr-merge", "pr_merge\n", "", None, 1, True, ["pr_merge"], b"pr_merge", ("pr_merge",), object(),
                       "git push origin main", "push", "force", "main", "push_main_branch", "pr_merge;push_main"):
            with self.subTest(method=repr(method)):
                self.assertFalse(mp.merge_method_allowed(method))


class ExplanationTest(unittest.TestCase):
    def problems(self, text, **kw):
        return mp.explanation_problems(text, **kw)

    def assert_problem(self, problems, *words):
        self.assertTrue(problems, "문제가 하나도 없다")
        self.assertTrue(any(all(word in problem for word in words) for problem in problems), (words, problems))

    def base(self, **changes):
        """render_explanation 의 기본 입력(경로 하나, 점검표는 classify_change 결과)."""
        values = dict(number="M075", pr_number=198, head_sha="c" * 40, changed_paths=["pipeline/a.py"], what=ANSWERS[0], why=ANSWERS[1], user_change=ANSWERS[2], risk=ANSWERS[3],
                      check_summary=ANSWERS[4], rollback=ANSWERS[5], classification=classify("blog", ["pipeline/a.py"], GOOD_TEXT))
        values.update(changes)
        return values

    def test_the_rendered_explanation_is_complete(self):
        text = make_text()
        self.assertEqual(self.problems(text), [])
        self.assertEqual(self.problems(text, pr_title="[M075] 초안 저장"), [])
        lines = text.split("\n")
        self.assertEqual(lines[0], "병합 요청 M075")
        self.assertEqual(lines[1], "대상 PR: #198 · 머리 커밋: ccccccc")
        for item, answer in zip(EXPLANATION_6, ANSWERS):
            self.assertIn(item + " " + answer, lines)
        self.assertIn("변경 파일 (2개)", lines)
        self.assertIn("- pipeline/drafts.py", lines)
        for label in OPERATOR_ONLY_12:
            self.assertIn("- " + label + ": 아니오", lines)
        self.assertIn("병합 방식: " + mp.AI_MERGE_OFF_NOTICE, lines)
        self.assertIn("지금은 AI 병합 기능이 꺼져 있어 운영자께서 직접 병합해 주세요.", text)
        self.assertIn("승인 방식은 반드시 병합 번호와 함께 사용해 주세요.", lines)
        self.assertEqual(lines[-3], "승인 예: M075 승인")
        self.assertEqual(lines[-2], "지금은 꺼져 있어 이 승인 글을 보내도 AI 는 병합하지 않습니다.")
        self.assertEqual(lines[-1], "")
        self.assertEqual(mp.APPROVAL_OFF_LINE, "지금은 꺼져 있어 이 승인 글을 보내도 AI 는 병합하지 않습니다.")
        self.assertNotIn("12항목 밖의 표시", text)

    def test_the_enabled_form_says_what_the_approval_does(self):
        text = make_text(enabled=True)
        self.assertEqual(self.problems(text), [])
        self.assertIn(mp.AI_MERGE_ON_NOTICE, text)
        self.assertNotIn(mp.AI_MERGE_OFF_NOTICE, text)
        self.assertNotIn(mp.APPROVAL_OFF_LINE, text)
        self.assertIn("main 에 직접 push 하지 않습니다", text)
        self.assertEqual(text.split("\n")[-2], "승인 예: M075 승인")

    def test_the_example_number_follows_the_requested_number(self):
        for number in ("M001", "M075", "M1000"):
            text = make_text(number=number)
            self.assertEqual(self.problems(text), [])
            self.assertIn("병합 요청 " + number + "\n", text)
            self.assertIn("승인 예: " + number + " 승인\n", text)

    def test_each_of_the_six_items_missing_is_reported_by_name(self):
        text = make_text()
        for item in EXPLANATION_6:
            with self.subTest(item=item):
                self.assert_problem(self.problems(drop_line(text, item + " ")), "항목이 빠졌습니다", item)

    def test_an_item_with_a_blank_short_or_non_korean_answer_is_reported(self):
        text = make_text()
        first = EXPLANATION_6[0] + " " + ANSWERS[0]
        for answer in ("", "없음", "TBD", "짧음", "the code was changed in the base", "pipeline/drafts.py", "1234567890"):
            with self.subTest(answer=answer):
                self.assert_problem(self.problems(replace_once(text, first, EXPLANATION_6[0] + " " + answer)), EXPLANATION_6[0])

    def test_the_answer_length_and_hangul_boundaries(self):
        """8자 미만이거나 한글이 4자 미만이면 문제, 그 경계의 바로 안쪽은 통과 — 두 기준이 서로를 가리지 않는다."""
        text = make_text()
        first = EXPLANATION_6[0] + " " + ANSWERS[0]
        for answer, flagged in (("가나다라마바사", True), ("가나다라마바사아", False), ("abcdefg가나다", True), ("abcd가나다라", False), ("가나다라마", True), ("가나다라", True),
                                ("가나다라마바사아자", False), ("abcdefghi가나다", True), ("abcdefg가나다라", False)):
            with self.subTest(answer=answer):
                problems = self.problems(replace_once(text, first, EXPLANATION_6[0] + " " + answer))
                self.assertEqual(any(EXPLANATION_6[0] in problem and "한글" in problem for problem in problems), flagged)

    def test_an_item_written_twice_is_reported(self):
        text = make_text() + "왜 필요한가요? 한 번 더 적은 이유입니다.\n"
        self.assert_problem(self.problems(text), "두 번 이상", "왜 필요한가요?")

    def test_the_first_line_must_be_the_request_line_with_a_standard_number(self):
        text = make_text()
        message = "첫 줄이 '병합 요청 M075' 모양이 아닙니다(번호는 M 뒤에 세 자리 또는 네 자리 숫자)"                  # 다른 불일치 문구가 아니라 바로 이 문제여야 한다
        self.assertIn(message, self.problems("\n".join(text.split("\n")[1:])))
        self.assertIn(message, self.problems(replace_once(text, "병합 요청 M075\n", "병합 요청 M75\n")))
        self.assertIn(message, self.problems(replace_once(text, "병합 요청 M075\n", "병합 요청 M0075\n")))
        self.assertIn(message, self.problems(replace_once(text, "병합 요청 M075\n", "승인 요청 M075\n")))
        self.assertIn(message, self.problems(replace_once(text, "병합 요청 M075\n", "병합 요청 M075 입니다\n")))
        for bad in ("M75", "M0075", "M000", "M12345"):                      # 표준이 아닌 번호가 첫 줄·승인 예·글 속에서 모두 같아도(서로 일치해도) 통과하지 않는다
            with self.subTest(bad=bad):
                self.assertIn(message, self.problems(text.replace("M075", bad)))

    def test_the_pr_number_and_head_commit_are_required_once(self):
        text = make_text()
        self.assert_problem(self.problems(replace_once(text, "대상 PR: #198 · 머리 커밋: ccccccc", "머리 커밋: ccccccc")), "대상 PR")
        self.assert_problem(self.problems(replace_once(text, "대상 PR: #198 · 머리 커밋: ccccccc", "대상 PR: #198")), "머리 커밋")
        self.assert_problem(self.problems(replace_once(text, "대상 PR: #198 · 머리 커밋: ccccccc", "대상 PR: #0 · 머리 커밋: ccccccc")), "대상 PR")
        self.assert_problem(self.problems(replace_once(text, "머리 커밋: ccccccc", "머리 커밋: ccccc")), "머리 커밋")                  # 5자는 짧다
        self.assert_problem(self.problems(replace_once(text, "머리 커밋: ccccccc", "머리 커밋: 해시없음")), "머리 커밋")
        self.assert_problem(self.problems(text + "대상 PR: #199\n"), "대상 PR")
        self.assert_problem(self.problems(text + "머리 커밋: abcdef1\n"), "머리 커밋")

    def test_the_changed_file_list_must_be_present_and_consistent(self):
        text = make_text()
        self.assert_problem(self.problems(replace_once(text, "변경 파일 (2개)\n", "")), "변경 파일 목록")
        self.assert_problem(self.problems(replace_once(text, "변경 파일 (2개)", "변경 파일 (3개)")), "개수")
        self.assert_problem(self.problems(replace_once(text, "변경 파일 (2개)", "변경 파일 (1개)")), "개수")
        self.assert_problem(self.problems(drop_line(drop_line(text, "- pipeline/drafts.py"), "- tests/test_drafts.py")), "비어 있습니다")
        self.assert_problem(self.problems(replace_once(text, "- tests/test_drafts.py\n", "- tests/test_drafts.py\n- ../evil.py\n").replace("(2개)", "(3개)")), "올바르지 않은 경로")

    def test_each_of_the_twelve_checklist_rows_flipped_to_yes_is_reported(self):
        text = make_text()
        for label in OPERATOR_ONLY_12:
            with self.subTest(label=label):
                flipped = replace_once(text, "- " + label + ": 아니오", "- " + label + ": 예")
                self.assert_problem(self.problems(flipped), "'예'", label)

    def test_each_of_the_twelve_checklist_rows_missing_is_reported(self):
        text = make_text()
        for label in OPERATOR_ONLY_12:
            with self.subTest(label=label):
                self.assert_problem(self.problems(drop_line(text, "- " + label + ":")), "빠진 항목", label)

    def test_a_garbled_or_extra_checklist_row_is_reported(self):
        text = make_text()
        self.assert_problem(self.problems(replace_once(text, "- PIPELINE_PAUSE: 아니오", "- PIPELINE_PAUSE: 모름")), "PIPELINE_PAUSE")
        self.assert_problem(self.problems(replace_once(text, "- PIPELINE_PAUSE: 아니오", "- PIPELINE_PAUSE:")), "PIPELINE_PAUSE")
        self.assert_problem(self.problems(replace_once(text, "- PIPELINE_PAUSE: 아니오", "- PIPELINE_PAUSE: 아니오\n- 새 항목: 예")), "새 항목")
        self.assert_problem(self.problems(replace_once(text, "- PIPELINE_PAUSE: 아니오", "- PIPELINE_PAUSE: 아니오 (일부)")), "PIPELINE_PAUSE")

    def test_a_duplicated_checklist_row_is_reported_even_when_the_last_one_says_no(self):
        """같은 항목이 두 번 나오면 뒤의 값이 앞의 '예'를 가리지 못한다."""
        text = make_text()
        for label in OPERATOR_ONLY_12:
            with self.subTest(label=label):
                row = "- " + label + ": 아니오"
                doubled = replace_once(text, row, "- " + label + ": 예\n" + row)
                self.assert_problem(self.problems(doubled), "같은 항목이 두 번", label)
                self.assert_problem(self.problems(doubled), "'예'", label)
                self.assert_problem(self.problems(replace_once(text, row, row + "\n" + row)), "같은 항목이 두 번", label)

    def test_an_unknown_checklist_row_is_reported_even_when_it_says_no(self):
        text = make_text()
        extra = replace_once(text, "- Main Branch 보호 설정: 아니오", "- Main Branch 보호 설정: 아니오\n- 알 수 없는 항목: 아니오")
        self.assert_problem(self.problems(extra), "알 수 없는 줄", "알 수 없는 항목")
        self.assertEqual([problem for problem in self.problems(extra) if "'예'" in problem], [])                      # 값이 '아니오'라도 모르는 줄은 따로 문제다
        self.assert_problem(self.problems(replace_once(text, "- PIPELINE_PAUSE: 아니오", "- 파이프라인 정지: 아니오")), "알 수 없는 줄", "파이프라인 정지")

    def test_a_checklist_row_after_a_blank_line_is_reported(self):
        """빈 줄로 점검표를 끊고 그 뒤에 '예' 줄을 숨겨도 읽는다."""
        text = make_text()
        split = replace_once(text, "- Main Branch 보호 설정: 아니오", "- Main Branch 보호 설정: 아니오\n\n- 외부 비용 발생 기능: 예")
        self.assert_problem(self.problems(split), "점검표 밖", "외부 비용 발생 기능")
        also = replace_once(text, "- Main Branch 보호 설정: 아니오", "- Main Branch 보호 설정: 아니오\n\n- Main Branch 보호 설정: 예")
        self.assert_problem(self.problems(also), "점검표 밖", "Main Branch 보호 설정")
        late = text + "- 광고·AdSense·ads.txt: 예\n"
        self.assert_problem(self.problems(late), "점검표 밖", "광고·AdSense·ads.txt")
        moved = drop_line(text, "- 의존성 추가:").replace("승인 방식은", "- 의존성 추가: 예\n승인 방식은")
        self.assert_problem(self.problems(moved), "빠진 항목", "의존성 추가")

    def test_the_checklist_header_is_required(self):
        text = make_text()
        header = "운영자 전용 항목 점검 (모두 아니오여야 AI 병합 대상입니다)"
        self.assertTrue(self.problems(replace_once(text, header + "\n", "")))
        self.assertTrue(self.problems(text.replace(header, "점검표 (생략)")))

    def test_a_yes_in_the_rendered_checklist_makes_it_not_an_ai_merge_request(self):
        """점검표는 classify_change 결과에서 채워진다 — 걸린 항목은 예로 적히고 그 설명은 AI 병합 요청으로 통과하지 못한다."""
        paths = ("pipeline/drafts.py", "tests/test_drafts.py")
        for code, label in mp.OPERATOR_ONLY_ITEMS:
            with self.subTest(code=code):
                text = make_text(classification=classify("blog", paths, GOOD_TEXT, dict(DECLARED_OK, **{code: True})))
                self.assertIn("- " + label + ": 예", text.split("\n"))
                self.assertEqual(sum(1 for line in text.split("\n") if line.endswith(": 예")), 1)
                self.assert_problem(self.problems(text), "'예'", label)
        self.assertEqual(self.problems(make_text(classification=classify("blog", paths, GOOD_TEXT, {code: False for code in mp.OPERATOR_ONLY_CODES}))), [])

    def test_the_checklist_follows_the_classification_of_the_real_change(self):
        """워크플로·광고 표면 경로를 설명에 넣으면 점검표에 그대로 예가 찍힌다(옛 기본값 전부 아니오가 운영자를 속이지 못한다)."""
        for path, code in ((".github/workflows/ci.yml", "workflow"), ("index.html", "ads"), ("_layouts/default.html", "ads"), ("_posts/2026-11-15-a.md", "public_content"),
                           ("pipeline/ops_inbox_policy.json", "pipeline_pause"), ("pipeline/blogs.json", "publish_mode"), ("pipeline/source_registry.json", "provider_activation"),
                           (".env", "credentials"), ("requirements.txt", "dependencies"), ("pipeline/blogs.json", "auto_publish")):
            with self.subTest(path=path, code=code):
                text = make_text(paths=(path,), classification=classify("blog", [path], GOOD_TEXT))
                label = dict(mp.OPERATOR_ONLY_ITEMS)[code]
                self.assertIn("- " + label + ": 예", text.split("\n"))
                self.assert_problem(self.problems(text), "'예'", label)
        text = make_text(paths=("pipeline/a.py",), classification=classify("blog", ["pipeline/a.py"], "x = 'adsbygoogle'\nPIPELINE_PAUSE\nDROP TABLE x\n"))
        for label in ("광고·AdSense·ads.txt", "PIPELINE_PAUSE", "데이터 삭제·Migration"):
            self.assertIn("- " + label + ": 예", text.split("\n"))
        self.assertEqual(sum(1 for line in text.split("\n") if line.endswith(": 예")), 3)

    def test_the_extra_flags_are_printed_and_make_it_not_an_ai_merge_request(self):
        for path, label in (("scripts/validate_repo.py", "안전 장치 파일"), ("pipeline/merge_policy.py", "병합 정책 자체")):
            with self.subTest(path=path):
                text = make_text(paths=(path,), classification=classify("blog", [path], GOOD_TEXT))
                self.assertIn("12항목 밖의 표시: " + label, text.split("\n"))
                self.assert_problem(self.problems(text), "12항목 밖의 표시", label)
                self.assertEqual(sum(1 for line in text.split("\n") if line.endswith(": 예")), 0)
        both = classify("blog", ["scripts/validate_repo.py"], "import requests\n")
        self.assertIn("12항목 밖의 표시: 안전 장치 파일, 새 외부 접속 코드", make_text(paths=("scripts/validate_repo.py",), classification=both).split("\n"))
        self.assertIn("12항목 밖의 표시: 데스크톱 앱 패키징·배포 설정", mp.render_explanation(**self.base(changed_paths=["VERSION"], classification=classify("desktop", ["VERSION"], ""))).split("\n"))

    def test_render_refuses_a_classification_that_does_not_belong_to_these_files(self):
        other = classify("blog", ["pipeline/other.py"], GOOD_TEXT)
        with self.assertRaises(ValueError):
            mp.render_explanation(**self.base(classification=other))
        stale = classify("blog", ["pipeline/a.py", "pipeline/b.py"], GOOD_TEXT)
        with self.assertRaises(ValueError):
            mp.render_explanation(**self.base(classification=stale))
        broken = dict(classify("blog", ["pipeline/a.py"], GOOD_TEXT).to_dict(), tier="operator_only")                       # ai_ok 인 내용이 운영자 전용이라고 적힌 모순
        with self.assertRaises(ValueError):
            mp.render_explanation(**self.base(classification=broken))
        broken = dict(classify("blog", [".github/x.yml"], "").to_dict(), tier="ai_ok")                             # 항목이 걸렸는데 ai_ok 라고 적힌 모순
        with self.assertRaises(ValueError):
            mp.render_explanation(**self.base(changed_paths=[".github/x.yml"], classification=broken))
        with self.assertRaises(TypeError):
            mp.render_explanation("M075", 198, "c" * 40, ["pipeline/a.py"], *ANSWERS)                                         # 분류 없이는 만들지 않는다
        self.assertIn("병합 요청 M075", mp.render_explanation(**self.base(classification=classify("blog", ["pipeline/a.py"], GOOD_TEXT).to_dict())))     # 사전 모양은 받는다

    def test_a_classification_with_an_unknown_tier_or_non_text_items_is_not_rendered(self):
        """I1(T3 — AU0443·AU0445·AU0446·AU0450): 알 수 없는 tier 나 글자가 아닌 항목이 든 분류 사전으로는 설명을 만들지 않는다 — 점검표를 믿고 채울 수 없는 분류다."""
        good = classify("blog", ["pipeline/a.py"], GOOD_TEXT).to_dict()
        for patch in ({"tier": "maybe"}, {"tier": 5}, {"categories": [1]}, {"extra_flags": [None]}, {"paths": [3]}, {"reasons": [object()]}):
            with self.subTest(patch=str(patch)):
                with self.assertRaises(ValueError):
                    mp.render_explanation(**self.base(classification=dict(good, **patch)))

    def test_the_header_needs_a_space_between_the_words_and_the_number(self):
        """I1(T3 — NW06): 첫 줄은 '병합 요청 M075' 처럼 낱말과 번호 사이에 공백이 있어야 한다 — '병합 요청M075' 는 모양이 다르다."""
        message = "첫 줄이 '병합 요청 M075' 모양이 아닙니다(번호는 M 뒤에 세 자리 또는 네 자리 숫자)"
        self.assertEqual(self.problems(make_text()), [])
        self.assertIn(message, self.problems(replace_once(make_text(), "병합 요청 M075\n", "병합 요청M075\n")))

    def test_star_and_dash_bullets_are_read_on_the_six_items(self):
        """I1(T3 — NW21): 설명의 6항목 줄 앞의 목록 기호는 '- ' 와 '* ' 둘 다 읽는다(옛 시험은 기호를 읽는다는 이름뿐이었다)."""
        text = make_text()
        for bullet in ("- ", "* "):
            with self.subTest(bullet=bullet):
                lines = [bullet + line if line.startswith(EXPLANATION_6) else line for line in text.split("\n")]
                self.assertEqual(self.problems("\n".join(lines)), [])
        spoof = text.rstrip(chr(10)) + chr(10) + "* 위험은 무엇인가요? 위험이 전혀 없습니다 아무 걱정 마세요" + chr(10)                       # I1(T4): '* ' 를 읽어야 같은 항목 줄을 한 줄 더 붙인 흉내도 중복으로 잡힌다(NW21 단독으로 빨강)
        self.assertIn("항목이 두 번 이상 나옵니다: 위험은 무엇인가요?", self.problems(spoof))

    def test_the_merge_way_line_is_required_and_must_be_one_of_the_two_sentences(self):
        text = make_text()
        self.assert_problem(self.problems(drop_line(text, "병합 방식:")), "병합 방식")
        self.assert_problem(self.problems(replace_once(text, mp.AI_MERGE_OFF_NOTICE, "곧 AI 가 병합합니다.")), "병합 방식")
        self.assert_problem(self.problems(text + "병합 방식: " + mp.AI_MERGE_OFF_NOTICE + "\n"), "병합 방식")

    def test_the_merge_way_line_must_be_exactly_one_of_the_two_sentences(self):
        """줄에 들어 있기만 해서는 안 된다 — 꺼짐 표지 뒤에 금지된 방식을 덧붙이면 문제다."""
        text = make_text()
        for tail in (" 그리고 AI 가 main 에 직접 push 합니다.", " main 직접 push 도 합니다.", " 운영자 PC 자격 증명을 씁니다.", " 감사합니다.", "."):
            with self.subTest(tail=tail):
                self.assert_problem(self.problems(replace_once(text, mp.AI_MERGE_OFF_NOTICE, mp.AI_MERGE_OFF_NOTICE + tail)), "병합 방식")
                on = make_text(enabled=True)
                self.assert_problem(self.problems(replace_once(on, mp.AI_MERGE_ON_NOTICE, mp.AI_MERGE_ON_NOTICE + tail)), "병합 방식")
        self.assert_problem(self.problems(replace_once(text, mp.AI_MERGE_OFF_NOTICE, "운영자 PC 자격 증명으로 main 직접 push 합니다.")), "허용하지 않는 방식")
        self.assert_problem(self.problems(replace_once(text, mp.AI_MERGE_OFF_NOTICE, "main 직접 push 로 병합합니다.")), "허용하지 않는 방식")
        self.assert_problem(self.problems(replace_once(text, mp.AI_MERGE_OFF_NOTICE, "")), "글자 그대로")
        self.assertEqual(self.problems(replace_once(text, "병합 방식: ", "병합 방식:  ")), [])                           # 앞뒤 공백은 줄 읽기에서 접힌다

    def test_the_off_state_needs_the_line_that_the_approval_does_nothing_right_after_the_example(self):
        text = make_text()
        self.assert_problem(self.problems(drop_line(text, mp.APPROVAL_OFF_LINE)), "승인해도 AI 가 병합하지 않는다는 줄")
        self.assert_problem(self.problems(text + mp.APPROVAL_OFF_LINE + "\n"), "승인해도 AI 가 병합하지 않는다는 줄")
        moved = drop_line(text, mp.APPROVAL_OFF_LINE).replace("승인 방식은", mp.APPROVAL_OFF_LINE + "\n승인 방식은")
        self.assert_problem(self.problems(moved), "'승인 예' 줄 바로 다음")
        self.assert_problem(self.problems(text.replace("승인 예: M075 승인\n", "승인 예: M075 승인\n\n")), "'승인 예' 줄 바로 다음")
        on = make_text(enabled=True)
        self.assert_problem(self.problems(on + mp.APPROVAL_OFF_LINE + "\n"), "함께 있습니다")

    def test_the_approval_guide_and_example_lines_are_required(self):
        text = make_text()
        self.assert_problem(self.problems(drop_line(text, "승인 방식은")), "승인 안내")
        self.assert_problem(self.problems(drop_line(text, "승인 예:")), "승인 예")
        self.assert_problem(self.problems(text + "승인 예: M075 승인\n"), "승인 예")

    def test_every_number_in_the_text_must_agree(self):
        text = make_text()
        mismatched = replace_once(text, "승인 예: M075 승인", "승인 예: M076 승인")
        self.assert_problem(self.problems(mismatched), "승인 예의 번호", "M076")
        self.assert_problem(self.problems(mismatched), "다른 번호의 승인 문구", "M076")
        stray = replace_once(text, ANSWERS[1], ANSWERS[1] + " 참고로 M999 승인 이라고 쓰면 됩니다.")
        self.assert_problem(self.problems(stray), "다른 번호의 승인 문구", "M999")
        self.assert_problem(self.problems(text, pr_title="[M076] 제목"), "PR 제목")
        self.assert_problem(self.problems(text, pr_title="제목 [M075]"), "PR 제목")
        self.assert_problem(self.problems(text, pr_title="[M075] [M076] 제목"), "PR 제목")
        self.assert_problem(self.problems(text, pr_title=""), "PR 제목")
        self.assertEqual(self.problems(text + "참고: M074 병합은 이미 끝났습니다.\n"), [])                 # 승인 문구가 아닌 다른 번호 언급은 괜찮다

    def test_invisible_and_direction_characters_are_reported(self):
        text = make_text()
        for char in (chr(0x200B), chr(0x200E), chr(0x202E), chr(0x2066), chr(0xFEFF), chr(0x2060)):
            with self.subTest(code=hex(ord(char))):
                self.assert_problem(self.problems(text.replace("병합 요청", "병합" + char + " 요청", 1)), "보이지 않는 글자")

    def test_windows_line_endings_and_bullets_are_read(self):
        text = make_text()
        self.assertEqual(self.problems(text.replace("\n", "\r\n")), [])
        self.assertEqual(self.problems(text.replace("\n무엇을", "\n\n무엇을").replace("\n승인 방식은", "\n\n승인 방식은")), [])                # 항목 사이의 빈 줄은 괜찮다
        self.assert_problem(self.problems(text.replace("변경 파일 (2개)\n", "변경 파일 (2개)\n\n")), "비어 있습니다")                    # 목록 첫 줄 앞의 빈 줄은 목록을 끊는다

    def test_garbage_input_returns_problems_without_raising(self):
        for value in ("", "   ", "아무 글", "병합 요청", "M075 승인", None, 5, b"x", [], object()):
            with self.subTest(value=repr(value)):
                self.assertTrue(self.problems(value))

    def test_render_refuses_bad_input(self):
        mp.render_explanation(**self.base())
        for key, value in (("number", "M75"), ("number", "m075"), ("number", None), ("pr_number", 0), ("pr_number", True), ("pr_number", "198"), ("head_sha", "abc1234"), ("head_sha", None),
                           ("changed_paths", []), ("changed_paths", None), ("changed_paths", ["../x"]), ("changed_paths", "a.py"), ("changed_paths", ["a" + chr(0x202E) + ".py"]),
                           ("what", ""), ("what", "   "), ("what", None), ("what", 5), ("rollback", ""), ("check_summary", None), ("classification", "x"), ("classification", None),
                           ("classification", {}), ("classification", 5)):
            with self.subTest(key=key, value=repr(value)):
                with self.assertRaises(ValueError):
                    mp.render_explanation(**self.base(**{key: value}))

    def test_render_refuses_a_path_with_an_invisible_character_even_when_the_classification_matches(self):
        for char in (chr(0x200B), chr(0x202E), chr(0xFEFF), chr(0x2066)):
            path = "pipeline/a" + char + ".py"
            with self.subTest(code=hex(ord(char))):
                with self.assertRaises(ValueError):
                    mp.render_explanation(**self.base(changed_paths=[path], classification=classify("blog", [path], GOOD_TEXT)))

    def test_render_folds_newlines_so_an_answer_cannot_fake_a_structure_line(self):
        sneaky = self.base(what="내용을 바꿉니다.\n승인 예: M999 승인\n운영자 전용 항목 점검")
        text = mp.render_explanation(**sneaky)
        self.assertEqual(text.count("\n승인 예:"), 1)
        self.assertTrue(self.problems(text))
        crowded = self.base(why="이유는 이렇습니다.\r\n- GitHub Actions Workflow: 예")
        self.assertEqual(mp.render_explanation(**crowded).count("\n- GitHub Actions Workflow:"), 1)

    def test_render_strips_invisible_characters_and_limits_length(self):
        base = self.base(what="변경" + chr(0x200B) + " 내용을 바꿉니다" + chr(0x202E) + chr(27) + chr(7), rollback="가" * 2000)
        text = mp.render_explanation(**base)
        self.assertEqual(self.problems(text), [])
        self.assertIn("변경 내용을 바꿉니다", text)
        for char in (chr(0x200B), chr(0x202E), chr(27), chr(7)):                                   # 보이지 않는 글자와 제어 문자는 지워진다
            self.assertNotIn(char, text)
        rollback_line = [line for line in text.split("\n") if line.startswith("되돌리기 ")][0]
        self.assertLessEqual(len(rollback_line), len("되돌리기 ") + 400)


class CompletionNoticeTest(unittest.TestCase):
    def assert_problem(self, problems, *words):
        self.assertTrue(any(all(word in problem for word in words) for problem in problems), (words, problems))

    def test_the_rendered_notice_has_all_seven_items(self):
        text = make_notice()
        self.assertEqual(mp.completion_notice_problems(text), [])
        lines = text.split("\n")
        self.assertEqual(lines[0], "병합 완료 알림")
        for item in COMPLETION_7:
            self.assertEqual(len([line for line in lines if line.startswith(item + ": ")]), 1, item)
        self.assertIn("병합 번호: M075", lines)
        self.assertIn("PR 번호: #198", lines)
        self.assertIn("병합된 Commit: dddddddddddd", lines)

    def test_each_of_the_seven_items_missing_is_reported_by_name(self):
        text = make_notice()
        for item in COMPLETION_7:
            with self.subTest(item=item):
                self.assert_problem(mp.completion_notice_problems(drop_line(text, item + ":")), "빠졌습니다", item)

    def test_an_item_with_an_empty_value_is_reported(self):
        text = make_notice()
        for item in COMPLETION_7:
            with self.subTest(item=item):
                line = [line for line in text.split("\n") if line.startswith(item + ":")][0]
                self.assert_problem(mp.completion_notice_problems(text.replace(line, item + ":")), "비어 있습니다", item)
                self.assert_problem(mp.completion_notice_problems(text.replace(line, item + ":   ")), "비어 있습니다", item)

    def test_an_item_without_a_colon_is_not_found(self):
        text = make_notice()
        self.assert_problem(mp.completion_notice_problems(replace_once(text, "이상 유무: 이상 없음", "이상 유무 이상 없음")), "빠졌습니다", "이상 유무")

    def test_an_item_written_twice_is_reported(self):
        text = make_notice() + "이상 유무: 있음\n"
        self.assert_problem(mp.completion_notice_problems(text), "두 번 이상", "이상 유무")

    def test_the_value_formats_are_checked(self):
        text = make_notice()
        for old, new, item in (("병합 번호: M075", "병합 번호: M75", "병합 번호"), ("병합 번호: M075", "병합 번호: 075", "병합 번호"), ("병합 번호: M075", "병합 번호: m075", "병합 번호"),
                               ("PR 번호: #198", "PR 번호: 열아홉", "PR 번호"), ("PR 번호: #198", "PR 번호: #0", "PR 번호"), ("PR 번호: #198", "PR 번호: 12a", "PR 번호"),
                               ("병합된 Commit: dddddddddddd", "병합된 Commit: 해시없음", "병합된 Commit"), ("병합된 Commit: dddddddddddd", "병합된 Commit: abc12", "병합된 Commit")):
            with self.subTest(new=new):
                self.assert_problem(mp.completion_notice_problems(replace_once(text, old, new)), item)
        self.assertEqual(mp.completion_notice_problems(replace_once(text, "PR 번호: #198", "PR 번호: 198")), [])

    def test_bullets_and_full_width_colons_are_read(self):
        text = make_notice()
        self.assertEqual(mp.completion_notice_problems("\n".join("- " + line if ": " in line else line for line in text.split("\n"))), [])
        self.assertEqual(mp.completion_notice_problems(text.replace(": ", chr(0xFF1A) + " ")), [])
        self.assertEqual(mp.completion_notice_problems(text.replace("\n", "\r\n")), [])

    def test_star_bullets_are_read_like_dash_bullets(self):
        """I1(T3 — NW22): 완료 알림 항목 앞의 목록 기호는 '- ' 와 '* ' 둘 다 읽는다."""
        text = make_notice()
        for bullet in ("- ", "* "):
            with self.subTest(bullet=bullet):
                self.assertEqual(mp.completion_notice_problems("\n".join(bullet + line if ": " in line else line for line in text.split("\n"))), [])
        spoof = text.rstrip(chr(10)) + chr(10) + "* 이상 유무: 이상 없음" + chr(10)                                                        # I1(T4): '* ' 를 읽어야 같은 항목 줄을 한 줄 더 붙인 흉내도 중복으로 잡힌다(NW22 단독으로 빨강)
        self.assertIn("항목이 두 번 이상 나옵니다: 이상 유무", mp.completion_notice_problems(spoof))

    def test_invisible_characters_are_reported(self):
        self.assert_problem(mp.completion_notice_problems(make_notice().replace("이상 유무", "이상" + chr(0x200B) + " 유무", 1)), "보이지 않는 글자")

    def test_garbage_input_returns_problems_without_raising(self):
        for value in ("", "알림", None, 5, b"x", [], object()):
            with self.subTest(value=repr(value)):
                self.assertTrue(mp.completion_notice_problems(value))

    def test_render_refuses_bad_input(self):
        base = dict(number="M075", pr_number=198, merged_commit="d" * 40, change="초안 저장이 반영되었습니다.", main_checks="전체 통과", anomaly="이상 없음", rollback="병합 커밋 한 개를 되돌립니다.")
        mp.render_completion_notice(**base)
        for key, value in (("number", "M75"), ("pr_number", 0), ("pr_number", True), ("merged_commit", "abc"), ("merged_commit", None), ("change", ""), ("rollback", None), ("anomaly", 5)):
            with self.subTest(key=key, value=repr(value)):
                with self.assertRaises(ValueError):
                    mp.render_completion_notice(**dict(base, **{key: value}))


def record(number, **changes):
    base = {"number": number}
    base.update({key: True for key, _label in mp.TRIAL_CRITERIA})
    base.update(changes)
    return base


class TrialTest(unittest.TestCase):
    OK3 = ("M070", "M071", "M072")

    def test_three_satisfied_records_continue(self):
        self.assertEqual(mp.evaluate_trial([record(n) for n in self.OK3]), "continue")
        self.assertEqual(mp.evaluate_trial([record(n) for n in self.OK3 + ("M073",)]), "continue")
        self.assertEqual(mp.evaluate_trial(tuple(record(n) for n in self.OK3)), "continue")
        report = mp.trial_report([record(n) for n in self.OK3])
        self.assertEqual((report.result, report.violations, report.counted), ("continue", (), 3))

    def test_fewer_than_three_without_violations_is_pending(self):
        for count in (0, 1, 2):
            with self.subTest(count=count):
                self.assertEqual(mp.evaluate_trial([record(n) for n in self.OK3[:count]]), "pending")

    def test_one_violation_stops_immediately_even_with_fewer_than_three_records(self):
        for key, label in mp.TRIAL_CRITERIA:
            for count in (1, 2, 3):
                with self.subTest(criterion=label, count=count):
                    records = [record(n) for n in self.OK3[:count - 1]] + [record(self.OK3[count - 1], **{key: False})]
                    report = mp.trial_report(records)
                    self.assertEqual(report.result, "stop_immediately")
                    self.assertTrue(any(label in violation for violation in report.violations), report.violations)
                    self.assertEqual(mp.evaluate_trial(records), "stop_immediately")

    def test_a_violation_in_any_position_of_a_longer_history_stops(self):
        for position in range(4):
            records = [record("M07%d" % n) for n in range(4)]
            records[position] = dict(records[position], no_revert=False)
            self.assertEqual(mp.evaluate_trial(records), "stop_immediately")

    def test_a_missing_or_non_boolean_value_is_a_violation(self):
        for key, _label in mp.TRIAL_CRITERIA:
            missing = record("M070")
            del missing[key]
            with self.subTest(key=key, how="missing"):
                self.assertEqual(mp.evaluate_trial([missing, record("M071"), record("M072")]), "stop_immediately")
            for value in ("true", "True", 1, 0, "예", [], {}, False):
                if key == "main_checks_passed" and value is None:
                    continue
                with self.subTest(key=key, value=repr(value)):
                    self.assertEqual(mp.evaluate_trial([record("M070", **{key: value})]), "stop_immediately")
        self.assertEqual(mp.evaluate_trial([record("M070", no_revert=None)]), "stop_immediately")

    def test_an_unknown_main_check_result_is_pending_not_continue(self):
        records = [record("M070"), record("M071"), record("M072", main_checks_passed=None)]
        self.assertEqual(mp.evaluate_trial(records), "pending")
        self.assertEqual(mp.evaluate_trial(records[:1] + [record("M071", main_checks_passed=None)]), "pending")
        self.assertEqual(mp.evaluate_trial(records + [record("M073", no_wrong_merge=False)]), "stop_immediately")

    def test_the_same_number_twice_is_a_violation(self):
        report = mp.trial_report([record("M070"), record("M070"), record("M071")])
        self.assertEqual(report.result, "stop_immediately")
        self.assertTrue(any("두 번 기록" in violation for violation in report.violations))
        self.assertEqual(mp.evaluate_trial([record("M070"), record("M070"), record("M070")]), "stop_immediately")

    def test_a_non_standard_number_or_a_malformed_record_is_a_violation(self):
        for bad in (record("M75"), record("m070"), record(None), record("P070"), record(70), {"number": "M070"}, "M070", None, 5, ["M070"]):
            with self.subTest(bad=repr(bad)):
                self.assertEqual(mp.evaluate_trial([bad, record("M071"), record("M072")]), "stop_immediately")

    def test_records_that_are_not_a_list_are_stopped(self):
        for value in (None, "M070", 5, {"M070": record("M070")}, record("M070"), object()):
            with self.subTest(value=repr(value)):
                self.assertEqual(mp.evaluate_trial(value), "stop_immediately")

    def test_three_records_of_which_one_is_bad_never_continue(self):
        for key, _label in mp.TRIAL_CRITERIA:
            records = [record("M070"), record("M071", **{key: False}), record("M072")]
            self.assertNotEqual(mp.evaluate_trial(records), "continue")

    def test_the_inputs_are_not_modified(self):
        records = [record(n) for n in self.OK3]
        before = copy.deepcopy(records)
        mp.evaluate_trial(records)
        self.assertEqual(records, before)

    def test_the_three_results_are_the_documented_words(self):
        self.assertEqual((mp.TRIAL_CONTINUE, mp.TRIAL_PENDING, mp.TRIAL_STOP), ("continue", "pending", "stop_immediately"))


class ClassifySiteDefaultDenyTest(unittest.TestCase):
    """블로그 저장소는 사이트로 내보내지 않는 맨 위 항목(SITE_INTERNAL_ENTRIES 21개) 밖의 파일·폴더를 공개 파일(public_content)로 본다 — 모르는 것은 막는 쪽이 기본이다(M1).
    README.md·CNAME·.nojekyll·새 고정 페이지·정적 파일·_data·_sass·_plugins 가 AI 병합으로 새지 않는다. 앱 저장소(desktop)에는 적용하지 않는다."""

    PUBLIC_ONLY = ("README.md", "CNAME", ".nojekyll", "faq.md", "disclaimer.md", "info/faq.md", "pages/terms.html", "ko/about.md", "style.css", "sitemap.xml", "favicon.ico", "humans.txt",
                   "_data/menu.yml", "_sass/main.scss", "_plugins/hook.rb", "LICENSE", "static/x.js", "css/site.css", "images/a.png", "blog/index.md", ".gitignore", ".design/a.png",
                   ".well-known/acme.txt", "newpage.md", "새페이지.md", "archive/2026/index.md", "sw.js", "manifest.json", "docs-x.html", "tests-report.html", "pipelines/a.py", "script/a.py")
    INTERNAL = {"AGENTS.md": ((), ("safety_guard",)), "AI_COLLAB.md": ((), ("safety_guard",)), "CLAUDE.md": ((), ("safety_guard",)), "GEMINI.md": ((), ("safety_guard",)),
                "HANDLER.md": ((), ("safety_guard",)), "WORKLOG.md": ((), ()), "docs": ((), ()), "인수인계": ((), ()), "generator.py": ((), ("safety_guard",)),
                "blogger_generator.py": ((), ("safety_guard",)), "pipeline": ((), ()), "scripts": ((), ()), "tests": ((), ()), "history.json": (("public_content",), ()),
                "blogger_history.json": (("public_content",), ()), "blogger_ko_history.json": (("public_content",), ()), "naver_history.json": (("public_content",), ()),
                "pages.json": (("public_content",), ()), "requirements-dev.txt": (("dependencies",), ()), "requirements-edits.txt": (("dependencies",), ()),
                "requirements-pipeline.txt": (("dependencies",), ())}
    FOLDERS = ("docs", "인수인계", "pipeline", "scripts", "tests")

    def result(self, path, kind="blog", text=""):
        return classify(kind, [path], text)

    def test_every_file_the_site_could_export_is_operator_only_as_public_content(self):
        for path in self.PUBLIC_ONLY:
            with self.subTest(path=path):
                result = self.result(path)
                self.assertEqual((result.tier, result.categories, result.extra_flags), ("operator_only", ("public_content",), ()), path)
                self.assertTrue(any("공개" in reason and path in reason for reason in result.reasons), result.reasons)

    def test_many_new_top_level_names_are_all_public_by_default(self):
        names = []
        for number in range(40):
            names += ["top%d/file%d.py" % (number, number), "new%d.md" % number, ".hidden%d" % number, "_x%d/a.rb" % number, "Docs%d/a.md" % number, "한글%d.txt" % number]
        for path in names:
            with self.subTest(path=path):
                self.assertEqual(self.result(path).categories, ("public_content",))

    def test_the_internal_entries_are_exactly_the_site_exclude_list_and_stay_ai_ok_unless_another_rule_applies(self):
        self.assertEqual(set(self.INTERNAL), set(mp.SITE_INTERNAL_ENTRIES))
        for entry in mp.SITE_INTERNAL_ENTRIES:
            path = entry + "/x.txt" if entry in self.FOLDERS else entry
            categories, extras = self.INTERNAL[entry]
            with self.subTest(entry=entry):
                result = self.result(path)
                self.assertEqual((result.categories, result.extra_flags), (categories, extras), path)
                self.assertEqual(result.tier, "ai_ok" if not categories and not extras else "operator_only")

    def test_the_default_deny_is_the_only_reason_for_the_unlisted_entries_and_never_piles_on_another_finding(self):
        for path, categories in ((".github/workflows/ci.yml", ("workflow",)), ("requirements.txt", ("dependencies",)), (".env", ("credentials",)), ("_layouts/a.html", ("ads",)),
                                 ("_includes/a.html", ("ads",)), ("ads.txt", ("ads",)), ("_config.yml", ("ads",)), ("pipeline/blogs.json", ("publish_mode", "auto_publish", "ads")),
                                 ("Gemfile", ("dependencies",)), ("package.json", ("dependencies",)), ("secret.txt", ("credentials",)), ("token.json", ("credentials",))):
            with self.subTest(path=path):
                self.assertEqual(set(self.result(path).categories), set(categories))
                self.assertNotIn("public_content", self.result(path).categories, path)

    def test_the_match_on_the_internal_entry_is_exact_and_case_sensitive(self):
        """GitHub Pages 는 대소문자를 가려 Docs/x.html 은 내보내지는데 docs 만 뺀다 — 이름이 정확히 같지 않으면 공개 파일로 본다."""
        for path in ("Docs/x.md", "DOCS/x.md", "Pipeline/x.py", "PIPELINE/x.py", "Tests/x.py", "TESTS/x.py", "Scripts/x.py", "인수인계2/x.md", "worklog.md", "Worklog.md", "WORKLOG.MD",
                     "docs.md", "docs2/x.md", "pipeline.py", "scripts.py", "tests.py", "generator.py.bak", "History.json", "requirements-dev.txt.bak"):
            with self.subTest(path=path):
                self.assertIn("public_content", self.result(path).categories, path)
        for path in ("docs/Docs/x.md", "pipeline/Tests/x.py", "tests/Pipeline/x.py", "docs/README.md", "pipeline/README.md", "scripts/CNAME", "tests/.nojekyll", "docs/style.css", "docs/_data/x.yml"):
            with self.subTest(inner=path):
                self.assertEqual(self.result(path).tier, "ai_ok", path)                       # 안쪽 폴더의 이름은 보지 않는다 — 맨 위 항목만 본다

    def test_the_explicit_public_file_names_are_flagged_even_next_to_other_findings(self):
        for path in ("readme.md", "README.MD", "cname", "CNAME", ".nojekyll", "sitemap.xml", "favicon.ico", "humans.txt", "style.css", "history.json", "blogger_ko_history.json", "pages.json"):
            with self.subTest(path=path):
                self.assertIn("public_content", self.result(path).categories, path)

    def test_the_application_repository_has_no_site(self):
        for path in ("README.md", "CNAME", ".nojekyll", "faq.md", "style.css", "src/x.py", "info/faq.md", "static/x.js", "docs/x.md", "LICENSE", ".gitignore"):
            with self.subTest(path=path):
                self.assertEqual(self.result(path, kind="desktop").tier, "ai_ok", path)

    def test_a_mixed_change_lists_the_public_files_in_one_reason(self):
        result = classify("blog", ["pipeline/a.py", "README.md", "CNAME", "faq.md", "info/x.md"], GOOD_TEXT)
        self.assertEqual(result.categories, ("public_content",))
        reason = [reason for reason in result.reasons if "사이트로 내보낼 수 있는 맨 위 항목" in reason or "공개 게시물" in reason]
        self.assertTrue(reason)
        self.assertNotIn("pipeline/a.py", " ".join(result.reasons))

    def test_a_pipeline_change_next_to_one_unknown_top_level_file_is_operator_only(self):
        self.assertEqual(classify("blog", ["pipeline/a.py", "tests/test_a.py", "docs/a.md"], GOOD_TEXT).tier, "ai_ok")
        self.assertEqual(classify("blog", ["pipeline/a.py", "tests/test_a.py", "docs/a.md", "extra.txt"], GOOD_TEXT).tier, "operator_only")

    def test_the_rule_holds_for_every_path_outside_the_internal_entries(self):
        """성질: 블로그 저장소에서 맨 위 항목이 내부 목록에 없는 경로는 무엇이든 운영자 전용이다."""
        seeds = ("a", "docs", "Docs", "pipeline", "src", "app", "_x", ".x", "x.md", "index", "robots.txt", "아", "docs-x", "tests_x", "scripts2", "WORKLOG", "worklog.md")
        tails = ("", "/a.py", "/b/c.md", ".py", ".txt", "/.nojekyll", "/docs/a.md", "/pipeline/a.py", "/tests/test_a.py")
        checked = 0
        for seed in seeds:
            for tail in tails:
                path = seed + tail
                if path.split("/")[0] in mp.SITE_INTERNAL_ENTRIES:
                    continue
                checked += 1
                with self.subTest(path=path):
                    self.assertEqual(classify("blog", [path]).tier, "operator_only", path)
        self.assertGreater(checked, 120)


class ClassifyDocumentTextTest(unittest.TestCase):
    """문서 파일(.md·.rst·.txt·.adoc)의 바뀐 줄에는 낱말 규칙(자격 증명 낱말·PIPELINE_PAUSE·삭제 낱말·secrets. 참조·Authorization 헤더·접속 낱말)을 적용하지 않는다 — 문서가 그 낱말을 설명하는 것은
    그 항목을 바꾸는 것이 아니다(총괄(AI)의 판단 R5, 운영자 확인 대기). 강한 비밀 모양과 광고 코드 낱말은 문서에서도 걸리고, 경로 규칙과 declared 는 그대로 적용한다."""

    WORDS = ("PIPELINE_PAUSE 를 설명합니다\n", "api_key 와 token 은 쓰지 않습니다\n", "secrets.TELEGRAM_BOT_TOKEN 참조\n", "DROP TABLE 과 rmtree 는 금지\n", "os.remove(path) 설명\n", "rm -rf 설명\n",
             "비밀번호·시크릿·자격 증명 이야기\n", "마이그레이션 계획\n", "Authorization: Bearer 헤더 설명\n", "import requests 와 curl 이야기\n", "migrate 와 unlink( 와 DROP COLUMN\n",
             "PIPELINE_PAUSE\n", "password = 1\n", "token\n", "secret\n", "access key\n", "private_key\n", "delete from rows\n")
    DOCS = ("docs/a.md", "docs/a.rst", "docs/a.txt", "docs/a.adoc", "docs/a.MD", "docs/A.Txt", "인수인계/작업내용.md", "WORKLOG.md", "pipeline/notes.txt", "tests/notes.md", "docs/sub/dir/x.rst")

    def test_documents_may_talk_about_the_watched_words(self):
        for path in self.DOCS:
            for text in self.WORDS:
                for kind in ("blog", "desktop"):
                    with self.subTest(path=path, text=text, kind=kind):
                        result = classify(kind, [path], text)
                        self.assertEqual((result.tier, result.categories, result.extra_flags), ("ai_ok", (), ()), (path, text, result.reasons))

    def test_the_same_words_in_code_are_operator_only(self):
        for path in ("pipeline/a.py", "scripts/a.sh", "pipeline/a.json", "pipeline/a.yml", "pipeline/a.md.py", "docs/tool.py", "docs/notes.json", "pipeline/a.html"):
            for text in self.WORDS:
                with self.subTest(path=path, text=text):
                    self.assertEqual(classify("blog", [path], text).tier, "operator_only", (path, text))
        for text in self.WORDS:                                                                                     # 시험 파일은 접속 낱말만 면제이고 나머지 낱말 규칙은 그대로다
            with self.subTest(path="tests/test_a.py", text=text):
                self.assertEqual(classify("blog", ["tests/test_a.py"], text).tier, "ai_ok" if text.startswith("import requests") else "operator_only", text)

    def test_each_kind_of_word_keeps_its_own_code_when_it_is_in_code(self):
        expected = (("PIPELINE_PAUSE\n", "pipeline_pause"), ("DROP TABLE x\n", "data_deletion_migration"), ("os.remove(p)\n", "data_deletion_migration"), ("secrets.X\n", "credentials"),
                    ("token\n", "credentials"), ("Authorization: Bearer x\n", "credentials"), ("adsbygoogle\n", "ads"))
        for text, code in expected:
            with self.subTest(text=text):
                self.assertEqual(classify("blog", ["pipeline/a.py"], text).categories, (code,))

    def test_strong_secret_shapes_in_documents_are_operator_only_and_never_echoed(self):
        values = dict(FAKE_SECRETS, stripe="s" + "k_live_" + "CANARY" + "a" * 18, bearer="Bear" + "er " + "CANARY" + "b" * 24)
        for name, value in values.items():
            for path in ("docs/a.md", "인수인계/작업내용.md", "docs/a.txt", "WORKLOG.md"):
                with self.subTest(name=name, path=path):
                    result = classify("blog", [path], "예시: " + value + " 끝\n")
                    self.assertEqual((result.tier, result.categories), ("operator_only", ("credentials",)), (name, path))
                    joined = " ".join(result.reasons)
                    self.assertIn("비밀 모양의 값이 있습니다", joined)
                    self.assertNotIn(value, joined)
                    self.assertNotIn("CANARY", joined)
        long_assignment = "pass" + "word = '" + "CANARY_" + "L" * 20 + "'\n"
        self.assertEqual(classify("blog", ["docs/a.md"], long_assignment).categories, ("credentials",))

    def test_a_header_word_or_a_short_value_is_not_a_strong_shape(self):
        for text in ("Authorization: Bearer 헤더 설명\n", "Bearer 짧은값\n", "bearer of news\n", "Authorization: Bearer <token>\n", "sk_live_ 접두어를 설명합니다\n", "sk_test_abc\n"):
            with self.subTest(text=text):
                self.assertEqual(classify("blog", ["docs/a.md"], text).tier, "ai_ok", text)

    def test_ad_code_words_in_documents_still_count(self):
        for text in ("adsbygoogle 를 설명합니다\n", "ca-pub- 로 시작하는 번호\n", "ADSBYGOOGLE\n"):
            with self.subTest(text=text):
                self.assertEqual(classify("blog", ["docs/a.md"], text).categories, ("ads",))

    def test_path_rules_and_declarations_still_apply_to_documents(self):
        for path, categories, extras in (("docs/AI_MERGE_POLICY.md", (), ("policy_self",)), ("docs/SECURITY_GUARDRAILS.md", (), ("safety_guard",)), ("_posts/2026-11-15-a.md", ("public_content",), ()),
                                         ("about.md", ("public_content",), ()), ("robots.txt", ("public_content",), ()), ("ads.txt", ("ads",), ()), ("requirements.txt", ("dependencies",), ()),
                                         ("requirements-dev.txt", ("dependencies",), ()), (".github/README.md", ("workflow",), ()), ("docs/secret_notes.md", ("credentials",), ()),
                                         ("docs/security/a.md", ("credentials",), ()), ("README.md", ("public_content",), ()), ("info/faq.md", ("public_content",), ())):
            with self.subTest(path=path):
                result = classify("blog", [path], "PIPELINE_PAUSE token\n")
                self.assertEqual((result.categories, result.extra_flags), (categories, extras), path)
        for code in mp.OPERATOR_ONLY_CODES:
            with self.subTest(declared=code):
                self.assertEqual(classify("blog", ["docs/a.md"], "x\n", dict(DECLARED_OK, **{code: True})).categories, (code,))
        self.assertEqual(classify("blog", ["docs/a.md"], "x\n", {}).tier, "operator_only")                       # 선언을 안 한 문서 변경도 통과하지 못한다

    def test_a_mapping_is_exempted_file_by_file(self):
        paths = ["docs/a.md", "pipeline/a.py"]
        words = "PIPELINE_PAUSE token DROP TABLE\n"
        self.assertEqual(classify("blog", paths, {"docs/a.md": words, "pipeline/a.py": GOOD_TEXT}).tier, "ai_ok")
        flagged = classify("blog", paths, {"docs/a.md": GOOD_TEXT, "pipeline/a.py": words})
        self.assertEqual(set(flagged.categories), {"pipeline_pause", "credentials", "data_deletion_migration"})
        both = classify("blog", paths, {"docs/a.md": words, "pipeline/a.py": words})
        self.assertEqual(set(both.categories), {"pipeline_pause", "credentials", "data_deletion_migration"})
        self.assertEqual(classify("blog", paths, {"docs/a.md": FAKE_SECRETS["google"], "pipeline/a.py": GOOD_TEXT}).categories, ("credentials",))

    def test_a_plain_text_is_exempted_only_when_every_changed_file_is_a_document(self):
        words = "PIPELINE_PAUSE token DROP TABLE\n"
        self.assertEqual(classify("blog", ["docs/a.md", "docs/b.txt", "WORKLOG.md"], words).tier, "ai_ok")
        for extra in ("pipeline/a.py", "tests/test_a.py", "docs/a.json", "docs/tool.py", "docs/notes.md.py"):
            with self.subTest(extra=extra):
                self.assertEqual(classify("blog", ["docs/a.md", extra], words).tier, "operator_only", extra)

    def test_the_document_is_decided_by_the_file_name_extension_only(self):
        words = "PIPELINE_PAUSE\n"
        for path in ("docs/tool.py", "notes.md.py", "docs/a.md/x.py", "docs/md", "docs/a.mdx", "docs/a.markdown", "docs/a.md.bak", "pipeline/a.json", "docs/.md.py"):
            with self.subTest(path=path):
                self.assertEqual(classify("desktop", [path], words).categories, ("pipeline_pause",), path)
        for path in ("docs/.md", "docs/a.txt", "docs/B.RST", "pipeline/x.txt", "a/b/c/d.adoc"):
            with self.subTest(doc=path):
                self.assertEqual(classify("desktop", [path], words).tier, "ai_ok", path)

    def test_a_key_that_is_not_a_listed_document_gets_the_full_rules(self):
        result = classify("blog", ["pipeline/a.py"], {"docs/x.md": "PIPELINE_PAUSE\n"})
        self.assertIn("invalid_input", result.extra_flags)
        self.assertIn("pipeline_pause", result.categories)
        result = classify("blog", ["docs/a.md"], {"docs/other.md": "PIPELINE_PAUSE\n"})
        self.assertIn("pipeline_pause", result.categories)
        result = classify("blog", ["docs/a.md"], {"./docs/a.md": "PIPELINE_PAUSE\n"})
        self.assertEqual(result.tier, "ai_ok")
        result = classify("blog", ["docs/a.md"], {"docs/a.md": "PIPELINE_PAUSE\n", "": "x"})
        self.assertIn("invalid_input", result.extra_flags)

    def test_a_documentation_only_change_that_mentions_the_words_is_ai_ok(self):
        """최근 작업 기록 커밋처럼 문서만 바꾸고 PIPELINE_PAUSE·키·토큰 낱말을 설명하는 변경은 AI 병합 대상이다(운영자 원문: 범위에 '문서')."""
        text = "- 2026-11-15 PIPELINE_PAUSE 는 그대로 두었고 API 키와 토큰은 건드리지 않았습니다. secrets.X 도 안 씁니다.\n"
        result = classify("blog", ["인수인계/작업내용.md", "docs/DEFECT_REGISTER.md", "WORKLOG.md"], {"인수인계/작업내용.md": text, "docs/DEFECT_REGISTER.md": text, "WORKLOG.md": text})
        self.assertEqual((result.tier, result.categories, result.extra_flags, result.reasons), ("ai_ok", (), (), ()))


class ClassifyNamedSafetyFilesTest(unittest.TestCase):
    """이름으로 적은 안전 장치 파일·폴더와 AI 가 읽는 규칙 문서(S1b·R5b) — 낱말로는 알 수 없는 발행 잠금·품질 Gate·인증 확인·발행기와 규칙 문서. 총괄(AI)의 판단(운영자 확인 대기)."""

    FILES = ("pipeline/publish_lock.py", "pipeline/quality_gate.py", "pipeline/gates.py", "pipeline/auth_check.py", "pipeline/registry.py", "pipeline/source_registry.py", "pipeline/health.py",
             "pipeline/draft_flow.py", "pipeline/edits/runner.py", "generator.py", "blogger_generator.py", "scripts/get_blogger_token.py", "scripts/watchdog.py", "tests/test_site_cleanup.py",
             "pipeline/run.py", "pipeline/operator_loop.py", "pipeline/telegram_inbox.py")
    PUBLISHERS = ("pipeline/publishers/__init__.py", "pipeline/publishers/base.py", "pipeline/publishers/blogger.py", "pipeline/publishers/issue_package.py", "pipeline/publishers/new_publisher.py",
                  "pipeline/publishers/sub/deep/x.py", "pipeline/publishers/notes.txt")
    RULE_DOCS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "AI_COLLAB.md", "HANDLER.md", "docs/CHARTER.md", "docs/SECURITY_GUARDRAILS.md", "docs/ACTIONS_GUIDE.md", "docs/AGENT_RUNBOOK.md",
                 "docs/SESSION_START.md", "docs/ENGINEERING_GUIDE.md", "docs/AGENT_DELEGATION.md", "docs/COPILOT_GUIDE.md", "docs/AI_FLOW.md", "docs/AI_MODEL_GUIDE.md", "docs/SOURCE_POLICY.md",
                 "docs/QUALITY_GATE.md", "docs/REQUEST_BRIEFING.md")
    CONFIRM_ITEMS = ("pipeline/shadow_run.py", "pipeline/drafts.py", "docs/GLOSSARY.md", "pipeline/profiles/blogger_practical_en.json", "tests/_bootstrap.py", "pipeline/__init__.py")
    NEAR_MISSES = ("pipeline/gate.py", "pipeline/gates2.py", "pipeline/health_check.py", "pipeline/registry_x.py", "pipeline/publish_lock_x.py", "pipeline/quality_gates.py", "pipeline/auth.py",
                   "scripts/watchdog2.py", "scripts/get_blogger_token2.py", "scripts/watchdog/a.py", "pipeline/publishers_x/a.py", "pipeline/publisher/a.py", "pipeline/publishers.py",
                   "sub/generator.py", "pipeline/generator.py", "pipeline/blogger_generator.py", "docs/generator.py", "pipeline/edits/runner2.py", "pipeline/edits/a.py", "tests/test_site_cleanup_x.py",
                   "pipeline/draft_flow2.py", "pipeline/drafts.py", "pipeline/run_helper.py", "pipeline/runs.py", "pipeline/operator_loop_x.py", "pipeline/telegram_inbox2.py", "pipeline/shadow_run.py",
                   "scripts/run.py", "sub/pipeline/run.py", "docs/pipeline/run.py")
    NEAR_DOCS = ("docs/CHARTER_NOTES.md", "docs/SESSION_START_NOTES.md", "docs/GLOSSARY.md", "docs/AGENTS_NOTES.md", "docs/AGENTS.md", "docs/CLAUDE.md", "인수인계/CLAUDE.md", "docs/ACTIONS.md",
                 "docs/FACT_PATH.md", "WORKLOG.md", "docs/DEFECT_REGISTER.md", "인수인계/작업내용.md", "docs/ENGINEERING_GUIDE_NOTES.md", "docs/QUALITY_GATE_NOTES.md")

    def assert_guard(self, path, kind="blog"):
        result = classify(kind, [path])
        self.assertEqual((result.tier, result.extra_flags), ("operator_only", ("safety_guard",)), path)
        self.assertEqual(result.categories, (), path)
        self.assertTrue(any("안전 장치 파일" in reason and path.split("/")[-1] in reason for reason in result.reasons), result.reasons)

    def test_every_named_safety_file_is_operator_only_in_both_repositories(self):
        self.assertEqual(mp.SAFETY_GUARD_FILES, self.FILES)
        for path in self.FILES:
            for kind in ("blog", "desktop"):
                with self.subTest(path=path, kind=kind):
                    self.assert_guard(path, kind)

    def test_everything_under_the_publishers_folder_is_operator_only(self):
        self.assertEqual(mp.SAFETY_GUARD_DIRS, ("pipeline/publishers",))
        for path in self.PUBLISHERS:
            with self.subTest(path=path):
                self.assert_guard(path)

    def test_the_ai_rule_documents_are_operator_only_although_documents_are_otherwise_free(self):
        self.assertEqual(set(mp.SAFETY_GUARD_DOCS), set(self.RULE_DOCS))
        self.assertEqual(len(mp.SAFETY_GUARD_DOCS), 18)
        for path in self.RULE_DOCS:
            for kind in ("blog", "desktop"):
                with self.subTest(path=path, kind=kind):
                    self.assert_guard(path, kind)

    def test_the_operator_confirm_items_are_not_in_the_list_so_a_change_to_them_is_decided_by_the_rest_of_the_rules(self):
        """운영자 확인 대기 항목(shadow_run·drafts·용어 사전·콘텐츠 안전 프로필·가져올 때 실행되는 파일)은 목록에 넣지 않았다 — 넣을지는 운영자가 정한다(§7-7)."""
        for path in self.CONFIRM_ITEMS:
            with self.subTest(path=path):
                self.assertEqual(classify("desktop", [path]).tier, "ai_ok", path)

    def test_the_names_are_matched_exactly_not_by_prefix_or_folder(self):
        for path in self.NEAR_MISSES:
            with self.subTest(path=path):
                self.assertEqual(classify("desktop", [path]).tier, "ai_ok", path)
        for path in self.NEAR_DOCS:
            with self.subTest(doc=path):
                self.assertEqual(classify("blog", [path]).tier, "ai_ok", path)

    def test_the_named_files_are_matched_without_regard_to_case_and_slashes(self):
        for path in ("Pipeline/Gates.py", "PIPELINE/GATES.PY", "pipeline" + chr(92) + "gates.py", "./pipeline/gates.py", "Generator.PY", "agents.md", "docs/charter.md", "Pipeline/Publishers/X.py",
                     "PIPELINE/PUBLISHERS/x.py"):
            with self.subTest(path=path):
                result = classify("desktop", [path])
                self.assertEqual((result.tier, result.extra_flags), ("operator_only", ("safety_guard",)), path)

    def test_a_named_file_among_ordinary_files_makes_the_whole_change_operator_only(self):
        for path in self.FILES + self.RULE_DOCS:
            with self.subTest(path=path):
                result = classify("blog", ["pipeline/topics.py", "tests/test_topics.py", "docs/GLOSSARY.md", path], GOOD_TEXT)
                self.assertEqual((result.tier, result.extra_flags), ("operator_only", ("safety_guard",)), path)

    def test_the_named_files_keep_their_other_flags(self):
        result = classify("blog", ["pipeline/source_registry.py", "pipeline/source_registry.json"], GOOD_TEXT)
        self.assertEqual((result.categories, result.extra_flags), (("provider_activation",), ("safety_guard",)))
        self.assertEqual(classify("blog", ["pipeline/merge_policy.py"]).extra_flags, ("policy_self",))                      # 이 정책의 파일은 policy_self 하나만 표시한다


class ClassifyTablesTest(unittest.TestCase):
    """표의 원소 하나하나가 혼자서도 걸리는지(R1) — 규칙 표(경로 이름·접미사·폴더·낱말·정규식 대안)를 시험에 글자 그대로 적어 두고 하나도 빠짐없이 순회한다.
    원소 하나를 지우는 변경은 해당 시료가 빨개진다. 패키징은 규칙마다 서로 겹치지 않는 시료를 쓴다(겹치면 한쪽을 지워도 다른 쪽이 가려 준다)."""

    DEPENDENCY_NAMES = ("requirements.txt", "requirements-dev.txt", "requirements.in", "requirements-dev.in", "constraints.txt", "constraints-dev.txt", "constraints.in", "constraints",
                        "package.json", "package-lock.json", "pnpm-lock.yaml", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "Pipfile.lock", "Gemfile", "Gemfile.lock", "poetry.lock",
                        "uv.lock", "yarn.lock", "a.lock", ".gitmodules", "environment.yml", "environment.yaml", "environment-dev.yml", "conda-env.yml", "conda.yml", "conda_requirements.txt",
                        "REQUIREMENTS.TXT", "Environment.YML", "dev-requirements.txt", "test-requirements.txt", "deps.txt", "pip-requirements.in", "my_requirements_x.txt", "deps-dev.in", "dependencies.txt",
                        "build_dependencies.in", "Dockerfile", "Makefile", "prod.Dockerfile", "Dockerfile.dev", "makefile", "GNUmakefile", "DEPS.TXT", "Test-Requirements.TXT")
    DEPENDENCY_FOLDERS = ("vendor", "node_modules", "requirements", "conda")
    CREDENTIAL_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".ppk", ".kdbx")
    CREDENTIAL_NAMES = (".env", ".env.example", ".env.local", ".netrc", ".npmrc", ".pypirc", "id_rsa", "id_rsa.pub", "id_dsa", "id_dsa.pub", "id_ecdsa", "id_ecdsa.pub", "id_ed25519", "id_ed25519.pub",
                        "token.json", "token-gmail.json", "service-account.json", "service_account.json", "serviceaccount.json", "my_service_account_key.json", "client_secret_1.json")
    CREDENTIAL_WORDS_IN_PATHS = ("secret", "credential", "keystore", "keyring")
    CREDENTIAL_TEXT = ("api key", "api_key", "api-key", "apikey", "API KEY", "secret", "password", "passwd", "credential", "private key", "private_key", "private-key", "privatekey", "access key",
                       "access_key", "access-key", "accesskey", "token", "비밀번호", "비밀 번호", "시크릿", "비밀 키", "API 키", "자격 증명", "자격증명", "인증 정보", "인증정보", "접근 키", "액세스 키",
                       "접근 토큰", "봇 토큰", "인증 토큰", "액세스 토큰")
    NOT_CREDENTIAL_TEXT = ("tokens", "tokenizer", "detokenize", "max_tokens", "keyboard", "sort_key", "passed", "비밀", "토큰들")
    DELETION_TEXT = ("drop table x", "DROP DATABASE x", "drop schema x", "DROP COLUMN c", "drop index i", "drop   table x", "delete from t", "TRUNCATE TABLE t", "rmtree(p)", "shutil.rmtree(p)",
                     "os.remove(p)", "os . remove (p)", "os.removedirs(p)", "os.rmdir(p)", "p.unlink()", "os.unlink(p)", "Path(x).unlink(missing_ok=True)", "unlink (p)", "rmdir(p)", "path.rmdir()",
                     "rm -rf data", "rm -r data", "rm -fr data", "rm -Rf data", "rm -f -r data", "마이그레이션 계획", "migrate()", "migrates", "migrated rows", "migrating", "migration", "migrations")
    NOT_DELETION_TEXT = ("items.remove(x)", "os.path.join(a, b)", "unlinked = 1", "rmdirs = 2", "rm file.txt", "rm -f file.txt", "dropdown", "drop tables", "drop_table", "delete_from_list", "promigrate",
                         "fingerprint", "format(x)", "remove(x)", "unlink", "rmdir")
    PUBLIC_ROOT = ("about.md", "contact.md", "privacy.md", "categories.md", "pages.json", "posts.json", "feed.xml", "robots.txt", "history.json", "blogger_history.json", "blogger_ko_history.json",
                   "naver_history.json", "README.md", "CNAME", ".nojekyll", "sitemap.xml", "favicon.ico", "humans.txt", "style.css", "404.html", "x.htm", "ABOUT.MD", "Feed.XML")
    PUBLIC_FOLDERS = ("_posts", "_blogger_drafts", "_blogger_ko_drafts", "_naver_drafts")
    ADS_NAMES = ("ads.txt", "app-ads.txt", "index.html", "_config.yml", "sub/ads.txt", "sub/index.html", "INDEX.HTML", "ADS.TXT")
    ADS_FOLDERS = ("_layouts", "_includes")
    PACKAGING_FILES = ("VERSION", "version.txt", "MANIFEST.in", "Version", "src/app/VERSION", "src/app/version.txt", "src/app/manifest.in")
    PACKAGING_SUFFIXES = (".spec", ".iss", ".nsi", ".wxs", ".wixproj", ".msix", ".msi", ".appxmanifest", ".manifest", ".rc")
    PACKAGING_FOLDERS = ("packaging", "installer", "installers", "package", "release", "releases", "dist", "build", "pyinstaller", "nsis", "msix", "wix")

    def codes(self, kind, path, text=""):
        result = classify(kind, [path], text)
        return result.categories, result.extra_flags

    def test_every_dependency_file_name_alone_is_enough(self):
        for name in self.DEPENDENCY_NAMES:
            for kind in ("blog", "desktop"):
                with self.subTest(name=name, kind=kind):
                    self.assertEqual(self.codes(kind, "pipeline/" + name)[0], ("dependencies",), name)
                    self.assertIn("dependencies", self.codes(kind, name)[0], name)

    def test_every_dependency_folder_alone_is_enough_at_any_depth(self):
        for folder in self.DEPENDENCY_FOLDERS:
            for path in (folder + "/a.txt", "pipeline/" + folder + "/a.txt", folder.upper() + "/a.txt", "a/b/" + folder + "/c/d.py"):
                for kind in ("blog", "desktop"):
                    with self.subTest(path=path, kind=kind):
                        self.assertEqual(self.codes(kind, path)[0], ("dependencies",), path)

    def test_names_that_only_look_like_dependency_files_are_not_flagged(self):
        for path in ("pipeline/requirement.txt", "pipeline/deps.py", "pipeline/deps.md", "pipeline/dependency.txt", "pipeline/docker.py", "pipeline/makes.py", "pipeline/requirements.md", "pipeline/requirements_notes.py", "pipeline/environment.md", "pipeline/environment.py", "pipeline/package.py", "pipeline/setup_tools.py",
                     "pipeline/pip_file_notes.md", "pipeline/gem_file.rb", "pipeline/lock.py", "pipeline/unlock.py.bak", "pipeline/condo.py", "docs/requirements.md",
                     "pipeline/vendors/a.py", "pipeline/node_module/a.js", "pipeline/requirement/a.py", "pipeline/conda_x/a.py"):
            with self.subTest(path=path):
                self.assertEqual(classify("desktop", [path]).tier, "ai_ok", path)

    def test_every_credential_file_suffix_and_name_alone_is_enough(self):
        for suffix in self.CREDENTIAL_SUFFIXES:
            for kind in ("blog", "desktop"):
                with self.subTest(suffix=suffix, kind=kind):
                    self.assertEqual(self.codes(kind, "pipeline/x" + suffix)[0], ("credentials",), suffix)
                    self.assertEqual(self.codes(kind, "pipeline/X" + suffix.upper())[0], ("credentials",), suffix)
        for name in self.CREDENTIAL_NAMES:
            for kind in ("blog", "desktop"):
                with self.subTest(name=name, kind=kind):
                    self.assertEqual(self.codes(kind, "pipeline/" + name)[0], ("credentials",), name)

    def test_every_credential_word_in_a_path_alone_is_enough(self):
        for word in self.CREDENTIAL_WORDS_IN_PATHS:
            for path in ("pipeline/my_" + word + "_x.py", "pipeline/" + word + ".txt", "pipeline/" + word + "/a.py", "pipeline/a/" + word.upper() + "x/b.py"):
                with self.subTest(path=path):
                    self.assertEqual(self.codes("blog", path)[0], ("credentials",), path)
        self.assertEqual(self.codes("blog", "pipeline/security/a.py")[0], ("credentials",))
        self.assertEqual(self.codes("blog", "pipeline/Security/a.py")[0], ("credentials",))

    def test_every_credential_word_in_a_changed_line_alone_is_enough(self):
        for text in self.CREDENTIAL_TEXT:
            for template in ("{}\n", "x = '{}'\n", "# {} 이야기", "my_{}_var = 1"):
                with self.subTest(text=text, template=template):
                    self.assertEqual(classify("blog", ["pipeline/x.py"], template.format(text)).categories, ("credentials",), text)
        for text in self.NOT_CREDENTIAL_TEXT:
            with self.subTest(clean=text):
                self.assertEqual(classify("blog", ["pipeline/x.py"], text + "\n").tier, "ai_ok", text)

    def test_every_deletion_word_alone_is_enough_and_the_look_alikes_are_not(self):
        for text in self.DELETION_TEXT:
            for template in ("{}\n", "x = '{}'\n", "# {}"):
                with self.subTest(text=text, template=template):
                    self.assertEqual(classify("blog", ["pipeline/x.py"], template.format(text)).categories, ("data_deletion_migration",), text)
        for text in self.NOT_DELETION_TEXT:
            with self.subTest(clean=text):
                self.assertEqual(classify("blog", ["pipeline/x.py"], text + "\n").tier, "ai_ok", text)

    def test_every_public_file_name_and_folder_alone_is_enough(self):
        for name in self.PUBLIC_ROOT:
            with self.subTest(name=name):
                self.assertIn("public_content", self.codes("blog", name)[0], name)
                self.assertEqual(self.codes("desktop", name), ((), ()), name)
        for folder in self.PUBLIC_FOLDERS:                                                 # 이 폴더 이름은 어느 깊이에 있든 공개 글이다(내부 폴더 안쪽도 — 기본 거부와 별개의 명시 규칙)
            for path in (folder + "/a.md", "sub/" + folder + "/a.md", folder.upper() + "/a.md", "pipeline/" + folder + "/a.md", "docs/" + folder + "/a.md", "tests/x/" + folder + "/a.md"):
                with self.subTest(path=path):
                    self.assertEqual(self.codes("blog", path)[0], ("public_content",), path)
                    self.assertEqual(self.codes("desktop", path), ((), ()), path)
        for path in ("assets/a.md", "ASSETS/a.md", "assets/css/a.css"):                      # assets 는 맨 위 폴더일 때만(안쪽 assets 는 사이트 파일이 아니다)
            with self.subTest(path=path):
                self.assertEqual(self.codes("blog", path)[0], ("public_content",), path)
        for path in ("pipeline/assets/a.md", "docs/assets/x.png", "tests/assets/a.json"):
            with self.subTest(path=path):
                self.assertEqual(self.codes("blog", path), ((), ()), path)
        for path in ("a.html", "a.htm", "A.HTM", "robots.html"):
            self.assertIn("public_content", self.codes("blog", path)[0], path)
        for path in ("pipeline/a.html", "docs/a.htm", "tests/fixtures/a.html"):
            self.assertEqual(self.codes("blog", path), ((), ()), path)                                 # 안쪽 폴더의 html 은 사이트 파일이 아니다

    def test_every_ad_surface_file_and_folder_alone_is_enough(self):
        for name in self.ADS_NAMES:
            with self.subTest(name=name):
                self.assertIn("ads", self.codes("blog", name)[0], name)
                self.assertEqual(self.codes("desktop", name), ((), ()), name)
        for folder in self.ADS_FOLDERS:
            for path in (folder + "/a.html", "x/" + folder + "/a.html", folder.upper() + "/a.html"):
                with self.subTest(path=path):
                    self.assertEqual(self.codes("blog", path)[0], ("ads",), path)

    def test_every_publish_settings_file_maps_to_exactly_its_items(self):
        for path, codes in (("pipeline/blogs.json", ("publish_mode", "auto_publish", "ads")), ("pipeline/source_registry.json", ("provider_activation",)),
                            ("pipeline/ops_inbox_policy.json", ("pipeline_pause", "publish_mode"))):
            with self.subTest(path=path):
                self.assertEqual(set(self.codes("blog", path)[0]), set(codes))
                self.assertEqual(self.codes("desktop", path)[0], ())

    def test_every_packaging_file_alone_is_enough(self):
        for path in self.PACKAGING_FILES:
            with self.subTest(path=path):
                self.assertEqual(self.codes("desktop", path), ((), ("packaging_release",)), path)
                self.assertNotIn("packaging_release", self.codes("blog", "pipeline/" + path.split("/")[-1])[1])

    def test_every_packaging_suffix_alone_is_enough(self):
        for suffix in self.PACKAGING_SUFFIXES:
            for path in ("src/app/x" + suffix, "src/app/X" + suffix.upper()):
                with self.subTest(path=path):
                    self.assertEqual(self.codes("desktop", path), ((), ("packaging_release",)), path)

    def test_every_packaging_folder_alone_is_enough(self):
        for folder in self.PACKAGING_FOLDERS:
            for path in ("src/" + folder + "/a.py", folder + "/a.py", "src/" + folder.upper() + "/a.py"):
                with self.subTest(path=path):
                    self.assertEqual(self.codes("desktop", path), ((), ("packaging_release",)), path)
        for path in ("src/packaged/a.py", "src/builder/a.py", "src/releases_x/a.py", "src/disto/a.py", "src/app/version.py", "src/app/versions.txt", "src/app/a.manifest.py", "src/app/a.rcx"):
            with self.subTest(clean=path):
                self.assertEqual(classify("desktop", [path]).tier, "ai_ok", path)

    def test_the_packaging_rules_are_only_for_the_application_repository(self):
        for path in self.PACKAGING_FILES[:3] + ("src/app/x.spec", "src/build/a.py"):
            self.assertNotIn("packaging_release", self.codes("blog", "pipeline/" + path.replace("/", "_"))[1], path)

    def test_the_workflow_folder_is_found_at_any_depth_and_any_case(self):
        for path in (".github/a", "sub/.github/a", ".GITHUB/a", "a/b/.GitHub/c/d.yml", ".github" + chr(92) + "a"):
            for kind in ("blog", "desktop"):
                with self.subTest(path=path, kind=kind):
                    self.assertEqual(self.codes(kind, path)[0], ("workflow",), path)
        self.assertEqual(classify("blog", ["pipeline/github/a.yml", "pipeline/.githubx/a.yml"]).tier, "ai_ok")

    def test_the_policy_files_are_matched_without_regard_to_case(self):
        for path in mp.POLICY_SELF_FILES:
            for variant in (path, path.upper(), path.lower(), "./" + path):
                with self.subTest(path=variant):
                    self.assertEqual(self.codes("desktop", variant), ((), ("policy_self",)), variant)
        self.assertEqual(classify("desktop", ["docs/AI_MERGE_POLICY.md.bak", "pipeline/merge_policy2.py", "tests/test_merge_policy_x.py", "sub/pipeline/merge_policy.py"]).tier, "operator_only")


class ClassifyExternalConnectionMoreTest(unittest.TestCase):
    """새 외부 접속 코드의 보완(S6) — 셸 스크립트의 따옴표 없는 명령·gopher 스킴·따옴표 안의 스킴 없는 주소·넓힌 최상위 도메인. 주소 글은 런타임에 조립한다."""

    CODE = "pipeline/fetcher.py"
    SHELL_PATHS = ("scripts/run.sh", "scripts/run.bash", "scripts/run.ps1", "scripts/run.bat", "scripts/run.cmd", "scripts/RUN.SH", "scripts/Run.Ps1", "scripts/sub/dir/x.CMD")
    SHELL_FLAGGED = ("git push origin main", "git push", "curl -s api", "curl", "wget -q x", "gh pr merge 5", "gh api x", "Invoke-WebRequest -Uri $u", "Invoke-RestMethod $u", "invoke-webrequest x",
                     "nc -z host 22", "ssh host ls", "scp a b:/c", "sftp host", "rsync -a a b", "telnet host", "nslookup host", "ncat -l 1", "netcat host 1", "iwr $u", "irm $u",
                     "Start-BitsTransfer -Source $u", "bitsadmin /transfer x", "git pull", "git fetch --all", "git clone repo", "git submodule update", "git remote add o x",
                     "if x; then curl y; fi", "x && wget y", "FOO=1 ssh h", "/usr/bin/curl y", "(curl y)", "echo hi | nc h 1", "GIT PUSH", "Curl x")
    SHELL_CLEAN = ("echo curly", "pycurl", "ssh-keygen -t ed25519", "echo ghost", "git status", "git log -1", "git diff", "git commit -m x", "git add .", "ncurses", "sync", "echo nc_value",
                   "echo my-curl", "echo a.curl", "git pushd", "echo irmx", "echo gh_x")

    def external(self, text, path=None, kind="blog"):
        result = classify(kind, [path or self.CODE], text)
        self.assertEqual(result.tier, "operator_only", text)
        self.assertIn("external_connection", result.extra_flags, text)
        return result

    def clean(self, text, path=None, kind="blog"):
        result = classify(kind, [path or self.CODE], text)
        self.assertEqual((result.tier, result.categories, result.extra_flags), ("ai_ok", (), ()), (text, result.reasons))

    def test_unquoted_network_commands_are_flagged_in_shell_scripts(self):
        for path in self.SHELL_PATHS:
            for line in self.SHELL_FLAGGED:
                with self.subTest(path=path, line=line):
                    result = self.external(line + "\n", path=path)
                    self.assertTrue(any("셸 스크립트에 네트워크 명령이 있습니다" in reason for reason in result.reasons), result.reasons)

    def test_shell_look_alikes_are_not_flagged(self):
        for path in self.SHELL_PATHS:
            for line in self.SHELL_CLEAN:
                with self.subTest(path=path, line=line):
                    self.clean(line + "\n", path=path)

    def test_the_same_unquoted_words_are_not_flagged_outside_shell_files(self):
        for path in ("pipeline/run.py", "scripts/run.json", "scripts/run.js", "scripts/run.yml", "scripts/run.html", "scripts/runsh", "scripts/run.sh.py", "scripts/run.shx", "scripts/sh"):
            for line in self.SHELL_FLAGGED:
                with self.subTest(path=path, line=line):
                    self.assertNotIn("셸 스크립트", " ".join(classify("blog", [path], line + "\n").reasons))

    def test_a_shell_text_for_several_files_is_checked_when_one_of_them_is_a_shell_script(self):
        text = "curl x\n"
        self.assertEqual(classify("blog", ["pipeline/a.py"], text).tier, "ai_ok")
        self.assertIn("external_connection", classify("blog", ["pipeline/a.py", "scripts/run.sh"], text).extra_flags)
        self.assertEqual(classify("blog", ["docs/a.md", "tests/test_a.py"], text).tier, "ai_ok")                       # 시험·문서만 바뀌면 건너뛴다
        self.assertIn("external_connection", classify("blog", ["scripts/run.sh", "docs/a.md"], {"scripts/run.sh": text, "docs/a.md": "x"}).extra_flags)
        self.assertEqual(classify("blog", ["scripts/run.sh", "docs/a.md"], {"scripts/run.sh": "echo hi\n", "docs/a.md": text}).tier, "ai_ok")              # 문서의 글은 보지 않는다

    REQUESTS_METHODS = ("get", "post", "put", "delete", "patch", "head", "options", "request", "Session", "session")
    GIT_SUBCOMMANDS = ("push", "pull", "fetch", "clone", "submodule", "remote")

    def test_every_requests_method_alone_is_enough(self):
        for name in self.REQUESTS_METHODS:
            for template in ("r = requests.{}(address)\n", "r = requests . {} (address)\n", "x = requests.{}()\n"):
                with self.subTest(name=name, template=template):
                    self.external(template.format(name))
        for text in ("requests.getx(a)", "my_requests.get(a)", "requests.get_all(a)", "requests.gets(a)", "requests.GET(a)", "requests.get", "xrequests.post(a)", "requests.sessions(a)"):
            with self.subTest(clean=text):
                self.clean(text + "\n")

    def test_every_quoted_git_subcommand_and_the_gh_forms_are_flagged(self):
        for name in self.GIT_SUBCOMMANDS:
            for template in ("cmd = ['git', '{}']\n", "cmd = 'git {} origin'\n", 'cmd = "git -C x {}"\n', "cmd = ['git', '-C', 'x', '{}', 'origin']\n"):
                with self.subTest(name=name, template=template):
                    self.external(template.format(name))
        for text in ("cmd = 'gh api x'\n", "cmd = 'gh'\n", "cmd = ['gh', 'pr']\n", 'cmd = "gh issue list"\n', "cmd = `gh run`\n", "cmd = ['git', 'ls-remote', a]\n"):
            with self.subTest(text=text):
                self.external(text)
        for text in ("cmd = ['git', 'status']\n", "cmd = ['git', 'log', '-1']\n", "cmd = 'ghost run'\n", "cmd = 'gh_x'\n", "cmd = ['git']\n", "cmd = 'github'\n"):
            with self.subTest(clean=text):
                self.clean(text)

    def test_gopher_is_an_external_scheme_too(self):
        self.assertIn("gopher", mp.EXTERNAL_SCHEMES)
        for scheme in ("gopher", "GOPHER", "Gopher"):
            with self.subTest(scheme=scheme):
                self.external("u = '" + url("host.org/x", scheme) + "'\n")
        self.clean("u = '" + url("example.com/x", "gopher") + "'\n")                                                      # 예시 주소는 걸리지 않는다

    def test_a_quoted_address_without_a_scheme_is_flagged(self):
        for text in ('src="//evil.com/x.js"', "u = '//evil.ru/x'", "`//cdn.service.io/lib.js`", "'//a.b.co.uk/p?q=1#f'", '"//evil.com:8443/x"', "'//EVIL.COM'", "x = '//evil.de'", "'//svc.provider.xyz/a'"):
            with self.subTest(text=text):
                self.external(text + "\n")
                self.external(text + "\n", path="scripts/ui/page.html")
        for text in ("'//example.com/x'", "'//a.example.org'", "'// comment text'", "'//localhost/x'", "'//x.py'", "'//README.md'", "'//a.b.c'", "'//path/to/file'", "'//'", "'///'", "'//x.test'", "// evil.com",
                     "//evil.com", "'/ /evil.com'", "'x//evil.com'", "'//evil'", "'//a.db'"):
            with self.subTest(clean=text):
                self.clean(text + "\n")

    def test_every_host_domain_alone_is_enough(self):
        self.assertEqual(len(mp.HOST_TLDS), 262)
        for tld in sorted(mp.HOST_TLDS):
            with self.subTest(tld=tld):
                self.external("host = 'svc.provider." + tld + "'\n")
                self.external("host = '//svc.provider." + tld + "/x.js'\n")
                self.external("host = \"" + "SVC.PROVIDER." + tld.upper() + ":8443/path\"\n")

    def test_file_name_domains_are_not_hosts_unless_they_carry_a_scheme(self):
        for tld in mp.FILE_NAME_TLDS:
            with self.subTest(tld=tld):
                self.clean("name = 'run." + tld + "'\n")
                self.clean("name = 'svc.provider." + tld + "'\n")
                self.clean("name = '//svc.provider." + tld + "/x'\n")
                self.external("u = '" + url("svc.provider." + tld) + "'\n")

    def test_dotted_names_that_are_not_hosts_stay_clean(self):
        for name in ("os.path", "self.name", "cache.db", "app.js", "x.ts", "x.json", "user.name", "core.editor", "x.yml", "pipeline.notify", "module.attr", "a.b.c", "x.com.py", "report.org.txt",
                     "file.name.txt", "index.html", "setup.py", "README.md", "run.sh", "x.rs", "a.pl", "a.so", "a.cc", "a.ps", "a.pm", "a.ml", "my.example", "a.test", "x.invalid", "a.zip", "a.mov"):
            with self.subTest(name=name):
                self.clean("name = '" + name + "'\n")
                self.clean("name = " + name + "\n")
        for text in ("os.path.join(a, b)", "self.name = 1", "value = obj.attr.name", "x = a.b.c.d"):
            with self.subTest(text=text):
                self.clean(text + "\n")

    def test_the_reasons_name_the_hosts_but_never_echo_the_line(self):
        result = self.external("x = '//svc.provider.ru/a.js'\ny = 'svc.other.kr'\n")
        joined = " ".join(result.reasons)
        for word in ("svc.provider.ru", "svc.other.kr", "새 호스트 주소"):
            self.assertIn(word, joined)
        self.assertNotIn("x = ", joined)


class ClassifySecretShapesTest(unittest.TestCase):
    """비밀 모양의 보완(I3·I4) — Authorization Bearer 헤더(코드에서), Stripe 형식 키, 긴 Bearer 값(문서에서도)."""

    def categories(self, text, path="pipeline/x.py"):
        return classify("blog", [path], text).categories

    def test_an_authorization_bearer_header_in_code_is_a_credential(self):
        for text in ('h = {"Authorization": "Bearer " + v}', "Authorization: Bearer abc", "authorization = 'bearer x'", "AUTHORIZATION:  BEARER", "headers['Authorization'] = f'Bearer {t}'",
                     'curl -H "Authorization: Bearer $X"', "Authorization,Bearer", "authorization bearer"):
            with self.subTest(text=text):
                result = classify("blog", ["pipeline/x.py"], text + "\n")
                self.assertEqual(result.categories, ("credentials",), text)
                self.assertTrue(any("Authorization Bearer 인증 헤더가 있습니다" in reason for reason in result.reasons), result.reasons)

    def test_the_header_needs_both_words_close_together_as_whole_words(self):
        for text in ("Authorization is required", "bearer instrument", "auth_bearer = 1", "authorizationbearer", "xauthorization bearer", "authorization bearerx", "authorization " + "." * 25 + "bearer",
                     "authorization\nbearer", "Bearer", "authorization"):
            with self.subTest(text=text):
                self.assertEqual(classify("blog", ["pipeline/x.py"], text + "\n").tier, "ai_ok", text)
        self.assertEqual(self.categories("authorization" + "." * 24 + "bearer"), ("credentials",))
        self.assertEqual(self.categories("authorization" + "." * 24 + "bearer", path="docs/a.md"), ())                         # 문서에서는 낱말 규칙이라 걸리지 않는다

    def test_a_stripe_style_key_is_a_credential_everywhere(self):
        for prefix in ("sk_live_", "sk_test_", "rk_live_", "rk_test_"):
            value = prefix + "CANARY" + "a" * 18
            for path in ("pipeline/x.py", "docs/a.md", "pipeline/x.json", "pipeline/x.txt"):
                with self.subTest(prefix=prefix, path=path):
                    result = classify("blog", [path], "k = '" + value + "'\n")
                    self.assertEqual(result.categories, ("credentials",), (prefix, path))
                    self.assertNotIn(value, " ".join(result.reasons))
        for text in ("sk_live_" + "a" * 8, "k=sk_test_" + "A1" * 4):
            self.assertEqual(self.categories(text, path="docs/a.md"), ("credentials",), text)
        for text in ("sk_live_" + "a" * 7, "pk_live_" + "a" * 24, "task_live_" + "a" * 24, "sk_prod_" + "a" * 24, "sk_live" + "a" * 24, "sk-live_" + "a" * 24, "sk_live_ " + "a" * 24, "_sk_live_" + "a" * 24):
            with self.subTest(clean=text):
                self.assertEqual(classify("blog", ["pipeline/x.py"], text + "\n").tier, "ai_ok", text)

    def test_a_long_bearer_value_is_a_credential_everywhere_and_a_short_one_is_not(self):
        for path in ("pipeline/x.py", "docs/a.md", "docs/a.txt"):
            with self.subTest(path=path):
                self.assertEqual(self.categories("Bearer " + "a" * 20, path=path), ("credentials",))
                self.assertEqual(self.categories("bearer" + chr(9) + ("A.b_c-d" + chr(126) + "e+f/g=") * 3, path=path), ("credentials",))
                self.assertEqual(self.categories("Bearer " + "a" * 19, path=path), ())
        self.assertEqual(self.categories("xBearer " + "a" * 30), ())                                                            # 단어가 이어진 것은 걸리지 않는다
        self.assertEqual(self.categories("_bearer " + "a" * 30), ())
        self.assertEqual(self.categories("Bearer " + "가" * 30), ())


class ApprovalRecordTest(unittest.TestCase):
    """승인 기록(S5) — 쉬운 설명을 보냈을 때의 머리 커밋과 승인 글이 도착했을 때의 머리 커밋이 다르면 승인은 무효다."""

    def record(self, **changes):
        values = dict(number="M075", pr_number=198, explained_head_sha=SHA_A, head_sha_at_approval=SHA_A)
        values.update(changes)
        return mp.ApprovalRecord(**values)

    def test_equal_heads_make_a_valid_record(self):
        record = self.record()
        self.assertEqual(record.problems(), [])
        self.assertTrue(record.valid)
        self.assertTrue(self.record(explained_head_sha=SHA_A.replace("1", "a"), head_sha_at_approval=SHA_A.upper().replace("1", "A")).valid)
        self.assertTrue(self.record(number="M1000", pr_number=1).valid)

    def test_a_head_that_changed_between_the_explanation_and_the_approval_text_invalidates_it(self):
        record = self.record(head_sha_at_approval=SHA_B)
        self.assertFalse(record.valid)
        problems = record.problems()
        self.assertEqual(len(problems), 1)
        for word in ("승인 글이 도착하기 전에 머리 커밋이 바뀌었습니다", "1111111", "2222222", "새 설명과 새 승인"):
            self.assertIn(word, problems[0])
        self.assertFalse(self.record(explained_head_sha=SHA_B).valid)

    def test_malformed_values_make_it_invalid(self):
        for changes, word in (({"number": "M75"}, "승인 번호"), ({"number": "m075"}, "승인 번호"), ({"number": None}, "승인 번호"), ({"number": 75}, "승인 번호"), ({"pr_number": 0}, "PR 번호"),
                              ({"pr_number": True}, "PR 번호"), ({"pr_number": "198"}, "PR 번호"), ({"pr_number": None}, "PR 번호"), ({"explained_head_sha": "abc1234"}, "40자 해시"),
                              ({"head_sha_at_approval": None}, "40자 해시"), ({"explained_head_sha": SHA_A + "0"}, "40자 해시"), ({"head_sha_at_approval": "g" * 40}, "40자 해시"),
                              ({"explained_head_sha": 5, "head_sha_at_approval": 5}, "40자 해시")):
            with self.subTest(changes=changes):
                record = self.record(**changes)
                self.assertFalse(record.valid)
                self.assertTrue(any(word in problem for problem in record.problems()), record.problems())

    def test_several_problems_are_listed_together(self):
        record = self.record(number="M75", pr_number=0, head_sha_at_approval=SHA_B)
        self.assertEqual(len(record.problems()), 3)

    def test_the_record_is_immutable_and_compares_by_value(self):
        record = self.record()
        with self.assertRaises(Exception):
            record.number = "M076"
        self.assertEqual(record, self.record())
        self.assertNotEqual(record, self.record(head_sha_at_approval=SHA_B))

    def test_the_record_and_the_precondition_facts_agree_about_the_heads(self):
        """같은 값으로 기록을 만들면 재확인 조건 2 도 같은 결론이다."""
        for arrived, expected in ((SHA_A, True), (SHA_B, False)):
            record = self.record(head_sha_at_approval=arrived)
            facts = good_facts()
            facts["approved_head_sha"], facts["head_sha_at_approval"] = record.explained_head_sha, record.head_sha_at_approval
            self.assertEqual(record.valid, expected)
            self.assertEqual(mp.check_preconditions(facts).ok, expected)


class PostMergeTest(unittest.TestCase):
    """병합 뒤 main 검사에 따른 다음 행동(S8, 문서 §9-4) — 실패하면 추가 병합을 하지 않고 되돌리기 요청과 쉬운 원인 설명만 보낸다."""

    def test_a_green_main_check_or_a_first_merge_has_no_restriction(self):
        for state in ("success", "none"):
            decision = mp.evaluate_post_merge(state)
            self.assertEqual((decision.state, decision.may_merge_next, decision.only_actions), (state, True, None))
            self.assertIn("제한이 없습니다", decision.reason)

    def test_a_red_main_check_allows_only_a_revert_request_and_an_easy_cause_explanation(self):
        decision = mp.evaluate_post_merge("failure")
        self.assertEqual((decision.state, decision.may_merge_next), ("failure", False))
        self.assertEqual(decision.only_actions, ("send_revert_request", "send_cause_explanation"))
        self.assertEqual(decision.only_actions, mp.POST_MERGE_REVERT_ACTIONS)
        for word in ("추가 병합을 하지 않고", "되돌리기 요청", "쉬운 원인 설명"):
            self.assertIn(word, decision.reason)

    def test_an_unfinished_main_check_waits_and_does_nothing(self):
        decision = mp.evaluate_post_merge("pending")
        self.assertEqual((decision.state, decision.may_merge_next, decision.only_actions), ("pending", False, ()))
        self.assertIn("기다립니다", decision.reason)

    def test_an_unknown_state_refuses_the_merge_and_sends_nothing(self):
        class Spoof(str):
            def __eq__(self, other):
                return True

            def __hash__(self):
                return hash("success")

        for value in ("", "SUCCESS", "Success", "Failure", "passed", "ok", " success", "success ", None, 5, True, False, [], ("success",), {"success"}, object(), b"success", Spoof("success"), Spoof("none")):
            with self.subTest(value=repr(value)):
                decision = mp.evaluate_post_merge(value)
                self.assertEqual((decision.state, decision.may_merge_next, decision.only_actions), (None, False, ()))
                self.assertIn("알 수 없습니다", decision.reason)

    def test_only_the_green_and_first_states_ever_allow_the_next_merge(self):
        allowed = [state for state in mp.POST_MERGE_STATES if mp.evaluate_post_merge(state).may_merge_next]
        self.assertEqual(allowed, ["success", "none"])
        for state in mp.POST_MERGE_STATES:
            decision = mp.evaluate_post_merge(state)
            if not decision.may_merge_next:
                self.assertTrue(set(decision.only_actions) <= set(mp.POST_MERGE_REVERT_ACTIONS))

    def test_the_result_is_immutable(self):
        decision = mp.evaluate_post_merge("failure")
        with self.assertRaises(Exception):
            decision.may_merge_next = True


class StrSubclassTest(unittest.TestCase):
    """비교를 바꿔치는 str 하위 형식은 어느 입구에서도 받지 않는다(I2) — 승인 글·병합 번호·병합 방식·머리 커밋."""

    class Evil(str):
        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

        def __hash__(self):
            return hash("x")

        def strip(self, *args):
            return "M075 승인"

        def lower(self):
            return "1" * 40

    def test_an_approval_text_must_be_a_plain_str(self):
        for text in (self.Evil("확인했습니다"), self.Evil("M075 승인"), self.Evil("")):
            with self.subTest(text=str.__repr__(text)):
                result = mp.check_approval_text(text)
                self.assertEqual((result.number, result.reason), (None, "empty"))
                self.assertIn("M075 승인", result.guidance)
                self.assertIsNone(mp.parse_approval(text))

    def test_a_plain_subclass_is_refused_too_even_when_it_behaves(self):
        class Text(str):
            pass

        self.assertIsNone(mp.parse_approval(Text("M075 승인")))
        self.assertEqual(mp.parse_approval(str(Text("M075 승인"))), "M075")

    class EvilInt(int):
        """양수·0 이상·같음을 거짓으로 꾸미는 int 하위 형식."""

        def __gt__(self, other):
            return True

        def __ge__(self, other):
            return True

        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

        def __hash__(self):
            return 1

    def test_numbers_must_be_exact_ints(self):
        """PR 번호·발견 수·남은 지적 수는 정확히 int 만 받는다 — 비교를 바꿔치는 int 하위 형식은 거절한다(I-N3, bool 거절 흐름은 그대로)."""
        for value in (self.EvilInt(-5), self.EvilInt(0), self.EvilInt(7)):
            with self.subTest(value=int(value)):
                ledger = mp.ApprovalLedger()
                self.assertFalse(ledger.consume("M075", value).ok)
                self.assertEqual(ledger.consumed_numbers, ())
                self.assertFalse(mp.ApprovalRecord("M075", value, SHA_A, SHA_A).valid)
                with self.assertRaises(ValueError):
                    mp.render_completion_notice("M075", value, "d" * 40, "초안 저장이 반영되었습니다.", "전체 통과", "이상 없음", "해당 병합 커밋 한 개를 되돌립니다.")
                with self.assertRaises(ValueError):
                    mp.render_explanation("M075", value, "c" * 40, ["pipeline/a.py"], *ANSWERS, classification=classify("blog", ["pipeline/a.py"], GOOD_TEXT))
                facts = good_facts()
                facts["approved_pr_number"] = facts["pr_number"] = value
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("number_match",))
                self.assertIn("양의 정수", verdict.failures[0].reason)
                facts = good_facts()
                facts["secret_findings"] = value                                                       # 발견 수가 0 이라고 우기는 하위 형식
                self.assertEqual(mp.check_preconditions(facts).failed_codes, ("no_secret_exposure",))
                facts = good_facts()
                facts["independent_verification"] = dict(facts["independent_verification"], open_required_findings=value)
                self.assertEqual(mp.check_preconditions(facts).failed_codes, ("independent_verified",))
        for value in (True, False, 1.0, "1", None):
            self.assertFalse(mp.ApprovalLedger().consume("M075", value).ok, repr(value))
        self.assertTrue(mp.ApprovalLedger().consume("M075", 198).ok)

    def test_the_repository_kind_must_be_a_plain_str(self):
        class Kind(str):
            pass

        for kind in (Kind("blog"), Kind("desktop"), self.Evil("blog"), self.Evil("desktop")):
            with self.subTest(kind=str.__repr__(kind)):
                result = mp.classify_change(kind, ["pipeline/a.py"], "", dict(DECLARED_OK))
                self.assertEqual((result.tier, "invalid_input" in result.extra_flags), ("operator_only", True))
                facts = good_facts()
                facts["repo_kind"] = kind
                self.assertEqual(mp.check_preconditions(facts).failed_codes, ("scope_matches",))
        self.assertEqual(mp.classify_change(str(Kind("blog")), ["pipeline/a.py"], "", dict(DECLARED_OK)).tier, "ai_ok")

    def test_the_merge_method_must_be_a_plain_str(self):
        for method in (self.Evil("push_main"), self.Evil("pr_merge"), self.Evil("force_push")):
            self.assertFalse(mp.merge_method_allowed(method))
        self.assertTrue(mp.merge_method_allowed("pr_merge"))

    def test_the_pull_request_state_must_be_a_plain_str(self):
        """R1(T3 — K38·TY06·AU0459): pr_state 는 정확히 str 만 받는다 — 비교를 바꿔치는 하위 형식(Evil)도 얌전한 하위 형식(Plain)도 열린 PR 로 통과하지 못한다(재확인 조건 1)."""
        class Plain(str):
            pass

        for value in (self.Evil("closed"), self.Evil("open"), self.Evil("merged"), Plain("open"), Plain("closed")):
            with self.subTest(value=str.__repr__(value)):
                facts = good_facts()
                facts["pr_state"] = value
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("number_match",))
                self.assertIn("PR 상태를 알 수 없습니다", verdict.failures[0].reason)
        facts = good_facts()
        facts["pr_state"] = str(Plain("open"))                                                                       # 같은 글자를 정확한 str 로 바꾸면 통과한다
        self.assertTrue(mp.check_preconditions(facts).ok)

    def test_trees_paths_and_the_main_check_state_must_be_plain_strs(self):
        """P5 정보 3(§5-4): 문서가 일반 글자(str)만 받는다고 적은 값 중 트리 해시·경로·main 검사 결과도 하위 형식(비교를 바꿔치는 것이든 얌전한 것이든)을 받지 않는다."""
        class Plain(str):
            pass

        for tree in (self.Evil(TREE_A), Plain(TREE_A)):
            with self.subTest(tree=str.__repr__(tree)):
                facts = good_facts()
                facts["current_tree"] = tree
                self.assertEqual(mp.check_preconditions(facts).failed_codes, ("independent_verified",))
                facts = good_facts()
                facts["independent_verification"] = dict(facts["independent_verification"], verified_tree=tree)
                self.assertEqual(mp.check_preconditions(facts).failed_codes, ("independent_verified",))
        for state in (self.Evil("success"), Plain("success"), Plain("none")):
            with self.subTest(state=str.__repr__(state)):
                decision = mp.evaluate_post_merge(state)
                self.assertEqual((decision.state, decision.may_merge_next), (None, False))
                facts = good_facts()
                facts["previous_merge_main_check"] = state
                self.assertEqual(mp.check_preconditions(facts).failed_codes, ("checks_pass",))
        self.assertTrue(mp.evaluate_post_merge(str(Plain("success"))).may_merge_next)                 # 같은 글자를 정확한 str 로 바꾸면 통과한다
        for path in (self.Evil("pipeline/a.py"), Plain("pipeline/a.py")):
            with self.subTest(path=str.__repr__(path)):
                self.assertIsNone(mp.normalize_repo_path(path))
        self.assertEqual(mp.normalize_repo_path(str(Plain("pipeline/a.py"))), "pipeline/a.py")

    def test_numbers_and_heads_must_be_plain_strs(self):
        evil = self.Evil("M076")
        self.assertFalse(mp.approval_matches(evil, "M075"))
        self.assertFalse(mp.approval_matches("M075", evil))
        self.assertFalse(mp.approval_matches(self.Evil("M075"), self.Evil("M075")))
        self.assertIsNone(mp.pr_title_label(self.Evil("[M075] x")))
        self.assertEqual(mp.pr_title_label(str(self.Evil("[M075] x"))), "M075")
        paths = ["pipeline/a.py"]
        self.assertFalse(mp.approval_still_valid(self.Evil("1" * 40), SHA_B, paths, paths))
        self.assertFalse(mp.approval_still_valid(SHA_A, self.Evil("2" * 40), paths, paths))
        ledger = mp.ApprovalLedger()
        self.assertFalse(ledger.consume(self.Evil("M075"), 198).ok)
        self.assertEqual(ledger.consumed_numbers, ())
        facts = good_facts()
        facts["approved_number"] = self.Evil("M075")
        self.assertEqual(mp.check_preconditions(facts).failed_codes, ("number_match",))
        facts = good_facts()
        facts["approved_head_sha"] = self.Evil("1" * 40)
        self.assertEqual(mp.check_preconditions(facts).failed_codes, ("no_new_commit",))


class PolicyStoryTest(unittest.TestCase):
    """운영자 확인 016 의 예(M075)가 처음부터 끝까지 이어지는지 — 설명 → 승인 → 재확인 → 완료 알림 → 시험."""

    def test_the_whole_flow_for_one_pr(self):
        paths = ["pipeline/drafts.py", "tests/test_drafts.py"]
        explanation = make_text(paths=paths)
        self.assertEqual(mp.explanation_problems(explanation, pr_title="[M075] 초안 저장 기능"), [])
        number = mp.parse_approval("M075 승인")
        self.assertEqual(number, "M075")
        label = mp.pr_title_label("[M075] 초안 저장 기능")
        self.assertTrue(mp.approval_matches(number, label))
        ledger = mp.ApprovalLedger()
        facts = good_facts()
        facts.update({"approved_number": number, "pr_title_label": label, "approved_paths": list(paths), "current_paths": list(paths),
                      "classification": classify("blog", paths, GOOD_TEXT), "consumed_numbers": list(ledger.consumed_numbers)})
        verdict = mp.check_preconditions(facts)
        self.assertTrue(verdict.ok, verdict.explain())
        self.assertTrue(mp.approval_still_valid(SHA_A, SHA_A, paths, paths))
        self.assertTrue(mp.merge_method_allowed("pr_merge"))
        self.assertTrue(ledger.consume(number, 198).ok)
        self.assertEqual(mp.completion_notice_problems(make_notice()), [])
        self.assertEqual(mp.evaluate_trial([record("M075")]), "pending")
        approval = mp.ApprovalRecord(number, 198, SHA_A, SHA_A)                                    # 승인 글이 도착한 순간의 기록
        self.assertTrue(approval.valid)
        self.assertTrue(mp.evaluate_post_merge("none").may_merge_next)                            # 첫 병합은 직전 main 검사가 없다
        self.assertTrue(mp.evaluate_post_merge("success").may_merge_next)

    def test_a_red_main_check_after_a_merge_stops_the_next_merge_and_allows_only_a_revert_request(self):
        facts = good_facts()
        facts["previous_merge_main_check"] = "failure"
        verdict = mp.check_preconditions(facts)
        self.assertEqual(verdict.failed_codes, ("checks_pass",))
        decision = mp.evaluate_post_merge("failure")
        self.assertFalse(decision.may_merge_next)
        self.assertEqual(decision.only_actions, mp.POST_MERGE_REVERT_ACTIONS)

    def test_a_documentation_only_change_that_mentions_the_watched_words_goes_through_the_whole_flow(self):
        """작업 기록처럼 PIPELINE_PAUSE·키·토큰 이야기가 든 문서만 바꾸는 변경은 분류·설명·재확인을 모두 통과한다 — 운영자 원문이 AI 병합 범위에 '문서' 를 명시했다."""
        paths = ["인수인계/작업내용.md", "docs/GLOSSARY.md"]
        text = {path: "- PIPELINE_PAUSE 는 그대로 두었고 API 키와 토큰은 건드리지 않았습니다.\n" for path in paths}
        classification = classify("blog", paths, text)
        self.assertEqual((classification.tier, classification.categories, classification.extra_flags), ("ai_ok", (), ()))
        self.assertEqual(mp.explanation_problems(make_text(paths=paths, classification=classification), pr_title="[M075] 작업 기록"), [])
        facts = good_facts()
        facts.update({"approved_paths": list(paths), "current_paths": list(paths), "classification": classification, "changed_text": text})
        verdict = mp.check_preconditions(facts)
        self.assertTrue(verdict.ok, verdict.explain())
        facts["changed_text"] = {path: "- 토큰 이야기\n" + FAKE_SECRETS["google"] + "\n" for path in paths}                  # 같은 문서라도 실제 비밀 모양이 들어오면 다시 계산한 분류가 막는다
        self.assertEqual(mp.check_preconditions(facts).failed_codes, ("scope_matches",))

    def test_a_late_commit_a_wrong_number_or_a_reused_approval_each_stop_the_merge(self):
        facts = good_facts()
        facts["current_head_sha"] = SHA_B
        self.assertFalse(mp.check_preconditions(facts).ok)
        self.assertIsNone(mp.parse_approval("확인했습니다"))
        facts = good_facts()
        facts["pr_title_label"] = "M076"
        self.assertFalse(mp.check_preconditions(facts).ok)
        ledger = mp.ApprovalLedger([("M075", 198)])
        facts = good_facts()
        facts["consumed_numbers"] = list(ledger.consumed_numbers)
        self.assertFalse(mp.check_preconditions(facts).ok)


if __name__ == "__main__":
    unittest.main()
