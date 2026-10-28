"""레지스트리에서 GitHub Actions 매트릭스를 만든다(티스토리·네이버는 블로그를 추가하면 워크플로 수정 없이 잡이 늘고, Blogger 는 블로그마다 채널 래퍼 워크플로 하나를 더해야 한다).

  python -m pipeline.plan --platform blogger           # {"include":[...]} 한 줄 JSON
  python -m pipeline.plan --platform blogger --count   # 대상 블로그 수
  python -m pipeline.plan --platform blogger --include-off   # 정지(mode off)한 블로그도 대상에 넣는다

--include-off 는 '인증 점검만' 하는 수동 실행 전용이다. 인증 점검은 쓰기가 없고, 시크릿을 등록한 직후 mode 를 켜기 *전에*
(정지 중에) 확인해야 하므로 정지한 블로그도 점검할 수 있어야 한다. 글을 만드는 실행에는 쓰지 않는다(러너는 mode off 를 다시 막는다).

레지스트리 검증에 실패하면 종료 코드 1(워크플로가 잘못된 설정으로 돌지 않게 한다).
--only 도 두 단계로 검사해 틀리면 종료 코드 1이다: 레지스트리에 없는 key(오타)도, 레지스트리에는 있지만
--platform 과 다른 플랫폼 블로그의 key 도 오류다. 둘 다 대상 0개(= generate 잡이 통째로 건너뛰어진 초록)가 되기 때문이다.
그래서 대상 0개는 대상(--only 로 지정한 블로그, 아니면 이 플랫폼 블로그 전체)이 모두 mode=off 로 정지됐거나
이 플랫폼 블로그가 없을 때만 생기고, 이것은 오류가 아니다(워크플로가 알림을 남긴다).
매트릭스에는 시크릿 '이름'만 들어간다. 값은 티스토리·네이버 워크플로가 secrets[...] 로 직접 읽는다. Blogger 는 채널별 래퍼(blogger-en.yml·blogger-ko.yml)가
그 이름을 역할 이름(PIPELINE_SECRET_<역할>)으로 명시해 넘기고, 검증기(scripts/validate_repo.py REG-6)가 래퍼가 넘기는 이름이 레지스트리와 같은지 본다.
"""
import argparse
import json
import sys

from pipeline.console import safe_output
from pipeline.registry import ROOT, RegistryError, enabled_blogs, load_registry, merged_blog, validate_registry

_SECRET_ROLES = ("llm_api_key", "blog_id", "client_id", "client_secret", "refresh_token")


def build_matrix(reg, platform=None, only=None, include_off=False):
    include = []
    if include_off:
        candidates = [merged_blog(reg, raw) for raw in reg.get("blogs", []) if isinstance(raw, dict)]
        candidates = [blog for blog in candidates if not platform or blog.get("platform") == platform]
    else:
        candidates = enabled_blogs(reg, platform)
    for blog in candidates:
        if only and blog["key"] != only:
            continue
        secrets = blog.get("secrets", {})
        item = {
            "key": blog["key"],
            "platform": blog["platform"],
            "mode": blog["mode"],
            "history": blog["state"]["history"],
            "content_dir": blog["state"]["content_dir"],
        }
        for role in _SECRET_ROLES:
            item[f"secret_{role}"] = secrets.get(role, "")
        include.append(item)
    return {"include": include}


def main(argv=None):
    safe_output()
    parser = argparse.ArgumentParser(prog="python -m pipeline.plan")
    parser.add_argument("--platform", default=None)
    parser.add_argument("--only", default=None, help="이 key 의 블로그만 (수동 실행용)")
    parser.add_argument("--count", action="store_true")
    parser.add_argument("--include-off", action="store_true",
                        help="정지(mode off)한 블로그도 대상에 넣는다(인증 점검만 하는 수동 실행 전용)")
    args = parser.parse_args(argv)
    try:
        reg = load_registry()
    except RegistryError as exc:
        print(f"[오류] {exc}", file=sys.stderr)
        return 1
    errors = validate_registry(reg, ROOT)
    if errors:
        print("[오류] 레지스트리 검증 실패:\n  - " + "\n  - ".join(errors), file=sys.stderr)
        return 1
    blogs = [merged_blog(reg, raw) for raw in reg["blogs"]]
    keys = [b["key"] for b in blogs]
    if args.only:
        # 1단계: 레지스트리에 없는 key. 오타 하나로 대상이 0개가 되어 generate 잡이 통째로 건너뛰어지면(초록) 아무도 모른다
        if args.only not in keys:
            print(f"[오류] --only {args.only!r} 는 레지스트리에 없는 key 입니다. 유효한 key: {', '.join(keys)}",
                  file=sys.stderr)
            return 1
        # 2단계: 레지스트리에는 있지만 이 플랫폼 블로그가 아닌 key(예: blogger 워크플로에 chance). 이것도 대상 0개(초록)가 된다
        owner = next(b for b in blogs if b["key"] == args.only)
        if args.platform and owner["platform"] != args.platform:
            same_platform = [b["key"] for b in blogs if b["platform"] == args.platform]
            print(f"[오류] --only {args.only!r} 는 {args.platform} 가 아니라 {owner['platform']} 플랫폼 블로그입니다. "
                  f"{args.platform} 플랫폼의 key: {', '.join(same_platform) or '(없음)'}", file=sys.stderr)
            return 1
    matrix = build_matrix(reg, args.platform, args.only, include_off=args.include_off)
    print(len(matrix["include"]) if args.count else json.dumps(matrix, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
