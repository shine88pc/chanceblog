"""이슈 기반 '정규화된 수정 요청' 시스템.

사용자는 GitHub 이슈 양식에서 대상과 수정 항목을 고르고, 시스템은 명세(edit-spec.yml)가 허용한
범위 안에서만 수정안을 만들어 **PR로** 올린다(main 직접 push 금지). 설명: docs/ISSUE_EDITS.md

- spec    : 명세 로드·검증, 경로 규칙(절대 금지 경로 포함)
- pages   : 고정 페이지 레지스트리(pages.json) 생성·검사
- forms   : 이슈 양식 읽기, 이슈 본문 파싱, 양식 드롭다운 동기화
- targets : 게시글 인덱스·매칭(_posts 스캔)
- ops     : 수정 방식(문자 그대로 교체 / 링크 / front matter / LLM 패치 / 이미지)
- checks  : 수정 후 사후 검증(허용 경로·광고 스니펫·front matter·크기·비밀)
- runner  : 한 건 처리 오케스트레이션 + CLI
"""
