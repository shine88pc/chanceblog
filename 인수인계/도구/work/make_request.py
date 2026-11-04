"""병합 부탁 요청 파일을 완성해 wt_r30 에 쓴다(링크 없음 — 운영자는 모바일의 PC 버전 GitHub 에서 제목을 보고 병합한다, 2026-11-02 운영자 요청).
사용: python -X utf8 make_request.py <R-번호> <슬러그> <초안 파일> <시험 문구> <검증 문구> [이전 문장] [소유자/저장소:브랜치]
병합 부탁(`kind: merge`)은 마지막 인자 `소유자/저장소:브랜치` 가 **필수**다 — 그 브랜치 머리 커밋의 자동 검사(wait_ci.py 와 같은 읽기)가
모두 끝나 초록이 아니면 요청 파일을 만들지 않는다(운영자 지시 2026-11-03: 병합 부탁은 검사가 이미 끝난 뒤에만).
초안의 @TESTS@·@VERIFY@·@PREVIOUS@ 를 채운다. 'URL' 이 남아 있으면 실패한다."""
import re
import sys
from pathlib import Path

S = Path(__file__).resolve().parent
number, slug, draft_name, tests, verify = sys.argv[1:6]
previous = sys.argv[6] if len(sys.argv) > 6 else ""
gate_target = sys.argv[7] if len(sys.argv) > 7 else ""

draft = ((S / draft_name).read_text(encoding="utf-8").replace("@TESTS@", tests).replace("@VERIFY@", verify).replace("@PREVIOUS@", previous))
leftover = [token for token in ("@TESTS@", "@VERIFY@", "@LINK@", "@PREVIOUS@") if token in draft]
if leftover:
    sys.exit("채우지 않은 자리표시자: " + ", ".join(leftover))
if re.search(r"https?://", draft):
    sys.exit("요청 파일에 링크 주소(http…)를 쓰지 않는다(운영자 요청 2026-11-02): " + re.search(r"https?://\S+", draft).group(0)[:80])
front = re.match(r"---\n(.*?)\n---\n", draft, re.S)
fields = dict(line.split(": ", 1) for line in front.group(1).splitlines()) if front else {}
if len(fields.get("title", "")) > 80 or len(fields.get("summary", "")) > 300:
    sys.exit(f"앞머리 길이 초과: title {len(fields.get('title', ''))}/80 summary {len(fields.get('summary', ''))}/300")
if fields.get("kind") == "merge":
    import subprocess
    sys.path.insert(0, str(S / "scratch"))
    import wait_ci
    if ":" not in gate_target:
        sys.exit("병합 부탁에는 마지막 인자로 소유자/저장소:브랜치 가 필요하다(그 브랜치의 자동 검사가 끝나 초록인지 확인한다)")
    gate_repo, gate_branch = gate_target.split(":", 1)
    ls = subprocess.run(["git", "ls-remote", f"https://github.com/{gate_repo}.git", f"refs/heads/{gate_branch}"], capture_output=True, text=True, timeout=90).stdout.split()
    if not ls:
        sys.exit(f"원격에 브랜치가 없다: {gate_target}")
    head = ls[0]
    runs = wait_ci.runs_for(gate_repo, gate_branch, head[:12])
    if not runs:
        sys.exit(f"머리 커밋 {head[:8]} 의 자동 검사 실행이 목록에 없다 — 아직 시작 전이거나 검사가 안 도는 브랜치다. 검사가 끝나 초록인 것을 확인한 뒤에 다시 실행한다")
    bad = [r for r in runs if r["status"] != "completed" or r["conclusion"] not in wait_ci.OK_CONCLUSIONS]
    if bad:
        sys.exit("검사가 아직 끝나지 않았거나 초록이 아니다: " + ", ".join(f"{r['id']}({r['status']}/{r['conclusion'] or '-'})" for r in bad))
    print(f"검사 관문 통과: {gate_target} @ {head[:8]} — 실행 {len(runs)}건 모두 끝나 초록(" + ", ".join(r["timing"] for r in runs) + ")")
target = S / "wt_r30" / "인수인계" / "요청함" / f"{number}_{slug}.md"
if target.exists():
    sys.exit("이미 있다: " + str(target))
target.write_text(draft, encoding="utf-8", newline="\n")
print("파일", target.name, "| 줄 수", draft.count("\n"), "| title", len(fields.get("title", "")), "| summary", len(fields.get("summary", "")))
