# Blogger API 연동 가이드

> 대상: Blogger 자동 게시  
> GitHub Actions에서 refresh token으로 게시하기 위한 1회 설정 절차입니다.

---

## 1. Google Cloud에서 준비

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 프로젝트 생성 (또는 기존 프로젝트 선택)
3. **API 및 서비스 → 라이브러리** → **Blogger API** 검색 후 **사용 설정**
4. **API 및 서비스 → 사용자 인증 정보**
5. **사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
   - 애플리케이션 유형: **데스크톱 앱**
   - 이름: 예) `chanceblog-blogger`
6. 생성된 **클라이언트 ID / 클라이언트 보안 비밀번호** 저장
7. JSON 다운로드 → 로컬에 `client_secret.json`으로 저장 (저장소에 커밋하지 말 것)

OAuth 동의 화면이 없다면:
- 외부 또는 내부 선택
- 테스트 사용자에 본인 Google 계정 추가 (테스트 모드일 때 필요)

---

## 2. Refresh Token 한 번 발급 (로컬)

```bash
pip install google-auth-oauthlib google-auth google-api-python-client

# 저장소 루트에서
python scripts/get_blogger_token.py
```

브라우저가 열리면 Blogger 권한이 있는 Google 계정으로 로그인·허용합니다.  
터미널에 출력되는 값을 복사합니다.

```
BLOGGER_CLIENT_ID=...
BLOGGER_CLIENT_SECRET=...
BLOGGER_REFRESH_TOKEN=...
```

**Blog ID 확인**
- Blogger → 설정 → 기본 → 블로그 ID (숫자)
- 또는 블로그 대시보드 URL / 설정 화면에 표시

---

## 3. GitHub Secrets 등록

저장소 **Settings → Secrets and variables → Actions**에 추가:

| Secret 이름 | 값 |
|-------------|-----|
| `GEMINI_API_KEY` | (기존) |
| `BLOGGER_BLOG_ID` | 블로그 숫자 ID |
| `BLOGGER_CLIENT_ID` | OAuth 클라이언트 ID |
| `BLOGGER_CLIENT_SECRET` | OAuth 클라이언트 시크릿 |
| `BLOGGER_REFRESH_TOKEN` | 발급받은 refresh token |

---

## 4. 동작 방식

1. `blogger_generator.py`가 글 생성
2. Secrets가 모두 있으면 `post_to_blogger()` 호출
3. refresh token으로 access token 갱신 후 Blogger API `posts.insert`
4. 성공 시 `blogger_history.json` status를 `posted`로 갱신, 초안 status도 반영

Secrets가 없으면 **생성 + 초안 저장만** 하고 게시는 건너뜁니다.

---

## 5. 보안 주의

- `client_secret.json`, `token.json`은 **절대 커밋하지 말 것**
- refresh token은 GitHub Secrets에만 보관
- OAuth 앱이 “테스트” 상태면 refresh token이 주기적으로 만료될 수 있음 → 가능하면 게시 상태로 전환하거나 재발급

---

## 6. 수동 테스트

```bash
export GEMINI_API_KEY=...
export BLOGGER_BLOG_ID=...
export BLOGGER_CLIENT_ID=...
export BLOGGER_CLIENT_SECRET=...
export BLOGGER_REFRESH_TOKEN=...
export BLOGGER_PUBLISH=1   # 1이면 게시 시도

python blogger_generator.py
```
