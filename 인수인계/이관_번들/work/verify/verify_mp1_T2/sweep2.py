"""R1 check (verifier lens T, WIP 6): runtime-patch sweep over every data table / regex alternative of the new module, one element at a time.
Derived values (HOST_TLDS, _SAFETY_*, _ROLLBACK_PLACEHOLDER_SET, EXTERNAL_MODULES, _URL_RE, _POLICY_SELF_FOLDED) are re-derived exactly as the module derives them,
so the patch equals a source-level deletion. Pass 1 runs the fast classify-related classes (failfast); pass 2 re-runs every survivor against the FULL behavior + docs modules;
pass 3 runs a differential battery on each final survivor (inputs built from the removed element's own table) to separate redundant/shadowed removals from real test gaps.
Usage: python sweep2.py [--only substring]   (source files are never touched)"""
import io
import os
import re
import sys
import time
import unittest

ROOT = "C:/work/ai/verify_mp1_T2/tree_lf"
os.chdir(ROOT)
sys.dont_write_bytecode = True
sys.path.insert(0, ROOT + "/tests")
sys.path.insert(0, ROOT)
import _bootstrap  # noqa: E402,F401
from pipeline import merge_policy as mp  # noqa: E402
import test_merge_policy as tmp  # noqa: E402
import test_merge_policy_docs as tdoc  # noqa: E402

BS = chr(92)
ONLY = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None


def classes_of(module, pick):
    found = []
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase) and pick(name):
            found.append(obj)
    return found


def make_suite(modules_and_picks, skip_slow=True):
    suite = unittest.TestSuite()
    for module, pick in modules_and_picks:
        for cls in classes_of(module, pick):
            for test in unittest.defaultTestLoader.loadTestsFromTestCase(cls):
                if skip_slow and "linear_time" in test.id():
                    continue
                suite.addTest(test)
    return suite


FAST_PICK = lambda n: n.startswith("Classify") or n in ("ConstantsPinTest", "PolicyStoryTest")      # noqa: E731
SUITES = {
    "fast": lambda: make_suite([(tmp, FAST_PICK)]),
    "full": lambda: make_suite([(tmp, lambda n: True), (tdoc, lambda n: True)], skip_slow=False),
}


def run(suite, failfast=True):
    res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0, failfast=failfast).run(suite)
    bad = res.failures + res.errors
    first = bad[0][0].id().split(".")[-2] + "." + bad[0][0].id().split(".")[-1] if bad else ""
    return res.testsRun, len(bad), first


# ---------------------------------------------------------------- regex alternative dropping
def alt_spans(p):
    n = len(p)
    top = {"start": 0, "bars": [], "end": n}
    stack, groups, i = [top], [top], 0
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
                else:
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
            out.append(([g["start"]] + [b + 1 for b in g["bars"]], g["bars"] + [g["end"]], g["bars"]))
    return out


def drop_alternatives(pattern):
    for bounds, ends, bars in alt_spans(pattern):
        for k in range(len(bounds)):
            new = pattern[:bounds[k]] + pattern[ends[k] + 1:] if k < len(bars) else pattern[:ends[k - 1]] + pattern[ends[k]:]
            yield pattern[bounds[k]:ends[k]], new


# ---------------------------------------------------------------- mutant list: (label, suite_key, patches dict)
MUTANTS = []
ORIG = {}


def orig(name):
    if name not in ORIG:
        ORIG[name] = getattr(mp, name)
    return ORIG[name]


def removed(value, element):
    return type(value)(x for x in value if x != element)


DERIVE = {
    "SAFETY_GUARD_DOCS": lambda nv: {"_SAFETY_DOC_FILES": frozenset(n.casefold() for n in nv)},
    "SAFETY_GUARD_FILES": lambda nv: {"_SAFETY_FILES": frozenset(n.casefold() for n in nv)},
    "SAFETY_GUARD_DIRS": lambda nv: {"_SAFETY_DIR_PREFIXES": tuple(n.casefold() + "/" for n in nv)},
    "ROLLBACK_PLACEHOLDERS": lambda nv: {"_ROLLBACK_PLACEHOLDER_SET": frozenset(t.casefold() for t in nv)},
    "NETWORK_MODULES": lambda nv: {"EXTERNAL_MODULES": nv + orig("SERVICE_SDK_MODULES")},
    "SERVICE_SDK_MODULES": lambda nv: {"EXTERNAL_MODULES": orig("NETWORK_MODULES") + nv},
    "COUNTRY_TLDS": lambda nv: {"HOST_TLDS": frozenset(n for n in nv + orig("GENERIC_TLDS") if n not in orig("FILE_NAME_TLDS"))},
    "GENERIC_TLDS": lambda nv: {"HOST_TLDS": frozenset(n for n in orig("COUNTRY_TLDS") + nv if n not in orig("FILE_NAME_TLDS"))},
    "POLICY_SELF_FILES": lambda nv: {"_POLICY_SELF_FOLDED": frozenset(n.casefold() for n in nv)},
    "EXTERNAL_SCHEMES": lambda nv: {"_URL_RE": re.compile(r"(?<![A-Za-z0-9_+.-])(?:" + "|".join(sorted(nv, key=len, reverse=True)) + "):" + "//" + r"""([^\s'"<>(){}`/?#]*)""", re.I)},
}

TABLES = ("_DEPENDENCY_DIRS", "_CRED_SUFFIXES", "_CRED_WORDS", "_ADS_FILES", "_ADS_DIRS", "_PUBLIC_DIRS", "_PUBLIC_ROOT_FILES", "SITE_INTERNAL_ENTRIES", "_PACKAGING_FILES",
          "_PACKAGING_SUFFIXES", "_PACKAGING_DIRS", "_JS_SUFFIXES", "SHELL_SUFFIXES", "DOC_SUFFIXES", "EXAMPLE_HOSTS", "EXAMPLE_TOP_LEVELS", "ROLLBACK_PLACEHOLDERS",
          "SAFETY_GUARD_WORDS", "SAFETY_GUARD_DOCS", "SAFETY_GUARD_FILES", "SAFETY_GUARD_DIRS", "NETWORK_MODULES", "SERVICE_SDK_MODULES", "GENERIC_TLDS", "EXTERNAL_SCHEMES",
          "POLICY_SELF_FILES")
for table in TABLES:
    value = orig(table)
    for element in sorted(value, key=str):
        new_value = removed(value, element)
        patches = {table: new_value}
        patches.update(DERIVE.get(table, lambda nv: {})(new_value))
        MUTANTS.append((table + " - " + repr(element), "fast", patches))

for element in orig("COUNTRY_TLDS"):                      # ~244 two-letter names: only the TLD-related classes are needed in pass 1
    new_value = removed(orig("COUNTRY_TLDS"), element)
    patches = {"COUNTRY_TLDS": new_value}
    patches.update(DERIVE["COUNTRY_TLDS"](new_value))
    MUTANTS.append(("COUNTRY_TLDS - " + repr(element), "tld", patches))

for code_path, codes in orig("_BLOG_SETTINGS").items():
    for code in codes:
        new = dict(orig("_BLOG_SETTINGS"))
        new[code_path] = tuple(c for c in new[code_path] if c != code)
        MUTANTS.append(("_BLOG_SETTINGS " + code_path + " - " + code, "fast", {"_BLOG_SETTINGS": new}))

REGEXES = ("_DEPENDENCY_BASE_RE", "_CRED_BASE_RE", "_ADS_TEXT_RE", "_DESTRUCTIVE_TEXT_RE", "_CRED_WORD_RE", "_KNOWN_HOST_RE", "_NET_CALL_RE", "_DYNAMIC_RE", "_NET_CLI_RE",
           "_JS_NET_RE", "_SHELL_NET_RE", "_IMPORT_STATEMENT_RE", "_AUTH_HEADER_RE", "_QUOTED_HOST_RE", "_QUOTED_RELATIVE_RE")
for name in REGEXES:
    rx = orig(name)
    for alt, new in drop_alternatives(rx.pattern):
        try:
            compiled = re.compile(new, rx.flags)
        except re.error:
            continue
        MUTANTS.append((name + " alt - " + alt, "fast", {name: compiled}))

SECRETS = orig("_SECRET_VALUE_RES")
for index, (label, _rx) in enumerate(SECRETS):
    MUTANTS.append(("_SECRET_VALUE_RES entry - " + label, "fast", {"_SECRET_VALUE_RES": tuple(x for i, x in enumerate(SECRETS) if i != index)}))
for index, (label, rx) in enumerate(SECRETS):
    for alt, new in drop_alternatives(rx.pattern):
        try:
            compiled = re.compile(new, rx.flags)
        except re.error:
            continue
        items = list(SECRETS)
        items[index] = (label, compiled)
        MUTANTS.append(("_SECRET_VALUE_RES " + label + " alt - " + alt, "fast", {"_SECRET_VALUE_RES": tuple(items)}))


def suite_for(key):
    if key == "tld":
        return make_suite([(tmp, lambda n: n in ("ClassifyTablesTest", "ClassifyExternalConnectionTest", "ClassifyExternalConnectionMoreTest"))])
    return SUITES[key]()


def apply(patches):
    saved = {k: getattr(mp, k) for k in patches}
    for k, v in patches.items():
        setattr(mp, k, v)
    return saved


def restore(saved):
    for k, v in saved.items():
        setattr(mp, k, v)


def signature(kind, path, text, declared):
    result = mp.classify_change(kind, [path], text, declared)
    return result.tier, result.categories, result.extra_flags


def battery_inputs(label):
    """Inputs built from the removed element's own table (or the removed regex alternative) in several shapes, for both repository kinds."""
    inputs = []
    if " alt - " in label:
        name, alt = label.split(" alt - ", 1)
        names = [alt, alt.upper(), alt.capitalize(), alt.replace("[ " + BS + "t]", " ").replace(BS + ".", ".").replace(BS + "s+", " ").replace("[_-]?", "_")]
        shapes = ("{}\n", "x = '{}'\n", "x = {}(a)\n", "cmd = '{} x'\n", "x = {}\n", "{} y\n", "import {}\n", "'{}'\n", "cmd = ['{}', 'x']\n", "x = requests.{}(a)\n", "git {} origin\n")
        for element in names:
            for shape in shapes:
                for path in ("pipeline/x.py", "scripts/x.sh", "scripts/x.js", "docs/a.md"):
                    for kind in ("blog", "desktop"):
                        inputs.append((kind, path, shape.format(element)))
        return inputs
    table, _sep, element = label.partition(" - ")
    pool = []
    if hasattr(mp, table):
        try:
            pool = [str(x) for x in orig(table)]
        except TypeError:
            pool = []
    if not pool:
        pool = [element.strip("'")]
    for name in pool:
        for path in (name, "pipeline/" + name, name + "/a.txt", "x/" + name + "/a.py", "src/app/x" + name, "src/app/X" + name.upper(), "docs/" + name):
            for kind in ("blog", "desktop"):
                inputs.append((kind, path, ""))
        for text in (name + "\n", "x = '" + name + "'\n", "x = 'svc.provider." + name + "'\n", "x = '//svc.provider." + name + "/x.js'\n", "import " + name + "\n", name + "(a)\n"):
            for path in ("pipeline/x.py", "docs/a.md"):
                inputs.append(("blog", path, text))
    return inputs


def main():
    base_run, base_bad, _ = run(SUITES["full"](), failfast=False)
    print("baseline(full): ran=%d failed=%d mutants=%d" % (base_run, base_bad, len(MUTANTS)), flush=True)
    assert base_bad == 0
    started = time.time()
    survivors1 = []
    for label, key, patches in MUTANTS:
        if ONLY and ONLY not in label:
            continue
        saved = apply(patches)
        try:
            ran, bad, first = run(suite_for(key))
        finally:
            restore(saved)
        if not bad:
            survivors1.append((label, patches))
        print("%-9s %s %s" % ("KILLED" if bad else "SURV1", label, ("<- " + first) if first else ""), flush=True)
    print("pass1 done: %d mutants, %d survived the fast suite, %d seconds" % (len(MUTANTS), len(survivors1), time.time() - started), flush=True)
    final = []
    for label, patches in survivors1:
        saved = apply(patches)
        try:
            ran, bad, first = run(SUITES["full"](), failfast=True)
        finally:
            restore(saved)
        print("%-9s %s %s" % ("KILLED2" if bad else "SURVIVED", label, ("<- " + first) if first else ""), flush=True)
        if not bad:
            final.append((label, patches))
    after_run, after_bad, _ = run(SUITES["full"](), failfast=False)
    print("after: ran=%d failed=%d (module restored)" % (after_run, after_bad))
    print("TOTAL %d mutants, final survivors %d, seconds %d" % (len(MUTANTS), len(final), time.time() - started))
    print("SURVIVORS (differential battery: does the removal change ANY classification of inputs built from the table's own elements?):")
    declared = dict.fromkeys(mp.DECLARED_REQUIRED, False)
    for label, patches in final:
        inputs = battery_inputs(label)
        base = [signature(kind, path, text, declared) for kind, path, text in inputs]
        saved = apply(patches)
        try:
            after = [signature(kind, path, text, declared) for kind, path, text in inputs]
        finally:
            restore(saved)
        changed = [(inputs[i], base[i], after[i]) for i in range(len(inputs)) if after[i] != base[i]]
        if changed:
            (kind, path, text), was, now = changed[0]
            print("  REAL-GAP    %s   (battery %d inputs, %d differ; first: %s %r %r: %s -> %s)" % (label, len(inputs), len(changed), kind, path, text[:40], was, now))
        else:
            print("  EQUIV-LIKE  %s   (battery %d inputs, identical)" % (label, len(inputs)))


if __name__ == "__main__":
    main()
