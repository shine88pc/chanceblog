p = "C:/work/ai/audit6/improve/mergepol1/doc_draft.md"
t = open(p, encoding="utf-8", newline="").read()


def rep(old, new, count=1):
    global t
    assert t.count(old) == count, (t.count(old), old[:100])
    t = t.replace(old, new)


# ---- I-N7: 켜진 뒤의 동작이라는 한 줄(§6·§8·§9·§10)
rep("## 6. 병합 직전 재확인 8조건\n\n", "## 6. 병합 직전 재확인 8조건\n\n이 절은 켜진 뒤의 동작이며 지금은 꺼져 있습니다.\n\n")
rep("## 8. 병합 방식 제한\n\n", "## 8. 병합 방식 제한\n\n이 절은 켜진 뒤의 동작이며 지금은 꺼져 있습니다. 다만 main 에 직접 push 하지 않는다는 원칙은 꺼져 있는 지금도 그대로입니다.\n\n")
rep("## 9. 사후 처리\n\n", "## 9. 사후 처리\n\n이 절은 켜진 뒤의 동작이며 지금은 꺼져 있습니다.\n\n")
rep("## 10. 첫 운영 3건 시험과 즉시 중지\n\n", "## 10. 첫 운영 3건 시험과 즉시 중지\n\n이 절은 켜진 뒤의 동작이며 지금은 꺼져 있습니다.\n\n")

# ---- S-N3: §6 의 과장 고치기
rep("다시 계산할 수 없는 값(선언 6항목)을 빼고는 넘겨받은 값을 믿지 않고 이 함수가 다시 확인합니다.",
    "이 함수가 스스로 다시 계산하는 것은 변경 분류와 머리 커밋 일치뿐이고 나머지 값은 모양만 확인합니다 — 그래서 값은 GitHub 에서 직접 읽는 신뢰할 수 있는 워크플로가 만든 것이어야 합니다(§11-3).")

# ---- I-N1: §7-2 8번 행
rep("`requirements*.txt`·`requirements*.in`·`requirements/`·`constraints*`·`vendor/`·`node_modules/`·",
    "`requirements*.txt`·`requirements*.in`(이름 안에 `requirements` 가 든 `dev-requirements.txt`·`pip-requirements.in` 도)·`deps.txt`(이름에 `deps`·`dependencies` 가 든 `.txt`·`.in` 파일)·`Dockerfile`·`Makefile`(이름 안에 있기만 하면)·`requirements/`·`constraints*`·`vendor/`·`node_modules/`·")

# ---- N-M1·S-N2: §7-2 아래 단락
rep("`normalize_repo_path` 가 경로를 `/` 로 통일합니다. 이름 바꾸기는 옛 경로와 새 경로를 모두, 삭제도 변경 파일에 넣어 분류합니다. `..` 구간이 든 경로·절대 경로·제어 문자(DEL 포함)가 든 경로·글자가 아닌 입력·**사전을 경로 목록으로 넘긴 입력**은 확인할 수 없는 입력이라 운영자 전용입니다.",
    "`normalize_repo_path` 가 경로를 `/` 로 통일합니다(줄 끝의 줄 바꿈만 떼고 경로 자체는 다듬지 않습니다). 이름 바꾸기는 옛 경로와 새 경로를 모두, 삭제도 변경 파일에 넣어 분류합니다. `..` 구간이 든 경로·절대 경로·**어느 구간이든 앞뒤에 공백(유니코드 공백 포함)이 있는 경로**·제어 문자(DEL·C1 포함)가 든 경로·글자가 아닌 입력·사전을 경로 목록으로 넘긴 입력은 확인할 수 없는 입력이라 운영자 전용입니다. 맨 앞의 공백 한 칸이 `docs` 같은 내부 폴더 이름처럼 보이게 하던 우회를 이렇게 막습니다.")
rep("경로마다 나눠 넘기는 사전의 키는 모두 변경 파일 목록에 있어야 하고, 없으면 입력 오류입니다(시험·문서 면제를 흉내 낼 수 없게).",
    "경로마다 나눠 넘기는 사전은 **키가 모두 변경 파일 목록에 있어야 하고 변경 파일마다 키가 있어야** 합니다. 글이 없는 파일은 빈 글을 넣고, 어긋나면 입력 오류입니다(시험·문서 면제를 흉내 내거나 코드 파일의 바뀐 줄을 숨길 수 없게).")

# ---- S-N1: §7-6 목록
rep("발행기·생성기·토큰 발급·감시 도구와 사이트 정리 시험): ", "발행기·생성기·토큰 발급·감시 도구·발행 실행기·접수 판정과 사이트 정리 시험): ")
rep("`scripts/watchdog.py`·`tests/test_site_cleanup.py`, 그리고 폴더 `pipeline/publishers` 의 모든 파일.",
    "`scripts/watchdog.py`·`tests/test_site_cleanup.py`·`pipeline/run.py`·`pipeline/operator_loop.py`·`pipeline/telegram_inbox.py`, 그리고 폴더 `pipeline/publishers` 의 모든 파일.")
rep("- AI 가 읽고 따르는 규칙 문서 10개도 운영자 전용입니다: `AGENTS.md`·`CLAUDE.md`·`GEMINI.md`·`AI_COLLAB.md`·`HANDLER.md`·`docs/CHARTER.md`·`docs/SECURITY_GUARDRAILS.md`·`docs/ACTIONS_GUIDE.md`·`docs/AGENT_RUNBOOK.md`·`docs/SESSION_START.md`. 이 문서를 AI 가 스스로 고쳐 자기 규칙을 바꾸는 길을 막기 위해서입니다.",
    "- AI 가 읽고 따르는 규칙 문서 18개도 운영자 전용입니다: `AGENTS.md`·`CLAUDE.md`·`GEMINI.md`·`AI_COLLAB.md`·`HANDLER.md`·`docs/CHARTER.md`·`docs/SECURITY_GUARDRAILS.md`·`docs/ACTIONS_GUIDE.md`·`docs/AGENT_RUNBOOK.md`·`docs/SESSION_START.md`·`docs/ENGINEERING_GUIDE.md`·`docs/AGENT_DELEGATION.md`·`docs/COPILOT_GUIDE.md`·`docs/AI_FLOW.md`·`docs/AI_MODEL_GUIDE.md`·`docs/SOURCE_POLICY.md`·`docs/QUALITY_GATE.md`·`docs/REQUEST_BRIEFING.md`. 이 문서를 AI 가 스스로 고쳐 자기 규칙을 바꾸는 길을 막기 위해서입니다. 용어 사전(`docs/GLOSSARY.md`)은 규칙이 아니라 사전이라 넣지 않았습니다(§7-7).")

# ---- §7-7 알려진 한계 보강
rep("- 이름에 안전 낱말이 없고 §7-6 의 이름 목록에도 없는 검사·정화 코드는 걸리지 않습니다(예: 콘텐츠 안전 프로필 `pipeline/profiles/`). 목록에 넣을지는 운영자가 정합니다.",
    "- 이름에 안전 낱말이 없고 §7-6 의 이름 목록에도 없는 검사·정화 코드는 걸리지 않습니다(예: 콘텐츠 안전 프로필 `pipeline/profiles/`). 목록에 넣을지는 운영자가 정합니다.\n"
    "- **운영자 확인 대기 항목**: 용어 사전 `docs/GLOSSARY.md` 를 규칙 문서 목록에 넣을지, `pipeline/shadow_run.py`(그림자 실행)와 `pipeline/drafts.py`(초안 처리)를 안전 장치 목록에 넣을지는 정하지 않았습니다(`pipeline/drafts.py` 를 넣으면 초안만 다루는 일반 변경도 운영자 전용이 됩니다). 그래서 지금은 이 셋을 바꾸는 변경이 다른 규칙에 걸리지 않으면 AI 병합 대상입니다.")
rep("- 새 외부 접속은 파일에 적힌 모양만 봅니다. 문자열을 쪼개 붙이거나 다른 파일에서 가져오는 접속, 따옴표 없는 비정형 주소, 무작위 문자열 모양의 비밀은 못 잡습니다.",
    "- 새 외부 접속은 파일에 적힌 모양만 봅니다. 문자열을 쪼개 붙이거나 다른 파일에서 가져오는 접속, 따옴표 없는 비정형 주소, 이름 없는 무작위 문자열 모양의 비밀은 못 잡습니다. 셸 명령 중 `openssl s_client`·`socat`·`aria2c`·`npm publish`·`docker push`·`pip install` 같은 것도 따로 잡지 않습니다. 파일 이름과 겹치는 국가 도메인(`evil.sh` 등)은 스킴이 없으면 못 잡습니다.\n"
    "- 도메인 이름처럼 생긴 따옴표 글(`'row.id'`·`'obj.is'`·`'a.to'`·`'config.dev'`·`'pipeline.store'`)은 새 호스트로 읽혀 걸립니다 — 운영자 전용 쪽으로 틀리는 오류입니다.\n"
    "- 되돌리는 방법 칸의 '모름' 문구는 목록에 있는 문구와 **정확히 같을 때만** 거절합니다. 조금 바꿔 쓰면 열 자가 넘는 한 통과합니다.")

# ---- §11-3
rep("  - 바뀐 줄(`changed_text`)에는 **추가된 줄과 지운 줄을 둘 다** 넣습니다(지운 줄에 광고 코드나 `PIPELINE_PAUSE` 가 있을 수 있어서). 경로마다 나눠 넘기는 사전의 키는 모두 변경 파일 목록에 있어야 합니다.",
    "  - 바뀐 줄(`changed_text`)에는 **추가된 줄과 지운 줄을 둘 다** 넣습니다(지운 줄에 광고 코드나 `PIPELINE_PAUSE` 가 있을 수 있어서). 경로마다 나눠 넘기는 사전은 키가 모두 변경 파일 목록에 있어야 하고 변경 파일마다 키가 있어야 합니다(글이 없는 파일은 빈 글).")
rep("- 12항목 분류 결과가 지금 변경 파일 목록으로 계산되는지(분류는 병합 직전에 이 함수가 다시 계산합니다)\n",
    "- 12항목 분류 결과가 지금 변경 파일 목록으로 계산되는지(분류는 병합 직전에 이 함수가 다시 계산합니다)\n"
    "- **값의 출처**(켜기 전의 필수 조건): `repo_kind`·`changed_text`·`checks`·`required_checks`·`independent_verification`·`has_conflict`·`secret_findings`·`pr_state`·`pr_draft`·`previous_merge_main_check` 는 GitHub 에서 직접 읽는 신뢰할 수 있는 워크플로가 만든 값이어야 합니다. PR 작성자나 PR 쪽 파일이 채울 수 있으면 안 됩니다 — 이 함수는 이 값들의 모양만 확인하고 진짜인지는 알 수 없습니다.\n")
open(p, "w", encoding="utf-8", newline="").write(t)
print("ok")
