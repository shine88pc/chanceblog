"""Compare the implementer's mutation_results.txt with my re-run (mutation_results_v.txt)."""
import re

IMPL = "C:/work/ai/audit6/improve/mergepol1/mutation_results.txt"
MINE = "C:/work/ai/verify_mp1_T/mutation_results_v.txt"


def parse(path):
    rows = {}
    for line in open(path, encoding="utf-8"):
        if not line.startswith("| ") or line.startswith("| ID") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        mid, area, what, result, classes, sha, same = cells[:7]
        m = re.match(r"빨강 (\d+)건", result)
        rows[mid] = (int(m.group(1)) if m else None, result, classes, sha, same)
    return rows


a, b = parse(IMPL), parse(MINE)
print("implementer rows:", len(a), "my rows:", len(b))
print("ids only in one side:", sorted(set(a) ^ set(b)))
diff_count = [(k, a[k][0], b[k][0]) for k in a if k in b and a[k][0] != b[k][0]]
diff_class = [(k, a[k][2], b[k][2]) for k in a if k in b and a[k][2] != b[k][2]]
print("different red counts:", len(diff_count), diff_count[:20])
print("different failing-class sets:", len(diff_class))
for k, x, y in diff_class[:10]:
    print("  ", k, "|", x, "|", y)
not_red = [k for k in b if b[k][0] is None]
print("my not-red:", not_red)
print("my restore flags all 'yes':", all(v[4] == "예" for v in b.values()))
print("distinct sha prefixes in my run:", sorted({v[3] for v in b.values()}))
print("distinct sha prefixes in implementer run:", sorted({v[3] for v in a.values()}))
print("min/max red count (mine):", min(v[0] for v in b.values()), max(v[0] for v in b.values()))
low = sorted([(v[0], k) for k, v in b.items()])[:0]
ones = [k for k, v in b.items() if v[0] == 1]
print("mutants killed by exactly one test (weakest kills):", len(ones))
print(" ".join(ones))
