"""이 PC 의 지금 사정(다른 사용자 접속·CPU·여유 메모리·시각)을 보고 '지금 동시에 돌려도 되는 에이전트 수'를 한 줄로 권한다(총괄 전용, 읽기만).
운영자 지시: 2026-11-23 아침 채팅(공용 PC — 중간 수준) → 같은 날 09:20 이슈 #246(탄력 운영 — 5개 이상도 괜찮고 매일 17–18시부터는 다른 사용자가 거의 없으니 최대한 활용).
사용: py -3.12 -X utf8 C:/work/ai/scratch/pc_load.py        (에이전트를 새로 띄우거나 무거운 시험을 돌리기 전에 한 번 본다)
규칙(권고일 뿐 — 총괄이 판단):
  · (2026-11-23 13:10 운영자 지시로 한 단계 느슨하게 — 이전 값은 괄호)
  · 다른 사람이 지금 쓰는 중(다른 접속이 '활성'이고 유휴 30분 미만)이면: 낮 3명(2)·17시 이후 4명(3)
  · 다른 사람이 없고 CPU 65% 미만(50)·여유 메모리 4GB 이상(5)이면: 낮 6명(5)·17시 이후 9명(8)
  · 다른 사람이 없지만 CPU 가 바쁘거나 메모리가 모자라면: 4명(3)
  · 안전판(그대로): CPU 85% 이상이거나 여유 메모리 3GB 미만이면 무조건 2명 이하
접속 목록은 `quser`(윈도) — 사용자 이름은 출력하지 않고 개수만 센다."""
import re
import subprocess
import sys
import time


def run(cmd, shell=False):
    done = subprocess.run(cmd, capture_output=True, shell=shell)
    for enc in ("cp949", "utf-8"):
        try:
            return done.stdout.decode(enc)
        except UnicodeDecodeError:
            continue
    return done.stdout.decode("utf-8", "replace")


def sessions():
    """(전체 접속 수, 다른 사람의 활성 접속 수) — `>` 표시가 내 접속이다."""
    out = run(["quser"]).splitlines()
    rows = [ln for ln in out[1:] if ln.strip()]
    total = len(rows)
    others_active = 0
    for ln in rows:
        if ln.lstrip().startswith(">"):
            continue
        disc = re.search(r"\bDisc\b|연결 끊김|끊김", ln) is not None
        idle = re.search(r"\s(\d+\+)?(\d+:)?\d+\s{2,}\d{4}-", ln)
        idle_txt = idle.group(0).strip().split()[0] if idle else "."
        idle_min = 0
        if idle_txt != "." and idle_txt.lower() != "none":
            m = re.match(r"(?:(\d+)\+)?(?:(\d+):)?(\d+)$", idle_txt)
            if m:
                days, hours, mins = int(m.group(1) or 0), int(m.group(2) or 0), int(m.group(3) or 0)
                idle_min = days * 1440 + hours * 60 + mins
        if not disc and idle_min < 30:
            others_active += 1
    return total, others_active


def cpu_percent():
    vals = []
    for _ in range(3):
        out = run(["powershell", "-NoProfile", "-Command",
                   "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average"]).strip()
        try:
            vals.append(float(out))
        except ValueError:
            pass
        time.sleep(0.7)
    return sum(vals) / len(vals) if vals else -1.0


def mem_free_gb():
    out = run(["powershell", "-NoProfile", "-Command",
               "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"]).strip()
    try:
        return float(out) / 1024 / 1024
    except ValueError:
        return -1.0


def main():
    total, others = sessions()
    cpu, mem = cpu_percent(), mem_free_gb()
    hour = time.localtime().tm_hour
    evening = hour >= 17
    if others > 0:
        cap, why = (4 if evening else 3), "다른 사람이 지금 쓰는 중"
    elif cpu >= 65 or (0 <= mem < 4):
        cap, why = 4, "다른 사람은 없지만 CPU·메모리 여유가 크지 않음"
    else:
        cap, why = (9 if evening else 6), "다른 사람이 없고 여유가 있음"
    if cpu >= 85 or (0 <= mem < 3):
        cap, why = min(cap, 2), "안전판(CPU 85% 이상 또는 여유 메모리 3GB 미만)"
    print(f"{time.strftime('%H:%M')} · 접속 {total}개(다른 사람 활성 {others}) · CPU {cpu:.0f}% · 여유 메모리 {mem:.1f}GB · "
          f"{'저녁(17시 이후)' if evening else '낮'} → 권고 에이전트 {cap}명 이하 [{why}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
