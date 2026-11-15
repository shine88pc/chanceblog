from pathlib import Path

p = Path("C:/work/ai/improve_wt_app15/tests/test_security_errorlog.py")
t = p.read_text(encoding="utf-8")


def swap(old, new):
    global t
    assert t.count(old) == 1, old[:60]
    t = t.replace(old, new)


# 1) Import 노드에는 module 이 없다
swap('''        for word in ("subprocess", "socket", "urllib", "http", "faulthandler", "traceback", "logging", "os.system", "startfile"):
            self.assertNotIn(word, [part for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for part in ((node.module or "").split(".") + [alias.name for alias in node.names])])
''', '''        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(part for alias in node.names for part in alias.name.split("."))
            elif isinstance(node, ast.ImportFrom):
                imported.update((node.module or "").split(".") + [alias.name for alias in node.names])
        for word in ("subprocess", "socket", "urllib", "http", "faulthandler", "traceback", "logging", "ctypes", "shutil", "tempfile"):
            self.assertNotIn(word, imported)
        self.assertNotIn("system", calls - {"os.system"} if False else {name.split(".")[-1] for name in calls if name.startswith("os.")} - {"replace", "open", "fspath"}, "os 로 하는 일은 이름 바꾸기·열기뿐이다")
''')
# 2) 'chanceblog.db' 에도 log 가 들어 있다
swap('''        self.assertFalse(any("log" in path.name for path in folder.rglob("*")))''',
     '''        self.assertFalse(any(path.name.startswith(("logs", "errors.log")) for path in folder.rglob("*")), "백업에 오류 기록이 들어갔다")''')
# 3) 가장 안쪽이 먼저 — 실제 추적과 견준다
swap('''        places = line.split(" ", 3)[3].split(" < ")
        self.assertEqual(len(places), 3, "caught_deep → outer → inner 세 곳")
        numbers = [int(place.rsplit(":", 1)[1]) for place in places]
        self.assertGreater(numbers[0], numbers[1], "가장 안쪽(오류가 난 곳)이 먼저다")
''', '''        places = line.split(" ", 3)[3].split(" < ")
        self.assertEqual(len(places), 3, "caught_deep → outer → inner 세 곳")
        outward = [frame.lineno for frame in traceback.extract_tb(error.__traceback__)]          # 바깥에서 안쪽 순서
        self.assertEqual([int(place.rsplit(":", 1)[1]) for place in places], outward[::-1], "가장 안쪽(오류가 난 곳)이 먼저다")
''')
swap("import threading\nimport types\nimport unittest\n", "import threading\nimport traceback\nimport types\nimport unittest\n")
# 4) 재진입 시험 — 안쪽 부름이 다시 안쪽 부름을 만들지 않게
swap('''        real = errorlog.ErrorLog._append
        nested = []

        def append_with_a_nested_error(this, line):
            if not nested:
                nested.append(this.record("unraisable", ValueError, caught()))
            return real(this, line)
''', '''        real = errorlog.ErrorLog._append
        state = {"entered": False, "nested": None}

        def append_with_a_nested_error(this, line):
            if not state["entered"]:
                state["entered"] = True
                state["nested"] = this.record("unraisable", ValueError, caught())
            return real(this, line)
''')
swap('''        self.assertEqual((result, nested), ([True], [True]))
        self.assertEqual(len(self.lines()), 2)''', '''        self.assertEqual((result, state["nested"]), ([True], True))
        self.assertEqual(len(self.lines()), 2)''')
p.write_text(t, encoding="utf-8")
print("고침")
