# 데스크톱 프로그램 설치·자동 업데이트(GitHub Releases) — 조사와 권고 (2026-10-30)

> 운영자 요청(2026-10-30, 채팅): 프로그램을 GitHub 로 공유해 개인 데스크톱에 설치하고, 이후 업데이트가 사용 중인 개인 PC 에서도 자동으로 적용되게 배포. 조사 에이전트 한 명이 2026-10-30 에 공식 문서·릴리스 API·저장소를 읽은 보고를 이 저장소의 사정(파이썬 코어 재사용, 개인 Windows PC, 개발은 AI 도구·빌드는 GitHub Actions, 운영자는 비개발자)에 맞춰 줄인 것이다. **세부 수치는 요약 도구를 거쳐 읽은 것이라 시행 전에 원문과 대조한다.** 표기: ◎ 공식 원문 / ○ 언론·해설 / △ 개인 글·추정 / ✕ 미확인. T3 = 운영자 승인이 드는 것.

## 한 줄 결론

- **1순위: 기존 파이썬 유지 + PyInstaller(`--onedir`) + Velopack(파이썬 SDK) + GitHub Releases 초안.** `vpk` 한 번으로 설치 파일(Setup.exe)·휴대용 ZIP·차등 업데이트·채널이 나온다(공식 PySide6 샘플 있음). 우리가 직접 얹을 것은 두 가지다: **Ed25519 서명 매니페스트**(업데이트 무결성)와 **앱 안의 백업·마이그레이션·롤백**(Velopack 문서에 자동 롤백이 없다).
- **2순위**: 같은 PyInstaller 산출물 + Inno Setup(사용자 단위 설치) + tufup 또는 자체 서명 업데이터 — .NET·Velopack 이 필요 없는 대신 적용·롤백 코드를 직접 짠다.
- Electron·Tauri 는 화면을 새로 만들 때의 3순위다(기존 시험 4,272개와 파이썬 코어를 못 쓴다).
- **코드 서명 인증서는 사지 않는다**(유료). 무서명으로 시작하되 업데이트 파일의 무결성은 자체 서명·해시로 지킨다. **먼저 운영자 PC 의 Smart App Control(SAC) 상태를 확인한다** — 켜져 있으면 무서명 프로그램이 차단된다.

## 후보 비교(줄임)

| 후보 | GitHub Releases·한도 | 무서명일 때 | 무관리자 | 차등·롤백·채널 | 이 프로젝트 적합 |
|---|---|---|---|---|---|
| ① Electron + electron-updater | 공개 저장소는 릴리스 목록 읽기, 비공개는 사용자 PC 에 토큰 필요 | 첫 설치 SmartScreen 경고. 서명 검증 우회 이력(2020, CVE-2024-39698) | 가능 | 차등·채널 있음, 롤백 없음, 휴대용 자동 갱신 불가 | 자료 최다, 기존 코드 못 씀, 8주 주기 업그레이드 부담 |
| ② Tauri v2 | 정적 `latest.json`(API 불필요) | 업데이터 서명 필수(변조 방어), 첫 설치 경고는 같음 | 가능 | 차등·롤백 없음 | Rust 빌드, 파이썬은 사이드카 |
| ③ 파이썬 + Inno Setup + 자작/tufup | 정적 URL(API 불필요) | 검증은 직접(Ed25519/TUF), PyInstaller 오탐 보고 많음 △ | `PrivilegesRequired=lowest` | tufup 패치·롤백 방어, 나머지 직접 | 코드·시험 그대로, 자작 업데이터 위험 |
| **④ Velopack(파이썬 SDK)** | GitHub 릴리스 API(비인증 시간당 60회/IP) 또는 정적 URL | 크기·해시만 검증, 서명 검증 문서 없음 → **자체 서명을 한 겹 더** | `%LocalAppData%` 설치 | zstd 차등·채널, 다운그레이드 기본 금지, **자동 롤백 문서 없음** | **1순위.** MIT, 최근 12개월 활발(1.2.161, 2026-09-29) |
| ⑤ .NET + Velopack | ④와 같음 | ④ | ④ | ④ | 재작성 필요 |
| ⑥ MSIX + App Installer | 웹 설치 프로토콜이 2023-12 부터 기본 꺼짐 | 신뢰 서명 필수(자체 서명도 기기마다 신뢰 등록) | 인증서 신뢰에 관리자 필요(추정) | 미확인 | 부적합 |
| ⑦ WinSparkle | appcast 정적 | EdDSA 서명 필수, 설치기 실행만 담당 | 설치기 몫 | 없음 | 보조 |
| ⑧ winget | 보조 배포 경로 | 심사·자동 검증 | 설치기 몫 | 자동 업데이트 아님 | 나중에 선택 |

공통: 앱이 받은 업데이트 파일에는 '인터넷에서 받음' 표식(MOTW)이 붙지 않아 SmartScreen 창이 뜨지 않는다(○) — 경고는 **첫 설치**에만 나온다. 첫 설치 경고는 서명 없이는 없앨 수 없다.

## 코드 서명 선택지

| 선택지 | 비용 | 조건·한계 |
|---|---|---|
| 무서명 | 0 | 첫 설치 경고. **SAC 켜짐이면 차단**(앱별 예외 불가) |
| 자체 서명 | 0 | 무서명과 동일(SAC 는 사용자·관리자 신뢰 루트를 불인정 ○) — 실익 없음 |
| SignPath Foundation | 0 | OSI 라이선스 공개 저장소, 활발한 유지, 이미 릴리스된 실행 파일, 릴리스마다 승인자, MFA. 심사 재량 |
| Azure Artifact Signing | 월 $9.99(Basic) | 조직은 한국 포함(Quickstart 2026-10-08), 개인은 미국·캐나다만. 문서 간 지역 설명이 엇갈림 → 포털에서 직접 확인 |
| 인증서 구매 | 연 약 $130~300 + 서명 서비스 | 개인 가능(정부 ID), HSM 필수, 유효 최대 460일 |
| Microsoft Store(MSIX) | 등록비 없음 | 개인 계정은 사업·직업과 무관한 앱만, GitHub Releases 방식과 다름 |

권고: ① 지금은 **무서명 + 자체 서명 매니페스트** ② SAC 가 켜져 있으면 운영자가 끄거나(2026-04 부터 재활성화 가능) 서명을 도입 ③ 서명이 필요해지면 SignPath(무료, 조건 충족 시) → 사업자등록이 있으면 Artifact Signing → 인증서 구매 순. 서명해도 SmartScreen 평판은 수 주·수백 건의 정상 설치가 쌓여야 조용해지므로 **1인 도구에서 서명의 실익은 주로 SAC 통과**다. 서명하려면 번들 안 모든 PE(.exe/.dll/.pyd)와 제거기까지 서명해야 한다.

## 권장 릴리스·업데이트 흐름

1. **버전 올리기(AI)**: PR 로 `VERSION`·`CHANGELOG`·이관 노트·DB 마이그레이션 갱신 → 시험 통과 후 운영자 병합 → 태그 `desktop-vX.Y.Z`(채널은 `-beta.N`/`-dev.N`). 이 저장소 안에 두면 사이트 태그와 섞이지 않게 접두사를 붙인다.
2. **Actions 빌드**(`windows-latest`): 시험 → PyInstaller → 자가 점검(`--selftest`) → `vpk download github`(차등 기준) → `vpk pack --channel` → SHA256SUMS + Ed25519 서명 → 초안 릴리스 업로드(`--publish` 를 빼면 초안).
3. **초안 릴리스**: Setup.exe·Portable.zip·full/delta 패키지·채널 매니페스트·SHA256SUMS(.sig)·변경 이력·이관 노트.
4. **운영자 공개**: 'Publish release' 한 번(텔레그램 요청으로 안내). **불변 릴리스(Settings → Releases → Enable release immutability)를 켜 두면** 공개 뒤 자산·태그를 바꿀 수 없다 ◎.
5. **앱의 확인**: 채널별로 확인, 서명 매니페스트의 서명·version·seq·expires 검증, 다운그레이드 거부.
6. **다운로드·검증**: Velopack 의 크기·해시 검증 + 서명된 해시 대조. 불일치하면 폐기.
7. **백업**: 데이터 폴더(설치 폴더 밖 — 업데이트는 `current` 만 교체)를 SQLite backup API 로 스냅샷, 최근 N개 보관.
8. **적용·마이그레이션**: `apply_updates_and_restart` → 첫 실행에서 `PRAGMA user_version` 순방향 마이그레이션 → 자체 점검 통과 시 '정상' 표식.
9. **롤백**: 점검 실패나 연속 기동 실패 2회면 백업 복원 + 이전 릴리스 재설치. 다운그레이드는 복구 모드에서만. (Velopack 에 없으니 **직접 구현·시험**)
10. **업데이트 시험**: Actions 에서 (n-1) 설치 → (n) 업데이트 → 롤백을 시뮬레이션.

워크플로 권한은 기본 전부 차단(`permissions: {}`), 시험 잡은 `contents: read`, 빌드 잡은 환경 시크릿(`environment: release`, 필수 검토자)과 `contents: write`(초안 업로드)만. 액션은 전체 SHA 로 고정, `pip --require-hashes`. 시크릿은 자동 `GITHUB_TOKEN` 과 `UPDATE_SIGNING_KEY`(Ed25519 개인키)뿐이다(서명 도입 시 SignPath·Azure 항목 추가).

## 업데이트 보안

| 위험 | 완화 |
|---|---|
| 중간자·호스팅 침해(Notepad++ 2025 사건: 업데이트 경로 변조, 설치기·XML 서명 미검증이 원인) | HTTPS 만, 서명 없으면 업데이트 거부 |
| 악성 릴리스 교체 | 불변 릴리스, 초안→공개, 앱 내장 공개키 서명, 출처 증명(공개 저장소) |
| 저장소 토큰·계정 탈취 | 패스키·2FA, 앱에 토큰 내장 금지, 기본 `GITHUB_TOKEN` 읽기 전용, 태그 보호, 워크플로 CODEOWNERS |
| 서명 키 분실·유출 | 환경 시크릿 + 오프라인 백업 2곳, 앱에 현재·예비 공개키 내장(분실하면 기존 설치에 업데이트 불가) |
| 롤백·동결 공격 | 매니페스트에 version·seq·expires, 다운그레이드 거부 |
| 업데이터 자체 버그 | 도구 내장 검증만 믿지 않고 자체 서명 한 겹 |
| AI 가 보안 코드를 바꿈 | 업데이트·서명·워크플로·공개키 변경 PR 은 T3 표시, 승인 전 병합 금지 |

## 운영자·AI 구분

- **운영자만**: GitHub 패스키, 저장소 설정(불변 릴리스·Environment `release`·태그 보호·Actions 권한), 시크릿 값 입력(`UPDATE_SIGNING_KEY` — 키 생성 스크립트는 AI 가 쓰되 개인키 값은 운영자만 보관), 서명 계정 가입·결제, **PC 점검(Smart App Control 상태)**, 최초 설치(경고 클릭), 릴리스마다 Publish release.
- **AI**: 앱·시험·워크플로 PR, 업데이트 클라이언트·서명 검증·백업·마이그레이션·롤백, 릴리스·이관 노트·복구 안내, 의존성 잠금·점검.
- **T3**: 새 저장소(선택 시), 환경·시크릿·키, 저장소 설정 변경, 서명 계정·결제, 서명·업데이트·워크플로 코드 수정 PR, `_config.yml` `exclude` 에 `desktop/` 추가(이 저장소에 둘 때).
- **운영자에게 물을 것(최소)**: 개인 PC 의 **Smart App Control 상태**(Windows 보안 → 앱 및 브라우저 컨트롤 → 스마트 앱 컨트롤: 켬/평가/끔), 서명이 필요해질 때를 위한 사업자등록 유무.

## 확인하지 못한 것·충돌·점검 시점

- 한국 개인의 Artifact Signing 자격(문서 간 충돌), SignPath 신청 절차·한국 거주자 가능 여부, 국내 인증기관 가격, Velopack 의 롤백·서명 검증은 '문서에 없음'일 뿐 코드는 미확인(정적 `latest/download` URL 방식 시험 필요), 설치기 한국어 지원, 토스트 알림용 앱 식별자 설정, PyInstaller 오탐 빈도, 설치 크기·빌드 시간 실측.
- 문서 충돌: '즉시 평판'(Velopack 문서) 대 '즉시 신뢰 아님'(MS) — MS 를 따랐다. Velopack 의 '1.3 부터 직접 서명'은 1.3 이 아직 시험판이라 현재 안정판(1.2.161)에는 해당하지 않는다.
- 점검 시점: 2026-11 말(Artifact Signing 지역·개인 자격), 2026-12(Velopack 1.3 정식·파이썬 SDK), SAC·SmartScreen 정책 변경 시(분기 1회).

## 주요 출처(2026-10-30 읽음, 전체 목록은 조사 보고에 있음)

Velopack: docs.velopack.io, github.com/velopack/velopack(`samples/PythonQt`) · electron-builder/updater: electron.build/v26 문서 · Tauri: v2.tauri.app/plugin/updater/ · Inno Setup: jrsoftware.org/ishelp · tufup: github.com/dennisvang/tufup · MS Learn: windows/apps/package-and-deploy/{code-signing-options,smartscreen-reputation}, azure/artifact-signing/quickstart · SAC FAQ: support.microsoft.com(스마트 앱 컨트롤) · SignPath: signpath.org/terms · GitHub: docs.github.com(불변 릴리스·secure-use·환경 시크릿), github.blog/changelog/2025-10-28-immutable-releases-are-now-generally-available/ · Notepad++ 사건: notepad-plus-plus.org/news/hijacked-incident-info-update/ · TUF 위협 모델: theupdateframework.io/docs/security/ · 구글 OAuth 네이티브 앱: developers.google.com/identity/protocols/oauth2/native-app
