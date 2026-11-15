"""usage: python survivors.py <defs.py> <py>  -> prints ids (space separated) that were GREEN (not caught) in the first pass (new test module alone) for that interpreter shape."""
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
defs_path, py = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("d", defs_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ids = list(module.MUTATIONS)
last = {}
for line in Path("C:/work/ai/verify_app15_2/v2/mut_log2.jsonl").read_text(encoding="utf-8").splitlines():
    row = json.loads(line)
    if row["py"] == py and row["modules"] == ["test_ui_sentence_color"] and row["id"] in ids:
        last[row["id"]] = row
print(" ".join(i for i in ids if i in last and not last[i]["caught"]))
