"""모듈의 줄 실행 여부 점검 — 시험이 한 번도 실행하지 않은 줄을 찾는다(읽기 전용, 표준 라이브러리만). 사용: linecov.py <작업 폴더>"""
import dis
import os
import sys
import unittest

root = os.path.abspath(sys.argv[1])
os.chdir(root)
sys.path.insert(0, root)
sys.path.insert(0, os.path.join(root, "tests"))
target = os.path.join(root, "pipeline", "merge_policy.py")
executed = set()


def tracer(frame, event, arg):
    if frame.f_code.co_filename == target:
        if event == "line":
            executed.add(frame.f_lineno)
        return tracer
    return None


sys.settrace(tracer)
suite = unittest.defaultTestLoader.discover(os.path.join(root, "tests"), pattern="test_merge_policy*.py", top_level_dir=os.path.join(root, "tests"))
result = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w")).run(suite)
sys.settrace(None)
print("ran", result.testsRun, "failures", len(result.failures), "errors", len(result.errors))

source = open(target, encoding="utf-8").read()
code = compile(source, target, "exec")
lines = set()


def walk(obj):
    for _offset, lineno in dis.findlinestarts(obj):
        if lineno:
            lines.add(lineno)
    for const in obj.co_consts:
        if hasattr(const, "co_code"):
            walk(const)


walk(code)
missing = sorted(lines - executed)
src = source.split("\n")
print("executable lines", len(lines), "executed", len(lines & executed), "missing", len(missing))
for number in missing:
    print("%4d: %s" % (number, src[number - 1][:150]))
