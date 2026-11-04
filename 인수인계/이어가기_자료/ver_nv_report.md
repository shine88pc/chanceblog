판정: 조건부 병합 가능 (기준 커밋 9bcb1c7 = 병합 가지 r134-naver-hub-safety-2 의 트리) — 델타의 높음·중간 지적 없음, 남은 병합 전 확인 1건(일 창 우선순위 정책)
근거 1: 델타 9bcb1c7 이 첫 검증의 네 지적(월 한도 소진 쉬는 시각·인증 창 갱신·SECURITY.md 한계 문장·옛 용도 acquire)을 제대로 풀었다 — 경계 직접 시험·델타 변이 24곳 전부 잡힘(새 시험만으로)·다른 용도 차분 시험 이상 없음.
근거 2: 네트워크·새 파일 쓰기·비밀 노출 없음, 다른 용도는 기준선과 결과·상태 파일 sha256 이 같고, Fail-Closed 7가지를 일부러 어겨 모두 고정 문장으로 막혔으며 한도를 자동으로 풀어 주는 길이 없다(높음 0건).
근거 3: 3.12.10·3.10.11 에서 첫 검증 18개 모듈(897개 시험)·델타 12개 모듈(653개 시험, 새 17개 포함) 전부 OK, 변이 111+24곳 중 놓침 3(동등 1·시험 공백 2)·델타 0. 남은 것: 중간 1·4·6(델타가 안 다룸)·낮음.

## ★ 델타 검증 — 둘째 WIP 커밋 `9bcb1c7` (728fedc..9bcb1c7, 7파일 +282/−14) — 첫 검증과 따로 표시
병합 가지 `ai/claude/r134-naver-hub-safety-2`(`3b0194f`)는 부모가 `3b1294b` 이고 트리가 `9bcb1c7` 과 **똑같다**(`git diff` 비어 있음). 커밋은 이 PC 의 `cd_repo` 에 이미 있어 복제해서 읽었다(GitHub 호출 없음, push 없음, 전체 시험 안 돌림).

**델타 한 줄 결론: 첫 검증의 네 지적(월 한도 쉬는 시각·인증 창 갱신·SECURITY.md 한계 문장·옛 용도 acquire)을 모두 제대로 풀었고, 다른 용도는 달라지지 않았으며, 새 부작용은 낮음 수준이다. 델타의 높음·중간 지적은 없다 — 남은 병합 전 확인은 델타와 상관없는 '일 창 우선순위'(아래 첫 검증 중간 1) 한 건뿐.**

델타가 한 일(코드 +39줄): `quota.py` — `_exhaust_until`(월 창이 있으면 다음 달 1일), `_confirms_auth`·`_report` 끝의 `connections.mark_call_ok` 호출, `_legacy_denial`(`acquire`·`acquire_entry` 앞); `connections.py` — `mark_call_ok`; 문서 4개; 시험 +237줄(새 시험 17개 + 개명한 기존 시험 1개).

### ⑴ 월 창 용도의 소진 응답 뒤 쉬는 시각 — 맞다
- 구현 모양: 서버가 시간대 있는 초기화 시각을 `now < 시각 <= now+48시간` 으로 주면 그 시각, 아니면 월 창이 하나라도 있으면 다음 달 1일 00:00(KST), 아니면 일 창 → 다음 한국 자정, 슬라이딩 창 → 그 길이.
- 경계 확인(`W\ver_nv_x\tools\deltacheck.py`): 월 처음(11-02 00:00 KST)·월말 23:59:59·12-01 00:00:00 정각(→1월 1일)·12-31 23:59:59(연말)·1-01 00:00(→2월 1일)·평년 2월 27일 23:59:59·윤년 2월 7칸 모두 기대 시각. 서버 시각 9칸(+10h·**정확히 +48h 는 받아들임**·+48h+1초·지금과 같음·1시간 전(이미 지남)·시간대 없음·글자는 무시하고 다음 달 1일, KST 표기·+1초는 그 시각) 모두 기대대로. 이틀 뒤 같은 달에는 닫혀 있고, 새 달 1초 전에도 닫혀 있고, 정각에 열린다. 시도 수는 한도까지 채워 넣지 않는다(3 그대로), `blocked_until`·`block_kind` 저장도 맞다. 일 창만 있는 제공자는 다음 자정 + 창을 한도까지 채움 그대로(시험용 일반 용도).
- **낮음 D1 — 풀리자마자 다시 막히는 연쇄**: 쉬는 시각이 정확히 한국 달력 월 00:00 이라, 서버의 월 초기화가 UTC 자정(=한국 09:00)이면 열리자마자 첫 호출이 또 '소진' 응답을 받아 **한 달을 더** 쉰다(`deltacheck.py` E4: 11-30T15:00Z 에 열린 뒤 소진 응답 → 12-31T15:00Z). 문서는 '월 초 최대 9시간 안에 소진 응답이 오면 그 한 달을 쉬게 될 수 있다' 로 정직하게 적었고 실제 소진 자체가 드물다(일 100 한도 → 월 3,100). → 쉬는 시각을 다음 달 1일 09:00(KST)로 늘리면 연쇄가 없다.

- **낮음 D5 — 한 달짜리 막힘을 운영자가 풀 길이 없다**: `acknowledge` 는 기간 소진 막힘(`blocked_until`)을 풀지 않고(`W\ver_nv_x\tools\deltablock.py`: 확인 뒤에도 `blocked`, 20일 뒤에도 '12월 01일 00:00 이후 자동 재개') 명령에도 안 이어져 있다(첫 검증 중간 4 와 같은 뿌리). 예전에는 잘못 분류된 응답 한 번이 하루 침묵이었지만 이제는 한 달이다 — `classify_http` 는 `quota_exhausted` 를 만들지 않으므로 N2 가 응답을 이 종류로 분류하는 규칙을 정하는 것이 중요하다. → N2 전에 확인 명령(쉬는 시각 해제)이나 분류 규칙(서버가 '월 한도 소진' 을 분명히 알린 응답만)을 확정.

### ⑵ 성공 보고가 마지막 성공 시각을 갱신하는 조건·저장 순서 — 맞다(모호한 입력 한 갈래만 느슨)
- 구현 모양: `outcome == OK` **그리고** `provider.fail_closed` **그리고** `_confirms_auth`(= 상태가 안 적힘(0) 또는 2xx, 응답을 못 썼다고 알리지 않음) 일 때만 `connections.mark_call_ok`(`last_ok_at`·`check_result=ok` 만 바꾸고 `checked_at` 은 그대로, 인증 실패(`auth_failed`) 항목은 `None` 으로 되살리지 않음).
- 29가지 조합 확인: 갱신 — 상태 미기재·200·204·299·응답 사용 True. 갱신 안 함 — 199·300·302·304·401·429·500·100·응답 못 씀(False)·상태 미기재+응답 못 씀, 실패 9종(429·시간 초과·일시·인증 실패·400·그 밖·기간 소진·정책·콘텐츠). 인증 실패 뒤 늦게 온 성공 보고는 멈춤을 풀지 못하고 다음 호출은 `auth_failed` 로 거절. 20시간마다 성공하면 100시간 넘게 이어지고 마지막 성공 24시간 1초 뒤 `auth_unclear`. 다른 제공자(이미지)의 성공 보고는 `connections.json` 바이트를 안 바꾼다. `keys list` 의 '마지막 확인' 은 시험 시각(그대로), `keys usage` 의 '마지막 성공 호출' 은 갱신됨 — 서로 다른 뜻이라 어긋남 없음.
- 저장 순서: `_save(state)`(사용량) → `mark_call_ok` 순서라 연결 설정 쓰기가 실패해도 사용량은 남는다(`cn.mark_call_ok` 가 `KEYS_BUSY` 를 던지게 해 확인: 시도 1·성공 1 보존). 사용량을 잡은 잠금 안에서 연결 설정 잠금을 잡는 순서(quota-state → connections)는 기존 `AUTH_FAILED` 경로와 같고 연결 설정 쪽에서 사용량 잠금을 잡는 곳이 없어 새 교착 위험이 없다.
- **낮음 D2 — 모양이 틀린 입력은 '미기재'로 본다**: `report()` 가 `status` 를 먼저 0 으로 바꾸므로 상태 700·`True`·글자 `'200'` 도 갱신하고, 응답 사용 값이 `0`·`''`(거짓 비슷)여도 `is not False` 라서 갱신한다(장부에는 `bool()` 로 '응답 안 씀' 이 적힘). 시험은 599 까지만 본다. → `_confirms_auth` 는 원래 입력이 정수 100~599 이거나 None 일 때만, `used_response` 는 `True`·`None` 일 때만.
- **낮음 D3 — 성공 보고가 예외를 던질 수 있다**: 연결 설정 쓰기·잠금 실패면 `report()` 가 `AppError` 로 끝난다(사용량은 이미 저장 — 시험 `…cannot_write_the_connection_file_still_keeps_the_usage_record` 가 의도로 못박음). N2 호출부가 '예외 = 호출 실패' 로 오해해 보고를 다시 하면 성공 수가 이중으로 오른다(상한 = 시도 수). → 계약을 문서에 적거나 예외를 삼키고 갱신만 건너뛴다.

### ⑶ SECURITY.md 한계 문장 — 사실과 맞다
- '상태 파일을 통째로 지우면 사용량이 0 으로 돌아간다(깨진 파일과 달리 알아내지 못한다)' — 맞음(`nvcheck.py` F8). 첫 검증의 병합 전 조건 1번이 이것이었다 — **해결**.
- '일 한도 100 이 먼저 막아 이 앱의 사용만으로는 한 달에 3,100회를 넘지 못한다 → 월 단계는 실제로는 닿기 어렵다' — 맞음(31일 × 100, `nvcheck2.py` X1·X2).
- '시계가 되돌아갔다가 마지막으로 본 시각의 5분 안으로 돌아오면 운영자 확인 없이 자동으로 다시 열린다' — 맞음(F7d). 이전 문장('저절로 풀리지 않고 … 확인할 때')이 코드와 달랐던 것을 고침 — 첫 검증 낮음 1 **해결(문서 정정)**.
- '서버의 월 초기화가 한국 달력 월보다 늦은 월 초(최대 9시간)에 소진 응답이 오면 그 한 달을 쉬게 될 수 있다' — 맞음(D1 의 연쇄가 같은 위험).
- 인증 문장 '성공한 호출의 보고 — 응답 상태가 2xx 이거나 안 적었고 응답을 썼을 때 — 는 갱신' 은 코드와 맞는다(안 적은 상태+응답 사용 미기재도 갱신 — 장부가 미기재를 '썼다' 로 보는 것과 같다). 다만 위 D2 의 모양이 틀린 입력은 문서가 다루지 않는다.
- DECISIONS D-35·ARCHITECTURE·CHANGELOG 의 같은 문장들도 같은 사실이고 시험 개수 192(75+117)는 실제와 맞다.

### ⑷ 옛 용도(`naver_openapi`) acquire 거절 — 다른 용도에 영향 없다
- `_legacy_denial` 은 `acquire` 에서 잠금·상태 읽기 **전**, `acquire_entry` 에서 잠금 전에 돌아 `Denied(code="legacy", degraded=True, use_cache=False)` 와 쉬운 한국어 안내('옛 용도라 호출하지 않습니다 — … 로 옮겨 쓰세요')를 준다.
- 옛 항목이 든 옛 파일에서 우선순위 4 × 호출 수 3(1·5·1000) × 캐시 2 = 24가지 모두 같은 거절, 어떤 파일도 만들거나 바꾸지 않음(상태 파일이 없으면 만들지 않고 있으면 바이트 그대로), 옛 항목의 연결 시험 호출(`acquire_entry`)도 거절, 같은 파일에서 이미지 용도는 그대로 `Lease`, `usage()`·`purpose_status` 는 그대로. 첫 검증 낮음 3 **해결**. (시험용 일반 레지스트리 `generic_registry()` 는 `legacy_to` 가 비어 있어 일반 동작 시험은 그대로 돈다.)
- 차분 시험(기준선 대 `9bcb1c7`): 무작위 1,000 시나리오·42,380 연산(`acquire` 12,884·`report` 6,623 중 기간 소진 응답 668·`usage` 2,527·`acquire_entry` 1,789·상태 파일 훼손 1,092)을 같은 시드·같은 가짜 시계로 기준선과 `9bcb1c7` 에 먹임 — 용도 5개(옛 `naver_openapi` 사본·검색광고·이미지·AI·Blogger)의 결과와 연산마다 상태 파일 sha256 이 **모두 같았다**(4개 시나리오는 이 PC 의 윈도 임시 쓰기 실패 `FILE_WRITE_FAILED` 잡음으로 달랐고 조용히 다시 돌리니 모두 같음 — 기간 소진 응답 668번을 포함해 다른 용도의 쉬는 시각·계수도 그대로, 새 용도 전용 칸이 다른 용도에 나타나지 않음).

### ⑸ 새 시험 17개의 질 — 좋다
- 내가 델타 코드에 새로 만든 변이 **24곳**(인증 갱신 상태 경계 4(300 포함·199·299 제외·응답 못 씀 무시)·미기재 거부·다른 제공자 갱신·실패도 갱신·저장 순서 뒤집기·쉬는 시각 5(옛 동작·자정으로·48시간 제한 삭제·지금과 같은 시각 허용·정확히 48시간 제외)·옛 용도 5(판정 끔·`acquire`·`acquire_entry` 거절 삭제·코드 바꿈·`degraded` 반전)·`mark_call_ok` 5(인증 실패 되살림·시험 시각도 바꿈·성공 시각 안 바꿈·처음 한 번만·확인 결과 안 바꿈)·창 이어 주기 1)을 **새 시험 3클래스 + 개명 시험(RotationTest)만으로** 돌려 24곳 잡힘·놓침 0
- 기존 시험 단언을 바꾼 한 곳(소진 응답 시험의 개명): 단언 3개를 '다음 한국 자정' → '다음 달 1일' 로 바꾸고 `resume_text`('12월 01일 00:00 이후 자동 재개') 단언을 더했다 — **약해지지 않았다(오히려 강해짐)**. 다른 기존 단언의 삭제·약화 없음(`git diff -U0` 에서 지워진 줄은 이 4줄뿐).
- 못 잡는 것(낮음 D2): 범위 밖 상태 값(600 이상·불리언)·거짓 비슷한 응답 사용 값은 시험이 없다.

### ⑹ 새 부작용
- 낮음 D3(성공 보고 예외 전파)·D2(모호한 입력)·D5(한 달 막힘을 풀 길 없음). 성공 보고마다 `connections.json`(+`.bak`)을 다시 쓴다(하루 최대 100번, 쓰기당 fsync 4번 — 무시할 수준). `.bak` 이 '운영자 변경 직전' 이 아니라 '마지막 성공 보고 직전' 이 되지만 `.bak` 의 용도(깨진 파일 복구용 직전 올바른 사본)는 그대로라 영향은 거의 없다.
- 다른 용도의 동작·상태 파일·`connections.json` 변화 없음(차분 시험·위 R5). 잠금 교착 없음. 첫 검증 중간 6(깨진 상태 파일을 고칠 때 즉시 저장)은 델타가 안 다뤘고 그대로 남음.

### 델타 시험 줄 (한 번에 하나씩 모듈별; 전체 시험은 안 돌림)
| 모듈 | 3.12.10 | 3.10.11 |
|---|---|---|
| `test_service_naver_hub_quota` | Ran 117 tests in 25.332s OK | Ran 117 tests in 30.749s OK |
| `test_service_naver_hub_registry` | Ran 75 tests in 3.468s OK | Ran 75 tests in 7.074s OK |
| `test_service_connections` | Ran 98 tests in 11.649s OK | Ran 98 tests in 13.177s OK |
| `test_service_quota` | Ran 71 tests in 24.809s OK | Ran 71 tests in 32.703s OK |
| `test_service_doctor` | Ran 45 tests in 3.281s OK | Ran 45 tests in 3.293s OK |
| `test_service_safety` | Ran 16 tests in 2.785s OK | Ran 16 tests in 2.766s OK |
| `test_repo_layout` | Ran 26 tests in 3.390s OK | (안 돌림) |
| `test_errors_catalog` | Ran 37 tests in 1.862s OK | (안 돌림) |
| `test_service_write_json` | Ran 19 tests in 0.469s OK | (안 돌림) |
| `test_service_cli_hardening` | Ran 36 tests in 6.616s OK | (안 돌림) |
| `test_security_shape` | Ran 43 tests in 0.461s OK | (안 돌림) |
| `test_service_quota_legacy_locale` | Ran 70 tests in 26.968s OK | (안 돌림) |
| 합계 | 12개 모듈 653개 — 전부 OK | 6개 모듈 422개 — 전부 OK |

---

# 첫 검증(`728fedc`) 결과 — 델타 `9bcb1c7` 에서 처리된 항목은 각 지적 앞에 표시

검증 시작 2026-11-04 20:02:31 · 끝 21:14 (마감 21:32:31) · 검증자: 이 변경을 쓰지 않은 별도 에이전트 · push·진짜 GitHub·텔레그램·NAVER 호출 없음 · 진짜 윈도 자격 증명 관리자는 건드리지 않음(가짜 보관소만) · 구현자의 변이 결과표는 읽지 않음(변이는 새로 설계)

## 판정: **조건부 병합 가능** — 높음 0건, 병합 전에 고칠 것 2건(문서 한 줄·정책 확인 한 가지)
1. 네트워크·새 파일 쓰기·비밀 노출이 없다: 보이지 않는 문자 0건, 새 import 는 `hashlib`·`unicodedata` 뿐, 비밀 변형 10종을 데이터 폴더 모든 파일·모든 명령 출력에서 훑어 0건, 잘못된 키 입력 23가지도 되풀이 0건.
2. 다른 용도는 그대로다: 무작위 2,000 시나리오·84,506 연산을 기준선과 새 복사본에 같은 시드로 먹여 결과와 상태 파일 sha256 이 모두 같았다(새 항목이 연결 설정에 있을 때 '깨진 파일 고치기' 한 갈래만 다름 — 중간 지적 6).
3. Fail-Closed 7가지를 일부러 어겨 모두 고정 문장으로 막혔고, 월 경계·단계 192칸 표·두 프로세스 경쟁이 규칙대로이며, 3.12.10 과 3.10.11 에서 18개 모듈이 전부 OK(새 시험 175개 포함), 변이 111곳 중 108곳 잡힘·3곳 놓침(동등 1·시험 공백 2).

(시각은 PC 시계 기준. 아래 `S\…` 는 지시서의 `S`(작업 폴더) 아래 경로.)

## 높음
없음. (한도를 자동으로 풀어 주는 길·비밀이 새는 길·다른 용도가 달라지는 길 중 코드 변경만으로 닿는 것은 찾지 못했다. 상태 파일 삭제·직접 고치기는 문서에 적힌 한계다.)

## 중간 (재현 방법 · 고칠 방향)
**[델타에서 안 다룸 — 남음]** 1. **일 한도 안에서 우선순위 보호(30/20/10%)가 사라졌다.** 새 용도는 우선순위와 상관없이 하루 100회를 다 쓸 수 있다(자동 새로고침 100·직접 분석 100·선택 후보 100·필수 100 — 같은 한도 100 인 일반 제공자는 70·80·90·100). 자동 새로고침이 하루를 다 쓰면 사용자가 고른 후보 호출도 그날은 거절된다. 재현: `W\ver_nv_x\tools\nvcheck3.py`. 문서는 '단계표가 있으면 이 몫 규칙을 쓰지 않는다' 고 적었지만 운영자가 정한 것은 월 단계뿐이다. → 일 창에는 기존 몫을 그대로 두고 월 창만 단계표를 쓰거나, '일 창은 예약 없음' 을 D-35 에 운영자 결정으로 못박는다.
**[델타 `9bcb1c7` 에서 해결 — 확인함]** 2. **서버가 '기간 한도 소진'을 알려도 쉬는 시각이 다음 한국 자정이다.** 재현: `nvcheck2.py` D7(`report(quota_exhausted)` → 쉬는 시각 2026-11-04T15:00Z, 이틀 뒤 같은 달에 다시 열림). 이 제공자의 서버 한도는 월 단위다(콘솔 30,000). 호출 코드가 없어 지금은 닿지 않는다. → `_exhaust_until` 이 월 창을 가진 제공자는 서버가 알려 준 시각이 없으면 다음 달 1일 00:00(KST)까지 쉬게(N2 전에).
**[델타에서 해결 — 확인함(모호한 입력 낮음 D2)]** 3. **연결 시험 성공 24시간이 지나면 새 호출이 전부 `auth_unclear` 로 막히는데, 성공한 호출은 그 시각을 갱신하지 않는다.** 재현: `nvcheck.py` F5f(성공 보고 25시간 뒤 `acquire` → 거절). 풀오토 원칙이면 N2 에서 하루 뒤 모든 자동 호출이 멈춘다. 문서에는 '24시간이 지났거나' 만 적혀 있다. → 성공 보고가 `mark_check(ok)` 를 부르게 하거나 유효 시간 규칙을 N2 설계에서 정한다.
**[델타에서 안 다룸 — 남음]** 4. **`acknowledge`(기록 사라짐·시계 확인)가 어떤 명령에도 이어져 있지 않다.** 다른 용도 호출이 깨진 파일을 고친 뒤에는 NAVER 가 영구히 막히고(F2d) 운영자가 풀 길이 없다 — 상태 파일을 지우는 길뿐인데 그러면 사용량이 0 으로 돌아간다. 문서에 '명령에 이어져 있지 않다' 로 적혀 있다. → N2 와 함께 `keys` 확인 명령(예: `keys resume naver_apihub --yes`)을 넣고, 그 전에는 문서의 한계 목록에 '풀 길 없음' 을 분명히 적는다.
**[델타에서 해결 — 확인함]** 5. **SECURITY.md 의 '알려 둔 한계' 에 '상태 파일을 통째로 지우면 사용량이 0 으로 돌아간다' 가 빠졌다.** ARCHITECTURE(한계 ⑫)·DECISIONS D-35 에는 있다. 재현: `git grep`, 동작은 `nvcheck.py` F8. → SECURITY.md '모르는 것과 안전한 쪽의 선택' 끝에 같은 한 문장을 더한다(병합 전).
**[델타에서 안 다룸 — 남음]** 6. **NAVER 항목이 연결 설정에 있으면, 깨진 상태 파일을 다른 용도가 고칠 때 그 용도의 '절반 가정' 계수와 빈 묶음이 파일에 저장된다.** 기준선은 그 호출이 거절되면 저장하지 않아 파일이 비었다. 재현: 차분 시험 변형 `ADD_HUB=1`(훼손 445개 시나리오 중 48개 차이 — 즉시 저장 `if for_write and any("audit"…): self._save(state)` 를 끄면 47개가 기준선과 같아지고 1개는 훼손된 글 모양 차이). 예: 옛 용도 하루 사용량 새 12,500 대 기준선 0. 더 보수적인 쪽이라 위험은 낮지만 '다른 용도는 바이트 단위로 그대로' 와 다르고 D-35 ⑧ 의 '다른 제공자의 파일 모양은 그대로' 가 이 갈래에서는 정확하지 않다. → hold 표시만 저장하고 다른 제공자의 가정 계수는 저장하지 않게 하거나, 이 차이를 D-35 에 적는다.

## 낮음
**[델타에서 문서 정정 — 확인함]** 1. 시계가 돌아오면(마지막 본 시각 −5분 이상) **확인 없이 자동으로 다시 열린다**(`nvcheck.py` F7d). 지시서의 '시계가 돌아와도 명시 확인 전엔 막힘' 과 다르다(문서는 '시계가 바로잡히면 열린다' 로 일관). 확인 명령은 없다(중간 4).
2. 옛 용도가 레지스트리 맨 뒤로 가서 `keys list` 순번이 달라진다(옛 파일: `[1]옛기본 [2]옛예비` → 새 `[3] [4]`). 번호 앞 8자로 지우는 명령은 영향 없고 `keys state 1 …` 같은 순번 명령은 다른 항목을 가리킬 수 있다.
**[델타에서 해결 — 확인함]** 3. 옛 용도 `acquire("naver_openapi")` 는 아직 몫을 내준다(옛 25,000/일 규칙, `nvcheck.py` G15). 부르는 곳이 없어 무해하나 문서의 '호출하지 않고 사용량도 세지 않는다' 와 다르다. → `acquire` 에서 옛 용도를 거절.
**[델타에서 문서에 적음 — 확인함]** 4. **일 100회 × 31일 = 3,100회라 월 70/80/90% 단계(21,000/24,000/27,000)는 일 한도를 올리기 전에는 닿지 않는다**(`nvcheck2.py` X1·X2). 시험은 상태 파일을 직접 써서 단계를 만든다. 운영자가 정한 숫자의 결과라 코드 결함은 아니다 — 정할 것.
5. 80% 이후 `new_candidate` '한 번에 5회' 는 **한 번 부를 때만** 막는다(5회씩 반복하면 계속 허용 — `nvcheck.py` S4b).
6. 상태 파일의 `last_seen` 이 `0001-01-01T00:00:00Z`(모양은 올바른 시각)이면 `acquire`·`keys usage` 가 `OverflowError` 로 예외를 던진다(Denied 가 아님, `W\ver_nv_x\tools\overflow.py`). 무작위로 어긋낸 상태 파일 1,500개 중 1개(`fuzzstate.py`). 직접 고친 파일에서만.
7. `report()` 는 깨진 파일을 `.bak` 으로 옮기고 hold 표시를 저장한다(`nvcheck4.py`) — 문서는 '이 제공자는 깨진 파일을 스스로 고치거나 옮기지 않는다'(호출 잡기 `acquire` 는 맞다).
8. 시계를 한 달 되돌려 `acknowledge` 한 뒤 시계를 복구하면 이번 달 사용량 창이 지난 달 라벨로 덮이고 장부 모순으로 한 달 멈춘다(`nvcheck.py` F7f) — 명령에 안 이어져 있어 지금은 닿지 않는다.
9. 같은 호출에 실패 보고 뒤 성공 보고가 오면 마지막이 이겨 성공으로 센다(`nvcheck4.py`). 호출하는 쪽이 한 번만 보고하면 무해.
10. 오류표 `QUOTA_STATE_INVALID` 의 '하실 일 없음 — … 정상으로 돌아옵니다' 는 NAVER 용도에는 맞지 않는다(이 문구는 NAVER 화면에는 나오지 않고 고정 안내가 나온다). 잘못된 용도 이름을 넣었을 때 오류 문구의 선택지에 옛 용도 이름이 보인다.
11. 키(Client ID)를 바꿔 끼우면 내부 사용량이 0 으로 새로 시작한다(한도 묶음 = Client ID 의 해시). 같은 Client ID 면 이어진다. 콘솔 한도는 그대로라 마지막 안전장치가 받는다.
12. `ruff --select F,E9,B,UP`: F·E9 0건, pyflakes 0건. B·UP 은 바뀐 파일 전체 20건 중 6건이 새것(기준선에도 같은 종류 14건: `timezone.utc`·`zip` 등 — 3.10 대상이라 `datetime.UTC` 를 못 쓴다). 새 시험의 `B023`(람다가 반복 변수 `asked` 를 묶지 않음) 1건. `vermin --target=3.10-`: 소스 최소 3.7·시험 3.10 — 통과.
13. 변이 S07(닫힘 단계가 '절약 모드' 로만 거절)은 **동등**이다: 기본 숫자에서는 월 창 한도(27,000)가 단계 90%(27,000)와 같아 창 검사가 먼저 막는다. 한도 숫자를 바꾸면 의미가 생기므로 변형 레지스트리 시험이 있으면 좋다.
14. 구현 지시서의 '내부 한도를 설정값으로 낮출 수 있게' 는 아직 안 된다(하루 100·월 27,000·분석 5회는 코드 안 값, 한도 등급은 구조만 있음) — 문서의 한계 목록에 적혀 있어 숨기지는 않았다. 운영자가 낮추고 싶으면 N2 이전에 정책 값 위치를 정해야 한다.
15. **시험 공백**: 시계가 **하루 넘게** 되돌아간 경우를 막는 시험이 없다 — 변이 N04(시계 검사 `now < seen - CLOCK_TOLERANCE` 를 '하루 이내일 때만' 으로 바꿈, 즉 큰 되돌림은 풀어 줌)가 모든 시험을 통과했다. 직접 시험(`nvcheck.py` F7e: 40일 되돌림 → 거절)은 막는다. → 5분 초과·하루 초과·한 달 되돌림 시험을 추가.
16. **시험 공백(동등에 가까움)**: 변이 P09(모르는 `hold` 값 `'x'` 를 올바른 모양으로 받음)가 모든 시험을 통과했다 — 어차피 `hold` 가 비어 있지 않으면 거절돼 결과는 같고 안내 문구만 다르다. 모양 검사가 엄격한지 보는 시험을 하나 더하면 좋다.

## 병합 전에 반드시 고칠 것 (델타 `9bcb1c7` 반영 뒤 상태)
1. ~~SECURITY.md 한계에 '상태 파일을 지우면 사용량 0' 한 문장~~ — **델타에서 해결(확인함)**.
2. **남음**: 중간 1(일 창 우선순위 보호)을 운영자 결정으로 확인 — 보호를 되살리거나 '일 창은 예약 없음' 을 D-35 에 적는다. (코드는 그대로 두고 문서만 고쳐도 병합 가능하다.)
3. (권고) 중간 6 은 D-35 ⑧ 에 한 줄을 적어 두면 '다른 용도 그대로' 주장과 맞는다 — 델타가 안 다뤘다.

## 해도 되는 것 (병합 뒤 N2 에서 처리)
중간 4(확인 명령 연결)·낮음 전부(순번 변화 안내·`last_seen` 극단값 방어·ruff 새 6건 정리 등)와 델타의 낮음 D1(쉬는 시각을 월 초 09:00 까지)·D2(모호한 입력)·D3(성공 보고 예외 계약). 모두 N1 에서는 호출 코드가 없어 닿지 않는다. (첫 검증의 중간 2·3 은 델타에서 이미 해결됨.)

## 확인한 것 (요약)
- **범위·위생**: `git diff 3b1294b 728fedc` = 21개 파일(+3,300/−203), 주장과 같음(소스 5개 외에 `errors/catalog.py` 문구 3행이 주장 목록에 빠졌으나 문서 표와 동기화된 것 — `scripts/sync_errors.py --check` 통과). `vendor/`·`AGENTS.md`·`ci.yml`·의존성 파일 변경 0. 새 import 는 `hashlib`·`unicodedata`·`dataclasses.replace` — `urllib`·`socket`·`http`·`subprocess` 0, 새 파일 쓰기 경로 0(`quota_state.json` 은 기존 `write_json`·`keep_bad_copy`). 바뀐 21개 파일의 저장된 글(blob) 전체를 보이지 않는 문자·방향 제어·BOM 로 훑어 0건, `git diff --check` 통과, blob 은 모두 LF(저장소 원래 모양, 작업 폴더만 CRLF).
- **기존 시험 약화 없음**: 지운 시험 줄 전수 확인 — 모두 새 용도(`naver_apihub`)·시험용 일반 레지스트리(`generic_registry()`)·`ai_assist` 로 옮겨 같은 단언을 다시 건 것이고 모듈별 시험 수(connections 95·keys_cli 37·quota 71·doctor 45·write_json 19)는 그대로다. 단 '일반 동작' 시험은 이제 실제 레지스트리가 아니라 옛 용도를 시험용으로 되살린 사본으로 돈다.
- **차분 시험**(`W\ver_nv_x\tools\diffharness.py`): 용도 5개(옛 `naver_openapi` 사본·검색광고·이미지·AI·Blogger)·무작위 2,000 시나리오·84,506 연산(`acquire` 25,702·`report` 13,275·`usage` 5,165·`acquire_entry` 3,524·상태 파일 훼손 2,194·시계 이동 12,998·정책 1,369) — 연산 결과와 연산마다 상태 파일 sha256 이 같음. 11개 시나리오는 윈도 임시 쓰기 실패(`FILE_WRITE_FAILED`, 이 PC 의 잡음)로 달랐고 조용히 다시 돌리니 모두 같음. 변형(새 용도 항목을 연결 설정에 둔 채, 700 시나리오): 훼손 없는 255개는 sha256 까지 모두 같음, 훼손 445개 중 397개 같음·48개 차이(중간 6). 명령줄 `keys` 47개 출력 비교: 다른 용도 블록·상태 파일은 바이트 같음(항목 번호는 무작위 uuid 라 제외).
- **용도 정정·옛 항목 호환**: `naver_apihub`(칸 `client_id`·`client_secret`, 항목 최대 1, `rotation=never`, 일 100·월 27,000, 콘솔 30,000, `implemented=False`) = 요구와 같음. 둘째 항목은 약관 확인 유무와 상관없이 쉬운 한국어로 거절. 옛 `connections.json`(옛 항목 2개+이미지+검색광고)은 깨지지 않고 읽히고 '옛 항목' 안내가 붙으며 읽기 명령은 파일을 안 바꿈, 새 항목 추가는 키를 묻기 전에 거절, `keys remove` 로 지워지고 키 보관소 항목은 자동 삭제 없음, 옛 항목이 있어도 새 용도에 키를 넣을 수 있음. `keys purposes/list/add/remove/state/order/usage/policy/test` 모두 새 용도에서 깨지지 않음.
- **월 창·한도**: 월 라벨·다음 달 1일을 12→1월·2월 말·윤년(2028-02-29)·월말 23:59:59→00:00:00·다른 시간대 입력(−08:00·+09:00·+14:00) 11가지로 확인(그중 +14:00 한 건은 내 기대값 계산 실수여서 바로잡아 확인), 일 100 먼저·월 27,000 먼저·둘 다 가득이면 더 늦은 초기화. **단계 192칸 표**(월 20,998~27,000 × 우선순위 4 × 호출 수 1·5·6·99): '호출 뒤 사용량이 경계를 넘을 때' 규칙과 전부 일치(경계값과 같으면 아직 아님, 넘으면 그 단계 — 70% 안내는 21,001 번째부터). 한 번에 크게 넘는 호출(1,000 회 단위, 일 한도를 올린 변형 레지스트리) 8가지 일치. 월 26,999 → 27,000 번째는 허용, 그다음은 `critical` 포함 거절·다음 달 1일에 다시. 80% 이후 `bulk_refresh` 거절·`new_candidate` 5회 허용 6회 거절·90% 에서 전부 거절.
- **시도/성공·장부**: 실패 9종(429·시간 초과·인증·400·그 밖·소진·정책·콘텐츠·5xx)이 모두 시도로 세어지고 성공은 0, 성공만 성공, 5xx 재시도는 시도 2회·재시도 칸 1, 캐시 적중은 시도·성공 불변·장부에만, 같은 호출 두 번 보고해도 성공 ≤ 시도, 장부 200건 상한(가득 찬 뒤 사흘 더 써도 파일 크기 80,240 → 80,348 바이트), 장부 칸은 정해진 12개뿐. 조건 해시 12자·키 순서·정규화 무관, 비밀 칸 이름(11가지)이 든 조건은 거절(전각·띄어쓰기 변형과 목록에 없는 `secret_key`·`access_token`·`x-api-key` 는 이름 검사를 통과하지만 해시 12자만 남고 값은 안 남음), 키 값이 이름 없는 칸에 들어가도 파일에 값·값 조각 0.
- **비밀 노출**: 카나리 비밀 변형 10종(원문·소문자·대문자·뒤집기·base64·hex·URL 인코딩·앞 8자·중간 9자·`client_secret=…`) + Client ID 를 데이터 폴더 모든 파일과 `keys` 모든 출력에서 훑어 0건(`keys list` 의 '끝 4자' 는 기존 설계), 잘못된 키 23가지(공백·따옴표·한글·점·너무 짧음·줄바꿈·키 모양·긴 값·보이지 않는 글자·전각)가 오류 문구에 되풀이되지 않음.
- **Fail-Closed**(`nvcheck.py`·`nvcheck4.py`): ① 깨진 상태 파일 8종(JSON 아님·빈 파일·목록·모르는 판·음수·널 문자·깊은 중첩·디렉터리가 됨)이 모두 `Denied` + 고정 문장 + 파일 그대로 + `.bak` 없음, `keys usage` 는 읽기만 하고 '절반 가정' 문구 대신 새 안내. 다른 용도(이미지)는 예전 방식(절반 가정·`.bak`·새 파일) 그대로. ② 계수 모순 5종(월>한도·일>한도·일>월·성공>시도·월<최고치)과 장부 합 모순 → 차단, `acknowledge` 로 안 풀림(월 초기화에 풀림). ③ 시계 정확히 5분 되돌림 허용·5분 1초 거절·40일 되돌림 거절·거절은 아무것도 안 씀(한계: 자동 해제는 낮음 1). ④ 연결 설정 깨짐 → 거절·파일 그대로. ⑤ 인증 5종(기록 없음·24시간 1초 뒤·정확히 24시간은 허용·인증 실패·시험 오류). ⑥ 잠금을 다른 흐름이 쥐면 `busy`, 쓰기 실패면 `unavailable`·계수 그대로. ⑦ 기록 사라짐(`hold`)은 `acknowledge(confirmed=True)` 에만 풀리고(1·'yes'·None·0 은 거절) 풀면 한도의 절반(13,500·50)부터. 모든 거절 문구가 고정 문장이고 영문 코드·내부 값 노출 0. 공격자 관점: 상태 파일을 지우면 사용량 0(문서에 적힌 한계), 파일 안의 `audit` 를 떼고 판 1 로 고치면 hold·시계·모순 검사가 꺼짐(직접 고친 파일), 시계를 앞으로 보냈다 되돌리면 한 달 가까이 멈춤(`clock`·장부 모순), 되돌린 시계+`acknowledge`(명령에 안 이어져 있음)는 낮음 8 — **자동으로 한도를 풀어 주는 길은 없다**. 두 프로세스가 같은 NAVER 용도를 동시에 140번 부르면 정확히 100 허용·40 거절·시도 100·장부 100·상태 파일 올바름(진짜 파일 잠금). 상태 파일을 무작위로 어긋낸 1,500개: 거절 1,440·허용 59·허용 뒤 파일이 올바르지 않은 경우 0·예외 1(낮음 6).
- **화면·명령줄**: `keys usage naver_apihub`/`keys policy naver_apihub` 가 오늘·이번 달 시도/성공·내부 한도·콘솔 한도·마지막 성공(한국 시간)·마지막 오류(쉬운 한국어+상태)·단계·멈춤 사유를 실제 값(JSON 값과 파일 값 일치)대로 보이고 멈춘 때 고정 문장이 나옴. 위치 인자와 `--purpose` 출력 같음, 서로 다른 용도를 두 번 적으면 사용법 오류(종료 2)이고 입력을 되풀이하지 않음, '검색량'·'조회수' 같은 상대지수 오해 문구 없음(관심도 변화로 적음), 사람이 읽는 화면에 영문 코드 없음. 읽기 명령 16가지는 없는 데이터 폴더를 만들지 않고, 깨진 상태 파일이 있어도 어떤 파일도 바꾸지 않음. 고정 문장은 지시서와 글자 그대로 같음.
- **문서**: 수치(하루 100·월 27,000·콘솔 30,000·최대 50,000·21,000/24,000/27,000·5회·24시간·5분·200건·12자·시험 175개)가 SECURITY·ARCHITECTURE·README·DECISIONS·CHANGELOG·코드·시험에서 같음. '호출 코드는 아직 없다' 를 모든 문서에 적음. D-35 는 다른 묶음과 안 겹침(P0 는 D-36~D-39 를 씀, 모든 가지에서 `| D-35 |` 는 N1 과 같은 내용의 `r134-naver-hub-safety-1`(트리 동일, 제목만 `[R-134]`)뿐). 부족한 곳: 중간 5·6.

## P0 묶음과 겹침 (읽기만 함)
`W\cd_wt_p0` 의 작업 트리(HEAD=`3b1294b`, 아직 커밋 전)가 바꾼 것: `CHANGELOG.md`(맨 끝에 한 줄 덧붙임)·`docs/DECISIONS.md`(D-34 다음에 D-36~D-39 네 행)·새 파일 `docs/TOPIC_ENGINE_PLAN.md` 와 시험 3개. N1 은 같은 두 파일의 **같은 자리**(CHANGELOG 맨 끝, DECISIONS 의 D-34 다음 — D-35 한 행)에 덧붙인다. P0 의 두 문서를 3b1294b 위에 커밋한 사본에서 `git merge-tree --write-tree` 를 해 보니 **충돌 파일은 `CHANGELOG.md`·`docs/DECISIONS.md` 둘뿐**(내용 충돌, 양쪽 줄 유지로 해결; DECISIONS 는 D-35 가 D-36 앞에 오게 정렬). `src/`·`tests/` 는 겹치지 않음(P0 는 아직 소스 변경이 없음). D-35 와 D-36~D-39 는 번호가 겹치지 않는다. 이 PC 의 `origin/main` 은 `3b1294b`(18:54 에 받은 것)이고 N1 은 그 위 한 커밋(빨리감기)이라 충돌 0.

## 시험 줄 (한 번에 하나씩 모듈별, `python -X utf8 -m unittest <모듈>`, 시험 전 여유 메모리 0.8~1.2GB)
| 모듈 | 3.12.10 | 3.10.11 |
|---|---|---|
| `test_service_naver_hub_registry` | Ran 75 tests in 4.443s OK | Ran 75 tests in 4.684s OK |
| `test_service_naver_hub_quota` | Ran 100 tests in 22.684s OK | Ran 100 tests in 32.530s OK |
| `test_service_connections` | Ran 98 tests in 16.344s OK | Ran 98 tests in 19.814s OK |
| `test_service_quota` | Ran 71 tests in 32.961s OK | Ran 71 tests in 40.906s OK |
| `test_service_keys_cli` | Ran 37 tests in 92.181s OK | Ran 37 tests in 97.618s OK |
| `test_security_keystore` | Ran 110 tests in 0.891s OK (skipped=1) | Ran 110 tests in 1.137s OK (skipped=1) |
| `test_service_quota_legacy_locale` | Ran 70 tests in 30.886s OK | Ran 70 tests in 33.586s OK |
| `test_service_doctor` | Ran 45 tests in 5.049s OK | Ran 45 tests in 5.880s OK |
| `test_service_write_json` | Ran 19 tests in 0.620s OK | Ran 19 tests in 0.734s OK |
| `test_service_safety` | Ran 16 tests in 3.318s OK | Ran 16 tests in 3.453s OK |
| `test_service_cli_hardening` | Ran 36 tests in 7.594s OK | Ran 36 tests in 8.191s OK |
| `test_errors_catalog` | Ran 37 tests in 2.672s OK | Ran 37 tests in 1.973s OK |
| `test_repo_layout` | Ran 26 tests in 3.510s OK | Ran 26 tests in 3.654s OK |
| `test_security_shape` | Ran 43 tests in 0.529s OK | Ran 43 tests in 0.623s OK |
| `test_security_mask` | Ran 50 tests in 3.349s OK | Ran 50 tests in 3.541s OK |
| `test_security_mask_boundary` | Ran 17 tests in 3.142s OK | Ran 17 tests in 3.495s OK |
| `test_security_mask_sk` | Ran 22 tests in 5.376s OK | Ran 22 tests in 7.164s OK |
| `test_ui_adapters` | Ran 25 tests in 3.499s OK | Ran 25 tests in 4.088s OK |
| 합계 | 18개 모듈 897개 시험 — OK | 18개 모듈 897개 시험 — OK |

`vermin`·`ruff`·`pyflakes`: 위 낮음 12. `scripts/sync_errors.py --check`: `errors/catalog.py 가 문서와 같다.`

## 변이 표 (새로 설계한 111곳 — 임시 사본에서 한 곳씩 일부러 어기고 새 시험 2모듈(failfast) → 놓치면 기존 8모듈)
| # | 일부러 어긴 곳 | 결과 | 잡은 시험(처음 실패한 것) |
|---|---|---|---|
| 1 | M01 12월 다음 해 넘김 삭제 | 잡힘 | naver_hub_quota.MonthWindowTest: the_month_label_and_the_next_month_start_follow_korean_calenda |
| 2 | M02 다음 달 1일 → 2일(월 경계 +1일) | 잡힘 | naver_hub_quota.MonthWindowTest: a_rolled_day_frees_the_day_but_not_the_month_and_a_rolled_mont |
| 3 | M03 월 라벨을 UTC 달력으로 | 잡힘 | naver_hub_quota.MonthWindowTest: december_rolls_over_into_the_next_years_january |
| 4 | M04 월 라벨 0채움 삭제 | 잡힘 | naver_hub_quota.MonthWindowTest: december_rolls_over_into_the_next_years_january |
| 5 | M05 라벨 선택 뒤바꿈(일↔월) | 잡힘 | naver_hub_quota.AttemptsAndSuccessesTest: a_late_success_is_credited_only_to_the_windows_the_call_starte |
| 6 | M06 _used_of 가 월 창을 일반 창으로 | 잡힘 | naver_hub_registry.CliHubTest: the_human_output_of_the_hub_commands_has_no_english_codes |
| 7 | M07 _next_reset 이 월 창을 모름 | 잡힘 | naver_hub_quota.MonthWindowTest: a_rolled_day_frees_the_day_but_not_the_month_and_a_rolled_mont |
| 8 | M08 _frees_at 월 창 → 하루 뒤 | 잡힘 | naver_hub_quota.MonthWindowTest: the_month_label_and_the_next_month_start_follow_korean_calenda |
| 9 | M09 한도 거절 재시도 시각이 창 종류를 무시 | 잡힘 | naver_hub_quota.MonthWindowTest: a_rolled_day_frees_the_day_but_not_the_month_and_a_rolled_mont |
| 10 | M10 한도 판정 +1(한 번 더 허용) | 잡힘 | naver_hub_quota.AttemptsAndSuccessesTest: the_old_denial_of_another_provider_keeps_its_own_wording |
| 11 | M11 한도 판정 ≤(한 번 덜 허용) | 잡힘 | naver_hub_quota.LedgerTest: the_ledger_keeps_only_the_latwo_hundred_calls |
| 12 | M12 _record 가 월 창을 세지 않음 | 잡힘 | naver_hub_registry.CliHubTest: the_human_output_of_the_hub_commands_has_no_english_codes |
| 13 | S01 단계 판정을 이 호출 빼고(used 만) | 잡힘 | naver_hub_quota.StageTest: a_manual_analysis_may_call_five_at_a_time_after_eighty_percent |
| 14 | S02 단계 검사 전체 끄기 | 잡힘 | naver_hub_quota.StageTest: a_manual_analysis_may_call_five_at_a_time_after_eighty_percent |
| 15 | S03 단계의 거절 목록 무시 | 잡힘 | naver_hub_quota.StageTest: a_stage_denial_asks_the_caller_to_use_the_saved_value_when_it_ |
| 16 | S04 수동 분석 상한 > → ≥ | 잡힘 | naver_hub_quota.StageTest: a_manual_analysis_may_call_five_at_a_time_after_eighty_percent |
| 17 | S05 수동 분석 상한이 selected 에 적용 | 잡힘 | naver_hub_quota.StageTest: a_manual_analysis_may_call_five_at_a_time_after_eighty_percent |
| 18 | S06 단계 거절 재시도 시각 → 다음 자정 | 잡힘 | naver_hub_quota.StageTest: automatic_refresh_stops_above_eighty_percent_and_says_why |
| 19 | S07 닫힘 단계가 절약 모드로만 | **놓침** | OK |
| 20 | S08 단계 문턱 70→71%(비율+1) | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_internal_limits_are_ninety_percent_of_the_console_limit |
| 21 | S09 단계 경계 > → ≥ | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_stage_switches_only_when_the_usage_after_the_call_goes_ove |
| 22 | S10 안내 단계 70→71 | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_stage_switches_only_when_the_usage_after_the_call_goes_ove |
| 23 | S11 제한 단계 80→81 | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_stage_switches_only_when_the_usage_after_the_call_goes_ove |
| 24 | S12 중지 단계 90→91 | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_internal_limits_are_ninety_percent_of_the_console_limit |
| 25 | S14 90% 단계가 critical 은 허용 | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_stage_table_is_exactly_70_80_90_percent |
| 26 | S15 수동 분석 5회 → 6회 | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_internal_limits_are_ninety_percent_of_the_console_limit |
| 27 | R01 내부 일 한도 100→101 | 잡힘 | naver_hub_registry.ApiHubSpecTest: one_provider_without_a_name_never_rotates_and_has_a_day_and_a_ |
| 28 | R02 내부 월 한도 27,000→27,001 | 잡힘 | naver_hub_registry.ApiHubSpecTest: one_provider_without_a_name_never_rotates_and_has_a_day_and_a_ |
| 29 | R03 콘솔 한도 30,000→30,001 | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_internal_limits_are_ninety_percent_of_the_console_limit |
| 30 | R04 rotation never → limited | 잡힘 | naver_hub_registry.ApiHubSpecTest: one_provider_without_a_name_never_rotates_and_has_a_day_and_a_ |
| 31 | R05 max_entries 1→2 | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_purpose_is_first_and_its_basic_properties_are_pinned |
| 32 | R06 fail_closed 반전(False) | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_ledger_and_fail_closed_flags_the_console_limit_and_the_fix |
| 33 | R07 항목 수 검사 ≥ → > | 잡힘 | naver_hub_registry.OneKeyTest: a_second_entry_is_refused_even_with_the_terms_and_another_valu |
| 34 | R08 add_entry 가 옛 용도 거절을 안 함 | 잡힘 | naver_hub_registry.LegacyTest: adding_to_the_legacy_purpose_is_refused_in_plain_korean_and_ch |
| 35 | R09 옛 용도 표시(legacy_to) 삭제 | 잡힘 | naver_hub_registry.ApiHubSpecTest: no_other_purpose_or_provider_has_the_new_flags |
| 36 | R10 옛 용도가 항상 목록에 보임 | 잡힘 | naver_hub_registry.LegacyTest: listed_purposes_follow_the_entries |
| 37 | R11 파일 읽기의 항목 수 검사가 3개로 약해짐 | 잡힘 | naver_hub_registry.OneKeyTest: a_file_with_two_hub_entries_is_an_invalid_file |
| 38 | R12 인증 유효 시간 24시간 → 24000시간 | 잡힘 | naver_hub_registry.AuthStateTest: only_a_fresh_successful_check_is_clear |
| 39 | R13 인증 실패 기록을 불명확으로 | 잡힘 | naver_hub_registry.AuthStateTest: only_a_fresh_successful_check_is_clear |
| 40 | R14 둘째 항목 거절 문구 세부 삭제 | 잡힘 | naver_hub_registry.OneKeyTest: the_refusal_says_one_key_in_plain_korean_and_why |
| 41 | R15 고정 문구 변경(저장된 정보 삭제) | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_ledger_and_fail_closed_flags_the_console_limit_and_the_fix |
| 42 | R16 키 글자 범위 검사 끄기(alnum) | 잡힘 | naver_hub_registry.CheckFieldsTest: a_secret_with_a_dot_is_refused_naming_the_field_but_not_the_va |
| 43 | R17 Client ID 최대 길이 128→129 | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_two_fields_are_loose_alnum_values_of_8_to_128_characters |
| 44 | R18 Client Secret 최소 길이 8→7 | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_two_fields_are_loose_alnum_values_of_8_to_128_characters |
| 45 | R19 장부 제공자 표시(ledger)를 끔 | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_ledger_and_fail_closed_flags_the_console_limit_and_the_fix |
| 46 | F01 깨진 파일을 이 용도에도 절반 가정 | 잡힘 | naver_hub_quota.FailClosedTest: another_provider_repairs_the_file_the_old_way_but_this_one_sta |
| 47 | F02 상태 파일 못 읽음 검사 끄기 | 잡힘 | naver_hub_quota.FailClosedTest: a_broken_state_file_denies_and_is_neither_moved_nor_repaired_b |
| 48 | F03 hold(기록이 사라짐) 검사 끄기 | 잡힘 | naver_hub_quota.FailClosedTest: another_provider_repairs_the_file_the_old_way_but_this_one_sta |
| 49 | F04 시계 되돌림 검사 끄기 | 잡힘 | naver_hub_quota.FailClosedTest: a_clock_one_second_beyond_five_minutes_back_is_denied_and_noth |
| 50 | F05 시계 허용 오차 5→6분 | 잡힘 | naver_hub_quota.FailClosedTest: a_clock_one_second_beyond_five_minutes_back_is_denied_and_noth |
| 51 | F06 인증 검사 끄기 | 잡힘 | naver_hub_registry.CliHubTest: policy_while_stopped_shows_the_fixed_sentence_and_json_has_the |
| 52 | F07 인증 불명확을 통과 | 잡힘 | naver_hub_registry.CliHubTest: policy_while_stopped_shows_the_fixed_sentence_and_json_has_the |
| 53 | F08 월 계수 한도 초과 ≥(경계) | 잡힘 | naver_hub_quota.FailClosedTest: a_day_above_the_limit_is_an_anomaly_but_exactly_the_limit_is_o |
| 54 | F09 성공>시도 검사 삭제 | 잡힘 | naver_hub_quota.FailClosedTest: more_successes_than_attempts_is_refused_as_a_broken_file_and_a |
| 55 | F10 일>월 검사 ≥ | 잡힘 | naver_hub_registry.CliHubTest: the_human_output_of_the_hub_commands_has_no_english_codes |
| 56 | F11 월 최고 계수 비교 약화 | 잡힘 | naver_hub_quota.FailClosedTest: a_month_count_below_the_highest_one_seen_is_an_anomaly_but_onl |
| 57 | F12 장부 합 비교 삭제 | 잡힘 | naver_hub_quota.FailClosedTest: the_ledger_cannot_hold_more_calls_than_the_month_count |
| 58 | F13 last_seen 이 뒤로도 움직임 | 잡힘 | naver_hub_quota.FailClosedTest: a_clock_that_went_back_by_exactly_five_minutes_is_still_allowe |
| 59 | F14 acknowledge 가 확인 표시 없이 통과 | 잡힘 | naver_hub_quota.FailClosedTest: the_operator_confirmation_needs_an_explicit_true_and_a_fail_cl |
| 60 | F15 acknowledge 가 절반 재계수를 안 함 | 잡힘 | naver_hub_quota.FailClosedTest: another_provider_repairs_the_file_the_old_way_but_this_one_sta |
| 61 | F16 Fail-Closed 도 깨진 파일을 스스로 옮김 | 잡힘 | naver_hub_quota.FailClosedTest: a_broken_state_file_denies_and_is_neither_moved_nor_repaired_b |
| 62 | F17 고정 문구 대신 구체 사유 노출 | 잡힘 | naver_hub_quota.FailClosedTest: a_broken_connection_settings_file_denies_with_the_fixed_senten |
| 63 | F18 _closed_wording 이 사유(cause)를 비움 | 잡힘 | naver_hub_quota.FailClosedTest: a_broken_connection_settings_file_denies_with_the_fixed_senten |
| 64 | F19 연결 설정 깨짐을 허용으로 | 잡힘 | SyntaxError: unmatched ')' |
| 65 | L01 성공/실패 뒤바꿈 | 잡힘 | naver_hub_registry.CliHubTest: usage_after_real_traffic_shows_attempts_and_successes_and_the_ |
| 66 | L02 모든 결과를 성공으로 셈 | 잡힘 | naver_hub_registry.CliHubTest: usage_after_real_traffic_shows_attempts_and_successes_and_the_ |
| 67 | L03 성공 수 상한(시도 수) 제거 | 잡힘 | naver_hub_quota.AttemptsAndSuccessesTest: reporting_the_same_call_twice_cannot_push_successes_above_atte |
| 68 | L04 월 창을 시도로 세지 않음 | 잡힘 | naver_hub_registry.CliHubTest: the_human_output_of_the_hub_commands_has_no_english_codes |
| 69 | L05 캐시 적중이 시도로 셈 | 잡힘 | naver_hub_quota.LedgerTest: a_cache_hit_before_any_call_creates_the_ledger_bucket_with_emp |
| 70 | L06 장부 상한 200→201 | 잡힘 | naver_hub_quota.LedgerTest: the_ledger_keeps_only_the_latwo_hundred_calls |
| 71 | L07 조건 해시 길이 12→16 | 잡힘 | naver_hub_quota.LedgerTest: the_condition_hash_is_twelve_hex_characters_independent_of_key |
| 72 | L08 비밀 칸 이름 거절 끄기 | 잡힘 | naver_hub_quota.LedgerTest: a_condition_with_a_credential_like_field_name_or_a_non_json_va |
| 73 | L09 조건 정규화 삭제(NFC·공백) | 잡힘 | naver_hub_quota.LedgerTest: the_condition_hash_is_twelve_hex_characters_independent_of_key |
| 74 | L10 조건 해시 키 정렬 삭제 | 잡힘 | naver_hub_quota.LedgerTest: the_condition_hash_is_twelve_hex_characters_independent_of_key |
| 75 | L11 장부가 상태의 일부를 안 남김(last_success 갱신 삭제) | 잡힘 | naver_hub_registry.CliHubTest: usage_after_real_traffic_shows_attempts_and_successes_and_the_ |
| 76 | L12 상태 파일 판 항상 2 | 잡힘 | naver_hub_quota.AttemptsAndSuccessesTest: other_providers_keep_the_old_state_shape_and_the_old_dict_shap |
| 77 | L13 모르는 판 3을 읽음 | 잡힘 | naver_hub_quota.FailClosedTest: a_broken_state_file_denies_and_is_neither_moved_nor_repaired_b |
| 78 | L14 한도 소진 응답이 장부 제공자 시도 수를 채움 | 잡힘 | naver_hub_quota.AttemptsAndSuccessesTest: every_failure_kind_counts_the_attempt_but_never_a_success |
| 79 | L15 HTTP 상태 범위 확대 | 잡힘 | naver_hub_quota.AttemptsAndSuccessesTest: the_http_status_is_stored_only_in_the_range_one_hundred_to_fiv |
| 80 | L16 성공>시도 모양 검사 < | 잡힘 | naver_hub_registry.CliHubTest: the_human_output_of_the_hub_commands_has_no_english_codes |
| 81 | L17 옛 용도도 사용량에 나옴 | 잡힘 | naver_hub_registry.LegacyTest: usage_hides_the_legacy_purpose_even_when_it_has_entries |
| 82 | V01 오류 종류 문구가 영문 코드 | 잡힘 | naver_hub_registry.CliHubTest: the_human_output_of_the_hub_commands_has_no_english_codes |
| 83 | V02 이번 달 시도/성공 뒤바꿈 | 잡힘 | naver_hub_registry.CliHubTest: usage_after_real_traffic_shows_attempts_and_successes_and_the_ |
| 84 | V03 단계 줄 삭제 | 잡힘 | naver_hub_registry.LedgerLinesTest: the_stage_line_appears_only_when_the_stage_is_not_ok |
| 85 | V04 호출 중지 때 고정 문구 대신 사유만 | 잡힘 | naver_hub_registry.CliHubTest: policy_while_stopped_shows_the_fixed_sentence_and_json_has_the |
| 86 | V05 CLI 가 옛 용도 거절을 안 함(키 묻기 전) | 잡힘 | naver_hub_registry.LegacyTest: the_cli_refuses_the_legacy_purpose_before_reading_or_asking_fo |
| 87 | V06 CLI 의 키 1개 용도 조기 거절 삭제 | 잡힘 | naver_hub_registry.OneKeyTest: the_cli_refuses_the_second_key_before_reading_stdin_or_asking_ |
| 88 | V07 usage 용도 중복 불일치 검사 반전 | 잡힘 | naver_hub_registry.CliHubTest: two_different_purposes_are_a_usage_error |
| 89 | V08 purposes 목록에 옛 용도 포함 | 잡힘 | naver_hub_registry.CliHubTest: purposes_json_adds_the_extra_keys_only_for_the_hub |
| 90 | V09 keys list 상태 줄에 옛 용도 항상 포함 | 잡힘 | naver_hub_registry.LegacyTest: the_purpose_status_block_lists_the_legacy_purpose_only_when_it |
| 91 | V10 월 한도 표시 라벨 '이번 달' → '하루' | 잡힘 | naver_hub_registry.CliHubTest: purposes_json_adds_the_extra_keys_only_for_the_hub |
| 92 | N01 단계 이름 closed→stop | 잡힘 | naver_hub_registry.ApiHubSpecTest: the_stage_switches_only_when_the_usage_after_the_call_goes_ove |
| 93 | N02 다른 제공자 일괄 갱신 몫 30→31% | 잡힘 | naver_hub_quota.PinsTest: the_constants_the_rules_depend_on_are_pinned |
| 94 | N03 마지막 예약 10→11%(표시) | 잡힘 | naver_hub_quota.PinsTest: the_constants_the_rules_depend_on_are_pinned |
| 95 | N04 시계 거절이 하루 넘게 되돌아가면 풀림(자동 해제) | **놓침** | OK |
| 96 | N05 캐시 적중 표시를 장부에 안 남김 | 잡힘 | naver_hub_quota.LedgerTest: a_cache_hit_is_noted_without_counting_an_attempt_or_a_success |
| 97 | N06 화면의 마지막 성공 시각을 안 보임 | 잡힘 | naver_hub_registry.CliHubTest: usage_after_real_traffic_shows_attempts_and_successes_and_the_ |
| 98 | N07 호출 시작 때 장부 상한을 안 자름 | 잡힘 | naver_hub_quota.LedgerTest: a_smaller_ledger_limit_drops_the_oldest_and_a_record_that_left |
| 99 | N08 재시도 횟수를 늘 0 으로 적음 | 잡힘 | naver_hub_quota.LedgerTest: the_first_attempt_has_no_retries_and_the_second_try_of_the_sam |
| 100 | P01 acknowledge 가 지금 시계를 마지막 본 시각으로 안 받아들임 | 잡힘 | naver_hub_quota.FailClosedTest: the_operator_confirmation_accepts_the_current_clock_and_reopen |
| 101 | P02 월 최고 계수 갱신 안 함 | 잡힘 | naver_hub_quota.FailClosedTest: a_month_count_below_the_highest_one_seen_is_an_anomaly_but_onl |
| 102 | P03 연결 시험 호출(acquire_entry)이 Fail-Closed 검사를 건너뜀 | 잡힘 | naver_hub_quota.FailClosedTest: another_provider_repairs_the_file_the_old_way_but_this_one_sta |
| 103 | P04 오늘 장부 합 검사가 월 라벨로 | 잡힘 | naver_hub_quota.AttemptsAndSuccessesTest: a_late_success_is_credited_only_to_the_windows_the_call_starte |
| 104 | P05 늦은 성공을 새 창에도 올림 | 잡힘 | naver_hub_quota.AttemptsAndSuccessesTest: a_late_success_is_credited_only_to_the_windows_the_call_starte |
| 105 | P06 오늘 성공 칸에 시도 수를 보임 | 잡힘 | naver_hub_registry.CliHubTest: usage_after_real_traffic_shows_attempts_and_successes_and_the_ |
| 106 | P07 usage 행에서 성공 수를 안 보임 | 잡힘 | naver_hub_registry.CliHubTest: usage_json_carries_the_ledger_and_the_attempt_and_success_colu |
| 107 | P08 깨진 파일에도 캐시 적중을 장부에 적음 | 잡힘 | naver_hub_quota.LedgerTest: a_cache_hit_is_not_noted_without_a_key_or_with_a_broken_state_ |
| 108 | P09 모르는 hold 값을 올바른 모양으로 받음 | **놓침** | OK |
| 109 | P10 장부 기록의 HTTP 상태 모양 검사 느슨 | 잡힘 | naver_hub_quota.SchemaTest: every_shape_rule_of_the_ledger_parts_is_enforced |
| 110 | P11 장부 길이 모양 검사 느슨(상한 무시) | 잡힘 | naver_hub_quota.SchemaTest: every_shape_rule_of_the_ledger_parts_is_enforced |
| 111 | P12 keys policy 가 사용량을 안 붙임 | 잡힘 | naver_hub_registry.CliHubTest: policy_shows_the_single_key_rule_the_stage_table_and_the_curre |

합계 111곳: 잡힘 108·놓침 3
- 놓친 것 `S07 닫힘 단계가 절약 모드로만` — 동등 변이(기본 한도에서는 월 창이 먼저 막아 결과가 같다 — 낮음 13).
- 놓친 것 `N04 시계 거절이 하루 넘게 되돌아가면 풀림(자동 해제)` — 시험 공백 — 낮음 15(시계를 하루 넘게 되돌리는 시험이 없다).
- 놓친 것 `P09 모르는 hold 값을 올바른 모양으로 받음` — 시험 공백(동등에 가까움) — 낮음 16.

## 못 확인한 것
- 진짜 NAVER 서버의 동작(실패 호출이 사용량에 들어가는지·월 초기화 시각·약관) — 공개 문서에 없고 호출이 금지라 확인하지 못함. 코드는 안전한 쪽(실패도 시도·한국 달력 월·10% 여유)으로 정해져 있음.
- 진짜 윈도 자격 증명 관리자(가짜 보관소만 씀; `security/keystore.py` 는 이번 변경에 없음).
- 이 PC 안 `origin/main`(3b1294b) 이후의 main — GitHub 접근 금지로 더 새 main 은 못 봄.
- 전체 시험 95개 모듈 중 18개만 돌림(나머지는 push 한 CI 몫). 창을 띄운 시험·`ui/` 시험은 돌리지 않음(이 변경은 `ui/` 를 안 건드림).
- 변이는 '새 시험 2모듈 → 기존 8모듈' 순서로 잡힘 여부만 봤고, 놓친 1곳(S07)이 동등인지는 숫자 계산으로 판단함(기본 한도에서 월 창이 먼저 막음).
- 시험 시작 전 여유 메모리가 0.8~1.2GB 로 대체로 1.0GB 아래였고, 3.10.11 시험과 변이 실행을 20:40~20:46 에 한 번 겹쳐 돌렸다(각각 파이썬 한 개씩, 다른 에이전트 프로세스는 건드리지 않음).
- 차분 시험은 이 PC 의 윈도 임시 쓰기 실패 잡음으로 11개 시나리오를 다시 돌렸다.


## 부록 — 델타 변이 표 (새로 설계한 24곳, 새 시험 3클래스 + 개명 시험만으로)
| # | 일부러 어긴 곳 | 결과 | 잡은 시험(처음 실패한 것) |
|---|---|---|---|
| 1 | X01 인증 갱신 상태 범위 상한 포함(<300 → <=300) | 잡힘 | naver_hub_quota.AuthRefreshTest: a_success_with_an_ambiguous_status_or_an_unused_response_does_ |
| 2 | X02 인증 갱신 상태 범위 하한 199 | 잡힘 | naver_hub_quota.AuthRefreshTest: a_success_with_an_ambiguous_status_or_an_unused_response_does_ |
| 3 | X03 인증 갱신 상태 범위 상한 299 제외 | 잡힘 | naver_hub_quota.AuthRefreshTest: a_success_with_an_ambiguous_status_or_an_unused_response_does_ |
| 4 | X04 응답 못 씀(False)을 무시 | 잡힘 | naver_hub_quota.AuthRefreshTest: a_success_with_an_ambiguous_status_or_an_unused_response_does_ |
| 5 | X05 상태 미기재는 갱신 안 함 | 잡힘 | naver_hub_quota.AuthRefreshTest: a_success_with_an_ambiguous_status_or_an_unused_response_does_ |
| 6 | X06 다른 제공자도 성공 보고로 connections.json 갱신 | 잡힘 | naver_hub_quota.AuthRefreshTest: providers_without_the_fail_closed_gate_do_not_touch_the_connec |
| 7 | X07 실패 결과도 갱신 | 잡힘 | naver_hub_quota.AuthRefreshTest: a_failure_of_any_kind_never_refreshes_the_last_success_time |
| 8 | X08 마지막 성공 시각을 한도 기록 저장보다 먼저 적음 | 잡힘 | naver_hub_quota.AuthRefreshTest: a_success_report_that_cannot_write_the_connection_file_still_k |
| 9 | X09 월 창이 있어도 다음 자정(옛 동작) | 잡힘 | naver_hub_quota.ExhaustedRestTest: a_server_reset_time_within_forty_eight_hours_wins_and_a_farthe |
| 10 | X10 월 창 쉬는 시각을 다음 자정으로 | 잡힘 | naver_hub_quota.ExhaustedRestTest: a_server_reset_time_within_forty_eight_hours_wins_and_a_farthe |
| 11 | X11 서버 초기화 시각 48시간 제한 삭제 | 잡힘 | naver_hub_quota.ExhaustedRestTest: a_server_reset_time_within_forty_eight_hours_wins_and_a_farthe |
| 12 | X12 서버 초기화 시각이 지금과 같아도 받아들임 | 잡힘 | naver_hub_quota.ExhaustedRestTest: a_server_reset_time_within_forty_eight_hours_wins_and_a_farthe |
| 13 | X13 서버 초기화 시각 정확히 48시간은 제외 | 잡힘 | naver_hub_quota.ExhaustedRestTest: a_server_reset_time_within_forty_eight_hours_wins_and_a_farthe |
| 14 | X14 옛 용도 판정이 늘 아님 | 잡힘 | naver_hub_quota.LegacyAcquireTest: the_connection_call_of_a_legacy_entry_is_refused_too |
| 15 | X15 acquire 가 옛 용도 거절을 안 함 | 잡힘 | naver_hub_quota.LegacyAcquireTest: the_legacy_purpose_is_refused_even_with_no_entry_at_all_instea |
| 16 | X16 acquire_entry 가 옛 용도 거절을 안 함 | 잡힘 | naver_hub_quota.LegacyAcquireTest: the_connection_call_of_a_legacy_entry_is_refused_too |
| 17 | X17 옛 용도 거절 코드를 no_key 로 | 잡힘 | naver_hub_quota.LegacyAcquireTest: the_connection_call_of_a_legacy_entry_is_refused_too |
| 18 | X18 옛 용도 거절이 degraded=False | 잡힘 | naver_hub_quota.LegacyAcquireTest: the_connection_call_of_a_legacy_entry_is_refused_too |
| 19 | X19 인증 실패로 멈춘 항목도 되살림 | 잡힘 | naver_hub_quota.AuthRefreshTest: a_late_success_does_not_revive_an_entry_stopped_for_failed_aut |
| 20 | X20 성공 보고가 마지막 시험 시각도 바꿈 | 잡힘 | naver_hub_quota.AuthRefreshTest: a_successful_report_refreshes_the_last_success_time_and_leaves |
| 21 | X21 성공 보고가 마지막 성공 시각을 안 바꿈 | 잡힘 | naver_hub_quota.AuthRefreshTest: a_success_with_an_ambiguous_status_or_an_unused_response_does_ |
| 22 | X22 마지막 성공 시각을 처음 한 번만 적음 | 잡힘 | naver_hub_quota.AuthRefreshTest: a_success_with_an_ambiguous_status_or_an_unused_response_does_ |
| 23 | X23 성공 보고가 확인 결과(check_result)를 안 바꿈 | 잡힘 | naver_hub_quota.AuthRefreshTest: mark_call_ok_changes_only_the_last_success_and_the_check_resul |
| 24 | X24 성공 보고의 마지막 성공 시각이 24시간 창을 안 이어 줌(시계 +1일 앞 기록) | 잡힘 | naver_hub_quota.AuthRefreshTest: a_success_with_an_ambiguous_status_or_an_unused_response_does_ |

합계 24곳: 잡힘 24·놓침 0
