"""주제 범주 허용 목록 — 이 경로가 글로 쓰는 지표를 **허용 목록**으로 정한다. 표준 라이브러리와 이 경로의 새 모듈(`pipeline/facts.py`)만 쓰고, 입출력·시계·난수 없음.

왜 허용 목록인가(독립 검증 V-02): 예전에는 키의 주제 접두사만 보고 건강·금융 범주를 막았다. 키를 `population.patients` 로 두고 라벨을 `당뇨병 환자 수`·`주식 지수`·`지금 사야 할 지수` 로 하면
라벨이 우회로가 됐고, 금지어는 부분 문자열이라 `무 조건`·`효 능` 처럼 띄어 쓰면 우회됐다. 차단 목록은 늘 하나가 모자란다 — 그래서 뒤집었다:
- **범주(Domain)** 마다 키 낱말·라벨 낱말·단위를 명시한다. Fact 의 키·라벨·단위·지역 낱말이 그 범주의 허용 목록에 **모두** 있을 때만 글이 된다.
  모르는 범주·낱말은 `UNKNOWN_TOPIC`(글을 만들지 않는다). 새 지표를 켜려면 실제 어댑터를 켜기 전에 이 표에 낱말을 올리고 시험한다(`docs/FACT_PATH.md` 어댑터 체크리스트).
- 보조로 차단 낱말(건강·금융·법률·과장·단정)을 **공백·중점·하이픈·문장 부호를 지운 글**에서도 찾는다(`compact`). 모든 칸(키·라벨·단위·지역·영문 라벨·Provider 이름)에 적용한다.
  차단 낱말이 있으면 허용 목록보다 먼저 `TOPIC_NOT_ALLOWED` 다. 낱말을 가로질러 찾을 때는 **낱말의 첫머리에서 시작하는 것만** 본다 — `무 조건`·`효 능` 은 잡고,
  `최고 소비` 의 `고소`·`판매 수` 의 `매수` 처럼 낱말 경계를 가로질러 우연히 생긴 글자는 잡지 않는다(과탐 방지, D-133).

설명: docs/FACT_PATH.md
"""
import re
import unicodedata
from dataclasses import dataclass

from pipeline import facts as F


@dataclass(frozen=True)
class Domain:
    """범주 하나. domain_id 는 키의 주제 접두사(`labour.unemployment_rate` 의 `labour`)다. category 는 생성기의 한국어 글 분류 이름."""
    domain_id: str
    name_ko: str
    category: str
    key_words: frozenset
    label_words: frozenset
    units: frozenset


@dataclass(frozen=True)
class Vocabulary:
    """허용 목록 전체: 범주들과 모든 범주가 같이 쓰는 지역 낱말(전체 이름 하나가 한 낱말) 및 지역 이름 모양(시험용 가상 지역)."""
    domains: dict
    regions: frozenset
    region_patterns: tuple


def _w(text):
    return frozenset(text.split())


# 모든 범주가 쓰는 구조 낱말(라벨을 이루는 말)
_COMMON_LABEL = "수 율 률 비율 평균 전체 합계 총 증감 증가율 감소율 지수 남성 여성 전년 대비 당 최고 최저 누적"

DOMAINS = {d.domain_id: d for d in (
    Domain("labour", "노동·고용", "경제·일",
           _w("labour unemployment employment employed unemployed persons rate participation force wage wages hours total workers jobs"),
           _w(_COMMON_LABEL + " 실업률 고용률 취업자 실업자 경제활동인구 경제활동참가율 참가율 임금 근로자 근로시간 시간당 월평균 청년 비정규직 일자리 구인 구직 상용 임시 일용 인구"),
           _w("% 명 천명 만명 시간 원")),
    Domain("economy", "경제", "경제·일",
           _w("economy gdp growth rate export exports import imports trade balance production industrial retail sales index total"),
           _w(_COMMON_LABEL + " 경제 성장률 경제성장률 국내총생산 생산 소비 수출 수입 무역 수지 무역수지 산업 산업생산 소매 판매 소매판매 경기 동행 선행 종합 금액 액"),
           _w("% 원 억원 조원 달러 억달러 유로 엔 점")),
    Domain("price", "물가", "경제·일",
           _w("price prices consumer producer index inflation rate average fuel"),
           _w(_COMMON_LABEL + " 물가 소비자물가 생산자물가 물가지수 상승률 가격 평균가격 요금 휘발유 경유 등유 쌀 달걀 소비자 생산자"),
           _w("% 원 점 달러 유로")),
    Domain("population", "인구", "사회·정책",
           _w("population total households household births birth density age median average male female foreign"),
           _w(_COMMON_LABEL + " 인구 총인구 가구 세대 출생아 합계출산율 출산율 고령 노인 청소년 연령 평균연령 인구밀도 밀도 이동 전입 전출 외국인"),
           _w("명 천명 만명 % 가구 세")),
    Domain("education", "교육", "사회·정책",
           _w("education students student schools school teachers teacher classes enrollment rate total"),
           _w(_COMMON_LABEL + " 학생 학교 학급 교원 교사 초등학교 중학교 고등학교 대학 대학교 대학원 진학률 취학률 졸업 입학 학급당 학생수"),
           _w("명 % 개 곳 학급")),
    Domain("environment", "환경·기상", "과학·환경",
           _w("environment temperature precipitation humidity wind speed fine dust particulate ozone concentration sea level rainfall snow pressure sunshine average max min"),
           _w(_COMMON_LABEL + " 기온 평균기온 최고기온 최저기온 강수량 습도 풍속 미세먼지 초미세먼지 농도 오존 이산화탄소 대기 수질 해수면 일조시간 적설량 기압 일수"),
           _w("℃ ㎜ % ppm 시간 일 m/s 점")),
    Domain("energy", "에너지", "과학·환경",
           _w("energy electricity power generation demand supply consumption price oil gas coal renewable solar wind nuclear capacity peak"),
           _w(_COMMON_LABEL + " 전력 발전량 전력수요 최대전력 소비량 사용량 가격 석유 원유 가스 석탄 재생에너지 태양광 풍력 원자력 수력 발전 수요 공급 설비용량"),
           _w("kW MW GW kWh MWh GWh TWh % 원 점")),
    # 우주날씨(지역 없는 계열): 앞쪽은 1단계의 기본 낱말, 뒤쪽(estimated … x)은 NOAA SWPC 어댑터(S2a)가 쓰는 우리 낱말이다 — 제공처 설명 문장이 아니다.
    # `장애`·`지원`처럼 `당`·`수` 같은 한 글자 구조 낱말 뒤에서 차단 낱말(`당장`)을 만드는 글자로 시작하는 낱말은 올리지 않는다(`전파 교란`).
    Domain("space_weather", "우주날씨", "과학·환경",
           _w("space weather geomagnetic kp index solar wind speed density flux xray sunspot number proton electron magnetic field "
              "estimated outlook interval scale observed daily monthly radio radiation minor major prob swpc smoothed flare class storm threshold floor a b c m x"),
           _w(_COMMON_LABEL + " 지자기 지자기지수 태양풍 풍속 속도 밀도 엑스선 플럭스 흑점 흑점수 전파 자기장 양성자 전자 Kp "
              "NOAA SWPC GOES 추정 예보 폭풍 등급 교란 방사선 확률 낮은 높은 일별 월평균 평활 X선 플레어 세기 기준 A급 B급 C급 M급 X급 하한"),
           _w("Kp km/s nT sfu % 개 건 단계 nW/㎡")),
)}

# 지역 낱말(전체 이름이 한 낱말). 시군구·외국 지역은 실제 어댑터를 켤 때 이 표에 올린다
REGION_WORDS = _w("서울특별시 부산광역시 대구광역시 인천광역시 광주광역시 대전광역시 울산광역시 세종특별자치시 경기도 강원특별자치도 충청북도 충청남도 전북특별자치도 전라북도 전라남도 경상북도 경상남도 제주특별자치도 "
                  "서울 부산 대구 인천 광주 대전 울산 세종 경기 강원 충북 충남 전북 전남 경북 경남 제주 전국 전체 수도권 대한민국 한국 세계 미국 일본 중국 캐나다 독일 프랑스 영국 이탈리아 유럽연합")
# 시험용 가상 지역 이름(`가상 지역 가` — 가짜 Provider 가 쓴다). 실제 어댑터는 이 모양을 쓰지 않는다
REGION_PATTERNS = (re.compile(r"가상 지역 [가-힣]"),)

VOCABULARY = Vocabulary(DOMAINS, REGION_WORDS, REGION_PATTERNS)

# ----------------------------------------------------------------------------
# 차단 낱말 — 공백·가운뎃점·하이픈·문장 부호를 지운 글에서 부분 문자열로 찾는다(`무 조건` 도 `무조건` 이다)
# ----------------------------------------------------------------------------
BLOCKED_WORDS = {
    "건강·의료": ("환자", "질환", "질병", "증상", "진단", "치료", "완치", "처방", "복용", "투약", "약물", "의약", "약효", "효능", "부작용", "병원", "의사", "간호", "수술", "입원",
              "응급", "감염", "확진", "백신", "접종", "당뇨", "고혈압", "고지혈", "치매", "우울증", "불면", "통증", "비만", "영양제", "건강기능", "면역", "항생", "임상",
              "폐암", "위암", "간암", "대장암", "유방암", "갑상선암", "전립선암", "췌장암", "암환자", "사망원인", "치사율", "발병", "유병"),
    "금융·투자": ("주식", "주가", "증시", "증권", "코스피", "코스닥", "나스닥", "펀드", "코인", "비트코인", "이더리움", "암호화폐", "가상자산", "가상화폐", "선물거래", "옵션거래",
              "레버리지", "공매도", "매수", "매도", "수익률", "사야", "팔아", "사세요", "파세요", "투자추천", "투자상품", "투자수익", "재테크", "급등주", "상장", "배당"),
    "법률": ("소송", "재판", "판결", "위법", "불법", "처벌", "형사", "민사", "고소", "고발", "변호", "법적책임", "합법", "위반"),
    "단정·과장·예측": ("보장", "반드시", "확실", "무조건", "틀림없", "분명", "단언", "명백", "즉시", "당장", "역대급", "폭등", "폭락", "급등", "급락", "충격", "대박", "놀라운", "경악",
                  "쇼크", "초유", "전무후무", "추천", "권유", "유망", "때문", "덕분", "전망", "예상", "예측"),
}
# 한 글자 낱말은 부분 문자열로 찾으면 과탐이라(암호·약속·병아리) 낱말 전체가 그 글자일 때만 본다
BLOCKED_TOKENS = frozenset({"암", "약", "병"})
# 영문 라벨(글에 쓰지 않지만 같은 칸이다)의 차단 낱말 — 소문자, 공백·부호를 지운 글에서
BLOCKED_WORDS_EN = ("patient", "disease", "illness", "cancer", "diabetes", "hospital", "medical", "medicine", "drug", "therapy", "stock", "invest", "crypto", "bitcoin",
                    "fund", "lawsuit", "illegal", "guarantee", "forecast", "predict")

_WORD_SPLIT = re.compile(r"[\s·/()\-]+")


def normalize(text):
    """NFKC 정규화(전각·호환 글자를 평범한 글자로)."""
    return unicodedata.normalize("NFKC", text or "")


def compact(text):
    """공백·가운뎃점·하이픈·문장 부호·보이지 않는 글자를 모두 지운 소문자 글(글자와 숫자만 남긴다)."""
    return "".join(ch for ch in normalize(text).lower() if ch.isalnum())


def words(text):
    """라벨을 낱말로 가른다(공백·가운뎃점·슬래시·하이픈·괄호에서)."""
    return [word for word in _WORD_SPLIT.split(normalize(text)) if word]


class _Flat:
    """글을 낱말로 가르고 글자·숫자만 이어 붙인 글(flat)과, 각 글자가 속한 낱말 번호(owner)·낱말의 첫 글자 위치(starts)."""

    def __init__(self, text):
        tokens = [compact(token) for token in words(text)]
        tokens = [token for token in tokens if token]
        self.tokens = tokens
        self.flat = "".join(tokens)
        self.owner, self.starts = [], set()
        for number, token in enumerate(tokens):
            self.starts.add(len(self.owner))
            self.owner += [number] * len(token)

    def has(self, needle):
        """needle(공백 등을 지운 글)이 낱말 하나 안에 있거나 낱말의 첫머리에서 시작해 여러 낱말에 걸쳐 있는가."""
        if not needle:
            return False
        at = self.flat.find(needle)
        while at != -1:
            if at in self.starts or self.owner[at] == self.owner[at + len(needle) - 1]:
                return True
            at = self.flat.find(needle, at + 1)
        return False


def found_phrases(text, phrases):
    """phrases 중 text 에 든 것 — 공백·가운뎃점·하이픈을 지워서도 찾되, 낱말 경계를 가로질러 우연히 생긴 글자는 세지 않는다."""
    flat = _Flat(text)
    return [phrase for phrase in phrases if flat.has(compact(phrase))]


def blocked_in(text, *, english=False):
    """text 에 든 차단 낱말 [(범주, 낱말)] (공백 등을 지운 글에서 부분 문자열로, 한 글자 낱말은 낱말 전체일 때만)."""
    flat = _Flat(text)
    if english:
        return [("영문", word) for word in BLOCKED_WORDS_EN if flat.has(word)]
    found = []
    for category, listed in BLOCKED_WORDS.items():
        found += [(category, word) for word in listed if flat.has(word)]
    found += [("건강·의료", token) for token in flat.tokens if token in BLOCKED_TOKENS]
    return found


def blocked_loose(text):
    """text 에 든 차단 낱말 [(범주, 낱말)] — 공백·부호를 모두 지운 글에서 **낱말 경계와 상관없이** 부분 문자열로 찾는다(`국민환 자 통계` 의 환자 도 잡는다, 재검증 D3).
    `blocked_in` 의 '낱말 첫머리' 규칙은 정상 입력(`최고 소비`·`판매 수`)을 살리려는 것이라 합성어의 꼬리를 나눠 쓴 우회를 못 잡는다. 이 함수는 그 반대로 엄격해서 경계를 가로질러 우연히 생긴 글자도
    잡는다(`최고 소비` 의 고소) — 허용 목록이 없는 자유 글 칸(공식 데이터 이름·독자용 안내 문장)에만 쓴다. 그런 칸은 사람이 고쳐 쓸 수 있어 오탐의 값이 작고, 놓치는 쪽의 값이 더 크다(D-155)."""
    flat = compact(text)
    found = []
    for category, listed in BLOCKED_WORDS.items():
        found += [(category, word) for word in listed if word in flat]
    found += [("건강·의료", token) for token in _Flat(text).tokens if token in BLOCKED_TOKENS]
    return found


def _region_ok(label, vocabulary):
    return label in vocabulary.regions or any(pattern.fullmatch(label) for pattern in vocabulary.region_patterns) or \
        all(word in vocabulary.regions for word in words(label))


def fact_problem(fact, allowed_domains, vocabulary=VOCABULARY):
    """Fact 한 개의 키·라벨·단위·지역 낱말이 허용 범주의 허용 목록 안인지. 문제가 없으면 None, 있으면 (코드, 우리 문장):
    TOPIC_NOT_ALLOWED(막힌 주제·차단 낱말) · UNKNOWN_TOPIC(허용 목록에 없는 범주·낱말). 문장에는 문제의 글을 싣지 않는다."""
    texts = (fact.key, fact.label_ko, fact.unit, fact.region, fact.region_label_ko)
    topic = fact.key.split(".", 1)[0]
    if topic in F.BLOCKED_TOPICS or any(blocked_in(text) for text in texts if text) or any(blocked_in(text, english=True) for text in (fact.label_en, fact.region_label_en) if text):
        return "TOPIC_NOT_ALLOWED", "건강·의료·금융 투자·법률 주제나 과장·단정 낱말이 있어 이 경로가 글로 만들지 않는다"
    domain = vocabulary.domains.get(topic)
    if domain is None or topic not in allowed_domains:
        return "UNKNOWN_TOPIC", "이 Recipe 가 허용한 범주가 아니라 글로 만들지 않는다"
    metric = fact.key.split(".", 1)[1] if "." in fact.key else ""
    if not metric or any(word not in domain.key_words for word in re.split(r"[._]+", metric) if word):
        return "UNKNOWN_TOPIC", "키의 지표 이름에 허용 목록에 없는 낱말이 있어 글로 만들지 않는다"
    if fact.label_ko is None or any(word not in domain.label_words for word in words(fact.label_ko)):
        return "UNKNOWN_TOPIC", "라벨에 허용 목록에 없는 낱말이 있어 글로 만들지 않는다"
    if fact.kind in F.NUMERIC_KINDS and fact.unit not in domain.units:          # 글자 종류(분류코드·상태)는 단위가 없다 — 숫자 종류만 단위를 본다
        return "UNKNOWN_TOPIC", "단위가 허용 목록에 없어 글로 만들지 않는다"
    if fact.region_label_ko is not None and not _region_ok(normalize(fact.region_label_ko), vocabulary):
        return "UNKNOWN_TOPIC", "지역 이름이 허용 목록에 없어 글로 만들지 않는다"
    return None


def text_problem(text, *, loose=False):
    """우리 글에 섞일 수 있는 바깥 글(Provider 이름·독자용 안내 문장)에 차단 낱말이 있는지 — 있으면 우리 문장 사유, 없으면 None. loose 이면 낱말 경계와 상관없이 찾는다(`blocked_loose`)."""
    if (blocked_loose(text) if loose else blocked_in(text)):
        return "건강·의료·금융 투자·법률 주제나 과장·단정 낱말이 있음"
    return None
