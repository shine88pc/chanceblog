"""AI 흐름 정적 규칙 시험(tests/ai_flow_scan.py) — 'AI 를 부르는 길'과 'Fact 자료가 AI 로 새는 길'을 소스 글자로 못박는다. 네트워크 없이 파일만 읽는다.

1. **지금 트리**(이 저장소의 생성기·pipeline·scripts·인수인계 도구)에서 규칙 위반이 0이고, 등록 목록(AI_PRIMITIVES·LLM_CONSUMERS·LLM_FACTORY_CALLERS·AI_CALL_SITES·POSTS_READERS)이 **코드가 실제로
   하는 일과 양쪽으로 일치**한다(낡은 항목·빠진 항목 모두 빨강). 등록 항목마다 빼 보면 위반이 생긴다(죽은 등록 없음).
2. **빨개짐 증명**: 규칙마다 위반 소스를 시험 안에 심어(합성 변이) 스캐너가 그 규칙으로 잡는지 본다. 변이는 감사 보고서의 M1–M14 에 이 묶음이 더한 것을 합쳐 40개 넘게 있고, 모두 메모리 안의 소스 글자 바꾸기라
   디스크의 파일을 건드리지 않는다(원복할 것이 없다). 변이 점검의 대조군(바뀐 곳 없음)은 위반 0 이다.
3. **사각지대를 '못 잡는다'고 단언한다**: 이름을 조립한 호출·비 Fact 코드의 동적 로드·서브프로세스·경로를 인자로 받는 읽기 도우미·모르는 AI 제공처 주소. 이것들이 잡히게 바뀌면 이 시험을 고치고 docs/AI_FLOW.md 를 같이 고친다.
4. 스캐너 성질: 결정적(두 번 돌려 같은 결과)·경로는 POSIX·유닉스/윈도우 어디서나 같다·파싱 못 하는 파일은 위반.
5. 다른 가지의 시험과 부딪히지 않는다: Fact 경로 시험(test_fact_structure)이 '새 모듈 이름을 부르는 줄'을 정규식으로 찾는다 — 이 묶음의 시험 파일에 그런 줄이 없다.
"""
import contextlib
import dataclasses
import io
import json
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap
import ai_flow_scan as S
from pipeline import provenance

ROOT = _bootstrap.ROOT
REAL = S.read_tree(ROOT)
CFG = S.DEFAULT_CONFIG
ENTRY = ("generator.py", "synthetic_fact_entry")      # 합성 뼈대의 이름(D-198: 2단계가 정할 진짜 진입 함수의 이름과 겹치지 않게 일부러 '합성' 이라고 지었다 — 겹치면 이 시험들의 합성 함수와 진짜 함수가 한 이름이 된다)
FACT_CFG = dataclasses.replace(CFG, fact_entries=frozenset({ENTRY}))
FACTS_NAME = "facts"


def src(*lines):
    return "\n".join(lines) + "\n"


def add(rel, text):
    def patch(sources):
        sources[rel] = text
    return patch


def edit(rel, old, new):
    def patch(sources):
        assert old in sources[rel], f"{rel}: 변이 대상 글자를 찾지 못했다 {old[:60]!r}"
        sources[rel] = sources[rel].replace(old, new, 1)
    return patch


def append(rel, text):
    def patch(sources):
        sources[rel] = sources[rel] + text
    return patch


def both(*patches):
    def patch(sources):
        for item in patches:
            item(sources)
    return patch


# 2단계가 생성기에 만들 Fact 분기의 합성 뼈대 — 한 군데 연결: 조립기만 부르고 AI 를 부르지 않는다(진짜 이름은 2단계가 정한다)
FACT_BRANCH = src(
    "",
    "",
    "def synthetic_fact_entry(records, facts, today, source):",
    "    from pipeline import fact_assembler, recipes",
    "    return fact_assembler.assemble(recipes.RECIPES['R01'], facts, today, records=records, source=source)",
)
DEF_FACT = "def synthetic_fact_entry(records, facts, today, source):\n"


def fire(sources, config=CFG):
    return S.check(sources, config)


def fired(sources, config=CFG):
    return {violation.rule.split()[0] for violation in fire(sources, config)}


def scene(patch=None, fact_branch=False):
    sources = dict(REAL)
    if fact_branch:
        sources["generator.py"] += FACT_BRANCH
    if patch is not None:
        patch(sources)
    return sources, (FACT_CFG if fact_branch else CFG)


# ----------------------------------------------------------------------------
# 합성 변이 표: (번호, 기대 규칙, 설명, 패치, Fact 분기 뼈대를 쓰는가)
# 감사 보고서 8-2 의 M1–M14(M9 는 워크플로 규칙 AF7 이라 이 묶음에 없다)와 이 묶음이 더한 N 시리즈
# ----------------------------------------------------------------------------
CASES = (
    # -- AF0: 읽을 수 없는 파일은 확인하지 못한 것 ------------------------------------------------------------------------------------------------------------
    ("N0a", "AF0", "문법 오류가 있는 새 모듈", add("pipeline/broken.py", "def f(:\n"), False),
    ("N0b", "AF0", "읽을 수 없는 파일(UTF-8 이 아님)", add("pipeline/unreadable.py", None), False),
    # -- AF1: 임포트 단방향 격리 -------------------------------------------------------------------------------------------------------------------------------
    ("M1", "AF1", "Fact 모듈(fact_assembler)이 generator 를 가져온다", edit("pipeline/fact_assembler.py", "import re\n", "import re\nimport generator\n"), False),
    ("M2", "AF1", "Fact 모듈(calc)이 pipeline.llm 을 가져온다(마스킹 도우미를 쓰려고 — 흔한 실수)", edit("pipeline/calc.py", "from pipeline import facts as F\n", "from pipeline.llm import mask\nfrom pipeline import facts as F\n"), False),
    ("M13", "AF1", "새 운영 모듈이 Fact 모듈과 AI 모듈을 모두 가져온다(새 다리)", add("pipeline/bridge2.py", src("from pipeline import fact_assembler", "from pipeline import llm")), False),
    ("N1a", "AF1", "Fact 모듈이 함수 안에서(지연 임포트) AI 모듈 topics 를 가져온다", append("pipeline/calc.py", src("", "", "def _lazy():", "    from pipeline import topics", "    return topics")), False),
    ("N1b", "AF1", "Fact 모듈이 상대 임포트로 llm 을 가져온다", edit("pipeline/recipes.py", "from pipeline import calc as C\n", "from . import llm\nfrom pipeline import calc as C\n"), False),
    ("N1c", "AF1", "AI 모듈(topics)이 Fact 모듈을 가져온다", edit("pipeline/topics.py", "import json\n", "import json\nfrom pipeline import facts as F\n"), False),
    ("N1d", "AF1", "AI 모듈(main_image)이 함수 안에서 Fact 모듈을 가져온다", append("pipeline/main_image.py", src("", "", "def _peek():", "    from pipeline import calc", "    return calc")), False),
    ("N1e", "AF1", "AI 모듈이 상수 글자로 importlib 를 불러 Fact 모듈을 가져온다", both(edit("pipeline/topics.py", "import json\n", "import importlib\nimport json\n"),
          append("pipeline/topics.py", src("", "", "def _peek():", "    return importlib.import_module('pipeline." + FACTS_NAME + "')"))), False),
    ("N1f", "AF1", "새 모듈이 다리(generator)와 Fact 모듈을 함께 가져온다 — 다리는 generator 한 곳뿐", add("pipeline/glue.py", src("import generator", "from pipeline import fact_assembler")), False),
    ("N1g", "AF1", "Fact 모듈(adapters.base)이 AI 모듈(run)을 가져온다", edit("pipeline/adapters/base.py", "import csv\n", "import csv\nfrom pipeline import run\n"), False),
    # -- AF2: AI SDK·AI 제공처 주소는 등록된 함수에만 ---------------------------------------------------------------------------------------------------------------
    ("M3", "AF2", "새 모듈이 google genai 를 가져와 generate_content 를 부른다", add("pipeline/polish.py", src(
        "def polish(text):", "    from google import genai", "    return genai.Client(api_key='x').models.generate_content(model='m', contents=text)")), False),
    ("N2a", "AF2", "새 모듈이 다른 AI SDK(anthropic)를 가져온다", add("pipeline/anth.py", src(
        "def ask(text):", "    import anthropic", "    return anthropic.Anthropic().messages.create(model='m', messages=text)")), False),
    ("N2b", "AF2", "등록 밖 함수가 generate_content 를 변수에 담는다(별칭 참조)", append("generator.py", src("", "", "def _alias(client):", "    ask = client.models.generate_content", "    return ask")), False),
    ("N2c", "AF2", "등록 밖 함수에 AI 제공처로 가는 주소 글자(직접 HTTP 호출 준비)", add("pipeline/rawhttp.py", src(
        "def go():", "    return 'https://generativelanguage.googleapis.com/v1beta/models/x:generateContent'")), False),
    ("N2d", "AF2", "공용 호출 객체 모듈에 등록 밖의 둘째 클라이언트 만들기", append("pipeline/llm.py", src("", "", "def make_second_client(key):", "    from google import genai", "    return genai.Client(api_key=key)")), False),
    # -- AF3: 호출 객체 llm 은 등록된 곳에서만 ---------------------------------------------------------------------------------------------------------------------
    ("M4", "AF3", "새 모듈이 호출 객체 llm(...) 를 부른다(등록 밖)", add("pipeline/summarize.py", src("def summarize(text, llm):", "    raw, _model = llm('요약: ' + text)", "    return raw")), False),
    ("N3a", "AF3", "클래스 메서드가 self.llm(...) 를 부른다", add("pipeline/classy.py", src(
        "class Helper:", "    def __init__(self, llm):", "        self.llm = llm", "    def ask(self, text):", "        return self.llm(text)")), False),
    ("N3b", "AF3", "등록 밖 함수가 build_llm 으로 호출 객체를 만든다", append("pipeline/run.py", src("", "", "def _extra(env, reg):", "    return build_llm(env, reg)")), False),
    ("N3c", "AF3", "호출 객체를 만들어 변수에 담아 부른다", add("pipeline/fac.py", src("def ask(key):", "    call = make_gemini_llm(key, ['m'])", "    return call('x')")), False),
    ("N3d", "AF3", "모듈 맨 위에서 호출 객체를 만든다", add("pipeline/fac2.py", src("CALL = make_gemini_llm('k', ['m'])")), False),
    # -- AF5: AI 입구·프롬프트·검색어 함수의 호출 지점 ---------------------------------------------------------------------------------------------------------------
    ("M7", "AF5", "그림자 실행에 등록 밖의 새 call_gemini_with_fallback 호출 지점", append("pipeline/shadow_run.py", src("", "", "def _evaluate_fact(g, post):", "    return g.call_gemini_with_fallback(post.title)")), False),
    ("N5a", "AF5", "AI 함수를 변수에 담아 부른다(별칭 참조)", append("pipeline/run.py", src("", "", "def _alias():", "    import generator", "    ask = generator.call_gemini_with_fallback", "    return ask('x')")), False),
    ("N5b", "AF5", "등록 밖 함수가 build_post_prompt 를 부른다", append("pipeline/edits/ops.py", src("", "", "def _prompt(g, item):", "    return g.build_post_prompt(item, [])")), False),
    ("N5c", "AF5", "등록 밖 함수가 make_image_queries 를 부른다", append("pipeline/edits/ops.py", src("", "", "def _queries(g, post):", "    return g.make_image_queries(post['title'], '', '')")), False),
    ("N5d", "AF5", "getattr 에 AI 함수 이름을 글자 상수로 넘긴다", append("pipeline/state.py", src("", "", "def _sneaky(module, text):", "    return getattr(module, 'call_gemini_with_fallback')(text)")), False),
    ("M14", "AF5", "operator.attrgetter 로 AI 함수 이름을 꺼낸다(감사 때는 사각지대 — 글자 상수 검사로 이제 잡힌다)", append("pipeline/state.py", src(
        "", "", "def _sneaky2(module, text):", "    import operator", "    return operator.attrgetter('call_gemini_with_fallback')(module)(text)")), False),
    ("N5e", "AF5", "등록 밖 함수가 SDK 호출 한 번(_generate)을 직접 부른다(입구 방벽을 건너뜀)", append("generator.py", src("", "", "def _direct(prompt):", "    return _generate('m', prompt, 0)")), False),
    ("N5f", "AF5", "등록 밖 함수가 get_client() 를 직접 부른다", append("pipeline/run.py", src("", "", "def _client():", "    import generator", "    return generator.get_client()")), False),
    # -- AF6: 표식을 거르지 않는 글 읽기 ----------------------------------------------------------------------------------------------------------------------------
    ("M8", "AF6", "AI 가능 함수 repair 가 표식을 거르지 않는 읽기(for_ai=False)를 부른다", edit("generator.py", "def repair(post, used):\n", "def repair(post, used):\n    _all = load_posts(for_ai=False)\n"), False),
    ("N6a", "AF6", "등록 밖의 새 `_posts` 읽기(Path('_posts').rglob)", add("pipeline/readall.py", src("from pathlib import Path", "", "def read_all():", "    return [p.read_text() for p in Path('_posts').rglob('*.md')]")), False),
    ("N6b", "AF6", "경로를 변수에 담아 읽는다(folder = root / '_posts')", add("pipeline/readvar.py", src("def read_all(root):", "    folder = root / '_posts'", "    return sorted(folder.glob('*.md'))")), False),
    ("N6c", "AF6", "POSTS_DIR.iterdir() 로 읽는다", add("pipeline/readdir.py", src("POSTS_DIR = None", "", "def names():", "    return [p.name for p in POSTS_DIR.iterdir()]")), False),
    ("N6d", "AF6", "os.walk('_posts') 로 읽는다", add("pipeline/readwalk.py", src("import os", "", "def names():", "    return [n for _r, _d, files in os.walk('_posts') for n in files]")), False),
    ("N6e", "AF6", "새 글 쓰기가 existing_titles 의 for_ai 를 끈다", edit("generator.py", "titles = existing_titles(history, posts, for_ai=True)", "titles = existing_titles(history, posts, for_ai=False)"), False),
    ("N6f", "AF6", "Blogger 러너가 other_blog_titles 의 for_ai 를 끈다", edit("pipeline/run.py", 'blog["key"])\n    if override:', 'blog["key"], for_ai=False)\n    if override:'), False),
    ("N6g", "AF6", "Blogger 러너가 entry_titles 의 for_ai 를 끈다", edit("pipeline/run.py", "recent_titles = entry_titles(history[-100:])", "recent_titles = entry_titles(history[-100:], for_ai=False)"), False),
    ("N6h", "AF6", "for_ai 를 식(변수)으로 넘긴다 — 켜졌는지 알 수 없다", append("generator.py", src(
        "", "", "def _flag_read(flag):", "    posts = load_posts(for_ai=flag)", "    return make_image_queries(posts[0]['title'], '', '')")), False),
    ("N6i", "AF6", "AI 가능 함수가 사람용 읽기(load_post_index)를 부른다", append("pipeline/edits/ops.py", src(
        "", "", "def _lookup(root, llm):", "    from pipeline.edits import targets", "    index = targets.load_post_index(root)", "    return image_queries('x', index[0]['title'], '', llm)")), False),
    ("N6j", "AF6", "Fact 분기가 도우미를 거쳐 표식을 거르지 않는 읽기를 부른다", both(edit("generator.py", DEF_FACT, DEF_FACT + "    _fact_read()\n"), append("generator.py", src("", "", "def _fact_read():", "    return load_posts(for_ai=False)"))), True),
    # -- AF4: Fact 분기에서 닿는 곳에 AI 0 ---------------------------------------------------------------------------------------------------------------------------
    ("M5", "AF4", "Fact 분기가 call_gemini_with_fallback 을 직접 부른다", edit("generator.py", DEF_FACT, DEF_FACT + "    call_gemini_with_fallback('다듬어: ' + str(facts))\n"), True),
    ("M6", "AF4", "Fact 분기가 도우미 → make_image_queries 로 추이적으로 AI 를 부른다", both(edit("generator.py", DEF_FACT, DEF_FACT + "    _decorate(facts)\n"),
          append("generator.py", src("", "", "def _decorate(x):", "    return make_image_queries(str(x), '', '')"))), True),
    ("M11", "AF4", "Fact 분기가 AI 함수를 변수(ask)에 담아 부른다", edit("generator.py", DEF_FACT, DEF_FACT + "    ask = call_gemini_with_fallback\n    ask('x')\n"), True),
    ("N4a", "AF4", "Fact 분기가 AI 함수를 콜백으로 넘긴다", edit("generator.py", DEF_FACT, DEF_FACT + "    sorted([], key=call_gemini_with_fallback)\n"), True),
    ("N4b", "AF4", "Fact 분기가 get_client() 를 부른다", edit("generator.py", DEF_FACT, DEF_FACT + "    get_client()\n"), True),
    ("N4c", "AF4", "Fact 분기가 AI 이름을 글자 상수로 꺼낸다(getattr)", edit("generator.py", DEF_FACT, DEF_FACT + "    getattr(sys.modules[__name__], 'call_gemini_with_fallback')('x')\n"), True),
    # -- AF8: 동적 실행·이름 조립 -------------------------------------------------------------------------------------------------------------------------------------
    ("M10", "AF8", "Fact 분기가 globals() 로 이름을 조립해 AI 함수를 부른다", edit("generator.py", DEF_FACT, DEF_FACT + "    globals()['call_gemini' + '_with_fallback']('x')\n"), True),
    ("M12", "AF8", "Fact 모듈(recipes)이 서브프로세스로 다른 프로그램을 실행한다", both(edit("pipeline/recipes.py", "from typing import Any, Callable\n", "import subprocess\nfrom typing import Any, Callable\n"),
          append("pipeline/recipes.py", src("", "", "def _spawn():", "    subprocess.run(['python', 'x.py'])"))), False),
    ("N8a", "AF8", "Fact 분기가 importlib 로 비상수 이름의 모듈을 불러온다", edit("generator.py", DEF_FACT, DEF_FACT + "    import importlib\n    importlib.import_module(source)\n"), True),
    ("N8b", "AF8", "Fact 모듈(calc)에 exec", append("pipeline/calc.py", src("", "", "def _run(code):", "    exec(code)")), False),
    ("N8c", "AF8", "Fact 모듈(fact_topics)에 eval", append("pipeline/fact_topics.py", src("", "", "def _run(code):", "    return eval(code)")), False),
    ("N8d", "AF8", "Fact 분기가 이름이 동적인 getattr 로 모듈 함수를 꺼낸다", edit("generator.py", DEF_FACT, DEF_FACT + "    getattr(recipes, source)\n"), True),
    ("N8e", "AF8", "Fact 모듈(adapters.mock_stats)이 호출 객체 llm(...) 를 부른다", append("pipeline/adapters/mock_stats.py", src("", "", "def _ai(llm):", "    return llm('x')")), False),
    # -- 독립 검증 지적 반영(D-196–D-198): 위치 인자·`**옵션`·중립 도우미·별칭 임포트·위험 모듈 임포트·TYPE_CHECKING 의 else ---------------------------------------------------------
    ("N6k", "AF6", "for_ai 를 위치 인자로 넘긴다 — load_posts(True)", edit("generator.py", "def fix_images(keyword=None):\n    posts = load_posts(for_ai=True)", "def fix_images(keyword=None):\n    posts = load_posts(True)"), False),
    ("N6l", "AF6", "for_ai 를 `**옵션` 으로 넘긴다", edit("generator.py", "def fix_images(keyword=None):\n    posts = load_posts(for_ai=True)", "def fix_images(keyword=None):\n    posts = load_posts(**{'for_ai': False})"), False),
    ("N6m", "AF6", "중립 도우미 한 단계 — AI 와 상관없는 새 함수가 for_ai=False 로 읽는다(UNFILTERED_SITES 등록이 필요하다)", add("pipeline/neutral_reader.py", src(
        "import generator", "", "def all_titles():", "    return [p['title'] for p in generator.load_posts(for_ai=False)]")), False),
    ("N6n", "AF6", "모듈 맨 위에서 for_ai=False 로 읽어 캐시해 둔다", add("pipeline/neutral_cache.py", src("import generator", "", "ALL = generator.load_posts(for_ai=False)")), False),
    ("N6o", "AF6", "사람용 읽기(load_post_index)를 부르는 새 도우미(HUMAN_CALLERS 등록이 필요하다)", add("pipeline/neutral_human.py", src(
        "from pipeline.edits import targets", "", "def index(root):", "    return targets.load_post_index(root)")), False),
    ("N5g", "AF5", "별칭 임포트 — from generator import call_gemini_with_fallback as ask", add("pipeline/alias_call.py", src(
        "from generator import call_gemini_with_fallback as ask", "", "def go(text):", "    return ask(text)")), False),
    ("N5h", "AF5", "함수 안의 별칭 임포트 — build_post_prompt as bp", add("pipeline/alias_call2.py", src(
        "def go(text):", "    from generator import build_post_prompt as bp", "    return bp(text, [])")), False),
    ("N8f", "AF8", "Fact 모듈(calc)이 subprocess 를 가져온다(호출하지 않아도 가져오는 것이 위반)", edit("pipeline/calc.py", "from decimal import Decimal\n", "import subprocess\nfrom decimal import Decimal\n"), False),
    ("N8g", "AF8", "Fact 모듈(fact_topics)이 importlib 를 가져온다", edit("pipeline/fact_topics.py", "import re\n", "import importlib\nimport re\n"), False),
    ("N8h", "AF8", "Fact 모듈(adapters.base)이 socket 을 가져온다", edit("pipeline/adapters/base.py", "import csv\n", "import csv\nimport socket\n"), False),
    ("N8i", "AF8", "Fact 모듈(recipes)이 from subprocess import run 으로 가져온다", edit("pipeline/recipes.py", "from typing import Any, Callable\n", "from subprocess import run\nfrom typing import Any, Callable\n"), False),
    ("N8j", "AF8", "Fact 분기가 함수 안에서 subprocess 를 가져온다", edit("generator.py", DEF_FACT, DEF_FACT + "    import subprocess\n"), True),
    ("N1h", "AF1", "Fact 모듈이 `if TYPE_CHECKING: … else:` 의 else 가지에서 generator 를 가져온다(else 는 실행된다)", edit(
        "pipeline/calc.py", "from pipeline import facts as F\n", "from typing import TYPE_CHECKING\nfrom pipeline import facts as F\nif TYPE_CHECKING:\n    pass\nelse:\n    import generator\n"), False),
    ("N6p", "AF6", "다른 모듈의 상수를 점 이름으로 불러 `_posts` 를 훑는다(generator.POSTS_DIR.glob)", add("pipeline/readattr.py", src(
        "import generator", "", "def names():", "    return [p.name for p in generator.POSTS_DIR.glob('*.md')]")), False),
)

# 못 잡는 것 — (번호, 설명, 패치, Fact 분기를 쓰는가). 어떤 규칙도 울리지 않아야 한다(울리게 바뀌면 이 표와 docs/AI_FLOW.md 의 사각지대 표를 같이 고친다)
BLIND_SPOTS = (
    ("B1", "비 Fact 코드에서 이름을 조립해 AI 함수를 부른다(globals()['call_gemini' + '_with_fallback'])", add("pipeline/extra.py", src(
        "def go(p):", "    return globals()['call_gemini' + '_with_fallback'](p)")), False),
    ("B2", "비 Fact 코드가 importlib 로 비상수 이름의 모듈을 불러 부른다", add("pipeline/extra2.py", src(
        "import importlib", "", "def go(name, p):", "    return getattr(importlib.import_module(name), 'run')(p)")), False),
    ("B3", "비 Fact 코드가 서브프로세스로 다른 파이썬 파일을 실행한다", add("pipeline/extra3.py", src("import subprocess", "", "def go():", "    return subprocess.run(['python', 'other.py'])")), False),
    ("B4", "경로를 인자로 받는 일반 읽기 도우미를 거쳐 `_posts` 를 읽는다", add("pipeline/extra4.py", src(
        "def list_md(base):", "    return sorted(base.rglob('*.md'))", "", "def posts():", "    from pathlib import Path", "    return list_md(Path('_posts'))")), False),
    ("B5", "목록에 없는 AI 제공처 주소", add("pipeline/extra5.py", src("def go():", "    return 'https://api.example-llm.invalid/v1/chat/completions'")), False),
    ("B6", "AI 키를 환경변수에서 읽는다(워크플로 키 식은 2단계의 AF7 이 맡는다)", add("pipeline/extra6.py", src("import os", "", "def key():", "    return os.environ.get('GEMINI_API_KEY')")), False),
    ("B7", "`_posts` 밖의 파생 목록(`history.json`·`pages.json`)을 직접 읽어 제목을 AI 입력으로 넘기는 새 함수 — AF6 은 `_posts` 읽기만 등록한다", add("pipeline/extra7.py", src(
        "import json", "", "def titles():", "    return [item.get('title') for item in json.load(open('history.json', encoding='utf-8'))]")), False),
    ("B8", "AI 를 부르는 코드를 감싼 `except Exception` 이 방벽 예외(AiInputForbidden)를 삼키는 새 코드 — 재던지기 줄(여기서는 ask_queries 의 `except ai_guard.AiInputForbidden`)을 바꿔도 규칙은 울리지 않는다",
     edit("pipeline/main_image.py", "    except ai_guard.AiInputForbidden:\n", "    except KeyError:\n"), False),
    ("B9", "호출 객체를 `llm` 이 아닌 이름으로 받아 부르거나 별칭 임포트(`make_gemini_llm as mk`)로 만들어 부른다 — AF3 은 이름 글자로 본다", add("pipeline/extra9.py", src(
        "from pipeline.llm import make_gemini_llm as mk", "", "def summarize(text, ask):", "    return ask('요약: ' + text)", "", "def build(key):", "    return mk(key, ['m'])")), False),
    ("B10", "AI 이름과 같은 이름의 새 함수가 진짜 함수를 감싸 부른다 — 정의 자신 안의 참조는 새 호출 지점으로 세지 않는다", add("pipeline/extra10.py", src(
        "def call_gemini_with_fallback(prompt):", "    import generator", "    return generator.call_gemini_with_fallback(prompt)")), False),
    ("B11", "AF2 의 SDK 목록 밖: 목록에 없는 패키지 이름·`chats.create(...).send_message`", add("pipeline/extra11.py", src(
        "from langchain_google_genai import ChatGoogleGenerativeAI", "", "def go(client, text):", "    return client.chats.create(model='m').send_message(text)")), False),
    ("B12", "Fact 모듈 안의 이름 조립(`globals()[이름]`)·`os.execv` — Fact 분기에서 닿는 함수에는 이름 조립 규칙이 있지만 Fact 모듈 자체에는 없다(정당한 getattr 쓰임이 있어 세지 않는다)", append("pipeline/calc.py", src(
        "", "", "def _lookup(name):", "    import os", "    os.execv('python', ['python'])", "    return globals()[name]")), False),
    ("B13", "읽기 함수 이름을 변수로 옮겨 for_ai 를 끈다(`reader = generator.load_posts; reader(for_ai=False)`) — 규칙은 호출 이름으로 본다", add("pipeline/extra13.py", src(
        "import generator", "", "def pull():", "    reader = generator.load_posts", "    return reader(for_ai=False)")), False),
    ("B14", "비 Fact 코드가 코드 글자를 `exec` 로 돌린다 — 글자 속 이름은 이름 글자 상수가 아니다", add("pipeline/extra14.py", src(
        "def go(x):", "    exec('from generator import call_gemini_with_fallback as f; f(x)')")), False),
    ("B15", "`_posts` 읽기 탐지가 놓치는 모양: 함수 밖에 둔 다른 이름의 상수(`POST_FOLDER = '_posts'` 뒤 `os.listdir(POST_FOLDER)`)·상수 목록을 돌며 훑기·매개변수 기본값의 `_posts`·글 하나를 경로로 바로 읽기·이어붙인 경로", add("pipeline/extra15.py", src(
        "import os", "", "POST_FOLDER = '_posts'", "", "def names():", "    return os.listdir(POST_FOLDER)")), False),
)


CASES_BY_ID = {case[0]: case[3] for case in CASES}


class RealTreeTest(unittest.TestCase):
    def test_the_real_tree_has_no_violations(self):
        found = fire(REAL)
        self.assertEqual(found, [], "\n".join(f"[{v.rule}] {v.where}:{v.line} {v.message}" for v in found[:20]))

    def test_the_fact_modules_are_in_this_tree_so_the_import_rule_is_live(self):
        analysis = S.Analysis(REAL)
        fact = {m for m in analysis.scans if m in CFG.fact_modules or any(m.startswith(prefix) for prefix in CFG.fact_prefixes)}
        self.assertEqual(len(fact), len(S.FACT_MODULE_NAMES), sorted(fact))

    def test_every_python_file_outside_tests_is_scanned_or_explicitly_excluded(self):
        loose = []
        for path in sorted(ROOT.rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if any(part in S.SKIP_DIRS for part in rel.split("/")[:-1]):
                continue
            if any(rel == root or rel.startswith(root + "/") for root in S.SCAN_ROOTS) or any(rel.startswith(prefix + "/") for prefix, _why in S.SCAN_EXCLUDED):
                continue
            loose.append(rel)
        self.assertEqual(loose, [], "스캔 범위 밖의 파이썬 파일 — SCAN_ROOTS 에 올리거나 SCAN_EXCLUDED 에 이유와 함께 올린다")
        self.assertGreater(len(REAL), 60)
        for rel in REAL:
            self.assertNotIn("\\", rel)

    def test_the_scanned_files_are_all_readable(self):
        self.assertEqual([rel for rel, text in REAL.items() if text is None], [])


class RegistryMatchesCodeTest(unittest.TestCase):
    """등록 목록은 지금 코드가 실제로 하는 일과 양쪽으로 같아야 한다: 코드에 있는데 등록이 없으면 위반(AF), 등록은 있는데 코드에 없으면(낡은 항목) 여기서 빨강."""

    @classmethod
    def setUpClass(cls):
        cls.found = S.inventory(REAL)

    def test_ai_primitives(self):
        self.assertEqual(self.found["primitives"], set(CFG.ai_primitives))

    def test_llm_consumers_and_factory_callers(self):
        self.assertEqual(self.found["consumers"], set(CFG.llm_consumers))
        self.assertEqual(self.found["factories"], set(CFG.llm_factory_callers))

    def test_ai_call_sites(self):
        for name, sites in CFG.ai_call_sites.items():
            with self.subTest(name=name):
                self.assertEqual(self.found["call_sites"][name], set(sites))

    def test_posts_readers(self):
        self.assertEqual(self.found["readers"], set(CFG.posts_readers))
        self.assertEqual({kind for kind, _why in CFG.posts_readers.values()}, {"filtered", "keys_only", "human"})

    def test_unfiltered_sites_and_human_callers_match_the_code_both_ways(self):
        """D-197: for_ai 를 켜지 않은 채 거르는 읽기를 부르는 함수 전부와 사람용 읽기를 부르는 함수 전부가 등록과 양쪽으로 같다(낡은 등록도 빠진 등록도 빨강)."""
        self.assertEqual(self.found["unfiltered_calls"], set(CFG.unfiltered_sites))
        self.assertEqual(self.found["human_callers"], set(CFG.human_callers))

    def test_every_registered_entry_has_a_reason(self):
        for table in (CFG.ai_primitives, CFG.llm_consumers, CFG.llm_factory_callers, CFG.unfiltered_sites, CFG.human_callers, *CFG.ai_call_sites.values()):
            for key, reason in table.items():
                self.assertTrue(isinstance(reason, str) and len(reason) >= 10, key)
        for key, (kind, reason) in CFG.posts_readers.items():
            self.assertTrue(len(reason) >= 10, key)

    def test_every_registered_site_names_a_file_that_exists_and_a_function_that_exists(self):
        analysis = S.Analysis(REAL)
        existing = {(scan.rel, qual) for scan in analysis.scans.values() for qual in scan.funcs}
        for table in (CFG.ai_primitives, CFG.llm_consumers, CFG.llm_factory_callers, *CFG.ai_call_sites.values(), CFG.posts_readers, CFG.unfiltered_sites, CFG.human_callers):
            for key in table:
                self.assertIn(key, existing)

    def test_the_gate_branchs_shadow_run_is_a_registered_call_site(self):
        self.assertIn(("pipeline/shadow_run.py", "_evaluate"), CFG.ai_call_sites["call_gemini_with_fallback"])
        self.assertIn(("pipeline/shadow_run.py", "_evaluate"), CFG.ai_call_sites["build_post_prompt"])

    def test_removing_any_registered_entry_makes_a_rule_fire(self):
        """등록은 일을 한다: 항목을 하나씩 빼면 그 항목이 막던 위반이 생긴다(죽은 등록이 없다)."""
        cases = [("ai_primitives", key, "AF2") for key in CFG.ai_primitives] + [("llm_consumers", key, "AF3") for key in CFG.llm_consumers] + \
                [("llm_factory_callers", key, "AF3") for key in CFG.llm_factory_callers] + [("posts_readers", key, "AF6") for key in CFG.posts_readers] + \
                [("unfiltered_sites", key, "AF6") for key in CFG.unfiltered_sites] + [("human_callers", key, "AF6") for key in CFG.human_callers]
        for field, key, rule in cases:
            with self.subTest(field=field, key=key):
                table = dict(getattr(CFG, field))
                del table[key]
                self.assertIn(rule, fired(REAL, dataclasses.replace(CFG, **{field: table})))
        for name, sites in CFG.ai_call_sites.items():
            for key in sites:
                with self.subTest(call=name, key=key):
                    trimmed = {n: dict(s) for n, s in CFG.ai_call_sites.items()}
                    del trimmed[name][key]
                    self.assertIn("AF5", fired(REAL, dataclasses.replace(CFG, ai_call_sites=trimmed)))


class BaselineTest(unittest.TestCase):
    def test_the_baseline_with_the_synthetic_fact_branch_has_no_violations(self):
        sources, config = scene(fact_branch=True)
        self.assertEqual(fire(sources, config), [])

    def test_the_bridge_may_import_fact_modules_but_a_plain_fact_consumer_is_not_a_bridge(self):
        sources, config = scene(fact_branch=True)
        self.assertIn("fact_assembler", sources["generator.py"])
        self.assertEqual(fired(sources, config), set())
        sources["pipeline/fact_report.py"] = src("from pipeline import facts as F", "", "def show(x):", "    return F.render(x)")      # Fact 모듈만 가져오는 새 모듈은 다리가 아니다
        self.assertEqual(fired(sources, config), set())


class MutantTest(unittest.TestCase):
    def test_every_mutant_makes_its_rule_fire(self):
        self.assertGreaterEqual(len(CASES), 40)
        caught = {}
        for ident, rule, description, patch, fact_branch in CASES:
            with self.subTest(mutant=ident, rule=rule):
                sources, config = scene(patch, fact_branch)
                result = fired(sources, config)
                caught[ident] = result
                self.assertIn(rule, result, f"{ident} {description}: 기대 {rule}, 발동 {sorted(result)}")
        self.assertEqual(len({case[0] for case in CASES}), len(CASES), "변이 번호가 겹친다")

    def test_every_rule_has_at_least_two_mutants(self):
        count = {}
        for _ident, rule, *_rest in CASES:
            count[rule] = count.get(rule, 0) + 1
        for rule in ("AF0", "AF1", "AF2", "AF3", "AF4", "AF5", "AF6", "AF8"):
            self.assertGreaterEqual(count.get(rule, 0), 2, rule)

    def test_messages_say_what_where_and_what_to_do(self):
        for ident in ("M3", "M4", "M7", "M8", "N6a", "M1", "M5", "M10"):
            ident_rule = next(case for case in CASES if case[0] == ident)
            sources, config = scene(ident_rule[3], ident_rule[4])
            found = [v for v in fire(sources, config) if v.rule.startswith(ident_rule[1])]
            self.assertTrue(found, ident)
            for violation in found:
                self.assertRegex(violation.where, r"^[\w./가-힣-]+\.py$")
                self.assertGreaterEqual(violation.line, 0)
                self.assertGreater(len(violation.message), 20)
        sources, _config = scene(CASES_BY_ID["M3"])
        text = "\n".join(v.message for v in fire(sources))
        self.assertIn("AI_PRIMITIVES", text)


class BlindSpotTest(unittest.TestCase):
    def test_the_known_blind_spots_are_not_caught(self):
        """못 잡는 것을 '못 잡는다'고 단언한다 — 정적 규칙을 믿고 런타임 방벽·AI 키 미전달을 줄이면 안 되는 이유(docs/AI_FLOW.md 사각지대 표)."""
        for ident, description, patch, fact_branch in BLIND_SPOTS:
            with self.subTest(blind=ident):
                sources, config = scene(patch, fact_branch)
                self.assertEqual(fired(sources, config), set(), f"{ident} {description}: 이제 잡힌다 — 이 표와 docs/AI_FLOW.md 의 사각지대 표를 고친다")

    def test_the_audit_blind_spot_m14_is_now_caught_by_the_string_constant_check(self):
        sources, config = scene(CASES_BY_ID["M14"])
        self.assertIn("AF5", fired(sources, config))

    def test_a_name_inside_a_docstring_or_a_comment_is_not_a_reference(self):
        sources, config = scene(add("pipeline/doc_only.py", src(
            "def explain():", '    """call_gemini_with_fallback 와 https://generativelanguage.googleapis.com/ 를 설명하는 글이다."""', "    # call_gemini_with_fallback 는 부르지 않는다", "    return 1")))
        self.assertEqual(fire(sources, config), [])

    def test_a_bare_host_name_in_a_data_table_is_not_a_call(self):
        sources, config = scene(add("pipeline/allow_table.py", src("ALLOW = ('generativelanguage.googleapis.com', 'api.openai.com')")))
        self.assertEqual(fire(sources, config), [])


class ScannerPropertiesTest(unittest.TestCase):
    def test_the_output_is_deterministic_and_sorted(self):
        sources, config = scene(CASES_BY_ID["M3"])
        first, second = fire(sources, config), fire(sources, config)
        self.assertEqual(first, second)
        self.assertEqual(first, sorted(first, key=lambda v: (v.rule, v.where, v.line, v.message)))

    def test_a_pure_function_does_not_touch_the_input(self):
        before = dict(REAL)
        fire(REAL)
        self.assertEqual(REAL, before)

    def test_scanning_the_real_tree_is_fast_enough(self):
        start = time.perf_counter()
        S.check(S.read_tree(ROOT))
        self.assertLess(time.perf_counter() - start, 60)

    def test_an_unparseable_file_is_a_violation_not_a_crash(self):
        sources, config = scene(add("pipeline/odd.py", "x = (1 +\n"))
        self.assertIn("AF0", fired(sources, config))

    def test_a_recursion_error_while_reading_a_source_is_a_violation_not_a_crash(self):
        """파이썬 판·운영체제마다 깊이 한계가 달라 같은 소스가 어떤 판에서는 읽히고 어떤 판에서는 RecursionError 가 난다 — 읽지 못하면 위반으로 센다(알 수 없으면 막는다). 한계에 기대지 않게 오류를 흉내 낸다."""
        for error in (RecursionError("simulated"), MemoryError(), SystemError("simulated"), ValueError("simulated")):
            name = type(error).__name__
            sources, config = scene(add("pipeline/deep_sim.py", f"x = 'read only under the simulated {name}'\n"))      # 글이 오류마다 달라야 스캔 캐시에 걸리지 않는다
            with self.subTest(error=name), mock.patch.object(S.ast, "parse", side_effect=error):
                hits = [v for v in fire(sources, config) if v.where == "pipeline/deep_sim.py"]
                self.assertEqual([v.rule for v in hits], ["AF0 PARSE"], hits)
                self.assertIn(f"구문을 분석하지 못함({name})", hits[0].message)

    def test_a_really_deep_source_never_crashes_the_scanner(self):
        """읽히면 위반 없음, 못 읽으면 AF0 — 어느 판에서든 예외로 터지지 않는다(한계 값은 판마다 다르므로 어느 쪽인지는 단언하지 않는다)."""
        deep = "x = " + " + ".join(["1"] * 1500) + "\n"
        sources, config = scene(add("pipeline/deep_real.py", deep))
        self.assertLessEqual(fired(sources, config), {"AF0"})

    def run_cli(self, *argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = S.main(list(argv))
        return code, buffer.getvalue()

    def test_the_command_line_fails_closed_on_a_wrong_path_an_empty_folder_or_a_partial_tree(self):
        """D-198: 잘못된 경로·빈 폴더·스캔 범위가 일부 없는 폴더가 '위반 0건·종료 0' 으로 초록이 되지 않는다(종료 2 와 고정 문장). 진짜 저장소는 읽은 파일 수와 함께 종료 0."""
        with tempfile.TemporaryDirectory() as tmp:
            partial = Path(tmp) / "partial"
            partial.mkdir()
            (partial / "generator.py").write_text("x = 1\n", encoding="utf-8")
            for target in (tmp, str(Path(tmp) / "missing"), str(partial), str(ROOT / "pipeline")):
                with self.subTest(target=Path(target).name):
                    code, out = self.run_cli(target)
                    self.assertEqual(code, 2, out)
                    self.assertIn("스캔하지 못했다", out)
                    self.assertNotIn("규칙 위반 0건", out)
        code, out = self.run_cli(str(ROOT))
        self.assertEqual(code, 0, out)
        found = re.search(r"읽은 파일 (\d+)개, 규칙 위반 0건", out)
        self.assertIsNotNone(found, out)
        self.assertGreater(int(found.group(1)), 60)

    def test_a_utf8_bom_in_a_source_file_is_not_a_syntax_error(self):
        """D-198: 윈도우 도구가 붙이는 BOM 은 파이썬도 눈감아 준다 — 합법 소스가 AF0 '문법 오류' 로 빨갛게 되지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.py").write_bytes(bytes([0xEF, 0xBB, 0xBF]) + "value = 1\n".encode("utf-8"))
            self.assertEqual(S.read_tree(tmp, scan_roots=("x.py",)), {"x.py": "value = 1\n"})
        self.assertEqual(S.check({"x.py": "value = 1\n"}), [])

    def test_a_violation_in_a_module_level_table_is_reported_at_its_own_line(self):
        """D-198: 호출이 아닌 참조(데이터 표에 적힌 AI 이름)의 위반이 줄 1 이 아니라 그 이름이 적힌 줄로 보고된다."""
        sources, config = scene(add("pipeline/tbl.py", src("# 머리말", "", "NAMES = {", "    'get_client': 1,", "}")))
        found = [v for v in fire(sources, config) if v.where == "pipeline/tbl.py"]
        self.assertEqual([(v.rule.split()[0], v.line) for v in found], [("AF5", 4)])

    def test_quoted_lines_stay_aligned_when_a_comment_holds_a_form_feed_or_a_line_separator(self):
        """D-198: 폼피드·U+2028 이 든 주석이 있어도 위반 메시지가 인용하는 줄이 파서의 줄 번호와 어긋나지 않는다(splitlines 는 그 글자에서도 줄을 나눈다)."""
        text = "def f(client):\n    a = 1  # \x0c\n    b = 2  # " + chr(0x2028) + "\n    return client.models.generate_content(model='m', contents='x')\n"
        sources, config = scene(add("pipeline/ff.py", text))
        found = [v for v in fire(sources, config) if v.where == "pipeline/ff.py"]
        self.assertTrue(found)
        for violation in found:
            self.assertEqual(violation.line, 4)
            self.assertIn("return client.models", violation.message)

    def test_every_risky_import_root_is_caught_in_a_fact_module_and_harmless_ones_are_not(self):
        for root in sorted(S.RISKY_IMPORT_ROOTS):
            with self.subTest(root=root):
                sources, config = scene(edit("pipeline/calc.py", "from decimal import Decimal\n", f"import {root}\nfrom decimal import Decimal\n"))
                self.assertIn("AF8", fired(sources, config))
        sources, config = scene(edit("pipeline/calc.py", "from decimal import Decimal\n", "import json\nimport re\nfrom decimal import Decimal\n"))
        self.assertEqual(fired(sources, config), set())

    def test_the_rule_names_are_the_documented_ones(self):
        self.assertEqual(S.RULE_NAMES, {"AF0": "PARSE", "AF1": "F-IMPORTS", "AF2": "AI-PRIMITIVES", "AF3": "LLM-CONSUMERS", "AF4": "FACT-NO-AI", "AF5": "AI-CALL-SITES",
                                        "AF6": "POSTS-FOR-AI", "AF8": "NO-DYNAMIC"})


class PromptFilesTest(unittest.TestCase):
    """R13: AI 입력의 바탕인 프롬프트 파일(레지스트리 blogs.json 의 prompt 와 .github/editorial 아래 글)에는 출처 표식 줄이 없다 —
    표식 글·Fact 자료를 프롬프트 파일로 옮겨 적는 길을 막는다(그 파일들은 사람이 고치는 정적 글이고 AI 입력으로 그대로 들어간다)."""
    MARKER_LINE = re.compile(r"(?im)^[ \t]*(?:[-?][ \t]+)*[\"']?provenance[\"']?[ \t]*:")

    def registered_prompts(self):
        found = []

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "prompt" and isinstance(value, str):
                        found.append(value)
                    else:
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
        walk(json.loads((ROOT / "pipeline" / "blogs.json").read_text(encoding="utf-8")))
        return found

    def test_every_registered_prompt_file_exists_under_the_editorial_folder(self):
        prompts = self.registered_prompts()
        self.assertGreaterEqual(len(prompts), 4, prompts)
        for rel in prompts:
            with self.subTest(rel):
                self.assertTrue(rel.startswith(".github/editorial/"), rel)
                self.assertTrue((ROOT / rel).is_file(), rel)

    def test_no_prompt_or_editorial_file_carries_a_provenance_marker(self):
        files = [path for path in sorted((ROOT / ".github" / "editorial").glob("*")) if path.suffix.lower() in (".md", ".yml")]
        self.assertGreaterEqual(len(files), 6, files)
        for path in files:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path.name):
                self.assertIsNone(self.MARKER_LINE.search(text), "프롬프트·편집 지침 파일에 출처 표식 줄이 있다 — 표식은 글 머리말과 이력에만 둔다")
                self.assertIn(provenance.mark_of_text(text), (provenance.MARK_NONE, provenance.MARK_NO_FRONT_MATTER))

    def test_the_marker_pattern_catches_the_forms_it_is_meant_to_catch(self):
        for text in ('provenance: "facts"\n', "  Provenance : facts\n", "- provenance: facts\n", '"provenance": facts\n', "title: x\r\nPROVENANCE: other\r\n"):
            with self.subTest(text=text):
                self.assertTrue(self.MARKER_LINE.search(text))
        for text in ("출처 provenance 는 머리말 키다\n", "provenance_note: x\n", "# provenance: facts 를 설명하는 줄이 아니다\n"):
            with self.subTest(text=text):
                self.assertIsNone(self.MARKER_LINE.search(text))


class OtherLanesSafetyTest(unittest.TestCase):
    """이 묶음의 시험 파일이 Fact 경로 시험(test_fact_structure.NoConnectionTest)의 정규식에 걸리지 않는다 — 그 시험은 다른 시험이 새 모듈 이름을 임포트·문자열로 부르는 줄을 찾아 빨갛게 한다.
    (그 시험은 Fact 경로가 병합된 트리에 있고, 이 묶음은 그 트리 위에 얹힌다 — 모듈 이름은 시험 안에서 런타임에 조립한다.)"""

    NAMES = r"(?:facts|calc|fact_topics|recipes|fact_assembler|adapters)"
    PATTERN = re.compile(rf"^\s*(?:from|import)\s+pipeline(?:\.{NAMES}\b|\s+import\s+[^\n#]*\b{NAMES}\b)"
                         rf"|^\s*(?:from|import)\s+{NAMES}\b|-m\s+pipeline\.{NAMES}\b|[\"']pipeline\.{NAMES}[\"']", re.M)
    MINE = ("tests/ai_flow_scan.py", "tests/ai_flow_helpers.py", "tests/test_ai_flow.py", "tests/test_ai_flow_consumers.py", "tests/test_ai_flow_docs.py", "tests/test_ai_guard.py",
            "tests/test_provenance.py")

    def test_none_of_my_test_files_name_the_fact_modules_the_way_the_connection_test_looks_for(self):
        checked = 0
        for rel in self.MINE:
            path = ROOT / rel
            if not path.exists():
                continue
            checked += 1
            self.assertIsNone(self.PATTERN.search(path.read_text(encoding="utf-8")), rel)
        self.assertGreaterEqual(checked, 5)

    def test_my_production_modules_do_not_import_the_fact_modules_either(self):
        for rel in ("pipeline/provenance.py", "pipeline/ai_guard.py"):
            self.assertIsNone(self.PATTERN.search((ROOT / rel).read_text(encoding="utf-8")), rel)

    def test_the_pattern_itself_would_catch_what_it_is_meant_to_catch(self):
        samples = ("from pipeline import " + FACTS_NAME, "import pipeline." + "calc", "  from pipeline import recipes as R", "x = 'pipeline." + FACTS_NAME + "'", "python -m pipeline." + "fact_assembler")
        for line in samples:
            self.assertIsNotNone(self.PATTERN.search(line), line)


if __name__ == "__main__":
    unittest.main()
