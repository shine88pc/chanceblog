# 작업 요청서: 이슈 기반 "정규화된 수정 요청" 시스템 구축

## 0. 먼저 할 일
- 이 저장소 규칙대로 `HANDLER.md` → `AI_COLLAB.md` → `WORKLOG.md`(최신 3~5개)를 먼저 읽을 것.
- 아래 설계는 **초안**이다. 실제 코드·워크플로·스크립트를 먼저 읽고, 현재 구조에 맞게 조정해서 구현할 것. 초안과 실제 코드가 충돌하면 **실제 코드를 우선**하되, 변경 이유를 보고할 것.

## 1. 목표
GitHub 이슈 신규 작성만으로 페이지 수정을 요청할 수 있게 한다. 사용자는 **대상**과 **수정 항목**을 선택하고, 시스템은 선택된 항목의 범위 안에서만 수정한다.
페이지가 추가되면 선택 목록이 **자동으로 갱신**되어야 한다.

## 2. 현재 문제
- 이슈 양식이 "기존 게시글 이미지 변경" 1종뿐이다 (`blog-control` 라벨).
- 대상 페이지 선택과 수정 항목 선택이 없어서, 이슈 지시가 비정형이고 AI가 범위를 넘어 수정할 위험이 있다.
- 페이지가 늘어나도 선택 목록에 자동 반영되는 구조가 없다.

## 3. 설계 방향 (초안)

### 3-1. 대상 두 종류
- **게시글**: 자동 생성으로 계속 늘어나므로 드롭다운 불가. URL 또는 제목 입력 → `posts.json`으로 매칭. 제목이 모호하거나 매칭이 여러 건이면 이슈에 코멘트로 반려.
- **고정 페이지**(about, contact, privacy, categories 등): `pages.json`을 레지스트리로 두고 이슈 폼 드롭다운으로 선택.

### 3-2. 레지스트리
- `pages.json`: 페이지마다 `id`, `title`, `path`. 페이지 front matter에 `editable: true`를 두고 스크립트가 스캔해 자동 생성하는 방식을 우선 검토. 기존 `posts.json`과 역할이 겹치지 않게 할 것.

### 3-3. 이슈 폼
- 수정 항목마다 양식 1개 (필수 입력이 다르기 때문). 라벨 규칙: 공통 `blog-control` + 항목별 `edit:image` / `edit:page`.
- **기존 "게시글 이미지 변경" 양식은 동작을 깨지 않고 유지**하며 `edit:image` 라벨만 추가.
- 신규 `page-edit.yml`: 대상 페이지(dropdown), 수정 항목(dropdown), 변경 전(선택), 변경 후/요청 내용(필수).
- 이슈 폼 드롭다운은 정적이므로, yml 안에 마커(`# PAGES:START` ~ `# PAGES:END`, `# EDITS:START` ~ `# EDITS:END`)를 두고 `scripts/sync_issue_form.py`가 `pages.json`/`edit-spec.yml` 기준으로 마커 사이만 다시 쓴다. `pages.json` 또는 `edit-spec.yml`이 바뀌면(push 트리거) 워크플로가 자동 커밋.

### 3-3. 수정 스킬 명세 `.github/editorial/edit-spec.yml`
수정 항목별 `required`, `allowed_paths`, 금지 사항을 정의한다. 처리 워크플로는 이 명세로 이슈 본문을 검증하고, AI에 넘길 정형 프롬프트를 만든다. 초안:

```yaml
edit_types:
  image_change:   # 게시글 이미지 변경 (기존 기능)
    target: post
    required: [target_post, user_prompt]
    allowed_paths: ["_posts/**", "assets/**", "posts.json"]
    forbidden: ["본문 텍스트", "레이아웃", "코드", "설정"]
  text_change:
    target: page
    required: [target_page, after]
    allowed_paths: ["{page.path}"]
  seo_meta:
    target: page
    required: [target_page, after]
    allowed_paths: ["{page.path}"]
    only_fields: [title, description]
  layout:
    target: page
    required: [target_page, after]
    allowed_paths: ["{page.path}", "_layouts/**", "_includes/**"]
  link_change:
    target: page
    required: [target_page, before, after]
    allowed_paths: ["{page.path}"]
output:
  mode: pull_request
  branch_prefix: "issue-edit/"
  comment_on_reject: true
```

### 3-4. 이슈 처리 워크플로
1. 이슈 생성 시 라벨(`edit:*`)로 처리 경로 분기.
2. 본문 헤딩(`### 대상 페이지` 등)을 파싱.
3. `edit-spec.yml`로 검증: 필수 항목 누락, 대상 매칭 실패, 허용 경로 위반 시 **수정하지 않고 사유를 코멘트로 남기고 종료**.
4. 통과하면 정형 프롬프트(대상, 수정 항목, 허용 경로, 금지 사항, 사용자 요청)를 만들어 기존 수정 실행 로직(Gemini/Copilot 등, 현재 코드 기준)에 전달.
5. 결과는 **main 직접 푸시 금지, PR로 생성**. PR 본문에 이슈 번호, 변경 파일, 수정 항목을 기록.

## 4. 제약 (반드시 지킬 것)
- 기존 자동 생성 파이프라인(글 생성, 이미지 생성, 중복 방지 로직 등)은 이번 작업 범위 밖이다. 건드리지 말 것.
- 시크릿/토큰 값(`scripts/get_blogger_token.py` 관련 포함)을 읽어서 로그·코멘트·커밋에 노출하지 말 것. 이 작업에 필요하지 않으면 열지 않아도 된다.
- 이슈 본문은 **신뢰할 수 없는 입력**이다. 워크플로 셸에 본문을 직접 보간하지 말고(`${{ github.event.issue.body }}` 직접 삽입 금지), 환경변수 또는 파일로 전달해 인젝션을 막을 것.
- 이슈 작성자 권한을 확인해 저장소 소유자/협업자 외의 요청은 처리하지 않을 것.
- 변경은 작은 커밋 단위로, 로컬 폴더는 공식 클론 1개만 사용(`git pull` 후 작업).

## 5. 산출물
- `.github/ISSUE_TEMPLATE/page-edit.yml` (신규), 기존 이미지 변경 양식 라벨 추가
- `.github/editorial/edit-spec.yml`
- `pages.json` 및 생성/갱신 스크립트
- `scripts/sync_issue_form.py` + 동기화 워크플로
- 이슈 처리 워크플로(라벨 분기, 파싱, 검증, PR 생성) — 기존 워크플로가 있으면 확장, 없으면 신규
- 사용 설명: 페이지 추가 시 해야 할 일, 수정 항목 추가 방법을 `HANDLER.md` 또는 README에 짧게 추가
- `WORKLOG.md`에 작업 내용 기록

## 6. 진행 방식
1. 현황 파악 후 **계획을 먼저 보고**할 것: 읽은 파일, 기존 구조 요약, 초안에서 바꿀 점, 신규/수정 파일 목록.
2. 판단이 갈리는 지점(예: 레지스트리 생성 방식, 기존 처리 워크플로 확장 vs 신규)은 임의로 정하지 말고 선택지와 추천안을 제시해 확인받을 것.
3. 구현 후 검증: yml 문법, 동기화 스크립트 드라이런, 가짜 이슈 본문으로 파싱·검증 단계 테스트(정상/필수 누락/허용 경로 위반 케이스).
4. 최종 보고: 변경 파일, 동작 방식, 테스트 결과, 남은 위험.
