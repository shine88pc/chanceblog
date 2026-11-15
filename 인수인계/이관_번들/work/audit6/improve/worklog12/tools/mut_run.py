"""변이 시험 — 작업 폴더의 사본(mut_tree)에서 문서를 일부러 틀리게 고쳐 점검 도구(사실 점검·새 줄 점검·기존 시험)가 빨개지는지 본다.

사용: python -X utf8 mut_run.py [이름 앞부분 ...]   (생략하면 전부)
사본의 자리표(@@)는 견본 값으로 채운 기준 사본에서 시작한다. 마지막에 사본의 두 문서가 기준과 sha256 이 같게 원복됐는지와 작업 폴더가 그대로인지 확인한다.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

WT = "C:/work/ai/improve_wt_worklog12"
MUT = "C:/work/ai/audit6/improve/worklog12/mut_tree"
TOOLS = "C:/work/ai/audit6/improve/worklog12/tools"
LOG = "C:/work/ai/audit6/improve/worklog12/mut_log.jsonl"
FREEZE = "C:/work/ai/audit6/improve/worklog12/freeze.json"
PY = "<사용자폴더>/AppData/Local/Programs/Python/Python312/python.exe"
DOC, WL = "인수인계/작업내용.md", "WORKLOG.md"
SAMPLES = {"@@END_HM@@": "20시 00분", "@@T_REF@@": "19:50", "@@NEWLINES@@": "150", "@@TESTS@@": "시험 줄 견본"}

# (이름, 항목, 파일, 옛 글, 새 글, 방식, 탐지기 목록)  — 탐지기: verify · check · test:<모듈>
MUTATIONS = [
    ("a1_header_hash", "W12-a", DOC, "`main` d503c1b([M065] 2026-11-13 17:25 병합", "`main` d503c1c([M065] 2026-11-13 17:25 병합", "once", ["verify"]),
    ("a2_limits_phrase", "W12-a", DOC, "① 병합은 운영자만 합니다(병합 부탁 → 운영자 병합 → AI 가 공개 기록으로 직접 확인).", "① 병합은 AI 가 합니다(병합 부탁 → 병합 → 확인).", "once", ["verify"]),
    ("a3_section07", "W12-a", DOC, "### 0-7. 혼자 이어 가는 길 — 운영자가 세션을 못 볼 때 (2026-11-13 저녁)", "### 0-7. 이어 가기", "once", ["verify"]),
    ("a4_next_numbers", "W12-a", DOC, "가 `M067`·`P056`·확인 `015`(승인 질문 묶음용", "가 `M066`·`P055`·확인 `014`(승인 질문 묶음용", "once", ["verify"]),
    ("a5_pinned_tgstd", "W12-a", DOC, "알림 번호(TG-STD, 운영자 승인 2026-11-06)", "알림 번호 TG-STD, 운영자 승인 2026-11-06)", "once", ["test:test_notice_requests"]),
    ("a6_placeholder", "W12-a", DOC, "(2026-11-13 저녁 스냅샷 — 20:01 확인, 문서 작성 시점 값)", "(2026-11-13 저녁 스냅샷 — @@T_REF@@ 확인, 문서 작성 시점 값)", "once", ["verify", "check"]),
    ("a7_item17_chat", "W12-a", DOC, "**운영자의 말로 인정하는 것은 저장소 소유자 계정이 올린 이슈뿐**이고", "**운영자의 말로 인정하는 것은 누가 올렸든 이슈 전부**이고", "once", ["verify"]),
    ("b1_merge_table_hash", "W12-b", DOC, "| 11-13 17:25 (main d503c1b) |", "| 11-13 17:25 (main d503c1c) |", "once", ["verify"]),
    ("b2_alert_time", "W12-b", DOC, "| R-314 | 17:24 |", "| R-314 | 17:29 |", "once", ["verify"]),
    ("b3_last_line", "W12-b", DOC, "- **마지막 갱신 이후 추가(", "- **추가 메모(", "once", ["verify"]),
    ("b4_tilde", "W12-b", DOC, "| R-316 | 17:57 | 진행 현황 P054 |", "| R-316 | 17:57 | 진행 현황 P054 ~ |", "once", ["check"]),
    ("b5_table_columns", "W12-b", DOC, "| AP5 | '계산이 값을 더하는 글' 판정 기준 | F104 | 결정 |", "| AP5 | '계산이 값을 더하는 글' 판정 기준 | F104 결정 |", "once", ["verify", "check"]),
    ("b6_old_name", "W12-b", DOC, "| R-306 | 13:17 | 병합완료 확인 M064 | 정상 |", "| R-306 | 13:17 | 병합완료 확인 M064 | 정상 (Guardrails) |", "once", ["check", "test:test_workflow_names"]),
    ("b7_const_digits", "W12-b", DOC, "| R-304 | 13:00 | 병합 부탁 M064(앱) | Package 빌드 수정 PCFIX1 |", "| R-304 | 13:00 | 병합 부탁 M064(앱) | Package 빌드 수정 PCFIX1 NOTICE_NO_REQUIRED_FROM_R=171 |", "once", ["test:test_notice_requests"]),
    ("b8_backlog_size", "W12-b", DOC, "(검증자도 과장으로 판정) 8묶음에 넣지 않았고", "(검증자도 과장으로 판정)" + "가" * 4200 + " 8묶음에 넣지 않았고", "once", ["verify"]),
    ("b9_url", "W12-b", DOC, "| R-312 | 16:27 | 진행 현황 P052 |", "| R-312 | 16:27 | 진행 현황 P052 http://example.test |", "once", ["check"]),
    ("c1_live_numbers", "W12-c", DOC, "공개 글 38편·사이트맵 45·피드 38(감사로", "공개 글 39편·사이트맵 45·피드 38(감사로", "once", ["verify"]),
    ("c2_worklog_heading", "W12-c", WL, "현행화 12차(WORKLOG12)", "현행화", "first", ["verify"]),
    ("c3_pinned_photo", "W12-c", DOC, "Blogger 대표 사진", "Blogger 메인 사진", "all", ["test:test_main_image_run"]),
    ("c4_pinned_reserve", "W12-c", DOC, "텔레그램 수신 '예약 읽기'", "텔레그램 수신 예약 읽기", "once", ["test:test_telegram_inbox_docs"]),
    ("c5_worklog_sections", "W12-c", WL, "### 남은 이슈 / 다음 AI 주의", "### 남은 이슈", "first", ["verify"]),
    ("c6_missing_row", "W12-c", DOC, "| M061 | R-295 | 블로그 #187 |", "| X061 | R-295 | 블로그 #187 |", "once", ["verify"]),
    ("c7_kind_mismatch", "W12-c", DOC, "| R-309 | 14:17 | 확인 013(할 일) |", "| R-309 | 14:17 | 확인 014(할 일) |", "once", ["verify"]),
    ("c9_m066_row", "W12-c", DOC, "| 11-13 19:41 (main bbe5bb7) |", "| 11-13 19:14 (main bbe5bb7) |", "once", ["verify"]),
    ("c10_alert_kind", "W12-c", DOC, "| R-318 | 19:47 | 진행 현황 P055 |", "| R-318 | 19:47 | 진행 현황 P054 |", "once", ["verify"]),
    ("c8_worklog_pinned_tgstd", "W12-c", WL, "## [2026-11-06] Claude – TG-STD", "## [2026-11-06] Claude – TGSTD", "once", ["test:test_notice_requests"]),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def read(path):
    with open(path, "r", encoding="utf-8", newline="") as h:
        return h.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as h:
        h.write(text)


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr)


def detect(kind):
    if kind == "verify":
        rc, out = run([sys.executable, "-X", "utf8", TOOLS + "/verify_worklog12.py", "--root", MUT, "--quiet"] + (["--skip-git"] if os.environ.get("SKIP_GIT") else []) + (["--freeze", FREEZE] if os.path.exists(FREEZE) else []))
    elif kind == "check":
        rc, out = run([sys.executable, "-X", "utf8", TOOLS + "/check_new_lines.py", MUT])
    else:
        mod = kind.split(":")[1]
        subprocess.run([sys.executable, "-X", "utf8", "C:/work/ai/audit6/n2/tools/memfree.py", "0.5"], capture_output=True)
        rc, out = run([PY, "-X", "utf8", "-B", "-m", "unittest", "discover", "-s", "tests", "-p", mod + ".py"], cwd=MUT)
    return rc, out


def main():
    want = sys.argv[1:]
    wt_hash = {f: sha(WT + "/" + f) for f in (DOC, WL)}
    if os.path.exists(MUT):
        shutil.rmtree(MUT, ignore_errors=True)
    shutil.copytree(WT, MUT, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    base = {}
    for f in (DOC, WL):
        text = read(MUT + "/" + f)
        for k, v in SAMPLES.items():
            text = text.replace(k, v)
        write(MUT + "/" + f, text)
        base[f] = text
    base_hash = {f: sha(MUT + "/" + f) for f in (DOC, WL)}
    print("기준 사본 만듦(자리표는 견본 값) —", {k: v[:10] for k, v in base_hash.items()})
    # 기준 점검
    for kind in ("verify", "check", "test:test_notice_requests", "test:test_main_image_run", "test:test_telegram_inbox_docs", "test:test_workflow_names"):
        rc, out = detect(kind)
        print("기준 %-34s rc=%d" % (kind, rc))
        if rc != 0:
            print(out[-1500:])
            print("기준 사본이 이미 빨강 — 중단")
            sys.exit(2)
    results = []
    open(LOG, "w", encoding="utf-8").close()
    for name, item, fname, old, new, mode, detectors in MUTATIONS:
        if want and not any(name.startswith(w) for w in want):
            continue
        for f in (DOC, WL):
            write(MUT + "/" + f, base[f])
        text = base[fname]
        n = text.count(old)
        if mode == "once" and n != 1 or mode in ("first", "all") and n < 1:
            print("건너뜀(옛 글 %d 번)" % n, name)
            results.append({"name": name, "item": item, "skipped": True, "occurrences": n})
            continue
        if mode == "all":
            mutated = text.replace(old, new)
        else:
            mutated = text.replace(old, new, 1)
        write(MUT + "/" + fname, mutated)
        t0 = time.time()
        outcome = {}
        for kind in detectors:
            rc, out = detect(kind)
            outcome[kind] = rc
        caught = any(rc != 0 for rc in outcome.values())
        rec = {"name": name, "item": item, "file": fname, "detectors": outcome, "caught": caught, "seconds": round(time.time() - t0, 1)}
        results.append(rec)
        with open(LOG, "a", encoding="utf-8") as h:
            h.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print("%-26s %-6s %s %s (%.0f초)" % (name, item, "잡힘" if caught else "놓침!!", outcome, rec["seconds"]))
    # 원복 확인
    for f in (DOC, WL):
        write(MUT + "/" + f, base[f])
    same_base = all(sha(MUT + "/" + f) == base_hash[f] for f in (DOC, WL))
    same_wt = all(sha(WT + "/" + f) == wt_hash[f] for f in (DOC, WL))
    total = [r for r in results if not r.get("skipped")]
    caught = [r for r in total if r["caught"]]
    print("\n변이 %d 개 중 %d 개 잡힘 / 건너뜀 %d · 사본 원복 sha256 같음: %s · 작업 폴더 문서 그대로: %s" % (len(total), len(caught), len(results) - len(total), same_base, same_wt))
    for item in ("W12-a", "W12-b", "W12-c"):
        sub = [r for r in total if r["item"] == item]
        print("  %s: %d 개 중 %d 개 잡힘" % (item, len(sub), len([r for r in sub if r["caught"]])))
    sys.exit(0 if len(caught) == len(total) and same_base and same_wt else 1)


if __name__ == "__main__":
    main()
