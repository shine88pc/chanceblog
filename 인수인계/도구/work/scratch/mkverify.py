"""검증 준비 도우미 — 갈래 하나의 S·Q 독립 검증에 필요한 읽기 전용 작업 나무 둘과 검증 지시서를 한 번에 만든다(총괄 전용).
사용:
  py -3.12 -X utf8 C:/work/ai/scratch/mkverify.py <갈래키> <저장소 폴더> <검증할 머리(해시 또는 가지)> <시작점(main 해시)> <지시서 이름 BRIEF_xx> <진행기록 폴더 슬러그> [--notes <특별 주의 파일>] [--extra-lens <이름>]
예:
  py -3.12 -X utf8 C:/work/ai/scratch/mkverify.py l8 C:/work/ai/wt_l8 ai/claude/NO-MERGE-l8-wip 3e18d1b BRIEF_L8 l8 --notes C:/work/ai/audit6/improve/wave2/notes_l8.txt
하는 일:
  1) `<저장소>` 에서 `git worktree add --detach C:/work/ai/verify/<키>_s <머리>` 와 `..._q` (이미 있으면 머리만 맞춘다)
  2) 출력 폴더 `C:/work/ai/verify/<키>_s_out`·`<키>_q_out` 만들기
  3) `C:/work/ai/audit6/improve/wave2/VERIFY_<키 대문자>.md` 쓰기(S·Q 공통 한 장 — 렌즈는 VERIFY_GENERAL 4절)
읽기 전용(저장소 파일 수정 없음, 푸시 없음). 앱 저장소의 `vendor/` 는 작업 나무에 그대로 따라온다(추적 파일)."""
import os
import subprocess
import sys

W = "C:/work/ai"


def run(*args, cwd=None):
    done = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return done.returncode, (done.stdout + done.stderr).strip()


def main(argv):
    notes_file = None
    extra = None
    single = False
    args = []
    it = iter(argv)
    for a in it:
        if a == "--notes":
            notes_file = next(it)
        elif a == "--extra-lens":
            extra = next(it)
        elif a == "--single":          # 작은 갈래: S·Q 두 관점을 한 검증자가 맡는다(작업 나무·출력 폴더 하나, 보고서 report_SQ.txt)
            single = True
        else:
            args.append(a)
    if len(args) != 6:
        print(__doc__)
        return 2
    key, repo, head, base, brief, slug = args
    code, full = run("git", "-C", repo, "rev-parse", head)
    if code != 0:
        print("머리를 못 찾음:", full)
        return 1
    code, base_full = run("git", "-C", repo, "rev-parse", base)
    if code != 0:
        print("시작점을 못 찾음:", base_full)
        return 1
    code, branch = run("git", "-C", repo, "rev-parse", "--abbrev-ref", head)
    lenses = ["sq"] if single else ["s", "q"] + ([extra.lower()] if extra else [])
    for lens in lenses:
        wt = f"{W}/verify/{key}_{lens}"
        out = f"{W}/verify/{key}_{lens}_out"
        os.makedirs(out, exist_ok=True)
        if os.path.isdir(wt):
            code, msg = run("git", "-C", wt, "checkout", "--detach", full)
            print(lens, "작업 나무 있음 → 머리 맞춤:", code, msg[-80:])
        else:
            code, msg = run("git", "-C", repo, "worktree", "add", "--detach", wt, full)
            print(lens, "작업 나무 만듦:", code, msg[-120:])
            if code != 0:
                return 1
    notes = ""
    if notes_file and os.path.isfile(notes_file):
        with open(notes_file, encoding="utf-8") as f:
            notes = f.read().strip()
    repo_kind = "앱 `chanceblog-desktop`" if "desktop" in repo or repo.rsplit("/", 1)[-1].startswith(("wt_l", "ocr_wt")) else "블로그 `chanceblog`"
    lens_rows = "\n".join(
        f"- {name}: 읽기 전용 작업 나무 `{W}/verify/{key}_{lens}` · 출력 폴더 `{W}/verify/{key}_{lens}_out/` · 보고서 `{W}/verify/{key}_{lens}_out/report_{name}.txt`"
        for name, lens in ([("SQ", "sq")] if single else [("S", "s"), ("Q", "q")] + ([(extra, extra.lower())] if extra else []))
    )
    if single:
        lens_rows += "\n- (작은 갈래라 S 와 Q 두 관점을 한 검증자가 모두 본다 — VERIFY_GENERAL 4절의 S·Q 항목을 둘 다 훑고, 발견 ID 는 SP-/QP- 를 그대로 쓴다)"
    text = f"""# 검증 지시서 — {key.upper()} — 총괄 작성

먼저 `{W}/audit6/improve/wave2/VERIFY_GENERAL.md` 를 읽는다(공통 규칙·환경·자원 예절·보고 형식·S/Q 관점). 이 문서는 이 갈래만의 사실이다.

- 저장소: {repo_kind} · 구현자 작업 폴더 `{repo}`(읽기만) · 검증할 가지 `{branch}`
- **머리 커밋(검증 대상): `{full}`** · 시작점(main): `{base_full}` — `git diff {base_full[:7]} {full[:7]} --stat` 이 변경 범위.
- 구현자에게 준 지시서(= 승인 범위·항목 정의의 정본): `{W}/audit6/improve/wave2/{brief}.md`
- 구현자 보고서와 진행 기록(구현자 주장 — 직접 확인할 것): `{W}/audit6/improve/{slug}/report.txt` · `progress.txt`
{lens_rows}
- 검증자는 자기 렌즈의 작업 나무·출력 폴더만 쓴다(다른 렌즈 폴더·구현자 폴더는 읽기만). 변이는 복사본에서만.

## 이 갈래의 특별 주의
{notes or '(총괄이 따로 적은 것 없음 — 지시서의 항목·금지 목록을 기준으로 본다)'}
"""
    path = f"{W}/audit6/improve/wave2/VERIFY_{key.upper()}.md"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("지시서:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
