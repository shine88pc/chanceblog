# Blogger API 연동 가이드

> 대상: Blogger 초안함 업로드·자동 게시
>
> GitHub Actions에서 refresh token으로 Blogger에 글을 올리기 위한 1회 설정 절차입니다.
>
> **이 절차는 영문 프로필 준비와 `mode: draft` 승인(운영자 채팅, T3) 뒤에 운영자가 직접 합니다.** 시크릿이 없으면 `mode: draft`는 저장소 파일에만 초안을 저장합니다(오류 아님).

---

## 1. Google Cloud에서 준비

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 프로젝트 생성 (또는 기존 프로젝트 선택)
3. **API 및 서비스 → 라이브러리** → **Blogger API** 검색 후 **사용 설정**
4. **OAuth 동의 화면**(새 화면 이름: Google Auth Platform)을 만들고 **게시 상태를 `In production`(프로덕션)으로 바꿉니다.** 화면 이름·버튼 이름은 구글이 바꿀 수 있습니다(추정: 대상(Audience) 화면의 '앱 게시').
   - **`Testing`(테스트) 상태로 두면 안 됩니다.** 사용자 유형이 '외부'이고 게시 상태가 `Testing`이면 refresh token이 **7일 만에 만료**됩니다(공식 문서 확인: Google 'OAuth 2.0' 문서의 refresh token expiration 항목, Cloud 도움말 'Manage App Audience'). 풀오토가 7일마다 멈춥니다.
   - 예전 안내처럼 '테스트 사용자에 본인 계정 추가'를 하면 `Testing` 상태가 됩니다. 테스트 사용자 추가는 필요 없습니다.
   - `In production`으로 바꾸면 동의 화면에 '확인되지 않은 앱' 경고가 나올 수 있습니다. 본인 계정 하나만 쓰는 용도라 동의할 때 '고급 → 이동'으로 진행하면 됩니다(추정: Blogger 범위가 민감 범위로 분류되는지는 공식 문서로 확인하지 못했습니다).
   - **`Testing` 때 받은 토큰은 `In production`으로 바꾼 뒤 새로 받습니다**(추정: 전환 뒤에도 기존 토큰이 계속 유효한지는 공식 문서에 명시가 없어 확인하지 못했습니다. 새로 받는 편이 안전합니다).
5. **API 및 서비스 → 사용자 인증 정보**
6. **사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
   - 애플리케이션 유형: **데스크톱 앱**
   - 이름: 예) `chanceblog-blogger`
7. 생성된 **클라이언트 ID / 클라이언트 보안 비밀번호** 저장
8. JSON 다운로드 → 로컬에 `client_secret.json`으로 저장 (저장소에 커밋하지 말 것)

---

## 2. Refresh Token 한 번 발급 (로컬)

> 반드시 위 1-4(`In production` 전환) **다음에** 발급합니다.

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

**Blog ID 확인** (추정: 아래 위치와 방법은 공식 문서로 확인하지 못했습니다)
- Blogger 대시보드 주소의 숫자(`.../blog/posts/<숫자>`)나 설정 화면에 표시되는 블로그 ID
- 다른 방법: API 탐색기에서 `blogs.getByUrl`(`https://www.googleapis.com/blogger/v3/blogs/byurl?url=<블로그 주소>`)로 조회한 `id`
- 같은 계정에 블로그가 여러 개이면 ID를 잘못 넣기 쉽습니다. 그래서 실행할 때 Blogger가 돌려준 블로그 주소가 `pipeline/blogs.json`의 `url`과 다르면 **글을 올리지 않고 멈춥니다**(`blog_mismatch`, 아래 §4).

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

- **`BLOGGER_*` 4종은 한꺼번에 등록하거나 하나도 등록하지 않습니다.** 일부만 있으면 초안함 업로드 실행이 설정 오류(빨강, 종료 2)로 멈춥니다. 하나도 없으면 `mode: draft`는 저장소 파일에만 저장합니다(오류 아님).
- 값은 채팅·저장소·메일에 붙이지 말고 이 화면에 직접 붙여 넣습니다.
- 등록해도 `pipeline/blogs.json`의 `mode`가 `off`이면 정기 실행은 대상 0개로 끝납니다. `mode`를 `draft`로 바꾸는 것은 운영자 승인 사항입니다.

---

## 4. 동작 방식

워크플로 `Blogger 글 자동 작성`(`blogger.yml`)이 `python -m pipeline.run --blog <key>`를 실행합니다.

1. 레지스트리 `mode`와 수동 실행 입력 `publish`로 글을 어디까지 보낼지 정합니다(아래 표).
2. Blogger에 쓰기 전에, 글을 만들기 전에 **인증 점검**(쓰기 없음)을 합니다: refresh token으로 access token 갱신 → `blogs.get`으로 블로그 조회 → 돌려준 블로그 주소가 `blogs.json`의 `url`과 같은지 확인. 하나라도 실패하면 Gemini 호출·업로드·게시 없이 빨강으로 끝납니다(분류와 할 일은 `docs/ARCHITECTURE.md` §4-1 '인증 점검 실패의 분류').
3. 글 생성·게이트를 통과하면 Blogger API `posts.insert`를 부릅니다. `isDraft=true`면 **초안함**에 올라가고(공개되지 않음), `false`면 즉시 게시됩니다. 응답에 글 ID가 없으면 실패로 처리합니다(즉시 게시는 글 주소도 있어야 합니다. 초안함 업로드는 글 ID만 있으면 성공이고, 주소가 없으면 이력의 `url`을 비우고 요약에 'Blogger 화면에서 확인'을 남깁니다).
4. 이력(`blogger_history.json`)에 `draft_uploaded`(초안함에 올림)·`posted`(게시)·`draft`(저장소 파일만)·`publish_failed`(실패)가 남고 `_blogger_drafts/`에 사본이 남습니다. 초안함에 올린 글은 **Blogger 화면에서 확인한 뒤 직접 게시**합니다.

| 상황 | 동작 |
|------|------|
| `mode: draft` + `BLOGGER_*` 4종 모두 있음 | 글을 만들어 **Blogger 초안함에 업로드**(`draft_uploaded`) |
| `mode: draft` + 4종 모두 없음 | 저장소 파일에만 저장(`draft`). 오류 아님, 실행 요약에 '초안함에는 올리지 않음' 표시 |
| `mode: draft` + 4종 중 일부만 있음 | 설정 오류(빨강, 종료 2). 모두 등록하거나 모두 지움 |
| `mode: auto` | 즉시 게시(`posted`). 시크릿이 없으면 글을 만들기 전에 빨강(종료 2) |
| `mode: off` | 실행하지 않음(정지) |
| 수동 실행 `publish` = `off` | 저장소 파일에만 저장(Blogger 접속 없음) |
| 수동 실행 `publish` = `draft`(기본) | 초안함에 업로드(시크릿이 하나도 없으면 저장소 파일에만) |
| 수동 실행 `publish` = `publish` | 즉시 게시(시크릿이 없으면 빨강) |

연습 실행(`dry_run` 체크)은 어느 경우에도 Blogger에 접속하지 않습니다. 하루 상한(블로그당 1건)은 `draft_uploaded`도 한 건으로 셉니다. 올리다 실패했어도 응답에서 글 ID를 읽은 실패(`publish_failed`)는 초안이 이미 만들어졌을 수 있어 같은 날 상한에 세므로, 재실행 전에 Blogger 초안함을 확인하세요(`topic`을 입력하면 상한을 건너뜁니다).

`mode: draft`여도 수동 실행에서 `publish` 입력을 `publish`로 고르면 즉시 게시합니다(기존 동작이며, 막을지는 T3에서 정합니다). 초안으로만 올리려면 `publish`를 `draft`(기본값)로 두세요.

**첫 실행에서만 확인되는 것**: 이 연동의 실제 구글 호출은 아직 한 번도 한 적이 없습니다. 시크릿을 등록한 뒤 `publish`=`draft` 수동 실행 1건으로 확인하세요: ① 로그에 `인증 점검 통과`와 `Blogger 초안함에 업로드했습니다` ② Blogger 화면의 글 목록에 초안이 보임 ③ 요약의 URL이 어떤 모양인지(초안 주소가 공개 주소처럼 열리는지는 공식 문서로 확인하지 못했습니다 — 추정). 응답에 글 ID가 없으면(즉시 게시는 주소도) 실패로 기록하고 '초안이 만들어졌을 수 있으니 재실행 전에 Blogger 초안함을 확인하세요'라고 알립니다.

---

## 5. 보안 주의

- `client_secret.json`, `token.json`은 **절대 커밋하지 말 것**
- refresh token은 GitHub Secrets에만 보관. 실행 로그는 비밀 값을 가려서 출력하지만 그것에 기대지 말고 값을 채팅·로그·이슈에 붙이지 않는다
- OAuth 동의 화면이 `Testing`이면 refresh token이 **7일 만에 만료**됩니다(공식 문서 확인). 다음 경우에도 토큰이 무효가 됩니다(공식 문서): 사용자가 접근을 철회했을 때, 6개월 동안 쓰지 않았을 때, 같은 계정·클라이언트로 받은 refresh token이 100개를 넘어 오래된 것부터 밀려날 때
- 토큰이 만료·폐기되면 Actions 실행이 빨강으로 끝나고, 로그에 `[SKIP] code=AUTH_CHECK_FAILED reason=auth_expired`, 요약에 '인증 만료'가 나옵니다. 조치: 동의 화면이 `In production`인지 확인 → `scripts/get_blogger_token.py`로 토큰 재발급 → `BLOGGER_REFRESH_TOKEN` 시크릿 교체. 연속 실패가 3회 이어지면 워치독 이슈도 열립니다
- 같은 계정의 다른 블로그 ID를 넣는 실수는 `blog_mismatch`로 막힙니다. 이때 응답의 블로그 주소는 같은 계정의 다른 블로그 정보라 공개 로그에 남기지 않습니다
- 권장: 시크릿 등록 뒤 최소 8일은 `mode: draft`(초안함)로 두고 인증 실패가 없는지 봅니다. 토큰 7일 경계를 넘겨야 `In production` 전환이 제대로 됐는지 알 수 있습니다

---

## 6. 수동 테스트

가장 쉬운 방법은 GitHub → Actions → `Blogger 글 자동 작성` → Run workflow입니다.

- **`인증 점검만 실행` 체크(기본 꺼짐)**: 글을 만들지 않고(Gemini 호출 0회, 저장소 변경·커밋 없음) Blogger 인증만 확인합니다 — 토큰 갱신, 블로그 조회, 돌려준 블로그 주소가 `blogs.json`의 `url`과 같은지. **시크릿을 등록한 직후와 토큰을 새로 받은 직후에 1회 실행**하세요. 통과하면 요약에 `AUTH_CHECK_OK`(확인한 시크릿 이름만, 값은 없음)가 나옵니다. 시크릿이 없으면 '시크릿 없음'으로 빨강(종료 2)입니다. 정지(`mode: off`) 중에도, `연습 실행`이 체크돼 있어도 실제로 점검합니다(쓰기가 없으므로). 체크하면 `publish`·`topic` 선택은 쓰이지 않습니다.
- `연습 실행` 체크: 가짜 AI 응답으로 흐름만 확인합니다(저장·업로드·게시 없음, Blogger 접속 없음).
- `publish` 선택: `off` 저장소 파일만 / `draft` Blogger 초안함 업로드(기본) / `publish` 즉시 게시.
- 정지(`mode: off`) 중에는 글을 만드는 수동 실행이 대상 0개로 끝납니다(인증 점검만은 예외).

로컬에서 직접 실행할 때(환경변수 이름은 레지스트리의 시크릿 이름과 같습니다):

```bash
export GEMINI_API_KEY=...        # 연습 실행(--dry-run)이 아니면 필요
export BLOGGER_BLOG_ID=...
export BLOGGER_CLIENT_ID=...
export BLOGGER_CLIENT_SECRET=...
export BLOGGER_REFRESH_TOKEN=...
export BLOGGER_PUBLISH=draft     # off=저장소 파일만 · draft=초안함 업로드 · publish=즉시 게시 · 비움/auto=레지스트리 mode를 따름

python -m pipeline.run --blog blogger_macat
```

글을 만들지 않고 인증만 확인하려면(Gemini 키 불필요, 쓰기 없음) `--auth-check`를 붙입니다. 종료 코드: 0 통과 · 1 인증 만료·네트워크·API 오류 · 2 시크릿 없음·권한·주소 불일치.

```bash
python -m pipeline.run --blog blogger_macat --auth-check
```

`BLOGGER_PUBLISH`의 예전 값(`1`·`true`·`yes`·`on` = 즉시 게시, `0`·`false`·`no`·`off` = 저장소 파일만, `auto`)은 그대로 쓸 수 있습니다. 알 수 없는 값(오타 등)은 설정 오류(종료 2)입니다.
