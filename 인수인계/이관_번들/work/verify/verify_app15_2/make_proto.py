"""Build proto_copy (a COPY of final_copy) with a throw-away prototype of the AP13 'open in topics' idea, three variants selectable at run time.
Nothing here touches the real worktree. Run: python make_proto.py
"""
import os
import shutil
from pathlib import Path

H = Path("C:/work/ai/verify_app15_2")
SRC, DST = H / "final_copy", H / "proto_copy"


def force(func, path, _exc):
    os.chmod(path, 0o666)
    func(path)


if DST.exists():
    shutil.rmtree(DST, onexc=force)
shutil.copytree(SRC, DST, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def sub(rel, old, new):
    path = DST / rel
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (rel, text.count(old), old[:60])
    path.write_text(text.replace(old, new), encoding="utf-8", newline="")


UI = "src/chanceblog_desktop/ui/"
# 1) controller: a 'wanted' slot (implementer's proposed design) consumed after the async read
sub(UI + "core/candidates_view.py", "        self.selected = None                                 # 고른 후보 번호(내부 열쇠 — 글이 아니다)\n",
    "        self.selected = None                                 # 고른 후보 번호(내부 열쇠 — 글이 아니다)\n        self.wanted = None                                   # PROTOTYPE: 읽기가 끝나면 고르고 싶은 후보 번호\n")
sub(UI + "core/candidates_view.py", "    def close_detail(self):\n",
    "    def want(self, candidate_id):\n        \"\"\"PROTOTYPE\"\"\"\n        self.wanted = candidate_id\n        if candidate_id in self._index:\n            self.selected, self.opened = candidate_id, True\n            return True\n        return False\n\n    def close_detail(self):\n")
sub(UI + "core/candidates_view.py", "        self._notices = {}\n        if self.selected is not None and self.selected not in self._index:\n",
    "        self._notices = {}\n        if self.wanted is not None:\n            wanted, self.wanted = self.wanted, None\n            if wanted in self._index:\n                self.selected, self.opened = wanted, True\n        if self.selected is not None and self.selected not in self._index:\n")
# 2) shell: three variants of the entry point
sub(UI + "qt/shell.py", "    def draft(self, topic_id, blog):\n        self.notify(self.state.draft_requested(topic_id, blog))\n",
    "    def draft(self, topic_id, blog):\n        self.notify(self.state.draft_requested(topic_id, blog))\n\n"
    "    PROTO_VARIANT = 'v1'\n\n"
    "    def open_in_topics(self, candidate_id):\n"
    "        \"\"\"PROTOTYPE of AP13: v1 = want() then go() (naive order) / v2 = go() then want() then render() / v3 = go() then set controller attributes directly (no new controller API).\"\"\"\n"
    "        candidates = self.state.candidates\n"
    "        if self.PROTO_VARIANT == 'v1':\n"
    "            candidates.want(candidate_id)\n"
    "            self.go('topics')\n"
    "        elif self.PROTO_VARIANT == 'v2':\n"
    "            self.go('topics')\n"
    "            candidates.want(candidate_id)\n"
    "            self.render()\n"
    "        elif self.PROTO_VARIANT == 'v4':\n"
    "            if candidate_id in candidates._index:\n"
    "                candidates.select(candidate_id)\n"
    "            else:\n"
    "                candidates.wanted = candidate_id\n"
    "            self.go('topics')\n"
    "        else:\n"
    "            self.go('topics')\n"
    "            candidates.selected, candidates.opened = candidate_id, True\n"
    "            self.render()\n")
# 3) drawer: the draft button now calls the prototype entry point
sub(UI + "qt/screens.py", "        button.clicked.connect(lambda _=False, key=draft[\"key\"]: shell.draft(d[\"id\"], key))\n",
    "        button.clicked.connect(lambda _=False, key=draft[\"key\"]: shell.open_in_topics(d[\"id\"]))\n")
print("proto_copy ready")
