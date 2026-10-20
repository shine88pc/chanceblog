"""레지스트리에서 GitHub Actions 매트릭스를 만든다(블로그를 추가하면 워크플로 수정 없이 잡이 늘어난다).

  python -m pipeline.plan --platform blogger           # {"include":[...]} 한 줄 JSON
  python -m pipeline.plan --platform blogger --count   # 대상 블로그 수

레지스트리 검증에 실패하면 종료 코드 1(워크플로가 잘못된 설정으로 돌지 않게 한다).
매트릭스에는 시크릿 '이름'만 들어간다. 값은 워크플로가 secrets[...] 로 직접 읽는다.
"""
import argparse
import json
import sys

from pipeline.registry import ROOT, RegistryError, enabled_blogs, load_registry, validate_registry

_SECRET_ROLES = ("llm_api_key", "blog_id", "client_id", "client_secret", "refresh_token")


def build_matrix(reg, platform=None, only=None):
    include = []
    for blog in enabled_blogs(reg, platform):
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
    parser = argparse.ArgumentParser(prog="python -m pipeline.plan")
    parser.add_argument("--platform", default=None)
    parser.add_argument("--only", default=None, help="이 key 의 블로그만 (수동 실행용)")
    parser.add_argument("--count", action="store_true")
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
    matrix = build_matrix(reg, args.platform, args.only)
    print(len(matrix["include"]) if args.count else json.dumps(matrix, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
