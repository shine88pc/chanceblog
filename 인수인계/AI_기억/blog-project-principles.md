---
name: blog-project-principles
description: "User's standing principles for the Chance_Blog + Blogger full-auto pipeline (repo as source of truth, no routine user work, extensible)"
metadata:
  node_type: memory
  type: feedback
  originSessionId: e42953cc-e88a-4d3e-9533-4d137ef15011
  modified: 2026-10-25T02:05:08.444Z
---

이 프로젝트(저장소 `shine88pc/chanceblog`, 로컬 `(옛 PC 의 KCY 폴더)`)에서 사용자가 반복해서 요구한 원칙:

1. **풀오토**: 블로그 발행에 사용자의 일상 작업이 없어야 한다. 블로그는 설정(`pipeline/blogs.json`)만으로 추가된다.
2. **저장소가 유일한 진실**: 작업 파일과 진행 상황은 전부 저장소에 올린다(HANDLER.md·WORKLOG.md). 외부 PC에서 이어받을 수 있어야 한다.
3. **여러 AI가 하나의 목표로**: 규칙은 AGENTS.md가 기준, 가드레일·검증 방법은 docs/ 아래 문서.
4. **보안·광고 표면 보호**: 비밀 금지, 광고 표면(index/privacy/about/contact/_includes/_layouts/_config.yml/ads.txt) 무승인 변경 금지.
5. **무료 한도 안에서 다수 게시 + 한도 분배** (2026-10-25 사용자 요청): Gemini 등 무료 한도를 넘지 않는 선에서 가능한 많이 게시하되, 블로그가 늘면 총 한도를 나눠 쓰고(설정의 가중치로), 한도를 알뜰히 쓰되 소량은 예비로 남긴다. 아직 설계·구현 전(4번 복구 후 별도 작업으로 제안함). 단 "양보다 근거" 원칙은 유지(한도는 상한이지 목표가 아니다).

**Why:** 사용자는 비개발자이고 회사 PC에서 파일 반출이 막혀 있으며, 블로그 수를 계속 늘릴 계획이다. 과거에 다른 AI가 `generator.py`를 통째로 덮어써 기능이 사라진 사고가 있었다.
**How to apply:** 새 기능은 레지스트리·테스트·문서(+WORKLOG)까지 한 묶음으로 끝낸다. "완료"는 검증 통과 후에만 말한다. 연결: [[user-profile]]
