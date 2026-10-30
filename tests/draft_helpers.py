"""승인 흐름(pipeline/drafts.py·draft_flow.py) 테스트 공용 도구: 가짜 git, 임시 bare origin + 로컬 clone, 가짜 GitHub, 글·이력 만들기.

네트워크·실제 시크릿 없이 돈다. 실제 git 은 임시 디렉터리 안에서만 쓰고, 이 PC 의 git 설정(줄 끝 변환·서명·사용자)에 기대지 않도록
시스템·전역 설정을 끄고(GIT_CONFIG_NOSYSTEM·빈 전역 설정) 작성자는 명령행으로 넣는다. git 프로세스 하나를 띄우는 데 0.3초 넘게 걸리는 PC가 있어서
(1) 판단 규칙·실패 처리는 명령을 기록하고 정해 둔 결과를 돌려주는 가짜 git(`FakeGit`)으로 시험하고, (2) 실제 git 은 꼭 필요한 이야기 몇 개에만 쓰며,
(3) bare origin 과 작업 clone 은 클래스마다 한 번만 만들어 시험마다 폴더를 복사한다(`OriginTemplate`·`Sandbox`: git 프로세스 0개).
"""
import fnmatch
import json
import os
import re
import shutil
import subprocess
import tempfile
import types
from pathlib import Path

import _bootstrap
from pipeline import draft_flow, drafts

ROOT = _bootstrap.ROOT

LINK = "https://www.reuters.com/a"
REPO = "shine88pc/chanceblog"

# 진짜 레지스트리(pipeline/blogs.json)의 chance.publish_flow 가 지금 가져야 할 값. 승인 흐름을 켜는 변경(T3, 게시 방식)은 blogs.json 의 한 줄과
# 이 한 줄을 함께 바꾼다. 시험이 값을 못 박아 두므로 레지스트리만 슬쩍 바뀌면 빨강이 되고(표지판), 둘을 함께 바꾸면 나머지 시험이 모두 통과한다
# (docs/ACTIONS_GUIDE.md 3-17 '켜는 법', `pr` 로 바꾼 사본의 전체 시험 통과를 확인했다). 이 값을 읽는 표지판 시험: tests/test_drafts.py(셋)·
# tests/test_generator_drafts.py·tests/test_batch2_integration.py(test_the_real_registry_is_unchanged_by_the_merge)·
# tests/test_ops_inbox_drafts.py(test_the_real_registry_gives_chance_blogger_and_package_rows_with_nothing_pending) — 값을 따로 적은 시험이 없어야 두 줄로 끝난다.
REAL_PUBLISH_FLOW = "direct"


class HermeticGit:
    """git 설정이 이 PC 에 기대지 않는 환경 변수 묶음(시험이 만드는 모든 git 프로세스에 쓴다)."""

    def __init__(self, root):
        empty = Path(root) / "empty.gitconfig"
        empty.write_text("", encoding="utf-8")
        # 작성자 환경 변수(GIT_AUTHOR_*)는 일부러 두지 않는다: 그 값이 있으면 draft_flow 가 명령행(-c)으로 넣는 봇 작성자를 덮어쓴다
        self.env = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(empty), "GIT_TERMINAL_PROMPT": "0"}

    def run(self, cwd, *args, check=True):
        proc = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "core.quotepath=off",
                               "-c", "commit.gpgsign=false", *args],
                              cwd=str(cwd), env={**os.environ, **self.env}, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if check and proc.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} 실패: {proc.stderr.strip()}")
        return proc


class OriginTemplate:
    """한 번 만들어 두고 시험마다 폴더째 복사하는 bare origin 과 그 clone(브랜치 main, 빈 이력 한 파일과 README 한 커밋)."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.git = HermeticGit(root)
        seed = root / "seed"
        seed.mkdir()
        self.git.run(seed, "init", "-q", "-b", "main")
        (seed / "history.json").write_bytes(b"[]\n")
        (seed / "README.md").write_bytes(b"seed\n")
        (seed / "_posts").mkdir()
        (seed / "_posts" / "keep.txt").write_bytes(b"keep\n")
        self.git.run(seed, "add", "-A")
        self.git.run(seed, "commit", "-q", "-m", "seed")
        self.bare = root / "origin-template.git"
        self.git.run(root, "clone", "-q", "--bare", str(seed), str(self.bare))
        self.work = root / "work-template"
        self.git.run(root, "clone", "-q", str(self.bare), str(self.work))

    def close(self):
        self.tmp.cleanup()


class Sandbox:
    """시험 하나의 작업 공간: 템플릿을 복사한 origin 과 그 작업 clone('work'). 만드는 데 git 프로세스를 쓰지 않는다(폴더 복사 + 설정의 주소 교체).
    clone(name) 은 실제 git clone — '새 실행기가 최신 main 을 받는' 일을 흉내 낼 때 쓴다. close() 로 지운다."""

    def __init__(self, template):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git = template.git
        self.origin = self.root / "origin.git"
        shutil.copytree(template.bare, self.origin)
        self.work = self.root / "work"
        shutil.copytree(template.work, self.work)
        config = self.work / ".git" / "config"
        text = config.read_text(encoding="utf-8")
        config.write_bytes(re.sub(r"(?m)^(\s*url = ).*$", lambda m: m.group(1) + self.origin.as_posix(), text).replace("\r\n", "\n").encode("utf-8"))

    def close(self):
        self.tmp.cleanup()

    def clone(self, name):
        dest = self.root / name
        self.git.run(self.root, "clone", "-q", str(self.origin), str(dest))
        return dest

    def sh(self, cwd, *args, check=True):
        return self.git.run(cwd, *args, check=check)

    def origin_branches(self):
        out = self.sh(self.origin, "for-each-ref", "--format=%(refname:short)", "refs/heads").stdout
        return sorted(line for line in out.splitlines() if line)

    def origin_show(self, ref, path):
        proc = self.sh(self.origin, "show", f"{ref}:{path}", check=False)
        return proc.stdout if proc.returncode == 0 else None

    def origin_history(self, ref="main"):
        text = self.origin_show(ref, "history.json")
        return json.loads(text) if text else None

    def origin_files(self, ref, folder="_posts"):
        return sorted(self.sh(self.origin, "ls-tree", "-r", "--name-only", ref, folder, check=False).stdout.splitlines())

    def commits(self, *rev_args, cwd=None):
        """git log 한 번으로 [(작성자, 메일, 제목, [바뀐 파일])...](최신 먼저). 질의 하나가 프로세스 하나라서 묶어서 묻는다."""
        out = self.sh(cwd or self.origin, "log", "--name-only", "--format=%x01%an|%ae|%s", *rev_args).stdout
        found = []
        for block in out.split("\x01")[1:]:
            head, _, files = block.partition("\n")
            who, mail, subject = head.split("|", 2)
            found.append((who, mail, subject, [line for line in files.splitlines() if line.strip()]))
        return found

    def git_git(self, cwd=None):
        """draft_flow.Git: 이 샌드박스의 git 환경을 쓰는 실행부 래퍼."""
        return draft_flow.Git(cwd=cwd or self.work, env=self.git.env)


def post_text(title, link=LINK, body_chars=140, notice=True):
    """승인 PR 본문 시험용 글 파일 내용(front matter + 본문 + 출처 목록 + 고지문). 기본 분량은 한국어 1000자·영어 1500자 기준을 모두 넘는다."""
    front = f'---\nlayout: post\ntitle: "{title}"\ncategory: "기술·미래"\ntags: []\nlang: ko\nsource_name: "Reuters"\n---\n\n'
    body = ("이 글은 시험용 본문입니다. " * body_chars) + f"\n\n근거는 [원문]({link})에 있습니다.\n"
    sources = f"\n## 출처\n- [Reuters: 원문 기사]({link})\n"
    tail = "\n*이 글은 AI 도구가 작성했고 출처는 검토나 승인을 하지 않았습니다. 분석과 해석의 책임은 이 사이트에 있습니다.*\n" if notice else ""
    return front + body + sources + tail


def write_draft(clone, date="2026-10-28", slot=9, stamp=None, topic="후보 기사", kr_title="초안 제목", en_title="Draft title",
                lane="technology", source_url=LINK, kr_text=None, en_text=None, extra=None):
    """generator.py 가 승인 흐름에서 하는 일을 흉내 낸다: 글 두 개를 쓰고 이력 항목(flow·branch·paths 포함)을 덧붙인다. 돌려주는 값: 항목."""
    clone = Path(clone)
    suffix = (stamp or f"{slot:02d}0000")
    kr_path = f"_posts/기술·미래/{date}-KR-{suffix}.md"
    en_path = f"_posts/Technology & Future/{date}-EN-{suffix}.md"
    for rel, text in ((kr_path, kr_text or post_text(kr_title, source_url)), (en_path, en_text or post_text(en_title, source_url))):
        target = clone / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    history_file = clone / "history.json"
    history = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else []
    entry = {"date": date, "topic": topic, "kr_title": kr_title, "en_title": en_title,
             "kr_image": f"https://images.unsplash.com/photo-{suffix}k", "en_image": f"https://images.unsplash.com/photo-{suffix}e",
             "slot": slot, "lane": lane, "source": "Reuters", "source_url": source_url}
    entry.update(drafts.entry_fields(date, slot, stamp, [kr_path, en_path]))
    entry.update(extra or {})
    history.append(entry)
    history_file.write_bytes((json.dumps(history[-200:], ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return entry


class FakeGit:
    """draft_flow.Git 의 대역: 실제 git 을 부르지 않고 명령을 calls 에 기록하며, 정해 둔 결과를 돌려준다.

    - history_head: `git show HEAD:history.json` 이 돌려줄 글(이번 실행 전의 이력).
    - remote: ls-remote 가 돌려줄 원격 브랜치 {이름: 해시}. 초안 브랜치 push 와 삭제는 이 사전을 고친다.
    - branch_files: `git show FETCH_HEAD:<경로>` 가 돌려줄 글 {경로: 내용}(PR 다시 열기 시험).
    - queue_failure(키, returncode, stderr, times): 그 종류의 명령을 앞에서부터 times 번 실패시킨다. 키는 push-branch(초안 브랜치 push)·
      push-base(기준 브랜치로 이력 push)·push-delete(삭제)·pull·ls-remote 이거나 첫 인자(checkout·add·commit·fetch …).
    path(상대경로)는 root 아래 실제 파일이다(글·이력은 진짜 파일로 쓴다)."""

    def __init__(self, root, history_head="[]\n", branch="main", remote=None, shallow=True):
        self.cwd, self.secrets, self.env = str(root), (), {}
        self.calls, self.failures = [], {}
        self.history_head, self.branch, self.shallow = history_head, branch, shallow
        self.remote = dict(remote or {})
        self.branch_files = {}

    def path(self, rel):
        return Path(self.cwd) / rel

    def queue_failure(self, key, returncode=1, stderr="rejected", times=1):
        self.failures.setdefault(key, []).extend([(returncode, stderr)] * times)

    def names(self):
        """부른 명령의 첫 인자 목록."""
        return [call[0] for call in self.calls]

    def calls_of(self, name):
        return [call for call in self.calls if call[0] == name]

    def _fail(self, key):
        queue = self.failures.get(key)
        return queue.pop(0) if queue else None

    def run(self, *args, check=True):
        self.calls.append(tuple(args))
        returncode, out, err = self._respond(args)
        if check and returncode != 0:
            raise draft_flow.GitError(args, returncode, err)
        return types.SimpleNamespace(returncode=returncode, stdout=out, stderr=err)

    def _respond(self, args):
        cmd = args[0]
        if cmd == "show" and args[1] == "HEAD:history.json":
            return 0, self.history_head, ""
        if cmd == "show" and args[1].startswith("FETCH_HEAD:"):
            text = self.branch_files.get(args[1][len("FETCH_HEAD:"):])
            return (0, text, "") if text is not None else (128, "", "fatal: path does not exist")
        if cmd == "rev-parse" and "--abbrev-ref" in args:
            return 0, self.branch + "\n", ""
        if cmd == "rev-parse" and "--is-shallow-repository" in args:
            return 0, ("true" if self.shallow else "false") + "\n", ""
        if cmd == "ls-remote":
            failure = self._fail("ls-remote")
            if failure:
                return failure[0], "", failure[1]
            pattern = args[-1]
            lines = [f"{sha}\trefs/heads/{name}" for name, sha in sorted(self.remote.items()) if fnmatch.fnmatchcase(f"refs/heads/{name}", pattern)]
            return 0, "\n".join(lines) + ("\n" if lines else ""), ""
        if cmd == "push":
            if "--delete" in args:
                failure = self._fail("push-delete")
                if failure:
                    return failure[0], "", failure[1]
                self.remote.pop(args[-1], None)
                return 0, "", ""
            if args[-1].startswith("refs/heads/"):
                failure = self._fail("push-branch")
                if failure:
                    return failure[0], "", failure[1]
                self.remote[args[-1].split(":")[0][len("refs/heads/"):]] = "a" * 40
                return 0, "", ""
            failure = self._fail("push-base")
            return (failure[0], "", failure[1]) if failure else (0, "", "")
        failure = self._fail(cmd)
        return (failure[0], "", failure[1]) if failure else (0, "", "")


class FakeGitHub:
    """drafts.GitHubClient 를 흉내 내는 메모리 속 가짜. 모든 호출을 calls 에 기록한다.

    - create_errors: 앞에서부터 하나씩 꺼내 던진다(None 이면 성공). 실제 GitHub 의 403(설정 꺼짐)·5xx 를 흉내 낼 때 쓴다.
    - list_error: list_draft_pull_requests 가 던질 오류.
    - label_error: 라벨 호출이 던질 오류.
    """

    def __init__(self, repo=REPO):
        self.repo = repo
        self.prs, self.calls = {}, []
        self.create_errors, self.list_error, self.label_error = [], None, None
        self.labels = {}
        self._next = 40

    def add_pr(self, number, head, state="open", merged=False, created="2026-10-28T00:00:00Z"):
        self.prs[number] = {"number": number, "state": state, "merged": merged, "head_ref": head, "head_repo": self.repo,
                            "created_at": created, "title": "t", "body": "", "base": "main", "labels": []}

    def create_pull_request(self, title, head, base, body):
        self.calls.append(("create", head))
        if self.create_errors:
            error = self.create_errors.pop(0)
            if error is not None:
                raise error
        if any(pr["head_ref"] == head and pr["state"] == "open" for pr in self.prs.values()):
            raise drafts.GitHubError("HTTP 422: A pull request already exists for shine88pc:" + head, status=422)
        self._next += 1
        self.prs[self._next] = {"number": self._next, "state": "open", "merged": False, "head_ref": head, "head_repo": self.repo,
                                "created_at": "2026-10-28T00:20:00Z", "title": title, "body": body, "base": base, "labels": []}
        return self._next

    def find_pull_request(self, head_ref):
        self.calls.append(("find", head_ref))
        for number in sorted(self.prs, reverse=True):
            if self.prs[number]["head_ref"] == head_ref:
                return dict(self.prs[number])
        return None

    def list_draft_pull_requests(self, state="all", max_pages=3):
        self.calls.append(("list", state))
        if self.list_error is not None:
            raise self.list_error
        items = [dict(self.prs[n]) for n in sorted(self.prs, reverse=True)]
        found = drafts.PullList(pr for pr in items if state == "all" or pr["state"] == state)
        found.complete = len(found) < 300                      # 실제 클라이언트는 쪽을 가득 채워 끝까지 읽으면 complete=False 로 알린다
        return found

    def ensure_label(self, name, color, description):
        self.calls.append(("label", name))
        if self.label_error is not None:
            raise self.label_error
        self.labels[name] = (color, description)

    def add_labels(self, number, labels):
        self.calls.append(("add_labels", number))
        if self.label_error is not None:
            raise self.label_error
        self.prs[number]["labels"] = list(labels)

    def verbs(self):
        return [c[0] for c in self.calls]
