---
applyTo: ".github/workflows/**"
---
# 워크플로 편집 규칙

워크플로는 비밀과 쓰기 권한을 다룬다. 사용자가 명시적으로 요청한 경우에만 고치고, 최소 변경으로 한다.
전체 규칙은 `docs/ENGINEERING_GUIDE.md` §3(W1~W9)와 `docs/SECURITY_GUARDRAILS.md` §2.2.

- 최상위 `permissions`를 명시하고 최소로 둔다. `write-all`, `pull_request_target`은 쓰지 않는다.
- `${{ github.event.* }}`·`inputs`를 `run:`에 직접 넣지 말고 `env:`로 받아 `"$VAR"`로 쓴다.
- 외부 액션은 커밋 SHA로 고정한다. `|| true`·`continue-on-error`로 실패를 숨기지 않는다.
- 모든 job에 `timeout-minutes`, 스케줄 워크플로에는 `concurrency`를 둔다.
- 워크플로 `name`과 job `name`은 한글로, 이름만 보고 자동인지 수동인지·무엇을 하는지 짐작할 수 있게 짓는다(예: `사이트 자동 배포`). 서로 다른 기능이 한 워크플로에 묶이면 나눈다. `run-name`에는 정기/수동·번호·불리언만 쓰고 이슈·PR 제목 같은 외부 문자열은 넣지 않는다(검증기 WF-11, 이름 표는 `docs/ARCHITECTURE.md` §2-1).
- 수정 후 `actionlint`와 `python scripts/validate_repo.py`를 통과시킨다.
