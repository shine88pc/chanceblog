"""AP14 범위 확인 — 묶음 실행 파일의 시작 파일(packaging/gui_entry.py `start_gui`)이 `launcher.main` 의 예외를 붙잡으면 오류 기록에 남는가?
진짜 `start_gui` 를 불러, 진짜와 같은 순서(경계 깔기 → 오류 기록 켜기 → 화면을 만들다 예외)를 흉내 낸 `launcher.main` 을 끼운다.
사용: python -B -X utf8 probe_entry.py <tree 폴더> <임시 작업 폴더>
"""
import os
import sys
from unittest import mock

tree, work = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(tree, "src"))
sys.path.insert(0, os.path.join(tree, "packaging"))
import gui_entry  # noqa: E402
from chanceblog_desktop.security import boundary  # noqa: E402

root = os.path.join(work, "entry_data")
spoken = []


def fake_main(argv=None, *, out=None):
    boundary.install()
    boundary.install_gui(qt=False)
    boundary.arm_error_log(lambda: root)                 # 진짜 launcher.main 이 화면을 만들기 전에 하는 일
    raise ImportError("DLL load failed while importing QtWidgets: C:/Users/CANARY_jane/AppData/x.dll")      # 묶음 창 없는 실행에서 흔한 시작 실패


with mock.patch("chanceblog_desktop.ui.launcher.main", fake_main), mock.patch.object(gui_entry, "say", lambda text, error=False: spoken.append(text)):
    code = gui_entry.start_gui()
boundary.active() and boundary.active().uninstall()
print("start_gui 반환:", code)
print("화면에 보인 안내:", spoken)
print("logs 폴더가 생겼나:", os.path.exists(os.path.join(root, "logs")), "| 데이터 폴더가 생겼나:", os.path.exists(root))
