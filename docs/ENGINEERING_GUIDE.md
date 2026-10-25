# 엔지니어링 가이드 — 코드 작성과 검증

> 대상: 이 저장소의 코드·워크플로·프롬프트를 고치는 모든 AI와 사람.
> 상위 규칙: [`CHARTER.md`](./CHARTER.md)(등급·협업), [`SECURITY_GUARDRAILS.md`](./SECURITY_GUARDRAILS.md)(보안). 구조: [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## 1. 환경과 명령

| 목적 | 명령 (저장소 루트에서) |
|------|------------------------|
| 검증 도구 설치 | `python -m pip install -r requirements-dev.txt` |
| 저장소 가드레일 검증 | `python scripts/validate_repo.py` (경고도 실패로: `--strict`) |
| 단위 테스트 | `python -m unittest discover -s tests` |
| 워크플로 정적 분석 | `actionlint` |
| 레지스트리 검증·요약 | `python -m pipeline.registry` |
| 블로그 드라이런 | `python -m pipeline.run --blog blogger_macat --dry-run` |
| 매트릭스 확인 | `python -m pipeline.plan --platform blogger` |
| 워치독 드라이런 | `python scripts/watchdog.py` (토큰이 없으면 출력만) |
| 이슈 수정 시스템 동기화 검사 | `python scripts/build_pages_registry.py --check` · `python scripts/sync_issue_form.py --check` (갱신은 `--check` 없이) |

- Python **3.10 이상** 문법만 쓴다(CI는 3.10과 3.12). 이 PC처럼 3.12만 있어도 3.10 전용 기능 금지.
- Windows는 시스템 `core.autocrlf=true`가 기본이다. 끄지 않는다(끄면 거의 모든 파일이 수정으로 보인다).
- 테스트·스크립트 실행 시 `-I`(격리 모드) 옵션을 쓰지 않는다. 저장소 루트를 import 경로로 쓴다.

## 2. 코드 작성 원칙

| # | 원칙 | 예 / 반례 |
|---|------|-----------|
| R1 | 블로그별 차이는 **설정**에 둔다 | ✅ `blogs.json`·프로필에 값 추가 / ❌ `if blog == "x":` 분기, 블로그용 스크립트 복사 |
| R2 | **순수 로직과 I/O를 분리**한다 | ✅ `gates.py`·`health.py`는 입출력 없음 / I/O는 `run.py`·`watchdog.py`·`publishers/` |
| R3 | 의존성은 **주입**한다 | `run(llm=…, publisher_factory=…, now=…, rng=…, out=…)` — 테스트가 가짜를 끼운다 |
| R4 | 표준 라이브러리를 우선한다 | 새 패키지는 T2. 버전 범위를 고정하고 `requirements-*.txt`에 둔다 |
| R5 | **LLM 출력은 검증 후에만** 쓴다 | 형식 파싱 → 정화 → 게이트. 파일 경로·명령·URL을 LLM이 정하게 하지 않는다 |
| R6 | 오류를 **분류**한다 | 설정 오류 2 / 인프라 실패 1 / 정상 건너뜀 0. 예외를 삼키지 말고, 삼켜야 하면 이유를 주석과 이력에 남긴다 |
| R7 | **멱등·재시도 안전** | 쓰기 전 존재 확인, 재시도 전 중복 확인, 파일은 임시 파일→교체(`state.write_json_atomic`) |
| R8 | 시간은 **UTC aware**, 날짜 경계만 KST | naive `datetime` 금지. 테스트에서는 `now`를 주입한다 |
| R9 | 로그는 사람이 읽는 한 줄 + **시크릿 마스킹** | 토큰·키·프롬프트 전문·예외의 원문 응답을 그대로 출력하지 않는다(`llm.mask`) |
| R10 | **손상된 상태는 덮어쓰지 않는다** | 이력 파일이 깨졌으면 종료 코드 1(`StateError`). 빈 목록으로 초기화하면 중복 방지가 무너진다 |
| R11 | 파일을 **통째로 덮어쓰지 않는다** | 최소 diff. 생성물은 생성기만 쓴다 |
| R12 | 새 플랫폼은 **어댑터**로 | 기존 블로그 코드를 복사하지 않는다([`ARCHITECTURE.md`](./ARCHITECTURE.md) §7) |
| R13 | CLI는 **어떤 콘솔에서도 죽지 않게** | 진입점 `main()` 첫 줄에 `pipeline.console.safe_output()`. Windows 한국어 콘솔(cp949)은 `—`·이모지를 출력하면 예외로 멈춘다(CI의 Linux는 UTF-8이라 드러나지 않는다) |
| R14 | 게시되는 문서(`.md`)에 **Liquid 구문을 쓰지 않는다** | GitHub Pages는 front matter 없는 `.md`도 Liquid로 처리해, 중괄호-퍼센트 태그 예시가 사이트 빌드를 깨뜨렸다(D-24). 예시는 문장으로 풀어 쓴다. 검증기 **LIQUID-1** |

## 3. 워크플로 작성 원칙

| # | 원칙 | 강제 |
|---|------|------|
| W1 | 최상위 `permissions`를 **명시하고 최소**로. 쓰기 권한은 필요한 job에만 | **WF-1** |
| W2 | 신뢰할 수 없는 값은 **`env:`로 받아 `"$VAR"`로 쓴다**(`run:`에 GitHub 표현식(달러 기호+이중 중괄호)을 직접 보간 금지) | **WF-4** |
| W3 | 모든 job에 `timeout-minutes`, 스케줄 워크플로에 `concurrency` | **WF-7·WF-8** |
| W4 | `\|\| true`, `continue-on-error`로 실패를 숨기지 않는다. 필요한 재시도는 명시적 루프로 | **WF-6** |
| W5 | 외부 액션은 SHA 고정, 패키지는 버전 범위 | **WF-5**·**DEP-1** |
| W6 | 커밋을 push하는 워크플로가 사이트를 바꾼다면 **배포를 dispatch**한다 | **WF-10** |
| W7 | `schedule.cron`은 레지스트리와 같게. 수동 실행 입력(`dry_run`, `publish`, 대상 블로그)을 제공한다 | **REG-2** |
| W8 | 시크릿은 `secrets[...]` → `env`로만. `echo` 금지 | **WF-9**·**REG-3** |
| W9 | 변경 후 `actionlint`가 0건이어야 한다 | CI |

## 4. 프롬프트·프로필 규칙

- 프롬프트(`.github/editorial/*`)는 톤·구조를, **정책·검증 기준은 프로필 JSON**에 둔다. 코드에 금지어를 박지 않는다.
- 금지 표현·패턴을 **추가(강화)**하는 것은 T1, **줄이거나 완화**하는 것은 T2(총괄 승인). 규칙을 바꾸면 `tests/test_gates.py`에 그 규칙을 보여 주는 케이스를 함께 추가한다.
- 프롬프트를 바꾸면 L2(드라이런)와 L3(초안) 결과를 확인한다. 게이트 통과율이 떨어지면 프롬프트를 고치고, 게이트를 풀지 않는다.

## 5. 테스트 작성 규칙

1. **결정론**: 시간·난수·LLM·게시 API는 주입한다. 네트워크·실제 시크릿을 쓰는 테스트는 금지.
2. **성공 경로만 쓰지 않는다.** 게이트 탈락, LLM 실패, 게시 실패(인증·일시 오류·중복), 손상된 파일, 일일 상한, 킬 스위치를 반드시 포함한다.
3. **보안 회귀 테스트**: 우회 페이로드(`<scr<script>ipt>`, 이벤트 핸들러, `javascript:` 링크 등)를 케이스로 남긴다. 새 우회가 발견되면 먼저 실패하는 테스트를 추가하고 고친다.
4. **실제 비밀처럼 보이는 리터럴을 소스에 쓰지 않는다.** 테스트에서는 런타임에 문자열을 조합한다(검증기 SEC-2 회피용 `allow` 표시에 기대지 않는다).
5. **테스트가 실제로 실패하는지 확인**한다. 고친 코드를 잠시 되돌렸을 때 테스트가 깨지지 않으면 그 테스트는 쓸모가 없다.
6. 임시 저장소는 `tests/test_run.py`의 `make_root()`를 쓴다(레지스트리·프로필·프롬프트를 복사하고 나머지는 빈 파일).

### 자주 하는 확장 작업

| 작업 | 절차 |
|------|------|
| 게이트 규칙 추가 | 프로필 JSON 수정 → `tests/test_gates.py`에 케이스 → `python -m pipeline.registry`(정규식 컴파일 확인) |
| 검증기 검사 추가 | `scripts/validate_repo.py`에 `check_*` 함수 + `run_checks`에 등록 → `tests/test_validate_repo.py` → [`SECURITY_GUARDRAILS.md`](./SECURITY_GUARDRAILS.md) §6 매핑표 갱신 |
| 어댑터 추가 | [`ARCHITECTURE.md`](./ARCHITECTURE.md) §7.B. 가짜 서비스로 재시도·중복·인증 실패 테스트(`tests/test_publisher_blogger.py` 참고) |
| 감시 규칙 추가 | `pipeline/health.py`에 순수 함수로 추가 → `tests/test_health.py` |

## 6. 검증 사다리

| 단계 | 무엇을 | 명령 / 방법 | 통과 기준 |
|------|--------|-------------|-----------|
| **L0 정적** | 문법·보안 규칙·설정 일관성 | `python scripts/validate_repo.py` · `actionlint` · `python -m pipeline.registry` | 오류 0건 |
| **L1 단위** | 로직(성공+실패 경로) | `python -m unittest discover -s tests` | 전부 통과, 네트워크 없음 |
| **L2 드라이런** | 전체 흐름(스텁 LLM, 파일·게시 없음) | `python -m pipeline.run --blog <key> --dry-run` 또는 Actions `dry_run` 체크 | 종료 코드 0, 변경 파일 없음. 예외: Chance 드라이런은 모든 분야에 검증된 기사가 없거나 소스에 접속하지 못하면 종료 1이다(이상 신호, `docs/ARCHITECTURE.md` §4-1) — 실행 요약의 탈락 사유를 확인하고 기사가 있을 때 다시 실행한다 |
| **L3 초안** | 실제 LLM·게이트·초안 저장, **게시 없음** | Actions → Blogger Generate → Run workflow(`publish` 미체크) | `draft`/`generated_unpublished` 기록, 초안 내용 확인 |
| **L4 카나리** | 실제 게시 소량 관찰 | `mode: auto`, 상한 1건/일, 3일 이상 | `posted` 연속, 워치독 이슈 0, 게시글 확인 |
| **L5 운영** | 지속 감시 | 워치독 일 2회, Actions 실패 메일 | 이슈 0건 |

변경 등급별 최소 단계: **T0** L0 · **T1** L0+L1(+해당 시 L2) · **T2** L0+L1+L2+L3, **독립 검증** · **T3** 사용자 승인 후 T2와 같음(광고 표면은 변경 전후 화면 확인).

Actions의 L2·L3는 저장소 Actions 탭에서 수동으로 실행한다. 이 환경에서 직접 실행할 수 없으면 "실행 필요"라고 WORKLOG에 적고 사용자·다음 AI에게 넘긴다. **실행하지 않은 검증을 통과했다고 쓰지 않는다.**

## 7. 완료 정의 (DoD)

WORKLOG 항목에 복사해서 체크한다.

```
- [ ] 변경 등급(T0~T3)을 정했다. T3이면 사용자 승인(날짜·요지)을 받았다
- [ ] 최신 main 위에서 작업했다 (git pull --rebase)
- [ ] 최소 diff — 관련 없는 파일·서식 변경, 파일 통째 덮어쓰기가 없다
- [ ] 새/변경 로직에 테스트(성공+실패 경로)가 있고 네트워크 없이 통과한다
- [ ] python scripts/validate_repo.py → 오류 0건
- [ ] python -m unittest discover -s tests → 통과
- [ ] (워크플로) actionlint 0건
- [ ] (블로그 동작) --dry-run 통과
- [ ] diff에 비밀·내부 정보·로컬 경로가 없다
- [ ] 문서(HANDLER 현황, 레지스트리, 관련 docs)와 코드가 일치한다
- [ ] WORKLOG.md 최상단에 항목(검증 증거 포함)을 남겼다
- [ ] 커밋 메시지에 AI 이름·대상을 적었다
```

## 8. 커밋·브랜치·WORKLOG

- 커밋 메시지: `type: 요약 (AI이름) [대상: Chance_Blog | Blogger | 공통]`. type은 `feat`·`fix`·`docs`·`chore`·`test`.
  광고 표면을 승인받아 고쳤다면 본문에 `Ad-Surface-Approved: <사유>` 한 줄.
- 브랜치: T0·T1은 main에 직접 가능. T2 이상은 `ai/<도구>/<주제>` 브랜치에서 작업한다. PR을 만들 수 없으면 diff 요약과 검증 결과를 사용자·총괄에게 보내 승인받는다.
- push 직전에 `git pull --rebase origin main`. 봇이 main에 직접 커밋한다.
- WORKLOG 항목 템플릿(기존 + 검증 증거):

```markdown
## [YYYY-MM-DD] AI이름 – 작업 제목

**작업자**: …  **대상**: Chance_Blog / Blogger / 공통  **등급**: T0~T3
**목적**: 한 줄

### 변경 사항
### 검증 증거
- 실행한 명령과 결과 요약(통과/실패 수), 실행하지 못한 검증은 "실행 필요"로 명시
### 다음 AI에게 남기는 주의사항
### 남은 이슈 / 확인할 점
```

## 9. 독립 검증(Verifier) 체크리스트

구현자의 설명을 전제로 삼지 말고 diff와 실행 결과만 본다.

1. diff만으로 변경 의도를 설명할 수 있는가? 범위 밖 변경은 없는가?
2. 실패 경로(LLM 실패, 게이트 탈락, 게시 실패, 손상된 파일)에서 무엇이 일어나는가? 조용히 넘어가는 곳은 없는가?
3. 두 번 실행해도 안전한가(멱등)? 재시도가 중복 게시를 만들 수 있는가?
4. 로그·예외·이력에 비밀이 새지 않는가?
5. 신뢰 경계: LLM·외부 입력이 명령·경로·URL·권한 결정에 쓰이는가?
6. 워크플로 권한이 늘었는가? 늘었다면 필요한 이유가 있는가?
7. 변경을 되돌리면 테스트가 실제로 실패하는가?
8. 문서·레지스트리·검증기와 일치하는가?
9. 광고 표면 파일을 건드렸는가? 승인 표시가 있는가?
10. 롤백 방법이 있는가(`git revert`, `mode: off`, `PIPELINE_PAUSE`)?

## 10. 롤백

| 상황 | 방법 |
|------|------|
| 코드·워크플로 회귀 | `git revert <sha>` 후 push |
| 블로그 한 곳을 멈춤 | `blogs.json`의 `mode: "off"` (T3 아님, 안전 방향) |
| 전체를 멈춤 | 저장소 Settings → Variables에 `PIPELINE_PAUSE=true` |
| 워크플로 하나를 멈춤 | Actions 탭 → 해당 워크플로 Disable |
| 잘못 게시된 글 | [`SECURITY_GUARDRAILS.md`](./SECURITY_GUARDRAILS.md) §4-B |

## 11. 실제로 있었던 실수

| 실수 | 결과 | 예방 |
|------|------|------|
| 낡은 로컬 사본으로 `generator.py` 통째 교체(`32a2469`) | 이미지 전용 이슈 처리 소실(D-01) | R11, 최신 main에서 작업, CI |
| 문서에는 "완료", main에는 코드 없음 | 다음 AI가 있는 기능으로 오해(D-06) | 완료 기록은 main + 검증 통과 후에만 |
| `GITHUB_TOKEN` push 후 배포 누락 | 봇 글이 다음 사람 push 때까지 게시 안 됨(D-02) | W6, 검증기 WF-10 |
| 오래된 모델 이름 하드코딩 | 첫 실행이 모든 모델 실패(D-04) | 모델 목록을 레지스트리에, 검증기 REG-4 |
| `\|\| true`로 `git add` 오류 은폐 | 실패가 성공처럼 보임(D-05) | W4, 검증기 WF-6 |
| CRLF 이중 변환(`\r\r\n`) 9개 파일 | git이 텍스트로 인식 못 함 | `autocrlf` 유지, 도구가 만든 파일 줄 끝 확인 |
| `auto_sync.bat`(30초마다 `git add .` + push) | 비밀·삭제·미완성 편집이 공개 저장소로 | 자동 push 스크립트 금지 |
