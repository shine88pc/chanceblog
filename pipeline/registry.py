"""블로그 레지스트리 로드·검증.

`pipeline/blogs.json`이 풀오토 파이프라인이 다루는 블로그의 단일 설정 원천이다.
블로그를 추가할 때는 코드를 고치지 않고 항목을 추가한다.
시크릿 '값'은 여기에 두지 않는다. 항목에는 환경변수(= GitHub Secrets) '이름'만 둔다.

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

MODES = ("off", "draft", "auto")

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
}

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_CRON_RE = re.compile(r"^\S+(\s+\S+){4}$")

_PROFILE_REQUIRED = (
    "name", "language", "length", "title", "structure", "labels", "similarity",
    "banned_patterns", "title_banned_patterns", "leak_patterns", "banned_topic_patterns",
    "disclosure_html", "seed_topics", "topic_cooldown_days",
)
# 정규식 목록 필드. body_* 는 선택 항목이다(없으면 본문 주제 가드레일을 쓰지 않는다 — pipeline/gates.py body_risk_hit).
_PATTERN_FIELDS = ("banned_patterns", "title_banned_patterns", "leak_patterns", "banned_topic_patterns",
                   "body_banned_patterns", "body_safe_patterns")
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

    shared = set(reg.get("shared_secrets", []))
    for name in shared:
        if not isinstance(name, str) or not _ENV_RE.match(name):
            errors.append(f"shared_secrets 항목이 올바른 이름이 아닙니다: {name!r}")
    seen_keys = set()
    secret_owner = {}

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

        profile_name = blog.get("profile")
        if platform == "blogger" and not profile_name:
            errors.append(f"{label}: platform blogger 는 profile 이 필요합니다.")
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

        if not isinstance(blog.get("ad_surface"), bool):
            errors.append(f"{label}: ad_surface는 true/false여야 합니다.")
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
