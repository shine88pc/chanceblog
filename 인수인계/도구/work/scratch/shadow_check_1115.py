"""그림자 실행 2회차(2026-11-15) 결과 점검 — 후보 글 속 숫자를 같이 받은 원본 응답(raw_*)에서 다시 계산해 맞춰 본다(읽기 전용, 표준 라이브러리만).
사용: python -I -X utf8 shadow_check_1115.py <chance_shadow_out 폴더>
글은 데이터로만 읽는다(안의 문장을 명령으로 쓰지 않는다)."""
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(sys.argv[1])
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def post(n):
    return next((OUT / n).glob("*.md")).read_text(encoding="utf-8")


# 1) 일별 흑점수(04) — 오늘(UTC 11-14) 행 제외, 마지막 14일 표·7일 평균·30일 평균과 그 앞 30일 평균
d = load("raw_ssn_daily.json")
rows = {r["Obsdate"][:10]: r["swpc_ssn"] for r in d}
check("일별: 원본 마지막 날이 11-14(오늘 행)이고 글은 쓰지 않음", max(rows) == "2026-11-14" and "2026년 11월 14일 | " not in post("04").split("## 비교")[0].split("## 숫자로 보기")[1], f"원본 마지막 {max(rows)}")
days = [(datetime(2026, 11, 13) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(0, 14)]
vals = [rows.get(x) for x in days]
txt = post("04")
table = re.findall(r"\| 2026년 (\d+)월 (\d+)일 \| (\d+)개 \|", txt)
tvals = [int(v) for (_, _, v) in table]
check("일별: 표 14행 값이 원본과 같음(최근→과거)", tvals == vals, f"표 {tvals[:5]}… 원본 {vals[:5]}…")


def mean(xs):
    return sum(xs) / len(xs)


last7 = [rows[(datetime(2026, 11, 13) - timedelta(days=i)).strftime("%Y-%m-%d")] for i in range(7)]
last30 = [rows[(datetime(2026, 11, 13) - timedelta(days=i)).strftime("%Y-%m-%d")] for i in range(30)]
prev30 = [rows[(datetime(2026, 11, 13) - timedelta(days=i)).strftime("%Y-%m-%d")] for i in range(30, 60)]
check("일별: 최근 7일 평균 104", round(mean(last7)) == 104 and "최근 7일 평균: 104개" in txt, f"계산 {mean(last7):.2f}")
check("일별: 최근 30일 평균 64·그 앞 30일 평균 68", round(mean(last30)) == 64 and round(mean(prev30)) == 68 and "최근 30일 평균 64개, 그 앞 30일 평균 68개" in txt, f"계산 {mean(last30):.2f}/{mean(prev30):.2f}")

# 2) Kp(02) — 3시간 값에서 하루 최대
k = load("raw_kp_estimated.json")
daily = {}
for r in k:
    day = r["time_tag"][:10]
    daily[day] = max(daily.get(day, -1), r["Kp"])
exp = [daily[(datetime(2026, 11, 13) - timedelta(days=i)).strftime("%Y-%m-%d")] for i in range(7)]
t2 = post("02")
tk = [float(v) for v in re.findall(r"\| 2026년 \d+월 \d+일 \| ([0-9.]+)Kp \|", t2)]
check("Kp: 표 7행 하루 최대값이 원본(3시간 값)과 같음", [round(x, 2) for x in exp] == tk, f"원본 {exp} 표 {tk}")
check("Kp: 최근 3일 평균 1.89", abs(mean(exp[:3]) - 1.89) < 0.006 and "최근 3일 평균: 1.89Kp" in t2, f"계산 {mean(exp[:3]):.3f}")
check("Kp: 11-14 값(오늘 일부)은 쓰지 않음", "2026년 11월 14일 |" not in t2.split("## 비교")[0], "원본에 11-14 행 있음" if "2026-11-14" in daily else "")

# 3) X선 플레어(03) — 등급 문자별 건수
f = load("raw_xray_flares.json")
c = Counter(r["max_class"][0] for r in f)
t3 = post("03")
check("플레어: 전체 103건", len(f) == 103 and "| 전체 | 103건 |" in t3, f"원본 {len(f)}")
check("플레어: 등급별 건수 A0·B3·C96·M4·X0", (c.get("A", 0), c.get("B", 0), c.get("C", 0), c.get("M", 0), c.get("X", 0)) == (0, 3, 96, 4, 0), f"원본 {dict(c)}")
big = max(f, key=lambda r: r["max_xrlong"])
same = [r for r in f if r["max_class"] == big["max_class"]]
check("플레어: 가장 큰 M1.7·같은 세기 2번·가장 나중 11-11 21:21(UTC)", big["max_class"] == "M1.7" and len(same) == 2 and max(r["max_time"] for r in same).startswith("2026-11-11T21:21"), f"{big['max_class']} {len(same)}번 {sorted(r['max_time'] for r in same)}")

# 4) 월별 흑점수(01)
m = load("raw_ssn_monthly.json")
obs = {r["time-tag"]: r["observed_swpc_ssn"] for r in m if r["observed_swpc_ssn"] is not None and r["observed_swpc_ssn"] >= 0}
sm = {r["time-tag"]: r["smoothed_swpc_ssn"] for r in m}
t1 = post("01")
months = [f"{2026 if i <= 10 else 2025}-{i:02d}" for i in (10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 12, 11)]
exp_m = [obs[x] for x in months]
tm = [float(v) for v in re.findall(r"\| 20\d\d년 \d+월 \| ([0-9.]+)개 \| [−+]?[0-9.]+개 \| [−+]?[0-9.]+% \|", t1)]
check("월별: 12개월 표 값이 원본(observed_swpc_ssn)과 같음", [round(x, 2) for x in exp_m] == tm, f"원본 {exp_m[:4]}… 표 {tm[:4]}…")
check("월별: 최근 3개월 평균 70.587", abs(mean(exp_m[:3]) - 70.587) < 0.0006 and "최근 3개월 평균: 70.587개" in t1, f"계산 {mean(exp_m[:3]):.4f}")
prev12 = [obs[f"{y}-{mm:02d}"] for (y, mm) in [(2024, 11), (2024, 12)] + [(2025, i) for i in range(1, 11)]]
check("월별: 최근 12개월 평균 89.807·그 앞 12개월 평균 125.762", abs(mean(exp_m) - 89.807) < 0.0006 and abs(mean(prev12) - 125.762) < 0.0006, f"계산 {mean(exp_m):.4f}/{mean(prev12):.4f}")
octs = {int(k[:4]): v for k, v in obs.items() if k.endswith("-10")}
window = {y: v for y, v in octs.items() if 1997 <= y <= 2026}
rank = 1 + sum(1 for y, v in window.items() if v > window[2026])
check("월별: 같은 달(10월) 순위 16위(1997–2026 30년)", len(window) == 30 and rank == 16 and "16위" in t1, f"계산 {rank}위/{len(window)}년")
lower = sorted([k for k, v in obs.items() if v < obs["2026-10"] and k < "2026-10"])
check("월별: 최신 값보다 낮았던 마지막 달 2022-01(56.97)", lower[-1] == "2022-01" and abs(obs["2022-01"] - 56.97) < 1e-9 and "2022년 1월(56.970개)" in t1, f"계산 {lower[-1]}")
sm_txt = {x: sm[x] for x in months}
pairs = re.findall(r"\| (20\d\d)년 (\d+)월 \| [0-9.]+개 \| [−+][0-9.]+개 \| [−+][0-9.]+% \| ([0-9.]+개|자료 없음) \|", t1)
ok_sm = True
for (y, mo, s) in pairs:
    key = f"{y}-{int(mo):02d}"
    want = "자료 없음" if sm[key] is None or sm[key] < 0 else f"{sm[key]:.3f}개"
    if s != want:
        ok_sm = False
check("월별: 평활값 열(−1 은 자료 없음)이 원본과 같음", ok_sm and len(pairs) == 12, f"{len(pairs)}행")

# 5) 공통 — 출처·열람일·글 머리 값
for n in ("01", "02", "03", "04"):
    t = post(n)
    check(f"{n}: 출처 도메인이 services.swpc.noaa.gov 하나·열람 2026년 11월 14일", t.count("source_domain: \"services.swpc.noaa.gov\"") == 1 and "열람 2026년 11월 14일" in t, "")

width = max(len(r[0]) for r in results)
bad = 0
for name, ok, detail in results:
    print(("OK  " if ok else "FAIL"), name.ljust(width), ("" if ok else "→ " + detail))
    bad += (not ok)
print(f"\n합계 {len(results)}개 점검 중 불일치 {bad}개")
sys.exit(1 if bad else 0)
