"""Builds mutate_v.py from the implementer's WIP 6 mutate.py by text substitution (paths only; plus a --mine switch and a --with-retired switch).
Reads the implementer's folder, writes only under verify_mp1_T2."""
import shutil

IMPL = "C:/work/ai/audit6/improve/mergepol1/"
OUT = "C:/work/ai/verify_mp1_T2/"
shutil.copyfile(IMPL + "mutants_extra.py", OUT + "mutants_extra.py")
src = open(IMPL + "mutate.py", encoding="utf-8").read()


def sub(old, new):
    global src
    assert src.count(old) == 1, (old[:60], src.count(old))
    src = src.replace(old, new)


sub('REPO = "C:/work/ai/improve_wt_mergepol1"', 'REPO = "C:/work/ai/verify_mp1_T2/tree_lf"')
sub('HERE = "C:/work/ai/audit6/improve/mergepol1"', 'HERE = "C:/work/ai/verify_mp1_T2"')
sub('open(HERE + "/mutation_results.txt", "w", encoding="utf-8")', 'open(HERE + "/" + OUT_NAME, "w", encoding="utf-8")')
sub('MEMFREE, "0.6"]', 'MEMFREE, "0.7"]')
sub('import mutants_extra  # noqa: E402', 'OUT_NAME = "mutation_results_v.txt"\nimport mutants_extra  # noqa: E402')
marker = 'MUTANTS = [m for m in MUTANTS if m["id"] not in mutants_extra.RETIRED]'
assert src.count(marker) == 1
src = src.replace(marker, '''ALL_WITH_RETIRED = list(MUTANTS)
''' + marker + '''
if "--with-retired" in sys.argv:
    MUTANTS = [m for m in ALL_WITH_RETIRED if m["id"] in mutants_extra.RETIRED]
    OUT_NAME = "mutation_results_retired.txt"


def _load_mine(name="my_mutants.py"):
    import importlib.util
    spec = importlib.util.spec_from_file_location("my_mutants", HERE + "/" + name)
    mod = importlib.util.module_from_spec(spec)
    mod.M, mod.A, mod.MOD, mod.DOC = M, A, MOD, DOC
    spec.loader.exec_module(mod)
    return mod.MY_MUTANTS


if "--mine" in sys.argv:
    _file = sys.argv[sys.argv.index("--mine") + 1]
    MUTANTS = _load_mine(_file)
    OUT_NAME = "mutation_results_" + _file.replace(".py", "") + ".txt"
''')
open(OUT + "mutate_v.py", "w", encoding="utf-8").write(src)
print("written", len(src))
