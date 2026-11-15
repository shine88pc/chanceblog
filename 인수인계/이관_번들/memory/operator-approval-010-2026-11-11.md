---
name: operator-approval-010-2026-11-11
description: "운영자가 확인 요청 010(R-261, PCKIT 빌드 워크플로 한 파일 T3)을 이슈 #178 로 승인(2026-11-11 19:26 KST) — 승인 범위와 아직 승인 아닌 것"
metadata:
  node_type: memory
  type: project
  originSessionId: 921b6032-bba9-4b52-8c2d-b24e5509c445
  modified: 2026-11-11T10:29:33.364Z
---

운영자가 2026-11-11 19:26:42 KST 에 이슈 #178 `[답변]`(라벨 운영자응답)으로 **확인 요청 010 = 선택 ①(승인)** 을 보냈다(R-261 발송 2분 뒤). 봇이 접수 코멘트를 달았고 요청 파일의 1번 '승인 — 워크플로 한 파일을 병합 부탁 대상에 올림(병합은 따로 부탁)' 과 대조해 유효함을 확인했다.

**승인 범위**: 데스크톱 저장소 `.github/workflows/package.yml` **한 파일**(수동 실행만·입력칸·비밀 없음·읽기 권한·산출물 네 가지 14일, 워크플로 가지 `ai/claude/NO-MERGE-pckit-workflow` 머리 abb6d42)을 **병합 부탁 대상에 올려도 된다**는 것. 액션 세 개의 고정값(checkout v4.4.0 `11d5960a…`·setup-python v5.6.0 `a26af69b…`·upload-artifact v4.6.2 `ea165f8d…`)은 내가 `git ls-remote --tags` 로 공식 태그와 일치함을 확인해 요청에 적었다.

**Why:** 개인 PC 로 앱을 옮기려면 회사 PC 반출이 안 되므로 GitHub Windows 러너가 만든 압축 파일을 개인 PC 브라우저로 내려받는 길이 필요하다.

**How to apply:** 이 승인은 병합 부탁이 아니다. 앱 보안 수정(PCSEC1)·초안 저장(LOCALSAVE)·백업(BACKUPUI)·N-3a·PCKIT 코드가 병합된 **뒤** `ai/claude/M###-package-workflow`(main 위 한 커밋·파일 한 개)로 병합 부탁을 따로 보낸다(CI 초록 뒤·한 번에 하나). 병합 뒤 Actions 에서 한 번 실행해 개인 PC 용 최종 Package(`--allow-missing-gate` 없이, `release_eligible=true`)를 만든다. 승인에 없는 것: 서명·스마트 앱 컨트롤 설정 변경·다른 워크플로·릴리스 게시. 첫 실행에서 DLL 출처 검사가 러너 환경 때문에 거절하면 고쳐서 다시 올린다. [[operator-security-decisions-2026-11-11]] [[operator-request-personal-pc-limited-use-2026-11-11]]
