---
applyTo: "about.md,contact.md,privacy.md,categories.md,index.html"
---
# 고정 페이지 편집 규칙

이 파일들은 광고(AdSense) 심사 대상이거나 사이트의 기본 페이지다. 요청받은 부분만 고친다.

- 파일 **전체를 읽고** 고친다. 요청한 문장을 원문에서 글자 그대로 찾은 뒤 그 부분만 바꾼다.
- 맨 위 `---` 사이의 front matter(`layout`, `title`, `description`, `permalink`)는 요청이 SEO 메타 수정이 아니면 바꾸지 않는다.
- Liquid 태그(`{% … %}`, `{{ … }}`)와 HTML 구조를 깨지 않는다.
- `index.html`의 광고 코드(`adsbygoogle`, `googlesyndication`, `ca-pub-…`)는 추가·삭제·이동하지 않는다.
- 새 `<script>`, `<iframe>`, 외부 링크를 넣지 않는다. 링크는 요청받은 URL만 교체한다.
- 개인정보처리방침(`privacy.md`)·소개(`about.md`)·문의(`contact.md`)의 사실 진술(운영 방식, 수집 항목, 연락처)은 요청에 근거가 없으면 지어내지 않는다.
- 불확실하면 고치지 말고 PR 설명에 "확인 필요"로 적는다.
- **Copilot 은 이 파일들(광고 표면)을 고치지 않는다.** 승인 표시(`Ad-Surface-Approved:`)는 Copilot 이 쓸 수 없고(검증기 AD-2), 승인 표시 없는 광고 표면 변경은 검증기 AD-1 이 막는다. 소유자가 이슈 양식으로 이 파일의 문구를 요청했어도 파일을 바꾸지 말고 PR 설명에 "광고 표면 변경 요청 — 자동 처리 양식이나 세션형 AI 가 필요"라고 쓰고 멈춘다. 정확한 교체는 이슈 양식의 자동 처리가 AI 없이 하고, 그 밖의 수정은 세션형 AI 가 운영자 승인을 받아 한다.
