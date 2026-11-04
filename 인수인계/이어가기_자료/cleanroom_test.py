"""새 PC 처럼 깨끗한 폴더에서 인수인계 도구가 도는지 시험한다(저장소는 push 한 가지에서 받는다).

사용: python -X utf8 cleanroom_test.py <푸시한 가지 이름> <시험 폴더 CR>
단계: ① 그 가지를 CR/blog_branch 로 clone ② 그 안의 setup_workspace.py 로 CR/W 를 만든다 ③ W 안 도구를 짧게 돌려 본다
읽기·로컬 시험만 한다(원격에 push 하지 않는다, 요청 파일은 만든 뒤 지운다).
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BRANCH = sys.argv[1]
CR = Path(sys.argv[2]).resolve()
BLOG_URL = "https://github.com/shine88pc/chanceblog.git"
results = []


def step(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("통과" if ok else "실패"), "—", name, ("— " + detail) if detail else "", flush=True)


def run(cmd, cwd=None, timeout=900, env=None):
    started = time.time()
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env)
    return done.returncode, (done.stdout or "") + (done.stderr or ""), time.time() - started


def main():
    if CR.exists():
        def force(func, path, _info):
            os.chmod(path, 0o700)       # git 객체 파일은 읽기 전용이라 지우기 전에 풀어 준다(Windows)
            func(path)
        shutil.rmtree(CR, onerror=force)
    CR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONUTF8="1", GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="false")

    code, out, took = run(["git", "clone", "--branch", BRANCH, "--single-branch", BLOG_URL, str(CR / "blog_branch")], env=env)
    step("① push 한 가지를 새로 clone", code == 0, f"{took:.0f}초" + ("" if code == 0 else " — " + out[-200:]))
    if code:
        return
    branch_repo = CR / "blog_branch"
    tools = branch_repo / "인수인계" / "도구"
    step("② 도구 폴더가 가지에 있다", (tools / "setup_workspace.py").exists() and (tools / "README.md").exists() and (tools / "work" / "make_request.py").exists())

    W = CR / "W"
    code, out, took = run([sys.executable, "-X", "utf8", str(tools / "setup_workspace.py"), str(W)], env=env)
    step("③ setup_workspace.py 실행(복사+두 저장소 clone+요청 가지 전환)", code == 0, f"{took:.0f}초\n" + out.strip()[-700:])
    if code:
        return

    needed = ["make_request.py", "make_info_request.py", "mk_merge_branch.py", "commit_as_author.py", "pipsafe.py", "r134_fill.py", "r135_fill.py",
              "p27p0b_brief.md", "verify_p1_brief.md", "r134_draft.md", "ver_p0_report.md", "ver_nv_report.md", "scratch/wait_ci.py", "scratch/watch_light.py", "scratch/watch_desktop.py",
              "scratch/runs_by_sha.py", "scratch/wait_ci_multi.py", "scratch/ci_web.py", "scratch/run_steps_times.py", "scratch/run_annotations.py"]
    missing = [name for name in needed if not (W / name).exists()]
    step("④ W 에 도구·지시서가 모두 복사됐다", not missing, "빠짐: " + ", ".join(missing) if missing else f"{len(needed)}개 확인")

    wt = W / "wt_r30"
    cd = W / "cd_repo"
    code, out, _ = run(["git", "-C", str(wt), "branch", "--show-current"])
    step("⑤ wt_r30 가 요청 가지에 있다", out.strip() == "ai/claude/desktop-bootstrap-merge", out.strip())
    code, out, _ = run(["git", "-C", str(cd), "rev-parse", "--short", "origin/main"])
    step("⑥ cd_repo 가 데스크톱 main 을 받았다", code == 0 and len(out.strip()) >= 7, out.strip())

    scripts = sorted(str(path) for path in list(W.glob("*.py")) + list((W / "scratch").glob("*.py")))
    code, out, _ = run([sys.executable, "-X", "utf8", "-m", "py_compile"] + scripts)
    step("⑦ 복사된 스크립트 py_compile", code == 0, out.strip()[-200:] if code else f"{len(scripts)}개")

    # 안내 요청 파일 만들기(링크·<…> 검사 포함) → 검증기 → 지우기
    draft = W / "cleanroom_draft.md"
    draft.write_text("---\nid: R-999\nkind: info\ntitle: [R-999] 새 폴더 시험\nsummary: 새 폴더 시험용 요청 파일입니다(곧 지웁니다).\nurgency: 보통\ncreated: 2026-11-04\n---\n\n# 새 폴더 시험\n\n- 표 없음, 링크 없음.\n", encoding="utf-8")
    code, out, _ = run([sys.executable, "-X", "utf8", str(W / "make_info_request.py"), "R-999", "cleanroom-test", draft.name], cwd=str(W), env=env)
    made = wt / "인수인계" / "요청함" / "R-999_cleanroom-test.md"
    step("⑧ make_info_request.py 가 요청 파일을 만든다", code == 0 and made.exists(), out.strip()[-200:])
    if made.exists():
        code, out, _ = run([sys.executable, "-X", "utf8", "scripts/validate_repo.py", "--root", "."], cwd=str(wt), env=env, timeout=600)
        step("⑨ 요청 파일이 저장소 검증기를 통과한다(오류 0건)", code == 0 and "오류 0건" in out, out.strip().splitlines()[-1] if out.strip() else "")
        made.unlink()

    # 한 커밋 병합 가지(로컬만)
    msg = W / "cleanroom_msg.txt"
    msg.write_text("[R-999] 새 폴더 시험 [대상: 공통]\n\n본문.\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\n", encoding="utf-8")
    code, out, _ = run([sys.executable, "-X", "utf8", str(W / "mk_merge_branch.py"), str(cd), "origin/main", "origin/main", str(msg), "ai/claude/tmp-cleanroom-smoke"], env=env)
    step("⑩ mk_merge_branch.py 가 한 커밋 가지를 만든다(로컬)", code == 0 and "강병수" in out, out.strip().splitlines()[-2][:140] if out.strip() else "")
    run(["git", "-C", str(cd), "branch", "-D", "ai/claude/tmp-cleanroom-smoke"])

    # 커밋 작성자 고정(임시 저장소)
    tmp = CR / "tmp_repo"
    tmp.mkdir()
    run(["git", "-C", str(tmp), "init", "-q"])
    (tmp / "a.txt").write_text("x\n", encoding="utf-8")
    run(["git", "-C", str(tmp), "add", "a.txt"])
    msg2 = W / "cleanroom_msg2.txt"
    msg2.write_text("시험 커밋\n\n본문 한글.\n", encoding="utf-8")
    code, out, _ = run([sys.executable, "-X", "utf8", str(W / "commit_as_author.py"), str(tmp), str(msg2)], env=env)
    code2, who, _ = run(["git", "-C", str(tmp), "log", "-1", "--format=%an <%ae> | %s"])
    step("⑪ commit_as_author.py 가 작성자를 고정해 커밋한다", code == 0 and "강병수" in who and "시험 커밋" in who, who.strip())

    # 읽기 도구(REST 호출 1~2회)
    code, out, _ = run([sys.executable, "-X", "utf8", str(W / "scratch" / "runs_by_sha.py"), "shine88pc/chanceblog", "4e2caa9"], env=env, timeout=120)
    step("⑫ runs_by_sha.py 가 실행 상태를 읽는다", code == 0 and "4e2caa9" in out, out.strip().replace("\n", " | ")[:200])

    # 감시 — 시작 줄만 보고 끝낸다
    try:
        proc = subprocess.Popen([sys.executable, "-X", "utf8", "-u", str(W / "scratch" / "watch_light.py")], cwd=str(W / "scratch"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=dict(env, WATCH_SINCE=str(int(time.time()))))
        first = ""
        deadline = time.time() + 90
        while time.time() < deadline:
            line = proc.stdout.readline()
            if line.strip():
                first += line
                if "기준" in line:
                    break
        proc.terminate()
        step("⑬ watch_light.py 가 시작 줄·기준 줄을 낸다", "감시 시작" in first, first.strip().replace("\n", " | ")[:200])
    except Exception as exc:  # noqa: BLE001 — 시험 도구라 모든 실패를 보고한다
        step("⑬ watch_light.py", False, str(exc)[:200])

    print()
    failed = [name for name, ok, _ in results if not ok]
    print("요약:", len(results) - len(failed), "통과 /", len(results), "단계", ("— 실패: " + "; ".join(failed)) if failed else "— 모두 통과")


main()
