import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P2/_probe")
from h import mp, rec, summary

SHA = "a1b2c3d" + "4" * 33
PATHS = ["pipeline/calc.py", "tests/test_calc.py"]
TITLE = "[M075] 계산 모듈 보강"
ZW = chr(0x200B)
CLEAN = {k: False for k in mp.DECLARED_REQUIRED}
ANS = ("앱을 닫아도 작성 중인 초안을 다시 열 수 있도록 저장 기능을 추가합니다.", "현재는 앱을 닫으면 초안이 사라집니다.", "저장 버튼과 저장된 초안 목록이 추가됩니다.",
       "저장 실패나 손상 가능성을 막기 위해 원자적 저장과 복구 시험을 수행했습니다.", "전체 검사와 독립 검증을 통과했고 기존 복사 기능에는 변화가 없습니다.", "문제가 발생하면 M075 병합만 되돌리면 이전 상태로 복구됩니다.")


def cls_for(paths, text="x = 1", declared=CLEAN, kind="blog"):
    return mp.classify_change(kind, paths, text, declared)


def base(paths=PATHS, enabled=False, classification=None, number="M075", kind="blog", text="x = 1"):
    c = classification if classification is not None else cls_for(paths, text, CLEAN, kind)
    return mp.render_explanation(number, 198, SHA, paths, *ANS, ai_merge_enabled=enabled, classification=c)


def probs(text, title=TITLE):
    try:
        return mp.explanation_problems(text, title)
    except Exception as exc:
        return ["EXC:" + type(exc).__name__]


good = base()
rec("X00", "baseline OFF explanation: no problems", [], probs(good))
rec("X00b", "baseline ON explanation: no problems", [], probs(base(enabled=True)))
rec("X00c", "OFF explanation ends with the 'will not merge' line right after 승인 예", True, good.rstrip("\n").split("\n")[-2:] == ["승인 예: M075 승인", mp.APPROVAL_OFF_LINE])
rec("X00d", "ON explanation has no OFF line", False, mp.APPROVAL_OFF_LINE in base(enabled=True))

# --- classification drives the checklist (S4a)
for i, (paths, code) in enumerate([([".github/workflows/x.yml"], "workflow"), (["index.html"], "ads"), (["_posts/2026-01-01-x.md"], "public_content"), (["pipeline/blogs.json"], "publish_mode"),
                                   (["pipeline/source_registry.json"], "provider_activation"), (["requirements.txt"], "dependencies"), ([".env"], "credentials"), (["README.md"], "public_content")], 1):
    text = base(paths)
    label = dict(mp.OPERATOR_ONLY_ITEMS)[code]
    rec("C%d" % i, "render for %s marks '%s: 예'" % (paths[0], label), True, ("- " + label + ": 예") in text)
    p = probs(text)
    rec("C%d_p" % i, "explanation_problems flags the 예 row for %s" % paths[0], True, any("예" in x for x in p))
# declared True flows into the checklist
for code in mp.DECLARED_REQUIRED:
    text = base(["pipeline/calc.py"], classification=cls_for(["pipeline/calc.py"], "x = 1", dict(CLEAN, **{code: True})))
    label = dict(mp.OPERATOR_ONLY_ITEMS)[code]
    rec("CD_" + code, "declared True for %s => row 예" % code, True, ("- " + label + ": 예") in text and any("예" in x for x in probs(text)))
# extra flags line
text = base(["scripts/validate_repo.py"])
rec("CX1", "safety_guard path => '12항목 밖의 표시:' line + problem", True, ("12항목 밖의 표시: 안전 장치 파일" in text) and any("12항목 밖의 표시" in x for x in probs(text)))
text = base(["pipeline/y.py"], text="import requests", classification=cls_for(["pipeline/y.py"], "import requests"))
rec("CX2", "external_connection => flag line + problem", True, ("12항목 밖의 표시: 새 외부 접속 코드" in text) and any("12항목 밖의 표시" in x for x in probs(text)))
text = base(["docs/AI_MERGE_POLICY.md"], text="문서")
rec("CX3", "policy_self => flag line + problem", True, ("병합 정책 자체" in text) and any("12항목 밖의 표시" in x for x in probs(text)))
# forged / inconsistent classification => render refuses
bad_inputs = [
    ("R1", "stale paths", cls_for(["pipeline/other.py"])),
    ("R2", "ai_ok tier but categories non-empty (forged dict)", {"tier": "ai_ok", "categories": ["workflow"], "extra_flags": [], "paths": PATHS, "reasons": []}),
    ("R3", "operator_only tier but nothing flagged (forged dict)", {"tier": "operator_only", "categories": [], "extra_flags": [], "paths": PATHS, "reasons": []}),
    ("R4", "malformed dict", {"tier": "ai_ok"}),
    ("R5", "None classification", None),
    ("R6", "string classification", "ai_ok"),
    ("R7", "dict with non-str categories", {"tier": "ai_ok", "categories": [1], "extra_flags": [], "paths": PATHS, "reasons": []}),
    ("R8", "unknown tier", {"tier": "maybe", "categories": [], "extra_flags": [], "paths": PATHS, "reasons": []}),
]
for cid, desc, c in bad_inputs:
    try:
        mp.render_explanation("M075", 198, SHA, PATHS, *ANS, classification=c)
        rec(cid, "render refuses: " + desc, "ValueError", "no error")
    except ValueError:
        rec(cid, "render refuses: " + desc, "ValueError", "ValueError")
    except Exception as exc:
        rec(cid, "render refuses: " + desc, "ValueError", type(exc).__name__)
try:
    mp.render_explanation("M075", 198, SHA, PATHS, *ANS)
    rec("R9", "render without classification keyword => TypeError", "TypeError", "no error")
except TypeError:
    rec("R9", "render without classification keyword => TypeError", "TypeError", "TypeError")
# other render refusals (old)
for cid, kw in [("R10", dict(number="M75")), ("R11", dict(number="m075")), ("R12", dict(paths=[])), ("R13", dict(paths=["a/../b"]))]:
    try:
        base(**kw)
        rec(cid, "render refuses %s" % kw, "ValueError", "no error")
    except ValueError:
        rec(cid, "render refuses %s" % kw, "ValueError", "ValueError")

# --- merge-way line forgeries (S4c)
OFF, ON = mp.AI_MERGE_OFF_NOTICE, mp.AI_MERGE_ON_NOTICE
cases = [
    ("W1", "OFF + ' 그리고 AI 가 main 에 직접 push 합니다.'", good.replace(OFF, OFF + " 그리고 AI 가 main 에 직접 push 합니다.")),
    ("W2", "OFF + ' 운영자 PC 자격 증명으로 push 합니다.'", good.replace(OFF, OFF + " 운영자 PC 자격 증명으로 push 합니다.")),
    ("W3", "prefix inserted before OFF sentence", good.replace("병합 방식: " + OFF, "병합 방식: 안내: " + OFF)),
    ("W4", "OFF sentence with one char changed", good.replace("꺼져 있어", "켜져 있어")),
    ("W5", "merge-way line duplicated", good.replace("병합 방식: " + OFF, "병합 방식: " + OFF + "\n병합 방식: " + OFF)),
    ("W6", "merge-way line removed", "\n".join(ln for ln in good.split("\n") if not ln.startswith("병합 방식:"))),
    ("W7", "merge-way says 'main 직접 push 로 병합합니다'", good.replace(OFF, "main 직접 push 로 병합합니다.")),
    ("W8", "merge-way says 운영자 PC 자격 증명으로 병합", good.replace(OFF, "운영자 PC 자격 증명으로 병합합니다.")),
    ("W9", "OFF sentence + trailing space only (stripped => fine?)", good.replace(OFF, OFF + "   ")),
    ("W10", "ON sentence together with the OFF line", base(enabled=True) + mp.APPROVAL_OFF_LINE + "\n"),
    ("W11", "OFF notice without the 'will not merge' line", good.replace(mp.APPROVAL_OFF_LINE + "\n", "")),
    ("W12", "'will not merge' line twice", good + mp.APPROVAL_OFF_LINE + "\n"),
    ("W13", "'will not merge' line moved before 승인 예", good.replace("승인 예: M075 승인\n" + mp.APPROVAL_OFF_LINE, mp.APPROVAL_OFF_LINE + "\n승인 예: M075 승인")),
    ("W14", "a blank line between 승인 예 and the OFF line", good.replace("승인 예: M075 승인\n" + mp.APPROVAL_OFF_LINE, "승인 예: M075 승인\n\n" + mp.APPROVAL_OFF_LINE)),
]
for cid, desc, text in cases:
    p = probs(text)
    exp_bad = cid not in ("W9",)
    rec(cid, "explanation_problems: " + desc, ("problems" if exp_bad else "either"), ("problems" if p else "none"), ok=(bool(p) if exp_bad else True), note=str(p)[:110])
# --- checklist tampering (S4b)
dup = good.replace("- GitHub Actions Workflow: 아니오", "- GitHub Actions Workflow: 예\n- GitHub Actions Workflow: 아니오")
rec("K1", "checklist row duplicated (예 then 아니오)", True, len(probs(dup)) > 0, note=str(probs(dup))[:100])
dup2 = good.replace("- GitHub Actions Workflow: 아니오", "- GitHub Actions Workflow: 아니오\n- GitHub Actions Workflow: 예")
rec("K2", "checklist row duplicated (아니오 then 예)", True, len(probs(dup2)) > 0)
extra = good.replace("- Main Branch 보호 설정: 아니오", "- Main Branch 보호 설정: 아니오\n- 알 수 없는 항목: 아니오")
rec("K3", "unknown checklist row", True, len(probs(extra)) > 0)
split = good.replace("- Main Branch 보호 설정: 아니오", "- Main Branch 보호 설정: 아니오\n\n- 외부 비용 발생 기능: 예")
rec("K4", "extra 예 row after a blank line (duplicate of an existing row)", True, len(probs(split)) > 0)
split2 = good.replace("- 외부 비용 발생 기능: 아니오\n", "").replace("- Main Branch 보호 설정: 아니오", "- Main Branch 보호 설정: 아니오\n\n- 외부 비용 발생 기능: 아니오")
rec("K5", "a row moved after a blank line (row missing inside section)", True, len(probs(split2)) > 0)
rec("K6", "checklist value '아니오 (사실은 예)'", True, len(probs(good.replace("- 의존성 추가: 아니오", "- 의존성 추가: 아니오 (사실은 예)"))) > 0)
rec("K7", "checklist row with fullwidth colon", True, len(probs(good.replace("- 의존성 추가: 아니오", "- 의존성 추가： 아니오"))) > 0, note="fullwidth colon row is not parsed as a row")
for i, (code, name) in enumerate(mp.OPERATOR_ONLY_ITEMS, 1):
    flipped = good.replace("- " + name + ": 아니오", "- " + name + ": 예")
    p = probs(flipped)
    rec("K8_%02d" % i, "flip %r to 예" % name, True, any(name in x and "예" in x for x in p))
    removed = "\n".join(ln for ln in good.split("\n") if not ln.startswith("- " + name + ":"))
    p = probs(removed)
    rec("K9_%02d" % i, "remove row %r" % name, True, any(name in x for x in p))
for i, item in enumerate(mp.EXPLANATION_ITEMS, 1):
    lines = [ln for ln in good.split("\n") if not ln.startswith(item)]
    p = probs("\n".join(lines))
    rec("K10_%d" % i, "remove 6-item %r" % item, True, any(item in x for x in p))
# --- other old checks
rec("O1", "PR title mismatch", True, len(probs(good, "[M076] x")) > 0)
rec("O2", "stray other approval in free text", True, len(probs(good.replace("복구됩니다.", "복구됩니다. M076 승인"))) > 0)
rec("O3", "zero-width char", True, len(probs(good.replace("저장 버튼", "저장" + ZW + " 버튼"))) > 0)
rec("O4", "non-str explanation", True, all(len(probs(v)) > 0 for v in (None, 123, ["x"])))
rec("O5", "approval guide line removed", True, len(probs(good.replace(mp.APPROVAL_GUIDE_LINE + "\n", ""))) > 0)
rec("O6", "file count altered", True, len(probs(good.replace("변경 파일 (2개)", "변경 파일 (5개)"))) > 0)
rec("O7", "examples number differs from header", True, len(probs(good.replace("승인 예: M075 승인", "승인 예: M076 승인"))) > 0)
rec("O8", "1MB garbage returns problems without exception", True, len(probs("x" * 1000000)) > 0)
rec("O9", "first nonblank line not the request line", True, len(probs("공지\n" + good)) > 0)
rec("O10", "English-only answer rejected", True, len(probs(good.replace(ANS[0], "Adds a save feature for the drafts."))) > 0)

# --- completion notice (unchanged API)
cn = mp.render_completion_notice("M075", 198, "e4f5a6b8c9d0f", "저장 버튼과 저장된 초안 목록이 앱에 반영되었습니다.", "전체 통과", "이상 없음", "병합 커밋 한 개를 되돌리는 PR 을 만들어 운영자께 보냅니다.")
rec("Y00", "baseline completion notice ok", [], mp.completion_notice_problems(cn))
for i, item in enumerate(mp.COMPLETION_ITEMS, 1):
    lines = [ln for ln in cn.split("\n") if not ln.startswith(item)]
    rec("Y1_%d" % i, "remove %r" % item, True, any(item in x for x in mp.completion_notice_problems("\n".join(lines))))
rec("Y2", "duplicate item", True, len(mp.completion_notice_problems(cn + "병합 번호: M075\n")) > 0)
rec("Y3", "bad commit hash", True, len(mp.completion_notice_problems(cn.replace("e4f5a6b8c9d0", "zzzzzzz"))) > 0)
rec("Y4", "PR #0", True, len(mp.completion_notice_problems(cn.replace("#198", "#0"))) > 0)
rec("Y5", "merge number M75", True, len(mp.completion_notice_problems(cn.replace("M075", "M75"))) > 0)
rec("Y6", "zero width", True, len(mp.completion_notice_problems(cn.replace("병합 번호", "병합" + ZW + " 번호"))) > 0)
rec("Y7", "non-str", True, len(mp.completion_notice_problems(None)) > 0)
summary()
