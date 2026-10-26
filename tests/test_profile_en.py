"""영문 Blogger 프로필(blogger_practical_en)·영어 프롬프트·레지스트리 전환 시험.

`blogger_macat`(macat0722)은 영문 블로그다. 레지스트리가 영문 프로필·영어 프롬프트를 가리키고, `mode`는 off 그대로다(켜는 것은
운영자 승인 T3). 실제 레지스트리는 건드리지 않고, 임시 저장소(make_root(lang="en"))에서 가짜 LLM으로 한 편을 끝까지 돌려
통과·탈락 경로를 확인한다. 네트워크를 쓰지 않는다.
"""
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date

import _bootstrap  # noqa: F401
from pipeline import gates, plan, registry, stubs, topics
from pipeline import run as run_mod
from pipeline.stubs import stub_llm
from test_run import NO_PUBLISH, NOW, make_root

REAL = _bootstrap.ROOT
EN = registry.load_profile("blogger_practical_en")
KO = registry.load_profile("blogger_practical_ko")

# 실제 이력의 제목(2026-10-26 기준). 영어 시드가 이런 제목과 겹쳐 교차 중복(0.6)으로 걸러지지 않는지 본다
CHANCE_EN_TITLES = [
    "Beyond Reactive Dashboards: Deconstructing OnePredict’s Vision of the ‘AI-Native Factory’",
    "Opening the Lab Doors: How KIMM’s Manufacturing AI Open Lab Bridges the Shop-Floor Gap",
    "Crossing Air and Water: How MIT and EPFL Are Translating Seabird Physics into Bio-Robotics",
    "From the Cleanroom to the Stage: Why Chip Designers Are Speaking Directly to Consumers",
    "Why an AI Left on a Virtual Island Invented Basketball: MIT’s Exploration of Machine Play",
    "Bill Gates on the 20-Year Horizon: The Societal Costs of Intellectual and Physical AI Superiority",
    "It’s a bird, it’s a plane … it’s a robo-puffin?",
    "From Chip Lab to Center Stage",
]
CHANCE_KR_TITLES = [
    "대시보드를 넘어 물리 법칙으로: 원프레딕트가 제시한 ‘AI 네이티브 팩토리’의 본질",
    "빌 게이츠의 ‘20년 경고’: AI의 지적·신체적 추월이 던지는 사회적 비용",
    "‘벽돌’의 공포에서 해방될까: 엔비디아 VBIOS 무플래싱 수정 소식이 던진 하드웨어 해킹의 미래",
]
MACAT_KO_HISTORY = [  # 영문 전환 전에 쌓인 한국어 이력(topic·title) — 같은 파일을 영문 글이 이어서 쓴다
    ("피곤할 때 에너지 올리는 간단한 방법", "점심만 지나면 골골? 피곤할 때 에너지를 올리는 간단한 습관 4가지"),
    ("감사 메모 3줄 쓰기로 하루 마무리하는 방법", "잠들기 전 3분, 마음을 편안하게 정리하는 감사 메모 3줄 쓰기 방법"),
    ("재택근무 책상 자세 가볍게 점검하는 체크리스트", "재택근무 중 찌뿌둥한 몸을 깨우는 책상 자세 체크리스트 4가지"),
    ("잠이 안 올 때 바로 해볼 수 있는 간단한 방법", "잠이 안 올 때 침대에서 바로 해보는 4가지 간단한 방법"),
    ("계단 오르기로 일상에 움직임 더하는 방법", "바쁜 하루, 계단 오르기로 가볍게 움직임 채우는 4가지 방법"),
]


# 실제 Gemini 글처럼 쓴 영어 표본 두 편: 굽은 따옴표·엔/엠 대시·숫자 범위·건강 느낌의 일상 낱말(수면·자세·눈 피로·긴장)이 들어 있다. 게이트를 통과해야 한다.
POST_1 = """Title: A Calming Wind-Down Routine for the Hour Before Bed
Labels: sleep, evening routine, habits
Content:
<p>You know the feeling: the day is technically over, but your mind hasn’t gotten the memo. Emails keep replaying, the TV is still on, and bedtime slips later and later. A short, repeatable wind-down routine can help your evening feel like a gentle runway instead of a cliff. Here’s a simple one you can build in about an hour — no special equipment needed, just a little planning and a few small choices.</p>
<h3>1. Pick a “lights-down” time and protect it</h3>
<p>Choose a time about 60 minutes before you want to be asleep and treat it like an appointment with yourself. When the alarm goes off, switch the big overhead lights for a lamp or two. Softer light signals to your brain that the day is winding down, and it makes the whole room feel calmer. If other people share your space, tell them what you’re doing; a quiet household makes the habit much easier to keep.</p>
<h3>2. Give your phone a bedtime of its own</h3>
<p>Scrolling is one of the easiest ways to stay wired. Set your phone on a charger across the room, ideally outside arm’s reach, and let it “go to bed” 30–45 minutes before you do. If you like having an alarm, buy a simple clock for a few dollars and keep the phone in another room. On the first few nights it may feel strange, but most people stop reaching for it surprisingly quickly once the evening has other things to enjoy.</p>
<h3>3. Do a ten-minute reset of your space</h3>
<p>Clear the surfaces you’ll see first tomorrow morning: the kitchen counter, your desk, the nightstand. Put clothes for tomorrow on a chair and set out your water bottle. Many people find that a tidy room makes it easier to relax, because there’s nothing left “shouting” for attention. A timer helps here — when it rings, stop, even if the room isn’t perfect.</p>
<h3>4. Add one slow, enjoyable activity</h3>
<p>Read a few pages of a paper book, stretch gently on the floor, or sip a caffeine-free herbal tea while you listen to quiet music. The goal isn’t to be productive — it’s to do something low-effort that you actually look forward to. Keep it consistent so your body starts to recognize the pattern, and swap activities freely when you get bored. A warm shower or a few slow breaths can fit in here too.</p>
<h3>5. Park tomorrow’s worries on paper</h3>
<p>If your head is busy, jot down three things you want to remember tomorrow, plus one thing that went well today. Writing them down gives your thoughts somewhere to go, so you’re not holding them all in your head while you try to drift off. Keep the notebook and pen where you can reach them without turning on a bright light.</p>
<h3>Tonight’s mini checklist</h3>
<ul>
<li><strong>Set a lights-down time:</strong> about an hour before bed</li>
<li><strong>Charge your phone away from the bed:</strong> 30–45 minutes before sleep</li>
<li><strong>Tidy one small area:</strong> surfaces and tomorrow’s clothes</li>
<li><strong>Choose one calm activity:</strong> reading, stretching, or quiet music</li>
<li><strong>Write a three-line note:</strong> tomorrow’s to-dos and one win</li>
</ul>
<p>You don’t have to do everything at once. Try one or two steps this week and add more when they start to feel natural. Everyone’s evenings look different, so adjust the timing to fit your life, and if you have specific health concerns, it’s always a good idea to talk with a healthcare professional before changing your routine. What’s the first small step you’ll try tonight?</p>
"""

POST_2 = """Title: A Quick Desk Posture Checklist for Remote Workers
Labels: posture, desk setup, remote work
Content:
<p>Working from home often means working from the couch, the kitchen table, or a chair that was never meant for eight hours of typing. By mid-afternoon your neck feels stiff, your shoulders creep up toward your ears, and your eyes feel tired. The good news is that a few small adjustments — and a handful of tiny movement breaks — can make a desk day feel noticeably easier. Use this quick checklist whenever you sit down, and treat it as a starting point rather than a rulebook.</p>
<h3>1. Check your screen height</h3>
<p>The top of your screen should sit at or just below eye level, about an arm’s length away. If you use a laptop, a stack of books or a simple stand plus a separate keyboard does the trick. When the screen is too low, you tend to hunch forward without noticing, and your neck ends up doing extra work all day. Try the adjustment for a few days before deciding whether it suits you.</p>
<h3>2. Set your chair and feet</h3>
<p>Aim for feet flat on the floor and knees roughly level with your hips. If your feet dangle, a sturdy box or a footrest helps. Sit back so your lower back is supported — a small rolled towel works well if your chair doesn’t have much support. Little changes like these often make long calls and deep-focus sessions more comfortable.</p>
<h3>3. Relax your shoulders and wrists</h3>
<p>Let your elbows rest close to your body at about a 90-degree angle. Keep your wrists in a comfortable, neutral line instead of bent up or down. Every so often, roll your shoulders back and let them drop away from your ears. A quick shake-out of the hands between emails can also feel good after a long stretch of typing.</p>
<h3>4. Follow the 20-20-20 habit</h3>
<p>Every 20 minutes, look at something about 20 feet away for 20 seconds. It’s an easy way to give your eyes a short break from the screen, and it doubles as a reminder to check your posture. A repeating timer on your phone or computer makes the habit nearly automatic after a week or two.</p>
<h3>5. Move a little every hour</h3>
<p>Stand up, walk to the window, refill your water bottle, or do three slow neck turns in each direction. Even a one- or two-minute pause can feel refreshing, and it keeps you from sitting in the same position all afternoon. If something hurts or feels dizzy, stop and rest. Pairing the pause with something you already do, like making tea, helps it stick.</p>
<h3>Your two-minute desk checklist</h3>
<ul>
<li><strong>Screen:</strong> top at eye level, arm’s length away</li>
<li><strong>Chair:</strong> feet flat, back supported, knees near hip height</li>
<li><strong>Arms:</strong> elbows close, wrists straight, shoulders loose</li>
<li><strong>Eyes:</strong> 20-20-20 every 20 minutes</li>
<li><strong>Movement:</strong> stand, stretch, or walk every hour</li>
</ul>
<p>Small tweaks add up, so don’t worry about getting everything perfect today. Pick one item from the list, try it for a week, and then add another. If you ever have questions about your own body or setup, a physician or physical therapist can give advice that fits you. Which part of your desk setup will you adjust first?</p>
"""


class RealRegistryEnglishTest(unittest.TestCase):
    """blogger_macat 항목만 영문 프로필로 전환됐고, 모드·시크릿 이름·일정은 그대로다."""

    def blog(self):
        return registry.get_blog(registry.load_registry(), "blogger_macat")

    def test_registry_validates_and_points_at_the_english_profile_and_prompt(self):
        reg = registry.load_registry()
        self.assertEqual(registry.validate_registry(reg), [])
        blog = self.blog()
        self.assertEqual((blog["profile"], blog["prompt"], blog["languages"]),
                         ("blogger_practical_en", ".github/editorial/BLOGGER_PROMPT_EN.md", ["en"]))
        self.assertEqual(blog["role"], "생활 습관 실용형 (EN)")
        self.assertEqual(registry.load_profile(blog["profile"])["language"], "en")

    def test_mode_is_still_off_and_nothing_else_about_publishing_changed(self):
        blog = self.blog()
        self.assertEqual(blog["mode"], "off")  # 켜는 것은 T3(운영자 채팅 승인)와 시크릿 등록(운영자)이 끝난 뒤의 별도 변경이다
        self.assertEqual(blog["secrets"], {"llm_api_key": "GEMINI_API_KEY", "blog_id": "BLOGGER_BLOG_ID", "client_id": "BLOGGER_CLIENT_ID",
                                            "client_secret": "BLOGGER_CLIENT_SECRET", "refresh_token": "BLOGGER_REFRESH_TOKEN"})
        self.assertEqual((blog["platform"], blog["url"], blog["workflow"], blog["entrypoint"]),
                         ("blogger", "https://macat0722.blogspot.com/", ".github/workflows/blogger.yml", "blogger_generator.py"))
        self.assertEqual((blog["schedule"], blog["limits"], blog["state"]),
                         ({"cron": "0 2 * * *"}, {"max_posts_per_day": 1},
                          {"history": "blogger_history.json", "content_dir": "_blogger_drafts"}))
        self.assertEqual(registry.get_blog(registry.load_registry(), "chance")["languages"], ["ko", "en"])  # Chance 항목은 그대로

    def test_the_korean_profile_and_prompt_are_kept_for_a_future_korean_blog(self):
        self.assertTrue((REAL / "pipeline" / "profiles" / "blogger_practical_ko.json").exists())
        self.assertTrue((REAL / ".github" / "editorial" / "BLOGGER_PROMPT.md").exists())
        self.assertEqual(registry.validate_profile(KO), [])
        self.assertEqual(KO["language"], "ko")

    def test_plan_skips_the_blog_while_off_and_keeps_the_same_matrix_shape_when_enabled(self):
        reg = registry.load_registry()
        self.assertEqual(plan.build_matrix(reg, "blogger"), {"include": []})
        reg["blogs"][1]["mode"] = "draft"
        item = plan.build_matrix(reg, "blogger")["include"][0]
        self.assertEqual(item["key"], "blogger_macat")
        self.assertEqual(item["secret_blog_id"], "BLOGGER_BLOG_ID")

    def test_a_profile_language_that_is_not_among_the_blog_languages_is_a_registry_error(self):
        """D-32 재발 방지: 영문 블로그에 한국어 프로필을 쓰거나 languages 만 고쳐 놓으면 레지스트리 검증(REG-1)이 막는다."""
        reg = registry.load_registry()
        reg["blogs"][1]["profile"] = "blogger_practical_ko"
        errors = registry.validate_registry(reg)
        self.assertTrue(any("blogger_macat" in e and "language('ko')" in e and "['en']" in e for e in errors), errors)
        reg = registry.load_registry()
        reg["blogs"][1]["languages"] = ["ko"]
        errors = registry.validate_registry(reg)
        self.assertTrue(any("blogger_practical_en" in e and "language('en')" in e for e in errors), errors)
        reg["blogs"][1]["profile"] = "blogger_practical_ko"          # 둘 다 한국어면 통과
        self.assertEqual(registry.validate_registry(reg), [])
        reg["blogs"][1]["languages"] = ["ko", "en"]                  # 여러 언어 블로그는 그중 하나면 된다
        self.assertEqual(registry.validate_registry(reg), [])

    def test_the_real_dry_run_is_skipped_because_the_mode_is_off(self):
        out = []
        code = run_mod.run(["--blog", "blogger_macat", "--dry-run"], environ={}, now=NOW, out=out.append)
        self.assertEqual(code, 0)
        self.assertIn("[SKIP] code=MODE_OFF blog=blogger_macat", "\n".join(out))

    def test_the_command_line_entry_point_agrees(self):
        # 환경은 그대로 두되 러너의 동작을 바꾸는 변수(일시정지·연습·시크릿)만 뺀다. 이 환경에서는 PATH·라이브러리 경로가 필요하다
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PIPELINE_", "BLOGGER_", "GEMINI", "UNSPLASH", "GITHUB_"))
               and k != "DRY_RUN"}
        env["PYTHONUTF8"] = "1"
        proc = subprocess.run([sys.executable, "-m", "pipeline.run", "--blog", "blogger_macat", "--dry-run"], cwd=str(REAL),
                              capture_output=True, text=True, encoding="utf-8", timeout=120, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[SKIP] code=MODE_OFF", proc.stdout)
        self.assertNotIn("DRY_RUN", proc.stdout)


class EnglishProfileTest(unittest.TestCase):
    def test_profile_is_valid_english_and_has_the_same_shape_as_the_korean_one(self):
        self.assertEqual(registry.validate_profile(EN), [])
        self.assertEqual((EN["name"], EN["language"]), ("blogger_practical_en", "en"))
        for key in ("length", "title", "structure", "labels", "similarity", "topic_cooldown_days", "max_attempts", "allow_links"):
            self.assertIn(key, EN)
        self.assertEqual((EN["structure"], EN["similarity"], EN["topic_cooldown_days"], EN["max_attempts"], EN["allow_links"]),
                         (KO["structure"], KO["similarity"], KO["topic_cooldown_days"], KO["max_attempts"], KO["allow_links"]))
        self.assertEqual(set(EN) - {"min_latin_ratio", "topic_expand_prompt"}, set(KO) - {"min_hangul_ratio"})

    def test_length_title_and_label_limits_are_the_english_equivalents(self):
        self.assertLess(EN["length"]["min_chars"], EN["length"]["max_chars"])
        self.assertGreater(EN["length"]["min_chars"], KO["length"]["min_chars"])  # 영어는 같은 분량을 더 많은 글자로 쓴다
        self.assertEqual((EN["title"]["min_chars"], EN["title"]["max_chars"]), (15, 70))
        self.assertEqual((EN["labels"]["min"], EN["labels"]["max"]), (KO["labels"]["min"], KO["labels"]["max"]))

    def test_disclosure_says_ai_assisted_general_reference_not_a_substitute_and_see_a_professional(self):
        html = EN["disclosure_html"]
        self.assertTrue(html.startswith("<p><em>") and html.endswith("</em></p>"))
        text = gates.plain_text(html).lower()
        for fragment in ("with the help of ai", "general", "for reference", "does not replace", "medical advice, diagnosis, or treatment",
                         "doctor", "qualified professional"):
            self.assertIn(fragment, text)
        self.assertFalse(re.search(r"[가-힣]", html))

    def test_prompt_extra_is_english_and_repeats_the_safety_rules(self):
        joined = " ".join(EN["prompt_extra"]).lower()
        for fragment in ("never claim", "medications", "supplements", "pregnancy", "infants", "weight loss", "dieting", "liver health", "never invent",
                         "personal experiences", "only the title, labels and content"):
            self.assertIn(fragment, joined)
        self.assertFalse(re.search(r"[가-힣]", joined))

    def test_every_gate_list_is_populated_and_english(self):
        for field in ("banned_patterns", "title_banned_patterns", "leak_patterns", "banned_topic_patterns", "body_banned_patterns",
                      "body_safe_patterns"):
            self.assertGreaterEqual(len(EN[field]), 4, field)
            self.assertFalse(any(re.search(r"[가-힣]", p) for p in EN[field] if field != "leak_patterns"), field)

    def test_the_english_profile_loads_through_the_registry_loader(self):
        self.assertEqual(registry.load_profile("blogger_practical_en"), EN)


class EnglishPromptTest(unittest.TestCase):
    def setUp(self):
        self.blog = registry.get_blog(registry.load_registry(), "blogger_macat")
        self.template = run_mod.load_prompt_template(REAL, self.blog)

    def test_template_loads_with_the_topic_placeholder_on_its_own_line(self):
        self.assertIn("{topic}", self.template)
        self.assertTrue(re.search(r"^Topic: \{topic\}$", self.template, re.M))
        self.assertEqual(len(re.findall(r"\{topic\}", self.template)), 1)

    def test_template_is_english_with_english_output_markers(self):
        self.assertFalse(re.search(r"[가-힣]", self.template))
        for marker in ("Title: (title)", "Labels: (comma-separated", "Content:"):
            self.assertIn(marker, self.template)

    def test_template_keeps_the_same_safety_rules_as_the_korean_prompt(self):
        lower = self.template.lower()
        for fragment in ("do not claim any health outcome", "may help", "diseases, treatments, medications, supplements, dosages, diagnoses, "
                         "health measurements such as blood pressure or blood sugar, pregnancy, infants, weight loss, dieting or liver health",
                         "never invent personal experiences", "do not add disclaimers",
                         "<h3>", "<ul>", "checklist", "600-900 words", "no markdown"):
            self.assertIn(fragment, lower)

    def test_the_stub_title_and_topic_survive_the_prompt_round_trip(self):
        prompt = run_mod.build_prompt(self.template, "A calm evening walk", EN)
        text, _ = stub_llm(prompt)
        self.assertTrue(text.startswith("Title: A calm evening walk"))
        for line in EN["prompt_extra"]:
            self.assertIn(line, prompt)

    def test_the_retry_feedback_reaches_the_prompt(self):
        prompt = run_mod.build_prompt(self.template, "A calm evening walk", EN, feedback=["[TITLE_TOPIC] ... 'weight loss'"])
        self.assertIn("[TITLE_TOPIC] ... 'weight loss'", prompt)

    def test_the_prompt_file_is_a_plain_markdown_file_the_registry_accepts(self):
        text = (REAL / ".github" / "editorial" / "BLOGGER_PROMPT_EN.md").read_text(encoding="utf-8")
        self.assertNotIn("{{", text)  # Liquid 구문 금지(검증기 LIQUID-1)
        self.assertNotIn("{%", text)


class RealisticPostTest(unittest.TestCase):
    """글 모양이 실제와 같은 영어 표본이 게이트 전체를 통과하고(오탐 없음), 위험 문장 하나가 끼면 탈락한다."""

    @staticmethod
    def parsed(raw):
        parsed = gates.parse_labeled_post(raw)
        clean, stats = gates.sanitize_html(parsed["content"])
        return {"title": parsed["title"], "labels": parsed["labels"], "content": clean}, stats

    def test_each_realistic_post_passes_the_whole_gate(self):
        for raw in (POST_1, POST_2):
            post, stats = self.parsed(raw)
            self.assertGreater(gates.text_length(gates.plain_text(post["content"])), EN["length"]["min_chars"])
            result = gates.check_post(post, EN, [], [], stats)
            self.assertTrue(result.ok, (post["title"], result.reasons))
            self.assertEqual(result.warnings, [])

    def test_a_single_risky_sentence_in_a_realistic_post_is_rejected_with_the_word(self):
        for old, new, word in (("Read a few pages of a paper book,", "Take a magnesium supplement, read a few pages of a paper book,", "supplement"),
                               ("It’s an easy way to give your eyes", "It lowers your blood pressure and is an easy way to give your eyes", "blood pressure")):
            raw = POST_1.replace(old, new) if word == "supplement" else POST_2.replace(old, new)
            self.assertNotEqual(raw, POST_1 if word == "supplement" else POST_2)
            post, stats = self.parsed(raw)
            result = gates.check_post(post, EN, [], [], stats)
            self.assertEqual(result.codes(), ["BODY_TOPIC"], result.reasons)
            self.assertIn(f"'{word}'", result.reasons[0])

    def test_realistic_posts_are_saved_as_drafts_by_the_runner(self):
        for raw in (POST_1, POST_2):
            with tempfile.TemporaryDirectory() as tmp:
                root = make_root(tmp, mode="draft", lang="en")
                out = []
                code = run_mod.run(["--blog", "blogger_macat", "--root", str(root)], environ=dict(NO_PUBLISH), now=NOW,
                                   llm=lambda prompt, text=raw: (text, "m"), rng=random.Random(1), out=out.append)
                self.assertEqual(code, 0, "\n".join(out))
                history = json.loads((root / "blogger_history.json").read_text(encoding="utf-8"))
                self.assertEqual((history[-1]["status"], history[-1]["attempts"]), ("draft", 1))
                draft = next((root / "_blogger_drafts").glob("*.md")).read_text(encoding="utf-8")
                self.assertIn(EN["disclosure_html"], draft)
                self.assertIn("<h3>", draft)

class StubAndExpandPromptTest(unittest.TestCase):
    def test_the_english_stub_is_chosen_by_the_prompt_and_korean_prompts_still_get_korean(self):
        english, _ = stub_llm("Topic: A calm evening walk")
        self.assertTrue(english.startswith("Title: ") and "\nLabels: " in english and "\nContent:\n" in english)
        korean, _ = stub_llm("주제: 출근 전 10분 가볍게 몸 깨우는 아침 루틴")
        self.assertTrue(korean.startswith("제목: "))
        self.assertEqual(korean, stubs.stub_post("출근 전 10분 가볍게 몸 깨우는 아침 루틴"))

    def test_a_topic_line_in_the_middle_of_a_korean_prompt_does_not_switch_the_language(self):
        korean, _ = stub_llm("주제: 가벼운 스트레칭 루틴\n\n[추가 규칙]\n- 예: Topic: x")
        self.assertTrue(korean.startswith("제목: "))

    def test_the_english_topic_expansion_stub_answers_a_json_array_of_safe_topics(self):
        prompt = topics.expand_prompt(EN, [], 8)
        reply, model = stub_llm(prompt)
        self.assertEqual(model, "stub")
        proposed = topics.parse_topic_list(reply)
        self.assertGreaterEqual(len(proposed), 3)
        for topic in proposed:
            self.assertTrue(gates.topic_allowed(topic, EN) and topics.TOPIC_MIN_CHARS <= len(topic) <= topics.TOPIC_MAX_CHARS, topic)

    def test_english_expand_prompt_fills_every_placeholder(self):
        prompt = topics.expand_prompt(EN, ["A calm walk after dinner", "Desk stretches"], 6)
        self.assertNotIn("{", prompt)
        self.assertIn("Suggest 6 gentle lifestyle topics", prompt)
        self.assertIn("(8-60 characters)", prompt)
        self.assertIn("- A calm walk after dinner\n- Desk stretches", prompt)
        self.assertIn("JSON array of strings", prompt)
        self.assertIn("weight loss", prompt)
        self.assertIn("- (none)", topics.expand_prompt(EN, [], 8))
        self.assertFalse(re.search(r"[가-힣]", topics.expand_prompt(EN, [], 8)))

    def test_english_stub_titles_stay_inside_the_title_limit_for_every_seed_and_long_override_topics(self):
        for topic in EN["seed_topics"] + ["x" * 60, "A very long override topic " * 3]:
            text, _ = stubs.stub_llm("Topic: " + topic)
            title = gates.parse_labeled_post(text)["title"]
            self.assertLessEqual(len(title), max(EN["title"]["max_chars"], len(topic)), topic)


class EnglishFlowTest(unittest.TestCase):
    """임시 저장소(mode draft, 실제 레지스트리 그대로의 영문 프로필)에서 한 편을 끝까지 돌린다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_root(tmp.name, mode="draft", lang="en")

    def go(self, env=None, llm=stub_llm, extra=(), now=NOW, seed=1):
        out = []
        code = run_mod.run(["--blog", "blogger_macat", "--root", str(self.root), *extra], environ=dict(env or {}), now=now, llm=llm,
                           rng=random.Random(seed), out=out.append)
        return code, "\n".join(out)

    def history(self):
        path = self.root / "blogger_history.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def drafts(self):
        folder = self.root / "_blogger_drafts"
        return sorted(folder.glob("*.md")) if folder.exists() else []

    def stub_with(self, prompt, replace=None, title=None, extra_paragraph=None):
        text, model = stub_llm(prompt)
        if replace:
            text = text.replace(*replace)
        if title:
            text = re.sub(r"^Title: .*$", f"Title: {title}", text, flags=re.M)
        if extra_paragraph:
            text = text.replace("<h3>A short checklist to try today</h3>", f"<p>{extra_paragraph}</p>\n<h3>A short checklist to try today</h3>")
        return text, model

    def scripted(self, *makers):
        prompts = []

        def llm(prompt):
            prompts.append(prompt)
            maker = makers[min(len(prompts), len(makers)) - 1]
            return maker(prompt)
        llm.prompts = prompts
        return llm

    def test_the_default_stub_runs_a_dry_run_end_to_end_in_english(self):
        before = {p for p in self.root.rglob("*")}
        code, out = self.go(extra=["--dry-run"], llm=None)
        self.assertEqual(code, 0, out)
        self.assertIn("[DRY_RUN] 게이트 통과", out)
        self.assertNotRegex(out, r"주제\(seed\): [가-힣]")
        self.assertEqual({p for p in self.root.rglob("*")}, before)  # 연습 실행은 아무것도 쓰지 않는다

    def test_a_draft_run_saves_an_english_draft_with_the_english_disclosure(self):
        code, out = self.go(env=NO_PUBLISH)
        self.assertEqual(code, 0, out)
        entry = self.history()[-1]
        self.assertEqual((entry["status"], entry["topic_source"], entry["attempts"]), ("draft", "seed", 1))
        self.assertIn(entry["topic"], EN["seed_topics"])
        self.assertLessEqual(len(entry["title"]), EN["title"]["max_chars"])
        draft = self.drafts()[0].read_text(encoding="utf-8")
        self.assertIn(EN["disclosure_html"], draft)
        self.assertFalse(re.search(r"[가-힣]", draft.split("---", 2)[2]))  # 본문·면책 모두 영어
        self.assertEqual(draft.count("<h3>") >= 3, True)

    def test_the_disclosure_is_added_after_the_gate_so_its_risk_words_never_fail_a_post(self):
        code, _ = self.go(env=NO_PUBLISH)
        self.assertEqual(code, 0)
        final = self.drafts()[0].read_text(encoding="utf-8")
        plain = gates.plain_text(final.split("---", 2)[2])
        self.assertIn("diagnosis", plain)  # 면책 문구의 위험 낱말은 게시본에 있다
        self.assertEqual(gates.body_risk_hit(plain, EN), (None, None))  # 면책·상담 문장이라 본문 검사에서도 건너뛴다

    def test_a_risky_title_is_rejected_every_time_and_the_word_is_fed_back(self):
        llm = self.scripted(lambda p: self.stub_with(p, title="Foods That Lower Blood Pressure Quickly"))
        code, out = self.go(env=NO_PUBLISH, llm=llm)
        self.assertEqual(code, 0)
        entry = self.history()[-1]
        self.assertEqual((entry["status"], entry["attempts"]), ("rejected", 3))
        self.assertIn("TITLE_TOPIC", json.dumps(entry["reasons"]))
        self.assertEqual(self.drafts(), [])
        self.assertIn("[SKIP] code=GATE_REJECTED", out)
        self.assertEqual(len(llm.prompts), 3)
        self.assertIn("[TITLE_TOPIC]", llm.prompts[1])
        self.assertIn("'Blood Pressure'", llm.prompts[1])

    def test_a_risky_body_then_a_clean_body_is_accepted_on_the_second_attempt(self):
        llm = self.scripted(lambda p: self.stub_with(p, extra_paragraph="Melatonin before bed can help you fall asleep faster."), stub_llm)
        code, out = self.go(env=NO_PUBLISH, llm=llm)
        self.assertEqual(code, 0, out)
        entry = self.history()[-1]
        self.assertEqual((entry["status"], entry["attempts"]), ("draft", 2))
        self.assertIn("[BODY_TOPIC]", llm.prompts[1])
        self.assertIn("'Melatonin'", llm.prompts[1])
        self.assertNotIn("Melatonin", self.drafts()[0].read_text(encoding="utf-8"))

    def test_a_professional_referral_in_the_body_is_not_a_reason_to_reject(self):
        hedge = "If you have any health concerns or take medication, talk to your doctor before changing your routine."
        llm = self.scripted(lambda p: self.stub_with(p, extra_paragraph=hedge))
        code, out = self.go(env=NO_PUBLISH, llm=llm)
        self.assertEqual(code, 0, out)
        entry = self.history()[-1]
        self.assertEqual((entry["status"], entry["attempts"]), ("draft", 1))
        self.assertIn(hedge, self.drafts()[0].read_text(encoding="utf-8"))

    def test_the_same_words_without_a_referral_are_rejected(self):
        llm = self.scripted(lambda p: self.stub_with(p, extra_paragraph="If you have high blood pressure, avoid this routine."))
        self.go(env=NO_PUBLISH, llm=llm)
        entry = self.history()[-1]
        self.assertEqual((entry["status"], entry["attempts"]), ("rejected", 3))
        self.assertIn("BODY_TOPIC", json.dumps(entry["reasons"]))

    def test_an_efficacy_claim_is_rejected_even_next_to_a_referral(self):
        llm = self.scripted(lambda p: self.stub_with(p, extra_paragraph="Ask your doctor, but this habit is a miracle for tired mornings."))
        self.go(env=NO_PUBLISH, llm=llm)
        self.assertIn("BANNED", json.dumps(self.history()[-1]["reasons"]))

    def test_a_korean_answer_for_the_english_blog_is_rejected_by_the_language_gate(self):
        llm = self.scripted(lambda p: (stubs.stub_post("출근 전 10분 가볍게 몸 깨우는 아침 루틴"), "m"))
        self.go(env=NO_PUBLISH, llm=llm)
        entry = self.history()[-1]
        self.assertEqual(entry["status"], "rejected")
        self.assertIn("[LANG]", json.dumps(entry["reasons"], ensure_ascii=False))
        self.assertEqual(self.drafts(), [])

    def test_a_manual_topic_with_a_banned_word_stops_before_any_llm_call(self):
        """수동 topic(override)도 금지 주제 목록을 통과해야 한다(D-64 ⑥ c): 걸리면 Gemini 를 부르기 전에 종료 2(TOPIC_BLOCKED), 이력·초안 없음.
        (예전에는 이 검사가 없어 제목 가드레일이 뒤늦게 3번 탈락시켰다.) 제목·본문 가드레일은 그 뒤의 두 번째 방어선으로 남는다."""
        llm = self.scripted(lambda p: self.stub_with(p))
        code, out = self.go(env=NO_PUBLISH, extra=["--topic", "Fast weight loss tips for busy people"], llm=llm)
        self.assertEqual(code, 2, out)
        self.assertIn("[SKIP] code=TOPIC_BLOCKED", out)
        self.assertEqual((llm.prompts, self.history(), self.drafts()), ([], [], []))

    def test_a_manual_safe_topic_runs_normally(self):
        code, _ = self.go(env=NO_PUBLISH, extra=["--topic", "A calm ten-minute walk after dinner"])
        self.assertEqual(code, 0)
        entry = self.history()[-1]
        self.assertEqual((entry["status"], entry["topic_source"]), ("draft", "override"))

    def test_when_the_seeds_run_out_the_english_expansion_prompt_is_used_and_filtered(self):
        (self.root / "blogger_history.json").write_text(
            json.dumps([{"topic": t, "date": "2026-10-20", "status": "posted"} for t in EN["seed_topics"]]), encoding="utf-8")
        proposals = json.dumps(["Detox water recipes", "Prescription-free ways to sleep better", "short",
                                "A calm ten-minute walk after dinner"])

        def expansion(prompt):
            return proposals, "m"
        llm = self.scripted(expansion, stub_llm)
        code, out = self.go(env=NO_PUBLISH, llm=llm)
        self.assertEqual(code, 0, out)
        self.assertIn("JSON array of strings", llm.prompts[0])
        self.assertIn("Topic: A calm ten-minute walk after dinner", llm.prompts[1])
        entry = self.history()[-1]
        self.assertEqual((entry["status"], entry["topic_source"], entry["topic"]), ("draft", "llm", "A calm ten-minute walk after dinner"))

    def test_korean_history_left_from_before_the_switch_does_not_block_english_seeds_or_posts(self):
        entries = [{"v": 1, "blog": "blogger_macat", "date": "2026-10-2%d" % (1 + i), "status": "generated_unpublished", "topic": topic,
                    "title": title, "labels": ["건강"], "attempts": 1} for i, (topic, title) in enumerate(MACAT_KO_HISTORY)]
        (self.root / "blogger_history.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        code, out = self.go(env=NO_PUBLISH, now=NOW.replace(day=27))
        self.assertEqual(code, 0, out)
        self.assertEqual([e["status"] for e in self.history()], ["generated_unpublished"] * 5 + ["draft"])
        self.assertIn(self.history()[-1]["topic"], EN["seed_topics"])

    def test_no_english_seed_is_filtered_out_by_the_cross_blog_or_korean_history_checks(self):
        avoid = CHANCE_EN_TITLES + CHANCE_KR_TITLES + [item for pair in MACAT_KO_HISTORY for item in pair]
        history = [{"topic": topic, "date": "2026-10-21"} for topic, _ in MACAT_KO_HISTORY]
        for seed in EN["seed_topics"]:
            with self.subTest(seed):
                self.assertTrue(topics._acceptable(seed, EN, history, date(2026, 10, 27), avoid), seed)

    def test_the_other_blog_titles_the_runner_collects_include_the_chance_titles_in_both_languages(self):
        """교차 중복은 문자열 비교라 언어가 달라도 동작한다. 영어 글은 Chance 영어 제목과 견주고, 한글 제목과는 거의 겹치지 않는다."""
        sample = "A Gentle Evening Routine for Better Sleep"
        score, _ = gates.most_similar(sample, CHANCE_EN_TITLES)
        self.assertLess(score, EN["similarity"]["other_blogs"])
        self.assertEqual(gates.most_similar(sample, CHANCE_KR_TITLES)[0] < 0.3, True)
        self.assertGreaterEqual(gates.most_similar("From Chip Lab to Center Stage", CHANCE_EN_TITLES)[0], 1.0)  # 같은 영어 제목은 잡는다


if __name__ == "__main__":
    unittest.main()
