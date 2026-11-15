import sys
sys.path.insert(0, "C:/work/ai/verify_mp1_P2/_probe")
from h import mp, rec, summary

CLEAN = {k: False for k in mp.DECLARED_REQUIRED}
OP, OK = "operator_only", "ai_ok"


def cl(paths, text="", kind="blog"):
    r = mp.classify_change(kind, paths, text, CLEAN)
    return r.tier, ",".join(r.categories + r.extra_flags)


for cid, desc, paths, text, exp in [
    ("M01", ".gitmodules (submodule = external code; info)", [".gitmodules"], "[submodule \"x\"]", OP),
    ("M02", "_data/navigation.yml (Jekyll data, site presentation)", ["_data/navigation.yml"], "- title: x", OP),
    ("M03", "_sass/main.scss (site style)", ["_sass/main.scss"], "a {color: red}", OP),
    ("M04", "_plugins/x.rb", ["_plugins/x.rb"], "x", OP),
    ("M05", ".gitignore (could un-ignore secrets; info)", [".gitignore"], "!.env", OP),
    ("M06", "shell script with unquoted git push origin main (info)", ["scripts/push.sh"], "git push origin main", OP),
    ("M07", "shell script with unquoted curl -X POST (info)", ["scripts/x.sh"], "curl -X POST $URL", OP),
    ("M08", "py: subprocess.run('git push origin main', shell=True)", ["pipeline/x.py"], "subprocess.run('git push origin main', shell=True)", OP),
    ("M09", "py: os.system('git push')", ["pipeline/x.py"], "os.system('git push')", OP),
    ("M10", "py: subprocess git commit (no push; ai_ok ok)", ["pipeline/x.py"], "subprocess.run(['git', 'commit', '-m', 'x'])", OK),
    ("M11", "gh cli quoted: ['gh','pr','merge']", ["pipeline/x.py"], "subprocess.run(['gh', 'pr', 'merge', '1'])", OP),
    ("M12", "gh cli in shell unquoted: gh pr merge 1 (info)", ["scripts/x.sh"], "gh pr merge 1 --squash", OP),
    ("M13", "PR merge API url string (https://api...) in py", ["pipeline/x.py"], "U = 'https://api.github.com/repos/x/y/pulls/1/merge'", OP),
    ("M14", "AGENTS.md (excluded from site; plain doc)", ["AGENTS.md"], "문서", OK),
    ("M15", "인수인계/작업내용.md (excluded; doc)", ["인수인계/작업내용.md"], "문서", OK),
    ("M16", ".design/x.png (dot dir; not published)", [".design/x.png"], "", OK),
    ("M17", "pipeline/draft_flow.py plain edit w/o keywords", ["pipeline/draft_flow.py"], "x = 1", OK),
    ("M18", "generator.py edit (publisher; not covered; info)", ["generator.py"], "post(title)", OK),
    ("M19", "pipeline/publishers/blogger.py edit isDraft toggled (info)", ["pipeline/publishers/blogger.py"], "isDraft = False", OK),
    ("M20", "desktop: external write switch file name guess", ["src/chanceblog_desktop/services/external_write.py"], "ENABLED = True", OK),
]:
    tier, tags = cl(paths, text, "desktop" if paths[0].startswith("src/") else "blog")
    rec(cid, desc, exp, tier, note="tags=" + tags)

# approval + irrelevant state: check_approval_text details for an enumerated sample
for t in ["M075 승인", "m075 승인", "M075승인", "M075 M076 승인", "확인했습니다", "승인", "M075 승인하되 이름은 바꿔 주세요"]:
    c = mp.check_approval_text(t)
    print("  approval-detail %-30r -> number=%r reason=%s" % (t, c.number, c.reason))
summary()
