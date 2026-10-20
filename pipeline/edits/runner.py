"""이슈 한 건 처리: 인식 → 파싱 → 검증 → 대상 해석 → 수정 → 사후 검증 → (파일 쓰기) → 산출물.

git·PR 은 이 모듈이 하지 않는다(워크플로가 한다). 이 모듈은 작업 트리의 대상 파일 한 개를 고치고,
워크플로가 쓸 파일(result.json, files.txt, commit_msg.txt, pr_title.txt, pr_body.md, comment.md …)을 --out 폴더에 쓴다.
`resolve_request` 는 '요청이 무엇을 허용하는가'만 해석하므로 PR 범위 검증(scope_check)도 같은 기준을 쓴다.

CLI: python -m pipeline.edits.runner --issue-file issue.json --out DIR [--dry-run]
     python -m pipeline.edits.runner --verify-staged DIR/files.txt   (스테이징 목록 == 허용 목록 확인)

종료 코드: 0 처리 끝(ok·rejected·ignored 포함) / 1 인프라 실패(AI·네트워크) / 2 설정·명세 오류
"""
import argparse
import json
import os
import posixpath
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pipeline import registry as registry_mod
from pipeline.console import safe_output
from pipeline.edits import checks, forms, frontmatter, ops, pages, spec as spec_mod, targets

MAX_FIELD_CHARS = 5000
EXIT_OK, EXIT_INFRA, EXIT_CONFIG = 0, 1, 2


@dataclass
class Result:
    status: str                       # ok | rejected | ignored | error
    message: str = ""
    reasons: list = field(default_factory=list)
    exit_code: int = EXIT_OK
    files: list = field(default_factory=list)
    branch: str = ""
    edit_type: str = ""
    target: str = ""
    ad_surface: bool = False
    commit_message: str = ""
    pr_title: str = ""
    pr_body: str = ""
    summary: str = ""
    comment: str = ""


@dataclass
class Request:
    """검증을 통과한 수정 요청: 무엇을·어디까지 고칠 수 있는가."""
    spec: dict
    number: int
    login: str
    assoc: str
    edit_key: str
    cfg: dict
    fields: dict
    target: dict                      # {path, title, id}
    patterns: list                    # 허용 경로(자리표시자 해석 후)
    ad_surface: bool


# ----------------------------------------------------------------------------
# 보조
# ----------------------------------------------------------------------------
def protected_paths(root):
    """광고 표면(ad_surface=true 블로그)의 보호 경로 목록. 레지스트리를 못 읽으면 RegistryError(호출부가 요청을 거부한다 — fail closed)."""
    reg = registry_mod.load_registry(Path(root) / "pipeline" / "blogs.json")
    out = []
    for raw in reg.get("blogs", []):
        blog = registry_mod.merged_blog(reg, raw)
        if blog.get("ad_surface"):
            out.extend(blog.get("protected_paths", []))
    return out


def is_protected(path, protected):
    """`./about.md`·`a//b` 같은 표기 차이로 비교를 우회하지 못하게 양쪽을 정규화한다."""
    path = posixpath.normpath(str(path).replace("\\", "/"))
    for p in protected:
        norm = posixpath.normpath(str(p).replace("\\", "/"))
        if path == norm or (str(p).endswith("/") and path.startswith(norm + "/")):
            return True
    return False


def _slug(text, limit=30):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:limit] or "x"


def _one_line(text, limit=90):
    """한 줄로 접고 자르며 멘션(@)을 무력화한다(커밋 제목·PR 제목·사유 문장용)."""
    return re.sub(r"\s+", " ", str(text)).strip()[:limit].replace("@", "@​")


def _code(text, limit=90):
    """신뢰할 수 없는 문자열을 한 줄 코드 스팬으로(마크다운·멘션·줄 시작 트레일러·워크플로 명령을 무력화)."""
    return "`" + re.sub(r"[`\s]+", " ", str(text)).strip()[:limit] + "`"


def _fence(text):
    """사용자 입력을 코드 펜스 안에 안전하게 넣는다(펜스 탈출·멘션 방지)."""
    clean = frontmatter.normalize_newlines(text).replace("~~~", "~ ~ ~").replace("@", "@​")
    return f"~~~~text\n{clean}\n~~~~"


def _reject(reasons, hint="", edit_type="", target=""):
    reasons = [_one_line(r, 400) for r in reasons]
    comment ="⚠️ **수정하지 않았습니다.**\n\n사유:\n" + "\n".join(f"- {r}" for r in reasons)
    if hint:
        comment += f"\n\n{hint}"
    comment += "\n\n(저장소는 변경되지 않았습니다. 내용을 고쳐 새 이슈로 올려 주세요.)"
    return Result("rejected", message=reasons[0], reasons=reasons, comment=comment, edit_type=edit_type, target=target)


def _error(message, exit_code=EXIT_INFRA):
    message = _one_line(message, 400)
    comment =f"❌ **처리 중 오류가 발생했습니다.**\n\n- {message}\n\n저장소는 변경되지 않았습니다. Actions 로그를 확인하세요."
    return Result("error", message=message, reasons=[message], comment=comment, exit_code=exit_code)


def build_llm(env, registry_models_):
    key = (env.get("GEMINI_API_KEY") or "").strip()
    if not key:
        return None
    from pipeline.llm import make_gemini_llm
    return make_gemini_llm(key, registry_models_, max_retries=2)


def registry_models(root):
    try:
        reg = registry_mod.load_registry(Path(root) / "pipeline" / "blogs.json")
        return reg["defaults"]["llm"]["models"]
    except (registry_mod.RegistryError, KeyError):
        return ["gemini-3.8-flash"]


def default_image_picker():
    """레거시 엔진의 Unsplash 검색을 재사용한다(Phase 3에서 pipeline 으로 이관)."""
    if not (os.environ.get("UNSPLASH_ACCESS_KEY") or "").strip():
        return None
    import generator  # noqa: PLC0415 - 환경변수를 읽는 모듈이라 키 확인 뒤에만 import

    def pick(queries, used):
        picked = generator.pick_images(queries, set(used), 1, allow_pool=False)
        if picked:
            generator.trigger_download(picked[0])
        return picked[0] if picked else None
    return pick


# ----------------------------------------------------------------------------
# 요청 해석 (수정은 하지 않는다)
# ----------------------------------------------------------------------------
def resolve_request(issue, root):
    """Request 또는 Result(ignored/rejected/error). 파일을 읽기만 하고 아무것도 쓰지 않는다."""
    root = Path(root)
    login = (issue.get("user") or {}).get("login", "?")
    assoc = str(issue.get("author_association") or "").upper()
    if "pull_request" in issue:
        return Result("ignored", message="PR 은 처리하지 않습니다.")
    if assoc not in spec_mod.ALLOWED_ASSOCIATIONS:
        return Result("ignored", message=f"작성자 권한({assoc or '알 수 없음'})이 없어 처리하지 않습니다.")

    try:
        spec = spec_mod.load_spec(root)
        problems = spec_mod.validate_spec(spec)
        if problems:
            return _error("수정 명세가 올바르지 않습니다: " + "; ".join(problems), EXIT_CONFIG)
        templates = forms.load_templates(root)
        labels = forms.label_map(templates)
        flabels = forms.field_labels(templates)
    except (spec_mod.SpecError, forms.FormError) as exc:
        return _error(str(exc), EXIT_CONFIG)

    issue_label, why = forms.identify_issue_label(issue, spec, templates, labels)
    if not issue_label:
        return _reject([why], "제공된 이슈 양식('고정 페이지 수정' 또는 '기존 게시글 이미지 변경')으로 작성해 주세요.")
    fields, duplicates = forms.parse_issue_body(issue.get("body") or "", labels)
    if duplicates:
        return _reject([f"항목 제목이 중복되었습니다: {', '.join(duplicates)} (본문 안에 양식 제목과 같은 줄이 있으면 처리할 수 없습니다)"])
    too_long = [flabels.get(k, k) for k, v in fields.items() if len(v) > MAX_FIELD_CHARS]
    if too_long:
        return _reject([f"입력이 너무 깁니다(최대 {MAX_FIELD_CHARS}자): {', '.join(too_long)}"])

    candidates = spec_mod.edit_types_for_label(spec, issue_label)
    if issue_label == "edit:page":
        edit_key = forms.option_id(fields.get("edit_type"))
        if edit_key not in candidates:
            return _reject([f"알 수 없는 수정 항목입니다: {edit_key or '(없음)'}"], "양식의 '수정 항목' 목록에서 선택해 주세요.")
    elif len(candidates) == 1:
        edit_key = next(iter(candidates))
    else:
        return _error(f"{issue_label} 에 수정 항목이 여러 개라 양식만으로 정할 수 없습니다(명세 확인).", EXIT_CONFIG)
    cfg = candidates[edit_key]

    missing = [flabels.get(k, k) for k in cfg["required"] if not fields.get(k)]
    if missing:
        return _reject([f"필수 항목이 비어 있습니다: {', '.join(missing)}"], edit_type=edit_key)

    if cfg["target"] == "page":
        page_id = forms.option_id(fields["target_page"])
        try:
            entry = pages.find_page(pages.load_registry(root), page_id)
        except pages.PagesError as exc:
            return _error(str(exc), EXIT_CONFIG)
        if not entry:
            return _reject([f"pages.json 에 없는 페이지입니다: {page_id}"],
                           "새 페이지라면 front matter 에 `editable: true` 를 넣고 동기화를 기다려 주세요.", edit_key)
        target = {"path": entry["path"], "title": entry["title"], "id": entry["id"]}
    else:
        hits, how = targets.match_post(fields["target_post"], targets.load_post_index(root))
        if how == "invalid":
            return _reject(["게시글 주소/제목이 올바르지 않습니다(한 줄, 300자 이하)."], edit_type=edit_key)
        if not hits:
            return _reject(["일치하는 게시글을 찾지 못했습니다."],
                           "블로그에서 글을 열어 주소창의 공개 URL 을 복사하거나, 글 제목을 정확히 입력해 주세요.", edit_key)
        if len(hits) > 1:
            return _reject([f"여러 글({len(hits)}건)이 일치해 대상을 정할 수 없습니다: " + " / ".join(targets.describe(hits))],
                           "공개 URL 로 정확히 지정해 주세요.", edit_key)
        target = {"path": hits[0]["path"], "title": hits[0]["title"], "id": Path(hits[0]["path"]).stem}

    path = target["path"]
    try:
        patterns = spec_mod.resolve_allowed(cfg, path)
    except ValueError:  # 레지스트리·인덱스가 변조되어 올바르지 않은 경로가 들어온 경우
        return _reject([f"{path} 은(는) 올바르지 않은 경로라 고칠 수 없는 경로입니다."], edit_type=edit_key)
    if not spec_mod.path_allowed(path, patterns):
        return _reject([f"{path} 은(는) 이 수정 항목으로 고칠 수 없는 경로입니다."], edit_type=edit_key, target=path)

    try:
        protected = protected_paths(root)
    except registry_mod.RegistryError as exc:
        return _error(f"블로그 레지스트리를 읽을 수 없어 광고 표면 여부를 확인할 수 없습니다: {exc}", EXIT_CONFIG)
    ad_surface = is_protected(path, protected)
    if ad_surface and assoc != "OWNER":
        return _reject([f"{path} 는 광고 심사 대상 페이지라 저장소 소유자(OWNER)의 요청만 처리합니다."], edit_type=edit_key, target=path)

    return Request(spec=spec, number=issue.get("number"), login=login, assoc=assoc, edit_key=edit_key, cfg=cfg,
                   fields=fields, target=target, patterns=patterns, ad_surface=ad_surface)


def check_mode(cfg):
    return {"front_matter": "front_matter", "image": "image"}.get(cfg["method"], "body")


# ----------------------------------------------------------------------------
# 본 처리
# ----------------------------------------------------------------------------
def process_issue(issue, root, env=None, llm=None, image_picker=None, dry_run=False):
    env = os.environ if env is None else env
    root = Path(root)
    req = resolve_request(issue, root)
    if isinstance(req, Result):
        return req
    cfg, fields, target, path = req.cfg, req.fields, req.target, req.target["path"]
    limits = req.spec["limits"]

    file_path = root / path
    try:
        text, newline = frontmatter.read_file(file_path)
    except (OSError, UnicodeDecodeError) as exc:
        return _error(f"대상 파일을 읽을 수 없습니다: {path} ({type(exc).__name__})", EXIT_CONFIG)
    if len(text) > limits["max_file_chars"]:
        return _reject([f"{path} 파일이 너무 커서({len(text)}자) 자동 수정하지 않습니다."], edit_type=req.edit_key, target=path)

    method = cfg["method"]
    try:
        if method in ("text", "llm_patch", "image") and llm is None:
            llm = build_llm(env, registry_models(root))
        if method == "image" and image_picker is None:
            image_picker = default_image_picker()
        if method == "text":
            new_text, how = ops.op_text(text, fields, cfg, llm)
        elif method == "link":
            new_text, how = ops.op_link(text, fields)
        elif method == "front_matter":
            new_text, how = ops.op_front_matter(text, fields, cfg)
        elif method == "llm_patch":
            new_text, how = ops.op_llm_patch(text, fields, cfg, llm), "AI 최소 패치"
        else:
            new_text, how = ops.op_image(text, fields, {"path": path, "title": target["title"]}, root, llm, image_picker)
    except ops.EditError as exc:
        return _reject([str(exc)], edit_type=req.edit_key, target=path)
    except ops.InfraError as exc:
        return _error(str(exc))

    reasons = checks.verify_changes({path: (text, new_text)}, req.patterns, limits, mode=check_mode(cfg),
                                    only_fields=cfg.get("only_fields"), ai_patch=(how == "AI 최소 패치"))
    if reasons:
        return _reject(reasons, edit_type=req.edit_key, target=path)

    if not dry_run:
        frontmatter.write_file(file_path, new_text, newline)
    number, login, assoc = req.number, req.login, req.assoc
    run_no = re.sub(r"[^0-9]", "", str(env.get("GITHUB_RUN_NUMBER", "")))
    branch = f"{req.spec['output']['branch_prefix']}{number}-{_slug(target['id'])}" + (f"-r{run_no}" if run_no else "")
    lines = checks.changed_line_count(text, new_text)
    diff = checks.unified_diff(text, new_text, path)
    summary = (f"- 대상: `{path}` ({_code(target['title'])})\n- 수정 항목: {cfg['label']} (`{req.edit_key}`, 방식: {_code(how, 120)})\n"
               f"- 바뀐 줄: {lines}줄")
    trailer = f"\nAd-Surface-Approved: 이슈 #{number} @{login}(OWNER) 요청 — {path}" if req.ad_surface else ""
    commit = (f"fix: [이슈 #{number}] {_one_line(target['title'], 40)} {cfg['label']} (issue-edit 봇) [대상: Chance_Blog]\n\n"
              f"{summary}\n\nRefs: #{number}\nRequested-By: @{login} ({assoc}){trailer}\n")
    pr_title = f"[이슈 #{number}] {_one_line(target['title'], 50)} — {cfg['label']}"
    ad_note = ("\n> ⚠️ **광고 표면 페이지**입니다. 소유자 요청에 따른 수정이며, **병합이 곧 승인**입니다. 병합 전에 변경 내용을 꼭 확인하세요.\n"
               if req.ad_surface else "")
    pr_body = (f"이슈 #{number} (@{login})의 수정 요청을 자동으로 처리한 PR 입니다.{ad_note}\n\n{summary}\n\n"
               f"### 요청 내용\n{_fence(fields.get('after') or fields.get('user_prompt') or '')}\n\n"
               f"### 변경 내용\n```diff\n{diff}\n```\n\n"
               "### 리뷰 체크리스트\n- [ ] 요청한 항목만 바뀌었다\n- [ ] 사실·수치·링크가 맞다\n- [ ] 광고 코드·레이아웃은 그대로다\n\n"
               f"Fixes #{number}\n")
    if req.ad_surface:
        pr_body += f"\nAd-Surface-Approved: 이슈 #{number} @{login}(OWNER) 요청 — {path}\n"
    return Result("ok", message=f"{path} 수정안 생성", files=[path], branch=branch, edit_type=req.edit_key, target=path,
                  ad_surface=req.ad_surface, commit_message=commit, pr_title=pr_title, pr_body=pr_body, summary=summary)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def write_outputs(result, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "status.txt").write_text(result.status + "\n", encoding="utf-8")
    (out / "branch.txt").write_text(result.branch + "\n", encoding="utf-8")
    (out / "files.txt").write_text("".join(f + "\n" for f in result.files), encoding="utf-8")
    (out / "commit_msg.txt").write_text(result.commit_message, encoding="utf-8")
    (out / "pr_title.txt").write_text(result.pr_title + "\n", encoding="utf-8")
    (out / "pr_body.md").write_text(result.pr_body, encoding="utf-8")
    (out / "summary.md").write_text(result.summary + "\n", encoding="utf-8")
    (out / "comment.md").write_text(result.comment + "\n" if result.comment else "", encoding="utf-8")


def verify_staged(files_txt, root=None):
    """git 스테이징 목록이 허용된 파일 목록과 정확히 같은지 확인한다(0: 같음)."""
    expected = {ln.strip() for ln in Path(files_txt).read_text(encoding="utf-8").splitlines() if ln.strip()}
    res = subprocess.run(["git", "-c", "core.quotepath=false", "diff", "--cached", "--name-only"], cwd=root,
                         capture_output=True, check=True)
    staged = {ln.strip() for ln in res.stdout.decode("utf-8", "replace").splitlines() if ln.strip()}
    if staged != expected:
        print(f"스테이징 목록이 허용 목록과 다릅니다. 허용={sorted(expected)} 스테이징={sorted(staged)}")
        return 1
    return 0


def main(argv=None):
    safe_output()
    parser = argparse.ArgumentParser(prog="python -m pipeline.edits.runner")
    parser.add_argument("--issue-file")
    parser.add_argument("--out")
    parser.add_argument("--root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-staged")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]

    if args.verify_staged:
        return verify_staged(args.verify_staged, root)
    if not (args.issue_file and args.out):
        parser.error("--issue-file 과 --out 이 필요합니다.")
    dry = args.dry_run or str(os.environ.get("DRY_RUN", "")).lower() in ("1", "true", "yes")
    try:
        issue = json.loads(Path(args.issue_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result = _error(f"이슈 데이터를 읽을 수 없습니다: {type(exc).__name__}", EXIT_CONFIG)
    else:
        result = process_issue(issue, root, dry_run=dry)
    write_outputs(result, args.out)
    print(f"[issue-edit] status={result.status} edit={_one_line(result.edit_type or '-', 60)} "
          f"target={_one_line(result.target or '-', 120)} {'(dry-run) ' if dry else ''}{_one_line(result.message, 300)}")
    for r in result.reasons:
        print(f"  - {_one_line(r, 300)}")
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
