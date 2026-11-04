# p24nv 진행 기록 (N1 NAVER API HUB 안전 틀)

## ▶ 3차(문서) 결과 (21:20 — 코디네이터 요청 21:13, 마감 21:35, 문서만·src/·시험 변경 없음)
- 브랜치 `ai/claude/naver-hub-safety-1`, 새 WIP 커밋 **`2cc6b5a`**(전체 `2cc6b5a85983fa570243af3dc6e545fa4da55903`), 부모 `9bcb1c7`(그대로), 작성자 강병수. push·병합 가지·PR 없음. 변경 5개 문서 파일(8줄 바뀜 — 긴 줄 하나가 한 줄), origin/main 은 여전히 `3b1294b`(기준 그대로).

| 고친 곳 | 내용 |
|---|---|
| `docs/DECISIONS.md` D-35 ⑦ | **구현 쪽 기본값(운영자가 따로 정하지 않은 것)** 으로 명시: 하루 100회 창에서도 우선순위 몫 보호(일반 제공자의 일괄 30%·새 후보 20%·선택 후보 10%)를 쓰지 않는다 — 운영자 문서가 정한 것은 월 70·80·90% 단계뿐. 결과(자동 새로고침이 하루를 다 쓰면 그날 직접 고른 후보도 거절 — 일반 제공자는 일괄 70·새 후보 80·선택 90회에서 멈추고 필수만 100회), 되돌리는 길 둘(일 창엔 기존 몫 규칙 `QuotaGuard._check` 한 곳 / N2 에서 자동 새로고침 하루 상한 낮춤), 결정 거리(기본값: 예약 없음 유지) |
| `docs/DECISIONS.md` D-35 ⑧ | '다른 제공자의 파일은 그대로' 의 예외 한 갈래: NAVER 항목이 연결 설정에 있을 때 다른 용도가 깨진 상태 파일을 고치면 그 호출이 거절돼도 절반 가정 계수·빈 묶음·NAVER hold 표시를 바로 저장(예전 동작은 거절되면 저장 안 해 파일이 빔 — 더 보수적이라 위험 낮음) |
| `docs/SECURITY.md` | 단계 문단에 '하루 100회 창에도 쓰지 않는다 — 구현 쪽 기본값' 괄호, 알려 둔 한계에 몫 보호 없음 한 줄(되돌리는 길·기본값 포함) |
| `docs/ARCHITECTURE.md` | 몫 규칙 문장에 같은 괄호, 알려 둔 한계 ⑮ 추가, 상태 파일 문단에 D-35 ⑧ 예외 한 문장 |
| `README.md` | NAVER 항목 단계 설명 뒤에 '하루 100회 안에서는 우선순위별 몫이 없다(구현 쪽 기본값, D-35)' 한 문장 |
| `CHANGELOG.md` | 문서 보강 문장 + 변이 개수(구현자 113곳 = 첫 90 + 1차 23, 112곳 잡고 1곳 동등) + 시험 개수 192개(75 + 117) |

- 수치 점검: README·CHANGELOG·SECURITY·ARCHITECTURE·DECISIONS 어디에도 `[시험수]`·`175개` 남지 않음(grep 0건). 새 시험 개수는 CHANGELOG 한 곳에만 있고 192개(registry 75 + hub_quota 117)로 코드와 같음. 변이 개수 문구는 CHANGELOG 한 곳(113곳·112 잡음·1 동등)이고 앞의 90곳(89+1)·1차 23곳과 합이 맞음.
- 시험이 읽는 문서 줄 확인: `grep` 으로 tests 를 훑어 문서를 읽는 모듈은 test_repo_layout(링크·D-nn 정의·키 모양·개인 이메일)·test_errors_catalog(TROUBLESHOOTING↔catalog)·test_service_connections(TROUBLESHOOTING 한 줄)뿐 — 이번에 TROUBLESHOOTING 은 안 바꿈.
- 시험(한 번에 하나, 3.12 / 진짜 3.10.11 모두 `OK`): test_security_shape 43 · test_repo_layout 26 · test_errors_catalog 37 · test_service_naver_hub_registry 75 · test_service_naver_hub_quota 117 · test_service_safety 16.
- 보이지 않는 글자 스캔 0건(바뀐 5개 파일, CRLF 유지) · `git diff --check` 통과.
- 막힌 곳: 없음. 정할 것: 일 창 우선순위 몫 보호를 둘지(기본값: 예약 없음 유지 — 운영자 결정 거리, D-35 ⑦).

---

## ▶ 수정 1차 결과 (20:54 — 코디네이터 수정 요청 20:30, 마감 21:10)
- 브랜치 `ai/claude/naver-hub-safety-1`, 새 WIP 커밋 **`9bcb1c7`**(전체 `9bcb1c7147460c376430714775cd7e0dbd1702d4`), 부모 `728fedc`(그대로), 작성자 강병수. push·병합 가지·PR 없음.
- 변경 7개 파일, +282/−14: `service/quota.py` +25(`_legacy_denial`·`_exhaust_until` 월 창 갈래·`_confirms_auth`·`_report` 의 성공 갱신), `service/connections.py` +14(`mark_call_ok`), `tests/test_service_naver_hub_quota.py` +237(기존 1곳 기대 수정·새 시험 17개), `docs/SECURITY.md`·`ARCHITECTURE.md`·`DECISIONS.md`(D-35)·`CHANGELOG.md`.
- 고친 것: ① 월 창이 있는 제공자는 서버의 기간 한도 소진 응답 뒤 다음 달 1일 00:00(한국 시간)까지 쉼(서버가 48시간 안의 초기화 시각을 주면 그 시각이 먼저, 일 창만 있는 제공자는 그대로) ② Fail-Closed 제공자의 성공 호출 보고가 마지막 성공 시각·확인 결과를 갱신해 인증 24시간 창을 이어 줌(응답 상태 2xx 또는 미기재 + 응답을 썼을 때만, 실패·모호한 결과·인증 실패로 멈춘 항목은 갱신 안 함, `checked_at` 은 그대로, 한도 기록을 먼저 저장) ③ SECURITY.md 알려 둔 한계에 상태 파일 통째 삭제=사용량 0·일 한도 때문에 월 단계는 닿기 어려움·시계가 5분 안으로 돌아오면 자동으로 열림·월 초 소진 응답이면 한 달을 쉴 수 있음을 적고 '인증 불명확'·시계 문장 정정(ARCHITECTURE·DECISIONS 도 같게) ④ 옛 용도(`naver_openapi`)로 `acquire`·`acquire_entry` 를 부르면 `legacy` 코드의 쉬운 한국어 거절(새 용도로 안내, 사용량 파일 안 건드림).
- 시험(3.12 / 진짜 3.10.11 모두 `OK`): registry 75, hub_quota 117(기존 100 + 새 17), 기존 quota 71, connections 98, doctor 45, write_json 19, shape 43, errors_catalog 37, repo_layout 26, safety 16, cli_hardening 36, keys_cli 37. (3.10 의 keys_cli 한 줄은 내가 로그를 읽는 사이 기록이 빠져 따로 다시 돌려 `Ran 37 tests in 80.771s OK`.)
- 변이: 이번 추가분 23곳(소진 갈래·서버 시각 상한·일 창 유지·인증 갱신 조건 9가지·인증 실패 되살림·`checked_at` 갱신·옛 용도 거절 6가지 …) 모두 잡힘·살아남음 0(앞의 90곳 결과는 아래 그대로).
- 다른 용도 불변: 옛 main(3b1294b)과 새 코드로 같은 시나리오(이미지·AI·Blogger 호출·보고·깨진 파일 복구·명령줄 usage/policy/list)를 다시 돌려 비교 — 차이는 무작위 항목 번호와 전체 사용량의 첫 용도 줄(naver_openapi → naver_apihub)뿐(29줄, 앞과 같음).
- 보이지 않는 글자·줄바꿈 스캔: 바뀐 7개 파일 0건. 기존 시험 약화 없음(바꾼 기대는 소진 뒤 쉬는 시각 1곳 — 더 엄격하게).
- 정리: 임시 복사본(p24nv_mutcopy2·p24nv_base2) 삭제. 스크립트·로그: S 아래 p24nv_mut_fix1.py/.log, p24nv_final2.ps1/.log, p24nv_diff_scenario.py.
- 막힌 곳: 없음. 정할 것: 없음(지시대로 acknowledge 명령줄·시계 자동 열림·순번 변화·월 단계 도달 불가는 고치지 않음).

---

# (이전 기록)

시작 18:31:46 / 마감 20:31:46 (시작 후 2시간) — 아래 시각은 PC 시계(Get-Date) 기준

## 18:58 (1차) / 19:41 (2차) / 19:56 (3차)
- 지시서·저장소 읽기 → src 구현 → 기존 시험 갱신·새 시험 2모듈·문서 → 변이 90곳(89 잡힘·1 동등)·스캔 0건·관련 14개 모듈 3.12·3.10.11 통과.

## 20:02 (4차 — 마무리)
- 한 일: 로컬 WIP 커밋(작성자 강병수) 후, 그 사이 main 이 R-128 병합(3b1294b, PR #20)으로 움직였음을 발견 → 같은 한 커밋을 새 main 위로 rebase(CHANGELOG.md 한 줄 충돌만 양쪽 줄 유지로 해결). 머리 커밋 `728fedc`(부모 3b1294b), 브랜치 `ai/claude/naver-hub-safety-1`. push·PR 없음. rebase 뒤 5개 모듈(repo_layout·errors_catalog·hub 2모듈·safety) 254개 3.12 통과, 스캔 0건.
- 정리: 내 임시 복사본(p24nv_mutcopy·p24nv_base) 삭제. 점검 스크립트·로그는 S 아래 p24nv_* / h_mut_run.py 에 남김.
- 남은 일: 마지막 보고만.
- 막힌 곳: 없음. 정할 것: 없음.
