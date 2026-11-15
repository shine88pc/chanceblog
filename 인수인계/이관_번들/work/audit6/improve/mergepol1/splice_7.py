"""doc_draft.md 의 '### 7-5.' 부터 '## 8.' 앞까지를 block_7_5.txt 로 바꾼다(정확히 한 번 나오는 표지만 허용)."""
HERE = "C:/work/ai/audit6/improve/mergepol1"
draft = open(HERE + "/doc_draft.md", encoding="utf-8").read()
block = open(HERE + "/block_7_5.txt", encoding="utf-8").read()
start_mark, end_mark = "### 7-5. ", "## 8. 병합 방식 제한"
assert draft.count(start_mark) == 1 and draft.count(end_mark) == 1
start, end = draft.index(start_mark), draft.index(end_mark)
assert start < end
assert block.endswith("\n\n")
open(HERE + "/doc_draft.md", "w", encoding="utf-8", newline="\n").write(draft[:start] + block + draft[end:])
print("spliced", len(block), "chars; draft now", len(draft[:start] + block + draft[end:]))
