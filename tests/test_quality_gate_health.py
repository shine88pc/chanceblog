"""독립 재검증(2026-11-09, 2차)이 찾은 건강 C(증상 + 즉각 효과 = QG4-CLAIM) 미탐 구조 다섯과 그 둘레의 회귀 시험.
 D1-1 절 경계(쉼표·느낌표·물음표) · D1-2 간격 글자 수 → 구조 규칙(행동 서술어·다른 대상이 끼면 행동 순서, 명사구·부사만 끼면 결과 수식) · D1-3 증상·질환 어휘(낱말 + 접미 규칙)
 · D1-4 긴 절(겹치는 창) · D1-5 효과 동사·활용·영문 · 상담 문구가 든 효능 주장 · D4 한 낱말 외국 인명 + 직함 · D5 이미지 대체글·HTML 속성·링크 글자 · D6 포트·계정이 다른 주소.
운영자 승인 표본(운영자 C 9·변형 15·영문 5·상담 문구·행동 순서 대조)과 검증자의 새 문장 105개·증상·질환 낱말 91개를 큰 목록으로 못박는다. 문장은 모두 지어낸 것이다."""
import time
import unicodedata
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import quality_gate_helpers as h
from pipeline import quality_gate as qg

NEUTRAL_TITLE = "미국 연방기관이 발표한 보고서의 핵심 내용"
EN_TITLE = "Agency report highlights"
PROFILES = None


def plain(n):
    unit = "이 문단은 설명을 이어 가기 위한 평범한 문장으로 구성되어 있으며 독자가 맥락을 이해하도록 돕습니다. "
    out = ""
    while len(out.replace(" ", "")) < n:
        out += unit
    return out.strip()


def plain_en(n):
    unit = "This paragraph keeps the explanation moving with plain sentences that help the reader follow the context of the story. "
    out = ""
    while len(out.replace(" ", "")) < n:
        out += unit
    return out.strip()


def body_with(sentence):
    return f"{plain(500)}\n\n{sentence}\n\n{plain(450)}"


def codes_body(sentence, lang="ko"):
    if lang == "ko":
        return [hold.code for hold in qg.rule_health("ko", NEUTRAL_TITLE, qg.prose_of(body_with(sentence)), PROFILES)]
    return [hold.code for hold in qg.rule_health("en", EN_TITLE, qg.prose_of(f"{plain_en(900)}\n\n{sentence}\n\n{plain_en(700)}"), PROFILES)]


def codes_title(sentence, lang="ko"):
    if lang == "ko":
        return [hold.code for hold in qg.rule_health("ko", sentence, qg.prose_of(body_with("평범한 문장입니다.")), PROFILES)]
    return [hold.code for hold in qg.rule_health("en", sentence, qg.prose_of(plain_en(900)), PROFILES)]


def setUpModule():
    global PROFILES
    PROFILES = h.health_profiles()


# --- 검증자·운영자 표본 ------------------------------------------------------------------------------------------------------------------
OPERATOR_C = ("이 영양제는 피로를 즉시 없애줍니다", "영양제로 불면이 바로 치료됩니다", "수면제 바로 끊어도 될까", "피로를 즉시 줄이는 방법", "자세를 바로 교정하는 책상 설정", "통증을 완전히 없애는 의자 선택법",
              "당뇨 100% 보장", "당뇨를 무조건 개선하는 식품", "암 완치 보장")
C_ENUM = ("목 통증을 즉시 완화하는 베개 고르는 법", "만성 피로를 확실히 해소하는 아침 습관", "어깨 결림을 바로 없애는 마사지 도구", "허리 통증을 완전히 교정하는 의자", "거북목을 즉시 교정하는 5분 운동",
          "두통을 무조건 줄일 수 있는 물 마시기 방법", "탈모를 완전히 예방하는 샴푸 사용법", "피부 트러블을 바로 해결하는 세안 루틴", "눈 피로를 확실히 회복시키는 안구 운동", "스트레스를 즉시 해소하는 호흡법",
          "근육통을 즉시 완화해 주는 폼롤러", "무릎 통증을 100% 없애 주는 보호대", "체중을 바로 감량하는 걷기 방법", "감기를 하루 만에 치료하는 차", "어지럼증을 즉각 없앨 수 있습니다",
          "소화불량을 확실하게 개선하는 식사법", "변비를 완전히 해결해 주는 유산균", "속쓰림을 즉시 줄여 줍니다", "불안감을 바로 해소하는 앱", "요통이 즉시 사라지는 쿠션", "피로 즉시 회복",
          "3일 만에 요통이 사라집니다", "누구나 요통을 완벽하게 치료할 수 있다", "아토피를 완벽히 잡는 보습 크림", "여드름을 100% 없애는 세안제", "우울감을 완전히 없애 주는 음악",
          "무기력을 확실히 해소하는 식단", "이 의자는 자세를 바로 교정합니다", "피로를 즉각 줄여 주는 비타민 샤워기", "눈 피로가 즉시 풀리는 안경")
C_OPEN = ("어깨 결림이 즉시 풀립니다", "통증이 바로 가라앉습니다", "두통이 즉각 멈춥니다", "기침이 바로 멎는 꿀차", "피로가 한 번에 날아가는 샤워 습관", "통증을 완전히 잊게 해 주는 의자",
          "두통 제로 비법", "통증 걱정 끝, 이 의자 하나로", "하루 5분으로 피로 완전 정복", "일주일이면 거북목이 교정됩니다", "자세가 바로 펴집니다", "허리가 즉시 편안해지는 의자",
          "알레르기를 즉시 차단하는 마스크", "코막힘이 바로 뚫리는 방법", "굽은 어깨를 즉시 펴 주는 밴드", "무릎 통증을 단번에 날려 버리는 운동")
C_CONDITION = ("비염이 바로 사라지는 차", "디스크를 즉시 없애는 자세", "무좀을 완전히 없애는 양말", "치질이 하루 만에 낫는 좌욕법", "통풍을 확실히 해소하는 식단", "이명을 즉시 줄이는 소리",
               "대상포진이 바로 낫는 방법", "오십견을 완전히 교정하는 스트레칭", "위염을 즉각 해결하는 음식", "족저근막염이 바로 사라지는 깔창", "손목 저림을 즉시 없애는 마우스", "무릎 연골을 완전히 회복시키는 방법")
C_DISEASE = ("고혈압 100% 해결", "치매 예방 보장", "우울증은 반드시 낫는다", "당뇨 완치 가능", "수면제를 바로 끊어도 괜찮다", "항생제는 즉시 중단해도 된다", "혈압약은 안 먹어도 됩니다", "진통제 없이 무조건 낫는 방법")
C_EN = ("Instantly relieve neck pain with this pillow", "This cushion permanently fixes back pain", "Say goodbye to headaches forever", "Back pain gone in one week", "Fatigue disappears immediately",
        "Cure anxiety in 5 minutes", "This tea eliminates bloating overnight", "A guaranteed way to stop snoring", "Erase eye strain at once", "Neck stiffness vanishes in minutes")
# 마케팅 말투 몇 개(되찾다·되돌리다·젊어지다·재생하다·구어 부사·5kg 감량)와 영어 lose·burn·shed·drop
C_MARKETING = ("시력을 완전히 되찾는 눈 운동", "관절을 즉시 되살리는 영양제", "노안을 완전히 되돌리는 방법", "스트레스가 확 풀리는 차", "뱃살이 쏙 빠지는 운동", "혈당이 뚝 떨어지는 식단",
               "한 달 만에 5kg 감량하는 비법", "피부 탄력을 확실히 되찾는 크림", "목 통증이 쭉 풀리는 베개", "거북목이 쫙 펴지는 스트레칭", "피부가 하루 만에 젊어지는 마스크", "관절 연골이 완전히 재생되는 영양제")
C_EN_MARKETING = ("Lose weight overnight with this tea", "Burn belly fat in one week", "Blood pressure drops instantly with this tea", "Shed body fat in five days")
GAP = ("통증을 즉시 이 베개 하나만으로 줄일 수 있습니다", "피로를 완전히 하루 한 번 이 방법만으로 없앨 수 있다", "두통을 바로 이 한 가지 습관으로 없앱니다", "이 의자에 앉으면 허리 통증이 완전히 그리고 영구적으로 사라집니다",
       "하루 10분 투자로 피로가 즉시 눈에 띄게 줄어듭니다", "목 통증은 이 스트레칭을 한 번 하는 즉시 눈 녹듯 사라집니다", "스트레스를 이 앱 하나로 바로 확실하게 날려 보내세요", "탈모가 걱정이라면 이 샴푸로 완전히 해결하세요",
       "무릎 통증을 이 보호대가 즉시 없애 줍니다", "누구나 이 방법을 따라 하면 두통이 바로 사라집니다", "자세를 이 책상 설정으로 한 번에 바로잡는 방법", "피곤함이 이 차 한 잔으로 금세 가시는 비밀")
GAP_MORE = ("통증을 단 5분 만에 이 쿠션 하나로 줄여 줍니다", "스트레스를 이 차 한 잔으로 바로 해소할 수 있어요", "피로가 이 비타민 한 알로 즉시 풀립니다", "무릎 통증이 이 보호대를 착용하면 즉시 사라집니다",
            "두통이 이 약을 먹으면 바로 낫습니다", "어깨 결림을 이 스트레칭 하나로 확실하게 날려 버립니다", "허리 통증이 이 의자에 앉기만 해도 완전히 사라집니다", "비염을 이 마스크 하나로 하루 만에 잡아 드립니다",
            "피부 트러블이 이 크림 하나만 바르면 금세 없어집니다", "스트레스를 이 방법으로 눈 깜짝할 사이에 해소합니다", "소화불량을 이 식단으로 이틀이면 해결합니다", "두통을 이 약 한 알로 즉각 가라앉힙니다",
            "체중을 이 운동 하나로 한 달 만에 감량합니다", "피로를 이 영양제 한 알로 단번에 날려 줍니다", "눈 피로를 이 안약 한 방울로 바로 풀어 줍니다", "탈모를 이 샴푸 하나로 완전히 영구적으로 막아 줍니다")
PUNCT = ("허리 통증, 즉시 줄이는 방법", "통증 걱정 이제 끝! 즉시 해소", "피로 이제 안녕, 단번에 사라집니다", "두통, 이 한 가지로 바로 사라집니다", "목 통증! 완전히 없애는 베개", "허리 디스크, 확실히 낫는 스트레칭",
         "불면증… 하룻밤에 해결!", "피곤하세요? 즉시 회복시켜 드립니다", "스트레스; 즉각 해소; 이 앱 하나로", "알레르기 걱정, 이제 완전히 차단", "무릎 통증 — 즉시 없애는 법", "비염! 바로 사라지는 차",
         "탈모, 이 샴푸로 완전히 예방", "뱃살 고민? 한 달이면 사라집니다", "어깨 결림, 5분 만에 풀립니다", "눈 피로, 단 하루 만에 회복", "소화불량, 이 차 한 잔으로 즉시 해결", "변비 탈출! 하루 만에 해결",
         "무기력, 이제 안녕", "손목 저림, 바로 해소하는 마우스", "많은 분이 고민하는 문제입니다. 허리 통증, 즉시 줄이는 방법을 알려 드립니다. 아래를 확인하세요.", "요즘 피곤하신가요? 이 비타민 하나면 즉시 회복됩니다. 지금 시작하세요.",
         "목 통증은 이제 그만! 단번에 없애 드립니다")
CONSULT = ("전문가와 상담하면 불면이 즉시 치료됩니다.", "의사에게 물어보면 이 영양제로 당뇨가 낫는다고 합니다.", "병원에 가지 않고 이 식단만으로 고혈압을 완치할 수 있다.", "약사와 상담 없이 이 보충제로 우울증이 사라집니다.",
           "의사 도움 필요 없이 두통을 100% 해결하는 법", "상담이 필요 없는 완벽한 감기 치료법", "병원 안 가도 통증이 바로 사라진다", "의사의 조언은 필요 없고 이 방법이면 불면이 해결됩니다",
           "전문가 상담을 받으세요. 하지만 이 영양제는 당뇨를 완치합니다.", "의사와 상담하세요(이 약은 암을 치료합니다).", "주치의에게 문의한 뒤 이 약으로 혈압을 100% 낮추세요", "상담 후 복용하면 비타민 C가 감기를 확실히 예방합니다")
CONSULT_EN = ("Talk to your doctor, but this supplement cures diabetes.", "You don't need a doctor, this pill cures insomnia instantly.", "Ask your pharmacist; this tea eliminates migraines forever.")
# 행동 순서를 꾸미는 부사(C 아님 — 운영자 기준)와 건강과 무관한 일반·기술·경제 문장: 효과 단정(QG4-CLAIM)이 걸면 안 된다
ACTION = ("통증이 있을 때 즉시 병원에 가서 치료를 받으세요", "두통이 심하면 바로 약국에서 약을 사 드세요", "스트레스를 받으면 즉시 휴식을 취해 완화하세요", "목이 아프면 바로 스트레칭을 하고 증상이 줄어드는지 확인하세요",
          "허리가 아프면 즉시 앉아서 휴식을 취하세요", "피로가 쌓이면 바로 일정을 줄이고 휴식을 늘리세요", "통증이 느껴지면 즉시 운동을 멈추고 의사와 상담하세요", "운동 중 통증이 느껴지면 즉시 멈추세요",
          "두통이 계속되면 바로 병원을 찾아가 진료를 받으세요", "알레르기 증상이 보이면 즉시 약을 복용하세요", "발열이 있으면 곧바로 검사를 받아 감염 여부를 확인하세요", "어지럼증이 생기면 바로 앉아서 물을 마시세요",
          "근육통이 심할 땐 즉시 찜질을 하고 안정을 취하세요", "통증이 있다면 지금 바로 전문의에게 문의하세요", "피곤할 때 바로 카페인을 찾기보다 짧은 산책을 해 보세요", "감기 기운이 느껴지면 바로 쉬고 수분을 충분히 마시세요",
          "눈이 피로하면 즉시 화면을 끄고 눈을 감아 휴식을 취하세요", "스트레스가 쌓이면 곧바로 대화할 사람을 찾아 이야기하세요", "허리 통증이 생기면 바로 자세를 점검하세요", "통증이 있을 때 바로 치료를 받는 것이 중요합니다",
          "허리가 아프면 지금 바로 자세를 교정하세요", "통증이 있을 때 즉시 쉬는 시간을 기록해 두는 방법", "피로할 때 바로 작업환경을 점검하는 방법", "자세가 불편하면 책상 높이를 바로 확인하는 기준")
CONTROL = ("시스템 장애를 즉시 해소했다고 회사는 밝혔다", "서비스 장애가 완전히 복구됐다고 발표했다", "화염을 완전히 차단하는 방화 소재가 개발됐다", "탄산염을 제거하는 공정을 즉시 도입했다",
           "급증하는 수요를 즉시 해소하기 위해 공장을 증설했다", "인증 절차를 즉시 간소화하는 법안이 통과됐다", "하드 디스크 오류를 즉시 해결하는 도구가 공개됐다", "디스크 공간을 바로 확보하는 방법",
           "금융 공황을 즉시 차단하기 위한 대책이 발표됐다", "이명박 정부는 규제를 즉시 완화했다", "해양 오염을 완전히 없애는 기술이 개발됐다", "대기 오염을 즉시 줄이는 정책이 시행된다",
           "공장은 탄소 배출을 제로로 만드는 설비를 도입했다", "보험증 재발급을 즉시 처리하는 시스템이 도입됐다", "저염 식단을 바로 시작하는 요리 교실이 열렸다", "천일염 가격이 즉시 안정되도록 정부가 대책을 마련했다",
           "정부는 감염 확산을 즉시 차단하겠다고 밝혔다", "전염병 확산을 완전히 막는 방역 체계가 가동됐다", "질병관리청은 백신을 즉시 공급한다고 밝혔다", "학생증을 즉시 발급하는 무인 기계가 설치됐다",
           "저작권증 위조를 완전히 차단하는 기술이 도입됐다", "서버 장애를 바로 감지해 해결하는 모니터링 도구가 공개됐다", "정부는 불량 식품을 즉시 회수해 폐기하도록 했다", "이 모델은 지연 시간을 100% 없애는 구조를 제안했다",
           "위원회는 갈등을 즉시 해소하라고 권고했다", "연구진은 오류를 완전히 제거하는 알고리즘을 발표했다", "정부는 규제를 즉시 완화하겠다고 밝혔다", "회사는 불량률을 완전히 없애는 공정을 개발했다고 주장했다",
           "이 프로그램은 오류를 즉시 교정한다", "위원회는 문제를 완전히 해결할 방안을 제시했다", "전자 피부 센서가 압력을 바로 감지한다", "데이터센터는 열을 즉시 방출하는 냉각 방식을 도입했다",
           "스트레스 요인을 점검했다면 바로 나아가는 단계다", "피로 누적을 확인한 뒤 곧바로 나아가는 방향을 정한다",
           "안전인증을 즉시 완료하는 절차가 도입됐다", "품질보증을 완전히 이행하겠다고 회사는 밝혔다", "예약증을 즉시 발급하는 시스템이 도입됐다", "사원증을 바로 교체하는 방법", "방염 소재를 완전히 교체했다고 밝혔다",
           "식염 가격이 바로 안정되도록 대책을 마련했다", "은행의 스트레스 테스트 부담을 즉시 줄이는 방안이 발표됐다", "스트레스 완화 영상을 즉시 재생 목록에 추가했다", "재생에너지 보급을 확실히 늘리는 정책이 발표됐다", "임대차 계약증을 즉시 발급하는 절차", "수강증을 즉시 발급하는 방법", "관람증을 바로 확인하는 방법")
VOCAB = """비염 디스크 무좀 치질 통풍 이명 대상포진 오십견 위염 장염 역류성식도염 방광염 중이염 결막염 편도염 부비동염 축농증 건선 습진 두드러기 지루성피부염
족저근막염 손목터널증후군 좌골신경통 척추측만증 허리디스크 목디스크 탈장 요로결석 담석 치주염 구내염 충치 잇몸질환 다래끼 안구건조증 노안 백내장 녹내장 근시
저혈압 빈맥 부정맥 두근거림 숨참 호흡곤란 코골이 수면무호흡 야뇨 빈뇨 배뇨 전립선 갱년기증후군 생리불순 월경통 불임 발기부전 여드름 기미 주름 흉터 건조증
무기력증 번아웃 공황 불안장애 우울감 ADHD 틱 자폐 치매 건망증 어지럼증 이석증 멀미 구토 메스꺼움 구취 입냄새 땀 다한증 냉증 수족냉증 부종 하지정맥류 쥐 관절염 류마티스 골다공증 통증 피로""".split()
# 일부러 증상 낱말로 세지 않는 모호한 낱말(주름·기미는 일반어, 틱·쥐·땀은 뜻이 여럿) — 목록에서 뺀 이유는 docs/QUALITY_GATE.md §9
VOCAB_AMBIGUOUS = {"기미", "주름", "틱", "땀", "쥐"}


def held_in_both(sentence):
    return bool(codes_body(sentence)) and bool(codes_title(sentence))


class ApprovedAndNewSamplesTest(unittest.TestCase):
    def check(self, sentences, lang="ko"):
        for sentence in sentences:
            with self.subTest(sentence=sentence):
                self.assertTrue(codes_body(sentence, lang), f"본문 위치 미탐: {sentence}")
                self.assertTrue(codes_title(sentence, lang), f"제목 위치 미탐: {sentence}")

    def test_the_operators_c_examples_and_the_verifiers_105_new_sentences_are_all_held(self):
        for name, group in (("운영자 C", OPERATOR_C), ("운영자 부사·동사 × 새 증상어", C_ENUM), ("열린 동사·구조", C_OPEN), ("목록 밖 증상·질환 이름", C_CONDITION), ("질환 + 단정", C_DISEASE), ("긴 간격", GAP)):
            with self.subTest(group=name):
                self.check(group)
        self.check(C_EN, "en")
        self.assertEqual(len(OPERATOR_C) + len(C_ENUM) + len(C_OPEN) + len(C_CONDITION) + len(C_DISEASE) + len(C_EN) + len(GAP), 9 + 30 + 16 + 12 + 8 + 10 + 12)

    def test_marketing_phrases_with_recovery_verbs_colloquial_adverbs_and_kilogram_loss_are_held(self):
        self.check(C_MARKETING)
        self.check(C_EN_MARKETING, "en")
        for sentence in C_MARKETING:
            self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)          # 프로필 낱말이 아니라 효과 단정 규칙 자체가 잡는다
        for sentence in C_EN_MARKETING:
            self.assertIsNotNone(qg._effect_claim(sentence, "en"), sentence)

    def test_punctuation_between_the_symptom_and_the_immediate_effect_does_not_hide_it(self):
        self.check(PUNCT)

    def test_a_long_gap_made_of_a_noun_phrase_or_adverbs_is_still_an_effect_claim(self):
        self.check(GAP_MORE)

    def test_consultation_phrases_do_not_excuse_an_efficacy_claim(self):
        self.check(CONSULT)
        self.check(CONSULT_EN, "en")

    def test_action_order_sentences_and_unrelated_sentences_are_not_held_as_effect_claims(self):
        for sentence in ACTION + CONTROL:
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)
                self.assertNotIn("QG4-CLAIM", codes_body(sentence))
                self.assertNotIn("QG4-CLAIM", codes_title(sentence))

    def test_some_action_sentences_pass_the_whole_health_rule(self):
        for sentence in ("두통이 심하면 바로 약국에서 사 드세요", "허리가 아프면 즉시 앉아서 휴식을 취하세요", "피로가 쌓이면 바로 일정을 줄이고 휴식을 늘리세요", "통증이 느껴지면 즉시 운동을 멈추고 기록하세요",
                         "운동 중 통증이 느껴지면 즉시 멈추세요", "허리가 아프면 지금 바로 자세를 교정하세요", "피로할 때 바로 작업환경을 점검하는 방법"):
            with self.subTest(sentence=sentence):
                self.assertEqual(codes_body(sentence), [], sentence)
                self.assertEqual(codes_title(sentence), [], sentence)


class SymptomVocabularyTest(unittest.TestCase):
    FRAMES = ("{w}을 즉시 없애는 방법", "{w}이 바로 사라지는 차", "{w} 100% 보장")

    def test_the_verifiers_91_words_are_held_in_every_frame_except_the_ambiguous_five(self):
        self.assertEqual(len(VOCAB), 91)
        for frame in self.FRAMES:
            missed = {word for word in VOCAB if not held_in_both(frame.format(w=word))}
            with self.subTest(frame=frame):
                self.assertEqual(missed - VOCAB_AMBIGUOUS, set(), "목록 밖 증상·질환 낱말이 통과한다")
                self.assertGreaterEqual(len(VOCAB) - len(missed), 78)          # 91개 중 85% 이상(78개)이라는 측정 목표

    def test_the_suffix_rules_read_unlisted_names_that_end_like_a_disease(self):
        for word in ("가나염", "다라마염", "불면증", "과민증", "협착증", "마비증", "엠피증후군", "수면 장애", "섭식장애", "당뇨병", "지병", "만성병", "성병"):
            with self.subTest(word=word):
                self.assertIsNotNone(qg._SYMPTOM_KO.search(f"{word}을 즉시"), word)

    def test_ordinary_words_that_end_the_same_way_are_not_symptoms(self):
        for word in ("저작권증", "보험증", "신분증", "영수증", "자격증", "학생증", "주민등록증", "화염", "탄산염", "질산염", "천일염", "저염", "고염", "무염", "오염", "요염", "감염", "전염", "급증", "폭증", "보증", "인증",
                     "검증", "입증", "시스템 장애", "서비스 장애", "통신 장애", "시각장애인", "하드 디스크", "디스크 공간", "SSD 디스크", "금융 공황", "이명박", "질병관리청", "가래떡", "졸음운전",
                     "안전인증", "품질보증", "정품인증", "예약증", "교환증", "임대차계약증", "수강증", "관람증", "사원증", "방염", "식염"):
            with self.subTest(word=word):
                self.assertIsNone(qg._SYMPTOM_KO.search(f"{word}을 즉시"), word)

    def test_a_kilogram_figure_with_loss_is_a_body_state_but_other_weights_are_not(self):
        for text in ("5kg 감량", "10 킬로 빼는", "3 KG 감량", "2킬로그램 빠지는"):
            with self.subTest(text=text):
                self.assertIsNotNone(qg._SYMPTOM_KO.search(text))
        for text in ("kg 감량", "배터리 5kg 줄이는", "5kg 상자를 옮기는"):
            with self.subTest(text=text):
                self.assertIsNone(qg._SYMPTOM_KO.search(text))

    def test_a_long_digit_run_does_not_make_the_symptom_search_quadratic(self):
        started = time.perf_counter()
        self.assertIsNone(qg._SYMPTOM_KO.search("1" * 30000))
        self.assertIsNotNone(qg._SYMPTOM_KO.search("1" * 30000 + "kg 감량"))                # 숫자 덩어리의 맨 앞에서만 시작하므로 선형이다(맨 앞 조건을 지우면 3만 자에 수십 초)
        self.assertLess(time.perf_counter() - started, 1.0)

    def test_a_colloquial_adverb_must_stand_alone(self):
        for text in ("통증이 확 줄어", "뱃살이 쏙 빠지는", "혈압이 뚝 떨어지는", "허리가 쫙 펴지는", "어깨가 쭉 풀리는"):
            with self.subTest(text=text):
                self.assertIsNotNone(qg._IMMEDIATE_KO.search(text))
        for text in ("명확 해소", "정확 하게", "통증 확인", "기확 "):
            with self.subTest(text=text):
                self.assertIsNone(qg._IMMEDIATE_KO.search(text))

    def test_symptom_words_that_are_also_ordinary_nouns_keep_their_guards(self):
        self.assertIsNotNone(qg._SYMPTOM_KO.search("디스크를 즉시 없애는 자세"))
        self.assertIsNone(qg._SYMPTOM_KO.search("컴퓨터 디스크를 즉시 정리"))
        self.assertIsNotNone(qg._SYMPTOM_KO.search("공황 발작을 즉시"))
        self.assertIsNone(qg._SYMPTOM_KO.search("금융 스트레스 테스트를 즉시"))
        self.assertIsNotNone(qg._SYMPTOM_KO.search("스트레스를 즉시"))
        self.assertIsNotNone(qg._SYMPTOM_KO.search("이명을 즉시"))
        self.assertIsNotNone(qg._SYMPTOM_KO.search("가래가 즉시"))


class ClaimStructureTest(unittest.TestCase):
    def test_a_short_text_is_one_unit_whatever_its_punctuation(self):
        text = "허리 통증, 즉시 줄이는 방법! 지금? 확인. 끝"
        self.assertLessEqual(len(text), qg.CLAIM_SHORT_CHARS)
        self.assertEqual(list(qg._claim_units(text)), [text])
        self.assertEqual(list(qg._claim_units("")), [])
        self.assertEqual(list(qg._claim_units(None)), [])

    def test_a_long_text_splits_at_sentence_ends_and_keeps_short_sentences_whole(self):
        first, second = "가" * 80 + ",", "나" * 80
        self.assertEqual(list(qg._claim_units(first + ". " + second)), [first, second])
        self.assertEqual(list(qg._claim_units("가" * 130 + "\n" + "나" * 20)), ["가" * 130, "나" * 20])           # 줄바꿈도 문장 경계, 120자를 넘는 문장도 쉼표가 없으면 통째로 한 조각

    def test_long_sentences_are_cut_into_clauses_and_neighbouring_pairs(self):
        c1, c2, c3 = "가" * 70, "나" * 70, "다" * 70
        self.assertEqual(list(qg._claim_units(f"{c1}, {c2}, {c3}")), [c1, c1 + " " + c2, c2, c2 + " " + c3, c3])
        self.assertEqual(list(qg._claim_units(f"{c1}! {c2}")), [c1, c1 + " " + c2, c2])

    def test_two_neighbouring_clauses_are_joined_only_while_they_fit_in_one_window(self):
        short, fits, too_long = "가" * 130, "나" * 199, "다" * 200
        self.assertEqual(len(short) + len(fits), qg.CLAIM_WINDOW - 71)
        joined = list(qg._claim_units(f"{short}, {fits}"))
        self.assertEqual(joined, [short, short + " " + fits, fits])                                    # 130 + 199 = 329 < 400
        first, second = "가" * 199, "나" * 200
        self.assertEqual(list(qg._claim_units(f"{first}, {second}")), [first, first + " " + second, second])          # 199 + 200 = 399 < 400: 이어 본다
        self.assertEqual(list(qg._claim_units(f"{second}, {too_long}")), [second, too_long])                          # 200 + 200 = 400: 이으면 한 창에 안 들어가므로 잇지 않는다

    def test_a_newline_is_a_boundary_even_in_a_short_text(self):
        self.assertEqual(list(qg._claim_units("통증이 심합니다\n즉시 줄이는 방법")), ["통증이 심합니다", "즉시 줄이는 방법"])
        self.assertIsNone(qg._effect_claim("통증이 심합니다\n즉시 줄이는 방법", "ko"))
        self.assertIsNotNone(qg._effect_claim("통증이 심합니다 즉시 줄이는 방법", "ko"))

    def test_a_question_mark_joins_only_a_short_question_to_its_answer(self):
        short_question, answer = "요즘 피곤하신가요", "나" * 130
        self.assertLessEqual(len(short_question), qg.CLAIM_QUESTION_CHARS)
        self.assertEqual(list(qg._claim_units(f"{short_question}? {answer}")), [short_question, short_question + " " + answer, answer])
        long_question = "가" * (qg.CLAIM_QUESTION_CHARS + 10)
        self.assertEqual(list(qg._claim_units(f"{long_question}? {answer}")), [long_question, answer])

    def test_a_period_is_always_a_boundary_in_a_long_text(self):
        body = body_with("요즘 허리 통증이 심합니다. 즉시 줄이는 방법을 소개합니다.")
        self.assertIsNone(qg._effect_claim(body, "ko"))                                  # 마침표로 끊긴 증상과 즉각 효과는 잇지 않는다(문장 둘)
        self.assertIsNotNone(qg._effect_claim(body_with("요즘 허리 통증이 심합니다 즉시 줄이는 방법을 소개합니다."), "ko"))      # 마침표가 없으면 한 문장이라 이어서 본다

    def test_windows_overlap_so_a_claim_up_to_two_hundred_chars_long_is_always_inside_one_window(self):
        self.assertEqual(list(qg._claim_windows("x" * qg.CLAIM_WINDOW)), ["x" * qg.CLAIM_WINDOW])
        self.assertEqual(len(list(qg._claim_windows("x" * (qg.CLAIM_WINDOW + 1)))), 2)
        text = "".join(chr(0xAC00 + i % 100) for i in range(1000))
        windows = list(qg._claim_windows(text))
        for start in range(0, len(text) - qg.CLAIM_STEP + 1, 7):
            piece = text[start:start + qg.CLAIM_STEP]
            self.assertTrue(any(piece in window for window in windows), start)

    def test_the_claim_search_never_looks_at_more_than_one_window_at_a_time(self):
        seen = []
        real = qg._claim_in

        def spy(unit, lang):
            seen.append(len(unit))
            return real(unit, lang)

        text = "통증 " + "즉시 이 베개 하나만으로 " * 400                 # 문장 부호 없는 긴 조각
        self.assertGreater(len(text), 3 * qg.CLAIM_WINDOW)
        with mock.patch.object(qg, "_claim_in", spy):
            self.assertIsNone(qg._effect_claim(text, "ko"))
        self.assertGreater(len(seen), 1)
        self.assertLessEqual(max(seen), qg.CLAIM_WINDOW)                   # 창을 지우고 조각 통째를 보면 시간이 글 길이의 제곱으로 늘어난다

    def test_a_claim_is_found_wherever_it_sits_in_a_long_sentence_without_any_punctuation(self):
        claim = " 통증을 즉시 줄이는 방법 "
        for offset in (0, 1, 100, 199, 200, 201, 380, 390, 395, 399, 400, 401, 405, 600, 790, 1000, 2000, 2990):
            sentence = "가" * offset + claim + "나" * (3000 - offset)
            with self.subTest(offset=offset):
                self.assertEqual(qg._effect_claim(sentence, "ko"), ("통증", "즉시", "줄이"))
                self.assertIsNotNone(qg._effect_claim(sentence, "ko"))
        self.assertEqual(qg._effect_claim("가" * 392 + claim, "ko"), ("통증", "즉시", "줄이"))        # 앞 400자만 보던 때 빠지던 모양

    def test_the_gap_decides_by_structure_not_by_length(self):
        modifies = qg._ko_gap_modifies_result
        self.assertTrue(modifies(""))
        self.assertTrue(modifies(" 이 베개 하나만으로 "))
        self.assertTrue(modifies(" 하루 한 번 이 방법만으로 "))
        self.assertTrue(modifies(" 그리고 영구적으로 "))
        self.assertTrue(modifies(" 통증을 "))                                              # 증상 자체가 대상이면 결과 수식이다
        self.assertFalse(modifies(" 병원에 가서 "))
        self.assertFalse(modifies(" 약을 먹으면 증상이 "))
        self.assertFalse(modifies(" 작업을 "))                                             # 증상이 아닌 다른 대상(…을)이 끼면 그 대상을 두고 하는 행동이다
        self.assertTrue(modifies(" 자세를 "))                                              # 증상 낱말인지는 조사까지 붙여 본다('자세' 는 조사가 붙을 때만 몸 상태 낱말)
        self.assertFalse(modifies(" 스트레칭을 하고 "))
        self.assertFalse(modifies(" 휴식을 취해 "))
        self.assertFalse(modifies("가" * (qg._CLAIM_GAP_KO_CAP + 1)))
        self.assertTrue(modifies("가" * qg._CLAIM_GAP_KO_CAP))

    def test_the_gap_cap_is_forty_chars(self):
        near = "통증을 즉시 " + "이 방법 " * 7 + "줄입니다"                                  # 사이 36자
        far = "통증을 즉시 " + "이 방법 " * 8 + "줄입니다"                                   # 사이 41자
        self.assertIsNotNone(qg._effect_claim(near, "ko"))
        self.assertIsNone(qg._effect_claim(far, "ko"))
        self.assertEqual(qg._CLAIM_GAP_EN, 30)

    def test_a_time_adverb_before_an_imperative_urges_an_action_but_an_absolute_adverb_still_claims(self):
        for sentence in ("허리가 아프면 지금 바로 자세를 교정하세요", "통증을 즉시 줄이세요", "피로를 곧바로 해소해 보세요", "스트레스를 당장 풀어 주세요"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)
        for sentence in ("탈모가 걱정이라면 이 샴푸로 완전히 해결하세요", "스트레스를 완벽하게 해소하세요", "불면을 확실히 없애 보세요", "피로를 즉시 줄여 줍니다", "통증을 바로 해소합니다"):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)
        self.assertEqual(qg._TEMPORAL_KO, frozenset({"즉시", "즉각", "곧바로", "바로", "당장"}))
        self.assertIsNotNone(qg._effect_claim("피로를 즉시 줄여 줍니다, 지금 시작하세요", "ko"))        # 명령형은 효과 동사 바로 뒤에서만 본다 — 뒤 절의 '시작하세요'가 앞 절의 단정을 가리지 못한다
        self.assertIsNone(qg._effect_claim("통증이 있으면 당장 교정하세요", "ko"))
        self.assertIsNone(qg._effect_claim("스트레스를 당장 풀어 보세요", "ko"))

    def test_an_object_that_means_receiving_treatment_is_not_an_effect_verb(self):
        for sentence in ("통증이 있으면 즉시 치료를 받으세요", "두통이 계속되면 바로 치료를 위해 병원에 가세요", "통증은 즉시 치료를 통해 관리하세요"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_every_declarative_ending_of_every_effect_family_is_a_claim(self):
        forms = ("줄입니다", "없앱니다", "낮춥니다", "날립니다", "녹입니다", "태웁니다", "끝냅니다", "막습니다", "잡습니다", "뚫습니다", "풀어 줍니다", "해소합니다", "해결합니다", "교정합니다", "개선합니다", "회복합니다",
                 "예방합니다", "감량합니다", "치료합니다", "완화합니다", "제거합니다", "차단합니다", "정복합니다", "치유합니다", "사라집니다", "낫습니다", "좋아집니다", "나아집니다", "멈춥니다", "멎습니다",
                 "되찾습니다", "되살립니다", "되돌립니다", "젊어집니다", "재생합니다", "재생됩니다", "빠집니다",
                 "펴집니다", "편안해집니다", "가라앉힙니다", "날아갑니다", "떨어집니다", "풀립니다", "뚫립니다", "없어집니다", "줄었습니다", "나았습니다", "풀렸습니다", "털어 줍니다", "극복합니다", "퇴치합니다", "정상화합니다")
        for form in forms:
            with self.subTest(form=form):
                self.assertIsNotNone(qg._effect_claim("통증을 즉시 " + form, "ko"), form)

    def test_stopping_is_an_effect_only_when_the_symptom_is_what_stops(self):
        self.assertIsNotNone(qg._effect_claim("두통이 즉각 멈춥니다", "ko"))
        self.assertIsNone(qg._effect_claim("운동 중 통증이 느껴지면 즉시 멈추세요", "ko"))
        self.assertIsNone(qg._effect_claim("통증이 느껴지면 즉시 작업을 멈추고 기록한다", "ko"))
        self.assertIsNone(qg._effect_claim("통증이 느껴지면 즉시 작업을 멈춰 주세요", "ko"))
        self.assertIsNone(qg._effect_claim("통증이 심하면 운동을 완전히 멈춰 주세요", "ko"))             # 단정 부사 + 멈춰 주세요: 멈추라는 부탁이지 증상이 멈춘다는 말이 아니다

    def test_freedom_phrases_with_a_symptom_are_claims_even_without_an_effect_verb(self):
        for sentence in ("두통 제로 비법", "통증 걱정 끝, 이 의자 하나로", "피로 이제 안녕", "굿바이 두통", "피로와 작별하는 습관", "스트레스 걱정 없는 하루"):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)
        for sentence in ("탄소 제로 건물을 짓는다", "안녕하세요 허리 통증 상담입니다", "피로가 쌓인 직장인의 하루가 이제 끝났다", "제로섬 게임의 피로", "이제 끝"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_english_additions(self):
        for sentence in C_EN + ("Say goodbye to stress for good", "Instant relief from back pain", "Headaches gone in two days", "Beat insomnia within a week", "Snoring? Stopped in one night", "This tea soothes a sore throat instantly"):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(qg._effect_claim(sentence, "en"), sentence)
        for sentence in ("Seek immediate medical attention if the chest pain lasts", "The weight of the evidence is clear", "Stress tests were completed"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "en"), sentence)

    def test_the_claim_search_stays_fast_on_thirty_thousand_characters_of_every_punctuation_shape(self):
        shapes = {"commas": "가," * 15000, "exclaims": "가! " * 10000, "questions": "가? " * 10000, "periods": "가. " * 10000, "mixed": ("허리 통증, 즉시 줄이는 방법! " * 2000)[:30000],
                  "no_punctuation": ("통증을 즉시 이 베개 하나만으로 줄일 수 있습니다 " * 1200)[:30000], "symptoms": "비염 두통 통증 피로 " * 2700, "suffixes": "가나염 다라증 마바병 " * 3000,
                  "adverbs": "즉시 이 베개 하나만으로 " * 2100, "effects": "줄이 없애 풀립 멈춥 " * 2700, "objects": "통증을 즉시 가나을 다라를 마바를 " * 1500}
        for name, text in shapes.items():
            started = time.perf_counter()
            qg._claim_lang_hit(text)
            with self.subTest(shape=name):
                self.assertLess(time.perf_counter() - started, 2.0)


class ProductCureClaimTest(unittest.TestCase):
    def test_a_product_that_is_said_to_cure_a_disease_is_held_even_with_a_consultation_phrase(self):
        for sentence in ("의사에게 물어보면 이 영양제로 당뇨가 낫는다고 합니다.", "의사와 상담하세요(이 약은 암을 치료합니다).", "그 보충제는 고혈압을 완치시킵니다", "이 식단은 불면을 고쳐 줍니다", "해당 제품이 우울증을 치료합니다"):
            with self.subTest(sentence=sentence):
                found = codes_body(sentence)
                self.assertIn("QG4-CLAIM", found, sentence)

    def test_denials_hedges_and_information_sentences_are_left_alone(self):
        for sentence in ("이 영양제는 당뇨를 치료하지 못합니다", "이 약이 암을 낫게 한다는 근거는 없다", "이 방법으로 낫는다는 주장은 입증되지 않았다", "이 영양제로 당뇨가 낫는다는 주장은 입증되지 않았다", "이 약이 암을 치료한다는 광고는 허위다", "이 약은 암을 치료하는 데 쓰입니다", "이 약은 처방 없이 구매할 수 없다",
                         "이 차이는 건강과 상관이 없다", "이 약속은 건강에 도움이 된다"):
            with self.subTest(sentence=sentence):
                self.assertNotIn("QG4-CLAIM", codes_body(sentence), sentence)

    def test_a_product_noun_must_be_a_whole_word(self):
        self.assertIsNone(qg._PRODUCT_CURE.search("이 약속은 당뇨를 치료합니다"))
        self.assertIsNone(qg._PRODUCT_CURE.search("이 차이는 암을 치료합니다"))
        self.assertIsNotNone(qg._PRODUCT_CURE.search("이 차는 암을 치료합니다"))
        self.assertIsNotNone(qg._PRODUCT_CURE.search("이 약은 암을 치료합니다"))

    def test_the_cure_verb_must_follow_the_product_within_forty_chars_of_the_same_sentence(self):
        def sentence(gap):
            return "이 영양제" + "는 " + "가" * (gap - 3) + " " + "치료합니다"          # 제품 낱말과 치료 활용 사이가 정확히 gap 글자

        self.assertIsNotNone(qg._PRODUCT_CURE.search(sentence(40)))
        self.assertIsNone(qg._PRODUCT_CURE.search(sentence(41)))
        self.assertIn("QG4-CLAIM", codes_body(sentence(40)))
        self.assertIsNone(qg._PRODUCT_CURE.search("이 영양제는 안전합니다. 다른 곳에서 당뇨를 치료합니다"))          # 마침표를 넘어 잇지 않는다

    def test_only_a_demonstrative_plus_a_product_or_method_is_a_cure_claim(self):
        for text in ("약은 암을 치료합니다", "연구에서 영양제는 우울증을 치료합니다", "치료법이 암을 치료합니다"):
            with self.subTest(text=text):
                self.assertIsNone(qg._PRODUCT_CURE.search(text))                      # 지시어가 없는 일반 서술은 이 규칙이 보지 않는다(한계 — docs/QUALITY_GATE.md §9)
        for text in ("이 앱은 지연을 해결합니다", "그 방법은 문제를 해결한다", "해당 제품은 오류를 개선합니다", "이 식단으로 사진 정리가 개선됩니다"):
            with self.subTest(text=text):
                self.assertNotIn("QG4-CLAIM", codes_body(text))                      # 건강 낱말이 없는 제품 효과 문장은 이 규칙의 대상이 아니다

    def test_a_product_cure_claim_in_the_title_is_held_too(self):
        self.assertIn("QG4-CLAIM", codes_title("이 영양제로 당뇨가 낫는다고 합니다"))
        self.assertIn("QG4-CLAIM", codes_title("이 차는 불면을 고쳐 줍니다"))


class TitledPeopleTest(unittest.TestCase):
    def test_a_one_word_foreign_name_with_a_head_title_is_a_person(self):
        for text, names in (("트럼프 대통령은 관세를 올리겠다고 밝혔다.", ["트럼프"]), ("파월 의장은 금리를 동결했다.", ["파월"]), ("시진핑 주석은 방문했다.", ["시진핑"]), ("머스크 CEO는 말했다.", ["머스크"])):
            with self.subTest(text=text):
                self.assertEqual(qg._titled_people(text)[1], names)

    def test_organisations_countries_and_modifiers_before_a_title_are_not_people(self):
        for text in ("한국은행 총재는 금리를 동결했다고 밝혔다.", "삼성전자 회장은 말했다.", "국회 의장은 말했다.", "시의회 의장은 말했다.", "미국 대통령은 방문했다.", "신임 대통령은 취임했다.", "정부 대표는 참석했다.",
                     "회사 대표는 말했다.", "러시아 대통령은 방문했다.", "이번 위원장은 말했다.", "서울대 교수는 말했다."):
            with self.subTest(text=text):
                self.assertEqual(qg._titled_people(text), ([], []))

    def test_a_two_word_name_is_counted_once(self):
        self.assertEqual(qg._titled_people("제롬 파월 연준 의장은 말했다.")[1].count("제롬 파월"), 1)
        self.assertNotIn("파월", qg._titled_people("제롬 파월 연준 의장은 말했다.")[1])
        self.assertNotIn("파월", qg._titled_people("제롬 파월 의장은 말했다.")[1])                           # 이미 읽은 두 낱말 이름 속의 '파월 의장은'을 한 낱말 이름으로 또 읽지 않는다
        self.assertEqual(qg._titled_people("제롬 파월 의장은 말했다.")[1].count("제롬 파월"), 1)

    def test_a_latin_word_before_a_korean_title_and_the_name_ceo_order(self):
        self.assertEqual(qg._titled_people("Powell 의장은 금리를 동결했다.")[0], ["Powell"])
        self.assertEqual(qg._titled_people("Elon Musk CEO announced it.")[0], ["Elon Musk"])
        self.assertEqual(qg._titled_people("Musk, the company's CEO, said so.")[0], ["Musk"])

    def test_sentence_openers_and_months_before_a_comma_are_not_names(self):
        for text in ("However, the company's director said so.", "In March, the agency's president said so.", "Meanwhile, the minister left.", "Today, the agency's chief executive spoke."):
            with self.subTest(text=text):
                self.assertEqual(qg._titled_people(text)[0], [])

    def test_an_invented_speaker_is_held_when_the_source_has_no_such_person(self):
        evidence = "The agency released a report on tariffs. President Lee commented on the data."
        two_speakers = qg.prose_of("트럼프 대통령은 관세를 올리겠다고 밝혔다. 파월 의장은 금리를 동결했다.")
        self.assertEqual([hold.code for hold in qg.rule_quotes("ko", two_speakers, evidence)], ["QG2-PERSON"])          # 직함 붙은 사람이 근거(1명)보다 많다
        self.assertEqual(qg.rule_quotes("ko", qg.prose_of("트럼프 대통령은 관세를 올리겠다고 밝혔다."), "President Trump announced tariffs."), [])
        self.assertEqual([hold.code for hold in qg.rule_quotes("ko", qg.prose_of("파월 의장은 금리를 동결했다."), "트럼프 대통령은 관세를 올리겠다고 밝혔다.")], ["QG2-PERSON"])   # 같은 글자 체계면 이름이 근거에 그대로 있어야 한다
        self.assertEqual(qg.rule_quotes("ko", qg.prose_of("트럼프 대통령은 관세를 올리겠다고 밝혔다."), "트럼프 대통령은 관세를 올리겠다고 밝혔다."), [])


class HiddenHealthTextTest(unittest.TestCase):
    def gate(self, **kw):
        return h.run_gate(data=h.make_data(ko=h.ko_body(**kw)), config=h.make_config(("ko",))).codes()

    def test_the_text_the_cleaner_removes_but_a_reader_can_see_is_collected(self):
        text = '![이 의자는 허리 통증을 즉시 없애 줍니다](x.png) <span title="완치 보장">설명</span> <img alt=\'당뇨가 낫는 차\' src="u"> [출처 글자](http://a) `code` ```print("x")```'
        found = qg.hidden_health_text(text)
        for piece in ("이 의자는 허리 통증을 즉시 없애 줍니다", "완치 보장", "당뇨가 낫는 차", "출처 글자"):
            self.assertIn(piece, found)
        self.assertEqual(found.count("이 의자는 허리 통증을 즉시 없애 줍니다"), 1)             # 이미지 대체글을 링크 글자로 또 읽지 않는다
        self.assertEqual(found.splitlines().count("출처 글자"), 1)
        self.assertNotIn("print", found)                          # 코드는 읽지 않는다(기술 글 오탐)
        self.assertEqual(qg.hidden_health_text("![ ](a.png) <b title=\"\">x</b> [ ](http://a)"), "")          # 비어 있는 조각은 모으지 않는다
        self.assertEqual(qg.hidden_health_text('<a aria-label="통증 완치 보장">x</a> <img alt="그림">'), "통증 완치 보장\n그림")
        self.assertEqual(qg.hidden_health_text(None), "")
        self.assertEqual(qg.hidden_health_text("평범한 글"), "")

    def test_an_efficacy_claim_hidden_in_an_image_description_an_html_attribute_or_a_source_link_text_is_held(self):
        self.assertIn("QG4-CLAIM", self.gate(extra="![이 의자는 허리 통증을 즉시 없애 줍니다](https://example.invalid/x.png)"))
        self.assertTrue({"QG4-ASSERT", "QG4-HEALTH"} & set(self.gate(extra='<span title="이 약은 당뇨를 완치합니다">설명</span>')))
        self.assertIn("QG4-CLAIM", self.gate(source_list="### 출처\n- [이 영양제로 당뇨가 낫는다는 연구](" + h.LINK + ")"))

    def test_an_ordinary_image_and_source_list_are_not_held(self):
        self.assertEqual([code for code in self.gate() if code.startswith("QG4")], [])
        self.assertEqual([code for code in self.gate(extra="![예시 그림](https://example.invalid/y.png)") if code.startswith("QG4")], [])

    def test_a_code_block_is_not_read_for_health_words(self):
        found = self.gate(extra="```\nweight = 3  # always clear the cache, stress test, pain point\n```")
        self.assertEqual([code for code in found if code.startswith("QG4")], [])


class UrlPortAndAccountTest(unittest.TestCase):
    def test_a_different_port_or_account_is_a_different_source(self):
        base = qg.normalize_url("https://example.com/news/a")
        self.assertEqual(base, "example.com/news/a")
        self.assertNotEqual(qg.normalize_url("https://example.com:8443/news/a"), base)
        self.assertNotEqual(qg.normalize_url("https://user@example.com/news/a"), base)
        self.assertNotEqual(qg.normalize_url("https://user:pw@example.com/news/a"), base)
        self.assertNotEqual(qg.normalize_url("https://a@example.com/news/a"), qg.normalize_url("https://b@example.com/news/a"))

    def test_the_default_ports_and_the_scheme_are_still_the_same_source(self):
        base = qg.normalize_url("https://example.com/news/a")
        for url in ("https://example.com:443/news/a", "http://example.com:80/news/a", "http://example.com/news/a", "HTTPS://WWW.Example.com/news/a/#top"):
            with self.subTest(url=url):
                self.assertEqual(qg.normalize_url(url), base)

    def test_an_unreadable_port_is_an_unreadable_address(self):
        for url in ("https://example.com:99999/a", "https://example.com:abc/a", "https://example.com:-1/a"):
            with self.subTest(url=url):
                self.assertEqual(qg.normalize_url(url), "")

    def test_the_verified_link_must_match_port_and_account_and_the_reuse_rule_sees_them(self):
        story = "원문은 [여기](https://example.com:8443/news/a)에 있습니다."
        self.assertFalse(qg.has_verified_link(story, "https://example.com/news/a"))
        self.assertTrue(qg.has_verified_link(story, "https://example.com:8443/news/a"))
        self.assertEqual(qg.rule_reuse("https://user@example.com/news/a", [{"source_url": "https://example.com/news/a"}]), [])
        self.assertEqual([hold.code for hold in qg.rule_reuse("https://example.com:443/news/a", [{"source_url": "https://example.com/news/a"}])], ["QG7-REUSE"])


# === 3차 독립 검증(2026-11-10)이 남긴 것: GATEFIX3 ===================================================================================================
# D1 …하고 형용사 나열 · D2 닫힌 목록 틈(어간·어순·시간 낱말·동의어) · D4 소수점 마침표 · D5 몸 낱말 대상 · D6–D8 허용 방향 오탐 · D9 숨은 글 · D11 제목 정규화 · D13 경계·상수·규칙 삭제 시험.
# 문장은 모두 지어낸 것이다.
ZWSP, SHY, WJ, IDEO_SPACE = chr(0x200B), chr(0x00AD), chr(0x2060), chr(0x3000)          # 제로폭 공백·소프트 하이픈·단어 결합자·전각 공백(소스에 보이지 않는 글자를 남기지 않으려고 chr 로 만든다)
ADJECTIVE_LISTS = ("안전하고 부드럽게", "편안하고 빠르게", "간편하고 정확하게", "깨끗하고 개운하게", "건강하고 가볍게", "자연스럽고 편하게", "쉽고 간단하게",
                   "안전하며 부드럽게", "편안하여 가볍게", "간편해서 확실하게", "깨끗하면서 개운하게", "신속하고 철저하게", "꼼꼼하고 정확하게", "확실하며 빠르게")
ACTION_FILLERS = (" 이 약을 먹고 ", " 병원에 가서 ", " 휴식을 취하고 ", " 스트레칭을 하고 ", " 확인하고 ", " 휴식하고 ", " 샤워하며 ", " 운동하면서 ", " 상담하여 ", " 연락해서 ", " 하고 ", " 그렇게 해서 ")
DO_VERB_STEMS = ("확인", "기록", "점검", "측정", "관찰", "체크", "휴식", "운동", "상담", "문의", "준비", "정리", "조절", "조정", "사용", "중단", "중지", "복용", "섭취", "실시", "진행", "시작", "이동", "대기", "연락", "신고", "검사",
                 "진료", "진찰", "진단", "처방", "접종", "교체", "청소", "세척", "환기", "스트레칭", "마사지", "명상", "산책", "샤워", "목욕", "취침", "기상", "외출", "귀가", "예약", "방문", "내원", "처치", "보관", "분리", "착용",
                 "부착", "적용", "비교", "선택", "구매", "구입", "신청", "등록", "시도", "실행", "참고", "검토", "저장", "입력", "설치", "재시작", "재부팅", "출발", "도착", "질문", "확보", "유지", "병행", "반복", "연습", "훈련",
                 "참여", "실천", "지속", "제외", "조치", "대화", "소독", "세안", "양치", "보온", "보습", "호흡", "이완", "관리", "조심", "주의", "검색", "조회", "전화", "호출", "촬영", "녹음", "메모", "압박", "고정", "냉각", "세탁",
                 "배치", "재측정", "재검사", "재확인", "재시도", "접속", "로그인", "다운로드", "업로드", "백업", "복원", "삭제", "초기화", "재설정", "설정", "변경", "수정", "편집", "공유", "전송", "발송", "전달", "보고", "안내", "공지", "거상")
TIME_UNITS = ("3초", "3분", "3시간", "3일", "3주", "3개월", "하루", "이틀", "사흘", "나흘", "사나흘", "열흘", "보름", "일주일", "이주일", "한 달", "며칠", "한 시간", "두 주", "세 시간", "네 주")
TIME_ENDINGS = ("이면", "이내", "만에", "안에", "내에", "동안", "후면", "뒤면", "만", "컷")
TIME_WORDS = ("두통 즉효 소개", "두통 즉효성 진통제", "곧 피로가 풀립니다", "바르자마자 통증이 줄어듭니다", "마시자마자 숙취가 가라앉는 차", "붙이는 순간 어깨 결림이 풀립니다", "누르는 순간 근육통이 풀리는 마사지건",
              "복용 직후 두통이 사라집니다", "단 한 번으로 통증이 사라집니다", "단 한 알이면 두통이 사라집니다", "단 한 잔으로 숙취가 가라앉습니다", "단 한 회 사용으로 통증이 줄어듭니다", "단 한 방울로 두통이 사라집니다",
              "단 1회로 통증이 사라집니다", "단 30초면 두통이 가라앉습니다", "단 2시간이면 비염이 가라앉습니다", "단 3주면 거북목이 교정됩니다", "단 2개월이면 체중이 줄어듭니다", "단 5분 컷 두통 해소", "단 사흘이면 불면이 해결됩니다", "단 3번이면 두통이 사라집니다",
              # 끝말이 따로 없는 '단 …'(다른 기간 대안이 같이 읽지 못하는 모양) — 단위마다 하나씩
              "단 하루 사용으로 통증이 줄어듭니다", "단 이틀 사용으로 두통이 사라집니다", "단 사흘 사용으로 불면이 해결됩니다", "단 30초 사용으로 두통이 사라집니다", "단 5분 사용으로 통증이 줄어듭니다",
              "단 2시간 사용으로 비염이 가라앉습니다", "단 3일 사용으로 허리 통증이 사라집니다", "단 2주 사용으로 거북목이 교정됩니다", "단 3개월 사용으로 체중이 줄어듭니다", "단 3번 사용으로 두통이 사라집니다",
              "단 1회 사용으로 통증이 줄어듭니다", "단 한 번 사용으로 두통이 사라집니다", "단 한 알 사용으로 두통이 사라집니다", "단 한 잔 사용으로 숙취가 가라앉습니다", "단 한 회 사용으로 통증이 줄어듭니다", "단 한 방울로 두통이 사라집니다", "단 5분이면 허리 통증이 해소됩니다", "단 하루에 끝내는 감기 비법", "단 3일 만에 허리 통증이 사라집니다", "단 이틀이면 불면이 해결됩니다", "허리 통증 100퍼 해결",
              "금새 두통이 사라집니다", "30분 이내에 편두통이 가라앉습니다", "하루만 써도 비염이 사라집니다", "일주일 뒤면 불면이 해결됩니다", "한 시간이면 비염이 가라앉습니다", "5초 만에 두통이 사라집니다")
# (사전형, 조사, 여섯 활용: 지금 -ㄴ다·관형 -는·합쇼 -ㅂ니다·과거 -었다·해요체·가능 -ㄹ 수 있다) — 검증자의 활용 행렬(동사 38 × 6꼴)
CONJUGATIONS = (
    ("줄이다", "을", ("줄인다", "줄이는", "줄입니다", "줄였다", "줄여요", "줄일 수 있다")), ("없애다", "을", ("없앤다", "없애는", "없앱니다", "없앴다", "없애요", "없앨 수 있다")),
    ("풀리다", "이", ("풀린다", "풀리는", "풀립니다", "풀렸다", "풀려요", "풀릴 수 있다")), ("사라지다", "이", ("사라진다", "사라지는", "사라집니다", "사라졌다", "사라져요", "사라질 수 있다")),
    ("없어지다", "이", ("없어진다", "없어지는", "없어집니다", "없어졌다", "없어져요", "없어질 수 있다")), ("가라앉다", "이", ("가라앉는다", "가라앉는", "가라앉습니다", "가라앉았다", "가라앉아요", "가라앉을 수 있다")),
    ("편안해지다", "이", ("편안해진다", "편안해지는", "편안해집니다", "편안해졌다", "편안해져요", "편안해질 수 있다")), ("좋아지다", "이", ("좋아진다", "좋아지는", "좋아집니다", "좋아졌다", "좋아져요", "좋아질 수 있다")),
    ("나아지다", "이", ("나아진다", "나아지는", "나아집니다", "나아졌다", "나아져요", "나아질 수 있다")), ("펴지다", "이", ("펴진다", "펴지는", "펴집니다", "펴졌다", "펴져요", "펴질 수 있다")),
    ("가벼워지다", "이", ("가벼워진다", "가벼워지는", "가벼워집니다", "가벼워졌다", "가벼워져요", "가벼워질 수 있다")), ("빠지다", "이", ("빠진다", "빠지는", "빠집니다", "빠졌다", "빠져요", "빠질 수 있다")),
    ("떨어지다", "이", ("떨어진다", "떨어지는", "떨어집니다", "떨어졌다", "떨어져요", "떨어질 수 있다")), ("날리다", "을", ("날린다", "날리는", "날립니다", "날렸다", "날려요", "날릴 수 있다")),
    ("끝내다", "을", ("끝낸다", "끝내는", "끝냅니다", "끝냈다", "끝내요", "끝낼 수 있다")), ("막다", "을", ("막는다", "막는", "막습니다", "막았다", "막아요", "막을 수 있다")),
    ("잡다", "을", ("잡는다", "잡는", "잡습니다", "잡았다", "잡아요", "잡을 수 있다")), ("낮추다", "을", ("낮춘다", "낮추는", "낮춥니다", "낮췄다", "낮춰요", "낮출 수 있다")),
    ("태우다", "을", ("태운다", "태우는", "태웁니다", "태웠다", "태워요", "태울 수 있다")), ("되찾다", "을", ("되찾는다", "되찾는", "되찾습니다", "되찾았다", "되찾아요", "되찾을 수 있다")),
    ("되돌리다", "을", ("되돌린다", "되돌리는", "되돌립니다", "되돌렸다", "되돌려요", "되돌릴 수 있다")), ("뚫리다", "이", ("뚫린다", "뚫리는", "뚫립니다", "뚫렸다", "뚫려요", "뚫릴 수 있다")),
    ("녹이다", "을", ("녹인다", "녹이는", "녹입니다", "녹였다", "녹여요", "녹일 수 있다")), ("날아가다", "이", ("날아간다", "날아가는", "날아갑니다", "날아갔다", "날아가요", "날아갈 수 있다")),
    ("멎다", "이", ("멎는다", "멎는", "멎습니다", "멎었다", "멎어요", "멎을 수 있다")), ("낫다", "이", ("낫는다", "낫는", "낫습니다", "나았다", "나아요", "나을 수 있다")),
    ("풀어주다", "을", ("풀어 준다", "풀어 주는", "풀어 줍니다", "풀어 줬다", "풀어 줘요", "풀어 줄 수 있다")), ("고치다", "을", ("고친다", "고치는", "고칩니다", "고쳤다", "고쳐요", "고칠 수 있다")),
    ("억제하다", "을", ("억제한다", "억제하는", "억제합니다", "억제했다", "억제해요", "억제할 수 있다")), ("진정시키다", "을", ("진정시킨다", "진정시키는", "진정시킵니다", "진정시켰다", "진정시켜요", "진정시킬 수 있다")),
    ("경감시키다", "을", ("경감시킨다", "경감시키는", "경감시킵니다", "경감시켰다", "경감시켜요", "경감시킬 수 있다")), ("잠재우다", "을", ("잠재운다", "잠재우는", "잠재웁니다", "잠재웠다", "잠재워요", "잠재울 수 있다")),
    ("누그러지다", "이", ("누그러진다", "누그러지는", "누그러집니다", "누그러졌다", "누그러져요", "누그러질 수 있다")), ("잦아들다", "이", ("잦아든다", "잦아드는", "잦아듭니다", "잦아들었다", "잦아들어요", "잦아들 수 있다")),
    ("감소하다", "이", ("감소한다", "감소하는", "감소합니다", "감소했다", "감소해요", "감소할 수 있다")), ("시원해지다", "이", ("시원해진다", "시원해지는", "시원해집니다", "시원해졌다", "시원해져요", "시원해질 수 있다")),
    ("괜찮아지다", "이", ("괜찮아진다", "괜찮아지는", "괜찮아집니다", "괜찮아졌다", "괜찮아져요", "괜찮아질 수 있다")))
# 멈추다는 증상이 주어인 꼴('두통이 즉각 멈춥니다')만 효과 동사로 읽는다('작업을 즉시 멈추는 방법'은 행동) — 그래서 관형·가능 꼴은 일부러 읽지 않는다
CONJUGATIONS_STOP = ("두통이 즉시 멈춘다", "두통이 즉시 멈춥니다", "두통이 즉시 멈췄다", "두통이 즉시 멈춰요")
CONJUGATIONS_STOP_NOT = ("두통이 즉시 멈추는", "두통이 즉시 멈출 수 있다")
# 2차 수정 이전 효과 동사 낱말 134개와 특수 모양: 어간 구조로 바꾸면서 하나도 빠지지 않았음을 못박는다
OLD_EFFECT_FORMS = """줄이 줄여 줄인 줄일 줄임 줄입 줄어 줄었 없애 없앤 없앨 없앱 없앴 없어지 없어진 없어져 없어집 없어졌 사라지 사라진 사라질 사라집 사라져 사라졌 해소 풀리 풀려 풀린 풀릴 풀립 풀렸 풀어 해결 교정 바로잡 치료 완치 나았 나은 나을
완화 개선 회복 예방 감량 제거 막아 막는 막은 막을 막습 잡아 잡는 잡은 잡습 날려 날리 날립 날아 덜어 낮추 낮춰 낮춘 낮출 낮춥 끝내 끝냅 가라앉 멈춥 멈춘다 멈췄 멈추게 멎 뚫리 뚫려 뚫린 뚫립 뚫어 뚫습 편안해지 편안해져 편안해집 편해지 편해져 펴지 펴져 펴집
펴준 정복 차단 녹이 녹여 녹입 녹아 태우 태워 태웁 좋아지 좋아져 좋아집 호전 치유 잊게 잊도록 털어 떨쳐 떨치 몰아내 물리쳐 극복 탈출 퇴치 끝장 개운 가뿐 가벼워지 가벼워집 가벼워져 정상화 떨어지 떨어집 떨어졌 떨어뜨리 떨어트리 되찾 되살 되돌리 되돌려 되돌립
젊어지 젊어져 젊어집 빠지는 빠집 물리치는 재생됩니다 재생합니다 가시어요 가시었 가시네요 가시죠 낫는다 낫습니다 낫게 낫다 낫고 낫기 낫도록 낫아 낫지 나아졌다 멈춰요""".split() + ["펴 주는", "펴주는", "씻어 내는", "씻어내는", "가시는 비밀"]
EFFECT_NOUNS = ("해소", "해결", "교정", "치료", "완치", "완화", "개선", "회복", "예방", "감량", "제거", "호전", "치유", "극복", "퇴치", "감소", "경감", "진정", "억제", "정상화", "차단")
NOUN_ORDER_HELD = ("피로 해소 효과가 즉시 나타납니다", "통증 완화 효과를 바로 느낄 수 있습니다", "피로 회복 즉시 가능", "허리 통증 완화 지금 바로", "두통 해결 당장 가능합니다", "허리 통증 해소 효과 즉시 체감",
                   "스트레스 해소, 지금 바로 가능합니다", "통증 개선 효과를 지금 바로 확인할 수 있습니다", "어깨 결림 해결 효과가 당장 나타납니다", "피로 회복 효과를 즉시 경험하세요", "두통 완화 즉시 가능", "허리 통증 완화 이제 바로", "스트레스 해소 바로도 가능합니다")
NOUN_ORDER_PASS = ("두통 예방 바로 알기", "통증 치료 바로 시작하세요", "스트레스 해소 방법 지금 바로 확인", "수면 장애 치료 바로 알아보기", "허리 통증 개선 효과를 바로 확인하세요", "통증 완화 효과가 즉시 나타나지 않을 수 있습니다",
                   "통증 완화 효과가 즉시 나타나는지 확인하세요", "허리 통증 완화 효과 전혀 없음", "허리 통증 완화에 대해 오랫동안 연구한 결과 지금 바로 가능합니다", "통증 치료 즉시 병원에 가서 상담받기")
NOT_ASSERTED = ("통증이 즉시 가라앉는지 확인하세요", "통증이 즉시 줄었는지 기록해 두세요", "통증이 즉시 가라앉을지 모릅니다", "통증이 즉시 가라앉은지 확인하세요", "통증이 바로 줄어들지 않아도 걱정하지 마세요",
                "통증이 곧 나아지지 않으면 병원에 가세요", "통증을 즉시 줄이지 못하면 병원에 가세요", "통증을 즉시 줄이지 마세요", "통증이 바로 사라지는지는 개인마다 다릅니다", "혈압이 바로 내려가지 않아도 약을 임의로 끊지 마세요",
                "통증을 즉시 줄이지 않으면 안 됩니다", "두통이 즉시 가라앉는지 기록해 두면 진료에 도움이 됩니다")
SYMPTOM_EN_PASS = ("traffic congestion", "network congestion", "port congestion", "the Great Depression", "depression-era", "economic depression", "market depression", "market stress", "financial stress", "credit stress", "supply chain stress",
                   "interest-rate stress", "cash-flow stress", "price stress", "funding stress", "liquidity stress", "systemic stress", "economic stress", "fiscal stress", "bank stress", "banking stress", "stress test", "stress tests",
                   "pain points", "pain point", "index weight", "portfolio weight", "risk weight", "weight of the evidence", "memory bloating", "code bloating", "software bloating", "data bloating", "security posture", "cyber posture",
                   "defense posture", "market anxiety", "inflation anxiety", "economic anxiety", "investor anxiety", "consumer anxiety", "pandemic hangover", "covid hangover", "market hangover", "economic hangover", "cold start",
                   "cold storage", "cold chain", "cold war", "cold call", "cold email", "cold boot")
SYMPTOM_EN_HOLD = ("nasal congestion", "chest congestion", "sinus congestion", "head congestion", "lung congestion", "depression", "stress", "pain", "pains", "back pain", "weight loss", "lose weight", "bloating",
                   "anxiety", "hangover", "hangovers", "posture", "the common cold", "colds", "blood pressure", "headache")


class GateFix3AdjectiveListTest(unittest.TestCase):
    """새 D1: `…하고` 로 이은 형용사 나열('안전하고 부드럽게')은 행동 순서가 아니라 결과를 꾸미는 말이다."""

    def test_an_adjective_list_between_the_adverb_and_the_effect_verb_is_an_effect_claim(self):
        for symptom in ("통증을", "피로를", "두통을", "스트레스를"):
            for adverb in ("즉시", "바로"):
                for adjectives in ADJECTIVE_LISTS:
                    for effect in ("줄여 줍니다", "없애 줍니다", "해소합니다"):
                        sentence = f"{symptom} {adverb} {adjectives} {effect}"
                        self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_a_do_verb_in_the_gap_is_an_action_order_whatever_connective_follows(self):
        for symptom in ("통증을", "피로를"):
            for adverb in ("즉시", "바로"):
                for filler in ACTION_FILLERS:
                    sentence = f"{symptom} {adverb}{filler}줄여 줍니다"
                    self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_every_listed_do_verb_is_an_action_with_every_connective_and_an_adjective_is_not(self):
        self.assertEqual(set(DO_VERB_STEMS), set(qg._DO_VERB_STEMS[3:-1].split("|")))          # 시험 목록과 코드 목록이 같다 — 낱말을 더하면 시험에도 더한다
        for stem in DO_VERB_STEMS:
            for connective in ("하고", "하며", "하면서", "하여", "해서", "하시고", "하시며", "하시면서", "하셔서"):
                with self.subTest(word=stem + connective):
                    self.assertIsNotNone(qg._ACTION_IN_GAP.search(f" {stem}{connective} "))
                    self.assertFalse(qg._ko_gap_modifies_result(f" {stem}{connective} 증상이 "))
        for adjective in ("안전", "편안", "간편", "정확", "깨끗", "건강", "확실", "철저", "신속", "충분", "완벽", "꼼꼼", "분명", "간단", "깔끔", "개운", "유연", "강력"):
            for connective in ("하고", "하며", "하면서", "하여", "해서", "하시고", "하시며", "하시면서", "하셔서"):
                with self.subTest(word=adjective + connective):
                    self.assertIsNone(qg._ACTION_IN_GAP.search(f" {adjective}{connective} "))
                    self.assertTrue(qg._ko_gap_modifies_result(f" {adjective}{connective} "))

    def test_a_bare_do_connective_with_no_word_before_it_is_an_action(self):
        modifies = qg._ko_gap_modifies_result
        for gap in (" 하고 ", " 하며 ", " 하면서 ", " 하여 ", " 그렇게 해서 ", " 해서 ", " 스트레칭을 하고 ", " 하시고 ", " 하시며 ", " 하시면서 ", " 하셔서 ", " 충분히 쉬시고 "):
            with self.subTest(gap=gap):
                self.assertFalse(modifies(gap))
        for gap in (" 안전하고 ", " 편안하여 ", " 간편해서 ", " 깨끗하면서 "):
            with self.subTest(gap=gap):
                self.assertTrue(modifies(gap))

    def test_the_other_connectives_stay_action_markers_whatever_comes_before_them(self):
        modifies = qg._ko_gap_modifies_result
        for gap in (" 마사지한 뒤 ", " 휴식한 후 ", " 확인한 다음 ", " 운동하다가 ", " 도착하자마자 ", " 병원에 가서 ", " 약을 먹으면 "):
            with self.subTest(gap=gap):
                self.assertFalse(modifies(gap))


class GateFix3TimeWordTest(unittest.TestCase):
    """새 D2-(다): 시간 낱말은 낱말 하나씩이 아니라 구조(동작 + 자마자·는 순간, 기간 단위 + 끝말)로 읽는다."""

    def test_time_phrases_that_the_verifier_found_in_the_gaps_are_held(self):
        for sentence in TIME_WORDS:
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)
                self.assertTrue(codes_body(sentence), sentence)
                self.assertTrue(codes_title(sentence), sentence)

    def test_every_period_unit_with_every_ending_is_an_immediate_adverb(self):
        for unit in TIME_UNITS:
            for ending in TIME_ENDINGS:
                sentence = f"{unit} {ending} 두통이 사라집니다"
                with self.subTest(sentence=sentence):
                    self.assertIsNotNone(qg._IMMEDIATE_KO.search(sentence))
                    self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_ordinary_time_talk_without_a_result_is_not_held(self):
        for sentence in ("통증이 있으면 도착하자마자 병원에 가서 치료를 받으세요", "복용 직후 통증이 느껴지면 즉시 병원에 가세요", "약을 먹자마자 두드러기가 생기면 즉시 응급실에 가세요", "주사를 맞는 순간 통증이 느껴지면 말씀해 주세요",
                         "운동 직후 근육통이 있으면 스트레칭을 해 주세요", "수술 직후에는 통증이 느껴질 수 있습니다", "결제 직후 영수증이 발송됩니다", "5초 만에 로그인이 완료됩니다", "누르는 순간 파일이 저장된다", "단 하루에 모든 일정이 확정됐다"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_the_action_before_neun_sunkan_is_part_of_the_time_word_the_hold_reason_shows(self):
        # 보류 사유에 찍히는 시간 낱말은 동작을 붙인 구('붙이는 순간')다 — 한 글자 조각('이는 순간')이 찍히면 사람이 어느 말이 걸렸는지 알아보기 어렵다
        for sentence, phrase in (("붙이는 순간 어깨 결림이 풀립니다", "붙이는 순간"), ("허리 통증이 바르는 순간 사라집니다", "바르는 순간"), ("마시는 순간에 숙취가 가라앉는 차", "마시는 순간에"), ("마시자마자 숙취가 가라앉는 차", "마시자마자")):
            with self.subTest(sentence=sentence):
                self.assertEqual(qg._IMMEDIATE_KO.search(sentence).group(0), phrase)
                self.assertEqual(qg._effect_claim(sentence, "ko")[1], phrase)

    def test_a_lone_gon_is_a_time_word_but_a_word_that_only_starts_with_it_is_not(self):
        self.assertIsNotNone(qg._IMMEDIATE_KO.search("곧 풀립니다"))
        self.assertIsNone(qg._IMMEDIATE_KO.search("곧은 자세를 유지하세요"))
        self.assertIsNone(qg._IMMEDIATE_KO.search("곧게 펴세요"))
        self.assertIsNotNone(qg._IMMEDIATE_KO.search("허리 통증 100퍼 해결"))
        self.assertIsNone(qg._IMMEDIATE_KO.search("100퍼는 아닙니다"))          # 퍼센트는 아래 `100\s*퍼센트` 가 읽는다. 퍼 뒤에 한글이 바로 붙은 말('100퍼는')은 아니다
        self.assertIsNotNone(qg._IMMEDIATE_KO.search("100퍼센트"))


class GateFix3EffectVerbTest(unittest.TestCase):
    """새 D2-(가)·(라): 효과 동사는 어간 × 활용 끝 묶음으로 읽는다(-ㄴ다·-었다·-ㄹ 수 있다·진·였·았·었 꼴)와 동의어."""

    def test_every_form_of_thirty_eight_effect_verbs_is_an_effect_claim(self):
        self.assertEqual(len(CONJUGATIONS), 37)                    # 멈추다는 아래에서 따로 — 합쳐 검증자의 38개
        for name, josa, forms in CONJUGATIONS:
            self.assertEqual(len(forms), 6)
            for form in forms:
                sentence = f"허리 통증{josa} 즉시 {form}"
                with self.subTest(verb=name, form=form):
                    self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_stopping_is_read_only_in_the_forms_where_the_symptom_is_what_stops(self):
        for sentence in CONJUGATIONS_STOP:
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)
        for sentence in CONJUGATIONS_STOP_NOT:
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_no_effect_word_that_was_read_before_is_lost(self):
        for form in OLD_EFFECT_FORMS:
            with self.subTest(form=form):
                self.assertIsNotNone(qg._EFFECT_KO.search("통증이 즉시 " + form), form)

    def test_the_synonyms_the_verifier_listed_are_effect_verbs(self):
        for sentence in ("염증을 바로 억제하는 식품", "두통을 즉각 진정시키는 아로마", "통증을 순식간에 경감시키는 패치", "피로를 단번에 리셋하는 수면법", "무좀균을 확실히 박멸하는 샴푸", "스트레스를 즉시 잠재우는 음악",
                         "두통에서 즉시 벗어나는 법", "통증이 즉시 잦아드는 마사지", "목 통증이 완전히 누그러지는 방법", "눈 피로가 바로 맑아지는 지압", "허리 통증이 즉시 감소합니다", "두통이 즉시 괜찮아집니다",
                         "스트레스에서 즉시 해방되는 법", "불안감을 즉각 안정시키는 호흡법", "통증을 즉시 고치는 방법", "허리를 바로 고쳐 주는 의자", "아침 부기를 바로 빼 주는 마사지", "목 통증을 즉시 누그러뜨리는 방법",
                         "두통이 바로 잦아듭니다", "통증이 즉시 물러갑니다", "피로가 곧 달아납니다", "통증이 즉시 사그라듭니다", "붓기가 즉시 빠져나갑니다", "통증을 즉시 쫓아내는 방법", "통증을 즉시 다스리는 방법", "두통을 즉시 달래는 차",
                         "혈압이 바로 낮아집니다", "혈압이 바로 내려갑니다", "무릎 관절을 바로 젊게 만드는 영양제", "피부가 하루 만에 깨끗해집니다", "관절이 바로 건강해집니다"):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_an_effect_verb_that_is_the_object_of_receiving_treatment_is_still_not_an_effect(self):
        for sentence in ("통증이 있으면 즉시 치료를 받으세요", "통증이 있으면 즉시 완화를 위해 병원에 가세요", "통증은 즉시 안정을 통해 관리하세요"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_plain_symptom_talk_without_an_adverb_is_not_a_claim(self):
        for sentence in ("허리 통증 정보", "통증 관리 앱 사용법", "두통 일지 쓰는 방법"):
            self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)


class GateFix3EffectNounOrderTest(unittest.TestCase):
    """새 D2-(나): 효과 명사가 부사 앞에 오는 어순('통증 해소 효과가 즉시 나타납니다')."""

    def test_an_effect_noun_before_the_adverb_with_a_result_predicate_or_at_the_end_is_a_claim(self):
        for sentence in NOUN_ORDER_HELD:
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)
                self.assertTrue(codes_body(sentence) and codes_title(sentence), sentence)

    def test_every_effect_noun_counts(self):
        for noun in EFFECT_NOUNS:
            sentence = f"허리 통증 {noun} 즉시 가능"
            with self.subTest(noun=noun):
                self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)
        self.assertEqual(qg._effect_claim("허리 통증 해소 효과가 즉시 나타납니다", "ko")[2], "해소")

    def test_guidance_actions_and_hedges_after_the_adverb_are_not_claims(self):
        for sentence in NOUN_ORDER_PASS:
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_each_result_predicate_is_a_claim_and_a_non_result_word_after_the_adverb_is_not(self):
        for predicate in ("가능합니다", "나타납니다", "느낄 수 있습니다", "느껴집니다", "체감됩니다", "경험하세요", "볼 수 있습니다", "누릴 수 있습니다", "얻을 수 있습니다", "발휘합니다", "드러납니다", "보입니다",
                          "실현됩니다", "발생합니다", "작용합니다", "효과가 있습니다", "확인할 수 있습니다", "맛볼 수 있습니다", "만나 보세요", "보장합니다",
                          "누리세요", "얻었습니다", "보이는 방법입니다", "효능이 있습니다"):          # 뒤의 4개는 앞 낱말과 끝만 다른 대안(누리·얻·보이·효능)을 따로 못박는다 — 다른 대안이 같은 문장을 대신 읽지 못하게
            sentence = f"스트레스 해소 효과를 바로 {predicate}"
            with self.subTest(predicate=predicate):
                self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)
        for word in ("알아보세요", "시작하세요", "신청하세요", "읽어 보세요", "비교해 보세요", "찾아보기"):
            sentence = f"스트레스 해소 효과를 바로 {word}"
            with self.subTest(word=word):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_the_effect_noun_must_be_right_before_the_adverb(self):
        self.assertIsNone(qg._effect_claim("두통 해소 방법은 여러 가지이며 바로 가능한 것도 있습니다", "ko"))
        self.assertIsNotNone(qg._effect_claim("두통 해소 즉시 가능한 방법", "ko"))


class GateFix3NotAssertedTest(unittest.TestCase):
    """새 D6: 결과를 묻는 절(…는지)과 부정(…지 않·못·마)은 효과 단정이 아니다."""

    def test_a_clause_that_asks_or_denies_the_effect_is_not_a_claim(self):
        for sentence in NOT_ASSERTED:
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_the_same_words_without_the_asking_or_denying_ending_are_still_claims(self):
        for sentence in ("통증이 즉시 가라앉습니다", "통증이 바로 줄어듭니다", "통증이 곧 나아집니다", "통증을 즉시 줄입니다", "혈압이 바로 내려갑니다", "통증이 즉시 가라앉는 방법", "통증이 즉시 줄어들며 두통이 사라집니다"):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_an_asking_clause_does_not_hide_a_later_claim(self):
        self.assertIsNotNone(qg._effect_claim("통증이 즉시 줄어드는지 확인해 보세요, 두통을 바로 해소합니다", "ko"))
        self.assertIsNotNone(qg._effect_claim("통증이 바로 줄어들지 않아도 걱정 마세요, 이 베개는 두통을 즉시 해소합니다", "ko"))

    def test_every_ending_of_the_asking_or_denying_clause_is_read(self):
        for ending in ("는지", "은지", "을지", "지 않", "지 못", "지 말", "지 마"):
            sentence = f"통증이 즉시 가라앉{ending} 모르겠습니다"
            with self.subTest(ending=ending):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)


class GateFix3SplitTest(unittest.TestCase):
    """새 D4: 소수점·약어·주소의 마침표는 문장 끝이 아니다."""

    def test_a_decimal_point_inside_a_claim_does_not_split_it(self):
        for sentence in ("통증이 99.9% 즉시 사라집니다", "허리 통증이 1.5배 빠르게 즉시 해소됩니다", "이 의자는 통증을 3.5일 만에 완전히 없앱니다", "체중이 0.5kg씩 즉시 줄어듭니다", "통증이 98.5% 즉시 사라집니다", "허리 통증이 2.5배 빠르게 즉시 풀립니다"):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(qg._effect_claim(body_with(sentence), "ko"), sentence)          # 본문 위치(긴 글)
                self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)                    # 제목 위치(짧은 글)
                self.assertTrue(codes_body(sentence), sentence)

    def test_a_real_sentence_end_still_splits_and_a_dot_before_a_letter_or_digit_does_not(self):
        self.assertEqual(qg._HARD_SPLIT.split("통증이 심합니다. 즉시 줄이는 방법"), ["통증이 심합니다", " 즉시 줄이는 방법"])
        self.assertEqual(qg._HARD_SPLIT.split("합계는 3.5입니다. 다음"), ["합계는 3.5입니다", " 다음"])
        self.assertEqual(qg._HARD_SPLIT.split("2026. 다음 해"), ["2026", " 다음 해"])                      # 숫자 뒤 마침표라도 뒤가 공백이면 문장 끝이다
        self.assertEqual(qg._HARD_SPLIT.split("문장.다음 문장"), ["문장", "다음 문장"])                      # 한글이 바로 붙은 마침표는 문장 끝이다
        self.assertEqual(qg._HARD_SPLIT.split("e.g. this, U.S. only"), ["e.g", " this, U.S", " only"])
        self.assertEqual(qg._HARD_SPLIT.split("see example.com now"), ["see example.com now"])
        self.assertEqual(qg._HARD_SPLIT.split("끝。다음\n줄"), ["끝", "다음", "줄"])

    def test_a_title_abbreviation_before_a_name_is_not_a_sentence_end(self):
        for text, parts in (("Dr. Kim said so. Next", ["Dr. Kim said so", " Next"]), ("Mr. Lee and Mrs. Park met Ms. Cho and Prof. Han at St. Mary", ["Mr. Lee and Mrs. Park met Ms. Cho and Prof. Han at St. Mary"])):
            with self.subTest(text=text):
                self.assertEqual(qg._HARD_SPLIT.split(text), parts)
                self.assertEqual(qg._SENTENCE_SPLIT.split(text), parts)

    def test_the_sentence_splitter_also_cuts_at_question_and_exclamation_marks(self):
        self.assertEqual(qg._SENTENCE_SPLIT.split("a. b! c? d。e！f？g\nh 9.9 Dr. Kim"), ["a", " b", " c", " d", "e", "f", "g", "h 9.9 Dr. Kim"])

    def test_the_product_cure_claim_and_the_negated_consultation_see_through_a_decimal_point(self):
        self.assertIsNotNone(qg._PRODUCT_CURE.search("이 영양제는 99.9% 확률로 당뇨를 치료합니다"))
        self.assertIsNone(qg._PRODUCT_CURE.search("이 영양제는 안전합니다. 다른 곳에서 당뇨를 치료합니다"))
        found = codes_body("병원에 가지 않고 통증이 99.9% 즉시 사라집니다")
        self.assertIn("QG4-HEALTH", found)
        holds = qg.rule_health("ko", NEUTRAL_TITLE, qg.prose_of(body_with("병원에 가지 않고 통증이 99.9% 즉시 사라집니다")), PROFILES)
        self.assertTrue(any("상담을 부정하는 문장" in hold.message for hold in holds), [hold.message for hold in holds])
        product = qg.rule_health("ko", NEUTRAL_TITLE, qg.prose_of(body_with("이 영양제는 99.9% 확률로 당뇨를 치료합니다")), PROFILES)
        self.assertTrue(any("이 제품·방법으로 낫게 한다는" in hold.message or hold.code == "QG4-ASSERT" for hold in product))


class GateFix3GapObjectTest(unittest.TestCase):
    """새 D5: 사이의 대상이 몸 낱말이고 뒤에 부사뿐이면 효과 동사의 대상이다."""

    def test_a_body_word_object_followed_only_by_adverbs_belongs_to_the_effect_verb(self):
        modifies = qg._ko_gap_modifies_result
        for gap in (" 몸을 가볍게 ", " 몸 전체를 ", " 온몸을 시원하게 ", " 다리를 아주 가볍게 ", " 눈을 편안하게 ", " 컨디션을 한결 ", " 팔과 다리를 시원하게 "):
            with self.subTest(gap=gap):
                self.assertTrue(modifies(gap))
        self.assertIsNotNone(qg._effect_claim("허리 통증이 즉시 몸을 가볍게 풀어 주는 방석", "ko"))
        self.assertIsNotNone(qg._effect_claim("피로가 바로 온몸을 시원하게 풀어 줍니다", "ko"))
        self.assertIsNotNone(qg._effect_claim("통증이 즉시 몸을 편안하고 가볍게 풀어 줍니다", "ko"))
        self.assertIsNotNone(qg._effect_claim("피로가 바로 온몸을 부드럽고 시원하게 풀어 줍니다", "ko"))
        self.assertIsNone(qg._effect_claim("허리가 아프면 즉시 눈을 감고 천천히 숨을 쉬며 통증이 풀리는지 느껴 보세요", "ko"))
        self.assertIsNotNone(qg._effect_claim("허리 통증이 즉시 팔과 다리를 가볍게 풀어 주는 스트레칭", "ko"))

    def test_every_body_word_is_read_and_ordinary_nouns_are_not(self):
        modifies = qg._ko_gap_modifies_result
        for word in ("몸", "온몸", "전신", "팔", "다리", "목", "눈", "머리", "얼굴", "손", "발", "등", "가슴", "배", "엉덩이", "골반", "허벅지", "종아리", "손목", "발목", "뼈", "혈관", "코", "입", "귀", "치아", "잇몸", "컨디션", "기분", "체력"):
            with self.subTest(word=word):
                self.assertTrue(modifies(f" {word}을 가볍게 "), word)
        for word in ("제목", "목표", "목록", "목적", "작업", "의자 높이", "일상", "사용", "약", "운동 강도", "책상"):
            with self.subTest(word=word):
                self.assertFalse(modifies(f" {word}을 가볍게 "), word)

    def test_a_body_word_followed_by_anything_but_adverbs_is_an_action_order_again(self):
        modifies = qg._ko_gap_modifies_result
        for gap in (" 눈을 감고 증상이 ", " 몸을 가볍게 컨디션을 올리며 ", " 다리를 높이 올려 증상이 ", " 팔을 쭉 펴면 통증이 ", " 몸을 이 베개로 "):
            with self.subTest(gap=gap):
                self.assertFalse(modifies(gap))
        for sentence in ("허리가 아프면 즉시 눈을 감고 피로가 풀리면 천천히 일어나세요", "허리가 아프면 바로 다리를 높이 올리면 통증이 줄어듭니다", "허리가 아프면 즉시 의자 높이를 낮췄더니 통증이 줄었다"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_an_ordinary_object_directly_before_the_effect_verb_keeps_meaning_an_action(self):
        self.assertFalse(qg._ko_gap_modifies_result(" 작업을 "))
        self.assertIsNone(qg._effect_claim("통증이 느껴지면 즉시 작업을 멈춰 주세요", "ko"))
        self.assertIsNone(qg._effect_claim("통증이 있으면 즉시 의자 높이를 낮춰 보세요", "ko"))


class GateFix3AllowedDirectionTest(unittest.TestCase):
    """새 D6·D7·D8: 허용 방향 오탐을 줄인다(보류 쪽 오류) — 줄이면서 미탐이 늘지 않는지도 함께 못박는다."""

    def test_words_that_only_look_like_symptoms_in_korean_are_not_symptoms(self):
        for text in ("한국 경제의 고질병을 근본적으로", "우리 사회의 고질병을 즉시", "근시안적 규제를 즉시", "근시안적 접근을 바로", "해수 탈염 설비가", "디스크 어레이를 바로 교체", "디스크 스토리지를 즉시", "디스크 백업을 바로", "디스크 암호화를 즉시",
                     "복식부기를 즉시", "단식부기가 바로"):
            with self.subTest(text=text):
                self.assertIsNone(qg._SYMPTOM_KO.search(text), text)
        for sentence in ("한국 경제의 고질병을 근본적으로 해결해야 한다는 지적이 나왔다", "해수 탈염 설비가 물 부족을 즉시 해소한다", "근시안적 규제를 즉시 바로잡아야 한다는 목소리가 커졌다", "디스크 어레이를 바로 교체하면 서비스 장애가 해소된다"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)

    def test_the_same_words_are_still_symptoms_in_a_health_sentence(self):
        for text in ("고질병을 즉시", "만성 고질병을 즉시", "허리의 고질병을 즉시", "근시를 즉시", "비염을 즉시", "디스크를 즉시", "디스크 질환을 즉시", "화병을 즉시", "혈액순환을 즉시", "혈액 순환을 즉시", "잇몸을 즉시", "눈 떨림을 즉시", "손 떨림을 즉시",
                     "다리 쥐를 즉시", "종아리 쥐를 즉시", "땀 냄새를 즉시", "아침 부기를 즉시", "부기를 즉시", "염증을 즉시", "위염을 즉시", "역류성 식도염을 즉시"):
            with self.subTest(text=text):
                self.assertIsNotNone(qg._SYMPTOM_KO.search(text), text)
        for text in ("떨림만 즉시", "쥐 한 마리를 즉시", "땀을 즉시", "주름을 즉시", "기미를 즉시"):
            with self.subTest(text=text):
                self.assertIsNone(qg._SYMPTOM_KO.search(text), text)          # 뜻이 여럿인 낱말(떨림·쥐·땀·주름·기미)은 일부러 증상으로 세지 않는다

    def test_a_word_that_contains_yeom_in_the_middle_is_not_an_inflammation(self):
        for word in ("하염없이", "제염소를", "머리염색을", "염색약을", "염려를", "염가에", "염소를", "염분을"):
            with self.subTest(word=word):
                self.assertIsNone(qg._SYMPTOM_KO.search(f"{word} 즉시"), word)
        for word in ("가나염", "다라염을", "비염", "역류성 식도염"):
            with self.subTest(word=word):
                self.assertIsNotNone(qg._SYMPTOM_KO.search(f"{word} 즉시"), word)

    def test_english_words_that_mean_something_else_in_traffic_economy_or_software_are_not_symptoms(self):
        for text in SYMPTOM_EN_PASS:
            with self.subTest(text=text):
                self.assertIsNone(qg._SYMPTOM_EN.search(text), text)
        for text in SYMPTOM_EN_HOLD:
            with self.subTest(text=text):
                self.assertIsNotNone(qg._SYMPTOM_EN.search(text), text)

    def test_english_sentences_about_traffic_markets_and_software_are_not_claims_but_health_ones_are(self):
        for sentence in ("The new toll will immediately reduce traffic congestion downtown.", "The update eliminates network congestion immediately.", "Port congestion ended overnight as the strike was settled.",
                         "The policy permanently ended the depression-era subsidy.", "The firm immediately beat the stress test thresholds.", "Market stress eased immediately after the announcement.", "The index weight dropped immediately after the rebalance.",
                         "The tool instantly removes pain points from the onboarding flow.", "Supply chain stress ended overnight.", "Inflation anxiety vanished overnight, analysts said.", "The pandemic hangover is gone for good in the housing market.",
                         "The fix immediately stops the memory bloating.", "Cold storage costs dropped instantly after the new contract.", "Security posture improved within a week."):
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "en"), sentence)
        for sentence in ("Relieve nasal congestion in seconds", "Instant relief from chest congestion", "This tea cures a hangover instantly", "Beat depression forever with this supplement", "Stress gone in 5 minutes", "Lose weight overnight",
                         "Pain disappears within a week", "Relieve stress instantly", "Cure your cold overnight", "Alleviate back pain instantly with this stretch", "Reverse hair loss in 30 days", "Instantly soothe sore muscles"):
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(qg._effect_claim(sentence, "en"), sentence)

    def test_an_acronym_before_a_title_is_an_organisation_not_a_person(self):
        for text in ("IMF 총재는 성장률 전망을 낮췄다고 밝혔다.", "WHO 사무총장은 새 지침을 발표했다.", "UN 사무총장은 휴전을 촉구했다.", "SEC 위원장은 규제 계획을 밝혔다.", "ECB 총재는 금리 인하를 시사했다.", "MIT 교수는 새 소재를 소개했다.", "NASA 국장은 말했다."):
            with self.subTest(text=text):
                self.assertEqual(qg._titled_people(text)[0], [], text)
                self.assertEqual([hold.code for hold in qg.rule_quotes("ko", qg.prose_of(text), "The agency published a table. No official was named.")], [], text)
        self.assertEqual(qg._titled_people("Powell 의장은 금리를 동결했다.")[0], ["Powell"])
        self.assertEqual(qg._titled_people("Elon Musk CEO announced it.")[0], ["Elon Musk"])
        self.assertEqual(qg._titled_people("Kim Jong UN 위원장은 말했다.")[0], ["Kim Jong UN"])          # 이름의 일부가 대문자인 것은 약어가 아니다
        for name, expected in (("IMF", True), ("WHO", True), ("NASA", True), ("ABCDE", True), ("U N", False), ("OpenAI", False), ("Powell", False), ("Elon Musk", False), ("A", False), ("ABCDEF", False), ("IMF WHO", True), ("", False)):
            with self.subTest(name=name):
                self.assertEqual(qg._is_acronym_name(name), expected)


class GateFix3HiddenTextTest(unittest.TestCase):
    """새 D9: 숨은 글(이미지 대체글·HTML 속성·마크다운 링크 제목)을 숫자·인용·이름 규칙도 읽는다."""

    def gate(self, **kw):
        return h.run_gate(data=h.make_data(ko=h.ko_body(**kw)), config=h.make_config(("ko",))).codes()

    def test_an_invented_number_in_an_image_description_an_attribute_or_a_link_title_is_held(self):
        self.assertIn("QG1-NUMBER", self.gate(extra="![신청은 9,999건이었다](x.png)"))
        self.assertIn("QG1-NUMBER", self.gate(extra='<span title="신청은 7,777명이었다">설명</span>'))
        self.assertIn("QG1-NUMBER", self.gate(extra='<img alt="신청은 8,888곳이었다" src="x.png">'))
        self.assertIn("QG1-NUMBER", self.gate(extra='<a aria-label="신청은 5,555명이었다">설명</a>'))
        self.assertIn("QG1-NUMBER", self.gate(extra='[자세히](a.html "신청은 6,666건이었다")'))
        self.assertIn("QG1-NUMBER", self.gate(extra="[자세히](a.html '신청은 4,444명이었다')"))
        self.assertIn("QG1-NUMBER", self.gate(extra='![그림](x.png "신청은 3,333곳이었다")'))

    def test_an_invented_quote_or_person_in_the_hidden_text_is_held(self):
        quote = "“이 문장은 근거 텍스트에 전혀 없는 아주 긴 인용 문장이며 사십 자를 넘깁니다”라고 말했다"
        self.assertIn("QG2-QUOTE", self.gate(extra=f"![{quote}](x.png)"))
        self.assertIn("QG2-PERSON", self.gate(extra="![김철수 위원장은 그렇게 설명했다](x.png)"))

    def test_numbers_in_the_source_list_link_titles_and_an_ordinary_image_are_still_not_read(self):
        self.assertNotIn("QG1-NUMBER", self.gate(source_list="### 출처\n- [2019년 9,999건 보고서](" + h.LINK + ")"))
        self.assertEqual([code for code in self.gate(extra="![예시 그림](y.png)") if code.startswith(("QG1", "QG2"))], [])
        self.assertEqual([code for code in self.gate() if code.startswith(("QG1", "QG2"))], [])

    def test_a_number_in_a_hidden_text_that_the_source_supports_is_not_held(self):
        self.assertEqual([code for code in self.gate(extra="![중위 소득 3.4% 증가](x.png)") if code.startswith("QG1")], [])

    def test_the_hidden_claim_text_has_the_pieces_but_no_link_text_and_is_folded(self):
        text = '![그림 설명](x.png) <span title="속성 글">a</span> [링크 글자](a.html "링크 제목") [그냥 링크](b.html) <img alt=\'다른 속성\' src="u">'
        found = qg.hidden_claim_text(text)
        for piece in ("그림 설명", "속성 글", "링크 제목", "다른 속성"):
            self.assertIn(piece, found)
        self.assertNotIn("링크 글자", found)
        self.assertNotIn("그냥 링크", found)
        self.assertEqual(found.count("\n\n"), found.count("\n") // 2)                     # 조각은 빈 줄로 잇는다(따옴표가 조각을 건너 짝지어지지 않게)
        self.assertEqual(qg.hidden_claim_text("![２０２６년](x.png)"), "2026년")           # 본문과 같은 정규화(NFKC)
        self.assertEqual(qg.hidden_claim_text("![매출" + ZWSP + "액](x.png)"), "매출액")          # 보이지 않는 서식 문자 제거
        self.assertEqual(qg.hidden_claim_text(None), "")
        self.assertEqual(qg.hidden_claim_text("평범한 글"), "")
        self.assertIn("링크 글자", qg.hidden_health_text(text))                            # 건강 규칙은 링크 글자도 읽는다
        self.assertIn("링크 제목", qg.hidden_health_text(text))
        self.assertEqual(qg.hidden_health_text("![２０２６](x.png)"), "2026")

    def test_the_hidden_pieces_are_joined_by_exactly_one_blank_line(self):
        """독립 검증 새 D6(MN17): 위 시험의 '빈 줄 수' 단언은 줄바꿈이 하나도 없어도 0 == 0 으로 통과했다 — 조각을 잇는 글자를 정확한 값으로 못박는다."""
        text = '![그림 설명](x.png) <span title="속성 글">a</span> [링크 글자](a.html "링크 제목") [그냥 링크](b.html) <img alt=\'다른 속성\' src="u">'
        self.assertEqual(qg.hidden_claim_text(text), "그림 설명\n\n속성 글\n\n다른 속성\n\n링크 제목")

    def test_a_quote_mark_in_one_hidden_piece_does_not_pair_with_one_in_the_next(self):
        """독립 검증 새 D6(MN17): 조각을 한 칸으로 이으면 앞 조각의 여는 따옴표와 뒤 조각의 닫는 따옴표가 한 인용으로 짝지어진다 — 빈 줄로 이어 짝지어지지 않는다."""
        extra = '![그는 "우리는 이번 일을 절대로 되돌리지 않을 것이며 끝까지 책임을 지겠다](x.png) 중간 글 ![약속했다" 라고 말했다](y.png)'
        self.assertEqual([code for code in self.gate(extra=extra) if code.startswith("QG2")], [])

    def test_the_markdown_title_pattern_is_not_quadratic_on_long_whitespace(self):
        """독립 검증 새 D2: `](` 뒤에 공백이 수만 자 이어지면 `\\s*` 와 `\\s+` 가 서로 공백을 나눠 가지며 제곱 시간이 됐다(29,000자에서 7.5초, check_candidate 15–22초) — 주소 자리를 1자 이상으로 해 선형으로 끝난다."""
        for filler in (" ", "\n", "\t"):
            text = "본문 끝 ](" + filler * 28000
            started = time.perf_counter()
            qg.hidden_claim_text(text)
            qg.hidden_health_text(text)
            self.assertLess(time.perf_counter() - started, 2.0, repr(filler))                 # 넉넉한 상한(느린 러너에서도 흔들리지 않게) — 고치기 전에는 이 상한을 몇 배 넘겼다
        self.assertEqual(qg.hidden_claim_text('[a](b.html "제목 글")'), "제목 글")             # 정상 링크 제목은 그대로 읽는다
        self.assertEqual(qg.hidden_claim_text('[a]( "빈 주소")'), "")                          # 빈 주소는 링크가 아니다(예전에는 읽었다 — 바뀐 한 모양)

    def test_an_efficacy_claim_in_a_markdown_link_title_is_held_by_the_health_rule(self):
        self.assertTrue({"QG4-ASSERT", "QG4-HEALTH", "QG4-CLAIM"} & set(self.gate(extra='[자세히](a.html "이 약은 당뇨를 완치합니다")')))
        self.assertIn("QG4-CLAIM", self.gate(extra='[자세히](a.html "허리 통증을 즉시 없애 줍니다")'))


class GateFix3TitleFoldTest(unittest.TestCase):
    """새 D11: 제목도 본문과 같은 정규화(NFKC·보이지 않는 서식 문자 제거)를 거친다."""

    def test_a_decomposed_or_zero_width_title_is_read_like_a_plain_one(self):
        plain_title = "통증을 즉시 줄이는 방법"
        for variant in (unicodedata.normalize("NFD", plain_title), "통증을 즉" + ZWSP + "시 줄이는 방법", "통증을 즉시" + SHY + " 줄이는 방법", "통증을 즉시" + WJ + " 줄이는 방법",
                        IDEO_SPACE.join(("통증을", "즉시", "줄이는", "방법")), "통증을 즉시 줄이는 방법"):
            with self.subTest(title=variant):
                self.assertTrue(codes_title(variant), variant)
                self.assertIn("QG4-CLAIM", codes_title(variant))

    def test_the_whole_flow_reads_the_folded_title(self):
        title = unicodedata.normalize("NFD", "통증을 즉시 줄이는 방법")
        found = h.run_gate(data=h.make_data(ko_title=title), config=h.make_config(("ko",))).codes()
        self.assertIn("QG4-CLAIM", found)
        found = h.run_gate(data=h.make_data(ko_title="통증을 즉" + ZWSP + "시 줄이는 방법"), config=h.make_config(("ko",))).codes()
        self.assertIn("QG4-CLAIM", found)

    def test_the_event_rule_reads_the_folded_title_too(self):
        body = h.ko_body(extra="개최 일정")                       # 본문에 행사 낱말 둘 — 제목의 행사 낱말(신호 3개)이 더해져야 보류선에 닿는다
        plain_title = "컨퍼런스 개최 안내"
        for variant in (plain_title, unicodedata.normalize("NFD", plain_title), "컨퍼런" + ZWSP + "스 개최 안내"):
            with self.subTest(title=variant):
                found = h.run_gate(data=h.make_data(ko=body, ko_title=variant), config=h.make_config(("ko",))).codes()
                self.assertIn("QG5-EVENT", found)
        self.assertNotIn("QG5-EVENT", h.run_gate(data=h.make_data(ko=body, ko_title="평범한 제목입니다"), config=h.make_config(("ko",))).codes())


GUARD_SAMPLES = {"않": "않았다고", "없다": "없다고", "없습니다": "없습니다라고", "아니": "아니라고", "못\\s": "못 했다고", "못합": "못합니다라고", "입증되지": "입증되지는", "증명되지": "증명되지는", "확인되지": "확인되지는",
                 "근거": "근거를 제시했다고", "과학적": "과학적으로 말했다고", "주장": "주장이라고", "광고": "광고라고", "허위": "허위라고", "과장": "과장이라고", "주의": "주의하라고", "믿지": "믿지는", "사실이": "사실이라고"}


class GateFix3BoundaryAndConstantTest(unittest.TestCase):
    """새 D13: 검증자의 변이 N01·N02·N03·N06·N09·N16·N21 이 살아남던 경계·상수·규칙 삭제를 못박는다."""

    def test_a_title_of_exactly_one_hundred_twenty_chars_is_one_unit_but_one_char_more_is_not(self):
        claim = "허리 통증. 즉시 줄이는 방법"
        for pad_len, expected in ((qg.CLAIM_SHORT_CHARS - len(claim), True), (qg.CLAIM_SHORT_CHARS - len(claim) + 1, False)):
            text = "가" * pad_len + claim
            with self.subTest(length=len(text)):
                self.assertEqual(len(text), qg.CLAIM_SHORT_CHARS if expected else qg.CLAIM_SHORT_CHARS + 1)
                self.assertEqual(qg._effect_claim(text, "ko") is not None, expected)          # 120자 이하는 마침표가 있어도 통째로 한 조각, 121자는 마침표에서 가른다(N01)
                self.assertEqual(len(list(qg._claim_units(text))), 1 if expected else 2)

    def test_a_sentence_of_exactly_one_hundred_twenty_chars_is_one_unit_but_one_char_more_is_cut_into_clauses(self):
        claim = "통증, 이것, 즉시 줄이는 방법"                       # 세 절에 걸친 단정: 문장째 보아야 보인다
        for pad_len, expected in ((qg.CLAIM_SHORT_CHARS - len(claim), True), (qg.CLAIM_SHORT_CHARS - len(claim) + 1, False)):
            sentence = "가" * pad_len + claim
            text = sentence + "\n" + "나" * 30
            with self.subTest(length=len(sentence)):
                self.assertEqual(len(sentence), qg.CLAIM_SHORT_CHARS if expected else qg.CLAIM_SHORT_CHARS + 1)
                self.assertEqual(qg._effect_claim(text, "ko") is not None, expected)          # 문장 120자 이하는 한 조각, 넘으면 절 하나씩과 이웃한 두 절(N02)
                self.assertEqual(sentence in list(qg._claim_units(text)), expected)

    def test_a_question_of_exactly_forty_chars_is_joined_to_its_answer_but_forty_one_is_not(self):
        answer = "나" * 70 + " 즉시 줄이는 방법 " + "다" * 50
        for question_len, joined in ((qg.CLAIM_QUESTION_CHARS, True), (qg.CLAIM_QUESTION_CHARS + 1, False)):
            question = "통증" + "가" * (question_len - 2)
            self.assertEqual(len(question), question_len)
            text = f"{question}? {answer}"
            with self.subTest(question_len=question_len):
                self.assertEqual(qg._effect_claim(text, "ko") is not None, joined)               # 질문이 40자 이하일 때만 답과 잇는다(N03)
                self.assertEqual((question + " " + answer) in list(qg._claim_units(text)), joined)

    def test_a_full_width_question_mark_joins_only_a_short_question_like_the_ascii_one(self):
        answer = "나" * 130
        short_question, long_question = "요즘 피곤하신가요", "가" * (qg.CLAIM_QUESTION_CHARS + 10)
        self.assertIn(short_question + " " + answer, list(qg._claim_units(f"{short_question}？ {answer}")))
        self.assertNotIn(long_question + " " + answer, list(qg._claim_units(f"{long_question}？ {answer}")))          # 전각 물음표도 긴 질문 뒤에서는 경계다(N21)
        self.assertEqual(list(qg._claim_units(f"{long_question}？ {answer}")), [long_question, answer])

    def test_the_classical_imperative_ending_also_urges_an_action(self):
        for sentence in ("허리가 아프면 지금 바로 자세를 교정하라", "통증이 있으면 당장 교정하라", "스트레스를 즉시 해소하라", "두통이 있으면 즉시 완화하라"):
            with self.subTest(sentence=sentence):
                self.assertIsNone(qg._effect_claim(sentence, "ko"), sentence)          # 시간 부사 + 명령형(N06)
        self.assertIsNotNone(qg._effect_claim("탈모가 걱정이라면 이 샴푸로 완전히 해결하라", "ko"))           # 단정 부사는 명령형이어도 단정이다

    def test_every_product_claim_exception_word_clears_the_sentence_on_its_own(self):
        for guard, sample in GUARD_SAMPLES.items():
            sentence = f"이 영양제가 당뇨를 치료한다는 말을 {sample}"
            with self.subTest(guard=guard):
                self.assertIsNotNone(qg._PRODUCT_CURE.search(sentence), sentence)
                self.assertIsNotNone(qg._CURE_GUARD.search(sentence), sentence)
                self.assertNotIn("QG4-CLAIM", codes_body(sentence), sentence)          # 한 낱말씩 따로 못박는다 — 다른 낱말이 같은 문장을 가리지 않게(N16)
        self.assertIn("QG4-CLAIM", codes_body("이 영양제가 당뇨를 치료한다는 말을 합니다"))
        self.assertEqual(set(GUARD_SAMPLES), set(qg._CURE_GUARD.pattern.split("|")))


# --- 낱말 목록·활용 묶음의 대안 하나하나를 못박는 표: 코드의 상수와 따로 시험에 적어 두므로 코드에서 대안 하나만 지워도 빨강이 된다 ------------------------------------------------
EFFECT_ENDS = {"이": "이여였인일임입", "지": "지져졌진질짐집", "치": "치쳐쳤친칠침칩", "키": "키켜켰킨킬킴킵", "우": "우워웠운울움웁", "내": "내냈낸낼냄냅", "추": "추춰췄춘출춤춥", "리": "리려렸린릴림립", "애": "애앴앤앨앰앱"}
EFFECT_ROOTS = {
    "이": ("줄", "녹"),
    "지": ("사라", "없어", "편안해", "편해", "펴", "좋아", "가벼워", "젊어", "시원해", "상쾌해", "산뜻해", "맑아", "말끔해", "깨끗해", "건강해", "튼튼해", "탱탱해", "부드러워", "밝아", "괜찮아", "누그러", "낮아", "떨어"),
    "치": ("고", "떨", "물리"), "키": ("진정시", "안정시"), "우": ("태", "잠재"), "내": ("끝", "몰아"), "추": ("낮",), "리": ("날", "되돌", "풀", "뚫", "떨어뜨", "떨어트"), "애": ("없",)}
EFFECT_SURFACES = (
    # 낱말 목록(활용형이 어간 묶음으로 만들어지지 않는 것)
    "줄어든다", "줄었다", "풀어 준다", "풀었다", "푸는 방법", "풉니다", "뚫어 준다", "뚫었다", "뚫습니다", "녹아내린다", "날아간다", "덜어 준다", "덜었다", "털어낸다", "털었다", "터는 방법", "막아 준다", "막았다", "막는다", "막은",
    "막을 수 있다", "막습니다", "막게 해 줍니다", "막도록 돕습니다", "잡아 준다", "잡았다", "잡는다", "잡은", "잡을 수 있다", "잡습니다",
    "해소", "해결", "교정", "바로잡는다", "치료한다", "완치된다", "완화한다", "개선한다", "회복한다", "예방한다", "감량한다", "제거한다", "호전된다", "치유한다", "정복한다", "차단한다", "극복한다", "탈출한다", "퇴치한다", "끝장낸다",
    "개운하다", "가뿐하다", "정상화된다", "억제한다", "경감한다", "감소한다", "리셋한다", "박멸한다", "해방된다", "벗어난다",
    "낫는다", "낫습니다", "낫게 한다", "낫다", "낫고", "낫기", "낫도록", "낫아", "낫지", "나았다", "나아졌다", "나은", "나을 수 있다", "가라앉는다", "잦아드는", "잦아들어", "잦아든다", "잦아듭니다", "누그러뜨린다", "누그러트린다",
    "멈춥니다", "멈춘다", "멈췄다", "멈춰요", "멈추게 한다", "멎는다",
    "펴 주는", "펴주는", "펴준다", "씻어 내는", "씻어내는", "잊게 해 주는", "잊도록 돕는", "되찾는다", "되살린다", "떨어뜨린다", "떨어트린다", "재생된다", "재생한다", "빠지는", "빠집니다", "빠진다", "빠졌다", "빠져요", "빠질 수 있다",
    "내려간다", "내려가는", "내려갑니다", "내려갔다", "내려갈 수 있다", "빼 주는", "빼 줍니다", "빼줘요", "빼 드려요", "빼 드립니다", "젊게 만든다", "젊게 만들어", "젊게 만듭니다",
    "물러간다", "물러가는", "물러갑니다", "물러갔다", "물러갈 수 있다", "달아나는", "달아난다", "달아납니다", "달아났다", "달아날 수 있다", "사그라드는", "사그라들어", "사그라든다", "사그라듭니다", "사그라지는", "사그라진다", "사그라졌다",
    "사그라져요", "빠져나간다", "쫓아낸다", "다스리는", "다스려요", "다스렸다", "다스린다", "다스릴 수 있다", "다스림", "다스립니다", "달래 준다", "달랜다", "달랠 수 있다", "달랬다",
    "가시는 비밀", "가시어요", "가시어집니다", "가시었", "가시네요", "가시죠", "진정되는", "진정돼요", "진정됩니다", "진정된", "안정되는", "안정돼요", "안정됩니다", "안정된",
    # 한 낱말 안에서 끝 글자만 다른 대안들(벗어나다·젊게 만들다·재생하다·가시다): 대안마다 하나씩
    "벗어나는", "벗어날 수 있다", "벗어납니다", "벗어났다", "젊게 만드는", "해방한다", "해방해 준다",
    "재생시키는", "재생하는", "재생해요", "재생할 수 있다", "재생함", "재생합니다", "재생되는", "재생됩니다", "재생될 수 있다", "재생됨", "재생됐다", "재생돼요",
    "가시는 비결", "가시는 비법", "가시는 효과", "가시는 마법", "가시는 차", "가시는 음료", "가시는 습관")
RIDDANCE_SURFACES = ("해방되는", "해방돼요", "해방됩니다", "해방된", "해방시키는", "해방시켜", "해방시킵니다", "해방시킨")
GAP_ADVERBS = ("아주", "매우", "훨씬", "한결", "정말", "너무", "더욱", "더", "좀", "잘", "참", "꽤", "그리고", "또한", "모두", "거의", "가볍게", "깨끗히", "깨끗이", "빨리", "시원하게",
               "편안하고", "깨끗하며", "정확하여", "간편해서", "부드럽고", "자유롭고")          # 형용사 나열도 몸 낱말 대상 뒤에서는 부사처럼 본다


class GateFix3EveryAlternativeTest(unittest.TestCase):
    """코드의 어간·활용 끝·낱말 목록에서 대안 하나만 지워도 알아채도록, 대안마다 문장 하나를 시험에 적어 둔다."""

    def test_every_root_with_every_ending_of_its_group_is_an_effect_verb(self):
        for group, roots in EFFECT_ROOTS.items():
            for root in roots:
                for end in EFFECT_ENDS[group]:
                    if root == "물리" and end == "치":
                        surface = "물리치는"                       # '물리치료'(치료를 뜻하는 낱말)는 효과 동사가 아니라 아래에서 따로 본다
                    else:
                        surface = root + end
                    with self.subTest(surface=surface):
                        self.assertIsNotNone(qg._effect_claim("통증을 즉시 " + surface, "ko"), surface)
        self.assertIsNone(qg._effect_claim("통증이 있으면 즉시 물리치료를 받으세요", "ko"))

    def test_every_listed_effect_surface_is_read(self):
        self.assertEqual(len(EFFECT_SURFACES), len(set(EFFECT_SURFACES)))
        for surface in EFFECT_SURFACES:
            with self.subTest(surface=surface):
                self.assertIsNotNone(qg._effect_claim("통증을 즉시 " + surface, "ko"), surface)

    def test_every_freedom_surface_is_a_claim_even_without_an_adverb(self):
        for surface in RIDDANCE_SURFACES:
            sentence = "누구나 두통에서 " + surface
            with self.subTest(sentence=sentence):
                self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)
        for surface in ("즉효", "즉효성", "즉효약"):
            self.assertIsNotNone(qg._effect_claim("두통 " + surface, "ko"), surface)
        self.assertIsNone(qg._effect_claim("노예 해방 기념일", "ko"))                # 증상이 없으면 읽지 않는다
        self.assertIsNone(qg._effect_claim("통증 해방 일지 쓰기", "ko"))              # 해방 뒤에 되다·시키다 꼴이 아니다

    def test_the_effect_noun_before_the_adverb_takes_every_particle_mark_lead_word_and_efficacy_word(self):
        for particle in "이가을를은는도":
            for sentence in (f"허리 통증 해소{particle} 즉시 가능", f"허리 통증 해소 효과{particle} 즉시 가능", f"허리 통증 해소 효능{particle} 즉시 가능"):
                with self.subTest(sentence=sentence):
                    self.assertIsNotNone(qg._effect_claim(sentence, "ko"), sentence)
        for mark in (",", "，", "·"):
            self.assertIsNotNone(qg._effect_claim(f"허리 통증 해소{mark} 즉시 가능", "ko"), mark)
        for lead in ("지금", "이제", "오늘"):
            self.assertIsNotNone(qg._effect_claim(f"허리 통증 완화 {lead} 바로", "ko"), lead)

    def test_every_gap_adverb_lets_a_body_word_object_belong_to_the_effect_verb(self):
        for adverb in GAP_ADVERBS:
            with self.subTest(adverb=adverb):
                self.assertTrue(qg._ko_gap_modifies_result(f" 몸을 {adverb} "), adverb)
        for word in ("올리며", "펴면", "감고", "이", "베개로", "컨디션을"):
            with self.subTest(word=word):
                self.assertFalse(qg._ko_gap_modifies_result(f" 몸을 {word} "), word)

    def test_a_later_negation_in_another_clause_does_not_hide_a_claim(self):
        self.assertIsNotNone(qg._effect_claim("통증을 즉시 줄입니다, 그렇지 않은 분도 있습니다", "ko"))          # 부정은 효과 동사 바로 뒤에서만 본다
        self.assertIsNotNone(qg._effect_claim("통증을 즉시 줄입니다, 효과가 없는지 묻지 마세요", "ko"))

    def test_the_symptom_words_that_are_only_symptoms_with_a_body_word_in_front(self):
        for text in ("근육 떨림을 즉시", "입술 떨림을 즉시", "다리 떨림을 즉시", "눈 떨림을 즉시", "손 떨림을 즉시", "다리 쥐를 즉시", "종아리 쥐를 즉시"):
            with self.subTest(text=text):
                self.assertIsNotNone(qg._SYMPTOM_KO.search(text), text)
        for text in ("마음 떨림을 즉시", "목소리 떨림을 즉시", "손쥐를 즉시"):
            with self.subTest(text=text):
                self.assertIsNone(qg._SYMPTOM_KO.search(text), text)


if __name__ == "__main__":
    unittest.main()
