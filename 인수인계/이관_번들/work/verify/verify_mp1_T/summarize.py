import re

rows = {}
for line in open("C:/work/ai/verify_mp1_T/mutation_results_v.txt", encoding="utf-8"):
    if not line.startswith("| ") or line.startswith("| ID") or line.startswith("|---"):
        continue
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    mid, area, what, result = cells[:4]
    m = re.match(r"빨강 (\d+)건", result)
    rows[mid] = (area, int(m.group(1)) if m else None)

new43 = ["S%02d" % i for i in range(1, 11)] + ["X%02d" % i for i in range(1, 27)] + ["J%02d" % i for i in range(16, 23)]
print("NEW 43 (red test counts):")
print(" ".join("%s=%d" % (k, rows[k][1]) for k in new43))
fam = {}
for k, (area, n) in rows.items():
    fam.setdefault(k[0], []).append((k, n))
print()
for f in sorted(fam):
    items = fam[f]
    print("%s: %d mutants, all red=%s, red-test counts min/max=%d/%d" % (f, len(items), all(n for _k, n in items), min(n for _k, n in items), max(n for _k, n in items)))
print()
old139 = [k for k in rows if k not in new43]
print("old139 count:", len(old139), "all red:", all(rows[k][1] for k in old139))
