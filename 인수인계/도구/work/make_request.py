"""병합 부탁 요청 파일을 완성해 wt_r30 에 쓴다(링크 없음 — 운영자는 모바일의 PC 버전 GitHub 에서 제목을 보고 병합한다, 2026-11-02 운영자 요청).
사용: python -X utf8 make_request.py <R-번호> <슬러그> <초안 파일> <시험 문구> <검증 문구> [이전 문장] [소유자/저장소:브랜치]
병합 부탁(`kind: merge`)은 마지막 인자 `소유자/저장소:브랜치` 가 **필수**다 — 그 브랜치 머리 커밋의 자동 검사(wait_ci.py 와 같은 읽기)가
모두 끝나 초록이 아니면 요청 파일을 만들지 않는다(운영자 지시 2026-11-03: 병합 부탁은 검사가 이미 끝난 뒤에만).
초안의 @TESTS@·@VERIFY@·@PREVIOUS@ 를 채운다. 'URL' 이 남아 있으면 실패한다.

알림 번호 칸(TG-STD, 운영자 승인 2026-11-06 계획 R-165) — 새 로직은 notice_tools.py·next_notice_no.py 에 있다(이 파일은 그것을 부르는 순서만 둔다):
- 앞머리에 `no: @NO@` 가 있으면 요청 종류(kind)에 맞는 **다음 알림 번호**(info=P·merge=M·그 밖=숫자만)를 next_notice_no.py 와 같은 방법으로 구해 채우고(wt_r30 저장소의 모든 원격 가지 +
  로컬 가지 + wt_r30 폴더의 작업 파일) 고른 번호를 출력한다. 숫자만인 번호는 `no: "003"` 처럼 따옴표로 쓴다. 읽기 전에 wt_r30 에서 `git fetch origin` 을 먼저 한다(이 도구는 네트워크를 쓰지 않는다).
- `kind: merge` 이고 앞머리에 `pr_title: @PR_TITLE@` 가 있으면 마지막 인자 브랜치의 머리 커밋 제목(커밋 메시지 `git log -1 --format=%B` 의 **첫 줄** — GitHub PR 제목과 같다, 로컬 가지가 없으면 origin/<가지>)을 **한 글자도 바꾸지 않고** 채운다
  (저장소 이름이 `-desktop` 으로 끝나면 cd_repo, 아니면 wt_r30 에서 읽는다). 200자 초과·제어 문자·보이지 않거나 비어 보이는 글자·비밀 모양(`key=`·`token=`·`secret=`·`AIza…`)·빈 제목이면 파일을 만들지 않고 이유를 말하며 멈춘다
  (비밀 모양이면 제목을 화면에 되풀이하지도 않는다). **손으로 쓴** `no`(표준 표기·kind 와 유형 일치·요청함에 이미 있는 번호가 아님)와 손으로 쓴 `pr_title`(같은 기준)도 만들기 전에 검사한다.
  제목을 읽은 커밋이 원격 가지 머리(검사 관문이 본 커밋)와 다르면 멈춘다 — 앞머리 `pr_title` 값에는 따옴표를 씌우지 않는다.
- 검증 문구(5번째 인자)가 비어 있고 병합 부탁의 검사 관문을 통과했다면 초안의 `@VERIFY@` 를 `검사 N칸 초록` 으로 채우고 그 사실을 출력한다(독립 검증을 했는지는 사람이 앞에 적는다 — 자동으로 쓰지 않는다).
- 앞머리의 새 칸(now·changed·next·waiting 200자, eta 100, check 60, target 100, verify 120, state 40, pr_title 200, 보기 하나 60)이 상한을 넘으면 어느 칸이 몇 자인지 말하고 만들지 않는다.
  앞머리 `id` 가 있고 파일 이름의 번호(<R-번호>)와 다르면 멈춘다(이미 같으면 그대로 둔다)."""
import re
import subprocess
import sys
from pathlib import Path

import next_notice_no as nn
import notice_tools as nt

HERE = Path(__file__).resolve().parent
GATE_TARGET_MESSAGE = "병합 부탁에는 마지막 인자로 소유자/저장소:브랜치 가 필요하다(그 브랜치의 자동 검사가 끝나 초록인지 확인한다)"


def default_gate(gate_target, workspace):
    """병합 브랜치 머리 커밋의 자동 검사가 모두 끝나 초록인지 읽는다. 통과하면 (머리 커밋 전체 해시, 실행 목록)을 돌려주고, 아니면 이유를 말하며 멈춘다."""
    sys.path.insert(0, str(workspace / "scratch"))
    import wait_ci
    gate_repo, gate_branch = gate_target.split(":", 1)
    ls = subprocess.run(["git", "ls-remote", f"https://github.com/{gate_repo}.git", f"refs/heads/{gate_branch}"], check=False, capture_output=True, text=True, timeout=90).stdout.split()
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
    return head, runs


def check_draft(text, number, pending=(), folder=None, skip=""):
    """채워진 초안을 검사한다(남은 자리표시자·링크·id·길이·손으로 쓴 알림 번호와 병합 PR 제목). 문제가 있으면 이유를 말하며 멈추고, 없으면 앞머리 값({키: 값})을 돌려준다.
    pending: 아직 채우지 않아도 되는 자리표시자. folder·skip: 요청함 폴더와 지금 만드는 파일 이름 — 주면 같은 번호를 이미 쓰는 파일도 찾는다(검증기 REQ-1 이 푸시 뒤에 잡을 것을 미리 잡는다)."""
    left = nt.leftover_placeholders(text, ignore=pending)
    if left:
        sys.exit("채우지 않은 자리표시자: " + ", ".join(left))
    if re.search(r"https?://", text):
        sys.exit("요청 파일에 링크 주소(http…)를 쓰지 않는다(운영자 요청 2026-11-02): " + re.search(r"https?://\S+", text).group(0)[:80])
    fields = nt.read_front(text)
    if fields.get("id") and fields["id"] != number:
        sys.exit(f"앞머리 id({fields['id']}) 가 파일 이름의 번호({number}) 와 다르다 — 초안을 고치거나 번호를 확인한다")
    over = nt.length_problems(fields)
    if over:
        sys.exit("앞머리 길이 초과: " + ", ".join(f"{key} {length}/{limit}" for key, length, limit in over))
    problem = nt.notice_front_problem(fields, folder, skip)
    if problem:
        sys.exit(problem)
    return fields


def main(argv=None, *, workspace=None, gate=None):
    """argv: 명령 줄 인자(기본 sys.argv[1:]). workspace: 작업 폴더 W(기본 이 파일이 있는 폴더 — wt_r30·cd_repo·scratch 가 그 아래). gate: 검사 관문 함수(시험에서 바꿔 끼운다)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 5:
        sys.exit(__doc__)
    number, slug, draft_name, tests, verify = argv[:5]
    previous = argv[5] if len(argv) > 5 else ""
    gate_target = argv[6] if len(argv) > 6 else ""
    work = Path(workspace) if workspace is not None else HERE
    name = f"{number}_{slug}.md"
    if nn.NAME_RE.fullmatch(name) is None:
        sys.exit(f"요청 파일 이름이 `R-001_짧은-영문-설명.md` 모양이 아니다(알림이 가지 않는다): {name}")
    folder = work / "wt_r30" / "인수인계" / "요청함"
    target = folder / name
    if target.exists():
        sys.exit("이미 있다: " + str(target))
    if not folder.is_dir():
        sys.exit(f"요청함 폴더가 없다: {folder} — wt_r30 이 요청 가지로 준비돼 있는지 확인한다(인수인계/도구/README.md §1)")
    draft = (work / draft_name).read_text(encoding="utf-8-sig")
    front = nt.read_front(draft)
    kind = front.get("kind", "")

    no_text = pr_title = title_sha = None
    if front.get("no") == "@NO@":
        number_type = nt.NOTICE_TYPE_OF_KIND.get(kind)
        if number_type is None:
            sys.exit(f"`no: @NO@` 를 채울 수 없다 — 초안의 kind 가 {kind!r} 이다(info·merge·decision·confirm·run 중 하나여야 번호 유형이 정해진다)")
        repo = work / "wt_r30"
        try:
            found = nn.scan(repo, dirs=[repo], local=True)
            no_text = nn.next_number(found, number_type)
        except (nn.ScanError, nn.NumberExhausted) as exc:
            sys.exit(f"알림 번호를 정하지 못했다: {exc}")
        print("알림 번호:", nn.describe(found, number_type, no_text))
    if front.get("pr_title") == "@PR_TITLE@":
        if kind != "merge":
            sys.exit(f"`pr_title: @PR_TITLE@` 는 병합 부탁(kind: merge)에서만 채운다(초안의 kind 는 {kind!r})")
        if ":" not in gate_target:
            sys.exit(GATE_TARGET_MESSAGE)
        gate_repo, gate_branch = gate_target.split(":", 1)
        source = work / nt.repo_folder(gate_repo)
        try:
            pr_title, title_sha, title_ref = nt.head_subject(source, gate_branch)
        except nt.TitleError as exc:
            sys.exit(f"병합 PR 제목을 읽지 못했다: {exc}")
        problem = nt.pr_title_problem(pr_title)
        if problem:
            shown = "(비밀로 보이는 글이라 화면에 적지 않는다)" if nt.looks_secret(pr_title) else pr_title      # 비밀 모양 제목을 터미널·로그에 되풀이하지 않는다
            sys.exit(f"병합 PR 제목을 그대로 쓸 수 없어 요청 파일을 만들지 않는다 — {problem}: {shown}")
        print(f"PR 제목(글자 그대로): {pr_title}  ← {source.name} 의 {title_ref} 머리 커밋 {title_sha[:8]}")

    auto_verify = kind == "merge" and verify == ""        # 검증 문구가 비었으면 검사 관문을 통과한 뒤 `검사 N칸 초록` 으로 채운다
    values = {"TESTS": tests, "PREVIOUS": previous}
    if not auto_verify:
        values["VERIFY"] = verify
    draft = nt.fill_placeholders(nt.fill_front_values(draft, no=no_text, pr_title=pr_title), values)
    taken_folder = folder if no_text is None else None        # 도구가 정한 번호(`@NO@`)는 요청함 파일까지 읽어 최댓값 + 1 로 구한 것이라 겹침 검사는 손으로 쓴 번호에만 한다
    fields = check_draft(draft, number, pending=("@VERIFY@",) if auto_verify else (), folder=taken_folder, skip=name)
    if kind == "merge":
        if ":" not in gate_target:
            sys.exit(GATE_TARGET_MESSAGE)
        head, runs = (gate or default_gate)(gate_target, work)
        if title_sha is not None and head != title_sha:
            sys.exit(f"PR 제목을 읽은 커밋({title_sha[:8]})이 검사 관문이 본 원격 가지 머리({head[:8]})와 다르다 — 가지를 push 했는지, git fetch origin 을 했는지 확인한다(다른 커밋의 제목을 쓰지 않는다)")
        if auto_verify and "@VERIFY@" in draft:
            filled = nt.auto_verify_text(len(runs))
            draft = nt.fill_placeholders(draft, {"VERIFY": filled})
            print(f"검증 문구가 비어 있어 `{filled}` 으로 채웠다 — 독립 검증을 했는지는 사람이 앞에 적는다(자동으로 쓰지 않음)")
            fields = check_draft(draft, number, folder=taken_folder, skip=name)
    target.write_text(draft, encoding="utf-8", newline="\n")
    print("파일", target.name, "| 줄 수", draft.count("\n"), "| title", len(fields.get("title", "")), "| summary", len(fields.get("summary", "")))


if __name__ == "__main__":
    main()
