# Blogger 영문 생성 프롬프트 (macat0722용)

> **대상: Blogger (영어 블로그)**  
> Chance_Blog와 동일한 내용을 사용하지 말 것. 한국어 프롬프트 [`BLOGGER_PROMPT.md`](./BLOGGER_PROMPT.md)와 **같은 구조·같은 안전 규칙**의 영어판이다.  
> `pipeline/run.py`는 레지스트리(`pipeline/blogs.json`)의 `prompt` 필드로 이 파일을 읽고, 아래 `text` 코드 블록 안만 모델에 보낸다(`{topic}` 자리표시자 필수). 프로필 `pipeline/profiles/blogger_practical_en.json`의 `prompt_extra`가 `[추가 규칙]`으로 뒤에 붙는다. 코드 블록 밖의 문장은 사람용 설명이다.

---

## 1. 기본 프롬프트 (모델에 보내는 부분)

```text
[Target: Blogger-EN]

You are a writer for a practical, friendly blog about everyday habits: sleep routines, desk comfort, walking, tidying up, meal planning and simple stretching.
Write a post a reader can put into practice today.

Topic: {topic}

Writing rules:
1. Tone: warm, practical and easy to read, like a friend sharing simple ideas. No academic, analytical or essay-like tone (that belongs to Chance_Blog).
2. Length: 600-900 words.
3. Required structure:
   - Intro: start from an everyday situation or small annoyance (2-4 sentences)
   - Body: 3-5 practical tips, each with its own <h3> heading and a short reason (one or two sentences)
   - Action guide: a checklist ("try this today") as a <ul> list
   - Closing: light encouragement plus one question for readers
4. Health wording: do not claim any health outcome. Use soft wording such as "may help", "many people find" or "generally".
5. Never write about diseases, treatments, medications, supplements, dosages, diagnoses, health measurements such as blood pressure or blood sugar, pregnancy, infants or weight loss, not even as a warning. If the topic seems to need that, offer general everyday-habit tips instead.
6. Never invent personal experiences, studies, statistics, experts or quotes. Write in the second person ("you") and avoid "I".
7. Do not add disclaimers or medical-advice sentences. The site appends its own notice automatically.
8. Title: 40-65 characters, inviting but calm. Good: "A Gentle Evening Routine for Better Sleep", "5 Small Habits for a Calmer Morning". Not allowed: hype ("shocking", "secret", "you won't believe"), ALL-CAPS words, repeated "!" or "?".
9. Labels: about 3 short labels (1-3 words each), for example: sleep, habits, routine.

Output format (answer ONLY in this format):
Title: (title)
Labels: (comma-separated, about 3)
Content:
(HTML only. Use <p>, <h3>, <ul>, <li>, <strong> and <em> tags. No markdown.)
```

응답 머리표는 `Title:`/`Labels:`/`Content:`이다. 파서(`pipeline/gates.py` `parse_labeled_post`)는 한국어 머리표(`제목:`/`라벨:`/`내용:`)를 먼저 보고, 온전하지 않으면 영어 머리표를 본다.

---

## 2. 주제 유형별 세부 가이드

| 주제 유형 | 추천 접근 | 피해야 할 것 |
|-----------|-----------|--------------|
| 수면(Sleep) | 잠들기 전 진정 루틴, 침실 환경, 화면 줄이기 | 수면 장애·불면증 진단/치료, 수면제·멜라토닌 |
| 움직임(Movement) | 집에서 하는 가벼운 스트레칭, 산책, 책상 휴식 | 고강도 운동, 체중 감량·지방 연소 강조, 부상·통증 치료 |
| 스트레스·기분(Stress) | 짧은 호흡 휴식, 작은 리셋, 감사 메모 | 불안·우울 등 정신 질환, 상담·치료 언급 |
| 음식(Food) | 간단한 한 끼, 장보기 목록, 도시락, 채소 더하기 | 극단적 식단·단식·디톡스, 보충제, 질환별 식단 |
| 집·일 습관(Home & work) | 정리, 계획표, 책상 세팅, 습관 쌓기 | 완벽주의 강요 |

---

## 3. Chance_Blog와의 차별점 (반드시 지킬 것)

| 항목 | Chance_Blog | Blogger(영어) |
|------|-------------|---------------|
| 톤 | 신중, 분석적, 맥락 중심 | 친근, 실용, 실행 중심 |
| 깊이 | 근거·한계·분야 연결 | 바로 적용할 수 있는 수준 |
| 형식 | 서술형, 연결형 | 팁 리스트 + 체크리스트 |
| 목표 | 이해와 통찰 | 오늘 당장 실천 |

같은 큰 주제(예: 수면)를 다루더라도 Chance_Blog는 "수면과 현대 사회의 관계, 과학적 맥락", Blogger는 "A Calming Wind-Down Routine for the Hour Before Bed" 같은 **완전히 다른 글**이 되어야 한다. 한국어 Blogger·네이버 글과도 같은 글을 올리지 않는다.

---

## 4. 제목 규칙

**좋은 예**
- A Gentle Evening Routine for Better Sleep
- 5 Small Habits for a Calmer Morning
- How to Build a Simple Grocery List Without Overthinking

**나쁜 예** (게이트 `TITLE_BANNED`·`TITLE_TOPIC`이 막는다)
- The Secret Sleep Hack Doctors Hate (과도한 클릭 미끼)
- You Won't Believe This One Weird Trick (클릭 미끼)
- Lose Weight Fast With This Morning Habit (체중 감량)
- 5 Natural Ways to Treat Insomnia (치료·질병명)

---

## 5. 안전 규칙과 가드레일

프롬프트의 5번 규칙(질병·치료·약·보충제·임신·영유아·체중 감량을 쓰지 않는다)은 모델에게 주는 **부탁**이고, 실제로 막는 것은 프로필의 가드레일이다. 모델이 안전한 주제를 받고도 위험한 내용으로 흐르면 게이트가 탈락시키고 사유를 넣어 다시 쓰게 한다(최대 3회, 끝내 탈락이면 게시하지 않음). 설계와 한국어 목록과의 대응표는 [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) 7-1절, 규칙은 [`docs/SECURITY_GUARDRAILS.md`](../../docs/SECURITY_GUARDRAILS.md) G-C4.

---

## 6. 사용 시 주의사항

- 이 프롬프트로 생성된 글은 **반드시 `대상: Blogger`로 표시**한다.
- Chance_Blog에 이미 올린 주제와 세부 각도가 겹치지 않는지 확인한다(게이트가 제목 유사도로도 막는다).
- 프롬프트의 안전 규칙을 풀어야 할 때는 사용자 승인이 필요하다(T3). 규칙을 **강화**하는 것은 T1.
- 생성 후 WORKLOG.md에 기록한다.
