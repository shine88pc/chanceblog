import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P2/_probe")
import re
import unicodedata
from h import mp, rec, summary

SRC = open("C:/work/ai/audit6/improve/mergepol1/operator_decision_016.md", encoding="utf-8").read().replace("\r\n", "\n").split("\n")


def bullets(first, last):
    """1-based inclusive line range -> list of '* item' texts."""
    out = []
    for ln in SRC[first - 1:last]:
        if ln.startswith("* "):
            out.append(ln[2:])
    return tuple(out)


phrases = bullets(28, 32)
conds = bullets(38, 45)
scopes = bullets(50, 56)
items12 = bullets(60, 71)
notice7 = bullets(81, 87)
trial6 = bullets(94, 99)

rec("V01", "operator 5 rejected phrases == REJECTED_PHRASES (byte-exact)", phrases, mp.REJECTED_PHRASES)
rec("V02", "operator 8 conditions == PRECONDITIONS labels", conds, tuple(n for _c, n in mp.PRECONDITIONS))
rec("V03", "operator 7 scopes == AI_MERGE_SCOPES", scopes, mp.AI_MERGE_SCOPES)
rec("V04", "operator 12 items == OPERATOR_ONLY_LABELS", items12, mp.OPERATOR_ONLY_LABELS)
rec("V05", "operator 7 completion items == COMPLETION_ITEMS", notice7, mp.COMPLETION_ITEMS)
rec("V06", "operator 6 trial criteria == TRIAL_CRITERIA labels", trial6, tuple(n for _k, n in mp.TRIAL_CRITERIA))
rec("V07", "counts 5/8/7/12/7/6", (5, 8, 7, 12, 7, 6), (len(phrases), len(conds), len(scopes), len(items12), len(notice7), len(trial6)))

# explanation items: operator example lines (18..23) begin with these labels
ex_lines = SRC[17:23]
labels = []
for ln in ex_lines:
    for lab in mp.EXPLANATION_ITEMS:
        if ln.startswith(lab):
            labels.append(lab)
rec("V08", "operator example's six labels in order == EXPLANATION_ITEMS", tuple(mp.EXPLANATION_ITEMS), tuple(labels))

# doc: all text pieces
DOC = open("C:/work/ai/verify_mp1_P2/docs/AI_MERGE_POLICY.md", encoding="utf-8").read().replace("\r\n", "\n")
for name, group in [("phrases", phrases), ("conds", conds), ("scopes", scopes), ("items12", items12), ("notice7", notice7), ("trial6", trial6)]:
    missing = [x for x in group if x not in DOC]
    rec("V09_" + name, "doc contains every operator %s literal" % name, [], missing)

# exact flow sentence
flow = SRC[75].strip()
rec("V10", "operator flow sentence appears verbatim in doc", True, flow in DOC, note=flow[:60])
mod_src = open("C:/work/ai/verify_mp1_P2/pipeline/merge_policy.py", encoding="utf-8").read()
rec("V11", "operator flow sentence appears verbatim in module docstring", True, flow in mod_src)

# explanation example from operator is reproduced in the doc example and the render output
op_example = [
    "무엇을 바꾸나요? 앱을 닫아도 작성 중인 초안을 다시 열 수 있도록 저장 기능을 추가합니다.",
    "왜 필요한가요? 현재는 앱을 닫으면 초안이 사라집니다.",
    "사용할 때 무엇이 달라지나요? 저장 버튼과 저장된 초안 목록이 추가됩니다.",
    "위험은 무엇인가요? 저장 실패나 손상 가능성을 막기 위해 원자적 저장과 복구 시험을 수행했습니다.",
    "검사 결과 전체 검사와 독립 검증을 통과했고 기존 복사 기능에는 변화가 없습니다.",
    "되돌리기 문제가 발생하면 M075 병합만 되돌리면 이전 상태로 복구됩니다.",
]
op_text = "\n".join(SRC)
for i, line in enumerate(op_example, 1):
    rec("V12_%d" % i, "operator example line %d is in operator file and doc" % i, (True, True), (line in op_text, line in DOC))

# suspicious characters in module constants/doc lines of lists (middle dot variants)
for ch in set("".join(mp.OPERATOR_ONLY_LABELS) + "".join(mp.AI_MERGE_SCOPES)):
    if ord(ch) > 127 and not (0xAC00 <= ord(ch) <= 0xD7A3):
        print("  non-hangul non-ascii char in constants: U+%04X %s" % (ord(ch), unicodedata.name(ch, "?")))

# approval guide and 승인 예
for line in ("승인 방식은 반드시 병합 번호와 함께 사용해 주세요.", "승인 예: M075 승인"):
    rec("V13", "operator line %r in operator file and in rendered explanation" % line, (True, True),
        (line in op_text, line in mp.render_explanation("M075", 1, "a" * 40, ["src/a.py"], "무엇을 바꾸나요 설명입니다", "왜 필요한가요 설명입니다", "달라지는 점입니다 설명", "위험은 작습니다 설명 문장", "검사를 통과했습니다 설명", "되돌리는 방법 설명 문장", classification=mp.classify_change("desktop", ["src/a.py"], "x = 1", {k: False for k in mp.DECLARED_REQUIRED}))))

# the notify standard regex equivalence (module says same value as pipeline.notify.NOTICE_NO_RE)
try:
    from pipeline import notify
    pat = notify.NOTICE_NO_RE.pattern if hasattr(notify, "NOTICE_NO_RE") else None
    print("  notify.NOTICE_NO_RE =", pat)
except Exception as exc:
    print("  notify import failed:", type(exc).__name__, exc)
summary()
