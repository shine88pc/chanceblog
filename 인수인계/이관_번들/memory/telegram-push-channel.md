---
name: telegram-push-channel
description: AI 가 사용자에게 텔레그램을 보내는 길 — 푸시로 도는 워크플로(저장소 시크릿)뿐. 2026-10-28 정식 경로(요청 파일 R-nnn → `[공통] AI 요청 텔레그램 알림`)가 병합·검증됨, 임시 tg-note-* 브랜치는 삭제
metadata:
  node_type: memory
  type: reference
  originSessionId: 6dd8f403-b855-4b67-ab8d-8eba60cc6b54
  modified: 2026-11-02T09:50:02.690Z
---

AI(이 세션)는 텔레그램 토큰·채팅 ID 를 갖고 있지 않다(GitHub 시크릿 `TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID` 에만 있고 채팅·저장소에 쓰지 않는다). 그래서 **텔레그램을 보낼 수 있는 것은 그 시크릿을 쓰는 워크플로뿐**이고, AI 가 일으킬 수 있는 이벤트는 `git push`(와 정기 실행을 기다리는 것)뿐이다.

**검증됨(2026-10-28 08:00 KST)**: 임시 브랜치 `ai/claude/tg-note-58`(저장소 원격에 남아 있음, **main 에 병합하지 않음**)에 `.github/workflows/tg-note.yml`(`on: push: branches: ['ai/claude/tg-note-**']`, 시크릿은 단계 env)과 `tg_note/send.py`(pipeline.notify.Notifier 로 전송)·메모 파일을 푸시 → 실행 #1 success, 주석 "텔레그램 메모를 보냈습니다"(= Result.sent True: HTTP 200·ok). 즉 비-main 푸시 워크플로가 시크릿을 쓰고 GitHub 러너가 api.telegram.org 에 닿고 토큰·채팅 ID 가 유효하다. 휴대폰 화면에 떴는지는 AI 가 볼 수 없다(서버 성공 응답까지만).

**정식 경로 검증됨(2026-10-28)**: 묶음 3(PR #57, main fda90c6, 16:58 병합)으로 `[공통] AI 요청 텔레그램 알림`(`ai-request.yml`)이 main 에 들어왔다. 병합 전 묶음 푸시(15:56)로 R-001~R-003 이, 병합 뒤 `ai/claude/r004-merge-report` 푸시(17:06)로 R-004(알림)가 성공 실행됐다(요청 알림 단계에 경고 주석 없음 = 전송 실패 없음; 성공 때는 주석이 따로 없고 로그에만 남아 AI 가 개수를 못 읽는다). 임시 `tg-note-*` 브랜치 셋은 지웠고(PR #60 도 함께 닫힘) 앞으로는 요청 파일을 쓴다. 운영자가 병합까지 걸린 시간은 푸시 후 약 1시간(재안내 메모 16:50 뒤 8분) — 급하면 푸시 55분쯤에 한 번 재안내한다.

**How to apply:** ① 정식 경로(작업 H, 병합 뒤): `인수인계/요청함/R-nnn_<슬러그>.md` 를 `ai/claude/**` 브랜치에 푸시하면 `[공통] AI 요청 텔레그램 알림` 이 보내고, 운영자는 이슈 양식 `[답변]`·`[요청]` 으로 답한다(작성자 OWNER + 요청 번호 일치만 인정) — 접수 확인 코멘트·텔레그램이 돌아온다. ② 그 전·급할 때는 임시 방식: `ai/claude/tg-note-<이름>` 새 브랜치(origin/main 에서) + `tg-note.yml` 의 메모 파일 인자 + `tg_note/<메모>.txt`(`# 제목`·`## 소제목` 굵게, `[버튼] 라벨 | 주소`)를 푸시하고 `poll_branch_run.py` 같은 공개 REST 로 실행·주석 확인. 새 브랜치마다 저장소 첫 화면에 "Compare & pull request" 배너가 뜨니 메모에 "PR 만들지 않아도 됩니다"를 적는다(만들면 PR 검사가 빨강 — 2026-10-28 12:45 에 PR #60 이 실제로 그렇게 만들어졌다). 운영자는 2026-10-28 부터 텔레그램 요청 외 GitHub 알림을 무시하기로 했으므로([[operator-telegram-requests-only]]) 임시 브랜치(`tg-note-*`)는 쓴 뒤 AI 가 지운다(병합 안 된 것만; 지우면 그 PR 도 닫힌다). ③ 메시지는 `pipeline/notify.py` 규칙(소독·허용 주소 github.com/shine88pc/chanceblog·3,800자·한 실행 5통)을 지키고 외부 글을 그대로 싣지 않는다. ④ **채팅에서 사용자가 "내용을 메세지로 보내줘"라고 하면(2026-11-02, R-048 브리핑)** = `kind: info` 요청 파일로 보낸다: 텔레그램에는 `title`(≤80자)·`summary`(≤300자 한 줄)·버튼(요청 열기 등)만 가고 **본문은 실리지 않는다**(요청 열기 버튼으로 연 파일에만 있음) → summary 에 핵심 요지를 꽉 채우고 본문에 전체 내용을 둔다. 한 푸시 알림 3통까지. 전체 본문을 텔레그램에 직접 싣는 길(옛 tg-note 식 워크플로)은 시크릿을 쓰는 새 워크플로라 만들지 않는다(필요하면 승인 요청). 관련: [[quiet-mode-defaults]], [[pr-flow-github-blocked]]
