# Copilot 지침

이 저장소의 규칙 정본은 [`AGENTS.md`](../AGENTS.md)다. 아래는 Copilot용 핵심 요약이다.

## 수정 요청을 받으면 (가장 중요)

1. **수정할 파일을 처음부터 끝까지 읽은 뒤** 고친다. 앞부분만 읽고 나머지를 추정하지 않는다. 파일을 다 읽지 못했다면 그렇게 말하고 멈춘다.
2. 요청에 적힌 문구·위치를 **원문과 글자 하나까지 대조**한다. 찾지 못하면 비슷한 곳을 고치지 말고 질문한다.
3. **요청한 부분만** 최소로 수정한다. 다른 문장·서식·링크·front matter를 정리하거나 되돌리지 않는다.
4. 확신이 없으면 추측하지 말고 PR 설명에 "확인 필요"로 적는다.
5. 끝나면 diff에 요청과 무관한 변경이 없는지 직접 확인하고, PR 설명에 **바꾼 곳 / 바꾸지 않은 곳**을 적는다.

## 이슈 양식으로 접수된 요청

이슈의 `대상 페이지` · `수정 항목` · `변경 전` · `변경 후`가 정확한 지시서다.

- 문구 수정 + `변경 전`이 있으면: 그 문구를 `변경 후`로 **그대로** 교체한다. 다른 변경은 하지 않는다.
- 링크 변경: URL만 교체한다. SEO 메타: `title`/`description` 줄만 바꾼다.
- PR 본문에 `Fixes #이슈번호`를 넣는다(PR 범위 검증이 이슈와 연결할 때 쓴다).
- PR이 올라오면 `PR 변경 범위 검사`(pr-scope-check.yml)가 요청 범위를 자동으로 점검한다.

## 건드리지 않는 곳 (사용자가 명시적으로 요청한 경우만)

광고 표면(`index.html`, `privacy.md`, `about.md`, `contact.md`, `_includes/`, `_layouts/`, `_config.yml`, `robots.txt`, `ads.txt`), `.github/workflows/`, `pipeline/`, `scripts/`, 비밀 파일. 광고 코드(`adsbygoogle`, `ca-pub-`)는 어떤 경우에도 추가·삭제하지 않는다.

## 읽을 문서

[`HANDLER.md`](../HANDLER.md) · [`docs/SECURITY_GUARDRAILS.md`](../docs/SECURITY_GUARDRAILS.md) · 코드 작업이면 [`docs/ENGINEERING_GUIDE.md`](../docs/ENGINEERING_GUIDE.md)

변경 후 `python scripts/validate_repo.py`와 `python -m unittest discover -s tests`를 통과시킨다.
