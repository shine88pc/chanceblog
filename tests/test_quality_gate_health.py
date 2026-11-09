"""독립 재검증(2026-11-09, 2차)이 찾은 건강 C(증상 + 즉각 효과 = QG4-CLAIM) 미탐 구조 다섯과 그 둘레의 회귀 시험.
 D1-1 절 경계(쉼표·느낌표·물음표) · D1-2 간격 글자 수 → 구조 규칙(행동 서술어·다른 대상이 끼면 행동 순서, 명사구·부사만 끼면 결과 수식) · D1-3 증상·질환 어휘(낱말 + 접미 규칙)
 · D1-4 긴 절(겹치는 창) · D1-5 효과 동사·활용·영문 · 상담 문구가 든 효능 주장 · D4 한 낱말 외국 인명 + 직함 · D5 이미지 대체글·HTML 속성·링크 글자 · D6 포트·계정이 다른 주소.
운영자 승인 표본(운영자 C 9·변형 15·영문 5·상담 문구·행동 순서 대조)과 검증자의 새 문장 105개·증상·질환 낱말 91개를 큰 목록으로 못박는다. 문장은 모두 지어낸 것이다."""
import time
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


if __name__ == "__main__":
    unittest.main()
