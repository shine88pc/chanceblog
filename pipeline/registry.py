"""블로그 레지스트리 로드·검증.

`pipeline/blogs.json`이 풀오토 파이프라인이 다루는 블로그의 단일 설정 원천이다.
블로그를 추가할 때는 코드를 고치지 않고 항목을 추가한다.
시크릿 '값'은 여기에 두지 않는다. 항목에는 환경변수(= GitHub Secrets) '이름'만 둔다.

블로그마다 `channel`(채널 라벨 — 그 블로그 워크플로 name 맨 앞의 `[라벨] `과 같은 글자)과 `ads`(광고 선언: off·pending_gate·on)를
적는다. 둘 다 이 파일이 검증한다(규칙: docs/ARCHITECTURE.md §3). 이 모듈은 표준 라이브러리만 쓴다 — blogger.yml 의 plan 잡이
pip install 없이 `python -m pipeline.plan` 으로 이 검증을 실행하기 때문이다(워크플로 name 은 YAML 을 해석하지 않고 줄을 본다).

초안 패키지 채널(platform tistory·naver, mode package): 공식 자동 게시 수단이 없어 글을 GitHub 이슈로 보여 주기만 한다. 이 채널은
시크릿 역할이 LLM 키뿐이고(구조적 보장) 계정 정보 낱말이 든 시크릿 이름은 보조로 막는다(PACKAGE_PLATFORMS·_package_errors, docs/SECURITY_GUARDRAILS.md G-S7).

CLI: python -m pipeline.registry   (검증 후 요약 출력, 오류가 있으면 종료 코드 1)
"""
import copy
import json
import re
import sys
from pathlib import Path, PurePosixPath

from pipeline.console import safe_output
from pipeline.gates import SUPPORTED_LANGUAGES, first_match

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = Path(__file__).resolve().parent / "blogs.json"
PROFILE_DIR = Path(__file__).resolve().parent / "profiles"

# 모드. off 정지 · draft 초안(Blogger: 초안함 업로드, 시크릿이 없으면 저장소 파일만) · package 초안 패키지(티스토리·네이버: 글을 만들어
# GitHub 이슈 1개로 보여 주기만 한다 — 공개 없음, 운영자가 복사해 직접 발행) · auto 자동 게시. 앞의 셋(off·draft·package)은 공개되지 않는 쪽이다.
MODES = ("off", "draft", "package", "auto")

# 광고 선언(D6, 2026-10-27 운영자 승인). 레지스트리가 아는 것은 '의도'뿐이다 — 광고는 각 플랫폼 화면에서 운영자가 켠다.
#   off          광고가 없다. 새 채널의 시작값이다(defaults.ads).
#   pending_gate 품질 게이트를 통과하면 켜려는 곳. 아직 광고 코드는 없다.
#   on           광고 코드가 사이트에 들어 있다(AdSense 승인 대기 중이어도 on). 우리가 코드를 관리하는 jekyll-git 에서만 쓴다.
# pending_gate/on 으로 올리는 편집은 T3(사용자 승인)다. 설명: docs/ARCHITECTURE.md §3 '광고 선언', docs/SECURITY_GUARDRAILS.md G-C10
ADS_STATES = ("off", "pending_gate", "on")

# 채널 라벨 = 그 블로그 워크플로 `name:` 맨 앞의 `[라벨] `(운영자가 Actions 목록에서 채널별로 묶어 본다). 블로그에 속하지 않는
# 워크플로의 구분(`공통`·`내부`)은 레지스트리 밖이라 여기에 없다(scripts/validate_repo.py WF-12 가 합쳐서 쓴다).
CHANNEL_LABELS = ("Chance", "Blogger", "Blogger 영문", "Blogger 한글", "티스토리", "네이버")

# 플랫폼별 필수 시크릿 역할. 새 플랫폼을 지원하려면 여기와 publishers/ 어댑터를 함께 추가한다.
PLATFORMS = {
    "jekyll-git": {
        "required_secrets": ["llm_api_key"],
        "optional_secrets": ["unsplash_key"],
    },
    "blogger": {
        "required_secrets": ["llm_api_key", "blog_id", "client_id", "client_secret", "refresh_token"],
        "optional_secrets": [],
    },
    # 초안 패키지 채널(아래 PACKAGE_PLATFORMS): 시크릿은 LLM 키뿐이다. 다른 역할과 계정 정보 모양의 이름은 검증이 막는다.
    "tistory": {"required_secrets": ["llm_api_key"], "optional_secrets": []},
    "naver": {"required_secrets": ["llm_api_key"], "optional_secrets": []},
}

# 초안 패키지 채널: 공식 자동 게시 수단이 없어(티스토리 오픈 API는 2024-02 종료, 네이버 글쓰기 API는 2020 종료) 글을 만들어 GitHub 이슈
# 1개(= 초안 1건)로 보여 주기만 하고, 운영자가 복사해 직접 발행한다(pipeline/publishers/issue_package.py). 로그인·세션·쿠키 자동화는 만들지 않고
# 계정 정보는 저장·처리하지 않는다 — 구조적 보장은 '이 채널의 시크릿 역할이 llm_api_key 뿐'이라는 것이다(_package_errors ③: 이름이 무엇이든 그 값은
# Gemini 키로만 쓰인다). 시크릿 이름의 금지 낱말 검사(아래)는 실수를 막는 보조일 뿐이라 우회 철자(PASS_WORD·TISTORY_PW 등)는 막지 못한다.
# platform → 그 채널의 라벨(channel.label). 초안 이슈의 라벨(`채널:<라벨>`)과 현황판이 이 라벨을 쓰므로 짝이 어긋나면 안 된다.
PACKAGE_PLATFORMS = {"tistory": "티스토리", "naver": "네이버"}
PACKAGE_MODES = ("off", "package")       # 이 채널에서 쓸 수 있는 mode(draft·auto 는 올릴 곳이 없다)
# 시크릿 이름에 이 낱말이 들면 막는다(실수 방지용 보조 — 포함 검사라 우회 철자는 통과한다. 구조적 보장은 역할 제한이다). 대문자 환경변수 이름 기준이다.
ACCOUNT_SECRET_WORDS = ("PASSWORD", "PASSWD", "PWD", "COOKIE", "SESSION", "LOGIN", "CREDENTIAL")

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_CRON_RE = re.compile(r"^\S+(\s+\S+){4}$")

_PROFILE_REQUIRED = (
    "name", "language", "length", "title", "structure", "labels", "similarity",
    "banned_patterns", "title_banned_patterns", "leak_patterns", "banned_topic_patterns",
    "disclosure_html", "seed_topics", "topic_cooldown_days",
)
# 정규식 목록 필드. body_* 는 선택 항목이다(없으면 본문 주제 가드레일을 쓰지 않는다 — pipeline/gates.py body_risk_hit).
# body_clause_split_patterns(절 경계)·body_safe_veto_patterns(면제를 취소하는 표현)는 빈 문자열에 맞으면 안 된다: 경계가 빈 문자열에 맞으면
# 절 나누기가 의미를 잃고, 면제 취소가 빈 문자열에 맞으면 모든 절의 면제가 취소돼 상담 안내 문장이 전부 탈락한다.
_PATTERN_FIELDS = ("banned_patterns", "title_banned_patterns", "leak_patterns", "banned_topic_patterns",
                   "body_banned_patterns", "body_safe_patterns", "body_clause_split_patterns", "body_safe_veto_patterns")
_RATIO_FIELDS = ("min_hangul_ratio", "min_latin_ratio")


class RegistryError(ValueError):
    """레지스트리·프로필을 읽을 수 없거나 형식이 잘못됐을 때."""


def deep_merge(base, override):
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_registry(path=None):
    path = Path(path) if path else REGISTRY_PATH
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"레지스트리를 읽을 수 없습니다 ({path}): {exc}") from exc


def merged_blog(reg, raw_blog):
    return deep_merge(reg.get("defaults", {}), raw_blog)


def get_blog(reg, key):
    for raw in reg.get("blogs", []):
        if isinstance(raw, dict) and raw.get("key") == key:
            return merged_blog(reg, raw)
    raise RegistryError(f"레지스트리에 없는 블로그 키: {key}")


def enabled_blogs(reg, platform=None):
    """mode가 off가 아닌 블로그 목록(기본값 병합본)."""
    out = []
    for raw in reg.get("blogs", []):
        blog = merged_blog(reg, raw)
        if blog.get("mode") == "off":
            continue
        if platform and blog.get("platform") != platform:
            continue
        out.append(blog)
    return out


def resolve_secrets(blog, environ):
    """역할 -> 값(앞뒤 공백 제거). 없으면 빈 문자열.

    우선순위: PIPELINE_SECRET_<ROLE> (워크플로 매트릭스가 블로그별 Secrets 를 역할 이름으로 넘길 때)
    > 레지스트리에 적힌 환경변수 이름 (로컬 수동 실행·단일 블로그).
    """
    out = {}
    for role, name in blog.get("secrets", {}).items():
        override = (environ.get("PIPELINE_SECRET_" + role.upper()) or "").strip()
        out[role] = override or (environ.get(name) or "").strip()
    return out


def missing_secret_roles(blog, environ):
    """플랫폼 필수 시크릿 중 값이 비어 있는 역할 목록."""
    spec = PLATFORMS.get(blog.get("platform"), {})
    values = resolve_secrets(blog, environ)
    return [role for role in spec.get("required_secrets", []) if not values.get(role)]


def _safe_rel(path_str):
    if not isinstance(path_str, str) or not path_str.strip():
        return False
    if re.match(r"^[A-Za-z]:", path_str):
        return False
    p = PurePosixPath(path_str.replace("\\", "/"))
    return not p.is_absolute() and ".." not in p.parts


_NAME_LABEL_RE = re.compile(r"^\[([^\[\]]+)\] (?=\S)")


def name_label(name):
    """워크플로 `name`·`run-name` 맨 앞의 `[구분] `에서 구분(라벨)을 꺼낸다. 문자열이 아니거나 그 모양이 아니면 None.
    `[라벨]` 바로 뒤에 공백 하나와 이름이 이어져야 한다(`[Chance]글`·`[Chance] ` 는 접두사가 아니다)."""
    match = _NAME_LABEL_RE.match(name) if isinstance(name, str) else None
    return match.group(1) if match else None


_TOP_NAME_LINE_RE = re.compile(r"^name[ \t]*:[ \t]*(.*)$")


def _workflow_name_problem(text, label):
    """워크플로 본문의 최상위 `name:` 줄(들여쓰기 없는 첫 줄)이 `"[라벨] 이름"`(따옴표로 감싼 값)이 아니면 이유, 맞으면 None.
    YAML 을 해석하지 않고 줄을 본다(이 모듈은 표준 라이브러리만 쓴다). 대괄호로 시작하는 값은 YAML 에서 따옴표가 없으면 배열로 읽혀
    문법 오류이므로 따옴표가 필수다."""
    prefix = re.escape(f"[{label}] ")
    for line in re.split(r"\r\n|\r|\n", text.lstrip(chr(0xFEFF))):
        match = _TOP_NAME_LINE_RE.match(line)
        if not match:
            continue
        # 따옴표로 감싼 값이 `[라벨] ` 로 시작하고 바로 이어 이름이 있어야 한다(닫는 따옴표가 곧바로 오면 이름이 빈 것이다)
        if re.match(r"""(["'])""" + prefix + r"(?!\1)\S", match.group(1).strip()):
            return None
        return f"name 줄이 `{line.strip()[:60]}` 입니다"
    return "최상위 name: 줄을 찾지 못했습니다"


def _channel_errors(raw_channel, blog, label, root, seen_labels, seen_keys):
    """channel 규칙: ① 필수·모양 ② 라벨이 CHANNEL_LABELS 중 하나 ③ 블로그 사이에 라벨·key 중복 없음 ④ 그 블로그 워크플로 name 이
    `[라벨] ` 로 시작. defaults 에서 물려받지 않고 항목에 직접 적는다(채널은 블로그마다 달라야 하므로 물려받을 값이 없다)."""
    allowed = " · ".join(CHANNEL_LABELS)
    if not isinstance(raw_channel, dict):
        return [f"{label}: channel이 필요합니다 — {{\"key\": \"영문 식별자\", \"label\": \"허용 라벨\"}} 모양으로 이 항목에 직접 적으세요"
                f"(허용 라벨: {allowed})."]
    errors = []
    channel_key, channel_label = raw_channel.get("key"), raw_channel.get("label")
    if not isinstance(channel_key, str) or not _KEY_RE.match(channel_key):
        errors.append(f"{label}: channel.key는 영소문자로 시작하는 [a-z0-9_] 2~31자여야 합니다: {channel_key!r}")
    elif channel_key in seen_keys:
        errors.append(f"{label}: channel.key가 다른 블로그('{seen_keys[channel_key]}')와 같습니다: {channel_key!r}. 채널은 블로그마다 달라야 합니다.")
    else:
        seen_keys[channel_key] = blog.get("key")
    if channel_label not in CHANNEL_LABELS:
        errors.append(f"{label}: channel.label은 {allowed} 중 하나여야 합니다: {channel_label!r}")
        return errors
    if channel_label in seen_labels:
        errors.append(f"{label}: channel.label이 다른 블로그('{seen_labels[channel_label]}')와 같습니다: {channel_label!r}. "
                      "채널 라벨은 블로그마다 달라야 합니다(같으면 Actions 목록에서 채널이 구분되지 않습니다).")
    else:
        seen_labels[channel_label] = blog.get("key")
    workflow = blog.get("workflow")
    if _safe_rel(workflow) and (root / workflow).is_file():       # 경로가 없거나 안전하지 않으면 workflow 경로 오류가 이미 알린다
        try:
            text = (root / workflow).read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:                      # UnicodeDecodeError 는 ValueError 의 하위
            errors.append(f"{label}: 워크플로 {workflow}를 읽을 수 없어 name 접두사를 확인하지 못했습니다: {exc}")
        else:
            problem = _workflow_name_problem(text, channel_label)
            if problem:
                errors.append(f"{label}: 워크플로 {workflow}의 {problem}. name은 channel.label({channel_label!r})에 맞춰 "
                              f"\"[{channel_label}] 이름\" 으로 시작해야 합니다(대괄호로 시작하는 값은 YAML 에서 따옴표가 필요합니다).")
    return errors


def _ads_errors(blog, label):
    """ads 규칙(D6): ① 값은 ADS_STATES 중 하나 ② on 은 우리가 광고 코드를 관리하는 jekyll-git 에서만 ③ ad_surface=true 도 jekyll-git 에서만.
    생략하면 defaults.ads(off)를 물려받는다."""
    errors = []
    ads, platform = blog.get("ads"), blog.get("platform")
    if ads not in ADS_STATES:
        errors.append(f"{label}: ads는 {' · '.join(ADS_STATES)} 중 하나여야 합니다: {ads!r}")
    elif ads == "on" and platform != "jekyll-git":
        errors.append(f"{label}: platform {platform!r} 블로그는 ads를 on으로 둘 수 없습니다 — on은 광고 코드를 이 저장소가 관리하는 "
                      "platform jekyll-git 에서만 씁니다. 다른 플랫폼은 품질 게이트를 통과한 뒤 운영자가 플랫폼 화면에서 켜므로 "
                      "그 전에는 off 또는 pending_gate 입니다.")
    if blog.get("ad_surface") is True and platform != "jekyll-git":
        errors.append(f"{label}: ad_surface=true는 platform jekyll-git 블로그에만 쓸 수 있습니다(지금 platform: {platform!r}). "
                      "광고 표면 파일은 이 저장소가 사이트를 가진 jekyll-git 에만 있습니다.")
    return errors


def _package_errors(raw, blog, label, secrets):
    """초안 패키지 채널(platform tistory·naver)의 규칙. 공식 자동 게시 수단이 없어 글을 이슈로 보여 주기만 하고, 계정 정보는 저장·처리하지 않는다
    (docs/SECURITY_GUARDRAILS.md G-S7). ① mode 는 off·package 만 ② channel.label 은 그 채널의 라벨(티스토리·네이버) ③ secrets 는 llm_api_key 만
    ④ 시크릿 이름에 PASSWORD·COOKIE·SESSION·LOGIN 같은 계정 정보 낱말이 없어야 한다. '계정 정보를 다루지 않는다'는 원칙의 구조적 보장은 ③(역할 제한)이고,
    ④(이름 검사)는 실수를 막는 보조다(포함 검사라 PASS_WORD·TISTORY_PW 같은 우회 철자는 통과한다)."""
    errors = []
    platform, mode = blog.get("platform"), blog.get("mode")
    if mode in MODES and mode not in PACKAGE_MODES:
        errors.append(f"{label}: platform {platform} 블로그의 mode는 {' · '.join(PACKAGE_MODES)} 중 하나여야 합니다(지금 {mode!r}) — "
                      "공식 자동 게시 수단이 없어 글을 이슈로 보여 주는 package 외에는 올릴 곳이 없습니다.")
    channel = raw.get("channel")
    wanted = PACKAGE_PLATFORMS[platform]
    if isinstance(channel, dict) and channel.get("label") in CHANNEL_LABELS and channel["label"] != wanted:
        # 초안 이슈 라벨(`채널:<라벨>`)과 현황판이 channel.label 을 쓴다. 짝이 어긋나면 초안이 엉뚱한 채널로 갈린다
        errors.append(f"{label}: platform {platform} 블로그의 channel.label은 {wanted!r} 이어야 합니다(지금 {channel['label']!r}) — "
                      "초안 이슈의 라벨 `채널:<라벨>`이 이 값으로 만들어집니다.")
    spec = PLATFORMS[platform]
    allowed = list(spec["required_secrets"]) + list(spec.get("optional_secrets", []))
    for role, env_name in secrets.items():
        if role not in allowed:
            errors.append(f"{label}: platform {platform} 의 secrets 에는 {' · '.join(allowed)} 만 둘 수 있습니다(허용되지 않는 역할: {role}) — "
                          "이 채널은 계정 정보(블로그 ID·클라이언트·refresh token·로그인·세션)를 저장하거나 처리하지 않습니다. "
                          "글은 GitHub 이슈로 보여 주고 운영자가 직접 발행합니다.")
        shown = env_name.upper() if isinstance(env_name, str) else ""
        found = next((word for word in ACCOUNT_SECRET_WORDS if word in shown), None)
        if found:
            errors.append(f"{label}: secrets.{role}의 이름 {env_name}에 계정 정보를 뜻하는 낱말({found})이 있습니다 — "
                          "이 채널은 비밀번호·쿠키·세션·로그인 정보를 저장하거나 처리하지 않습니다.")
    return errors


def validate_profile(profile):
    """프로필 오류 목록. 정규식은 실제로 컴파일해 본다."""
    errors = []
    if not isinstance(profile, dict):
        return ["프로필은 객체여야 합니다."]
    for field in _PROFILE_REQUIRED:
        if field not in profile:
            errors.append(f"프로필 필수 항목 누락: {field}")
    if "language" in profile and profile["language"] not in SUPPORTED_LANGUAGES:
        # 모르는 언어는 글 언어 검사(gates.check_post)가 조용히 꺼진다
        errors.append(f"프로필 language는 {'·'.join(SUPPORTED_LANGUAGES)} 중 하나여야 합니다: {profile['language']!r}")
    for field in _RATIO_FIELDS:
        if field in profile:
            value = profile[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
                errors.append(f"프로필 {field}는 0~1 사이 숫자여야 합니다.")
    patterns_ok = True
    for field in _PATTERN_FIELDS:
        patterns = profile.get(field, []) or []
        if not isinstance(patterns, list):
            errors.append(f"프로필 {field}는 정규식 문자열의 배열이어야 합니다.")
            patterns_ok = False
            continue
        for pattern in patterns:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except (re.error, TypeError) as exc:
                errors.append(f"프로필 {field}의 정규식 오류 {pattern!r}: {exc}")
                patterns_ok = False
                continue
            if compiled.search(""):
                # 한 줄 끝에 '|' 를 남긴 것 같은 실수. 금지 목록이면 모든 글이 탈락하고, body_safe_patterns 면 모든 문장을 건너뛰어
                # 본문 가드레일이 조용히 꺼진다
                errors.append(f"프로필 {field}의 정규식 {pattern!r}이 빈 문자열에도 맞습니다 — 모든 글(문장)에 걸립니다.")
                patterns_ok = False
    extra = profile.get("prompt_extra")
    if extra is not None and not (isinstance(extra, list) and all(isinstance(line, str) for line in extra)):
        errors.append("프로필 prompt_extra는 문자열 배열이어야 합니다.")
    expand = profile.get("topic_expand_prompt")
    if expand is not None and not (isinstance(expand, str) and "{n}" in expand and "{avoid}" in expand):
        errors.append("프로필 topic_expand_prompt는 {n}과 {avoid} 자리표시자를 가진 문자열이어야 합니다.")
    length = profile.get("length", {})
    if not (isinstance(length.get("min_chars"), int) and isinstance(length.get("max_chars"), int)
            and 0 < length["min_chars"] < length["max_chars"]):
        errors.append("프로필 length.min_chars < length.max_chars 인 양의 정수여야 합니다.")
    sim = profile.get("similarity", {})
    for name in ("same_blog", "other_blogs"):
        value = sim.get(name)
        if not isinstance(value, (int, float)) or not 0 < value <= 1:
            errors.append(f"프로필 similarity.{name}은 0~1 사이 숫자여야 합니다.")
    seeds = profile.get("seed_topics")
    if not isinstance(seeds, list) or not seeds or not all(isinstance(s, str) and s.strip() for s in seeds):
        errors.append("프로필 seed_topics는 비어 있지 않은 문자열 배열이어야 합니다.")
    elif patterns_ok:
        for seed in seeds:  # 시드도 주제 가드레일을 통과해야 한다(걸리는 시드는 조용히 한 번도 뽑히지 않는다)
            raw, word = first_match(profile.get("banned_topic_patterns"), seed)
            if raw is not None:
                errors.append(f"프로필 seed_topics의 {seed!r}가 banned_topic_patterns에 걸립니다('{word}').")
    if not isinstance(profile.get("topic_cooldown_days"), int) or profile["topic_cooldown_days"] < 0:
        errors.append("프로필 topic_cooldown_days는 0 이상 정수여야 합니다.")
    return errors


def load_profile(name, profile_dir=None):
    path = Path(profile_dir or PROFILE_DIR) / f"{name}.json"
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"프로필을 읽을 수 없습니다 ({path}): {exc}") from exc
    errors = validate_profile(profile)
    if errors:
        raise RegistryError(f"프로필 {name} 오류: " + "; ".join(errors))
    return profile


def validate_registry(reg, root=None):
    """레지스트리 오류 목록(비어 있으면 정상). 파일 존재 여부는 root 기준으로 확인한다."""
    root = Path(root) if root else ROOT
    errors = []
    if not isinstance(reg, dict):
        return ["레지스트리 최상위는 객체여야 합니다."]
    if reg.get("schema_version") != 1:
        errors.append("schema_version은 1이어야 합니다.")
    blogs = reg.get("blogs")
    if not isinstance(blogs, list) or not blogs:
        return errors + ["blogs는 비어 있지 않은 배열이어야 합니다."]

    defaults = reg.get("defaults")
    if not isinstance(defaults, dict) or defaults.get("ads") != "off":
        # ads 를 적지 않은 새 블로그가 광고를 켠(또는 켜려는) 상태로 시작하지 않게 한다. 바꾸는 것은 T3(정책)이다
        errors.append("defaults.ads는 off여야 합니다 — ads를 적지 않은 새 블로그는 광고 없이 시작해야 합니다"
                      "(품질 게이트를 통과하기 전에는 광고를 켜지 않는다, docs/SECURITY_GUARDRAILS.md G-C10).")

    shared = set(reg.get("shared_secrets", []))
    for name in shared:
        if not isinstance(name, str) or not _ENV_RE.match(name):
            errors.append(f"shared_secrets 항목이 올바른 이름이 아닙니다: {name!r}")
    seen_keys = set()
    secret_owner = {}
    seen_channel_labels, seen_channel_keys = {}, {}

    for index, raw in enumerate(blogs):
        if not isinstance(raw, dict):
            errors.append(f"blogs[{index}]는 객체여야 합니다.")
            continue
        blog = merged_blog(reg, raw)
        key = blog.get("key")
        label = f"블로그 '{key}'" if key else f"blogs[{index}]"

        if not isinstance(key, str) or not _KEY_RE.match(key):
            errors.append(f"{label}: key는 영소문자로 시작하는 [a-z0-9_] 2~31자여야 합니다.")
        elif key in seen_keys:
            errors.append(f"{label}: key가 중복됩니다.")
        else:
            seen_keys.add(key)

        if not isinstance(blog.get("name"), str) or not blog["name"].strip():
            errors.append(f"{label}: name이 필요합니다.")
        platform = blog.get("platform")
        if platform not in PLATFORMS:
            errors.append(f"{label}: 지원하지 않는 platform {platform!r} (지원: {', '.join(PLATFORMS)})")
        if not str(blog.get("url", "")).startswith("https://"):
            errors.append(f"{label}: url은 https:// 로 시작해야 합니다.")
        langs = blog.get("languages")
        if not isinstance(langs, list) or not langs or not all(isinstance(x, str) and x for x in langs):
            errors.append(f"{label}: languages는 문자열 배열이어야 합니다.")
        if blog.get("mode") not in MODES:
            errors.append(f"{label}: mode는 {MODES} 중 하나여야 합니다.")
        elif blog.get("mode") == "package" and platform not in PACKAGE_PLATFORMS:
            errors.append(f"{label}: mode package 는 platform {' · '.join(PACKAGE_PLATFORMS)} 에서만 쓸 수 있습니다(지금 platform: {platform!r}) — "
                          "package 는 공식 자동 게시 수단이 없는 채널의 초안을 GitHub 이슈로 보여 주는 모드입니다.")
        if "mode" not in raw:
            # defaults.mode 를 물려받는 블로그는 defaults 가 auto 일 때 시크릿만 등록하면 곧바로 자동 게시된다. 모드는 항목마다 직접 적게 한다
            errors.append(f"{label}: mode를 이 항목에 직접 적어야 합니다(defaults.mode 를 물려받으면 새 블로그가 의도하지 않은 모드로 "
                          "바로 동작할 수 있습니다. 새 블로그는 off 로 시작하세요).")

        for field in ("workflow", "entrypoint", "prompt"):
            value = blog.get(field)
            if not _safe_rel(value):
                errors.append(f"{label}: {field} 경로가 올바르지 않습니다: {value!r}")
            elif not (root / value).exists():
                errors.append(f"{label}: {field} 파일이 없습니다: {value}")
        errors.extend(_channel_errors(raw.get("channel"), blog, label, root, seen_channel_labels, seen_channel_keys))

        profile_name = blog.get("profile")
        if (platform == "blogger" or platform in PACKAGE_PLATFORMS) and not profile_name:
            errors.append(f"{label}: platform {platform} 는 profile 이 필요합니다.")
        if profile_name:
            profile_path = root / "pipeline" / "profiles" / f"{profile_name}.json"
            if not profile_path.exists():
                errors.append(f"{label}: 프로필 파일이 없습니다: pipeline/profiles/{profile_name}.json")
            else:
                loaded = None
                try:
                    loaded = json.loads(profile_path.read_text(encoding="utf-8"))
                    profile_errors = validate_profile(loaded)
                except (OSError, json.JSONDecodeError) as exc:
                    profile_errors = [f"읽을 수 없음: {exc}"]
                errors.extend(f"{label}: {e}" for e in profile_errors)
                if not profile_errors and isinstance(langs, list) and loaded["language"] not in langs:
                    # 영문 블로그에 한국어 프로필을 쓰는 것 같은 어긋남(D-32). 글 언어 검사는 프로필의 language 를 따른다
                    errors.append(f"{label}: 프로필 {profile_name}의 language({loaded['language']!r})가 이 블로그의 languages {langs} 에 없습니다.")

        state = blog.get("state") or {}
        for field in ("history", "content_dir"):
            if not _safe_rel(state.get(field)):
                errors.append(f"{label}: state.{field} 경로가 올바르지 않습니다: {state.get(field)!r}")

        cron = (blog.get("schedule") or {}).get("cron")
        if not isinstance(cron, str) or not _CRON_RE.match(cron.strip()):
            errors.append(f"{label}: schedule.cron은 5필드 cron 식이어야 합니다: {cron!r}")

        per_day = (blog.get("limits") or {}).get("max_posts_per_day")
        if not isinstance(per_day, int) or not 1 <= per_day <= 24:
            errors.append(f"{label}: limits.max_posts_per_day는 1~24 정수여야 합니다.")

        models = (blog.get("llm") or {}).get("models")
        if not isinstance(models, list) or not models or not all(isinstance(m, str) and m for m in models):
            errors.append(f"{label}: llm.models는 비어 있지 않은 문자열 배열이어야 합니다.")

        secrets = blog.get("secrets")
        if not isinstance(secrets, dict):
            errors.append(f"{label}: secrets는 {{역할: 환경변수 이름}} 객체여야 합니다.")
            secrets = {}
        spec = PLATFORMS.get(platform, {})
        for role in spec.get("required_secrets", []):
            if role not in secrets:
                errors.append(f"{label}: platform {platform}에 필요한 secrets 역할 누락: {role}")
        for role, env_name in secrets.items():
            if not isinstance(env_name, str) or not _ENV_RE.match(env_name):
                errors.append(f"{label}: secrets.{role}가 올바른 환경변수 이름이 아닙니다: {env_name!r}")
                continue
            owner = secret_owner.setdefault(env_name, key)
            if owner != key and env_name not in shared:
                errors.append(
                    f"{label}: 시크릿 이름 {env_name}을(를) 블로그 '{owner}'도 쓰고 있습니다. "
                    "블로그마다 고유 이름을 쓰거나 shared_secrets에 명시하세요.")
        if platform in PACKAGE_PLATFORMS:
            errors.extend(_package_errors(raw, blog, label, secrets))

        if not isinstance(blog.get("ad_surface"), bool):
            errors.append(f"{label}: ad_surface는 true/false여야 합니다.")
        errors.extend(_ads_errors(blog, label))
        protected = blog.get("protected_paths")
        if not isinstance(protected, list) or not all(_safe_rel(p) for p in protected):
            errors.append(f"{label}: protected_paths는 상대 경로 배열이어야 합니다.")
        elif blog.get("ad_surface") and not protected:
            errors.append(f"{label}: ad_surface=true 이면 protected_paths가 비어 있을 수 없습니다.")

        health = blog.get("health") or {}
        gap = health.get("max_gap_hours")
        if not isinstance(gap, (int, float)) or gap <= 0:
            errors.append(f"{label}: health.max_gap_hours는 양수여야 합니다.")
    return errors


def main(argv=None):
    safe_output()
    try:
        reg = load_registry()
    except RegistryError as exc:
        print(f"[오류] {exc}")
        return 1
    errors = validate_registry(reg)
    for blog in reg.get("blogs", []):
        merged = merged_blog(reg, blog)
        print(f"- {merged.get('key'):<14} {merged.get('platform'):<11} mode={merged.get('mode'):<5} "
              f"cron={merged.get('schedule', {}).get('cron')}  ({merged.get('name')})")
    if errors:
        print(f"\n레지스트리 오류 {len(errors)}건:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("\n레지스트리 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
