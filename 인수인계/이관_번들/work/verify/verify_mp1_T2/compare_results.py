"""Compare the implementer's WIP 6 mutation_results_wip6.txt with my re-run (res_new.txt + res_old.txt)."""
import re
import sys

IMPL = "C:/work/ai/audit6/improve/mergepol1/mutation_results_wip6.txt"
MINE = ["C:/work/ai/verify_mp1_T2/res_new.txt", "C:/work/ai/verify_mp1_T2/res_old.txt"]


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
        rows[mid] = (int(m.group(1)) if m else None, result, classes, sha, same, area, what)
    return rows


a = parse(IMPL)
b = {}
for path in MINE:
    try:
        b.update(parse(path))
    except FileNotFoundError:
        print("missing", path)
print("implementer rows:", len(a), "my rows:", len(b))
print("ids only in one side:", sorted(set(a) ^ set(b))[:20])
common = sorted(set(a) & set(b))
diff_count = [(k, a[k][0], b[k][0]) for k in common if a[k][0] != b[k][0]]
diff_class = [(k, a[k][2], b[k][2]) for k in common if a[k][2] != b[k][2]]
print("compared:", len(common), "different red counts:", len(diff_count), diff_count[:15])
print("different failing-class sets:", len(diff_class))
for k, x, y in diff_class[:10]:
    print("  ", k, "|", x, "|", y)
not_red = [k for k in b if b[k][0] is None]
print("my not-red:", not_red)
print("my restore flags all 'yes':", all(v[4] == "예" for v in b.values()))
print("distinct restored sha prefixes (mine):", sorted({v[3] for v in b.values()}))
fam = {}
for k, v in b.items():
    fam.setdefault(re.match(r"[A-Za-z]+", k).group(0), []).append((k, v[0]))
for f in sorted(fam):
    items = fam[f]
    reds = [n for _k, n in items if n]
    print("%-3s %3d mutants, red=%3d, red-test counts min/max=%s/%s" % (f, len(items), len(reds), min(reds) if reds else "-", max(reds) if reds else "-"))
ones = sorted(k for k, v in b.items() if v[0] == 1)
print("killed by exactly one test (%d):" % len(ones), " ".join(ones))
