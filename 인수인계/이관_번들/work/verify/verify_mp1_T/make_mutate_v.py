"""Builds mutate_v.py from the implementer's mutate.py by text substitution (so no escape sequences are retyped).
Only paths change (read the implementer's tool, never write under the implementer's report folder)."""
src = open("C:/work/ai/audit6/improve/mergepol1/mutate.py", encoding="utf-8").read()


def sub(old, new, count=1):
    global src
    assert src.count(old) == count, (old, src.count(old))
    src = src.replace(old, new)


sub('REPO = "C:/work/ai/improve_wt_mergepol1"', 'REPO = "C:/work/ai/verify_mp1_T/tree_lf"')
sub('HERE = "C:/work/ai/audit6/improve/mergepol1"', 'HERE = "C:/work/ai/verify_mp1_T"')
sub('open(HERE + "/mutation_results.txt", "w", encoding="utf-8")', 'open(HERE + "/" + OUT_NAME, "w", encoding="utf-8")')
# choose mutant set: default = implementer's 182, --mine = my own list from my_mutants.py (MY_MUTANTS), --only filters by id
sub('NL = "\\n"\nMUTANTS = [', 'NL = "\\n"\nOUT_NAME = "mutation_results_v.txt"\nMUTANTS = [')
sub('def sha256(path):', '''def _load_mine():
    import importlib.util
    spec = importlib.util.spec_from_file_location("my_mutants", HERE + "/my_mutants.py")
    mod = importlib.util.module_from_spec(spec)
    mod.M, mod.A, mod.MOD, mod.DOC = M, A, MOD, DOC
    spec.loader.exec_module(mod)
    return mod.MY_MUTANTS


if "--mine" in sys.argv:
    MUTANTS = _load_mine()
    OUT_NAME = "mutation_results_mine.txt"


def sha256(path):''')
open("C:/work/ai/verify_mp1_T/mutate_v.py", "w", encoding="utf-8").write(src)
print("written", len(src))
