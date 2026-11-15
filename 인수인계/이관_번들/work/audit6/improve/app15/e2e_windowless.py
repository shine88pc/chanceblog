"""AP14 창 없는 실행 한 번 — `pythonw.exe`(콘솔이 없어 `sys.stderr` 가 None)로 작은 스크립트를 돌려, 경계를 깔고 오류 기록을 켠 뒤 처리하지 못한 예외를 내면 **고치기 전에는 어디에도 안 남던 것이**
데이터 폴더의 `logs/errors.log` 에 오류 이름과 코드 위치만 남는지 본다. 사용: python -X utf8 e2e_windowless.py <작업 폴더 또는 사본> <pythonw 경로>  (임시 폴더만 쓰고 끝나면 지운다)"""
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1])
pythonw = sys.argv[2]
tmp = Path(tempfile.mkdtemp(prefix="app15-windowless-"))
data = tmp / "data"
facts = tmp / "facts.txt"
key = "AI" + "za" + ("CANARY_WL_" + hashlib.sha256(b"app15-windowless").hexdigest())[:35]
child = tmp / "child.py"
child.write_text(f'''import sys
from pathlib import Path
sys.path.insert(0, {str(root / "src")!r})
facts = Path({str(facts)!r})
facts.write_text("stderr_is_none=" + str(sys.stderr is None) + "\\nstdout_is_none=" + str(sys.stdout is None) + "\\n", encoding="utf-8")
from chanceblog_desktop.security import boundary
boundary.install_gui(qt=False)
boundary.arm_error_log(lambda: Path({str(data)!r}))
with facts.open("a", encoding="utf-8") as handle:
    handle.write("logs_before_error=" + str((Path({str(data)!r}) / "logs").exists()) + "\\n")
def explode():
    raise RuntimeError("CANARY_WL_MESSAGE 오늘의 비밀 글 본문 " + {key!r} + " C:/Users/CANARY_WL_USER/Secret Folder/note.txt")
explode()
''', encoding="utf-8")
try:
    # 표준 입출력 핸들을 하나도 물려주지 않는다(close_fds) — 더블클릭으로 연 창 없는 실행 파일처럼 자식의 sys.stdout·sys.stderr 가 None 이 된다. 결과는 자식이 파일에 직접 적는다
    done = subprocess.run([pythonw, "-X", "utf8", str(child)], stdin=None, stdout=None, stderr=None, close_fds=True, creationflags=0x08000000, timeout=120)
    print("종료 코드:", done.returncode)
    print(facts.read_text(encoding="utf-8").strip())
    log = data / "logs" / "errors.log"
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    print("기록 파일이 생겼나:", log.exists())
    for line in text.splitlines():
        print("  줄:", line)
    print("가짜 글·비밀·경로가 파일에 있나:", any(piece in text for piece in ("CANARY", "Secret Folder", "note.txt", "Users", key, "비밀 글")))
    print("logs 안의 파일:", sorted(path.name for path in (data / "logs").iterdir()) if (data / "logs").exists() else None)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
