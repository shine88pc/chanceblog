"""Summarize v2/mut_log2.jsonl: per mutant id -> first pass Qt-less (new test alone), Qt-less suite (new test + test_ui_core + cdesign + c1a), Qt (new test alone). RED = a test failed (mutant caught).
usage: python summarize.py"""
import json
import sys
from pathlib import Path

rows = [json.loads(line) for line in Path("C:/work/ai/verify_app15_2/v2/mut_log2.jsonl").read_text(encoding="utf-8").splitlines()]
table = {}
order = []
for row in rows:
    key = row["id"]
    if key not in table:
        table[key] = {"what": row["what"]}
        order.append(key)
    modules = row["modules"]
    shape = "qt" if row["py"] == "qt" else ("dev_alone" if modules == ["test_ui_sentence_color"] else "dev_suite")
    table[key][shape] = "RED" if row["caught"] else "GREEN"
    if not row["restored"]:
        table[key]["restored"] = "NOT RESTORED"
    table[key].setdefault("reds_" + shape, row["reds"][:2])


def sort_key(k):
    prefix = "".join(c for c in k if c.isalpha())
    number = int("".join(c for c in k if c.isdigit()) or 0)
    return ({"NM": 0, "N": 1, "FP": 2}.get(prefix, 3), number)


print("id".ljust(6), "Qt-less alone".ljust(14), "Qt-less suite".ljust(14), "Qt alone".ljust(9), "what")
for key in sorted(order, key=sort_key):
    t = table[key]
    print(key.ljust(6), t.get("dev_alone", "-").ljust(14), t.get("dev_suite", "-").ljust(14), t.get("qt", "-").ljust(9), t["what"][:110], t.get("restored", ""))
print("all restored:", all("restored" not in t for t in table.values()), "| runs:", len(rows))
