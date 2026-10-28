---
id: R-002
kind: run
title: Blogger 시크릿 3종 등록 뒤 인증 점검을 다시 실행해 주세요 (이슈 #58)
summary: 08:52 인증 점검에서 BLOGGER_BLOG_ID·BLOGGER_CLIENT_ID·BLOGGER_REFRESH_TOKEN 이 비어 있다고 나왔습니다. Settings → Secrets and variables → Actions 의 Secrets 탭에 3종을 등록한 뒤 같은 점검을 다시 실행해 주세요. 결과는 AI 가 자동으로 읽습니다.
urgency: 보통
created: 2026-10-28
---

# R-002 · Blogger 시크릿 3종 등록 뒤 인증 점검 다시 실행

## 지금까지
- 2026-10-28 08:52 에 실행하신 `인증 점검만 실행`이 **"게시용 시크릿이 일부만 등록(없는 것: `BLOGGER_BLOG_ID`·`BLOGGER_CLIENT_ID`·`BLOGGER_REFRESH_TOKEN`)"** 으로 멈췄습니다(글·게시 없음, 쓰기 없음). 지금 Actions 시크릿에는 `BLOGGER_CLIENT_SECRET` 만 보입니다.
- 코드의 연동 이름은 맞습니다(이슈 #58 리뷰). 비어 있는 것은 **값 등록**입니다.

## 1단계 — 시크릿 3종 등록 (휴대폰 가능)
저장소 **Settings**(휴대폰은 More ⋯ 안) → **Secrets and variables** → **Actions** → **Secrets** 탭 → **New repository secret**.
| 이름(글자 그대로) | 값 |
|---|---|
| `BLOGGER_BLOG_ID` | 블로그 관리 화면 주소의 숫자 |
| `BLOGGER_CLIENT_ID` | OAuth 클라이언트 ID |
| `BLOGGER_REFRESH_TOKEN` | 발급받은 refresh token |

- **Variables 탭이 아니라 Secrets 탭**에 있어야 합니다(Variables 에 넣으면 시크릿으로 읽히지 않습니다). 이미 Variables 에 넣으셨다면 Secrets 에 새로 등록하세요.
- 값은 **원본에서 바로 복사해 붙여넣기**. 채팅 앱에서 복사하면 눈에 안 보이는 글자가 섞일 수 있습니다(섞이면 이제 코드가 지우고 쓰며 요약에 이름만 알립니다).
- `BLOGGER_REFRESH_TOKEN` 은 `BLOGGER_CLIENT_ID`·`BLOGGER_CLIENT_SECRET` 과 **같은 OAuth 클라이언트로 한 번에 발급**한 값이어야 합니다(`scripts/get_blogger_token.py` 가 세 줄을 같이 출력). ID·시크릿을 새로 만드셨다면 토큰도 새로 발급해 **셋을 함께** 등록하세요.
- 값을 이슈·채팅에 쓰지 마세요.

## 2단계 — 인증 점검 다시 실행
Actions → 워크플로 선택(묶음 병합 **전** `[Blogger] 글 자동 작성(초안함 업로드)`, **후** `[Blogger 영문] 글 자동 작성`) → **Run workflow** → **"인증 점검만 실행"만 체크**(나머지 그대로) → 초록 **Run workflow** → 1~2분 뒤 실행의 **Summary**.

## 결과 읽는 법
| 요약에 보이는 것 | 뜻 | 할 일 |
|---|---|---|
| `AUTH_CHECK_OK` | 정상 | 없음 — AI 가 자동으로 확인합니다 |
| 시크릿 일부 없음(없는 것: 이름) | 아직 빠진 것이 있음 | 그 이름을 Secrets 에 등록 |
| 인증 만료(auth_expired) | refresh token 만료·폐기 | OAuth 동의 화면 '프로덕션' 확인 후 토큰 새로 발급·등록 |
| 권한·접근 불가(auth_failed) | ID·시크릿·토큰 불일치 또는 블로그 권한 | 세 값을 **같은 클라이언트의 같은 발급**으로 다시 등록 |
| 블로그 주소 불일치(blog_mismatch) | `BLOGGER_BLOG_ID` 가 다른 블로그 | 블로그 ID 확인 |
| 네트워크·API 오류 | 일시적 | 잠시 뒤 다시 실행 |

## 알려 주기
**하지 않아도 됩니다** — AI 가 실행 결과(성공·실패와 점검 문구)를 공개 정보로 자동으로 읽습니다. 막히면 텔레그램의 **[답하기]** → 양식에서 요청 번호 `R-002`, 답 "문제", 메모에 **요약의 결과 문구만**(값은 쓰지 마세요).
