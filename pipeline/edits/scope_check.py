"""PR 범위 검증: 이슈 양식으로 접수된 요청과 PR 의 실제 변경이 일치하는지 확인한다.

누가 만든 PR 이든(Copilot·사람·봇) 같은 기준으로 본다. 목적은 '앞부분만 읽고 나머지를 추정해서 요청 밖을 바꾸는' 실수를
개발 지식이 없어도 알아볼 수 있게 하는 것이다.

  ✅ 통과        요청한 교체와 정확히 일치하는 변경만 있다(문자 그대로 교체·링크·SEO 메타처럼 기대값을 계산할 수 있는 경우)
  ⚠️ 확인 필요   범위 안이지만 내용이 요청과 맞는지 자동으로 증명할 수 없다(AI 가 문장을 쓴 경우 등)
  ❌ 범위 밖     허용되지 않은 파일·광고 코드·front matter 변경, 요청과 다른 교체 등

PR 이 고치려는 코드(pipeline/ 등)를 실행하지 않도록, 이 도구는 항상 base 커밋의 체크아웃에서 실행하고
head 쪽 파일은 `git show <sha>:<path>` 로 읽기만 한다.

CLI
  python -m pipeline.edits.scope_check --find-issue pr.json                       # PR 본문에서 연결된 이슈 번호 출력
  python -m pipeline.edits.scope_check --pr-file pr.json --issue-file issue.json --out DIR
종료 코드: 0 통과/확인 필요/해당 없음, 1 범위 밖 변경 발견, 2 설정 오류
"""
import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.console import safe_output
from pipeline.edits import checks, frontmatter, ops, runner, spec as spec_mod

MARKER = "<!-- issue-edit-scope-check -->"
_ISSUE_RE = re.compile(r"(?i)\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s*:?\s+#(\d+)")


@dataclass
class Report:
    verdict: str                                   # PASS | WARN | FAIL | SKIP
    items: list = field(default_factory=list)      # [(기호, 문장)]
    title: str = ""
    details: list = field(default_factory=list)    # 코드 블록으로 보여 줄 추가 정보

    def markdown(self):
        head = {"PASS": "✅ **통과** — 요청한 범위 안의 변경만 있습니다.",
                "WARN": "⚠️ **확인 필요** — 범위 안이지만 내용이 요청과 맞는지 자동으로 증명할 수 없습니다. 아래 변경을 직접 확인해 주세요.",
                "FAIL": "❌ **요청 범위 밖 변경이 있습니다.** 병합하지 말고 수정을 요청하세요(예: \"요청한 부분만 바꾸고 나머지는 되돌려 주세요\").",
                "SKIP": "ℹ️ 이슈 양식으로 접수된 수정 요청이 아니라 범위 검증을 건너뜁니다."}[self.verdict]
        out = [MARKER, f"### 🔎 요청 범위 검증{(' — ' + self.title) if self.title else ''}", "", head, ""]
        out += [f"- {sym} {text}" for sym, text in self.items]
        for block in self.details:
            out += ["", "```diff", block, "```"]
        return "\n".join(out) + "\n"


def find_issue_number(pr_text):
    m = _ISSUE_RE.search(pr_text or "")
    return int(m.group(1)) if m else None


def _git(root, *args):
    return subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=root, capture_output=True, check=True).stdout


def git_changed(root, base, head):
    """[(상태, 경로)] — 이름 변경은 삭제+추가로 본다."""
    out = _git(root, "diff", "--name-status", "--no-renames", base, head).decode("utf-8", "replace")
    changes = []
    for line in out.splitlines():
        status, _, path = line.partition("\t")
        if path:
            changes.append((status[:1], path))
    return changes


def git_show(root, sha, path):
    try:
        return frontmatter.normalize_newlines(_git(root, "show", f"{sha}:{path}").decode("utf-8"))
    except subprocess.CalledProcessError:
        return None


def expected_after(req, before_text):
    """요청만으로 기대값을 계산할 수 있으면 그 텍스트, 아니면 None."""
    fields, method = req.fields, req.cfg["method"]
    try:
        if method == "text" and frontmatter.normalize_newlines(fields.get("before", "")).strip():
            return ops.op_text(before_text, fields, req.cfg, None)[0]
        if method == "link":
            return ops.op_link(before_text, fields)[0]
        if method == "front_matter":
            return ops.op_front_matter(before_text, fields, req.cfg)[0]
    except ops.EditError:
        return None
    return None


def check_pull(issue, root, base, head, changes=None, show=None):
    """이슈 요청과 PR(base..head)의 변경을 비교한 Report."""
    show = show or (lambda sha, path: git_show(root, sha, path))
    req = runner.resolve_request(issue, root)
    if isinstance(req, runner.Result):
        if req.status == "ignored" or "인식하지 못했습니다" in req.message:
            return Report("SKIP", [("ℹ️", req.message)])
        return Report("FAIL", [("❌", f"연결된 이슈의 요청을 해석할 수 없습니다: {req.message}")])
    changes = changes if changes is not None else git_changed(root, base, head)
    path = req.target["path"]
    title = f"이슈 #{req.number} — `{path}` · {req.cfg['label']}"
    items, details, fail = [], [], False

    if not changes:
        return Report("FAIL", [("❌", "PR 에 변경된 파일이 없습니다.")], title)
    others = [p for _, p in changes if p != path]
    deleted = [p for s, p in changes if s == "D"]
    if others:
        fail = True
        shown = ", ".join(f"`{p}`" for p in others[:8]) + (" …" if len(others) > 8 else "")
        items.append(("❌", f"요청하지 않은 파일이 바뀌었습니다({len(others)}개): {shown}"))
    if path in deleted:
        return Report("FAIL", items + [("❌", f"대상 파일 `{path}` 이(가) 삭제되었습니다.")], title)
    if all(p != path for _, p in changes):
        return Report("FAIL", items + [("❌", f"대상 파일 `{path}` 이(가) 바뀌지 않았습니다.")], title)

    before, after = show(base, path), show(head, path)
    if before is None or after is None:
        return Report("FAIL", items + [("❌", f"`{path}` 의 이전/이후 내용을 읽을 수 없습니다.")], title)
    items.append(("✅" if not others else "ℹ️", f"대상 파일 `{path}` 이(가) 변경되었습니다."))

    reasons = checks.verify_changes({path: (before, after)}, req.patterns, req.spec["limits"],
                                    mode=runner.check_mode(req.cfg), only_fields=req.cfg.get("only_fields"))
    if reasons:
        fail = True
        items += [("❌", r) for r in reasons]
    else:
        items.append(("✅", "허용 경로·변경 크기·광고 코드·front matter·위험 마크업 검사를 통과했습니다."))

    proven = False
    if req.cfg["method"] == "image":
        fm = frontmatter.parse_front_matter(frontmatter.split_front_matter(after)[0]) or {}
        old_fm = frontmatter.parse_front_matter(frontmatter.split_front_matter(before)[0]) or {}
        old_url, new_url = str(old_fm.get("image") or ""), str(fm.get("image") or "")
        if new_url.startswith(ops.UNSPLASH_PREFIX) and old_url and after == before.replace(old_url, new_url):
            items.append(("✅", "대표 이미지 URL 만 새 이미지로 바뀌었고 나머지는 그대로입니다."))
            proven = True
        else:
            fail = True
            items.append(("❌", "이미지 교체 외의 변경이 있거나 새 이미지가 Unsplash 주소가 아닙니다."))
    else:
        want = expected_after(req, before)
        if want is not None:
            if after == want:
                items.append(("✅", "요청한 교체와 정확히 일치하는 변경입니다(그 밖의 글자는 하나도 바뀌지 않았습니다)."))
                proven = True
            else:
                fail = True
                items.append(("❌", "요청한 교체와 다릅니다. 요청 외의 부분이 바뀌었거나 교체 결과가 요청과 다릅니다."))
                details.append(checks.unified_diff(want, after, f"{path} (기대 → 실제)"))
        else:
            items.append(("⚠️", "이 수정 항목은 AI 가 문장을 쓰므로 결과가 요청과 맞는지 자동으로 증명할 수 없습니다."))
    if fail:
        return Report("FAIL", items, title, details)
    return Report("PASS" if proven else "WARN", items, title, details)


def main(argv=None):
    safe_output()
    parser = argparse.ArgumentParser(prog="python -m pipeline.edits.scope_check")
    parser.add_argument("--find-issue")
    parser.add_argument("--pr-file")
    parser.add_argument("--issue-file")
    parser.add_argument("--out")
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]

    if args.find_issue:
        pr = json.loads(Path(args.find_issue).read_text(encoding="utf-8"))
        number = find_issue_number(f"{pr.get('title', '')}\n{pr.get('body') or ''}")
        print(number if number else "")
        return 0
    if not (args.pr_file and args.issue_file and args.out):
        parser.error("--pr-file, --issue-file, --out 이 필요합니다.")
    try:
        pr = json.loads(Path(args.pr_file).read_text(encoding="utf-8"))
        issue = json.loads(Path(args.issue_file).read_text(encoding="utf-8"))
        base, head = pr["base"]["sha"], pr["head"]["sha"]
        report = check_pull(issue, root, base, head)
    except (OSError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError, spec_mod.SpecError) as exc:
        print(f"[오류] {type(exc).__name__}: {exc}")
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(report.markdown(), encoding="utf-8")
    (out / "verdict.txt").write_text(report.verdict + "\n", encoding="utf-8")
    print(f"[scope-check] {report.verdict} {report.title}")
    for sym, text in report.items:
        print(f"  {sym} {text}")
    return 1 if report.verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
