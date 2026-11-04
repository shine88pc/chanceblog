# 개선안 담당 — 시험·변경 이력 계획 (개선안을 구현할 때 쓸 시험 목록과 변경 이력 틀)
작성 2026-11-04 · 이슈 #114 지시서 '9. 최종 결과물 — 테스트 결과 및 변경 이력'의 **계획 부분**과 이슈 #121(구현·시험까지 T1·T2)을 위한 준비 · **이번 준비 단계는 코드·사이트·설정 변경이 없으므로 아래 시험은 아직 하나도 실행하지 않았습니다**(실행 결과가 아니라 '무엇을 어떻게 시험할지'입니다). 짝 문서: `11_generator_improvement_plan.md`(검사 번호 S·G·분야 판정의 정의 — 검사 S1~S20 은 진단 담당 의 이야기 번호 S01~S20 과 다른 번호)·`15_execution_plan.md`(파동)·`12_quality_checklist.md`.

## 0. 이번 준비 단계 — 변경 없음
> **이번 단계(2026-11-04 조사·문서 작성)의 변경: 없음.** 저장소(`shine88pc/chanceblog`)·사이트·광고 코드·애드센스·발행 설정(`mode: auto`·`publish_flow: direct`)·워크플로·`_posts/`·`history.json` 어디에도 쓰거나 보내지 않았고, 체크아웃·커밋·push·브랜치 생성도 없습니다. 새로 만든 파일은 모두 `S`(= `(작업 폴더)`) 폴더 안에만 있고, 저장소 복사본(`(작업 폴더)`)은 읽기만 했습니다. 외부 요청은 공개 RSS 피드 표본 읽기 3회(피드 요청 모두 17번, 사이트별 robots.txt 확인 뒤·호스트 사이 6초 간격)뿐이고 GitHub 공개 REST·사이트 페이지·원문 페이지는 열지 않았습니다.
이 한 줄이 맞다는 것을 구현 단계에서 다시 확인하는 방법은 §2 D(auto 불변)와 §4 틀의 '불변 확인' 줄입니다.

## 1. 시험 원칙(저장소 `docs/ENGINEERING_GUIDE.md` §5·§9 를 따름)
1. **네트워크·실제 키 없이** 돌고 시간·난수·LLM·게시 API 는 주입합니다(가짜 Gemini·가짜 Unsplash·가짜 피드).
2. **성공 경로만 쓰지 않습니다**: 탈락·빈 입력·깨진 입력·이상한 글자·정규식 최악 입력을 반드시 넣습니다.
3. **시험이 실제로 실패하는지 확인**합니다(변이 점검 — 고친 코드를 잠시 되돌리거나 검사 한 줄을 지웠을 때 시험이 깨지는지). 새 검사의 '그 검사만 막는 표본'을 규칙마다 둡니다.
4. 새 정규식은 **되돌아가기가 입력 길이에 지수로 늘지 않게** 짜고 최악 모양의 시간을 시험으로 잽니다(R5, D-80 전례).
5. 비밀처럼 보이는 문자열을 소스에 쓰지 않습니다. 파이썬 3.10·3.12 모두에서 통과해야 합니다.
6. **'꺼진 상태에서 이전과 같다'는 실행 결과로 증명**합니다(문서의 주장이 아니라 같은 가짜 입력의 출력 비교, §9-11).
7. 기존 시험의 단정을 약하게 만들지 않습니다. 프롬프트·표를 바꿔 기존 시험이 깨지면 기대값을 **새 사실에 맞게 고치되 이유를 변경 이력에 적습니다**(U3 라운드의 방식).

## 2. 시험 목록
종류: **유지** = 이미 있는 시험이 그대로 통과해야 함 / **신규** = 새로 씀 / **갱신** = 기존 시험의 기대값만 새 사실에 맞게 고침. 'L' 은 검증 사다리 단계(L0 검증기·L1 단위·L2 드라이런·L3 초안)입니다.

### A. 회귀 방지(유지) — 어떤 단계에서도 전부 통과
| 번호 | 시험(파일) | 지키는 것 | 종류 |
|---|---|---|---|
| A1 | `tests/test_generator_slots.py` | 슬롯 판정, 후보 수집·탈락 코드, `ALL_REJECTED` 는 정기 실행에서 경고(초록)·수동 실행에서 예외, 본문 검증 탈락 시 다음 후보 | 유지 |
| A2 | `tests/test_prompt_grounding.py` | `GROUNDING_RULES` 정확히 세 줄, 모든 소스 프롬프트에 규칙 한 번씩, 같은 지시가 두 번 나오지 않음 | 유지(분야 지시를 더하면 **갱신**: 새 줄만 추가) |
| A3 | `tests/test_generator_front_matter.py`·`tests/test_posts_front_matter.py` | 머리말 검사, **실제 `_posts` 52편**의 머리말(새 선택 필드가 필수 키가 아님을 확인) | 유지 |
| A4 | `tests/test_unsplash_credit.py`·`test_unsplash_credit_fix.py`·`test_chance_credit.py`·`test_chance_credit_fix.py`·`test_edits_credit*.py` | U3: 작가 출처 필수·주소 검사·출처 줄·키 비노출 | 유지 |
| A5 | `tests/test_gates.py`·`test_guardrails.py` | Blogger 게이트(`pipeline/gates.py`)가 새 모듈로 바뀌지 않음 | 유지 |
| A6 | `tests/test_registry.py`·`test_drafts.py`·`test_generator_drafts.py`·`test_chance_draft_workflow.py` | 레지스트리·승인 흐름, `REAL_PUBLISH_FLOW` 표지판 | 유지 |
| A7 | `tests/test_validate_repo.py` + `python scripts/validate_repo.py` | AD-1(광고 표면 승인 표시)·REG-5·WF-* | 유지 |
| A8 | `tests/test_workflow_names.py`·`test_site_cleanup.py` | 워크플로 이름·`_config.yml` exclude 목록 | 유지 |
| A9 | `python -m unittest discover -s tests` 전체(3.10·3.12) | 전체 | 유지 |

### B. 그림자 모드 검증(신규) — 개선안 1단계
| 번호 | 시험(제안 이름) | 무엇을 확인 | 통과 기준 |
|---|---|---|---|
| B1 | `test_quality_off_is_byte_identical` | 같은 가짜 입력(피드 사본·가짜 Gemini)으로 main 의 `generator.py` 와 변경본(`quality=off`)을 돌려 비교 | 표준 출력·종료 코드·생성 파일·이력·실행 요약이 바이트 동일 |
| B2 | `test_quality_shadow_changes_nothing_but_the_summary` | `quality=shadow` 에서 결과 비교 | 생성 파일·이력·모델 호출 수·사진 조회 수가 `off` 와 같고, 로그·요약에 `[QUALITY]` 줄만 늘어남 |
| B3 | `test_quality_checks_never_raise_on_odd_input` | 빈 글·아주 긴 줄·BOM·제어 문자·방향 문자·거대한 숫자·깨진 마크다운 | 예외 없이 결과를 돌려줌. 내부 오류가 나도 조용히 지나가지 않고 요약에 `QUALITY_ERROR` 코드가 남음 |
| B4 | `test_quality_findings_are_sanitized` | 요약·로그에 쓰는 문구 | 모델이 쓴 글·원문 문장이 들어가지 않고 코드·고정 문구뿐(`_one_line`·`md_cell` 통과, `::` 명령 흉내 무력화) — R9·G-L2 |
| B5 | `test_gemini_call_count_is_unchanged` | 후보 3개 × (통과/탈락/전부 탈락) 시나리오 | `FakeGemini.calls` 가 변경 전과 같음(shadow·hold 모두) |
| B6 | `test_hold_internal_error_fails_closed` | hold 모드에서 검사 코드가 예외를 던질 때 | 그 후보를 탈락시키고 `::warning::` 고정 문장 + `QUALITY_ERROR` 기록(의심스러우면 게시하지 않음, AGENTS §2-4). **이 처리(탈락 vs shadow 강등)는 운영자 확인 항목** |

### C. 보류 동작(신규) — 개선안 4·§4-7
| 번호 | 시험 | 무엇을 확인 | 통과 기준 |
|---|---|---|---|
| C1 | `test_hold_rejects_candidate_and_next_is_published` | hold + 환산 의심 후보(10-27 형태 표본) → 다음 후보 | 첫 후보 탈락, 둘째 후보 게시(기존 `test_a_thin_body_rejects_that_candidate…` 와 같은 모양) |
| C2 | `test_hold_all_rejected_is_a_warning_in_schedule_mode` | 모든 후보 불량 | 정기 실행: 무게시·`ALL_REJECTED`·경고·종료 0·이력 불변·사진 조회 0, 수동 실행: 예외(빨강) |
| C3 | `test_verdict_codes` | 판정 코드 | `FIXABLE`(수정 후 통과)과 `HOLD`(발행 보류)가 요약에 구별되어 나오고 둘 다 발행하지 않음 |
| C4 | `test_signals_never_change_the_verdict` | 신호만 있는 후보(숫자 없음·가정형 많음·인과 단정) | 항상 `PASS`, '사람 확인 우선' 표시만 붙음(**신호가 판정을 바꾸지 않는다는 불변식**) |
| C5 | `test_pre_model_gates_call_the_model_zero_times` | `THIN_INPUT`·`DUP_URL`(승인 시) | `FakeGemini.calls == 0`, 새 `DROP_LABELS` 코드가 요약 표에 나타나고 `docs/ARCHITECTURE.md` 탈락 사유 표와 일치 |
| C6 | `test_retry_budget`(승인 시) | 실행당 후보 수·기억 | 하루 정기 실행 30회 가정 시 모델 호출 상한을 넘지 않음, 기억 파일이 `health.py`·`slot_state`·`note_manual_over_cap` 에 영향 0 |
| C7 | `test_pass_path_is_unchanged_for_clean_candidates` | 모든 검사를 통과하는 깨끗한 후보 | 기존 게시 결과와 같음(분야 판정·품질 줄만 추가) |

### D. 'auto' 설정 불변 확인(신규) — 이 계획의 가장 중요한 불변식
| 번호 | 시험 | 무엇을 확인 | 통과 기준 |
|---|---|---|---|
| D1 | `test_chance_publish_settings_are_pinned` | `pipeline/blogs.json` chance 의 `mode`·`publish_flow`·`limits.max_posts_per_day`·`schedule.slots_kst`·`schedule.cron`·`health`(승인 전) | `auto`·`direct`·2·`[9, 18]`·`17 * * * *`·36 그대로. **값이 바뀌면 이 시험이 빨강**이라 바꾸는 변경은 시험도 같이 바꿔야 하고 그것이 승인의 흔적이 됨(기존 `REAL_PUBLISH_FLOW` 표지판 방식) |
| D2 | `test_chanceblog_workflow_is_pinned` | `chanceblog.yml` 의 cron 두 줄·`permissions`·단계 env 이름 | YAML 로 읽어 비교, `actionlint` 0건 |
| D3 | `test_slot_and_mode_branches_unchanged` | `slot_state`·`SLOT_HOURS`·`main()` 분기 | 기존 시험(A1) + 새 표본 |
| D4 | `validate_repo --base origin/main` | AD-1 | 광고 표면 변경 0건 보고 |
| D5 | 변경 파일 목록 점검 | `git diff --stat origin/main` | `index.html`·`_layouts/`·`_includes/`·`_config.yml`·`about.md`·`privacy.md`·`contact.md`·`robots.txt`·`ads.txt`·워크플로가 목록에 없음(있다면 별도 승인 표시 `Ad-Surface-Approved:` 확인) |

### E. 분야 판정·분야 규칙(신규, #121) — 개선안 §3-A
| 번호 | 시험 | 무엇을 확인 | 통과 기준 |
|---|---|---|---|
| E1 | `test_classify_field_covers_every_lane_and_source` | `EDITORIAL_LANES` 6개·`NEWS_SOURCES` 중 약관 allowed 전부 | 모두 주 분야를 돌려줌(대응표 완전성), 같은 입력은 같은 출력 |
| E2 | `test_classify_field_adds_secondary_from_title_and_tags` | 제목·분류 태그에 분야를 바꾸는 말 | 보조 분야가 더해지고 규칙은 합집합 |
| E3 | `test_unknown_or_low_confidence_uses_strictest_union` | 소스 기본값과 키워드가 충돌 | '신뢰도 낮음' 기록 + 가장 엄격한 규칙 합집합 |
| E4 | `test_disabled_fields_apply_no_rules` | `enabled: false` 분야(생활·IT·여행·리뷰·교육·취미) | 규칙이 적용되지 않고 새 분야를 켜려면 설정 변경이 필요(T3) |
| E5 | `test_field_rules_block_and_pass_samples` | 분야마다 '걸리는 글'·'통과해야 하는 글'·경계 | 규칙마다 그 규칙만 막는 표본이 있음(`RuleCoverageTest` 방식), 설명서형 글의 '~할 수 있다'는 통과 |
| E6 | `test_field_table_matches_the_docs` | 개선안 §3-A-3 대응표 ↔ 코드 상수 | 문서·코드 일치(기존 `DocsTest` 패턴) |

### F. 구조 비강제(신규, #121 핵심) — '같은 목차를 강제하지 않는다'를 시험으로 고정
| 번호 | 시험 | 무엇을 확인 | 통과 기준 |
|---|---|---|---|
| F1 | `test_no_check_depends_on_structure` | 소제목 0·1·5개, 표 없음·표 3개, 결론 절 없음, 도입 없음인 서로 다른 구성의 **내용상 올바른 글 10종** | 모든 검사의 결과(판정·신호)가 구성 때문에 달라지지 않음 |
| F2 | `test_same_facts_in_different_layouts_get_the_same_verdict` | 같은 사실을 표로 쓴 글과 줄글로 쓴 글 | 같은 판정 |
| F3 | `test_quality_module_has_no_structure_counters` | `pipeline/quality_checks.py` 정적 점검 | 소제목 개수·표 행 수·목차 모양을 세는 코드가 없음(예외는 출처 구간을 찾는 S2 하나뿐이며 허용 목록으로 명시) |
| F4 | `test_check_registry_has_no_structure_category` | 검사 목록 상수 | 분류에 '구조'가 없음. 표준 글 담당 템플릿 초판의 개수 검사('사실 표 행 수·분석 소제목 수·한계 항목 수')와 v0.2 §9-2 의 위치·모양 표지 확인(도입부 위치·표나 목록 표지·한계 절 유무)에 해당하는 검사가 없음 |

### G. 숫자·환산·한·영 대조 / 출처 자르기(신규) — 개선안 ①
| 번호 | 시험 | 무엇을 확인 | 통과 기준 |
|---|---|---|---|
| G1 | `test_number_extraction_and_units` | '28.8억'↔'2.88 billion', '4조 2천억', 퍼센트, 소수, 쉼표, 날짜(`2026년`·`10월 29일`) 제외, 31 이하 정수 제외 | 정규화 값이 같고 날짜·작은 수는 제외 |
| G2 | `test_krw_conversion_suspect` | 한국어 글에 원화 금액, 원문·영어 짝에 없음 / 원문이 한국 기관이면 제외 | 10-27 형태 표본은 걸리고 식약처 형태 표본은 안 걸림 |
| G3 | `test_pair_number_mismatch` | 10-27(환산)·10-30(반올림·파생 수치) 형태 표본, 날짜·작은 수 잡음 표본 | 앞의 둘만 걸림. 파생 수치 허용 규칙은 표본으로 고정 |
| G4 | `test_source_split_shapes` | 출처 제목 모양 12종 이상(`##`·`###`·`####`·`**출처**`·`**Source**`·`## Source`·`### References`·`**출처 및 참고자료**`·구분선 뒤·콜론 붙음·대소문자) | 모두 출처 구간으로 인식, 본문 안 링크와 목록 속 링크가 구별됨 |
| G5 | `test_true_body_length` | 출처 목록·인용 줄·고지문을 뺀 진짜 분량 | 지금 기준과 새 기준의 차이를 표본(공개 후반 2편 형태)으로 고정 |
| G6 | `test_quality_regexes_have_no_catastrophic_backtracking` | 최악 입력 시간 | 입력 길이에 선형(상한 시간 안) |
| G7 | `test_grounding_check`(승인 시) | G1 근거 대조 — 근거 텍스트에 있는 숫자는 통과, 없는 숫자는 걸림, 두 숫자의 차·비 파생값은 허용 규칙대로 | 표본 통과 |
| G8 | `test_real_posts_with_known_exceptions` | 실제 `_posts` 52편에 새 검사를 돌려 **알려진 예외 목록**으로 관리(`test_posts_front_matter` 방식) | 새로 올라온 글이 기준을 넘으면 다음 PR 검사가 빨강(봇 커밋은 시험을 안 돌리므로 사후 감지) |

### H. 입력 보강(승인 시, 신규)
| 번호 | 시험 | 통과 기준 |
|---|---|---|
| H1 | 소스별 `feed_text_limit` | 설정한 소스만 길어지고 다른 소스는 300자 그대로, `no_page_fetch` 소스는 영향 없음 |
| H2 | 본문 칸 선택(`description`/`content:encoded`) — 실제 피드 사본(NASA형: 설명 366자·본문 4,342자) 고정 표본 | 설정이 켜진 소스에서만 본문 칸을 읽음, **추가 네트워크 요청 0** |
| H3 | 악성 입력 소독(프롬프트 인젝션 문구·태그·긴 URL·제어 문자) | 프롬프트에 안전하게 들어가고 길이 상한을 지킴(G-L2) |
| H4 | 근거 텍스트가 후보와 함께 보관되고 G1 이 같은 텍스트를 씀 | 일치 |
| H5 | 복제도 신호(5어절 겹침) | 원문을 길게 옮긴 표본은 걸리고 인용 한 줄은 안 걸림(G-C8) |

### I. 이미지·내부 링크(승인 시, 신규)
| 번호 | 시험 | 통과 기준 |
|---|---|---|
| I1 | alt 형식 검사 | 'Thumbnail'·'image'·파일명·제목 복사·길이 이탈은 걸리고 설명형 한 문장은 통과 |
| I2 | 캡션 고정 문구(illustration) | 코드가 붙이고 모델이 쓴 캡션은 믿지 않음(출처 줄과 같은 위조 방지) |
| I3 | 이력의 새 필드(사진 ID·작가·라이선스 안내 주소·선택 일시)가 옛 항목과 함께 읽힘 | 옛 이력 항목(문자열)에도 죽지 않음 |
| I4 | U3 시험 전부(A4) | 통과 |
| I5 | 이미지 기록 누락 → 보류 | 기록이 비면 `HOLD`, '작가 모름' 사진은 기존처럼 쓰지 않음 |
| I6 | `find_related` | 자기 자신·비공개·다른 언어 제외, 점수 하한 미달이면 '없음', 후보 밖 주소 거절 |
| I7 | 주소 계산 vs `posts.json` | 진단 담당 의 실제 주소 38개(식품 날짜 2편 지정 주소 포함)를 고정 표본으로 일치 |
| I8 | 본문 Liquid 금지 | 링크에 `post_url` 등 Liquid 가 없음(D-24 방지, R14) |

### J. 감시·문서·변이(신규/갱신)
| 번호 | 시험 | 통과 기준 |
|---|---|---|
| J1 | 보류 상황의 워치독: 기록이 `health.py` 의 `REAL_POST_STATUSES`·`REJECT_STREAK` 를 오염시키지 않음, `max_gap_hours` 조정 시 STALE 시점이 기대대로 | 일치 |
| J2 | 문서 시험: `DROP_LABELS`↔`docs/ARCHITECTURE.md` 탈락 사유 표, 새 규칙↔`docs/SECURITY_GUARDRAILS.md` | 문서·코드 일치 |
| J3 | **변이 점검**: 새 검사의 한 줄 삭제·임계값 완화·분기 뒤집기·판정 코드 바꾸기를 작업 폴더 복사본에서만 넣어 시험이 깨지는지 확인 | 살아남은 변이는 '동등한 변이'로 사유를 적거나 시험을 보강 |
| J4 | 독립 검증자 체크리스트(ENGINEERING_GUIDE §9 의 11개) | 구현자와 다른 세션이 diff·시험만 보고 판정 |

### K. 글(본문) 정정 파동용 확인(실행안 W2~W8)
글 정정 PR 은 코드가 아니므로 위 시험 대신 **글 확인 절차**를 씁니다: 근거 표(열람 날짜)·체크리스트 필수 6·한·영 대조·`python scripts/validate_repo.py`·`python -m unittest discover -s tests`(특히 A3 가 실제 글 전체의 머리말을 검사)·병합 전 사이트 빌드 전·후 비교·병합 뒤 `pages.yml verify` 통과.

## 3. 검증 사다리 매핑(단계별 최소 기준)
| 개선안 단계 | 등급 | 검증 |
|---|---|---|
| 1 그림자 모드(1·1'·1b) | T2 | L0 + L1(A·B·D·E·F·G) + L2 드라이런(꺼짐·shadow 비교) + L3 초안(실제 Gemini 수동 연습 실행 소량) + **독립 검증** + 꺼진 상태 바이트 동일 증거 |
| 3a·3b 보류 승격 | T3 + T2 | 위와 같음 + 승격 건별 C 시험 + 첫 1주 관찰(§5) + 운영자 채팅 승인 |
| 3c 재시도 제어 | T2/T3 | C6 + 호출 수 시험 + 승인 |
| 4 입력 보강 | T3 + T2 | H 시험 + L3 시험 글 전/후 비교 + 소스별 약관 확인표 승인 |
| 5 프롬프트·템플릿 | T1/T3 | A2 갱신 + L2 + L3, 게이트를 풀지 않음(§4 원칙) |
| 6 이미지 | T2 + 문구 T3 | A4 + I 시험 |
| 7 내부 링크 | T2 | I6~I8 |
| 8 워치독 기준 | T1(정책 확인) | J1 |
실행하지 못한 검증은 '실행 필요'로 적고 통과했다고 쓰지 않습니다(ENGINEERING_GUIDE §6).

## 4. 변경 이력 기록 틀(한 장) — 구현 단계마다 `WORKLOG.md` 항목과 `인수인계/작업내용.md` 에 같은 내용으로
```markdown
## [YYYY-MM-DD] <AI 이름> – C-nn <변경 제목>        (대상: Chance_Blog / 공통)    등급: T0 / T1 / T2 / T3

**무엇을 바꿨나**: 파일·함수·설정 이름(예: `pipeline/quality_checks.py` 신규, `generator.py` generate_blog_posts 후보 검증 칸, `pipeline/blogs.json` chance.quality.S4 = shadow)
**왜**: 개선안 항목(① 등)·운영자 요구(#114 5단계·#121)·근거 사례(예: 10-27 원화 환산)
**요청·승인 근거**: 채팅 날짜·요지 또는 `[답변]` 요청 번호 R-nnn — (T3 는 반드시. 승인이 없으면 '해당 없음(T0/T1)')
**바뀐 동작**: 꺼짐 / shadow / hold — 검사 번호(S4 등) — 판정 코드(PASS·FIXABLE·HOLD)
**불변 확인**: mode=auto · publish_flow=direct · cron · permissions · 광고 표면 파일 · Gemini 호출 수  → 각각 '변화 없음' 또는 변화와 승인 번호
**영향받는 소비자 점검**: health.py(STALE·REJECT_STREAK) · slot_state · note_manual_over_cap · 확인 필요 모음 — 영향 없음 / 있음(조치)
**시험 결과**: 명령과 결과 요약(예: `python -m unittest discover -s tests` 3.10 OK n개·3.12 OK n개), 신규 시험 개수, 실행하지 못한 것은 '실행 필요'
**독립 검증**: 검증자(다른 세션)·결과(조건부 병합 가능 등)·지적과 반영
**관찰 결과**(켠 뒤 첫 N회): 보류율 · 하루 Gemini 호출 합계 · STALE 여부 · 오탐 기록
**되돌리는 법**: 설정값(`shadow`/`off`) · `git revert <해시>` · `PIPELINE_PAUSE=true`
**미해결·다음 단계**:
```
### 예(이번 준비 단계)
`C-00 · 2026-11-04 · 변경 없음(조사·문서 작성) · 등급 T0 · 바뀐 동작 없음 · 불변 확인 전부 변화 없음 · 시험 실행 없음 · 산출물은 S 폴더의 문서 5개(개선안, 체크리스트, 재심사 점검표, 시험·변경 이력 계획, 실행안)와 진행 기록 1개뿐 · 되돌릴 것 없음.`

### 글(본문) 정정 이력 틀 — 실행안 W2~W8 용
```
이야기: S__ <제목>      파일: <한글 / 영문>      분류(진단 담당): <유지·수정·대폭 수정>      파동: W_
근거 표 위치: <파일·절>      원문 열람일: <날짜>      열지 못한 곳: <있다면>
바꾼 것(문장 단위): 삭제 / 정정 / 추가 — 각각 근거(출처 위치)
한·영 일치 확인: 숫자 □ 날짜 □ 상태 단어 □
체크리스트: 필수 6 ○/×/?   판정: 통과 / 수정 후 통과 / 발행 보류
등급: T1(근거 필수)   PR: <번호>   병합 전 사이트 빌드 비교: □   되돌리는 법: git revert <해시>
```

## 5. 켠 뒤 관찰 계획(승인 후 첫 실행들)
| 시점 | 확인할 것 | 어디서 | 이상 신호 → 조치 |
|---|---|---|---|
| 병합 직후 첫 정기 실행 | 실행 요약에 `[QUALITY]` 줄과 분야 판정이 나오는가, Gemini 호출 수가 이전과 같은가, 게시 결과가 같은가 | Actions 실행 요약 | 호출 수 증가·게시 변화 → 설정 `off`·원인 조사 |
| 첫 7일 | 후보 10건 이상의 신호·판정 분포, 사람 표본 5쌍 점검(체크리스트) 오탐 기록 | 요약 집계 + 표본 기록 양식 | 오탐이 2건 이상 → 임계값·사전 조정 후 재관찰, 보류 승격 보류 |
| 보류 승격 뒤 첫 7일(건별) | 보류율·슬롯 채움·하루 호출 합계·STALE | `history.json`·요약·워치독 | 보류율 30% 초과·호출 12회 초과·STALE → 해당 검사만 `shadow` 로 |
| 입력 보강 뒤 | 시험 글 전/후 비교(핵심 숫자 재현·복제도·길이) | 수동 연습 실행(실제 호출 소량) 요약 | 복제도 신호·길이 인플레이션 → 소스별 상한 낮춤 |
