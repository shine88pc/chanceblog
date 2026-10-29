"""변경을 보내기 전에 도는 검증 사다리를 한 번에 돌려 요약한다(docs/AGENT_RUNBOOK.md J4).

순서: ① 전체 시험 ② 저장소 규칙 검증기 ③ actionlint ④ pyflakes ⑤ vermin(3.10 이하) ⑥ 3.12 전용 f-string.
①②는 언제나 돈다. ③~⑥은 도구가 없으면 '건너뜀(이유)'로 보고한다 — 건너뛴 검증을 통과로 세지 않는다(AGENTS.md 절대 규칙 7).
검증기는 기준 커밋을 못 구하면 광고 표면 검사(AD-1·AD-2)를 못 하므로 그때도 '건너뜀'이다.
④~⑥은 기준 커밋과 비교해 바뀐 .py 파일만 본다(기준을 못 구하면 저장소의 모든 .py).
코드는 Python 3.10 에서 돌아야 하므로(3.12 전용 문법 금지) ⑤⑥이 있다. ⑥은 3.12 이상 파이썬에서만 검사할 수 있다.

사용: python scripts/final_checks.py [--root .] [--base origin/main] [--tests-pattern 'test_x.py'] [--json]
도구 준비: pip install -r requirements-dev.txt pyflakes vermin   (docs/SESSION_START.md §2-1)
종료 코드: 0 모든 단계 통과 / 1 실패한 단계 있음 / 2 사용법 오류 / 3 실패는 없지만 건너뛴 단계가 있어 **불완전**(통과로 보고하지 않는다)
표준 라이브러리만 쓴다.
"""
import argparse
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import time
import tokenize
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.console import one_line, safe_output  # noqa: E402

DEFAULT_BASE = "origin/main"
PASS, FAIL, SKIP = "통과", "실패", "건너뜀"
TEST_TIMEOUT, TOOL_TIMEOUT = 1800, 300
# 저장소 관행이라 경고로 세지 않는 pyflakes 줄: 시험 파일이 import 경로를 잡으려는 `_bootstrap`, 패키지 `__init__` 이 이름을 다시 내보내려는 import 두 줄
_IGNORED_PYFLAKES = ("'_bootstrap' imported but unused",
                     "'pipeline.publishers.base.PublishError' imported but unused",
                     "'pipeline.publishers.base.PublishResult' imported but unused")
_SOURCE_DIRS = ("pipeline", "scripts", "tests")
_GIT = ["git", "-c", "core.quotepath=off"]       # 비ASCII 파일 이름을 따옴표·8진수로 감싸지 않고 그대로 낸다


class Step:
    def __init__(self, name, status, detail, seconds=0.0):
        self.name, self.status, self.detail, self.seconds = name, status, detail, round(seconds, 1)

    def as_dict(self):
        return {"name": self.name, "status": self.status, "detail": self.detail, "seconds": self.seconds}


def _decode(data):
    return data.decode("utf-8", "replace") if isinstance(data, bytes) else (data or "")


def default_runner(cmd, cwd, timeout):
    """(종료 코드, 표준 출력, 표준 오류). 시간 초과는 종료 코드 124, 실행 파일이 없으면 127 로 돌려준다."""
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", f"{timeout}초 안에 끝나지 않아 중단했습니다"
    except OSError as exc:
        return 127, "", f"실행하지 못했습니다: {type(exc).__name__}"
    return proc.returncode, _decode(proc.stdout), _decode(proc.stderr)


# ---------------------------------------------------------------------------
# 바뀐 파일·도구 찾기
# ---------------------------------------------------------------------------
def base_exists(root, base, runner):
    code, _, _ = runner(["git", "rev-parse", "--verify", "--quiet", base + "^{commit}"], root, 30)
    return code == 0


def all_python_files(root):
    files = [p.name for p in Path(root).glob("*.py")]
    for folder in _SOURCE_DIRS:
        files += [p.relative_to(root).as_posix() for p in (Path(root) / folder).rglob("*.py")]
    return sorted(set(files))


def changed_python_files(root, base, runner):
    """(파일 목록, 설명). 기준과 작업 폴더를 비교한 .py(새 파일 포함). 기준이 없으면 모든 .py."""
    if base and base_exists(root, base, runner):
        code, out, _ = runner(_GIT + ["diff", "--name-only", base], root, 60)
        code2, new, _ = runner(_GIT + ["ls-files", "--others", "--exclude-standard"], root, 60)
        if code == 0 and code2 == 0:
            names = sorted({line.strip() for line in (out + "\n" + new).splitlines() if line.strip().endswith(".py")})
            return [n for n in names if (Path(root) / n).exists()], f"기준 {base} 대비 바뀐 .py"
    return all_python_files(root), "기준을 구하지 못해 모든 .py"


def find_executable(name, which=shutil.which):
    """PATH 에서, 없으면 지금 파이썬이 있는 폴더(가상환경의 Scripts·bin)에서 실행 파일을 찾는다."""
    found = which(name)
    if found:
        return found
    for candidate_name in (name, name + ".exe"):
        candidate = Path(sys.executable).parent / candidate_name
        if candidate.exists():
            return str(candidate)
    return None


def has_module(name):
    return importlib.util.find_spec(name) is not None


# ---------------------------------------------------------------------------
# 3.12 전용 f-string: 3.12 의 tokenize 로만 알 수 있다
# ---------------------------------------------------------------------------
def find_py312_only_fstrings(source):
    """source(bytes)에서 (줄, 열, 사유) 목록. 3.12 에서 처음 허용된 f-string 모양: 식 안에서 같은 따옴표를 다시 쓰기(문자열·f-string),
    식 안의 역슬래시·주석, 한 줄(따옴표 하나) f-string 식 안의 줄바꿈. 3.12 미만 파이썬에서는 FSTRING_START 토큰이 없어 호출하면 안 된다."""
    # 3.12 에서 생긴 토큰 이름은 getattr 로 읽는다(3.10 에서 이 파일을 불러와도 깨지지 않고, vermin 이 이 파일을 3.12 전용으로 보지 않는다)
    fstring_start, fstring_end = getattr(tokenize, "FSTRING_START", None), getattr(tokenize, "FSTRING_END", None)
    if fstring_start is None:
        raise RuntimeError("3.12 이상 파이썬이 필요합니다")
    problems, stack = [], []
    for tok in tokenize.tokenize(io.BytesIO(source).readline):
        if tok.type == fstring_start:
            quote = tok.string[-3:] if tok.string[-3:] in ('"""', "'''") else tok.string[-1]
            if stack and stack[-1] == quote:
                problems.append((tok.start[0], tok.start[1], "f-string 식 안에서 같은 따옴표의 f-string 을 다시 씀"))
            stack.append(quote)
        elif tok.type == fstring_end:
            if stack:
                stack.pop()
        elif stack and tok.type == tokenize.STRING:
            if tok.string.lstrip("rbfuRBFU").startswith(stack[-1]):
                problems.append((tok.start[0], tok.start[1], "f-string 식 안에서 같은 따옴표를 다시 씀"))
            elif "\\" in tok.string:
                problems.append((tok.start[0], tok.start[1], "f-string 식 안의 역슬래시"))
        elif stack and tok.type == tokenize.COMMENT:
            problems.append((tok.start[0], tok.start[1], "f-string 식 안의 주석"))
        elif stack and tok.type in (tokenize.NL, tokenize.NEWLINE) and len(stack[-1]) == 1:
            problems.append((tok.start[0], tok.start[1], "한 줄 f-string 식 안의 줄바꿈"))
    return problems


# ---------------------------------------------------------------------------
# 단계
# ---------------------------------------------------------------------------
def step_tests(root, pattern, runner):
    started = time.monotonic()
    name = "전체 시험" if not pattern else f"시험({pattern})"
    cmd = [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests"] + (["-p", pattern] if pattern else [])
    code, out, err = runner(cmd, root, TEST_TIMEOUT)
    text = err + "\n" + out
    ran = re.search(r"^Ran (\d+) tests? in ([\d.]+)s", text, re.M)
    ok_line = re.search(r"^OK(?: \(([^)]*)\))?\s*$", text, re.M)
    elapsed = time.monotonic() - started
    if code == 0 and ran and ok_line:
        total = int(ran.group(1))
        if total == 0:
            return Step(name, FAIL, "시험이 하나도 돌지 않았습니다(0개) — 파일 이름 패턴이나 폴더를 확인하세요", elapsed)
        skipped_match = re.search(r"skipped=(\d+)", ok_line.group(1) or "")
        skipped = int(skipped_match.group(1)) if skipped_match else 0
        detail = f"{total - skipped}개 통과 ({ran.group(2)}초)" + (f", 건너뛴 시험 {skipped}개(필요한 도구가 없어서일 수 있다)" if skipped else "")
        return Step(name, PASS, detail, elapsed)
    tail = [one_line(line, 160) for line in text.strip().splitlines()[-8:]]
    return Step(name, FAIL, " | ".join(tail) or f"종료 코드 {code}", elapsed)


def step_validate(root, base, runner):
    started = time.monotonic()
    cmd = [sys.executable, "-X", "utf8", "scripts/validate_repo.py"]
    has_base = bool(base) and base_exists(root, base, runner)
    if has_base:
        cmd += ["--base", base]
    code, out, err = runner(cmd, root, TOOL_TIMEOUT)
    summary = next((line for line in (out + "\n" + err).splitlines() if line.startswith("요약:")), "")
    detail = one_line(summary or f"종료 코드 {code}", 200)
    if code != 0:
        errors = [one_line(line, 160) for line in out.splitlines() if line.startswith("ERROR")][:5]
        return Step("저장소 규칙 검증기", FAIL, detail + ((" | " + " | ".join(errors)) if errors else ""), time.monotonic() - started)
    if not has_base:       # 광고 표면(AD-1)·에이전트 승인 표시(AD-2) 검사는 기준 커밋이 있어야 돈다 — 못 본 검사를 통과로 세지 않는다
        return Step("저장소 규칙 검증기", SKIP, detail + " — 기준 커밋을 못 구해 광고 표면 검사(AD-1·AD-2)를 하지 못했습니다(나머지 검사는 통과)", time.monotonic() - started)
    return Step("저장소 규칙 검증기", PASS, detail, time.monotonic() - started)


def step_actionlint(root, runner, which):
    exe = find_executable("actionlint", which)
    if not exe:
        return Step("actionlint", SKIP, "실행 파일이 없습니다(pip install -r requirements-dev.txt)")
    files = sorted(p.relative_to(root).as_posix() for p in (Path(root) / ".github" / "workflows").glob("*.yml"))
    if not files:
        return Step("actionlint", SKIP, "워크플로 파일이 없습니다")
    started = time.monotonic()
    code, out, err = runner([exe] + files, root, TOOL_TIMEOUT)
    if code == 0:
        return Step("actionlint", PASS, f"워크플로 {len(files)}개, 지적 0건", time.monotonic() - started)
    lines = [one_line(line, 160) for line in (out + "\n" + err).splitlines() if line.strip()][:6]
    return Step("actionlint", FAIL, " | ".join(lines) or f"종료 코드 {code}", time.monotonic() - started)


def step_pyflakes(root, files, runner, module_ok):
    if not module_ok("pyflakes"):
        return Step("pyflakes", SKIP, "pyflakes 가 설치돼 있지 않습니다(pip install pyflakes)")
    if not files:
        return Step("pyflakes", PASS, "검사할 .py 변경이 없습니다")
    started = time.monotonic()
    code, out, err = runner([sys.executable, "-m", "pyflakes"] + files, root, TOOL_TIMEOUT)
    if code not in (0, 1):      # pyflakes 는 경고가 없으면 0, 있으면 1 이다. 그 밖(2·시간 초과·실행 실패)은 도구가 제대로 못 돈 것이다
        return Step("pyflakes", FAIL, f"pyflakes 가 비정상 종료했습니다(종료 코드 {code}): " + one_line(" ".join((out + " " + err).split()), 160), time.monotonic() - started)
    lines = [line for line in (out + "\n" + err).splitlines() if line.strip() and not any(skip in line for skip in _IGNORED_PYFLAKES)]
    if not lines:
        return Step("pyflakes", PASS, f"새 경고 없음(파일 {len(files)}개)", time.monotonic() - started)
    return Step("pyflakes", FAIL, " | ".join(one_line(line, 160) for line in lines[:6]) + (f" … 외 {len(lines) - 6}건" if len(lines) > 6 else ""), time.monotonic() - started)


def step_vermin(root, files, runner, which):
    exe = find_executable("vermin", which)       # `python -m vermin` 은 실행되지 않는다(패키지에 __main__ 이 없다)
    if not exe:
        return Step("vermin(3.10 이하)", SKIP, "vermin 이 설치돼 있지 않습니다(pip install vermin)")
    if not files:
        return Step("vermin(3.10 이하)", PASS, "검사할 .py 변경이 없습니다")
    started = time.monotonic()
    code, out, err = runner([exe, "--target=3.10-", "--no-tips"] + files, root, TOOL_TIMEOUT)
    text = out + "\n" + err
    found = re.search(r"Minimum required versions?: (\d+)\.(\d+)", text)
    seen = " ".join(text.split())[:240]
    if "Target versions not met" in text or (found and (int(found.group(1)), int(found.group(2))) > (3, 10)):
        return Step("vermin(3.10 이하)", FAIL, "3.10 보다 새 문법·모듈을 씁니다: " + one_line(seen, 240), time.monotonic() - started)
    if not found:        # 버전 줄을 못 읽었다 = 검사가 돌지 않았다. 통과로 세지 않는다
        return Step("vermin(3.10 이하)", FAIL, "vermin 결과를 읽지 못했습니다(종료 코드 %s): %s" % (code, one_line(seen, 200)), time.monotonic() - started)
    return Step("vermin(3.10 이하)", PASS, f"최소 {found.group(1)}.{found.group(2)}", time.monotonic() - started)


def step_fstrings(root, files, version=None):
    if tuple(version or sys.version_info)[:2] < (3, 12):
        return Step("3.12 전용 f-string", SKIP, "이 검사는 3.12 이상 파이썬에서만 할 수 있습니다")
    if not files:
        return Step("3.12 전용 f-string", PASS, "검사할 .py 변경이 없습니다")
    started = time.monotonic()
    problems = []
    for name in files:
        try:
            for line, col, why in find_py312_only_fstrings((Path(root) / name).read_bytes()):
                problems.append(f"{name}:{line}:{col} {why}")
        except (OSError, tokenize.TokenError, SyntaxError) as exc:
            problems.append(f"{name}: 읽지 못했습니다({type(exc).__name__})")
    if problems:
        return Step("3.12 전용 f-string", FAIL, " | ".join(problems[:6]), time.monotonic() - started)
    return Step("3.12 전용 f-string", PASS, f"문제 0건(파일 {len(files)}개)", time.monotonic() - started)


def run_ladder(root, base, pattern=None, runner=default_runner, which=shutil.which, module_ok=has_module):
    files, note = changed_python_files(root, base, runner)
    steps = [step_tests(root, pattern, runner), step_validate(root, base, runner), step_actionlint(root, runner, which),
             step_pyflakes(root, files, runner, module_ok), step_vermin(root, files, runner, which), step_fstrings(root, files)]
    return steps, files, note


def verdict_of(steps):
    """(판정, 종료 코드): 실패가 있으면 ('실패', 1), 실패는 없고 건너뜀이 있으면 ('불완전', 3), 모두 통과면 ('통과', 0)."""
    if any(s.status == FAIL for s in steps):
        return "실패", 1
    if any(s.status == SKIP for s in steps):
        return "불완전", 3
    return "통과", 0


def render(steps, files, note, base):
    lines = [f"검증 사다리 ({note} {len(files)}개)"]
    for number, step in enumerate(steps, 1):
        lines.append(f"{number}. {step.name:<18} {step.status:<4} — {step.detail}")
    failed = [s for s in steps if s.status == FAIL]
    skipped = [s for s in steps if s.status == SKIP]
    lines.append(f"결과: {verdict_of(steps)[0]} (실패 {len(failed)} · 건너뜀 {len(skipped)})")
    if skipped:
        lines.append("※ 건너뛴 검증은 통과가 아닙니다 — 보고에는 '실행 필요: " + ", ".join(s.name for s in skipped) + "' 라고 적으세요(종료 코드 3).")
    return lines


def main(argv=None, runner=default_runner, which=shutil.which, module_ok=has_module, out=print):
    safe_output()
    parser = argparse.ArgumentParser(description="검증 사다리(시험·검증기·정적 검사)를 한 번에 돌린다")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="저장소 루트(기본: 이 스크립트의 저장소)")
    parser.add_argument("--base", default=DEFAULT_BASE, help="비교 기준 커밋·브랜치(기본: %(default)s)")
    parser.add_argument("--tests-pattern", help="시험 파일 이름 패턴(예: test_llm_timeout.py) — 일부만 돌릴 때")
    parser.add_argument("--json", action="store_true", help="사람이 읽는 표 대신 JSON 으로 낸다")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if not (root / "scripts" / "validate_repo.py").exists():
        out(f"[사용법 오류] 저장소 루트가 아닙니다: {one_line(str(root), 120)}")
        return 2
    steps, files, note = run_ladder(root, args.base, args.tests_pattern, runner, which, module_ok)
    verdict, code = verdict_of(steps)
    if args.json:
        out(json.dumps({"base": args.base, "result": verdict, "changed_python_files": files, "steps": [s.as_dict() for s in steps]}, ensure_ascii=False, indent=2))
    else:
        for line in render(steps, files, note, args.base):
            out(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
