"""외부 접속 '알려진 모양' 스캐너 — 저장소의 파이썬 소스를 AST 로 읽어 네트워크에 닿을 수 있는 모양(호출·참조·import)을 모은다(순수 함수: 소스 글과 상대 경로만 받는다).
tests/test_egress.py(등록 목록 대조)와 합성 점검(다른 가지가 병합된 트리 읽기)이 함께 쓴다. 요청은 한 번도 보내지 않는다.

**보증이 아니다.** 이 스캐너는 '알려진 모양'의 목록이고, 새 모양·동적 코드·소스 밖의 일(시험 코드, 파이썬이 아닌 파일, 하위 프로세스가 도는 다른 프로그램)은 잡지 못한다.
사람 검토가 마지막 방어선이다. 잡지 못하는 모양은 docs/SOURCE_POLICY.md 7절의 사각지대 표에 적고, tests/test_egress.py 의 BLIND_SPOT_SHAPES 가 그 표를 실제와 맞춘다.

무엇을 보나(모양 종류 — Site.kind):
  net:<이름>          urlopen·urlretrieve·build_opener·install_opener·OpenerDirector·URLopener·FancyURLopener·HTTP(S)Handler·HTTP(S)Connection·create_connection·socket.socket·
                      getaddrinfo·gethostby*·wrap_socket·open_connection·start_tls 이름의 호출·참조·from-import(별칭을 써도 `from x import y as z` 줄에서 잡는다)
  lib:<패키지>        requests·httpx·aiohttp·urllib3·pycurl·httplib2·feedparser·ftplib·smtplib·xmlrpc·webbrowser·ctypes·telnetlib·poplib·imaplib·nntplib 같은 네트워크 라이브러리 import
  sdk:<모듈>          구글 SDK(genai·googleapiclient·oauth2·auth) import
  dyn:getattr         getattr 로 이름을 동적으로 고르거나 네트워크 이름·모듈에 닿는 모양
  dyn:dict-lookup     `x.__dict__[…]`·`vars(x)[…]`·`globals()[…]` 로 네트워크 이름에 닿는 모양
  dyn:import          importlib.import_module·__import__      dyn:eval / dyn:exec  eval·exec 호출
  parse:<이름>        URL 을 받을 수 있는 파서(xml.sax.parse·xml.dom.minidom.parse·xml.dom.pulldom.parse·xml.etree.ElementTree.parse·pandas.read_*)
  proc:<도구>         subprocess·os.system·os.popen·os.exec*·os.spawn* 중 명령에 네트워크 도구(curl·wget·git 의 ls-remote/fetch/clone/pull/push/remote/submodule·powershell·pwsh·certutil·bitsadmin·
                      ssh·scp·nslookup·ftp·telnet·gh·pip …)가 글자로 들었거나, 명령이 글자 목록이 아니라 동적인 경우(proc:dynamic)

관문 인정(Site.gated)은 아래 **모두**가 맞을 때만이다(주소를 알 수 있는 urlopen·urlretrieve 호출만 대상 — 어느 하나라도 확신할 수 없으면 '인정 안 함'이다, 곧 실패 쪽이다):
  ① 같은 함수에서 `pipeline.egress.check_url` 을 **문장으로** 불렀고 — 그 이름(`egress`·별칭·`check_url`)은 **파일 안에서 오직 `pipeline.egress` 를 가리키는 import 로만** 묶여 있어야 한다
    (매개변수·지역 대입·`for`/`with`/`except` 대상·함수/클래스 정의로 같은 이름을 다시 묶거나, 다른 모듈 `egress` 를 가져오거나, 이름을 import 없이 쓰거나, `from … import *` 가 있으면 인정하지 않는다),
  ② 그 첫 인자(주소 식)가 네트워크 호출에 쓰는 주소 식과 `ast.dump` 로 같으며(호출이 든 식은 안 됨 — 두 번 계산하면 값이 달라질 수 있다. `Request` 변수를 따라갈 때는 그 이름을 묶는 곳이 **하나**이고 `이름 = Request(…)` 한 줄일 때만),
  ③ 관문 호출이 호출보다 앞서고 그 호출을 지배하며(조건문·반복문·`with`·핸들러 안의 관문은 아님. `try` 본문 안의 관문은 **모든 핸들러가 끝에서 무조건 `raise` 하고** `return`·`break`·`continue` 가 없을 때만),
  ④ 두 호출 사이에 주소 식의 이름에 다시 대입하지 않았고(이름뿐 아니라 그 이름 아래 속성·첨자 대입도) — 호출이 반복문 안에 있고 관문은 반복문 밖이면 **반복문 전체**에서 대입하지 않았으며,
  ⑤ 호출이 람다·내포·생성기식 안에 있지 않다(늦게 실행되거나 다른 범위의 이름을 본다).
  `source_policy.egress_gate` 처럼 `legacy` 에서 아무 일도 하지 않는 호출은 관문으로 인정하지 않는다 — 그런 호출은 등록 목록(EGRESS_EXCEPTIONS)에 '어느 모드에서 무엇이 막는지'와 함께 올린다.
  못 보는 것(문서에 적음): 객체의 내용을 바꾸는 메서드 호출(`items.reverse()`)·전역을 바꾸는 함수 호출·`check_url` 에 모든 것을 허용하는 가짜 registry 를 넘기는 것(호출자 책임) — 이 틈들은 관문 인정이 아니라 사람 검토 몫이다.
"""
import ast
import collections
import functools
import os
import re
from pathlib import Path

Site = collections.namedtuple("Site", "file function kind line gated note")

# ----------------------------------------------------------------------------
# 알려진 모양 표
# ----------------------------------------------------------------------------
NET_NAMES = frozenset({
    "urlopen", "urlretrieve", "build_opener", "install_opener", "create_connection", "HTTPConnection", "HTTPSConnection",
    "OpenerDirector", "URLopener", "FancyURLopener", "HTTPHandler", "HTTPSHandler",
    "open_connection", "open_unix_connection", "wrap_socket", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "start_tls",
    "get_server_certificate", "getfqdn", "getnameinfo", "create_datagram_endpoint", "create_unix_connection", "SocketHandler", "DatagramHandler", "SMTPHandler", "RobotFileParser",
})
NET_FQNS = frozenset({"socket.socket", "socket.SocketType", "_socket.socket"})
NET_FQN_PREFIXES = ("multiprocessing.connection.",)
NET_LIBS = frozenset({
    "requests", "httpx", "aiohttp", "urllib3", "pycurl", "httplib2", "feedparser", "ftplib", "smtplib", "xmlrpc", "webbrowser", "ctypes", "telnetlib", "poplib", "imaplib", "nntplib",
    "websockets", "websocket", "paramiko", "boto3", "botocore", "grpc", "aioftp", "openai", "anthropic", "cohere", "mistralai", "ollama", "langchain", "vertexai", "selenium", "playwright",
    "scrapy", "mechanize", "yt_dlp", "youtube_dl", "tweepy", "telebot", "slack_sdk", "discord", "gspread", "redis", "pymongo", "psycopg2", "pymysql",
    "_socket", "treq", "dns", "tornado", "twisted", "lxml", "sh", "plumbum", "pexpect", "fabric",
})
NET_LIB_PREFIXES = ("pip._vendor",)                                               # pip 이 품고 있는 requests 등(`from pip._vendor import requests`)
SDK_PREFIXES = ("google.genai", "googleapiclient", "google.oauth2", "google.auth", "google_auth_oauthlib", "google.generativeai", "google.cloud")
URL_PARSER_FQNS = frozenset({"xml.sax.parse", "xml.sax.make_parser", "xml.dom.minidom.parse", "xml.dom.pulldom.parse", "xml.etree.ElementTree.parse", "xml.etree.ElementTree.iterparse"})
URL_PARSER_PREFIXES = ("pandas.read_",)
PROC_FQNS = frozenset({"subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_call", "subprocess.check_output", "subprocess.getoutput", "subprocess.getstatusoutput",
                       "os.system", "os.popen", "os.startfile", "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell", "pty.spawn"})
PROC_PREFIXES = ("os.exec", "os.spawn")
NET_TOOLS = frozenset({"curl", "wget", "powershell", "pwsh", "invoke-webrequest", "iwr", "invoke-restmethod", "irm", "certutil", "bitsadmin", "ssh", "scp", "sftp", "nslookup", "ftp", "telnet",
                       "nc", "ncat", "netcat", "tftp", "rsync", "ping", "tracert", "dig", "gh", "pip", "pip3", "npm", "npx", "winget", "choco",
                       "openssl", "socat", "explorer", "xdg-open", "mshta", "rundll32", "start-bitstransfer", "net.webclient", "downloadstring", "downloadfile"})
SHELL_PROGRAMS = frozenset({"powershell", "pwsh", "cmd", "bash", "sh", "zsh", "wsl"})
PYTHON_PROGRAMS = frozenset({"python", "python3", "py", "pythonw"})
INTERPRETER_PROGRAMS = frozenset({"node", "nodejs", "deno", "bun", "perl", "ruby", "php", "lua"})     # `-e`·`-c` 로 코드 글자를 받는 다른 언어 실행기 — 글자 속은 보지 않으므로 코드 인자가 있으면 동적으로 본다
WRAPPER_PROGRAMS = frozenset({"env", "timeout", "nice", "nohup", "sudo", "time", "busybox", "xargs", "stdbuf", "setsid", "command", "exec", "ionice", "chroot", "strace"})   # 뒤에 오는 프로그램을 대신 실행하는 도구
GIT_NET_SUBCOMMANDS = frozenset({"ls-remote", "fetch", "clone", "pull", "push", "remote", "submodule", "lfs", "request-pull"})
GIT_VALUE_OPTIONS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix"})
DYN_MODULE_FQNS = frozenset({"urllib", "urllib.request", "http", "http.client", "socket", "ssl", "asyncio", "subprocess", "os", "importlib", "ctypes", "builtins", "_socket", "runpy", "pty"})
DYN_IMPORT_FQNS = frozenset({"importlib.import_module", "importlib.__import__", "importlib.util.spec_from_file_location", "runpy.run_module", "runpy.run_path", "builtins.__import__",
                             "importlib.machinery.SourceFileLoader", "importlib.machinery.SourcelessFileLoader"})
DYN_IMPORT_ATTRS = frozenset({"load_module", "exec_module"})                       # 로더가 파일을 코드로 불러오는 메서드 이름
BUILTIN_EXEC_NAMES = frozenset({"eval", "exec", "__import__", "compile"})           # 글자를 코드로 바꾸거나 실행하는 내장 이름 — 부르는 것뿐 아니라 이름을 다른 변수에 담는 것도 본다
BUILTIN_EXEC_FQNS = frozenset({"builtins.eval", "builtins.exec", "builtins.compile"})
DYN_CODE_FQNS = frozenset({"types.FunctionType", "types.CodeType", "timeit.timeit", "timeit.repeat", "timeit.Timer", "code.interact", "code.InteractiveInterpreter"})
DYN_ATTRGET_FQNS = frozenset({"operator.attrgetter", "operator.methodcaller", "functools.partial", "functools.partialmethod"})
DESERIALIZE_FQNS = frozenset({"pickle.load", "pickle.loads", "pickle.Unpickler", "marshal.load", "marshal.loads", "dill.load", "dill.loads", "cloudpickle.load", "cloudpickle.loads", "shelve.open",
                              "yaml.load", "yaml.load_all", "yaml.unsafe_load", "yaml.unsafe_load_all", "yaml.full_load", "yaml.full_load_all"})     # 데이터가 코드를 되살리는 길(안전하지 않은 읽기)
STAR_MODULES = frozenset({"subprocess", "os", "socket", "ssl", "asyncio", "importlib", "builtins", "ctypes", "runpy", "pty", "_socket", "urllib.request", "http.client", "multiprocessing.connection", "logging.handlers"})
GATE_FQNS = frozenset({"pipeline.egress.check_url"})          # 관문으로 인정하는 이름은 이 점 이름 하나뿐 — 파일 안에서 오직 `pipeline.egress` 를 가리키는 import 로 풀릴 때만(SRCV2 D1)
_NET_TOOL_RE = re.compile(r"(?<![\w.-])(?:" + "|".join(sorted((re.escape(t) for t in NET_TOOLS if t not in ("pip", "pip3")), key=len, reverse=True)) + r")(?:\.exe)?(?![\w-])", re.I)
_GIT_NET_RE = re.compile(r"(?<![\w.-])git(?:\.exe)?\s+(?:-\S+\s+)*(?:" + "|".join(sorted(GIT_NET_SUBCOMMANDS)) + r")(?![\w-])", re.I)
_PIP_RE = re.compile(r"(?<![\w.-])pip3?(?:\.exe)?\s+(?:install|download)(?![\w-])", re.I)

# 스캔 범위(상대 경로 머리말): tests/ 밖의 모든 *.py 는 아래 '스캔함' 이거나 '제외(이유)' 둘 중 하나여야 한다(tests/test_egress.py 가 확인 — 새 최상위 폴더가 생기면 빨강).
SCAN_ROOTS = ("generator.py", "blogger_generator.py", "pipeline", "scripts", "인수인계/도구", ".github")
SCAN_EXCLUDED = (
    ("tests", "시험 코드 — 운영 경로가 아니다(가짜 소켓·urlopen 흉내가 많아 스캔하면 잡음이 된다). 시험이 진짜 네트워크를 쓰지 않는 것은 시험 모음의 몫이고 이 스캐너가 보증하지 않는다"),
)
SKIP_DIRS = frozenset({".git", "__pycache__"})                          # 어느 깊이에서든 건너뛰는 폴더 이름(저장소 기계 폴더뿐)
SKIP_TOP_DIRS = frozenset({"node_modules", "_site", ".ruff_cache", ".pytest_cache", ".venv", "venv"})          # 저장소 맨 위에서만 건너뛴다(빌드 산출물·가상환경) — 스캔 폴더 안쪽의 같은 이름 폴더는 읽는다(SRCV2 D2: `pipeline/venv/x.py` 가 보이지 않던 틈)


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _collect_aliases(tree):
    """모듈 안의 모든 import 가 만드는 이름 → 가능한 원래 이름 집합(범위를 가리지 않는다 — 보수적으로 합친다)."""
    aliases = collections.defaultdict(set)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname].add(alias.name)
                else:
                    top = alias.name.split(".")[0]
                    aliases[top].add(top)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                aliases[alias.asname or alias.name].add(f"{node.module}.{alias.name}")
    for _ in range(2):                                    # `sp = subprocess`·`o = os`·`ur = urllib.request`: 알려진 모듈 이름을 다른 이름에 담으면 그 이름도 같은 모듈로 푼다(SRCV2 D3 ④, 두 번 돌려 `a = b` 사슬까지)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, (ast.Name, ast.Attribute)):
                dotted = _dotted(node.value)
                if not dotted:
                    continue
                first, _, rest = dotted.partition(".")
                for base in (aliases.get(first) or {first}):
                    full = base + ("." + rest if rest else "")
                    if full in DYN_MODULE_FQNS:
                        aliases[node.targets[0].id].add(full)
    return aliases


def _parent_map(tree):
    parent = {}
    for node in ast.walk(tree):
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for index, child in enumerate(value):
                    if isinstance(child, ast.AST):
                        parent[child] = (node, field, index)
            elif isinstance(value, ast.AST):
                parent[value] = (node, field, None)
    return parent


_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _walk_no_defs(node):
    """node 아래를 훑되 중첩 함수·클래스·람다 안으로는 들어가지 않는다(정의할 때는 실행되지 않는 코드)."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        yield current
        if not isinstance(current, _DEF_NODES):
            stack.extend(ast.iter_child_nodes(current))


def _simple_expr(node):
    """같은 식을 두 번 계산해도 같은 값이라고 볼 수 있는 단순한 식인가: 상수·이름·속성·상수 키 첨자·f-문자열·문자열 덧셈. 호출이 든 식은 아니다."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.Attribute):
        return _simple_expr(node.value)
    if isinstance(node, ast.Subscript):
        return _simple_expr(node.value) and isinstance(node.slice, ast.Constant)
    if isinstance(node, ast.JoinedStr):
        return all(_simple_expr(v) for v in node.values)
    if isinstance(node, ast.FormattedValue):
        return _simple_expr(node.value) and node.format_spec is None and node.conversion == -1
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _simple_expr(node.left) and _simple_expr(node.right)
    return False


def _always_raises(handler):
    """except 핸들러가 **모든 경로에서** 예외를 다시 올리는가(SRCV2 D1): 본문의 마지막 문장이 무조건 `raise` 이고 본문 어디에도 `return`·`break`·`continue` 가 없다.
    죽은 분기나 조건부 `raise`(`if False: raise`·`if strict: raise`)는 삼키는 길이 남아 있으므로 '다시 올린다'로 보지 않는다."""
    body = handler.body
    if not body or not isinstance(body[-1], ast.Raise):
        return False
    return not any(isinstance(n, (ast.Return, ast.Break, ast.Continue)) for stmt in body for n in [stmt] + list(_walk_no_defs(stmt)))


def _is_try(node):
    return isinstance(node, ast.Try) or node.__class__.__name__ == "TryStar"


def _transparent(compound, parent, field):
    """관문 문장(부모 `parent`, 그 부모의 칸 `field`)이 복합문 `compound` 안에 있을 때, 관문이 복합문 밖의 코드까지 지배하는가: 문장이 **try 본문에 직접** 들어 있고(부모가 try 자신 — except 핸들러·else·finally 본문이면 안 된다)
    모든 핸들러가 끝에서 무조건 raise 하며 finally 가 흐름을 가로채지 않을 때만."""
    if not _is_try(compound) or parent is not compound or field != "body":
        return False
    if not all(_always_raises(h) for h in compound.handlers):
        return False
    for stmt in compound.finalbody:
        if any(isinstance(n, (ast.Return, ast.Break, ast.Continue)) for n in [stmt] + list(_walk_no_defs(stmt))):
            return False
    return True


def _dominates(gate_chain, site_chain):
    """관문 문장 사슬이 호출 문장 사슬을 지배하는가(사슬 = 함수 본문에서 그 문장까지의 (문장, 부모, 필드, 순번) 목록). 둘이 갈라지는 지점에서 같은 목록의 앞뒤여야 하고 관문은 그 목록의 문장이거나 투명한 try 안이어야 한다."""
    k = 0
    while k < len(gate_chain) and k < len(site_chain) and gate_chain[k][0] is site_chain[k][0]:
        k += 1
    if k >= len(gate_chain) or k >= len(site_chain):
        return False                                  # 같은 문장 안의 호출은 순서를 알 수 없고, 한쪽이 다른 쪽을 감싸는 꼴도 지배가 아니다
    gate, site = gate_chain[k], site_chain[k]
    if gate[1] is not site[1] or gate[2] != site[2]:
        return False                                  # 같은 목록(같은 부모·같은 필드)이 아니면 — if 의 본문과 else, try 의 본문과 핸들러 — 지배하지 못한다
    if gate[3] >= site[3]:
        return False
    for depth in range(k + 1, len(gate_chain)):
        _, parent, field, _ = gate_chain[depth]
        if not _transparent(gate_chain[depth - 1][0], parent, field):
            return False                              # 조건문·반복문·with·핸들러·else·삼키는 try 안의 관문은 호출을 지배하지 않는다
    return True


def _join_pieces(left, right):
    """이어붙인 두 글자 식의 조각 목록을 한 글자로 이어 붙인다(`'cu' + 'rl '` → `curl `) — 목록 인자와 달리 덧셈·f-문자열은 사이에 공백이 없다."""
    if left and right:
        return left[:-1] + [left[-1] + right[0]] + right[1:]
    return left + right


def _names_in(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _store_root(node):
    """대입·삭제 대상 `a.b[c].d` 의 뿌리 이름(없으면 None). 이름·속성·첨자만 따라간다."""
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _import_targets(node, rel):
    """import 문 하나가 만드는 (묶이는 이름, 가리키는 점 이름 또는 None). 상대 import 는 파일 위치로 풀고 `*` 는 ('*', 모듈)."""
    out = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            out.append((alias.asname, alias.name) if alias.asname else (alias.name.split(".")[0], alias.name.split(".")[0]))
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if node.level:
            package = rel.split("/")[:-1]
            keep = len(package) - (node.level - 1)
            base = package[:keep] if keep > 0 else []
            module = ".".join(base + ([node.module] if node.module else []))
        for alias in node.names:
            if alias.name == "*":
                out.append(("*", module))
            else:
                out.append((alias.asname or alias.name, f"{module}.{alias.name}" if module else alias.name))
    return out


def _binding_names(node):
    """노드 하나가 묶는(바꾸는) 이름들(import 는 제외 — 따로 본다): 이름 대입·삭제·함수 매개변수·함수/클래스 정의·except 대상·match 포획."""
    if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
        return [node.id]
    if isinstance(node, ast.arg):
        return [node.arg]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.ExceptHandler) and node.name:
        return [node.name]
    if node.__class__.__name__ in ("MatchAs", "MatchStar") and getattr(node, "name", None):
        return [node.name]
    if node.__class__.__name__ == "MatchMapping" and getattr(node, "rest", None):
        return [node.rest]
    return []


class _Scan(ast.NodeVisitor):
    def __init__(self, tree, rel):
        self.tree = tree
        self.rel = rel
        self.sites = []
        self.calls = collections.defaultdict(list)
        self.stack = []                                # (이름, 노드) — 함수·클래스 중첩
        self.aliases = _collect_aliases(tree)
        self.parent = _parent_map(tree)
        self.address = {}                              # urlopen/urlretrieve 이름 노드 → 주소 식 노드
        self.address_extra = {}                        # 같은 노드 → 주소를 찾으며 거친 변수 이름(`req` — 그 속성을 바꾸는 대입도 주소 변경으로 본다)
        self._extra = set()
        self.call_funcs = set()                        # 호출의 함수 자리에 있는 노드(참조와 호출을 가르는 데 쓴다)
        self._gates = {}
        self.bindings = collections.defaultdict(list)  # 파일 전체에서 이름 → 그 이름을 묶는 곳들: ("import", 점 이름) 또는 ("other", 종류)
        self.star_import = False                       # `from … import *` 가 있으면 어느 이름이든 어디서 왔는지 알 수 없다
        for node in ast.walk(tree):
            for name, target in _import_targets(node, rel):
                if name == "*":
                    self.star_import = True
                else:
                    self.bindings[name].append(("import", target))
            for name in _binding_names(node):
                self.bindings[name].append(("other", node.__class__.__name__))

    # -- 이름 풀이 ------------------------------------------------------------------------------
    def resolve(self, node):
        dotted = _dotted(node)
        if not dotted:
            return set()
        first, _, rest = dotted.partition(".")
        bases = self.aliases.get(first) or {first}
        return {base + ("." + rest if rest else "") for base in bases}

    def qual(self):
        return ".".join(name for name, _ in self.stack) or "<module>"

    def scope_node(self):
        return self.stack[-1][1] if self.stack else self.tree

    # -- 지점 기록 ------------------------------------------------------------------------------
    def add(self, kind, node, address=None):
        gated, note = False, "관문을 거치지 않음(주소를 알 수 없는 모양이거나 같은 주소를 앞서 판정한 egress.check_url 이 없음)"
        if address is not None:
            gated, note = self.gate_status(node, address, self.address_extra.get(node, frozenset()))
        self.sites.append(Site(self.rel, self.qual(), kind, node.lineno, gated, note))

    # -- 관문 판정 ------------------------------------------------------------------------------
    def chain(self, node, scope):
        out, current = [], node
        while current is not scope and current in self.parent:
            parent, field, index = self.parent[current]
            if isinstance(current, ast.stmt):
                out.append((current, parent, field, index))
            current = parent
        out.reverse()
        return out

    def is_gate_call(self, func):
        """호출의 함수 자리가 `pipeline.egress.check_url` 인가(SRCV2 D1): 점 이름이 정확히 그 이름 하나로 풀리고, 그 뿌리 이름이 파일 안에서 **오직 pipeline.egress 를 가리키는 import 로만** 묶여 있다.
        이름을 import 없이 쓰거나 다른 모듈(`import egress`)을 가져오거나 매개변수·지역 대입·반복 대상 등으로 다시 묶거나 `from … import *` 가 있으면 인정하지 않는다."""
        dotted = _dotted(func)
        if not dotted or self.star_import:
            return False
        root, _, rest = dotted.partition(".")
        bound = self.bindings.get(root)
        if not bound or any(kind != "import" for kind, _ in bound):
            return False
        if {base + ("." + rest if rest else "") for kind, base in bound if kind == "import"} != GATE_FQNS:      # import 로 묶인 것만 풀이한다 — 다시 묶은 곳이 있는지는 위의 줄이 따로 본다(한 줄이 한 가지 일만)
            return False
        return True

    def gates(self, scope):
        key = id(scope)
        if key not in self._gates:
            found = []
            for node in _walk_no_defs(scope):
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and self.is_gate_call(node.value.func):
                    call = node.value
                    arg = call.args[0] if call.args else next((k.value for k in call.keywords if k.arg == "url"), None)
                    if arg is not None and _simple_expr(arg):
                        found.append((ast.dump(arg), node.lineno, self.chain(node, scope)))
            self._gates[key] = found
        return self._gates[key]

    def reassigned(self, scope, address, low, high, extra=frozenset(), loops=()):
        """주소 식의 이름(과 주소를 찾으며 거친 변수 이름)이 관문 줄과 호출 줄 사이에서 다시 묶이거나(이름 대입·삭제·except 대상·import) 그 이름 아래 속성·첨자가 바뀌는가(`self.url = …`·`cfg['url'] = …`·`req.full_url = …`).
        `loops` 는 호출은 안에 있고 관문은 밖에 있는 반복문들 — 그 반복문 **전체**(호출 뒤의 줄 포함)에서 같은 변경이 있으면 다음 번 반복이 확인 안 된 주소를 쓴다(SRCV2 D1-4)."""
        names = _names_in(address)
        watched = names | set(extra)                 # 거쳐 온 변수(`req`)는 이미 한 번만 묶임이 확인됐으니 이름을 다시 묶는 것은 볼 필요가 없고, 그 아래 속성·첨자 대입(`req.full_url = …`)만 본다

        def hit(node):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)) and node.id in names:
                return True
            if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)) and _store_root(node) in watched:
                return True
            if isinstance(node, ast.ExceptHandler) and node.name in names:
                return True
            if isinstance(node, (ast.Import, ast.ImportFrom)) and any(name in names for name, _ in _import_targets(node, self.rel)):
                return True
            return False

        for node in _walk_no_defs(scope):
            if low < getattr(node, "lineno", 0) <= high and hit(node):
                return True
        for loop in loops:
            if any(hit(node) for node in _walk_no_defs(loop)):
                return True
        return False

    def gate_status(self, site_node, address, extra=frozenset()):
        if not _simple_expr(address):
            return False, "주소 식이 단순하지 않다(호출이 들어 있음) — 같은 식인지 판정할 수 없어 관문으로 인정하지 않음"
        scope = self.scope_node()
        current = site_node
        while current is not scope and current in self.parent:
            current = self.parent[current][0]
            if isinstance(current, (ast.Lambda, ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.DictComp)):
                return False, "호출이 람다·내포·생성기식 안에 있다(늦게 실행되거나 다른 범위의 이름을 본다) — 관문으로 인정하지 않음"
        site_chain = self.chain(site_node, scope)
        dump = ast.dump(address)
        for gate_dump, gate_line, gate_chain in self.gates(scope):
            if gate_dump != dump or gate_line >= site_node.lineno:
                continue
            gate_stmts = {id(entry[0]) for entry in gate_chain}
            loops = [entry[0] for entry in site_chain if isinstance(entry[0], (ast.For, ast.AsyncFor, ast.While)) and id(entry[0]) not in gate_stmts]
            if _dominates(gate_chain, site_chain) and not self.reassigned(scope, address, gate_line, site_node.lineno, extra, loops):
                return True, f"egress.check_url(줄 {gate_line})이 같은 주소 식을 앞서 지배적으로 판정"
        return False, "같은 주소 식을 앞서(지배하며) 판정한 egress.check_url 호출이 없음 — source_policy.egress_gate 처럼 legacy 에서 아무 일도 안 하는 호출은 관문이 아니다"

    # -- 주소 식 추적(urlopen(req) 의 req 가 Request(url) 로 만든 것인지) ---------------------------------------
    def request_address(self, call):
        self._extra = set()
        if call.args:
            return self._trace(call.args[0], call.lineno, 0)
        for keyword in call.keywords:
            if keyword.arg in ("url", "fullurl"):
                return self._trace(keyword.value, call.lineno, 0)
        return None

    def _is_request_call(self, node):
        if not isinstance(node, ast.Call):
            return False
        names = self.resolve(node.func)
        return bool(names & {"urllib.request.Request"}) or _dotted(node.func).split(".")[-1] == "Request"

    def assignments_before(self, name, line):
        """현재 범위에서 `name = …` 으로 line 앞에 대입한 문장 전부(없으면 빈 목록)."""
        return [node for node in _walk_no_defs(self.scope_node())
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name and node.lineno < line]

    def unique_assignment(self, name, line):
        """현재 범위에서 `name` 을 묶는 곳이 **단 하나**이고 그것이 `name = …` 한 줄(line 앞)일 때 그 대입 문장. 그 밖 — 매개변수이거나, 다른 대입·반복 대상·with·except·import·정의가 더 있거나(분기마다 다른 값),
        호출 뒤에 있는 것 — 은 None(SRCV2 D1-6: 마지막 줄의 대입 하나만 따라가면 `if flag: req = Request(evil) else: req = Request(u)` 의 앞 가지를 놓친다)."""
        scope = self.scope_node()
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = scope.args
            params = [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs] + ([args.vararg.arg] if args.vararg else []) + ([args.kwarg.arg] if args.kwarg else [])
            if name in params:
                return None
        found = []
        for node in _walk_no_defs(scope):
            if name in _binding_names(node) or (isinstance(node, (ast.Import, ast.ImportFrom)) and any(bound == name for bound, _ in _import_targets(node, self.rel))):
                found.append(node)
        if len(found) != 1:
            return None
        parent = self.parent.get(found[0], (None,))[0]
        if isinstance(parent, ast.Assign) and len(parent.targets) == 1 and parent.targets[0] is found[0] and parent.lineno < line:
            return parent
        return None

    def _trace(self, arg, line, depth):
        if self._is_request_call(arg):
            if arg.args:
                return arg.args[0]
            return next((k.value for k in arg.keywords if k.arg in ("url", "full_url")), None)
        if isinstance(arg, ast.Name) and depth < 3:
            self._extra.add(arg.id)
            best = self.unique_assignment(arg.id, line)
            if best is not None:
                traced = self._trace(best.value, best.lineno, depth + 1)
                if traced is not None and traced is not best.value:
                    return traced
                if _simple_expr(best.value):
                    return best.value
        return arg

    # -- 방문 -----------------------------------------------------------------------------------
    def scoped(self, node):
        self.stack.append((node.name, node))
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = scoped

    def visit_Call(self, node):
        name = _dotted(node.func)
        if name:
            self.calls[(self.rel, self.qual())].append((name, node.lineno))
        func = node.func
        self.call_funcs.add(func)
        leaf = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
        if leaf in ("urlopen", "urlretrieve"):
            self.address[func] = self.request_address(node)
            self.address_extra[func] = frozenset(self._extra)
        fqns = self.resolve(func)
        if isinstance(func, ast.Name) and func.id == "getattr":
            self.check_getattr(node)
        elif isinstance(func, ast.Name) and func.id in ("eval", "exec", "compile"):
            self.add(f"dyn:{func.id}", node)
        elif fqns & BUILTIN_EXEC_FQNS:
            self.add("dyn:" + sorted(fqns & BUILTIN_EXEC_FQNS)[0].split(".")[1], node)
        elif fqns & DYN_IMPORT_FQNS or (isinstance(func, ast.Name) and func.id == "__import__") or (isinstance(func, ast.Attribute) and func.attr in DYN_IMPORT_ATTRS):
            self.add("dyn:import", node)
        elif fqns & DYN_CODE_FQNS:
            self.add("dyn:code", node)
        elif fqns & DYN_ATTRGET_FQNS:
            self.check_attrget(node, fqns)
        elif isinstance(func, ast.Attribute) and func.attr == "__getattribute__":
            self.add("dyn:getattr", node)
        elif fqns & DESERIALIZE_FQNS:
            self.add("dyn:deserialize", node)
        elif isinstance(func, ast.Attribute) and func.attr == "get" and self.is_dict_view(func.value) and self.net_key(node.args[0] if node.args else None):
            self.add("dyn:dict-lookup", node)
        elif fqns & URL_PARSER_FQNS or any(f.startswith(URL_PARSER_PREFIXES) for f in fqns):
            self.add("parse:" + sorted(fqns)[0], node)
        elif fqns & PROC_FQNS or any(f.startswith(PROC_PREFIXES) for f in fqns):
            self.check_process(node, sorted(fqns)[0])
        self.generic_visit(node)

    def is_dict_view(self, value):
        """`x.__dict__`·`vars(x)`·`globals()`·`locals()` — 이름으로 속성을 꺼낼 수 있는 사전 보기."""
        return (isinstance(value, ast.Attribute) and value.attr == "__dict__") or (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in ("vars", "globals", "locals"))

    def net_key(self, key):
        """사전 보기의 키가 정수·동적이거나 네트워크 이름이면 True(상수 글자이고 네트워크 이름이 아니면 False)."""
        return not (isinstance(key, ast.Constant) and isinstance(key.value, str)) or key.value in NET_NAMES or key.value in BUILTIN_EXEC_NAMES or key.value == "__builtins__"

    def check_getattr(self, node):
        if len(node.args) < 2:
            return
        name = node.args[1]
        const = name.value if isinstance(name, ast.Constant) and isinstance(name.value, str) else None
        if const is None or const in NET_NAMES or const in BUILTIN_EXEC_NAMES or (self.resolve(node.args[0]) & DYN_MODULE_FQNS):
            self.add("dyn:getattr", node)

    def check_attrget(self, node, fqns):
        """`operator.attrgetter('x')`·`methodcaller('x')` 는 이름이 상수이고 네트워크 이름이 아니면 정상(정렬 키 등), `functools.partial(getattr, …)` 은 getattr 을 넘겨 두는 모양이다."""
        if fqns & {"functools.partial", "functools.partialmethod"}:
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Name) and first.id in ("getattr", "setattr", "eval", "exec", "__import__"):
                self.add("dyn:getattr", node)
            return
        first = node.args[0] if node.args else None
        const = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
        if const is None or const in NET_NAMES or const in BUILTIN_EXEC_NAMES:
            self.add("dyn:getattr", node)

    def check_process(self, node, fqn):
        if fqn == "os.startfile":                                    # 파일·주소를 연결 프로그램으로 연다(주소면 브라우저) — 무엇을 열지 글자만으로 알 수 없다
            self.add("proc:startfile", node)
            return
        if any(k.arg == "executable" for k in node.keywords):         # `Popen(['x', …], executable='curl')` — 실제 실행 파일이 인자 목록과 다르다
            self.add("proc:executable", node)
            return
        command = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg in ("args", "cmd", "command")), None)
        if fqn == "asyncio.create_subprocess_exec" or fqn.startswith(PROC_PREFIXES):          # 프로그램과 인자가 위치 인자로 따로 온다 — 목록 인자는 펼쳐 한 명령으로 본다
            flat = []
            for arg in node.args:
                flat.extend(arg.elts if isinstance(arg, (ast.List, ast.Tuple)) else [arg])
            command = ast.List(elts=flat, ctx=ast.Load()) if flat else None
        assigned = self.assignments_before(command.id, node.lineno) if isinstance(command, ast.Name) else []
        if assigned:                                              # `cmd = [...]` 으로 먼저 만든 명령이면 그 값을 본다 — 앞에서 대입한 모든 값(분기마다 다를 수 있다)을 보고 가장 의심스러운 것을 따른다
            kinds = [self.process_kind(a.value, node) for a in assigned]
            real = [k for k in kinds if k and k != "dynamic"]
            kind = real[0] if real else ("dynamic" if "dynamic" in kinds else None)
        else:                                                     # 대입을 찾지 못한 이름은 무엇인지 알 수 없다(process_kind 가 dynamic 으로 본다)
            kind = self.process_kind(command, node)
        if kind:
            self.add(f"proc:{kind}", node)

    def process_kind(self, command, call):
        """명령에서 네트워크 도구나 동적 명령을 알아본다. 해당 없으면 None."""
        if command is None:
            return "dynamic"
        if isinstance(command, (ast.List, ast.Tuple)):
            elements = command.elts
            if not elements:
                return "dynamic"
            first = elements[0]
            if isinstance(first, ast.Starred):
                return "dynamic"
            program = self.token(first)
            rest = elements[1:]
            if program is None:
                if isinstance(first, ast.Attribute) and _dotted(first) == "sys.executable":
                    return self.python_kind(rest)
                return "dynamic"
            if program in WRAPPER_PROGRAMS:                          # `env curl …`·`timeout 5 curl …`: 래퍼가 대신 실행하는 프로그램을 본다(옵션·VAR=값·숫자는 건너뛴다)
                inner = list(rest)
                while inner and isinstance(inner[0], ast.Constant) and isinstance(inner[0].value, str) and (inner[0].value.startswith("-") or "=" in inner[0].value or inner[0].value.replace(".", "").isdigit()):
                    inner.pop(0)
                return self.process_kind(ast.List(elts=inner, ctx=ast.Load()), call) if inner else None
            if program in NET_TOOLS and program not in ("pip", "pip3") and program not in SHELL_PROGRAMS:
                return program
            if program in ("pip", "pip3"):
                return self.pip_kind(rest)
            if program == "git":
                return self.git_kind(rest)
            if program in SHELL_PROGRAMS:
                fragments = [e.value for e in rest if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                if len(fragments) != len(rest):
                    return "dynamic"
                return self.text_kind(ast.Constant(value=" ".join(fragments))) if fragments else (program if program in ("powershell", "pwsh") else None)
            if program in PYTHON_PROGRAMS:
                return self.python_kind(rest)
            if program in INTERPRETER_PROGRAMS:                       # `node -e '…'` 처럼 코드 글자를 받는 실행기 — 글자 속은 보지 않는다
                values = [e.value for e in rest if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                return program if any(v in ("-e", "--eval", "-p", "--print", "-c", "-r", "-E") for v in values) else None
            if any(isinstance(e, ast.Constant) and isinstance(e.value, str) and "://" in e.value for e in elements):
                return "url"                                          # 모르는 프로그램의 인자에 주소 글자가 있다
            return None
        if isinstance(command, ast.BinOp) and isinstance(command.op, ast.Add):          # `cmd + ["--", path]` — 목록 덧셈은 프로그램(첫 칸)을 바꾸지 못하므로 앞쪽 목록의 프로그램을 본다
            head = command.left
            if isinstance(head, (ast.List, ast.Tuple)) and head.elts:
                return self.process_kind(head, call)
            if isinstance(head, ast.Name):
                assigned = self.assignments_before(head.id, call.lineno)
                if assigned and all(isinstance(a.value, (ast.List, ast.Tuple)) for a in assigned):
                    kinds = [self.process_kind(a.value, call) for a in assigned]
                    real = [k for k in kinds if k and k != "dynamic"]
                    return real[0] if real else ("dynamic" if "dynamic" in kinds else None)
        return self.text_kind(command)

    def token(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            base = re.split(r"[\\/]", node.value)[-1].lower()
            return base[:-4] if base.endswith(".exe") else base
        return None

    def python_kind(self, rest):
        values = [e.value for e in rest if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if "-m" in values and values.index("-m") + 1 < len(values) and values[values.index("-m") + 1] in ("pip", "http.server", "ensurepip"):
            return "pip"
        if "-c" in values:                                            # `python -c '…'` — 코드 글자 속은 보지 않는다
            return "python-c"
        return None

    def pip_kind(self, rest):
        values = [e.value for e in rest if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        return "pip" if (not rest or any(v in ("install", "download") for v in values) or len(values) != len(rest)) else None

    def git_kind(self, rest):
        index = 0
        while index < len(rest):
            element = rest[index]
            if isinstance(element, ast.Starred) or not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
                return "git:dynamic"
            value = element.value
            if value in GIT_VALUE_OPTIONS:
                index += 2
                continue
            if value.startswith("-"):
                index += 1
                continue
            if value == "archive" and any(self.starts_with_text(e, "--remote") for e in rest[index + 1:]):
                return "git:archive-remote"
            return f"git:{value}" if value in GIT_NET_SUBCOMMANDS else None
        return None

    def text_pieces(self, node):
        """문자열 명령 식의 (글자 조각 목록, 변수 부분이 있는가). 호출·내포 같은 계산이 든 식이면 None(동적 — 무슨 명령이 될지 알 수 없다)."""
        if isinstance(node, ast.Constant):
            return ([node.value] if isinstance(node.value, str) else []), False
        if isinstance(node, ast.JoinedStr):
            out, dynamic = [], False
            for value in node.values:
                got = self.text_pieces(value)
                if got is None:
                    return None
                out = _join_pieces(out, got[0])
                dynamic = dynamic or got[1]
            return out, dynamic
        if isinstance(node, ast.FormattedValue):
            got = self.text_pieces(node.value)
            return None if got is None else (got[0], True)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
            left, right = self.text_pieces(node.left), self.text_pieces(node.right)
            if left is None or right is None:
                return None
            if isinstance(node.op, ast.Add):
                return _join_pieces(left[0], right[0]), left[1] or right[1]
            return left[0] + right[0], left[1] or right[1]
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
            return [], True
        if isinstance(node, (ast.Tuple, ast.List)):
            out, dynamic = [], False
            for element in node.elts:
                got = self.text_pieces(element)
                if got is None:
                    return None
                out += got[0]
                dynamic = dynamic or got[1]
            return out, dynamic
        return None

    def text_kind(self, node):
        """문자열 명령(셸 한 줄)에서 네트워크 도구를 알아본다. 해당 없으면 None, 무슨 명령인지 알 수 없으면 'dynamic'."""
        got = self.text_pieces(node)
        if got is None or not got[0]:
            return "dynamic"
        text = " ".join(got[0])
        match = _GIT_NET_RE.search(text)
        if match:
            return "git:" + re.split(r"\s+", match.group(0).strip())[-1]
        if _PIP_RE.search(text):
            return "pip"
        match = _NET_TOOL_RE.search(text)
        if match:
            return match.group(0).lower().removesuffix(".exe")
        if got[1] and re.match(r"\s*git(?:\.exe)?(?:\s|$)", text, re.I):
            return "git:dynamic"
        if got[1] and self.starts_with_variable(node):
            return "dynamic"                                          # `f'{tool} {u}'`·`tool + ' ' + u`·`'%s %s' % (tool, u)` — 실행할 프로그램 이름이 변수다
        if "://" in text:
            return "url"                                              # 셸 한 줄에 주소 글자가 있다(`cmd /c start 주소` 등)
        return None

    def starts_with_text(self, node, prefix):
        """글자 식(상수·덧셈·f-문자열)의 맨 앞 조각이 prefix 로 시작하는가(`'--remote=' + u`)."""
        if isinstance(node, ast.Constant):
            return isinstance(node.value, str) and node.value.startswith(prefix)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.starts_with_text(node.left, prefix)
        if isinstance(node, ast.JoinedStr) and node.values:
            return self.starts_with_text(node.values[0], prefix)
        return False

    def starts_with_variable(self, node):
        """글자 명령 식의 맨 앞 조각(프로그램 이름 자리)이 변수인가."""
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript, ast.Call, ast.FormattedValue)):
            return True
        if isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and not value.value.strip():
                    continue
                return self.starts_with_variable(value)
            return False
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.starts_with_variable(node.left)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            left = node.left
            return isinstance(left, ast.Constant) and isinstance(left.value, str) and left.value.lstrip().startswith("%")
        return False

    def is_process_name(self, resolved):
        return bool(resolved & PROC_FQNS) or any(f.startswith(PROC_PREFIXES) for f in resolved)

    def visit_Attribute(self, node):
        resolved = self.resolve(node)
        if node.attr in NET_NAMES:
            self.add("net:" + node.attr, node, self.address.get(node))
        elif resolved & NET_FQNS:
            self.add("net:" + sorted(resolved & NET_FQNS)[0], node)
        elif any(f.startswith(NET_FQN_PREFIXES) for f in resolved):
            self.add("net:" + sorted(f for f in resolved if f.startswith(NET_FQN_PREFIXES))[0], node)
        elif node not in self.call_funcs and self.is_process_name(resolved):
            self.add("proc:ref", node)                                   # subprocess.run 을 부르지 않고 넘겨 두는 모양(기본 인자·변수에 담기) — 나중에 어떤 명령으로 불릴지 알 수 없다
        self.generic_visit(node)

    def visit_Name(self, node):
        resolved = self.resolve(node)
        if node.id in NET_NAMES:
            self.add("net:" + node.id, node, self.address.get(node))
        elif resolved & NET_FQNS:
            self.add("net:" + sorted(resolved & NET_FQNS)[0], node)
        elif node not in self.call_funcs and node.id in self.aliases and self.is_process_name(resolved):
            self.add("proc:ref", node)
        elif isinstance(node.ctx, ast.Load) and node.id == "__builtins__":
            self.add("dyn:builtins", node)                               # `__builtins__['exec']` — 내장 이름을 사전으로 꺼낸다
        elif isinstance(node.ctx, ast.Load) and node.id in BUILTIN_EXEC_NAMES and node not in self.call_funcs:
            self.add("dyn:ref:" + node.id, node)                         # `e = eval`·`imp = __import__` — 글자를 코드로 바꾸는 내장 이름을 부르지 않고 넘겨 둔다

    def visit_Subscript(self, node):
        if self.is_dict_view(node.value) and self.net_key(node.slice):
            self.add("dyn:dict-lookup", node)
        elif "sys.modules" in self.resolve(node.value) and not (isinstance(node.slice, ast.Name) and node.slice.id == "__name__") \
                and (not (isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)) or node.slice.value in DYN_MODULE_FQNS):
            self.add("dyn:modules", node)                                # `sys.modules['subprocess'].run` — 이미 불러온 모듈을 이름 글자로 꺼낸다
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in NET_LIBS:
                self.add("lib:" + top, node)
            elif alias.name.startswith(NET_LIB_PREFIXES):
                self.add("lib:" + alias.name, node)
            if alias.name.startswith(SDK_PREFIXES):
                self.add("sdk:" + alias.name, node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        if module.split(".")[0] in NET_LIBS:
            self.add("lib:" + module.split(".")[0], node)
        elif module.startswith(NET_LIB_PREFIXES):
            self.add("lib:" + module, node)
        if any(alias.name == "*" for alias in node.names) and module in STAR_MODULES:
            self.add("dyn:star:" + module, node)                         # `from subprocess import *` — 뒤에 오는 맨 이름 호출(`run(...)`)이 어디서 왔는지 이름으로 알 수 없다
        if module.startswith(SDK_PREFIXES) or (module == "google" and any(a.name in ("genai", "oauth2", "auth", "generativeai", "cloud") for a in node.names)):
            self.add("sdk:" + module, node)
        for alias in node.names:
            if alias.name in NET_NAMES:
                self.add("net:" + alias.name, node)
            elif module == "socket" and alias.name == "socket":
                self.add("net:socket.socket", node)


def scan_source(source, rel):
    """(호출 지점 목록, 함수별 호출 이름 목록). 지점 = Site(파일, 함수, 모양 종류, 줄, 관문 인정 여부, 메모). 함수 이름은 `Class.method`·`outer.inner`, 모듈 바로 아래는 `<module>`.
    호출 목록은 `{(파일, 함수): [(점으로 이은 호출 이름, 줄), ...]}`(참고용 — 관문 인정은 지점에 이미 계산돼 있다)."""
    tree = ast.parse(source)
    scan = _Scan(tree, rel)
    scan.visit(tree)
    return scan.sites, dict(scan.calls)


def is_gated(site, calls=None):
    """지점이 관문(egress.check_url)을 거쳤다고 인정되는가(`scan_source` 가 위 ①–④ 를 따져 계산해 둔 값)."""
    return bool(site.gated)


def is_listed(site, exceptions):
    """지점이 등록 목록(EGRESS_EXCEPTIONS)에 있는가: 같은 파일의 같은 함수이거나, 함수가 "*" 이고 `kinds` 로 모양 종류를 좁힌 항목(종류를 좁히지 않은 와일드카드는 아무것도 면제하지 못한다)."""
    for entry in exceptions:
        if entry.file != site.file or entry.function not in (site.function, "*"):
            continue
        kinds = tuple(getattr(entry, "kinds", ()) or ())
        if entry.function == "*" and not kinds:
            continue
        if kinds and not any(site.kind.startswith(kind) for kind in kinds):
            continue
        return True
    return False


def ungated_unlisted(sites, calls, exceptions):
    """관문을 거쳤다고 인정되지 않고 예외 목록에도 없는 (파일, 함수) 목록."""
    return sorted({(s.file, s.function) for s in sites if not s.gated and not is_listed(s, exceptions)})


# ----------------------------------------------------------------------------
# 트리 읽기
# ----------------------------------------------------------------------------
def _under(rel, prefix):
    return rel == prefix or rel.startswith(prefix + "/")


def all_python_files(root):
    """저장소 안의 모든 *.py(상대 경로, 정렬) — 스캔함·제외 목록 중 하나에 들어 있는지 확인하는 데 쓴다."""
    out = []
    for folder, dirs, files in os.walk(root):
        base = Path(folder).relative_to(root).as_posix()
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not (base == "." and d in SKIP_TOP_DIRS)]
        out += [name if base == "." else f"{base}/{name}" for name in files if name.endswith(".py")]
    return sorted(out)


def python_files(root):
    """스캔 범위(SCAN_ROOTS 아래의 *.py)의 파일 경로(Path)."""
    root = Path(root)
    return [root / rel for rel in all_python_files(root) if any(_under(rel, prefix) for prefix in SCAN_ROOTS)]


def unscoped_files(root):
    """스캔함(SCAN_ROOTS)도 제외(SCAN_EXCLUDED)도 아니거나 둘 다에 걸린 *.py — 비어 있어야 한다(새 최상위 폴더가 생기면 여기 걸린다)."""
    out = []
    for rel in all_python_files(root):
        scanned = any(_under(rel, prefix) for prefix in SCAN_ROOTS)
        excluded = any(_under(rel, prefix) for prefix, _ in SCAN_EXCLUDED)
        if scanned == excluded:
            out.append(rel)
    return out


@functools.lru_cache(maxsize=8)
def _scan_tree_cached(root):
    sites, calls = [], {}
    for path in python_files(root):
        rel = path.relative_to(root).as_posix()
        found, called = scan_source(path.read_text(encoding="utf-8"), rel)
        sites += found
        calls.update(called)
    return tuple(sites), tuple(calls.items())


def scan_tree(root):
    """(지점 목록, 호출 목록) — 호출마다 복사본을 돌려준다(부르는 쪽이 고쳐도 안전)."""
    sites, calls = _scan_tree_cached(str(Path(root).resolve()))
    return list(sites), dict(calls)


# ----------------------------------------------------------------------------
# 워크플로 yml 가벼운 훑기(줄 단위 글자 검색 — .github 는 보호 경로라 읽기만 한다)
# ----------------------------------------------------------------------------
YML_PATTERNS = (
    ("curl", re.compile(r"(?<![\w.-])curl(?:\.exe)?(?![\w-])", re.I)),
    ("wget", re.compile(r"(?<![\w.-])wget(?![\w-])", re.I)),
    ("powershell-web", re.compile(r"(?<![\w.-])(?:Invoke-WebRequest|Invoke-RestMethod|iwr|irm|Start-BitsTransfer)(?![\w-])")),
    ("net-tool", re.compile(r"(?<![\w.-])(?:nslookup|certutil|bitsadmin|telnet|scp|sftp|ncat|netcat)(?![\w-])")),
    ("git", _GIT_NET_RE),
    ("gh", re.compile(r"(?<![\w.-])gh\s+(?:api|pr|issue|run|workflow|release|repo|auth)(?![\w-])")),
    ("pip", _PIP_RE),
    ("python-net", re.compile(r"(?<![\w.])(?:urllib|urlopen|http\.client|requests\.(?:get|post|put|delete|head|request|Session)|socket\.)")),
)


def yml_files(root):
    base = Path(root) / ".github"
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*") if p.is_file() and p.suffix in (".yml", ".yaml"))


def scan_yml(root):
    """[(상대 경로, 종류, 줄 번호)] — 주석이 아닌 줄에서 네트워크 도구·명령 글자를 찾는다."""
    root = Path(root)
    out = []
    for path in yml_files(root):
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for kind, pattern in YML_PATTERNS:
                if pattern.search(stripped):
                    out.append((rel, kind, number))
    return out
