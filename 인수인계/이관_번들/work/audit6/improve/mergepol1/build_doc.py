"""doc_draft.md 의 자리표시자를 모듈이 만든 글로 바꿔 docs/AI_MERGE_POLICY.md 를 만든다(UTF-8, LF). 사용: build_doc.py"""
import sys

sys.path.insert(0, "C:/work/ai/improve_wt_mergepol1")
from pipeline import merge_policy as mp

DRAFT = "C:/work/ai/audit6/improve/mergepol1/doc_draft.md"
TARGET = "C:/work/ai/improve_wt_mergepol1/docs/AI_MERGE_POLICY.md"

ANSWERS = ("앱을 닫아도 작성 중인 초안을 다시 열 수 있도록 저장 기능을 추가합니다.", "현재는 앱을 닫으면 초안이 사라집니다.", "저장 버튼과 저장된 초안 목록이 추가됩니다.",
           "저장 실패나 손상 가능성을 막기 위해 원자적 저장과 복구 시험을 수행했습니다.", "전체 검사와 독립 검증을 통과했고 기존 복사 기능에는 변화가 없습니다.",
           "문제가 발생하면 M075 병합만 되돌리면 이전 상태로 복구됩니다.")
PATHS = ["src/chanceblog_desktop/content/drafts_store.py", "tests/test_drafts_store.py"]
classification = mp.classify_change("desktop", PATHS, "", dict.fromkeys(mp.DECLARED_REQUIRED, False))
assert classification.tier == "ai_ok", classification
explanation = mp.render_explanation("M075", 198, "a1b2c3d" + "0" * 33, PATHS, *ANSWERS, classification=classification)
notice = mp.render_completion_notice("M075", 198, "e4f5a6b8c9d0e1f2a3b4c5d6e7f8091a2b3c4d5e", "저장 버튼과 저장된 초안 목록이 앱에 반영되었습니다.", "전체 통과", "이상 없음",
                                     "병합 커밋 한 개를 되돌리는 PR 을 만들어 운영자께 보냅니다.")
assert mp.explanation_problems(explanation, pr_title="[M075] 초안 저장 기능") == []
assert mp.completion_notice_problems(notice) == []

text = open(DRAFT, encoding="utf-8").read()
assert text.count("@@EXPLANATION@@") == 1 and text.count("@@NOTICE@@") == 1
text = text.replace("@@EXPLANATION@@", explanation).replace("@@NOTICE@@", notice)
open(TARGET, "w", encoding="utf-8", newline="\n").write(text)
print("written", TARGET, len(text), "chars", text.count("\n"), "lines")
