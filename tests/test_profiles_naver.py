"""네이버 초안 패키지 채널의 콘텐츠 프로필(`naver_life_tips_ko`)과 프롬프트 파일 시험. 네트워크 없이 돈다. 티스토리는 2026-10-30 운영자 결정(제외·격리)으로 이 저장소에 없다.

프로필은 한글 AI·도구 프로필(`blogger_ai_tools_ko`)의 가드레일(banned_*·body_*·leak_*·상담 구절 면제)·길이·제목·라벨·유사도 설정을 **한 글자도 바꾸지 않고** 가져오고,
주제 구성(시드 36개)·확장 프롬프트·예시 규칙·AI 고지 문구만 채널에 맞춘다. 이 시험이 고정하는 것:
  1) 구조: 바뀐 필드가 의도한 일곱 가지뿐이고 가드레일은 기준 프로필과 같다.
  2) 시드: 36개(구성 비율·35~55자)와 모두 가드레일 통과, 다른 블로그의 시드·제목과 충돌하지 않는다.
  3) 게이트: 정상 글은 통과하고 나쁜 표본(지어낸 경험·수치·의료·법률·금융·링크)은 탈락한다.
  4) 프롬프트 파일과 레지스트리: 파일이 러너가 읽는 모양이고 레지스트리 항목·워크플로·이력 제외가 맞다.
"""
import copy
import datetime
import random
import re
import unittest

import _bootstrap  # noqa: F401
from pipeline import gates, registry, topics
from pipeline import run as run_mod
from pipeline.state import entry_titles, read_json_list
from pipeline.stubs import stub_post

REAL = _bootstrap.ROOT
BASE = registry.load_profile("blogger_ai_tools_ko")
BASE_PRACTICAL = registry.load_profile("blogger_practical_ko")
EN = registry.load_profile("blogger_practical_en")
REGISTRY = registry.load_registry(REAL / "pipeline" / "blogs.json")

CHANNELS = {
    "naver_life_tips_ko": {
        "blog": "naver_life_tips", "label": "네이버", "platform": "naver", "prompt": ".github/editorial/NAVER_PROMPT.md", "cron": "20 6 * * *", "url": "https://blog.naver.com/shine5652",
        "mix": {"계절·절기·명절 준비": 14, "여행·외출 준비": 8, "생활 습관·살림 관리": 14},
        "normal": [
            "장마철에는 신발장 문을 자주 열어 환기하고 제습제를 두면 습기를 줄이는 데 도움이 돼요.",
            "눅눅해진 이불은 맑은 날 햇볕에 말린 뒤 완전히 식혀서 보관하세요.",
            "에어컨 필터는 설명서에 나온 방법대로 분리해 먼지를 털어 내고 말려서 끼우세요.",
            "선풍기를 에어컨과 함께 쓰면 찬 공기가 골고루 퍼져 설정 온도를 높여도 시원해요.",
            "김장철 전에는 냉장고 안 오래된 식재료를 먼저 정리해 자리를 만들어 두세요.",
            "겨울에는 창문 틈과 문틈으로 들어오는 바람을 막아 주면 집 안이 훨씬 따뜻해져요.",
            "환절기에는 계절이 지난 옷과 이불을 세탁해서 완전히 말린 뒤 수납해 두세요.",
            "대청소는 방별로 날짜를 나누면 하루에 모든 것을 하지 않아도 되어 부담이 적어요.",
            "나들이 전에는 날씨 예보와 준비물 목록을 먼저 확인해 보세요.",
            "명절 연휴 전에 냉장고를 정리해 두면 장 보는 목록을 만들기 쉬워져요.",
            "선물은 포장과 배송 날짜를 미리 정해 두면 마지막에 서두르지 않아도 돼요.",
            "귀성길에는 간식과 물, 충전기를 차 안 손이 닿는 곳에 미리 챙겨 두세요.",
            "단풍 나들이에는 아침저녁 기온 차를 생각해 겹쳐 입을 수 있는 옷을 챙기세요.",
            "여행 짐은 꼭 필요한 물건만 목록으로 적은 뒤 하나씩 지워 가며 싸 보세요.",
            "집을 비우기 전에는 가스 밸브와 전원, 쓰레기를 확인하는 점검 목록을 만들어 두세요.",
            "캐리어는 옷과 세면도구를 구역으로 나누어 담으면 찾기도 쉽고 부피도 줄어요.",
            "젖은 우산은 펼쳐서 그늘에서 말린 뒤 접어 두면 냄새와 녹을 줄일 수 있어요.",
            "부모님과 함께하는 나들이는 쉬는 시간을 일정 사이에 넉넉히 넣어 두세요.",
            "여행에서 돌아오면 빨래부터 돌려 놓고 짐을 풀면 정리가 빨라져요.",
            "도시락과 돗자리는 전날 밤에 미리 챙겨 두면 아침이 한결 여유로워요.",
            "여권과 충전기, 어댑터는 한곳에 모아 두면 출발 전에 빠뜨리지 않아요.",
            "멀티탭 스위치를 쓰면 쓰지 않는 기기의 대기 전력을 쉽게 끊을 수 있어요.",
            "빨래는 모아서 한 번에 돌리면 물과 시간을 함께 아낄 수 있어요.",
            "남은 식재료는 눈에 잘 띄는 칸에 모아 두고 일주일 안에 쓰도록 계획해 보세요.",
            "분리배출 기준은 지역마다 다를 수 있으니 안내표를 만들어 눈에 띄는 곳에 붙여 두세요.",
            "싱크대 배수구는 주기적으로 망을 비우고 뜨거운 물을 흘려 주면 냄새를 줄일 수 있어요.",
            "조명은 필요한 곳만 켜는 습관을 들이면 집 안이 더 아늑하게 느껴져요.",
            "한 주 식단을 미리 정해 두면 장보기와 요리 시간이 줄어요.",
            "설거지용 수세미는 자주 헹구고 말려서 오래 쓰고 상태를 보고 바꿔 주세요.",
            "우편물은 받는 즉시 한곳에 모아 두면 중요한 서류를 놓치지 않아요.",
            "물건마다 자리를 정해 두면 정리하는 시간이 눈에 띄게 줄어들어요.",
        ],
    },
}

# 나쁜 본문 표본(가드레일이 한 글자도 다르지 않으므로 대표만 본다): (문장, 걸려야 하는 곳) — BANNED(banned_patterns) · BODY(body_banned_patterns)
BAD_BODY = [
    ("제가 직접 써 봤더니 정리 시간이 확 줄었어요.", "BANNED"),
    ("직접 해 본 결과 설정이 훨씬 간단해졌어요.", "BANNED"),
    ("이 설정으로 작업 속도가 30% 빨라집니다.", "BANNED"),
    ("전문가에 따르면 이 방법이 가장 안전하다고 합니다.", "BANNED"),
    ("사용자 후기를 보면 대부분 만족했다고 해요.", "BANNED"),
    ("100% 안전한 방법입니다.", "BANNED"),
    ("이 습관으로 불면증이 완치됩니다.", "BANNED"),
    ("혈압을 낮추는 데 이 방법이 도움이 됩니다.", "BODY"),
    ("세금 계산은 이렇게 하면 됩니다.", "BODY"),
    ("대출 금리를 비교해 보세요.", "BODY"),
]
LISTS = {"BANNED": "banned_patterns", "BODY": "body_banned_patterns"}
GUARDRAIL_KEYS = ("banned_patterns", "banned_topic_patterns", "body_banned_patterns", "body_clause_split_patterns", "body_safe_patterns", "body_safe_veto_patterns",
                  "leak_patterns", "title_banned_patterns", "language", "length", "title", "labels", "structure", "similarity", "allow_links", "max_attempts",
                  "min_hangul_ratio", "topic_cooldown_days")
# 채널마다 시드가 닿는 위험 영역의 안전 문장(프롬프트 파일 규칙 8 과 프로필 prompt_extra 가 같은 문장을 가진다) — 게이트는 이런 안내의 빠짐을 못 잡으므로 문장 자체를 못박는다
NAVER_SAFETY = ("청소 도구·수납함·가전", "제품 설명서를 먼저 확인하라고", "해마다 조금씩 다를 수 있다고", "세제를 섞어 쓰지 말고 제품 설명서의 사용법과 환기 안내를 따르라고",
                "보관 기간이나 온도를 숫자로 단정하지 않고 포장에 적힌 표시와 제조사 안내를 확인하라고", "여권 유효기간·입국 조건·전압처럼 나라마다 다른 사실은 단정하지 않고 공식 안내에서 확인하라고")
CHANGED_KEYS = {"_doc", "_seed_mix", "name", "topic_expand_prompt", "prompt_extra", "disclosure_html", "seed_topics"}


def profile_of(name):
    return registry.load_profile(name)


def history_titles():
    titles = []
    for path in ("history.json", "blogger_history.json", "blogger_ko_history.json"):
        titles += entry_titles(read_json_list(REAL / path))
    return titles


def good_post(profile, topic, sentence=""):
    post = gates.parse_labeled_post(stub_post(topic))
    clean, stats = gates.sanitize_html(post["content"])
    if sentence:
        clean = clean.replace("</p>", f" {sentence}</p>", 1)
    return {"title": post["title"], "labels": post["labels"], "content": clean}, stats


def codes_of(profile, post, stats=None):
    return gates.check_post(post, profile, [], [], stats).codes()


class StructureTest(unittest.TestCase):
    def test_each_profile_is_valid_named_like_its_file_and_clean_text(self):
        for name in CHANNELS:
            with self.subTest(profile=name):
                profile = profile_of(name)
                self.assertEqual(registry.validate_profile(profile), [])
                self.assertEqual(profile["name"], name)
                raw = (REAL / "pipeline" / "profiles" / f"{name}.json").read_bytes()
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                self.assertTrue(raw.endswith(b"\n"))
                self.assertNotIn(b"\r", raw.replace(b"\r\n", b"\n"))          # 줄 끝 CRLF 는 Windows 체크아웃(autocrlf)이 바꾼 것 — 저장된 파일은 LF 다

    def test_the_guardrails_are_exactly_the_korean_ai_tools_profiles(self):
        for name in CHANNELS:
            profile = profile_of(name)
            for key in GUARDRAIL_KEYS:
                self.assertEqual(profile[key], BASE[key], (name, key))

    def test_only_the_seven_channel_specific_fields_differ_from_the_base(self):
        for name in CHANNELS:
            profile = profile_of(name)
            self.assertEqual({key for key in set(profile) | set(BASE) if profile.get(key) != BASE.get(key)}, CHANGED_KEYS, name)
            self.assertEqual(set(profile), set(BASE), name)

    def test_the_disclosure_is_an_honest_ai_notice_in_korean_without_links(self):
        for name in CHANNELS:
            html = profile_of(name)["disclosure_html"]
            self.assertTrue(html.startswith("<p><em>") and html.endswith("</em></p>"), name)
            self.assertIn("AI의 도움을 받아 작성·편집한 일반 정보", html)
            self.assertNotRegex(html, r"https?://|www\.|@|<a ", name)
            self.assertIn("전문가와 상담", html)
        self.assertIn("제품의 사용법과 안전 수칙은 제조사의 설명서와 공식 안내에서 다시 확인하고", profile_of("naver_life_tips_ko")["disclosure_html"])

    def test_the_prompt_extra_changes_only_the_three_channel_lines_and_keeps_the_safety_lines(self):
        for name in CHANNELS:
            extra, base = profile_of(name)["prompt_extra"], BASE["prompt_extra"]
            self.assertEqual(len(extra), len(base), name)
            self.assertEqual([i for i in range(len(base)) if extra[i] != base[i]], [3, 4, 5], name)
            joined = "\n".join(extra)
            for needle in ("지어내지 않는다", "단정하지 않는다", "홍보하거나 순위를 매기거나", "법률·세금·대출·투자·보험", "허용 태그는 p, h3, ul, ol, li, strong, em, br"):
                self.assertIn(needle, joined, (name, needle))

    def test_the_channel_lines_carry_what_the_channel_needs(self):
        naver = "\n".join(profile_of("naver_life_tips_ko")["prompt_extra"])
        for needle in NAVER_SAFETY:
            self.assertIn(needle, naver)

    def test_the_expansion_prompt_names_the_mix_the_excluded_areas_and_keeps_the_placeholders(self):
        for name, spec in CHANNELS.items():
            prompt = profile_of(name)["topic_expand_prompt"]
            for placeholder in ("{n}", "{min}", "{max}", "{avoid}"):
                self.assertEqual(prompt.count(placeholder), 1, (name, placeholder))
            for needle in ("건강·의료", "법률·세금·대출·투자·보험", "홍보·순위 비교", "JSON 문자열 배열만"):
                self.assertIn(needle, prompt, (name, needle))
            self.assertEqual(len(re.findall(r"약 \d+%", prompt)), 3, name)
            self.assertNotIn("증상", prompt, name)       # '증상' 은 주제 금지어라 확장 주제가 헛되이 걸러진다


class SeedTest(unittest.TestCase):
    def test_there_are_36_unique_seeds_in_the_declared_mix(self):
        for name, spec in CHANNELS.items():
            profile = profile_of(name)
            seeds = profile["seed_topics"]
            self.assertEqual(len(seeds), 36, name)
            self.assertEqual(len(set(seeds)), 36, name)
            self.assertEqual(profile["_seed_mix"], spec["mix"], name)
            self.assertEqual(sum(spec["mix"].values()), 36, name)

    def test_every_seed_is_35_to_55_characters_and_inside_the_topic_range_the_picker_accepts(self):
        for name in CHANNELS:
            for seed in profile_of(name)["seed_topics"]:
                self.assertTrue(35 <= len(seed) <= 55, f"{name} {len(seed)}자: {seed}")
                self.assertTrue(topics.TOPIC_MIN_CHARS <= len(seed) <= topics.TOPIC_MAX_CHARS, seed)
                self.assertEqual(seed, topics.clean_topic(seed))

    def test_every_seed_passes_the_topic_guardrail_and_the_registry_checks_it(self):
        for name in CHANNELS:
            profile = profile_of(name)
            for seed in profile["seed_topics"]:
                self.assertTrue(gates.topic_allowed(seed, profile), seed)
                self.assertEqual(gates.first_match(profile["banned_topic_patterns"], seed), (None, None), seed)
                self.assertIsNone(gates.matches_any(profile["banned_patterns"], seed), seed)
                self.assertIsNone(gates.matches_any(profile["leak_patterns"], seed), seed)
            broken = copy.deepcopy(profile)
            broken["seed_topics"] = profile["seed_topics"] + ["대출 금리 비교하는 방법과 순서를 알아보기"]
            self.assertTrue(any("seed_topics" in error and "banned_topic_patterns" in error for error in registry.validate_profile(broken)), name)

    def test_no_seed_contains_a_price_a_link_a_first_person_word_or_an_experience_claim(self):
        for name in CHANNELS:
            for seed in profile_of(name)["seed_topics"]:
                self.assertNotRegex(seed, r"\d[\d,]*\s*(?:원|달러)|https?://|www\.|저는|제가|써\s*봤|해\s*본\s*결과", seed)

    def test_seeds_do_not_collide_with_each_other_or_with_any_other_blogs_topics_or_titles(self):
        threshold = BASE["similarity"]["other_blogs"]
        chosen = {name: profile_of(name)["seed_topics"] for name in CHANNELS}
        existing = list(BASE["seed_topics"]) + list(BASE_PRACTICAL["seed_topics"]) + list(EN["seed_topics"]) + history_titles()
        for name, seeds in chosen.items():
            for index, seed in enumerate(seeds):
                for other in seeds[index + 1:]:
                    self.assertLess(gates.similarity(seed, other), threshold, (name, seed, other))
            others = [s for n, ss in chosen.items() if n != name for s in ss]
            for seed in seeds:
                score, nearest = gates.most_similar(seed, existing + others)
                self.assertLess(score, threshold, (name, seed, nearest))
                self.assertTrue(topics._acceptable(seed, profile_of(name), [], datetime.date(2026, 10, 30), existing + others), seed)

    def test_the_picker_chooses_only_from_these_seeds_and_covers_all_of_them(self):
        for name in CHANNELS:
            profile = profile_of(name)
            seen = set()
            for number in range(400):
                topic, source = topics.pick_topic(profile, [], datetime.date(2026, 10, 30), [], random.Random(number))
                self.assertEqual(source, "seed")
                seen.add(topic)
            self.assertEqual(seen, set(profile["seed_topics"]), name)

    def test_the_seeds_differ_from_the_korean_blogs_seeds_by_angle_not_only_by_wording(self):
        """네이버는 '계절·여행·절약 습관' 각도다 — 한글 Blogger 의 집 정리 낱말 묶음과 겹치는 시드가 거의 없다."""
        home_words = ("현관", "욕실", "가계부", "베란다", "서랍", "택배 상자")         # 한글 Blogger 집·살림 시드의 주된 대상(옷장·냉장고는 계절·명절 맥락에서 쓰이므로 뺀다 — 겹침은 유사도 시험이 따로 막는다)
        for seed in profile_of("naver_life_tips_ko")["seed_topics"]:
            self.assertFalse(any(word in seed for word in home_words), seed)


class GateTest(unittest.TestCase):
    def test_the_stub_post_passes_for_every_seed(self):
        for name in CHANNELS:
            profile = profile_of(name)
            for seed in profile["seed_topics"]:
                post, stats = good_post(profile, seed)
                self.assertEqual(codes_of(profile, post, stats), [], (name, seed))

    def test_there_are_thirty_normal_sentences_per_channel_and_none_is_turned_down(self):
        for name, spec in CHANNELS.items():
            profile = profile_of(name)
            self.assertGreaterEqual(len(spec["normal"]), 30, name)
            for sentence in spec["normal"]:
                self.assertIsNone(gates.matches_any(profile["banned_patterns"], sentence), (name, sentence))
                self.assertIsNone(gates.matches_any(profile["leak_patterns"], sentence), (name, sentence))
                post, stats = good_post(profile, profile["seed_topics"][0], sentence)
                self.assertEqual(codes_of(profile, post, stats), [], (name, sentence))

    def test_the_bad_samples_turn_a_whole_post_down(self):
        for name in CHANNELS:
            profile = profile_of(name)
            for sentence, where in BAD_BODY:
                post, stats = good_post(profile, profile["seed_topics"][0], sentence)
                self.assertNotEqual(codes_of(profile, post, stats), [], (name, sentence))

    def test_the_post_with_links_is_turned_down(self):
        for name in CHANNELS:
            profile = profile_of(name)
            post, stats = good_post(profile, profile["seed_topics"][0], "자세한 내용은 https://example.com 에서 보세요.")
            self.assertNotEqual(codes_of(profile, post, stats), [], name)

    def test_the_language_check_wants_korean(self):
        for name in CHANNELS:
            profile = profile_of(name)
            english = {"title": "A calm routine for phones", "labels": ["phone"], "content": "<h3>One</h3><p>" + "Check the settings and restart the device. " * 40 + "</p><ul><li>a</li></ul><h3>Two</h3><h3>Three</h3>"}
            self.assertNotEqual(codes_of(profile, english), [], name)


class PromptFileTest(unittest.TestCase):
    def blog(self, name):
        return next(b for b in REGISTRY["blogs"] if b["key"] == CHANNELS[name]["blog"])

    def prompt_text(self, name):
        return (REAL / CHANNELS[name]["prompt"]).read_text(encoding="utf-8")

    def template(self, name):
        return run_mod.load_prompt_template(REAL, self.blog(name))

    def test_the_registry_points_at_this_prompt_and_the_runner_accepts_it(self):
        for name, spec in CHANNELS.items():
            blog = self.blog(name)
            self.assertEqual(blog["prompt"], spec["prompt"])
            template = self.template(name)
            self.assertEqual(template.count("{topic}"), 1)
            prompt = run_mod.build_prompt(template, "테스트 주제", profile_of(name))
            self.assertIn("[추가 규칙]", prompt)

    def test_the_head_names_the_channel_exactly_as_the_registry_labels_it(self):
        for name, spec in CHANNELS.items():
            label = self.blog(name)["channel"]["label"]
            self.assertEqual(label, spec["label"])
            self.assertTrue(self.template(name).startswith(f"[대상: {label}]"), name)
            self.assertIn(f"**대상: {label} (레지스트리 `{spec['blog']}`", self.prompt_text(name))

    def test_the_twelve_numbered_rules_are_all_there_in_order(self):
        for name in CHANNELS:
            numbers = [int(m) for m in re.findall(r"^(\d{1,2})\. ", self.template(name), re.M)]
            self.assertEqual(numbers, list(range(1, 13)), name)

    def test_the_prompt_files_carry_the_same_safety_sentences_as_the_profiles(self):
        for name, needles in (("naver_life_tips_ko", NAVER_SAFETY[3:]),):
            template = self.template(name)
            for needle in needles:
                self.assertIn(needle, template, (name, needle))

    def test_the_rules_say_what_they_are_for(self):
        for name in CHANNELS:
            template = self.template(name)
            for needle in ("지어내지 않는다", "단정하지 않는다", "홍보하거나 순위를 매기거나", "법률·세금·대출·투자·보험", "링크, 웹 주소, 이메일 주소, 이미지, 표를 넣지 않는다", "면책·고지 문장은 쓰지 않는다"):
                self.assertIn(needle, template, (name, needle))
            self.assertNotIn("증상", template, name)

    def test_the_numbers_the_prompt_asks_for_fit_inside_what_the_profile_gate_accepts(self):
        for name in CHANNELS:
            profile, template = profile_of(name), self.template(name)
            low, high = (int(x.replace(",", "")) for x in re.search(r"글 길이: ([\d,]+)~([\d,]+)자", template).groups())
            self.assertTrue(profile["length"]["min_chars"] <= low < high <= profile["length"]["max_chars"], name)
            t_low, t_high = (int(x) for x in re.search(r"제목: (\d+)~(\d+)자", template).groups())
            self.assertTrue(profile["title"]["min_chars"] <= t_low < t_high <= profile["title"]["max_chars"], name)
            self.assertIn("3개 내외", template)

    def test_the_output_format_asks_for_the_markers_the_runner_parser_reads_and_only_the_allowed_tags(self):
        for name in CHANNELS:
            template = self.template(name)
            for marker in ("제목:", "라벨:", "내용:"):
                self.assertIn(marker, template)
            self.assertIn("<p>, <h3>, <ul>, <li>, <strong>, <em> 태그만 사용", template)
            for tag in re.findall(r"<(/?[a-z0-9]+)", template):
                self.assertIn(tag.lstrip("/"), {"p", "h3", "ul", "ol", "li", "strong", "em", "br"}, (name, tag))

    def test_an_answer_written_exactly_in_the_format_the_prompt_asks_for_parses_and_passes_the_gate(self):
        for name in CHANNELS:
            profile = profile_of(name)
            seed = profile["seed_topics"][0]
            post, stats = good_post(profile, seed)
            self.assertEqual(codes_of(profile, post, stats), [])

    def test_the_prompt_file_has_the_operator_reading_list_before_turning_the_channel_on(self):
        for name in CHANNELS:
            text = self.prompt_text(name)
            for needle in ("## 6. 켜기 전에 운영자가 읽을 것 (T3)", "`ads: off`", "`_config.yml` 의 `exclude`", "직접 경험·판단 문단", "R-024"):
                self.assertIn(needle, text, (name, needle))


class RegistryEntryTest(unittest.TestCase):
    def test_the_entry_is_a_package_channel_with_only_the_llm_secret_and_no_ads(self):
        for name, spec in CHANNELS.items():
            blog = next(b for b in REGISTRY["blogs"] if b["key"] == spec["blog"])
            self.assertEqual(blog["platform"], spec["platform"])
            self.assertEqual(blog["url"], spec["url"])                                   # 운영자가 R-024 에서 준 주소 그대로
            self.assertEqual(blog["health"], {"max_gap_hours": 50, "max_failure_streak": 3, "max_unpublished_days": 3})
            self.assertIn(blog["mode"], ("off", "package"))
            self.assertEqual(blog["profile"], name)
            self.assertEqual(blog["entrypoint"], "pipeline/run.py")
            self.assertEqual(blog["workflow"], f".github/workflows/{spec['platform']}.yml")
            self.assertEqual(blog["schedule"]["cron"], spec["cron"])
            self.assertEqual(blog["secrets"], {"llm_api_key": "GEMINI_API_KEY"})
            self.assertEqual((blog["ads"], blog["ad_surface"]), ("off", False))
            self.assertEqual(blog["limits"]["max_posts_per_day"], 1)
            self.assertTrue(blog["state"]["content_dir"].startswith("_"))            # 밑줄 폴더는 Jekyll 이 사이트로 내지 않는다
            workflow = (REAL / blog["workflow"]).read_text(encoding="utf-8")
            self.assertIn(f"cron: '{spec['cron']}'", workflow)

    def test_a_channel_that_is_on_keeps_its_history_file_out_of_the_published_site(self):
        """mode package 로 켠 채널의 이력 파일(루트 *.json)은 `_config.yml` 의 exclude 에 있어야 한다 — 없으면 이력이 공개 주소가 된다(`_config.yml` 은 광고 표면 — T3)."""
        config = (REAL / "_config.yml").read_text(encoding="utf-8")
        for spec in CHANNELS.values():
            blog = next(b for b in REGISTRY["blogs"] if b["key"] == spec["blog"])
            if blog["mode"] == "package":
                self.assertRegex(config, rf"(?m)^\s*-\s*{re.escape(blog['state']['history'])}\s*$", blog["key"])

    def test_the_history_file_the_registry_points_at_exists_and_reads_as_a_json_list(self):
        """러너는 이력 파일이 JSON 배열이 아니면 멈춘다(`read_json_list` — 깨진 이력으로 조용히 이어 가지 않는다, 감시는 STATE_CORRUPT).
        채널이 처음 켜질 때 커밋된 이력 파일이 그 모양인지 못 박는다(봇이 항목을 더해도 배열이다)."""
        for spec in CHANNELS.values():
            blog = next(b for b in REGISTRY["blogs"] if b["key"] == spec["blog"])
            path = REAL / blog["state"]["history"]
            self.assertTrue(path.is_file(), blog["key"])
            self.assertIsInstance(read_json_list(path), list, blog["key"])

    def test_the_real_registry_labels_and_keys_are_unique_across_all_blogs(self):
        keys = [b["key"] for b in REGISTRY["blogs"]]
        labels = [b["channel"]["label"] for b in REGISTRY["blogs"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(labels), len(set(labels)))


if __name__ == "__main__":
    unittest.main()
