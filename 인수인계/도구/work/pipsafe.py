"""안전하게 pip 설치하기 — 공식 PyPI 휠만(`--only-binary=:all:`), 의존 패키지까지 풀어 본 뒤 **나온 지 14일 미만인 버전이 있으면 멈춘다**.

사용: python -X utf8 pipsafe.py <대상 파이썬 exe> <패키지==버전> [<패키지==버전> ...]
1) `pip install --dry-run --report` 로 설치될 패키지 전부를 알아낸다(설치 안 함)
2) 각 패키지·버전의 PyPI 업로드 시각과 휠 크기를 보인다 — 14일 미만이거나 yanked 이면 목록을 보이고 종료 코드 3(설치 안 함)
3) 이상 없으면 같은 인자로 실제 설치(`--only-binary=:all:`)하고 설치 목록을 보인다
"""
import datetime
import json
import subprocess
import sys
import tempfile
import urllib.request

MIN_AGE_DAYS = 14


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def main():
    python, specs = sys.argv[1], sys.argv[2:]
    if not specs:
        print(__doc__)
        return 2
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        report_path = handle.name
    dry = run([python, "-m", "pip", "install", "--dry-run", "--only-binary=:all:", "--report", report_path, *specs])
    if dry.returncode != 0:
        print("해석 실패:\n" + (dry.stdout + dry.stderr)[-1500:])
        return 1
    report = json.load(open(report_path, encoding="utf-8"))
    now = datetime.datetime.now(datetime.timezone.utc)
    young, rows = [], []
    for item in report["install"]:
        name, version = item["metadata"]["name"], item["metadata"]["version"]
        filename = item["download_info"]["url"].rsplit("/", 1)[-1]
        data = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30))
        uploaded = min(f["upload_time_iso_8601"] for f in data["urls"])
        age = (now - datetime.datetime.fromisoformat(uploaded.replace("Z", "+00:00"))).days
        size = sum(f["size"] for f in data["urls"] if f["filename"] == filename) / 1e6
        yanked = any(f.get("yanked") for f in data["urls"])
        rows.append((name, version, age, size, yanked))
        if age < MIN_AGE_DAYS or yanked:
            young.append((name, version, age, yanked))
    for name, version, age, size, yanked in rows:
        print(f"  {name:24} {version:12} 나이 {age:4}일  {size:7.1f} MB" + ("  [yanked]" if yanked else ""))
    print(f"합계 약 {sum(r[3] for r in rows):.1f} MB, 패키지 {len(rows)}개")
    if young:
        print("14일 미만 또는 yanked:", young, "→ 설치하지 않습니다. 이 패키지를 더 오래된 버전으로 고정해 다시 부르세요.")
        return 3
    done = run([python, "-m", "pip", "install", "--only-binary=:all:", *specs])
    print((done.stdout + done.stderr)[-800:])
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
