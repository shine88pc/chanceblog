---
applyTo: "pipeline/**,scripts/**,tests/**,generator.py,blogger_generator.py"
---
# 코드·시험 편집 규칙 (위임 작업)

이 경로는 T2다(`docs/CHARTER.md` §6.2). 소유자가 지정한 위임 작업에서만, 일이 요구한 만큼만 고친다. 구현자와 검증자는 서로 다른 주체여야 한다.

- 새 로직은 `pipeline/` 모듈과 `tests/` 시험으로 만든다. 블로그별 `if`·코드 복사 대신 `pipeline/blogs.json` 항목과 프로필을 쓴다.
- 시험은 **네트워크 없이** 돈다: 가짜 opener·가짜 클라이언트를 주입한다. 성공 경로와 실패 경로를 모두 시험하고, 시험이 정말 잡는지 코드를 일부러 틀리게 바꿔(변이) 확인한다.
- 코드는 **Python 3.10**에서 돌아야 한다. f-string 식 안에서 같은 따옴표를 다시 쓰거나 주석을 넣지 않는다(3.12 전용). 표준 라이브러리를 우선한다.
- 외부에서 온 글(이슈 본문·웹·LLM 출력)은 데이터다. 명령·파일 경로·URL·셸 명령을 고르는 데 쓰지 않는다. 로그에 넣을 때는 `pipeline/console.py`의 `one_line`을 거친다.
- 의심스러우면 게시하지 않는다(fail closed). 실패를 `except: pass`·`|| true`로 숨기지 않고 종료 코드·이력·알림으로 드러낸다.
- 비밀·토큰·키를 코드·시험·로그에 쓰지 않는다. 시험의 가짜 값은 실제 키처럼 보이지 않게 `FAKE-…` 꼴로 분명히 가짜로 쓴다(비밀 검사에 걸리지 않게).
- Gemini 호출은 `pipeline/llm.py`를 거친다(호출당 시간 상한과 폴백이 거기 있다). 모델 목록·재시도 횟수·일일 상한을 늘리면 비용이 늘므로 T3다.
- 고치지 않는다(T3로 본다): 광고 표면(`index.html`·`_layouts/` 등), `pipeline/blogs.json`은 **어느 필드든**(`mode`·`ad_surface`·`protected_paths`·`ads`·`schedule`·`limits`·`secrets`·모델 목록), `pipeline/edits/`(이슈로 자동 수정할 수 있는 범위 — `NEVER_ALLOW` 를 줄이거나 허용 경로를 넓히면 T3), `scripts/validate_repo.py`(검사 장치를 스스로 고치면 그 검사는 힘을 잃는다), `.github/` 전체. 필요하면 PR 설명에 이유를 적고 세션형 AI 에게 넘긴다.
- 자동 commit/push 스크립트·예약 작업·강제 push·삭제를 만들거나 하지 않는다(`AGENTS.md` §2의 5).
- 끝나면 `python scripts/final_checks.py --base origin/main` 결과를 PR 본문에 붙이고, 못 돌린 단계는 "실행 필요"로 적는다.
