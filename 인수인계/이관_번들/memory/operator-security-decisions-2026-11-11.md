---
name: operator-security-decisions-2026-11-11
description: "운영자 2026-11-11 ~09:2x 채팅 — 보안 조사(높음 3건) 결과에 대한 결정 9항목: 폴더 이름 유지·H1 공통 Redaction(11개 위치)·H2 끝 4자리 제거(표시 5가지만)·M3 초안 저장·Backup 전 Secret 검사·H3 외부 Write 완전 비활성(후속으로 미루지 않음)·Blogger OAuth UI 숨김·개인 PC 필수 시험(표준 계정·다른 계정)·Installer 정보·Package Gate 12항목, 일정은 Gate 기준으로 재산정(11-14~15 고정 금지)"
metadata:
  node_type: memory
  type: project
  originSessionId: 921b6032-bba9-4b52-8c2d-b24e5509c445
  modified: 2026-11-11T00:21:34.046Z
---

**운영자 채팅 원문:** `C:/work/ai/audit6/secaudit/operator_decisions_2026-11-11.md`(저장소 금지). 앞선 보안 조사 보고(SECAUDIT: 필수 0·높음 3·중간 3)에 대한 답 — **높음 결함 3건이 있으므로 개인 PC 제한 Package 는 아직 만들지 말 것**, 아래 기준으로 수정:
1. **데이터 폴더 `ChanceblogDesktop` 유지**, 이름 변경·마이그레이션 금지.
2. **H1**: Package 전 필수. 공통 Redaction(각 기능에서 따로 구현 금지, 공통 경계)을 일반 로그·오류 로그·예외·스택 추적·진단 정보·연결 시험 결과·URL 질의·요청 헤더·UI 메시지·시험 실패 출력·워크플로 산출물에 적용. 대상 이름: Authorization·api_key·apikey·serviceKey·access_token·refresh_token·client_secret·password·Cookie·Set-Cookie·X-API-Key.
3. **H2**: 끝 4자리 표시 전부 제거. UI 는 Provider 이름·Key Slot·등록됨/미등록·마지막 연결 시험·등록 시각만(원문·일부 문자열 금지).
4. **M3**: 초안 저장과 Backup 전에 Secret 형태 검사 — Google API Key·GitHub Token·Bearer Token·OAuth Token·AWS Access Key·PEM Private Key. 발견 시 전체 토큰 재표시 금지·위치·유형만·기본값 저장/Backup 중지·본문으로 돌아가 제거 안내·자동 삭제·치환 금지·**초기 Package 에 '무시하고 저장' 제공 금지**.
5. **H3**: 후속으로 미루지 말고 이번 Package 전 범위 — 초기 제한 Package 는 **외부 Write 완전 비활성**. 허용: 로컬 Profile·Seed·후보·규칙 기반 초안·편집·복사·기존 글 읽기·글 모양 점검·로컬 저장·Backup/Restore·네이버 글쓰기 페이지 열기. 금지: git push·GitHub PR 생성·Chance 자동 게시·Blogger API 호출·Blogger 게시·네이버 자동 로그인·게시·Cookie/Session 사용·예약 게시·외부 초안 전송. UI 버튼만 숨기지 말고 External Write Service 비활성·External Adapter 미등록·Runtime Gate·Network Write 0 시험 — 컴퓨터에 기존 Git 로그인이 있어도 앱이 push 못 해야 함.
6. **Blogger OAuth 입력칸**: Credential Manager 저장 구조는 유지 가능, 호출 코드 없는 초기 Package 에서는 입력 UI 를 숨기거나 비활성. Blogger 초안 기능 구현 때 Scope·연결 해제·Token 삭제·재인증·초안 전용 정책과 함께 별도 검증 후 노출.
7. **개인 PC 필수 시험**(운영자가 개인 PC 에서 — 이 PC 는 관리자 세션·UAC 꺼짐이라 AI 가 표준 계정 시험 불가): 표준 사용자 계정에서 설치·실행·**Profile·Seed·초안 저장**·재실행 후 복원·Backup/Restore·Credential 등록·삭제·관리자 권한 요구 0 + 다른 일반 Windows 계정에서 첫 계정 LocalAppData DB 접근 실패·Credential 접근 실패.
8. **Installer**: 첫 Package 에 Version(0.1.0-preview.1 권장)·Git Commit·SHA-256·Dependency 목록·Build 방법·Malware 검사 결과·서명 여부·SmartScreen 예상 동작, 미서명이면 '개인 PC 제한 시험용, 미서명 Package' 명확 표시.
9. **Package Gate**(모두 통과해야 제안): H1 수정·H2 제거·H3 외부 Write 완전 비활성·M3 Secret 저장 방지·표준 사용자 실행·다른 일반 계정 데이터 접근 차단·Backup Secret 0·Log Secret 0·Credential 사용자 범위 확인·SHA-256 제공·외부 게시 0 증명·전체 시험과 독립 검증 통과. **일정은 11-14~15 로 고정하지 말고 Gate 통과 기준으로 재산정. H3 를 별도 후속으로 미룬 상태에서는 Package 배포 금지.**

**Why:** 개인 PC 단일 사용자 로컬 앱의 보안 경계(Windows 계정)를 지키되 외부 공개 경로는 0 으로 시작하려는 운영자 방침. **내 이전 기본값 변경**: 초안 저장을 '선택(1단계 제외)'로 정했었으나 운영자가 7번에서 'Profile·Seed·초안 저장·재실행 후 복원'을 Package 시험 항목으로 요구 → **초안 저장은 이제 Package 필수**(Gate 11). H3 도 '스위치 기본 꺼짐'(내 PCSEC1 초안)이 아니라 완전 비활성+켜는 길 없음으로 강화.
**How to apply:** ① 수정 묶음 PCSEC1(구현자 `a6cf797fec2d016b3`, 지시서 `audit6/PCSEC1_BRIEF.md` + `audit6/PCSEC1_ADDENDUM.md`(우선)): H3 네 겹(Service 비활성·Adapter 미등록·소스 상수 `capabilities.py` Runtime Gate·Network Write 0 시험)·H1 공통 경계(프로세스 전체 stdout/stderr·logging·excepthook·UI 메시지)·H2·M3 스캐너 API(체크포인트 먼저)·Blogger 숨김·M1·M2·M4. ② 스캐너 API 가 나오면 **LOCALSAVE 묶음**(초안 저장·재시작 복원·백업 범위에 `settings.json`·글쓰기 열기 폴백) 시작. ③ **PCKIT**: 0.1.0-preview.1 빌드·manifest(Git Commit·SHA-256·의존성 목록·빌드 방법·Malware 검사·서명 여부·SmartScreen 예상)·개인 PC 시험지(표준 계정·다른 계정 — 운영자용 쉬운 글)·빌드 워크플로는 `.github` 변경이라 T3(운영자 승인 요청 필요). ④ 순서: PCSEC1→LOCALSAVE→PCKIT→preview 빌드→운영자 개인 PC 시험→Gate 12항목 통과→Package 제안. 일정은 날짜 고정 없이 추정 범위만. ⑤ 블로그 워크플로 artifact 에 비밀이 올라가는지 읽기 전용 점검은 별도 후속(낮은 우선순위 — 이 결정의 '워크플로 산출물' 항목은 데스크톱은 규칙 시험, 블로그는 점검).
