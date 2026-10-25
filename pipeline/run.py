"""블로그 한 곳을 한 번 실행한다: 주제 선정 → 생성 → 게이트 → (게시 | 초안) → 이력 기록.

사용: python -m pipeline.run --blog blogger_macat [--dry-run] [--publish auto|on|off] [--topic "..."]

종료 코드
  0 정상 종료(일일 상한·정지·게이트 탈락·주제 없음 등 '건너뜀' 포함). 건너뛴 사유는
    '[SKIP] code=...' 한 줄과 실행 요약에 남는다(docs/ARCHITECTURE.md 4-1)
  1 인프라 실패(LLM 호출·주제 확장·게시 API·이력 파일). Actions 실행이 실패로 표시되어 알림이 간다
  2 설정 오류(레지스트리·프롬프트·LLM 키·게시 대상인데 게시용 시크릿 누락)

환경변수
  DRY_RUN=1          파일·게시 없이 전체 흐름만 확인(스텁 LLM)
  PIPELINE_PAUSE=1   킬 스위치. 아무 것도 하지 않고 종료(저장소 Variables 로 설정)
  BLOGGER_PUBLISH    1/0/auto (호환용). 비어 있으면 레지스트리 mode 를 따른다
  BLOGGER_TOPIC      주제 지정(수동 실행용)
"""
import argparse
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline import gates
from pipeline.console import md_cell, one_line, safe_output
from pipeline.llm import LLMError, make_gemini_llm, mask
from pipeline.publishers.base import PublishError
from pipeline.registry import (ROOT, RegistryError, get_blog, load_profile, load_registry,
                               merged_blog, missing_secret_roles, resolve_secrets, validate_registry)
from pipeline.state import KST, StateError, entry_titles, other_blog_titles, read_json_list, write_json_atomic
from pipeline.stubs import stub_llm
from pipeline.topics import clean_topic, pick_topic

EXIT_OK, EXIT_INFRA, EXIT_CONFIG = 0, 1, 2
HISTORY_KEEP = 200
DRAFTS_KEEP = 120
TITLE_SHOWN = 120      # 로그·요약에 보여 줄 글 제목의 최대 길이(제목은 LLM 유래)
REASONS_SHOWN = 600    # 로그·요약에 보여 줄 게이트 탈락 사유 전체의 최대 길이
COUNTED_STATUSES = {"posted", "draft", "generated_unpublished"}
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="python -m pipeline.run")
    p.add_argument("--blog", required=True, help="pipeline/blogs.json 의 key")
    p.add_argument("--root", default=None, help="저장소 루트(기본: 이 패키지의 상위)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--publish", choices=["auto", "on", "off"], default=None)
    p.add_argument("--topic", default=None)
    return p.parse_args(argv)


def _flag(environ, name):
    return str(environ.get(name, "")).strip().lower() in _TRUE


def publish_policy(cli_value, environ):
    raw = (cli_value or environ.get("BLOGGER_PUBLISH") or "").strip().lower()
    if raw in _TRUE or raw == "on":
        return "on"
    if raw in _FALSE or raw == "off":
        return "off"
    return "auto"


def load_prompt_template(root, blog):
    text = (Path(root) / blog["prompt"]).read_text(encoding="utf-8")
    match = re.search(r"```text\n(.*?)```", text, re.S)
    if not match or "{topic}" not in match.group(1):
        raise RegistryError(f"프롬프트 파일에 ```text 블록과 {{topic}} 자리표시자가 필요합니다: {blog['prompt']}")
    return match.group(1).strip()


def build_prompt(template, topic, profile, feedback=None):
    prompt = template.replace("{topic}", topic)
    extra = profile.get("prompt_extra") or []
    if extra:
        prompt += "\n\n[추가 규칙]\n" + "\n".join(f"- {line}" for line in extra)
    if feedback:
        prompt += ("\n\n[이전 시도에서 고쳐야 할 점]\n" + "\n".join(f"- {r}" for r in feedback)
                   + "\n위 문제를 모두 고쳐 처음부터 다시 작성한다.")
    return prompt


def save_draft(root, blog, when_kst, post, meta):
    """감사용 사본을 저장소에 남긴다(Jekyll은 언더스코어 폴더를 사이트로 내보내지 않는다)."""
    folder = Path(root) / blog["state"]["content_dir"]
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "-", post["title"]).strip("-")[:40] or "post"
    path = folder / f"{when_kst:%Y-%m-%d-%H%M}-{slug}.md"
    lines = [
        "---",
        f"title: {json.dumps(post['title'], ensure_ascii=False)}",
        f"labels: {json.dumps(post['labels'], ensure_ascii=False)}",
        f"topic: {json.dumps(meta['topic'], ensure_ascii=False)}",
        f"blog: {blog['key']}",
        f"status: {meta['status']}",
        f"generated_at: {meta['generated_at']}",
    ]
    if meta.get("url"):
        lines.append(f"url: {json.dumps(meta['url'])}")
    lines.append("---")
    path.write_text("\n".join(lines) + "\n\n" + post["content_html"] + "\n", encoding="utf-8")
    files = sorted(folder.glob("*.md"))
    for old in files[:-DRAFTS_KEEP]:
        old.unlink()
    return path


def _write_summary(environ, text):
    target = environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def skip_line(code, **fields):
    """건너뜀·실패를 로그에서 한 줄로 찾게 하는 규격: [SKIP] code=CODE key=value ... (docs/ARCHITECTURE.md 4-1)."""
    return " ".join([f"[SKIP] code={code}"] + [f"{key}={value}" for key, value in fields.items()])


def _summarize(environ, blog, code, text):
    """실행 요약 한 블록. 정상 건너뜀·경고·실패 모두 같은 모양으로 남긴다(성공 경로는 아래에서 따로 쓴다)."""
    _write_summary(environ, f"### {blog['key']}\n- 결과: **{code}** — {text}")


def default_publisher_factory(blog, environ):
    secrets = resolve_secrets(blog, environ)
    if blog["platform"] == "blogger":
        from pipeline.publishers.blogger import BloggerPublisher
        return BloggerPublisher(secrets["blog_id"], secrets["client_id"],
                                secrets["client_secret"], secrets["refresh_token"])
    raise RegistryError(f"이 러너가 지원하지 않는 platform: {blog['platform']}")


def run(argv=None, environ=None, now=None, llm=None, publisher_factory=None, rng=None, out=print):
    args = parse_args(argv)
    environ = os.environ if environ is None else environ
    root = Path(args.root).resolve() if args.root else ROOT
    now = now or datetime.now(timezone.utc)
    rng = rng or random.Random()
    dry = args.dry_run or _flag(environ, "DRY_RUN")

    # ---- 설정 -------------------------------------------------------------
    try:
        reg = load_registry(root / "pipeline" / "blogs.json")
        errors = validate_registry(reg, root)
        if errors:
            out("[설정 오류] 레지스트리 검증 실패:\n  - " + "\n  - ".join(errors))
            return EXIT_CONFIG
        blog = get_blog(reg, args.blog)
        if blog["platform"] != "blogger":
            out(f"[설정 오류] 이 러너는 platform=blogger 만 지원합니다 ({blog['platform']}). "
                "다른 플랫폼은 docs/ARCHITECTURE.md 로드맵을 따릅니다.")
            return EXIT_CONFIG
        profile = load_profile(blog["profile"], root / "pipeline" / "profiles")
        template = load_prompt_template(root, blog)
    except RegistryError as exc:
        out(f"[설정 오류] {exc}")
        return EXIT_CONFIG

    # 정지는 일부러 켜는 것이라 종료 코드는 0이다. 대신 ::notice:: 로 Actions 화면(실행 요약 위쪽 주석)에 남겨,
    # 변수를 켜 놓고 잊어도 "왜 아무것도 안 올라오지?" 할 때 눈에 띄게 한다.
    if _flag(environ, "PIPELINE_PAUSE"):
        out(skip_line("PAUSED", blog=blog["key"], var="PIPELINE_PAUSE"))
        out("[일시정지] PIPELINE_PAUSE 가 켜져 있어 실행하지 않습니다.")
        out(f"::notice::[{blog['key']}] 저장소 변수 PIPELINE_PAUSE 가 켜져 있어 이번 실행을 건너뜁니다. 계속 멈춰 둘 것이 아니라면 "
            "Settings > Secrets and variables > Actions > Variables 에서 PIPELINE_PAUSE 를 지우세요.")
        _summarize(environ, blog, "PAUSED", "저장소 변수 PIPELINE_PAUSE 가 켜져 있습니다.")
        return EXIT_OK
    if blog["mode"] == "off":
        out(skip_line("MODE_OFF", blog=blog["key"]))
        out(f"[{blog['key']}] mode=off — 실행하지 않습니다.")
        out(f"::notice::[{blog['key']}] 레지스트리(pipeline/blogs.json)에서 mode=off 로 정지된 블로그라 이번 실행을 건너뜁니다. "
            "다시 켜려면 mode 를 draft 또는 auto 로 바꾸세요.")
        _summarize(environ, blog, "MODE_OFF", "레지스트리(pipeline/blogs.json)에서 mode=off 로 정지된 블로그입니다.")
        return EXIT_OK

    policy = publish_policy(args.publish, environ)
    will_publish = (policy == "on") or (policy == "auto" and blog["mode"] == "auto")

    # 게시 대상인데 게시용 시크릿이 없으면 글을 만들기 전에 멈춘다. 예전에는 초안만 저장하고 초록으로 끝나
    # 게시가 한 번도 안 된 채 며칠이 지나도 눈에 띄지 않았다(D-25). 시크릿은 '이름'만 표시한다.
    if will_publish:
        missing = [role for role in missing_secret_roles(blog, environ) if role != "llm_api_key"]
        if missing:
            names = ", ".join(blog["secrets"].get(role, role) for role in missing)
            message = (f"게시용 시크릿이 등록되어 있지 않습니다: {names} "
                       "(저장소 Settings > Secrets and variables > Actions). "
                       "등록하기 전에는 이 블로그를 mode=draft 또는 off 로 두세요.")
            if not dry:
                out(skip_line("SECRETS_MISSING", blog=blog["key"], missing=names.replace(" ", "")))
                out(f"::error::[{blog['key']}] {message}")
                _summarize(environ, blog, "SECRETS_MISSING", message)
                return EXIT_CONFIG
            out(f"::warning::[{blog['key']}] (DRY_RUN이라 계속합니다) {message}")

    # ---- 상태·상한 --------------------------------------------------------
    history_path = root / blog["state"]["history"]
    try:
        history = read_json_list(history_path)
    except StateError as exc:
        out(f"[인프라 오류] {exc}")
        return EXIT_INFRA

    local_now = now.astimezone(KST)
    today = local_now.date()
    override = clean_topic(args.topic or environ.get("BLOGGER_TOPIC", ""))
    produced_today = [e for e in history if isinstance(e, dict)
                      and e.get("date") == today.isoformat() and e.get("status") in COUNTED_STATUSES]
    cap = blog["limits"]["max_posts_per_day"]
    if len(produced_today) >= cap and not override:
        counted = ", ".join(sorted({str(e.get("status")) for e in produced_today}))
        out(skip_line("DAILY_CAP", blog=blog["key"], date=today, cap=cap, today=len(produced_today)))
        out(f"::notice::[{blog['key']}] 오늘({today}) 상한 {cap}건에 도달해 건너뜁니다 "
            f"(오늘 기록: {counted}). 수동 실행에서 topic 을 입력하면 상한을 건너뛰고 실행합니다.")
        _summarize(environ, blog, "DAILY_CAP",
                   f"오늘({today}) 상한 {cap}건에 도달해 건너뜀(오늘 기록: {counted}). 게시되지 않은 초안도 상한에 포함됩니다.")
        return EXIT_OK

    # ---- LLM --------------------------------------------------------------
    if llm is None:
        if dry:
            llm = stub_llm
        else:
            api_key = resolve_secrets(blog, environ).get("llm_api_key", "")
            if not api_key:
                message = f"LLM 키({blog['secrets']['llm_api_key']})가 없습니다. Settings > Secrets 를 확인하세요."
                out(skip_line("SECRETS_MISSING", blog=blog["key"], missing=blog["secrets"]["llm_api_key"]))
                out(f"[설정 오류] {message}")
                out(f"::error::[{blog['key']}] {message}")
                _summarize(environ, blog, "SECRETS_MISSING", message)
                return EXIT_CONFIG
            llm = make_gemini_llm(api_key, blog["llm"]["models"], blog["llm"].get("max_retries", 2))

    # ---- 주제 -------------------------------------------------------------
    recent_titles = entry_titles(history[-100:])
    other_titles = other_blog_titles(root, [merged_blog(reg, b) for b in reg["blogs"]], blog["key"])
    if override:
        topic, source = override, "override"
    else:
        topic, source = pick_topic(profile, history, today, other_titles + recent_titles, rng, llm=llm)

    base_entry = {"v": 1, "blog": blog["key"], "date": today.isoformat(), "generated_at": local_now.isoformat()}

    def record(entry):
        entry = {**base_entry, **entry}
        if not dry:
            history.append(entry)
            write_json_atomic(history_path, history, keep=HISTORY_KEEP)
        return entry

    if not topic and source == "expand_failed":
        # 시드를 다 쓴 뒤 LLM에게 새 주제를 받는 호출이 실패했다. '주제 없음'이 아니라 인프라 실패다(E12).
        message = "주제 확장 LLM 호출이 실패했습니다. LLM 키·할당량·모델 이름을 확인하세요."
        out(skip_line("EXPAND_FAILED", blog=blog["key"]))
        out(f"::error::[{blog['key']}] {message}")
        record({"status": "llm_failed", "topic": "", "reasons": ["[TOPIC] expand_failed"]})
        _summarize(environ, blog, "EXPAND_FAILED", message)
        return EXIT_INFRA
    if not topic:
        out(skip_line("NO_TOPIC", blog=blog["key"], source=source))
        out(f"::warning::[{blog['key']}] 고를 주제가 없습니다({source}). 시드 주제를 보강하세요. 건너뜁니다.")
        record({"status": "skipped_no_topic", "topic": "", "reasons": [f"[TOPIC] {source}"]})
        _summarize(environ, blog, "NO_TOPIC", f"고를 주제가 없습니다({source}).")
        return EXIT_OK
    out(f"[{blog['key']}] 주제({source}): {topic}")

    # ---- 생성 + 게이트(탈락 사유를 넣어 재작성) -----------------------------
    accepted, model, attempts, reasons, feedback = None, "", 0, [], None
    for attempt in range(1, int(profile.get("max_attempts", 3)) + 1):
        attempts = attempt
        try:
            raw, model = llm(build_prompt(template, topic, profile, feedback))
        except LLMError as exc:
            out(skip_line("LLM_FAILED", blog=blog["key"], attempt=attempt))
            out(f"[인프라 오류] LLM 호출 실패: {one_line(mask(exc))}")
            out(f"::error::[{blog['key']}] LLM 호출이 실패했습니다. LLM 키·할당량·모델 이름을 확인하세요.")
            record({"status": "llm_failed", "topic": topic, "reasons": [f"[LLM] {mask(exc)[:300]}"], "attempts": attempt})
            _summarize(environ, blog, "LLM_FAILED", "LLM 호출이 실패했습니다(원인은 이 단계의 로그를 보세요).")
            return EXIT_INFRA
        try:
            parsed = gates.parse_labeled_post(raw)
        except gates.GateError as exc:
            reasons = [f"[PARSE] {exc}"]
            feedback = reasons
            out(f"  시도 {attempt}: 형식 오류 → 재작성 ({exc})")
            continue
        clean, stats = gates.sanitize_html(parsed["content"], allow_links=bool(profile.get("allow_links")))
        post = {"title": parsed["title"], "labels": parsed["labels"], "content": clean}
        result = gates.check_post(post, profile, recent_titles, other_titles, stats)
        if result.ok:
            accepted = post
            for warning in result.warnings:
                out(f"  참고: {warning}")
            break
        reasons = result.reasons
        feedback = result.reasons
        out(f"  시도 {attempt}: 게이트 탈락 → 재작성 ({'; '.join(result.codes())})")

    if accepted is None:
        # 사유에는 이력 속 다른 글의 제목이 들어 있을 수 있다(외부 유래). 로그·요약에는 한 줄로 접어서만 쓰고,
        # ::warning:: 주석에는 아예 넣지 않는다(고정 문장만).
        out(skip_line("GATE_REJECTED", blog=blog["key"], attempts=attempts))
        out(f"[{blog['key']}] 게이트를 통과하지 못해 게시하지 않습니다: {one_line('; '.join(reasons), REASONS_SHOWN)}")
        out(f"::warning::[{blog['key']}] 게이트를 {attempts}번 모두 통과하지 못해 게시하지 않았습니다. 다음 실행에서 다시 시도합니다.")
        record({"status": "rejected", "topic": topic, "reasons": reasons, "attempts": attempts, "model": model})
        _summarize(environ, blog, "GATE_REJECTED", md_cell('; '.join(reasons), REASONS_SHOWN))
        return EXIT_OK

    final_html = gates.append_disclosure(accepted["content"], profile)
    post = {"title": accepted["title"], "labels": accepted["labels"], "content_html": final_html}

    # ---- 게시 / 초안 ------------------------------------------------------
    status, url, post_id, exit_code, extra = "draft", "", "", EXIT_OK, []
    if dry:
        out("[DRY_RUN] 게이트 통과 — 게시·저장 없이 종료합니다.")
        out(f"  제목: {one_line(post['title'], TITLE_SHOWN)} / 라벨: {post['labels']} / 본문 {gates.text_length(gates.plain_text(accepted['content']))}자")
        _summarize(environ, blog, "DRY_RUN", f"게이트 통과, 게시·저장 없이 종료(제목: {md_cell(post['title'], TITLE_SHOWN)})")
        return EXIT_OK
    if will_publish:
        # 게시용 시크릿 누락은 위의 사전 점검에서 이미 걸러졌다(여기까지 오면 4종 모두 있다).
        try:
            publisher = (publisher_factory or default_publisher_factory)(blog, environ)
            publisher.healthcheck()
            result = publisher.publish(post["title"], post["content_html"], post["labels"], draft=False)
            status, url, post_id = "posted", result.url, result.post_id
            out(f"  게시 성공: {url}")
        except PublishError as exc:
            status, exit_code = "publish_failed", EXIT_INFRA
            extra = [f"[{exc.code}] {mask(exc)[:300]}"]
            out(skip_line("PUBLISH_FAILED", blog=blog["key"], reason=exc.code))
            out(f"[인프라 오류] 게시 실패({exc.code}): {one_line(mask(exc))}")
            out(f"::error::[{blog['key']}] 게시에 실패했습니다({exc.code}). 이 단계의 로그와 BLOGGER_API_SETUP.md 의 점검 항목을 확인하세요.")
    else:
        out("  게시 정책이 draft/off 여서 초안만 저장합니다.")

    meta = {"topic": topic, "status": status, "generated_at": local_now.isoformat(), "url": url}
    draft_path = save_draft(root, blog, local_now, post, meta)
    record({"status": status, "topic": topic, "topic_source": source, "title": post["title"],
            "labels": post["labels"], "url": url, "post_id": post_id, "model": model,
            "attempts": attempts, "reasons": extra})
    out(f"  초안 저장: {draft_path.relative_to(root).as_posix()} / 상태: {status}")
    _write_summary(environ, f"### {blog['key']}\n- 결과: **{status}** — {md_cell(post['title'], TITLE_SHOWN)}\n"
                            f"- URL: {url or '(없음)'}")
    return exit_code


def main(argv=None):
    safe_output()
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
