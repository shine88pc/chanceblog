from pathlib import Path

p = Path("C:/work/ai/improve_wt_app15/tests/test_security_errorlog.py")
t = p.read_text(encoding="utf-8")
old = '''        self.assertNotIn("system", calls - {"os.system"} if False else {name.split(".")[-1] for name in calls if name.startswith("os.")} - {"replace", "open", "fspath"}, "os 로 하는 일은 이름 바꾸기·열기뿐이다")
'''
new = '''        self.assertEqual({name for name in calls if name.startswith("os.")}, {"os.replace"}, "os 로 하는 일은 이름 바꾸기 하나뿐이다(프로세스·셸·파일 열기 호출 없음)")
'''
assert t.count(old) == 1
p.write_text(t.replace(old, new), encoding="utf-8")
print("고침")
