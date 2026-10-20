# Chance_Blog Work Log (AI 인수인계 로그)

> **이 파일은 AI가 작업을 시작하기 전에 반드시 최신 항목을 읽어야 하는 인수인계 로그입니다.**  
> 필독 순서: **HANDLER.md** → **AI_COLLAB.md** → **이 파일 최신 항목**

최신 항목이 위에 오도록 **최신순**으로 작성합니다.

---

## [2026-10-20] Claude – 로컬 폴더(KCY)를 공식 저장소 작업 폴더로 전환

**작업자**: Claude  
**대상**: 공통  
**목적**: HANDLER.md P0(로컬 폴더 통합) 이행 — 내려받아 둔 복사본을 `shine88pc/chanceblog` main 추적 저장소로 전환

### 변경 사항
- 로컬 작업 폴더(`KCY`)를 git 저장소로 전환 (`origin` = `https://github.com/shine88pc/chanceblog.git`, `main`이 `origin/main` 추적, 기준 커밋 `313dc5c`). 파일 내용은 그대로 두고 `git reset`으로 인덱스만 main에 맞춤
- main에 있으나 로컬에 없던 `_posts/`(16개) 복원 (`auto_sync.bat`도 복원했으나 아래 사유로 제거)
- 로컬 파일 9개(`_layouts/*`, `_includes/*`, `.github/editorial/*`, `.github/skills/humanize/*`, `scripts/get_blogger_token.py`)는 줄 끝이 `\r\r\n`으로 이중 변환돼 있었음. 줄 끝을 정규화하면 main과 내용이 동일함을 확인한 뒤 main 기준으로 복구
- `client_secret.json.json` → `client_secret.json` 이름 변경 (`scripts/get_blogger_token.py`가 이 이름을 찾음). 내용은 열어보지 않음
- `.gitignore` 신규: `client_secret*.json`, `token*.json`, `.env` (main에는 `.gitignore`가 없었음)
- `auto_sync.bat` 제거 (사용자가 판단을 위임). 30초마다 `git add .` → 커밋 → `main` push를 검토 없이 반복해 비밀 파일·미완성 편집·삭제가 공개 저장소에 그대로 올라갈 위험이 있고, 문서·워크플로 어디에서도 참조하지 않는 스크립트였음. 복구: `git show 313dc5c:auto_sync.bat`
- 로컬 전용이던 `인수인계/이슈_기반_게시글_이미지_수정_인수인계.md`를 원문 그대로 저장소에 추가 (이전 AI 세션 작성본)
- HANDLER.md 갱신: §0 현재 상태, §1 루트 랜딩 저장소, §2 완료 표, §3 P0 완료·P1 현황·P2, §7 주의, §8 인수인계 문, §10 다른 PC에서 이어받기, §11 브랜치·이전 사본 현황
- 이 clone에만 git 작성자 정보를 설정하고, 변경을 4개 커밋(`.gitignore` / `auto_sync.bat` 제거 / 인수인계 문서 / HANDLER·WORKLOG)으로 나눠 `main`에 push

### 다음 AI에게 남기는 주의사항
1. `auto_sync.bat`(검토 없는 자동 push)은 제거했다. 같은 동작의 스크립트·예약 작업을 사용자 확인 없이 다시 만들지 말 것. 다른 폴더에서 이 사본을 돌리고 있다면 중단할 것.
2. `shine88pc/shine88pc.github.io`는 별도 저장소(루트 랜딩 `index.html`·`README.md`·`robots.txt`, Google Ads 스크립트 커밋 있음). README상 글·블로그의 원본은 `chanceblog`이며 HANDLER.md §1에 반영했다.
3. 이 PC는 시스템 설정이 `core.autocrlf=true`다. 작업 폴더 파일은 CRLF가 정상이고 저장소에는 LF로 저장되므로 `autocrlf`를 끄지 말 것(끄면 거의 모든 파일이 수정으로 보인다).
4. git 작성자 정보는 이 clone(`KCY`)에만 저장소 로컬로 설정했다. 다른 폴더·PC에서 clone하면 커밋 전에 따로 설정할 것.
5. 사용자는 작업 PC의 파일을 외부로 반출할 수 없어 다른 PC에서 작업을 이어받는다. 새 PC에서는 HANDLER.md §10을 따를 것.
6. 이전 로컬 사본(미커밋 변경 있음)과 `feature/image-fix-20261019-0000` 브랜치(`index.html` −608줄)는 낡았으므로 열어서 push·병합하지 말 것 (HANDLER.md §11).
7. `blogger.yml` 첫 스케줄 실행은 2026-10-21 02:00 UTC(KST 11시) 예정이며 아직 실행 이력이 없다. 실행되면 `_blogger_drafts/`·`blogger_history.json`이 main에 커밋되므로 작업 전 `git pull --rebase`.

### 남은 이슈 / 확인할 점
- 작업 전 `git pull --rebase origin main` (봇이 `main`에 직접 커밋함)
- `feature/image-fix-20261019-0000`·`backup/issue-template-$TS` 브랜치를 지울지 결정 (사용자)
- Blogger Generate 첫 실행 결과 확인 (Actions 탭)
- Blogger refresh token 발급: `pip install google-auth-oauthlib` → `python scripts/get_blogger_token.py` (브라우저 동의가 필요해 사용자 직접 실행) → 출력값을 GitHub Secrets에 등록

---

## [2026-10-20] Grok – HANDLER.md 신설 (폴더 통합·멀티 AI 규칙)

**작업자**: Grok  
**대상**: 공통  
**목적**: 여러 AI·로컬 폴더 불일치 문제를 막기 위한 중앙 핸들러 문서 작성 및 필독 체계 강화

### 변경 사항
- **HANDLER.md** 신규
  - 완료 작업 현황
  - 조치 필요 사항 (P0 로컬 폴더 1개로 통합, VS Code 동기화, Secrets, 주제 충돌 등)
  - 작업 전 필수 확인 파일 목록
  - 작업 후 WORKLOG/HANDLER 기록 의무
  - 금지 사항
  - **GPT 복붙용 인수인계 문** 포함
- **README.md** — 필독 순서에 HANDLER.md를 1번으로 추가

### 사용자·다음 AI 조치 (P0)
1. GitHub `main`을 clone/pull 한 **공식 폴더 하나만** 사용
2. VS Code는 그 폴더만 Open Folder
3. 작업 전 `git pull`, 작업 후 커밋·push
4. `client_secret.json`은 공식 폴더 루트, 커밋 금지
5. GPT 세션 시작 시 HANDLER.md §8 블록 전달 권장

### 다음 AI에게 남기는 주의사항
1. 작업 시작 전 HANDLER → AI_COLLAB → WORKLOG 필수
2. 로컬 경로를 추측하지 말고 사용자가 연 폴더가 git remote 공식 저장소인지 확인
3. Blogger API Secrets는 사용자 등록 전제

### 남은 이슈
- 로컬 폴더 통합 (사용자)
- Blogger Secrets / token 발급 (사용자)
- 주제 충돌 방지, 초안 품질, AdSense

---

## [2026-10-20] Grok – Blogger API 코드 연동 완료 (Secrets 대기)

**작업자**: Grok  
**대상**: Blogger  
**목적**: API 게시 코드·가이드·워크플로 구현. 실게시는 Secrets 후.

---

## [2026-10-20] Grok – Blogger 생성 워크플로·초안·전략·프롬프트

이전 항목: blogger.yml, blogger_generator, BLOGGER_PROMPT, 듀얼 전략, AI 협업 체계.

---

## 로그 작성 가이드 (모든 AI 공통)

```markdown
## [YYYY-MM-DD] AI이름 – 작업 제목

**작업자**: GPT / Grok / Claude 등  
**대상**: Chance_Blog / Blogger / 공통  
**목적**: 한 줄 요약

### 변경 사항
- ...

### 다음 AI에게 남기는 주의사항
1. ...

### 남은 이슈 / 확인할 점
- ...
```
