"""블로그 한 곳을 한 번 실행한다: 주제 선정 → 생성 → 게이트 → (게시 | 초안) → 이력 기록.

사용: python -m pipeline.run --blog blogger_macat [--dry-run] [--publish auto|on|off] [--topic "..."]

종료 코드
  0 정상 종료(게이트 탈락·일일 상한·주제 없음으로 '건너뜀'인 경우 포함)
  1 인프라 실패(LLM 호출·게시 API·이력 파일). Actions 실행이 실패로 표시되어 알림이 간다
  2 설정 오류(레지스트리·프롬프트·시크릿 누락)

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

    if _flag(environ, "PIPELINE_PAUSE"):
        out("[일시정지] PIPELINE_PAUSE 가 켜져 있어 실행하지 않습니다.")
        return EXIT_OK
    if blog["mode"] == "off":
        out(f"[{blog['key']}] mode=off — 실행하지 않습니다.")
        return EXIT_OK

    policy = publish_policy(args.publish, environ)
    will_publish = (policy == "on") or (policy == "auto" and blog["mode"] == "auto")

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
        out(f"[{blog['key']}] 오늘({today}) 상한 {cap}건에 도달해 건너뜁니다.")
        return EXIT_OK

    # ---- LLM --------------------------------------------------------------
    if llm is None:
        if dry:
            llm = stub_llm
        else:
            api_key = resolve_secrets(blog, environ).get("llm_api_key", "")
            if not api_key:
                out(f"[설정 오류] LLM 키({blog['secrets']['llm_api_key']})가 없습니다. Settings > Secrets 를 확인하세요.")
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

    if not topic:
        out(f"[{blog['key']}] 고를 주제가 없습니다({source}). 건너뜁니다.")
        record({"status": "skipped_no_topic", "topic": "", "reasons": [f"[TOPIC] {source}"]})
        return EXIT_OK
    out(f"[{blog['key']}] 주제({source}): {topic}")

    # ---- 생성 + 게이트(탈락 사유를 넣어 재작성) -----------------------------
    accepted, model, attempts, reasons, feedback = None, "", 0, [], None
    for attempt in range(1, int(profile.get("max_attempts", 3)) + 1):
        attempts = attempt
        try:
            raw, model = llm(build_prompt(template, topic, profile, feedback))
        except LLMError as exc:
            out(f"[인프라 오류] LLM 호출 실패: {exc}")
            record({"status": "llm_failed", "topic": topic, "reasons": [f"[LLM] {mask(exc)[:300]}"], "attempts": attempt})
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
        out(f"[{blog['key']}] 게이트를 통과하지 못해 게시하지 않습니다: {'; '.join(reasons)}")
        record({"status": "rejected", "topic": topic, "reasons": reasons, "attempts": attempts, "model": model})
        _write_summary(environ, f"### {blog['key']}\n- 결과: **rejected** — {'; '.join(reasons)}")
        return EXIT_OK

    final_html = gates.append_disclosure(accepted["content"], profile)
    post = {"title": accepted["title"], "labels": accepted["labels"], "content_html": final_html}

    # ---- 게시 / 초안 ------------------------------------------------------
    status, url, post_id, exit_code, extra = "draft", "", "", EXIT_OK, []
    if dry:
        out("[DRY_RUN] 게이트 통과 — 게시·저장 없이 종료합니다.")
        out(f"  제목: {post['title']} / 라벨: {post['labels']} / 본문 {gates.text_length(gates.plain_text(accepted['content']))}자")
        return EXIT_OK
    if will_publish:
        missing = [r for r in missing_secret_roles(blog, environ) if r != "llm_api_key"]
        if missing:
            status = "generated_unpublished"
            extra = [f"[SECRETS] 게시 시크릿 미등록: {', '.join(missing)}"]
            out(f"  게시 시크릿이 없어 초안만 저장합니다 (미등록: {', '.join(missing)})")
        else:
            try:
                publisher = (publisher_factory or default_publisher_factory)(blog, environ)
                publisher.healthcheck()
                result = publisher.publish(post["title"], post["content_html"], post["labels"], draft=False)
                status, url, post_id = "posted", result.url, result.post_id
                out(f"  게시 성공: {url}")
            except PublishError as exc:
                status, exit_code = "publish_failed", EXIT_INFRA
                extra = [f"[{exc.code}] {mask(exc)[:300]}"]
                out(f"[인프라 오류] 게시 실패({exc.code}): {exc}")
    else:
        out("  게시 정책이 draft/off 여서 초안만 저장합니다.")

    meta = {"topic": topic, "status": status, "generated_at": local_now.isoformat(), "url": url}
    draft_path = save_draft(root, blog, local_now, post, meta)
    record({"status": status, "topic": topic, "topic_source": source, "title": post["title"],
            "labels": post["labels"], "url": url, "post_id": post_id, "model": model,
            "attempts": attempts, "reasons": extra})
    out(f"  초안 저장: {draft_path.relative_to(root).as_posix()} / 상태: {status}")
    _write_summary(environ, f"### {blog['key']}\n- 결과: **{status}** — {post['title']}\n- URL: {url or '(없음)'}")
    return exit_code


def main(argv=None):
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
