"""2차 지시 소스 고치기(AP14) — `errorlog.py` 의 돌려쓰기(S4)와 문구(S5·S3)를 정확히 한 곳씩 바꾼다(옛 글이 정확히 한 번 나오지 않으면 실패). 사용: python -X utf8 round2_src.py <작업 폴더>"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1])
HERE = Path(__file__).resolve().parent
EDIT = HERE / "doc_edit.py"
FILE = "src/chanceblog_desktop/security/errorlog.py"

PAIRS = [
    # S5 — 속도 제한 문구(정해진 구간)와 켜는 곳 문구(시험)
    ("같은 시간에 오류가 쏟아져도(그리기 오류가 계속 되풀이될 때) 1분에 30줄까지만 쓴다.",
     "같은 시간에 오류가 쏟아져도(그리기 오류가 계속 되풀이될 때) 정해진 1분 구간마다 30줄까지만 쓴다(구간은 첫 줄이 쓰일 때 시작하고, 구간 경계에서는 짧은 시간에 더 나올 수 있다)."),
    # S4 — 돌려쓰기가 막혀도 옛 파일을 잃지 않는다
    ("(돌려쓰기에 실패하면 한도를 넘기지 않으려고 그 줄을 쓰지 않는다)",
     "(돌려쓰기에 실패하면 한도를 넘기지 않으려고 그 줄을 쓰지 않고, 옛 파일은 먼저 지우지 않으므로 가장 오래된 `.2` 도 잃지 않는다 — 이름 바꾸기가 `.2` 를 덮어쓴다)"),
    ("켜는 곳은 화면(GUI) 진입점 하나다(`security/boundary.arm_error_log` — 명령줄·예시 화면·시험은 켜지 않는다). `boundary` 의 설치를 되돌리면 함께 꺼진다.\n",
     "켜는 곳은 화면(GUI) 진입점 하나다(`security/boundary.arm_error_log` — 명령줄과 예시 화면은 켜지 않는다. `--data-dir` 없이 `launcher.main` 을 부르는 기존 시험은 켜질 수 있으나 켜기만으로는 아무것도 읽거나 만들지 않고 뒷정리로 끈다). `boundary` 의 설치를 되돌리면 함께 꺼진다.\n"
     "\n"
     "**기록이 닿지 않는 길(한계)**: 묶음 실행 파일의 시작 실패(`packaging/gui_entry.py` 의 `start_gui` 가 잡아 메시지 상자로 오류 종류 이름만 알린다)·작업 스레드(`ui/core/jobs.py`)가 삼킨 오류와 화면 콜백 안의 오류·네이티브 충돌·데이터 폴더를 풀지 못하는 경우.\n"
     "이 길들에 기록을 잇는 일은 AP14 가 바꾸는 목록 밖이라 하지 않았다(D-488 의 후속 항목).\n"),
    ('''    def _allowed(self):
        """1분에 `RATE_COUNT` 줄까지만."""''',
     '''    def _allowed(self):
        """정해진 1분 구간마다 `RATE_COUNT` 줄까지만(구간은 첫 줄이 쓰일 때 시작한다 — 구간 경계에서는 짧은 시간에 더 나올 수 있다)."""'''),
    ('''    def _rotate(self, folder):
        """`errors.log` → `.1` → `.2`(가장 오래된 것은 지운다). 한 단계라도 막히면 예외를 내서 호출한 쪽이 이 줄을 버리게 한다(한도를 넘겨 쓰지 않는다)."""
        names = [FILE_NAME] + [f"{FILE_NAME}.{number}" for number in range(1, self._backups + 1)]
        oldest = folder / names[-1]
        if oldest.exists():
            oldest.unlink()
        for index in range(len(names) - 2, -1, -1):
            source = folder / names[index]
            if source.exists():
                os.replace(source, folder / names[index + 1])
''',
     '''    def _rotate(self, folder):
        """`errors.log` → `.1` → `.2` — 이름을 바꾸는 것뿐이다: 가장 오래된 `.2` 는 먼저 지우지 않고 `os.replace` 가 덮어쓴다(먼저 지우면 이름 바꾸기가 막혔을 때 새 줄도 못 쓰고 `.2` 도 잃는다).
        한 단계라도 막히면 예외를 내서 호출한 쪽이 이 줄을 버리게 한다(한도를 넘겨 쓰지 않는다)."""
        names = [FILE_NAME] + [f"{FILE_NAME}.{number}" for number in range(1, self._backups + 1)]
        if len(names) == 1:                                            # 옛 파일을 하나도 안 남기는 설정 — 현재 파일을 비운다
            (folder / names[0]).unlink(missing_ok=True)
            return
        for index in range(len(names) - 2, -1, -1):
            source = folder / names[index]
            if source.exists():
                os.replace(source, folder / names[index + 1])
'''),
]


def run(*args):
    done = subprocess.run([sys.executable, "-X", "utf8", str(EDIT), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    print(done.stdout.strip() or done.stderr.strip())
    if done.returncode:
        raise SystemExit(done.returncode)


with tempfile.TemporaryDirectory() as folder:
    for index, (old, new) in enumerate(PAIRS):
        old_file, new_file = Path(folder) / f"old{index}.txt", Path(folder) / f"new{index}.txt"
        old_file.write_text(old, encoding="utf-8", newline="\n")
        new_file.write_text(new, encoding="utf-8", newline="\n")
        run("replace", ROOT / FILE, old_file, new_file)
