"""검증자 P 의 재현 입력(차이가 났던 것)을 새 코드에 다시 넣어 본다 — 읽기 전용."""
import sys

sys.path.insert(0, "C:/work/ai/improve_wt_mergepol1")
from pipeline import merge_policy as mp

D = dict.fromkeys(mp.DECLARED_REQUIRED, False)


def op(label, paths, text="", kind="blog"):
    result = mp.classify_change(kind, paths, text, D)
    flag = "OK " if result.tier == "operator_only" else "BAD"
    print(flag, label, result.categories, result.extra_flags)
    return result.tier == "operator_only"


ok = True
for label, paths, text in (
        ("H12 README.md", ["README.md"], ""), ("H13 CNAME", ["CNAME"], ""), ("H19 faq.md", ["faq.md"], ""), ("H20 info/faq.md", ["info/faq.md"], ""), ("H21 pages/terms.html", ["pages/terms.html"], ""),
        ("H22 ko/about.md", ["ko/about.md"], ""), ("H23 style.css", ["style.css"], ""), ("H24 sitemap.xml", ["sitemap.xml"], ""), ("H25 favicon.ico", ["favicon.ico"], ""),
        ("H26 .nojekyll", [".nojekyll"], ""), ("H27 humans.txt", ["humans.txt"], ""), ("H32 disclaimer.md", ["disclaimer.md"], ""), ("I03 requirements/base.txt", ["requirements/base.txt"], ""),
        ("I04 requirements.in", ["requirements.in"], ""), ("I23 environment.yml", ["environment.yml"], ""), ("J08 publishers/blogger.py", ["pipeline/publishers/blogger.py"], "draft = False"),
        ("J09 draft_flow PIPELINE_PAUSE removed", ["pipeline/draft_flow.py"], "if PIPELINE_PAUSE:\n    return\n"), ("K43 Authorization Bearer", ["pipeline/x.py"], 'h = {"Authorization": "Bearer " + v}'),
        ("K44 sk_live_", ["pipeline/x.py"], "k = 'sk_live_" + "CANARY" + "a" * 18 + "'"), ("L07 os.remove", ["pipeline/x.py"], "os.remove(path)"), ("L08 DROP COLUMN", ["pipeline/x.py"], "ALTER TABLE t DROP COLUMN c"),
        ("L09 rm -rf", ["scripts/x.sh"], "rm -rf data/"), ("L10 Path.unlink", ["pipeline/x.py"], "Path(x).unlink()"), ("L13 DROP INDEX", ["pipeline/x.py"], "DROP INDEX i"),
        ("O15 gates.py", ["pipeline/gates.py"], ""), ("O16 auth_check.py", ["pipeline/auth_check.py"], ""), ("P18 quoted evil.ru", ["pipeline/x.py"], "u = 'evil.ru'"),
        ("P20 protocol-relative", ["scripts/x.js"], 'src="//evil.com/x.js"'), ("P26 gopher", ["pipeline/x.py"], "u = '" + "gopher" + ":" + "//evil.org/x'"),
        ("P31 Invoke-WebRequest", ["scripts/x.ps1"], "Invoke-WebRequest -Uri $u"), ("Q13 paths dict", {"a": 1}, "x")):
    ok &= op(label, paths, text)

# 설명·승인 쪽
facts = {}
text = mp.render_explanation("M075", 198, "c" * 40, [".github/workflows/x.yml"], "내용을 바꿉니다 쉽게", "이유가 있습니다 쉽게", "달라지는 점입니다 쉽게", "위험은 작습니다 쉽게", "검사를 통과했습니다 쉽게", "되돌립니다 쉽게 합니다",
                             classification=mp.classify_change("blog", [".github/workflows/x.yml"], "", D))
print("X30:", "- GitHub Actions Workflow: 예" in text, bool(mp.explanation_problems(text)))
text = mp.render_explanation("M075", 198, "c" * 40, ["pipeline/a.py"], "내용을 바꿉니다 쉽게", "이유가 있습니다 쉽게", "달라지는 점입니다 쉽게", "위험은 작습니다 쉽게", "검사를 통과했습니다 쉽게", "되돌립니다 쉽게 합니다",
                             classification=mp.classify_change("blog", ["pipeline/a.py"], "", D))
off = mp.AI_MERGE_OFF_NOTICE
print("X13:", bool(mp.explanation_problems(text.replace(off, off + " 그리고 AI 가 main 에 직접 push 합니다."))))
dup = text.replace("- GitHub Actions Workflow: 아니오", "- GitHub Actions Workflow: 예\n- GitHub Actions Workflow: 아니오")
print("X14:", bool(mp.explanation_problems(dup)))
extra = text.replace("- Main Branch 보호 설정: 아니오", "- Main Branch 보호 설정: 아니오\n- 알 수 없는 항목: 아니오")
print("X15:", bool(mp.explanation_problems(extra)))
split = text.replace("- Main Branch 보호 설정: 아니오", "- Main Branch 보호 설정: 아니오\n\n- 외부 비용 발생 기능: 예")
print("X17:", bool(mp.explanation_problems(split)))


class Evil(str):
    def __eq__(self, other):
        return True

    def strip(self, *args):
        return "M075 승인"


print("A102:", mp.parse_approval(Evil("확인했습니다")), mp.check_approval_text(Evil("x")).reason)
print("E30:", mp.merge_method_allowed(Evil("push_main")))
print("ALL OPERATOR-ONLY:", ok)
