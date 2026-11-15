import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P2/_probe")
import random
import re
import time
from h import mp, rec, summary

TOK = ["M", "m", "0", "1", "7", "5", "9", "00", "075", "M075", "m076", "승인", "승", "인", "확인했습니다", "진행하세요", "좋아 보입니다", "기본값대로", "다음 단계 진행",
       " ", "  ", "\t", "\n", "\r\n", ".", "..", "!", "?", ":", "-", "[", "]", "`", ">", '"', chr(0x200B), chr(0xFEFF), chr(0x00A0), chr(0xFF10), chr(0xFF2D), chr(0x3000), chr(0x202E),
       "승인합니다", "취소", "하지", "않습니다", "main", "push", "M1000", "M10000", "M0075", "M000", "x"]


def oracle(t):
    if not isinstance(t, str):
        return None
    b = t.strip(" \t\r\n")
    if len(b) > 2000:
        return None
    m = re.fullmatch(r"[Mm]([0-9]{3,4})[ \t]+승인\.?", b)
    if not m:
        return None
    d = m.group(1)
    if len(d) == 3 and d == "000":
        return None
    if len(d) == 4 and d[0] == "0":
        return None
    return "M" + d


random.seed(20261115)
bad = []
approved = 0
t0 = time.time()
N = 300000
for i in range(N):
    n = random.randint(1, 9)
    s = "".join(random.choice(TOK) for _ in range(n))
    if random.random() < 0.15:   # bias toward near-approvals
        s = random.choice([" ", "", "\n"]) + random.choice(["M", "m"]) + random.choice(["075", "76", "1000", "0075", "999", "000"]) + random.choice([" ", "\t", "  ", ""]) + "승인" + random.choice(["", ".", "!", " 취소", "합니다", "\n"]) + random.choice(["", " ", "\n"])
    a = mp.parse_approval(s)
    o = oracle(s)
    if a != o:
        bad.append((s, a, o))
    if a is not None:
        approved += 1
print("fuzz N=%d approvals=%d mismatches=%d time=%.1fs" % (N, approved, len(bad), time.time() - t0))
for s, a, o in bad[:10]:
    print("  MISMATCH", repr(s), a, o)
rec("FZ1", "parse_approval agrees with independent oracle on 300k random inputs", 0, len(bad))
rec("FZ2", "fuzz produced a healthy number of accepted approvals (sanity of the generator)", True, approved > 1000, note=str(approved))

# no-exception fuzz for the other parsers
errs = 0
for i in range(20000):
    n = random.randint(0, 40)
    s = "".join(random.choice(TOK + ["병합 요청 M075", "대상 PR: #1", "머리 커밋: abcdef1", "- ", "변경 파일 (1개)", "운영자 전용 항목 점검", "병합 방식:", "무엇을 바꾸나요?", "병합 번호: M075"]) for _ in range(n))
    try:
        mp.explanation_problems(s)
        mp.explanation_problems(s, s)
        mp.completion_notice_problems(s)
        mp.classify_change("blog", [s or "x"], s, {})
        mp.classify_change("desktop", [s or "x", "a.py"], {"a.py": s}, None)
        mp.check_approval_text(s)
    except Exception as exc:
        errs += 1
        if errs < 4:
            print("  EXC", type(exc).__name__, repr(s)[:80])
rec("FZ3", "no exception from parsers/classifier on 20k random texts", 0, errs)
summary()
