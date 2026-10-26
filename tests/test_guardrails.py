"""주제 가드레일(docs/SECURITY_GUARDRAILS.md G-C4) 시험.

같은 위험 영역(질병·치료·약·보충제·진단·임신·영유아·체중 감량)을 세 곳에서 막는다.
  (a) 주제 후보(시드·LLM 확장)  (b) 생성된 제목·라벨  (c) 생성된 본문
영문 프로필(blogger_practical_en)은 한국어 프로필(blogger_practical_ko)과 같은 엄격함의 영어판이다.
오탐(정상 글이 탈락)도 같은 무게로 고정한다: 재시도 3회가 모두 탈락하면(ALL_REJECTED) 그날 발행을 잃는다.
네트워크를 쓰지 않는다.
"""
import copy
import json
import random
import re
import unicodedata
import unittest
from datetime import date

import _bootstrap  # noqa: F401
from pipeline import gates, registry, stubs, topics

KO = registry.load_profile("blogger_practical_ko")
EN = registry.load_profile("blogger_practical_en")


def stub_post(profile, topic=None):
    """프로필 언어에 맞는 스텁 글(게이트를 통과하는 기준 글)과 정화 통계."""
    if profile["language"] == "en":
        text, _ = stubs.stub_llm("Topic: " + (topic or profile["seed_topics"][3]))
    else:
        text, _ = stubs.stub_llm("주제: " + (topic or profile["seed_topics"][3]))
    parsed = gates.parse_labeled_post(text)
    clean, stats = gates.sanitize_html(parsed["content"])
    return {"title": parsed["title"], "labels": parsed["labels"], "content": clean}, stats


def check(profile, mutate=None, sentence=None):
    """기준 글을 고쳐(제목·라벨·본문 끝에 문장 추가) 검사한 GateResult."""
    post, stats = stub_post(profile)
    post = copy.deepcopy(post)
    if mutate:
        post.update(mutate)
    if sentence:
        post["content"] += f"<p>{sentence}</p>"
    return gates.check_post(post, profile, [], [], stats)


# ----------------------------------------------------------------------------
# (a) 주제 후보 — 영어
# ----------------------------------------------------------------------------
FORBIDDEN_EN_TOPICS = [
    # 치료·완치·진단·처방·의료
    "Natural ways to treat insomnia at home",
    "Home treatment for a stiff back",
    "Can stretching cure back pain?",
    "Healing foods for a stronger body",
    "Home remedies for tired eyes",
    "Physical therapy exercises you can do at home",
    "How to self-diagnose posture problems",
    "Prescription-free ways to sleep better",
    "Medical advice for desk workers",
    "A guide to over-the-counter sleep aids",
    "Your first week on a new medication routine",
    "Recovery meal plan after surgery",
    "Flu shot injections: what to know",
    "Acupuncture for stress relief",
    "Five ways to treat yourself after work",
    # 질병
    "Cancer prevention habits for every day",
    "Diet tips for people with diabetes",
    "Foods that lower blood pressure",
    "Lowering cholesterol with daily walks",
    "Habits that fight depression",
    "Coping with an anxiety disorder at work",
    "What to do during a panic attack",
    "Heart disease and your daily steps",
    "Stroke risk and sitting all day",
    "Arthritis-friendly stretching",
    "Asthma and exercise at home",
    "Dementia prevention puzzles",
    "Obesity and desk jobs",
    "COVID recovery routine",
    "Migraine triggers in your kitchen",
    "Chronic pain and morning stretches",
    "Suicide prevention awareness walks",
    "How to stop self-harm urges",
    "A bipolar-friendly daily schedule",
    "Anti-inflammatory meal prep",
    "Insomnia fixes that actually work",
    # 약·보충제
    "Best magnesium supplements for sleep",
    "Melatonin: how much should you take?",
    "Vitamin D dosage for winter",
    "Is ibuprofen safe for sore muscles?",
    "Taking multivitamins every morning",
    "Pain relievers versus stretching",
    "Cutting your daily dose of caffeine",
    "Sleeping pills versus a bedtime routine",
    "CBD gummies for sleep",
    # 임신·영유아
    "Safe stretches during pregnancy",
    "Sleep schedules for newborns",
    "Prenatal yoga at home",
    "Feeding routines for infants",
    "Postpartum meal prep",
    "Toddler bedtime battles",
    "Breastfeeding-friendly snacks",
    # 체중 감량·디톡스
    "Fast weight loss tips for busy people",
    "How to lose 10 pounds in a month",
    "Fat-burning workouts at home",
    "Burn belly fat while you sleep",
    "A three-day juice cleanse",
    "Detox water recipes",
    "A crash diet that actually works",
    "Intermittent fasting for beginners",
    "Keto meal prep for the week",
    "How to boost your immune system",
    # 대소문자·굴절형
    "TREATMENT OPTIONS FOR POOR SLEEP",
    "Treating tension with stretches",
    "Cured by walking?",
    "She heals fast with this routine",
    "Diagnosing posture problems at home",
    "Prescribed rest days",
    "Diabetic-friendly snack swaps",
    "Depressed? Try this morning habit",
    "Overdose of screen time",
]

ALLOWED_EN_TOPICS = [
    # 낱말 일부가 겹치는 일상어: cure/secure·obscure·manicure·accurate, cancer/cancel·Cancun, dose/dosa, insulin/insulation,
    # pill/pillow, treat/retreat, medication/meditation, surgery/surge, patients/patience, stroke/keystrokes, infant/infantry
    "Secure your sleep schedule in three steps",
    "Obscure hobbies to try on a quiet weekend",
    "A weekend manicure and relaxation routine",
    "Accurate habit tracking with a simple notebook",
    "Cancel plans without guilt: protecting your rest",
    "Cancun trip packing list for a relaxed week",
    "Dosa and idli breakfast ideas",
    "Improve bedroom insulation for cozy winter nights",
    "Choosing a pillow for a better night's rest",
    "A weekend retreat at home",
    "Five-minute meditation breaks for a busy workday",
    "Tame the afternoon energy surge",
    "The practice of patience in daily routines",
    "Fewer keystrokes, more focus: typing breaks",
    "Cheers to a calmer commute",
    "Heart-shaped lunch box ideas",
    "Blood orange smoothie for a bright morning",
    "Beginner weight training at home",
    "Dealing with a loss of motivation",
    "Lose yourself in a good book tonight",
    "A slim wallet cleanout checklist",
    "Quick breakfast ideas for school mornings",
    "A 15-minute kitchen cleaning routine",
    "Packing for different weather conditions",
    "Chronic procrastination and a simple timer",
    "A healthy habit of morning light",
    "Inject some color into your workspace",
    "Be patient with a brand-new habit",
    # 일상 주제
    "An easy stretching routine you can do at home",
    "A gentle morning routine for people who hate waking up",
    "How to plan a one-week walking challenge",
    "A quick desk posture checklist for remote workers",
    "Ten-minute meal ideas using what's in your fridge",
    "A Sunday evening routine for an easier Monday morning",
    "How to build a simple grocery list without overthinking",
    "Neck and shoulder stretches for long sitting days",
]

# 같은 낱말의 굴절형·대소문자. 모두 막혀야 한다.
EN_INFLECTIONS = {
    "treat": ["treat", "treats", "treated", "treating", "treatment", "treatments", "TREATMENT", "Treatment"],
    "cure": ["cure", "cures", "cured", "curing", "curable", "CURE"],
    "diagnose": ["diagnose", "diagnoses", "diagnosed", "diagnosing", "diagnosis", "diagnostic", "Diagnosis"],
    "prescribe": ["prescribe", "prescribes", "prescribed", "prescribing", "prescription", "prescriptions"],
    "supplement": ["supplement", "supplements", "supplemented", "supplementing", "supplementation", "Supplements"],
    "dose": ["dose", "doses", "dosed", "dosing", "dosage", "dosages", "DOSE", "overdose"],
    "pregnant": ["pregnant", "pregnancy", "pregnancies", "Pregnant"],
    "surgery": ["surgery", "surgeries", "surgical", "surgeon", "Surgeon"],
    "cancer": ["cancer", "cancers", "cancerous", "Cancer"],
    "diabetes": ["diabetes", "diabetic", "diabetics", "Diabetic"],
    "depression": ["depression", "depressive", "depressed", "antidepressants"],
    "suicide": ["suicide", "suicidal", "Suicidal"],
    "self-harm": ["self-harm", "self harm", "selfharm", "self-harming"],
    "weight loss": ["weight loss", "weight-loss", "weightloss", "Weight Loss"],
    "fat burn": ["fat burn", "fat-burning", "fat burner", "burn fat", "burning belly fat"],
    "detox": ["detox", "detoxes", "detoxing", "detoxification", "DETOX"],
    "infant": ["infant", "infants", "newborn", "newborns", "babies", "toddler", "toddlers"],
}

# 낱말 일부가 겹칠 뿐인 일상어(단어 경계). 하나라도 막히면 오탐이다.
EN_LOOKALIKES = ["secure", "secured", "obscure", "manicure", "pedicure", "accurate", "procure", "cancel", "canceled", "Cancun",
                 "dosa", "insulation", "insulated", "pillow", "pillows", "retreat", "street", "meditation", "surge", "patience",
                 "keystrokes", "infantry", "health", "healthy", "wheel", "cleanser", "cleaning", "breakfast", "fasten",
                 "heartbeat", "bloodstream", "diabolical", "treaty"]


# ----------------------------------------------------------------------------
# 규칙(정규식)마다 '그 규칙만 막는 표본'. RuleCoverageTest 가 모든 패턴에 자기 표본이 있는지 본다 —
# 패턴을 더하면 표본도 더하고, 지우면 표본이 남아도 괜찮다. 한 문장에 위험 낱말은 하나만 둔다.
# ----------------------------------------------------------------------------
EN_TOPIC_RULE_SAMPLES = [
    "Ways to treat your weekend like a reset", "A cure for the Sunday scaries", "Time to heal your sleep schedule",
    "A quick remedy for messy desks", "Retail therapy alternatives", "Diagnosing why your desk stays messy", "A prescribed weekly planner",
    "A medical-free weekend plan", "Laughter as the best medicine", "Daily medication reminders for your phone",
    "Packing your meds for travel", "A clinical approach to tidying", "Surgery-free weekend plans", "Injection-free weekend plans",
    "Vaccine day snack ideas", "Steroids and gym playlists", "Acupuncture clinic playlists", "Chiropractic visit playlists",
    "Disease-proof weekend plans", "Symptoms of a cluttered desk", "Chronic pain and planners", "Inflammation-proof lunch boxes",
    "Cancer awareness walks", "Tumor board lunch prep", "Chemo day tote bag packing", "Oncology podcasts for commutes",
    "Melanoma awareness picnic", "Diabetic-friendly snack swaps", "Insulin and lunch breaks", "Hypertension and desk work",
    "Blood pressure apps compared", "Cholesterol-free recipes", "Cardiac rehab playlists", "Depressed? Try a walk",
    "Anxiety attacks at work", "Bipolar-friendly schedules", "Mental health crisis lines", "Bulimia awareness week",
    "Suicide hotline numbers", "Insomnia and bedroom lighting", "Arthritis-friendly gardening", "Drug store checklists",
    "A pill organizer checklist", "Pharmacy pickup reminders", "Supplement shelf cleanup", "Multivitamin shelf cleanup",
    "Melatonin and bedroom lighting", "A dose of weekend calm", "A 200 mg habit", "Aspirin-free weekends", "Pregnancy-friendly desks",
    "Expecting mothers brunch ideas", "Fetal heartbeat podcasts", "Infant car seat checklist", "Weight loss journaling",
    "Lose weight tracker apps", "Fat burning playlists", "Slimming closet storage", "Keto pantry labels", "Detox your inbox",
    "Immune support recipes",
]
EN_BODY_RULE_SAMPLES = [
    "Disease risk grows with long sitting.", "Infection spreads in crowded rooms.", "Chronic fatigue can follow busy weeks.",
    "Inflammation builds up slowly.", "Cancer screenings matter.", "A tumor is a lump.", "Chemo days are tiring.",
    "Oncology wards have visiting hours.", "Melanoma risk rises with sunburn.", "Diabetic snack lists vary.", "Insulin needs timing.",
    "Hypertension runs in families.", "Blood sugar swings are common.", "Cholesterol numbers change.", "A cardiac check is wise.",
    "Depressed moods happen.", "Panic attacks feel scary.", "Dementia affects memory.", "Mental health crisis lines are open.",
    "Bulimia is serious.", "Suicide is serious.", "Insomnia can persist.", "Asthma flares in cold air.", "Treatments vary by case.",
    "A quick cure is rare.", "Therapy can take months.", "Diagnosis takes time.", "Prescriptions are renewed yearly.",
    "Medical staff are busy.", "Medicine cabinets need tidying.", "These stretches treat chronic back pain.",
    "Surgery recovery takes time.", "Drug labels are small.", "A pill box helps.", "Supplement shelves get dusty.",
    "A multivitamin sits on the shelf.", "Melatonin is sold widely.", "Check the dosage.", "Take 200 mg.", "Ibuprofen is common.",
    "Pregnancy changes routines.", "Nursing mothers need rest.", "A fetus grows quickly.", "Toddlers wake early.",
    "Weight loss claims are everywhere.", "Many try to lose weight each January.", "Fat burning claims are common.",
    "Slimming teas are marketed widely.", "Keto menus are popular.", "Detox kits are marketed widely.",
]
EN_SAFE_RULE_SAMPLES = [  # 위험 낱말이 있어도 이 문장 하나만으로 건너뛰어지는 문장(패턴마다 하나)
    "Check with your doctor before trying a new supplement routine.",
    "This post is not a substitute for medical advice.",
    "This is not medical advice about dosage.",
    "For informational purposes only: this covers supplement basics.",
]
EN_CLAIM_SAMPLES = [
    "This miracle routine fixes everything.", "A cure-all for tired mornings.", "There are no side effects when you try this.",
    "It is 100% effective.", "Guaranteed to work for everyone.", "This will definitely help you sleep.", "It cures anxiety.",
    "These foods prevent disease.", "There is no need to see a doctor.", "You won't need medication.",
    "Use this instead of seeing a doctor.", "This can replace your doctor.", "Stop taking your medication and try this.",
    "Clinically proven to boost energy.", "A magic pill for better focus.", "Fight inflammation with this drink.",
]
EN_CLICKBAIT_TITLES = [
    "Shocking Habits for Calm Mornings", "Mind-Blowing Desk Stretches", "You Won't Believe This Tidy Desk", "Crazy Easy Morning Routine",
    "The Secret Garden Walk Routine", "Doctors Recommend Morning Walks", "One Weird Trick for Mornings", "Absolutely Do This Tonight",
    "Must-Try Morning Habits", "Reset Your Evenings Once and For All", "Calm Mornings, Made Simple!!", "NEVER Skip Your Evening Walk",
]
EN_CALM_TITLES = ["A Calm Morning Routine in 10 Minutes", "5 Easy Ways to Unwind After Work", "NASA-Inspired Sleep Tips for Tonight",
                  "Your Guide to Morning Light and Better Focus", "One Small Habit for a Calmer Evening",
                  "Try a Simple Screen-Free Hour Tonight", "Ready for a Reset? A Gentle Sunday Plan"]
EN_LEAK_SAMPLES = [
    "As an AI I should say so", "As a language model I should say so", "I am an AI assistant here", "I cannot provide medical advice here",
    "I'm sorry about the delay", "Certainly, here's how it goes", "Here is your blog post", "```html", "{topic}", "[Target: Blogger-EN]",
    "[Insert image here]", "Title: My Post", "Remember the todo list", "Lorem ipsum dolor sit amet", "This is **bold** text", "# Heading",
]
EN_NOT_LEAKS = ["Plan your evening so it ends calmly.", "A to-do list for the week keeps things simple.",
                "Content creators often work late, so set a cut-off time.", "The title of your day can be 'calm'.",
                "Use a notebook titled Wins.", "Languages are fun to learn on a commute.", "Sorry-not-sorry moments happen; just reset."]
KO_RULE_SAMPLES = [
    "치료 일정은 달라요", "완치 사례를 모아 봤어요", "처방 기준이 달라요", "약물 정보는 다루지 않아요", "복용 시간을 정해요",
    "보충제 선반을 정리해요", "영양제 통을 정리해요", "수술 일정을 잡아요", "질환 목록을 적어요", "질병 이야기는 하지 않아요",
    "암 이야기는 하지 않아요", "당뇨 식단은 달라요", "고혈압 정보는 달라요", "우울증 이야기는 아니에요", "공황 상황은 흔해요",
    "자살 예방 이야기예요", "자해 충동 이야기예요", "임신 중에는 달라요", "태아 성장은 달라요", "영유아 일과는 달라요",
    "신생아 일과는 달라요", "한약 달이는 법", "주사 맞는 날", "시술 후 관리", "의료 정보는 달라요", "진단 결과는 달라요",
    "다이어트 약 후기", "체중 감량 식단",
]
KO_SAFE_RULE_SAMPLES = [
    "임신 중이거나 약을 복용 중이라면 의사와 상담한 뒤 시작하세요.", "임신 중에는 상담을 의사와 먼저 하세요.",
    "이 글은 진단이나 치료를 대신하지 않습니다.", "이 글은 의학적 조언이 아닙니다 — 복용법은 다루지 않아요",
]

class EnglishTopicGuardTest(unittest.TestCase):
    def test_at_least_forty_forbidden_and_thirty_allowed_samples(self):
        self.assertGreaterEqual(len(FORBIDDEN_EN_TOPICS), 40)
        self.assertGreaterEqual(len(ALLOWED_EN_TOPICS), 30)

    def test_forbidden_topics_are_blocked(self):
        for topic in FORBIDDEN_EN_TOPICS:
            with self.subTest(topic):
                self.assertFalse(gates.topic_allowed(topic, EN), topic)

    def test_a_forbidden_topic_never_becomes_the_chosen_topic_even_when_the_llm_proposes_it(self):
        """(a) 주제 후보 경로: 시드를 모두 쿨다운에 넣어 LLM 확장으로 가게 하고, 금지 주제만 제안받으면 '주제 없음'이다."""
        history = [{"topic": t, "date": "2026-10-26"} for t in EN["seed_topics"]]
        for topic in FORBIDDEN_EN_TOPICS:
            self.assertTrue(topics.TOPIC_MIN_CHARS <= len(topic) <= topics.TOPIC_MAX_CHARS, topic)  # 길이 때문에 걸러지는 표본이 아니어야 한다
            reply = json.dumps([topic])
            with self.subTest(topic):
                self.assertEqual(topics.pick_topic(EN, history, date(2026, 10, 27), [], random.Random(1),
                                                   llm=lambda prompt, r=reply: (r, "m")), (None, "exhausted"), topic)

    def test_a_safe_llm_topic_is_chosen_after_the_forbidden_ones_are_dropped(self):
        history = [{"topic": t, "date": "2026-10-26"} for t in EN["seed_topics"]]
        reply = json.dumps(["Fast weight loss tips for busy people", "Detox water recipes", "short",
                            "A calm ten-minute walk to unwind after work"])
        self.assertEqual(topics.pick_topic(EN, history, date(2026, 10, 27), [], random.Random(1), llm=lambda prompt: (reply, "m")),
                         ("A calm ten-minute walk to unwind after work", "llm"))

    def test_allowed_topics_pass_including_substring_lookalikes(self):
        for topic in ALLOWED_EN_TOPICS:
            with self.subTest(topic):
                self.assertTrue(gates.topic_allowed(topic, EN), topic)

    def test_every_inflection_and_case_is_blocked(self):
        for stem, forms in EN_INFLECTIONS.items():
            for form in forms:
                with self.subTest(f"{stem}: {form}"):
                    self.assertFalse(gates.topic_allowed(f"Easy tips about {form} for busy people", EN), form)
                    self.assertFalse(gates.topic_allowed(form, EN), form)

    def test_lookalike_words_are_not_blocked(self):
        for word in EN_LOOKALIKES:
            with self.subTest(word):
                self.assertTrue(gates.topic_allowed(f"A calm routine about {word}", EN), word)

    def test_word_boundary_includes_punctuation_and_hyphens(self):
        for text in ("(supplements)", "supplement, then sleep", "Treatment-free?", "weight-loss!", "cure.", "'cancer'", "\"depression\""):
            with self.subTest(text):
                self.assertFalse(gates.topic_allowed(f"A short guide {text}", EN), text)

    def test_the_specific_cases_named_in_the_review(self):
        self.assertTrue(gates.topic_allowed("Secure your evening routine", EN))   # cure ⊄ secure
        self.assertFalse(gates.topic_allowed("A cure for stress", EN))
        self.assertTrue(gates.topic_allowed("Cancel your evening plans", EN))     # cancer ⊄ cancel
        self.assertFalse(gates.topic_allowed("Cancer and daily walks", EN))
        self.assertFalse(gates.topic_allowed("Get a daily dose of caffeine", EN))
        self.assertTrue(gates.topic_allowed("Dosa breakfast ideas", EN))          # dose ⊄ dosa
        self.assertTrue(gates.topic_allowed("A comfortable pillow guide", EN))    # pills ⊄ pillow


class KoreanTopicGuardTest(unittest.TestCase):
    """한국어 프로필의 주제 목록은 이제 제목·라벨에도 걸린다. 일상어를 막으면 안 되므로 오탐도 고정한다."""

    FORBIDDEN = ["치료법 총정리", "임신 중 안전한 운동", "혈압 약 복용 시간", "암 예방 식단", "다이어트 약 후기", "우울증 치료 습관",
                 "당뇨 환자를 위한 식단", "보충제 고르는 법", "영양제 챙겨 먹는 시간", "수술 후 회복 식단", "신생아 수면 패턴",
                 "영유아 간식 아이디어", "자해 충동 다스리기", "자살 예방 캠페인", "한약 복용법", "주사 맞은 날 관리",
                 "체중 감량 식단 짜기", "질병 예방 습관", "질환별 운동", "의료 정보 찾는 법", "공황 증상 다스리기",
                 "완치된 사람들의 습관", "처방전 없이 쓰는 방법", "시술 후 관리", "태아 건강 챙기기", "진단 체크리스트로 알아보는 건강"]
    ALLOWED = ["암막 커튼으로 수면 환경 만들기", "암기가 잘 되는 공부 환경 만들기", "집에서 쉽게 하는 스트레칭 루틴",
               # 투자해서·주사위: 낱말 일부가 '자해'·'주사'와 겹칠 뿐인 일상어(실제 생성 글 문장에서 나온 오탐을 고쳤다)
               "하루 3분 투자해서 저녁 정리하기", "주사위로 정하는 오늘의 산책 코스", "딱 5분만 투자해서 책상 비우는 법"]

    def test_forbidden_and_allowed(self):
        for topic in self.FORBIDDEN:
            with self.subTest(topic):
                self.assertFalse(gates.topic_allowed(topic, KO), topic)
        for topic in self.ALLOWED:
            with self.subTest(topic):
                self.assertTrue(gates.topic_allowed(topic, KO), topic)

    def test_self_harm_word_must_start_a_word_and_injection_word_must_not_be_dice(self):
        self.assertFalse(gates.topic_allowed("자해를 줄이는 방법", KO))
        self.assertFalse(gates.topic_allowed("충동적 자해 행동", KO))
        self.assertTrue(gates.topic_allowed("퇴근 후 10분 투자해서 정리하기", KO))
        self.assertFalse(gates.topic_allowed("예방 주사 맞는 날", KO))
        self.assertTrue(gates.topic_allowed("보드게임용 주사위 고르기", KO))


# ----------------------------------------------------------------------------
# (b) 생성된 제목·라벨
# ----------------------------------------------------------------------------
class TitleAndLabelGuardTest(unittest.TestCase):
    EN_TITLES_BLOCKED = ["5 Natural Ways to Treat Insomnia Tonight", "Lose Weight Fast With This Morning Habit",
                         "A Gentle Cure for Monday Stress Today", "Foods That Lower Blood Pressure Quickly",
                         "Detox Your Evenings: 5 Easy Habits", "Supplements That Support Better Sleep",
                         "Heal Your Body With a Simple Walk", "What Pregnant Women Should Know About Stretching"]
    EN_TITLES_OK = ["A Gentle Evening Routine for Better Sleep", "5 Small Habits for a Calmer Morning",
                    "How to Build a Simple Grocery List Fast", "Simple Desk Stretches for Long Workdays",
                    "Secure Your Sleep Schedule in 3 Steps", "Meditation Breaks for a Busy Workday"]
    KO_TITLES_BLOCKED = ["당뇨에 좋은 아침 습관 4가지", "다이어트 약 없이 체중 감량하는 방법", "영양제 챙겨 먹는 아침 루틴 4가지",
                         "임신 중에도 안전한 스트레칭 방법"]
    # 실제로 생성돼 이력(blogger_history.json)에 남아 있는 제목 5개 + 일상 제목
    KO_TITLES_OK = ["점심만 지나면 골골? 피곤할 때 에너지를 올리는 간단한 습관 4가지",
                    "잠들기 전 3분, 마음을 편안하게 정리하는 감사 메모 3줄 쓰기 방법",
                    "재택근무 중 찌뿌둥한 몸을 깨우는 책상 자세 체크리스트 4가지",
                    "잠이 안 올 때 침대에서 바로 해보는 4가지 간단한 방법",
                    "바쁜 하루 계단 오르기로 가볍게 움직임 채우는 4가지 방법",
                    "딱 3분 투자해서 하루를 정리하는 저녁 습관"]

    def test_english_titles(self):
        for title in self.EN_TITLES_BLOCKED:
            with self.subTest(title):
                self.assertIn("TITLE_TOPIC", check(EN, {"title": title}).codes(), title)
        for title in self.EN_TITLES_OK:
            with self.subTest(title):
                self.assertEqual(check(EN, {"title": title}).codes(), [], title)

    def test_korean_titles(self):
        for title in self.KO_TITLES_BLOCKED:
            with self.subTest(title):
                self.assertIn("TITLE_TOPIC", check(KO, {"title": title}).codes(), title)
        for title in self.KO_TITLES_OK:
            with self.subTest(title):
                self.assertEqual(check(KO, {"title": title}).codes(), [], title)

    def test_the_reason_names_the_word_so_the_rewrite_can_remove_it(self):
        reasons = check(EN, {"title": "Foods That Lower Blood Pressure Quickly"}).reasons
        title_reason = [r for r in reasons if r.startswith("[TITLE_TOPIC]")][0]
        self.assertIn("'Blood Pressure'", title_reason)
        reasons = check(KO, {"title": "당뇨에 좋은 아침 습관 4가지"}).reasons
        self.assertIn("'당뇨'", [r for r in reasons if r.startswith("[TITLE_TOPIC]")][0])

    def test_the_matched_word_is_folded_to_one_line(self):
        """맞은 낱말은 모델 출력에서 온다. 사유는 로그·요약·재작성 프롬프트에 들어가므로 한 줄·40자 이내로만 넣는다."""
        profile = copy.deepcopy(EN)
        profile["banned_topic_patterns"] = [r"(?s)evil.{0,200}word"]
        title = "evil\n::error::boom\r##[x] " + "z" * 100 + " word, a calm routine"
        reason = [r for r in check(profile, {"title": title}).reasons if r.startswith("[TITLE_TOPIC]")][0]
        self.assertEqual(reason.splitlines(), [reason])
        self.assertNotIn("::", reason)
        self.assertLess(len(reason), 200)

    def test_labels_are_checked_with_the_same_list(self):
        for label in ("weight loss", "Supplements", "diabetes", "pregnancy", "detox", "TREATMENT"):
            with self.subTest(label):
                self.assertIn("LABELS", check(EN, {"labels": ["habits", label]}).codes(), label)
        for label in ("sleep hygiene", "healthy habits", "routines", "meditation", "Self-care", "mental health"):
            with self.subTest(label):
                self.assertNotIn("LABELS", check(EN, {"labels": ["habits", label]}).codes(), label)
        self.assertIn("LABELS", check(KO, {"labels": ["수면", "다이어트 약"]}).codes())
        self.assertNotIn("LABELS", check(KO, {"labels": ["수면", "마음건강"]}).codes())
        reasons = check(EN, {"labels": ["habits", "Weight Loss", "sleep"]}).reasons
        self.assertIn("'Weight Loss'", [r for r in reasons if r.startswith("[LABELS]")][0])  # 걸린 라벨을 사유에 적는다

    def test_english_label_length_limit_is_30_characters(self):
        self.assertNotIn("LABELS", check(EN, {"labels": ["a" * 30]}).codes())
        self.assertIn("LABELS", check(EN, {"labels": ["a" * 31]}).codes())

    def test_each_guard_point_is_what_blocks_it(self):
        """제목 검사를 지우면 같은 제목이 통과한다 = 이 시험이 TITLE_TOPIC 규칙 자체를 고정한다(다른 규칙이 대신 막는 게 아니다)."""
        for profile, title in ((EN, "Foods That Lower Blood Pressure Quickly"), (KO, "당뇨에 좋은 아침 습관 4가지")):
            loose = copy.deepcopy(profile)
            loose["banned_topic_patterns"] = [r"zzz-never-matches"]
            self.assertEqual(check(loose, {"title": title}).codes(), [], title)


# ----------------------------------------------------------------------------
# (c) 생성된 본문
# ----------------------------------------------------------------------------
BODY_BLOCKED_EN = [
    "Take 400 mg of magnesium before bed to fall asleep faster.",
    "Melatonin supplements can help you fall asleep.",
    "Skip this stretch if you are pregnant.",
    "Newborns need a different schedule altogether.",
    "Walking lowers your blood pressure and cholesterol.",
    "Regular walks may reduce your risk of heart disease and diabetes.",
    "Struggling with insomnia? These tips can help.",
    "Anxiety disorders often respond well to breathing techniques.",
    "Lose weight fast with this morning habit.",
    "This detox routine flushes toxins from your body.",
    "Use ibuprofen if your muscles feel sore.",
    "A doctor may prescribe sleeping pills for this.",
    "Fasting for sixteen hours helps your body reset.",
    "Cure your headaches with this simple stretch.",
    "Our immune system needs vitamin C supplements.",
    "Toddlers should avoid this exercise.",
    "Infants should sleep on their backs.",
    "Breastfeeding mothers should drink more water.",
    "People with high blood pressure should avoid caffeine.",
    "If you have depression, increase your daily steps.",
    "Therapy and medication are often combined.",
    "Your doctor can diagnose the cause of your fatigue.",
    "This habit will treat your insomnia naturally.",
    "A daily dose of caffeine keeps you going.",
    "Chemotherapy patients often feel tired.",
    "Try a keto breakfast to burn fat.",
    "An overdose of screen time is common.",
    "These stretches treat chronic back pain.",
    "Surgery is not needed for a stiff neck.",
    "Clinical studies show this works.",
]

BODY_OK_EN = [
    "Talk to your doctor before starting a new exercise routine.",
    "If you have any health concerns, consult a healthcare professional first.",
    "This article is for informational purposes only and is not a substitute for professional medical advice, diagnosis, or treatment.",
    "It does not replace professional medical advice.",
    "If pain or dizziness shows up, stop and ask a professional.",
    "Check with your doctor or pharmacist if you take medication or are pregnant.",
    "Always seek medical advice if symptoms persist.",
    "Treat yourself to a quiet cup of tea after dinner.",
    "A small treat like fruit can make the evening feel special.",
    "Get a dose of fresh air on your lunch break.",
    "Keep a water bottle at your desk and sip regularly.",
    "Try a five-minute walk after lunch.",
    "Cancel meetings that could have been an email.",
    "Secure a regular bedtime for the whole week.",
    "Use pillows to support your back while you read.",
    "Stay patient with yourself while the habit settles in.",
    "Choose snacks like fruit, nuts, or yogurt.",
    "Many people find a short walk helpful for clearing their head.",
    "Replace scrolling with a few pages of a book.",
    "Don't stop trying: consistency matters more than perfection.",
    "Do not skip your morning stretch.",
    "Chronic procrastination can be tackled with a simple timer.",
    "Five minutes of meditation can reset a busy afternoon.",
    "Never stop taking your medication without asking your doctor.",
    "If you ever feel unwell, listen to your body and rest.",
    "Dimming the lights an hour before bed signals that the day is ending.",
    "A kitchen scale can make portioning meals easier.",
    "Healing takes time, so be patient with a new habit that has not clicked yet.",
]

# 건강 느낌이 나지만 위험하지 않은 일상 문장(정상 글이 탈락하면 안 된다)
BENIGN_WELLNESS_EN = [
    "Stress builds up quietly during a long workday, and a short pause can help you reset.",
    "Aim for a regular bedtime, a cool and dark room, and a screen-free hour before sleep.",
    "Many people notice they feel more alert after a glass of water and a few minutes of fresh air.",
    "Muscle tension in the neck and shoulders often comes from long hours at a desk, so stand up and roll your shoulders.",
    "Heart rate and breathing slow down when you take long, steady breaths.",
    "Caffeine late in the day can make it harder to wind down, so many people switch to decaf after lunch.",
    "Sugar in a sweetened coffee adds up, so try a smaller size or less syrup.",
    "Sore muscles after a new routine are common, so start small and build gradually.",
    "Feeling tired in the afternoon is normal; a snack with protein and a short walk can help.",
    "Burnout often sneaks in when there is no clear end to the workday.",
    "Anxious thoughts at night are easier to handle when you write them down before bed.",
    "A headache after hours of screen time may ease with a break, water, and dimmer lighting.",
    "Listen to your body, and stop if something hurts or feels dizzy.",
    "Blood flow improves a little when you stand up and move around every hour.",
    "Cortisol is often called the stress hormone, but you do not need to track it to enjoy a calmer evening.",
    "Counting calories is not necessary to enjoy a balanced plate of colorful foods.",
    "Doctor appointments, school pickups, and errands can crowd your calendar, so batch them when possible.",
    "Heat from a warm shower can make you sleepy, which is why many people shower before bed.",
    "Herbal tea without caffeine can be a cozy part of a bedtime routine.",
    "Keep a small first-aid kit at home, just in case.",
    "Posture checks every hour can reduce stiffness during long sitting days.",
    "Sleep tends to improve when mornings start with light and evenings end with calm.",
    "Please be patient with yourself; a new routine takes a few weeks to feel natural.",
    "Don't stop taking breaks: a two-minute pause is easier to repeat than a long one.",
    "A short walk can lift your mood and clear your head, even if it is only ten minutes.",
    "Protein, fiber, and vegetables keep a meal filling without much planning.",
    "Hydration matters, so keep a bottle in sight and sip through the day.",
    "Your brain works better with regular breaks, and a timer makes them easy to remember.",
    "Keep the evening light soft and avoid heavy meals right before bed.",
    "Oatmeal, bananas, and nuts make easy breakfast choices on busy mornings.",
    "Kids and adults alike enjoy a simple wind-down ritual before bed.",
    "Weekend meal prep can save time and reduce last-minute takeout orders.",
    "Try tracking your steps with a simple app or a notebook.",
    "Gentle yoga flows are popular for stretching and relaxing at home.",
    "Gratitude journaling takes three lines and about two minutes.",
    "A cluttered desk can make focusing harder, so clear one small area first.",
    "Healthy habits are built one small step at a time, so celebrate tiny wins.",
    "Some people prefer morning workouts, while others feel better moving in the evening.",
    "Your sleeping position matters less than a comfortable mattress and pillow.",
    "Fresh fruit makes a sweet snack that does not need preparation.",
    "The stomach feels better when meals are not rushed, so slow down and chew well.",
    "Walking meetings add movement to your workday without extra time.",
    "Light stretching before bed relaxes the legs and back.",
    "Take care of your eyes by looking at something far away every twenty minutes.",
    "Healing takes time, so be patient with a new habit that has not clicked yet.",
    "Wellness is personal, and what works for a friend may not work for you.",
    "Your energy dips are normal, and planning around them can feel kind.",
    "Back-to-back video calls are tiring, so schedule five-minute gaps.",
    "Soreness in the legs after stairs is a sign that your muscles are working.",
    "Drinking water first thing in the morning is an easy habit to start.",
    "You do not need special equipment, just a bit of floor space and ten minutes.",
    "A balanced breakfast might include eggs, toast, fruit, or yogurt.",
]


class EnglishBodyGuardTest(unittest.TestCase):
    def test_sample_sizes(self):
        self.assertGreaterEqual(len(BODY_BLOCKED_EN), 25)
        self.assertGreaterEqual(len(BENIGN_WELLNESS_EN), 50)
        self.assertGreaterEqual(len(BODY_OK_EN) + len(BENIGN_WELLNESS_EN), 70)

    def test_risky_sentences_are_blocked_by_the_body_guard(self):
        for sentence in BODY_BLOCKED_EN:
            with self.subTest(sentence):
                self.assertIn("BODY_TOPIC", check(EN, sentence=sentence).codes(), sentence)

    def test_safe_sentences_pass_with_no_reason_at_all(self):
        for sentence in BODY_OK_EN + BENIGN_WELLNESS_EN:
            with self.subTest(sentence):
                self.assertEqual(check(EN, sentence=sentence).codes(), [], sentence)

    def test_the_body_guard_is_what_blocks_them(self):
        """body_banned_patterns 를 지우면 같은 문장이 통과한다 — 다른 게이트가 대신 막는 것이 아니다. (변이: 본문 가드레일 삭제)"""
        loose = copy.deepcopy(EN)
        loose["body_banned_patterns"] = []
        for sentence in ("Take 400 mg of magnesium before bed to fall asleep faster.", "Skip this stretch if you are pregnant.",
                         "Walking lowers your blood pressure and cholesterol.", "Lose weight fast with this morning habit.",
                         "Struggling with insomnia? These tips can help."):
            with self.subTest(sentence):
                self.assertEqual(check(loose, sentence=sentence).codes(), [], sentence)
                self.assertIn("BODY_TOPIC", check(EN, sentence=sentence).codes(), sentence)

    def test_professional_referral_sentences_are_skipped_even_with_risk_words(self):
        for sentence in ("If you are pregnant or have high blood pressure, check with your doctor before trying this.",
                         "People taking medication should talk to a pharmacist first.",
                         "Please consult a qualified professional about any diabetes or heart disease concerns.",
                         "This post is not a substitute for medical advice, diagnosis, or treatment."):
            with self.subTest(sentence):
                self.assertEqual(check(EN, sentence=sentence).codes(), [], sentence)

    def test_the_same_words_without_a_referral_are_blocked(self):
        for sentence in ("If you are pregnant or have high blood pressure, avoid this stretch.",
                         "People taking medication should skip the afternoon coffee.",
                         "Diabetes and heart disease are common reasons to be careful."):
            with self.subTest(sentence):
                self.assertIn("BODY_TOPIC", check(EN, sentence=sentence).codes(), sentence)

    def test_a_referral_in_one_sentence_does_not_excuse_risk_words_in_another(self):
        """예외는 문장 단위다. 같은 글(같은 문단)에 상담 안내가 있어도 다른 문장의 위험 낱말은 걸린다."""
        for tail in ("<p>Talk to your doctor before changing your routine.</p><p>Melatonin before bed can help you fall asleep faster.</p>",
                     "<p>Talk to your doctor about this. Melatonin before bed can help you fall asleep faster. Sleep well.</p>",
                     "<p>This post is not a substitute for medical advice.</p><ul><li>Skip the stretch if you are pregnant</li></ul>"):
            with self.subTest(tail):
                post, stats = stub_post(EN)
                result = gates.check_post({**post, "content": post["content"] + tail}, EN, [], [], stats)
                self.assertIn("BODY_TOPIC", result.codes())
        post, stats = stub_post(KO)
        result = gates.check_post({**post, "content": post["content"] + "<p>의사와 상담하세요. 비타민 보충제를 드세요.</p>"}, KO, [], [], stats)
        self.assertIn("BODY_TOPIC", result.codes())

    def test_a_referral_does_not_excuse_an_efficacy_claim(self):
        """상담 안내 문장은 위험 낱말만 건너뛴다. 효능 단정(banned_patterns)은 예외 없이 막는다."""
        for sentence in ("Ask your doctor, but this stretch is a miracle for tired mornings.",
                         "Talk to your doctor, though it is 100% effective for everyone.",
                         "See a doctor if you like, but there are no side effects here.",
                         "Consult a professional, or simply stop taking your medication and try this."):
            with self.subTest(sentence):
                self.assertIn("BANNED", check(EN, sentence=sentence).codes(), sentence)

    def test_the_profiles_own_disclosure_is_a_safe_sentence(self):
        """append_disclosure 는 검사 뒤에 붙는다. 그래도 모델이 같은 면책 문장을 본문에 쓰면 통과해야 한다."""
        for profile in (EN, KO):
            plain = gates.plain_text(profile["disclosure_html"])
            with self.subTest(profile["language"]):
                self.assertEqual(gates.body_risk_hit(plain, profile), (None, None))
                self.assertEqual(check(profile, sentence=plain).codes(), [])
                unguarded = copy.deepcopy(profile)
                unguarded["body_safe_patterns"] = []
                self.assertNotEqual(gates.body_risk_hit(plain, unguarded), (None, None))  # 예외가 없으면 면책 문구가 걸린다

    def test_efficacy_claims_are_blocked(self):
        for claim in EN_CLAIM_SAMPLES:
            with self.subTest(claim):
                self.assertIn("BANNED", check(EN, sentence=claim).codes(), claim)

    def test_negated_disclaimers_are_not_efficacy_claims(self):
        for sentence in ("It does not replace your doctor.", "This is not meant to replace your doctor.",
                         "Please don't stop taking your medication.", "Never stop taking any prescription without asking your doctor.",
                         "Do not skip your meds.", "No single habit will cure everything.", "Sleep is not a cure for everything.",
                         "Quit scrolling after 10 pm.", "Reduce screen time in the evening.", "Lower the lights an hour before bed."):
            with self.subTest(sentence):
                self.assertNotIn("BANNED", check(EN, sentence=sentence).codes(), sentence)


# ----------------------------------------------------------------------------
# 영어 프로필의 나머지 규칙(클릭 미끼 제목·AI 자기 언급·단정 표현)과 규칙별 적용 범위
# ----------------------------------------------------------------------------
class EnglishProfileRulesTest(unittest.TestCase):
    def test_clickbait_titles_are_blocked_and_calm_ones_are_not(self):
        for title in EN_CLICKBAIT_TITLES:
            with self.subTest(title):
                self.assertIn("TITLE_BANNED", check(EN, {"title": title}).codes(), title)
        for title in EN_CALM_TITLES:
            with self.subTest(title):
                self.assertEqual(check(EN, {"title": title}).codes(), [], title)

    def test_ai_self_reference_and_template_leftovers_are_blocked_and_look_alikes_are_not(self):
        for sentence in EN_LEAK_SAMPLES:
            with self.subTest(sentence):
                self.assertIn("LEAK", check(EN, sentence=sentence).codes(), sentence)
        for sentence in EN_NOT_LEAKS:
            with self.subTest(sentence):
                self.assertNotIn("LEAK", check(EN, sentence=sentence).codes(), sentence)

    def test_the_english_title_and_body_limits_are_enforced(self):
        self.assertIn("TITLE_LEN", check(EN, {"title": "Too short"}).codes())
        self.assertIn("TITLE_LEN", check(EN, {"title": "A" + " calm" * 20}).codes())
        post, stats = stub_post(EN)
        self.assertIn("LEN_SHORT", gates.check_post({**post, "content": "<h3>a</h3><h3>b</h3><h3>c</h3><ul><li>x</li></ul><p>Short.</p>"},
                                                    EN, [], [], stats).codes())
        self.assertIn("LEN_LONG", check(EN, {"content": post["content"] + "<p>" + "Calm words here. " * 500 + "</p>"}).codes())
        self.assertIn("STRUCT_H3", check(EN, {"content": re.sub(r"</?h3>", "", post["content"])}).codes())
        self.assertIn("STRUCT_LIST", check(EN, {"content": re.sub(r"</?(?:ul|li)>", "", post["content"])}).codes())

    def test_english_duplicates_are_caught_like_korean_ones(self):
        post, stats = stub_post(EN)
        self.assertIn("DUP_SAME", gates.check_post(post, EN, [post["title"]], [], stats).codes())
        self.assertIn("DUP_OTHER", gates.check_post(post, EN, [], [post["title"]], stats).codes())
        self.assertNotIn("DUP_OTHER", gates.check_post(post, EN, [], ["어젯밤에 쓴 한국어 제목입니다 정말로"], stats).codes())


class RuleCoverageTest(unittest.TestCase):
    """규칙마다 '그 규칙만 막는 표본'이 있어야 한다(ENGINEERING_GUIDE: 규칙을 더하면 그 규칙을 보여 주는 케이스를 같이 더한다).
    패턴 하나를 지우거나 약하게 만들었을 때 시험이 모르고 지나가는 일을 막는다."""

    def assertEveryPatternHasItsOwnSample(self, patterns, samples, label):
        self.assertTrue(patterns, label)
        for index, pattern in enumerate(patterns):
            others = patterns[:index] + patterns[index + 1:]
            owned = [s for s in samples if gates.first_match([pattern], s)[0] is not None and gates.first_match(others, s)[0] is None]
            self.assertTrue(owned, f"{label}: 이 패턴만 막는 표본이 없다 → {pattern}")

    def test_english_lists(self):
        self.assertEveryPatternHasItsOwnSample(EN["banned_topic_patterns"], EN_TOPIC_RULE_SAMPLES, "영어 주제·제목·라벨 목록")
        self.assertEveryPatternHasItsOwnSample(EN["body_banned_patterns"], EN_BODY_RULE_SAMPLES, "영어 본문 목록")
        self.assertEveryPatternHasItsOwnSample(EN["banned_patterns"], EN_CLAIM_SAMPLES, "영어 효능 단정 목록")
        self.assertEveryPatternHasItsOwnSample(EN["title_banned_patterns"], EN_CLICKBAIT_TITLES, "영어 클릭 미끼 목록")
        self.assertEveryPatternHasItsOwnSample(EN["leak_patterns"], EN_LEAK_SAMPLES, "영어 AI 자기 언급·잔재 목록")

    def test_korean_lists(self):
        self.assertEveryPatternHasItsOwnSample(KO["banned_topic_patterns"], KO_RULE_SAMPLES, "한국어 주제·제목·라벨 목록")
        self.assertEveryPatternHasItsOwnSample(KO["body_banned_patterns"], KO_RULE_SAMPLES, "한국어 본문 목록")

    def test_every_sample_is_blocked_everywhere_it_should_be(self):
        for sample in EN_TOPIC_RULE_SAMPLES:
            self.assertFalse(gates.topic_allowed(sample, EN), sample)
        for sample in EN_BODY_RULE_SAMPLES:
            self.assertIn("BODY_TOPIC", check(EN, sentence=sample).codes(), sample)
        for sample in KO_RULE_SAMPLES:
            self.assertFalse(gates.topic_allowed(sample, KO), sample)
            self.assertIn("BODY_TOPIC", check(KO, sentence=sample + ".").codes(), sample)
        for sample in EN_SAFE_RULE_SAMPLES:  # 위험 낱말이 있어도 면책·상담 문장이라 통과해야 한다
            self.assertIsNotNone(gates.first_match(EN["body_banned_patterns"], sample)[0], sample)
            self.assertEqual(check(EN, sentence=sample).codes(), [], sample)
        for sample in KO_SAFE_RULE_SAMPLES:
            self.assertIsNotNone(gates.first_match(KO["body_banned_patterns"], sample)[0], sample)
            self.assertEqual(check(KO, sentence=sample).codes(), [], sample)

    def test_every_body_exemption_pattern_is_the_only_reason_its_sample_passes(self):
        for profile, samples in ((EN, EN_SAFE_RULE_SAMPLES), (KO, KO_SAFE_RULE_SAMPLES)):
            patterns = profile["body_safe_patterns"]
            for index, pattern in enumerate(patterns):
                without = {**profile, "body_safe_patterns": patterns[:index] + patterns[index + 1:]}
                owned = [s for s in samples if gates.body_risk_hit(s, profile) == (None, None) and gates.body_risk_hit(s, without) != (None, None)]
                self.assertTrue(owned, f"{profile['name']}: 이 예외 패턴만으로 통과하는 문장이 없다 → {pattern}")
                self.assertEqual(check(profile, sentence=owned[0]).codes(), [], owned[0])

class KoreanBodyGuardTest(unittest.TestCase):
    BLOCKED = ["이 방법으로 불면증이 완치됩니다.", "비타민 보충제를 함께 드세요.", "임신 중에는 이 동작을 피하세요.",
               "당뇨가 있는 분들은 아침 식단을 바꾸세요.", "혈압약 복용 시간을 아침으로 옮겨 보세요.", "우울증이 있다면 더 많이 걸어 보세요.",
               "체중 감량에 도움이 되는 간식입니다.", "다이어트 약 대신 이 습관을 해 보세요.", "신생아는 수면 패턴이 다릅니다.",
               "한약을 달여 마시면 좋아요.", "예방 주사를 맞은 날에는 쉬세요.", "수술 후에는 이 운동을 하세요.", "자해를 줄이는 방법도 있어요."]
    OK = ["일반적으로 도움이 될 수 있어요. 불편이 계속되면 전문가와 상담하세요.",
          "이 글은 진단이나 치료를 대신하지 않습니다.",
          "임신 중이거나 약을 복용 중이라면 의사와 상담한 뒤 시작하세요.",
          "건강에 대한 고민이 있다면 의사·약사 등 전문가와 상담하세요.",
          "당뇨나 고혈압이 있다면 병원에서 먼저 확인해 보세요.",
          "이 글은 의학적 조언이 아닙니다.",
          # 실제로 생성돼 게이트를 통과했던 글의 문장('투자해서'가 '자해'와 겹쳐 새 본문 검사에 걸렸던 것) 외 일상 문장
          "바로 잠들기 전 딱 3분만 투자해서 '감사 메모 3줄'을 적어보는 거예요.",
          "주사위를 굴려 오늘의 산책 코스를 정해 보세요.",
          "암막 커튼을 달면 방이 한결 어두워져요.",
          "혈액순환이 잘 되도록 가볍게 몸을 풀어 주면 개운한 느낌을 받을 수 있어요.",
          "미지근한 물을 한 컵 천천히 마셔 주면 나른한 기운을 깨우는 데 도움이 될 수 있습니다.",
          "스마트폰을 손이 닿지 않는 곳에 두고 은은한 조명 아래에서 조용한 음악을 들어 보세요."]

    def test_risky_sentences_are_blocked(self):
        for sentence in self.BLOCKED:
            with self.subTest(sentence):
                self.assertIn("BODY_TOPIC", check(KO, sentence=sentence).codes(), sentence)

    def test_safe_sentences_pass_with_no_reason_at_all(self):
        for sentence in self.OK:
            with self.subTest(sentence):
                self.assertEqual(check(KO, sentence=sentence).codes(), [], sentence)

    def test_the_body_list_uses_the_same_words_as_the_topic_list(self):
        """한국어는 제목·라벨·본문에 같은 어휘를 쓴다(영어는 본문 목록이 일상어와 겹치는 낱말을 뺀 부분집합). 한쪽만 고치면 이 시험이 알린다."""
        self.assertEqual(KO["body_banned_patterns"], KO["banned_topic_patterns"])

    def test_the_body_guard_is_what_blocks_it(self):
        loose = copy.deepcopy(KO)
        loose["body_banned_patterns"] = []
        self.assertEqual(check(loose, sentence="비타민 보충제를 함께 드세요.").codes(), [])
        self.assertIn("BODY_TOPIC", check(KO, sentence="비타민 보충제를 함께 드세요.").codes())

    def test_a_profile_without_body_patterns_has_no_body_guard(self):
        """body_* 는 선택 항목이다. 없는 프로필(예: 앞으로 만들 다른 프로필)은 예전처럼 본문 위험 낱말 검사를 하지 않는다."""
        legacy = copy.deepcopy(KO)
        del legacy["body_banned_patterns"], legacy["body_safe_patterns"]
        self.assertEqual(registry.validate_profile(legacy), [])
        self.assertEqual(gates.body_risk_hit("임신 중에는 쉬세요.", legacy), (None, None))
        self.assertEqual(check(legacy, sentence="임신 중에는 쉬세요.").codes(), [])

    def test_the_stub_and_every_seed_still_pass(self):
        for seed in KO["seed_topics"]:
            with self.subTest(seed):
                post, stats = stub_post(KO, seed)
                result = gates.check_post(post, KO, [], [], stats)
                self.assertTrue(result.ok, result.reasons)


class EvasionAndSpeedTest(unittest.TestCase):
    """모델이 낱말 사이에 보이지 않는 문자·태그를 끼워도 걸리고, 길고 반복적인 입력에도 정규식이 폭주하지 않는다."""

    def test_invisible_characters_inside_a_word_do_not_hide_it(self):
        for word in ("supple\u200bment", "treat\u00adment", "pregn\u2060ant", "dia\ufeffbetes", "mela\u200dtonin"):
            with self.subTest(word):
                self.assertFalse(gates.topic_allowed(f"Easy tips about {word}", EN), word)
                self.assertIn("BODY_TOPIC", check(EN, sentence=f"Try a {word} routine tonight.").codes(), word)
        for word in ("치\u200b료", "당\u00ad뇨", "임\ufeff신"):
            with self.subTest(word):
                self.assertFalse(gates.topic_allowed(f"{word} 습관", KO), word)
                self.assertIn("BODY_TOPIC", check(KO, sentence=f"{word} 중에는 쉬세요.").codes(), word)

    def test_tags_and_entities_inside_a_word_do_not_hide_it(self):
        for sentence in ("Try melato<b>nin</b> tonight.", "Try &#115;upplements tonight.", "Try sup<wbr>plements tonight.",
                         "Try pregn&shy;ant stretches tonight.", "Try Melatonin tonight&#33;"):
            with self.subTest(sentence):
                self.assertIn("BODY_TOPIC", check(EN, sentence=sentence).codes(), sentence)

    def test_curly_quotes_special_hyphens_and_fullwidth_letters_are_folded_before_matching(self):
        """모델은 영어 글에 굽은 따옴표(U+2019)를 자주 쓴다. 곧은 따옴표로만 쓴 패턴이 굽은 따옴표를 놓치면 안전한 면책이 탈락하고 단정은 통과한다."""
        curly = "’"
        for sentence in (f"This isn{curly}t a substitute for medical advice, diagnosis, or treatment.",
                         f"It doesn{curly}t replace professional medical advice.", f"This isn{curly}t medical advice about dosage."):
            with self.subTest(sentence):
                self.assertEqual(check(EN, sentence=sentence).codes(), [], sentence)
        self.assertNotIn("BANNED", check(EN, sentence=f"Please don{curly}t stop taking your medication.").codes())
        self.assertIn("BANNED", check(EN, sentence=f"You won{curly}t need medication.").codes())
        self.assertIn("TITLE_BANNED", check(EN, {"title": f"You Won{curly}t Believe This Tidy Desk"}).codes())
        self.assertIn("LEAK", check(EN, sentence=f"I{curly}m sorry about the delay").codes())
        self.assertFalse(gates.topic_allowed(f"Weight{chr(0x2011)}loss journaling", EN))      # 줄바꿈 없는 하이픈
        self.assertFalse(gates.topic_allowed(f"Self{chr(0x2013)}harm awareness walks", EN))   # 엔 대시
        fullwidth = "".join(chr(ord(c) + 0xFEE0) for c in "supplement")                       # 전각 영문
        self.assertFalse(gates.topic_allowed(f"Easy {fullwidth} shelf cleanup", EN))
        self.assertIn("BODY_TOPIC", check(EN, sentence=f"A {fullwidth} sits on the shelf.").codes())
        decomposed = unicodedata.normalize("NFD", "치료")                                       # 풀어 쓴 한글 자모
        self.assertNotEqual(decomposed, "치료")
        self.assertFalse(gates.topic_allowed(f"{decomposed} 습관", KO))
        self.assertIn("TITLE_BANNED", check(KO, {"title": "이런 습관이 있다고요！！"}).codes())  # 전각 느낌표

    def test_invisible_characters_do_not_change_what_is_allowed(self):
        self.assertTrue(gates.topic_allowed("Sec\u200bure your sleep schedule", EN))
        self.assertEqual(check(EN, sentence="Secure\u200b a regular bed\u00adtime for the whole week.").codes(), [])

    def test_worst_case_inputs_finish_quickly(self):
        import time
        payloads = ["treat " * 1200, "lose a " * 1000, "cure " * 1400, "a " * 3500, "heart " * 1200, "no need to " * 700,
                    "stop taking " * 600, ("word " * 20 + ". ") * 300, "talk to a " * 700, "ask see call " * 500,
                    "(" * 300 + "treat" + ")" * 300, "x" * 7000]
        for payload in payloads:
            post, stats = stub_post(EN)
            started = time.perf_counter()
            gates.check_post({**post, "content": f"<p>{payload}</p>"}, EN, [], [], stats)
            self.assertLess(time.perf_counter() - started, 2.0, payload[:30])
        ko_payloads = ["치료 " * 1200, "자해 " * 1500, "의사와 상담 " * 800, "가나다 " * 2000]
        for payload in ko_payloads:
            post, stats = stub_post(KO)
            started = time.perf_counter()
            gates.check_post({**post, "content": f"<p>{payload}</p>"}, KO, [], [], stats)
            self.assertLess(time.perf_counter() - started, 2.0, payload[:30])


# ----------------------------------------------------------------------------
# 시드
# ----------------------------------------------------------------------------
class SeedTest(unittest.TestCase):
    def test_every_seed_passes_the_topic_guard_and_the_length_rule(self):
        for profile in (EN, KO):
            seen = set()
            for seed in profile["seed_topics"]:
                with self.subTest(profile["name"] + ": " + seed):
                    self.assertTrue(gates.topic_allowed(seed, profile), seed)
                    self.assertTrue(topics.TOPIC_MIN_CHARS <= len(seed) <= topics.TOPIC_MAX_CHARS, f"{len(seed)}자: {seed}")
                    self.assertNotIn(seed, seen)
                    seen.add(seed)

    def test_english_seeds_are_about_thirty_and_every_stub_post_for_them_passes_the_gate(self):
        self.assertTrue(30 <= len(EN["seed_topics"]) <= 40, len(EN["seed_topics"]))
        for seed in EN["seed_topics"]:
            with self.subTest(seed):
                post, stats = stub_post(EN, seed)
                result = gates.check_post(post, EN, [], [], stats)
                self.assertTrue(result.ok, result.reasons)

    def test_english_seeds_are_everyday_habits_and_not_clickbait(self):
        rx = gates._compiled(EN["title_banned_patterns"])
        for seed in EN["seed_topics"]:
            with self.subTest(seed):
                self.assertFalse(any(r.search(seed) for r in rx), seed)
                self.assertFalse(re.search(r"[가-힣]", seed))

    def test_a_banned_seed_is_a_profile_error(self):
        bad = copy.deepcopy(EN)
        bad["seed_topics"].append("Natural ways to treat insomnia at home")
        errors = registry.validate_profile(bad)
        self.assertTrue(any("seed_topics" in e and "treat" in e.lower() for e in errors), errors)
        bad = copy.deepcopy(KO)
        bad["seed_topics"].append("임신 중 안전한 운동 방법")
        self.assertTrue(any("seed_topics" in e for e in registry.validate_profile(bad)))


# ----------------------------------------------------------------------------
# 글 언어
# ----------------------------------------------------------------------------
class LanguageGateTest(unittest.TestCase):
    def test_english_post_passes_and_korean_text_fails_the_english_profile(self):
        self.assertEqual(check(EN).codes(), [])
        korean_body = "<h3>하나</h3><h3>둘</h3><h3>셋</h3><ul><li>가</li></ul><p>" + "오늘 바로 해볼 수 있는 작은 습관입니다. " * 150 + "</p>"
        self.assertIn("LANG", check(EN, {"content": korean_body}).codes())

    def test_a_mostly_korean_post_with_some_english_words_fails(self):
        body = "<h3>One</h3><h3>Two</h3><h3>Three</h3><ul><li>x</li></ul><p>" + ("Walk daily. 오늘 바로 해볼 수 있는 작은 습관이에요. " * 100) + "</p>"
        self.assertIn("LANG", check(EN, {"content": body}).codes())

    def test_a_few_foreign_words_are_tolerated_but_the_title_must_be_latin(self):
        post, _ = stub_post(EN)
        body = post["content"] + "<p>We call this kimchi (김치) time.</p>"
        self.assertNotIn("LANG", check(EN, {"content": body}).codes())
        self.assertIn("LANG", check(EN, {"title": "A Calm Evening Routine 김치"}).codes())
        self.assertIn("LANG", check(EN, {"title": "A Calm Evening Routine 夜"}).codes())

    def test_accented_latin_letters_are_fine(self):
        post, _ = stub_post(EN)
        body = post["content"] + "<p>Try a café stop, a crème brûlée treat-free evening, or a jalapeño-free dinner. Naïve plans work too.</p>"
        self.assertNotIn("LANG", check(EN, {"content": body}).codes())
        self.assertNotIn("LANG", check(EN, {"title": "A Café Walk for a Calmer Afternoon"}).codes())

    def test_accented_letters_count_as_latin_letters_not_as_foreign_ones(self):
        """é·ñ·ü 가 비율 계산에서 '라틴이 아닌 글자'로 세어지면 프랑스어·스페인어 낱말이 많은 글이 탈락한다(경계는 U+024F)."""
        post, _ = stub_post(EN)
        body = post["content"] + "<p>" + "Åäö éèê ïîí ñ ü " * 200 + "</p>"
        self.assertNotIn("LANG", check(EN, {"content": body}).codes())
        self.assertIn("LANG", check(EN, {"content": post["content"] + "<p>" + "Ωμέγα αβγδ " * 200 + "</p>"}).codes())  # 그리스 문자는 아니다

    def test_the_ratio_threshold_comes_from_the_profile(self):
        post, _ = stub_post(EN)
        body = post["content"] + "<p>" + "가나다라마바사 " * 30 + "</p>"      # 한글 210자(전체 글자의 약 7%)
        self.assertNotIn("LANG", check(EN, {"content": body}).codes())
        strict = copy.deepcopy(EN)
        strict["min_latin_ratio"] = 0.99
        self.assertIn("LANG", check(strict, {"content": body}).codes())

    def test_korean_profile_language_gate_is_unchanged(self):
        english_body = "<h3>a</h3><h3>b</h3><h3>c</h3><ul><li>x</li></ul><p>" + "This is plain English text. " * 80 + "</p>"
        self.assertIn("LANG", check(KO, {"content": english_body}).codes())
        self.assertEqual(check(KO).codes(), [])
        self.assertNotIn("[LANG] 제목에", " ".join(check(KO, {"title": "Hello World Title Here"}).reasons))  # 제목 라틴 검사는 영어 프로필만


# ----------------------------------------------------------------------------
# 응답 머리표
# ----------------------------------------------------------------------------
class MarkerTest(unittest.TestCase):
    def test_english_markers_parse(self):
        parsed = gates.parse_labeled_post("Title: A Calm Morning Routine\nLabels: sleep, habits, sleep\nContent:\n<p>Hello</p>")
        self.assertEqual(parsed, {"title": "A Calm Morning Routine", "labels": ["sleep", "habits"], "content": "<p>Hello</p>"})

    def test_english_markers_are_case_insensitive_and_accept_synonyms(self):
        parsed = gates.parse_labeled_post("TITLE: **Bold Title**\nlabels: #sleep #habits\nCONTENT:\n<p>x</p>")
        self.assertEqual((parsed["title"], parsed["labels"]), ("Bold Title", ["sleep", "habits"]))
        parsed = gates.parse_labeled_post("Title: T Title Here\nTags: a, b\nBody:\n<p>x</p>")
        self.assertEqual((parsed["labels"], parsed["content"]), (["a", "b"], "<p>x</p>"))

    def test_code_fences_and_leading_blank_lines_are_ignored(self):
        parsed = gates.parse_labeled_post("\n```html\nTitle: A Calm Morning Routine\nLabels: a\nContent:\n<p>x</p>\n```")
        self.assertEqual(parsed["content"], "<p>x</p>")

    def test_korean_markers_win_and_their_result_is_unchanged(self):
        parsed = gates.parse_labeled_post("제목: 한국어 제목입니다\n라벨: 수면, 습관\n내용:\n<p>Content: not a marker here</p>")
        self.assertEqual((parsed["title"], parsed["labels"]), ("한국어 제목입니다", ["수면", "습관"]))
        self.assertEqual(parsed["content"], "<p>Content: not a marker here</p>")

    def test_missing_sections_name_the_missing_items_in_the_language_of_the_markers_used(self):
        with self.assertRaises(gates.GateError) as ctx:
            gates.parse_labeled_post("Title: A Calm Morning Routine\nContent:\n<p>x</p>")
        self.assertIn("Labels", str(ctx.exception))
        with self.assertRaises(gates.GateError) as ctx:
            gates.parse_labeled_post("제목: 한국어 제목입니다\n내용:\n<p>x</p>")
        self.assertIn("라벨", str(ctx.exception))
        with self.assertRaises(gates.GateError) as ctx:
            gates.parse_labeled_post("그냥 문장만 있는 응답")
        self.assertIn("제목, 라벨, 내용", str(ctx.exception))  # 아무 머리표도 없으면 예전과 같은 안내

    def test_mixed_marker_languages_never_fill_in_a_missing_section(self):
        for raw in ("제목: 한국어 제목입니다\nLabels: a, b\n내용:\n<p>x</p>", "Title: A Calm Morning Routine\n라벨: a\nContent:\n<p>x</p>"):
            with self.assertRaises(gates.GateError):
                gates.parse_labeled_post(raw)

    def test_empty_title_or_body_still_raises(self):
        with self.assertRaises(gates.GateError):
            gates.parse_labeled_post("Title: ***\nLabels: a\nContent:\n<p>x</p>")


# ----------------------------------------------------------------------------
# 프로필 검증(레지스트리)
# ----------------------------------------------------------------------------
class ProfileValidationTest(unittest.TestCase):
    def errors(self, mutate, base=EN):
        profile = copy.deepcopy(base)
        mutate(profile)
        return registry.validate_profile(profile)

    def assertHas(self, errors, fragment):
        self.assertTrue(any(fragment in e for e in errors), f"{fragment!r} 가 {errors} 에 없음")

    def test_both_real_profiles_are_valid(self):
        self.assertEqual(registry.validate_profile(EN), [])
        self.assertEqual(registry.validate_profile(KO), [])

    def test_unknown_language_is_an_error_because_it_would_switch_the_language_gate_off(self):
        self.assertHas(self.errors(lambda p: p.update(language="ja")), "language")
        self.assertHas(self.errors(lambda p: p.update(language="")), "language")

    def test_ratio_fields_are_numbers_between_zero_and_one(self):
        for bad in (0, -0.1, 1.5, "0.9", None, True):
            self.assertHas(self.errors(lambda p, b=bad: p.update(min_latin_ratio=b)), "min_latin_ratio")
        self.assertHas(self.errors(lambda p: p.update(min_hangul_ratio=2), base=KO), "min_hangul_ratio")
        self.assertEqual(self.errors(lambda p: p.update(min_latin_ratio=1)), [])

    def test_bad_regexes_in_the_new_lists_are_reported(self):
        for field in ("body_banned_patterns", "body_safe_patterns", "banned_topic_patterns", "banned_patterns"):
            self.assertHas(self.errors(lambda p, f=field: p[f].append("([unclosed")), "정규식 오류")
            self.assertHas(self.errors(lambda p, f=field: p.update({f: "not a list"})), "배열")

    def test_a_pattern_that_matches_the_empty_string_is_an_error(self):
        """끝에 '|' 를 남기는 실수. 금지 목록이면 모든 글이 탈락하고, body_safe_patterns 면 모든 문장을 건너뛰어 본문 가드레일이 꺼진다."""
        for field in ("body_banned_patterns", "body_safe_patterns", "banned_topic_patterns", "banned_patterns",
                      "title_banned_patterns", "leak_patterns"):
            for bad in ("treat|", "(?:)", "a*", r"\s*", "^", "$"):
                with self.subTest(f"{field}: {bad!r}"):
                    self.assertHas(self.errors(lambda p, f=field, b=bad: p[f].append(b)), "빈 문자열")

    def test_every_pattern_in_both_real_profiles_is_non_empty(self):
        for profile in (EN, KO):
            for field in registry._PATTERN_FIELDS:
                for pattern in profile.get(field, []):
                    self.assertIsNone(re.compile(pattern, re.IGNORECASE).search(""), (profile["name"], field, pattern))

    def test_topic_expand_prompt_needs_its_placeholders(self):
        self.assertHas(self.errors(lambda p: p.update(topic_expand_prompt="no placeholders here")), "topic_expand_prompt")
        self.assertHas(self.errors(lambda p: p.update(topic_expand_prompt={"x": 1})), "topic_expand_prompt")
        self.assertEqual(self.errors(lambda p: p.update(topic_expand_prompt="Give {n} topics. Avoid:\n{avoid}")), [])

    def test_prompt_extra_must_be_a_list_of_strings(self):
        self.assertHas(self.errors(lambda p: p.update(prompt_extra="one long string")), "prompt_extra")
        self.assertHas(self.errors(lambda p: p.update(prompt_extra=["ok", 3])), "prompt_extra")


if __name__ == "__main__":
    unittest.main()
