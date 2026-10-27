"""묶음 2 통합(작업 INT)이 더한 시험 — Chance 승인 흐름(E)·티스토리·네이버 초안 패키지(C)·초안 현황판(B)·텔레그램 알림(TG)이 한 저장소에서 만나는 곳.

네 작업은 서로를 모른 채 같은 기준 위에서 만들어져 각자의 시험은 자기 기준만 본다. 여기서는 서로의 값을 직접 읽어 '같은 약속을 쓰는지'를 고정한다:
① 라벨·제목 약속(만드는 쪽 E·C 와 읽는 쪽 B 가 같은 글자를 쓴다) ② 만든 초안이 확인 필요 모음에 '초안 대기' 한 줄·코멘트 하나·휴대폰 알림 한 통으로 나오는 길
③ 레지스트리 검증(E 의 publish_flow 와 C 의 package 모드·플랫폼이 한 파일에서 함께 산다) ④ chanceblog.yml 의 단계 순서(E 의 두 단계 뒤 TG 의 알림 단계)와
'켜기 전에 연결할 것'(E·C 가 초안을 만든 직후 ops-inbox 즉시 실행·발행 대기 알림은 일부러 연결하지 않았다)이 문서와 코드에서 같게 말해지는지.
네트워크는 쓰지 않는다(가짜 GitHub·가짜 텔레그램 HTTP).
"""
import inspect
import json
import re
import tempfile
import unittest
from pathlib import Path

import _bootstrap
import ops_inbox_helpers as h
import ops_inbox as oi
from notify_helpers import ENV as TELEGRAM_ENV, FakeNet, leaks
from package_helpers import entry_of, make_package_root, registry_of
from pipeline import drafts, inbox, notify, registry
from pipeline import run as run_mod
from pipeline.publishers import issue_package
from test_chance_draft_workflow import evaluate, steps_of
from test_issue_package import make_draft as make_package_draft
from test_notify_integration import patched_network

REAL = _bootstrap.ROOT
OPS_ENV = {"GITHUB_REPOSITORY": h.REPO, "GITHUB_TOKEN": "gh" + "s_" + "Q" * 36, "GITHUB_REPOSITORY_OWNER": "octo"}


def registry_text(flow=None):
    """B 의 채널 레지스트리(Chance·Blogger·티스토리·네이버)에 Chance 의 publish_flow 만 얹는다."""
    reg = json.loads(h.CHANNEL_REGISTRY)
    if flow is not None:
        reg["blogs"][0]["publish_flow"] = flow
    return json.dumps(reg, ensure_ascii=False)


def table_rows(board):
    return [[cell.strip() for cell in line[2:-2].split(" | ")] for line in board.splitlines() if line.startswith("| ") and not line.startswith("| 채널 |")]


# ----------------------------------------------------------------------------
# ① 라벨·제목 약속
# ----------------------------------------------------------------------------
class LabelPromiseTest(unittest.TestCase):
    def test_the_label_names_the_makers_write_are_the_names_the_board_reads(self):
        self.assertEqual({drafts.LABEL_DRAFT, issue_package.DRAFT_LABEL, inbox.DRAFT_LABEL}, {"초안"})
        self.assertEqual({issue_package.DISCARD_LABEL, inbox.DISCARD_LABEL}, {"폐기"})
        self.assertEqual({issue_package.CHANNEL_LABEL_PREFIX, inbox.CHANNEL_LABEL_PREFIX}, {"채널:"})

    def test_the_chance_channel_label_is_the_registry_channel_label(self):
        """E 의 PR 라벨 `채널:Chance` 와 제목 접두의 Chance 는 레지스트리 `channel.label`(B 가 읽는 값)과 같은 글자다."""
        chance = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), "chance")
        self.assertEqual(drafts.LABEL_CHANNEL, inbox.CHANNEL_LABEL_PREFIX + chance["channel"]["label"])
        self.assertEqual(drafts.PR_TITLE_PREFIX, f"[{inbox.DRAFT_LABEL}][{chance['channel']['label']}]")

    def test_the_package_channel_labels_are_registry_labels_and_the_board_builds_their_label_names(self):
        for platform, label in registry.PACKAGE_PLATFORMS.items():
            with self.subTest(platform=platform):
                self.assertEqual(issue_package.PACKAGE_INFO[platform]["label"], label)
                spec = issue_package.build_issue(make_package_draft(platform))
                self.assertEqual(spec.labels, [inbox.DRAFT_LABEL, inbox.CHANNEL_LABEL_PREFIX + label])
                blogs = [h.channel_blog(f"{platform}_x", label, platform=platform)]
                self.assertIn(inbox.CHANNEL_LABEL_PREFIX + label, [item["name"] for item in inbox.draft_label_specs(blogs)])

    def test_the_title_the_makers_write_is_shown_by_the_board_without_the_brackets(self):
        pr_title = drafts.build_pr_title("승인 대기 글", "Waiting post")
        issue_title = issue_package.build_issue(make_package_draft("tistory")).title
        for raw, label, shown in ((h.make_issue(15, pr_title, labels=[drafts.LABEL_DRAFT, drafts.LABEL_CHANNEL], pull=True), "Chance", "승인 대기 글 / Waiting post"),
                                  (h.make_issue(41, issue_title, labels=issue_package.build_issue(make_package_draft("tistory")).labels), "티스토리", "테스트 글 제목입니다")):
            with self.subTest(label=label):
                draft = inbox.normalize_draft(raw)
                self.assertEqual(draft["channel"], label)
                text = inbox.draft_items([draft], h.NOW, h.REPO_URL)[0].title
                self.assertIn(shown, text)
                self.assertNotIn("[초안]", text)
                self.assertNotIn(f"[{label}]", text)


# ----------------------------------------------------------------------------
# ② 만든 초안이 확인 필요 모음에 나오는 길(한 번 점검 + 휴대폰 알림)
# ----------------------------------------------------------------------------
class BoardSeesTheMakersTest(unittest.TestCase):
    def setUp(self):
        notify.reset_budget()
        self.addCleanup(notify.reset_budget)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.summary = self.tmp / "summary.md"
        self.out = []

    def world(self, *, chance_pr=False, package_issue=False, flow="pr"):
        root = h.make_root(self.tmp / "repo", histories={"history.json": [], "blogger_history.json": []}, blogs_json=registry_text(flow))
        fake = h.FakeGitHub()
        fake.runs = {name: [h.make_run(i, h.ago(hours=1 + i))] for i, name in enumerate(("chanceblog.yml", "blogger.yml", "watchdog.yml", "guardrails.yml"), start=1)}
        if chance_pr:
            title = drafts.build_pr_title("승인 대기 글", "Waiting post")
            fake.issues.append(h.make_issue(15, title, labels=[drafts.LABEL_DRAFT, drafts.LABEL_CHANNEL], created=h.ago(hours=3), pull=True))
            fake.pulls = [h.make_pull_raw(15, title=title, sha="c" * 40, login=h.BOT, user_type="Bot", assoc="CONTRIBUTOR")]
            fake.details = {15: {"mergeable": True, "mergeable_state": "clean"}}
            fake.check_runs = {"c" * 40: []}            # 저장소 기본 토큰이 연 PR 은 검사가 돌지 않는다
        if package_issue:
            spec = issue_package.build_issue(make_package_draft("tistory", title="맛집 지도 만드는 법"))
            fake.issues.append(h.make_issue(41, spec.title, body=spec.body, labels=spec.labels, created=h.ago(hours=3)))
        return fake, root

    def check(self, fake, root, net=None):
        net = net if net is not None else FakeNet()
        environ = dict(OPS_ENV, GITHUB_STEP_SUMMARY=str(self.summary), **TELEGRAM_ENV)
        with patched_network(net):
            code = oi.run(environ, fake, h.NOW, root, self.out.append, sleep=lambda seconds: None)
        return code, net

    def inbox_issue(self, fake):
        return next(issue for issue in fake.issues if issue["title"] == inbox.ISSUE_TITLE)

    def test_a_chance_approval_pr_is_one_waiting_line_one_comment_and_one_phone_alert(self):
        fake, root = self.world(chance_pr=True)
        code, net = self.check(fake, root)
        self.assertEqual((code, net.calls), (0, 1))
        body = self.inbox_issue(fake)["body"]
        self.assertEqual(table_rows(body)[0][:3], ["Chance", "1", "1일 미만"])
        self.assertEqual(body.count("초안 대기 — 승인 대기 글 / Waiting post"), 1)
        self.assertNotIn("검사 결과 없음", body)                                    # 같은 PR 의 '검사 결과 없음' 줄은 없다
        self.assertEqual(inbox.parse_marker(body).items, ("draft:15:wait",))
        comments = fake.comments[self.inbox_issue(fake)["number"]]
        self.assertEqual(len(comments), 1)
        self.assertIn("초안 대기 — 승인 대기 글 / Waiting post", comments[0])
        text = net.bodies()[0]["text"]
        self.assertTrue(text.startswith(f"{notify.PIN_MARK} 확인 필요 모음 — 새로 해야 할 일 1건\n"))
        self.assertIn("초안 대기 — 승인 대기 글 / Waiting post", text)
        self.assertEqual(leaks(self.out, json.dumps(fake.comments, ensure_ascii=False), json.dumps(fake.issues, ensure_ascii=False)), [])

    def test_a_package_issue_is_one_waiting_line_one_comment_and_one_phone_alert(self):
        fake, root = self.world(package_issue=True)
        code, net = self.check(fake, root)
        self.assertEqual((code, net.calls), (0, 1))
        body = self.inbox_issue(fake)["body"]
        rows = table_rows(body)
        self.assertEqual([row[0] for row in rows], ["Chance", "Blogger", "티스토리", "네이버"])
        self.assertEqual(rows[2][:3], ["티스토리", "1", "1일 미만"])
        self.assertEqual(body.count("초안 대기 — 맛집 지도 만드는 법"), 1)
        self.assertEqual(inbox.parse_marker(body).items, ("draft:41:wait",))
        self.assertEqual(len(fake.comments[self.inbox_issue(fake)["number"]]), 1)
        self.assertIn("초안 대기 — 맛집 지도 만드는 법", net.bodies()[0]["text"])

    def test_the_next_check_sends_neither_a_comment_nor_a_phone_alert_again(self):
        fake, root = self.world(chance_pr=True, package_issue=True)
        self.check(fake, root)
        writes = len(fake.writes())
        code, net = self.check(fake, root)
        self.assertEqual((code, net.calls), (0, 0))
        self.assertEqual(len(fake.writes()), writes)
        self.assertEqual(len(fake.comments[self.inbox_issue(fake)["number"]]), 1)

    def test_two_new_drafts_in_one_check_are_one_comment_and_one_phone_message(self):
        fake, root = self.world(chance_pr=True, package_issue=True)
        code, net = self.check(fake, root)
        self.assertEqual((code, net.calls), (0, 1))
        self.assertEqual(len(fake.comments[self.inbox_issue(fake)["number"]]), 1)
        text = net.bodies()[0]["text"]
        self.assertIn("새로 해야 할 일 2건", text)
        self.assertIn("승인 대기 글 / Waiting post", text)
        self.assertIn("맛집 지도 만드는 법", text)

    def test_without_the_telegram_secrets_the_board_and_the_comment_are_the_same(self):
        fake, root = self.world(chance_pr=True, package_issue=True)
        environ = dict(OPS_ENV, GITHUB_STEP_SUMMARY=str(self.summary))
        with patched_network(FakeNet()) as net:
            code = oi.run(environ, fake, h.NOW, root, self.out.append, sleep=lambda seconds: None)
        self.assertEqual((code, net.calls), (0, 0))
        self.assertEqual(len(fake.comments[self.inbox_issue(fake)["number"]]), 1)
        self.assertNotIn("텔레그램", "\n".join(self.out))

    def test_the_package_runner_summary_head_is_the_same_shape_as_blogger(self):
        """C 의 초안 패키지 러너와 B 의 Blogger 요약이 같은 함수(summary_head)로 머리를 쓴다."""
        for platform, label in (("tistory", "티스토리"), ("naver", "네이버")):
            blog = {"key": f"{platform}_test", "name": f"{label} 시험 블로그", "channel": {"key": platform, "label": label}}
            self.assertEqual(run_mod.summary_head(blog), f"### [{label}] {label} 시험 블로그")
        self.assertNotIn("_summary_head", inspect.getsource(run_mod))


# ----------------------------------------------------------------------------
# ③ 레지스트리 검증 — E 의 publish_flow 와 C 의 package 가 한 파일에서 함께 산다
# ----------------------------------------------------------------------------
class RegistryCombinationTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def errors(self, mutate=None, mode="package"):
        root = make_package_root(self.tmp / f"r{len(list(self.tmp.iterdir()))}", mode=mode, mutate=mutate)
        return registry.validate_registry(registry_of(root), root)

    def test_the_real_registry_is_unchanged_by_the_merge(self):
        reg = registry.load_registry(REAL / "pipeline" / "blogs.json")
        blogs = [registry.merged_blog(reg, raw) for raw in reg["blogs"]]
        self.assertEqual([blog["key"] for blog in blogs], ["chance", "blogger_macat"])
        self.assertEqual({blog["key"]: blog["mode"] for blog in blogs}, {"chance": "auto", "blogger_macat": "off"})
        self.assertEqual(blogs[0]["publish_flow"], "direct")
        self.assertFalse(any(blog["platform"] in registry.PACKAGE_PLATFORMS for blog in blogs))

    def test_the_approval_flow_and_the_package_blogs_live_in_one_registry(self):
        self.assertEqual(self.errors(lambda reg: entry_of(reg, "chance").update(publish_flow="pr")), [])

    def test_each_feature_still_rejects_what_it_rejected_alone(self):
        flow_on_package = self.errors(lambda reg: entry_of(reg, "tistory_test").update(publish_flow="pr"))
        self.assertTrue(any("publish_flow는 platform jekyll-git 에서만" in error for error in flow_on_package), flow_on_package)
        package_on_chance = self.errors(lambda reg: entry_of(reg, "chance").update(mode="package"))
        self.assertTrue(any("mode package 는 platform tistory · naver 에서만" in error for error in package_on_chance), package_on_chance)
        pr_needs_auto = self.errors(lambda reg: entry_of(reg, "chance").update(publish_flow="pr", mode="draft"))
        self.assertTrue(any("publish_flow 가 pr 이면 mode 는 auto" in error for error in pr_needs_auto), pr_needs_auto)
        wrong_mode = self.errors(lambda reg: entry_of(reg, "naver_test").update(mode="auto"))
        self.assertTrue(any("mode는 off · package 중 하나" in error for error in wrong_mode), wrong_mode)

    def test_the_mode_and_platform_names_of_the_two_features_do_not_overlap(self):
        self.assertEqual(registry.MODES, ("off", "draft", "package", "auto"))
        self.assertEqual(registry.PUBLISH_FLOWS, ("direct", "pr"))
        self.assertEqual(set(registry.PACKAGE_PLATFORMS), {"tistory", "naver"})
        self.assertTrue(set(registry.PACKAGE_PLATFORMS) <= set(registry.PLATFORMS))
        self.assertFalse(set(registry.PUBLISH_FLOWS) & set(registry.MODES))


# ----------------------------------------------------------------------------
# ④ chanceblog.yml — 단계 순서와 '켜기 전에 연결할 것'
# ----------------------------------------------------------------------------
class ChanceblogWorkflowTest(unittest.TestCase):
    def alert_step(self):
        return next(step for step in steps_of() if step.get("name") == "텔레그램 알림(새 글)")

    def commit_step(self):
        return next(step for step in steps_of() if step.get("id") == "commit")

    def test_the_steps_run_in_this_order_with_the_alert_last(self):
        names = [step.get("name") or step.get("uses") for step in steps_of()]
        self.assertEqual(names, ["actions/checkout@v4", "actions/setup-python@v5", "발행 흐름 확인 (레지스트리 publish_flow)", "의존성 설치",
                                 "AI 블로그 제너레이터 실행", "변경 사항 커밋", "Pages 배포 실행 (새 커밋이 있을 때만)",
                                 "초안 올리기와 승인 PR 열기 (승인 흐름일 때만)", "텔레그램 알림(새 글)"])

    def test_the_new_post_alert_runs_after_a_direct_push_and_never_in_the_approval_flow(self):
        """승인 흐름에서는 글을 main 에 커밋하지 않아 pushed 출력이 없다 → 새 글 알림 단계는 돌지 않는다(발행 대기 알림은 '켜기 전에 연결할 것')."""
        for event, inputs in (("schedule", {}), ("workflow_dispatch", {"dry_run": False})):
            for flow, pushed_when_commit_runs, expected in (("direct", "true", True), ("pr", "true", False)):
                with self.subTest(event=event, flow=flow):
                    commit_runs = evaluate(self.commit_step()["if"], event, inputs, flow)
                    pushed = pushed_when_commit_runs if commit_runs else ""
                    self.assertEqual(commit_runs, flow == "direct")
                    self.assertEqual(evaluate(self.alert_step()["if"], event, inputs, flow, pushed=pushed), expected)

    def test_the_approval_step_and_the_alert_step_are_never_both_the_reason_for_a_run(self):
        for flow in ("direct", "pr"):
            deliver = next(step for step in steps_of() if "pipeline.draft_flow deliver" in step.get("run", ""))
            runs = evaluate(deliver["if"], "schedule", {}, flow)
            alert = evaluate(self.alert_step()["if"], "schedule", {}, flow, pushed="true" if evaluate(self.commit_step()["if"], "schedule", {}, flow) else "")
            self.assertFalse(runs and alert, flow)

    def test_the_connections_that_are_not_made_are_written_down_where_the_docs_and_the_code_agree(self):
        """E·C 가 초안을 만든 직후 ops-inbox 즉시 실행·발행 대기 알림은 일부러 연결하지 않았다. 연결하면 이 시험과 ARCHITECTURE §4-2-1 의
        '켜기 전에 연결할 것' 단락을 함께 고친다(문서가 '아직 연결하지 않았다'고 말하는데 코드가 연결돼 있거나 그 반대가 되지 않게)."""
        guide = (REAL / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        start = guide.index("### 4-2-1.")
        section = guide[start:guide.index("\n## ", start)]
        self.assertIn("**켜기 전에 연결할 것**", section)
        self.assertIn("ops-inbox.yml", section.split("**켜기 전에 연결할 것**")[1])
        self.assertIn("notify_draft_waiting", section.split("**켜기 전에 연결할 것**")[1])
        for name, source in (("pipeline/draft_flow.py", (REAL / "pipeline" / "draft_flow.py").read_text(encoding="utf-8")),
                             ("pipeline/publishers/issue_package.py", (REAL / "pipeline" / "publishers" / "issue_package.py").read_text(encoding="utf-8")),
                             ("pipeline/run.py 의 초안 패키지 경로", inspect.getsource(run_mod._package_deliver))):
            with self.subTest(source=name):
                self.assertNotIn("notify", source.replace("noqa", ""), f"{name} 이 텔레그램 알림을 부른다 — ARCHITECTURE §4-2-1 의 '켜기 전에 연결할 것'과 이 시험을 고친다")
                self.assertNotIn("ops-inbox", source, f"{name} 이 ops-inbox 를 부른다 — ARCHITECTURE §4-2-1 의 '켜기 전에 연결할 것'과 이 시험을 고친다")
                self.assertNotIn("workflow_dispatch", source)

    def test_the_docs_number_the_four_features_without_reusing_a_number(self):
        """통합에서 겹친 번호를 옮겼다: ACTIONS_GUIDE 3-17(E)·3-18(TG)·3-19(C)·6-12·6-13(C)·6-14(TG), ARCHITECTURE §4-4(E)·§4-5(TG), 가드레일 G-L8(E)·G-L9(C)·G-C11(E)·G-C12(TG)."""
        guide = (REAL / "docs" / "ACTIONS_GUIDE.md").read_text(encoding="utf-8")
        headings = re.findall(r"^### (\d+-\d+)\. ", guide, re.M)
        self.assertEqual(len(headings), len(set(headings)), sorted(h_ for h_ in headings if headings.count(h_) > 1))
        for number, word in (("3-17", "Chance 글을 내가 승인"), ("3-18", "텔레그램"), ("3-19", "티스토리·네이버 초안 이슈"),
                             ("6-12", "[티스토리]"), ("6-13", "[네이버]"), ("6-14", "텔레그램 알림 시험")):
            self.assertTrue(re.search(rf"^### {number}\. .*{re.escape(word)}", guide, re.M), f"ACTIONS_GUIDE 의 {number} 절이 {word!r} 을 다루지 않는다")
        architecture = (REAL / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
        titles = re.findall(r"^## (\d+-\d+)\. ", architecture, re.M)
        self.assertEqual(len(titles), len(set(titles)))
        self.assertTrue(re.search(r"^## 4-4\. Chance 승인 흐름", architecture, re.M))
        self.assertTrue(re.search(r"^## 4-5\. 텔레그램 알림 계층", architecture, re.M))
        rows = re.findall(r"^\| (G-[A-Z]\d+) \|", (REAL / "docs" / "SECURITY_GUARDRAILS.md").read_text(encoding="utf-8"), re.M)
        self.assertEqual(len(rows), len(set(rows)), sorted(row for row in rows if rows.count(row) > 1))
        for rule in ("G-L8", "G-L9", "G-C11", "G-C12"):
            self.assertIn(rule, rows)
        defects = re.findall(r"^\| \*\*(D-\d+)\*\* \|", (REAL / "docs" / "DEFECT_REGISTER.md").read_text(encoding="utf-8"), re.M)
        self.assertEqual(len(defects), len(set(defects)))
        self.assertEqual([d for d in defects if d in ("D-72", "D-73", "D-74")], ["D-72", "D-73", "D-74"])


if __name__ == "__main__":
    unittest.main()
