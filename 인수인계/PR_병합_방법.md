# PR 만들고 병합하는 방법 (운영자용)

> AI가 GitHub 화면을 쓸 수 없을 때(브라우저 차단·로그인 불가 등) 운영자가 **직접** 병합하는 방법입니다. GitHub에 로그인된 브라우저 하나면 됩니다(휴대폰 브라우저도 됩니다). 마지막 갱신: 2026-10-27, 갱신자: Claude

## 한눈에 (3분 + 기다리는 시간)

1. 아래 **PR 만들기 링크**를 연다 → 초록 **"Create pull request"** 버튼을 누른다. (제목·본문은 이미 채워져 있습니다.)
2. PR 화면 아래쪽 검사가 **모두 초록 체크**가 될 때까지 기다린다(보통 5~10분).
3. 초록 **"Squash and merge"** 버튼 → **"Confirm squash and merge"** 를 누른다. 끝.
4. 병합하고 5~10분 뒤 저장소의 **Actions** 탭에서 `[공통] 사이트 자동 배포`가 초록인지 본다.
5. 채팅에 "묶음 1 병합했어"라고만 알려 주세요. 그러면 다음 작업을 이어 갑니다.

## 지금 병합할 PR: 묶음 1

**[묶음 1 PR 만들기](https://github.com/shine88pc/chanceblog/compare/main...ai/claude/batch-1?quick_pull=1&title=%EB%AC%B6%EC%9D%8C%201%3A%20%EC%9B%8C%ED%81%AC%ED%94%8C%EB%A1%9C%20%5B%EA%B5%AC%EB%B6%84%5D%20%EC%9D%B4%EB%A6%84%C2%B7channel/ads%28%EC%9E%91%EC%97%85%EC%9A%94%EC%B2%AD%EC%84%9C%205%20PR-A%29%20%2B%20Blogger%20%EA%B0%80%EB%93%9C%EB%A0%88%EC%9D%BC%203%EC%B0%A8%20%2B%20%ED%85%94%EB%A0%88%EA%B7%B8%EB%9E%A8%C2%B7RPA%20%EC%A1%B0%EC%82%AC%20%EB%AC%B8%EC%84%9C%20%E2%80%94%20%EB%8F%85%EB%A6%BD%20%EA%B2%80%EC%A6%9D%20%EB%B3%91%ED%95%A9%20%EA%B0%80%EB%8A%A5%2C%20%EC%8B%9C%ED%97%98%202222%EA%B0%9C%20%ED%86%B5%EA%B3%BC%20%28Claude%29%20%5B%EB%8C%80%EC%83%81%3A%20%EA%B3%B5%ED%86%B5%5D&body=%EB%AC%B6%EC%9D%8C%20PR%EC%9E%85%EB%8B%88%EB%8B%A4%28AI%20%EA%B0%80%20GitHub%20%ED%99%94%EB%A9%B4%EC%9D%84%20%EC%93%B8%20%EC%88%98%20%EC%97%86%EC%96%B4%20%EC%9A%B4%EC%98%81%EC%9E%90%EA%B0%80%20%ED%95%9C%20%EB%B2%88%EC%97%90%20%EB%B3%91%ED%95%A9%ED%95%98%EB%8F%84%EB%A1%9D%20%EB%AC%B6%EC%9D%8C%29.%20%EA%B5%AC%EC%84%B1%EA%B3%BC%20%EA%B2%80%EC%A6%9D%3A%0A1%29%20%EC%9E%91%EC%97%85%EC%9A%94%EC%B2%AD%EC%84%9C%205%20PR-A%3A%20%EC%9B%8C%ED%81%AC%ED%94%8C%EB%A1%9C%2010%EA%B0%9C%20%EC%9D%B4%EB%A6%84%EC%97%90%20%5BChance%5D/%5BBlogger%5D/%5B%EA%B3%B5%ED%86%B5%5D%20%EC%A0%91%EB%91%90%EC%82%AC%2C%20%EB%A0%88%EC%A7%80%EC%8A%A4%ED%8A%B8%EB%A6%AC%20channel%C2%B7ads%20%ED%95%84%EB%93%9C%2C%20%EA%B2%80%EC%A6%9D%20%EA%B7%9C%EC%B9%99%20WF-12%C2%B7REG-5.%20%EB%8F%99%EC%9E%91%20%EB%B3%80%ED%99%94%20%EC%97%86%EC%9D%8C%28%EB%AA%85%EB%A0%B9%2033%EA%B0%9C%20%EC%B6%9C%EB%A0%A5%EC%9D%B4%20main%20%EA%B3%BC%20%EB%B0%94%EC%9D%B4%ED%8A%B8%20%EB%8F%99%EC%9D%BC%29.%20%EB%8F%85%EB%A6%BD%20%EA%B2%80%EC%A6%9D%20%EB%B3%91%ED%95%A9%20%EA%B0%80%EB%8A%A5%28%EB%A7%89%EB%8A%94%20%EA%B2%B0%ED%95%A8%200%29.%0A2%29%20Blogger%20%EC%A3%BC%EC%A0%9C%20%EA%B0%80%EB%93%9C%EB%A0%88%EC%9D%BC%203%EC%B0%A8%20%EB%B3%B4%EA%B0%95%3A%20%ED%94%84%EB%A1%9C%ED%95%84%20%ED%8C%A8%ED%84%B4%C2%B7%EC%8B%9C%ED%97%98%C2%B7%EB%AC%B8%EC%84%9C%EB%A7%8C%28%EC%BD%94%EB%93%9C%EB%8A%94%20%EC%A3%BC%EC%84%9D%29.%20%EB%8F%85%EB%A6%BD%20%EA%B2%80%EC%A6%9D%20%EB%B3%91%ED%95%A9%20%EA%B0%80%EB%8A%A5%28%EB%A7%89%EB%8A%94%20%EA%B2%B0%ED%95%A8%200%29.%0A3%29%20%ED%85%94%EB%A0%88%EA%B7%B8%EB%9E%A8%20%EC%95%8C%EB%A6%BC%C2%B7%EC%98%A4%ED%86%A0%EB%A7%88%EC%9A%B0%EC%8A%A4%20%EC%A1%B0%EC%82%AC%20%EB%AC%B8%EC%84%9C%2C%20%EC%9A%B4%EC%98%81%EC%9E%90%20%EC%84%A4%EC%A0%95%20%EB%A9%94%EB%AA%A8%20%ED%99%95%EC%9D%B8%28%EC%B1%84%ED%8C%85%20ID%20%EA%B0%92%20%EC%82%AD%EC%A0%9C%29%2C%20%EC%A7%84%ED%96%89%20%ED%98%84%ED%99%A9%2C%20%EC%9D%B4%20%EB%B3%91%ED%95%A9%20%EC%95%88%EB%82%B4.%0Amode%C2%B7%EC%8B%9C%ED%81%AC%EB%A6%BF%C2%B7%EA%B4%91%EA%B3%A0%20%ED%91%9C%EB%A9%B4%20%EB%B3%80%EA%B2%BD%20%EC%97%86%EC%9D%8C.%20%EC%A0%84%EC%B2%B4%20%EC%8B%9C%ED%97%98%202222%EA%B0%9C%20%ED%86%B5%EA%B3%BC.%20%EC%84%B8%EB%B6%80%EB%8A%94%20WORKLOG.md%20%EB%A7%A8%20%EC%9C%84%20%ED%95%AD%EB%AA%A9%203%EA%B0%9C.%0A%EB%B3%91%ED%95%A9%20%EC%A0%84%20%ED%99%95%EC%9D%B8%3A%20Settings%E2%86%92Rules%20%EC%97%90%20%27%ED%95%84%EC%88%98%20%EC%83%81%ED%83%9C%20%EA%B2%80%EC%82%AC%27%EA%B0%80%20%EC%A7%80%EC%A0%95%EB%8F%BC%20%EC%9E%88%EC%9C%BC%EB%A9%B4%20%EC%95%8C%EB%A0%A4%20%EC%A3%BC%EC%84%B8%EC%9A%94%28%EC%9B%8C%ED%81%AC%ED%94%8C%EB%A1%9C%20%EC%9D%B4%EB%A6%84%EC%9D%B4%20%EB%B0%94%EB%80%9D%EB%8B%88%EB%8B%A4%29.%0A%0A%F0%9F%A4%96%20Generated%20with%20%5BClaude%20Code%5D%28https%3A//claude.com/claude-code%29)**

들어 있는 것(각각 독립 검증을 받았고, 묶음 전체의 전체 시험도 통과했습니다):
- **워크플로 이름 `[구분]` 접두사 + 채널·광고 선언**(작업요청서 5의 PR-A): Actions 목록에서 `[Chance]`·`[Blogger]`·`[공통]`으로 묶여 보입니다. 글 발행·사이트·Blogger·광고 동작은 바뀌지 않습니다(명령 33개의 출력이 기존과 바이트 단위로 같음).
- **Blogger 주제 가드레일 3차 보강**: 건강·의료 주제를 거르는 규칙의 빈틈을 더 막았습니다(Blogger 글은 아직 꺼져 있어 지금 영향은 없습니다).
- **조사 문서·진행 현황**: 텔레그램 알림·오토마우스 조사 결과, 올려 주신 설정 메모 확인, 이 안내 문서.

병합 전에 확인할 것 1가지: 저장소 **Settings → Rules** 에 "필수 상태 검사(Require status checks)"가 지정돼 있으면 알려 주세요. 이번 병합으로 검사 이름 앞에 `[공통]`이 붙습니다. 지정돼 있지 않다면 신경 쓰지 않아도 됩니다.

## 단계별 설명 (PC·휴대폰 브라우저 공통)

1. **링크를 엽니다.** 로그인 화면이 나오면 GitHub에 로그인합니다. 로그인되어 있으면 "Open a pull request" 화면이 바로 보입니다.
2. **초록 "Create pull request" 를 누릅니다.** 화면이 PR 페이지(주소 끝이 `/pull/숫자`)로 바뀌면 만들어진 것입니다.
3. **검사를 기다립니다.** 페이지 맨 아래쪽 "Checks"(또는 병합 상자)에서 노란 점은 진행 중, 초록 체크는 통과입니다. `검사 (Python 3.10)`, `검사 (Python 3.12)`, `이슈 요청 범위 확인`이 모두 초록이면 **"All checks have passed"** 가 보입니다.
   - 빨간 ✗ 가 하나라도 있으면 **병합하지 말고** 화면을 캡처해 알려 주세요.
   - "This branch has conflicts that must be resolved" 가 보여도 병합하지 말고 알려 주세요.
4. **"Squash and merge" (초록 버튼)** 을 누르고, 제목·본문 칸은 **그대로 둔 채** "Confirm squash and merge" 를 누릅니다.
5. "Pull request successfully merged and closed" 가 뜨면 병합 완료입니다. **"Delete branch" 버튼은 누르지 마세요**(병합한 브랜치를 지우지 않는 규칙입니다).
6. 병합 5~10분 뒤 **Actions** 탭에서 `[공통] 사이트 자동 배포`가 초록인지 확인합니다. 빨강이면 알려 주세요(병합 직후 한 번은 제가 직접 확인합니다).

## 휴대폰에서 할 때

- 휴대폰 브라우저에서 위 링크를 열어 같은 순서로 하면 됩니다(GitHub 앱이 설치되어 있으면 앱으로 열릴 수 있고, 앱에서도 "Pull requests"에서 같은 PR을 열어 "Merge pull request → Squash and merge"를 누르면 같습니다).
- 텔레그램 알림이 켜진 뒤에는 알림의 링크 버튼으로 PR 화면을 바로 열 수 있습니다.

## 막혔을 때

| 보이는 것 | 의미·할 일 |
|-----------|-----------|
| "Open a pull request" 대신 이미 PR 이 있다는 안내 | 누군가 이미 만든 것입니다. 그 PR 로 들어가 3번부터 진행 |
| 검사가 20분 넘게 노란 점 | GitHub 지연일 수 있습니다. 기다리다 알려 주세요 |
| 빨간 ✗ / conflicts | 병합하지 말고 캡처해서 알려 주세요(제가 고칩니다) |
| "Squash and merge" 가 안 보이고 "Merge pull request" 만 있음 | 그대로 "Merge pull request" 를 눌러도 내용은 같습니다. 알려 주시면 설정을 확인합니다 |
| 병합했는데 사이트 배포가 빨강 | 제가 읽을 수 있는 공개 정보로 먼저 확인합니다. 캡처가 있으면 같이 주세요 |

## 다음 묶음(예정)

구현·독립 검증이 끝나는 대로 같은 방식의 링크를 드립니다(묶음 1이 병합된 뒤, 충돌이 없게 제가 맞춰서 만듭니다).

| 예정 | 상태 |
|------|------|
| 텔레그램 알림(새 글·초안 대기·확인 필요) | 구현 중 |
| Chance 초안→사람 승인 후 공개(기본 꺼짐) | 구현 중 |
| 초안 현황판(확인 필요 모음 안) | 구현 중 |
| 티스토리·네이버 초안 패키지(대상 0개) | 구현 중 |
| 한글 Blogger(kcyoon, 꺼진 상태) + Blogger 워크플로 분리 | 묶음 1 병합 뒤 시작 |

## 왜 PR 3개가 아니라 묶음 1개인가

PR 3개를 차례로 병합하면 두 번째부터 `WORKLOG.md` 맨 위 항목이 겹쳐 "conflicts"가 생길 수 있고, 이 충돌은 비개발자가 풀기 어렵습니다. 묶음은 제가 미리 충돌을 풀고 합친 결과를 시험한 것이라 한 번의 클릭으로 끝납니다. 구성 요소 각각의 독립 검증 결과와 병합 전 확인 사항은 `WORKLOG.md` 맨 위 항목과 `docs/analysis/`의 문서에 있습니다.
