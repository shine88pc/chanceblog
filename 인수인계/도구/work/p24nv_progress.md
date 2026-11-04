# p24nv 진행 기록 (N1 NAVER API HUB 안전 틀)

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
