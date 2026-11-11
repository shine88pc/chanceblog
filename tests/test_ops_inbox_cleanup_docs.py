"""확인 필요 모음 정리(2026-11-11)의 문서 시험 — `docs/OPS_INBOX.md` §10·규칙표 갱신·`docs/DEFECT_REGISTER.md` D-270–D-279·정책 파일이 코드의 실제 이름·값·표와 어긋나지 않는지.
문서의 글이 옳은지는 시험이 알 수 없어 사람이 본다. 여기서는 숫자·이름·표·링크·문서 규칙(물결표·http 주소·Liquid 없음)과 '코드가 만드는 항목 id 가 문서에 있는가'를 본다.
"""
import json
import re
import unittest
from datetime import datetime, timedelta, timezone

import _bootstrap
import ops_inbox_helpers as h
import ops_inbox as oi
from pipeline import inbox
from pipeline import inbox_policy as ip

ROOT = _bootstrap.ROOT
DOC = (ROOT / "docs" / "OPS_INBOX.md").read_text(encoding="utf-8")
REGISTER = (ROOT / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8")
POLICY = json.loads((ROOT / ip.POLICY_FILE).read_text(encoding="utf-8"))
MY_DEFECTS = tuple(f"D-{n}" for n in range(270, 290))        # 이 묶음의 번호 대역(전체 최댓값은 못박지 않는다) — D-270–D-279 는 처음 구현, D-280–D-289 는 독립 검증 뒤 고침


def section(number):
    """`### 10-n.` 소절의 글."""
    start = DOC.index(f"### 10-{number}. ")
    nxt = re.search(r"^###? ", DOC[start + 5:], re.M)
    return DOC[start:start + 5 + nxt.start()] if nxt else DOC[start:]


SECTION_10 = DOC[DOC.index("## 10. 오래된 항목과 의도된 정지 정리"):]


class SectionShapeTest(unittest.TestCase):
    def test_section_ten_has_the_eleven_subsections_in_order(self):
        heads = re.findall(r"^### (10-\d+)\. (.+)$", SECTION_10, re.M)
        self.assertEqual([number for number, _title in heads], [f"10-{n}" for n in range(1, 12)])
        self.assertEqual(DOC.count("## 10. 오래된 항목과 의도된 정지 정리 (2026-11-11, 결함 D-270–D-289)"), 1)
        self.assertEqual(DOC.count("\n## 10. "), 1)

    def test_the_new_text_follows_the_document_rules(self):
        self.assertNotIn(chr(126), SECTION_10)
        self.assertIsNone(re.search(r"https?://", SECTION_10))
        self.assertNotIn("{{", SECTION_10)
        self.assertNotIn("{%", SECTION_10)
        self.assertNotRegex(SECTION_10, r"[A-Za-z]:[/\\]")                    # 로컬 경로 없음
        for rel in re.findall(r"\]\((\.\./[^)#]+)\)", SECTION_10):
            self.assertTrue((ROOT / "docs" / rel).resolve().exists(), rel)

    def test_the_tables_of_section_ten_have_equal_columns(self):
        for block in re.findall(r"((?:^\|.*\|\n)+)", SECTION_10, re.M):
            counts = {line.count("|") for line in block.splitlines()}
            self.assertEqual(len(counts), 1, block[:80])

    def test_the_seven_requirements_table_names_a_test_class_that_exists(self):
        names = re.findall(r"`([A-Za-z]+Test)`", section(1))
        self.assertGreaterEqual(len(names), 8)
        sources = "\n".join((ROOT / "tests" / name).read_text(encoding="utf-8") for name in
                            ("test_ops_inbox_cleanup.py", "test_ops_inbox_cleanup_script.py", "test_ops_inbox_policy.py"))
        for name in names:
            self.assertIn(f"class {name}(", sources, name)


class NumbersAndNamesTest(unittest.TestCase):
    def test_the_limits_in_the_guide_are_the_constants(self):
        self.assertIn(f"최대 {oi.MAX_APPROVAL_LOOKUPS}가지, `MAX_APPROVAL_LOOKUPS`", section(2))
        self.assertIn(f"`SEASON_GRACE_DAYS`={ip.SEASON_GRACE_DAYS}일", section(6))
        self.assertIn(f"최대 {ip.MAX_DECISIONS}개", section(7))
        self.assertIn(f"1–{ip.MAX_RESUME_CONDITIONS}개", section(7))
        for value in (ip.REASON_MAX, ip.REF_MAX, ip.CONDITION_MAX, ip.DECISION_REASON_MAX, ip.DOC_MAX):
            self.assertIn(f"{value}자 이하", section(7), value)
        self.assertEqual(ip.MAX_POLICY_BYTES, 64 * 1024)
        self.assertIn("64KB", section(7))
        self.assertIn(f"`{ip.POLICY_FILE}`", section(7))

    def test_the_review_signals_in_the_guide_are_the_ones_the_code_reads(self):
        text = section(5)
        for word in (ip.REVIEW_QUALITY_KEY, ip.REVIEW_QUALITY_OK, ip.REVIEW_SAFETY_KEY, ip.REVIEW_SAFETY_OK, "post_id", "초안 N건 게시 검토", "초안 N건 대기(검토 조건 미확인)"):
            self.assertIn(word, text, word)
        for label, _key, _value in ip.REVIEW_LABELS:
            self.assertTrue(label in text or label.replace(" 통과", "") in text, label)

    def test_every_item_id_family_the_code_makes_is_in_the_guide(self):
        for word in ("pause:planned", "pause:resume_approval", "draft:<번호>:paused", "draft:<번호>:season", "draft:<번호>:keep", "draft:<번호>:discard", "approval_prs", "approve:<커밋 7자>"):
            self.assertIn(word, DOC, word)
        policy = ip.parse_policy_text((ROOT / ip.POLICY_FILE).read_text(encoding="utf-8"))
        now = datetime(2026, 11, 11, 2, 16, tzinfo=timezone.utc)
        drafts = [h.make_draft(88, "[초안][네이버] 봄맞이 정리", "네이버", created=h.iso(now - timedelta(days=12))),
                  h.make_draft(89, "[초안][티스토리] 서랍 정리", "티스토리", created=h.iso(now - timedelta(days=1))),
                  h.make_draft(103, "[초안][네이버] 가을 점검", "네이버", created=h.iso(now - timedelta(days=8)))]
        blogs = [h.channel_blog("naver_x", "네이버", "naver", "off"), h.channel_blog("tistory_x", "티스토리", "tistory", "package")]
        made = {i.id for i in inbox.build_items(inbox.Snapshot(now=now, repo=h.REPO, blogs=blogs, drafts=drafts, paused=True, policy=policy))}
        self.assertTrue({"pause:planned", "draft:88:discard", "draft:103:discard", "draft:89:paused"} <= made, made)
        made = {i.id for i in inbox.build_items(inbox.Snapshot(now=now, repo=h.REPO, blogs=blogs, drafts=drafts[:1] + drafts[1:2]))}
        self.assertTrue({"draft:88:season", "draft:89:wait"} <= made, made)

    def test_the_season_table_in_the_guide_is_the_code_table(self):
        text = section(6)
        rows = {line.split("|")[1].strip(): line for line in text.splitlines() if line.startswith("| ") and not line.startswith(("| 묶음", "|---", "|-"))}
        self.assertEqual(set(rows), {term[0] for term in ip.SEASON_TERMS})
        for name, pattern, _start, _end in ip.SEASON_TERMS:
            self.assertIn(ip.season_window_text(name), rows[name], name)
            plain = {"봄": "꽃구경", "어린이날·어버이날": "어버이날", "여름": "장마", "가을": "단풍", "추석": "한가위", "수능": "수능", "김장": "김장", "겨울": "한파", "설·정월": "대보름", "연말·성탄": "크리스마스"}[name]
            self.assertTrue(pattern.search(plain), (name, plain))
            self.assertIn(plain, rows[name], (name, plain))

    def test_the_decision_kinds_and_the_key_kinds_are_listed(self):
        text = section(7)
        for kind in ip.DECISION_KINDS:
            self.assertIn(f"`{kind}`", text, kind)
        for prefix in ("approve:", "draft:", "blogger:", "pr:"):
            self.assertIn(f"`{prefix}", text, prefix)
        self.assertEqual(set(ip.DECISION_KEY_PREFIXES), {"approve", "draft", "blogger", "pr"})

    def test_the_current_policy_table_names_every_key_of_the_real_file(self):
        text = section(7)
        for key in POLICY["item_decisions"]:
            self.assertIn(f"`{key}`", text, key)
        self.assertIn("`planned_pause`", text)
        self.assertIn("재개 Gate 미통과", text)
        self.assertFalse(POLICY["planned_pause"]["resume_gate_passed"])

    def test_the_guide_says_who_may_change_the_policy_and_that_nothing_is_written(self):
        text = SECTION_10
        for phrase in ("AI 가 자동으로 고치지 않습니다", "사람이 검토하는 병합", "분류와 표시만", "이슈를 닫거나 라벨 `폐기`를 붙이지 않고", "읽기 호출뿐"):
            self.assertIn(phrase, text, phrase)

    def test_the_limits_are_written_down_honestly(self):
        text = section(9)
        for phrase in ("병합 직후 몇 시간", "패치 초안", "`review_quality`·`review_safety`", "제목만 봅니다", "T3", "D-279"):
            self.assertIn(phrase, text, phrase)
        self.assertIn("17. 병합 직후 몇 시간은 본문이 낡을 수 있고", DOC)


class RulesTableAndFilesTest(unittest.TestCase):
    def test_the_rules_table_rows_say_what_changed(self):
        for phrase in ("**이미 병합됐거나 닫힌 PR**", "싣지 않습니다**(2026-11-11, D-271", "action(정책 파일에 의도된 정지가 없을 때) · info(있을 때)", "초안 N건 게시 검토",
                       "초안 N건 대기(검토 조건 미확인)", "| 초안(정리, 2026-11-11) |", "`draft:<번호>:paused`", "`draft:<번호>:season`", "`draft:<번호>:keep`·`draft:<번호>:discard`",
                       "`N (정지 전 초안)`"):
            self.assertIn(phrase, DOC, phrase)
        self.assertNotIn("`N (정지 중)`", DOC)
        self.assertNotIn('"초안 N건 게시 대기", 링크는 Blogger 관리 화면', DOC)

    def test_the_files_table_lists_the_new_files_and_every_path_exists(self):
        for rel in ("pipeline/inbox_policy.py", "pipeline/ops_inbox_policy.json"):
            self.assertIn(f"[`{rel}`](../{rel})", DOC, rel)
            self.assertTrue((ROOT / rel).is_file(), rel)
        for name in ("test_ops_inbox_policy.py", "test_ops_inbox_cleanup.py", "test_ops_inbox_cleanup_script.py", "test_ops_inbox_cleanup_docs.py", "ops_inbox_repro.py"):
            self.assertIn(name.replace(".py", ""), DOC, name)
            self.assertTrue((ROOT / "tests" / name).is_file(), name)

    def test_the_reading_table_and_the_first_section_mention_the_cleanup(self):
        self.assertIn("**정리 규칙(2026-11-11)**", DOC)
        self.assertIn("폐기 후 닫기 권장·철 지난·정지 전 초안(§10)", DOC)
        self.assertIn("계획된 일시정지·유지로 정한 초안(§10)", DOC)

    def test_the_pinned_phrases_of_the_older_tests_are_still_in_the_guide(self):
        for phrase in ("게시 확인(2026-11-02, 이슈 #89)", "`DRAFT_REMIND_AFTER_HOURS`(6시간)", "Blogger 게시 확인(블로그 공개 피드)", "feeds/posts/summary?alt=json",
                       "공개 글이 하나도 없는 피드", "예약 게시(SCHEDULED)", "열린 지 3일 이하", "`draft:<번호>:wait`", "`draft:<번호>:stale`"):
            self.assertIn(phrase, DOC, phrase)


class DefectRegisterTest(unittest.TestCase):
    def rows(self):
        return {m.group(1): m.group(0) for m in re.finditer(r"^\| \*\*(D-\d+)\*\* \|.*$", REGISTER, re.M)}

    def test_each_number_of_the_band_is_one_well_formed_row(self):
        found = re.findall(r"^\| \*\*(D-\d+)\*\* \|", REGISTER, re.M)
        for number in MY_DEFECTS:
            self.assertEqual(found.count(number), 1, number)
        rows = self.rows()
        for number in MY_DEFECTS:
            self.assertEqual(rows[number].count("|"), 7, number)            # 칸 여섯
            self.assertNotIn(chr(126), rows[number], number)
            self.assertNotIn("http", rows[number], number)

    def test_the_states_use_the_registers_vocabulary_and_the_open_ones_say_what_is_missing(self):
        rows = self.rows()
        states = {number: rows[number].split("|")[5].strip() for number in MY_DEFECTS}
        for number, state in states.items():
            self.assertTrue(state.startswith(("**해결**", "**완화**", "**열림**", "**결정**")), (number, state[:20]))
        self.assertTrue(states["D-279"].startswith("**열림**"))
        self.assertIn("T3", rows["D-279"])
        self.assertTrue(states["D-274"].startswith("**완화**"))
        self.assertIn("신호 기록은 **열림**", states["D-274"])
        self.assertTrue(states["D-277"].startswith("**결정**") and states["D-278"].startswith("**결정**"))

    def test_the_header_note_names_the_range_and_the_section(self):
        self.assertIn("> D-270–D-279 는 2026-11-11 에 추가했다(확인 필요 모음의 오래된 항목·의도된 정지 분류 정리 — `docs/OPS_INBOX.md` §10).", REGISTER)

    def test_every_test_class_the_rows_name_exists(self):
        sources = "\n".join((ROOT / "tests" / name).read_text(encoding="utf-8") for name in
                            ("test_ops_inbox_cleanup.py", "test_ops_inbox_cleanup_script.py", "test_ops_inbox_policy.py", "test_ops_inbox_cleanup_docs.py"))
        rows = self.rows()
        for number in MY_DEFECTS:
            for name in re.findall(r"`([A-Za-z]+Test)`", rows[number]):
                self.assertIn(f"class {name}(", sources, (number, name))

    def test_the_rows_do_not_depend_on_other_bundles_numbers(self):
        rows = self.rows()
        for number in MY_DEFECTS:
            for other in re.findall(r"D-(\d+)", rows[number]):
                if f"D-{other}" != number:
                    self.assertIn(f"D-{other}", MY_DEFECTS, (number, other))      # 이 묶음의 번호끼리만 서로 가리킨다


class SourceMentionsTest(unittest.TestCase):
    def test_the_script_and_the_rule_module_say_the_same_things_as_the_guide(self):
        script = (ROOT / "scripts" / "ops_inbox.py").read_text(encoding="utf-8")
        rules = (ROOT / "pipeline" / "inbox.py").read_text(encoding="utf-8")
        policy = (ROOT / "pipeline" / "inbox_policy.py").read_text(encoding="utf-8")
        for word in ("MAX_APPROVAL_LOOKUPS", "ops_inbox_policy.json", "오래된 항목 정리(2026-11-11"):
            self.assertIn(word, script, word)
        for word in ("오래된 항목과 의도된 정지(2026-11-11", "정책 파일이 없거나(Snapshot.policy 가 None)"):
            self.assertIn(word, rules, word)
        for word in ("AI 가 자동으로 고치지 않는다", "사람이 검토하는 병합뿐"):
            self.assertIn(word, policy, word)

    def test_no_tilde_in_the_new_module_and_no_web_address_in_the_policy_data(self):
        for rel in ("pipeline/inbox_policy.py", "pipeline/ops_inbox_policy.json"):
            self.assertNotIn(chr(126), (ROOT / rel).read_text(encoding="utf-8"), rel)
        self.assertIsNone(re.search(r"https?://", (ROOT / ip.POLICY_FILE).read_text(encoding="utf-8")))
        # 규칙 모듈의 주석에는 주소를 쓰지 않는다 — 코드에 있는 거절용 낱말(http 로 시작하는 두 가지)만 예외다
        comments = [line.split("#", 1)[1] for line in (ROOT / "pipeline" / "inbox_policy.py").read_text(encoding="utf-8").splitlines() if "#" in line]
        self.assertFalse([c for c in comments if re.search(r"https?://", c) and "_FORBIDDEN" not in c])


class AfterVerificationDocsTest(unittest.TestCase):
    """독립 검증 뒤 고침(D-280–D-289)의 설명이 문서에 있고 코드의 이름·값과 같다."""

    def test_the_guide_says_which_runs_the_approval_rule_leaves_in(self):
        text = section(2)
        for phrase in ("이 저장소의 그 PR 에 딸린 실행만 뺍니다", "포크에서 온 PR 의 실행이거나 head 저장소를 알 수 없으면", "`head_sha` 가 병합됐거나 닫힌 PR 들의 head 커밋",
                       "`Snapshot.branch_pr_heads`", "D-281"):
            self.assertIn(phrase, text, phrase)

    def test_the_pause_table_names_both_checks_and_the_limit_constant(self):
        text = section(3)
        self.assertIn(f"{inbox.PLANNED_PAUSE_LONG_DAYS}일(`PLANNED_PAUSE_LONG_DAYS`)", text)
        for phrase in ("`pause:long`", "`pause:unset`", "정책 파일은 일시정지를 선언했는데 변수 PIPELINE_PAUSE 가 꺼져 있습니다 — 실수로 해제했나요?", "계획된 일시정지가 길어졌어요 — 재개 조건을 점검하세요"):
            self.assertIn(phrase, text, phrase)
        self.assertEqual(inbox.PLANNED_PAUSE_LONG_DAYS, 21)

    def test_the_release_checklist_has_a_named_place_and_the_item_text_points_there(self):
        text = section(3)
        for phrase in ("**해제 점검표의 위치**", "`planned_pause.resume_conditions`", "`docs/ARCHITECTURE.md` 4-9절", "16항목 증거 한 장", "`인수인계/작업내용.md`",
                       "재개 조건이 모두 통과했다고 정책 파일에 기록되면(AI 가 준비하고 운영자가 병합하는 변경) 재개 승인 항목으로 알립니다"):
            self.assertIn(phrase, text, phrase)
        policy = ip.parse_policy_text((ROOT / ip.POLICY_FILE).read_text(encoding="utf-8"))
        planned = one_item(inbox.pause_items(True, "https://github.com/o/r", policy))
        self.assertIn("재개 조건이 모두 통과했다고 정책 파일에 기록되면(AI 가 준비하고 운영자가 병합하는 변경) 재개 승인 항목으로 알립니다", planned.hint)
        self.assertNotIn("알려 드립니다", planned.hint)                                     # 모음이 조건 통과를 스스로 아는 것처럼 말하지 않는다
        gate = ip.parse_policy({"schema_version": 1, "planned_pause": dict(POLICY["planned_pause"], resume_gate_passed=True)})
        resume = one_item(inbox.pause_items(True, "https://github.com/o/r", gate))
        self.assertIn("해제 점검표", resume.hint)
        self.assertIn("docs/OPS_INBOX.md 10-3절", resume.hint)
        self.assertIn("16항목 증거 한 장", resume.hint)
        self.assertIn("## 4-9. 제한 재개 잠금", (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8"))
        self.assertTrue((ROOT / "인수인계" / "작업내용.md").is_file())                          # 점검표를 가리키는 작업 기록이 있다(그 안의 낱말은 못박지 않는다)

    def test_the_stopped_table_note_rule_is_in_the_guide(self):
        text = section(4)
        for phrase in ("표에 그런 칸이 하나라도 있으면 표 아래 설명이 정지용 문구로 바뀝니다", "일부 채널만 멈췄으면(`mode: off`)", "D-284"):
            self.assertIn(phrase, text, phrase)

    def test_the_season_rule_is_for_issue_drafts_only_and_the_exceptions_are_named(self):
        text = section(6)
        for phrase in ("이슈 초안(티스토리·네이버 패키지 초안)에만 쓰고 Chance 승인 흐름의 PR 초안은 뺍니다", "`draft:<번호>:wait`", "D-280", "'연말정산'", "'새 학기'", "'겨울왕국'", "'한여름 밤의 꿈'", "1월 말까지 늘렸습니다"):
            self.assertIn(phrase, text, phrase)
        self.assertIn("**이슈 초안**", DOC.split("## 10. ")[0])                              # 앞쪽 규칙표의 행도 같은 말을 한다

    def test_the_policy_file_section_names_the_four_key_shapes_and_the_new_refusals(self):
        text = section(7)
        self.assertEqual(len(ip._KEY_SHAPES), 4)
        for phrase in ("모양은 네 가지뿐이며 다른 모양은 파일 전체를 쓰지 않는 사유입니다", "`approve:<커밋 7자>`", "`draft:<번호>`", "`blogger:<블로그 키>:drafts:<시각 12자리>`", "`pr:<번호>`",
                       "`approve:more`", "같은 칸이 두 번 나오는 것", "아홉 자리 이상 숫자·`pub-` 번호·전화 모양", "오늘(한국 날짜)보다 뒤의 시작일·결정일", "너무 깊게 중첩돼 파서가 재귀 한도에 닿거나 메모리가 모자란 파일",
                       "재귀 한도·메모리 부족을 포함해 예외로 죽지 않습니다", "오늘 한국 날짜보다 뒤면 거절"):
            self.assertIn(phrase, text, phrase)
        self.assertNotIn("시각을 뺀 `blogger:<블로그 키>:drafts` 도 쓸 수 있지만", text)        # 넓은 키를 쓸 수 있다는 옛 문장이 남아 있지 않다
        self.assertNotIn("가장 구체적인(긴) 키가 이깁니다. 결정은", text)

    def test_the_limits_name_the_false_alarms_the_misses_and_the_patch_observations(self):
        text = section(9)
        for phrase in ("(미탐)", "오탐은 일곱 가지를 없앴지만(D-285)", "개학·졸업·에어컨·패딩", "알림이 가지 않습니다(PR 초안은 이 판정에서 빠져 알림이 그대로입니다, D-280)",
                       "닫힘 이벤트의 실행이 승인 대기(`action_required`)로 멈추지 않고 도는지 관측", "읽기 전용 토큰으로 도는 PR", "신호 이름은 누가 판정했는가·판정 버전을 말하지 않습니다(§10-11)"):
            self.assertIn(phrase, text, phrase)

    def test_the_resume_checks_section_lists_the_six_things_with_their_state(self):
        text = section(11)
        rows = [line for line in text.splitlines() if re.match(r"^\| \d+ \|", line)]
        self.assertEqual(len(rows), 6)
        for phrase in ("철 지난 초안 규칙의 PR 초안 처리", "Blogger 검토 신호를 이력에 쓰는 쪽", "`review_quality`·`review_safety`", "누가 판정했는가(품질 Gate 인가 사람인가)와 판정 버전", "마지막 커밋의 실행만 뺍니다",
                       "`planned_pause.active`", "21일", "`resume_gate_passed`", "열림", "고쳤음(D-280)", "고쳤음(D-281)", "표시만(D-288)"):
            self.assertIn(phrase, text, phrase)
        self.assertIn("정책 파일의 재개 조건 6가지에는 없는 것들입니다", text)

    def test_the_new_register_rows_are_in_the_band_and_say_who_found_them(self):
        rows = {m.group(1): m.group(0) for m in re.finditer(r"^\| \*\*(D-\d+)\*\* \|.*$", REGISTER, re.M)}
        for number in (f"D-{n}" for n in range(280, 290)):
            self.assertIn("독립 검증", rows[number], number)
        self.assertIn("> D-280–D-289 는 2026-11-11 에 추가했다(확인 필요 모음 독립 검증의 새 문제 D1–D11 을 고침 — `docs/OPS_INBOX.md` §10-11).", REGISTER)
        self.assertTrue(rows["D-285"].split("|")[5].strip().startswith("**완화**"))
        for number in ("D-280", "D-281", "D-282", "D-283", "D-284", "D-286", "D-287", "D-288", "D-289"):
            self.assertTrue(rows[number].split("|")[5].strip().startswith("**해결**"), number)
        self.assertIn("관측한다(패치 초안의 README)", rows["D-279"])


def one_item(items):
    assert len(items) == 1, [i.id for i in items]
    return items[0]


if __name__ == "__main__":
    unittest.main()
