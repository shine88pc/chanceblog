---
name: approval-scope-and-site-checks
description: T3 승인은 목록에 적힌 항목에만 유효 — 같은 성격이어도 목록 밖 파일은 따로 묻기. 사이트(Pages) 변경은 병합 전 실제 Jekyll 빌드 비교로 검증
metadata:
  node_type: memory
  type: feedback
  originSessionId: (세션 번호)
  modified: 2026-10-26T04:42:13.695Z
---

T3(광고 표면·신뢰 목록·공개 콘텐츠) 승인은 **채팅으로 보여 준 항목 목록**에만 유효하다. 같은 목적이라도 목록에 없는 파일·폴더를 PR에 넣지 않고 따로 묻는다.

**Why:** 2026-10-26 사이트 정리 PR #34 독립 검증이, 승인받은 "운영 문서 19개(AGENTS·AI_COLLAB·CLAUDE·GEMINI·HANDLER·WORKLOG·docs/·인수인계/)" 말고 코드·상태 파일 12개 이름(`generator.py`·`pipeline/`·`scripts/`·`tests/`·`history.json` 등)을 `_config.yml exclude`에 더한 것을 승인 범위 밖이라고 지적했다. 기능 위험은 없었지만 T3 승인 경계 문제였다. 승인 요청을 쓸 때 **파일명까지** 적으면 이런 어긋남이 없다.

**How to apply:** ① 승인 요청에 대상 파일·항목을 구체적으로 적는다 ② 구현 후 diff를 승인 목록과 한 줄씩 대조하고, 더 넓히고 싶으면 PR에 넣지 말고 작업내용.md §3에 새 결정 항목으로 올린다 ③ PR 본문·문서에 "머리 부분 불변" 같은 단정은 diff로 확인하고 쓴다(noscript 한 줄이 head에 들어간 것을 놓쳤다).

사이트 변경(Jekyll `_config.yml`·`index.html` 등)은 병합 전에 **실제 GitHub Pages 빌드로 main과 PR을 각각 빌드해 견주는** 임시 브랜치를 쓴다: 임시 브랜치 `ai/claude/tmp-jekyll-build-check-*`에 `actions/checkout` → `configure-pages` → `actions/jekyll-build-pages`(배포 없음)를 main·PR 두 번 돌리고 `_site` 파일 목록·사이트맵·홈 카드·광고 스크립트 개수를 비교하는 워크플로를 두고 push하면 돈다(`guardrails.yml`은 main push와 PR에서만 돌아 임시 브랜치에는 영향 없음). 결과 로그는 로그인된 내장 브라우저에서 읽는다([[dev-environment-notes]]). Jekyll 3.10의 `exclude`는 항목으로 **시작하는** 이름도 빼고 사용자 `exclude`가 기본 제외를 대체한다. 점검이 끝나면 임시 브랜치는 지운다(병합한 브랜치가 아니므로 지워도 된다).
