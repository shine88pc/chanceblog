src = open("C:/work/ai/verify_mp1_T/mutate_v.py", encoding="utf-8").read()


def sub(old, new):
    global src
    assert src.count(old) == 1, (old, src.count(old))
    src = src.replace(old, new)


sub('WORK = HERE + "/mut_tree"', 'WORK = HERE + "/mut_tree3"')
sub('HERE + "/my_mutants.py"', 'HERE + "/my_mutants3.py"')
sub('OUT_NAME = "mutation_results_mine.txt"', 'OUT_NAME = "mutation_results_mine3.txt"')
open("C:/work/ai/verify_mp1_T/mutate_v3.py", "w", encoding="utf-8").write(src)
print("ok")
