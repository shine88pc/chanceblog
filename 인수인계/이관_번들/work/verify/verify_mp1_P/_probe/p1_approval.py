import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P/_probe")
import time
from h import mp, rec, summary

ZW = chr(0x200B)
ZWNJ = chr(0x200C)
ZWJ = chr(0x200D)
WJ = chr(0x2060)
BOM = chr(0xFEFF)
RLO = chr(0x202E)
LRM = chr(0x200E)
NBSP = chr(0x00A0)
IDEO = chr(0x3000)
THIN = chr(0x2009)
VS16 = chr(0xFE0F)

import unicodedata

NFD_SEUNGIN = unicodedata.normalize("NFD", "승인")


class Evil(str):
    def strip(self, *a, **k):
        return "M075 승인"


CASES = [
    ("A01", "exact", "M075 승인", "M075"),
    ("A02", "lowercase m", "m075 승인", "M075"),
    ("A03", "no space", "M075승인", None),
    ("A04", "승인합니다", "M075 승인합니다", None),
    ("A05", "승인 취소", "M075 승인 취소", None),
    ("A06", "승인하지 않습니다", "M075 승인하지 않습니다", None),
    ("A07", "보류 M076 승인", "M075 보류 M076 승인", None),
    ("A08", "fullwidth digits", "M０７５ 승인".replace("\\uff10", ""), None),
    ("A09", "hanja 承認", "M075 承認", None),
    ("A10", "ZWSP between M and digits", "M" + ZW + "075 승인", None),
    ("A11", "ZWSP after number", "M075" + ZW + " 승인", None),
    ("A12", "ZWSP before 승인", "M075 " + ZW + "승인", None),
    ("A13", "ZWSP inside 승인", "M075 승" + ZW + "인", None),
    ("A14", "ZWSP at end", "M075 승인" + ZW, None),
    ("A15", "BOM at start", BOM + "M075 승인", None),
    ("A16", "RLO at start", RLO + "M075 승인", None),
    ("A17", "NBSP between", "M075" + NBSP + "승인", None),
    ("A18", "ideographic space between", "M075" + IDEO + "승인", None),
    ("A19", "blockquote >", "> M075 승인", None),
    ("A20", "inline code", "`M075 승인`", None),
    ("A21", "code block", "```\nM075 승인\n```", None),
    ("A22", "double-quoted", "\"M075 승인\"", None),
    ("A23", "M75 too few digits", "M75 승인", None),
    ("A24", "M0075 5 digits starting 0", "M0075 승인", None),
    ("A25", "M1000 4 digits valid", "M1000 승인", "M1000"),
    ("A26", "M10000 too many", "M10000 승인", None),
    ("A27", "M000", "M000 승인", None),
    ("A28", "two numbers before", "M075 M076 승인", None),
    ("A29", "two numbers after", "M075 승인 M076", None),
    ("A30", "two approval lines", "M075 승인\nM076 승인", None),
    ("A31", "승인 alone", "승인", None),
    ("A32", "승인합니다 alone", "승인합니다", None),
    ("A33", "reject phrase 확인했습니다", "확인했습니다", None),
    ("A34", "reject phrase 진행하세요", "진행하세요", None),
    ("A35", "reject phrase 좋아 보입니다", "좋아 보입니다", None),
    ("A36", "reject phrase 기본값대로", "기본값대로", None),
    ("A37", "reject phrase 다음 단계 진행", "다음 단계 진행", None),
    ("A38", "확인했습니다 + approval", "확인했습니다 M075 승인", None),
    ("A39", "approval + 확인했습니다", "M075 승인 확인했습니다", None),
    ("A40", "M075 진행하세요", "M075 진행하세요", None),
    ("A41", "M075 기본값대로", "M075 기본값대로", None),
    ("A42", "기본값대로 승인", "기본값대로 승인", None),
    ("A43", "좋아 보입니다. + approval", "좋아 보입니다. M075 승인", None),
    ("A44", "다음 단계 진행 + approval", "다음 단계 진행 M075 승인", None),
    ("A45", "surrounding spaces", "  M075 승인  ", "M075"),
    ("A46", "surrounding newlines", "\nM075 승인\n", "M075"),
    ("A47", "surrounding tabs", "\tM075 승인\t", "M075"),
    ("A48", "tab between", "M075\t승인", "M075"),
    ("A49", "two spaces between", "M075  승인", "M075"),
    ("A50", "trailing period", "M075 승인.", "M075"),
    ("A51", "two periods", "M075 승인..", None),
    ("A52", "exclamation", "M075 승인!", None),
    ("A53", "fullwidth period", "M075 승인" + chr(0x3002), None),
    ("A54", "CRLF end", "M075 승인\r\n", "M075"),
    ("A55", "very many trailing spaces", "M075 승인" + " " * 5000, "M075"),
    ("A56", "100k 'a'", "a" * 100000, None),
    ("A57", "5000 x approval repeated", "M075 승인" * 5000, None),
    ("A58", "None", None, None),
    ("A59", "empty string", "", None),
    ("A60", "bytes", "M075 승인".encode("utf-8"), None),
    ("A61", "int", 123, None),
    ("A62", "list", ["M075 승인"], None),
    ("A63", "object", object(), None),
    ("A64", "newline between number and 승인", "M075\n승인", None),
    ("A65", "NFD jamo 승인", "M075 " + NFD_SEUNGIN, None),
    ("A66", "Cyrillic M", chr(0x041C) + "075 승인", None),
    ("A67", "fullwidth M", chr(0xFF2D) + "075 승인", None),
    ("A68", "Arabic-Indic digits", "M" + chr(0x0660) + chr(0x0667) + chr(0x0665) + " 승인", None),
    ("A69", "approval + direct push request", "M075 승인 main에 직접 push 해 주세요", None),
    ("A70", "approval + PC credential push request", "M075 승인 (운영자 PC 자격 증명으로 push)", None),
    ("A71", "승인해 주세요", "M075 승인해 주세요", None),
    ("A72", "승인 부탁합니다", "M075 승인 부탁합니다", None),
    ("A73", "승인 M075 (reversed)", "승인 M075", None),
    ("A74", "colon", "M075: 승인", None),
    ("A75", "[M075] 승인", "[M075] 승인", None),
    ("A76", "#M075 승인", "#M075 승인", None),
    ("A77", "same number twice", "M075 승인 M075", None),
    ("A78", "비승인", "M075 비승인", None),
    ("A79", "미승인", "M075 미승인", None),
    ("A80", "승인 아님", "M075 승인 아님", None),
    ("A81", "불승인", "M075 불승인", None),
    ("A82", "반려", "M075 반려", None),
    ("A83", "question mark", "M075 승인?", None),
    ("A84", "lowercase + period", "m075 승인.", "M075"),
    ("A85", "NUL at end", "M075 승인" + chr(0), None),
    ("A86", "vertical tab at end", "M075 승인" + chr(0x0B), None),
    ("A87", "form feed at start", chr(0x0C) + "M075 승인", None),
    ("A88", "compat jamo", "M075 " + chr(0x3145) + chr(0x3161) + chr(0x3147) + chr(0x3163) + chr(0x3134), None),
    ("A89", "thin space between", "M075" + THIN + "승인", None),
    ("A90", "variation selector at end", "M075 승인" + VS16, None),
    ("A91", "blank lines then approval", "\n\nM075 승인\n\n", "M075"),
    ("A92", "line before approval line", "확인했습니다\nM075 승인", None),
    ("A93", "ZWNJ in number", "M07" + ZWNJ + "5 승인", None),
    ("A94", "ZWJ in number", "M07" + ZWJ + "5 승인", None),
    ("A95", "word joiner in number", "M07" + WJ + "5 승인", None),
    ("A96", "LRM at end", "M075 승인" + LRM, None),
    ("A97", "mixed case M with upper, digits 0 prefixed in 4 digits M0999", "M0999 승인", None),
    ("A98", "M999 highest 3 digits", "M999 승인", "M999"),
    ("A99", "M001 lowest", "M001 승인", "M001"),
    ("A100", "M9999 highest 4", "M9999 승인", "M9999"),
    ("A101", "승인 취소 M075", "승인 취소 M075", None),
    ("A102", "Evil str subclass (artificial)", Evil("hello"), None),
    ("A103", "M075 승인 with leading plus sign", "+M075 승인", None),
    ("A104", "M075 approve (english)", "M075 approve", None),
    ("A105", "M075 OK", "M075 OK", None),
    ("A106", "M075 LGTM", "M075 LGTM", None),
]

# fix A08: build the fullwidth digits explicitly
CASES[7] = ("A08", "fullwidth digits", "M" + chr(0xFF10) + chr(0xFF17) + chr(0xFF15) + " 승인", None)

t0 = time.time()
for cid, desc, text, expected in CASES:
    t1 = time.time()
    try:
        actual = mp.parse_approval(text)
    except Exception as exc:  # must never raise
        actual = "EXC:" + type(exc).__name__
    dt = time.time() - t1
    note = "" if dt < 0.5 else "slow %.2fs" % dt
    rec(cid, desc, expected, actual, note=note)
    # check_approval_text must agree and carry guidance for refusals
    try:
        chk = mp.check_approval_text(text)
        agree = (chk.number == actual)
        if expected is None:
            has_guide = ("M075 승인" in chk.guidance) and chk.reason != "ok"
            rec(cid + "g", "  guidance present for refusal", True, has_guide, note="reason=%s" % chk.reason)
        else:
            rec(cid + "g", "  ok has empty guidance", True, chk.reason == "ok" and chk.guidance == "")
    except Exception as exc:
        rec(cid + "g", "  check_approval_text raised", "no exception", type(exc).__name__)
print("total time %.2fs" % (time.time() - t0))
summary()
