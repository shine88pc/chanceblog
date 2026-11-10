"""외부 호출 관문(pipeline/egress.py) 시험.

- 관문: 운영 호스트의 목적×경로 규칙(OPS_RULES), 허용 목록의 `fact` 목적, 거부 문구, 검사된 opener(리다이렉트 재판정)와 최종 주소 재판정.
- 호출 목록: 저장소의 파이썬 소스에서 '알려진 모양'(tests/egress_scan.py 머리말)의 외부 접속 지점을 AST 로 모아 등록 목록(egress.EGRESS_EXCEPTIONS)과 비교한다.
  **보증이 아니다** — 새 모양·동적 코드·소스 밖의 일은 잡지 못하고(BLIND_SPOT_SHAPES 가 잡지 못하는 모양을 못박는다), 사람 검토가 마지막 방어선이다.
- 스캔 범위를 못박는다(tests/ 밖의 모든 *.py 는 스캔함 또는 제외(이유) 중 하나)·워크플로 yml 의 네트워크 도구 줄 등록.

네트워크를 쓰지 않는다 — 소스를 읽기만 하고 opener 시험은 가짜 전송(처리기)을 끼운다(요청은 한 번도 보내지 않는다)."""
import ast
import email
import io
import re
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import _bootstrap  # noqa: F401
from egress_scan import (SCAN_EXCLUDED, SCAN_ROOTS, Site, all_python_files, is_gated, is_listed, python_files, scan_source, scan_tree, scan_yml,  # noqa: F401  (재노출 — 검증자 도구·문서 시험이 쓴다)
                         ungated_unlisted, unscoped_files)
from pipeline import egress, source_registry as sr
from source_registry_helpers import GOOD_HOST, TODAY, good_provider, registry_data

ROOT = _bootstrap.ROOT

# ----------------------------------------------------------------------------
# 독립 검증(SRCV)이 새 모듈에 심은 56가지 모양 — 전부 '관문을 거치지 않고 등록되지 않은 지점'으로 잡혀야 한다(고치기 전에는 20개만 잡혔다). 모양 하나가 소스 한 조각이다.
# ----------------------------------------------------------------------------
PROBE_SHAPES = [
    ("direct urllib.request.urlopen", "import urllib.request\ndef f(u):\n    return urllib.request.urlopen(u)\n"),
    ("from urllib.request import urlopen as u", "from urllib.request import urlopen as _u\ndef f(u):\n    return _u(u)\n"),
    ("import urllib.request as r; r.urlopen", "import urllib.request as r\ndef f(u):\n    return r.urlopen(u)\n"),
    ("getattr(urllib.request, 'urlopen')", "import urllib.request\ndef f(u):\n    return getattr(urllib.request, 'urlopen')(u)\n"),
    ("getattr with concatenated name", "import urllib.request\ndef f(u):\n    return getattr(urllib.request, 'url' + 'open')(u)\n"),
    ("urllib.request.__dict__['urlopen']", "import urllib.request\ndef f(u):\n    return urllib.request.__dict__['urlopen'](u)\n"),
    ("importlib.import_module + getattr", "import importlib\ndef f(u):\n    m = importlib.import_module('urllib.' + 'request')\n    return getattr(m, 'urlopen')(u)\n"),
    ("importlib.import_module(...).urlopen attr", "import importlib\ndef f(u):\n    return importlib.import_module('urllib.request').urlopen(u)\n"),
    ("__import__('urllib.request').request.urlopen", "def f(u):\n    return __import__('urllib.request').request.urlopen(u)\n"),
    ("eval string", "def f(u):\n    return eval('__import__(\"urllib.request\").request.urlopen')(u)\n"),
    ("exec string", "def f(u):\n    exec('import urllib.request as q; q.urlopen(u)')\n"),
    ("OpenerDirector().open", "import urllib.request\ndef f(u):\n    o = urllib.request.OpenerDirector()\n    o.add_handler(urllib.request.HTTPSHandler())\n    return o.open(u)\n"),
    ("urllib.request.URLopener().open", "import urllib.request\ndef f(u):\n    return urllib.request.URLopener().open(u)\n"),
    ("urllib.request.HTTPSHandler + build_opener", "import urllib.request\ndef f(u):\n    return urllib.request.build_opener(urllib.request.HTTPSHandler()).open(u)\n"),
    ("http.client.HTTPSConnection", "import http.client\ndef f(h):\n    return http.client.HTTPSConnection(h)\n"),
    ("http.client alias hc", "import http.client as hc\ndef f(h):\n    return hc.HTTPSConnection(h)\n"),
    ("from http import client; client.HTTPSConnection", "from http import client\ndef f(h):\n    return client.HTTPSConnection(h)\n"),
    ("getattr(http.client, 'HTTPSConnection')", "import http.client\ndef f(h):\n    return getattr(http.client, 'HTTPS' + 'Connection')(h)\n"),
    ("socket.create_connection", "import socket\ndef f(h):\n    return socket.create_connection((h, 443))\n"),
    ("socket.socket().connect", "import socket\ndef f(h):\n    s = socket.socket()\n    s.connect((h, 443))\n    return s\n"),
    ("socket.getaddrinfo (DNS leak)", "import socket\ndef f(h):\n    return socket.getaddrinfo(h, 443)\n"),
    ("ssl.create_default_context().wrap_socket + socket", "import socket, ssl\ndef f(h):\n    c = ssl.create_default_context()\n    return c.wrap_socket(socket.socket(), server_hostname=h)\n"),
    ("asyncio.open_connection", "import asyncio\nasync def f(h):\n    return await asyncio.open_connection(h, 443)\n"),
    ("subprocess curl", "import subprocess\ndef f(u):\n    return subprocess.run(['curl', '-s', u], capture_output=True).stdout\n"),
    ("subprocess powershell Invoke-WebRequest", "import subprocess\ndef f(u):\n    return subprocess.run(['powershell', '-c', 'iwr ' + u], capture_output=True).stdout\n"),
    ("subprocess git clone/ls-remote url", "import subprocess\ndef f(u):\n    return subprocess.run(['git', 'ls-remote', u], capture_output=True).stdout\n"),
    ("os.system curl", "import os\ndef f(u):\n    return os.system('curl ' + u)\n"),
    ("os.popen wget", "import os\ndef f(u):\n    return os.popen('wget -qO- ' + u).read()\n"),
    ("requests (top-level import)", "import requests\ndef f(u):\n    return requests.get(u)\n"),
    ("requests lazy import in function", "def f(u):\n    import requests\n    return requests.get(u)\n"),
    ("importlib requests", "import importlib\ndef f(u):\n    return importlib.import_module('requests').get(u)\n"),
    ("urllib3 import", "import urllib3\ndef f(u):\n    return urllib3.PoolManager().request('GET', u)\n"),
    ("urllib3 from-import", "from urllib3 import PoolManager\ndef f(u):\n    return PoolManager().request('GET', u)\n"),
    ("httpx", "import httpx\ndef f(u):\n    return httpx.get(u)\n"),
    ("aiohttp", "import aiohttp\nasync def f(u):\n    async with aiohttp.ClientSession() as s:\n        return await s.get(u)\n"),
    ("pycurl", "import pycurl\ndef f(u):\n    c = pycurl.Curl()\n    c.setopt(c.URL, u)\n"),
    ("httplib2", "import httplib2\ndef f(u):\n    return httplib2.Http().request(u)\n"),
    ("feedparser.parse(url)", "import feedparser\ndef f(u):\n    return feedparser.parse(u)\n"),
    ("xml.sax.parse(url) (fetches remote)", "import xml.sax\ndef f(u, h):\n    xml.sax.parse(u, h)\n"),
    ("xml.dom.minidom.parse(url)", "import xml.dom.minidom\ndef f(u):\n    return xml.dom.minidom.parse(u)\n"),
    ("pandas.read_csv(url)", "import pandas\ndef f(u):\n    return pandas.read_csv(u)\n"),
    ("ftplib", "import ftplib\ndef f(h):\n    return ftplib.FTP(h)\n"),
    ("smtplib", "import smtplib\ndef f(h):\n    return smtplib.SMTP_SSL(h)\n"),
    ("xmlrpc.client.ServerProxy", "import xmlrpc.client\ndef f(u):\n    return xmlrpc.client.ServerProxy(u)\n"),
    ("webbrowser.open", "import webbrowser\ndef f(u):\n    webbrowser.open(u)\n"),
    ("ctypes wininet", "import ctypes\ndef f(u):\n    ctypes.windll.wininet.InternetOpenUrlW(0, u, None, 0, 0, 0)\n"),
    ("google genai SDK import", "def f():\n    from google import genai\n    return genai.Client()\n"),
    ("google genai via importlib", "import importlib\ndef f():\n    return importlib.import_module('google.genai')\n"),
    ("googleapiclient discovery.build", "def f():\n    from googleapiclient.discovery import build\n    return build('blogger', 'v3')\n"),
    ("opener passed as default arg (reference only)", "import urllib.request\ndef f(u, opener=urllib.request.urlopen):\n    return opener(u)\n"),
    ("urlopen reference stored in module global", "import urllib.request\n_OPEN = urllib.request.urlopen\ndef f(u):\n    return _OPEN(u)\n"),
    ("fake gate: gate call with constant url then real url", "import urllib.request\ndef f(u):\n    source_policy.egress_gate('https://x.example/', 'fact', None)\n    return urllib.request.urlopen(u)\n"),
    ("fake gate: gate call inside dead branch", "import urllib.request\ndef f(u):\n    if False:\n        egress.check_url(u, 'fact', None)\n    return urllib.request.urlopen(u)\n"),
    ("fake gate: gate call in try with swallowed exception", "import urllib.request\ndef f(u):\n    try:\n        egress.check_url(u, 'fact', None)\n    except Exception:\n        pass\n    return urllib.request.urlopen(u)\n"),
    ("gate with different url variable than fetched", "import urllib.request\ndef f(u, v):\n    egress.check_url(u, 'fact', None)\n    return urllib.request.urlopen(v)\n"),
    ("gate result ignored (egress_gate no-op in legacy)", "import urllib.request\ndef f(u):\n    source_policy.egress_gate(u, 'feed', now)\n    return urllib.request.urlopen(u)\n"),
]

# 검증자의 5종(고치기 전 '놓침' 가운데 대표): getattr·curl·socket·feedparser·상수 관문
THE_FIVE_LABELS = ("getattr(urllib.request, 'urlopen')", "subprocess curl", "socket.socket().connect", "feedparser.parse(url)", "fake gate: gate call with constant url then real url")

# 지금도 잡지 못하는 모양(원리상 정적으로 보이지 않거나, 알려진 목록에 없는 것). 이 표가 docs/SOURCE_POLICY.md 7절의 사각지대 표와 같다 — 스캐너가 더 잘 보게 되면 이 시험이 알려 주니 문서 표와 함께 고친다.
BLIND_SPOT_SHAPES = [
    ("다른 파이썬 파일을 하위 프로세스로 실행", "import subprocess, sys\ndef f():\n    return subprocess.run([sys.executable, 'elsewhere.py'], check=True)\n", "그 파일이 스캔 범위 밖이면 거기서 하는 일을 볼 수 없다(범위 안이면 그 파일에서 따로 잡힌다)"),
    ("목록에 없는 새 SDK", "import stripe\ndef f():\n    return stripe.Charge.list()\n", "네트워크 라이브러리·SDK 목록은 유한하다"),
    ("넘겨받은 실행기가 부르는 명령", "def f(runner, url):\n    return runner(['curl', url])\n", "실행기를 부르는 자리(호출한 쪽의 `subprocess.run` 참조는 proc:ref 로 잡히지만 명령 내용은 보지 않는다)"),
    ("numpy.loadtxt 가 주소를 읽음", "import numpy as np\ndef f(u):\n    return np.loadtxt(u)\n", "numpy 같은 일반 계산 라이브러리는 목록에 올릴 수 없다(주소를 읽을 수 있는 함수 이름의 목록이 따로 없다)"),
    ("UNC 경로를 파일처럼 열기", "def f(host):\n    return open('//' + host + '/share/x.txt').read()\n", "네트워크 드라이브·UNC 경로는 파일 열기라 네트워크 이름이 없다 — 파일 열기는 보지 않는다"),
]


def kinds_of(source, rel="pipeline/x.py"):
    sites, _ = scan_source(source, rel)
    return sorted(site.kind for site in sites)


def unlisted_for(source, rel="pipeline/planted_probe.py", exceptions=None):
    sites, calls = scan_source(source, rel)
    return ungated_unlisted(sites, calls, egress.EGRESS_EXCEPTIONS if exceptions is None else exceptions)


# ----------------------------------------------------------------------------
# 스캐너 단위 시험
# ----------------------------------------------------------------------------
class ScannerSelfTest(unittest.TestCase):
    """스캐너가 무엇을 지점으로 보고 무엇을 보지 않는지(이 시험이 거짓 음성·거짓 양성으로 무너지지 않게)."""

    def kinds(self, source):
        sites, _ = scan_source(source, "x.py")
        return sorted((s.function, s.kind) for s in sites)

    def test_direct_calls_and_references_are_sites(self):
        self.assertEqual(self.kinds("import urllib.request\ndef f(u):\n    return urllib.request.urlopen(u)\n"), [("f", "net:urlopen")])
        self.assertEqual(self.kinds("import urllib.request\nclass C:\n    def __init__(self, opener=None):\n        self._open = opener or urllib.request.urlopen\n"), [("C.__init__", "net:urlopen")])
        self.assertEqual(self.kinds("import urllib.request\ndef fetch(u, opener=urllib.request.urlopen):\n    pass\n"), [("fetch", "net:urlopen")])
        self.assertEqual(self.kinds("from urllib.request import urlopen\ndef f(u):\n    urlopen(u)\n"), [("<module>", "net:urlopen"), ("f", "net:urlopen")])
        self.assertEqual(self.kinds("import socket\ndef f():\n    socket.create_connection(('a', 1))\n"), [("f", "net:create_connection")])
        self.assertEqual(self.kinds("import http.client\ndef f():\n    http.client.HTTPSConnection('a')\n"), [("f", "net:HTTPSConnection")])
        self.assertEqual(self.kinds("import urllib.request\ndef f():\n    o = urllib.request.build_opener()\n    urllib.request.install_opener(o)\n    urllib.request.urlretrieve('u')\n"),
                         [("f", "net:build_opener"), ("f", "net:install_opener"), ("f", "net:urlretrieve")])
        self.assertEqual(self.kinds("def outer():\n    def inner(u):\n        import requests\n        return requests.get(u)\n"), [("outer.inner", "lib:requests")])
        self.assertEqual(self.kinds("import requests\n"), [("<module>", "lib:requests")])
        self.assertEqual(self.kinds("from requests import get\n"), [("<module>", "lib:requests")])
        self.assertEqual(self.kinds("import httpx, aiohttp, urllib3\n"), [("<module>", "lib:aiohttp"), ("<module>", "lib:httpx"), ("<module>", "lib:urllib3")])

    def test_sdk_clients_are_sites(self):
        self.assertEqual(self.kinds("def get_client():\n    from google import genai\n    return genai.Client()\n"), [("get_client", "sdk:google")])
        self.assertEqual(self.kinds("def s():\n    from googleapiclient.discovery import build\n"), [("s", "sdk:googleapiclient.discovery")])
        self.assertEqual(self.kinds("def s():\n    from google.oauth2.credentials import Credentials\n"), [("s", "sdk:google.oauth2.credentials")])
        self.assertEqual(self.kinds("def s():\n    from google.auth.transport.requests import Request\n"), [("s", "sdk:google.auth.transport.requests")])
        self.assertEqual(self.kinds("def s():\n    import google_auth_oauthlib.flow\n"), [("s", "sdk:google_auth_oauthlib.flow")])

    def test_harmless_lookalikes_are_not_sites(self):
        for source in ("import socket\ntry:\n    pass\nexcept socket.timeout:\n    pass\n", "import http.client\ntry:\n    pass\nexcept http.client.HTTPException:\n    pass\n",
                       "def run(requests):\n    requests.append(1)\n", "import urllib.parse\ndef f(u):\n    return urllib.parse.urlparse(u)\n", "import urllib.request\nreq = urllib.request.Request('u')\n",
                       "import subprocess\nsubprocess.run(['git'])\n", "def urlopen_like():\n    pass\n", "import subprocess\nsubprocess.run(['git', 'status', '--short'])\n",
                       "import subprocess\nsubprocess.run(['git', '-C', 'x', 'log', '-1'])\n", "import subprocess, sys\nsubprocess.run([sys.executable, '-m', 'unittest'])\n",
                       "import os\nos.system('echo hello')\n", "import ast\ntree = ast.parse('x = 1')\n", "def f(o):\n    return getattr(o, 'name', None)\n", "def f(d):\n    return d.get('urlopen')\n",
                       "import json\nx = json.load(open('a.json'))\n", "import socket\nname = socket.gethostname()\n"):
            self.assertEqual(self.kinds(source), [], source)

    def test_every_listed_shape_is_a_site_of_the_expected_kind(self):
        table = [
            ("getattr(urllib.request, 'urlopen')(u)", "import urllib.request\ndef f(u):\n    return getattr(urllib.request, 'urlopen')(u)\n", "dyn:getattr"),
            ("getattr with a computed name", "def f(m, n):\n    return getattr(m, n)(1)\n", "dyn:getattr"),
            ("getattr of a network name", "def f(m):\n    return getattr(m, 'urlopen')\n", "dyn:getattr"),
            ("__dict__[...]", "import urllib.request\ndef f():\n    return urllib.request.__dict__['urlopen']\n", "dyn:dict-lookup"),
            ("vars(...).get(...)", "import urllib.request\ndef f():\n    return vars(urllib.request).get('urlopen')\n", "dyn:dict-lookup"),
            ("globals()[name]", "def f(n):\n    return globals()[n]\n", "dyn:dict-lookup"),
            ("importlib.import_module", "import importlib\ndef f(n):\n    return importlib.import_module(n)\n", "dyn:import"),
            ("__import__", "def f(n):\n    return __import__(n)\n", "dyn:import"),
            ("runpy.run_path", "import runpy\ndef f(p):\n    return runpy.run_path(p)\n", "dyn:import"),
            ("eval", "def f(s):\n    return eval(s)\n", "dyn:eval"),
            ("exec", "def f(s):\n    exec(s)\n", "dyn:exec"),
            ("OpenerDirector", "import urllib.request\ndef f():\n    return urllib.request.OpenerDirector()\n", "net:OpenerDirector"),
            ("URLopener", "import urllib.request\ndef f():\n    return urllib.request.URLopener()\n", "net:URLopener"),
            ("FancyURLopener", "import urllib.request\ndef f():\n    return urllib.request.FancyURLopener()\n", "net:FancyURLopener"),
            ("HTTPSHandler", "import urllib.request\ndef f():\n    return urllib.request.HTTPSHandler()\n", "net:HTTPSHandler"),
            ("socket.socket", "import socket\ndef f():\n    return socket.socket()\n", "net:socket.socket"),
            ("socket aliased module", "import socket as sk\ndef f():\n    return sk.socket()\n", "net:socket.socket"),
            ("from socket import socket", "from socket import socket as S\ndef f():\n    return S()\n", "net:socket.socket"),
            ("getaddrinfo", "import socket\ndef f(h):\n    return socket.getaddrinfo(h, 443)\n", "net:getaddrinfo"),
            ("gethostbyname", "import socket\ndef f(h):\n    return socket.gethostbyname(h)\n", "net:gethostbyname"),
            ("wrap_socket", "def f(c, s):\n    return c.wrap_socket(s)\n", "net:wrap_socket"),
            ("asyncio.open_connection", "import asyncio\nasync def f(h):\n    return await asyncio.open_connection(h, 443)\n", "net:open_connection"),
            ("pycurl", "import pycurl\n", "lib:pycurl"), ("httplib2", "from httplib2 import Http\n", "lib:httplib2"), ("feedparser", "import feedparser\n", "lib:feedparser"),
            ("ftplib", "import ftplib\n", "lib:ftplib"), ("smtplib", "import smtplib\n", "lib:smtplib"), ("xmlrpc", "import xmlrpc.client\n", "lib:xmlrpc"),
            ("webbrowser", "import webbrowser\n", "lib:webbrowser"), ("ctypes", "import ctypes\n", "lib:ctypes"), ("telnetlib", "import telnetlib\n", "lib:telnetlib"),
            ("poplib", "import poplib\n", "lib:poplib"), ("imaplib", "import imaplib\n", "lib:imaplib"), ("nntplib", "import nntplib\n", "lib:nntplib"),
            ("xml.sax.parse", "import xml.sax\ndef f(u, h):\n    xml.sax.parse(u, h)\n", "parse:xml.sax.parse"),
            ("minidom.parse", "import xml.dom.minidom\ndef f(u):\n    return xml.dom.minidom.parse(u)\n", "parse:xml.dom.minidom.parse"),
            ("pulldom.parse", "import xml.dom.pulldom\ndef f(u):\n    return xml.dom.pulldom.parse(u)\n", "parse:xml.dom.pulldom.parse"),
            ("ElementTree.parse (alias)", "import xml.etree.ElementTree as ET\ndef f(u):\n    return ET.parse(u)\n", "parse:xml.etree.ElementTree.parse"),
            ("pandas.read_csv (alias)", "import pandas as pd\ndef f(u):\n    return pd.read_csv(u)\n", "parse:pandas.read_csv"),
        ]
        for label, source, expected in table:
            with self.subTest(label=label):
                self.assertIn(expected, kinds_of(source), label)

    def test_process_commands_are_judged_by_their_program_and_by_being_dynamic(self):
        table = [
            ("subprocess.run(['curl', '-s', u])", "import subprocess\ndef f(u):\n    subprocess.run(['curl', '-s', u])\n", "proc:curl"),
            ("wget", "import subprocess\ndef f(u):\n    subprocess.check_output(['wget', '-qO-', u])\n", "proc:wget"),
            ("powershell with a computed command", "import subprocess\ndef f(u):\n    subprocess.run(['powershell', '-c', 'iwr ' + u])\n", "proc:dynamic"),
            ("powershell with Invoke-WebRequest text", "import subprocess\nsubprocess.run(['powershell', '-c', 'Invoke-WebRequest x'])\n", "proc:invoke-webrequest"),
            ("certutil", "import subprocess\nsubprocess.run(['certutil', '-urlcache', 'x'])\n", "proc:certutil"),
            ("ssh", "import subprocess\nsubprocess.run(['ssh', 'host'])\n", "proc:ssh"),
            ("gh", "import subprocess\nsubprocess.run(['gh', 'pr', 'list'])\n", "proc:gh"),
            ("git ls-remote", "import subprocess\nsubprocess.run(['git', 'ls-remote', 'u'])\n", "proc:git:ls-remote"),
            ("git push after -C", "import subprocess\nsubprocess.run(['git', '-C', 'x', 'push'])\n", "proc:git:push"),
            ("git with starred args", "import subprocess\ndef f(*a):\n    subprocess.run(['git', *a])\n", "proc:git:dynamic"),
            ("git with a computed subcommand", "import subprocess\ndef f(s):\n    subprocess.run(['git', s])\n", "proc:git:dynamic"),
            ("git clone as text", "import os\nos.system('git clone https://x.example/r.git')\n", "proc:git:clone"),
            ("command is a parameter", "import subprocess\ndef f(cmd):\n    subprocess.run(cmd)\n", "proc:dynamic"),
            ("command list assigned first", "import subprocess\ndef f(u):\n    cmd = ['curl', u]\n    subprocess.run(cmd)\n", "proc:curl"),
            ("sys.executable -m pip install", "import subprocess, sys\nsubprocess.run([sys.executable, '-m', 'pip', 'install', 'x'])\n", "proc:pip"),
            ("pip install text", "import os\nos.system('pip install x')\n", "proc:pip"),
            ("os.system with a curl text", "import os\ndef f(u):\n    os.system('curl ' + u)\n", "proc:curl"),
            ("os.system f-string", "import os\ndef f(u):\n    os.system(f'curl {u}')\n", "proc:curl"),
            ("os.popen wget", "import os\ndef f(u):\n    return os.popen('wget -qO- ' + u).read()\n", "proc:wget"),
            ("os.system of a name", "import os\ndef f(c):\n    os.system(c)\n", "proc:dynamic"),
            ("os.system of a call result", "import os\ndef f(c):\n    os.system(build(c, 'x'))\n", "proc:dynamic"),
            ("os.system of an environment lookup", "import os\nos.system(os.environ['CMD'])\n", "proc:dynamic"),
            ("a computed git text", "import os\ndef f(s):\n    os.system('git ' + s)\n", "proc:git:dynamic"),
            ("os.execv of a curl path", "import os\nos.execv('/usr/bin/curl', ['curl'])\n", "proc:curl"),
            ("os.spawnv dynamic", "import os\ndef f(p):\n    os.spawnv(os.P_WAIT, p, [p])\n", "proc:dynamic"),
            ("subprocess.run kept as a value", "import subprocess\ndef f(runner=subprocess.run):\n    return runner\n", "proc:ref"),
            ("subprocess.run assigned to a name", "import subprocess\nrunner = subprocess.run\n", "proc:ref"),
            ("from subprocess import run, then used", "from subprocess import run\ndef f(c):\n    run(c)\n", "proc:dynamic"),
        ]
        for label, source, expected in table:
            with self.subTest(label=label):
                self.assertIn(expected, kinds_of(source), label)
        self.assertNotIn("proc:ref", kinds_of("import subprocess\nsubprocess.run(['git', 'status'])\n"))                    # 부르는 것은 참조가 아니다

    def test_the_planted_file_name_and_function_name_are_what_the_registry_is_keyed_by(self):
        sites, _ = scan_source("import urllib.request\nclass A:\n    def m(self, u):\n        def inner():\n            return urllib.request.urlopen(u)\n        return inner\n", "pipeline/z.py")
        self.assertEqual([(s.file, s.function) for s in sites], [("pipeline/z.py", "A.m.inner")])


class GateRecognitionTest(unittest.TestCase):
    """관문 인정 기준(P01·SRCV2 D1): 같은 주소 식·앞서 호출·지배·상수만으로는 안 됨·legacy 에서 아무 일도 안 하는 호출은 관문이 아님·관문 이름은 오직 pipeline.egress 를 가리키는 import 로만·
    모든 핸들러가 끝에서 무조건 raise 할 때만 try 안의 관문 인정·반복문 이월 대입·람다·내포·분기마다 다른 Request 는 인정 안 함."""

    PREFIX = "from pipeline import egress\n"        # 아래 사례 소스는 이 한 줄(관문 모듈 import)을 앞에 붙여 시험한다 — 이름을 import 없이 쓰는 모양은 UNGATED_BY_NAME 에 따로 있다

    def left(self, source, exceptions=(), prefix=True):
        return unlisted_for((self.PREFIX if prefix else "") + source, "x.py", exceptions)

    GATED = [
        ("gate before urlopen", "def f(u):\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("Request built from the same address", "def f(u):\n    egress.check_url(u, 'fact', reg)\n    req = urllib.request.Request(u, headers={'A': 'b'})\n    return urllib.request.urlopen(req, timeout=5)\n"),
        ("Request inline in a with", "def f(u):\n    egress.check_url(u, 'fact', reg)\n    with urllib.request.urlopen(urllib.request.Request(u), timeout=5) as r:\n        return r.read()\n"),
        ("constant-key subscript address", "def f(src):\n    egress.check_url(src['url'], 'fact', reg)\n    return urllib.request.urlopen(src['url'])\n"),
        ("the very same constant", "def f():\n    egress.check_url('https://x.example/a', 'fact', reg)\n    return urllib.request.urlopen('https://x.example/a')\n"),
        ("gate and call in the same if body", "def f(u):\n    if u:\n        egress.check_url(u, 'fact', reg)\n        return urllib.request.urlopen(u)\n"),
        ("gate in a try whose handler re-raises", "def f(u):\n    try:\n        egress.check_url(u, 'fact', reg)\n    except egress.EgressDenied as exc:\n        raise AdapterError('EGRESS_DENIED') from exc\n    return urllib.request.urlopen(u)\n"),
        ("aliased module", "from pipeline import egress as eg\ndef f(u):\n    eg.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("from-import of the function", "from pipeline.egress import check_url\ndef f(u):\n    check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("an f-string address", "def f(h):\n    egress.check_url(f'https://{h}/x', 'fact', reg)\n    return urllib.request.urlopen(f'https://{h}/x')\n"),
        ("keyword url", "def f(u):\n    egress.check_url(url=u, purpose='fact', registry=reg)\n    return urllib.request.urlopen(u)\n"),
        ("call in a loop body after the gate in the same body", "def f(us):\n    for u in us:\n        egress.check_url(u, 'fact', reg)\n        urllib.request.urlopen(u)\n"),
        ("every handler ends in a bare raise after logging", "def f(u):\n    try:\n        egress.check_url(u, 'fact', reg)\n    except egress.EgressDenied as exc:\n        log(exc)\n        raise\n    return urllib.request.urlopen(u)\n"),
        ("a Request bound once from the same address", "def f(u):\n    egress.check_url(u, 'fact', reg)\n    req = urllib.request.Request(u, headers={'A': 'b'})\n    return urllib.request.urlopen(req, timeout=5)\n"),
        ("a gate in the middle of the try body with an always-raising handler", "def f(u):\n    try:\n        prepare()\n        egress.check_url(u, 'fact', reg)\n    except Exception:\n        raise\n    return urllib.request.urlopen(u)\n"),
    ]
    # 이름 풀이가 관문 인정을 좌우하는 사례(앞 PREFIX 를 붙이지 않는다) — 진짜 관문은 인정, 나머지는 인정하지 않는다(SRCV2 D1-7–D1-10).
    GATED_BY_NAME = [
        ("import pipeline.egress with the dotted name", "import pipeline.egress\ndef f(u):\n    pipeline.egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("aliased module", "from pipeline import egress as eg\ndef f(u):\n    eg.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("from-import of the function", "from pipeline.egress import check_url\ndef f(u):\n    check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("a lazy import inside the function", "def f(u):\n    from pipeline import egress\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
    ]
    UNGATED_BY_NAME = [
        ("the name is used without any import", "def f(u):\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("egress is a parameter, not the module", "from pipeline import egress as _gate\ndef f(u, egress):\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("egress is a local object that shadows the module name", "from pipeline import egress\nclass _Noop:\n    def check_url(self, *a, **k):\n        return None\ndef f(u):\n    egress = _Noop()\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("import egress is a different module", "import egress\ndef f(u):\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("the module name is rebound inside the function after the import", "from pipeline import egress\ndef f(u, eg2):\n    egress = eg2\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("the module name is rebound by a for target", "from pipeline import egress\ndef f(u, gates):\n    for egress in gates:\n        pass\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("the module name is rebound by a with target", "from pipeline import egress\ndef f(u, ctx):\n    with ctx as egress:\n        pass\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("two imports give the same name two meanings", "from pipeline import egress\nfrom elsewhere import egress\ndef f(u):\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("a function named like the module", "from pipeline import egress\ndef egress():\n    pass\ndef f(u):\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("a star import makes every name uncertain", "from pipeline import egress\nfrom helpers import *\ndef f(u):\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("the gate function is imported from another module", "from pipeline.other import check_url\ndef f(u):\n    check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
    ]
    UNGATED = [
        ("no gate at all", "def f(u):\n    return urllib.request.urlopen(u)\n"),
        ("gate after the call", "def f(u):\n    x = urllib.request.urlopen(u)\n    egress.check_url(u, 'fact', reg)\n    return x\n"),
        ("a different variable than the one fetched", "def f(u, v):\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(v)\n"),
        ("a constant gate then the real address", "def f(u):\n    egress.check_url('https://x.example/', 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("gate in a dead branch", "def f(u):\n    if False:\n        egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("gate in a conditional branch only", "def f(u, mode):\n    if mode == 'x':\n        egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("gate in a loop body, call after the loop", "def f(us):\n    for u in us:\n        egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("gate in a try whose exception is swallowed", "def f(u):\n    try:\n        egress.check_url(u, 'fact', reg)\n    except Exception:\n        pass\n    return urllib.request.urlopen(u)\n"),
        ("gate in a try that only logs", "def f(u):\n    try:\n        egress.check_url(u, 'fact', reg)\n    except egress.EgressDenied:\n        log('no')\n    return urllib.request.urlopen(u)\n"),
        ("gate in a try whose handler returns instead of raising", "def f(u):\n    try:\n        egress.check_url(u, 'fact', reg)\n    except egress.EgressDenied:\n        return None\n    return urllib.request.urlopen(u)\n"),
        ("gate in a try whose finally swallows by returning", "def f(u):\n    try:\n        egress.check_url(u, 'fact', reg)\n    finally:\n        return urllib.request.urlopen(u)\n"),
        ("gate inside a with block", "def f(u):\n    with ctx():\n        egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("gate in an except handler", "def f(u):\n    try:\n        pass\n    except Exception:\n        egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("gate in a nested function", "def f(u):\n    def g():\n        egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("gate in the other branch", "def f(u, a):\n    if a:\n        egress.check_url(u, 'fact', reg)\n    else:\n        return urllib.request.urlopen(u)\n    return None\n"),
        ("source_policy.egress_gate does nothing in legacy", "def f(u):\n    source_policy.egress_gate(u, 'feed', now)\n    return urllib.request.urlopen(u)\n"),
        ("an unresolved bare check_url name", "def f(u):\n    check_url(u)\n    return urllib.request.urlopen(u)\n"),
        ("the address is reassigned between the gate and the call", "def f(u):\n    egress.check_url(u, 'fact', reg)\n    u = other()\n    return urllib.request.urlopen(u)\n"),
        ("an address with a call in it", "def f(u):\n    egress.check_url(u.strip(), 'fact', reg)\n    return urllib.request.urlopen(u.strip())\n"),
        ("the gate result is assigned, not a statement", "def f(u):\n    ok = egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("a request variable that came from elsewhere", "def f(u, req):\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(req)\n"),
        ("a Request built from another address", "def f(u, v):\n    egress.check_url(u, 'fact', reg)\n    req = urllib.request.Request(v)\n    return urllib.request.urlopen(req)\n"),
        ("the gate is in another function", "def g(u):\n    egress.check_url(u, 'fact', reg)\ndef f(u):\n    return urllib.request.urlopen(u)\n"),
        ("only a reference, no call to bind an address to", "def f(u):\n    egress.check_url(u, 'fact', reg)\n    opener = urllib.request.urlopen\n    return opener(u)\n"),
        ("a module-level call after a gate in a function", "def g(u):\n    egress.check_url(u, 'fact', reg)\nurllib.request.urlopen('https://x.example/')\n"),
        # -- SRCV2 D1: 문서가 적은 인정 기준과 코드가 달랐던 열 가지 모양(고친 뒤 모두 인정하지 않는다) + 같은 부류 ------------------------------------------------------------------
        ("D1-1 a gate in an except handler body followed by raise", "def f(u):\n    try:\n        pass\n    except Exception:\n        egress.check_url(u, 'fact', reg)\n        raise\n    return urllib.request.urlopen(u)\n"),
        ("D1-2 a handler whose raise is in a dead branch", "def f(u):\n    try:\n        egress.check_url(u, 'fact', reg)\n    except Exception:\n        if False:\n            raise\n    return urllib.request.urlopen(u)\n"),
        ("D1-3 a handler that re-raises only when strict", "def f(u, strict=False):\n    try:\n        egress.check_url(u, 'fact', reg)\n    except Exception:\n        if strict:\n            raise\n    return urllib.request.urlopen(u)\n"),
        ("D1-4 an address changed after the call inside a loop", "def f(u, nxt):\n    egress.check_url(u, 'fact', reg)\n    while True:\n        urllib.request.urlopen(u)\n        u = nxt()\n"),
        ("D1-5 a lambda that reads the address later", "def f(u):\n    egress.check_url(u, 'fact', reg)\n    g = lambda: urllib.request.urlopen(u)\n    u = 'https://evil.example/'\n    return g()\n"),
        ("D1-6 a Request assigned differently in the two branches", "def f(u, evil, flag):\n    if flag:\n        req = urllib.request.Request(evil)\n    else:\n        req = urllib.request.Request(u)\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(req)\n"),
        ("a handler that returns on one path before raising", "def f(u):\n    try:\n        egress.check_url(u, 'fact', reg)\n    except Exception:\n        if u:\n            return None\n        raise\n    return urllib.request.urlopen(u)\n"),
        ("a handler that breaks out of a surrounding loop before raising", "def f(us):\n    for u in us:\n        try:\n            egress.check_url(u, 'fact', reg)\n        except Exception:\n            if not u:\n                break\n            raise\n        urllib.request.urlopen(u)\n"),
        ("a gate in the else clause of a try", "def f(u):\n    try:\n        pass\n    except Exception:\n        raise\n    else:\n        egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("a gate in a finally clause", "def f(u):\n    try:\n        pass\n    finally:\n        egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"),
        ("an attribute of the address changed between the gate and the call", "def f(self):\n    egress.check_url(self.url, 'fact', reg)\n    self.url = 'https://evil.example/'\n    return urllib.request.urlopen(self.url)\n"),
        ("a subscript of the address changed between the gate and the call", "def f(cfg):\n    egress.check_url(cfg['url'], 'fact', reg)\n    cfg['url'] = 'https://evil.example/'\n    return urllib.request.urlopen(cfg['url'])\n"),
        ("Request.full_url changed after the gate", "def f(u):\n    egress.check_url(u, 'fact', reg)\n    req = urllib.request.Request(u)\n    req.full_url = 'https://evil.example/'\n    return urllib.request.urlopen(req)\n"),
        ("the call is inside a generator expression", "def f(u):\n    egress.check_url(u, 'fact', reg)\n    return (urllib.request.urlopen(u) for _ in range(2))\n"),
        ("a comprehension variable shadows the checked address", "def f(u, others):\n    egress.check_url(u, 'fact', reg)\n    return [urllib.request.urlopen(u)\n            for u in others]\n"),
        ("a for target rebinds the address after a gate outside the loop", "def f(u, us):\n    egress.check_url(u, 'fact', reg)\n    for u in us:\n        urllib.request.urlopen(u)\n"),
        ("the Request variable is bound twice", "def f(u):\n    req = urllib.request.Request(u)\n    egress.check_url(u, 'fact', reg)\n    req = other()\n    return urllib.request.urlopen(req)\n"),
        ("the Request variable is a parameter that is also assigned", "def f(u, req):\n    egress.check_url(u, 'fact', reg)\n    req = urllib.request.Request(u)\n    return urllib.request.urlopen(req)\n"),
    ]

    def test_a_call_is_gated_only_by_the_same_address_checked_earlier_and_dominating(self):
        for label, source in self.GATED:
            with self.subTest(label=label):
                self.assertEqual(self.left(source), [], label)

    def test_everything_else_stays_ungated(self):
        for label, source in self.UNGATED:
            with self.subTest(label=label):
                self.assertNotEqual(self.left(source), [], label)

    def test_gate_names_are_judged_by_what_they_are_imported_from(self):
        for label, source in self.GATED_BY_NAME:
            with self.subTest(label=label):
                self.assertEqual(self.left(source, prefix=False), [], label)
        for label, source in self.UNGATED_BY_NAME:
            with self.subTest(label=label):
                self.assertNotEqual(self.left(source, prefix=False), [], label)

    def test_a_relative_import_is_resolved_by_the_file_position(self):
        source = "from .. import egress\nimport urllib.request\ndef f(u):\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"
        self.assertEqual(unlisted_for(source, "pipeline/adapters/x.py", ()), [])                                   # pipeline/adapters/x.py 의 `..` 는 pipeline 이다
        self.assertNotEqual(unlisted_for(source, "pipeline/x.py", ()), [])                                          # pipeline/x.py 의 `..` 는 저장소 밖 — 풀 수 없으니 인정하지 않는다
        other = "from ..other import egress\nimport urllib.request\ndef f(u):\n    egress.check_url(u, 'fact', reg)\n    return urllib.request.urlopen(u)\n"
        self.assertNotEqual(unlisted_for(other, "pipeline/adapters/x.py", ()), [])                                 # 이름이 같아도 다른 모듈이다

    def test_the_gate_names_are_the_declared_ones(self):
        from egress_scan import GATE_FQNS
        self.assertEqual(egress.GATE_CALLS, ("egress.check_url",))
        self.assertEqual(GATE_FQNS, {"pipeline.egress.check_url"})                       # 점 이름 하나뿐 — 파일 안에서 pipeline.egress 를 가리키는 import 로만 풀린다(SRCV2 D1)
        self.assertNotIn("source_policy.egress_gate", egress.GATE_CALLS)                 # legacy 에서 아무 일도 안 하는 호출은 관문이 아니다

    def test_registration_matches_file_and_function_and_a_wildcard_must_narrow_the_kinds(self):
        source = "import urllib.request\ndef f(u):\n    return urllib.request.urlopen(u)\n"
        self.assertEqual(self.left(source, [egress.EgressException("x.py", "f", "시험용 예외 이유 문장입니다")]), [])
        self.assertEqual(self.left(source, [egress.EgressException("y.py", "f", "다른 파일의 예외는 소용없다 소용없다")]), [("x.py", "f")])
        self.assertEqual(self.left(source, [egress.EgressException("x.py", "g", "다른 함수의 예외는 소용없다 소용없다")]), [("x.py", "f")])
        self.assertEqual(self.left(source, [egress.EgressException("x.py", "*", "종류를 좁히지 않은 와일드카드는 면제하지 못한다")]), [("x.py", "f")])
        self.assertEqual(self.left(source, [egress.EgressException("x.py", "*", "종류를 좁힌 와일드카드는 그 종류만 면제한다", "", ("net:urlopen",))]), [])
        self.assertEqual(self.left(source, [egress.EgressException("x.py", "*", "다른 종류만 면제하는 와일드카드는 소용없다", "", ("proc:ref",))]), [("x.py", "f")])

    def test_a_new_unmarked_call_would_be_caught_in_the_real_tree(self):
        """저장소 한 곳에 아무 표시 없이 urlopen 을 더하면(가정) 지금 등록 목록으로는 통과하지 못한다."""
        sites, calls = scan_tree(ROOT)
        planted, planted_calls = scan_source("import urllib.request\ndef new_feature(u):\n    return urllib.request.urlopen(u)\n", "pipeline/new_module.py")
        calls.update(planted_calls)
        self.assertEqual(ungated_unlisted(sites + planted, calls, egress.EGRESS_EXCEPTIONS), [("pipeline/new_module.py", "new_feature")])


class ProbeShapesTest(unittest.TestCase):
    """독립 검증의 56가지 심은 모양이 모두 빨강이 되고(고치기 전 20/56), 지금도 못 잡는 모양은 그대로 못 잡는다고 못박는다."""

    def test_all_fifty_six_planted_shapes_are_caught(self):
        self.assertEqual(len(PROBE_SHAPES), 56)
        missed = [label for label, source in PROBE_SHAPES if not unlisted_for(source)]
        self.assertEqual(missed, [], "새 모듈에 심은 모양을 못 잡았다")

    def test_the_five_the_verifier_called_out_are_red(self):
        shapes = dict(PROBE_SHAPES)
        for label in THE_FIVE_LABELS:
            with self.subTest(label=label):
                self.assertIn(label, shapes)
                left = unlisted_for(shapes[label])
                self.assertTrue(left, label)                                            # 라이브러리 import 는 모듈 줄에서, 호출은 함수에서 잡히니 어느 쪽이든 새 파일의 지점이다
                self.assertEqual({file for file, _ in left}, {"pipeline/planted_probe.py"}, label)

    def test_the_blind_spots_are_still_blind_and_the_doc_table_lists_them(self):
        """잡지 못하는 모양을 숨기지 않는다. 스캐너가 이 가운데 하나를 잡게 되면 이 시험이 빨개지니 docs 의 사각지대 표에서 그 줄을 지운다."""
        for label, source, why in BLIND_SPOT_SHAPES:
            with self.subTest(label=label):
                self.assertEqual(kinds_of(source), [], label)
                self.assertGreaterEqual(len(why), 15)
        doc = (ROOT / "docs" / "SOURCE_POLICY.md").read_text(encoding="utf-8")
        for label, _, _ in BLIND_SPOT_SHAPES:
            self.assertIn(f"`{label}`", doc, f"사각지대 표에 없는 모양: {label}")

    # SRCV2 D3: 사각지대 표에 있다고 했거나 문서가 본다고 적은 부류인데 놓치던 모양 — 지금은 잡는다(이 목록이 빠지면 빨강)
    CAUGHT_SHAPES = [
        ("operator.attrgetter 로 이름을 꺼냄", "import operator, urllib.request\ndef f(u):\n    return operator.attrgetter('urlopen')(urllib.request)(u)\n", "dyn:getattr"),
        ("operator.methodcaller", "import operator, urllib.request\ndef f(u):\n    return operator.methodcaller('urlopen', u)(urllib.request)\n", "dyn:getattr"),
        ("functools.partial(getattr, …)", "import functools, urllib.request\ndef f(u):\n    return functools.partial(getattr, urllib.request, 'urlopen')()(u)\n", "dyn:getattr"),
        ("__getattribute__ 로 이름을 꺼냄", "import urllib.request\ndef f(u):\n    return urllib.request.__getattribute__('urlopen')(u)\n", "dyn:getattr"),
        ("pickle 이 코드를 되살림", "import pickle\ndef f(blob):\n    return pickle.loads(blob)\n", "dyn:deserialize"),
        ("yaml.load 로 객체를 되살림", "import yaml\ndef f(t):\n    return yaml.load(t, Loader=yaml.UnsafeLoader)\n", "dyn:deserialize"),
        ("별 가져오기 subprocess", "from subprocess import *\ndef f(u):\n    return run(['curl', '-s', u])\n", "dyn:star:subprocess"),
        ("별 가져오기 os", "from os import *\ndef f(u):\n    return system('curl ' + u)\n", "dyn:star:os"),
        ("별 가져오기 socket", "from socket import *\ndef f(h):\n    return socket()\n", "dyn:star:socket"),
        ("모듈을 다른 이름에 담음", "import subprocess\nsp = subprocess\ndef f(u):\n    return sp.run(['curl', u])\n", "proc:curl"),
        ("sys.modules 에서 꺼냄", "import sys\ndef f(u):\n    return sys.modules['subprocess'].run(['curl', u])\n", "dyn:modules"),
        ("builtins.eval", "import builtins\ndef f(s):\n    return builtins.eval(s)\n", "dyn:eval"),
        ("eval 을 변수에 담음", "def f(s):\n    e = eval\n    return e(s)\n", "dyn:ref:eval"),
        ("__builtins__ 사전", "def f(s):\n    return __builtins__['exec'](s)\n", "dyn:builtins"),
        ("compile 로 코드 만들기", "def f(src, g):\n    return compile(src, '<x>', 'exec')\n", "dyn:compile"),
        ("timeit 이 글자를 실행", "import timeit\ndef f(s):\n    return timeit.timeit(s, number=1)\n", "dyn:code"),
        ("SourceFileLoader.load_module", "import importlib.machinery\ndef f(p):\n    return importlib.machinery.SourceFileLoader('m', p).load_module()\n", "dyn:import"),
        ("프로그램 이름이 변수인 f-문자열 명령", "import os\ndef f(tool, u):\n    return os.system(f'{tool} {u}')\n", "proc:dynamic"),
        ("프로그램 이름이 변수인 덧셈 명령", "import os\ndef f(tool, u):\n    return os.system(tool + ' ' + u)\n", "proc:dynamic"),
        ("프로그램 이름이 변수인 퍼센트 명령", "import os\ndef f(tool, u):\n    return os.system('%s %s' % (tool, u))\n", "proc:dynamic"),
        ("글자 조각으로 도구 이름을 쪼갬", "import os\ndef f(u):\n    return os.system('cu' + 'rl ' + u)\n", "proc:curl"),
        ("env 뒤의 curl", "import subprocess\ndef f(u):\n    return subprocess.run(['env', 'curl', '-s', u])\n", "proc:curl"),
        ("timeout 뒤의 curl", "import subprocess\ndef f(u):\n    return subprocess.run(['timeout', '5', 'curl', u])\n", "proc:curl"),
        ("busybox 뒤의 wget", "import subprocess\ndef f(u):\n    return subprocess.run(['busybox', 'wget', '-O-', u])\n", "proc:wget"),
        ("asyncio.create_subprocess_exec 의 래퍼 뒤 curl", "import asyncio\nasync def f(u):\n    return await asyncio.create_subprocess_exec('env', 'curl', u)\n", "proc:curl"),
        ("os.execvp 의 래퍼 뒤 curl", "import os\ndef f(u):\n    os.execvp('env', ['env', 'curl', u])\n", "proc:curl"),
        ("explorer 로 주소 열기", "import subprocess\ndef f(u):\n    subprocess.run(['explorer', u])\n", "proc:explorer"),
        ("cmd /c start 로 주소 열기", "import subprocess\ndef f():\n    subprocess.run(['cmd', '/c', 'start', 'https://x.example/'])\n", "proc:url"),
        ("os.startfile", "import os\ndef f():\n    os.startfile('https://x.example/')\n", "proc:startfile"),
        ("openssl s_client", "import subprocess\ndef f(h):\n    subprocess.run(['openssl', 's_client', '-connect', h])\n", "proc:openssl"),
        ("python -c 로 코드 글자 실행", "import subprocess, sys\ndef f(u):\n    subprocess.run([sys.executable, '-c', 'import urllib.request', u])\n", "proc:python-c"),
        ("node -e", "import subprocess\ndef f(u):\n    subprocess.run(['node', '-e', 'fetch(process.argv[1])', u])\n", "proc:node"),
        ("powershell 의 Net.WebClient 글자", "import subprocess\ndef f():\n    subprocess.run(['powershell', '-c', '(New-Object Net.WebClient).DownloadString(1)'])\n", "proc:net.webclient"),
        ("git archive --remote", "import subprocess\ndef f(u):\n    subprocess.run(['git', 'archive', '--remote=' + u, 'HEAD'])\n", "proc:git:archive-remote"),
        ("executable= 로 실행 파일을 바꿈", "import subprocess\ndef f(u):\n    subprocess.Popen(['x', u], executable='curl')\n", "proc:executable"),
        ("분기마다 다른 명령 목록 중 curl 이 있는 쪽", "import subprocess\ndef f(u, flag):\n    if flag:\n        cmd = ['curl', u]\n    else:\n        cmd = ['ls', u]\n    return subprocess.run(cmd)\n", "proc:curl"),
        ("ssl.get_server_certificate", "import ssl\ndef f(h):\n    return ssl.get_server_certificate((h, 443))\n", "net:get_server_certificate"),
        ("socket.getfqdn", "import socket\ndef f(ip):\n    return socket.getfqdn(ip)\n", "net:getfqdn"),
        ("loop.create_datagram_endpoint", "def f(loop, h):\n    return loop.create_datagram_endpoint(None, remote_addr=(h, 53))\n", "net:create_datagram_endpoint"),
        ("multiprocessing.connection.Client", "import multiprocessing.connection as mc\ndef f(h):\n    return mc.Client((h, 443))\n", "net:multiprocessing.connection.Client"),
        ("logging.handlers.SocketHandler", "import logging.handlers\ndef f(h):\n    return logging.handlers.SocketHandler(h, 443)\n", "net:SocketHandler"),
        ("urllib.robotparser.RobotFileParser", "import urllib.robotparser\ndef f(u):\n    rp = urllib.robotparser.RobotFileParser(u)\n    rp.read()\n", "net:RobotFileParser"),
        ("socket.SocketType", "import socket\ndef f(h):\n    return socket.SocketType()\n", "net:socket.SocketType"),
        ("_socket 모듈", "import _socket\ndef f(h):\n    return _socket.socket()\n", "lib:_socket"),
        ("pip 이 품은 requests", "from pip._vendor import requests\ndef f(u):\n    return requests.get(u)\n", "lib:pip._vendor"),
        ("dnspython", "import dns.resolver\ndef f(h):\n    return dns.resolver.resolve(h)\n", "lib:dns"),
        ("lxml", "from lxml import etree\ndef f(u):\n    return etree.parse(u)\n", "lib:lxml"),
        ("xml.sax.make_parser", "import xml.sax\ndef f(u, h):\n    p = xml.sax.make_parser()\n    p.parse(u)\n", "parse:xml.sax.make_parser"),
    ]
    FALSE_ALARM_SHAPES = [                       # 알려진 모양을 닮았지만 네트워크에 닿지 않는 평범한 코드 — 잡으면 등록 잡음이 늘어난다
        ("sys.modules[__name__]", "import sys\ndef f():\n    return sys.modules[__name__]\n"),
        ("정렬 키로 attrgetter", "import operator\ndef f(rows):\n    return sorted(rows, key=operator.attrgetter('name'))\n"),
        ("re.compile", "import re\ndef f(t):\n    return re.compile(t)\n"),
        ("yaml.safe_load", "import yaml\ndef f(t):\n    return yaml.safe_load(t)\n"),
        ("git log 목록 덧셈", "import subprocess\ndef f(path):\n    cmd = ['git', 'log', '--format=%ct']\n    return subprocess.run(cmd + ['--', path])\n"),
        ("env 뒤의 로컬 git", "import subprocess\ndef f():\n    return subprocess.run(['env', 'FOO=1', 'git', 'status'])\n"),
        ("글자 명령이 상수 로컬 명령", "import os\ndef f():\n    return os.system('git status')\n"),
    ]

    def test_the_shapes_the_verifier_listed_in_the_third_group_are_now_caught_with_the_expected_kind(self):
        for label, source, expected in self.CAUGHT_SHAPES:
            with self.subTest(label=label):
                self.assertIn(expected, kinds_of(source), label)
                self.assertNotEqual(unlisted_for(source), [], label)

    def test_harmless_lookalikes_of_the_new_shapes_are_not_sites(self):
        for label, source in self.FALSE_ALARM_SHAPES:
            with self.subTest(label=label):
                self.assertEqual(kinds_of(source), [], label)


class ScanScopeTest(unittest.TestCase):
    """스캔 범위를 못박는다: tests/ 밖의 모든 *.py 는 '스캔함' 또는 '제외(이유)' 목록 중 하나에 있다. .github·인수인계/도구 는 기본으로 스캔한다."""

    def test_every_python_file_outside_tests_is_scanned_or_excluded_with_a_reason(self):
        self.assertEqual(unscoped_files(ROOT), [], "스캔 범위 목록(SCAN_ROOTS·SCAN_EXCLUDED)에 없는 파이썬 파일 — 새 폴더를 만들었다면 tests/egress_scan.py 에 올리세요")
        for prefix, reason in SCAN_EXCLUDED:
            self.assertGreaterEqual(len(reason.strip()), 20, prefix)
            self.assertTrue((ROOT / prefix).exists(), prefix)
        for prefix in SCAN_ROOTS:
            self.assertTrue((ROOT / prefix).exists(), prefix)

    def test_the_scope_is_the_documented_one(self):
        self.assertEqual(SCAN_ROOTS, ("generator.py", "blogger_generator.py", "pipeline", "scripts", "인수인계/도구", ".github"))
        self.assertEqual([prefix for prefix, _ in SCAN_EXCLUDED], ["tests"])
        scanned = {p.relative_to(ROOT).as_posix() for p in python_files(ROOT)}
        for name in ("generator.py", "blogger_generator.py", "pipeline/run.py", "pipeline/publishers/blogger.py", "scripts/watchdog.py", "scripts/validate_repo.py", "pipeline/egress.py"):
            self.assertIn(name, scanned)
        self.assertTrue(any(name.startswith("인수인계/도구/") for name in scanned), "인수인계/도구 아래 파이썬 파일이 스캔 범위에 있어야 한다")      # 도구 폴더의 구체적인 파일 이름은 다른 묶음이 바꾸므로 못박지 않는다
        self.assertTrue(all(not name.startswith("tests/") for name in scanned))

    def test_folders_named_like_build_output_are_skipped_only_at_the_top_of_the_repository(self):
        """SRCV2 D2: `venv`·`node_modules` 이름의 폴더는 저장소 맨 위에서만 건너뛴다 — 스캔 폴더 안쪽의 같은 이름 폴더에 몰래 둔 파이썬 파일도 읽는다."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            code = "import urllib.request\ndef f(u):\n    return urllib.request.urlopen(u)\n"
            for rel in ("venv/top.py", "node_modules/top2.py", "pipeline/venv/leak.py", "pipeline/node_modules/leak2.py", "scripts/_site/leak3.py", "pipeline/__pycache__/ok.py", ".git/hooks/x.py", "pipeline/ok.py"):
                path = base / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(code, encoding="utf-8")
            expected = ["pipeline/node_modules/leak2.py", "pipeline/ok.py", "pipeline/venv/leak.py", "scripts/_site/leak3.py"]
            self.assertEqual(all_python_files(base), expected)
            sites, _ = scan_tree(base)
            self.assertEqual(sorted({s.file for s in sites}), expected)

    def test_a_new_top_level_folder_and_new_files_in_the_roots_behave(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            code = "import urllib.request\ndef f(u):\n    return urllib.request.urlopen(u)\n"
            for rel in ("generator.py", "blogger_generator.py", "pipeline/a.py", "scripts/b.py", "인수인계/도구/c.py", "인수인계/도구/work/scratch/c2.py", ".github/scripts/d.py", "tests/e.py"):
                path = base / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(code, encoding="utf-8")
            sites, _ = scan_tree(base)
            self.assertEqual(sorted({s.file for s in sites}), sorted(["generator.py", "blogger_generator.py", "pipeline/a.py", "scripts/b.py", "인수인계/도구/c.py", "인수인계/도구/work/scratch/c2.py",
                                                                   ".github/scripts/d.py"]))     # tests/ 만 스캔 밖
            self.assertEqual(unscoped_files(base), [])
            (base / "newdir").mkdir()
            (base / "newdir" / "x.py").write_text(code, encoding="utf-8")
            (base / "tools.py").write_text(code, encoding="utf-8")
            self.assertEqual(unscoped_files(base), ["newdir/x.py", "tools.py"])               # 새 최상위 폴더·파일은 빨강


# 워크플로 yml 의 네트워크 도구 줄(.github 는 보호 경로라 읽기만 한다): (파일, 종류) → 이유. 새 curl·wget 줄이나 새 도구가 생기면 등록 전까지 빨강이다. 이미 있는 줄은 종류별로 등록한다.
_GH = "자기 저장소 GitHub(PR·이슈·실행 읽기·쓰기) — GITHUB_TOKEN 권한 안의 gh 명령"
_GIT = "자기 저장소 origin 과의 git(pull --rebase·push·fetch·ls-remote)"
_PIP = "공식 패키지 인덱스에서 의존성 설치(빌드 의존 — C-37)"
YML_REGISTERED = {
    (".github/workflows/auto-pr.yml", "gh"): _GH,
    (".github/workflows/blogger.yml", "git"): _GIT, (".github/workflows/blogger.yml", "pip"): _PIP,
    (".github/workflows/chance-fix-images.yml", "gh"): _GH, (".github/workflows/chance-fix-images.yml", "git"): _GIT, (".github/workflows/chance-fix-images.yml", "pip"): _PIP,
    (".github/workflows/chance-shadow.yml", "pip"): _PIP,                      # 그림자 실행(읽기 전용) 워크플로의 의존성 설치(Gate 병합 M034 뒤 — 같은 공식 인덱스)
    (".github/workflows/chanceblog.yml", "gh"): _GH, (".github/workflows/chanceblog.yml", "git"): _GIT, (".github/workflows/chanceblog.yml", "pip"): _PIP,
    (".github/workflows/guardrails.yml", "git"): _GIT, (".github/workflows/guardrails.yml", "pip"): _PIP,
    (".github/workflows/issue-edit.yml", "gh"): _GH, (".github/workflows/issue-edit.yml", "git"): _GIT, (".github/workflows/issue-edit.yml", "pip"): _PIP,
    (".github/workflows/naver.yml", "git"): _GIT, (".github/workflows/naver.yml", "pip"): _PIP,
    (".github/workflows/pr-scope-check.yml", "gh"): _GH, (".github/workflows/pr-scope-check.yml", "pip"): _PIP,
    (".github/workflows/sync-issue-form.yml", "git"): _GIT, (".github/workflows/sync-issue-form.yml", "pip"): _PIP,
    (".github/workflows/tistory.yml", "git"): _GIT, (".github/workflows/tistory.yml", "pip"): _PIP,
}


class WorkflowYmlScanTest(unittest.TestCase):
    """워크플로 yml 을 줄 단위 글자 검색으로 훑는다(가벼운 시험 — 파이썬 호출 목록과 별개)."""

    def test_every_network_tool_line_in_the_workflows_is_registered_and_every_registration_is_alive(self):
        found = {(rel, kind) for rel, kind, _ in scan_yml(ROOT)}
        self.assertGreater(len(found), 15)                                          # 실제로 읽었는지(빈 검사로 통과하지 않게)
        self.assertEqual(sorted(found - set(YML_REGISTERED)), [], "등록되지 않은 네트워크 도구 줄(curl·wget·git·gh·pip …) — 이유와 함께 YML_REGISTERED 에 올리세요")
        self.assertEqual(sorted(set(YML_REGISTERED) - found), [], "낡은 등록 — 그 줄이 사라졌다")
        for reason in YML_REGISTERED.values():
            self.assertGreaterEqual(len(reason), 15)
        self.assertEqual({kind for _, kind in found} & {"curl", "wget", "powershell-web", "net-tool", "python-net"}, set())      # 지금 워크플로에는 curl·wget 줄이 없다 — 생기면 빨강

    def test_a_new_curl_or_wget_line_would_be_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / ".github" / "workflows"
            base.mkdir(parents=True)
            (base / "x.yml").write_text("jobs:\n  a:\n    steps:\n      - run: |\n          # curl is only a comment here\n          curl -s https://x.example/\n          wget -qO- https://y.example/\n"
                                        "          Invoke-WebRequest https://z.example/\n          python -c \"import urllib.request\"\n          git push origin HEAD\n          gh api x\n          pip install y\n", encoding="utf-8")
            found = sorted({kind for _, kind, _ in scan_yml(tmp)})
            self.assertEqual(found, ["curl", "gh", "git", "pip", "powershell-web", "python-net", "wget"])
            self.assertEqual([n for _, kind, n in scan_yml(tmp) if kind == "curl"], [6])        # 주석 줄(5행)은 건너뛴다


# ----------------------------------------------------------------------------
# 실제 저장소 호출 목록
# ----------------------------------------------------------------------------
class RealTreeCallListTest(unittest.TestCase):
    """저장소의 실제 외부 접속 지점: 관문(check_url)을 거쳤다고 인정되거나 이유·막는 장치와 함께 등록된 것."""

    @classmethod
    def setUpClass(cls):
        cls.sites, cls.calls = scan_tree(ROOT)

    def test_every_site_is_gated_or_registered(self):
        self.assertGreater(len(self.sites), 40)                                     # 스캐너가 실제로 읽었는지(빈 검사로 통과하지 않게)
        left = ungated_unlisted(self.sites, self.calls, egress.EGRESS_EXCEPTIONS)
        self.assertEqual(left, [], "관문을 거쳤다고 인정되지 않고 등록 목록(pipeline/egress.py EGRESS_EXCEPTIONS)에도 없는 외부 접속 지점 — 관문(egress.check_url)을 같은 주소로 앞서 부르게 하거나 이유와 함께 등록하세요")

    def test_every_exception_entry_is_alive_unique_and_says_why_and_what_blocks(self):
        keys = [(e.file, e.function, tuple(e.kinds)) for e in egress.EGRESS_EXCEPTIONS]
        self.assertEqual(len(keys), len(set(keys)), "등록 목록에 같은 항목이 두 번 있다")
        for entry in egress.EGRESS_EXCEPTIONS:
            self.assertTrue(any(is_listed(site, [entry]) for site in self.sites), f"낡은 항목: {entry.file} {entry.function} — 지점이 없어졌거나 함수 이름이 바뀌었다")
            self.assertGreaterEqual(len(entry.reason.strip()), 20, f"{entry.file} {entry.function}: 이유가 너무 짧다")
            self.assertGreaterEqual(len(entry.gate.strip()), 15, f"{entry.file} {entry.function}: 어떤 관문이 어느 모드에서 막는지(또는 막는 장치 없음)를 적어야 한다")
            self.assertTrue((ROOT / entry.file).is_file(), entry.file)
            if entry.function == "*":
                self.assertTrue(entry.kinds, f"{entry.file}: 와일드카드는 모양 종류를 좁혀야 한다")

    def test_every_entry_covers_exactly_the_kinds_and_the_number_of_sites_it_was_registered_for(self):
        """SRCV2 D2: 등록 단위가 함수라 같은 함수에 알려진 모양이 나중에 더해져도 지나가던 구멍을 막는다 — 면제하는 모양 종류의 앞 조각과 지점 수를 못박았다.
        다른 종류가 더해지면 등록 밖 지점이 되고, 같은 종류가 늘면 이 시험이 빨개진다. 와일드카드 항목은 세지 않는다(종류만 좁힌다)."""
        for entry in egress.EGRESS_EXCEPTIONS:
            label = f"{entry.file} {entry.function}"
            if entry.function == "*":
                self.assertTrue(entry.kinds, label)
                self.assertIsNone(entry.count, label)
                continue
            self.assertTrue(entry.kinds, f"{label}: 면제하는 모양 종류를 적어야 한다")
            if entry.count is None:                                                      # 다른 묶음이 계속 고치는 파일의 항목 — 종류만 좁히고 개수는 세지 않는다
                continue
            self.assertIsInstance(entry.count, int, label)
            self.assertGreaterEqual(entry.count, 1, label)
            mine = [site for site in self.sites if is_listed(site, [entry])]
            self.assertEqual(len(mine), entry.count, f"{label}: 등록한 지점 수와 다르다 — 이 함수에 알려진 모양의 호출이 {len(mine)}곳 있다(사람이 보고 이유·막는 장치와 함께 다시 등록)")

    def test_the_gate_column_is_honest_about_the_mode_that_blocks(self):
        """'allowlist 에서 막힘' 이라고 적은 항목은 모두 legacy 에서 열려 있다고도 적는다(그 호출은 legacy 에서 아무 일도 안 하는 egress_gate 뒤에 있다)."""
        for entry in egress.EGRESS_EXCEPTIONS:
            if entry.gate.startswith("allowlist 에서는 막힘"):
                self.assertIn("legacy", entry.gate, entry.function)
                self.assertIn("열려", entry.gate, entry.function)
        blocked = [e.function for e in egress.EGRESS_EXCEPTIONS if e.gate.startswith("allowlist 에서는 막힘")]
        self.assertEqual(sorted(blocked), ["_fetch_source_excerpt", "_resolve_article_url", "fetch_news_items"])      # 모드에 따라 막히는 곳은 이 세 곳뿐

    def test_nothing_in_the_real_tree_is_gated_by_check_url_yet(self):
        """지금 코드의 어느 호출도 `egress.check_url` 을 같은 주소로 앞서 부르지 않는다 — 관문을 연결한 호출은 allowlist 에서만 동작하는 `source_policy.egress_gate` 뒤에 있고 그것은 관문으로 인정하지 않는다."""
        self.assertEqual([site for site in self.sites if is_gated(site)], [])

    def test_the_content_paths_are_registered_with_the_allowlist_gate_not_hidden_as_gated(self):
        """C-01 피드·C-02 기사 페이지 발췌·C-03 구글 뉴스 해석기: allowlist 에서만 막힌다 — 그렇게 등록돼 있고 관문으로 인정되지 않는다(P01)."""
        listed = {(e.file, e.function): e for e in egress.EGRESS_EXCEPTIONS}
        for function in ("fetch_news_items", "_fetch_source_excerpt", "_resolve_article_url"):
            sites = [s for s in self.sites if (s.file, s.function) == ("generator.py", function)]
            self.assertEqual(len(sites), 1, function)
            self.assertFalse(sites[0].gated, function)
            entry = listed[("generator.py", function)]
            self.assertIn("allowlist", entry.gate)
            self.assertIn("egress_gate", entry.gate)
            self.assertIn("legacy", entry.gate)

    def test_the_url_ok_reason_names_every_host_it_really_reaches(self):
        entry = next(e for e in egress.EGRESS_EXCEPTIONS if (e.file, e.function) == ("generator.py", "url_ok"))
        for needle in ("FIX_IMAGES", "image:", "NASA", "운영자 결정"):
            self.assertIn(needle, entry.reason)

    def test_the_registry_covers_the_known_shapes_in_the_tools_folder(self):
        tools = {(s.file, s.function) for s in self.sites if s.file.startswith("인수인계/도구/")}
        self.assertGreaterEqual(len(tools), 1)                                                                                         # 도구 폴더의 지점 수는 다른 묶음이 도구를 더하거나 빼면 달라지므로 못박지 않는다 — 모든 지점이 등록돼 있는지는 위 시험이 본다
        self.assertEqual({s.kind for s in self.sites if s.file.startswith("인수인계/도구/") and s.kind.startswith("net:")}, {"net:urlopen"})


class OpsRulesTest(unittest.TestCase):
    """고정 운영 호스트 규칙(P02): 호스트마다 허용 목적과 허용 경로가 있고 일반 웹 읽기·모르는 목적은 거부한다."""

    EXPECTED = {
        "api.github.com": ("ops_repo",),
        "api.telegram.org": ("ops_notify",),
        "blogger.googleapis.com": ("ops_publish",),
        "generativelanguage.googleapis.com": ("ops_llm",),
        "oauth2.googleapis.com": ("ops_auth",),
    }
    OWN = "owner1/repo1"
    SAMPLES = {      # 호스트 → (코드가 실제로 부르는 꼴의 허용 경로들)
        "api.github.com": ["/repos/owner1/repo1/issues", "/repos/owner1/repo1/issues/12/comments", "/repos/owner1/repo1/issues/12/labels", "/repos/owner1/repo1/labels", "/repos/owner1/repo1/labels/x",
                           "/repos/owner1/repo1/pulls", "/repos/owner1/repo1/pulls/12", "/repos/owner1/repo1/commits/main", "/repos/owner1/repo1/commits/abc123/check-runs",
                           "/repos/owner1/repo1/actions/runs", "/repos/owner1/repo1/actions/runs/9/jobs", "/repos/owner1/repo1/actions/workflows/a.yml/runs", "/repos/owner1/repo1/check-runs/5/annotations",
                           "/rate_limit"],
        "api.telegram.org": ["/bot123456:ABC-def_GHI/sendMessage", "/bot123456:ABC-def_GHI/getUpdates"],
        "oauth2.googleapis.com": ["/token"],
        "generativelanguage.googleapis.com": ["/v1beta/models/gemini-x:generateContent", "/v1beta/models", "/v1/models/gemini-x:generateContent"],
        "blogger.googleapis.com": ["/v3/blogs/123", "/v3/blogs/123/posts", "/v3/blogs/123/posts/456"],
    }
    DENIED_PATHS = {
        "api.github.com": ["/", "/user", "/orgs/x", "/repos/torvalds/linux/readme", "/repos/torvalds/linux/issues", "/repos/owner1/repo1", "/repos/owner1/repo1/readme", "/repos/owner1/repo1/contents/x",
                           "/repos/owner1/repo1/git/refs", "/repos/owner1/repo2/issues", "/repos/owner1/repo1x/issues", "/repos/owner1/repo1/issuesx", "/repos/owner1/repo1/issues/../../../../user",
                           "/repos/owner1/repo1/issues/%2e%2e/x", "/repos/owner1/repo1//issues", "/repos/Owner1/Repo1/issues", "/search/code", "/gists"],
        "api.telegram.org": ["/", "/bot123456:ABC/deleteWebhook", "/bot123456:ABC/sendMessage/x", "/file/bot123456:ABC/x", "/botx/sendMessage", "/bot123456:AB C/sendMessage", "/bot123456/sendMessage"],
        "oauth2.googleapis.com": ["/", "/token/x", "/revoke", "/tokeninfo", "/o/oauth2/auth"],
        "generativelanguage.googleapis.com": ["/", "/v2/models/x", "/v1beta/files", "/v1beta/models/a/b", "/upload/v1beta/files", "/v1beta/modelsx"],
        "blogger.googleapis.com": ["/", "/v3/users/self", "/v3/blogs", "/v3/blogs/1/pages", "/v3/blogs/1/posts/2/comments", "/v2/blogs/1"],
    }
    GENERAL_PURPOSES = ("fact", "feed", "page", "resolve", "web", "article", "ops", "crawl", "")

    def allowed(self, url, purpose, own_repo=OWN, registry=None):
        try:
            egress.check_url(url, purpose, registry, own_repo)
        except egress.EgressDenied:
            return False
        return True

    def test_the_rule_table_is_pinned_and_consistent(self):
        self.assertEqual({r.host: r.purposes for r in egress.OPS_RULES}, self.EXPECTED)
        self.assertEqual(egress.OPS_HOSTS, frozenset(self.EXPECTED))
        self.assertEqual(egress.OPS_PURPOSES, frozenset(p for ps in self.EXPECTED.values() for p in ps))
        self.assertEqual(sorted(egress.OPS_HOST_BASIS), sorted(egress.OPS_HOSTS))
        for rule in egress.OPS_RULES:
            self.assertTrue(rule.paths and rule.purposes, rule.host)
            self.assertTrue(sr.valid_host(rule.host), rule.host)
            for purpose in rule.purposes:
                self.assertRegex(purpose, r"^ops_[a-z]+$")
            for pattern in rule.paths:
                re.compile(pattern.replace("{repo}", "a/b"))                       # 정규식이 올바르다
                self.assertTrue(pattern.startswith("/"), pattern)
        self.assertTrue(egress.OPS_PURPOSES.isdisjoint(sr.ALLOWED_PURPOSES | sr.GENERAL_WEB_PURPOSES))     # 운영 목적은 허용 목록 목적·일반 웹 읽기와 겹치지 않는다

    def test_hosts_said_to_be_in_the_code_really_are_and_the_rest_are_marked_sdk(self):
        for host, basis in egress.OPS_HOST_BASIS.items():
            if basis == "sdk":
                self.assertIn(host, {"generativelanguage.googleapis.com", "blogger.googleapis.com"})       # 코드에 문자열이 없는 SDK 호스트 — 이 둘뿐
                continue
            self.assertIn(host, (ROOT / basis).read_text(encoding="utf-8"), f"{host} 가 {basis} 에 없다")

    def test_www_googleapis_com_is_not_an_operations_host_and_the_code_only_names_it_as_an_oauth_scope(self):
        """D-173: 코드에 있는 www.googleapis.com 은 OAuth 범위 이름(…/auth/blogger)이고 요청 목적지가 아니다 — googleapiclient>=2 는 번들 디스커버리를 써서 내려받지도 않는다."""
        self.assertNotIn("www.googleapis.com", egress.OPS_HOSTS)
        self.assertIn("google-api-python-client>=2,<3", (ROOT / "requirements-pipeline.txt").read_text(encoding="utf-8"))
        hits = 0
        for path in python_files(ROOT):
            rel = path.relative_to(ROOT).as_posix()
            if rel == "pipeline/egress.py":
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for match in re.finditer(r"www\.googleapis\.com(/[^\s\"']*)?", line):
                    hits += 1
                    self.assertTrue((match.group(1) or "").startswith("/auth/"), f"{rel}:{number} — OAuth 범위 이름이 아닌 www.googleapis.com 사용")
        self.assertGreaterEqual(hits, 2)

    def test_the_github_paths_the_code_calls_are_all_inside_the_rule(self):
        """근거: 여섯 GitHub 클라이언트가 부르는 경로의 첫 조각 전부가 규칙의 목록 안에 있다(코드를 grep 하지 않고 AST 로 읽는다)."""
        allowed = {"issues", "labels", "pulls", "commits", "actions", "check-runs", "rate_limit"}
        seen = set()
        files = ("pipeline/operator_loop.py", "pipeline/drafts.py", "pipeline/publishers/issue_package.py", "scripts/ops_inbox.py", "scripts/github_status.py", "scripts/watchdog.py")
        for rel in files:
            tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))):
                    continue
                name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
                if name not in ("request", "_request", "get", "post", "patch", "repo_get"):
                    continue
                for arg in node.args:
                    head = None
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        head = arg.value
                    elif isinstance(arg, ast.JoinedStr) and arg.values and isinstance(arg.values[0], ast.Constant):
                        head = arg.values[0].value
                        if head == "/repos/":                                   # f"/repos/{self.repo}/issues?…" 의 /issues 부분(뒤가 계산되는 식이면 건너뛴다)
                            head = arg.values[2].value if len(arg.values) >= 3 and isinstance(arg.values[2], ast.Constant) else None
                    if head and head.startswith("/") and len(head) > 1:
                        seen.add(head[1:].split("/")[0].split("?")[0])
        self.assertTrue(seen and seen <= allowed, sorted(seen - allowed))
        self.assertGreaterEqual(len(seen), 5)

    def test_each_host_passes_only_its_own_purpose_on_its_own_paths(self):
        for host, paths in self.SAMPLES.items():
            own = self.EXPECTED[host][0]
            for path in paths:
                url = f"https://{host}{path}?x=1"
                with self.subTest(host=host, path=path):
                    self.assertTrue(self.allowed(url, own), url)
                    for purpose in self.GENERAL_PURPOSES + tuple(sorted(egress.OPS_PURPOSES - {own})):
                        self.assertFalse(self.allowed(url, purpose), (url, purpose))      # 일반 웹 읽기·fact·모르는 목적·다른 호스트의 운영 목적은 거부

    def test_paths_outside_the_rule_are_denied_for_every_purpose(self):
        every = self.GENERAL_PURPOSES + tuple(sorted(egress.OPS_PURPOSES))
        for host, paths in self.DENIED_PATHS.items():
            for path in paths:
                url = f"https://{host}{path}"
                with self.subTest(host=host, path=path):
                    for purpose in every:
                        self.assertFalse(self.allowed(url, purpose), (url, purpose))

    def test_the_verifier_repro_is_denied_for_every_purpose_and_every_repo_argument(self):
        """검증자 재현: api.github.com/repos/torvalds/linux/readme 가 어떤 목적에서도 통과하던 것."""
        url = "https://api.github.com/repos/torvalds/linux/readme"
        for purpose in self.GENERAL_PURPOSES + tuple(sorted(egress.OPS_PURPOSES)):
            for own in (None, self.OWN, "torvalds/linux", "", "x", 5):
                self.assertFalse(self.allowed(url, purpose, own), (purpose, own))
        for own in (None, "", "owner1", "owner1/", "/repo1", "owner1/repo1/extra", "own er/repo1", "owner1/..", "owner1/.", 5, ["owner1/repo1"]):
            self.assertFalse(self.allowed("https://api.github.com/repos/owner1/repo1/issues", "ops_repo", own), own)       # 자기 저장소 이름이 없거나 올바르지 않으면 저장소 경로는 열리지 않는다
        self.assertTrue(self.allowed("https://api.github.com/rate_limit", "ops_repo", None))                           # 저장소가 없는 경로는 own_repo 없이도 열린다

    def test_operations_hosts_are_never_handed_over_to_the_registry(self):
        """운영 호스트는 허용 목록으로 넘어가지 않는다 — 허용 목록 Provider 가 운영 호스트를 접근 경로로 적어도 fact 로 통과하지 못한다."""
        data = registry_data(good_provider(access=[{"kind": "api", "hosts": ["api.github.com"], "paths": ["/v1/"], "auth": "KEY", "rate_limit": "100 per day"}]))
        registry = sr.build_registry(data, TODAY)
        self.assertEqual([p.provider_id for p in registry.active_providers()], ["fixture_stats"])
        self.assertTrue(registry.is_url_allowed("https://api.github.com/v1/x", "fact")[0])                              # 레지스트리 자체는 허용하지만
        self.assertFalse(self.allowed("https://api.github.com/v1/x", "fact", registry=registry))                       # 관문은 운영 규칙으로만 본다
        self.assertFalse(self.allowed("https://api.github.com/v1/x", "ops_repo", registry=registry))

    def test_tricks_on_operations_hosts_do_not_pass(self):
        for url in ("http://api.github.com/rate_limit", "https://api.github.com:8443/rate_limit", "https://api.github.com@evil.example/rate_limit", "https://evil.example@api.github.com/rate_limit",
                    "https://api.github.com./rate_limit", "https://api.github.com.evil.example/rate_limit", "https://x.api.github.com/rate_limit", "https://api.github.com\\@evil.example/",
                    "ftp://api.github.com/rate_limit", "//api.github.com/rate_limit", "api.github.com/rate_limit", "https://api.github.com//rate_limit", "https://xapi.github.com/rate_limit",
                    "https://github.com/rate_limit", "https://api.github.com/rate_limit/..;/user", "https://api.github.com/%252e%252e/rate_limit"):
            with self.subTest(url=url):
                self.assertFalse(self.allowed(url, "ops_repo"), url)
        self.assertTrue(self.allowed("HTTPS://API.GITHUB.COM/rate_limit", "ops_repo"))
        self.assertTrue(self.allowed("https://api.github.com:443/rate_limit", "ops_repo"))

    def test_no_content_host_is_an_operations_host(self):
        registry = sr.load_registry(today=TODAY)
        content = {h for p in registry.providers() for a in p.access for h in a.hosts} | {h for p in registry.providers() for h in p.reference_hosts}
        self.assertEqual(content & egress.OPS_HOSTS, set())                       # 운영 호스트는 콘텐츠 Provider 의 호스트가 아니다(통과 목록으로 콘텐츠를 읽게 되는 일이 없게)


class CheckUrlTest(unittest.TestCase):
    def registry(self):
        return sr.build_registry(registry_data(good_provider()), TODAY)

    def allowed(self, url, purpose="fact", registry=True):
        try:
            egress.check_url(url, purpose, self.registry() if registry is True else registry)
        except egress.EgressDenied as exc:
            return False, str(exc)
        return True, ""

    def test_registered_active_hosts_pass_for_the_fact_purpose_and_everything_else_is_denied(self):
        self.assertTrue(self.allowed(f"https://{GOOD_HOST}/v1/series?id=1")[0])
        for url in (f"https://{GOOD_HOST}/v2/x", "https://evil.example/v1/", "https://www.nasa.gov/feed/", "https://api.unsplash.com/search/photos", f"http://{GOOD_HOST}/v1/x",
                    f"https://{GOOD_HOST}/v1/..;/x", f"https://{GOOD_HOST}/v1/%252e%252e/x"):
            self.assertFalse(self.allowed(url)[0], url)
        self.assertFalse(self.allowed(f"https://{GOOD_HOST}/v1/x", registry=None)[0])            # 허용 목록이 없으면 운영 호스트 규칙만

    def test_only_the_fact_purpose_passes_for_registered_hosts(self):
        for purpose in ("feed", "page", "resolve", "web", "rss", "article", "fetch", "ops", "ops_repo", "facts", "", None):
            ok, message = self.allowed(f"https://{GOOD_HOST}/v1/x", purpose)
            self.assertFalse(ok, purpose)
        ok, message = self.allowed(f"https://{GOOD_HOST}/v1/x", "feed")
        self.assertIn("Tier 3", message)
        ok, message = self.allowed(f"https://{GOOD_HOST}/v1/x", "web")
        self.assertIn("허용 목적", message)

    def test_the_real_registry_allows_no_content_host_for_any_purpose(self):
        real = sr.load_registry(today=TODAY)
        for provider in real.providers():
            for access in provider.access:
                for host in access.hosts:
                    for purpose in ("fact", "feed", "page", "resolve", "web"):
                        self.assertFalse(self.allowed(f"https://{host}/", purpose, registry=real)[0], (provider.provider_id, host, purpose))

    def test_the_denial_names_the_host_and_never_the_path_query_or_token(self):
        for url in ("https://evil.example/private-name?token=SECRET&key=1#frag", f"https://{GOOD_HOST}/v9/private-name?token=SECRET#frag", "http://evil.example/private-name?token=SECRET",
                    "https://u:SECRET@evil.example/private-name", "https://evil.example/%2e%2e/private-name?token=SECRET", "https://evil.example:99/private-name?token=SECRET",
                    "https://api.github.com/repos/torvalds/linux/private-name?token=SECRET", "https://api.telegram.org/bot123:SECRET/deleteWebhook"):
            ok, message = self.allowed(url)
            self.assertFalse(ok)
            for leaked in ("private-name", "SECRET", "token", "frag", "key=1", "u:", "torvalds", "deleteWebhook"):
                self.assertNotIn(leaked, message, url)
            self.assertIn("외부 호출 거부", message)
        _, message = self.allowed("https://evil.example/x")
        self.assertIn("evil.example", message)

    def test_the_exception_carries_host_purpose_and_reason(self):
        with self.assertRaises(egress.EgressDenied) as caught:
            egress.check_url("https://evil.example/x?token=SECRET", "fact", self.registry())
        exc = caught.exception
        self.assertEqual((exc.host, exc.purpose), ("evil.example", "fact"))
        self.assertIn("허용 목록", exc.reason)
        self.assertNotIn("SECRET", repr(exc) + str(exc))
        with self.assertRaises(egress.EgressDenied) as caught:
            egress.check_url(["not", "a", "url"], "Bad Purpose!", self.registry())
        self.assertEqual(caught.exception.host, sr.UNKNOWN_HOST)
        self.assertEqual(caught.exception.purpose, "(형식 오류)")
        self.assertIsInstance(caught.exception, Exception)

    def test_check_url_and_check_final_url_only_judge_and_never_send_a_request(self):
        """판정 함수는 요청을 보내지 않는다 — egress.py 의 네트워크 모양은 검사된 opener 를 만드는 함수 한 곳뿐이고, 어디에도 .open(·urlopen( 호출이 없다."""
        source = (ROOT / "pipeline" / "egress.py").read_text(encoding="utf-8")
        sites, _ = scan_source(source, "pipeline/egress.py")
        self.assertEqual({s.function for s in sites}, {"build_checked_opener"})
        self.assertEqual({s.kind for s in sites}, {"net:HTTPSHandler", "net:OpenerDirector"})
        self.assertIsNone(re.search(r"\.open\(|urlopen\(|^\s*(?:import|from)\s+(?:socket|http|requests|subprocess)", source, re.M))


# ----------------------------------------------------------------------------
# 검사된 opener(P03) — 가짜 전송으로 네트워크 없이
# ----------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, url, code=200, headers=None):
        self.url, self.code = url, code
        self.msg = "OK" if code == 200 else "Found"
        self._headers = email.message_from_string("".join(f"{k}: {v}\n" for k, v in (headers or {}).items()) + "\n")
        self.fp = io.BytesIO(b"body")

    def info(self):
        return self._headers

    def geturl(self):
        return self.url

    def read(self, *args):
        return self.fp.read(*args)

    def close(self):
        pass

    @property
    def status(self):
        return self.code


class FakeHttps(urllib.request.BaseHandler):
    """https 요청을 보내지 않고 미리 정한 응답(코드, 머리글)을 돌려주는 전송 처리기. 받은 요청의 주소·머리글을 기록한다."""

    def __init__(self, routes):
        self.routes = routes
        self.sent = []
        self.headers = []

    def https_open(self, request):
        self.sent.append(request.full_url)
        self.headers.append({k.lower(): v for k, v in request.header_items()})
        code, headers = self.routes[request.full_url]
        return FakeResponse(request.full_url, code, headers)


class CheckedOpenerTest(unittest.TestCase):
    HOST2 = "data.fixture-two.example"

    def registry(self):
        second = good_provider(provider_id="fixture_two", access=[{"kind": "api", "hosts": [self.HOST2], "paths": ["/api/"], "auth": "KEY", "rate_limit": "100 per day"}])
        return sr.build_registry(registry_data(good_provider(), second), TODAY)

    def opener(self, routes, **kwargs):
        transport = FakeHttps(routes)
        return egress.build_checked_opener("fact", self.registry(), https_handler=transport, **kwargs), transport

    def test_an_allowed_request_without_redirect_passes_and_the_final_address_check_agrees(self):
        url = f"https://{GOOD_HOST}/v1/a"
        opener, transport = self.opener({url: (200, {})})
        response = opener.open(url)
        self.assertEqual(response.geturl(), url)
        self.assertEqual(transport.sent, [url])
        egress.check_final_url(response.geturl(), "fact", self.registry())

    def test_the_first_request_is_judged_too_and_nothing_is_sent_for_a_denied_address(self):
        for url in ("https://evil.example/x", f"https://{GOOD_HOST}/v2/x", f"https://{GOOD_HOST}/v1/..;/x", f"http://{GOOD_HOST}/v1/a"):
            opener, transport = self.opener({})
            with self.subTest(url=url), self.assertRaises(egress.EgressDenied):
                opener.open(url)
            self.assertEqual(transport.sent, [], url)

    def test_other_schemes_have_no_handler_at_all(self):
        opener, transport = self.opener({})
        for url in ("file:///etc/hosts", "ftp://x.example/a", "data:text/plain,hi", "gopher://x.example/"):
            with self.subTest(url=url), self.assertRaises((urllib.error.URLError, egress.EgressDenied)):
                opener.open(url)
        self.assertEqual(transport.sent, [])
        names = {type(handler).__name__ for handler in opener.handlers}
        for forbidden in ("FileHandler", "FTPHandler", "CacheFTPHandler", "DataHandler", "ProxyHandler", "HTTPHandler"):
            self.assertNotIn(forbidden, names)

    def test_redirects_inside_the_allowed_area_are_followed_with_a_relative_location(self):
        first, second = f"https://{GOOD_HOST}/v1/a", f"https://{GOOD_HOST}/v1/b"
        opener, transport = self.opener({first: (302, {"Location": "/v1/b"}), second: (200, {})})
        response = opener.open(first)
        self.assertEqual(response.geturl(), second)
        self.assertEqual(transport.sent, [first, second])

    def test_a_redirect_to_another_registered_host_is_followed_and_drops_credentials(self):
        first, second = f"https://{GOOD_HOST}/v1/a", f"https://{self.HOST2}/api/z"
        opener, transport = self.opener({first: (301, {"Location": second}), second: (200, {})})
        request = urllib.request.Request(first, headers={"Authorization": "Bearer SECRET", "X-Api-Key": "K", "Accept": "x"})
        opener.open(request)
        self.assertEqual(transport.sent, [first, second])
        self.assertEqual(transport.headers[0].get("authorization"), "Bearer SECRET")
        self.assertNotIn("authorization", transport.headers[1])                      # 다른 호스트로 따라갈 때 인증 머리글을 뗀다
        self.assertNotIn("x-api-key", transport.headers[1])
        self.assertEqual(transport.headers[1].get("accept"), "x")
        same_first, same_second = f"https://{GOOD_HOST}/v1/a", f"https://{GOOD_HOST}/v1/b"
        opener, transport = self.opener({same_first: (302, {"Location": same_second}), same_second: (200, {})})
        opener.open(urllib.request.Request(same_first, headers={"Authorization": "Bearer SECRET"}))
        self.assertEqual(transport.headers[1].get("authorization"), "Bearer SECRET")      # 같은 호스트면 유지

    def test_a_redirect_out_of_the_allowed_area_is_denied_and_never_sent(self):
        first = f"https://{GOOD_HOST}/v1/a"
        for target in ("https://evil.example/x", f"https://{GOOD_HOST}/v2/x", f"http://{GOOD_HOST}/v1/b", f"https://{GOOD_HOST}:8443/v1/b", f"https://{GOOD_HOST}/v1/%2e%2e/x",
                       "https://api.github.com/repos/o/r/issues", "ftp://x.example/a", f"https://{GOOD_HOST}@evil.example/v1/b"):
            opener, transport = self.opener({first: (302, {"Location": target})})
            with self.subTest(target=target), self.assertRaises((egress.EgressDenied, urllib.error.HTTPError)):
                opener.open(first)
            self.assertEqual(transport.sent, [first], target)                        # 두 번째 요청은 보내지 않았다

    def test_the_redirect_cap_is_three_and_zero_refuses_every_redirect(self):
        chain = {f"https://{GOOD_HOST}/v1/{i}": (302, {"Location": f"/v1/{i + 1}"}) for i in range(5)}
        chain[f"https://{GOOD_HOST}/v1/3"] = (200, {})
        opener, transport = self.opener(chain)
        opener.open(f"https://{GOOD_HOST}/v1/0")                                      # 리다이렉트 3번(0→1→2→3)은 따라간다
        self.assertEqual(len(transport.sent), 4)
        chain[f"https://{GOOD_HOST}/v1/3"] = (302, {"Location": "/v1/4"})
        chain[f"https://{GOOD_HOST}/v1/4"] = (200, {})
        opener, transport = self.opener(chain)
        with self.assertRaises(urllib.error.HTTPError):
            opener.open(f"https://{GOOD_HOST}/v1/0")                                  # 네 번째 리다이렉트는 거부
        self.assertEqual(len(transport.sent), 4)
        opener, transport = self.opener(chain, max_redirects=0)
        with self.assertRaises(urllib.error.HTTPError):
            opener.open(f"https://{GOOD_HOST}/v1/0")                                  # 0 이면 첫 리다이렉트부터 거부
        self.assertEqual(transport.sent, [f"https://{GOOD_HOST}/v1/0"])

    def test_a_redirect_loop_is_refused(self):
        a, b = f"https://{GOOD_HOST}/v1/a", f"https://{GOOD_HOST}/v1/b"
        opener, transport = self.opener({a: (302, {"Location": "/v1/b"}), b: (302, {"Location": "/v1/a"})})
        with self.assertRaises(urllib.error.HTTPError):
            opener.open(a)
        self.assertLessEqual(len(transport.sent), 4)

    def test_the_handlers_can_be_called_directly(self):
        """처리기를 직접 불러 본다: redirect_request 는 새 주소를 판정하고, 요청 처리기는 첫 요청을 판정한다."""
        registry = self.registry()
        handler = egress._CheckedRedirectHandler("fact", registry, None, 3)
        request = urllib.request.Request(f"https://{GOOD_HOST}/v1/a")
        new = handler.redirect_request(request, io.BytesIO(b""), 302, "Found", email.message_from_string("\n"), f"https://{GOOD_HOST}/v1/b")
        self.assertEqual(new.full_url, f"https://{GOOD_HOST}/v1/b")
        with self.assertRaises(egress.EgressDenied):
            handler.redirect_request(request, io.BytesIO(b""), 302, "Found", email.message_from_string("\n"), "https://evil.example/b")
        pre = egress._CheckedHandler("fact", registry, None)
        self.assertIs(pre.https_request(request), request)
        with self.assertRaises(egress.EgressDenied):
            pre.https_request(urllib.request.Request("https://evil.example/"))
        with self.assertRaises(egress.EgressDenied):
            pre.http_request(urllib.request.Request(f"http://{GOOD_HOST}/v1/a"))

    def test_operations_hosts_work_through_the_checked_opener_with_their_own_purpose(self):
        url = "https://api.telegram.org/bot123:ABC/sendMessage"
        transport = FakeHttps({url: (200, {})})
        opener = egress.build_checked_opener("ops_notify", None, https_handler=transport)
        self.assertEqual(opener.open(url).geturl(), url)
        transport = FakeHttps({})
        opener = egress.build_checked_opener("fact", None, https_handler=transport)
        with self.assertRaises(egress.EgressDenied):
            opener.open(url)
        self.assertEqual(transport.sent, [])
        repo_url = "https://api.github.com/repos/owner1/repo1/issues"
        transport = FakeHttps({repo_url: (200, {})})
        egress.build_checked_opener("ops_repo", None, own_repo="owner1/repo1", https_handler=transport).open(repo_url)
        transport = FakeHttps({repo_url: (200, {})})
        with self.assertRaises(egress.EgressDenied):
            egress.build_checked_opener("ops_repo", None, own_repo="owner2/repo2", https_handler=transport).open(repo_url)

    def test_check_final_url_judges_the_address_after_the_fact(self):
        registry = self.registry()
        egress.check_final_url(f"https://{GOOD_HOST}/v1/x", "fact", registry)
        for url in ("https://evil.example/x", f"https://{GOOD_HOST}/v2/x", None, ""):
            with self.subTest(url=url), self.assertRaises(egress.EgressDenied):
                egress.check_final_url(url, "fact", registry)

    def test_the_default_transport_is_the_standard_https_handler(self):
        opener = egress.build_checked_opener("fact", self.registry())
        self.assertIn("HTTPSHandler", {type(handler).__name__ for handler in opener.handlers})


if __name__ == "__main__":
    unittest.main()
