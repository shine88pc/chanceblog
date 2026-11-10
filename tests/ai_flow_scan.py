"""AI 흐름 정적 규칙 스캐너 — 저장소의 파이썬 소스를 AST 로 읽어 'AI 를 부르는 길'과 'Fact 자료가 AI 로 새는 길'의 알려진 모양을 모은다.
순수 함수다: 소스 글자(상대 경로 → 글)와 설정만 받고 파일·네트워크를 쓰지 않는다. tests/test_ai_flow.py(등록 목록 대조·합성 위반·변이)가 쓰고, 아래 `main` 은 다른 작업 트리를 읽는 점검용이다.

**보증이 아니다.** 알려진 모양의 목록이다. 이름을 조립한 호출·`llm` 이 아닌 이름으로 받은 호출 객체·같은 이름을 가진 껍데기 함수·함수 이름을 변수로 옮겨 부르는 호출(functools.partial(getattr …)·pickle)과
소스 밖의 일은 잡지 못한다 — 그 사각지대는 docs/AI_FLOW.md 의 표에 적고(시험 BlindSpotTest 가 '못 잡는다' 고 단언한다), 못 잡는 것은 런타임 방벽(pipeline/ai_guard.py)과 AI 키 미전달(2단계)이 맡는다.
이 스캐너를 약하게 만드는 변경(등록 목록 늘리기·규칙 지우기)은 T3 다.

규칙(실패 메시지는 한 줄로 '무엇이·어디서·무엇을 하라'를 말한다)
  AF1 F-IMPORTS       Fact 모듈 ↔ AI 모듈 임포트 단방향 격리: 둘 사이의 추이적 폐포(함수 안 임포트 포함), 다리는 BRIDGES 뿐이고 다리 안쪽은 따라가지 않는다
  AF2 AI-PRIMITIVES   AI SDK 임포트·클라이언트 생성·`.generate_content`(호출·별칭 참조)·AI 제공처 주소 글자는 등록된 함수(AI_PRIMITIVES)에만
  AF3 LLM-CONSUMERS   호출 객체 `llm(...)` 를 부르는 함수(LLM_CONSUMERS)와 호출 객체를 만드는 함수(LLM_FACTORY_CALLERS)는 등록된 곳에만
  AF4 FACT-NO-AI      DEFAULT_ENTRIES(Fact 분기 진입 함수 — 설정 fact_entries)에서 호출·참조로 닿는 함수에 AI 가능 함수·AI 이름이 없다(별칭·콜백 참조 포함). 지금 진입 함수 목록은 비어 있다 — 2단계가 채운다
  AF5 AI-CALL-SITES   `call_gemini_with_fallback`·`build_post_prompt`·`make_image_queries` 를 부르거나 참조하는 곳은 등록된 함수(AI_CALL_SITES)뿐
  AF6 POSTS-FOR-AI    `_posts` 를 읽는 함수는 모두 POSTS_READERS 에 올라 있고, AI 가능 함수·Fact 분기는 표식을 거르지 않는 읽기를 **직접** 부르지 못하며 for_ai 를 끄거나 변수·`**옵션`·위치 인자로 넘기지 못한다.
                      그에 더해 for_ai 를 켜지 않은 채 거르는 읽기를 부르는 모든 함수(UNFILTERED_SITES)와 사람용 읽기를 부르는 모든 함수(HUMAN_CALLERS)는 AI 가능 여부와 상관없이 등록돼야 한다 —
                      중립 도우미 한 단계를 거치는 우회는 도우미의 등록 없이는 생길 수 없다(등록은 사람이 보는 자리다. 함수 이름을 변수로 옮겨 부르는 모양은 못 본다)
  AF8 NO-DYNAMIC      Fact 모듈이 subprocess·importlib·runpy·ctypes·multiprocessing·socket 을 가져오거나 exec/eval·동적 임포트 호출·서브프로세스 호출이 있으면 위반이고, Fact 분기에서 닿는 함수에는 이름이 동적인
                      getattr·`globals()[식]` 도 위반이다(Fact 모듈 안의 비상수 getattr 는 정당한 쓰임이 있어 세지 않는다 — 못 잡는다)
  (AF7 워크플로 AI 키 식은 `content_source` 스위치가 생기는 2단계가 더한다 — docs/AI_FLOW.md)
  AF0 PARSE           읽을 수 없거나 문법 오류인 파일은 확인하지 못한 것이므로 위반이다(알 수 없으면 막는다)

등록 목록(AI_PRIMITIVES·LLM_CONSUMERS·LLM_FACTORY_CALLERS·AI_CALL_SITES·POSTS_READERS)은 지금 코드의 호출 지점 전부로 시작하고 **이유와 함께** 적는다. 새 항목을 올리려면 이유를 쓰고
docs/AI_FLOW.md 의 표도 같이 고친다(tests/test_ai_flow_docs.py 가 표와 상수의 일치를 본다). 모듈 이름은 저장소 루트 기준의 점 이름이다(generator.py → generator, pipeline/llm.py → pipeline.llm).
"""
import ast
import collections
import dataclasses
import os
import re
import sys
from pathlib import Path

Violation = collections.namedtuple("Violation", "rule where line message")

RULE_NAMES = {
    "AF0": "PARSE", "AF1": "F-IMPORTS", "AF2": "AI-PRIMITIVES", "AF3": "LLM-CONSUMERS", "AF4": "FACT-NO-AI", "AF5": "AI-CALL-SITES", "AF6": "POSTS-FOR-AI", "AF8": "NO-DYNAMIC",
}

# ----------------------------------------------------------------------------
# 알려진 모양 표
# ----------------------------------------------------------------------------
SDK_CALL_ATTRS = frozenset({"generate_content", "generate_content_stream", "generate_content_async", "embed_content", "count_tokens", "generate_text",
                            "stream_generate_content", "generate_answer", "generate_message"})
SDK_CREATE_OWNERS = frozenset({"completions", "messages", "responses", "chat", "embeddings"})      # `.create(` 는 흔해서 앞 객체 이름이 이것일 때만 센다
AI_SDK_ROOTS = ("openai", "anthropic", "vertexai", "cohere", "mistralai", "ollama", "litellm", "langchain", "langchain_core", "langchain_openai", "langchain_community",
                "transformers", "huggingface_hub", "groq", "together", "replicate", "deepseek", "llama_cpp", "google.generativeai", "google.genai", "google.cloud.aiplatform",
                "azure.ai", "boto3.bedrock")
# AI 제공처로 가는 **주소**(스킴이 붙은 글자) — 호스트 이름만 적은 데이터 표(외부 접속 허용 목록 따위)는 호출이 아니므로 세지 않는다. 이름을 조립한 주소는 못 잡는다(사각지대)
AI_HOST_RX = re.compile(r"https?://[^\s'\"<>]*(?:generativelanguage\.googleapis|aiplatform\.googleapis|api\.openai|openai\.azure|api\.anthropic|api\.mistral|api\.cohere|api\.deepseek|api\.groq|"
                        r"api-inference\.huggingface|openrouter\.ai|api\.together|api\.replicate|bedrock-runtime)|localhost:11434", re.I)
LLM_CALLABLE_NAMES = frozenset({"llm", "_llm", "call_llm", "llm_call"})       # 호출 객체를 부르는 이름(의존성 주입)
LLM_FACTORIES = frozenset({"make_gemini_llm", "build_llm"})                   # 호출 객체를 만드는 함수
DYNAMIC_CALLS = frozenset({"import_module", "__import__", "spec_from_file_location", "exec_module", "run_path", "run_module"})
SPAWN_ATTRS = frozenset({"run", "Popen", "call", "check_call", "check_output", "system", "popen", "spawnl", "spawnv", "startfile"})
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
POSTS_PATH_NAMES = frozenset({"POSTS_DIR", "POSTS"})        # `_posts` 폴더 경로를 담는 이름(모듈 상수)
POSTS_LISTING_ATTRS = frozenset({"rglob", "glob", "iterdir", "scandir", "listdir", "walk"})
COMMON_METHODS = frozenset({"get", "set", "add", "update", "append", "extend", "pop", "run", "read", "write", "open", "close", "join", "split", "strip", "format", "items",
                            "keys", "values", "copy", "find", "match", "search", "sub", "replace", "startswith", "endswith", "lower", "upper", "encode", "decode", "send",
                            "call", "remove", "clear", "sort", "count", "index", "insert", "load", "loads", "dump", "dumps", "exists", "mkdir", "unlink", "is_file", "is_dir",
                            "read_text", "write_text", "iterdir", "glob", "rglob", "resolve", "group", "groups", "finditer", "findall", "fullmatch", "compile", "get_nowait"})
AI_HIT_KINDS = frozenset({"sdk_import", "sdk_client", "sdk_call", "llm_call", "ai_host"})       # 이 중 하나를 직접 하는 함수 = AI 를 부를 수 있는 함수의 바닥
FILTERED_READERS = frozenset({"load_posts", "existing_titles", "entry_titles", "other_blog_titles"})      # `for_ai` 매개변수가 있고 기본이 True(표식 글을 거름)인 읽기

# ----------------------------------------------------------------------------
# 스캔 범위 — tests/ 밖의 모든 *.py 는 아래 '스캔함' 이거나 '제외(이유)' 둘 중 하나여야 한다(tests/test_ai_flow.py 가 확인 — 새 최상위 폴더가 생기면 빨강)
# ----------------------------------------------------------------------------
SCAN_ROOTS = ("generator.py", "blogger_generator.py", "pipeline", "scripts", "인수인계/도구")
SCAN_EXCLUDED = (
    ("tests", "시험 코드 — 운영 경로가 아니다(가짜 AI 호출 대역이 많아 스캔하면 잡음이 된다). 시험이 진짜 AI 를 부르지 않는 것은 시험 모음의 몫이다"),
)
SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules", "_site", ".ruff_cache", ".pytest_cache", ".venv", "venv"})

# ----------------------------------------------------------------------------
# 등록 목록 — 지금 코드(Gate 가지 포함)의 호출 지점 전부. 값은 '왜 여기에 있는가' 한 줄이다. 늘리려면 이유를 쓰고 docs/AI_FLOW.md 표를 같이 고친다.
# ----------------------------------------------------------------------------
_PIPELINE = "pipeline"
FACT_MODULE_NAMES = ("facts", "calc", "fact_topics", "recipes", "fact_assembler", "adapters", "adapters.base", "adapters.mock_stats")
FACT_MODULES = frozenset(f"{_PIPELINE}.{name}" for name in FACT_MODULE_NAMES)       # 구조화 Fact 경로 1단계 모듈(트리에 있는 것만 쓴다)
FACT_PREFIXES = (f"{_PIPELINE}.adapters.",)                                         # 앞으로 생길 제공처 어댑터
BRIDGES = frozenset({"generator"})                                                   # Fact 와 AI 분기를 한 파일에 두는 유일한 운영 모듈(2단계) — 두 분기의 분리는 AF4 가 지킨다
AI_PRIMITIVES = {
    ("generator.py", "get_client"): "Chance 생성기의 Gemini SDK 클라이언트 만들기(지연 임포트) — 모든 Chance AI 호출의 바닥",
    ("generator.py", "_generate.call"): "Chance 생성기의 SDK 호출 한 번(generate_content) — call_gemini_with_fallback 만 부른다",
    ("pipeline/llm.py", "make_gemini_llm.client"): "공용 호출 객체의 SDK 클라이언트 만들기(지연 임포트) — Blogger·Naver·이슈 수정·대표 사진·주제 확장의 바닥",
    ("pipeline/llm.py", "make_gemini_llm.call"): "공용 호출 객체의 SDK 호출 — 모델 폴백·재시도·시간 상한·호출 기록이 이 안에 있다",
}
LLM_CONSUMERS = {
    ("pipeline/topics.py", "pick_topic"): "Blogger·Naver 주제 확장 — 자기 블로그 이력 주제만 프롬프트에 싣는다",
    ("pipeline/run.py", "run"): "Blogger·Naver 글 쓰기 — 프롬프트 파일·주제·게이트 탈락 사유(다른 블로그 제목은 표식 항목을 건너뛴 목록에서)",
    ("pipeline/main_image.py", "ask_queries"): "Blogger 대표 사진 영어 검색어 — 방금 쓴 Blogger 글의 제목·라벨(AI 가 쓴 글)",
    ("pipeline/edits/ops.py", "op_llm_patch"): "이슈 수정의 AI 최소 패치 — 대상은 루트 고정 페이지뿐이고 표식이 있는 파일은 거절한다",
    ("pipeline/edits/ops.py", "image_queries"): "이슈 수정의 이미지 검색어 — op_image 가 표식 글을 AI 를 부르기 전에 거절한다",
}
LLM_FACTORY_CALLERS = {
    ("pipeline/run.py", "run"): "Blogger·Naver 러너가 호출 객체를 만든다(키가 있을 때)",
    ("pipeline/edits/runner.py", "build_llm"): "이슈 수정 러너의 호출 객체 만들기",
    ("pipeline/edits/runner.py", "_process"): "이슈 수정 러너가 build_llm 을 부른다",
}
AI_NAMES = frozenset({"call_gemini_with_fallback", "_generate", "get_client", "make_image_queries", "build_post_prompt", "make_gemini_llm", "build_llm", "llm"})      # Fact 분기가 닿으면 안 되는 이름
AI_CALL_SITES = {
    "_generate": {
        ("generator.py", "call_gemini_with_fallback"): "모델 폴백 루프 — SDK 호출 한 번(_generate)은 이 함수만 부른다(그래야 입구 방벽 ai_guard.assert_clean 을 거친다)",
    },
    "get_client": {
        ("generator.py", "_generate.call"): "SDK 호출 한 번이 클라이언트를 얻는 곳 — 다른 함수가 클라이언트를 직접 얻어 부르면 입구 방벽을 건너뛴다",
        ("pipeline/egress.py", "<module>"): "외부 접속 예외 표에 데이터로 적힌 글자 get_client 한 줄(호출하지 않는다 — 호출 지점이 아니라 이름만 적은 표)",
    },
    "call_gemini_with_fallback": {
        ("generator.py", "make_image_queries"): "기존 글 이미지 교체의 영어 검색어(제목·태그·분류 — 표식 글은 repair 가 건너뛴다)",
        ("generator.py", "generate_blog_posts"): "새 글 쓰기(피드 항목 + 최근 제목 30개 — 표식 글이 빠진 목록)",
        ("pipeline/shadow_run.py", "_evaluate"): "그림자 실행의 후보 평가 — generator 를 가져오지 않고 인자 g 로 받아 부른다(감사 F6)",
    },
    "build_post_prompt": {
        ("generator.py", "generate_blog_posts"): "새 글 프롬프트 조립",
        ("pipeline/shadow_run.py", "_evaluate"): "그림자 실행의 프롬프트 조립(generate_blog_posts 와 같은 함수·같은 입력)",
    },
    "make_image_queries": {
        ("generator.py", "repair"): "기존 글 이미지 교체 — 표식 글이면 부르기 전에 돌아온다",
    },
}
# `_posts` 를 읽는 함수 전부(AST 로 찾은 것과 일치해야 한다). 종류: filtered = for_ai 매개변수(기본 True)로 표식 글을 거른다 · keys_only = 이미지 주소 키만 모은다(제목·글자를 돌려주지 않는다) ·
# human = 사람·알림·사이트가 읽는 곳(AI 를 부르는 함수·Fact 분기는 부르지 않는다)
POSTS_READERS = {
    ("generator.py", "load_posts"): ("filtered", "AI 입력이 될 수 있는 읽기의 유일한 문 — for_ai=True(기본)면 표식 글·표식 여부를 알 수 없는 글을 목록에서 뺀다"),
    ("pipeline/edits/ops.py", "used_image_keys"): ("keys_only", "이미 쓴 Unsplash 이미지 주소 키(호스트+경로)만 모은다 — 제목·태그·본문 글자를 돌려주지 않아 AI 입력이 될 수 없다"),
    ("pipeline/edits/targets.py", "load_post_index"): ("human", "이슈의 대상 글 찾기(주소·파일 이름·제목 비교) — 결과는 사람에게 보이는 코멘트에 쓰이고, AI 로 가는 길(op_image)은 글 파일 자체의 표식을 본다"),
    ("scripts/verify_pages_deploy.py", "find_candidates"): ("human", "배포 뒤 공개 확인의 최신 글 고르기 — 사이트 주소만 만든다"),
}
FILTERED_KEYWORD = "for_ai"
FILTERED_POSITIONAL_MAX = {"load_posts": 0, "existing_titles": 2, "entry_titles": 1, "other_blog_titles": 3}      # 표식을 거르는 읽기마다 위치 인자로 받는 개수(for_ai 는 키워드 전용이라 이보다 많이 넘기면 for_ai 를 위치로 넘긴 것이다)
# for_ai 를 켜지 않은 채(끔·식) 표식을 거르는 읽기를 부르는 함수 전부 — AI 를 부를 수 있든 없든 올려야 한다(AI 를 부를 수 있는 함수는 이 등록과 상관없이 위반이다). 중립 도우미 한 단계를 거쳐 for_ai 를 끄는 우회가 '등록해야 보이게' 한다(D-197).
UNFILTERED_SITES = {
    ("pipeline/state.py", "other_blog_titles"): "받은 for_ai(기본 켜짐)를 entry_titles 에 그대로 넘기는 통과 함수 — AI 를 부르지 않는다",
}
# 사람용(`human`) 읽기를 부르는 함수 전부(AI 를 부를 수 있는 함수·Fact 분기는 부르지 못한다 — 그 규칙과 별개로, 새 호출 지점이 생기면 등록해야 보이게 한다. D-197).
HUMAN_CALLERS = {
    ("pipeline/edits/runner.py", "resolve_request"): "이슈의 대상 글 찾기(load_post_index) — 결과는 사람에게 보이는 코멘트에 쓰이고 AI 입력으로 가지 않는다",
    ("scripts/verify_pages_deploy.py", "select_newest"): "배포 뒤 공개 확인의 최신 글 고르기(find_candidates) — 사이트 주소만 만든다",
}
RISKY_IMPORT_ROOTS = frozenset({"subprocess", "importlib", "runpy", "ctypes", "multiprocessing", "socket"})      # Fact 모듈이 가져오면 위반(AF8): 프로세스·동적 로드·네이티브 호출·네트워크
DEFAULT_ENTRIES = frozenset()      # Fact 분기 진입 함수 (파일, 함수) — 2단계가 생성기에 Fact 분기를 만들 때 채운다(지금은 비어 있다: AF4 는 합성 소스로만 시험한다)


@dataclasses.dataclass(frozen=True)
class Config:
    fact_modules: frozenset = FACT_MODULES
    fact_prefixes: tuple = FACT_PREFIXES
    bridges: frozenset = BRIDGES
    ai_primitives: dict = dataclasses.field(default_factory=lambda: dict(AI_PRIMITIVES))
    llm_consumers: dict = dataclasses.field(default_factory=lambda: dict(LLM_CONSUMERS))
    llm_factory_callers: dict = dataclasses.field(default_factory=lambda: dict(LLM_FACTORY_CALLERS))
    ai_names: frozenset = AI_NAMES
    ai_call_sites: dict = dataclasses.field(default_factory=lambda: {name: dict(sites) for name, sites in AI_CALL_SITES.items()})
    posts_readers: dict = dataclasses.field(default_factory=lambda: dict(POSTS_READERS))
    fact_entries: frozenset = DEFAULT_ENTRIES
    unfiltered_sites: dict = dataclasses.field(default_factory=lambda: dict(UNFILTERED_SITES))
    human_callers: dict = dataclasses.field(default_factory=lambda: dict(HUMAN_CALLERS))


DEFAULT_CONFIG = Config()


# ----------------------------------------------------------------------------
# 소스 읽기
# ----------------------------------------------------------------------------
def module_name(rel):
    parts = rel.split("/")
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def read_tree(root, scan_roots=SCAN_ROOTS):
    """{상대 경로(POSIX): 글} — scan_roots 아래 모든 *.py. 읽을 수 없는 파일은 글을 None 으로 둔다(AF0 이 위반으로 센다)."""
    root = Path(root)
    found = {}
    for entry in scan_roots:
        base = root / entry
        if base.is_file():
            files = [base]
        elif base.is_dir():
            files = []
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
                files += [Path(dirpath, name) for name in sorted(filenames) if name.endswith(".py")]
        else:
            continue
        for path in files:
            rel = path.relative_to(root).as_posix()
            try:
                found[rel] = path.read_text(encoding="utf-8-sig")      # 윈도우 도구가 붙이는 BOM 은 파이썬도 소스에서 눈감아 준다 — 합법 소스를 문법 오류로 세지 않는다
            except (OSError, UnicodeDecodeError):
                found[rel] = None
    return found


# ----------------------------------------------------------------------------
# AST 분석
# ----------------------------------------------------------------------------
def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _terminal(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _mentions_posts(node, posts_vars):
    """식 안에 `_posts` 폴더를 가리키는 이름(POSTS_DIR 따위)·글자 `_posts`·이 함수에서 그런 식을 대입받은 지역 이름이 있는가."""
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and (child.id in POSTS_PATH_NAMES or child.id in posts_vars):
            return True
        if isinstance(child, ast.Attribute) and child.attr in POSTS_PATH_NAMES:      # `generator.POSTS_DIR.glob(…)` 처럼 다른 모듈의 상수를 점 이름으로 부르는 모양(D-198)
            return True
        if isinstance(child, ast.Constant) and isinstance(child.value, str) and "_posts" in child.value:
            return True
    return False


class _Func:
    __slots__ = ("module", "qual", "lineno", "params", "calls", "hits", "refs", "names", "locals", "posts_reads", "strs", "ref_lines")

    def __init__(self, module, qual, lineno, params):
        self.module, self.qual, self.lineno, self.params = module, qual, lineno, params
        self.calls = []         # (단순 이름, 점 이름, 줄, for_ai 상태)
        self.hits = []          # (종류, 줄, 설명)
        self.refs = set()       # 읽은 이름(Name·Attribute 이름) — 별칭·콜백으로 넘기는 참조까지 보려는 용도
        self.names = set()      # 읽은 '맨 이름'(Name 만) — 참조 간선은 이것만 쓴다(속성 이름은 add·search 처럼 흔해서 과대 간선을 만든다)
        self.locals = set()     # 이 함수 안에서 대입된 이름
        self.posts_reads = []   # `_posts` 를 훑는 호출 (줄, 설명)
        self.strs = set()       # 이름처럼 생긴 글자 상수(`getattr(g, "call_gemini_with_fallback")`·`operator.attrgetter("…")`·`globals()["…"]` 처럼 이름을 글자로 넘기는 호출을 잡으려는 용도)
        self.ref_lines = {}     # 이름 → 처음 읽은 줄(호출이 아닌 참조 위반의 줄을 정확히 보고하려는 용도 — 모듈 맨 위 데이터 표의 위반이 줄 1 로 나오지 않게)


class _Scan(ast.NodeVisitor):
    def __init__(self, module, rel, text):
        self.module, self.rel, self.lines = module, rel, text.split("\n")      # splitlines 는 폼피드·U+2028 에서도 줄을 나눠 파서의 줄 번호와 어긋난다
        self.funcs = {"<module>": _Func(module, "<module>", 1, ())}
        self.cur = self.funcs["<module>"]
        self.stack = []
        self.imports = {}
        self.llm_vars = set()
        self.docstrings = set()
        self.posts_vars = [set()]
        self.tree = None
        self.import_records = []

    def _line(self, lineno):
        return self.lines[lineno - 1].strip()[:140] if 1 <= lineno <= len(self.lines) else ""

    # ---- 구조 ----
    def _mark_docstring(self, node):
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            self.docstrings.add(id(body[0].value))

    def visit_Module(self, node):
        self._mark_docstring(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self._mark_docstring(node)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node):
        self._mark_docstring(node)
        qual = ".".join(self.stack + [node.name])
        args = node.args
        params = [a.arg for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)]
        if args.vararg:
            params.append("*" + args.vararg.arg)
        if args.kwarg:
            params.append("**" + args.kwarg.arg)
        info = _Func(self.module, qual, node.lineno, tuple(params))
        self.funcs[qual] = info
        previous = self.cur
        self.cur = info
        self.stack.append(node.name)
        self.posts_vars.append(set())
        self.generic_visit(node)
        self.posts_vars.pop()
        self.stack.pop()
        self.cur = previous

    visit_AsyncFunctionDef = visit_FunctionDef

    # ---- 임포트 ----
    def visit_Import(self, node):
        for alias in node.names:
            self.imports[alias.asname or alias.name.split(".")[0]] = alias.name
            self._import_hit(alias.name, node.lineno)
            self._note_ref(alias.name.split(".")[-1], node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        base = ("." * node.level) + (node.module or "")
        for alias in node.names:
            self.imports[alias.asname or alias.name] = f"{base}.{alias.name}".strip(".")
            self._import_hit(f"{node.module or ''}.{alias.name}".strip("."), node.lineno)
            self._note_ref(alias.name, node.lineno)        # 가져온 이름 자체를 참조로 센다 — `from generator import call_gemini_with_fallback as ask` 의 별칭 호출도 이 가져오기 한 줄에서 잡힌다(D-198)
        self.generic_visit(node)

    def _note_ref(self, name, lineno):
        self.cur.refs.add(name)
        self.cur.ref_lines.setdefault(name, lineno)

    def _import_hit(self, dotted_name, lineno):
        top = dotted_name.split(".")[0]
        if top in RISKY_IMPORT_ROOTS:
            self.cur.hits.append(("risky_import", lineno, f"프로세스·동적 로드·네이티브·네트워크 모듈 임포트: {dotted_name}"))
        for root in AI_SDK_ROOTS:
            if dotted_name == root or dotted_name.startswith(root + "."):
                self.cur.hits.append(("sdk_import", lineno, f"AI SDK 임포트: {dotted_name}"))
                return

    # ---- 호출 ----
    def visit_Call(self, node):
        name, full, line = _terminal(node.func), _dotted(node.func), node.lineno
        for_ai = "absent"
        for keyword in node.keywords:
            if keyword.arg == FILTERED_KEYWORD:
                for_ai = keyword.value.value if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, bool) else "expr"
            elif keyword.arg is None and name in FILTERED_READERS and for_ai == "absent":
                for_ai = "expr"      # `**옵션` 으로 넘긴다 — for_ai 가 켜졌는지 알 수 없다
        if name in FILTERED_READERS and for_ai == "absent" and (any(isinstance(arg, ast.Starred) for arg in node.args) or len(node.args) > FILTERED_POSITIONAL_MAX[name]):
            for_ai = "expr"          # `*인자` 또는 키워드 전용 자리를 넘는 위치 인자 — for_ai 를 위치로 넘긴 모양(코드는 TypeError 로 막지만 규칙도 알 수 없음으로 센다)
        if name:
            self.cur.calls.append((name, full, line, for_ai))
        if isinstance(node.func, ast.Attribute) and node.func.attr == "create" and _terminal(node.func.value) in SDK_CREATE_OWNERS:
            self.cur.hits.append(("sdk_call", line, f"SDK 호출 `{_terminal(node.func.value)}.create(` — {self._line(line)}"))
        if name == "Client" and full.split(".")[0] in ("genai", "openai", "anthropic"):
            self.cur.hits.append(("sdk_client", line, f"AI 클라이언트 생성 `{full}(` — {self._line(line)}"))
        if (isinstance(node.func, ast.Name) and node.func.id in LLM_CALLABLE_NAMES) or \
                (isinstance(node.func, ast.Attribute) and node.func.attr in LLM_CALLABLE_NAMES and isinstance(node.func.value, ast.Name) and node.func.value.id in ("self", "cls")):
            self.cur.hits.append(("llm_call", line, f"호출 객체 호출 `{full or name}(…)` — {self._line(line)}"))
        if isinstance(node.func, ast.Name) and node.func.id in self.llm_vars:
            self.cur.hits.append(("llm_call", line, f"호출 객체 변수 호출 `{node.func.id}(…)` — {self._line(line)}"))
        if name in LLM_FACTORIES:
            self.cur.hits.append(("llm_factory", line, f"호출 객체 만들기 `{name}(` — {self._line(line)}"))
        if name in DYNAMIC_CALLS:
            self.cur.hits.append(("dynamic_import", line, f"동적 임포트·실행 `{full or name}(` — {self._line(line)}"))
        if isinstance(node.func, ast.Name) and node.func.id in ("exec", "eval"):
            self.cur.hits.append(("exec_eval", line, f"`{node.func.id}(` — {self._line(line)}"))
        if isinstance(node.func, ast.Attribute) and node.func.attr in SPAWN_ATTRS and _terminal(node.func.value) in ("subprocess", "os", "sp"):
            self.cur.hits.append(("spawn", line, f"프로세스 실행 `{full}(` — {self._line(line)}"))
        if name in ("getattr", "setattr") and len(node.args) >= 2 and not isinstance(node.args[1], ast.Constant):
            self.cur.hits.append(("dynamic_getattr", line, f"이름이 동적인 `{name}(` — {self._line(line)}"))
        # `_posts` 를 훑는 호출: X.rglob(…)·os.walk(X)·listdir(X) … 의 X(또는 인자)가 `_posts` 폴더를 가리킨다
        if name in POSTS_LISTING_ATTRS:
            receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
            probes = ([receiver] if receiver is not None else []) + list(node.args)
            if any(_mentions_posts(probe, self.posts_vars[-1]) for probe in probes):
                self.cur.posts_reads.append((line, f"`{name}(` — {self._line(line)}"))
        self.generic_visit(node)

    def visit_Assign(self, node):
        if isinstance(node.value, ast.Call) and _terminal(node.value.func) in LLM_FACTORIES:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.llm_vars.add(target.id)
        if _mentions_posts(node.value, self.posts_vars[-1]):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.posts_vars[-1].add(target.id)
        self.generic_visit(node)

    def visit_Subscript(self, node):
        base = node.value
        namespace = ((isinstance(base, ast.Call) and isinstance(base.func, ast.Name) and base.func.id in ("globals", "vars", "locals"))
                     or (isinstance(base, ast.Attribute) and base.attr == "__dict__"))
        if namespace and not isinstance(node.slice, ast.Constant):
            self.cur.hits.append(("dynamic_getattr", node.lineno, f"이름이 동적인 네임스페이스 조회 `…[식]` — {self._line(node.lineno)}"))
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.cur.refs.add(node.id)
            self.cur.names.add(node.id)
            self.cur.ref_lines.setdefault(node.id, node.lineno)
        else:
            self.cur.locals.add(node.id)

    def visit_Attribute(self, node):
        if isinstance(node.ctx, ast.Load):
            self.cur.refs.add(node.attr)
            self.cur.ref_lines.setdefault(node.attr, node.lineno)
            if node.attr in SDK_CALL_ATTRS:
                self.cur.hits.append(("sdk_call", node.lineno, f"SDK 호출·참조 `.{node.attr}` — {self._line(node.lineno)}"))
        self.generic_visit(node)

    def visit_Constant(self, node):
        value = node.value
        if not isinstance(value, str) or id(node) in self.docstrings:
            return
        if len(value) < 80 and _IDENTIFIER.fullmatch(value):
            self.cur.strs.add(value)
            self.cur.ref_lines.setdefault(value, node.lineno)
        elif len(value) < 2000 and AI_HOST_RX.search(value):
            self.cur.hits.append(("ai_host", node.lineno, f"AI 제공처 주소 글자: {value[:60]}"))


_SCAN_CACHE = {}


def _scan_source(rel, text):
    """(스캔, None) 또는 (None, (줄, 사유)). 같은 (경로, 글)은 한 번만 읽는다 — 변이를 여러 번 돌려도 바뀌지 않은 파일은 다시 파싱하지 않는다(스캔 결과는 읽기 전용이다)."""
    key = (rel, text)
    found = _SCAN_CACHE.get(key)
    if found is None:
        if text is None:
            found = (None, (0, "파일을 읽을 수 없다(UTF-8 아님·읽기 오류)"))
        else:
            try:
                tree = ast.parse(text, filename=rel)
                scan = _Scan(module_name(rel), rel, text)
                scan.visit(tree)
                scan.tree = tree
                walker = _ImportWalker(scan.module, rel)
                walker.visit(tree)
                scan.import_records = walker.records
            except SyntaxError as exc:
                found = (None, (exc.lineno or 0, f"문법 오류: {exc.msg}"))
            except (RecursionError, MemoryError, ValueError, SystemError) as exc:
                # 파이썬 판마다 깊이 한계가 달라(리눅스 3.10·3.12 와 윈도우) 어떤 판에서는 읽히고 어떤 판에서는 못 읽는 소스가 있다 — 못 읽으면 '보지 못했다' 를 위반으로 센다(알 수 없으면 막는다).
                found = (None, (0, f"구문을 분석하지 못함({type(exc).__name__}) — 너무 깊게 중첩되었거나 읽을 수 없는 소스는 위반으로 본다"))
            else:
                found = (scan, None)
        if len(_SCAN_CACHE) > 600:
            _SCAN_CACHE.clear()
        _SCAN_CACHE[key] = found
    return found


class Analysis:
    """read_tree 결과(소스 글자 사전)를 한 번 분석한 것: scans(모듈→_Scan)·direct(AI 를 직접 하는 함수)·capable(AI 를 부를 수 있는 함수)·edges(호출 간선)·errors(파싱 실패)."""

    def __init__(self, sources):
        self.scans, self.errors = {}, []
        for rel, text in sorted(sources.items()):
            scan, error = _scan_source(rel, text)
            if error is not None:
                self.errors.append((rel, error[0], error[1]))
            else:
                self.scans[scan.module] = scan
        self.index = collections.defaultdict(list)
        for module, scan in self.scans.items():
            for qual in scan.funcs:
                if qual != "<module>":
                    self.index[qual.split(".")[-1]].append((module, qual))
        self.edges = collections.defaultdict(set)
        self.reverse = collections.defaultdict(set)
        for module, scan in self.scans.items():
            for qual, info in scan.funcs.items():
                for name, full, _line, _flag in info.calls:
                    targets, fuzzy = self._resolve(scan, name, full)
                    for target in targets:
                        self.edges[(module, qual)].add((target, fuzzy))
                        self.reverse[target].add(((module, qual), fuzzy))
        self.direct = {(m, q) for m, s in self.scans.items() for q, f in s.funcs.items() if any(h[0] in AI_HIT_KINDS for h in f.hits)}
        self.capable = set(self.direct)
        queue = collections.deque(self.direct)
        while queue:
            node = queue.popleft()
            for caller, _fuzzy in self.reverse.get(node, ()):
                if caller not in self.capable:
                    self.capable.add(caller)
                    queue.append(caller)
        self.top_level = {m: {q for q in s.funcs if q != "<module>" and "." not in q} for m, s in self.scans.items()}
        self.imports_graph = self._import_graph()

    def rel(self, node):
        return self.scans[node[0]].rel

    def func(self, node):
        return self.scans[node[0]].funcs[node[1]]

    def _resolve(self, scan, callee, full):
        """호출 하나가 가리킬 수 있는 ([(모듈, qual)], 이름만 같아서 닿은 것인가). 과대 추정이다 — 놓치지 않는 쪽으로 틀린다."""
        parts = full.split(".") if full else [callee]
        same = [(m, q) for m, q in self.index.get(callee, []) if m == scan.module]
        if len(parts) == 1:
            if same:
                return same, False
            target = scan.imports.get(callee)
            if target:
                mod = target.rsplit(".", 1)[0].lstrip(".")
                return [(m, q) for m, q in self.index.get(callee, []) if m == mod or m.endswith("." + mod) or mod.endswith("." + m)], False
            return [], False
        if parts[0] in ("self", "cls"):
            return same, False
        if parts[0] in scan.imports:
            target = scan.imports[parts[0]].lstrip(".")
            in_tree = [m for m in self.scans if m == target or m.endswith("." + target) or target.endswith("." + m)]
            return ([(m, q) for m, q in self.index.get(callee, []) if m in in_tree], False) if in_tree else ([], False)
        if same:
            return same, False
        if callee in COMMON_METHODS:
            return [], False
        every = self.index.get(callee, [])
        return (every, True) if every and len(every) <= 6 else ([], False)

    # ---- 임포트 그래프 ----
    def _import_graph(self):
        """모듈 → [(대상 모듈, 줄, 함수 안인가)] — 트리 안 모듈로 가는 간선만. `import a.b.c` 는 부모 패키지의 __init__ 도 실행하므로 부모 간선도 넣는다."""
        known = set(self.scans)
        graph = {}
        for module, scan in self.scans.items():
            edges = []
            for dst, line, lazy in scan.import_records:
                parts = dst.split(".") if dst else []
                for size in range(1, len(parts) + 1):
                    candidate = ".".join(parts[:size])
                    if candidate in known and candidate != module:
                        edges.append((candidate, line, lazy))
            graph[module] = edges
        return graph


class _ImportWalker(ast.NodeVisitor):
    """한 모듈의 임포트 기록 (가져온 점 이름, 줄, 함수 안인가): `import`·`from … import`(상대 임포트 포함)·상수 글자를 넘긴 `importlib.import_module`/`__import__`. TYPE_CHECKING 안의 임포트는 실행되지 않으므로 뺀다.
    트리 안 모듈인지는 보지 않는다(분석마다 모듈 집합이 달라 Analysis 가 걸러 낸다) — 그래서 파일마다 한 번만 만들어 둘 수 있다."""

    def __init__(self, module, rel):
        self.records, self.depth = [], 0
        is_package = rel.endswith("/__init__.py") or rel == "__init__.py"
        self.package = module if is_package else module.rpartition(".")[0]

    def _absolute(self, level, name):
        if level == 0:
            return name or ""
        base = self.package.split(".") if self.package else []
        base = base[:len(base) - (level - 1)] if level > 1 else base
        return ".".join(part for part in base + (name.split(".") if name else []) if part)

    def visit_FunctionDef(self, node):
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node):
        test = node.test
        typing_only = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
        if not typing_only:
            self.generic_visit(node)
        else:
            for child in node.orelse:      # `if TYPE_CHECKING:` 의 본문은 실행되지 않지만 else 가지는 실행된다 — 거기의 임포트는 센다
                self.visit(child)

    def visit_Import(self, node):
        for alias in node.names:
            self.records.append((alias.name, node.lineno, self.depth > 0))

    def visit_ImportFrom(self, node):
        base = self._absolute(node.level, node.module or "")
        self.records.append((base, node.lineno, self.depth > 0))
        for alias in node.names:
            if alias.name != "*":
                self.records.append((f"{base}.{alias.name}" if base else alias.name, node.lineno, self.depth > 0))

    def visit_Call(self, node):
        if _terminal(node.func) in ("import_module", "__import__") and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            self.records.append((node.args[0].value, node.lineno, True))
        self.generic_visit(node)


def _closure(graph, roots, stop=()):
    """roots 에서 임포트로 추이적으로 닿는 모듈 집합과 부모(경로 복원용). stop 에 든 모듈은 집합에는 들어가지만 그 안쪽 간선은 따라가지 않는다(다리)."""
    seen, parent = set(roots), {root: None for root in roots}
    queue = collections.deque(sorted(roots))
    while queue:
        current = queue.popleft()
        if current in stop and current not in roots:
            continue
        for dst, _line, _lazy in graph.get(current, ()):
            if dst not in seen:
                seen.add(dst)
                parent[dst] = current
                queue.append(dst)
    return seen, parent


def _path(parent, dst):
    out = []
    while dst is not None:
        out.append(dst)
        dst = parent[dst]
    return " -> ".join(reversed(out))


def _function_closure(analysis, starts):
    """starts 에서 호출 간선과 참조 간선(맨 이름이 같은 모듈의 최상위 함수나 가져온 함수를 가리킴)으로 닿는 함수와 부모(사슬 복원용)."""
    parent = {start: None for start in starts}
    queue = collections.deque(sorted(starts))
    while queue:
        current = queue.popleft()
        scan = analysis.scans[current[0]]
        info = scan.funcs.get(current[1])
        nexts = [target for target, _fuzzy in analysis.edges.get(current, ())]
        if info is not None:
            for name in info.names - {p.lstrip("*") for p in info.params} - info.locals:
                if name in analysis.top_level.get(current[0], ()):
                    nexts.append((current[0], name))
                else:
                    bound = scan.imports.get(name)
                    if bound and "." in bound:
                        mod, _dot, func = bound.lstrip(".").rpartition(".")
                        nexts.extend((m, func) for m in analysis.top_level if (m == mod or m.endswith("." + mod)) and func in analysis.top_level[m])
        for target in nexts:
            if target not in parent and target[0] in analysis.scans and target[1] in analysis.scans[target[0]].funcs:
                parent[target] = current
                queue.append(target)
    return parent


def _chain(analysis, parent, node):
    out = []
    while node is not None:
        out.append(f"{analysis.rel(node)}:{node[1]}")
        node = parent[node]
    return " <- ".join(out)


# ----------------------------------------------------------------------------
# 규칙
# ----------------------------------------------------------------------------
def check(sources, config=DEFAULT_CONFIG):
    """소스 글자 사전({상대 경로: 글})과 설정으로 모든 규칙을 돌려 Violation 목록을 낸다(정렬됨). 순수 함수."""
    analysis = Analysis(sources)
    out = [Violation("AF0 PARSE", rel, line, f"{message} — 확인하지 못한 파일은 위반이다(알 수 없으면 막는다)") for rel, line, message in analysis.errors]
    scans = analysis.scans

    def at(node):
        return (analysis.rel(node), node[1])

    fact = {m for m in scans if m in config.fact_modules or any(m.startswith(prefix) for prefix in config.fact_prefixes)}
    core = {m for (m, q) in analysis.direct if any(h[0] in ("sdk_call", "sdk_client", "llm_call", "ai_host") for h in scans[m].funcs[q].hits)}
    graph = analysis.imports_graph

    # ---- AF1 ----
    if fact:
        seen, parent = _closure(graph, sorted(fact), stop=config.bridges)
        for hit in sorted((core | set(config.bridges)) & (seen - fact) & set(scans)):
            out.append(Violation("AF1 F-IMPORTS", scans[hit].rel, 0, f"Fact 모듈이 AI 쪽 모듈 {hit} 를 가져온다(경로 {_path(parent, hit)}) — Fact 모듈은 표준 라이브러리와 Fact 모듈만 가져온다"))
        for module in sorted(core - set(config.bridges)):
            seen, parent = _closure(graph, [module], stop=config.bridges)
            for hit in sorted(fact & seen):
                out.append(Violation("AF1 F-IMPORTS", scans[module].rel, 0, f"AI 모듈 {module} 이 Fact 모듈 {hit} 를 가져온다(경로 {_path(parent, hit)}) — AI 모듈은 Fact 모듈을 가져오지 않는다"))
        for module in sorted(set(scans) - fact - core - set(config.bridges)):
            seen, _parent = _closure(graph, [module], stop=config.bridges)
            if seen & fact and seen & core:
                out.append(Violation("AF1 F-IMPORTS", scans[module].rel, 0, f"{module} 이 Fact 모듈과 AI 모듈을 모두 가져온다 — 새 다리다. 다리는 BRIDGES({sorted(config.bridges)}) 뿐이다"))

    # ---- AF2 · AF3 ----
    for (module, qual) in sorted(analysis.direct):
        for kind, line, text in scans[module].funcs[qual].hits:
            if kind in ("sdk_import", "sdk_client", "sdk_call", "ai_host") and (scans[module].rel, qual) not in config.ai_primitives:
                out.append(Violation("AF2 AI-PRIMITIVES", scans[module].rel, line, f"AI SDK 사용({text[:70]})이 등록되지 않은 함수 {qual} 에 있다 — AI_PRIMITIVES 에 이유와 함께 올리거나 지운다"))
            if kind == "llm_call" and (scans[module].rel, qual) not in config.llm_consumers:
                out.append(Violation("AF3 LLM-CONSUMERS", scans[module].rel, line, f"호출 객체 `llm(...)` 를 부르는 곳이 등록되지 않았다({qual}) — LLM_CONSUMERS 에 올리거나 지운다"))
    for module, scan in sorted(scans.items()):
        for qual, info in scan.funcs.items():
            for kind, line, text in info.hits:
                if kind == "llm_factory" and (scan.rel, qual) not in config.llm_factory_callers:
                    out.append(Violation("AF3 LLM-CONSUMERS", scan.rel, line, f"호출 객체 만들기({text[:60]})가 등록되지 않은 함수 {qual} 에 있다 — LLM_FACTORY_CALLERS 에 올리거나 지운다"))

    # ---- AF5 ----
    for module, scan in sorted(scans.items()):
        for qual, info in scan.funcs.items():
            for name, sites in config.ai_call_sites.items():
                if (name in info.refs or name in info.strs) and (scan.rel, qual) not in sites and qual.split(".")[-1] != name:       # 정의 자신 안의 재귀는 새 호출 지점이 아니다
                    line = next((ln for n, _f, ln, _x in info.calls if n == name), info.ref_lines.get(name, info.lineno))
                    out.append(Violation("AF5 AI-CALL-SITES", scan.rel, line, f"`{name}` 를 부르거나 참조하는 새 지점 {qual} — AI_CALL_SITES 에 이유와 함께 올리거나 지운다"))

    # ---- AF6 ----
    reader_nodes = {}
    for module, scan in sorted(scans.items()):
        for qual, info in scan.funcs.items():
            if info.posts_reads:
                key = (scan.rel, qual)
                reader_nodes[key] = (module, qual)
                if key not in config.posts_readers:
                    out.append(Violation("AF6 POSTS-FOR-AI", scan.rel, info.posts_reads[0][0], f"새 `_posts` 읽기 지점 {qual} — POSTS_READERS 에 종류(filtered·keys_only·human)와 이유를 올리거나 지운다"))
    unsafe = {node for node in reader_nodes.values() if config.posts_readers.get(at(node), ("",))[0] == "human"}
    unsafe |= {node for node in reader_nodes.values() if config.posts_readers.get(at(node), ("",))[0] == ""}
    fact_closure = _function_closure(analysis, {(m, q) for m, s in scans.items() for q in s.funcs if (s.rel, q) in config.fact_entries}) if config.fact_entries else {}
    guarded = sorted(analysis.capable | set(fact_closure))
    for node in guarded:
        info = analysis.func(node)
        for name, _full, line, flag in info.calls:
            if name in FILTERED_READERS and flag is not True and flag != "absent":
                out.append(Violation("AF6 POSTS-FOR-AI", analysis.rel(node), line, f"AI 가능 함수 {node[1]} 가 `{name}` 의 for_ai 를 켜지 않은 채({flag!r}) 부른다 — 표식 글의 제목·태그가 AI 입력이 될 수 있다"))
        for target, _fuzzy in sorted(analysis.edges.get(node, ())):
            if target in unsafe and target != node:
                out.append(Violation("AF6 POSTS-FOR-AI", analysis.rel(node), info.lineno, f"AI 가능 함수 {node[1]} 가 provenance 를 거르지 않는 읽기 {target[1]} 를 부른다 — Fact 글의 제목·태그가 AI 입력이 될 수 있다"))

    # AF6 등록 두 가지(D-197): AI 가능 여부와 상관없이 — for_ai 를 켜지 않은 채 거르는 읽기를 부르는 모든 함수와 사람용 읽기를 부르는 모든 함수는 등록돼 있어야 한다.
    # 중립 도우미 한 단계를 거쳐 for_ai 를 끄거나 사람용 읽기를 부르는 우회가 AF6 의 '직접 호출만 본다' 를 빠져나가도, 도우미 자신이 등록 없이는 생길 수 없다.
    for module, scan in sorted(scans.items()):
        for qual, info in scan.funcs.items():
            for name, _full, line, flag in info.calls:
                if name in FILTERED_READERS and flag is not True and flag != "absent" and (scan.rel, qual) not in config.unfiltered_sites and qual.split(".")[-1] != name:
                    out.append(Violation("AF6 POSTS-FOR-AI", scan.rel, line, f"{qual} 가 `{name}` 의 for_ai 를 켜지 않은 채({flag!r}) 부른다 — UNFILTERED_SITES 에 이유와 함께 올리거나 지운다"))
    human_nodes = {node for node in reader_nodes.values() if config.posts_readers.get(at(node), ("",))[0] == "human"}
    for caller, targets in sorted(analysis.edges.items()):
        for target, _fuzzy in sorted(targets):
            if target in human_nodes and caller != target and at(caller) not in config.human_callers:
                out.append(Violation("AF6 POSTS-FOR-AI", analysis.rel(caller), analysis.func(caller).lineno, f"{caller[1]} 가 사람용 읽기 {target[1]} 를 부른다 — HUMAN_CALLERS 에 이유와 함께 올리거나 지운다"))

    # ---- AF4 · AF8 (Fact 분기) ----
    entries = {(m, q) for m, s in scans.items() for q in s.funcs if (s.rel, q) in config.fact_entries}
    if entries:
        for node in sorted(fact_closure):
            info = analysis.func(node)
            if node in analysis.capable and node not in entries:
                out.append(Violation("AF4 FACT-NO-AI", analysis.rel(node), info.lineno, f"Fact 분기에서 닿는 함수 {node[1]} 가 AI 호출로 이어진다 — 사슬 {_chain(analysis, fact_closure, node)}"))
            for name in sorted(((info.refs | {c[0] for c in info.calls}) & config.ai_names) | (info.strs & set(config.ai_call_sites))):
                out.append(Violation("AF4 FACT-NO-AI", analysis.rel(node), info.lineno, f"Fact 분기에서 닿는 함수 {node[1]} 가 AI 이름 `{name}` 을 부르거나 참조한다 — 사슬 {_chain(analysis, fact_closure, node)}"))
            kinds = ("dynamic_import", "exec_eval", "spawn", "risky_import") if node[0] in fact else ("dynamic_import", "exec_eval", "dynamic_getattr", "spawn", "risky_import")
            for kind, line, text in info.hits:
                if kind in kinds:
                    out.append(Violation("AF8 NO-DYNAMIC", analysis.rel(node), line, f"Fact 분기에서 닿는 {node[1]} 에 동적 실행·이름 조립({text[:60]})이 있다"))
    # ---- AF8 (Fact 모듈 자체) ----
    for module in sorted(fact):
        for qual, info in scans[module].funcs.items():
            for kind, line, text in info.hits:
                if kind in ("dynamic_import", "exec_eval", "spawn", "risky_import", "sdk_import", "sdk_call", "sdk_client", "llm_call", "ai_host"):
                    out.append(Violation("AF8 NO-DYNAMIC", scans[module].rel, line, f"Fact 모듈 {module} 에 {kind}({text[:60]}) 이 있다 — Fact 모듈은 동적 실행·AI 호출을 하지 않는다"))
    return sorted(set(out), key=lambda v: (v.rule, v.where, v.line, v.message))


def inventory(sources, config=DEFAULT_CONFIG):
    """등록 목록이 지금 코드와 맞는지 보는 사실표(시험이 쓴다): 실제로 AI 를 직접 하는 함수·llm 호출 함수·호출 객체 만드는 함수·이름별 호출 지점·`_posts` 읽는 함수."""
    analysis = Analysis(sources)
    scans = analysis.scans
    found = {"primitives": set(), "consumers": set(), "factories": set(), "call_sites": {name: set() for name in config.ai_call_sites}, "readers": set(),
             "filtered_calls": set(), "capable": {(analysis.rel(n), n[1]) for n in analysis.capable}, "parse_errors": [e[0] for e in analysis.errors],
             "unfiltered_calls": set(), "human_callers": set()}
    human_nodes = {(scan.module, qual) for scan in scans.values() for qual in scan.funcs if config.posts_readers.get((scan.rel, qual), ("",))[0] == "human"}
    for caller, targets in analysis.edges.items():
        if any(target in human_nodes and caller != target for target, _fuzzy in targets):
            found["human_callers"].add((analysis.rel(caller), caller[1]))
    for module, scan in scans.items():
        for qual, info in scan.funcs.items():
            key = (scan.rel, qual)
            kinds = {h[0] for h in info.hits}
            if kinds & {"sdk_import", "sdk_client", "sdk_call", "ai_host"}:
                found["primitives"].add(key)
            if "llm_call" in kinds:
                found["consumers"].add(key)
            if "llm_factory" in kinds:
                found["factories"].add(key)
            for name in config.ai_call_sites:
                if (name in info.refs or name in info.strs) and qual.split(".")[-1] != name:
                    found["call_sites"][name].add(key)
            if info.posts_reads:
                found["readers"].add(key)
            for name, _full, _line, flag in info.calls:
                if name in FILTERED_READERS and qual.split(".")[-1] != name:
                    found["filtered_calls"].add((scan.rel, qual, name, "기본" if flag == "absent" else ("켬" if flag is True else ("끔" if flag is False else "식"))))
                    if flag is not True and flag != "absent":
                        found["unfiltered_calls"].add(key)
    return found


def main(argv):
    """다른 작업 트리를 읽는 점검: python tests/ai_flow_scan.py <저장소 루트>… — 위반 목록과 읽은 파일 수를 낸다. 종료 코드: 위반이 있으면 1, 스캔하지 못했으면 2(읽은 파일이 하나도 없거나
    스캔 범위가 하나라도 없다 — 잘못된 경로·빈 폴더가 '위반 0건·종료 0' 으로 초록이 되지 않게 한다, D-198), 모두 깨끗하면 0."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    failed = 0
    for root in argv or [str(Path(__file__).resolve().parent.parent)]:
        sources = read_tree(root)
        missing = [entry for entry in SCAN_ROOTS if not (Path(root) / entry).exists()]
        if not sources or missing:
            print(f"== {root}: 스캔하지 못했다 — 읽은 파일 {len(sources)}개, 없는 스캔 범위 {', '.join(missing) or '없음'}. 저장소 루트를 확인한다(이것은 '위반 0건' 이 아니다)")
            failed = max(failed, 2)
            continue
        found = check(sources)
        print(f"== {root}: 읽은 파일 {len(sources)}개, 규칙 위반 {len(found)}건")
        for violation in found[:60]:
            print(f"   [{violation.rule}] {violation.where}:{violation.line} {violation.message}")
        failed = max(failed, 1 if found else 0)
    return failed


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
