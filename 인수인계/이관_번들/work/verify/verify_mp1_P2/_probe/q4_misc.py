import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P2/_probe")
from h import mp, rec, summary

CLEAN = {k: False for k in mp.DECLARED_REQUIRED}
OP, OK = "operator_only", "ai_ok"
A = "1" * 40
PATHS = ["pipeline/calc.py"]


def tier(paths, text, kind="blog"):
    return mp.classify_change(kind, paths, text, CLEAN)


def has_ext(paths, text, kind="blog"):
    r = tier(paths, text, kind)
    return "external_connection" in r.extra_flags


# ======== str subclass defences (I2)
class S(str):
    pass


class Eq(str):
    def __eq__(self, o):
        return True
    __hash__ = str.__hash__


class Strip(str):
    def strip(self, *a, **k):
        return "M075 승인"


rec("Z01", "parse_approval(Strip('hello')) -> None", None, mp.parse_approval(Strip("hello")))
rec("Z02", "parse_approval(S('M075 승인')) -> None (subclass refused)", None, mp.parse_approval(S("M075 승인")))
rec("Z03", "merge_method_allowed(Eq('x')) -> False", False, mp.merge_method_allowed(Eq("x")))
rec("Z04", "merge_method_allowed(S('pr_merge')) -> False", False, mp.merge_method_allowed(S("pr_merge")))
rec("Z05", "approval_matches(S('M075'), 'M075') -> False", False, mp.approval_matches(S("M075"), "M075"))
rec("Z06", "approval_matches(Eq('M075'), 'M076') -> False", False, mp.approval_matches(Eq("M075"), "M076"))
rec("Z07", "pr_title_label(S('[M075] x')) -> None", None, mp.pr_title_label(S("[M075] x")))
rec("Z08", "approval_still_valid with S sha -> False", False, mp.approval_still_valid(S(A), A, ["a.py"], ["a.py"]))
rec("Z09", "ApprovalLedger.consume(S('M075'), 1) refused", False, mp.ApprovalLedger().consume(S("M075"), 1).ok)
rec("Z10", "ApprovalLedger.consume(Eq('M075'), 1) refused", False, mp.ApprovalLedger().consume(Eq("M075"), 1).ok)
rec("Z11", "check_approval_text(Strip) reason", "empty", mp.check_approval_text(Strip("x")).reason)


class I(int):
    def __gt__(self, o):
        return True

    def __ge__(self, o):
        return True


rec("Z12", "INFO: int subclass with overridden __gt__ as PR number (_positive_int uses isinstance)", False, mp.ApprovalLedger().consume("M075", I(-5)).ok, note="INFO: int subclass not refused")
rec("Z13", "ledger bool PR refused", False, mp.ApprovalLedger().consume("M075", True).ok)

# ======== shell scripts (S6): unquoted network commands
sh_cases = [
    ("SH01", ["scripts/push.sh"], "git push origin main", True), ("SH02", ["scripts/x.sh"], "curl -X POST $URL", True), ("SH03", ["scripts/x.sh"], "gh pr merge 1 --squash", True),
    ("SH04", ["scripts/x.ps1"], "Invoke-WebRequest -Uri $u", True), ("SH05", ["scripts/x.ps1"], "iwr $u", True), ("SH06", ["scripts/x.bat"], "curl http2.example.org/x", True),
    ("SH07", ["scripts/x.cmd"], "wget $u", True), ("SH08", ["scripts/x.sh"], "ssh host ls", True), ("SH09", ["scripts/x.bash"], "scp a b:c", True), ("SH10", ["scripts/x.sh"], "rsync -a . host:/x", True),
    ("SH11", ["scripts/x.sh"], "nc -l 80", True), ("SH12", ["scripts/x.sh"], "git pull origin main", True), ("SH13", ["scripts/x.sh"], "git fetch --all", True), ("SH14", ["scripts/x.sh"], "git clone repo", True),
    ("SH15", ["scripts/x.sh"], "git submodule update", True), ("SH16", ["scripts/x.sh"], "git remote add o u", True), ("SH17", ["scripts/x.sh"], "Invoke-RestMethod $u", True),
    ("SH18", ["scripts/x.sh"], "echo hello", False), ("SH19", ["scripts/x.sh"], "git commit -m x", False), ("SH20", ["scripts/x.sh"], "git status", False),
    ("SH21", ["scripts/x.sh"], "ssh-keygen -t ed25519", False), ("SH22", ["scripts/x.sh"], "export GH_TOKEN=x", True), ("SH23", ["scripts/x.sh"], "pycurl_install", False),
    ("SH24", ["scripts/x.py"], "git push origin main", False), ("SH25", ["scripts/x.sh", "docs/y.md"], "git push origin main", True), ("SH26", ["scripts/x.sh"], "CURL -X POST $URL", True),
    ("SH27", ["scripts/x.sh"], "python -c \"import urllib.request; urllib.request.urlopen(u)\"", True), ("SH28", ["scripts/x.sh"], "openssl s_client -connect host:443", False),
    ("SH29", ["scripts/x.sh"], "socat TCP:host:80 -", False), ("SH30", ["scripts/x.sh"], "aria2c http2example", False), ("SH31", ["scripts/x.sh"], "npm publish", False),
    ("SH32", ["scripts/x.sh"], "docker push img", False), ("SH33", ["scripts/x.sh"], "pip install requests", False),
]
for cid, paths, text, exp in sh_cases:
    got = has_ext(paths, text)
    rec(cid, "shell %s: %r -> external_connection=%s" % (paths[0], text, exp), exp, got, note="INFO" if (not exp and got is False and cid in ("SH28", "SH29", "SH30", "SH31", "SH32", "SH33")) else "")
# py file: quoted network commands remain
for cid, text in [("SQ1", 'subprocess.run(["curl", u])'), ("SQ2", 'os.system("wget x")'), ("SQ3", "Popen(['git', 'push'])"), ("SQ4", "subprocess.run(['gh', 'pr', 'merge', '1'])"), ("SQ5", "subprocess.run(['git', 'ls-remote', u])")]:
    rec(cid, "py quoted network cmd %r" % text, True, has_ext(["pipeline/x.py"], text))
# gopher and protocol-relative and quoted hosts
for cid, text, exp in [
    ("NH1", 'U = "gopher://evil.com:70/"', True), ("NH2", 'var s = "//evil.com/t.js";', True), ("NH3", 'HOST = "collector.evil.ru"', True), ("NH4", "HOST = 'evil.in'", True),
    ("NH5", 'HOST = "evil.tk"', True), ("NH6", 'HOST = "evil.cn"', True), ("NH7", 'HOST = "x.evil.com"', True), ("NH8", 'HOST = "evil.xyz"', True), ("NH9", 'HOST = "evil.top"', True),
    ("NH10", 'HOST = "evil.live"', True), ("NH11", 'HOST = "evil.shop"', True), ("NH12", 'HOST = "evil.dev"', True),
    ("NH13", 'HOST = "evil.sh"', False), ("NH14", 'HOST = "evil.py"', False), ("NH15", 'HOST = "evil.md"', False), ("NH16", 'HOST = "evil.so"', False), ("NH17", 'HOST = "evil.cc"', False),
    ("NH18", 'HOST = "evil.ps"', False), ("NH19", 'HOST = "evil.pl"', False), ("NH20", 'HOST = "evil.rs"', False), ("NH21", 'HOST = "evil.ml"', False), ("NH22", 'HOST = "evil.pm"', False),
    ("NH23", 'U = "https://evil.sh/x"', True), ("NH24", 'U = "https://evil.so/x"', True), ("NH25", 'U = "//evil.sh/x.js"', False),
    ("NH26", 'HOST = "evil.example"', False), ("NH27", 'HOST = "evil.test"', False), ("NH28", 'HOST = "x.example.com"', False), ("NH29", 'HOST = "evil.invalid"', False),
    ("NH30", "U = 'https://<이메일>/'", True), ("NH31", "U = 'https://evil.com#@example.com'", True),
]:
    got = has_ext(["pipeline/x.py"], text)
    rec(cid, "quoted host/URL %r -> flagged=%s" % (text, exp), exp, got, note=("INFO documented FILE_NAME_TLDS gap" if (exp is False and cid in ("NH13", "NH15", "NH16", "NH17", "NH18", "NH19", "NH20", "NH21", "NH22", "NH25")) else ""))
# false positives of the widened domain rule (information)
fp = [("FP1", "os.path", "x = 'os.path'"), ("FP2", "self.name", "k = 'self.name'"), ("FP3", "pipeline.store", "m = 'pipeline.store'"), ("FP4", "dotted ids 'row.id'", "k = 'row.id'"),
      ("FP5", "'obj.is'", "k = 'obj.is'"), ("FP6", "'a.to'", "k = 'a.to'"), ("FP7", "'requirements.in'", "f = 'requirements.in'"), ("FP8", "'config.dev'", "k = 'config.dev'"), ("FP9", "'data.app'", "k = 'data.app'"),
      ("FP10", "'run.py'", "f = 'run.py'"), ("FP11", "'README.md'", "f = 'README.md'"), ("FP12", "'index.js'", "f = 'index.js'"), ("FP13", "'my.config'", "f = 'my.config'"), ("FP14", "'version.txt'", "f = 'version.txt'"),
      ("FP15", "'x.json'", "f = 'x.json'"), ("FP16", "'archive.tar.gz'", "f = 'archive.tar.gz'"), ("FP17", "'a.b.c'", "f = 'a.b.c'"), ("FP18", "'module.sh'", "f = 'module.sh'")]
for cid, desc, text in fp:
    got = has_ext(["pipeline/x.py"], text)
    print("  FP-info %-5s %-26s flagged=%s" % (cid, desc, got))
# ======== modules / calls still caught (regression)
for cid, text in [("EC1", "import requests"), ("EC2", "from urllib import request"), ("EC3", "import socket"), ("EC4", "m = __import__('socket')"), ("EC5", "importlib.import_module('requests')"),
                  ("EC6", "urlopen(u)"), ("EC7", "exec(code)"), ("EC8", "import anthropic"), ("EC9", "from google import genai"), ("EC10", "socket.create_connection((h, 80))"),
                  ("EC11", "socket.getaddrinfo(h, 80)"), ("EC12", "import aiohttp"), ("EC13", "asyncio.open_connection(h, 80)"), ("EC14", 'U = "ws://evil.com"'), ("EC15", 'U = "https://api.github.com/x"')]:
    rec(cid, "regression: %r" % text, True, has_ext(["pipeline/x.py"], text))
rec("EC16", "external text in docs/ md exempt", False, has_ext(["docs/x.md"], "import requests"))
rec("EC17", "external text in tests/ exempt", False, has_ext(["tests/test_x.py"], "import requests"))
rec("EC18", "external text in Tests/ (capital) NOT exempt", True, has_ext(["Tests/test_x.py"], "import requests"))
rec("EC19", "external text in pipeline/tests/ NOT exempt", True, has_ext(["pipeline/tests/test_x.py"], "import requests"))

# ======== PR open / draft defence via check_preconditions is covered in q2; classify tier checks for misc kinds
rec("K1", "classify with repo_kind='blog' str subclass -> invalid", OP, mp.classify_change(S("blog"), ["docs/x.md"], "x", CLEAN).tier)
rec("K2", "classify with changed path str subclass accepted (strings are strings)", OK, mp.classify_change("blog", [S("docs/x.md")], "x", CLEAN).tier)
rec("K3", "classify with changed_text str subclass treated as text", OK, mp.classify_change("blog", ["docs/x.md"], S("문서"), CLEAN).tier)
summary()
