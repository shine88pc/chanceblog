"""병렬 갈래 현황판 — 작업 폴더마다 머리·WIP 커밋 수·마지막 커밋 시각·미커밋 파일 수·진행 기록 갱신 시각을 한 줄씩 보여 준다(읽기 전용).
사용: py -3.12 -X utf8 C:/work/ai/scratch/lanes.py"""
import os
import subprocess
import time

W = "C:/work/ai"
LANES = [
    ("OCR B1", "ocr_wt", "1f35804", "audit6/improve/ocr_b/progress_b1.txt"),
    ("OCR B2", "ocr_wt_b2", "1f35804", "audit6/improve/ocr_b2/progress.txt"),
    ("OCR B3", "ocr_wt_b3", "1f35804", "audit6/improve/ocr_b3/progress.txt"),
    ("OCR D", "ocr_wt_d", "1f35804", "audit6/improve/ocr_d/progress.txt"),
    ("앱 L2", "wt_l2", "3e18d1b", "audit6/improve/l2/progress.txt"),
    ("앱 L3", "wt_l3", "3e18d1b", "audit6/improve/l3/progress.txt"),
    ("앱 L4", "wt_l4", "3e18d1b", "audit6/improve/l4/progress.txt"),
    ("앱 L5", "wt_l5", "3e18d1b", "audit6/improve/l5/progress.txt"),
    ("앱 L8", "wt_l8", "3e18d1b", "audit6/improve/l8/progress.txt"),
    ("블로그 L6", "wt_l6", "2704125", "audit6/improve/l6/progress.txt"),
    ("블로그 L7", "wt_l7", "2704125", "audit6/improve/l7/progress.txt"),
    ("블로그 AP6a", "wt_ap6a", "2704125", "audit6/improve/ap6a/progress.txt"),
    ("블로그 AP6b", "wt_ap6b", "2704125", "audit6/improve/ap6b/progress.txt"),
    ("블로그 AP1", "wt_ap1", "2704125", "audit6/improve/ap1/progress.txt"),
    ("블로그 AP4", "wt_ap4", "2704125", "audit6/improve/ap4/progress.txt"),
    ("블로그 AP5", "wt_ap5", "2704125", "audit6/improve/ap5/progress.txt"),
    ("블로그 AP16", "wt_ap16", "2704125", "audit6/improve/ap16/progress.txt"),
    ("블로그 AP17", "wt_ap17", "2704125", "audit6/improve/ap17/progress.txt"),
]


def git(folder, *args):
    done = subprocess.run(["git", "-C", f"{W}/{folder}", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return done.stdout.strip()


def age(path):
    try:
        minutes = int((time.time() - os.path.getmtime(path)) / 60)
        return f"{minutes}분 전"
    except OSError:
        return "없음"


print(time.strftime("%m-%d %H:%M"), "갈래 현황")
for name, folder, base, progress in LANES:
    head = git(folder, "rev-parse", "--short", "HEAD")
    count = git(folder, "rev-list", "--count", f"{base}..HEAD")
    when = git(folder, "log", "-1", "--format=%ad", "--date=format:%H:%M")
    dirty = len([l for l in git(folder, "status", "--short").splitlines() if l.strip()])
    print(f"{name:9s} 머리 {head} · WIP {count}개 · 마지막 커밋 {when or '-'} · 미커밋 {dirty}개 · 진행 기록 {age(f'{W}/{progress}')}")
