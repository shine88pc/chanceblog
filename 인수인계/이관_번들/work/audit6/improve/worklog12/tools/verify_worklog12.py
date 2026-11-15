"""WORKLOG12 사실 점검 — 작업 폴더(또는 변이 시험용 사본)의 두 문서가 git·요청 가지·번호 도구·공개 값과 맞는지 기계로 대조한다(읽기 전용).

사용: python -X utf8 verify_worklog12.py --root <저장소 루트> [--posts 38 --sitemap 45 --feed 38 --ads 1] [--skip-git] [--quiet]
종료 코드: 0 = 모두 통과 / 1 = 하나라도 어긋남.  --skip-git 이면 git·번호 도구가 필요한 대조는 건너뛴다(구조·자리표·크기만).
"""
import argparse
import json
import re
import subprocess
import sys

BLOG = "C:/work/ai/wt_r30"
APP = "C:/work/ai/cd_repo"
REQ_REF = "origin/ai/claude/NO-MERGE-operator-requests"
REQ_DIR = "인수인계/요청함/"

ap = argparse.ArgumentParser()
ap.add_argument("--root", required=True)
ap.add_argument("--posts", type=int, default=38)
ap.add_argument("--sitemap", type=int, default=45)
ap.add_argument("--feed", type=int, default=38)
ap.add_argument("--ads", type=int, default=1)
ap.add_argument("--skip-git", action="store_true")
ap.add_argument("--freeze", default="", help="snapshot_truth.py 가 만든 값(머리·마지막 번호·다음 번호)으로 스냅샷 대조 — 그 뒤 생긴 일은 무시")
ap.add_argument("--quiet", action="store_true")
args = ap.parse_args()

fails = []
passes = 0


def ok(cond, label, detail=""):
    global passes
    if cond:
        passes += 1
        if not args.quiet:
            print("  ok  ", label)
    else:
        fails.append(label)
        print("  FAIL", label, detail)


def git(repo, *a):
    r = subprocess.run(["git", "-C", repo, "-c", "core.quotepath=false", *a], capture_output=True, encoding="utf-8")
    return r.stdout


def read(rel):
    with open(args.root + "/" + rel, "r", encoding="utf-8", newline="") as h:
        return h.read().replace("\r\n", "\n")


doc = read("인수인계/작업내용.md")
wl = read("WORKLOG.md")
lines = doc.split("\n")

# ---------------------------------------------------------------- 구조
print("[구조]")
ok("@@" not in doc and "@@" not in wl, "자리표(@@) 없음")
for needle in ("### 0-7. 혼자 이어 가는 길", "17. **소통 방식 전환(운영자 2026-11-13 오후 마지막 채팅 지시)**", "18. **프로그램 성능을 높이는 개선은 AI 가 스스로 진행",
               "18. **(2026-11-13 저녁 갱신) 지금 운영자만 할 수 있는 일", "**마지막 갱신 이후 추가", "**개선 발굴 완료와 백로그 요약", "**알림 목록 R-301–R-3",
               "**병합 7건 표(11-13", "| 42 | **텔레그램 확인 012(R-307", "| 43 | **텔레그램 확인 013(R-309", "| 44 | **텔레그램 확인 014(R-310", "| 45 | **아직 안 보낸 텔레그램 확인 015"):
    ok(needle in doc, "문서에 있음: " + needle[:46])
i17 = doc.index("17. **소통 방식 전환(운영자 2026-11-13 오후 마지막 채팅 지시)**")
i18 = doc.index("18. **프로그램 성능을 높이는 개선은 AI 가 스스로 진행")
item17 = doc[i17:i18]
item18 = doc[i18:doc.index("\n", i18)]
for needle in ("텔레그램", "이슈", "저장소 소유자", "채팅"):
    ok(needle in item17, "0-2 17번에 낱말 '%s'" % needle)
for needle in ("병합은 운영자만", "독립 검증", "T3", "PIPELINE_PAUSE", "제안만", "이슈 답"):
    ok(needle in item18, "0-2 18번에 낱말 '%s'" % needle)
four = doc[doc.index("18. **(2026-11-13 저녁 갱신)"):doc.index("\n", doc.index("18. **(2026-11-13 저녁 갱신)"))]
for needle in ("013/1/", "PIPELINE_PAUSE", "Variables", "resume_gate_passed", "이어서 진행해줘", "저장소 인수인계/작업내용.md 맨 위 §0 부터 읽고 이어서 진행해줘"):
    ok(needle in four, "§4 18번에 '%s'" % needle[:30])
s07 = doc[doc.index("### 0-7. 혼자 이어 가는 길"):doc.index("## 1. 한눈에 보기")]
for needle in ("23:00", "이어서 진행해줘", "GitHub 쪽 자동화", "저장소 인수인계/작업내용.md 맨 위 §0 부터 읽고 이어서 진행해줘", "예약 작업"):
    ok(needle in s07, "§0-7 에 '%s'" % needle[:30])
# 마지막 갱신 이후 추가 줄은 2026-11-13 절의 맨 아래(다음 날짜 머리 바로 앞 마지막 항목)
d13 = doc.index("\n### 2026-11-13\n")
d12 = doc.index("\n### 2026-11-12\n")
block13 = doc[d13:d12].rstrip("\n").split("\n")
ok(block13[-1].startswith("- **마지막 갱신 이후 추가"), "'마지막 갱신 이후 추가' 가 2026-11-13 절의 맨 아래 줄")
# 백로그 요약 크기 8–10KB 이내(문서 안 표)
b0 = doc.index("- **개선 발굴 완료와 백로그 요약")
b1 = doc.index("- **제한 사용 시작 보고 10항목")
size = len(doc[b0:b1].encode("utf-8"))
ok(size <= 10240, "백로그 요약 크기 10KB 이하(%d바이트)" % size)
ok(size >= 4000, "백로그 요약이 너무 짧지 않음(%d바이트)" % size)
tbl = doc[b0:b1]
ok(all(("| L%d |" % n) in tbl for n in range(1, 9)), "백로그 표에 L1–L8 모두")
ok(all(("| AP%d |" % n) in tbl for n in range(1, 19)), "백로그 표에 AP1–AP18 모두")
ok("W1 " in tbl and "W16 " in tbl, "백로그 요약에 W1–W16")
# 표 칸 수
bad = []
for name, text in (("작업내용.md", doc), ("WORKLOG.md", wl)):
    ls = text.split("\n")
    i = 0
    while i < len(ls):
        if ls[i].startswith("|"):
            j = i
            while j < len(ls) and ls[j].startswith("|"):
                j += 1
            want = ls[i].count("|")
            bad += [(name, i + k + 1) for k in range(j - i) if ls[i + k].count("|") != want]
            i = j
        else:
            i += 1
ok(not bad, "표 칸 수가 모두 맞음", str(bad[:3]))

# ---------------------------------------------------------------- WORKLOG.md
print("[WORKLOG.md]")
wl_lines = wl.split("\n")
first_entry = next(i for i, ln in enumerate(wl_lines) if ln.startswith("## ["))
ok(wl_lines[first_entry].startswith("## [2026-11-13] Claude – DOC: 인수인계/작업내용.md 현행화 12차(WORKLOG12)"), "WORKLOG.md 맨 위 항목이 이번 현행화")
entry = "\n".join(wl_lines[first_entry:first_entry + 40])
for needle in ("**작업자**", "**대상**", "**등급**", "**목적**", "### 변경 사항", "### 검증 증거", "### 남은 이슈 / 다음 AI 주의", "확인 필요"):
    ok(needle in entry, "WORKLOG 항목에 '%s'" % needle)

# ---------------------------------------------------------------- 숫자(공개 값)
print("[공개 값]")
ok(("공개 글 %d편" % args.posts) in doc and ("사이트맵 %d" % args.sitemap) in doc and ("피드 %d" % args.feed) in doc, "공개 글·사이트맵·피드 숫자가 문서에 있음")
live_line = doc[doc.index("### 0-3. 진행 중인 일과 다음 행동"):doc.index("### 0-4.")]
ok(("공개 글 %d편·사이트맵 %d·피드 %d·광고 스크립트 %d줄" % (args.posts, args.sitemap, args.feed, args.ads)) in live_line, "0-3 의 공개 상태 문장이 읽은 값과 같음")
sec6 = doc[doc.index("## 6. 블로그별 현황"):doc.index("## 7. 이 문서 쓰는 법")]
ok(("공개 글 %d편·사이트맵 %d·피드 %d" % (args.posts, args.sitemap, args.feed)) in sec6, "§6 Chance 줄 숫자가 읽은 값과 같음")

if args.skip_git:
    print("(git 대조 건너뜀)")
else:
    # ------------------------------------------------------------ git 대조
    print("[git 사실]")
    frz = json.load(open(args.freeze, encoding="utf-8")) if args.freeze else None
    blog_head = frz["blog_head"] if frz else git(BLOG, "rev-parse", "--short=7", "origin/main").strip()
    app_head = frz["app_head"] if frz else git(APP, "rev-parse", "--short=7", "origin/main").strip()
    root_head = frz["root_head"] if frz else "2f699ba"
    head_txt = doc[:doc.index("\n## 0. 이어가기")]
    ok(("`main` %s(" % blog_head) in head_txt, "머리 기준의 블로그 main 머리가 origin/main(%s)" % blog_head)
    ok(("`main` %s(" % app_head) in head_txt, "머리 기준의 앱 main 머리가 origin/main(%s)" % app_head)
    ok(("`main` %s(" % root_head) in head_txt, "머리 기준의 루트 main 머리(%s)" % root_head)
    ok(("`%s`" % blog_head) in live_line, "0-3 의 블로그 main 머리")
    ok(("`%s`" % app_head) in live_line, "0-3 의 앱 main 머리")

    def timemap(repo):
        out = git(repo, "log", "--first-parent", "origin/main", "-80", "--format=%h|%cd", "--date=format:%m-%d %H:%M")
        return {ln.split("|")[0]: ln.split("|")[1] for ln in out.strip().split("\n") if "|" in ln}

    blog_t, app_t = timemap(BLOG), timemap(APP)
    rows = [ln for ln in lines if re.match(r"^\| M06[0-6] \|", ln)]
    ok(len(rows) == 7, "병합 표에 M060–M066 일곱 행(%d)" % len(rows))
    for ln in rows:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        num, req, repo_pr, _content, merged = cells
        m = re.match(r"11-13 (\d\d:\d\d) \(main ([0-9a-f]{7})\)", merged)
        ok(bool(m), "%s 병합 칸 모양" % num, merged)
        if not m:
            continue
        tmap = app_t if repo_pr.startswith("데스크톱") else blog_t
        ok(m.group(2) in tmap and tmap[m.group(2)] == "11-13 " + m.group(1), "%s 병합 시각·머리 해시가 git 과 같음" % num, "%s %s" % (m.group(2), tmap.get(m.group(2))))
        repo = APP if repo_pr.startswith("데스크톱") else BLOG
        parents = git(repo, "log", "-1", "--format=%p", m.group(2)).split()
        ok(len(parents) >= 1, "%s 부모 존재" % num)
        if repo_pr.startswith("블로그"):
            ok(len(parents) == 1, "%s 블로그 병합은 부모 하나(squash)" % num, str(parents))
            ok(("%s" % req) in doc, "%s 요청 번호 %s 가 문서에 있음" % (num, req))
    # 알림 목록 대조
    names = git(BLOG, "ls-tree", "--name-only", REQ_REF, REQ_DIR).strip().split("\n")
    rfiles = {}
    for nm in names:
        mm = re.match(r"인수인계/요청함/(R-(\d+))_", nm)
        if mm:
            rfiles[int(mm.group(2))] = nm
    max_r = frz["max_r"] if frz else max(rfiles)
    ok(("R-%d" % (max_r + 1)) in doc[doc.index("번호 현황(2026-11-13 저녁 스냅샷"):doc.index("번호 현황(2026-11-13 저녁 스냅샷") + 3000], "0-5 의 다음 요청 번호 R-%d" % (max_r + 1))
    rrows = [ln for ln in lines if re.match(r"^\| R-3\d\d \|", ln)]
    seen = set()
    for ln in rrows:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        rid, hhmm, kindno, _desc = cells
        n = int(rid.split("-")[1])
        seen.add(n)
        ok(n in rfiles, "%s 요청 파일이 요청 가지에 있음" % rid)
        if n not in rfiles:
            continue
        body = git(BLOG, "show", "%s:%s" % (REQ_REF, rfiles[n]))
        fm = body.split("---")[1] if body.startswith("---") else ""
        kind = re.search(r"^kind: (\S+)", fm, re.M)
        no = re.search(r'^no: "?([A-Z]?\d+)"?', fm, re.M)
        kind, no = (kind.group(1) if kind else ""), (no.group(1) if no else "")
        want = {"merge": "병합 부탁 " + no, "merged": "병합완료 확인 " + no, "info": "진행 현황 " + no, "run": "확인 " + no, "decision": "확인 " + no}.get(kind, "?")
        ok(kindno.startswith(want), "%s 종류·번호 '%s' 가 요청 파일(%s %s)과 맞음" % (rid, kindno, kind, no))
        t = git(BLOG, "log", REQ_REF, "--diff-filter=A", "--format=%cd", "--date=format:%H:%M", "--", rfiles[n]).strip().split("\n")[-1]
        ok(t == hhmm, "%s 시각 %s 가 요청 파일이 올라간 시각(%s)과 같음" % (rid, hhmm, t))
    ok(seen == set(range(301, max_r + 1)), "알림 목록이 R-301–R-%d 전부" % max_r, str(sorted(set(range(301, max_r + 1)) - seen)))
    ok(("R-%d" % max_r) in doc, "요청 가지의 마지막 R 번호(R-%d)가 문서에 있음" % max_r)
    # 번호 도구
    if frz:
        nums = (frz["next_p"], frz["next_m"], frz["next_c"])
    else:
        nn = subprocess.run([sys.executable, "-X", "utf8", "C:/work/ai/next_notice_no.py", "--repo", BLOG, "--dir", BLOG, "--local"], capture_output=True, encoding="utf-8").stdout
        p_next = re.search(r"P 다음 번호: (P\d+)", nn)
        m_next = re.search(r"M 다음 번호: (M\d+)", nn)
        c_next = re.search(r"확인 다음 번호: (\d+)", nn)
        ok(bool(p_next and m_next and c_next), "번호 도구 출력 읽음", nn[:120])
        nums = (p_next.group(1), m_next.group(1), c_next.group(1)) if (p_next and m_next and c_next) else None
    if nums:
        seg = doc[doc.index("번호 현황(2026-11-13 저녁 스냅샷"):doc.index("번호 현황(2026-11-13 저녁 스냅샷") + 3000]
        ok(all(("`%s`" % n) in seg for n in (nums[1], nums[0], nums[2])), "0-5 의 다음 번호 %s·%s·%s 가 번호 도구(또는 스냅샷)와 같음" % (nums[1], nums[0], nums[2]))
    # 이슈 번호가 있는 요청 가지 머리
    rh = frz["req_head"] if frz else git(BLOG, "rev-parse", "--short=7", REQ_REF).strip()
    ok(rh in doc, "0-5 의 요청 가지 머리 %s" % rh)

print("\n통과 %d · 실패 %d" % (passes, len(fails)))
for f in fails:
    print("  - 실패:", f)
sys.exit(1 if fails else 0)
