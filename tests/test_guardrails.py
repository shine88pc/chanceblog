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
    "Liver function trackers", "Dieting playlists", "Shed pounds playlists", "Body fat playlists", "Sleep aid shelf cleanup",
    "Menopause podcast playlists",
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
    "Liver health is trending.", "Dieting is popular.", "Shed pounds quickly.", "Body fat varies.", "A sleep aid sits on the shelf.",
    "Menopause is common.", "Immunity claims are common.",
]
EN_SAFE_RULE_SAMPLES = [  # 위험 낱말이 있어도 이 문장 하나만으로 건너뛰어지는 문장(패턴마다 하나)
    "Check with your doctor before trying a new supplement routine.",
    "This post is not a substitute for medical advice.",
    "This is not medical advice about dosage.",
    "This guide is for informational purposes only and covers supplement basics.",
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
    "혈당 기록장은 달라요", "불면의 밤은 길어요", "콜레스테롤 수치는 달라요", "치매 이야기는 아니에요", "갱년기 이야기는 아니에요",
    "편두통 일기는 달라요", "면역력 이야기는 아니에요", "임상 결과는 달라요", "접종 일정은 달라요", "스테로이드 이야기는 아니에요",
    "침술 이야기는 아니에요", "수면제 이야기는 아니에요", "건강기능식품 선반을 정리해요", "멜라토닌 이야기는 아니에요",
    "종합 비타민 선반을 정리해요", "증상 메모는 달라요", "천식 이야기는 아니에요", "자폐 이야기는 아니에요", "종양 이야기는 아니에요",
    "심장병 이야기는 아니에요", "디톡스 이야기는 아니에요", "단식 이야기는 아니에요", "저탄고지 식단은 달라요", "체지방 기록은 달라요",
    "간 건강 이야기는 아니에요", "요법 이야기는 아니에요", "임산부 이야기는 아니에요", "400mg 이야기는 아니에요",
]
KO_SAFE_RULE_SAMPLES = [
    "임신 중이거나 약을 복용 중이라면 의사와 상담한 뒤 시작하세요.", "임신 중에는 상담을 의사와 먼저 하세요.",
    "이 글은 진단이나 치료를 대신하지 않습니다.", "복용법을 다루는 이 글은 의학적 조언이 아닙니다.",
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
                    "(" * 300 + "treat" + ")" * 300, "x" * 7000,
                    # D-64 ⑧: 새 도입구·3인칭 주어·부사·연결어가 겹쳐 나오는 반복 입력
                    "so you should ask " * 400, "so you might want to " * 300, "and people should " * 400, "so please also just first " * 300, "so do do do " * 500,
                    "so you should make sure to remember to " * 150, "so ask " + "your " * 1500 + "doctor"]
        for payload in payloads:
            post, stats = stub_post(EN)
            started = time.perf_counter()
            gates.check_post({**post, "content": f"<p>{payload}</p>"}, EN, [], [], stats)
            self.assertLess(time.perf_counter() - started, 2.0, payload[:30])
        ko_payloads = ["치료 " * 1200, "자해 " * 1500, "의사와 상담 " * 800, "가나다 " * 2000,
                       "그래서 의사와 " * 600, "고 꼭 반드시 먼저 우선 " * 400, "대해서 의사와 " * 600, "서 서 서 " * 1500]
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
        for field in ("body_banned_patterns", "body_safe_patterns", "banned_topic_patterns", "banned_patterns",
                      "body_clause_split_patterns", "body_safe_veto_patterns"):
            self.assertHas(self.errors(lambda p, f=field: p[f].append("([unclosed")), "정규식 오류")
            self.assertHas(self.errors(lambda p, f=field: p.update({f: "not a list"})), "배열")

    def test_a_pattern_that_matches_the_empty_string_is_an_error(self):
        """끝에 '|' 를 남기는 실수. 금지 목록이면 모든 글이 탈락하고, body_safe_patterns 면 모든 문장을 건너뛰어 본문 가드레일이 꺼진다."""
        for field in ("body_banned_patterns", "body_safe_patterns", "banned_topic_patterns", "banned_patterns",
                      "title_banned_patterns", "leak_patterns", "body_clause_split_patterns", "body_safe_veto_patterns"):
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


# ----------------------------------------------------------------------------
# (c) 본문 — 상담 구절은 같은 문장 안의 위험한 권유를 면제하지 않는다(D-64 ⑥ a)
#   면제(body_safe_patterns)는 '문장'이 아니라 '절' 단위다. 문장을 문장부호·접속어에서 절로 쪼개 상담 구절이 없는 절은 따로 검사하고,
#   용량(body_safe_veto_patterns)이 든 절은 상담 구절이 있어도 면제하지 않는다.
# ----------------------------------------------------------------------------
MIXED_BLOCKED_EN = [
    # 독립 검증(2026-10-26)이 낸 문장 셋
    "Magnesium supplements may help you sleep, but talk to your doctor first.",
    "Vitamin D supplements may lower your blood pressure, so ask your doctor.",
    "Taking 400 mg of magnesium before bed can improve sleep; check with your doctor.",
    # 이음 방식별 변형
    "Magnesium supplements help you sleep — ask your doctor first.",
    "Magnesium supplements help you sleep: ask your doctor first.",
    "Magnesium supplements help you sleep - talk to your pharmacist first.",
    "Magnesium supplements help you sleep -- check with your doctor first.",
    "Magnesium supplements help you sleep, though you should consult a professional.",
    "Magnesium supplements help you sleep although you can ask your doctor.",
    "Magnesium supplements help you sleep but ask your doctor.",
    "Melatonin helps you fall asleep, yet it is wise to talk to a doctor.",
    "Take magnesium supplements nightly, and ask your doctor if you are unsure.",
    "Take magnesium supplements nightly and ask your doctor if you are unsure.",
    "Take magnesium supplements nightly, then talk to your doctor.",
    "Take magnesium supplements nightly (ask your doctor first).",
    "Magnesium supplements help you sleep[ask your doctor first].",
    "Take magnesium supplements nightly, and you should talk to your doctor.",
    "Take magnesium supplements nightly, however, ask your doctor.",
    "Take magnesium supplements nightly, and then ask your doctor.",
    # 상담 구절이 앞에 오고 위험한 권유가 뒤에 오는 문장
    "Talk to your doctor, but magnesium supplements help you sleep.",
    "Check with your pharmacist; melatonin works well for most people.",
    # 질환·보충제를 단정하는 절
    "A daily cup of turmeric tea can reduce inflammation, though you should consult a professional.",
    "Many people with diabetes find that a short walk helps, but ask your doctor.",
    # 용량이 든 절은 상담 구절이 있어도 면제하지 않는다(같은 절 안이라 쪼개지지 않는 문장)
    "Ask your doctor whether 400 mg of magnesium is right for you.",
    "Consult your doctor about taking 5000 IU of vitamin D daily.",
    # D-64 ⑦ N-1: 쉼표 없는 접속어·도입구 — 접속어 바로 뒤에 상담 구절이 오면 쪼갠다(쉼표는 있어도 없어도 된다)
    "Vitamin D supplements may lower your blood pressure so ask your doctor.",            # 검증자의 N-1 문장(쉼표 없음)
    "Vitamin D supplements may lower your blood pressure SO ASK YOUR DOCTOR.",            # 대문자(경계 패턴도 대소문자를 무시한다)
    "Magnesium supplements may help you sleep, which is why you should talk to your doctor first.",
    "Take magnesium supplements nightly, unless you ask your doctor.",
    "Magnesium supplements may help you sleep or ask your doctor.",
    "Melatonin helps many people fall asleep because you should check with your pharmacist.",
    "Take magnesium supplements nightly and then consult your doctor if you feel unsure.",
    "Magnesium supplements may help you sleep, therefore speak with a healthcare professional.",
    "Magnesium supplements may help you sleep so it is wise to ask your doctor.",
    "Magnesium supplements may help you sleep, and make sure to talk to your doctor first.",
    "Magnesium supplements may help you sleep so call your doctor.",                     # 약한 동사(see·call·visit·contact·seek)
    "Take magnesium supplements nightly and see your doctor if you are unsure.",
    "Talk to your doctor first, and take magnesium supplements at night.",               # 상담 구절이 앞에 오고 위험한 권유가 뒤에 오는 문장
    "Magnesium supplements help you sleep, but talk to your doctor first; the rest of the routine is simple.",   # 서로 다른 패턴의 경계가 한 문장에 둘
    # D-64 ⑦ N-5: 대문자 접속어, 문장 끝 !·?
    "Magnesium supplements may help you sleep, BUT talk to your doctor first.",
    "Is it safe to take supplements? Ask your doctor.",
    "Take magnesium supplements nightly! Talk to your doctor if you are unsure.",
    # D-64 ⑦ N-3: 용량 단위(milligrams·grams·units·capsules·영어 숫자말)
    "Ask your doctor whether four hundred milligrams of magnesium supplements is right for you.",
    "Ask your doctor whether 0.4 g of melatonin is right for you.",
    # D-64 ⑧ N2-1: 연결어 바로 뒤에 쉼표가 붙은 모양(연결어마다 하나). 연결어가 있으니 쉼표 이음과 달리 가른다
    "Magnesium supplements may help you sleep, therefore, ask your doctor first.",
    "Magnesium supplements may help you sleep, thus, you should talk to your doctor.",
    "Take magnesium supplements nightly, hence, it is wise to ask your doctor.",
    "Vitamin D supplements may lower your blood pressure, so, please ask your doctor.",
    "Melatonin helps many people fall asleep, because, you should check with your pharmacist.",
    "Take magnesium supplements nightly, unless, you ask your doctor.",
    "Magnesium supplements may help you sleep or, ask your doctor.",
    "Magnesium supplements may help you sleep, but, talk to your doctor first.",
    "Magnesium supplements may help you sleep, so, call your doctor.",                       # 약한 동사
    # D-64 ⑧ N2-4: 허용 목록을 넓힌 도입구·3인칭 주어·두 겹 도입구(쉼표 없는 연결어 + 도입구 + 상담 구절)
    "Magnesium supplements may help you sleep so you might want to ask your doctor.",
    "Magnesium supplements may help you sleep so you may wish to talk to your pharmacist.",
    "Magnesium supplements may help you sleep so you'd better check with your doctor.",
    "Magnesium supplements may help you sleep so you should definitely ask your doctor.",
    "Magnesium supplements may help you sleep so you really should consult a professional.",
    "Magnesium supplements may help you sleep so it would be wise to ask your doctor.",
    "Magnesium supplements may help you sleep so it is advisable to talk to your doctor.",
    "Magnesium supplements may help you sleep so I would suggest you ask your doctor.",
    "Magnesium supplements may help you sleep so we recommend you check with your pharmacist.",
    "Magnesium supplements may help you sleep so please do ask your doctor.",
    "Magnesium supplements may help you sleep so kindly consult a professional.",
    "Magnesium supplements may help you sleep so don't forget to ask your doctor.",
    "Magnesium supplements may help you sleep so feel free to ask your doctor.",
    "Magnesium supplements may help you sleep so do not hesitate to talk to your pharmacist.",
    "Magnesium supplements may help you sleep so always remember to check with your doctor.",
    "Magnesium supplements may help you sleep so take a moment to talk to your doctor.",
    "Magnesium supplements may help you sleep so people should ask their doctor.",
    "Magnesium supplements may help you sleep so they should talk to a professional.",
    "Magnesium supplements may help you sleep so you should make sure to ask your doctor.",
    # D-64 ⑧ N2-4: 동명사·refer to·목록에 없던 연결어
    "Magnesium supplements may help you sleep so asking your doctor is wise.",
    "Magnesium supplements may help you sleep so seeing a doctor is wise.",
    "Magnesium supplements may help you sleep so refer to your doctor.",
    "Magnesium supplements may help you sleep, nevertheless ask your doctor.",
    "Magnesium supplements may help you sleep, accordingly check with your doctor.",
    "Magnesium supplements may help you sleep, for this reason ask your doctor.",
    "Magnesium supplements may help you sleep, that said, ask your doctor.",
    "Magnesium supplements may help you sleep however ask your doctor.",
    "Magnesium supplements may help you sleep so definitely ask your doctor.",
    # D-64 ⑧ N2-4·N2-6: 연결어만으로 가르는 패턴(', so' 뒤가 상담 구절이 아니어도 가른다)이 맡는 문장
    "Magnesium supplements may help you sleep, so many people also see their doctor.",
    "Magnesium supplements may help you sleep, while many people also see their doctor.",
    "Magnesium supplements may help you sleep, yet many people also see their doctor.",
    "Magnesium supplements may help you sleep, then many people also see their doctor.",
    "Magnesium supplements may help you sleep, however, many people also see their doctor.",
    "Magnesium supplements may help you sleep, and then many people also see their doctor.",
]
# 계속 통과해야 하는 정상 상담 안내(질환·임신·약을 이름 붙인 것 포함 — 운영자 결정 3번)
REFERRAL_OK_EN = [
    "If you are pregnant, talk to your doctor before changing your routine.",
    "If you have diabetes or high blood pressure, ask your doctor before starting a new exercise plan.",
    "Check with your doctor before trying a new supplement routine.",
    "Please consult a qualified professional about any diabetes or heart disease concerns, and take it slowly.",
    "Talk to your doctor first, especially if you take medication or are pregnant.",
    "If you take supplements, talk to your doctor, but otherwise keep your routine simple.",
    "Always ask your doctor or pharmacist before taking any supplements.",
    "Ask your pharmacist (or doctor) if you take medication.",
    "Check with your doctor if you have asthma, diabetes, and high blood pressure.",
    "This article is for informational purposes only, but it is not a substitute for medical advice.",
    "Note: if you are pregnant, talk to your doctor.",
    "Health tip: ask your doctor before taking supplements.",
    "People taking medication should talk to a pharmacist first.",
    "If you are on medication, check with your doctor, and keep the rest of your routine simple.",
    "Talk to your doctor if you are pregnant; otherwise this routine is a gentle one.",
    "It is not medical advice, but many people feel calmer after a quiet walk.",
    "If you have a medical condition, consult your doctor - then adjust the plan slowly.",
    "Check with your doctor before using a well-known supplement.",   # 낱말 안의 하이픈은 가르지 않는다
    # 아래 STRICT_TRADE_OFF_* 와 같은 뜻을 한 절로 쓰면 통과한다
    "If you have a health condition, such as diabetes or high blood pressure, talk to your doctor before you begin.",
    "Because pregnancy can change your needs, talk to your doctor.",
    "Pregnant women and people with diabetes should check with a doctor first.",
    "Anyone who is pregnant or has diabetes should check with a doctor first.",
    "People with high blood pressure should ask their doctor before trying new breathing exercises.",
    # D-64 ⑦ N-1 의 새 접속어 경계가 정상 안내를 새로 막지 않는지 — 상담 구절이 먼저 오거나, 접속어 뒤가 상담 구절이 아니거나, 도입구 앞에 접속어가 없는 문장
    "Check with your doctor first because medication can interact with some foods.",
    "Ask your doctor since everyone with a medical condition is different.",
    "Talk to your doctor as soon as you notice symptoms.",
    "Many people with diabetes keep walking while they talk to their doctor about options.",
    "Because you have asthma, you should check with your doctor.",
    "If you have asthma, you should talk to your doctor before changing your routine.",
    "If you take medication, please talk to your doctor first.",
    "If you have a heart condition, make sure to talk to your doctor first.",
    "If you are on medication, remember to check with your doctor.",
    "Whether you take medication or not, it is wise to ask your doctor.",
    "People who take medication or visit a doctor regularly should check with their doctor.",
    "Everyone, including people with asthma, can ask their doctor.",
    # D-64 ⑧: 새 도입구·연결어·동명사가 정상 안내를 새로 막지 않는지 — 연결어 앞에 위험 절이 없거나(쉼표 이음·조건절·문장 첫머리), 주어가 길어 3인칭 목록에 안 걸리는 문장
    "If you take medication, you might want to check with your doctor first.",
    "If you are pregnant, you may wish to ask your pharmacist before changing your routine.",
    "Because you take medication, you'd better talk to your doctor first.",
    "Whether you take medication or not, it would be wise to ask your doctor.",
    "Since everyone is different, I would suggest you ask your doctor first.",
    "If you have a health condition, we recommend you talk to your doctor.",
    "People with asthma should definitely ask their doctor about stretching.",
    "If you take medication, please do talk to your pharmacist.",
    "Anyone who is pregnant should ask their doctor first.",
    "Pregnant women and anyone taking medication should talk to their doctor.",
    "However, ask your doctor if you take medication.",
    "Seeing a doctor is wise if you take medication.",
    "If you have asthma, referring to a specialist may help.",
    "People taking medication, therefore, should ask their doctor.",
    "If you are on medication, kindly consult your doctor.",
    "If you take medication, feel free to ask your doctor, and do not hesitate to call.",
    "If you have a heart condition, it makes sense to talk to your doctor.",
]
MIXED_BLOCKED_KO = [
    "마그네슘 보충제는 잠드는 데 도움이 될 수 있지만 먼저 의사와 상담하세요.",
    "비타민 보충제를 드시되 의사와 상담하세요.",
    "혈압을 낮출 수 있는데, 의사와 상담해 보세요.",
    "보충제를 챙겨 드시고 의사와 상담하세요.",
    "보충제가 잠에 도움이 됩니다 — 의사와 상담하세요.",
    "멜라토닌을 드세요; 의사와 상담하세요.",
    "보충제를 드세요 (의사와 상담하세요).",
    "400mg을 드시고 의사와 상담하세요.",
    "의사와 상담하면 400mg 정도가 적당해요.",          # 용량이 든 절은 상담 구절이 있어도 면제하지 않는다
    "보충제는 도움이 되지만, 의사와 상담하세요.",
    "혈당이 낮아질 수 있으나 의사와 상담하세요.",
    "보충제는 도움이 됩니다, 그러나 의사와 상담하세요.",
    # D-64 ⑦ N-1: 쉼표 없는 접속어·'고,'·'서'·'고 나서'·괄호 안의 부사
    "마그네슘 보충제는 잠드는 데 도움이 돼요, 그래서 먼저 의사와 상담하세요.",
    "혈압이 높을 수 있어요 따라서 의사와 상담하세요.",
    "혈압이 높을 수 있어요, 그러므로 의사와 상담하세요.",
    "혈압이 높을 수 있어요 그러니까 먼저 의사와 상담하세요.",
    "혈압이 높을 수 있어요, 그러니 의사와 상담하세요.",
    "마그네슘 보충제는 잠드는 데 도움이 돼서 먼저 의사와 상담하세요.",
    "보충제를 챙겨 드시고, 의사와 상담하세요.",
    "보충제를 챙겨 드시고 나서 먼저 의사와 상담하세요.",
    "보충제를 드세요 (먼저 의사와 상담하세요).",
    # D-64 ⑦ N-5: 문장 끝 ?
    "보충제를 드셔도 될까요? 의사와 상담하세요.",
    "보충제를 드세요 (의사와 상담하세요); 나머지 일과는 간단해요.",                                  # 서로 다른 패턴의 경계가 한 문장에 둘
    # D-64 ⑦ N-3 · N-5: 용량 단위(알·정·캡슐·g)와 띄어 쓴 mg
    "의사와 상담해서 멜라토닌 2알을 정하세요.",
    "의사와 상담해서 멜라토닌 0.4 g을 정하세요.",
    "의사와 상담하면 400 mg 정도가 적당해요.",
    # D-64 ⑧ N2-1: 연결어 바로 뒤의 쉼표
    "혈압이 높을 수 있어요, 그러므로, 의사와 상담하세요.",
    "혈압이 높을 수 있어요, 그러니, 먼저 의사와 상담하세요.",
    "혈압이 높을 수 있어요, 따라서, 의사와 상담하세요.",
    "마그네슘 보충제는 잠드는 데 도움이 돼서, 의사와 상담하세요.",
    "보충제는 도움이 됩니다, 그러나, 의사와 상담하세요.",
    # D-64 ⑧ N2-3: '그러므로' 계열의 접속 부사
    "혈압이 높을 수 있어요, 그렇기 때문에 의사와 상담하세요.",
    "혈압이 높을 수 있어요, 이 때문에 의사와 상담하세요.",
    "혈압이 높을 수 있어요, 그런 이유로 의사와 상담하세요.",
    # D-64 ⑧ N2-3: 안전 패턴이 인식하는 상담 낱말(경계 패턴이 몰라서 통과하던 것)
    "혈압이 높을 수 있어요, 그래서 주치의와 상담하세요.",
    "혈압이 높을 수 있어요, 그래서 한의원에서 상담하세요.",
    "혈압이 높을 수 있어요, 그래서 영양사와 상담하세요.",
    "혈압이 높을 수 있어요, 그래서 의료 전문가와 상담하세요.",
    "혈압이 높을 수 있어요, 그래서 가까운 병원에서 의사와 상담하세요.",
    "혈압이 높을 수 있어요, 그래서 반드시 먼저 전문의와 상담하세요.",
    "보충제를 챙겨 드시고 주치의와 상담하세요.",
    "보충제를 챙겨 드세요 (한의원에서 상담하세요).",
]
REFERRAL_OK_KO = [
    "임신 중이거나 약을 복용 중이라면 의사와 상담한 뒤 시작하세요.",
    "당뇨나 고혈압이 있다면 병원에서 먼저 확인해 보세요.",
    "건강에 대한 고민이 있다면 의사·약사 등 전문가와 상담하세요.",
    "혈압약을 드시는 분은 의사와 상담하세요.",
    "이 글은 진단이나 치료를 대신하지 않습니다.",
    "몸이 불편하면 전문가와 상담해 보는 것이 좋아요.",
    "일반적인 참고용이며 진단이나 치료를 대신하지 않습니다.",
    "복용 중인 약이 있다면 의사와 상담하세요.",
    "임신 중에는 몸 상태가 달라질 수 있어 의사와 상담하세요.",
    "임신 중이면 의사와 상담하세요.",
    "혈압이 걱정되면 병원에서 의사와 상담하세요.",          # '에서'(장소)는 '서' 접속 어미가 아니다
    "임신 중이라면 가까운 병원에서 전문의와 상담하세요.",
    "집에서 쉬다가 불편하면 의사와 상담하세요.",
    "보충제를 드시기 전에는 꼭 의사와 상담하세요.",
    # D-64 ⑧ N2-3: 후치사처럼 쓰인 `~서`(…에 대해서·관해서·위해서·통해서·인해서·비해서·의해서·관련해서·로서·에 따라서·앞서·여기서)는 접속 어미가 아니라서 가르지 않는다
    "임신 중에는 영양제에 대해서 의사와 상담하세요.",
    "혈압에 관해서 의사에게 문의하세요.",
    "임신 중에는 안전을 위해서 의사와 상담하세요.",
    "혈압 측정 결과를 통해서 의사와 상담하세요.",
    "혈당 변화로 인해서 의사와 상담이 필요할 수 있어요.",
    "임신 중에는 이전에 비해서 의사와 상담하는 횟수를 늘리세요.",
    "임신 중에는 의사의 설명에 의해서 약사와 상담하세요.",
    "복용 중인 약과 관련해서 약사와 상담하세요.",
    "당뇨 환자로서 의사와 상담하세요.",
    "혈압에 따라서 의사와 상담하세요.",
    "보충제를 시작하기에 앞서 의사와 상담하세요.",
    "수술 전에 앞서서 의사와 상담하세요.",
    "임신 중에는 여기서 의사와 상담하세요.",
    "임신 중에는 의사에게서 약사에게서 모두 확인하세요.",
    "임신 중에는 의사한테서 약사한테서 모두 확인하세요.",
    # D-64 ⑧: 접속 어미·괄호 뒤가 상담 구절일 때만 가른다 — 뒤가 다른 말이면 한 절이라 면제된다(경계 패턴의 앞내다보기를 지우면 이 문장들이 막힌다)
    "임신 중에는 천천히 시작하세요 (자세한 내용은 의사와 상담하세요).",
    "임신 중이라면 쉬고 천천히 걷는 것이 좋고, 불편하면 의사와 상담해 보세요.",
    "임신 중에는 몸 상태가 달라질 수 있어요, 그러므로 천천히 시작하고 불편하면 의사와 상담하세요.",
    "임신 중에는 몸이 달라져서 천천히 시작하고 불편하면 의사와 상담하세요.",
]
# 알려진 과잉 차단(의도한 트레이드오프, D-64 ⑥ a). 병명을 이름 붙인 절과 상담 구절이 `, so`·`—`·`:`·`;`·`으니`로 나뉜 정상 안내도 막는다 —
# '위험한 권유, so 의사에게 물어보세요'(MIXED_BLOCKED_*)와 구조로는 구별되지 않기 때문이다. 같은 뜻을 한 절로 쓰면(위 REFERRAL_OK_*) 통과한다.
# 이 문장들이 통과하게 바뀌면 그 결정을 일부러 뒤집는 것이니, 시험과 docs/ARCHITECTURE.md §7-1 '절 단위 면제'의 한계 문단을 같이 고친다.
STRICT_TRADE_OFF_EN = [
    "Pregnancy can change your needs, so talk to your doctor.",
    "If you have a health condition—such as diabetes or high blood pressure—talk to your doctor before you begin.",
    "Who should check with a doctor first: pregnant women, people with diabetes, and anyone on medication.",
    "Some people take supplements; if you do, talk to your doctor first.",
    "People with high blood pressure — ask your doctor before trying new breathing exercises.",
    # D-64 ⑦ N-1 로 쉼표 없는 접속어와 도입구까지 닫으면서 같이 막히게 된 정상 안내(같은 모양 — 위험한 낱말이 든 절 + 접속어 + 상담 절)
    "Medication can interact with food, which is why you should talk to your doctor.",
    "Do not start any new supplement unless you check with your doctor first.",
    "People with asthma can then ask their doctor about stretching.",
    "Pregnant women should rest and then check with their doctor if they feel dizzy.",
    "Pregnant women should rest, otherwise check with their doctor.",
    # D-64 ⑧ N2-2: `or`·`unless`·`, then` 계열도 같은 모양이라 막는다. 풀지 말지는 첫 실제 영어 초안의 BODY_TOPIC 빈도를 보고 정한다(WORKLOG)
    "Stay home if you have symptoms, or talk to a healthcare professional.",
    "People with high blood pressure should skip this routine or ask their doctor first.",
    "If you have diabetes, keep the routine gentle or check with your doctor.",
    "Avoid this exercise if you have asthma unless you check with your doctor.",
    "If you have high blood pressure, then talk to your doctor before changing your routine.",
    "If you are pregnant, then check with your doctor first.",
    # D-64 ⑧ N2-4: 도입구·3인칭 주어까지 넓힌 값
    "Heart conditions vary a lot, so you may want to check with your doctor before you begin.",
    "Everyone responds differently to medication, which is why people should ask their doctor.",
]
STRICT_TRADE_OFF_KO = [
    "임신 중에는 몸 상태가 달라질 수 있으니 의사와 상담하세요.",
    "임신 중이라서 의사와 상담이 필요해요.",
    "혈압이 높을 수 있어요, 그래서 의사와 상담하세요.",
    # D-64 ⑧ N2-3: 같은 뜻의 접속 부사(그렇기 때문에·이 때문에)도 '그러므로'처럼 막는다
    "임신 중에는 몸 상태가 달라질 수 있어요, 그렇기 때문에 의사와 상담하세요.",
]


class ClauseScopedExemptionTest(unittest.TestCase):
    def test_the_three_sentences_from_the_independent_review_are_blocked_by_the_body_guard(self):
        for sentence in MIXED_BLOCKED_EN[:3]:
            with self.subTest(sentence):
                self.assertIn("BODY_TOPIC", check(EN, sentence=sentence).codes(), sentence)

    def test_every_mixed_sentence_is_blocked_in_both_languages(self):
        for profile, sentences in ((EN, MIXED_BLOCKED_EN), (KO, MIXED_BLOCKED_KO)):
            for sentence in sentences:
                with self.subTest(sentence):
                    self.assertIn("BODY_TOPIC", check(profile, sentence=sentence).codes(), sentence)

    def test_ordinary_referral_sentences_still_pass_with_no_reason_at_all(self):
        for profile, sentences in ((EN, REFERRAL_OK_EN), (KO, REFERRAL_OK_KO)):
            for sentence in sentences:
                with self.subTest(sentence):
                    self.assertEqual(check(profile, sentence=sentence).codes(), [], sentence)

    def test_every_sentence_terminator_starts_a_new_sentence(self):
        """. ! ? 와 전각 。 ！ ？ 는 모두 문장 경계다(D-64 ⑦ N-5): 위험한 문장과 상담 문장이 서로를 면제하지 않는다."""
        for terminator in (".", "!", "?", "。", "！", "？"):
            sentence = f"Take magnesium supplements nightly{terminator} Talk to your doctor if you are unsure."
            with self.subTest(terminator):
                self.assertIn("BODY_TOPIC", check(EN, sentence=sentence).codes(), sentence)

    def test_a_locative_particle_is_not_a_connective_ending(self):
        """한국어 '서' 접속 어미(돼서·해서)는 가르지만 장소의 '에서'(병원에서)는 가르지 않는다 — '병원에서 의사와 상담하세요'는 한 절이다."""
        splitters = gates._clause_splitter(KO)
        self.assertEqual(gates._split_clauses("혈압이 걱정되면 병원에서 의사와 상담하세요", splitters), ["혈압이 걱정되면 병원에서 의사와 상담하세요"])
        self.assertEqual(len(gates._split_clauses("혈압이 걱정돼서 의사와 상담하세요", splitters)), 2)

    def test_known_over_blocks_stay_blocked_until_the_decision_is_reversed_on_purpose(self):
        for profile, sentences in ((EN, STRICT_TRADE_OFF_EN), (KO, STRICT_TRADE_OFF_KO)):
            for sentence in sentences:
                with self.subTest(sentence):
                    self.assertIn("BODY_TOPIC", check(profile, sentence=sentence).codes(), sentence)

    def test_the_new_scope_is_what_blocks_them_not_some_other_gate(self):
        """프로필의 절 경계·면제 취소 목록을 비우면 같은 문장이 (예전처럼) 면제돼 통과한다. 다른 게이트가 대신 막는 것이 아니다."""
        loose = copy.deepcopy(EN)
        loose["body_clause_split_patterns"] = []
        for sentence in ("Magnesium supplements may help you sleep, but talk to your doctor first.",
                         "Vitamin D supplements may lower your blood pressure, so ask your doctor.",
                         "Take magnesium supplements nightly and ask your doctor if you are unsure."):
            with self.subTest(sentence):
                self.assertEqual(check(loose, sentence=sentence).codes(), [], sentence)
                self.assertIn("BODY_TOPIC", check(EN, sentence=sentence).codes(), sentence)
        no_veto = copy.deepcopy(EN)
        no_veto["body_safe_veto_patterns"] = []
        sentence = "Ask your doctor whether 400 mg of magnesium is right for you."
        self.assertEqual(check(no_veto, sentence=sentence).codes(), [], sentence)
        self.assertIn("BODY_TOPIC", check(EN, sentence=sentence).codes(), sentence)
        loose_ko = copy.deepcopy(KO)
        loose_ko["body_clause_split_patterns"] = []
        sentence = "마그네슘 보충제는 잠드는 데 도움이 될 수 있지만 먼저 의사와 상담하세요."
        self.assertEqual(check(loose_ko, sentence=sentence).codes(), [], sentence)

    def test_punctuation_boundaries_work_without_any_profile_list(self):
        """; : — -- 와 띄어 쓴 하이픈은 모든 언어에 공통이라 코드에 있다. 프로필에 목록이 없어도(예: 앞으로 만들 다른 프로필) 쪼갠다."""
        bare = copy.deepcopy(EN)
        del bare["body_clause_split_patterns"], bare["body_safe_veto_patterns"]
        self.assertEqual(registry.validate_profile(bare), [])
        for separator in ("; ", ": ", " — ", "—", " ― ", " -- ", "--", " - ", " – "):
            sentence = f"Magnesium supplements help you sleep{separator}ask your doctor first."
            with self.subTest(separator):
                self.assertIn("BODY_TOPIC", check(bare, sentence=sentence).codes(), sentence)
        for sentence in ("Ask your doctor before using a well-known supplement.", "Talk to your doctor about the 2-3 supplements you take."):
            with self.subTest(sentence):
                self.assertEqual(check(bare, sentence=sentence).codes(), [], sentence)  # 낱말·범위 안의 하이픈은 가르지 않는다

    def test_a_split_pattern_with_a_capturing_group_never_leaks_its_text_as_a_clause(self):
        """re.split 은 묶음 괄호의 내용까지 조각으로 돌려준다. 경계 위치만 쓰므로 프로필이 묶음 괄호를 써도 조각이 늘지 않는다."""
        splitter = gates._clause_splitter({"body_clause_split_patterns": [r"\s+(but)\s+"]})
        self.assertEqual(gates._split_clauses("tea helps but ask your doctor", splitter), ["tea helps", "ask your doctor"])
        self.assertEqual(gates._split_clauses("a; b — c", gates._clause_splitter({})), ["a", "b", "c"])
        zero_width = gates._clause_splitter({"body_clause_split_patterns": [r"(?<=x)(?=y)"]})
        self.assertEqual(gates._split_clauses("xyz", zero_width), ["xyz"])  # 길이 0 경계는 무시

    def test_boundaries_from_different_patterns_are_merged_in_text_order(self):
        """패턴마다 따로 찾은 경계를 글에서의 순서대로 하나로 합친다(D-64 ⑦ N-4): 맞닿은 경계는 빈 조각을 남기지 않고, 겹친 경계는 가장 먼 끝까지 합치며,
        뒤 패턴의 경계가 앞 패턴의 경계보다 글에서 앞서도 잃지 않는다."""
        touching = gates._clause_splitter({"body_clause_split_patterns": [r",\s+so", r";\s*"]})
        self.assertEqual(gates._split_clauses("a, so; b", touching), ["a", "b"])                                  # ', so' 바로 뒤에 '; ' — 빈 조각 없음
        overlapping = gates._clause_splitter({"body_clause_split_patterns": [r"\s+and\s+then\s+ask\s+", r"then"]})
        self.assertEqual(gates._split_clauses("tea and then ask your doctor", overlapping), ["tea", "your doctor"])  # 안쪽 경계가 바깥 경계를 줄이지 않는다
        out_of_order = gates._clause_splitter({"body_clause_split_patterns": [r";\s*", r"\s+but\s+"]})
        self.assertEqual(gates._split_clauses("a but b; c", out_of_order), ["a", "b", "c"])                       # 목록 순서와 글 순서가 달라도 둘 다 가른다

    def test_an_efficacy_claim_is_still_blocked_whatever_the_clause_layout(self):
        for sentence in ("Ask your doctor; this stretch is a miracle for tired mornings.",
                         "Talk to your doctor — it is 100% effective for everyone."):
            with self.subTest(sentence):
                self.assertIn("BANNED", check(EN, sentence=sentence).codes(), sentence)

    def test_every_profile_boundary_pattern_is_needed_by_one_of_the_sentences(self):
        """경계 패턴을 하나 지우면 그것만으로 막히던 문장이 통과해야 한다(약하게 만든 패턴을 시험이 모르고 지나가지 않게)."""
        for profile, sentences in ((EN, MIXED_BLOCKED_EN), (KO, MIXED_BLOCKED_KO)):
            patterns = profile["body_clause_split_patterns"]
            for index, pattern in enumerate(patterns):
                without = {**profile, "body_clause_split_patterns": patterns[:index] + patterns[index + 1:]}
                owned = [s for s in sentences if gates.body_risk_hit(s, profile) != (None, None) and gates.body_risk_hit(s, without) == (None, None)]
                with self.subTest(f"{profile['name']}: {pattern}"):
                    self.assertTrue(owned, "이 경계 패턴이 있어야만 막히는 문장이 없다")

    def test_the_veto_pattern_is_needed_by_a_sentence(self):
        for profile, sentences in ((EN, MIXED_BLOCKED_EN), (KO, MIXED_BLOCKED_KO)):
            patterns = profile["body_safe_veto_patterns"]
            for index, pattern in enumerate(patterns):
                without = {**profile, "body_safe_veto_patterns": patterns[:index] + patterns[index + 1:]}
                owned = [s for s in sentences if gates.body_risk_hit(s, profile) != (None, None) and gates.body_risk_hit(s, without) == (None, None)]
                with self.subTest(f"{profile['name']}: {pattern}"):
                    self.assertTrue(owned, "이 면제 취소 패턴이 있어야만 막히는 문장이 없다")

    def test_the_disclosures_and_safe_samples_are_not_vetoed(self):
        """면제 취소(용량)는 면책 문구·상담 안내를 막지 않는다."""
        for profile in (EN, KO):
            plain = gates.plain_text(profile["disclosure_html"])
            self.assertEqual(gates.body_risk_hit(plain, profile), (None, None))
        for sentence in EN_SAFE_RULE_SAMPLES:
            self.assertEqual(gates.body_risk_hit(sentence, EN), (None, None), sentence)


# 검증자의 연결어 그리드(D-64 ⑦ N-1): 위험한 절 4 × 상담 구절 4 × 연결어. 닫은 연결어는 열여섯 문장이 모두 막히고,
# 일부러 안 닫은 연결어(쉼표로만 이은 모양과 같은 계열)는 지금 그대로 통과한다 — docs/ARCHITECTURE.md §7-1 의 한계 목록과 같다.
GRID_RISKY_EN = ["Magnesium supplements may help you sleep", "Melatonin helps many people fall asleep", "A turmeric supplement can reduce inflammation",
                 "Vitamin D supplements may lower your blood pressure"]
GRID_REFER_EN = ["talk to your doctor first", "ask your doctor", "check with your pharmacist", "consult a healthcare professional"]
GRID_CLOSED_EN = [", but ", " but ", ", yet ", " yet ", ", so ", " so ", ", while ", " while ", ", though ", " though ", ", although ", " although ", ", whereas ",
                  ", however, ", ", and ", " and ", ", or ", " or ", ", then ", " then ", ", because ", ", since ", ", as ", ", which means you should ",
                  ", so make sure to ", ", and make sure to ", ", but remember to ", ", unless you ", ", otherwise ", ", except that you should ",
                  ", though you should ", ", plus ", ", meaning you can ", ", thus you should ", ", therefore ", ", hence ", ", and you should ", ", and you can ",
                  ", but you can ", ", and it is wise to ", ", but it is best to ", ", and it helps to ", ", but it is always wise to ", ", which is why you should ",
                  ", so it is wise to ", " (", " [", " – ", " - ", " — ", "; ", ": ", ". ", "! ", "? ", "\n", ", and then ", ", and so ", ", and yet ",
                  # D-64 ⑧ N2-1: 연결어 바로 뒤의 쉼표
                  ", so, ", " so, ", ", yet, ", " yet, ", ", while, ", ", then, ", ", or, ", " or, ", ", and, ", " and, ", ", because, ", ", since, ", ", as, ", ", unless, ", ", otherwise, ",
                  ", therefore, ", ", thus, ", ", hence, ", ", plus, ", ", but, ", ", although, ", ", though, ", ", whereas, ", ", however, ", ", and then, ",
                  ", which is why, you should ", ", meaning, you can ", ", so, you should ", ", therefore, it is wise to ",
                  # D-64 ⑧ N2-4: 쉼표 없는 연결어 + 허용 목록을 넓힌 도입구·3인칭 주어, 목록에 없던 연결어
                  " so you might want to ", " so you may wish to ", " so you'd better ", " so you should definitely ", " so you really should ", " so it would be wise to ",
                  " so it is advisable to ", " so I would suggest you ", " so we recommend you ", " so please do ", " so kindly ", " so don't forget to ", " so feel free to ", " so do not hesitate to ", " so always remember to ",
                  " so take a moment to ", " so people should ", " so they should ", " so everyone should ", " so you should make sure to ", " because you might want to ",
                  " or you might want to ", " so definitely ", " so please, ", ", however ", " however ", ", accordingly ", ", consequently ", ", for this reason ",
                  ", for that reason ", ", nevertheless ", ", nonetheless ", ", that said, ", ", even so, "]    # 'even so'는 연결어 `so`가 가른다
GRID_OPEN_EN = [", ", ", if you want, ", ", also ", ", just ", ", please ", ", of course, ", ", remember to ", ", be sure to ", ", make sure to ",
                # D-64 ⑧: 연결어 뒤의 부사절 도입구('조건절 + 쉼표 + 상담 구절'과 구별되지 않는다)와 상담 구절을 앞세우지 않는 연결어
                " so if in doubt, ", " so to be safe, ", " so of course, ", ", to be safe, ", ", still ", ", in case you want to ", " so that you can "]
GRID_STEMS_KO = ["마그네슘 보충제는 잠드는 데 도움이 되", "멜라토닌을 먹으면 잠이 잘 오", "이 영양제는 혈압을 낮춰 주"]
GRID_REFERRAL_KO = "먼저 의사와 상담하세요."
GRID_CLOSED_KO = ["{a}지만 {r}", "{a}지만, {r}", "{a}는데 {r}", "{a}는데, {r}", "{a}으니 {r}", "{a}니까 {r}", "{a}면서 {r}", "{a}으며 {r}", "{a}하되 {r}", "{a}고 {r}",
                  "{a}고, {r}", "{a}. 다만 {r}", "{a}, 다만 {r}", "{a}, 그러나 {r}", "{a}, 그래서 {r}", "{a}, 따라서 {r}", "{a}, 그러므로 {r}", "{a}, 그러니 {r}",
                  "{a}; {r}", "{a} — {r}", "{a} ({r})", "{a}(참고: {r})", "{a}서 {r}", "{a}지만 그래도 {r}", "{a}지만 꼭 {r}", "{a}지만 반드시 {r}", "{a}고 나서 {r}",
                  # D-64 ⑧ N2-1·N2-3: 연결어 바로 뒤의 쉼표, 그러므로 계열 접속 부사
                  "{a}, 그러므로, {r}", "{a}, 그러니, {r}", "{a}, 따라서, {r}", "{a}, 그래서, {r}", "{a}서, {r}", "{a}, 그러나, {r}",
                  "{a}, 그렇기 때문에 {r}", "{a}, 이 때문에 {r}", "{a}, 그런 이유로 {r}", "{a}, 이런 이유로, {r}"]
# 일부러 열어 둔 한국어 연결: 쉼표 이음·`~는 점,`와 같은 계열이거나(`므로`·`기 때문에`·`다 보니`·`거나`·`또는`·`또한`·`그러면`·`물론`), 막으면 정상 안내 오탐이 느는 것(`므로`: 검증자의
# 정상 안내 '…달라지므로 의사와 상담하세요'가 새로 막힌다)
GRID_OPEN_KO = ["{a}, {r}", "{a}는 점, {r}", "{a}므로 {r}", "{a}기 때문에 {r}", "{a}다 보니 {r}", "{a}거나 {r}", "{a}든지 {r}", "{a}, 또는 {r}", "{a}, 아니면 {r}",
                "{a}, 또한 {r}", "{a}, 게다가 {r}", "{a}, 그러면 {r}", "{a}, 물론 {r}"]


class ConnectorGridTest(unittest.TestCase):
    @staticmethod
    def english(risky, connector, referral):
        closing = {"(": ")", "[": "]"}.get(connector.strip(), "")
        return f"{risky}{connector}{referral}{closing}."

    def test_every_closed_english_connector_blocks_all_sixteen_sentences(self):
        for connector in GRID_CLOSED_EN:
            with self.subTest(connector):
                for risky in GRID_RISKY_EN:
                    for referral in GRID_REFER_EN:
                        sentence = self.english(risky, connector, referral)
                        self.assertNotEqual(gates.body_risk_hit(sentence, EN), (None, None), sentence)

    def test_every_closed_korean_template_blocks_all_three_stems(self):
        for template in GRID_CLOSED_KO:
            with self.subTest(template):
                for stem in GRID_STEMS_KO:
                    sentence = template.format(a=stem, r=GRID_REFERRAL_KO)
                    self.assertNotEqual(gates.body_risk_hit(sentence, KO), (None, None), sentence)

    def test_the_connectors_left_open_on_purpose_still_pass(self):
        """쉼표(또는 '는 점,')만으로 이은 상담 구절은 'If you are pregnant, talk to your doctor'와 모양이 같아 구별할 수 없다. 닫으면 이 시험과 문서의 한계 목록을 같이 고친다."""
        for connector in GRID_OPEN_EN:
            with self.subTest(connector):
                for risky in GRID_RISKY_EN:
                    for referral in GRID_REFER_EN:
                        sentence = self.english(risky, connector, referral)
                        self.assertEqual(gates.body_risk_hit(sentence, EN), (None, None), sentence)
        for template in GRID_OPEN_KO:
            with self.subTest(template):
                for stem in GRID_STEMS_KO:
                    sentence = template.format(a=stem, r=GRID_REFERRAL_KO)
                    self.assertEqual(gates.body_risk_hit(sentence, KO), (None, None), sentence)


class ListItemAndFoldingTest(unittest.TestCase):
    """줄바꿈(목록 항목)으로 문장을 가르는 규칙과 사유 문구의 한 줄 접기를 고정한다(독립 검증이 변이로 지운 부분, D-64 ⑥ e)."""

    def test_list_items_are_judged_one_by_one(self):
        """<li> 는 마침표 없이 끝나므로 줄바꿈이 문장 경계다. 줄바꿈으로 가르지 않으면 한 항목의 위험 권유가 다음 항목의 상담 구절에 면제된다."""
        post, stats = stub_post(EN)
        risky = "<ul><li>Take magnesium supplements every night</li><li>Talk to your doctor if you are unsure</li></ul>"
        self.assertIn("BODY_TOPIC", gates.check_post({**post, "content": post["content"] + risky}, EN, [], [], stats).codes())
        self.assertIsNotNone(gates.body_risk_hit("Take magnesium supplements every night\nTalk to your doctor if you are unsure", EN)[0])
        safe = "<ul><li>If you take supplements, talk to your doctor</li><li>Drink water through the day</li></ul>"
        self.assertEqual(gates.check_post({**post, "content": post["content"] + safe}, EN, [], [], stats).codes(), [])
        ko_post, ko_stats = stub_post(KO)
        ko_risky = "<ul><li>보충제를 매일 밤 드세요</li><li>궁금하면 의사와 상담하세요</li></ul>"
        self.assertIn("BODY_TOPIC", gates.check_post({**ko_post, "content": ko_post["content"] + ko_risky}, KO, [], [], ko_stats).codes())

    def test_the_matched_word_in_a_body_reason_is_folded_to_one_short_line(self):
        word = "chiropract" + "x" * 80       # \bchiropract\w* 는 끝없이 이어지는 낱말도 잡는다
        reasons = [r for r in check(EN, sentence=f"A {word} visit.").reasons if r.startswith("[BODY_TOPIC]")]
        self.assertEqual(len(reasons), 1)
        quoted = re.search(r"'([^']*)'", reasons[0]).group(1)
        self.assertLessEqual(len(quoted), 40)
        self.assertTrue(quoted.endswith("…"), quoted)
        self.assertNotIn("\n", reasons[0])


class EnglishVariantAndHardeningTest(unittest.TestCase):
    """영어 두 낱말 용어의 하이픈·붙여 쓰기·동의어 변형과 다이어트·간 건강(D-64 ⑥ d·f)."""
    FORBIDDEN = [
        "blood-pressure", "bloodpressure", "Blood-Sugar Friendly Meals", "blood sugar-friendly meals", "blood-glucose checks",
        "sleeping tablets", "sleep aid", "sleep aids", "sleep-aid gadgets", "sleeping-tablet tips",
        "shed pounds fast", "shedding weight", "shed a few inches", "drop a few kilos", "dropping 10 lbs", "dropped 5 pounds",
        "heart-disease facts", "heart-attack signs", "heart-failure facts", "panic-attack tips", "mental-health crisis lines", "kidney-stone diets", "fatty-liver friendly snacks",
        "crash-diet tips", "calorie-deficit math", "pain-reliever shelf", "chronic-pain routines", "vitamin-gummies",
        "expecting-mothers brunch", "nursing-mothers tips", "eating-disorder awareness", "sleep-apnea gadgets", "intermittent-fasting basics",
        "50 μg", "50 µg", "400mg", "5000 IU",                                   # 용량(그리스 뮤·마이크로 기호·붙여 쓴 단위)
        "liver health", "liver-health tips", "liver function", "healthy liver habits", "support your liver",
        "dieting", "diet plan", "diet-plan templates", "diet pills", "diet culture", "diet programs", "dieters",
        "belly fat", "body-fat checks", "visceral fat", "menopause", "perimenopause", "postmenopausal", "boost your immunity",
    ]
    # 낱말 일부나 일상 표현만 겹치는 것. 단독 diet·balanced diet 는 일상어라 막지 않는다
    ALLOWED = [
        "liver and onions for a quick dinner", "Deliver your weekly plan on time", "A healthy diet of small habits", "Dietary fiber basics",
        "Meet a dietitian-approved snack", "A garden shed makeover", "Shed light on your evening routine", "Drop by a friend's place",
        "Drop the phone one hour earlier", "Capsule wardrobe checklist", "Tablet-free evenings", "Body language basics",
        "Belly laughs with friends", "Sleep-friendly bedroom colors", "Sleep tracker comparison", "Balanced diet basics", "Blood orange smoothie",
    ]

    def test_every_variant_is_blocked_as_a_topic_a_title_a_label_and_in_the_body(self):
        for phrase in self.FORBIDDEN:
            with self.subTest(phrase):
                self.assertFalse(gates.topic_allowed(phrase, EN), phrase)
                self.assertIn("TITLE_TOPIC", check(EN, {"title": f"A Calm Evening With {phrase.title()} Ideas"}).codes(), phrase)
                self.assertIn("LABELS", check(EN, {"labels": ["habits", phrase[:30]]}).codes(), phrase)
                self.assertIn("BODY_TOPIC", check(EN, sentence=f"Many readers ask about {phrase} these days.").codes(), phrase)

    def test_look_alike_phrases_are_not_blocked(self):
        for phrase in self.ALLOWED:
            with self.subTest(phrase):
                self.assertTrue(gates.topic_allowed(phrase, EN), phrase)
                self.assertEqual(check(EN, sentence=f"{phrase}.").codes(), [], phrase)

    def test_a_dietitian_is_still_a_valid_professional_to_ask(self):
        self.assertEqual(check(EN, sentence="Ask a registered dietitian before changing how you eat.").codes(), [])

    def test_the_english_prompt_tells_the_model_the_same_words(self):
        prompt = (_bootstrap.ROOT / ".github" / "editorial" / "BLOGGER_PROMPT_EN.md").read_text(encoding="utf-8").lower()
        for fragment in ("weight loss, dieting or liver health",):
            self.assertIn(fragment, prompt)
        self.assertIn("dieting or liver health", " ".join(EN["prompt_extra"]).lower())
        self.assertIn("다이어트·간 건강", " ".join(KO["prompt_extra"]))


KO_NEW_WORDS = [
    "혈압", "고혈압", "저혈압", "혈당", "불면", "불면증", "콜레스테롤", "치매", "갱년기", "폐경", "편두통", "면역", "면역력", "임상", "접종", "예방접종",
    "스테로이드", "침술", "카이로프랙틱", "항생제", "진통제", "수면제", "해열제", "항우울제", "소염제", "알약", "건강기능식품", "멜라토닌", "종합 비타민",
    "멀티비타민", "비타민제", "증상", "환자", "감염", "천식", "관절염", "갑상선", "빈혈", "비만", "골다공증", "지방간", "간염", "뇌전증", "자폐", "조현병",
    "알츠하이머", "파킨슨", "양극성", "강박증", "불안장애", "섭식장애", "거식증", "폭식증", "종양", "항암", "백혈병", "림프종", "심장병", "심근경색",
    "뇌졸중", "협심증", "부정맥", "동맥경화", "심혈관", "디톡스", "단식", "간헐적 단식", "키토제닉", "키토 식단", "저탄고지", "체지방", "지방 연소",
    "지방 분해", "슬리밍", "간 건강", "간 기능", "간 수치", "간 질환", "간 해독", "요법", "임산부", "산모", "출산", "다이어트", "400mg", "5000IU",
    "밀리그램", "마이크로그램",
]
# 일상어와 겹칠 뿐인 한국어(막으면 오탐). '비타민'(단독)·'통증'·'알레르기'·'아이'는 열린 운영자 결정(D-64 ④)이라 일부러 넣지 않았다
KO_LOOKALIKES = ["간단한 식단 정리", "간식 시간 정하기", "시간 건강하게 쓰는 법", "주사위 놀이", "하루 3분 투자해서 정리하기", "암막 커튼 달기", "간단식 도시락",
                 "분단식 구조", "단순한 하루", "출근길 산책", "감사 메모 쓰기", "환기와 정리", "혈액순환에 좋은 스트레칭", "수면 시간을 일정하게",
                 "비타민 D가 들어 있는 햇빛 산책", "통증 없이 가볍게 움직이기", "아이와 함께하는 저녁 산책", "알레르기 걱정 없는 환기법"]
KO_BENIGN_SENTENCES = [
    "오늘은 작은 습관 하나만 골라서 가볍게 시작해 보세요.", "점심시간에 15분 정도 걸으면 기분 전환에 도움이 될 수 있어요.",
    "자기 전에 화면을 줄이면 편안한 밤을 보내는 데 도움이 돼요.", "물병을 눈에 띄는 곳에 두면 자주 마시기 쉬워요.",
    "책상 위를 5분만 정리해도 다음 날 아침이 한결 가벼워져요.", "일주일에 한 번 돌아보며 나에게 맞게 조금씩 고쳐 가면 돼요.",
    "스트레칭은 무리하지 않는 범위에서 천천히 해 보세요.", "몸이 불편하면 전문가와 상담해 보는 것이 좋아요.",
    "퇴근 후 10분 동안 창문을 열어 환기하고 가볍게 정리해 보세요.", "비 오는 날에는 집 안에서 할 수 있는 작은 루틴을 정해 두면 편해요.",
    "도시락을 미리 준비해 두면 점심 고민이 줄어들어요.", "출근길에 한 정거장 먼저 내려 걸어 보는 것도 좋은 방법이에요.",
    "집중이 안 될 때는 25분 타이머를 맞추고 한 가지 일만 해 보세요.", "주말 장보기 목록을 미리 적어 두면 시간이 절약돼요.",
    "아침에 햇빛을 잠깐 쬐면 하루를 시작하는 기분이 한결 상쾌해져요.", "감사한 일 세 줄을 적는 습관은 하루를 차분하게 마무리해 줘요.",
    "시간을 정해 두고 스마트폰을 내려놓으면 저녁이 한결 여유로워져요.", "간단한 간식은 눈에 띄는 곳에 두어 챙기기 쉽게 해 보세요.",
    "한 번에 많이 바꾸기보다 작은 변화를 꾸준히 이어 가는 것이 중요해요.", "마음이 급할 때는 숨을 천천히 세 번 쉬고 시작해 보세요.",
]
# 실제로 생성돼 이력에 남은 한국어 글 5편(_blogger_drafts)의 문장 40개와 제목·라벨·주제. 새 한국어 목록이 정상 글을 막지 않는지 본다
KO_REAL_DRAFT_SENTENCES = [
    "오늘은 이렇게 갑자기 피로가 몰려올 때 일상에서 복잡한 준비 없이 바로 실천할 수 있는 간단한 에너지 충전 방법들을 소개해 드릴게요.",
    "우리 몸에 수분이 조금만 부족해져도 쉽게 피로함을 느끼고 집중력 저하가 찾아올 수 있어요.",
    "차가운 물보다는 미지근한 물을 한 컵 천천히 마셔주면 체내 수분 균형을 맞추고 혈액순환을 도와 나른한 기운을 깨우는 데 도움이 될 수 있습니다.",
    "오랫동안 같은 자세로 앉아 있으면 혈액순환이 원활하지 않아 뇌로 가는 산소 공급이 줄어들기 쉬워요.",
    "이때 잠시 자리에서 일어나 손을 위로 높이 뻗어 기지개를 켜거나, 2~3분 정도 가볍게 제자리 걸음을 걸어주면 근육의 긴장이 풀리고 정신이 한결 맑아지는 느낌을 받을 수 있습니다.",
    "밀폐된 실내 공간은 이산화탄소 농도가 높아져 쉽게 졸음과 피로를 유발하곤 합니다.",
    "창문을 열어 환기를 시키고, 시원한 공기를 마시며 5초간 천천히 숨을 들이마시고 내쉬는 깊은 호흡을 해보세요.",
    "뇌에 신선한 산소가 공급되어 멍했던 머리가 가벼워지는 데 도움을 줍니다.",
    "이럴 때 복잡한 머릿속을 차분하게 정리하고 하루를 기분 좋게 마무리할 수 있는 좋은 방법이 있어요.",
    "바로 잠들기 전 딱 3분만 투자해서 '감사 메모 3줄'을 적어보는 거예요.",
    "거창한 일 대신 아주 사소한 순간 찾기",
    "감사 메모를 적으라고 하면 대단한 성공이나 특별한 행운을 떠올려야 할 것 같아 부담을 느끼기 쉽습니다.",
    "하지만 아침에 마신 따뜻한 커피 한 잔, 점심시간에 잠깐 쬐었던 기분 좋은 햇살, 버스를 놓치지 않고 바로 탄 일처럼 일상의 지극히 평범한 일이면 충분해요.",
    "사소한 긍정적 경험에 집중하는 연습은 지친 뇌의 긴장을 풀고 마음을 편안하게 만드는 데 많은 도움이 될 수 있습니다.",
    "스마트폰 메모장 대신 종이와 펜 사용하기",
    "누운 자리에서 스마트폰으로 적기보다는, 머리맡에 작은 수첩과 펜을 두고 직접 손으로 적는 것을 권해드려요.",
    "오늘은 지금 앉아 계신 그 자리에서 1분 만에 가볍게 확인해 볼 수 있는 책상 자세 체크리스트를 준비해 봤어요.",
    "노트북이나 모니터를 사용할 때 화면이 너무 아래에 있으면 자연스럽게 고개가 숙여지고 목이 앞으로 나오기 쉬워요.",
    "일반적으로 시선이 아래로 15도 이상 계속 떨어지면 목 뒤쪽 근육에 가해지는 부담이 훨씬 커질 수 있답니다.",
    "모니터 화면의 맨 윗부분이 내 눈높이와 비슷하거나 살짝 아래에 오도록 노트북 거치대나 두꺼운 책을 받쳐주시는 것이 좋아요.",
    "엉덩이를 의자 깊숙이 넣고 등받이 활용하기",
    "집중하다 보면 의자 끝에 엉덩이만 살짝 걸치고 등을 구부정하게 만 채로 일하는 경우가 많죠.",
    "의자 끝에 앉으면 상체의 무게를 오롯이 허리 아래쪽이 지탱해야 해서 쉽게 피로해질 수 있어요.",
    "엉덩이를 의자 안쪽 끝까지 쑥 밀어 넣고, 허리와 등이 등받이에 편안하게 닿도록 앉는 습관을 들여보세요.",
    "이럴 때는 억지로 잠을 청하기보다 몸과 마음에 들어간 힘을 슬쩍 빼주는 가벼운 행동들이 도움이 될 수 있어요.",
    "천천히 숨을 내쉬는 4-7-8 호흡법",
    "침대에 편안히 누워 숨을 깊게 다스려보세요.",
    "4초 동안 코로 천천히 숨을 들이마시고, 7초 동안 숨을 잠깐 멈춘 뒤, 8초에 걸쳐 입으로 가늘고 길게 숨을 내쉬는 방법입니다.",
    "일반적으로 날숨을 길게 쉬면 긴장했던 몸이 이완 모드로 전환되는 데 도움이 될 수 있어요.",
    "20분 넘게 뒤척였다면 침대 밖으로 나오기",
    "잠이 오지 않는데 계속 침대에 누워있으면 뇌가 '침대=뒤척이며 고민하는 곳'으로 기억하기 쉽습니다.",
    "20분 이상 잠들지 못했다면 과감히 일어나 거실이나 방 한구석으로 이동해보세요.",
    "만약 일상 속에서 큰 부담 없이 몸을 움직이고 싶다면, 매일 마주치는 계단부터 활용해 보는 건 어떨까요?",
    "퇴근길 지하철 출구부터 시작해 보세요",
    "처음부터 아파트 높은 층수를 다 걸어 올라가겠다고 마음먹으면 시작도 전에 지치기 쉽습니다.",
    "가장 쉬운 방법은 퇴근길 지하철역이나 버스 정류장 근처의 짧은 계단부터 이용하는 거예요.",
    "에스컬레이터 앞에 길게 늘어선 줄을 지나쳐 계단으로 발걸음을 옮기는 것만으로도 하루 활동량을 자연스럽게 늘리는 데 도움이 될 수 있습니다.",
    "'딱 2~3층만' 먼저 걷는 규칙 만들기",
    "집이나 사무실이 고층에 있다면, 엘리베이터를 아예 타지 않겠다는 다짐보다는 '목적지 2~3개 층 전'에서 내리는 방식을 추천해요.",
    "예를 들어 10층에 산다면 7층이나 8층에서 내려 남은 층만 계단으로 올라가는 식입니다.",
]
KO_REAL_DRAFT_METADATA = [
    ("점심만 지나면 골골? 피곤할 때 에너지를 올리는 간단한 습관 4가지", ["건강", "생활습관", "피로회복"], "피곤할 때 에너지 올리는 간단한 방법"),
    ("잠들기 전 3분, 마음을 편안하게 정리하는 감사 메모 3줄 쓰기 방법", ["마음건강", "수면습관", "라이프스타일"], "감사 메모 3줄 쓰기로 하루 마무리하는 방법"),
    ("재택근무 중 찌뿌둥한 몸을 깨우는 책상 자세 체크리스트 4가지", ["재택근무", "생활습관", "자세교정"], "재택근무 책상 자세 가볍게 점검하는 체크리스트"),
    ("잠이 안 올 때 침대에서 바로 해보는 4가지 간단한 방법", ["수면팁", "생활습관", "건강"], "잠이 안 올 때 바로 해볼 수 있는 간단한 방법"),
    ("바쁜 하루, 계단 오르기로 가볍게 움직임 채우는 4가지 방법", ["운동습관", "건강관리", "일상루틴"], "계단 오르기로 일상에 움직임 더하는 방법"),
]


class KoreanHardeningTest(unittest.TestCase):
    """한국어 목록 보강(D-64 ⑥ b·f): 영어가 막는 질환·약·감량 낱말의 한국어 대응."""

    def test_every_new_word_is_blocked_as_a_topic_a_title_a_label_and_in_the_body(self):
        self.assertGreaterEqual(len(KO_NEW_WORDS), 80)
        for word in KO_NEW_WORDS:
            with self.subTest(word):
                self.assertFalse(gates.topic_allowed(f"{word} 이야기", KO), word)
                self.assertIn("TITLE_TOPIC", check(KO, {"title": f"저녁 루틴으로 알아보는 {word} 이야기"}).codes(), word)
                self.assertIn("LABELS", check(KO, {"labels": ["생활습관", word]}).codes(), word)
                self.assertIn("BODY_TOPIC", check(KO, sentence=f"요즘 {word} 이야기가 많아요.").codes(), word)

    def test_the_eight_words_named_in_the_review_are_in_the_list(self):
        for word in ("불면", "혈압", "혈당", "콜레스테롤", "치매", "갱년기", "편두통", "면역력"):
            with self.subTest(word):
                self.assertFalse(gates.topic_allowed(f"{word} 관리 루틴", KO), word)

    def test_look_alike_words_are_not_blocked(self):
        for phrase in KO_LOOKALIKES:
            with self.subTest(phrase):
                self.assertTrue(gates.topic_allowed(phrase, KO), phrase)
                self.assertEqual(check(KO, sentence=f"{phrase}.").codes(), [], phrase)

    def test_ordinary_lifestyle_sentences_are_not_blocked(self):
        for sentence in KO_BENIGN_SENTENCES:
            with self.subTest(sentence):
                self.assertEqual(check(KO, sentence=sentence).codes(), [], sentence)

    def test_sentences_from_the_real_generated_drafts_are_not_blocked(self):
        self.assertGreaterEqual(len(KO_REAL_DRAFT_SENTENCES), 40)
        for sentence in KO_REAL_DRAFT_SENTENCES:
            with self.subTest(sentence[:40]):
                self.assertEqual(gates.body_risk_hit(sentence, KO), (None, None), sentence)
        for title, labels, topic in KO_REAL_DRAFT_METADATA:
            with self.subTest(title):
                self.assertTrue(gates.topic_allowed(title, KO) and gates.topic_allowed(topic, KO), title)
                self.assertTrue(all(gates.topic_allowed(label, KO) for label in labels), labels)

    def test_the_body_list_is_still_the_topic_list(self):
        self.assertEqual(KO["body_banned_patterns"], KO["banned_topic_patterns"])

    def test_the_diet_and_liver_words_the_collaboration_doc_promises_are_in_the_gate(self):
        for profile, phrases in ((KO, ("다이어트 식단", "간 건강 챙기기", "간 기능 회복")),
                                 (EN, ("a simple diet plan", "liver health habits", "liver function tips"))):
            for phrase in phrases:
                with self.subTest(phrase):
                    self.assertFalse(gates.topic_allowed(phrase, profile), phrase)
        doc = (_bootstrap.ROOT / "AI_COLLAB.md").read_text(encoding="utf-8")
        sentence = next(line for line in doc.splitlines() if line.startswith("- **언어·프로필(2026-10-26)**"))
        self.assertIn("다이어트·간 건강", sentence)
        self.assertNotIn("게이트에 아직 없고", sentence)    # 예전 문구(게이트에 없고 프롬프트로만 막는다)가 남아 있지 않다


class ProfileFieldValidationTest(unittest.TestCase):
    """새 선택 필드 body_clause_split_patterns·body_safe_veto_patterns 의 검증(레지스트리, 검증기 REG-1)."""

    def errors(self, mutate, base=EN):
        profile = copy.deepcopy(base)
        mutate(profile)
        return registry.validate_profile(profile)

    def test_both_real_profiles_define_both_fields(self):
        for profile in (EN, KO):
            self.assertTrue(profile["body_clause_split_patterns"], profile["name"])
            self.assertTrue(profile["body_safe_veto_patterns"], profile["name"])

    def test_bad_values_are_reported(self):
        for field in ("body_clause_split_patterns", "body_safe_veto_patterns"):
            self.assertTrue(any("정규식 오류" in e for e in self.errors(lambda p, f=field: p[f].append("([unclosed"))), field)
            self.assertTrue(any("배열" in e for e in self.errors(lambda p, f=field: p.update({f: "not a list"}))), field)
            for bad in ("but|", "(?:)", r"\s*", "x*"):
                with self.subTest(f"{field}: {bad!r}"):
                    self.assertTrue(any("빈 문자열" in e for e in self.errors(lambda p, f=field, b=bad: p[f].append(b))), field)

    def test_a_split_pattern_with_a_global_flag_or_a_shared_group_name_validates_and_runs(self):
        """패턴을 `(?:p1)|(?:p2)` 하나로 합치던 때는 `(?i)` 같은 전역 플래그나 같은 이름의 묶음이 레지스트리 검증(패턴 하나씩 컴파일)을
        통과하고도 실행 중에 re.error 로 터졌다(D-64 ⑦ N-4). 지금은 패턴마다 따로 쓰므로 검증을 통과한 설정은 그대로 돌아간다."""
        extra = [r"(?i)\s+furthermore\s+", r"(?P<joiner>\s+albeit\s+)", r"(?P<joiner>\s+notwithstanding\s+)"]
        profile = copy.deepcopy(EN)
        profile["body_clause_split_patterns"] = profile["body_clause_split_patterns"] + extra
        self.assertEqual(registry.validate_profile(profile), [])
        for word in ("furthermore", "albeit", "notwithstanding"):
            sentence = f"Magnesium supplements help you sleep {word} ask your doctor first."
            with self.subTest(word):
                self.assertEqual(gates.body_risk_hit(sentence, EN), (None, None), sentence)          # 새 패턴이 없으면 통과하는 문장이고
                self.assertNotEqual(gates.body_risk_hit(sentence, profile), (None, None), sentence)  # 새 패턴이 가르면 막힌다

    def test_what_the_registry_accepts_the_body_guard_can_run(self):
        """불변식: 레지스트리가 오류 0으로 받은 절 경계·면제 취소 패턴은 본문 검사가 예외 없이 돌린다."""
        weird = [r"(?i)\s+meanwhile\s+", r"(?P<a>\s+afterwards\s+)", r"(\s+)\1(?=ask)", r"(?<=,)\s+(?=ask)", r"\s+(?:whereby|wherein)\s+"]
        for field in ("body_clause_split_patterns", "body_safe_veto_patterns"):
            for pattern in weird:
                profile = copy.deepcopy(EN)
                profile[field] = profile[field] + [pattern]
                with self.subTest(f"{field}: {pattern}"):
                    self.assertEqual(registry.validate_profile(profile), [])
                    gates.body_risk_hit("Magnesium supplements help you sleep meanwhile ask your doctor first.", profile)   # 예외 없이 돈다

    def test_a_profile_may_omit_both_fields(self):
        self.assertEqual(self.errors(lambda p: (p.pop("body_clause_split_patterns"), p.pop("body_safe_veto_patterns"))), [])


class LatinExtendedLetterTest(unittest.TestCase):
    """영어 글 언어 검사의 라틴 범위 경계(U+024F). 폴란드어·체코어·루마니아어 글자(U+0100~U+024F)도 라틴 문자다(D-64 ⑥ e)."""

    def test_latin_extended_a_and_b_letters_count_as_latin(self):
        post, _ = stub_post(EN)
        polish = "Zażółć gęślą jaźń. " * 70        # ż ł ć ę ś ą ź ń 는 U+0100 이상(라틴 확장-A)
        romanian = "Șoarece țânțar șarpe. " * 200    # Ș ț 는 라틴 확장-B(U+0218~U+021B)
        for extra in (polish, romanian, polish + romanian):
            with self.subTest(extra[:12]):
                self.assertNotIn("LANG", check(EN, {"content": post["content"] + "<p>" + extra + "</p>"}).codes())
        self.assertNotIn("LANG", check(EN, {"title": "A Gentle Łódź Walk for a Calmer Afternoon"}).codes())
        self.assertIn("LANG", check(EN, {"content": post["content"] + "<p>" + "ɐɑɒɓɔɕ ʁʂʃʄ " * 120 + "</p>"}).codes())  # IPA 확장(U+0250~)은 라틴이 아니다


# ----------------------------------------------------------------------------
# 선택지 하나까지 지키는 표본(D-64 ⑥ e). 패턴 안의 | 선택지를 하나씩 지운 변이(이 보강에서 바꾸거나 더한 패턴 전부)를 돌려 보니
# 패턴 단위 시험(RuleCoverageTest 등)은 낱말 하나가 빠진 패턴을 모르고 지나갔다. 그래서 선택지마다 '그 선택지로만 막히는' 표본을 둔다.
# 패턴에 선택지를 더하면 표본도 더한다. 다른 패턴이 같은 말을 이미 막는 중복 선택지(ARCHITECTURE §7-1에 적음)는 표본이 없어도 된다.
# ----------------------------------------------------------------------------
EN_ALTERNATIVE_SAMPLES = [
    "5 mcg", "acetaminophen", "anemia", "anemic", "antibiotic", "antidepressant", "antihistamine", "anxiety attack", "arthritis", "aspirin",
    "benzodiazepine", "cardiovascular", "chronic condition", "chronic fatigue", "cirrhosis", "copd", "coronavirus", "covid", "diet chart",
    "diet drink", "diet food", "diet menu", "diet programme", "diet regimen", "diet shake", "diet tea", "epilepsy", "expecting parents",
    "expecting women", "fad diet", "fibromyalgia", "healthier liver", "heart attacks", "heart condition", "heart conditions", "hepatitis",
    "hiv", "kidney failure", "lactating", "liver care", "liver damage", "liver enzyme", "liver support", "mental health condition",
    "mental health issue", "mental health problem", "migraine", "nsaid", "obese", "obesity", "opioid", "osteoporosis", "otc",
    "over the counter", "painkiller", "panic attack", "paracetamol", "sedative", "seizure", "sleep capsule", "starvation", "starve",
    "starved", "starves", "starving", "stroke", "support the liver", "supporting liver", "supporting the liver", "supports liver",
    "supports the liver", "thyroid", "tummy fat", "vitamin capsule", "vitamin tablet",
]
# 같은 낱말이 두 묶음에 들어 있는 패턴(shed…/drop…, expecting…/nursing…)은 묶음마다 표본이 따로 있어야 한다
EN_ALTERNATIVE_SAMPLES += (
    [f"{verb} {thing}" for verb in ("shed", "sheds", "shedding") for thing in ("5 pounds", "5 lbs", "5 kilos", "5 kgs", "weight", "fat", "inches")]
    + [f"{verb} {amount} {unit}" for verb in ("drop", "drops", "dropped", "dropping") for amount in ("a few", "some", "several", "5")
       for unit in ("pounds", "lbs", "kilos", "kgs")]
    + [f"{lead} {noun}" for lead in ("expecting", "nursing") for noun in ("mothers", "moms", "mums")]
)
EN_REFERRAL_VERBS = ("talk", "ask", "check", "consult", "speak", "see", "visit", "contact", "call", "seek")
EN_ADVICE_VERBS = ("take", "try", "add", "use", "start", "drink", "eat", "choose", "pick", "consider", "include", "get", "buy", "combine",
                   "mix", "limit", "avoid", "skip", "stop", "increase", "reduce")
EN_SUBJECT_WORDS = ("you", "your", "they", "it", "this", "that", "these", "those", "we")
# 절 경계 하나하나('Tea helps' 와 'the rest' 사이에 끼웠을 때 정확히 두 절로 갈라져야 하는 조각). ', and just talk' 의 'just' 는
# 머리말 없는 ', and talk' 를 아래 ' and talk' 규칙도 가르기 때문에 쉼표 규칙만 따로 시험하려고 끼운 것이다
EN_BOUNDARY_FRAGMENTS = (
    [" but", " although", " though", " whereas", ", yet", ", so", ", while", ", then", ", however", ", and then"]
    + [f", and {lead} take" for lead in ("please", "also", "always", "just")]
    + [f", and just {verb}" for verb in EN_REFERRAL_VERBS]
    + [f", and {word}" for word in EN_ADVICE_VERBS + EN_SUBJECT_WORDS]
    + [f" and {lead} ask" for lead in ("please", "also", "always")]
    + [f" and {verb}" for verb in EN_REFERRAL_VERBS]
    + [f"({verb}" for verb in EN_REFERRAL_VERBS]
    # D-64 ⑧ N2-1: 연결어 바로 뒤의 쉼표(연결어 앞의 쉼표는 있어도 없어도 된다)
    + [" but,", " although,", " though,", " whereas,", ", yet,", ", so,", ", while,", ", then,", ", however,", ", and then,"]
)
# D-64 ⑦ N-1: 쉼표 없는 접속어 + 상담 구절. 새 영어 패턴 둘(강한 동사·약한 동사)의 선택지마다 그 선택지로만 갈라지는 조각
# D-64 ⑧ N2-4: 목록에 없던 연결어(두 패턴 모두에 들어갔다). 쉼표가 앞에 있든 없든, 바로 뒤에 쉼표가 붙든 말든 가른다
EN_NEW_CONNECTORS = ("however", "accordingly", "consequently", "for this reason", "for that reason", "nevertheless", "nonetheless", "that said")
EN_CONNECTORS = ("so", "yet", "while", "then", "or", "because", "since", "as", "unless", "otherwise", "therefore", "thus", "hence", "plus",
                 "which is why", "that is why", "which means", "that means", "meaning", "this means", "except that") + EN_NEW_CONNECTORS
EN_CAUSAL_CONNECTORS = ("so", "yet", "then", "because", "since", "unless", "otherwise", "therefore", "thus", "hence", "plus",
                        "which is why", "that is why", "which means", "that means", "meaning", "this means", "except that") + EN_NEW_CONNECTORS
EN_MODALS = ("should", "can", "could", "may", "might", "must", "will", "would", "need to", "ought to")
EN_ITS_FORMS = ("it is", "it's", "it would be", "it will be")
EN_ITS_ADVERBS = ("", "always ", "really ", "highly ")
EN_ITS_ADJECTIVES = ("wise", "best", "better", "smart", "safest", "important", "recommended", "advisable", "a good idea", "a smart move")
EN_THIRD_SUBJECTS = ("people", "readers", "everyone", "everybody", "anyone", "they", "users", "patients", "parents", "beginners", "most people", "we")
EN_THIRD_MODALS = ("should", "can", "may", "might", "must", "need to", "ought to")
EN_LEAD_INS = (
    [f"{subject} should" for subject in ("you", "it", "one")] + [f"you {modal}" for modal in EN_MODALS]
    + [f"you {adverb} {modal}" for adverb in ("really", "definitely", "certainly", "probably") for modal in ("should", "ought to", "need to", "must")]
    + [f"you {auxiliary} {verb} to" for auxiliary in ("might", "may", "will") for verb in ("want", "wish")] + ["you'll want to", "you'll wish to"]
    + ["you'd better", "you had better", "you", "make sure to", "be sure to", "make certain to", "be certain to", "remember to", "always remember to", "consider"]
    + [f"be {adjective} to" for adjective in ("wise", "smart", "best", "sensible")]
    + [f"{form} {EN_ITS_ADVERBS[index % len(EN_ITS_ADVERBS)]}{adjective} to"
       for index, (form, adjective) in enumerate((form, adjective) for form in EN_ITS_FORMS for adjective in EN_ITS_ADJECTIVES)]
    + ["it is recommended that you", "it makes sense to"]
    + ["I suggest", "I recommend", "I'd suggest that", "I'd recommend that", "I would suggest", "I would recommend that", "we suggest", "we recommend", "we'd suggest that",
       "we'd recommend", "we would suggest that", "we would recommend that", "I suggest you", "we recommend you", "I would suggest you", "we'd recommend that you"]     # 뒤의 `you`는 도입구 `you`가 받는다
    + ["do", "please do", "do not forget to", "don't forget to", "do not hesitate to", "don't hesitate to", "feel free to", "take a moment to", "take the time to", "kindly"]
    + [f"{subject} {EN_THIRD_MODALS[index % len(EN_THIRD_MODALS)]}" for index, subject in enumerate(EN_THIRD_SUBJECTS)]
    + ["you should make sure to", "do remember to", "you might consider", "it may be wise to"]          # 도입구 두 겹
)
EN_PROFESSIONALS = ("doctor", "physician", "pharmacist", "nurse", "dietitian", "nutritionist", "therapist", "counselor", "counsellor", "psychologist",
                    "psychiatrist", "clinician", "specialist", "professional", "healthcare provider", "healthcare professional", "healthcare practitioner",
                    "healthcare team", "health care provider", "health provider", "health professional", "health practitioner", "medical professional",
                    "medical provider", "medical practitioner", "medical advice", "medical attention", "medical help", "medical care")
EN_STRONG_PHRASES = ("talk to", "talk with", "speak to", "speak with", "check with", "consult", "ask", "refer to",
                     "talking to", "talking with", "speaking to", "speaking with", "checking with", "consulting", "asking", "referring to")
EN_WEAK_VERBS = ("see", "call", "visit", "contact", "seek", "seeing", "calling", "visiting", "contacting", "seeking")
EN_REFERRAL_ADVERBS = ("please", "also", "always", "just", "first", "definitely", "probably", "really", "certainly", "simply")
EN_PROFESSIONAL_PLURALS = tuple(f"{noun}s" for noun in EN_PROFESSIONALS if not noun.endswith(("advice", "attention", "help", "care")))      # 복수형도 가른다(doctors·healthcare teams)
EN_CONNECTOR_FRAGMENTS = list(dict.fromkeys(
    [f" {c} ask your doctor" for c in EN_CONNECTORS]
    + [f" {c}, ask your doctor" for c in EN_CONNECTORS]         # D-64 ⑧ N2-1: 연결어 바로 뒤의 쉼표
    + [" and you should ask your doctor", " and, you should ask your doctor"]    # 'and' 는 도입구 없이는 ' and ask' 규칙이 같이 가르므로 도입구를 붙여 시험한다
    + [f" so {lead} ask your doctor" for lead in EN_LEAD_INS]
    + [f" so {adverb} ask your doctor" for adverb in EN_REFERRAL_ADVERBS]
    + [f" so {adverb}, ask your doctor" for adverb in EN_REFERRAL_ADVERBS]
    + [f" so {phrase} your doctor" for phrase in EN_STRONG_PHRASES]
    + [f" so ask your {noun}" for noun in EN_PROFESSIONALS + EN_PROFESSIONAL_PLURALS]
    + [f" {c} see your doctor" for c in EN_CAUSAL_CONNECTORS]
    + [f" {c}, see your doctor" for c in EN_CAUSAL_CONNECTORS]
    + [f" so {lead} see your doctor" for lead in EN_LEAD_INS]
    + [f" so {adverb} see your doctor" for adverb in EN_REFERRAL_ADVERBS]
    + [f" so {verb} your doctor" for verb in EN_WEAK_VERBS]
    + [f" so see your {noun}" for noun in EN_PROFESSIONALS + EN_PROFESSIONAL_PLURALS]
    + [f" so {adverb}, see your doctor" for adverb in EN_REFERRAL_ADVERBS]
))
KO_REFERRAL_NOUNS = ("의사", "약사", "전문가", "전문의", "의료진", "병원", "상담", "문의", "주치의", "한의원", "영양사")    # 상담사는 '상담'으로 시작해 따로 둘 필요가 없다
KO_ADVERBS = ("꼭", "반드시", "먼저", "항상", "우선", "일단", "미리", "한번", "한 번")
KO_MODIFIERS = ("가까운", "담당", "전문", "주변", "동네", "의료", "건강", "치과", "한")                # 상담 낱말 앞에 붙는 말(가까운 병원·담당 의사·의료 전문가·건강 상담·치과 의사·한의사)
KO_CONNECTIVES = ("그러므로", "그러니", "그렇기 때문에", "이 때문에", "그런 이유로", "이런 이유로")     # '그러니까'는 첫 패턴 목록의 ~니까 가 가른다
KO_BOUNDARY_FRAGMENTS = list(dict.fromkeys(
    ["지만", "하되", "는데", "은데", "인데", "으나", "면서", "으며", "하며", "니까", "으니"]
    + [", 그러나", ", 다만", ", 단", ", 그런데", ", 그리고"]
    + [f"고 {lead} 약사" for lead in KO_ADVERBS]
    + [f"고 {noun}" for noun in KO_REFERRAL_NOUNS]
    + [f"({noun}" for noun in KO_REFERRAL_NOUNS]
    # D-64 ⑦ N-1
    + ["고, 의사", "고,의사"]
    + [f"({lead} 의사" for lead in KO_ADVERBS]
    + [f", {word} 의사" for word in KO_CONNECTIVES] + [f" {word} 의사" for word in KO_CONNECTIVES]
    + [f", 그러니 {lead} 의사" for lead in KO_ADVERBS] + [f", 그러니 {noun}" for noun in KO_REFERRAL_NOUNS]
    + ["돼서 의사", ", 그래서 의사", ", 따라서 의사", "고 나서 의사"] + [f"돼서 {lead} 의사" for lead in KO_ADVERBS] + [f"돼서 {noun}" for noun in KO_REFERRAL_NOUNS]
    # D-64 ⑧ N2-1: 연결어 바로 뒤의 쉼표
    + [", 그러나, 의사", ", 하지만, 의사", ", 그리고, 의사", ", 그러므로, 의사", ", 그러니, 의사", "돼서, 의사", ", 따라서, 의사", ", 그래서, 의사", "돼서， 의사"]
    # D-64 ⑧ N2-3: 상담 낱말 앞의 말(가까운 병원·담당 의사·한의사)과 부사 여러 개
    + [f"고 {modifier} 의사" for modifier in KO_MODIFIERS] + [f"({modifier} 의사" for modifier in KO_MODIFIERS]
    + [f", 그러니 {modifier} 의사" for modifier in KO_MODIFIERS] + [f"돼서 {modifier} 의사" for modifier in KO_MODIFIERS]
    + ["고 꼭 반드시 먼저 의사", "고 반드시 먼저 전문의", "돼서 꼭 먼저 의사", ", 그러므로 꼭 반드시 먼저 의사", "(꼭 먼저 의사", "고 한 번 의사", "고 한번 의사"]
    + ["고 가까운 병원", "고 의료 전문가", "고 건강 전문가", "고 담당 의사", "고 치과 의사", "고 전문 의료진"]
    # 세 번째 부사까지(부사 반복 {0,3})와 전각 쉼표·괄호 — 본문 검사는 NFKC 로 먼저 반각으로 바꾸지만 절 쪼개기 함수는 글을 그대로 받는다
    + ["(꼭 반드시 먼저 의사", "돼서 꼭 반드시 먼저 의사", ", 그러니 꼭 반드시 먼저 의사"]
    + ["， 그러나， 의사", "，그러므로， 의사", "고， 의사", "（의사", "（꼭 먼저 의사"]
))
# 용량 면제 취소(D-64 ⑦ N-3): 상담 구절이 있어도 이 표기가 든 절은 면제하지 않는다. 문장에 banned 낱말(melatonin·멜라토닌)을 넣어 면제 취소가 막는 것만 보게 한다
EN_NUMBER_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "fifteen", "twenty", "thirty",
                   "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "half", "couple")
EN_DOSES = list(dict.fromkeys(
    [f"5 {unit}" for unit in ("mg", "mgs", "mcg", "μg", "ug", "IU", "g", "milligrams", "micrograms", "grams", "units", "capsules", "tablets", "softgels", "gummies", "gummy")]
    + ["400mg", "400mgs", "400-mg", "400 -mg", "400- mg", "0.4 g", "10,000 units", "1000iu", "1.5 grams"]       # 띄어 쓴 하이픈 사이 간격은 plain_text 가 공백 하나로 접으므로 하이픈으로 시험한다
    + [f"{word} tablets" for word in EN_NUMBER_WORDS]
    + [f"two {unit}" for unit in ("milligrams", "micrograms", "grams", "units", "capsules", "tablets", "softgels", "gummies")]
    + ["half a tablet", "a couple of tablets", "one hundred and fifty milligrams", "twenty-five milligrams", "a couple of gummies", "half a softgel"]
    + [f"1 {unit}" for unit in ("milligram", "microgram", "gram", "unit", "capsule", "tablet", "softgel")]                      # 단수형
    + [f"one {unit}" for unit in ("milligram", "microgram", "gram", "unit", "capsule", "tablet", "softgel", "gummy")] + ["a two-tablet dose"]
))
EN_DOSE_TEMPLATE = "Ask your doctor whether {} of melatonin is right for you."
KO_NATIVE_NUMBERS = ("한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열")
KO_DOSES = list(dict.fromkeys(
    [f"5{unit}" for unit in ("mg", "mgs", "mcg", "μg", "IU", "g")]
    + ["5 mg", "400mgs", "0.4 g", "10,000 mg", "500밀리그램", "50마이크로그램", "100그램", "100 그램", "1킬로그램", "1 킬로그램", "2 g"]
    + ["2정", "2 정", "3캡슐", "2알", "2 알"]
    + [f"{number} 알" for number in KO_NATIVE_NUMBERS] + ["한 정", "두 캡슐", "반 알", "반 정", "반 캡슐"]
))
KO_DOSE_TEMPLATE = "의사와 상담해서 멜라토닌 {}을 정하세요."
# D-64 ⑧ N2-5: 일상어는 용량이 아니다. 문장마다 금지 낱말(melatonin·멜라토닌)과 상담 구절이 같은 절에 있어야 시험이 의미가 있다 — 면제 취소가 일상어를 용량으로 잘못 읽으면 막히고,
# 같은 틀에 진짜 용량을 넣으면(아래 짝) 면제 취소가 있어야만 막힌다. 면제 취소가 읽는 '5G'(대소문자)·'6 glasses'(뒤 경계)·'B12 tablets'(앞 경계)·'2정거장'·'5gb'는 각각 그 규칙만 시험한다
EN_EVERYDAY_TEMPLATE = "Ask your doctor about melatonin and {}."
EN_EVERYDAY_NOT_DOSES = ("a handful of nuts", "a 10-inch tablet stand", "a 5G phone", "the 5G network", "6 glasses of water", "your B12 tablets", "a couple of ideas",
                         "ten minutes", "twenty steps", "half an hour", "two cups of tea", "a hundred ideas", "forty winks",
                         "a phone tablet stand", "two gramophone records", "2 tabletop games")      # 숫자말·단위 앞뒤 경계(`one`⊂`phone`, `gram`⊂`gramophone`, `tablet`⊂`tabletop`)
EN_EVERYDAY_DOSE_TWINS = ("400 mg", "5 g", "2 tablets")
KO_EVERYDAY_TEMPLATE = "의사와 상담해서 멜라토닌과 {} 중에서 정하세요."     # 일상어 뒤가 공백이라야 `2정거장`의 '거장' 두 글자가 용량 뒤 두 글자 보호(`(?![가-힣]{2,})`)를 시험한다
KO_EVERYDAY_NOT_DOSES = ("2정거장", "한 정거장", "5G 요금제", "5gb 데이터", "프로그램", "세 알아보기")
KO_EVERYDAY_DOSE_TWINS = ("400 mg", "5g", "2정")


class AlternativeCoverageTest(unittest.TestCase):
    def test_every_english_word_sample_is_blocked_by_both_word_lists(self):
        self.assertEqual(len(EN_ALTERNATIVE_SAMPLES), len(set(EN_ALTERNATIVE_SAMPLES)))
        for sample in EN_ALTERNATIVE_SAMPLES:
            with self.subTest(sample):
                self.assertFalse(gates.topic_allowed(sample, EN), sample)
                self.assertIsNotNone(gates.first_match(EN["body_banned_patterns"], sample)[0], sample)

    def test_every_connector_fragment_splits_a_sentence_into_exactly_two_clauses(self):
        # 뒤 문장은 상담 낱말로 시작하지 않는다(', 그리고 의사…' 는 '그리고' 선택지 없이도 '고 + 의사' 규칙이 갈라 버린다)
        for profile, frame, fragments in ((EN, "Tea helps{} the rest", EN_BOUNDARY_FRAGMENTS + EN_CONNECTOR_FRAGMENTS),
                                          (KO, "보충제{} 오늘은 쉬세요", KO_BOUNDARY_FRAGMENTS)):
            self.assertEqual(len(fragments), len(set(fragments)))
            splitter = gates._clause_splitter(profile)
            for fragment in fragments:
                text = frame.format(fragment)
                with self.subTest(text):
                    self.assertEqual(len(gates._split_clauses(text, splitter)), 2, text)

    def test_every_dose_notation_keeps_a_referral_clause_from_exempting_the_dose(self):
        for profile, template, doses in ((EN, EN_DOSE_TEMPLATE, EN_DOSES), (KO, KO_DOSE_TEMPLATE, KO_DOSES)):
            for dose in doses:
                sentence = template.format(dose)
                with self.subTest(sentence):
                    self.assertIn("BODY_TOPIC", check(profile, sentence=sentence).codes(), sentence)

    def test_everyday_counting_words_are_not_doses(self):
        """용량 면제 취소가 일상어를 용량으로 읽지 않는다. 모든 문장에 금지 낱말과 상담 구절이 같이 들어 있어, 면제 취소가 잘못 읽으면 막히고 면제 취소를 비우면 통과한다.
        같은 틀에 진짜 용량을 넣은 짝은 면제 취소가 있어야만 막힌다(D-64 ⑧ N2-5)."""
        for profile, template, everyday, twins in ((EN, EN_EVERYDAY_TEMPLATE, EN_EVERYDAY_NOT_DOSES, EN_EVERYDAY_DOSE_TWINS),
                                                   (KO, KO_EVERYDAY_TEMPLATE, KO_EVERYDAY_NOT_DOSES, KO_EVERYDAY_DOSE_TWINS)):
            no_veto = {**profile, "body_safe_veto_patterns": []}
            for word in everyday:
                sentence = template.format(word)
                with self.subTest(sentence):
                    self.assertIsNotNone(gates.first_match(profile["body_banned_patterns"], sentence)[0], sentence)    # 금지 낱말이 있고
                    self.assertEqual(gates.body_risk_hit(sentence, no_veto), (None, None), sentence)                   # 상담 구절로 면제되는 절이라
                    self.assertEqual(check(profile, sentence=sentence).codes(), [], sentence)                          # 면제 취소가 용량으로 읽지 않아야 통과한다
            for dose in twins:
                sentence = template.format(dose)
                with self.subTest(sentence):
                    self.assertEqual(gates.body_risk_hit(sentence, no_veto), (None, None), sentence)
                    self.assertIn("BODY_TOPIC", check(profile, sentence=sentence).codes(), sentence)


# ----------------------------------------------------------------------------
# D-64 ⑧ (3차 보강): 상담 구절의 모양·한국어 상담 낱말 정렬·후치사 `~서`
# ----------------------------------------------------------------------------
class ReferralPhraseShapeTest(unittest.TestCase):
    """영어 상담 구절의 모양(창 길이·낱말 모양·상담 부사 두 개·동명사)을 하나씩 고정한다. 2차 보강의 변이 시험에서 지우거나 약하게 만들어도 시험이 모르고
    지나가던 곳이다(D-64 ⑧ N2-6). 모두 '위험한 절 + 쉼표 없는 연결어 + 상담 구절' 모양이고, 연결어 `so` 하나로 시험한다."""
    RISKY = "Magnesium supplements may help you sleep"
    BLOCKED = (
        "so ask your very kind local doctor",                                                   # 동사와 전문가 낱말 사이 4단어(강한 동사)
        "so call your very kind local doctor",                                                  # 4단어(약한 동사)
        "so ask your board-certified doctor", "so call your board-certified doctor",             # 창 안의 하이픈 낱말
        "so ask your family's doctor", "so call your family's doctor",                           # 창 안의 아포스트로피 낱말
        "so please also ask your doctor", "so just always call your doctor",                     # 상담 부사 두 개 연속
        "so talking to your doctor first is wise", "so asking your doctor first is wise",        # 동명사
        "so consulting your doctor first is wise",
    )
    OPEN = (
        "so ask your very kind local family doctor",                                            # 창은 4단어다 — 5단어부터는 열려 있다(문서 한계)
        "so anyone taking medication should ask their doctor",                                   # 수식어가 붙은 3인칭 주어
        "so those with health concerns should ask their doctor",
        "or see your doctor", "while see your doctor", "as seeing your doctor is wise",          # 약한 동사는 or·while·as 와 쓰이면 일상 서술이라 가르지 않는다
    )

    def test_each_shape_is_blocked(self):
        for tail in self.BLOCKED:
            sentence = f"{self.RISKY} {tail}."
            with self.subTest(sentence):
                self.assertIn("BODY_TOPIC", check(EN, sentence=sentence).codes(), sentence)

    def test_the_documented_limits_are_still_open(self):
        """닫으면 정상 안내 오탐이 늘거나(`or see a specialist`) 창을 넓혀야 한다. 일부러 닫을 때 이 시험과 ARCHITECTURE §7-1 한계 목록을 같이 고친다."""
        for tail in self.OPEN:
            sentence = f"{self.RISKY} {tail}."
            with self.subTest(sentence):
                self.assertEqual(gates.body_risk_hit(sentence, EN), (None, None), sentence)


KO_REFERRAL_PHRASES = (
    "의사와 상담하세요", "약사에게 문의하세요", "전문가와 상담하세요", "전문의와 상담하세요", "의료진과 상담하세요", "병원을 방문하세요",
    "주치의와 상담하세요", "한의원에서 상담하세요", "영양사와 상담하세요", "상담사와 상담하세요", "의료 전문가와 상담하세요", "건강 전문가에게 문의하세요",
    "가까운 병원에서 의사와 상담하세요", "담당 의사와 상담하세요", "치과 의사와 상담하세요", "전문 의료진과 상담하세요", "한의사와 상담하세요",
    "주변 병원에서 상담하세요", "동네 약사에게 문의하세요", "반드시 먼저 전문의와 상담하세요", "꼭 항상 의사와 상담하세요", "우선 의사와 상담하세요",
    "일단 병원을 방문하세요", "미리 약사와 상담하세요", "한번 전문가와 상담하세요", "한 번 의사와 상담하세요",
)
KO_ALIGNMENT_TEMPLATES = ("혈압이 높을 수 있어요, 그래서 {}", "혈압이 높을 수 있고 {}", "혈압이 높을 수 있어요 ({})", "혈압이 높을 수 있어요, 그러므로 {}",
                          "혈압이 높을 수 있어요, 그렇기 때문에 {}")
# 후치사·부사처럼 쓰여 접속 어미가 아닌 `~서`(앞에 쉼표·명사가 있다). 끝의 세 개(`가족에게서`·`친구한테서`·`집에서`)는 출처·장소 조사 `에게서`·`한테서`·`에서`
KO_POSTPOSITION_PHRASES = ("영양제에 대해서", "영양제에 관해서", "안전을 위해서", "혈압 측정 결과를 통해서", "혈당 변화로 인해서", "이전에 비해서", "약사의 설명에 의해서",
                           "복용 중인 약과 관련해서", "환자로서", "혈압에 따라서", "시작하기에 앞서", "수술에 앞서서", "여기서", "거기서", "저기서", "어디서",
                           "가족에게서", "친구한테서", "집에서")
KO_CONNECTIVE_PHRASES = ("영양제를 챙겨서", "영양제를 먹어서", "임신 중이라서", "수면에 도움이 돼서", "영양제를 준비해서", "영양제를 소통해서", "영양제에 동의해서",
                         "영양제 이야기를 듣고 나서", "그래서", "따라서")


class KoreanReferralAlignmentTest(unittest.TestCase):
    """한국어 경계 패턴이 아는 상담 낱말을 안전 패턴(body_safe_patterns)이 인식하는 것과 맞춘다(D-64 ⑧ N2-3). 어긋나면 안전 패턴만 알아 면제가 남는다
    (`그래서 주치의와 상담하세요`가 통과하던 것). 후치사처럼 쓰인 `~서`(…에 대해서·위해서·통해서·로서·에 따라서·앞서)는 접속 어미가 아니라서 가르지 않는다."""

    def test_every_referral_phrase_the_safe_pattern_recognises_is_a_boundary_too(self):
        safe = gates._compiled(KO["body_safe_patterns"])
        for phrase in KO_REFERRAL_PHRASES:
            self.assertTrue(any(rx.search(gates._normalized(phrase)) for rx in safe), phrase)   # 안전 패턴이 인식하는 상담 구절이다
            for template in KO_ALIGNMENT_TEMPLATES:
                sentence = template.format(phrase) + "."
                with self.subTest(sentence):
                    self.assertIn("BODY_TOPIC", check(KO, sentence=sentence).codes(), sentence)

    def test_postpositions_that_look_like_connective_endings_do_not_split(self):
        for phrase in KO_POSTPOSITION_PHRASES:
            sentence = f"임신 중에는 {phrase} 의사와 상담하세요."
            with self.subTest(sentence):
                self.assertEqual(check(KO, sentence=sentence).codes(), [], sentence)
                self.assertEqual(len(gates._split_clauses(sentence[:-1], gates._clause_splitter(KO))), 1, sentence)

    def test_real_connective_endings_still_split_even_when_a_postposition_ends_the_same_way(self):
        """`준비해서`는 `비해서`로, `소통해서`는 `통해서`로, `동의해서`는 `의해서`로 끝나지만 접속 어미다(후치사는 앞에 공백이 있는 낱말 `대해서`·`비해서`…)."""
        for phrase in KO_CONNECTIVE_PHRASES:
            sentence = f"임신 중에는 {phrase} 의사와 상담하세요."
            with self.subTest(sentence):
                self.assertIn("BODY_TOPIC", check(KO, sentence=sentence).codes(), sentence)


if __name__ == "__main__":
    unittest.main()
