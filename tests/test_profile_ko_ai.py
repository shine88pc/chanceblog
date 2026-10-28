"""한글 Blogger(kcyoon) 콘텐츠 프로필 `blogger_ai_tools_ko` 시험(작업 D). 네트워크 없이 돈다.

이 프로필은 한국어 Blogger 프로필(blogger_practical_ko)의 가드레일 구조(banned_*·body_*·leak_*·상담 구절 면제)를 그대로 가져오고, 일상 속 AI·디지털 도구 + 집·살림
블로그에 맞게 넓히거나 좁혔다. 지금은 레지스트리에서 mode off 라 글이 나가지 않지만, 켜기 전에 가드레일이 의도대로인지를 이 시험이 고정한다:
  1) 구조·시드: 필드, 시드 36개(AI·디지털 26 + 집·살림 10, 각 35~55자)와 모두 가드레일 통과, 번역·복제와 다른 블로그 제목과의 충돌이 없다.
  2) 게이트: 정상 문장(일상·AI 도구·보안·집 정리) 오탐 0 / 지어낸 경험·수치·후기·링크·의료·법률·금융 조언·자기 언급이 탈락 / 언어·구조·길이.
  3) 규칙 표: 이 블로그가 더하거나 좁힌 규칙마다 '그 규칙만' 표본을 잡는지(다른 규칙이 대신 잡는 것을 가른다).
"""
import copy
import datetime
import json
import random
import re
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from pipeline import gates, registry, topics
from pipeline import run as run_mod
from pipeline.state import entry_titles, other_blog_titles, read_json_list
from pipeline.stubs import stub_llm, stub_post, stub_post_en

REAL = _bootstrap.ROOT
PROFILE = registry.load_profile("blogger_ai_tools_ko")
BASE = registry.load_profile("blogger_practical_ko")
EN = registry.load_profile("blogger_practical_en")
PROFILE_PATH = REAL / "pipeline" / "profiles" / "blogger_ai_tools_ko.json"
SEEDS = PROFILE["seed_topics"]

# 정상 문장(본문): 일상·AI 도구·보안·집 정리 낱말을 골고루 쓴다. 프로필의 어떤 금지 목록에도 걸리면 안 된다.
NORMAL_SENTENCES = [
    "AI 챗봇에게 질문할 때는 상황과 원하는 결과를 먼저 적어 주세요.",
    "답변이 길면 핵심만 다섯 줄로 요약해 달라고 다시 요청해 보세요.",
    "챗봇이 알려 준 내용은 틀릴 수 있으니 중요한 부분은 공식 도움말에서 다시 확인하세요.",
    "회의 메모를 맡기기 전에 이름과 연락처 같은 개인정보는 지우는 것이 좋아요.",
    "번역기가 만든 문장은 어색한 부분이 없는지 한 번 더 읽어 보세요.",
    "생성형 AI는 그럴듯한 문장을 만들어 내지만 사실 확인은 사용자의 몫입니다.",
    "언어 모델이 만든 요약은 원문과 나란히 놓고 빠진 내용을 찾아보면 좋아요.",
    "AI 어시스턴트 기능이 켜져 있는지 설정 화면에서 확인할 수 있어요.",
    "비밀번호는 계정마다 다르게 만들고 비밀번호 관리자에 보관해 두세요.",
    "2단계 인증을 켜면 비밀번호가 알려져도 한 번 더 확인 절차를 거치게 됩니다.",
    "악성코드에 감염되는 일을 줄이려면 출처를 모르는 파일은 열지 않는 습관이 중요해요.",
    "피싱 문자의 링크를 누르지 않고 공식 앱에서 직접 확인하면 피해를 예방할 수 있습니다.",
    "암호를 자주 바꾸기보다 길고 서로 다른 암호를 쓰면 계정 도용을 예방할 수 있어요.",
    "공용 와이파이에서는 중요한 로그인을 피하는 편이 안전해요.",
    "앱 권한 화면에서 위치와 마이크 권한이 꼭 필요한지 하나씩 살펴보세요.",
    "배터리 사용량이 많은 앱부터 확인해 불필요한 백그라운드 실행을 꺼 보세요.",
    "스마트폰 저장공간이 부족하면 사진을 클라우드로 옮긴 뒤 기기에서 지우는 방법이 있어요.",
    "PC가 느릴 때는 시작 프로그램 목록에서 자주 쓰지 않는 항목을 꺼 보세요.",
    "중요한 파일은 클라우드와 외장 저장장치 두 곳에 나눠 보관해 두면 안심이에요.",
    "캘린더에 반복 일정을 등록해 두면 매달 하는 일을 잊지 않을 수 있어요.",
    "메모 앱에서는 폴더를 너무 많이 만들지 말고 태그 몇 개로 단순하게 나눠 보세요.",
    "스프레드시트 수식이 낯설다면 AI에게 한 줄씩 설명해 달라고 부탁해 보세요.",
    "무료 도구를 고를 때는 개인정보를 어디까지 요구하는지 먼저 살펴보세요.",
    "ToDo 앱에서는 오늘 할 일을 세 가지만 적어 두면 부담이 줄어요.",
    "요금제와 무료 한도는 자주 바뀌니 서비스의 공식 안내 화면에서 확인하세요.",
    "10분만 투자하면 바탕화면을 깔끔하게 정리할 수 있어요.",
    "다운로드 폴더는 일주일에 한 번 날짜순으로 정렬해 필요 없는 파일을 지워 보세요.",
    "냉장고 선반마다 이름표를 붙이면 식재료를 찾는 시간이 줄어요.",
    "욕실 청소는 요일별로 나누어 한 번에 하나만 하면 부담이 적어요.",
    "옷장을 정리할 때는 계절별로 나누고 입지 않는 옷은 따로 모아 두세요.",
    "가계부는 매일 쓰기보다 일주일에 한 번 영수증을 모아 정리해도 충분해요.",
    "장보기 전에 냉장고 속 재료를 먼저 확인하면 같은 물건을 또 사는 일이 줄어요.",
    "외출하기 전에 전등과 가전 전원을 확인하는 점검 목록을 현관에 붙여 두세요.",
    "택배 상자는 테이프와 송장을 떼어 내고 접어서 분리배출하면 좋아요.",
    "겨울이 오기 전에 창틀 틈새를 확인하고 필요하면 문풍지를 붙여 보세요.",
    "서랍은 한 칸씩 비워서 자주 쓰는 물건만 앞쪽에 다시 넣어 보세요.",
    "화상 회의 전에 마이크와 카메라가 제대로 작동하는지 시험해 보세요.",
    "알림은 꼭 필요한 앱만 남기고 나머지는 요약으로 받도록 바꿔 보세요.",
    "구글 계정 보안 화면에서 복구용 전화번호와 이메일이 최신인지 확인해 두세요.",
    "수상한 메일은 첨부 파일을 열지 말고 발신자 주소부터 천천히 살펴보세요.",
    "직접 해 본 적이 없다면 작은 설정 하나부터 천천히 바꿔 보세요.",
    "먼저 작은 부분에 적용해 보고 괜찮으면 범위를 넓혀 가세요.",
    "써 보면 알겠지만 처음에는 낯설어도 금방 익숙해져요.",
    "AI에게 맡긴 결과는 직접 읽어 보고 고쳐 쓰세요.",
    "이 방법은 일반적으로 도움이 될 수 있지만 상황에 따라 다를 수 있어요.",
    "사진을 날짜별 앨범으로 나누어 두면 나중에 찾기 쉬워요.",
    "브라우저 확장 프로그램은 자주 쓰는 몇 개만 남기고 나머지는 꺼 두세요.",
    "공식 도움말에는 메뉴 위치가 자세히 나와 있으니 화면과 비교하며 따라 해 보세요.",
    "계약서 같은 중요한 서류는 스캔해서 폴더 이름에 날짜를 붙여 보관하세요.",
    "예약 문자는 일정 앱에 옮겨 적어 두면 놓치지 않아요.",
    "절약한 시간은 정리한 폴더를 다시 어지럽히지 않는 데 쓰세요.",
]

# 나쁜 본문 표본: (문장, 걸려야 하는 곳). 곳 = BANNED(banned_patterns) · LEAK(leak_patterns) · BODY(body_banned_patterns, 상담 구절 면제 후)
BAD_BODY = [
    # 지어낸 개인 경험
    ("제가 직접 써 봤더니 정리 시간이 확 줄었어요.", "BANNED"),
    ("써 보니 생각보다 훨씬 편했습니다.", "BANNED"),
    ("직접 해 본 결과 설정이 훨씬 간단해졌어요.", "BANNED"),
    ("이 방법으로 정리했더니 폴더 찾기가 쉬워졌어요.", "BANNED"),
    ("저는 매일 아침 이 기능을 켜 두고 씁니다.", "BANNED"),
    ("저희 집에서도 같은 방식으로 정리해 두었습니다.", "BANNED"),
    ("직접 테스트해 봤는데 답변이 훨씬 정확했어요.", "BANNED"),
    ("여러 도구를 비교해 보았더니 차이가 컸습니다.", "BANNED"),
    # 지어낸 수치·벤치마크
    ("이 설정으로 작업 속도가 30% 빨라집니다.", "BANNED"),
    ("정리 시간이 2배 줄어드는 효과가 있어요.", "BANNED"),
    ("벤치마크 결과 응답 속도가 크게 좋아졌습니다.", "BANNED"),
    # 지어낸 인용·후기·연구
    ("전문가에 따르면 이 방법이 가장 안전하다고 합니다.", "BANNED"),
    ("한 연구에 따르면 하루 10분 정리가 집중력을 높인다고 해요.", "BANNED"),
    ("사용자 후기를 보면 대부분 만족했다고 해요.", "BANNED"),
    ("개발자 인터뷰에서 이 기능의 장점이 소개됐어요.", "BANNED"),
    ("통계에 따르면 대다수가 이 방법을 쓴다고 합니다.", "BANNED"),
    # 결과 단정·보장
    ("이 설정을 켜면 해킹 걱정이 전혀 없어요.", "BANNED"),
    ("100% 안전한 방법입니다.", "BANNED"),
    ("절대 뚫리지 않는 비밀번호를 만들 수 있어요.", "BANNED"),
    ("완벽하게 차단할 수 있습니다.", "BANNED"),
    # 의료
    ("이 습관으로 불면증이 완치됩니다.", "BANNED"),
    ("감기를 예방할 수 있습니다.", "BANNED"),
    ("약을 끊어도 괜찮아요.", "BANNED"),
    ("혈압을 낮추는 데 이 앱이 도움이 됩니다.", "BODY"),
    ("영양제를 챙겨 먹으면 집중력이 좋아져요.", "BODY"),
    ("우울증이 있다면 이 방법을 따라 해 보세요.", "BODY"),
    # 법률
    ("저작권 침해로 소송이 걸릴 수 있어요.", "BODY"),
    ("변호사를 거치지 않고 합의금을 정하세요.", "BODY"),
    ("개인정보보호법 위반이면 책임을 져야 합니다.", "BODY"),
    # 세금·대출·투자·보험
    ("연말정산 환급액을 늘리는 방법을 알려 드릴게요.", "BODY"),
    ("세금을 줄이려면 이 앱에 영수증을 올려 보세요.", "BODY"),
    ("대출 금리가 낮은 곳을 비교해 보세요.", "BODY"),
    ("주식 투자 종목을 AI에게 추천받아 보세요.", "BODY"),
    ("비트코인 수익률을 확인하는 앱을 소개합니다.", "BODY"),
    ("보험료를 아끼려면 가입 상품을 정리해 보세요.", "BODY"),
    # 링크·주소·이메일
    ("자세한 내용은 https://example.com/help 에서 확인하세요.", "BANNED"),
    ("공식 사이트 www.example.org 에 접속해 보세요.", "BANNED"),
    ("macat0722.blogspot.com 에서 영문판을 볼 수 있어요.", "BANNED"),
    ("문의는 hello@example.com 으로 보내 주세요.", "BANNED"),
    ("shine88pc.github.io 의 글도 함께 읽어 보세요.", "BANNED"),
    # 요금·한도
    ("월 9,900원짜리 요금제를 쓰면 한도가 늘어납니다.", "BANNED"),
    ("무료 플랜은 하루 50회까지 쓸 수 있어요.", "BANNED"),
    # 광고·제휴 어조
    ("이 도구는 강력 추천합니다.", "BANNED"),
    ("지금 바로 구독하세요.", "BANNED"),
    ("할인 코드를 입력하면 더 저렴해요.", "BANNED"),
    ("이 글은 협찬을 받아 작성했습니다.", "BANNED"),
    # AI 자기 언급·머리말·자리표시자
    ("저는 AI 언어 모델이라서 직접 써 볼 수는 없어요.", "LEAK"),
    ("죄송합니다. 다시 작성해 드리겠습니다.", "LEAK"),
    ("다음은 요청하신 블로그 글입니다.", "LEAK"),
    ("물론이죠! 아래에 정리해 드릴게요.", "LEAK"),
    ("As an AI language model, I cannot test this.", "LEAK"),
    ("[링크 삽입] 에서 내려받으세요.", "LEAK"),
    ("TODO: 여기에 예시를 더 넣기", "LEAK"),
]

# 정상 제목(제목 게이트 전부 통과): 비밀번호·감염·ToDo 같은 이 블로그의 일상 낱말을 포함한다
NORMAL_TITLES = [
    "AI 챗봇에게 질문하는 방법 5가지",
    "비밀번호 관리자로 계정 정리하는 방법",
    "2단계 인증을 켜는 순서와 복구 수단 확인",
    "스마트폰 사진을 날짜별로 정리하고 백업하는 법",
    "악성코드 감염을 줄이는 파일 열기 습관",
    "피싱 문자를 구분하는 기본 체크리스트",
    "ToDo 앱으로 하루 계획 세우는 방법",
    "냉장고 수납을 한눈에 정리하는 방법",
    "욕실 청소 순서를 요일별로 나누는 요령",
    "가계부 쓰기 부담을 줄이는 습관 3가지",
    "AI에게 긴 문서를 요약시키는 요령과 확인 순서",
    "공용 와이파이에서 지켜야 할 보안 습관",
    "PC가 느릴 때 먼저 확인할 시작 프로그램",
    "메모 앱을 태그로 단순하게 정리하는 법",
    "화상 회의 전에 해 두는 장비 점검 순서",
    "피싱 피해를 예방하는 문자 확인 요령",
]

# 나쁜 제목: (제목, 걸려야 하는 곳) TITLE_BANNED · TITLE_TOPIC · BANNED(본문 금지 패턴이 제목에도 걸림) · LEAK
BAD_TITLES = [
    ("충격! 이 설정 하나로 스마트폰이 달라졌습니다", "TITLE_BANNED"),
    ("비밀 노하우를 공개합니다", "TITLE_BANNED"),
    ("AI 도구 TOP 5 순위", "TITLE_BANNED"),
    ("역대급 설정 꿀팁", "TITLE_BANNED"),
    ("무조건 해야 하는 스마트폰 설정", "TITLE_BANNED"),
    ("직접 써 본 후기", "TITLE_BANNED"),
    ("챗봇 사용 후기 총정리", "TITLE_BANNED"),
    ("모르면 손해 보는 계정 설정", "TITLE_BANNED"),
    ("주식 투자에 AI 활용하기", "TITLE_TOPIC"),
    ("세금 신고를 AI로 끝내는 법", "TITLE_TOPIC"),
    ("대출 금리 비교하는 방법", "TITLE_TOPIC"),
    ("저작권 걱정 없이 AI 그림 쓰는 법", "TITLE_TOPIC"),
    ("보험 설계를 챗봇에게 맡기기", "TITLE_TOPIC"),
    ("당뇨 관리 앱 사용법", "TITLE_TOPIC"),
    ("직접 써 봤더니 달라진 점", "BANNED"),
    ("https://example.com 활용법", "BANNED"),
]

# ---- 규칙 표: (목록, 규칙을 알아보는 조각, 걸려야 하는 표본, 걸리면 안 되는 표본). `=` 로 시작하는 조각은 규칙 전체와 같아야 한다.
# 목록: banned(제목+본문 전체, 예외 없음) · title(제목) · leak(제목+본문) · topic(주제·제목·라벨) · body(본문, 상담 구절 면제 후)
RULES = [
    # ---- banned: 기본(의료 효능·결과 단정) — 기본 프로필에서 그대로 가져온 것(일부는 이 블로그의 낱말과 안 부딪히게 좁혔다)
    ("banned", "=완치", ["이 습관으로 불면증이 완치됩니다."], ["정리 습관이 완성됩니다."]),
    ("banned", "만병통치", ["만병통치 같은 설정 하나면 충분해요."], ["통치 방식의 차이를 설명해요."]),
    ("banned", "기적의", ["기적의 정리 방법을 알려 드려요."], ["기적 같은 일은 없어요."]),
    ("banned", "특효", ["특효가 있는 설정이에요."], ["특별한 효과를 기대하지 않아요."]),
    ("banned", "부작용", ["이 앱은 부작용이 전혀 없어요."], ["알림이 늘어나는 부작용을 줄이려면 설정을 바꾸세요."]),
    ("banned", "100\\s*%\\s*(?:효과", ["100% 효과가 있어요."], ["100% 충전된 배터리를 뽑아 보세요."]),
    ("banned", "반드시\\s*(?:낫", ["반드시 낫습니다."], ["반드시 직접 읽어 보고 고쳐 쓰세요."]),
    ("banned", "(?:치료|완치)\\s*(?:된다", ["이 방법으로 치료됩니다."], ["치료 이야기는 쓰지 않는 블로그예요."]),
    ("banned", "예방\\s*(?:된다", ["이 방법으로 감기를 예방할 수 있습니다."],
     ["피싱 피해를 예방할 수 있습니다.", "암호를 길게 만들면 계정 도용을 예방할 수 있어요.", "2단계 인증으로 도용이 예방됩니다."]),
    ("banned", "(?:병원|의사)(?:에|를)?", ["병원에 갈 필요가 없어요."], ["병원 예약 문자를 일정 앱에 옮겨 두세요."]),
    ("banned", "(?<![가-힣])약(?:을|은)?", ["약을 끊어도 괜찮아요."], ["계약을 중단하려면 약관을 확인하세요.", "예약을 줄이려면 일정 앱을 쓰세요.", "약 30분이면 끝나요."]),
    # ---- banned: 이 블로그가 더한 것 — 결과·성능 단정
    ("banned", "100\\s*%\\s*(?:안전", ["100% 안전한 방법입니다."], ["100% 충전된 휴대폰으로 시작하세요."]),
    ("banned", "절대\\s*(?:안전", ["절대 뚫리지 않는 비밀번호를 만들 수 있어요.", "이 설정은 절대 안전합니다."], ["절대값 정렬 기능을 써 보세요."]),
    ("banned", "(?:완벽(?:하게|히)?", ["완벽하게 차단할 수 있습니다.", "확실히 막아 줍니다."], ["완벽한 계획보다 작은 실행이 낫습니다."]),
    ("banned", "(?:해킹|유출|사기|피싱)", ["해킹 걱정이 전혀 없어요.", "유출 위험이 없습니다."], ["해킹 사고를 줄이려면 2단계 인증을 켜세요."]),
    ("banned", "\\d+(?:\\.\\d+)?\\s*(?:%|퍼센트|배)", ["작업 속도가 30% 빨라집니다.", "정리 시간이 2배 줄었어요."], ["배터리가 30% 남았을 때 절전 모드를 켜세요.", "앱을 2배속으로 재생해 보세요."]),
    # ---- banned: 지어낸 개인 경험·후기·인용
    ("banned", "시켜)\\s*(?:봤|보았|보니)", ["써 보니 편했어요.", "직접 테스트해 봤는데 정확했어요.", "비교해 보았더니 차이가 컸어요."],
     ["써 보세요.", "써 보면 알아요.", "한 번 해 보세요.", "해 본 적이 없다면 천천히 해 보세요."]),
    ("banned", "본\\s*(?:결과|뒤|후|경험", ["직접 해 본 결과 간단했어요.", "써 본 경험이 있어요."], ["해 본 적이 없다면 시작해 보세요."]),
    ("banned", "직접\\s*(?:[가-힣]+\\s*){0,3}(?:봤", ["직접 눌러 봤어요."], ["직접 눌러 보세요.", "직접 확인해 보고 고치세요."]),
    ("banned", "(?:했|썼|켰|꿨", ["정리했더니 편해졌어요.", "설정을 켰더니 조용해졌어요."], ["정리하면 편해집니다.", "켜면 조용해져요."]),
    ("banned", "(?<![가-힣])(?:저는", ["저는 매일 아침 이 기능을 써요.", "제가 쓰는 방법이에요.", "저희 집도 같은 방식이에요."], ["제어판에서 확인하세요.", "나는 새처럼 가볍게 정리해요."]),
    ("banned", "(?:전문가|연구", ["전문가에 따르면 이 방법이 안전하대요.", "연구 결과에 따르면 효과가 있대요."], ["공식 도움말에 따르면 이 메뉴에서 바꿀 수 있어요.", "설정에 따라 다를 수 있어요."]),
    ("banned", "인터뷰|(?:사용|이용", ["개발자 인터뷰에서 소개됐어요.", "사용 후기를 보면 만족도가 높대요."], ["사용 방법을 알려 드려요."]),
    # ---- banned: 자주 바뀌는 사실(요금·한도)
    ("banned", "(?:월|연|한\\s*달", ["월 9,900원 요금제예요.", "한 달 3만 원이면 돼요.", "$5짜리 플랜이에요."], ["월 1회 점검하세요.", "한 달에 한 번 정리하세요."]),
    ("banned", "(?:무료|유료)\\s*(?:플랜", ["무료 플랜은 하루 50회까지 쓸 수 있어요.", "하루 20번까지 제한이 있어요.", "하루 10건 제한이 있어요.", "하루 5번 이하로만 쓸 수 있어요."], ["무료 도구를 고를 때는 개인정보를 확인하세요.", "하루 한 번 점검하세요."]),
    # ---- banned: 광고·제휴 어조
    ("banned", "강력\\s*추천", ["이 도구를 강력 추천합니다.", "지금 바로 구독하세요.", "가입을 권합니다."], ["지금 구독 중인 서비스를 확인하세요.", "추천 설정을 따라 해 보세요."]),
    ("banned", "(?:할인|프로모션)", ["할인 코드를 입력하세요.", "협찬을 받았어요.", "제휴 링크예요.", "내돈내산 후기예요.", "최저가를 찾아보세요."], ["할인 정보는 공식 화면에서 확인하세요."]),
    # ---- banned: 어떤 링크도 금지(웹 주소·도메인·이메일)
    ("banned", "(?:https?|ftp)", ["https://example.com 에서 확인하세요.", "www.example.org 를 열어 보세요."], ["공식 사이트 주소는 직접 입력하세요."]),
    ("banned", "(?<![A-Za-z0-9\\-.@])", ["macat0722.blogspot.com 도 있어요.", "shine88pc.github.io 글도 보세요.", "naver.com 로그인 화면이에요."],
     ["파일 이름은 report.txt 로 저장하세요.", "Node.js 를 설치하지 마세요."]),
    ("banned", "[A-Za-z0-9._%+", ["문의는 hello@example.com 으로 보내세요."], ["골뱅이(@) 기호를 눌러 보세요."]),
    # ---- title
    ("title", "충격", ["충격 설정 하나"], ["충전 설정 하나"]),
    ("title", "경악", ["경악할 설정"], ["경력 정리 설정"]),
    ("title", "소름", ["소름 돋는 정리법"], ["소음 줄이는 정리법"]),
    ("title", "대박", ["대박 앱 모음"], ["대화 앱 모음"]),
    ("title", "미쳤", ["미쳤다 이 설정"], ["미리 챙기는 설정"]),
    ("title", "이것만\\s*알면", ["이것만 알면 끝"], ["이것만 확인하세요"]),
    ("title", "(?:^|\\s)절대", ["절대 하지 말아야 할 설정"], ["절대값 정렬법"]),
    ("title", "무조건", ["무조건 켜야 할 설정"], ["조건을 정하는 방법"]),
    ("title", "비밀(?!번호)", ["비밀 노하우 공개"], ["비밀번호 관리자 시작하기", "비밀번호를 정리하는 방법"]),
    ("title", "의사들이", ["의사들이 말하는 습관"], ["의사소통 정리법"]),
    ("title", "[!?]{2,}", ["이게 되네?? 설정"], ["이게 되나요? 설정"]),
    ("title", "모르면\\s*손해", ["모르면 손해 보는 설정", "역대급 설정", "난리 난 설정"], ["모르는 설정 찾는 법"]),
    ("title", "최고의|최강", ["최고의 AI 도구", "최강 정리법", "1위 앱", "도구 순위", "TOP 5 앱", "best 3 앱"], ["최고 속도 설정은 다루지 않아요", "순서대로 정리하기"]),
    ("title", "후기|리뷰", ["사용 후기", "앱 리뷰"], ["후속 설정 정리"]),
    # ---- leak
    ("leak", "(?:저는|제가|전)", ["저는 AI 언어 모델이라서 쓸 수 없어요.", "전 AI 어시스턴트입니다."], ["AI 어시스턴트 기능을 켜 보세요.", "언어 모델이 만든 요약을 확인하세요."]),
    ("leak", "(?:로서|으로서)\\s*(?:저는|제가|저의", ["AI로서 저는 도와드릴 수 없습니다.", "언어 모델로서 죄송합니다."], ["AI는 도구로서 쓰이는 때가 많아요."]),
    ("leak", "as an? (?:ai", ["As an AI, I cannot do that.", "as a assistant I can help"], ["an AI tool can help you"]),
    ("leak", "as a (?:large )?language model", ["As a large language model I do not know."], ["a language model is a tool"]),
    ("leak", "=죄송", ["죄송합니다. 다시 쓸게요."], ["송금 정리 요령"]),
    ("leak", "(?:요청하신|말씀하신)", ["요청하신 블로그 글입니다."], ["요청 사항을 정리하세요."]),
    ("leak", "다음은\\s*[^.\\n]{0,24}", ["다음은 아래의 블로그 글입니다.", "다음은 포스팅 초안입니다"], ["다음은 점검 순서입니다."]),
    ("leak", "(?:물론이죠|물론입니다", ["물론이죠! 정리해 드릴게요."], ["물론 직접 확인도 필요해요."]),
    ("leak", "```", ["```html"], ["따옴표를 쓰지 않아요."]),
    ("leak", "\\{topic\\}", ["{topic} 에 대해 씁니다."], ["{ 주제 }"]),
    ("leak", "\\[(?:대상|링크", ["[링크 삽입]", "[대상: Blogger 한글]", "[이미지 넣기]"], ["[1] 번호 목록"]),
    ("leak", "(?m)^\\s*(?:제목|라벨|내용)", ["제목: 가짜 제목"], ["내용을 정리하세요."]),
    ("leak", "\\btodo\\s*[:：]", ["TODO: 예시 더 넣기"], ["ToDo 앱을 쓰세요.", "todo list 를 만들어 보세요."]),
    ("leak", "lorem ipsum", ["Lorem ipsum dolor"], ["lorem 없음"]),
    ("leak", "\\*\\*", ["**굵게**"], ["별표 하나 *"]),
    ("leak", "(?m)^\\s*#{1,6}\\s", ["# 제목"], ["#해시태그 없음"]),
    # ---- topic: 이 블로그가 더한 법률·세금·대출·투자·보험·주거 계약 어휘와 좁힌 낱말
    ("topic", "법률|법적", ["법률 상담 대신 AI에게 물어보기", "법적 분쟁 줄이는 설정"], ["방법을 정리하는 순서"]),
    ("topic", "소송|고소(?!한)", ["소송 절차를 AI로 알아보기", "고소장 쓰는 법"], ["고소한 냄새를 줄이는 환기 습관"]),
    ("topic", "저작권|상표권", ["AI 그림 저작권 걱정 줄이기"], ["저장 권한 확인하기"]),
    ("topic", "보호법", ["개인정보보호법 정리"], ["개인정보 보호 습관"]),
    ("topic", "세금|세무", ["세금 계산을 AI에게 맡기기", "연말 정산 서류 정리", "홈택스 사용 순서"], ["세탁기 정리 요령"]),
    ("topic", "대출|이자율", ["대출 금리 비교하기", "신용 점수 올리는 법", "카드 연체 줄이기"], ["품질을 담보하는 방법", "대화를 정리하는 방법"]),
    ("topic", "(?:주식|펀드|코인", ["주식 투자에 AI 활용하기", "비트코인 시세 확인 앱", "펀드 수익률 보기", "재테크 앱 고르기"], ["10분 투자해서 바탕화면 정리하기", "주식회사 서류 파일 이름 정하기"]),
    ("topic", "(?:자동차|건강|생명", ["자동차 보험 비교하기", "보험금 청구 서류 정리"], ["백업은 보험 같은 안전장치예요"]),
    ("topic", "임대차|전세", ["전세 계약 서류 정리", "월세 납부 알림 설정", "보증금 영수증 보관"], ["전세계 사용자가 쓰는 번역 도구"]),
    ("topic", "증상|환자", ["컴퓨터가 느려지는 증상 확인하기", "환자 기록 정리"], ["상황을 확인하는 순서"]),
    ("topic", "(?:세균|박테리아", ["독감 감염 예방 습관", "감염병 정리", "세균 감염을 줄이는 청소"], ["악성코드 감염을 줄이는 파일 열기 습관", "바이러스에 감염된 파일 열지 않기"]),
]


def good_post(topic=SEEDS[0], sentence="", title=None, labels=None):
    """게이트를 통과하는 글(스텁이 만든 한국어 본문). sentence 가 있으면 첫 문단 끝에 붙여 그 문장만 시험한다."""
    post = gates.parse_labeled_post(stub_post(topic))
    clean, stats = gates.sanitize_html(post["content"])
    if sentence:
        clean = clean.replace("</p>", f" {sentence}</p>", 1)
    return {"title": title or post["title"], "labels": labels if labels is not None else post["labels"], "content": clean}, stats


def codes_of(post, stats=None, recent=(), other=()):
    return gates.check_post(post, PROFILE, list(recent), list(other), stats).codes()


class StructureTest(unittest.TestCase):
    def test_the_profile_is_valid_and_named_like_its_file(self):
        self.assertEqual(registry.validate_profile(PROFILE), [])
        self.assertEqual(PROFILE["name"], "blogger_ai_tools_ko")
        self.assertEqual(PROFILE_PATH.stem, PROFILE["name"])
        self.assertEqual(PROFILE["language"], "ko")

    def test_the_file_is_utf8_without_bom_and_ends_with_a_newline(self):
        raw = PROFILE_PATH.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(json.loads(raw.decode("utf-8")), PROFILE)                                             # UTF-8 로 그대로 읽힌다(깨진 글자 없음)

    def test_the_guardrail_structure_is_the_korean_practical_profile_s(self):
        """banned_*·body_*·leak_*·상담 구절 면제 구조를 그대로 가져왔다: 같은 필드를 갖고 길이·구조·라벨·유사도·쿨다운이 같다. 다른 것은 의도한 것뿐이다."""
        self.assertLessEqual(set(BASE), set(PROFILE))
        self.assertEqual(set(PROFILE) - set(BASE), {"_seed_mix", "topic_expand_prompt"})
        for key in ("max_attempts", "length", "title", "structure", "labels", "allow_links", "similarity", "topic_cooldown_days", "body_safe_veto_patterns"):
            self.assertEqual(PROFILE[key], BASE[key], key)
        self.assertIs(PROFILE["allow_links"], False)
        self.assertEqual((BASE["min_hangul_ratio"], PROFILE["min_hangul_ratio"]), (0.5, 0.6))               # AI·도구 글에는 영문 낱말이 섞이므로 한글 비율 기준을 따로 둔다(하한 60%)

    def test_every_base_medical_rule_is_still_there_except_the_four_narrowed_ones(self):
        """의료 낱말·효능 단정·본문 목록은 하나도 줄이지 않았다. 좁힌 곳은 이 블로그의 일상 낱말과 부딪히는 네 곳뿐이다(감염·예방 단정·약·비밀·todo·AI 어시스턴트 자기 언급은 아래 규칙 표가 따로 본다)."""
        narrowed_topic = {"증상|환자|감염"}
        self.assertEqual(set(BASE["banned_topic_patterns"]) - set(PROFILE["banned_topic_patterns"]), narrowed_topic)
        self.assertEqual(set(BASE["body_banned_patterns"]) - set(PROFILE["body_banned_patterns"]), narrowed_topic)
        self.assertEqual(set(BASE["banned_patterns"]) - set(PROFILE["banned_patterns"]),
                         {"(?:치료|완치|예방)\\s*(?:된다|됩니다|됐다|할\\s*수\\s*있습니다|가\\s*가능)", "약(?:을|은)?\\s*(?:끊|중단|줄이)"})
        self.assertEqual(set(BASE["title_banned_patterns"]) - set(PROFILE["title_banned_patterns"]), {"비밀"})
        # 누출 목록: AI 자기 언급(AI 어시스턴트·언어 모델은 이 블로그의 일상 낱말), 영문 자기 언급 둘, 자리표시자, todo 는 더 정확한 모양으로 바꿨다
        self.assertEqual(set(BASE["leak_patterns"]) - set(PROFILE["leak_patterns"]),
                         {"AI\\s*(?:로서|언어\\s*모델|어시스턴트)", "as an ai", "language model", "\\[대상", "todo"})

    def test_the_consultation_exemption_and_clause_splitters_also_know_lawyers_and_tax_accountants(self):
        old, new = "의사|약사|전문가|전문의|의료진", "의사|약사|변호사|법무사|세무사|회계사|노무사|재무\\s*설계사|금융\\s*전문가|법률\\s*전문가|세무\\s*전문가|전문가|전문의|의료진"
        self.assertEqual(len(PROFILE["body_clause_split_patterns"]), len(BASE["body_clause_split_patterns"]))
        for before, after in zip(BASE["body_clause_split_patterns"], PROFILE["body_clause_split_patterns"]):
            self.assertEqual(before.replace(old, new), after)
        self.assertEqual([p.replace(old, new) for p in BASE["body_safe_patterns"]], PROFILE["body_safe_patterns"][:len(BASE["body_safe_patterns"])])
        self.assertEqual(len(PROFILE["body_safe_patterns"]), len(BASE["body_safe_patterns"]) + 1)          # 법률·세무·투자·금융 면책 한 줄이 더해졌다
        for pattern in PROFILE["body_clause_split_patterns"] + PROFILE["body_safe_patterns"]:
            re.compile(pattern, re.IGNORECASE)

    def test_the_disclosure_is_an_honest_ai_notice_in_korean_without_links(self):
        html = PROFILE["disclosure_html"]
        self.assertTrue(html.startswith("<p><em>") and html.endswith("</em></p>"))
        for fragment in ("AI의 도움을 받아 작성·편집", "공식 화면에서 확인", "전문적인 조언이 아니며", "전문가와 상담하세요"):
            self.assertIn(fragment, html)
        for word in ("건강", "법률", "세금", "금융", "투자"):
            self.assertIn(word, html)
        self.assertNotRegex(html, r"https?://|<a ")
        self.assertEqual(gates.append_disclosure("<p>본문</p>", PROFILE), "<p>본문</p>\n" + html)

    def test_the_prompt_extra_lines_carry_the_rules_the_brief_asked_for(self):
        lines = "\n".join(PROFILE["prompt_extra"])
        for fragment in ("링크, 이미지, 스크립트, 표는 넣지 않는다", "웹 주소와 이메일 주소도 글자로 쓰지 않는다", "허용 태그는 p, h3, ul, ol, li, strong, em, br 뿐이다",
                         "개인 경험·수치·벤치마크·인터뷰·사용자 후기·전문가의 말·연구 결과를 지어내지 않는다", "'써 봤더니'", "'직접 해 본 결과'", "1인칭(저는·제가)",
                         "가격·요금제·무료 한도·기능 이름·메뉴 위치·버전", "설정이나 도움말 화면에서 직접 확인하는 방법",
                         "홍보하거나 순위를 매기거나 구매·가입을 권하지 않는다", "법률·세금·대출·투자·보험 조언은 경고로도 쓰지 않는다",
                         "답이 틀릴 수 있으니 중요한 내용은 직접 확인", "개인정보·비밀번호·계정 정보·회사 기밀을 입력하지 말라고", "응답에는 제목/라벨/내용 외의 설명"):
            self.assertIn(fragment, lines)
        self.assertTrue(all(isinstance(line, str) and line for line in PROFILE["prompt_extra"]))

    def test_the_expansion_prompt_asks_for_the_same_seventy_thirty_mix_and_names_the_excluded_areas(self):
        template = PROFILE["topic_expand_prompt"]
        for placeholder in ("{n}", "{avoid}", "{min}", "{max}"):
            self.assertIn(placeholder, template)
        for fragment in ("약 70%", "약 30%", "AI·디지털 도구", "집·살림", "질병·치료·약·보충제·진단·임신·영유아·체중 감량", "법률·세금·대출·투자·보험",
                         "가격·요금제·무료 한도", "홍보·순위 비교", "JSON 문자열 배열"):
            self.assertIn(fragment, template)
        text = topics.expand_prompt(PROFILE, ["이미 쓴 주제 하나"], 8)
        self.assertNotRegex(text, r"\{(?:n|avoid|min|max)\}")
        self.assertIn("- 이미 쓴 주제 하나", text)
        self.assertIn("8개", text)
        self.assertIn(f"{topics.TOPIC_MIN_CHARS}~{topics.TOPIC_MAX_CHARS}자", text)
        answer, model = stub_llm(text)                                                                     # 스텁이 이 지시문을 주제 확장으로 알아본다(JSON 문자열 배열)
        self.assertEqual(model, "stub")
        self.assertTrue(topics.parse_topic_list(answer))

    def test_the_expansion_prompt_gives_the_seventy_thirty_mix_in_its_opening_and_again_in_its_own_composition_line(self):
        """독립 검증 N7(변이 X22): '약 70%'·'약 30%' 는 첫 문장에도 있어서 위 시험은 `구성:` 줄을 통째로 지워도 통과했다. 비율을 직접 지시하는 줄을 따로 고정한다."""
        lines = PROFILE["topic_expand_prompt"].splitlines()
        self.assertRegex(lines[0], r"AI·디지털 도구 활용법\(약 70%\)과 집·살림 정리 습관\(약 30%\)")
        composition = [line for line in lines if line.startswith("구성:")]
        self.assertEqual(len(composition), 1, lines)
        self.assertRegex(composition[0], r"^구성: AI·디지털 도구 활용 주제를 약 70%, 집·살림\(정리·수납·청소 순서, 절약·계획 습관, 계절 점검 체크리스트\) 주제를 약 30%로 섞는다\.$")
        self.assertLess(lines.index(composition[0]), next(index for index, line in enumerate(lines) if line.startswith("조건:")))      # 조건(제외 범위)보다 앞에서 구성을 정한다

    def test_the_expansion_stub_answers_pass_the_same_topic_filter_as_seeds(self):
        picked = topics.pick_topic(PROFILE, [{"topic": seed, "date": "2026-10-20"} for seed in SEEDS], datetime.date(2026, 10, 21), [], random.Random(1), llm=stub_llm)
        self.assertEqual(picked[1], "llm")
        self.assertTrue(gates.topic_allowed(picked[0], PROFILE))


class SeedTest(unittest.TestCase):
    AI_WORDS = ("AI", "챗봇", "번역", "요약", "스마트폰", "PC", "비밀번호", "계정", "인증", "파일", "메모", "메일", "문자", "캘린더", "스프레드시트", "사진", "브라우저", "화상", "와이파이", "앱", "알림", "도구")
    HOME_WORDS = ("현관", "냉장고", "욕실", "옷장", "가계부", "장보기", "전등", "베란다", "서랍", "택배")

    def test_there_are_36_seeds_26_for_ai_and_digital_tools_and_10_for_the_home(self):
        self.assertEqual(len(SEEDS), 36)
        self.assertEqual(PROFILE["_seed_mix"], {"AI·디지털 도구": 26, "집·살림": 10})
        self.assertEqual(len(set(SEEDS)), 36)
        for seed in SEEDS[:26]:
            self.assertTrue(any(word in seed for word in self.AI_WORDS), seed)
            self.assertFalse(any(word in seed for word in self.HOME_WORDS), seed)
        for seed in SEEDS[26:]:
            self.assertTrue(any(word in seed for word in self.HOME_WORDS), seed)
        self.assertAlmostEqual(26 / 36, 0.72, delta=0.03)                                                    # 70:30 안팎

    def test_every_seed_is_35_to_55_characters_and_inside_the_topic_range_the_picker_accepts(self):
        for seed in SEEDS:
            self.assertTrue(35 <= len(seed) <= 55, f"{len(seed)}자: {seed}")
            self.assertTrue(topics.TOPIC_MIN_CHARS <= len(seed) <= topics.TOPIC_MAX_CHARS, seed)
            self.assertEqual(seed, topics.clean_topic(seed))                                                   # 정리해도 바뀌지 않는다

    def test_every_seed_passes_the_topic_guardrail_and_the_registry_checks_it(self):
        for seed in SEEDS:
            self.assertTrue(gates.topic_allowed(seed, PROFILE), seed)
            self.assertEqual(gates.first_match(PROFILE["banned_topic_patterns"], seed), (None, None), seed)
            self.assertIsNone(gates.matches_any(PROFILE["banned_patterns"], seed), seed)                       # 시드가 제목이 돼도 단정·광고·링크 낱말이 없다
            self.assertIsNone(gates.matches_any(PROFILE["leak_patterns"], seed), seed)
        broken = copy.deepcopy(PROFILE)
        broken["seed_topics"] = SEEDS + ["대출 금리 비교하는 방법과 순서를 알아보기"]
        self.assertTrue(any("seed_topics" in error and "banned_topic_patterns" in error for error in registry.validate_profile(broken)))

    def test_no_seed_contains_a_price_a_link_a_first_person_word_or_an_experience_claim(self):
        for seed in SEEDS:
            self.assertNotRegex(seed, r"\d[\d,]*\s*(?:원|달러)|https?://|www\.|저는|제가|써\s*봤|해\s*본\s*결과", seed)

    def test_seeds_do_not_collide_with_each_other_or_with_the_other_blogs_topics(self):
        """주제 선정은 다른 블로그 제목과 other_blogs(0.6) 이상 비슷하면 그 시드를 건너뛴다 — 시드가 조용히 한 번도 안 뽑히는 일이 없어야 한다."""
        threshold = PROFILE["similarity"]["other_blogs"]
        for index, seed in enumerate(SEEDS):
            for other in SEEDS[index + 1:]:
                self.assertLess(gates.similarity(seed, other), threshold, (seed, other))
        existing = list(EN["seed_topics"]) + list(BASE["seed_topics"])
        for path in ("history.json", "blogger_history.json"):
            existing += entry_titles(read_json_list(REAL / path))
        for seed in SEEDS:
            score, nearest = gates.most_similar(seed, existing)
            self.assertLess(score, threshold, (seed, nearest))
        for seed in SEEDS:                                                                                  # 그래서 빈 이력에서도 모든 시드를 뽑을 수 있다
            self.assertTrue(topics._acceptable(seed, PROFILE, [], datetime.date(2026, 10, 21), existing), seed)

    def test_the_seeds_are_not_translations_of_the_english_blogs_seeds(self):
        """영문(macat0722)과 번역·복제를 하지 않는다(작업요청서 §3-4): 영문 시드의 한국어 대응(수면·스트레칭·호흡·야식 같은 생활 습관)과 겹치는 낱말이 없다."""
        habit_words = ("수면", "잠", "스트레칭", "호흡", "야식", "산책", "물 자주", "카페인", "배달 음식", "목과 어깨", "20-20-20", "다이어트")
        for seed in SEEDS:
            self.assertFalse(any(word in seed for word in habit_words), seed)

    def test_the_picker_chooses_only_from_these_seeds_and_covers_all_of_them(self):
        seen = set()
        for number in range(400):
            topic, source = topics.pick_topic(PROFILE, [], datetime.date(2026, 10, 21), [], random.Random(number))
            self.assertEqual(source, "seed")
            seen.add(topic)
        self.assertEqual(seen, set(SEEDS))


class GateTest(unittest.TestCase):
    def test_the_stub_post_passes_for_every_seed(self):
        for seed in SEEDS:
            post, stats = good_post(seed)
            self.assertEqual(codes_of(post, stats), [], seed)
            self.assertLessEqual(len(post["title"]), PROFILE["title"]["max_chars"], seed)

    def test_there_are_at_least_forty_normal_sentences_and_none_is_flagged_by_any_body_rule(self):
        self.assertGreaterEqual(len(NORMAL_SENTENCES), 40)
        for sentence in NORMAL_SENTENCES:
            with self.subTest(sentence=sentence):
                self.assertIsNone(gates.matches_any(PROFILE["banned_patterns"], sentence))
                self.assertIsNone(gates.matches_any(PROFILE["leak_patterns"], sentence))
                self.assertEqual(gates.body_risk_hit(sentence, PROFILE), (None, None))

    def test_a_normal_sentence_inside_a_full_post_never_turns_it_down(self):
        for sentence in NORMAL_SENTENCES:
            post, stats = good_post(sentence=sentence)
            self.assertEqual(codes_of(post, stats), [], sentence)

    def test_normal_titles_pass_and_the_security_words_are_not_collateral_damage(self):
        for title in NORMAL_TITLES:
            post, stats = good_post(title=title)
            self.assertEqual(codes_of(post, stats), [], title)
        self.assertTrue(any("비밀번호" in title for title in NORMAL_TITLES) and any("감염" in title for title in NORMAL_TITLES) and any("ToDo" in title for title in NORMAL_TITLES))

    def test_every_bad_body_sample_is_caught_by_the_list_it_belongs_to(self):
        self.assertGreaterEqual(len(BAD_BODY), 50)
        for sentence, where in BAD_BODY:
            with self.subTest(sentence=sentence):
                got = {"BANNED": gates.matches_any(PROFILE["banned_patterns"], sentence), "LEAK": gates.matches_any(PROFILE["leak_patterns"], sentence),
                       "BODY": gates.body_risk_hit(sentence, PROFILE)[0]}[where]
                self.assertIsNotNone(got)

    def test_every_bad_body_sample_turns_a_whole_post_down_with_the_matching_reason(self):
        reason = {"BANNED": "BANNED", "LEAK": "LEAK", "BODY": "BODY_TOPIC"}
        for sentence, where in BAD_BODY:
            with self.subTest(sentence=sentence):
                post, stats = good_post(sentence=sentence)
                self.assertIn(reason[where], codes_of(post, stats))

    def test_every_bad_title_is_turned_down(self):
        reason = {"TITLE_BANNED": "TITLE_BANNED", "TITLE_TOPIC": "TITLE_TOPIC", "BANNED": "BANNED", "LEAK": "LEAK"}
        for title, where in BAD_TITLES:
            with self.subTest(title=title):
                post, stats = good_post(title=title)
                self.assertIn(reason[where], codes_of(post, stats))

    def test_a_banned_label_turns_the_post_down(self):
        for label in ("주식 투자", "세금", "대출", "다이어트", "저작권", "재테크"):
            post, stats = good_post(labels=["AI 활용", label])
            self.assertIn("LABELS", codes_of(post, stats), label)
        post, stats = good_post(labels=["AI 활용", "디지털 정리", "집 정리"])
        self.assertEqual(codes_of(post, stats), [])

    def test_a_post_with_links_is_turned_down_even_when_the_sanitizer_already_stripped_the_tags(self):
        """allow_links 가 false 라 <a> 는 정화 단계에서 벗겨진다(글자만 남음). 주소를 글자로 쓴 글은 banned_patterns 가 탈락시킨다 — 어떤 링크도 글에 남지 않는다."""
        raw = gates.parse_labeled_post(stub_post(SEEDS[0]))["content"].replace("</p>", ' <a href="https://example.com/x">여기</a></p>', 1)
        clean, stats = gates.sanitize_html(raw, allow_links=False)
        self.assertEqual(stats["links_removed"], 1)
        self.assertNotIn("<a", clean)
        post = {"title": "AI 챗봇에게 질문하는 방법 5가지", "labels": ["AI 활용"], "content": clean}
        self.assertEqual(gates.check_post(post, PROFILE, [], [], stats).codes(), [])                       # 태그만 벗겨진 글은 링크가 없다
        with_text = gates.parse_labeled_post(stub_post(SEEDS[0]))["content"].replace("</p>", ' <a href="https://example.com/x">https://example.com/x</a></p>', 1)
        clean, stats = gates.sanitize_html(with_text, allow_links=False)
        self.assertIn("BANNED", gates.check_post({"title": "AI 챗봇에게 질문하는 방법 5가지", "labels": ["AI 활용"], "content": clean}, PROFILE, [], [], stats).codes())

    def test_the_other_blogs_addresses_are_refused_as_text(self):
        for address in ("macat0722.blogspot.com", "https://macat0722.blogspot.com/", "shine88pc.github.io/chanceblog/", "kcyoon.blogspot.com"):
            post, stats = good_post(sentence=f"{address} 도 읽어 보세요.")
            self.assertIn("BANNED", codes_of(post, stats), address)

    def test_the_language_check_wants_korean(self):
        post, stats = good_post()
        english = {"title": "A calm evening routine for better sleep", "labels": ["habits"],
                   "content": gates.sanitize_html(gates.parse_labeled_post(stub_post_en("A calm routine"))["content"])[0]}
        self.assertIn("LANG", codes_of(english))
        self.assertNotIn("LANG", codes_of(post, stats))

        def swap_every(step):
            """한글 글자를 step 번째마다 영문 글자로 바꾼다(한글 비율이 얼마나 남는지 정확히 정한다)."""
            seen = [0]

            def swap(match):
                seen[0] += 1
                return "x" if seen[0] % step == 0 else match.group(0)
            return dict(post, content=re.sub(r"[가-힣]", swap, post["content"]))
        self.assertIn("LANG", codes_of(swap_every(2)))                                                    # 한글 약 50% < 60%
        self.assertNotIn("LANG", codes_of(swap_every(5)))                                                 # 한글 약 80% ≥ 60%
        self.assertEqual(PROFILE["min_hangul_ratio"], 0.6)

    def test_structure_length_and_labels_are_still_checked(self):
        post, stats = good_post()
        short = dict(post, content="<p>너무 짧아요</p>")
        self.assertTrue({"LEN_SHORT", "STRUCT_H3", "STRUCT_LIST"} <= set(codes_of(short)))
        longer = dict(post, content=post["content"] + "<p>" + "가나다라 " * 800 + "</p>")
        self.assertIn("LEN_LONG", codes_of(longer))
        self.assertIn("LABELS", codes_of(dict(post, labels=[])))
        self.assertIn("LABELS", codes_of(dict(post, labels=["가" * 21])))
        self.assertIn("TITLE_LEN", codes_of(dict(post, title="짧아")))

    def test_a_title_like_another_blogs_title_is_turned_down_from_both_sides(self):
        english_side = ["AI 챗봇에게 질문할 때 답이 더 정확해지는 입력 요령"]
        post, stats = good_post(title="AI 챗봇에게 질문할 때 답이 더 정확해지는 입력 요령")
        self.assertIn("DUP_OTHER", codes_of(post, stats, other=english_side))
        self.assertNotIn("DUP_OTHER", codes_of(post, stats, other=["A calm evening routine for better sleep"]))
        self.assertIn("DUP_SAME", codes_of(post, stats, recent=english_side))

    def test_the_cross_check_reads_the_other_blogs_histories_in_both_directions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reg = registry.load_registry(REAL / "pipeline" / "blogs.json")
            blogs = [registry.merged_blog(reg, raw) for raw in reg["blogs"]]
            (root / "history.json").write_text(json.dumps([{"kr_title": "크로니클 한 편", "en_title": "A Chance Piece"}], ensure_ascii=False), encoding="utf-8")
            (root / "blogger_history.json").write_text(json.dumps([{"title": "A Gentle Evening Routine"}], ensure_ascii=False), encoding="utf-8")
            (root / "blogger_ko_history.json").write_text(json.dumps([{"title": "비밀번호 관리자 시작하기"}], ensure_ascii=False), encoding="utf-8")
            korean_sees = other_blog_titles(root, blogs, "blogger_kcyoon")
            english_sees = other_blog_titles(root, blogs, "blogger_macat")
        self.assertIn("A Gentle Evening Routine", korean_sees)
        self.assertIn("크로니클 한 편", korean_sees)
        self.assertNotIn("비밀번호 관리자 시작하기", korean_sees)                         # 자기 이력은 빠진다(자기 중복은 DUP_SAME 이 따로 본다)
        self.assertIn("비밀번호 관리자 시작하기", english_sees)                           # 영문이 한글 이력도 본다
        self.assertNotIn("A Gentle Evening Routine", english_sees)


class ExemptionStructureTest(unittest.TestCase):
    """전문가 상담·면책 문장은 건너뛰고 나머지에서 위험 표현을 찾는 구조(절 단위)가 법률·세금·금융·투자에도 같게 작동한다."""

    def hit(self, text):
        return gates.body_risk_hit(text, PROFILE)[0]

    def test_a_consultation_sentence_is_exempt_for_every_profession(self):
        for sentence in ("세금 문제는 세무사와 상담하세요.", "계약이 걱정되면 변호사에게 문의하세요.", "투자 권유가 아닙니다.", "법률 자문이 아닙니다.",
                         "대출이 필요하면 금융 전문가와 상담해 보세요.", "혈압이 걱정되면 의사와 상담하세요."):
            self.assertIsNone(self.hit(sentence), sentence)

    def test_advice_followed_by_a_consultation_phrase_in_one_sentence_is_still_turned_down(self):
        """위험한 권유 뒤에 상담 구절을 붙인 문장이 통째로 면제되면 안 된다(D-64 ⑥ a) — 법률·금융에도 같다."""
        for sentence in ("주식 투자 종목을 추천하지만 먼저 세무사와 상담하세요.", "대출 금리가 낮은 곳을 고르지만 전문가와 상담하세요.",
                         "혈압을 낮추는 방법이지만 먼저 의사와 상담하세요."):
            self.assertIsNotNone(self.hit(sentence), sentence)

    def test_the_base_medical_exemption_still_works_exactly_like_before(self):
        for sentence in ("진단이나 치료를 대신하지 않습니다.", "의학적 조언이 아닙니다.", "건강 고민은 의사·약사와 상담하세요."):
            self.assertIsNone(self.hit(sentence), sentence)
        self.assertIsNotNone(self.hit("보충제를 먹으면 잠이 잘 와요."))
        self.assertIsNone(gates.body_risk_hit("10분 투자해서 정리해 보세요.", PROFILE)[0])


class RuleTableTest(unittest.TestCase):
    """이 블로그가 더하거나 좁힌 규칙마다 그 규칙만 표본을 잡는지: 걸려야 하는 표본은 '처음 걸린 규칙'이 바로 그 규칙이고, 걸리면 안 되는 표본에는 그 규칙이 맞지 않는다."""
    LISTS = {"banned": PROFILE["banned_patterns"], "title": PROFILE["title_banned_patterns"], "leak": PROFILE["leak_patterns"],
             "topic": PROFILE["banned_topic_patterns"], "body": PROFILE["body_banned_patterns"]}

    def owner(self, group, snippet):
        patterns = self.LISTS[group]
        owners = [p for p in patterns if p == snippet[1:]] if snippet.startswith("=") else [p for p in patterns if snippet in p]
        return owners

    def test_the_table_is_big_enough_and_each_snippet_names_exactly_one_rule(self):
        self.assertGreaterEqual(len(RULES), 70)
        for group, snippet, positives, negatives in RULES:
            self.assertEqual(len(self.owner(group, snippet)), 1, (group, snippet))
            self.assertTrue(positives and negatives, (group, snippet))

    def test_each_rule_catches_its_positives_first_and_ignores_its_negatives(self):
        for group, snippet, positives, negatives in RULES:
            rule = self.owner(group, snippet)[0]
            rx = re.compile(rule, re.IGNORECASE)
            for sample in positives:
                first, _word = gates.first_match(self.LISTS[group], sample)
                self.assertEqual(first, rule, f"[{group}] {sample!r}: 처음 걸린 규칙이 다름({first!r} / 기대 {snippet!r})")
            for sample in negatives:
                self.assertIsNone(rx.search(gates._normalized(sample)), f"[{group}] {snippet!r} 가 걸리면 안 되는 표본: {sample!r}")

    def test_every_new_or_narrowed_rule_is_in_the_table(self):
        """표에 없는 새 규칙이 조용히 생기지 않게: 기본 프로필에 없던 규칙은 모두 표의 어떤 규칙이다(주제·본문의 법률·금융 목록은 아래 두 시험이 따로 본다)."""
        in_table = {rule for group, snippet, _p, _n in RULES for rule in self.owner(group, snippet)}
        for group, base_key in (("banned", "banned_patterns"), ("title", "title_banned_patterns"), ("leak", "leak_patterns")):
            added = set(PROFILE[base_key]) - set(BASE[base_key])
            self.assertEqual(added - in_table, set(), group)

    def test_the_legal_and_financial_topic_words_are_in_both_the_topic_and_the_body_lists(self):
        extra_topic = [p for p in PROFILE["banned_topic_patterns"] if p not in BASE["banned_topic_patterns"]]
        extra_body = [p for p in PROFILE["body_banned_patterns"] if p not in BASE["body_banned_patterns"]]
        self.assertEqual(extra_topic, extra_body)                                  # 주제·제목·라벨에 거는 것과 본문에 거는 것이 같은 낱말 묶음이다
        self.assertEqual(len(extra_topic), 8)                                       # 좁힌 감염 한 개 + 법률·세금·대출·투자·보험·주거 계약 일곱 개
        joined = "|".join(extra_topic)
        for word in ("법률", "소송", "변호사", "저작권", "세금", "연말", "대출", "금리", "주식", "코인", "재테크", "보험", "전세", "보증금", "임대차"):
            self.assertIn(word, joined)

    def test_legal_and_financial_advice_is_turned_down_in_the_body_too(self):
        for sentence in ("저작권 침해로 소송이 걸릴 수 있어요.", "세금을 줄이려면 이 앱에 영수증을 올려 보세요.", "대출 금리가 낮은 곳을 비교해 보세요.",
                         "주식 투자 종목을 AI에게 추천받아 보세요.", "비트코인 수익률을 확인하는 앱을 소개합니다.", "보험료를 아끼려면 가입 상품을 정리해 보세요.",
                         "전세 보증금을 돌려받는 순서를 알려 드릴게요."):
            self.assertIsNotNone(gates.body_risk_hit(sentence, PROFILE)[0], sentence)

    def test_the_security_words_the_blog_needs_are_not_blocked(self):
        for sentence in ("악성코드에 감염되면 파일이 열리지 않을 수 있어요.", "바이러스에 감염된 의심 파일은 열지 마세요.", "피싱을 예방하려면 링크를 누르기 전에 주소를 확인하세요."):
            self.assertEqual(gates.body_risk_hit(sentence, PROFILE), (None, None), sentence)
            self.assertIsNone(gates.matches_any(PROFILE["banned_patterns"], sentence), sentence)
        self.assertIsNotNone(gates.body_risk_hit("독감에 감염된 사람과 접촉했다면 쉬세요.", PROFILE)[0])


PROMPT_KO = ".github/editorial/BLOGGER_PROMPT_KO_AI.md"
PROMPT_EN = ".github/editorial/BLOGGER_PROMPT_EN.md"
# 모델에 가는 `text` 블록의 번호 규칙마다 '그 규칙이 말해야 하는 것'. 규칙 줄(하위 목록 포함)에 이 조각이 모두 있어야 한다 — 규칙 하나를 지우거나 뜻을 바꾸면 여기서 걸린다.
PROMPT_RULES = {
    1: ("톤:", "차분하고 친근한 존댓말", "광고·홍보 말투는 쓰지 않는다"),
    2: ("글 길이:", "1,200~2,000자"),
    3: ("반드시 포함할 구조", "도입:", "2~4문장", "본론:", "3~5개", "<h3> 소제목", "점검 목록:", "<ul> 목록", "마무리:", "질문 하나"),
    4: ("경험을 지어내지 않는다:", '"써 봤더니"', '"직접 해 본 결과"', "개인 경험·수치·벤치마크·인터뷰·사용자 후기·전문가의 말·연구 결과를 쓰지 않는다", "저는·제가", "~해 보세요"),
    5: ("자주 바뀌는 사실은 단정하지 않는다", "가격, 요금제, 무료 한도, 기능 이름, 메뉴 위치, 버전", "직접 확인하는 방법"),
    6: ("홍보하거나 순위를 매기거나 구매·가입을 권하지 않는다", "챗봇, 번역기, 메모 앱"),
    7: ("건강·의료(질병, 치료, 약, 보충제, 진단, 임신, 영유아, 체중 감량)", "법률·세금·대출·투자·보험", "경고나 조언으로도 쓰지 않는다"),
    8: ("AI의 답이 틀릴 수 있으니 중요한 내용은 직접 확인하라고 안내", "개인정보·비밀번호·계정 정보·회사 기밀을 입력하지 말라고"),
    9: ("링크, 웹 주소, 이메일 주소, 이미지, 표를 넣지 않는다",),
    10: ("면책·고지 문장은 쓰지 않는다",),
    11: ("제목:", "20~45자", "\"충격\"", "\"TOP 5\"", "후기"),
    12: ("라벨:", "3개 내외"),
}


def prompt_template(relative=PROMPT_KO):
    """러너가 읽는 그대로(`text` 코드 블록) — 모델에 실제로 가는 글이다."""
    return run_mod.load_prompt_template(REAL, {"prompt": relative})


def numbered_rules(template):
    """{번호: 규칙 글(들여 쓴 하위 줄 포함)}."""
    rules, current = {}, None
    for line in template.splitlines():
        match = re.match(r"^(\d{1,2})\. ", line)
        if match:
            current = int(match.group(1))
            rules[current] = line
        elif current is not None and line.startswith(" "):
            rules[current] += "\n" + line
        else:
            current = None
    return rules


def output_format_markers(template):
    """`출력 형식`/`Output format` 블록이 모델에게 요구하는 머리표 [(머리표, 그 줄의 나머지)] — 줄 맨 앞 `이름:` 모양만."""
    start = max(template.find("출력 형식"), template.find("Output format"))
    assert start >= 0, "출력 형식 블록이 없습니다"
    return re.findall(r"^([^\s:]+):[ \t]*(.*)$", template[start:], re.M)


class PromptFileTest(unittest.TestCase):
    """한글 프롬프트 파일(`BLOGGER_PROMPT_KO_AI.md`)의 `text` 블록은 모델에 가는 글이다. 영문 프롬프트는 몇 줄을 고정하는 시험이 있었지만 한글 프롬프트는 `{topic}` 자리표시자
    말고는 아무것도 지키지 않아 규칙 문장·머리·글 길이·구조·출력 머리표를 지워도 모든 시험이 통과했다(독립 검증 N7: P19·X24~X27·Y01~Y07). 규칙마다 말해야 하는 것을 고정하고,
    프롬프트가 요구하는 머리표·범위가 러너의 파서와 프로필 게이트가 받아들이는 것과 같은지 대조한다."""

    def setUp(self):
        self.template = prompt_template()
        self.rules = numbered_rules(self.template)
        self.blog = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), "blogger_kcyoon")

    def test_the_registry_points_at_this_prompt_and_the_runner_accepts_it(self):
        self.assertEqual(self.blog["prompt"], PROMPT_KO)
        self.assertEqual(self.template.count("{topic}"), 1)
        self.assertIn("\n주제: {topic}\n", self.template)
        self.assertNotIn("{{", self.template)

    def test_the_head_names_the_korean_channel_exactly_as_the_registry_labels_it(self):
        first = next(line for line in self.template.splitlines() if line.strip())
        self.assertEqual(first, f"[대상: {self.blog['channel']['label']}]")
        self.assertEqual(first, "[대상: Blogger 한글]")

    def test_the_twelve_numbered_rules_are_all_there_in_order(self):
        self.assertEqual(list(self.rules), list(range(1, 13)))
        self.assertIn("작성 규칙:", self.template)

    def test_each_rule_still_says_what_it_is_for(self):
        for number, fragments in PROMPT_RULES.items():
            for fragment in fragments:
                with self.subTest(rule=number, fragment=fragment):
                    self.assertIn(fragment, self.rules[number])

    def test_the_numbers_the_prompt_asks_for_fit_inside_what_the_profile_gate_accepts(self):
        """프롬프트가 요구하는 글 길이·제목 길이·소제목 수·라벨 수가 프로필 게이트 범위 안이다(예전 변이: 글 길이 100~200자·제목 100자·라벨 20개가 모두 통과했다)."""
        low, high = (int(value.replace(",", "")) for value in re.search(r"글 길이: ([\d,]+)~([\d,]+)자", self.rules[2]).groups())
        self.assertTrue(PROFILE["length"]["min_chars"] <= low < high <= PROFILE["length"]["max_chars"], (low, high, PROFILE["length"]))
        low, high = (int(value) for value in re.search(r"제목: (\d+)~(\d+)자", self.rules[11]).groups())
        self.assertTrue(PROFILE["title"]["min_chars"] <= low < high <= PROFILE["title"]["max_chars"], (low, high, PROFILE["title"]))
        low, high = (int(value) for value in re.search(r"단계 (\d+)~(\d+)개", self.rules[3]).groups())
        self.assertTrue(low >= PROFILE["structure"]["min_h3"] and low <= high, (low, high, PROFILE["structure"]))      # 소제목이 게이트의 최소(3개)를 채운다
        self.assertIs(PROFILE["structure"]["require_list"], True)
        self.assertRegex(self.rules[3], r"점검 목록:.*<ul>")                                                             # 게이트가 요구하는 목록(<ul>)을 프롬프트도 요구한다
        count = int(re.search(r"라벨: (\d+)개 내외", self.rules[12]).group(1))
        self.assertTrue(PROFILE["labels"]["min"] <= count <= PROFILE["labels"]["max"], (count, PROFILE["labels"]))

    def test_the_output_format_asks_for_the_markers_the_runner_parser_reads(self):
        """모델이 프롬프트대로 답하면 러너의 파서(`gates.parse_labeled_post`)가 읽을 수 있어야 한다 — 머리표가 어긋나면(예: `제목:` → `T:`) 매번 형식 오류로 재작성 3회 끝에 탈락한다(독립 검증 Y06)."""
        markers = output_format_markers(self.template)
        self.assertEqual([name for name, _rest in markers], list(gates._MARKER_SETS[0][0]))          # 제목:/라벨:/내용: — 파서가 먼저 보는 머리표 묶음
        lines = self.template.splitlines()
        self.assertTrue(lines[lines.index("내용:") + 1].startswith("(HTML"))                          # 머리표 다음 줄이 본문 형식 안내(HTML)다

    def test_an_answer_written_exactly_in_the_format_the_prompt_asks_for_parses(self):
        (title_marker, _), (labels_marker, _), (content_marker, _) = output_format_markers(self.template)
        answer = f"{title_marker}: 샘플 제목입니다\n{labels_marker}: 라벨하나, 라벨둘, 라벨셋\n{content_marker}:\n<p>본문 문단입니다.</p>\n<h3>소제목</h3>\n<ul><li>항목</li></ul>"
        self.assertEqual(gates.parse_labeled_post(answer),
                         {"title": "샘플 제목입니다", "labels": ["라벨하나", "라벨둘", "라벨셋"], "content": "<p>본문 문단입니다.</p>\n<h3>소제목</h3>\n<ul><li>항목</li></ul>"})

    def test_the_english_prompt_asks_for_markers_the_same_parser_reads_too(self):
        """같은 대조를 영문 프롬프트에도: 두 프롬프트의 머리표가 모두 파서가 아는 묶음 중 하나다."""
        template = prompt_template(PROMPT_EN)
        markers = output_format_markers(template)
        self.assertEqual([name for name, _rest in markers], list(gates._MARKER_SETS[1][0]))
        (title_marker, _), (labels_marker, _), (content_marker, _) = markers
        parsed = gates.parse_labeled_post(f"{title_marker}: A sample title\n{labels_marker}: one, two\n{content_marker}:\n<p>Body.</p>")
        self.assertEqual((parsed["title"], parsed["labels"], parsed["content"]), ("A sample title", ["one", "two"], "<p>Body.</p>"))

    def test_the_helper_finds_a_changed_marker(self):
        """대조 도우미가 헛돌지 않는다: 머리표를 바꾼 틀에서는 이름이 달라지고 그 틀대로 쓴 답은 파싱되지 못한다."""
        broken = self.template.replace("제목: (제목)", "T: (제목)")
        self.assertNotEqual([name for name, _rest in output_format_markers(broken)], list(gates._MARKER_SETS[0][0]))
        (title_marker, _), (labels_marker, _), (content_marker, _) = output_format_markers(broken)
        with self.assertRaises(gates.GateError):
            gates.parse_labeled_post(f"{title_marker}: 제목\n{labels_marker}: 가, 나\n{content_marker}:\n<p>본문</p>")

    def test_the_prompt_file_says_only_the_same_language_check_is_in_code_and_the_operator_checks_the_rest(self):
        """독립 검증 N2: 예전 문장('제목은 서로의 이력과 비교해 비슷하면 탈락한다')은 번역·복제 금지를 코드가 보장하는 것처럼 읽혔다. 제목 유사도는 같은 언어 안에서만 걸린다."""
        text = (REAL / PROMPT_KO).read_text(encoding="utf-8")
        line = next(line for line in text.splitlines() if line.startswith("- 같은 글을 영문·한글로 옮겨 올리지 않는다"))
        for fragment in ("코드가 막는 것은 같은 언어 안의 제목 중복뿐이다", "`DUP_OTHER`", "코드가 못 잡는다", "눈으로 확인한다"):
            self.assertIn(fragment, line)
        self.assertNotIn("제목은 서로의 이력과 비교해 비슷하면(`DUP_OTHER`) 탈락한다.", text)
        section_6 = text[text.index("## 6."):text.index("## 7.")]
        item_7 = next(line for line in section_6.splitlines() if line.startswith("7. "))
        for fragment in ("영문 블로그(macat0722)", "번역·복제", "눈으로 확인", "같은 언어 안에서만"):
            self.assertIn(fragment, item_7)
        self.assertIn("같은 언어 안에서만 걸리므로", text[text.index("## 7."):])                           # 7. 사용 시 주의사항의 '게이트가 제목 유사도로도 막는다'도 같은 한계를 말한다
        self.assertIn("영문 글의 번역·복제는 코드가 못 잡아 운영자가 확인한다", text[:text.index("## 1.")])

    def test_the_operator_docs_carry_the_same_limit(self):
        def read(relative):
            return (REAL / relative).read_text(encoding="utf-8")
        architecture = read("docs/ARCHITECTURE.md")
        self.assertIn("**영문 글의 번역·복제는 코드가 못 잡는다**", architecture)
        self.assertIn("글자 유사도라 같은 언어 안에서만 걸린다", architecture)
        self.assertIn("문자열 비교라 같은 언어 안의 중복만 막는다", architecture)
        self.assertIn("같은 언어 안에서만", next(line for line in read("docs/SECURITY_GUARDRAILS.md").splitlines() if line.startswith("| G-C5 ")))
        self.assertIn("영문 블로그(macat0722)의 글을 번역·복제한 글이 아닌지", next(line for line in read("docs/ACTIONS_GUIDE.md").splitlines() if line.startswith("| 6 | 초안 1건을 Blogger 초안함")))
        self.assertIn("번역·복제", next(line for line in read("HANDLER.md").splitlines() if line.startswith("| 한글 Blogger `blogger_kcyoon`")))

    def test_the_measurement_the_docs_rely_on_still_holds(self):
        """문서의 '번역 제목은 유사도가 대체로 0.2 이하'가 실제 유사도 함수로 맞는지 — 영·한 번역 쌍은 탈락 기준(0.6)에 한참 못 미치고, 같은 언어의 거의 같은 제목은 걸린다."""
        pairs = (("A Gentle Evening Routine for Better Sleep", "더 나은 수면을 위한 차분한 저녁 루틴"), ("5 Small Habits for a Calmer Morning", "더 차분한 아침을 위한 작은 습관 5가지"),
                 ("How to Ask an AI Chatbot Better Questions", "AI 챗봇에게 더 나은 질문을 하는 방법"), ("Organize Your Phone Photos by Date and Album", "스마트폰 사진을 날짜와 앨범으로 정리하는 방법"),
                 ("Turn On Two-Step Verification for Your Account", "계정의 2단계 인증을 켜는 방법"), ("A Simple Weekly Bathroom Cleaning Plan", "간단한 주간 욕실 청소 계획"))
        limit = PROFILE["similarity"]["other_blogs"]
        for english, korean in pairs:
            with self.subTest(english):
                self.assertLess(gates.similarity(english, korean), 0.25)
                self.assertNotIn("DUP_OTHER", codes_of(good_post(korean)[0], other=[english]))        # 번역 제목은 교차 중복 검사를 그냥 지나간다
        near = ("AI 챗봇에게 더 정확한 답을 받는 질문 요령 5가지", "AI 챗봇에게 더 정확한 답을 받는 질문 요령 다섯 가지")
        self.assertGreaterEqual(gates.similarity(*near), limit)                                       # 같은 언어에서는 걸린다
        self.assertIn("DUP_OTHER", codes_of(good_post(near[0])[0], other=[near[1]]))

    def test_the_prompt_and_its_extra_rules_do_not_contradict_each_other_on_the_html_tags(self):
        """프롬프트(본문 HTML 태그 목록)와 프로필 `prompt_extra`(허용 태그)가 같은 태그를 허용한다 — 한쪽만 고치면 모델이 받는 지시가 어긋난다."""
        allowed_in_extra = set(re.findall(r"\b(p|h3|ul|ol|li|strong|em|br)\b", re.search(r"허용 태그는 ([^.]*?) 뿐이다", "\n".join(PROFILE["prompt_extra"])).group(1)))
        in_prompt = set(re.findall(r"<(\w+)>", re.search(r"\(HTML 형식\. ([^)]*)\)", self.template).group(1)))
        self.assertTrue(in_prompt <= allowed_in_extra, (in_prompt, allowed_in_extra))                # 프롬프트가 권하는 태그는 모두 허용 태그다
        self.assertEqual(in_prompt, {"p", "h3", "ul", "li", "strong", "em"})


if __name__ == "__main__":
    unittest.main()
