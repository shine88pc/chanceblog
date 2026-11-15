"""Exploratory runtime-patch mutation sweep (verifier, lens T).
For each data table / regex alternative used by classify_change, patch ONE element out of the live module
(in a scratch process, source files untouched), run tests/test_merge_policy.py, record killed/survived.
Usage: python sweep.py [--only substring]"""
import io
import os
import re
import sys
import time
import unittest

ROOT = "C:/work/ai/verify_mp1_T/tree_lf"
os.chdir(ROOT)
sys.dont_write_bytecode = True
sys.path.insert(0, ROOT + "/tests")
sys.path.insert(0, ROOT)
import _bootstrap  # noqa: E402,F401
from pipeline import merge_policy as mp  # noqa: E402
import test_merge_policy as tmp  # noqa: E402

BS = chr(92)
ONLY = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None


def run_suite():
    suite = unittest.defaultTestLoader.loadTestsFromModule(tmp)
    res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0, failfast=True).run(suite)
    bad = res.failures + res.errors
    first = bad[0][0].id().split(".")[-2] + "." + bad[0][0].id().split(".")[-1] if bad else ""
    return res.testsRun, len(bad), first


def alt_spans(p):
    """Return list of (group_label, [(alt_start, alt_end)...], bars, end) for every group (incl. top level) that has >= 2 alternatives."""
    n = len(p)
    top = {"start": 0, "bars": [], "end": n}
    stack = [top]
    groups = [top]
    i = 0
    while i < n:
        c = p[i]
        if c == BS:
            i += 2
            continue
        if c == "[":
            j = i + 1
            if j < n and p[j] == "^":
                j += 1
            if j < n and p[j] == "]":
                j += 1
            while j < n and p[j] != "]":
                if p[j] == BS:
                    j += 1
                j += 1
            i = j + 1
            continue
        if c == "(":
            j = i + 1
            if j < n and p[j] == "?":
                j += 1
                nxt = p[j:j + 1]
                if nxt in (":", "=", "!"):
                    j += 1
                elif p[j:j + 2] in ("<=", "<!"):
                    j += 2
                elif nxt in ("P", "<"):
                    j = p.index(">", j) + 1
                else:                                  # inline flags such as (?i) : not a group
                    i = p.index(")", j) + 1
                    continue
            g = {"start": j, "bars": [], "end": None}
            stack.append(g)
            groups.append(g)
            i = j
            continue
        if c == ")":
            g = stack.pop()
            g["end"] = i
            i += 1
            continue
        if c == "|":
            stack[-1]["bars"].append(i)
        i += 1
    out = []
    for g in groups:
        if g["bars"]:
            bounds = [g["start"]] + [b + 1 for b in g["bars"]]
            ends = g["bars"] + [g["end"]]
            out.append((bounds, ends, g["bars"]))
    return out


def drop_alternatives(pattern):
    """yield (description, new_pattern) removing exactly one alternative of one group."""
    for bounds, ends, bars in alt_spans(pattern):
        for k in range(len(bounds)):
            if k < len(bars):
                new = pattern[:bounds[k]] + pattern[ends[k] + 1:]
            else:
                new = pattern[:ends[k - 1]] + pattern[ends[k]:]
            yield pattern[bounds[k]:ends[k]], new


MUTANTS = []   # (label, apply, restore)


def add_const_drop(name):
    value = getattr(mp, name)
    for element in sorted(value, key=str):
        def apply(name=name, value=value, element=element):
            setattr(mp, name, type(value)(x for x in value if x != element))

        def restore(name=name, value=value):
            setattr(mp, name, value)
        MUTANTS.append((name + " - " + repr(element), apply, restore))


def add_regex_drop(name):
    rx = getattr(mp, name)
    for alt, new in drop_alternatives(rx.pattern):
        try:
            compiled = re.compile(new, rx.flags)
        except re.error:
            continue

        def apply(name=name, compiled=compiled):
            setattr(mp, name, compiled)

        def restore(name=name, rx=rx):
            setattr(mp, name, rx)
        MUTANTS.append((name + " alt - " + alt, apply, restore))


for const in ("_CRED_SUFFIXES", "_CRED_WORDS", "_ADS_FILES", "_ADS_DIRS", "_PUBLIC_DIRS", "_PUBLIC_ROOT_FILES", "_PACKAGING_FILES", "_PACKAGING_SUFFIXES", "_PACKAGING_DIRS",
              "_JS_SUFFIXES", "_ROLLBACK_PLACEHOLDERS"):
    add_const_drop(const)

for code_path, codes in list(mp._BLOG_SETTINGS.items()):
    for code in codes:
        def apply(code_path=code_path, code=code):
            new = dict(mp._BLOG_SETTINGS)
            new[code_path] = tuple(c for c in new[code_path] if c != code)
            mp._BLOG_SETTINGS = new

        def restore(orig=dict(mp._BLOG_SETTINGS)):
            mp._BLOG_SETTINGS = orig
        MUTANTS.append(("_BLOG_SETTINGS " + code_path + " - " + code, apply, restore))

for index, (label, _rx) in enumerate(mp._SECRET_VALUE_RES):
    def apply(index=index):
        mp._SECRET_VALUE_RES = tuple(x for i, x in enumerate(ORIG_SECRET) if i != index)

    def restore():
        mp._SECRET_VALUE_RES = ORIG_SECRET
    MUTANTS.append(("_SECRET_VALUE_RES entry - " + label, apply, restore))
ORIG_SECRET = mp._SECRET_VALUE_RES

for name in ("_ADS_TEXT_RE", "_DESTRUCTIVE_TEXT_RE", "_CRED_WORD_RE", "_DEPENDENCY_BASE_RE", "_CRED_BASE_RE", "_QUOTED_HOST_RE", "_KNOWN_HOST_RE", "_NET_CALL_RE", "_DYNAMIC_RE",
             "_NET_CLI_RE", "_JS_NET_RE", "_URL_RE", "_IMPORT_STATEMENT_RE"):
    add_regex_drop(name)
for index, (label, rx) in enumerate(mp._SECRET_VALUE_RES):
    for alt, new in drop_alternatives(rx.pattern):
        try:
            compiled = re.compile(new, rx.flags)
        except re.error:
            continue

        def apply(index=index, compiled=compiled, label=label):
            items = list(ORIG_SECRET)
            items[index] = (label, compiled)
            mp._SECRET_VALUE_RES = tuple(items)

        def restore():
            mp._SECRET_VALUE_RES = ORIG_SECRET
        MUTANTS.append(("_SECRET_VALUE_RES " + label + " alt - " + alt, apply, restore))


def main():
    base_run, base_bad, _ = run_suite()
    print("baseline: ran=%d failed=%d mutants=%d" % (base_run, base_bad, len(MUTANTS)))
    assert base_bad == 0
    survivors = []
    started = time.time()
    for label, apply, restore in MUTANTS:
        if ONLY and ONLY not in label:
            continue
        apply()
        try:
            ran, bad, first = run_suite()
        finally:
            restore()
        status = "KILLED" if bad else "SURVIVED"
        print("%-9s %s %s" % (status, label, ("<- " + first) if first else ""))
        if not bad:
            survivors.append(label)
    after_run, after_bad, _ = run_suite()
    print("after: ran=%d failed=%d (module restored)" % (after_run, after_bad))
    print("TOTAL %d mutants, survivors %d, seconds %d" % (len(MUTANTS), len(survivors), time.time() - started))
    print("SURVIVORS:")
    for label in survivors:
        print("  " + label)


main()
