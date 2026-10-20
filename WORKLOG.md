# Chance_Blog Work Log (AI 인수인계 로그)

> **이 파일은 AI가 작업을 시작하기 전에 반드시 최신 항목을 읽어야 하는 인수인계 로그입니다.**  
> 사용자가 별도로 지시하지 않아도, 이 저장소에서 작업하는 모든 AI는 `AI_COLLAB.md`와 함께 이 파일을 먼저 확인해야 합니다.

최신 항목이 위에 오도록 **최신순**으로 작성합니다.

---

## [2026-10-20] Grok – Blogger API 코드 연동 완료 (Secrets 대기)

**작업자**: Grok  
**대상**: Blogger  
**목적**: Blogger API 게시 경로를 코드·워크플로·가이드까지 구현. 실제 게시는 사용자 Secrets 등록 후 가능.

### 변경 사항
- `.github/editorial/BLOGGER_API_SETUP.md` — OAuth·Secrets 설정 가이드
- `scripts/get_blogger_token.py` — 로컬에서 refresh token 1회 발급
- `blogger_generator.py` — `post_to_blogger()` 추가, `BLOGGER_PUBLISH=1` 시 게시
- `.github/workflows/blogger.yml` — 게시 옵션·API 패키지·Secrets 연결

### 사용자가 해야 할 일 (1회)
1. Google Cloud에서 Blogger API 활성화 + 데스크톱 OAuth 클라이언트 생성
2. `python scripts/get_blogger_token.py` 로 refresh token 발급
3. GitHub Secrets 등록:
   - `BLOGGER_BLOG_ID`
   - `BLOGGER_CLIENT_ID`
   - `BLOGGER_CLIENT_SECRET`
   - `BLOGGER_REFRESH_TOKEN`
4. Actions에서 publish 체크 후 실행, 또는 스케줄(Secrets 있으면 자동 게시 시도)

### 다음 AI에게 남기는 주의사항
1. Secrets 없으면 생성·초안만 동작 (정상)
2. API 코드는 완료 — 인증 값은 사용자가 넣어야 함
3. 다음 우선: 주제 충돌 방지, 초안 품질 점검

### 남은 이슈 / 다음 단계
- 사용자 Secrets 등록 (블로거 API 실게시 활성화)
- 주제 충돌 방지
- 초안 품질 점검 / 샘플 테스트
- AdSense 승인 모니터링

---

## [2026-10-20] Grok – Blogger 생성 전용 워크플로 + 초안 저장

**작업자**: Grok  
**대상**: Blogger  
**목적**: API 없이 스케줄 생성·초안 저장

---

## [2026-10-20] Grok – Blogger 게시 방식 확정

**작업자**: Grok  
**대상**: Blogger  
**목적**: GitHub Actions + Blogger API 공식 경로

---

## [2026-10-20] Grok – blogger_generator.py / 프롬프트 / 구조 설계

이전 항목 요약: 생성기·BLOGGER_PROMPT·듀얼 전략·AI 협업 체계 구축 완료.

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
