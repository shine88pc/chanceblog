# P0 진행 기록 (5채널 주제 선정 전략 1단계 — 기존 동작을 시험으로 먼저 보호)

- 시작 시각: 2026-11-04 19:27 (KST)
- 마감: 2026-11-04 20:57 (시작 후 90분)
- 작업 폴더: W\cd_wt_p0 (가지 ai/claude/p0-topic-protect-1, 기준 origin/main 3b1294b)

## 맨 위 — 보완 2차 끝(21:29, 마감 21:45 전) — 독립 검증 최종 보고서 `ver_p0_report.md`(조건부 병합 가능: 중간 2·낮음 12) 반영
- **새 WIP 커밋 `23ca08e`**(전체 23ca08ebf1550b373300a424cdea96d95eea8c7e, 작성자 강병수, 부모 `4c746d6`, 앞 두 커밋 그대로, push·PR 없음). 작업 트리 깨끗, `git diff --stat origin/main HEAD -- src` 비어 있음, 기존 시험 변경 0.
- **변경 파일 6개(+139·−37, 모두 내 앞 커밋의 줄)**: docs/TOPIC_ENGINE_PLAN.md(396줄 그대로) · docs/DECISIONS.md(D-36 ①·D-39 ④ 고침 + D-40·D-41 행 더함) · CHANGELOG.md(D-36~D-41) · tests/test_topic_protect_ui.py · tests/test_topic_protect_suggest.py · tests/test_topic_protect_candidates.py.
- 반영: M1(계획 7절 ③·⑥ 의 connections.py 인용을 '3b1294b 기준'과 'N1 병합 뒤(r134-naver-hub-safety-2 머리 3b0194f)'로 나눔 — 밀리는 인용은 connections.py 뿐임을 전수 대조) · M2(Qt 소스 시험을 ast 기반으로 — 주석으로 남긴 옛 줄에 안 속고 동작이 같은 정리에 안 깨짐) · 낮음 1(V11 추세 표·V30 칩 되돌림·V34 흔한 말 시험 추가)·3(D-40·D-41)·4(제안 상태 시작 목록은 사용자 데이터에만)·5(P4 행 구체화)·6(상대값 낱말만 보게 좁힘)·7(Legacy KNOWN_DEFECT 주석)·8(오늘 고정·실제 시계 안 읽음 확인)·9(계획 3.2·D-36 ① 의존 방향 정확히)·11(비공개 이름 주석)·2(9.1 '기존 시험과 합쳐' 문장). 미반영: 낮음 10(중립 예시 프로필)·12(README 링크) — 이유는 보고서 000절.
- **시험 줄**(3.12.10 / 3.10.11): `test_topic_protect_ui` Ran 31 tests OK / OK · `test_topic_protect_suggest` Ran 26 tests OK / OK · `test_topic_protect_candidates` Ran 19 tests OK / OK(합 76) · `test_repo_layout` Ran 26 OK / OK · `test_content_model` 34 · `test_ui_core` 94 · `test_service_candidates_cli` 60 OK / OK · N1 병합 가지 머리(3b0194f) 위에서도 새 3모듈 OK / OK.
- 변이 점검 67곳(15곳 추가)을 최종 시험으로 처음부터 다시: 동작을 깨뜨리는 62곳 모두 잡힘, 동작이 같은 정리 4곳(M57~M60)과 오경보 방지 1곳(M67)은 통과(맞음), 기대와 다른 것 0. ruff 새 시험 3개 0건, git diff --check·BOM·보이지 않는 글자·줄 끝 공백·탭 0건.
- 보고서 `W\p25p0_report.md` 맨 위에 '000. 2차 수정' 절 추가(반영한 것 표·반영하지 않은 것과 이유·시험 결과·새 커밋 해시).

## 맨 위 — 보완 1차 끝(20:44, 30분 마감 20:59 전) — 독립 검증 지적 3건 반영
- **새 WIP 커밋 `4c746d6`**(전체 4c746d62dfb9f685a584abf734799bbecbd03f59, 작성자 강병수, 부모 `1f2297b` 그대로, push·PR 없음). 작업 트리 깨끗, `git diff --stat origin/main HEAD -- src` 비어 있음, 기존 시험 변경 0.
- **변경 파일 6개(+123·−31)**: docs/TOPIC_ENGINE_PLAN.md(396줄 그대로) · docs/DECISIONS.md(D-36~D-39 다시 씀) · CHANGELOG.md(끝 줄) · tests/test_topic_protect_ui.py(+4) · tests/test_topic_protect_suggest.py(+3) · tests/test_topic_protect_candidates.py(+1).
- ① 출처 표기: 계획 문서 4.2(누가 정했나 열)·5.1·7절 ⑥·10절 E 행·D-36~D-39·CHANGELOG 에서 '운영자가 한 말'과 '이 계획의 해석'·'이 조사의 결론'을 나눔(운영자가 말하지 않은 것을 운영자 말로 쓴 곳 없음 — `운영자` 낱말 전수 재확인). ② 기존 절대 횟수 칸의 화면 이름·단위를 못박는 시험 `LegacyDemandLabelTest` 4개 + 명령줄 1개(기존 시험은 행 라벨 재라벨 M43 을 놓침을 확인). ③ P0b 영향(보관함 후보 우선도 89.1 → 81.8)을 계획 문서 8.1·8.2·8.3 에 적고 시험 3개로 현재 값을 못박음.
- **시험 줄**(3.12.10 / 3.10.11): `test_topic_protect_ui` Ran 29 tests OK / OK · `test_topic_protect_suggest` Ran 25 tests OK / OK · `test_topic_protect_candidates` Ran 19 tests OK / OK(합 73) · `test_repo_layout` Ran 26 tests OK / OK · 공개 가지 N1(`b2096ce`) 머리에서 73개 3.12·3.10 `Ran 73 tests … OK`.
- 변이 점검 10곳 추가(M43~M52, 총 52곳) 모두 잡힘. ruff 새 시험 3개 0건. `git diff --check`·BOM·보이지 않는 글자·줄 끝 공백·탭 0건.
- 보고서 `W\p25p0_report.md` 에 '00. 보완 1차' 절을 더하고 같은 표현(1절 4번·4절 ⑥·7절 5번)·개수(73·11·52)를 고쳤다.

## (1차 끝) 지금 상태 (20:09 갱신, 시작 후 42분 — 마감 20:57 전에 완료)
- **끝: 모든 일을 마쳤다.** 로컬 WIP 커밋 1f2297b(작성자 강병수, push·PR 없음), 작업 트리 깨끗, src/ 0줄.
- 새 시험 3개 모듈 65개(ui 25·suggest 22·candidates 18) 3.12·3.10 OK · 변이 점검 42곳 모두 잡힘(M09·M17 은 시험 보강 뒤) · 기존 시험 모듈 14개 3.12·3.10 OK · ruff 새 파일 0건 · git diff --check·BOM·보이지 않는 글자 0건.
- 문서: 계획 문서 396줄·D-36~D-39·CHANGELOG 한 줄(운영자 R-131 승인 반영, 별도 topic_engine.db·마이그레이션 없음) · search_demand 의미 조사 절(결론 'Legacy 유지·자동 이전 없음'은 맞음, 근거 두 곳 보정).
- 보고서: W\p25p0_report.md (맨 앞 6항목). 남은 일 없음. 코디네이터가 정할 것은 보고서 7절.

## 30분 단위 기록
- 19:27 시작. 요청서 읽음. 작업 폴더 만들기부터.
- 19:41 코디네이터 지시 보강(운영자 R-131 답) 수신 — r131_operator_answer.md 읽고 반영 시작.
- 19:50 새 시험 65개 통과(3.12/3.10). 변이 점검 준비.
- 19:57 변이 점검 37곳 완료(35곳 즉시 잡힘, 2곳 시험 보강 뒤 잡힘). 기존 시험 모듈 8개 OK.
- 20:00 문서 포크 보고 수신(계획 문서 396줄·D-36~D-39·CHANGELOG 확정 갱신). 최종 점검·보고서 단계.
- 20:08 보고서 작성(맨 앞 6항목·변이 표·search_demand 조사·결정 목록).
- 20:09 WIP 커밋 1f2297b 확인, 작업 트리 깨끗. 끝.
