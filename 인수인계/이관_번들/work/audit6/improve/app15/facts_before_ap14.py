"""AP14 고치기 전 사실 — 고치기 전 코드(사본)에서 새 시험이 확인하는 사실들이 어떤지 읽는다(파일을 고치지 않고 읽기만 한다). 사용: python -X utf8 facts_before_ap14.py <사본 폴더>"""
import importlib.util
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path[:0] = [str(root / "src"), str(root / "tests")]
from chanceblog_desktop.security import backup_note, boundary  # noqa: E402

print("새 모듈 security/errorlog.py 가 있나:", importlib.util.find_spec("chanceblog_desktop.security.errorlog") is not None)
print("경계에 arm_error_log 가 있나:", hasattr(boundary, "arm_error_log"))
print("백업의 담지 않는 것 이름:", [name for name, _ in backup_note.EXCLUDED])
print("그중 `logs/` 가 있나:", "logs/" in [name for name, _ in backup_note.EXCLUDED])
print("이유 문장에 '로그 파일을 만들지 않' 이 있나:", any("로그 파일을 만들지 않" in reason for _, reason in backup_note.EXCLUDED))
security = (root / "docs" / "SECURITY.md").read_text(encoding="utf-8")
trouble = (root / "docs" / "TROUBLESHOOTING.md").read_text(encoding="utf-8")
states = (root / "docs" / "UI_STATES.md").read_text(encoding="utf-8")
print("SECURITY 가 '로그 파일·내보내기: 아직 없다' 인가:", "**로그 파일·내보내기**: 아직 없다" in security)
print("TROUBLESHOOTING 이 '지금은 로그 파일이나' 인가:", "지금은 로그 파일이나" in trouble)
print("UI_STATES 가 '로그 파일은 설치 파일 묶음' 인가:", "로그 파일은 설치 파일 묶음" in states)
launcher = (root / "src" / "chanceblog_desktop" / "ui" / "launcher.py").read_text(encoding="utf-8")
print("launcher 가 오류 기록을 켜나:", "arm_error_log" in launcher)
state = (root / "src" / "chanceblog_desktop" / "ui" / "core" / "app_state.py").read_text(encoding="utf-8")
print("report_unexpected 가 파일 기록을 부르나:", "errorlog" in state)
