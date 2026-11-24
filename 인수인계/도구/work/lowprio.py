"""낮은 우선순위(BELOW_NORMAL)로 명령을 돌린다 — 이 PC 는 다른 사용자도 쓰므로 시험·퍼징·변이는 이것으로 감싼다(2026-11-23 운영자 지시: 성능을 중간 이상으로만).
자식 프로세스도 같은 우선순위를 물려받는다(윈도 규칙). 표준 입출력은 그대로 이어진다.
사용: python -X utf8 lowprio.py <명령> [인자 ...]   (종료 코드는 명령의 것을 그대로 돌려준다)"""
import subprocess
import sys

BELOW_NORMAL_PRIORITY_CLASS = 0x00004000

if len(sys.argv) < 2:
    sys.exit("사용: lowprio.py <명령> [인자 ...]")
sys.exit(subprocess.run(sys.argv[1:], creationflags=BELOW_NORMAL_PRIORITY_CLASS).returncode)
