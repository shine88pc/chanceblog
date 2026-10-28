---
id: R-015
kind: decision
title: 영문 Blogger(macat0722) 인증 통과 — 초안함 업로드(draft)로 켤까요? (T3)
summary: 영문 Blogger 인증 점검이 통과했습니다(블로그 주소 일치). 켜려면 승인이 필요합니다: 일상 습관 팁 영문 글(주제 34개·친근한 실용 톤·의료·건강 주장 금지) + mode draft(글은 Blogger 초안함에만 올라가고 공개는 직접). 승인 A 로 이대로 켜기, 고칠 점은 보류+메모, 광고는 계속 끕니다.
urgency: 보통
created: 2026-10-28
---

# R-015 · 영문 Blogger(macat0722) 켜기 결정 (T3)

## 결과
- 영문 인증 점검(실행 #40698028320)이 **통과**했습니다 — 토큰 갱신, 블로그 조회, 블로그 주소 일치를 확인했습니다(쓰기 없음). 앱 게시와 시크릿 덮어쓰기가 제대로 됐습니다. 고맙습니다.
- 이제 **켜는 일**(T3 승인)만 남았습니다.

## 켜면 일어나는 일 (`mode: draft`)
- 매일 **11:00(KST)에 글 1편**(하루 상한 1건)을 만들어 **Blogger 초안함에만** 올립니다. **공개는 사용자님이 Blogger 화면에서 직접** 합니다(자동 공개 아님, `auto` 는 별도 승인).
- 같은 글이 저장소 `_blogger_drafts/` 에 남고, 이력은 `blogger_history.json` 에 남습니다(이 파일은 사이트에 공개되지 않게 이미 제외돼 있습니다).
- Gemini 무료 한도를 Chance·한글 Blogger 와 함께 씁니다(한도 관리 장치가 막아 줍니다).
- **광고는 계속 끕니다**(레지스트리 `ads: off`, Blogger 화면에서도 켜지 않기).

## 읽어 보실 것 (정책·톤)
1. **주제 34개**(`pipeline/profiles/blogger_practical_en.json`): 일상 습관·루틴 팁입니다. 예: "A calming wind-down routine for the hour before bed", "A one-minute breathing break for stressful moments", "An easy stretching routine you can do at home", "A 30-minute weekend home reset routine", "Ten-minute meal ideas using what's in your fridge", "How to keep a weekly planner you'll actually use". 같은 주제는 60일 안에 다시 쓰지 않습니다. 수면·스트레칭·호흡·식사처럼 건강과 겹쳐 보이는 일상 주제가 있어 **의료·치료 주장은 코드 가드레일이 막습니다**(아래 3). 마음에 걸리는 주제가 있으면 메모로 알려 주세요.
2. **글 모양**: 친근하고 실용적인 영어, 팁 목록 + 체크리스트, 소제목 3개 이상·목록 1개 이상, 길이 2,400~7,500자, 제목 15~70자. Chance 와 겹치지 않는 **완전히 다른 글**(Chance 는 분석, Blogger 는 "오늘 당장 실천")입니다.
3. **쓰지 않는 것**(프롬프트 + 코드 검사로 막음): 질병·약·보충제·용량·진단·혈압·혈당 같은 건강 수치·임신·영유아·체중 감량·다이어트·간 건강(경고 형태로도), "치료·예방·완치" 주장, 지어낸 개인 경험·연구·통계·전문가·인용, 링크·이미지·스크립트·표.
4. **모든 글 끝의 AI 고지**(자동으로 붙음): "This article was written and edited with the help of AI and shares general lifestyle information for reference only. It does not replace professional medical advice, diagnosis, or treatment. If you have a health concern, please talk to a doctor, pharmacist, or another qualified professional."
5. 실제 모델 글로는 **한 번도 시험하지 못했습니다**(그래서 초안함에서 직접 읽어 보시고 공개를 정하는 `draft` 로 시작합니다).

## 함께 알려 주시면 좋은 것 (선택 — 메모에 한 줄)
macat0722 구글 계정이 **Chance 블로그의 AdSense 계정과 같은 계정**입니까? 같다면 Blogger 쪽 정책 위반이 AdSense 계정에 영향을 줄 수 있어 **공개 전에 글을 읽는 일이 특히 중요**합니다(그래서 `draft` 로 시작합니다). 모르시면 "모름"이라고 적어도 됩니다.

## 승인 범위 (A 를 승인하시면 이것만)
1. `pipeline/blogs.json`: `blogger_macat` 의 `mode` 를 `off` → **`draft`**. (`auto`·광고·다른 블로그·프로필·프롬프트·시크릿은 건드리지 않습니다.)
2. 위 1~4 의 주제·톤·금지·고지문 **그대로**(수정 없이).
`_config.yml`(광고 표면)은 바꾸지 않습니다 — 영문 이력 파일은 이미 제외돼 있습니다.

## 선택지
| 선택 | 하는 일 |
|---|---|
| **A (추천)** | 이대로 켭니다(`draft`, 초안함 업로드만) |
| 보류 + 메모 | 고칠 점을 메모에 적어 주세요(예: 빼고 싶은 주제, 금지어 추가). 제가 고친 뒤 다시 묻습니다 |
| 거절 | 켜지 않습니다 |

## 답하는 법
[답하기] → `AI 요청에 답하기` 양식에서 요청 번호 **R-015**, 답변 **승인**, 선택 **A** — 이대로 켜려면. 고칠 점이 있으면 답변 **보류**와 메모. 켜지 않으려면 **거절**.

## 승인하시면 제가 하는 것
1. 파일 하나를 고치고 시험을 돌린 뒤 독립 검증을 거쳐 **PR 하나**로 병합 부탁을 드립니다(한글 켜기 PR 과 같은 시기면 한 번에 병합되도록 묶습니다).
2. 병합 뒤 첫 실행(다음 11:00 또는 수동 실행)을 제가 읽고 결과를 텔레그램으로 알립니다.
3. 첫 초안이 Blogger 초안함에 올라오면 **직접 읽어 보시고 공개할지 정해 주세요**. 공개 전에는 블로그에 보이지 않습니다.
