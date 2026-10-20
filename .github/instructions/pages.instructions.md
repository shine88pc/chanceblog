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
