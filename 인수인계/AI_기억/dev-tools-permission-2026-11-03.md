---
name: dev-tools-permission-2026-11-03
description: 운영자 상시 허가(2026-11-03 18:35 채팅) — 필요한 개발 도구는 받아서 써도 되고 품질 상승 요인이 많으면 진행해도 됨; 내가 지키는 안전 경계와 설치한 도구 목록(C:\ccgui)
metadata:
  node_type: memory
  type: feedback
  originSessionId: (세션 번호)
  modified: 2026-11-03T09:41:48.760Z
---

**운영자 지시(2026-11-03 18:35, 채팅):** "필요한 도구가 있으면 받아서 사용할 수 있도록 해줘. 퀄리티 상승 요인이 많다면 진행해도 돼." (같은 날 18:05 의 'D2 화면 도구 설치 허용'을 넓힌 상시 허가.)

**Why:** 검증 보고마다 '이 PC 에 3.10·Linux·측정 도구가 없어 못 했다'가 반복됐고, CI 에서야 드러나 병합 부탁이 늦어졌다(R-068·R-071 의 빨간 검사). 운영자는 기다림·재확인 번거로움을 줄이고 품질을 올리길 원한다.

**내가 지키는 경계(허가를 넓게 읽지 않는다):**
- **공식 출처만**: PyPI 휠(`S\pipsafe.py` — `pip install --dry-run --report` 로 의존 패키지까지 풀고 **나온 지 14일 미만·yanked 이면 멈춤**, `--only-binary=:all:`), 파이썬 본체는 python.org(MD5 대조 + Authenticode 서명자 'Python Software Foundation' 확인). wheel 이 없어 sdist 만 있는 패키지는 내려받아 `setup.py`·모듈을 읽고 위험 구문이 없을 때만(예: proxy_tools 0.1.0).
- **사용자 수준·격리 설치만**: `C:\ccgui\` 아래(짧은 경로 — 긴 경로 한도를 시스템 설정으로 풀지 않음). **관리자 권한·시스템/보안 설정 변경(레지스트리 PATH·Defender 제외·Windows 기능·WSL·Docker·긴 경로 켜기)·계정 만들기·유료·비밀 입력은 하지 않는다** — 필요하면 번호 있는 요청으로 묻는다.
- **기록**: 설치할 때마다 이 파일의 목록에 이름·버전·출처·크기·용도를 적는다. 저장소의 앱·CI 의존성에는 추가하지 않는다(앱은 계속 표준 라이브러리만; 도구는 로컬 개발용).
- 회사 PC 라 정책 차단(프록시·AppLocker)이 나오면 우회하지 않고 보고한다.

**설치한 도구(2026-11-03):**
| 위치 | 내용 | 출처·확인 | 크기 | 용도 |
|---|---|---|---|---|
| `C:\ccgui\py310\python.exe` | CPython **3.10.11**(사용자 설치, 런처·PATH·파일 연결 없음) | python.org `python-3.10.11-amd64.exe`, MD5 a55e9c1e…2f51 일치, 서명자 PSF 유효 | 52 MB | **진짜 3.10 시험**(CI 의 3.10 칸을 로컬에서 미리). 3.10.12 이후는 소스만 배포라 마지막 바이너리인 3.10.11 |
| `C:\ccgui\v310` | 3.10 가상환경 + pip 25.0.1·PyYAML 6.0.3 | PyPI(3.12 의 pip 로 `--python` 설치 — 3.10.11 의 옛 pip 는 회사 프록시 인증서를 못 믿어 실패) | 작음 | 블로그 시험 3.10 실행 |
| `C:\ccgui\dev` | 3.12 가상환경: coverage 7.16.2·ruff 0.17.1·hypothesis 6.170.5(+sortedcontainers)·Pillow 13.0.0·pyflakes 4.0.3·vermin 1.9.2 | PyPI 공식 휠, 14일 이상 | 약 19 MB | 시험 적용 범위(안 닿은 줄·가지)·코드 점검·무작위 입력 점검·하한 버전 점검 |
| `C:\ccgui\v` | GUI 시제품 가상환경: PySide6-Essentials 6.12.0·pywebview 6.2.1(+pythonnet·proxy_tools 등), **PyInstaller 6.22.3·Pillow 13.0.0**(pyinstaller-hooks-contrib 2026.8·setuptools 84.0.0 으로 고정) | PyPI | 약 250 MB | 화면 도구 비교·번들 크기 실측 |
| `C:\ccgui\dl\` | 내려받은 설치 파일 보관(py310_installer) | — | 29 MB | 지워도 됨 |

**쓰는 법:** 3.10 시험 `C:\ccgui\py310\python.exe -X utf8 -m unittest discover -s tests`(데스크톱은 표준 라이브러리만); 블로그는 `C:\ccgui\v310\Scripts\python.exe`. 적용 범위 `C:\ccgui\dev\Scripts\python.exe -m coverage run --branch --source=… -m unittest …`. 린트 `C:\ccgui\dev\Scripts\ruff.exe check --select F,E9,B,UP --target-version py310 src tests`. **새 설치는 `python -X utf8 S\pipsafe.py <대상 파이썬> <패키지==버전>…`** 로(Python 3.10 의 pip 는 옛 버전이면 `C:\ccgui\dev\Scripts\python.exe -m pip --python <3.10 exe> install …` 로).
**지우는 법:** `C:\ccgui` 폴더 삭제 + 3.10 은 설치 프로그램의 제거(HKCU 항목)로. 할 일: 저장소 문서에 개발 도구 목록 반영(데스크톱 `docs/MIGRATION.md` 환경 절, 블로그 `docs/AGENT_RUNBOOK.md` — 다음 문서 PR).
관련: [[operator-answers-r078-2026-11-03]] [[dev-environment-notes]] [[feedback-precheck-ci-before-merge-request]]
