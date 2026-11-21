"""F072 — Chance 엔진(generator.py)의 Unsplash 키 읽기 정리(확인 015 의 AP6, 결함 D-370, 변경 등급 T3 — 시크릿 처리).

환경 변수 UNSPLASH_ACCESS_KEY 는 generator 를 가져올 때(import) 한 번 읽힌다. 예전에는 정리 없이 읽어서, 시크릿 끝에 줄바꿈이 하나 붙거나(붙여 넣을 때 흔하다) 폭 없는 공백이 섞이면
요청 머리글을 만드는 순간 오류가 났다. 줄바꿈이 낀 쪽은 그 오류 문구에 키 글자가 그대로 실렸고(`Invalid header value b'Client-ID <키>…'`) generator 가 그 문구를 로그에 찍었다.
이제 Blogger·알림이 쓰는 같은 함수(pipeline.console.clean_secret)로 읽는다. 깨끗한 키는 바이트 하나도 바뀌지 않고, 정리하고 나서 비면(공백·보이지 않는 글자뿐) 스텁이다.

구성: ① 서브프로세스 — import 때 읽으므로 사례마다 generator 를 새로 가져온다. 가짜 키는 `CANARY_` 로 시작하는 조립 문자열(소스에 완성된 키 모양을 두지 않는다)이고 줄바꿈·폭 없는 공백·앞뒤 공백을 섞어
환경 변수로 준다. 소켓은 모두 막혀 있고, 연결 단계에서 OSError 를 내는 가짜 연결 클래스를 써서 '요청 머리글 검사(연결 전에 ValueError 가 나는 곳)'까지만 진짜 코드가 돈다 — 네트워크는 없다.
자식 프로세스는 불리언과 개수만 돌려주고 키 글자는 출력하지 않는다. ② generator.py 소스(AST) — 이 환경 변수를 읽는 식은 모두 `clean_secret(` 안에 있다.
"""
import ast
import json
import os
import subprocess
import sys
import unittest

import _bootstrap

ROOT = _bootstrap.ROOT
ENV_NAME = "UNSPLASH_ACCESS_KEY"
ZW = chr(0x200B)        # 폭 없는 공백
WJ = chr(0x2060)        # 단어 결합자
BOM = chr(0xFEFF)       # 바이트 순서 표시
SHY = chr(0x00AD)       # 소프트 하이픈
HANGUL = chr(0xAC00)    # 눈에 보이지만 라틴-1 밖인 글자(요청 머리글에 못 싣는다)
CORE = "CANARY" + "_" + "unsplash" + "KEY" + "-" + "ab12"       # 가짜 키(소스에 완성된 키 모양을 두지 않는다)

# (사례 이름, 환경 변수 값(None 이면 변수를 두지 않는다), 정리 뒤에 기대하는 generator.UNSPLASH_KEY)
KEY_CASES = (
    ("clean", CORE, CORE),
    ("trailing_lf", CORE + "\n", CORE),
    ("trailing_crlf", CORE + "\r\n", CORE),
    ("spaces_tab_cr", " \t" + CORE + " \r", CORE),
    ("interior_lf", CORE[:8] + "\n" + CORE[8:], CORE),
    ("zero_width", ZW + CORE[:9] + ZW + CORE[9:] + WJ, CORE),
    ("bom_soft_hyphen", BOM + CORE + SHY, CORE),
)
STUB_CASES = (
    ("unset", None, ""),
    ("empty", "", ""),
    ("spaces", "   ", ""),
    ("lf_only", "\n", ""),
    ("invisible_only", ZW + BOM + WJ, ""),
)
OUTSIDE_LATIN1 = ("outside_latin1", CORE + HANGUL, CORE + HANGUL)
REQUESTS_PER_CASE = 3       # 자식이 부르는 요청 세 가지: 검색(search_unsplash)·고정 목록 사진 조회(fetch_pool_photo)·사용 알림(trigger_download)

# 자식 프로세스가 도는 코드. 인자: 저장소 루트, 가짜 키의 알맹이(CORE). 표준 입력: 사례 목록(JSON). 표준 출력 마지막 줄: 결과(JSON) — 불리언·개수·정리한 로그뿐이다.
CHILD = r'''
import contextlib
import http.client
import io
import json
import os
import socket
import sys
import unicodedata
import urllib.request

root, core = sys.argv[1], sys.argv[2]
cases = json.load(sys.stdin)
sys.path.insert(0, root)

network = []


def blocked(*args, **kwargs):
    network.append(1)
    raise AssertionError("network attempt")


socket.socket.connect = blocked
socket.create_connection = blocked
socket.getaddrinfo = blocked


class Offline(http.client.HTTPConnection):
    """연결을 열지 않는 가짜 연결: 요청 머리글 검사(putheader)까지는 진짜 코드가 돌고, 연결 단계에서 OSError 를 낸다."""
    attempts = 0

    def connect(self):
        Offline.attempts += 1
        raise OSError("offline test")


class OfflineHandler(urllib.request.AbstractHTTPHandler):
    https_request = urllib.request.AbstractHTTPHandler.do_request_

    def https_open(self, req):
        return self.do_open(Offline, req)


director = urllib.request.OpenerDirector()
director.add_handler(OfflineHandler())
urllib.request.install_opener(director)

POOL = "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?auto=format"
PHOTO = "https://images.unsplash.com/photo-1558494949-ef010cbdcc31"
PING = "https://api.unsplash.com/photos/abcde12345/download"
HIDDEN = ("Cc", "Cf", "Cs")

results = []
g = None
for case in cases:
    os.environ.pop("UNSPLASH_ACCESS_KEY", None)
    if case["value"] is not None:
        os.environ["UNSPLASH_ACCESS_KEY"] = case["value"]
    sys.modules.pop("generator", None)
    import generator as g
    expect = case["expect"]
    Offline.attempts = 0
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        found = g.search_unsplash("tree")
        pooled = g.fetch_pool_photo(POOL)
        g._download_locations[g.image_key(PHOTO)] = PING
        g.trigger_download(PHOTO)
    log = out.getvalue()
    auth = g._api_request("https://api.unsplash.com/photos/x").get_header("Authorization") or ""
    results.append({
        "name": case["name"],
        "key_is_str": isinstance(g.UNSPLASH_KEY, str),
        "key_ok": g.UNSPLASH_KEY == expect,
        "stub": bool(g.STUB_UNSPLASH),
        "header_ok": auth == "Client-ID " + expect,
        "header_hidden": any(unicodedata.category(ch) in HIDDEN for ch in auth),
        "connects": Offline.attempts,
        "log_has_key": core in log,
        "log_has_header_error": any(word in log for word in ("Invalid header", "codec can", "Client-ID")),
        "log": log.replace(core, "<KEY>"),
        "returned": [found, pooled],
    })

import pipeline.console
shared = getattr(g, "clean_secret", None) is pipeline.console.clean_secret
print(json.dumps({"network": len(network), "shared": shared, "results": results}))
'''

DROPPED_ENV = (ENV_NAME, "GEMINI_API_KEY", "PIPELINE_PAUSE", "DRY_RUN", "FIX_IMAGES", "SHADOW_RUN", "EVENT_NAME", "POST_HOURS_KST")


def run_child(cases):
    """사례마다 generator 를 새로 가져와 결과(불리언·개수)를 모은다. 자식이 실패하면 표준 출력·오류의 끝을 담아 시험을 실패시킨다."""
    env = {k: v for k, v in os.environ.items() if k not in DROPPED_ENV and not k.startswith("PIPELINE_SECRET_")}
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    payload = json.dumps([{"name": name, "value": value, "expect": expect} for name, value, expect in cases])
    done = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", CHILD, str(ROOT), CORE], cwd=str(ROOT), env=env, input=payload,
                          capture_output=True, text=True, encoding="utf-8", timeout=300)
    lines = done.stdout.strip().splitlines()
    if done.returncode != 0 or not lines:
        raise AssertionError("자식 프로세스가 실패했다(종료 %s)\n%s" % (done.returncode, (done.stdout + done.stderr)[-1500:].replace(CORE, "<KEY>")))
    return json.loads(lines[-1])


class UnsplashKeyReadTest(unittest.TestCase):
    """generator 를 가져올 때 읽은 키·요청 머리글·로그를 본다(서브프로세스 한 번에 모든 사례를 돌린다 — 사례마다 모듈을 새로 가져온다)."""

    @classmethod
    def setUpClass(cls):
        cls.report = run_child(KEY_CASES + STUB_CASES + (OUTSIDE_LATIN1,))
        cls.by_name = {item["name"]: item for item in cls.report["results"]}

    def test_every_case_was_run(self):
        names = [name for name, _value, _expect in KEY_CASES + STUB_CASES + (OUTSIDE_LATIN1,)]
        self.assertEqual(sorted(self.by_name), sorted(names))

    def test_a_clean_key_is_used_byte_for_byte_and_every_request_reaches_the_connection(self):
        got = self.by_name["clean"]
        self.assertTrue(got["key_is_str"], got)
        self.assertTrue(got["key_ok"], got)              # 바이트 하나도 바뀌지 않는다
        self.assertTrue(got["header_ok"], got)           # 요청 머리글은 `Client-ID ` 와 키 그대로
        self.assertFalse(got["stub"], got)
        self.assertEqual(got["connects"], REQUESTS_PER_CASE, got)
        self.assertEqual(got["returned"], [[], None], got)

    def test_dirty_keys_are_cleaned_before_use(self):
        for name, _value, _expect in KEY_CASES[1:]:
            with self.subTest(case=name):
                got = self.by_name[name]
                self.assertTrue(got["key_ok"], got)                  # 정리된 키가 깨끗한 키와 같다
                self.assertTrue(got["header_ok"], got)
                self.assertFalse(got["header_hidden"], got)          # 요청 머리글에 줄바꿈·제어 문자·보이지 않는 글자가 없다
                self.assertFalse(got["stub"], got)                   # 정리하고도 값이 남으면 스텁이 아니다

    def test_a_cleaned_key_lets_every_request_get_past_the_header_check(self):
        for name, _value, _expect in KEY_CASES:
            with self.subTest(case=name):
                got = self.by_name[name]
                self.assertEqual(got["connects"], REQUESTS_PER_CASE, got)        # 세 요청 모두 연결 단계까지 간다(머리글 오류로 멈추지 않는다)
                self.assertFalse(got["log_has_header_error"], got)
                self.assertEqual(got["returned"], [[], None], got)

    def test_the_log_never_carries_the_key_text(self):
        for name, got in sorted(self.by_name.items()):
            with self.subTest(case=name):
                self.assertFalse(got["log_has_key"], got)

    def test_blank_or_missing_values_are_a_stub_and_send_no_request(self):
        for name, _value, _expect in STUB_CASES:
            with self.subTest(case=name):
                got = self.by_name[name]
                self.assertTrue(got["key_is_str"], got)              # 없는 변수도 빈 문자열이다(예전에는 None)
                self.assertTrue(got["key_ok"], got)
                self.assertTrue(got["stub"], got)                    # 공백·보이지 않는 글자뿐인 값도 스텁이다
                self.assertEqual(got["connects"], 0, got)
                self.assertEqual(got["log"].strip(), "UNSPLASH_ACCESS_KEY 없음: 검색 생략", got)       # 예전과 같은 한 줄
                self.assertEqual(got["returned"], [[], None], got)

    def test_a_visible_character_outside_latin1_still_stops_before_the_connection_but_never_prints_the_whole_key(self):
        """남은 한계를 못박는다(고치기 전에도 같다): 눈에 보이는 글자는 clean_secret 이 지우지 않으므로 머리글을 만들다 멈추지만, 그 오류 문구에는 글자 하나와 위치만 있다."""
        got = self.by_name["outside_latin1"]
        self.assertTrue(got["key_ok"], got)
        self.assertFalse(got["stub"], got)
        self.assertEqual(got["connects"], 0, got)
        self.assertFalse(got["log_has_key"], got)

    def test_no_connection_was_opened_and_the_shared_function_is_the_one_in_use(self):
        self.assertEqual(self.report["network"], 0)          # 소켓 연결·이름 풀이 시도가 한 번도 없었다
        self.assertTrue(self.report["shared"])               # generator.clean_secret 이 pipeline.console.clean_secret 그 함수다


def is_const(node, value):
    return isinstance(node, ast.Constant) and node.value == value


def env_reads(source, name):
    """소스에서 환경 변수 `name` 을 읽는 식 전부와 각 식을 바로 감싼 부모 노드: 첫 인자가 그 이름인 호출(os.environ.get·os.getenv·getenv 등)과 그 이름으로 하는 인덱스(os.environ[...])."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    reads = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args and is_const(node.args[0], name):
            reads.append(node)
        elif isinstance(node, ast.Subscript) and is_const(node.slice, name):
            reads.append(node)
    return [(node, parents.get(node)) for node in reads]


def wrapped_in_clean_secret(read, parent):
    """읽는 식의 바로 위 부모가 `clean_secret(<읽는 식>, ...)` 호출인가."""
    return (isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id == "clean_secret"
            and bool(parent.args) and parent.args[0] is read)


def unwrapped_reads(source, name):
    return [read.lineno for read, parent in env_reads(source, name) if not wrapped_in_clean_secret(read, parent)]


class UnsplashKeySourceTest(unittest.TestCase):
    """generator.py 소스를 AST 로 읽는다: 키를 읽는 식이 `clean_secret(` 밖에 하나라도 생기면 빨개진다."""

    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "generator.py").read_text(encoding="utf-8")

    def test_every_read_of_the_environment_variable_goes_through_clean_secret(self):
        reads = env_reads(self.source, ENV_NAME)
        self.assertGreaterEqual(len(reads), 1)               # 읽는 식을 못 찾아 조용히 통과하지 않게
        self.assertEqual(unwrapped_reads(self.source, ENV_NAME), [])

    def test_clean_secret_is_imported_from_pipeline_console_before_it_is_used(self):
        tree = ast.parse(self.source)
        imports = [(node.lineno, alias) for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "pipeline.console" for alias in node.names]
        found = [lineno for lineno, alias in imports if alias.name == "clean_secret" and alias.asname is None]
        self.assertEqual(len(found), 1, imports)
        self.assertLess(found[0], min(read.lineno for read, _parent in env_reads(self.source, ENV_NAME)))       # 쓰기 전에 가져온다
        redefined = [node.lineno for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == "clean_secret"]
        redefined += [target.lineno for node in ast.walk(tree) if isinstance(node, ast.Assign) for target in node.targets if isinstance(target, ast.Name) and target.id == "clean_secret"]
        self.assertEqual(redefined, [])                      # 같은 이름을 모듈 안에서 따로 만들지 않는다

    def test_the_source_check_really_sees_an_unwrapped_read(self):
        wrapped = 'import os\nKEY = clean_secret(os.environ.get("UNSPLASH_ACCESS_KEY"))\n'
        self.assertEqual(len(env_reads(wrapped, ENV_NAME)), 1)           # 읽는 식을 본다
        self.assertEqual(unwrapped_reads(wrapped, ENV_NAME), [])
        for label, text in (
                ("plain get", 'import os\nKEY = os.environ.get("UNSPLASH_ACCESS_KEY")\n'),
                ("get with default", 'import os\nKEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")\n'),
                ("getenv", 'import os\nKEY = os.getenv("UNSPLASH_ACCESS_KEY")\n'),
                ("subscript", 'import os\nKEY = os.environ["UNSPLASH_ACCESS_KEY"]\n'),
                ("strip only", 'import os\nKEY = (os.environ.get("UNSPLASH_ACCESS_KEY") or "").strip()\n'),
                ("another function", 'import os\nKEY = other(os.environ.get("UNSPLASH_ACCESS_KEY"))\n'),
                ("clean_secret on the wrong argument", 'import os\nKEY = clean_secret("x", os.environ.get("UNSPLASH_ACCESS_KEY"))\n')):
            with self.subTest(shape=label):
                self.assertEqual(len(unwrapped_reads(text, ENV_NAME)), 1)
        self.assertEqual(env_reads('import os\nKEY = os.environ.get("OTHER_NAME")\n', ENV_NAME), [])      # 다른 이름은 보지 않는다


if __name__ == "__main__":
    unittest.main()
