import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P/_probe")
from h import mp, rec, summary

SHA = "a1b2c3d" + "4" * 33
PATHS = ["src/chanceblog_desktop/content/drafts_store.py", "tests/test_drafts_store.py"]
TITLE = "[M075] 앱 초안 저장 기능"
ZW = chr(0x200B)


def base(number="M075", paths=PATHS, enabled=False, checklist=None):
    return mp.render_explanation(
        number, 198, SHA, paths,
        "앱을 닫아도 작성 중인 초안을 다시 열 수 있도록 저장 기능을 추가합니다.",
        "현재는 앱을 닫으면 초안이 사라집니다.",
        "저장 버튼과 저장된 초안 목록이 추가됩니다.",
        "저장 실패나 손상 가능성을 막기 위해 원자적 저장과 복구 시험을 수행했습니다.",
        "전체 검사와 독립 검증을 통과했고 기존 복사 기능에는 변화가 없습니다.",
        "문제가 발생하면 M075 병합만 되돌리면 이전 상태로 복구됩니다.",
        ai_merge_enabled=enabled, checklist=checklist)


def probs(text, title=TITLE):
    try:
        return mp.explanation_problems(text, title)
    except Exception as exc:
        return ["EXC:" + type(exc).__name__]


good = base()
rec("X00", "baseline rendered explanation has no problems", [], probs(good))
rec("X00b", "baseline enabled-form has no problems", [], probs(base(enabled=True)))

# six items removed one by one
for i, item in enumerate(mp.EXPLANATION_ITEMS, 1):
    lines = [ln for ln in good.split("\n") if not ln.startswith(item)]
    p = probs("\n".join(lines))
    rec("X01_%d" % i, "remove item %r" % item, True, any(item in x for x in p), note=str(p)[:100])

# checklist rows flipped to yes / removed
for i, (code, name) in enumerate(mp.OPERATOR_ONLY_ITEMS, 1):
    flipped = good.replace("- " + name + ": 아니오", "- " + name + ": 예")
    p = probs(flipped)
    rec("X02_%02d" % i, "flip checklist %r to 예" % name, True, any("예" in x for x in p) and any(name in x for x in p), note=str(p)[:100])
    lines = [ln for ln in good.split("\n") if not ln.startswith("- " + name + ":")]
    p = probs("\n".join(lines))
    rec("X03_%02d" % i, "remove checklist row %r" % name, True, any(name in x for x in p), note=str(p)[:100])

rec("X04", "header number != approval example", True, any("다릅니다" in x for x in probs(good.replace("승인 예: M075 승인", "승인 예: M076 승인"))))
rec("X05", "PR title label mismatch", True, len(probs(good, "[M076] x")) > 0)
rec("X05b", "PR title without label", True, len(probs(good, "no label here")) > 0)
rec("X06", "stray other-number approval phrase in free text", True, len(probs(good.replace("복구됩니다.", "복구됩니다. M076 승인"))) > 0)
rec("X07", "zero-width char inside", True, len(probs(good.replace("저장 버튼", "저장" + ZW + " 버튼"))) > 0)
rec("X08", "approval guide line removed", True, len(probs(good.replace(mp.APPROVAL_GUIDE_LINE + "\n", ""))) > 0)
rec("X09", "item line duplicated", True, len(probs(good.replace("왜 필요한가요?", "왜 필요한가요? 현재는 앱을 닫으면 초안이 사라집니다.\n왜 필요한가요?", 1))) > 0)
rec("X10", "file count altered", True, len(probs(good.replace("변경 파일 (2개)", "변경 파일 (5개)"))) > 0)
rec("X11", "PR line duplicated", True, len(probs(good.replace("대상 PR: #198", "대상 PR: #198\n대상 PR: #1"))) > 0)
rec("X12", "merge-way line removed", True, len(probs("\n".join(ln for ln in good.split("\n") if not ln.startswith("병합 방식:")))) > 0)
rec("X13", "merge-way line = OFF notice + extra 'main 에 직접 push 합니다' (substring check; info)", True,
    len(probs(good.replace(mp.AI_MERGE_OFF_NOTICE, mp.AI_MERGE_OFF_NOTICE + " 그리고 AI 가 main 에 직접 push 합니다."))) > 0, note="INFO")
# duplicate checklist rows: first says 예, second says 아니오
dup = good.replace("- GitHub Actions Workflow: 아니오", "- GitHub Actions Workflow: 예\n- GitHub Actions Workflow: 아니오")
rec("X14", "checklist row duplicated with conflicting values (예 then 아니오)", True, len(probs(dup)) > 0, note="last-wins dict hides the 예 row")
extra = good.replace("- Main Branch 보호 설정: 아니오", "- Main Branch 보호 설정: 아니오\n- 알 수 없는 항목: 아니오")
rec("X15", "extra unknown checklist row 'foo: 아니오' (info)", True, len(probs(extra)) > 0, note="INFO")
rec("X16", "checklist value '아니오 (사실은 예)'", True, len(probs(good.replace("- 의존성 추가: 아니오", "- 의존성 추가: 아니오 (사실은 예)"))) > 0)
# blank line splitting the checklist, then a 예 row after the break
split = good.replace("- Main Branch 보호 설정: 아니오", "- Main Branch 보호 설정: 아니오\n\n- 외부 비용 발생 기능: 예")
rec("X17", "blank line then extra 예 row after checklist break", True, len(probs(split)) > 0, note="rows after a blank line are not read")
rec("X18", "non-str explanation", True, len(probs(None)) > 0 and len(probs(123)) > 0 and len(probs(["x"])) > 0)
rec("X19", "all-English answers rejected (hangul needed)", True, len(probs(good.replace("앱을 닫아도 작성 중인 초안을 다시 열 수 있도록 저장 기능을 추가합니다.", "Adds a save feature for the drafts."))) > 0)
oneline = good.replace("\n왜 필요한가요?", " 왜 필요한가요?", 1)
rec("X21", "two items on one line", True, len(probs(oneline)) > 0)
rec("X22", "first nonblank line is not the request line", True, len(probs("공지\n" + good)) > 0)
rec("X23", "items quoted with > prefix", True, len(probs(good.replace("무엇을 바꾸나요?", "> 무엇을 바꾸나요?"))) > 0)
rec("X24", "empty string", True, len(probs("")) > 0)
rec("X25", "very long (1MB) garbage no exception/time", True, len(probs("x" * 1000000)) > 0)

# render with .github path: checklist default 아니오 even though path is a workflow (info)
bad_render = base(paths=[".github/workflows/x.yml"])
rec("X30", "render_explanation for a .github path still prints 'GitHub Actions Workflow: 아니오' and passes explanation_problems (misleading to operator)", True,
    ("- GitHub Actions Workflow: 예" in bad_render) or len(probs(bad_render)) > 0, note="SHOULD: checklist default does not follow classify_change")
# render with ads path
bad_render2 = base(paths=["index.html", "_layouts/default.html"])
rec("X31", "render_explanation for ad-surface paths prints '광고·AdSense·ads.txt: 아니오' and passes (misleading)", True,
    ("- 광고·AdSense·ads.txt: 예" in bad_render2) or len(probs(bad_render2)) > 0, note="SHOULD")
# render refusals
for cid, kwargs in [("X40", dict(number="M75")), ("X41", dict(number="m075")), ("X42", dict(paths=[])), ("X43", dict(paths=["a/../b"]))]:
    try:
        base(**kwargs)
        rec(cid, "render_explanation(%s) refused" % kwargs, "ValueError", "no error")
    except ValueError:
        rec(cid, "render_explanation(%s) refused" % kwargs, "ValueError", "ValueError")

# ---- completion notice
cn = mp.render_completion_notice("M075", 198, "e4f5a6b8c9d0f", "저장 버튼과 저장된 초안 목록이 앱에 반영되었습니다.", "전체 통과", "이상 없음", "병합 커밋 한 개를 되돌리는 PR 을 만들어 운영자께 보냅니다.")
rec("Y00", "baseline completion notice ok", [], mp.completion_notice_problems(cn))
for i, item in enumerate(mp.COMPLETION_ITEMS, 1):
    lines = [ln for ln in cn.split("\n") if not ln.startswith(item)]
    p = mp.completion_notice_problems("\n".join(lines))
    rec("Y01_%d" % i, "remove %r" % item, True, any(item in x for x in p), note=str(p)[:80])
rec("Y02", "duplicate item", True, len(mp.completion_notice_problems(cn + "병합 번호: M075\n")) > 0)
rec("Y03", "empty value", True, len(mp.completion_notice_problems(cn.replace("이상 유무: 이상 없음", "이상 유무:"))) > 0)
rec("Y04", "bad commit hash", True, len(mp.completion_notice_problems(cn.replace("e4f5a6b8c9d0", "zzzzzzz"))) > 0)
rec("Y05", "PR number #0", True, len(mp.completion_notice_problems(cn.replace("#198", "#0"))) > 0)
rec("Y06", "non-str", True, len(mp.completion_notice_problems(None)) > 0)
rec("Y07", "zero-width", True, len(mp.completion_notice_problems(cn.replace("병합 번호", "병합" + ZW + " 번호"))) > 0)
rec("Y08", "fullwidth colon accepted", [], mp.completion_notice_problems(cn.replace("병합 번호:", "병합 번호" + chr(0xFF1A))))
rec("Y09", "merge number M75", True, len(mp.completion_notice_problems(cn.replace("M075", "M75"))) > 0)
rec("Y10", "commit with 3 chars", True, len(mp.completion_notice_problems(cn.replace("e4f5a6b8c9d0", "e4f"))) > 0)
rec("Y11", "value '-' for 이상 유무 passes (info)", True, len(mp.completion_notice_problems(cn.replace("이상 없음", "-"))) > 0, note="INFO content unjudged")
rec("Y12", "contradiction main 검사 결과 실패 + 이상 없음 passes (info)", True, len(mp.completion_notice_problems(cn.replace("전체 통과", "실패"))) > 0, note="INFO content unjudged")
rec("Y13", "revert-commit item reading '없음' passes (info)", True, len(mp.completion_notice_problems(cn.replace("병합 커밋 한 개를 되돌리는 PR 을 만들어 운영자께 보냅니다.", "없음"))) > 0, note="INFO")
summary()
