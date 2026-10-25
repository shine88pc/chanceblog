"""제목만 바꾸는 이슈 수정 PR 도 '저장소 규칙·테스트 자동 검사' 워크플로가 초록이어야 한다 — pages.json 이 낡았는지는 '구조'(id·path·url)로만 판단한다.

실제 Actions 기준선 시험(2026-10-25): 이슈 양식으로 categories 의 SEO 제목을 바꾸자 PR 이 만들어졌지만(2줄 변경), 그 브랜치의 '저장소 규칙·테스트 자동 검사' 실행이
`pages.json 가 최신이 아닙니다` 로 실패했다(test_real_repository_registry_is_current · 검증기 SYNC-1). pages.json 의 title 이 front matter 에서 와서,
제목을 고치는 PR 은 pages.json 을 같이 고치지 않기 때문이다. 제목은 병합 뒤 '이슈 양식 페이지 목록 갱신' 워크플로가 pages.json·양식 드롭다운에 반영한다.
페이지가 추가·삭제·이동되거나 id·url 이 바뀌는 불일치는 계속 잡아야 한다.
"""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401
from edits_helpers import ABOUT, issue, make_edit_root, page_body, write
from pipeline.edits import forms, pages, runner, spec as spec_mod

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

FAQ = "---\nlayout: info\ntitle: 자주 묻는 질문\neditable: true\npermalink: /faq/\n---\n본문입니다.\n"
SEO = "seo_meta | SEO 메타 수정 (title/description)"


def retitle(root, rel, title):
    path = Path(root) / rel
    text = path.read_bytes().decode("utf-8")
    new = re.sub(r"(?m)^title:.*$", f"title: {json.dumps(title, ensure_ascii=False)}", text, count=1)
    assert new != text, rel
    path.write_bytes(new.encode("utf-8"))


class RegistryCase(unittest.TestCase):
    def fresh(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = make_edit_root(tmp.name, extra_pages={"faq.md": FAQ})
        spec = spec_mod.load_spec(root)
        forms.sync_page_form(root, spec, pages.load_registry(root), write=True)     # faq 가 들어간 상태로 양식 드롭다운도 맞춘다('이슈 양식 페이지 목록 갱신' 워크플로가 한 뒤)
        return root, spec

    def setUp(self):
        self.root, self.spec = self.fresh()

    def stale(self, **kw):
        return pages.check_registry(self.root, self.spec, **kw)

    def registry(self):
        return json.loads((self.root / "pages.json").read_text(encoding="utf-8"))

    def write_registry(self, data, **dump_kw):
        dump_kw.setdefault("indent", 2)
        (self.root / "pages.json").write_bytes((json.dumps(data, ensure_ascii=False, **dump_kw) + "\n").encode("utf-8"))


class TitleOnlyChangesTest(RegistryCase):
    def test_the_starting_state_is_current_even_strictly(self):
        self.assertEqual(self.stale(), [])
        self.assertEqual(self.stale(strict_titles=True), [])

    def test_title_only_changes_are_not_stale_but_strict_mode_still_sees_them(self):
        for rel in ("about.md", "categories.md", "faq.md"):
            retitle(self.root, rel, f"{rel} 의 새 제목")
            self.assertEqual(self.stale(), [], rel)
            self.assertEqual(len(self.stale(strict_titles=True)), 1, rel)      # 제목 말고는 아무것도 면제하지 않는다는 대조
        retitle(self.root, "about.md", "한 번 더 바꾼 제목")
        self.assertEqual(self.stale(), [])

    def test_a_different_title_in_pages_json_itself_is_not_stale_either(self):
        data = self.registry()
        data["pages"][0]["title"] = "손으로 바꾼 제목"
        self.write_registry(data)
        self.assertEqual(self.stale(), [])
        self.assertEqual(len(self.stale(strict_titles=True)), 1)

    def test_after_the_sync_workflow_runs_everything_is_strictly_current(self):
        """병합 뒤: '이슈 양식 페이지 목록 갱신' 워크플로가 pages.json 과 양식 드롭다운을 새 제목으로 다시 쓴다."""
        retitle(self.root, "categories.md", "카테고리 (기준선 시험)")
        pages.write_registry(self.root, self.spec)
        self.assertTrue(forms.sync_page_form(self.root, self.spec, pages.load_registry(self.root), write=True))
        self.assertEqual(self.stale(strict_titles=True), [])
        self.assertIn("categories | 카테고리 (기준선 시험)", (self.root / ".github" / "ISSUE_TEMPLATE" / "page-edit.yml").read_text(encoding="utf-8"))

    def test_the_dropdown_check_follows_the_registry_file_so_a_title_pr_does_not_trip_it(self):
        retitle(self.root, "about.md", "새 제목")
        self.assertFalse(forms.sync_page_form(self.root, self.spec, pages.load_registry(self.root), write=False))


class StructuralChangesStillCaughtTest(RegistryCase):
    def assertStale(self, label):
        reasons = self.stale()
        self.assertEqual(len(reasons), 1, label)
        self.assertIn("최신이 아닙니다", reasons[0], label)

    def test_added_page(self):
        write(self.root, "notes2.md", "---\ntitle: 새 페이지\neditable: true\n---\n본문\n")
        self.assertStale("추가")

    def test_removed_page(self):
        (self.root / "faq.md").unlink()
        self.assertStale("삭제")

    def test_moved_page_keeps_its_id_but_changes_the_path(self):
        os.replace(self.root / "faq.md", self.root / "faq.html")
        self.assertStale("이동(경로 변경)")

    def test_permalink_and_edit_id_changes(self):
        path = self.root / "faq.md"
        text = path.read_bytes().decode("utf-8")
        path.write_bytes(text.replace("permalink: /faq/", "permalink: /faq-new/").encode("utf-8"))
        self.assertStale("url 변경")
        path.write_bytes(text.replace("permalink: /faq/", "permalink: /faq/\nedit_id: faq2").encode("utf-8"))
        self.assertStale("id 변경")

    def test_a_title_change_does_not_hide_a_structural_change(self):
        retitle(self.root, "about.md", "새 제목")
        write(self.root, "notes2.md", "---\ntitle: 새 페이지\neditable: true\n---\n본문\n")
        self.assertStale("제목 변경 + 추가")
        (self.root / "notes2.md").unlink()
        (self.root / "faq.md").unlink()
        self.assertStale("제목 변경 + 삭제")

    def test_missing_or_damaged_registry_files(self):
        data = self.registry()
        raw = json.dumps(data, ensure_ascii=False, indent=2)
        put = lambda text: (self.root / "pages.json").write_bytes(text.encode("utf-8"))  # noqa: E731
        variants = {
            "끝 개행 없음": lambda: put(raw),                      # 앞뒤 공백·개행 차이도 '최신 아님'이다(비교에서 strip 하지 않는다)
            "끝 개행 두 개": lambda: put(raw + "\n\n"),
            "앞에 빈 줄": lambda: put("\n" + raw + "\n"),
            "끝에 공백": lambda: put(raw + " \n"),
            "title 키가 없는 항목": lambda: self.write_registry({**data, "pages": [{k: v for k, v in data["pages"][0].items() if k != "title"}, *data["pages"][1:]]}),
            "항목이 객체가 아님": lambda: self.write_registry({**data, "pages": ["about", *data["pages"][1:]]}),
            "들여쓰기 변경": lambda: self.write_registry(data, indent=4),
            "페이지에 키 추가": lambda: self.write_registry({**data, "pages": [{**data["pages"][0], "x": 1}, *data["pages"][1:]]}),
            "순서 변경": lambda: self.write_registry({**data, "pages": list(reversed(data["pages"]))}),
            "항목 삭제": lambda: self.write_registry({**data, "pages": data["pages"][:-1]}),
            "version 변경": lambda: self.write_registry({**data, "version": 2}),
            "항목 id 바꿈": lambda: self.write_registry({**data, "pages": [{**data["pages"][0], "id": "other"}, *data["pages"][1:]]}),
            "경로 바꿈": lambda: self.write_registry({**data, "pages": [{**data["pages"][0], "path": "other.md"}, *data["pages"][1:]]}),
            "url 바꿈": lambda: self.write_registry({**data, "pages": [{**data["pages"][0], "url": "/other/"}, *data["pages"][1:]]}),
            "깨진 JSON": lambda: (self.root / "pages.json").write_text("{oops", encoding="utf-8"),
            "목록이 아님": lambda: self.write_registry({"version": 1, "pages": {}}),
            "빈 목록": lambda: self.write_registry({"version": 1, "pages": []}),
        }
        for label, damage in variants.items():
            self.write_registry(data)
            self.assertEqual(self.stale(), [], label)
            damage()
            self.assertStale(label)
        (self.root / "pages.json").unlink()
        self.assertEqual(self.stale(), ["pages.json 가 없습니다."])


class ValidatorFollowsTheSameRuleTest(RegistryCase):
    def findings(self):
        return vr.check_edit_system(self.root, vr.list_files(self.root))

    def test_title_change_is_clean_and_structure_change_still_warns(self):
        self.assertEqual(self.findings(), [])
        retitle(self.root, "about.md", "새 제목")
        self.assertEqual([f.line() for f in self.findings()], [])              # 예전에는 WARN [SYNC-1] pages.json 가 최신이 아닙니다
        write(self.root, "notes2.md", "---\ntitle: 새 페이지\neditable: true\n---\n본문\n")
        found = self.findings()
        self.assertEqual(sorted((f.check, f.level) for f in found), [("SYNC-1", "WARN")])
        self.assertIn("pages.json", found[0].message)
        (self.root / "notes2.md").unlink()
        (self.root / "faq.md").unlink()
        self.assertEqual(sorted((f.check, f.level) for f in self.findings()), [("SYNC-1", "WARN")])

    def test_the_real_repository_is_clean(self):
        real = _bootstrap.ROOT
        self.assertEqual([f.line() for f in vr.check_edit_system(real, vr.list_files(real))], [])
        self.assertEqual(pages.check_registry(real, spec_mod.load_spec(real)), [])


class TitleChangePullRequestScenarioTest(RegistryCase):
    """기준선 시험과 같은 흐름: 이슈 양식(대상 categories, 수정 항목 seo_meta)으로 제목만 바꾸는 수정안."""

    def test_issue_edit_title_change_leaves_guardrails_green(self):
        registry_before = (self.root / "pages.json").read_bytes()
        form = self.root / ".github" / "ISSUE_TEMPLATE" / "page-edit.yml"
        form_before = form.read_bytes()
        res = runner.process_issue(issue(page_body(page="categories | 카테고리", edit=SEO, after="title: 카테고리 (기준선 시험)")),
                                   self.root, env={"GITHUB_RUN_NUMBER": "1"})
        self.assertEqual((res.status, res.files, res.branch), ("ok", ["categories.md"], "issue-edit/12-categories-r1"))
        self.assertIn('title: "카테고리 (기준선 시험)"', (self.root / "categories.md").read_text(encoding="utf-8"))
        # 수정 PR 은 요청한 파일 한 개만 바꾼다: 레지스트리·양식은 그대로(병합 뒤 '이슈 양식 페이지 목록 갱신' 워크플로가 갱신)
        self.assertEqual((self.root / "pages.json").read_bytes(), registry_before)
        self.assertEqual(form.read_bytes(), form_before)
        # '저장소 규칙·테스트 자동 검사' 워크플로가 보는 두 가지: 단위 테스트(pages.check_registry)와 검증기(SYNC-1)
        self.assertEqual(self.stale(), [])
        self.assertEqual([f.line() for f in vr.check_edit_system(self.root, vr.list_files(self.root))], [])

    def test_the_same_flow_on_a_protected_page_and_a_description_only_edit(self):
        res = runner.process_issue(issue(page_body(page="about | 소개와 편집 원칙", edit=SEO, after="title: 바뀐 소개 제목\ndescription: 새 설명")),
                                   self.root, env={})
        self.assertEqual(res.status, "ok", res.reasons)
        self.assertEqual(self.stale(), [])
        self.assertNotEqual((self.root / "about.md").read_bytes().decode("utf-8"), ABOUT)


if __name__ == "__main__":
    unittest.main()
