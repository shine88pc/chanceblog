"""제한 재개 잠금의 '실제 git' 이야기(pipeline/publish_lock.py + pipeline/draft_flow.py): 임시 bare origin 과 clone, 실제 생성기(가짜 소스·가짜 Gemini), 가짜 GitHub 로
① 잠금이 켜진 승인 흐름에서 main 에는 이력만 올라가고 글은 초안 브랜치에만 있다 ② 같은 날 두 번째 슬롯은 아무것도 만들지 않는다 ③ 열린 초안 상한은 **실제 `git ls-remote`** 로 원격의
초안 브랜치를 세고, 병합된 초안은 빼며 이력에 없는 브랜치는 열린 것으로 센다 ④ 규칙을 어긴 레지스트리는 아무것도 올리지 않는다 — 를 하루하루 따라간다.
git 프로세스 하나가 1초 가까이 걸리는 PC 가 있어서 이야기 하나를 클래스 하나로 만들고(setUpClass 에서 한 번) 질의는 묶어서 한다. 네트워크·실제 시크릿 없이 돈다."""
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap  # noqa: F401
from draft_helpers import FakeGitHub, OriginTemplate, Sandbox
from lock_helpers import CHANCE, lock_ready, mutated, set_in, write_registry
from pipeline import draft_flow, drafts, registry
from test_draft_flow import BRANCH_9, ENV
from test_generator_drafts import run_tick
from test_generator_slots import at, candidate

BRANCH_29 = "ai/draft/2026-10-29-s9"
BRANCH_30 = "ai/draft/2026-10-30-s9"
DUMMY_1, DUMMY_2 = "ai/draft/2026-10-30-m000001", "ai/draft/2026-10-30-m000002"


class RealGitLockStoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = OriginTemplate()
        cls.box = box = Sandbox(cls.template)
        cls.gh, cls.out, cls.sleeps = FakeGitHub(), [], []
        cls.env = {**box.git.env, "EVENT_NAME": "schedule"}
        cls.lock_path = write_registry(box.root, lock_ready(), "lock-blogs.json")
        cls.direct_path = write_registry(box.root, mutated(lambda r: set_in(r, CHANCE, publish_flow="direct")), "direct-blogs.json")

        def tick(clone, now, path=cls.lock_path, name="s.md", **kwargs):
            with mock.patch.object(registry, "REGISTRY_PATH", path):
                return run_tick(clone, now, remote_exists="real", git_env=cls.env, summary_name=name, guarded=True, **kwargs)

        def deliver(clone):
            return draft_flow.deliver(box.git_git(clone), cls.gh, dict(ENV), out=cls.out.append, sleep=cls.sleeps.append)

        cls.main_commits = lambda: len(box.commits("main"))
        # ① 10-28 09:20: 가드 통과 → 초안 → 올리기. main 에는 이력 커밋 하나, 글은 초안 브랜치에만 있다
        cls.tick1 = tick(box.work, at(9, 20, day=28), name="s1.md")
        cls.result1 = deliver(box.work)
        cls.branches1 = box.origin_branches()
        cls.main_posts1 = box.origin_files("main")
        cls.draft_posts1 = box.origin_files(BRANCH_9)
        cls.main_history1 = box.origin_history("main")
        cls.commits1 = cls.main_commits()
        # ② 같은 날 18:20(새 실행기가 최신 main 을 받는다): 하루 상한에 닿아 아무것도 만들지 않는다
        cls.evening = box.clone("evening")
        cls.tick2 = tick(cls.evening, at(18, 20, day=28), name="s2.md", feed=[candidate("해양 관측 위성 자료 공개", "https://www.reuters.com/b")])
        cls.branches2, cls.commits2 = box.origin_branches(), cls.main_commits()
        cls.evening_posts = sorted(p.relative_to(cls.evening).as_posix() for p in (cls.evening / "_posts").rglob("*.md"))
        # ③ 다음 날 09:20: 하루 상한은 새로 시작하고, 열린 초안은 1개(10-28)라 상한 3 아래 — 실제 git ls-remote 로 센다
        cls.day2 = box.clone("day2")
        cls.tick3 = tick(cls.day2, at(9, 20, day=29), name="s3.md", feed=[candidate("캐나다 소비자물가지수 발표", "https://www.reuters.com/c")])
        cls.result3 = deliver(cls.day2)
        cls.branches3 = box.origin_branches()
        # ④ 운영자가 열어 두지 않은 초안 브랜치가 둘 더 있다(이력에 없는 브랜치도 열린 것으로 센다) → 10-30 틱은 상한(3)에 닿아 건너뛴다
        cls.merger = merger = box.clone("merger")
        box.sh(merger, "push", "-q", "origin", f"HEAD:refs/heads/{DUMMY_1}", f"HEAD:refs/heads/{DUMMY_2}")
        cls.day3 = box.clone("day3")
        cls.tick4 = tick(cls.day3, at(9, 20, day=30), name="s4.md", feed=[candidate("다른 날의 기사 제목입니다", "https://www.reuters.com/d")])
        cls.branches4, cls.commits4 = box.origin_branches(), cls.main_commits()
        # ⑤ 운영자가 10-28·10-29 초안을 병합한다(실제 3-way 병합 + push): 병합된 초안은 세지 않아 열린 것이 둘로 줄고, 10-30 틱이 초안을 만든다
        for branch in (BRANCH_9, BRANCH_29):
            box.sh(merger, "merge", "-q", "--no-ff", "-m", branch, f"origin/{branch}")
        box.sh(merger, "push", "-q", "origin", "HEAD:refs/heads/main")
        cls.day3b = box.clone("day3b")
        cls.tick5 = tick(cls.day3b, at(9, 20, day=30), name="s5.md", feed=[candidate("다른 날의 기사 제목입니다", "https://www.reuters.com/d")])
        cls.result5 = deliver(cls.day3b)
        cls.branches5 = box.origin_branches()
        # ⑥ 규칙을 어긴 레지스트리(잠금 켬 + direct): 아무것도 만들지 않고 빨강으로 끝난다
        cls.bad = box.clone("bad")
        before = box.origin_branches()
        cls.bad_posts_before = cls.posts_of(cls.bad)                                      # ⑤ 에서 병합한 10-28·10-29 글(넷)이 main 에 이미 있다
        cls.tick6 = tick(cls.bad, at(9, 20, day=31), cls.direct_path, "s6.md", flow="direct")
        cls.branches6_same = box.origin_branches() == before
        cls.bad_posts = cls.posts_of(cls.bad)

    @staticmethod
    def posts_of(clone):
        return sorted(p.relative_to(clone).as_posix() for p in (clone / "_posts").rglob("*.md"))

    @classmethod
    def tearDownClass(cls):
        cls.box.close()
        cls.template.close()

    def test_the_first_tick_makes_a_draft_and_the_delivery_opens_its_pr(self):
        self.assertIsNone(self.tick1.value)
        self.assertEqual([e["branch"] for e in self.tick1.history], [BRANCH_9])
        self.assertEqual((self.result1.status, self.result1.code), ("opened", 0))
        self.assertEqual(self.branches1, [BRANCH_9, "main"])

    def test_main_has_only_the_history_entry_and_the_posts_live_only_on_the_draft_branch(self):
        self.assertEqual(self.main_posts1, ["_posts/keep.txt"])                           # 병합 전에는 글이 main 에 없다 — 공개되지 않는다
        self.assertEqual(len(self.draft_posts1), 3)                                       # 초안 브랜치: 시드 파일 + 글 둘
        self.assertEqual(sum(1 for path in self.draft_posts1 if path.endswith(".md")), 2)
        self.assertEqual([(e["flow"], e["branch"]) for e in self.main_history1], [("pr", BRANCH_9)])
        self.assertEqual(self.commits1, 2)                                                  # 시드 + 이력 커밋 하나

    def test_the_second_slot_of_the_same_day_makes_nothing_at_all(self):
        self.assertIsInstance(self.tick2.value, SystemExit)
        self.assertEqual(self.tick2.value.code, 0)
        self.assertIn("[SKIP] code=LOCK_DAILY_CAP date=2026-10-28 today=1 cap=1", self.tick2.out)
        self.assertEqual(self.tick2.prompts, [])                                           # 모델을 부르지 않았다
        self.assertEqual((self.branches2, self.commits2), (self.branches1, self.commits1))     # 원격이 그대로다
        self.assertEqual(self.evening_posts, [])                                            # 작업 트리에도 새 글이 없다
        self.assertIn("**LOCK_DAILY_CAP**", self.tick2.summary)

    def test_the_next_day_starts_a_new_count_and_one_open_draft_leaves_room(self):
        self.assertIsNone(self.tick3.value)
        self.assertEqual(self.tick3.history[-1]["branch"], BRANCH_29)
        self.assertEqual((self.result3.status, self.result3.code), ("opened", 0))
        self.assertEqual(self.branches3, [BRANCH_9, BRANCH_29, "main"])

    def test_three_unmerged_drafts_found_by_a_real_ls_remote_stop_the_next_one(self):
        """열린 초안 브랜치 넷(10-28·10-29 초안 + 이력에 없는 둘) → 상한(3)에 닿아 건너뛴다. 이력에 없는 브랜치도 열린 것으로 센다."""
        self.assertIsInstance(self.tick4.value, SystemExit)
        self.assertEqual(self.tick4.value.code, 0)
        self.assertIn("[SKIP] code=OPEN_DRAFTS_CAP open=4 limit=3", self.tick4.out)
        self.assertEqual(self.tick4.prompts, [])
        self.assertEqual(self.branches4, sorted([BRANCH_9, BRANCH_29, DUMMY_1, DUMMY_2, "main"]))
        self.assertEqual(self.commits4, self.commits1 + 1)                                  # 10-29 초안의 이력 커밋 하나뿐 — 이 틱은 아무것도 올리지 않았다

    def test_merged_drafts_are_not_counted_so_the_next_tick_makes_its_draft(self):
        self.assertIsNone(self.tick5.value)
        self.assertEqual(self.tick5.history[-1]["branch"], BRANCH_30)
        self.assertEqual((self.result5.status, self.result5.code), ("opened", 0))
        self.assertEqual(self.branches5, sorted([BRANCH_9, BRANCH_29, BRANCH_30, DUMMY_1, DUMMY_2, "main"]))

    def test_a_registry_that_breaks_a_rule_makes_and_pushes_nothing(self):
        self.assertIsInstance(self.tick6.value, SystemExit)
        self.assertEqual(self.tick6.value.code, 1)
        self.assertIn("[SKIP] code=LOCK_BLOCKED rules=L1,L3", self.tick6.out)
        self.assertEqual(self.tick6.prompts, [])
        self.assertEqual(len(self.bad_posts_before), 4)                                   # 병합된 글 넷뿐이었고
        self.assertEqual(self.bad_posts, self.bad_posts_before)                           # 이 틱은 새 글(10-31)을 하나도 만들지 않았다
        self.assertTrue(self.branches6_same)

    def test_the_guard_never_wrote_to_the_repository_by_itself(self):
        """가드는 읽기만 한다: 건너뜀·멈춤 틱(②·④·⑥)의 작업 트리에는 새 파일이 없다(요약 파일은 clone 밖)."""
        for clone in (self.evening, self.day3, self.bad):
            status = self.box.sh(clone, "status", "--porcelain").stdout.strip()
            self.assertEqual(status, "", clone)


if __name__ == "__main__":
    unittest.main()
