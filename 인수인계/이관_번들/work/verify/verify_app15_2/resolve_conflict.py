"""Resolve a conflicted file by keeping the 'theirs' side (the commit being applied) and dropping given line ranges/blocks.
usage: python resolve_conflict.py <file> <mode> [pattern...]
 mode 'theirs'   : keep THEIRS side of every conflict hunk, drop ours
 mode 'both'     : keep ours then theirs (concatenate)
Extra patterns (regex, matched per line) name lines to DELETE from the kept text (single lines) -- used to drop the other item's lines.
Block deletion: pattern of form  BLOCK:<start-regex>:<end-regex-exclusive>  deletes from first matching start line up to (not including) the end line.
Prints a short report of the hunks it resolved.
"""
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
mode = sys.argv[2]
patterns = sys.argv[3:]
text = path.read_text(encoding="utf-8")
lines = text.split("\n")
out = []
state = "normal"
ours, theirs = [], []
hunks = 0
for line in lines:
    if line.startswith("<<<<<<< ") and state == "normal":
        state, ours, theirs = "ours", [], []
        hunks += 1
    elif line.startswith("=======") and state == "ours":
        state = "theirs"
    elif line.startswith(">>>>>>> ") and state == "theirs":
        out.extend(theirs if mode == "theirs" else (theirs + ours if mode == "reverse" else ours + theirs))
        state = "normal"
    elif state == "ours":
        ours.append(line)
    elif state == "theirs":
        theirs.append(line)
    else:
        out.append(line)
assert state == "normal", "unterminated conflict"
for pattern in patterns:
    if pattern.startswith("BLOCK:"):
        _tag, start, end = pattern.split(":", 2)
        index = next((i for i, line in enumerate(out) if re.search(start, line)), None)
        if index is None:
            print("block start not found:", start)
            continue
        stop = next((i for i in range(index + 1, len(out)) if re.search(end, out[i])), len(out))
        del out[index:stop]
    else:
        out = [line for line in out if not re.search(pattern, line)]
path.write_text("\n".join(out), encoding="utf-8", newline="")
print(f"{path.name}: resolved {hunks} hunk(s), mode={mode}, extra rules={len(patterns)}")
