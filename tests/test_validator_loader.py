"""검증기의 YAML 읽기·워크플로 후보 고르기 시험 — 안전 검증 S 의 권고 AN1-S-6(중복 키)·AN1-S-7(이벤트 이름·확장자의 대소문자).

WF-16 은 허용 파일 모양을 '정확히 같아야 한다' 방식으로 고정하므로 검증기가 읽은 값과 GitHub 가 읽은 값이 같아야 한다.
 · 중복 키: PyYAML 은 `permissions` 를 `write` 로 먼저 쓰고 `read` 로 다시 써도 조용히 마지막 값을 받는다 — 검증기는 `read` 를 보고 GitHub 는 다르게 읽을 수 있다. 이제 중복 키는 오류(WF-0)다.
 · 대소문자: `on: {Workflow_Run: …}`·`on: [WORKFLOW_RUN]`·파일 이름 `x.YML` 이 허용 목록·금지 규칙(WF-3·WF-16)을 피하지 못한다.
"""
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

import _bootstrap

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

BASE = 'name: "[공통] x"\npermissions:\n  contents: read\njobs:\n  j:\n    name: 가\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - run: echo hi\n'


def findings_of(files, check_name="check_workflows"):
    """{경로: 글} 를 임시 저장소에 쓰고 검증기 검사 하나를 돌려 Finding 목록을 돌려준다."""
    with tempfile.TemporaryDirectory() as tmp:
        root, rels = Path(tmp), []
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            rels.append(rel)
        return getattr(vr, check_name)(root, rels)


def wf0(findings):
    return [finding for finding in findings if finding.check == "WF-0"]


class DuplicateKeyTest(unittest.TestCase):
    """AN1-S-6: 같은 표 안의 중복 키는 YAML 오류(WF-0)다."""

    def test_the_loader_refuses_a_duplicate_permissions_key_the_value_the_audit_probe_hid(self):
        text = 'name: "[공통] x"\npermissions:\n  contents: write\npermissions:\n  contents: read\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n'
        self.assertEqual(yaml.safe_load(text)["permissions"], {"contents": "read"})            # 대조: 예전 읽기는 마지막 값만 보였다
        with self.assertRaises(yaml.YAMLError) as caught:
            vr._load_yaml(text)
        self.assertIn("중복 키", str(caught.exception))
        self.assertIn("permissions", str(caught.exception))
        found = wf0(findings_of({".github/workflows/x.yml": text}))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].level, "ERROR")
        self.assertIn("YAML 문법 오류", found[0].message)
        self.assertIn("중복 키", found[0].message)

    def test_a_duplicate_checkout_ref_is_refused(self):
        text = BASE.replace("      - run: echo hi\n", "      - uses: actions/checkout@v6\n        with:\n          ref: ${{ github.event.workflow_run.head_sha }}\n          ref: ${{ github.event.repository.default_branch }}\n")
        self.assertEqual(yaml.safe_load(text)["jobs"]["j"]["steps"][0]["with"]["ref"], "${{ github.event.repository.default_branch }}")      # 예전에는 안전한 값만 보였다
        found = wf0(findings_of({".github/workflows/x.yml": text}))
        self.assertEqual(len(found), 1)
        self.assertIn("중복 키", found[0].message)

    def test_a_duplicate_on_key_is_refused(self):
        text = BASE.replace("permissions:", "on:\n  workflow_run:\n    workflows: [ci]\n    types: [completed]\non:\n  push:\npermissions:", 1)
        self.assertEqual(set(vr._triggers(yaml.safe_load(text))), {"push"})                     # 대조: 예전 읽기는 workflow_run 이 사라진 것으로 봤다 — 허용 목록 규칙을 피한다
        found = wf0(findings_of({".github/workflows/x.yml": text}))
        self.assertEqual(len(found), 1)
        self.assertIn("중복 키", found[0].message)

    def test_duplicates_at_any_depth_and_among_non_string_keys_are_refused(self):
        for label, text in {"env": "a:\n  env:\n    X: 1\n    X: 2\n", "step": "steps:\n  - run: a\n    run: b\n", "boolean on": "on: 1\non: 2\n", "numbers": "1: a\n1: b\n",
                            "yes and true are the same key": "yes: a\ntrue: b\n"}.items():
            with self.subTest(label):
                with self.assertRaises(yaml.YAMLError):
                    vr._load_yaml(text)

    def test_the_same_key_name_in_different_tables_and_merge_key_overrides_are_not_duplicates(self):
        ok = "a:\n  x: 1\nb:\n  x: 2\nlist:\n  - x: 1\n  - x: 2\n"
        self.assertEqual(vr._load_yaml(ok), {"a": {"x": 1}, "b": {"x": 2}, "list": [{"x": 1}, {"x": 2}]})
        merged = "base: &b\n  contents: read\n  actions: read\nuse:\n  <<: *b\n  contents: none\n"
        self.assertEqual(vr._load_yaml(merged)["use"], {"contents": "none", "actions": "read"})      # 합병 키로 덮어쓰는 것은 YAML 의 정상 쓰임이다
        self.assertEqual(vr._load_yaml(""), None)
        self.assertEqual(vr._load_yaml("- a\n- b\n"), ["a", "b"])

    def test_several_merge_keys_in_one_table_are_not_duplicates_but_a_plain_duplicate_next_to_them_is(self):
        """합병 키 `<<` 는 한 표에 여러 번 쓸 수 있고(PyYAML 은 모두 합친다) 중복 키가 아니다 — 같은 표의 보통 키 중복은 합병 키가 있어도 그대로 오류다. 건너뛰는 태그는 PyYAML 이 `<<` 에 붙이는 실제 태그다."""
        base = "a: &a\n  x: 1\nb: &b\n  y: 2\n"
        both = base + "use:\n  <<: *a\n  <<: *b\n  z: 3\n"
        self.assertEqual(yaml.safe_load(both)["use"], {"x": 1, "y": 2, "z": 3})                  # 대조: 예전 읽기도 두 합병을 모두 합친다
        self.assertEqual(vr._load_yaml(both)["use"], {"x": 1, "y": 2, "z": 3})
        with self.assertRaises(yaml.YAMLError):
            vr._load_yaml(base + "use:\n  <<: *a\n  <<: *b\n  z: 3\n  z: 4\n")
        self.assertEqual(yaml.compose("<<: {a: 1}\n").value[0][0].tag, vr._MERGE_TAG)             # 상수가 PyYAML 이 실제로 붙이는 합병 태그와 같다

    def test_malformed_table_nodes_are_yaml_errors_and_never_crash_the_validator(self):
        """표 키가 목록·표처럼 해시할 수 없는 글은 중복 검사에서 건너뛰고 PyYAML 이 YAMLError(unhashable key)로 낸다. 표가 아닌 값에 표 태그(`!!map`)를 붙인 글도 마찬가지 — 중복 검사 자체가
        TypeError·ValueError 로 죽으면 검증기가 이 글에서 통째로 멎는다(표 노드가 아니면 검사를 건너뛰고 PyYAML 의 오류에 맡긴다)."""
        for label, text in {"list key": "? [a, b]\n: 1\n", "table key": "? {a: 1}\n: 2\n", "list key after a normal one": "x: 1\n? [a]\n: 2\n",
                            "map tag on a list": "!!map [a, b]\n", "map tag on a word": "!!map word\n", "map tag on a nested list": "k: !!map [a, b]\n"}.items():
            with self.subTest(label):
                with self.assertRaises(yaml.YAMLError):
                    vr._load_yaml(text)
        found = wf0(findings_of({".github/workflows/x.yml": 'name: "[공통] x"\n? [a, b]\n: 1\n'}))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].level, "ERROR")

    def test_the_strict_loader_is_as_safe_as_safe_load_and_gives_the_same_values_as_yaml_load(self):
        """엄격한 읽기는 SafeLoader 하위 클래스다 — 파이썬 태그(`!!python/object/apply:` 같은 것)로 코드를 되살리지 못하고 YAMLError 로 거절한다(저장소의 글을 읽는 도구가 글이 시키는 일을 하지 않는다).
        로더를 직접 부르는 읽기(외부 접속 스캐너가 `yaml.load` 이름을 '안전하지 않은 읽기' 로 표시해 그 이름을 피한다)가 `yaml.load` 와 같은 값을 내고, 문서가 둘이면 오류인 것도 같다."""
        self.assertTrue(issubclass(vr._UniqueKeyLoader, yaml.SafeLoader))
        for text in ("!!python/object/apply:os.getcwd []\n", "x: !!python/object/new:os.getcwd []\n", "!!python/name:os.system\n", "- !!python/object/apply:eval ['1']\n"):
            with self.subTest(text):
                with self.assertRaises(yaml.YAMLError):
                    vr._load_yaml(text)
        for sample in ("a: 1\nb: [x, y]\nc: {d: e}\n", "- 1\n- two\n- [3, 4]\n", "just a string\n", "", "# only a comment\n", "on:\n  push:\nx: &a [1]\ny: *a\n"):
            with self.subTest(sample):
                self.assertEqual(vr._load_yaml(sample), yaml.load(sample, Loader=vr._UniqueKeyLoader))
                self.assertEqual(vr._load_yaml(sample), yaml.safe_load(sample))
        with self.assertRaises(yaml.YAMLError):
            vr._load_yaml("a: 1\n---\nb: 2\n")                                                  # 문서가 둘이면 오류 — safe_load 와 같다

    def test_the_validator_source_has_no_yaml_load_call_for_the_egress_scanner_to_flag(self):
        """tests/egress_scan.py 가 `yaml.load` 를 '데이터가 코드를 되살리는 길' 로 표시한다 — scripts/validate_repo.py 는 그 이름을 부르지 않고(`yaml.safe_load` 와 로더 인스턴스 호출만), 그래서 외부 접속 등록 목록을 늘리지 않는다."""
        import ast
        tree = ast.parse((ROOT / "scripts" / "validate_repo.py").read_text(encoding="utf-8"))
        called = {f"{node.func.value.id}.{node.func.attr}" for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)}
        for name in ("yaml.load", "yaml.load_all", "yaml.unsafe_load", "yaml.full_load"):
            self.assertNotIn(name, called)
        self.assertIn("yaml.safe_load", called)

    def test_non_strict_loading_keeps_the_old_last_value_reading_for_the_two_config_files(self):
        text = "a: 1\na: 2\n"
        self.assertEqual(vr._load_yaml(text, strict=False), {"a": 2})
        with self.assertRaises(yaml.YAMLError):
            vr._load_yaml(text)
        source = (ROOT / "scripts" / "validate_repo.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("strict=False"), 3)                                        # 정의의 설명 한 곳 + `_config.yml`·편집 명세 둘뿐
        self.assertIn('_load_yaml(read_text(root, "_config.yml") or "", strict=False)', source)
        self.assertIn('_load_yaml(read_text(root, spec_path) or "", strict=False)', source)

    def test_every_other_checker_leaves_a_duplicate_key_file_to_wf0_without_crashing(self):
        text = BASE.replace("permissions:", "on: workflow_run\npermissions:", 1).replace("  contents: read\n", "  contents: write\n  contents: read\n", 1)
        files = {".github/workflows/x.yml": text}
        for name in ("check_workflow_run_workflows", "check_telegram_secrets", "check_workflow_names", "check_workflow_prefixes"):
            findings_of(files, name)                                                             # 예외 없이 끝난다(WF-0 은 check_workflows 가 낸다)
        self.assertTrue(wf0(findings_of(files)))

    def test_no_yaml_file_of_the_repository_has_a_duplicate_key(self):
        """기존 워크플로·이슈 양식·설정 전부가 새 읽기를 통과한다 — 새로 걸리는 오류가 0 이다(켜는 날의 전제)."""
        bad = []
        checked = 0
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in (".yml", ".yaml") or any(part in vr.SKIP_DIRS for part in path.relative_to(ROOT).parts):
                continue
            checked += 1
            try:
                vr._load_yaml(path.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                bad.append((path.relative_to(ROOT).as_posix(), str(exc).splitlines()[0]))
        self.assertGreaterEqual(checked, 25)
        self.assertEqual(bad, [])

    def test_the_real_workflows_still_load_to_the_same_values_as_before(self):
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            self.assertEqual(vr._load_yaml(text), yaml.safe_load(text), path.name)


class CaseVariantTest(unittest.TestCase):
    """AN1-S-7: 이벤트 이름과 파일 확장자의 대소문자 변형이 허용 목록·금지 규칙을 피하지 못한다."""

    def test_triggers_are_read_with_lowercase_event_names_in_every_form(self):
        self.assertEqual(vr._triggers({"on": {"Workflow_Run": {"types": ["completed"]}, "PUSH": None}}), {"workflow_run": {"types": ["completed"]}, "push": None})
        self.assertEqual(vr._triggers({"on": ["WORKFLOW_RUN", "Push"]}), {"workflow_run": None, "push": None})
        self.assertEqual(vr._triggers({"on": "Workflow_Run"}), {"workflow_run": None})
        self.assertEqual(vr._triggers({True: {"Issues": None}}), {"issues": None})                  # YAML 1.1: `on` 이 True 로 읽힌다
        self.assertEqual(vr._triggers({"on": {"push": None}}), {"push": None})                      # 소문자는 그대로
        self.assertEqual(vr._triggers({"on": None}), {})
        self.assertEqual(vr._triggers("not a table"), {})

    def test_a_mixed_case_workflow_run_event_does_not_escape_the_allow_list(self):
        for label, on_text in {"table key": "on:\n  Workflow_Run:\n    workflows: [ci]\n    types: [completed]\n", "upper list": "on: [WORKFLOW_RUN]\n", "mixed string": "on: Workflow_Run\n"}.items():
            with self.subTest(label):
                text = BASE.replace("permissions:", on_text + "permissions:", 1)
                found = [f for f in findings_of({".github/workflows/x.yml": text}) if f.check == "WF-16"]
                self.assertTrue(found, label)
                self.assertIn("허용 목록에 없는 workflow_run", "\n".join(f.message for f in found))
                alone = findings_of({".github/workflows/x.yml": text}, "check_workflow_run_workflows")
                self.assertTrue(alone, label)

    def test_a_mixed_case_pull_request_target_is_still_forbidden(self):
        for on_text in ("on:\n  Pull_Request_Target:\n", "on: [PULL_REQUEST_TARGET]\n", "on: Pull_Request_Target\n"):
            with self.subTest(on_text):
                text = BASE.replace("permissions:", on_text + "permissions:", 1)
                found = [f for f in findings_of({".github/workflows/x.yml": text}) if f.check == "WF-3"]
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0].level, "ERROR")

    def test_the_workflow_file_filter_ignores_the_case_of_the_extension_only(self):
        files = [".github/workflows/a.yml", ".github/workflows/b.yaml", ".github/workflows/c.YML", ".github/workflows/d.Yaml", ".github/workflows/e.YAML", ".github/workflows/sub/f.yml",
                 ".github/workflows/g.yml.bak", ".github/workflows/h.txt", ".GITHUB/workflows/i.yml", ".github/Workflows/j.yml", "x/.github/workflows/k.yml", ".github/workflows/.yml"]
        self.assertEqual(vr._workflow_files(files), [".github/workflows/a.yml", ".github/workflows/b.yaml", ".github/workflows/c.YML", ".github/workflows/d.Yaml", ".github/workflows/e.YAML"])

    def test_an_uppercase_extension_copy_of_an_allowed_workflow_is_checked_and_refused(self):
        real = (ROOT / ".github" / "workflows" / "merge-ready-notice.yml").read_text(encoding="utf-8")
        rel = ".github/workflows/merge-ready-notice.YML"
        found = [f for f in findings_of({rel: real}) if f.check == "WF-16"]
        self.assertTrue(found)
        self.assertIn("허용 목록에 없는 workflow_run", "\n".join(f.message for f in found))
        self.assertEqual(findings_of({".github/workflows/merge-ready-notice.yml": real}), [])        # 진짜 이름은 오류 없이 통과(대조)

    def test_mixed_case_keys_other_than_events_are_left_alone(self):
        """이벤트 이름만 접는다 — 설정 값·다른 키는 그대로다(`branches` 같은 하위 키의 대소문자는 GitHub 가 그대로 읽는다)."""
        raw = vr._triggers({"on": {"Push": {"Branches": ["Main"]}}})
        self.assertEqual(raw, {"push": {"Branches": ["Main"]}})


if __name__ == "__main__":
    unittest.main()
