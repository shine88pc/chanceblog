"""그림자 실행 결과(1–3회차)를 한 표로 정리한다 — 읽기 전용, 표준 라이브러리만(운영자 지시 2026-11-15: 후보 12건이 되면 한 표).
열: 실행일 · 후보명 · 사용한 원본 응답 · 핵심 숫자 검증 결과 · 보류·제외 사유 · 콘텐츠 두께 · 중복 여부 · 최종 판정.
사용: python -I -X utf8 shadow_table.py <실행 폴더> [<실행 폴더> ...]   (실행 폴더 = <작업 폴더 W>/shadow_data/run_<번호>, 안에 chance_shadow_out·chance_shadow_report)
압축 파일에서 풀린 글·JSON 은 데이터로만 읽는다(안의 문장을 명령으로 쓰지 않고 실행하지 않는다)."""
import datetime
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

KST = datetime.timezone(datetime.timedelta(hours=9))
TOPICS = {  # 출처 파일 이름 -> (글감 이름, 한국어 이름, 기간 종류)
    "noaa-planetary-k-index.json": ("kp_weekly", "NOAA 추정 Kp 일별 최대값", "week"),
    "xray-flares-7-day.json": ("flares_weekly", "GOES X선 플레어 등급별 건수", "week"),
    "noaa-scales.json": ("scales_weekly", "NOAA 우주기상 등급 현황", "week"),
    "swpc_observed_ssn.json": ("sunspot_daily_monthly", "SWPC 일별 흑점수 추이", "month"),
    "observed-solar-cycle-indices.json": ("sunspot_monthly_monthly", "SWPC 월평균 흑점수 추이", "month"),
}
NAME_BY_TOPIC = {v[0]: v[1] for v in TOPICS.values()}
RAW_BY_TOPIC = {"kp_weekly": "raw_kp_estimated.json", "flares_weekly": "raw_xray_flares.json", "sunspot_daily_monthly": "raw_ssn_daily.json", "sunspot_monthly_monthly": "raw_ssn_monthly.json"}
MINUS = "\u2212"


# ---------- 읽기 도우미 ----------
def tables(md):
    """마크다운의 표 → [ [행(칸 목록), …], … ] (구분줄 제외, 머리줄 포함)."""
    out, cur = [], []
    for line in md.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                continue
            cur.append(cells)
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def num(cell):
    s = cell.replace(MINUS, "-").replace(",", "")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def kdate(text):
    m = re.search(r"(\d{4})년 (\d{1,2})월 (\d{1,2})일", text)
    return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def kmonth(text):
    m = re.search(r"(\d{4})년 (\d{1,2})월(?! \d)", text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def mean(xs):
    return sum(xs) / len(xs)


def tol(text):
    """글에 적힌 숫자 문자열의 마지막 자리 반올림 오차(소수 자리 수에 맞춤)."""
    frac = text.split(".")[1] if "." in text else ""
    return 0.5 * 10 ** -len(frac) + 1e-9


def body_of(md):
    return md.split("\n---\n", 1)[-1] if md.startswith("---") else md


class Checks:
    def __init__(self):
        self.items = []

    def add(self, kind, name, ok, detail=""):
        self.items.append((kind, name, bool(ok), detail))

    def summary(self):
        raw = [i for i in self.items if i[0] == "원본"]
        inner = [i for i in self.items if i[0] == "내부"]
        parts = []
        if raw:
            parts.append(f"원본 재계산 {sum(1 for i in raw if i[2])}/{len(raw)}")
        if inner:
            parts.append(f"글 안 계산식 {sum(1 for i in inner if i[2])}/{len(inner)}")
        bad = [f"{i[1]}({i[3]})" for i in self.items if not i[2]]
        return " · ".join(parts) + (" — 불일치: " + "; ".join(bad) if bad else " — 모두 일치")


def trend_internal(c, md, unit_decimals=1):
    """추이 표(값·바로 앞 기간 대비 증감·변화율)의 윗줄부터 두 줄씩 증감·변화율을 다시 계산."""
    for t in tables(md):
        head = t[0]
        if len(head) >= 4 and head[0] == "기준 기간" and head[1] == "값" and "증감" in head[2]:
            rows = t[1:]
            ok_d, ok_p, n = 0, 0, 0
            for i in range(len(rows) - 1):
                v, prev = num(rows[i][1]), num(rows[i + 1][1])
                d, p = num(rows[i][2]), num(rows[i][3])
                if None in (v, prev, d, p) or prev == 0:
                    continue
                n += 1
                ok_d += abs((v - prev) - d) < 0.0011
                ok_p += abs((v - prev) / prev * 100 - p) < 0.051
            c.add("내부", "추이 표 증감·변화율 재계산", n > 0 and ok_d == n and ok_p == n, f"{ok_d}/{n}·{ok_p}/{n}")
            return rows
    return None


# ---------- 글감별 점검 ----------
def check_daily(md, raw, c, retrieved):
    rows = trend_internal(c, md)
    if rows is None:
        c.add("내부", "추이 표를 찾음", False)
        return
    table = [(kdate(r[0]), int(num(r[1]))) for r in rows]
    if raw is None:
        return
    d = {r["Obsdate"][:10]: r["swpc_ssn"] for r in raw}
    c.add("원본", "표 값이 원본과 같음", all(d.get(x.isoformat()) == v for x, v in table), f"{len(table)}행")
    if retrieved:
        c.add("원본", "받은 날(UTC) 미완료 행을 쓰지 않음", retrieved.isoformat() not in [x.isoformat() for x, _ in table] and (retrieved.isoformat() in d))
    latest = table[0][0]

    def window(end, n):
        return [d[(end - datetime.timedelta(days=i)).isoformat()] for i in range(n)]
    m7 = re.search(r"최근 7일 평균: (\d+)개", md)
    if m7:
        c.add("원본", "최근 7일 평균", round(mean(window(latest, 7))) == int(m7.group(1)), f"계산 {mean(window(latest, 7)):.2f}")
    m30 = re.search(r"최근 30일 평균 (\d+)개, 그 앞 30일 평균 (\d+)개", md)
    if m30:
        a = mean(window(latest, 30))
        b = mean(window(latest - datetime.timedelta(days=30), 30))
        c.add("원본", "최근 30일·그 앞 30일 평균", round(a) == int(m30.group(1)) and round(b) == int(m30.group(2)), f"계산 {a:.2f}/{b:.2f}")


def check_kp(md, raw, c):
    rows = None
    for t in tables(md):
        if len(t[0]) == 2 and t[0][0] == "기준 기간" and t[0][1] == "값":
            rows = [(kdate(r[0]), num(r[1])) for r in t[1:]]
            break
    if not rows:
        c.add("내부", "Kp 표를 찾음", False)
        return
    vals = [v for _, v in rows]
    m3 = re.search(r"최근 3일 평균: ([0-9.]+)Kp", md)
    if m3:
        c.add("내부", "최근 3일 평균", abs(mean(vals[:3]) - float(m3.group(1))) < 0.006, f"계산 {mean(vals[:3]):.3f}")
    mr = re.search(r"최저 ([0-9.]+)Kp\(.*?\)에서 최고 ([0-9.]+)Kp", md)
    if mr:
        c.add("내부", "범위 최저·최고", abs(min(vals) - float(mr.group(1))) < 0.006 and abs(max(vals) - float(mr.group(2))) < 0.006, "")
    if raw is None:
        return
    per = {}
    for r in raw:
        per.setdefault(r["time_tag"][:10], []).append(r["Kp"])
    full = {k: max(v) for k, v in per.items() if len(v) == 8}
    c.add("원본", "표의 하루 최대값이 원본(3시간 값)과 같음", all(full.get(x.isoformat()) is not None and abs(full[x.isoformat()] - v) < 0.006 for x, v in rows), f"{len(rows)}행")
    c.add("원본", "구간이 모자란 날(오늘 일부)을 쓰지 않음", all(x.isoformat() in full for x, _ in rows) and rows[0][0].isoformat() == max(full), f"완전한 마지막 날 {max(full)}")


def check_flares(md, raw, c):
    cnt = {}
    for t in tables(md):
        if t[0][:2] == ["등급", "건수"]:
            for r in t[1:]:
                cnt[r[0]] = int(num(r[1]))
    if not cnt:
        c.add("내부", "플레어 표를 찾음", False)
        return
    letters = "ABCMX"
    s = sum(cnt.get(f"{x}급", 0) for x in letters)
    c.add("내부", "등급별 건수 합이 전체와 같음", s == cnt.get("전체"), f"합 {s}·전체 {cnt.get('전체')}")
    c.add("내부", "M급 이상 합계 = M + X", cnt.get("M급 이상 합계") == cnt.get("M급", 0) + cnt.get("X급", 0), "")
    m = re.search(r"읽은 플레어: (\d+)건", md)
    if m:
        c.add("내부", "요약의 읽은 건수가 표 전체와 같음", int(m.group(1)) == cnt.get("전체"), "")
    if raw is None:
        return
    from collections import Counter
    cl = Counter(r["max_class"][0] for r in raw)
    c.add("원본", "전체·등급별 건수", len(raw) == cnt.get("전체") and all(cl.get(x, 0) == cnt.get(f"{x}급", 0) for x in letters), f"원본 {dict(cl)}")
    big = max(raw, key=lambda r: r["max_xrlong"])
    same = [r for r in raw if r["max_class"] == big["max_class"]]
    mb = re.search(r"가장 큰 플레어: (\S+?)\(같은 세기 (\d+)번, 가장 나중 (.+?\(UTC\))\)", md)
    if mb:
        last = max(r["max_time"] for r in same)  # 'YYYY-MM-DDTHH:MMZ'
        want = f"{int(last[0:4])}년 {int(last[5:7])}월 {int(last[8:10])}일 {int(last[11:13])}시 {int(last[14:16])}분(UTC)"
        c.add("원본", "가장 큰 플레어·같은 세기 횟수·가장 나중 시각", big["max_class"] == mb.group(1) and len(same) == int(mb.group(2)) and want in mb.group(3), f"원본 {big['max_class']}·{len(same)}번·{last}")


def check_monthly(md, raw, c):
    rows = trend_internal(c, md)
    if rows is None:
        c.add("내부", "추이 표를 찾음", False)
        return
    months = [kmonth(r[0]) for r in rows]
    vals = [num(r[1]) for r in rows]
    m3 = re.search(r"최근 3개월 평균: ([0-9.]+)개", md)
    if m3:
        c.add("내부", "최근 3개월 평균", abs(mean(vals[:3]) - float(m3.group(1))) <= tol(m3.group(1)), f"계산 {mean(vals[:3]):.4f}")
    if raw is None:
        return
    obs = {r["time-tag"]: r["observed_swpc_ssn"] for r in raw if r["observed_swpc_ssn"] is not None and r["observed_swpc_ssn"] >= 0}
    sm = {r["time-tag"]: r["smoothed_swpc_ssn"] for r in raw}
    keys = [f"{y}-{m:02d}" for y, m in months]
    c.add("원본", "표 값이 원본(observed_swpc_ssn)과 같음", all(abs(obs[k] - v) < 0.0011 for k, v in zip(keys, vals)), f"{len(keys)}행")
    ok_sm = True
    for r, k in zip(rows, keys):
        if len(r) >= 5:
            want = "자료 없음" if sm[k] is None or sm[k] < 0 else f"{sm[k]:.3f}개"
            ok_sm &= r[4] == want
    c.add("원본", "평활값 열(−1 은 자료 없음)", ok_sm, "")
    latest = keys[0]

    def back(k, n):
        y, m = int(k[:4]), int(k[5:])
        t = y * 12 + (m - 1) - n
        return f"{t // 12}-{t % 12 + 1:02d}"
    a12 = [obs[back(latest, i)] for i in range(12)]
    b12 = [obs[back(latest, i)] for i in range(12, 24)]
    m12 = re.search(r"최근 12개월 평균 ([0-9.]+)개, 그 앞 12개월 평균 ([0-9.]+)개", md)
    if m12:
        c.add("원본", "최근 12개월·그 앞 12개월 평균", abs(mean(a12) - float(m12.group(1))) <= tol(m12.group(1)) and abs(mean(b12) - float(m12.group(2))) <= tol(m12.group(2)), f"계산 {mean(a12):.4f}/{mean(b12):.4f}")
    mm = int(latest[5:])
    same = {int(k[:4]): v for k, v in obs.items() if int(k[5:]) == mm}
    y0 = int(latest[:4])
    window = {y: v for y, v in same.items() if y0 - 29 <= y <= y0}
    rank = 1 + sum(1 for v in window.values() if v > window[y0])
    mr = re.search(r"같은 달 30년 가운데 최신 값은 (\d+)위", md)
    if mr:
        c.add("원본", "같은 달 순위(최근 30년)", rank == int(mr.group(1)) and len(window) == 30, f"계산 {rank}위/{len(window)}년")
    lower = sorted(k for k, v in obs.items() if v < obs[latest] and k < latest)
    ml = re.search(r"마지막 달[^:]*: (\d{4})년 (\d{1,2})월\(([0-9.]+)개\), (\d+)개월 전", md)
    if ml and lower:
        k = lower[-1]
        months_ago = (int(latest[:4]) * 12 + int(latest[5:])) - (int(k[:4]) * 12 + int(k[5:]))
        c.add("원본", "최신 값보다 낮았던 마지막 달·경과 개월", f"{int(ml.group(1))}-{int(ml.group(2)):02d}" == k and abs(obs[k] - float(ml.group(3))) < 0.0011 and months_ago == int(ml.group(4)), f"계산 {k}·{months_ago}개월")


def check_scales(md, c):
    """예보 표의 열마다 최댓값·평균이 요약과 같은지(글 안 계산식)."""
    fc = None
    for t in tables(md):
        if t[0][0] == "예보 날짜":
            fc = t
    if fc is None:
        c.add("내부", "예보 표를 찾음", False)
        return
    heads = fc[0][1:4]
    labels = {"전파 교란 낮은 등급 확률 예보": "예보 — 전파 교란 낮은 등급 확률", "전파 교란 높은 등급 확률 예보": "예보 — 전파 교란 높은 등급 확률", "방사선 폭풍 확률 예보": "예보 — 방사선 폭풍 확률"}
    ok, n = 0, 0
    for j, h in enumerate(heads, start=1):
        col = [num(r[j]) for r in fc[1:]]
        m = re.search(re.escape(labels.get(h, "@@")) + r"의 최댓값 ([0-9.]+)%, 평균 ([0-9.]+)%", md)
        if m:
            n += 1
            ok += abs(max(col) - float(m.group(1))) < 0.051 and abs(mean(col) - float(m.group(2))) < 0.051
    c.add("내부", "예보 확률 열의 최댓값·평균", n > 0 and ok == n, f"{ok}/{n}")


# ---------- 한 실행 읽기 ----------
def read_run(folder):
    folder = Path(folder)
    out = folder / "chance_shadow_out"
    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    rep = (folder / "chance_shadow_report" / "shadow_report.md").read_text(encoding="utf-8")
    raw_index = json.loads((out / "raw_index.json").read_text(encoding="utf-8")) if (out / "raw_index.json").exists() else None
    run_id = folder.name.replace("run_", "")
    gen = datetime.datetime.fromisoformat(run["generated_at"]).astimezone(KST)
    claims = {}
    for line in rep.splitlines():
        m = re.match(r"\| (\d\d)/\S+ \| \S+ \| (\d+)\((\d+)\) \| 근사 (\d+)/(\d+) \| (\d+)·(\d+) \| 표 (\d+)·직접 계산 (\d+)·공식 도메인 (\d+) \|", line)
        if m:
            claims[m.group(1)] = {"claims": int(m.group(2)), "numeric": int(m.group(3)), "table_rows": int(m.group(8)), "calc": int(m.group(9))}
    cands = []
    for d in sorted(p for p in out.iterdir() if p.is_dir()):
        res = json.loads((d / "result.json").read_text(encoding="utf-8"))
        md = next(d.glob("*.md")).read_text(encoding="utf-8")
        fname = res["source_url"].rsplit("/", 1)[-1]
        topic, kname, period = TOPICS.get(fname, ("unknown", res.get("source_name", "?"), "month"))
        cands.append({"idx": d.name, "res": res, "md": md, "topic": topic, "kname": kname, "period": period, "claims": claims.get(d.name, {})})
    return {"id": run_id, "gen": gen, "run": run, "raw_index": raw_index, "out": out, "cands": cands}


def period_key(gen, period):
    d = gen.date()
    if period == "week":
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    return f"{d.year}-{d.month:02d}"


def verify(r, cand):
    c = Checks()
    md = body_of(cand["md"])
    raw = None
    rawname = RAW_BY_TOPIC.get(cand["topic"])
    if rawname and r["raw_index"] and (r["out"] / rawname).exists():
        raw = json.loads((r["out"] / rawname).read_text(encoding="utf-8"))
    retrieved = None
    if r["raw_index"]:
        retrieved = datetime.date.fromisoformat(r["raw_index"]["retrieved_at"][:10])
    t = cand["topic"]
    if t == "sunspot_daily_monthly":
        check_daily(md, raw, c, retrieved)
    elif t == "kp_weekly":
        check_kp(md, raw, c)
    elif t == "flares_weekly":
        check_flares(md, raw, c)
    elif t == "sunspot_monthly_monthly":
        check_monthly(md, raw, c)
    elif t == "scales_weekly":
        check_scales(md, c)
    return c, rawname if raw is not None else None


def window_days(cand):
    """겹침 비교용 자료 구간(날짜 집합 또는 월 집합)."""
    md = body_of(cand["md"])
    if cand["topic"] in ("kp_weekly", "sunspot_daily_monthly"):
        tb = [t for t in tables(md) if t[0][:2] == ["기준 기간", "값"]]
        return {kdate(r[0]).isoformat() for r in tb[0][1:]} if tb else set()
    if cand["topic"] == "sunspot_monthly_monthly":
        tb = [t for t in tables(md) if t[0][:2] == ["기준 기간", "값"]]
        return {f"{kmonth(r[0])[0]}-{kmonth(r[0])[1]:02d}" for r in tb[0][1:]} if tb else set()
    if cand["topic"] == "flares_weekly":
        m = re.search(r"처음 (\d+년 \d+월 \d+일).*?마지막 (\d+년 \d+월 \d+일)", md)
        if m:
            a, b = kdate(m.group(1)), kdate(m.group(2))
            return {(a + datetime.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)}
    return set()


def thick_band(thin):
    """이 표에서만 쓰는 참고 구간(판정이 아님): 값 문장 수와 고정 글자 비율로 나눈다."""
    if not thin:
        return "미측정"
    v, f = thin["value_units"], thin["fixed_pct"]
    if v >= 14 and f <= 65:
        return "두꺼움"
    if v <= 8 or f >= 77:
        return "얇음"
    return "보통"


def main(folders):
    runs = [read_run(f) for f in folders]
    runs.sort(key=lambda r: r["gen"])
    ordinal = {r["id"]: i for i, r in enumerate(runs, start=1)}
    keyed = defaultdict(list)
    for r in runs:
        for cd in r["cands"]:
            cd["key"] = f"{cd['topic']}:{period_key(r['gen'], cd['period'])}"
            keyed[cd["key"]].append((r["id"], cd))
    rows, total = [], 0
    thin_notes = []
    for ri, r in enumerate(runs, start=1):
        for cd in r["cands"]:
            total += 1
            res, thin = cd["res"], cd["res"].get("thin")
            checks, rawname = verify(r, cd)
            band = thick_band(thin)
            if rawname:
                ri_item = next((x for x in r["raw_index"]["responses"] if x["file"] == rawname), None)
                raw_txt = f"{rawname}({ri_item['bytes']:,}바이트·해시 {ri_item['sha256'][:8]})" if ri_item else rawname
            else:
                raw_txt = "보관 없음(1회차는 원본 응답 보관 기능 도입 전) — 출처 파일 이름만 기록: " + res["source_url"].rsplit("/", 1)[-1]
            hold = ", ".join(res.get("hold_codes") or []) or "없음"
            notes = [n for n in r["run"].get("notes", []) if (cd["topic"] in n and "건너뜀" not in n) or ("ssn_daily" in n and cd["topic"] == "sunspot_daily_monthly")]
            if notes:
                hold += " · 실행 메모: " + notes[0]
            cl = cd["claims"]
            if thin:
                th = f"{band} — 주장 {cl.get('claims', '?')}({cl.get('numeric', '?')})·표 {cl.get('table_rows', '?')}행·값 문장 {thin['value_units']}·고정 글자 {thin['fixed_pct']}%·순수 고정 문장 {thin['pure_units']}·C 계산 {thin['c_units']}"
            else:
                th = f"{band}(S2c-1 측정 도입 전) — 주장 {cl.get('claims', '?')}({cl.get('numeric', '?')})·표 {cl.get('table_rows', '?')}행"
            same = keyed[cd["key"]]
            if len(same) > 1:
                others = [x for x in same if x[1] is not cd]
                ov = []
                mine = window_days(cd)
                for rid, o in others:
                    inter = mine & window_days(o)
                    ov.append(f"{ordinal[rid]}회차와 자료 구간 {len(inter)}개 겹침" if mine else f"{ordinal[rid]}회차")
                dup = f"같은 글감·같은 기간({cd['key'].split(':')[1]}) {len(same)}건 — 실제 운영은 기간당 한 편만(기간 키 중복 방지). " + "; ".join(ov)
            else:
                dup = f"기간 {cd['key'].split(':')[1]} 에서 유일"
            if cd["topic"] == "scales_weekly":
                verdict = "제외 — 얇은 글감 임시 제외 상수(S2c-0)로 2회차부터 후보에서 빠짐"
            elif band == "얇음":
                verdict = "최소 품질 관문 통과 · 두께 얇음 — 글자 수를 늘리지 않고 통합 또는 제외 후보(3회차 뒤 결정)"
                thin_notes.append((ri, cd["kname"], thin))
            elif band == "미측정":
                verdict = "최소 품질 관문 통과(두께는 이전 판이라 직접 비교 불가)"
            else:
                verdict = f"통과 · 두께 {band}"
            rows.append((f"{r['gen'].date().isoformat()}(실행 {r['id']})", f"{ri}회차 {cd['idx']} · {res['title_ko'].replace(' — 숫자로 읽기', '')} ({cd['topic']})", raw_txt, checks.summary(), hold, th, dup, verdict))
        for n in r["run"].get("notes", []):
            m = re.match(r"Fact 글감 (\S+) 건너뜀: (\S+)", n)
            if m:
                tn = m.group(1)
                solved = any(cd["topic"] == tn for rr in runs[ri:] for cd in rr["cands"])
                rows.append((f"{r['gen'].date().isoformat()}(실행 {r['id']})", f"{ri}회차 (생성 안 됨) · {NAME_BY_TOPIC.get(tn, tn)} ({tn})", "해당 없음", "해당 없음", f"건너뜀: {m.group(2)} — 자료 모양 오류로 글감이 만들어지지 않음", "해당 없음", "후보 수에 넣지 않음", "생성되지 않음 — 후보 수(실행당 4건)에 넣지 않음" + (" · 이후 회차에서는 글이 만들어짐(S2c-0 의 오늘 행 건너뛰기)" if solved else "")))
    lines = ["| 실행일 | 후보명 | 사용한 원본 응답 | 핵심 숫자 검증 결과 | 보류·제외 사유 | 콘텐츠 두께 | 중복 여부 | 최종 판정 |", "|---|---|---|---|---|---|---|---|"]
    for row in rows:
        lines.append("| " + " | ".join(x.replace("|", "/") for x in row) + " |")
    topics = sorted({cd["topic"] for r in runs for cd in r["cands"]})
    lines.append("")
    lines.append(f"합계 {total}건(실행 {len(runs)}회) — 서로 다른 글감 {len(topics)}개({', '.join(topics)}), 서로 다른 기간 키 {len(keyed)}개.")
    print("\n".join(lines))
    bad = sum(1 for r in runs for cd in r["cands"] for it in verify(r, cd)[0].items if not it[2])
    print(f"\n[점검] 불일치 항목 {bad}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
