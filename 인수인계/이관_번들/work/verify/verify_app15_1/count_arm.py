"""AP14 2차 — 문서 주장 '`--sample` 없이 launcher.main 을 끝까지 부르는 기존 시험이 오류 기록을 켠다 — 그래도 기본 데이터 폴더에는 아무것도 안 생긴다' 를 센다.
launcher.main 이 부르는 boundary.arm_error_log 를 세는 껍데기를 씌우고 지정한 시험 모듈들을 한 프로세스로 돌린다. LOCALAPPDATA 를 verify_app15_1 아래 빈 폴더로 돌려 '기본 데이터 폴더' 를 가로챈다.
사용: python -B -X utf8 count_arm.py <tree 폴더> <가짜 LOCALAPPDATA 폴더> <시험 모듈…>
"""
import os
import sys
import unittest

TREE, LOCAL = sys.argv[1], sys.argv[2]
MODULES = sys.argv[3:]
assert LOCAL.replace("\\", "/").startswith("C:/work/ai/verify_app15_1/")
os.makedirs(LOCAL, exist_ok=True)
os.environ["LOCALAPPDATA"] = LOCAL
sys.path[:0] = [os.path.join(TREE, "src"), os.path.join(TREE, "tests"), os.path.join(TREE, "packaging"), TREE]
os.chdir(os.path.join(TREE, "tests"))

from chanceblog_desktop.security import boundary, errorlog  # noqa: E402

current = {"id": None}
armed = []
real_arm = boundary.arm_error_log


def counting_arm(resolve_folder):
    result = real_arm(resolve_folder)
    log = errorlog.active()
    armed.append((current["id"], bool(result), log is not None and log._folder is not None))     # 마지막 값: 켜는 순간 이미 폴더를 풀었나
    return result


boundary.arm_error_log = counting_arm


class Result(unittest.TextTestResult):
    def startTest(self, test):
        current["id"] = test.id()
        super().startTest(test)


suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
with open(os.devnull, "w") as sink:
    outcome = unittest.TextTestRunner(resultclass=Result, verbosity=0, stream=sink).run(suite)
print("시험 %d개, 실패 %d, 오류 %d" % (outcome.testsRun, len(outcome.failures), len(outcome.errors)))
per_module = {}
for test_id, ok, resolved in armed:
    module = test_id.split(".")[0] if test_id else "?"
    per_module.setdefault(module, []).append((test_id.split(".", 1)[1] if test_id else "?", ok, resolved))
for module, items in sorted(per_module.items()):
    print("%s: 오류 기록을 켠 시험 %d개" % (module, len(items)))
    for name, ok, resolved in items:
        print("    - %s (arm=%r, 켜는 순간 폴더 해석=%r)" % (name, ok, resolved))
print("합계: 켠 시험 %d개 (%d개 모듈)" % (len(armed), len(per_module)))
data = os.path.join(LOCAL, "ChanceblogDesktop")
print("가짜 기본 데이터 폴더 %s 가 생겼나: %r" % (data, os.path.exists(data)))
print("그 안에 logs 가 생겼나: %r" % os.path.exists(os.path.join(data, "logs")))
print("시험이 끝난 뒤 errorlog.active() =", errorlog.active())
