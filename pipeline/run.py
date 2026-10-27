"""블로그 한 곳을 한 번 실행한다: 주제 선정 → 생성 → 게이트 → (게시 | Blogger 초안함 업로드 | 초안 이슈 | 저장소 초안) → 이력 기록.

사용: python -m pipeline.run --blog blogger_macat [--dry-run] [--publish auto|draft|publish|on|off] [--topic "..."]
      python -m pipeline.run --blog blogger_macat --auth-check     # 글을 만들지 않고 인증만 점검(쓰기 없음)

글을 어디까지 보내는지는 레지스트리 mode 와 BLOGGER_PUBLISH(수동 실행 입력)로 정해진다:
  mode auto  → 즉시 게시(posted)             mode draft → Blogger 초안함에 업로드(draft_uploaded)
  게시용 시크릿 4종이 하나도 없는 mode draft 는 저장소 파일에만 저장한다(draft). 일부만 있으면 설정 오류다.
  업로드·게시 전에는 인증 점검(pipeline/auth_check.py: 토큰 갱신·blogs.get·블로그 주소 일치)을 먼저 한다.
  mode package(platform tistory·naver) → 글을 GitHub 이슈 1개(초안 패키지)로 만들어 보여 주기만 한다(package_issued, 공개 없음).
  운영자가 이슈의 복사 상자로 직접 발행한다(pipeline/publishers/issue_package.py). Blogger 인증·시크릿 점검은 하지 않고(Gemini 키와
  GITHUB_TOKEN 뿐), BLOGGER_PUBLISH 는 쓰지 않는다. 같은 채널에 열린 초안 이슈가 3건 이상이면 새로 만들지 않는다(PACKAGE_BACKLOG).
  연습 실행은 이슈 본문을 만들어 실행 요약에만 보이고 GitHub API 를 부르지 않는다.

종료 코드
  0 정상 종료(일일 상한·정지·게이트 탈락·주제 없음 등 '건너뜀' 포함). 건너뛴 사유는
    '[SKIP] code=...' 한 줄과 실행 요약에 남는다(docs/ARCHITECTURE.md 4-1)
  1 인프라 실패(LLM 호출·주제 확장·게시 API·이력 파일·인증 만료·네트워크). Actions 실행이 실패로 표시되어 알림이 간다
  2 설정 오류(레지스트리·프롬프트·LLM 키·게시용 시크릿 누락·블로그 주소 불일치·권한 없음·BLOGGER_PUBLISH 값 오류·
    수동 주제가 금지 주제 낱말에 걸림. 초안 패키지: GITHUB_TOKEN·GITHUB_REPOSITORY 없음·이슈 권한 없음·본문이 이슈 한도를 넘음)

환경변수
  DRY_RUN=1          파일·게시 없이 전체 흐름만 확인(스텁 LLM). Blogger 에도 접속하지 않는다
  PIPELINE_PAUSE=1   킬 스위치. 아무 것도 하지 않고 종료(저장소 Variables 로 설정)
  BLOGGER_PUBLISH    글을 어디까지 보낼지. 비어 있거나 auto 면 레지스트리 mode 를 따른다.
                     off(0·false·no) = 저장소 파일에만 저장, Blogger 는 건드리지 않음
                     draft = Blogger 초안함에 업로드(게시용 시크릿 필요, 하나도 없으면 파일만 저장)
                     publish(on·1·true·yes) = 즉시 게시(게시용 시크릿 필요, 없으면 종료 2)
  BLOGGER_TOPIC      주제 지정(수동 실행용). 프로필의 금지 주제 낱말에 걸리면 Gemini 를 부르기 전에 종료 2(TOPIC_BLOCKED)
  TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID  둘 다 있으면 초안함 업로드·즉시 게시에 성공했을 때 이력·초안 파일·실행 요약을 쓴 뒤 맨 마지막에 휴대폰(텔레그램)으로
                     알린다(pipeline/notify.py). 없으면 아무 일도 하지 않고 출력도 그대로다. 알림이 실패해도 게시 결과·이력·요약·종료 코드는
                     바뀌지 않는다(연습 실행·실패에서는 보내지 않는다)
  BLOGGER_AUTH_CHECK 1 이면 --auth-check 와 같다(워크플로의 '인증 점검만 실행' 입력). 정지(mode off) 중에도, 연습 실행이 켜져 있어도
                     실제로 점검한다(쓰기가 없다). 종료 코드: 0 통과 / 1 인증 만료·네트워크·API 오류 / 2 시크릿 없음·권한·주소 불일치
  GITHUB_TOKEN·GITHUB_REPOSITORY  (초안 패키지 전용) 초안 이슈를 읽고 만드는 데 쓴다. 워크플로가 넘기고, 오류 문구에서 가린다
"""
import argparse
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline import gates, notify
from pipeline.auth_check import auth_check, exit_code_for, label_for, safe_code, sentence_for
from pipeline.console import md_cell, one_line, safe_output
from pipeline.llm import LLMError, call_log_of, make_gemini_llm, purpose
from pipeline.publishers import issue_package
from pipeline.publishers.base import PublishError, redact
from pipeline.registry import (PACKAGE_PLATFORMS, PLATFORMS, ROOT, RegistryError, get_blog, load_profile, load_registry,
                               merged_blog, missing_secret_roles, resolve_secrets, validate_registry)
from pipeline.state import KST, StateError, entry_titles, other_blog_titles, read_json_list, write_json_atomic
from pipeline.stubs import stub_llm
from pipeline.topics import clean_topic, pick_topic

EXIT_OK, EXIT_INFRA, EXIT_CONFIG = 0, 1, 2
HISTORY_KEEP = 200
DRAFTS_KEEP = 120
TITLE_SHOWN = 120      # 로그·요약에 보여 줄 글 제목의 최대 길이(제목은 LLM 유래)
REASONS_SHOWN = 600    # 로그·요약에 보여 줄 게이트 탈락 사유 전체의 최대 길이
# 하루 상한에 세는 상태. draft_uploaded(Blogger 초안함에 올림)도 한 건이다. rejected·llm_failed 등 글이 안 나온 실행은 세지 않는다.
# publish_failed 는 글 ID(post_id)가 남은 것만 센다(_counts_toward_cap): 올리다 실패했어도 글이 이미 만들어졌을 수 있다
# package_issued(초안 패키지 이슈를 만듦, 티스토리·네이버)도 한 건이다: 이슈를 닫기 전까지 운영자의 손을 기다리는 초안이다.
COUNTED_STATUSES = {"posted", "draft", "draft_uploaded", "generated_unpublished", "package_issued"}
_TRUE = {"1", "true", "yes", "on"}
# BLOGGER_PUBLISH·--publish 값 → 정책. on=즉시 게시, draft=Blogger 초안함 업로드, off=저장소 파일에만 저장, auto=레지스트리 mode 를 따름
_POLICY_VALUES = {"": "auto", "auto": "auto", "draft": "draft",
                  "on": "on", "1": "on", "true": "on", "yes": "on", "publish": "on",
                  "off": "off", "0": "off", "false": "off", "no": "off"}
# 게시용 시크릿 역할(LLM 키 제외): 블로그 ID·OAuth 클라이언트 ID·시크릿·refresh token
PUBLISH_ROLES = tuple(role for role in PLATFORMS["blogger"]["required_secrets"] if role != "llm_api_key")


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="python -m pipeline.run")
    p.add_argument("--blog", required=True, help="pipeline/blogs.json 의 key")
    p.add_argument("--root", default=None, help="저장소 루트(기본: 이 패키지의 상위)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--publish", choices=["auto", "draft", "publish", "on", "off"], default=None)
    p.add_argument("--topic", default=None)
    p.add_argument("--auth-check", action="store_true",
                   help="글을 만들지 않고 Blogger 인증만 점검한다(토큰 갱신·블로그 조회·주소 일치, 쓰기 없음, Gemini 호출 0회)")
    return p.parse_args(argv)


def _flag(environ, name):
    return str(environ.get(name, "")).strip().lower() in _TRUE


def publish_policy(cli_value, environ):
    """글을 어디까지 보낼지: 'on'(즉시 게시) · 'draft'(Blogger 초안함 업로드) · 'off'(저장소 파일만) · 'auto'(레지스트리 mode 를 따름).
    알 수 없는 값은 None 이다(호출자가 설정 오류로 멈춘다. 오타를 auto 로 읽으면 mode auto 에서 뜻하지 않게 게시될 수 있다)."""
    raw = (cli_value or environ.get("BLOGGER_PUBLISH") or "").strip().lower()
    return _POLICY_VALUES.get(raw)


def decide_delivery(policy, mode):
    """정책과 레지스트리 mode 로 정해지는 전달 방식: 'publish'(즉시 게시) · 'draft'(Blogger 초안함에 업로드) · 'package'(초안 이슈, 티스토리·네이버) ·
    'file'(저장소 파일에만). mode off 는 이 함수에 오기 전에 멈춘다(오면 'file'). 초안 패키지 채널은 정책이 auto 일 때만 이 함수에 온다(run() 이 막는다)."""
    if policy == "on":
        return "publish"
    if policy == "draft":
        return "draft"
    if policy == "off":
        return "file"
    return {"auto": "publish", "draft": "draft", "package": "package"}.get(mode, "file")


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


def summary_head(blog):
    """실행 요약의 첫 줄 `### [채널 라벨] 블로그 이름`(예: `### [Blogger] Blogger (macat0722)`). 요약을 열자마자 어느 채널·블로그의 실행인지 보인다.
    채널 라벨과 이름은 레지스트리(저장소 파일)에서 오지만 한 줄·마크다운 안전을 보장하려고 md_cell 을 거친다. 채널 라벨을 읽을 수 없으면 이름만,
    이름도 없으면 블로그 key 를 쓴다. 이 줄만 바뀌었다 — 요약의 나머지 줄은 예전과 같다(동작 불변을 바이트 비교로 확인했다)."""
    channel = blog.get("channel")
    label = md_cell(channel.get("label"), 30) if isinstance(channel, dict) else ""
    name = md_cell(blog.get("name"), 60)
    if label and name:
        return f"### [{label}] {name}"
    return f"### {name or md_cell(blog.get('key'), 60)}"


def skip_line(code, **fields):
    """건너뜀·실패를 로그에서 한 줄로 찾게 하는 규격: [SKIP] code=CODE key=value ... (docs/ARCHITECTURE.md 4-1)."""
    return " ".join([f"[SKIP] code={code}"] + [f"{key}={value}" for key, value in fields.items()])


def _summarize(environ, blog, code, text, ai_lines=()):
    """실행 요약 한 블록. 정상 건너뜀·경고·실패 모두 같은 모양으로 남긴다(성공 경로는 아래에서 따로 쓴다).
    ai_lines: 이번 실행의 Gemini 호출 기록 줄(무료 한도를 나눠 쓰므로 실패·예외로 끝난 실행에서도 남긴다)."""
    _write_summary(environ, f"{summary_head(blog)}\n- 결과: **{code}** — {text}" + "".join(f"\n- {line}" for line in ai_lines))


def _alert_result(environ, out, blog, status, title, url):
    """게시·초안함 업로드 성공을 텔레그램으로 알린다(보조 알림, pipeline/notify.py). 시크릿 TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID 가 없으면 아무것도 하지 않고
    출력도 만들지 않는다(기존 동작과 바이트 단위로 같다). 알림이 실패하거나 예외가 나도 게시 결과·이력·요약·종료 코드는 바뀌지 않는다 —
    로그에 한 줄과 고정 문장 ::warning:: 만 더한다(토큰·채팅 ID 는 어디에도 쓰지 않는다)."""
    try:
        notifier = notify.Notifier(environ)
        if not notifier.enabled:
            return
        result = notifier.notify_blogger_result(status, title, url=url, blog_label=blog["channel"]["label"], extra_prefixes=(blog["url"],))
        notify.log_result(result, out)
    except Exception as exc:  # noqa: BLE001 - 알림은 보조다: 어떤 예외도 글 게시 결과를 바꾸지 못한다(클래스 이름만 남긴다. 예외 문구에 요청 주소가 있을 수 있다)
        out(f"[참고] 텔레그램 알림 중 예기치 않은 오류({type(exc).__name__}) — 게시 결과에는 영향이 없습니다")


def _checked_result(result, as_draft=False):
    """게시 결과의 글 ID·주소를 검사한다. 비어 있으면 PublishError(bad_response) — 어댑터가 이미 검사하지만, 다른 어댑터나
    가짜 어댑터가 빈 값을 돌려줘도 '게시 성공'으로 기록하지 않는다. 초안함 업로드(as_draft)는 글 ID 만 있으면 올라간 것이고
    주소는 빈칸일 수 있다(어댑터와 같은 기준 — 초안 응답에 url 이 오는지는 실제 호출로 확인해야 한다). 즉시 게시는 주소가 필수다."""
    post_id = str(getattr(result, "post_id", "") or "").strip()
    url = str(getattr(result, "url", "") or "").strip()
    if not post_id or (not url and not as_draft):
        raise PublishError("게시 결과에 글 ID" + ("" if as_draft else " 또는 주소(url)") + "가 없습니다"
                           "(Blogger 화면에서 글이 만들어졌는지 확인하세요)", code="bad_response", post_id=post_id)
    return post_id, url


def _secret_values(blog, environ):
    """오류 문구에서 글자 그대로 가릴 값들: 시크릿 값 전부와 클라이언트 ID 앞 12자리. 앞 12자리는 구글 클라우드 프로젝트 번호로,
    'Blogger API has not been used in project <번호>' 같은 403 문구에 실려 나오므로 값 자체가 아니어도 함께 가린다(공개 저장소 로그에
    남지 않게). 일반 실행과 단독 인증 점검(--auth-check)이 같은 목록을 쓴다."""
    resolved = resolve_secrets(blog, environ)
    values = [value for value in resolved.values() if value]
    project_number = str(resolved.get("client_id") or "").split("-")[0]
    if project_number:
        values.append(project_number)
    return values


def _counts_toward_cap(entry):
    """하루 상한에 세는 이력 항목인가: COUNTED_STATUSES, 그리고 글 ID 가 남은 publish_failed.
    올리다 실패했어도 글 ID 가 남았다면 초안·글이 이미 Blogger 에 만들어졌을 수 있다. 세지 않으면 같은 날 재실행(정기 실행 포함)이
    같은 주제로 초안을 또 만들어 초안함에 쌓인다. 글 ID 가 없는 실패(인증·네트워크 등)는 아무것도 안 만들었으니 세지 않는다."""
    status = entry.get("status")
    if status in COUNTED_STATUSES:
        return True
    return status == "publish_failed" and bool(str(entry.get("post_id") or "").strip())


def _auth_check_failed(out, environ, blog, record, code, detail):
    """인증 점검 실패를 한곳에서 알린다: [SKIP] 줄·원인 한 줄·고정 문장 ::error::·이력(publish_failed)·실행 요약. 종료 코드를 돌려준다.
    code 는 어댑터가 낸 분류이고(auth_check.FAILURES 에 없으면 api_error 로 접는다), detail 은 이미 비밀을 가린 원인 문구다."""
    code = safe_code(code)
    exit_code = exit_code_for(code)
    out(skip_line("AUTH_CHECK_FAILED", blog=blog["key"], reason=code, exit=exit_code))
    out(f"[{'설정' if exit_code == EXIT_CONFIG else '인프라'} 오류] 인증 점검 실패({code}): {one_line(detail)}")
    out(f"::error::[{blog['key']}] {sentence_for(code)}")
    if record is not None:  # 단독 점검(--auth-check)은 쓰기가 없으므로 이력을 남기지 않는다
        record({"status": "publish_failed", "topic": "", "reasons": [f"[{code}] {one_line(detail, 300)}"]})
    _summarize(environ, blog, "AUTH_CHECK_FAILED", f"{label_for(code)}({code}) — {sentence_for(code)}")
    return exit_code


def run_auth_check_only(out, environ, blog, publisher_factory, secret_values, dry):
    """--auth-check: 글을 만들지 않고 인증만 점검한다(토큰 갱신 → blogs.get → 블로그 주소 일치). 쓰기·Gemini 호출·이력·초안이 없다.

    종료 코드: 0 통과 / 1 인프라(인증 만료·네트워크·API 오류) / 2 설정(시크릿 없음·권한·주소 불일치).
    정지(mode off) 중에도 점검한다(시크릿을 등록한 직후 mode 를 켜기 전에 확인해야 하므로). 연습 실행(DRY_RUN)이 켜져 있어도
    쓰기가 없는 점검은 실제로 수행한다(점검 자체가 목적이다)."""
    missing = [role for role in missing_secret_roles(blog, environ) if role != "llm_api_key"]
    if missing:
        names = ", ".join(blog["secrets"].get(role, role) for role in missing)
        if len(missing) == len(PUBLISH_ROLES):
            message = (f"인증 점검을 할 수 없습니다: 게시용 시크릿이 하나도 등록되어 있지 않습니다({names}). "
                       "저장소 Settings > Secrets and variables > Actions 에 등록한 뒤 다시 실행하세요(.github/editorial/BLOGGER_API_SETUP.md).")
            code_text = "시크릿 없음"
        else:
            message = (f"인증 점검을 할 수 없습니다: 게시용 시크릿이 일부만 등록되어 있습니다(없는 것: {names}). "
                       f"{len(PUBLISH_ROLES)}종을 모두 등록하세요(저장소 Settings > Secrets and variables > Actions).")
            code_text = "시크릿 일부 없음"
        out(skip_line("SECRETS_MISSING", blog=blog["key"], missing=names.replace(" ", ""), check="auth"))
        out(f"::error::[{blog['key']}] {message}")
        _summarize(environ, blog, "SECRETS_MISSING", f"**{code_text}** — {message}")
        return EXIT_CONFIG
    if dry:
        out(f"[{blog['key']}] 연습 실행(DRY_RUN)이 켜져 있지만 인증 점검은 쓰기가 없어 실제로 점검합니다.")
    if blog["mode"] == "off":
        out(f"[{blog['key']}] mode=off(정지 중)이지만 인증 점검은 쓰기가 없어 실행합니다.")
    try:
        publisher = (publisher_factory or default_publisher_factory)(blog, environ)
        auth_check(publisher, blog["url"])
    except PublishError as exc:
        return _auth_check_failed(out, environ, blog, None, exc.code, redact(exc, secret_values))
    except Exception as exc:  # noqa: BLE001 - 어댑터 밖의 예외(설치 누락 등)도 기록하고 멈춘다
        return _auth_check_failed(out, environ, blog, None, "unexpected", f"{type(exc).__name__}: {redact(exc, secret_values)}")
    out(f"[{blog['key']}] 인증 점검 통과: 토큰 갱신·블로그 조회·블로그 주소 일치(쓰기 없음).")
    out(f"::notice::[{blog['key']}] 인증 점검 통과 — 토큰 갱신·블로그 조회·블로그 주소 일치를 확인했습니다(쓰기 없음, 글은 만들지 않았습니다).")
    names = ", ".join(blog["secrets"].get(role, role) for role in PUBLISH_ROLES)
    _write_summary(environ, f"{summary_head(blog)}\n"
                            "- 결과: **AUTH_CHECK_OK** — 토큰 갱신·블로그 조회·블로그 주소 일치를 확인했습니다(쓰기 없음, 글은 만들지 않았습니다).\n"
                            f"- 확인한 시크릿(이름만, 값은 출력하지 않음): {names}\n"
                            f"- 레지스트리 mode: {blog['mode']}(점검은 mode와 무관하게 실행됩니다)")
    return EXIT_OK


def default_publisher_factory(blog, environ):
    secrets = resolve_secrets(blog, environ)
    if blog["platform"] == "blogger":
        from pipeline.publishers.blogger import BloggerPublisher
        return BloggerPublisher(secrets["blog_id"], secrets["client_id"],
                                secrets["client_secret"], secrets["refresh_token"])
    if blog["platform"] in PACKAGE_PLATFORMS:   # 초안 패키지: GitHub 이슈. 계정 정보 없이 워크플로가 넘기는 토큰으로만 쓴다
        return issue_package.IssuePackagePublisher(environ.get("GITHUB_REPOSITORY"), environ.get("GITHUB_TOKEN"))
    raise RegistryError(f"이 러너가 지원하지 않는 platform: {blog['platform']}")


# ----------------------------------------------------------------------------
# 초안 패키지(mode package, platform tistory·naver) 경로. Blogger 경로는 건드리지 않고, run() 이 delivery == "package" 일 때만 여기로 온다.
# 글을 GitHub 이슈 1개로 만들어 보여 주기만 하고(공개 없음), 운영자가 복사해 직접 발행한다. 설명: docs/ARCHITECTURE.md §4-1·§7-B
# ----------------------------------------------------------------------------
# 실패 분류(PublishError.code) → 이름·::error:: 고정 문장. 문장에는 외부·AI 유래 문자열을 넣지 않는다. 종료 코드는 설정(2)과 인프라(1)로 가른다:
# 권한이 없거나(auth_failed) 글이 이슈 한도를 넘는(too_long) 것은 사람이 설정을 고쳐야 풀리고, 나머지는 시간이 지나거나 다시 실행하면 풀릴 수 있다.
PACKAGE_FAILURES = {
    "auth_failed": ("권한·접근 불가", "GitHub 이슈를 읽거나 쓸 권한이 없습니다. 워크플로 permissions 에 issues: write 가 있는지, 저장소 Settings > Actions > General 의 "
                                      "Workflow permissions 와 Issues 기능이 막혀 있지 않은지 확인하세요."),
    "too_long": ("본문이 너무 김", "초안이 이슈 본문 한도(약 6만 자)에 들어가지 않아 만들지 않았습니다. 프로필의 length.max_chars 를 줄이세요."),
    "invalid_draft": ("초안이 비었음", "AI 가 만든 제목이나 본문이 정화한 뒤 비어(스크립트·태그뿐인 출력 등) 이슈를 만들 수 없습니다. GitHub 는 부르지 않았고 이슈도 만들어지지 "
                                       "않았습니다. 다음 실행이 새 글을 만듭니다."),
    "network": ("네트워크 오류", "GitHub 서버에 연결하지 못했습니다(연결 실패·시간 초과). 잠시 뒤 다시 실행하세요."),
    "bad_response": ("응답 이상", "GitHub 가 필요한 값이 빠진 응답을 돌려줬습니다. 이 단계의 로그를 확인하고 이슈 목록에서 초안이 만들어졌는지 보세요."),
    "api_error": ("API 오류", "GitHub API 가 오류를 돌려줬습니다(호출 한도·서버 오류 포함). 이 단계의 로그를 확인하고 잠시 뒤 다시 실행하세요."),
    "unexpected": ("예기치 않은 오류", "초안 이슈를 만드는 중 예기치 않은 오류가 났습니다. 이 단계의 로그를 확인하세요."),
}
PACKAGE_CONFIG_CODES = frozenset({"auth_failed", "too_long", "invalid_draft"})
PACKAGE_BUILD_CODES = frozenset({"too_long", "invalid_draft"})        # 본문을 만드는 단계의 입력 문제(GitHub 를 부르기 전). 연습 실행과 같은 stage=build 로 알린다
PACKAGE_STAGES = {"precheck": "만들기 전 점검", "build": "본문 만들기", "issue": "만들기"}


def _package_code(code):
    return code if code in PACKAGE_FAILURES else "api_error"


def _package_exit(code):
    return EXIT_CONFIG if code in PACKAGE_CONFIG_CODES else EXIT_INFRA


def _summary_head(blog):
    return f"### {blog['key']}"


def _run_url(environ):
    """만든 Actions 실행의 주소(GITHUB_REPOSITORY·GITHUB_RUN_ID 가 모양에 맞을 때만). 어댑터가 한 번 더 모양을 확인한다."""
    repo, run_id = str(environ.get("GITHUB_REPOSITORY") or "").strip(), str(environ.get("GITHUB_RUN_ID") or "").strip()
    return f"https://github.com/{repo}/actions/runs/{run_id}" if re.fullmatch(r"[\w.\-]+/[\w.\-]+", repo) and run_id.isdigit() else ""


def _package_failed(out, environ, blog, stage, code, detail, ai_lines, summarize=True, maybe_created=True):
    """초안 패키지 실패를 한곳에서 알린다: [SKIP] 줄·원인 한 줄·고정 문장 ::error::·실행 요약. 종료 코드를 돌려준다. detail 은 이미 비밀을 가린 원인 문구다.
    이슈를 만들다 만들어졌는지 모호하게 실패한 경우(stage issue, maybe_created)는 이슈가 만들어졌을 수 있으니 재실행 전에 이슈 목록을 먼저 보게 한다
    (같은 날 다시 실행하면 같은 글이 둘이 될 수 있다). HTTP 4xx 로 거절된 실패(maybe_created 가 거짓)는 만들어지지 않았음이 확실해 그 안내를 붙이지 않는다.
    summarize 가 거짓이면 실행 요약은 부른 쪽이 마지막에 한 번만 쓴다(이슈 단계: 이력·사본 결과와 함께)."""
    code = _package_code(code)
    exit_code = _package_exit(code)
    name, sentence = PACKAGE_FAILURES[code]
    look_first = (" 초안 이슈가 만들어졌을 수 있으니 재실행 전에 라벨 `초안` 이슈 목록을 확인하세요."
                  if stage == "issue" and code not in PACKAGE_CONFIG_CODES and maybe_created else "")
    out(skip_line("PACKAGE_FAILED", blog=blog["key"], stage=stage, reason=code, exit=exit_code))
    out(f"[{'설정' if exit_code == EXIT_CONFIG else '인프라'} 오류] 초안 이슈 {PACKAGE_STAGES[stage]} 실패({code}): {one_line(detail)}")
    out(f"::error::[{blog['key']}] {sentence}{look_first}")
    if summarize:
        _summarize(environ, blog, "PACKAGE_FAILED", f"{name}({code}, {PACKAGE_STAGES[stage]}) — {sentence}{look_first}", ai_lines())
    return exit_code


def _package_precheck(out, environ, blog, publisher_factory, record, secret_values, ai_lines):
    """이슈를 만들기 전(Gemini 를 부르기 전)의 점검. 쓰기 없음. (게시자, 종료 코드)를 돌려주고, 종료 코드가 None 이면 계속한다.
    ① GITHUB_TOKEN·GITHUB_REPOSITORY 가 있는지(없으면 설정 오류) ② 같은 채널에 열린 초안 이슈 수를 읽어 OPEN_DRAFT_LIMIT 이상이면 건너뛴다(적체 방지).
    읽기에 실패하면 이슈를 만들 수 있는지 알 수 없으므로 멈춘다(fail closed)."""
    token = str(environ.get("GITHUB_TOKEN") or "").strip()
    repo = str(environ.get("GITHUB_REPOSITORY") or "").strip()
    missing = [name for name, value in (("GITHUB_TOKEN", token), ("GITHUB_REPOSITORY", repo)) if not value]
    if missing:
        names = ", ".join(missing)
        message = (f"초안 이슈를 만들 정보가 없습니다: {names}. 워크플로의 이 단계에 GITHUB_TOKEN 환경변수(secrets.GITHUB_TOKEN)를 넘기고 "
                   "permissions 에 issues: write 를 두어야 합니다(로컬 실행은 --dry-run 으로 본문만 봅니다).")
        out(skip_line("SECRETS_MISSING", blog=blog["key"], missing=names.replace(" ", "")))
        out(f"[설정 오류] {message}")
        out(f"::error::[{blog['key']}] {message}")
        _summarize(environ, blog, "SECRETS_MISSING", message)
        return None, EXIT_CONFIG
    channel = blog["channel"]["label"]
    try:
        publisher = (publisher_factory or default_publisher_factory)(blog, environ)
        open_drafts = publisher.count_open_drafts(channel)
    except PublishError as exc:
        detail = redact(exc, secret_values)
        record({"status": "publish_failed", "topic": "", "reasons": [f"[{_package_code(exc.code)}] {one_line(detail, 300)}"]})
        return None, _package_failed(out, environ, blog, "precheck", exc.code, detail, ai_lines)
    except Exception as exc:  # noqa: BLE001 - 어댑터 밖의 예외도 기록하고 멈춘다
        detail = f"{type(exc).__name__}: {redact(exc, secret_values)}"
        record({"status": "publish_failed", "topic": "", "reasons": [f"[unexpected] {one_line(detail, 300)}"]})
        return None, _package_failed(out, environ, blog, "precheck", "unexpected", detail, ai_lines)
    limit = issue_package.OPEN_DRAFT_LIMIT
    if open_drafts >= limit:
        out(skip_line("PACKAGE_BACKLOG", blog=blog["key"], open=open_drafts, limit=limit))
        out(f"::notice::[{blog['key']}] 같은 채널에 열린 초안 이슈가 {open_drafts}건(상한 {limit}건)이라 새 초안을 만들지 않고 건너뜁니다. "
            "쌓인 초안을 발행해 이슈를 닫거나, 쓰지 않을 초안에 라벨 `폐기`를 붙이면 다음 실행부터 다시 만들어집니다.")
        _summarize(environ, blog, "PACKAGE_BACKLOG",
                   f"같은 채널(라벨 `{issue_package.CHANNEL_LABEL_PREFIX}{channel}`)에 열린 `초안` 이슈가 {open_drafts}건(상한 {limit}건)이라 새로 만들지 않았습니다. "
                   "발행했으면 이슈를 닫고, 쓰지 않을 초안에는 라벨 `폐기`를 붙이거나 닫아 주세요(`폐기` 라벨이 붙은 것은 세지 않습니다).", ai_lines())
        return publisher, EXIT_OK
    out(f"[{blog['key']}] 초안 이슈 점검 통과: 열린 초안 {open_drafts}건(상한 {limit}건 미만).")
    return publisher, None


def _package_gate_info(profile, post, accepted, result, stats, attempts, model):
    """이슈 본문의 '게이트 점검 결과'에 쓸 요약. 숫자와 정화 통계, 게이트 참고 사항만 담는다(탈락 사유는 통과했으므로 없다)."""
    length, title = profile.get("length") or {}, profile.get("title") or {}
    return {"attempts": attempts, "model": model, "chars": gates.text_length(gates.plain_text(accepted["content"])),
            "min_chars": length.get("min_chars"), "max_chars": length.get("max_chars"),
            "title_chars": len(post["title"]), "title_min": title.get("min_chars"), "title_max": title.get("max_chars"),
            "warnings": list(result.warnings), "removed": {key: value for key, value in stats.items() if value}}


def _package_draft(environ, blog, today, post, profile, gate_info):
    return issue_package.PackageDraft(
        blog_key=blog["key"], platform=blog["platform"], channel_label=blog["channel"]["label"], date=today.isoformat(),
        title=post["title"], html=post["content_html"], tags=post["labels"], gate=gate_info,
        allow_links=bool(profile.get("allow_links")), run_url=_run_url(environ))


def _package_dry_run(out, environ, blog, draft, post, accepted, ai_lines):
    """연습 실행: 이슈 제목·라벨·본문을 만들어 실행 요약에만 보이고 GitHub 를 부르지 않는다(호출 0회). 본문이 이슈 한도에 안 들어가면
    실제 실행도 실패할 것이므로 연습도 같은 설정 오류로 끝낸다."""
    try:
        spec = issue_package.build_issue(draft)
    except PublishError as exc:
        return _package_failed(out, environ, blog, "build", exc.code, str(exc), ai_lines)
    out("[DRY_RUN] 게이트 통과 — 이슈·저장 없이 종료합니다(GitHub API 호출 0회).")
    out(f"  제목: {one_line(post['title'], TITLE_SHOWN)} / 라벨: {post['labels']} / 본문 {gates.text_length(gates.plain_text(accepted['content']))}자")
    out(f"  이슈 제목: {one_line(spec.title, 120)} / 이슈 라벨: {', '.join(spec.labels)} / 이슈 본문 {len(spec.body)}자(미리보기는 실행 요약에 있습니다)")
    _write_summary(environ, "\n".join([
        _summary_head(blog), f"- 결과: **DRY_RUN** — 게이트 통과, 이슈·저장 없이 종료(제목: {md_cell(post['title'], TITLE_SHOWN)})",
        "- GitHub API 호출: 0회(연습 실행은 이슈를 만들지 않고 적체도 점검하지 않습니다)",
        f"- 이슈 제목: {md_cell(spec.title, 120)}", f"- 이슈 라벨: {', '.join(f'`{label}`' for label in spec.labels)}",
        *[f"- {line}" for line in ai_lines()], "",
        "아래는 실제 실행에서 만들어질 이슈 본문의 미리보기입니다(맨 위 숨은 표지 `draft-id` 는 화면에 보이지 않습니다).", "", "---", "", spec.body, "---"]))
    return EXIT_OK


def _package_deliver(out, environ, blog, root, local_now, draft, post, topic, source, model, attempts, publisher, secret_values, record, ai_lines):
    """초안 이슈를 만들고(멱등) 이력·저장소 사본·실행 요약을 남긴다. 종료 코드를 돌려준다. Blogger 경로의 꼬리와 같은 순서다: 이력을 먼저 쓰고 사본은 나중에 쓴다."""
    status, url, post_id, exit_code, extra, fail_text = "package_issued", "", "", EXIT_OK, [], ""
    try:
        result = publisher.publish_package(draft)
        post_id, url = (str(getattr(result, "post_id", "") or "").strip(), str(getattr(result, "url", "") or "").strip())
        if not post_id or not url:
            raise PublishError("이슈 번호나 주소가 없습니다(GitHub 이슈 목록에서 초안이 만들어졌는지 확인하세요)", code="bad_response")
        post_id, url = redact(post_id, secret_values), redact(url, secret_values)
        out(f"  초안 이슈를 만들었습니다(공개되지 않음): {one_line(url)}")
    except PublishError as exc:
        code, detail = _package_code(exc.code), redact(exc, secret_values)
        status, post_id, url = "publish_failed", "", ""
        extra, fail_text = [f"[{code}] {detail[:300]}"], f"{code}: {detail}"
        # 입력 문제(비었음·너무 김)는 연습 실행과 같은 stage=build 로, 그 밖은 stage=issue. 어댑터가 '만들어졌을 수 있다'고 표시하지 않은 게시자는 있다고 본다
        exit_code = _package_failed(out, environ, blog, "build" if code in PACKAGE_BUILD_CODES else "issue", code, detail, ai_lines, summarize=False,
                                    maybe_created=bool(getattr(exc, "maybe_created", True)))
    except Exception as exc:  # noqa: BLE001 - 어댑터가 분류하지 못한 예외도 기록하고 초안 사본을 남긴다
        detail = f"{type(exc).__name__}: {redact(exc, secret_values)}"
        status, post_id, url = "publish_failed", "", ""
        extra, fail_text = [f"[unexpected] {detail[:300]}"], f"unexpected: {detail}"
        exit_code = _package_failed(out, environ, blog, "issue", "unexpected", detail, ai_lines, summarize=False)
    for note in getattr(publisher, "notes", None) or ():       # 어댑터가 모은 참고 사항(같은 표지의 이슈를 다시 쓴 일 등)
        out(f"[참고] {one_line(redact(str(note), secret_values))}")

    meta = {"topic": topic, "status": status, "generated_at": local_now.isoformat(), "url": url}
    history_ok, draft_path = True, None
    try:
        record({"status": status, "topic": topic, "topic_source": source, "title": post["title"], "labels": post["labels"], "url": url,
                "post_id": post_id, "model": model, "attempts": attempts, "reasons": extra})
    except OSError:
        history_ok, exit_code = False, EXIT_INFRA
        out(skip_line("HISTORY_WRITE_FAILED", blog=blog["key"], status=status))
        out(f"[인프라 오류] 이력 파일을 쓰지 못했습니다. 이번 결과: 상태 {status} · 이슈 번호 {one_line(post_id) or '(없음)'} · 주소 {one_line(url) or '(없음)'}")
        out(f"::error::[{blog['key']}] 이력 파일을 쓰지 못했습니다. 이미 초안 이슈가 만들어졌을 수 있으니 같은 날 다시 실행하기 전에 "
            "라벨 `초안` 이슈 목록을 확인하세요(이번 결과의 이슈 번호·주소는 이 단계의 로그에 있습니다).")
    try:
        draft_path = save_draft(root, blog, local_now, post, meta)
        out(f"  초안 저장: {draft_path.relative_to(root).as_posix()} / 상태: {status}")
    except OSError:
        out(f"::warning::[{blog['key']}] 저장소 초안 파일(감사용 사본)을 저장하지 못했습니다. 이 단계의 로그를 확인하세요.")
        out(f"[인프라 오류] 초안 파일 저장 실패(상태: {status})")
    service = issue_package.PACKAGE_INFO[blog["platform"]]["service"]
    lines = [_summary_head(blog), f"- 결과: **{status}** — {md_cell(post['title'], TITLE_SHOWN)}", f"- 초안 이슈: {md_cell(url, 300) or '(없음)'}"]
    if status == "package_issued":
        lines.append(f"- 안내: 공개된 글이 아닙니다. 이슈의 복사 상자로 {service}에 직접 발행하고 이슈를 닫으세요(읽는 법: docs/ACTIONS_GUIDE.md 3-19).")
    if status == "publish_failed":
        lines.append(f"- 사유: {md_cell(fail_text, REASONS_SHOWN)}")
        lines.append("- 안내: 이슈를 만들지 못했습니다. 만든 글은 저장소 초안 파일에 남았습니다." if draft_path is not None else "- 안내: 이슈를 만들지 못했습니다.")
    lines += [f"- 참고: {md_cell(redact(str(note), secret_values), 200)}" for note in getattr(publisher, "notes", None) or ()]
    if not history_ok:
        lines.append("- 이력 기록 실패: 이력 파일을 쓰지 못했습니다. 이미 초안 이슈가 만들어졌을 수 있으니 같은 날 다시 실행하기 전에 라벨 `초안` 이슈 목록을 확인하세요.")
    if draft_path is None:
        lines.append("- 초안 파일 저장 실패: 저장소 초안 파일(감사용 사본)을 저장하지 못했습니다.")
    lines += [f"- {line}" for line in ai_lines()]
    _write_summary(environ, "\n".join(lines))
    return exit_code


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
        if blog["platform"] != "blogger" and blog["platform"] not in PACKAGE_PLATFORMS:
            out(f"[설정 오류] 이 러너는 platform=blogger·tistory·naver 만 지원합니다 ({blog['platform']}). "
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
    auth_only = args.auth_check or _flag(environ, "BLOGGER_AUTH_CHECK")  # 워크플로는 입력을 환경변수로만 넘긴다
    if blog["mode"] == "off" and not auth_only:
        out(skip_line("MODE_OFF", blog=blog["key"]))
        out(f"[{blog['key']}] mode=off — 실행하지 않습니다.")
        out(f"::notice::[{blog['key']}] 레지스트리(pipeline/blogs.json)에서 mode=off 로 정지된 블로그라 이번 실행을 건너뜁니다. "
            "다시 켜려면 mode 를 draft 또는 auto 로 바꾸세요.")
        _summarize(environ, blog, "MODE_OFF", "레지스트리(pipeline/blogs.json)에서 mode=off 로 정지된 블로그입니다.")
        return EXIT_OK

    is_package = blog["platform"] in PACKAGE_PLATFORMS   # 초안 패키지 채널(티스토리·네이버): Blogger 의 인증·게시 방식이 없다
    if auth_only and is_package:
        # 점검할 계정 인증이 없다. 조용히 글을 만들면 읽기만 하려던 요청이 이슈를 만들어 버리므로 멈춘다
        message = ("인증 점검(--auth-check·BLOGGER_AUTH_CHECK)은 Blogger 블로그 전용입니다. 티스토리·네이버 초안 패키지 채널은 "
                   "계정 정보를 쓰지 않아 점검할 인증이 없습니다(GitHub 이슈 권한은 실행할 때 확인합니다).")
        out(skip_line("AUTH_CHECK_UNSUPPORTED", blog=blog["key"], platform=blog["platform"]))
        out(f"[설정 오류] {message}")
        out(f"::error::[{blog['key']}] {message}")
        _summarize(environ, blog, "AUTH_CHECK_UNSUPPORTED", message)
        return EXIT_CONFIG

    if auth_only:  # 인증만 점검한다: 글 생성·게시 입력(BLOGGER_PUBLISH·topic)은 읽지 않고, 이력·초안·Gemini 도 건드리지 않는다
        return run_auth_check_only(out, environ, blog, publisher_factory, _secret_values(blog, environ), dry)

    policy = publish_policy(args.publish, environ)
    if policy is None:
        message = ("BLOGGER_PUBLISH 값을 알 수 없습니다. off(저장소 파일만)·draft(Blogger 초안함 업로드)·"
                   "publish(즉시 게시)·auto 중 하나이거나 비워 두세요.")
        out(skip_line("INVALID_PUBLISH", blog=blog["key"]))
        out(f"[설정 오류] {message}")
        out(f"::error::[{blog['key']}] {message}")
        _summarize(environ, blog, "INVALID_PUBLISH", message)
        return EXIT_CONFIG
    if is_package and policy != "auto":
        # 초안 패키지 채널에는 즉시 게시·Blogger 초안함·저장소 파일만 저장이 없다(글은 항상 초안 이슈로 간다). 값을 무시하면 조용히 다른 일이 일어난다
        message = ("이 채널(초안 패키지)에서는 BLOGGER_PUBLISH·--publish 를 쓰지 않습니다. 글은 항상 GitHub 이슈(초안)로만 만들어지고 공개되지 않습니다. "
                   "값을 비우거나 auto 로 두세요.")
        out(skip_line("INVALID_PUBLISH", blog=blog["key"]))
        out(f"[설정 오류] {message}")
        out(f"::error::[{blog['key']}] {message}")
        _summarize(environ, blog, "INVALID_PUBLISH", message)
        return EXIT_CONFIG
    delivery = decide_delivery(policy, blog["mode"])
    secret_values = _secret_values(blog, environ)  # 오류 문구에서 실제 값을 가린다
    if is_package:
        secret_values = secret_values + [str(environ.get("GITHUB_TOKEN") or "").strip()]   # 이슈 API 오류 문구에 실릴 수 있는 토큰도 가린다

    # 즉시 게시, 또는 시크릿이 일부만 있는 초안함 업로드인데 게시용 시크릿이 없으면 글을 만들기 전에 멈춘다. 예전에는
    # 초안만 저장하고 초록으로 끝나 게시가 한 번도 안 된 채 며칠이 지나도 눈에 띄지 않았다(D-25). 시크릿은 '이름'만 표시한다.
    # 초안함 업로드(mode draft)인데 게시용 시크릿이 하나도 없으면 오류가 아니라 '시크릿 등록 전'의 정상 상태다:
    # 저장소 파일에만 저장하고 그 사실을 로그·요약에 남긴다. 일부만 있는 것은 등록하다 만 실수일 가능성이 커서 멈춘다.
    missing = [role for role in missing_secret_roles(blog, environ) if role != "llm_api_key"]
    names = ", ".join(blog["secrets"].get(role, role) for role in missing)
    upload_skipped = ""
    secrets_incomplete = bool(missing) and (delivery == "publish" or (delivery == "draft" and len(missing) < len(PUBLISH_ROLES)))
    if secrets_incomplete:
        if delivery == "publish":
            message = (f"게시용 시크릿이 등록되어 있지 않습니다: {names} "
                       "(저장소 Settings > Secrets and variables > Actions). "
                       "등록하기 전에는 이 블로그를 mode=draft(저장소 파일에만 저장) 또는 off 로 두세요.")
        else:
            message = (f"게시용 시크릿이 일부만 등록되어 있습니다(없는 것: {names}). Blogger 초안함에 올리려면 "
                       f"{len(PUBLISH_ROLES)}종을 모두 등록하고, 올리지 않으려면 모두 지우세요(저장소 Settings > Secrets and variables > Actions).")
        if not dry:
            out(skip_line("SECRETS_MISSING", blog=blog["key"], missing=names.replace(" ", "")))
            out(f"::error::[{blog['key']}] {message}")
            _summarize(environ, blog, "SECRETS_MISSING", message)
            return EXIT_CONFIG
        out(f"::warning::[{blog['key']}] (DRY_RUN이라 계속합니다) {message}")

    # ---- 수동 주제 -------------------------------------------------------
    # 운영자가 직접 입력한 주제(--topic·BLOGGER_TOPIC)도 시드·LLM 확장 주제와 같은 금지 주제 목록을 통과해야 한다(주제 가드레일 (a), D-64 ⑥ c).
    # 예전에는 이 경로만 검사가 없어 제목·본문 가드레일이 뒤늦게 막았고, 그 사이 Gemini 호출과 하루 상한을 쓸 수 있었다.
    # 입력을 고쳐 다시 실행하면 되는 설정 오류라 INVALID_PUBLISH 처럼 종료 2(빨강)로 끝내고, 조용한 초록으로 넘기지 않도록 걸린 낱말을 로그·요약에 남긴다.
    # 상태 파일(이력)을 읽기 전, Gemini 를 부르기 전에 멈춘다. 일시정지·mode off·잘못된 BLOGGER_PUBLISH·시크릿 누락 오류가 먼저 처리되는 순서는 그대로고,
    # 시크릿이 하나도 없는 초안함 업로드의 안내(UPLOAD_SKIPPED, '저장소 파일에만 저장합니다')만 이 검사 뒤에 둔다 — 아무것도 저장하지 않고 멈추는 실행에
    # '저장합니다'가 먼저 찍히면 안내가 모순이다(D-64 ⑦ N-7).
    override = clean_topic(args.topic or environ.get("BLOGGER_TOPIC", ""))
    if override and not gates.topic_allowed(override, profile):
        _, matched = gates.first_match(profile.get("banned_topic_patterns"), override)
        word = one_line(matched, 40)
        out(skip_line("TOPIC_BLOCKED", blog=blog["key"], word=word.replace(" ", "_")))
        out(f"[설정 오류] 입력한 주제가 금지 주제 낱말('{word}')에 걸려 Gemini 를 부르지 않고 멈춥니다. "
            "질병·치료·약·보충제·진단·임신·영유아·체중 감량·다이어트·간 건강 같은 건강 주장 주제는 쓰지 않습니다. 주제를 바꿔 다시 실행하세요.")
        out(f"::error::[{blog['key']}] 입력한 주제(topic)가 금지 주제 낱말에 걸려 멈췄습니다. 걸린 낱말은 실행 요약에 있습니다. 주제를 바꿔 다시 실행하세요.")
        _summarize(environ, blog, "TOPIC_BLOCKED",
                   f"입력한 주제가 금지 주제 낱말('{md_cell(matched, 40)}')에 걸려 Gemini 호출 없이 멈췄습니다. 주제를 바꿔 다시 실행하세요.")
        return EXIT_CONFIG

    if missing and delivery == "draft" and not secrets_incomplete:
        upload_skipped, delivery = names, "file"
        out(skip_line("UPLOAD_SKIPPED", blog=blog["key"], reason="NO_SECRETS", missing=names.replace(" ", "")))
        out(f"::notice::[{blog['key']}] Blogger 초안함에는 올리지 않고 저장소 파일에만 저장합니다(게시용 시크릿이 없음). "
            "시크릿을 등록하면 다음 실행부터 초안함에 올라갑니다(.github/editorial/BLOGGER_API_SETUP.md).")

    # ---- 상태·상한 --------------------------------------------------------
    history_path = root / blog["state"]["history"]
    try:
        history = read_json_list(history_path)
    except StateError as exc:
        out(f"[인프라 오류] {exc}")
        return EXIT_INFRA

    local_now = now.astimezone(KST)
    today = local_now.date()
    produced_today = [e for e in history if isinstance(e, dict)
                      and e.get("date") == today.isoformat() and _counts_toward_cap(e)]
    cap = blog["limits"]["max_posts_per_day"]
    if len(produced_today) >= cap and not override:
        counted = ", ".join(sorted({str(e.get("status")) for e in produced_today}))
        failed_but_made = any(e.get("status") == "publish_failed" for e in produced_today)
        why = (" publish_failed 는 글 ID 가 남아 있어 센 것입니다(올리다 실패했지만 Blogger 에 글이 만들어졌을 수 있습니다). "
               "Blogger 초안함·글 목록에서 확인하세요." if failed_but_made else "")
        out(skip_line("DAILY_CAP", blog=blog["key"], date=today, cap=cap, today=len(produced_today)))
        out(f"::notice::[{blog['key']}] 오늘({today}) 상한 {cap}건에 도달해 건너뜁니다 "
            f"(오늘 기록: {counted}).{why} 수동 실행에서 topic 을 입력하면 상한을 건너뛰고 실행합니다.")
        _summarize(environ, blog, "DAILY_CAP",
                   f"오늘({today}) 상한 {cap}건에 도달해 건너뜀(오늘 기록: {counted}). 게시되지 않은 초안도 상한에 포함됩니다.{why}")
        return EXIT_OK

    # ---- LLM --------------------------------------------------------------
    stub_used = False
    if llm is None:
        if dry:
            llm, stub_used = stub_llm, True
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
    # 요청별 호출 기록(무료 한도 측정): 어느 블로그의 호출인지와 로그 출력처를 정한다. 주입된 가짜 llm 에는 기록 장치가 없다.
    call_log = call_log_of(llm)
    if call_log is not None:
        call_log.configure(label=blog["key"], out=out, purpose="generate")

    def ai_lines():
        """실행 요약에 붙일 Gemini 호출 줄. 실패·예외로 끝난 실행에서도 호출 수가 사라지지 않게 모든 종료 경로에서 쓴다."""
        if call_log is not None:
            return call_log.summary_lines()
        return ["Gemini 호출: 0회(가짜 AI 응답 사용)"] if stub_used else []

    base_entry = {"v": 1, "blog": blog["key"], "date": today.isoformat(), "generated_at": local_now.isoformat()}

    def record(entry):
        entry = {**base_entry, **entry}
        if not dry:
            history.append(entry)
            write_json_atomic(history_path, history, keep=HISTORY_KEEP)
        return entry

    # ---- 인증 점검(사전 점검) -----------------------------------------------
    # 업로드·게시를 하려면 글을 만들기 전에(Gemini 를 부르기 전에) 쓰기 없이 토큰 갱신·블로그 조회·주소 일치를 확인한다.
    # 인증이 깨진 날 무료 한도를 쓰지 않고, 엉뚱한 블로그(같은 계정의 다른 블로그 ID)에 쓰는 사고를 글 생성 전에 막는다.
    # 연습 실행은 Blogger 에 접속하지 않는다.
    publisher = None
    if delivery in ("publish", "draft") and not dry:
        try:
            publisher = (publisher_factory or default_publisher_factory)(blog, environ)
            auth_check(publisher, blog["url"])
        except PublishError as exc:
            return _auth_check_failed(out, environ, blog, record, exc.code, redact(exc, secret_values))
        except Exception as exc:  # noqa: BLE001 - 어댑터 밖의 예외(설치 누락 등)도 기록하고 멈춘다
            return _auth_check_failed(out, environ, blog, record, "unexpected",
                                      f"{type(exc).__name__}: {redact(exc, secret_values)}")
        out(f"[{blog['key']}] 인증 점검 통과: 토큰 갱신·블로그 조회·주소 일치(쓰기 없음).")

    # ---- 초안 패키지 사전 점검(Gemini 를 부르기 전, 쓰기 없음) -----------------------
    # GITHUB_TOKEN·저장소가 있는지, 같은 채널에 열린 초안 이슈가 상한(3건) 미만인지. 연습 실행은 GitHub 를 부르지 않으므로 건너뛴다.
    if delivery == "package" and not dry:
        publisher, early = _package_precheck(out, environ, blog, publisher_factory, record, secret_values, ai_lines)
        if early is not None:
            return early

    # ---- 주제 -------------------------------------------------------------
    recent_titles = entry_titles(history[-100:])
    other_titles = other_blog_titles(root, [merged_blog(reg, b) for b in reg["blogs"]], blog["key"])
    if override:
        topic, source = override, "override"
    else:
        with purpose(llm, "topic-expansion"):
            topic, source = pick_topic(profile, history, today, other_titles + recent_titles, rng, llm=llm)

    if not topic and source == "expand_failed":
        # 시드를 다 쓴 뒤 LLM에게 새 주제를 받는 호출이 실패했다. '주제 없음'(초록)으로 넘기면 LLM 키·할당량 문제가
        # 가려지므로 인프라 실패(종료 1)로 다룬다.
        message = "주제 확장 LLM 호출이 실패했습니다. LLM 키·할당량·모델 이름을 확인하세요."
        out(skip_line("EXPAND_FAILED", blog=blog["key"]))
        out(f"::error::[{blog['key']}] {message}")
        record({"status": "llm_failed", "topic": "", "reasons": ["[TOPIC] expand_failed"]})
        _summarize(environ, blog, "EXPAND_FAILED", message, ai_lines())
        return EXIT_INFRA
    if not topic:
        out(skip_line("NO_TOPIC", blog=blog["key"], source=source))
        out(f"::warning::[{blog['key']}] 고를 주제가 없습니다({source}). 시드 주제를 보강하세요. 건너뜁니다.")
        record({"status": "skipped_no_topic", "topic": "", "reasons": [f"[TOPIC] {source}"]})
        _summarize(environ, blog, "NO_TOPIC", f"고를 주제가 없습니다({source}).", ai_lines())
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
            out(f"[인프라 오류] LLM 호출 실패: {one_line(redact(exc, secret_values))}")
            out(f"::error::[{blog['key']}] LLM 호출이 실패했습니다. LLM 키·할당량·모델 이름을 확인하세요.")
            record({"status": "llm_failed", "topic": topic, "reasons": [f"[LLM] {redact(exc, secret_values)[:300]}"], "attempts": attempt})
            _summarize(environ, blog, "LLM_FAILED", "LLM 호출이 실패했습니다(원인은 이 단계의 로그를 보세요).", ai_lines())
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
        _summarize(environ, blog, "GATE_REJECTED", md_cell('; '.join(reasons), REASONS_SHOWN), ai_lines())
        return EXIT_OK

    final_html = gates.append_disclosure(accepted["content"], profile)
    post = {"title": accepted["title"], "labels": accepted["labels"], "content_html": final_html}

    # ---- 게시 / 초안 ------------------------------------------------------
    status, url, post_id, exit_code, extra, fail_text = "draft", "", "", EXIT_OK, [], ""
    if delivery == "package":
        # 초안 패키지: 게이트를 통과한 글을 이슈 1개로 만든다(연습 실행은 본문만 만들어 실행 요약에 보인다). 이력·사본·요약은 이 경로가 따로 쓴다.
        # 루프를 break 로 빠져나온 마지막 result·stats 가 통과한 시도의 것이다.
        draft = _package_draft(environ, blog, today, post, profile,
                               _package_gate_info(profile, post, accepted, result, stats, attempts, model))
        if dry:
            return _package_dry_run(out, environ, blog, draft, post, accepted, ai_lines)
        return _package_deliver(out, environ, blog, root, local_now, draft, post, topic, source, model, attempts,
                                publisher, secret_values, record, ai_lines)
    if dry:
        out("[DRY_RUN] 게이트 통과 — 게시·저장 없이 종료합니다.")
        out(f"  제목: {one_line(post['title'], TITLE_SHOWN)} / 라벨: {post['labels']} / 본문 {gates.text_length(gates.plain_text(accepted['content']))}자")
        _summarize(environ, blog, "DRY_RUN", f"게이트 통과, 게시·저장 없이 종료(제목: {md_cell(post['title'], TITLE_SHOWN)})",
                   ai_lines())
        return EXIT_OK
    if delivery in ("publish", "draft"):
        # 게시용 시크릿 누락과 인증은 위의 사전 점검에서 이미 걸러졌다(여기까지 오면 4종이 모두 있고 인증 점검을 통과했다).
        as_draft = delivery == "draft"
        noun = "Blogger 초안함 업로드" if as_draft else "게시"
        # 실패 주석은 고정 문장이다. 어느 단계에서 났든 글이 이미 만들어졌을 수 있어(응답만 실패한 경우 포함) 다시 실행하기 전에
        # Blogger 를 먼저 보게 한다 — 같은 날 정기 실행·수동 실행이 초안·글을 또 만들지 않도록(V-03).
        look_first = ("초안이 만들어졌을 수 있으니 재실행 전에 Blogger 초안함을 확인하세요." if as_draft
                      else "글이 올라갔을 수 있으니 재실행 전에 Blogger 글 목록을 확인하세요.")
        try:
            result = publisher.publish(post["title"], post["content_html"], post["labels"], draft=as_draft)
            post_id, url = _checked_result(result, as_draft)
            # 응답 속 글 ID·주소에 블로그 ID 같은 값이 섞여 올 수 있다(예: .../blog/post/edit/<블로그 ID>/<글 ID>): 이력·로그·요약에 쓰기 전에 가린다
            post_id, url = redact(post_id, secret_values), redact(url, secret_values)
            status = "draft_uploaded" if as_draft else "posted"
            if as_draft:
                out(f"  Blogger 초안함에 업로드했습니다(공개되지 않음): "
                    f"{one_line(url) if url else '주소 없음(응답에 url 이 없습니다 — Blogger 화면에서 확인하세요)'}")
            else:
                out(f"  게시 성공: {one_line(url)}")
        except PublishError as exc:
            code, detail = safe_code(exc.code), redact(exc, secret_values)
            status, exit_code = "publish_failed", EXIT_INFRA
            post_id = redact(str(getattr(exc, "post_id", "") or ""), secret_values)
            extra, fail_text = [f"[{code}] {detail[:300]}"], f"{code}: {detail}"
            out(skip_line("PUBLISH_FAILED", blog=blog["key"], reason=code, target=delivery))
            out(f"[인프라 오류] {noun} 실패({code}): {one_line(detail)}")
            out(f"::error::[{blog['key']}] {noun}에 실패했습니다({code}). 이 단계의 로그와 BLOGGER_API_SETUP.md 의 점검 항목을 확인하세요. {look_first}")
        except Exception as exc:  # noqa: BLE001 - 어댑터가 분류하지 못한 예외도 기록하고 초안 파일을 남긴다(예전에는 이력 없이 죽을 수 있었다)
            detail = f"{type(exc).__name__}: {redact(exc, secret_values)}"
            status, exit_code = "publish_failed", EXIT_INFRA
            extra, fail_text = [f"[unexpected] {detail[:300]}"], f"unexpected: {detail}"
            out(skip_line("PUBLISH_FAILED", blog=blog["key"], reason="unexpected", target=delivery))
            out(f"[인프라 오류] {noun} 중 예기치 않은 오류: {one_line(detail)}")
            out(f"::error::[{blog['key']}] {noun} 중 예기치 않은 오류가 났습니다. 이 단계의 로그를 확인하세요. 초안은 저장소 파일에 남겼습니다. {look_first}")
        # 어댑터가 모은 참고 사항(예: 중복 확인 실패)은 성공·실패와 상관없이 로그에 남긴다. 외부 문구라 한 줄로 접고 비밀을 가린다
        for note in getattr(publisher, "notes", None) or ():
            out(f"[참고] {one_line(redact(str(note), secret_values))}")
    else:
        out("  Blogger 에는 올리지 않고 저장소 파일에만 초안을 저장합니다.")

    meta = {"topic": topic, "status": status, "generated_at": local_now.isoformat(), "url": url}
    # 이력을 파일 저장보다 먼저 쓴다. 같은 글을 두 번 올리지 않게 막는 기준이 이력이라, 이미 Blogger 에 올라간 뒤에는 감사용 사본
    # 파일이 실패해도 이력은 남아야 한다. 어느 쪽 쓰기가 실패해도 예외로 죽지 않고(올라간 글의 주소·글 ID 를 잃지 않게) 고정 문장
    # 주석과 요약을 남긴 채 끝낸다. 이력 실패는 같은 글이 또 올라갈 수 있어 빨강(종료 1), 사본 실패는 글이 올라갔다면 노랑이다.
    history_ok, draft_path = True, None
    try:
        record({"status": status, "topic": topic, "topic_source": source, "title": post["title"],
                "labels": post["labels"], "url": url, "post_id": post_id, "model": model,
                "attempts": attempts, "reasons": extra})
    except OSError:
        history_ok, exit_code = False, EXIT_INFRA
        out(skip_line("HISTORY_WRITE_FAILED", blog=blog["key"], status=status))
        out(f"[인프라 오류] 이력 파일을 쓰지 못했습니다. 이번 결과: 상태 {status} · 글 ID {one_line(post_id) or '(없음)'} · "
            f"주소 {one_line(url) or '(없음)'}")
        out(f"::error::[{blog['key']}] 이력 파일을 쓰지 못했습니다. 이미 Blogger 에 올라갔을 수 있으니 같은 날 다시 실행하기 전에 "
            "Blogger 초안함·글 목록을 확인하세요(이번 결과의 글 ID·주소는 이 단계의 로그에 있습니다).")
    try:
        draft_path = save_draft(root, blog, local_now, post, meta)
        out(f"  초안 저장: {draft_path.relative_to(root).as_posix()} / 상태: {status}")
    except OSError:
        if delivery in ("publish", "draft"):
            out(f"::warning::[{blog['key']}] 저장소 초안 파일(감사용 사본)을 저장하지 못했습니다. 이 단계의 로그를 확인하세요.")
        else:  # 저장소 파일이 유일한 결과물인데 못 썼다: 글이 남지 않았으니 성공으로 끝내지 않는다
            exit_code = EXIT_INFRA
            out(f"::error::[{blog['key']}] 저장소 초안 파일을 저장하지 못했습니다. Blogger 에는 올리지 않는 실행이라 글이 남지 않았습니다. "
                "이 단계의 로그를 확인하고 다시 실행하세요.")
        out(f"[인프라 오류] 초안 파일 저장 실패(상태: {status})")
    lines = [summary_head(blog), f"- 결과: **{status}** — {md_cell(post['title'], TITLE_SHOWN)}",
             f"- URL: {md_cell(url, 300) or '(없음)'}"]
    if status == "draft_uploaded":
        lines.append("- 안내: Blogger 초안함에 올렸습니다. 아직 공개되지 않았으니 Blogger 화면에서 확인한 뒤 직접 게시하세요.")
        if not url:
            lines.append("- 안내: 응답에 글 주소(url)가 없어 주소는 비워 두었습니다. Blogger 화면의 초안함에서 이 글(제목 위)을 찾아 확인하세요.")
    if status == "publish_failed":
        lines.append(f"- 사유: {md_cell(fail_text, REASONS_SHOWN)}")
        if post_id:
            lines.append(f"- 글 ID: {md_cell(post_id, 120)} — 글이 이미 만들어졌을 수 있으니 재실행 전에 Blogger 에서 확인하세요.")
    if not history_ok:
        lines.append("- 이력 기록 실패: 이력 파일을 쓰지 못했습니다. 이미 올라간 글이 있을 수 있으니 같은 날 다시 실행하기 전에 "
                     "Blogger 초안함·글 목록을 확인하세요.")
    if draft_path is None:
        lines.append("- 초안 파일 저장 실패: 저장소 초안 파일(감사용 사본)을 저장하지 못했습니다.")
    if upload_skipped:
        lines.append("- Blogger 초안함에는 올리지 않음(게시용 시크릿 없음): 저장소 파일에만 저장했습니다. "
                     f"등록할 시크릿: {upload_skipped}")
    lines += [f"- {line}" for line in ai_lines()]  # Gemini 호출 기록(무료 한도 측정)
    _write_summary(environ, "\n".join(lines))
    # 휴대폰(텔레그램) 알림은 맨 마지막에 보낸다: 이력·초안 파일·실행 요약을 모두 쓴 뒤라서, 알림이 오래 걸리거나 그 사이 프로세스가 끊겨도
    # 이미 올라간 글·초안의 기록이 남는다(같은 날 재실행이 하루 상한·중복 방지를 볼 수 있다). 알림의 어떤 실패도 위의 결과·종료 코드를 바꾸지 않는다.
    if status in ("draft_uploaded", "posted"):
        _alert_result(environ, out, blog, status, post["title"], url)
    return exit_code


def main(argv=None):
    safe_output()
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
