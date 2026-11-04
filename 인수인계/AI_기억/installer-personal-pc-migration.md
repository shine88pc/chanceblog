---
name: installer-personal-pc-migration
description: 운영자 2026-11-03 채팅(20:2x) '모든 절차가 최종적으로 완료되면 아래 내용으로 마무리' — Windows 설치 프로그램(GitHub Releases)·개인 PC 이관 요구사항 16항목, 저장소에 이미 있는 설계(RELEASE.md·D-04~D-06·store 마이그레이션)와의 대조, 마무리 단계 작업 순서·T3 경계·위험(스마트 앱 컨트롤)
metadata:
  node_type: memory
  type: project
  originSessionId: (세션 번호)
  modified: 2026-11-03T13:29:06.071Z
---

**운영자 채팅(2026-11-03 20:2x):** "모든 절차가 최종적으로 완료되면 아래 내용으로 마무리 하는걸로 진행해줘" + `## Installer 및 개인 PC 이관 요구사항` 16항목. **지금 만들지 않는다** — 작성 기반 병합·화면 도구 결정·화면 구현·후보 제안·키 연결 설정·본문 초안·독립 검증이 모두 끝난 **마지막 단계**다. 채팅 지시는 유효한 승인이지만 릴리스 공개·서명키·시크릿·태그는 T3 라 그 시점에 번호 있는 요청으로 따로 받는다(`AGENTS.md` §2).

**16항목(번호는 운영자 원문 그대로, 말은 줄임):**
1. chanceblog-desktop 의 Windows 설치 프로그램을 **GitHub Releases** 로 배포.
2. 설치 파일에 Gemini·Naver·Blogger·GitHub·Image Provider 등 **실제 API Key·Token 을 넣지 않는다.**
3. 키는 설치 후 사용자가 **설정 화면에서 직접 등록**, **Windows Credential Manager 또는 DPAPI 기반 보안 저장소**에 저장.
4. **GitHub Actions 용 Secret 과 개인 PC 실행용 API Key 를 분리**.
5. **키 없이도 설치·실행·기본 화면·로컬 초안 관리**가 가능해야 한다.
6. 여러 키는 **공급자와 용도별로 분리**해 관리.
7. **429·일일 한도·일시적 5xx·Timeout 일 때만** 허용된 다음 키 또는 제공자로 전환.
8. **401·403·잘못된 요청·정책 차단·콘텐츠 차단**은 자동 키 전환으로 숨기지 말고 사용자에게 **조치 방법을 표시**.
9. **무료 한도 우회를 목적으로 무제한 키를 순환시키는 기능은 구현하지 않는다.**
10. **프로그램 설치 위치와 사용자 데이터 위치를 분리**.
11. 업데이트·재설치 때 **초안·설정·발행 기록·이미지 메타데이터가 삭제되지 않게**.
12. 업데이트 전 **자동 백업**, DB 스키마 마이그레이션이 실패하면 **이전 데이터로 복구**.
13. Release Asset: `Setup.exe` · `Portable.zip` · `SHA256SUMS.txt` · `CHANGELOG.md` · `MIGRATION_NOTES.md`.
14. 초기 배포는 **`v0.x.x-beta`** 형식, **개인 PC 에서 설치·업데이트·삭제·복구를 검증한 뒤 v1.0.0** 으로 전환.
15. 코드 서명이 없는 초기 설치 파일은 **SmartScreen 경고**가 날 수 있음을 README·설치 안내에 기록.
16. Private 저장소 자동 업데이트에 **Personal Access Token 을 설치 파일에 넣지 않는다**. 초기에는 **GitHub Releases 페이지를 열어 사용자가 직접 업데이트**.

**저장소에 이미 있는 것(2026-11-03 20:35, 데스크톱 main `32c19c6` + 작업 브랜치 읽음):**
- `docs/RELEASE.md` + D-04·D-05·D-06: PyInstaller `--onedir` + Velopack(`vpk`) + Actions 가 **초안 릴리스**로 올리고 운영자가 'Publish release' 한 번. 공개 파일 = Setup.exe·휴대용 ZIP·full/delta 패키지·`SHA256SUMS.txt`(+서명)·`CHANGELOG.md`·`MIGRATION_NOTES.md` → **항목 13 과 같다.** 무서명 + 자체 Ed25519 서명 매니페스트, 유료 인증서 안 삼, 사용자 폴더 설치(관리자 불필요, D-06).
- 사용자 데이터는 `%LOCALAPPDATA%/ChanceblogDesktop`(`service/context.py`) — 항목 10 일부. `content/store.py` 에 `SCHEMA_VERSION=2`·`PRAGMA user_version`·순방향 `MIGRATIONS`·`backup(폴더)`·백업 복원 → 항목 11·12 의 바닥. **남은 것:** 업데이트 직전 자동 백업을 실제로 부르는 흐름·마이그레이션 실패 때 자동 복구·그 시험.
- **운영자 16항목이 우선하는 차이:** (a) RELEASE.md 는 앱 안 자동 다운로드·적용(서명 매니페스트·`apply_updates_and_restart`)이지만 운영자는 **초기에 'Releases 페이지 열기'(수동 업데이트)** → 자동 적용·서명 매니페스트·`UPDATE_SIGNING_KEY` 시크릿은 뒤로 미룬다(만들 때 T3). (b) 태그 형식: RELEASE.md `vX.Y.Z-beta.N` ↔ 운영자 `v0.x.x-beta` → 운영자 형식을 따른다(`v0.1.0-beta`, 다음 `v0.1.1-beta`…; 결정 기록 D-xx 갱신). (c) D-07(선택 AI 키는 필요 확인 전엔 안 만든다)은 그대로 — 단 키를 받는 자리는 설정 화면(항목 3).
- **위험(RELEASE.md '코드 서명'):** **스마트 앱 컨트롤(SAC)이 켜진 개인 PC 는 무서명 프로그램을 아예 차단**한다(SmartScreen 의 '추가 정보 → 실행' 으로도 안 됨). 운영자가 개인 PC 에서 Windows 보안 → 앱 및 브라우저 컨트롤 → 스마트 앱 컨트롤 상태를 먼저 확인해야 한다. README·설치 안내(항목 15)에 SmartScreen 과 SAC 를 둘 다 쓴다. SAC 가 켜져 있으면 서명(SignPath 무료 등)을 검토 — 그 결정은 운영자 몫.

**키 관련(항목 3~9)은 20:3x 에 키 보관 구현자 `a5dd64af19b4121dd`('k')에 새 정책으로 전달함:** 전환 가능한 오류는 정확히 4종(429 한도·일일/기간 한도 소진·일시적 5xx(500·502·503·504)·Timeout), 전환하지 않는 오류는 401·403(인증)·400·422(잘못된 요청)·정책 차단·콘텐츠 차단·기타 → 쉬운 한국어 **조치 안내만**(자동 전환·자동 재시도 없음); 같은 용도·제공자 안의 `사용`·`예비` 항목, 다음 제공자는 운영자가 켠 `fallback_providers` 만(기본 비어 있음); 용도마다 키 최대 3개(`MAX_ENTRIES_PER_PURPOSE=3` — 무제한 순환 금지의 구조적 보증, 시험으로 고정); 한 요청에서 한 바퀴; 같은 한도 묶음(같은 프로젝트·앱)의 항목으로는 한도 오류 때 전환하지 않음; 둘째 키를 추가할 때 약관 경고 1회·확인 기록; 키가 없는 상태는 정상('연결 안 됨' 안내만); PC 키는 Actions 시크릿과 별개(같은 값 재사용 금지 안내). **이전 '예비 키 전환 기본 꺼짐' 정책은 운영자의 새 결정으로 대체**(→ 다음 `decision` 요청에서 그 항목은 뺀다. [[gui-polish-spec-v11-and-keys]] 정정 참조). Gemini 는 한도가 키가 아니라 프로젝트 단위라 같은 프로젝트 키 추가로는 한도가 늘지 않는다는 사실은 그대로 안내에 쓴다.

**마무리 단계 작업 순서(착수 시 — 이 순서로, 묶음마다 독립 검증):**
1. **차이 분석 먼저**(요구서 v0.3.1 때처럼): 16항목 × (이미 있음/부분/없음) 표 + 위 차이 3건을 `decision`/`info` 로 운영자에게(기본값 포함). SAC 상태 확인 요청 포함(운영자 몫).
2. **앱 쪽**: ① 업데이트 확인 = 공개 Releases API 로 최신 `v*-beta`/stable 조회 → '새 버전이 있습니다'+버튼이 Releases 페이지를 기본 브라우저로 연다(PAT 없음·자동 설치 없음, 항목 16) ② 버전이 바뀐 첫 실행에서 **자동 백업**(`backups/<날짜-버전>/`, 비밀 값 없음 — 키는 자격 증명 관리자) → 마이그레이션 → 점검, 실패하면 **백업으로 자동 복구**하고 사용자에게 쉬운 말로 안내(항목 11·12) ③ 설치 위치(읽기 전용 프로그램 파일)와 데이터 위치(`%LOCALAPPDATA%/ChanceblogDesktop`) 분리 시험, 삭제(제거기)가 데이터를 지우지 않는지(지우기는 별도 선택) ④ 키 없이 첫 실행·초안 만들기·복사 흐름 시험(항목 5).
3. **릴리스 쪽**: `release.yml`(workflow_dispatch, `windows-latest`, 권한 최소·액션 SHA 고정): 시험 → PyInstaller → 자가 점검 → `vpk pack` → `SHA256SUMS.txt` → `CHANGELOG.md`(해당 버전 발췌)·`MIGRATION_NOTES.md` → **초안(prerelease) 릴리스**로만 업로드. **설치 파일 비밀 검사**(키·토큰·`.env` 모양이 번들에 없음 — `security/mask.py` 재사용) 시험, (n-1)→(n) 업데이트·롤백 시뮬레이션은 Actions 에서.
4. **문서**: README 설치 절(SmartScreen·SAC 경고·키 없이 시작·업데이트 방법·데이터 위치·백업과 복구), `docs/INSTALL.md`·`docs/UPDATE_AND_RECOVERY.md`·`docs/RELEASE.md` 갱신, 개인 PC 검증 체크리스트(운영자가 따라 할 '설치 → 키 없이 실행 → 초안 → 업데이트 → 삭제 → 복구' 쉬운 한국어; 결과는 `[답변]` 이슈 또는 요청 답으로).
5. **공개**: `v0.1.0-beta` 초안 릴리스 → 운영자가 'Publish release'(T3, 번호 요청) → **운영자가 개인 PC 에서 검증**(AI 가 할 수 없음) → 통과하면 v1.0.0 승격은 운영자 결정.
5-1. **화면 도구·이미지 관련 설치 검증(운영자 채팅 2026-11-03 22:27 추가):** 화면은 **PySide6**(R-087 G1=B) — PyInstaller `--onedir` 묶음에 **JPG·PNG·WebP 를 읽는 Qt 이미지 형식 플러그인(`imageformats`)이 들었는지 확인**하고 **설치된 환경에서 `QImageReader.supportedImageFormats()` 로 검증**(설치 시험 체크리스트에 넣는다), WebView2 불필요, 개인 PC 검증에서 **1366×768/100%·1920×1080/100%·1920×1080/125%(필수)·150%(조건부 — 핵심 기능만)** 실제 배율 확인·한글 입력기·화면 읽기. 
6. **한계를 숨기지 않는다:** 무서명 exe — SmartScreen 경고·백신 오탐 가능; 이 PC(회사)에서는 격리 폴더 설치 시험까지만; 개인 PC 검증과 SAC 확인은 운영자 몫.

관련: [[desktop-repo-chanceblog-desktop]] [[gui-polish-spec-v11-and-keys]] [[unsplash-image-provider-analysis]] [[desktop-auto-draft-v031]]
