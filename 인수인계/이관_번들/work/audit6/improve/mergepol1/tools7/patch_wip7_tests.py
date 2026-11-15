p = "C:/work/ai/improve_wt_mergepol1/tests/test_merge_policy.py"
t = open(p, encoding="utf-8", newline="").read()
BS = chr(92)


def rep(old, new, count=1):
    global t
    assert t.count(old) == count, (t.count(old), old[:100])
    t = t.replace(old, new)


def replace_line(marker, new_line):
    """marker 가 든 줄이 정확히 하나일 때 그 줄 전체를(들여쓰기 유지) 바꾼다."""
    global t
    lines = t.split("\n")
    hits = [i for i, line in enumerate(lines) if marker in line]
    assert len(hits) == 1, (marker, hits)
    indent = lines[hits[0]][: len(lines[hits[0]]) - len(lines[hits[0]].lstrip())]
    lines[hits[0]] = indent + new_line
    t = "\n".join(lines)


# ---- 못박기: 안전 목록
rep('''"docs/AGENT_RUNBOOK.md", "docs/SESSION_START.md"))''',
    '''"docs/AGENT_RUNBOOK.md", "docs/SESSION_START.md", "docs/ENGINEERING_GUIDE.md", "docs/AGENT_DELEGATION.md", "docs/COPILOT_GUIDE.md", "docs/AI_FLOW.md",
                                                "docs/AI_MODEL_GUIDE.md", "docs/SOURCE_POLICY.md", "docs/QUALITY_GATE.md", "docs/REQUEST_BRIEFING.md"))''')
rep('''"scripts/get_blogger_token.py", "scripts/watchdog.py", "tests/test_site_cleanup.py"))''',
    '''"scripts/get_blogger_token.py", "scripts/watchdog.py", "tests/test_site_cleanup.py", "pipeline/run.py", "pipeline/operator_loop.py",
                                                 "pipeline/telegram_inbox.py"))''')

# ---- 허용 분류 시료
rep('''("오류 수정", "blog", ["pipeline/run.py"], "if value is None:\\n    return 0\\n"),''', '''("오류 수정", "blog", ["pipeline/rounding.py"], "if value is None:\\n    return 0\\n"),''')
rep('''("blog", "pipeline/tokenizer.py"), ("blog", "docs/SOURCE_POLICY.md"),''', '''("blog", "pipeline/tokenizer.py"), ("blog", "docs/GLOSSARY.md"),''')
rep('''for kind, path in (("blog", "docs/SOURCE_POLICY.md"), ("blog", "docs/AI_FLOW.md"), ("blog", "docs/QUALITY_GATE.md"), ("blog", "docs/ARCHITECTURE.md"), ("blog", "docs/security_notes.md"),''',
    '''for kind, path in (("blog", "docs/GLOSSARY.md"), ("blog", "docs/FACT_PATH.md"), ("blog", "docs/OPS_INBOX.md"), ("blog", "docs/ARCHITECTURE.md"), ("blog", "docs/security_notes.md"),''')

# ---- 이름 안전 목록 시험의 목록
rep('''"pipeline/draft_flow.py", "pipeline/edits/runner.py", "generator.py", "blogger_generator.py", "scripts/get_blogger_token.py", "scripts/watchdog.py", "tests/test_site_cleanup.py")
    PUBLISHERS''', '''"pipeline/draft_flow.py", "pipeline/edits/runner.py", "generator.py", "blogger_generator.py", "scripts/get_blogger_token.py", "scripts/watchdog.py", "tests/test_site_cleanup.py",
             "pipeline/run.py", "pipeline/operator_loop.py", "pipeline/telegram_inbox.py")
    PUBLISHERS''')
rep('''    RULE_DOCS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "AI_COLLAB.md", "HANDLER.md", "docs/CHARTER.md", "docs/SECURITY_GUARDRAILS.md", "docs/ACTIONS_GUIDE.md", "docs/AGENT_RUNBOOK.md",
                 "docs/SESSION_START.md")''',
    '''    RULE_DOCS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "AI_COLLAB.md", "HANDLER.md", "docs/CHARTER.md", "docs/SECURITY_GUARDRAILS.md", "docs/ACTIONS_GUIDE.md", "docs/AGENT_RUNBOOK.md",
                 "docs/SESSION_START.md", "docs/ENGINEERING_GUIDE.md", "docs/AGENT_DELEGATION.md", "docs/COPILOT_GUIDE.md", "docs/AI_FLOW.md", "docs/AI_MODEL_GUIDE.md", "docs/SOURCE_POLICY.md",
                 "docs/QUALITY_GATE.md", "docs/REQUEST_BRIEFING.md")
    CONFIRM_ITEMS = ("pipeline/shadow_run.py", "pipeline/drafts.py", "docs/GLOSSARY.md", "pipeline/profiles/blogger_practical_en.json", "tests/_bootstrap.py", "pipeline/__init__.py")''')
rep('''"pipeline/draft_flow2.py", "pipeline/drafts.py")
    NEAR_DOCS''', '''"pipeline/draft_flow2.py", "pipeline/drafts.py", "pipeline/run_helper.py", "pipeline/runs.py", "pipeline/operator_loop_x.py", "pipeline/telegram_inbox2.py", "pipeline/shadow_run.py",
                   "scripts/run.py", "sub/pipeline/run.py", "docs/pipeline/run.py")
    NEAR_DOCS''')
rep('''"docs/AGENT_DELEGATION.md", "WORKLOG.md", "docs/DEFECT_REGISTER.md", "인수인계/작업내용.md")

    def assert_guard''', '''"docs/FACT_PATH.md", "WORKLOG.md", "docs/DEFECT_REGISTER.md", "인수인계/작업내용.md", "docs/ENGINEERING_GUIDE_NOTES.md", "docs/QUALITY_GATE_NOTES.md")

    def assert_guard''')
rep('''        self.assertEqual(len(mp.SAFETY_GUARD_DOCS), 10)''', '''        self.assertEqual(len(mp.SAFETY_GUARD_DOCS), 18)''')
rep('''    def test_the_names_are_matched_exactly_not_by_prefix_or_folder(self):''', '''    def test_the_operator_confirm_items_are_not_in_the_list_so_a_change_to_them_is_decided_by_the_rest_of_the_rules(self):
        """운영자 확인 대기 항목(shadow_run·drafts·용어 사전·콘텐츠 안전 프로필·가져올 때 실행되는 파일)은 목록에 넣지 않았다 — 넣을지는 운영자가 정한다(§7-7)."""
        for path in self.CONFIRM_ITEMS:
            with self.subTest(path=path):
                self.assertEqual(classify("desktop", [path]).tier, "ai_ok", path)

    def test_the_names_are_matched_exactly_not_by_prefix_or_folder(self):''')

# ---- 의존성 이름(I-N1)
rep('''                        "REQUIREMENTS.TXT", "Environment.YML")''', '''                        "REQUIREMENTS.TXT", "Environment.YML", "dev-requirements.txt", "test-requirements.txt", "deps.txt", "pip-requirements.in", "my_requirements_x.txt", "deps-dev.in", "dependencies.txt",
                        "build_dependencies.in", "Dockerfile", "Makefile", "prod.Dockerfile", "Dockerfile.dev", "makefile", "GNUmakefile", "DEPS.TXT", "Test-Requirements.TXT")''')
rep('''        for path in ("pipeline/requirements.md", "pipeline/requirements_notes.py",''', '''        for path in ("pipeline/requirement.txt", "pipeline/deps.py", "pipeline/deps.md", "pipeline/dependency.txt", "pipeline/docker.py", "pipeline/makes.py", "pipeline/requirements.md", "pipeline/requirements_notes.py",''')

# ---- 경로 정규화 시험 갱신(N-M1)
replace_line('self.assertEqual(mp.normalize_repo_path(" a', 'self.assertEqual(mp.normalize_repo_path("a" + chr(92) + "b.py" + chr(10)), "a/b.py")                                         # 줄 끝의 줄 바꿈만 뗀다')
rep('''    def test_normalize_path(self):''', '''    SPACE_PATHS = (" docs/x.html", chr(0xA0) + "tests/page.html", chr(0x3000) + "tests/x.html", chr(0x2003) + "인수인계/x.html", "  pipeline/page.html", " WORKLOG.md", " scripts/x.js",
                   chr(0x85) + "docs/x.html", chr(0x2028) + "docs/x.html", chr(0x1F) + "docs/x", chr(9) + "tests/x.html", chr(0x2029) + "docs/x", chr(0x202F) + "docs/x", chr(0x1680) + "docs/x")

    def test_a_path_whose_segment_has_whitespace_around_it_is_refused(self):
        """맨 앞의 공백이 구간 이름을 바꿔 내부 폴더(docs·tests·인수인계)처럼 보이게 하던 우회를 막는다(N-M1) — 어느 구간이든 앞뒤 공백이면 확인할 수 없는 입력이다."""
        for path in self.SPACE_PATHS + ("docs /x", "docs/x ", "docs/ x", "docs/x" + chr(9), "docs" + chr(0xA0) + "/x", "a/" + chr(0x3000) + "/b", " ", "a/ /b", "./ docs/x", "docs/./ x",
                                         " " + chr(92) + "docs" + chr(92) + "x", "docs" + chr(92) + " x"):
            with self.subTest(path=repr(path)):
                self.assertIsNone(mp.normalize_repo_path(path))

    def test_every_unicode_whitespace_is_refused_in_front_in_the_middle_and_at_the_end(self):
        spaces = [chr(code) for code in range(0x30000) if chr(code).isspace()]
        self.assertGreater(len(spaces), 20)
        for space in spaces:
            for path in (space + "docs/x.html", "docs" + space + "/x.html", "docs/" + space + "x.html", "docs/x.html" + space):
                with self.subTest(code=hex(ord(space)), path=repr(path)):
                    if path == "docs/x.html" + space and space in (chr(10), chr(13)):
                        self.assertEqual(mp.normalize_repo_path(path), "docs/x.html")               # 줄 끝의 줄 바꿈만 뗀다
                    else:
                        self.assertIsNone(mp.normalize_repo_path(path))

    def test_only_the_line_end_is_trimmed(self):
        for path in ("docs/x.html", "docs/x.html" + chr(10), "docs/x.html" + chr(13) + chr(10), "docs/x.html" + chr(10) + chr(10), "docs/x.html" + chr(13)):
            self.assertEqual(mp.normalize_repo_path(path), "docs/x.html", repr(path))
        for path in ("docs/x.html " + chr(10), "docs/x.html" + chr(10) + " ", chr(10) + "docs/x.html", "docs/" + chr(10) + "x.html", chr(13) + "docs/x.html"):
            self.assertIsNone(mp.normalize_repo_path(path), repr(path))

    def test_control_characters_anywhere_refuse_the_path_including_del_and_the_c1_range(self):
        for code in list(range(0, 32)) + list(range(127, 160)):
            with self.subTest(code=hex(code)):
                self.assertIsNone(mp.normalize_repo_path("a" + chr(code) + "b/c.py"))
                self.assertIsNone(mp.normalize_repo_path("a/b" + chr(code) + "c.py"))
                self.assertIsNone(mp.normalize_repo_path("a/b/c.py" + chr(code) + "x"))
        for code in (160, 173, 0x200B, 0x200E, 0x202E, 0xFEFF):                                    # 제어 문자가 아닌 것(보이지 않는 글자 등)은 이름 일부라 정규화는 그대로 두고 분류가 공개 파일로 막는다
            path = "a/b" + chr(code) + "c.py"
            self.assertEqual(mp.normalize_repo_path(path), path)

    def test_only_a_plain_str_is_a_path(self):
        class Path(str):
            pass

        self.assertIsNone(mp.normalize_repo_path(Path("docs/x.html")))
        self.assertEqual(mp.normalize_repo_path(str(Path("docs/x.html"))), "docs/x.html")

    def test_a_refused_path_voids_an_approval(self):
        for path in self.SPACE_PATHS:
            self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, [path], [path]), repr(path))
            self.assertFalse(mp.approval_still_valid(SHA_A, SHA_A, ["pipeline/a.py", path], ["pipeline/a.py", path]), repr(path))

    def test_normalize_path(self):''')

# ---- 입력 오류: 공백 경로·사전 키(S-N2)
rep('''    def test_a_bad_changed_text_is_not_ai_ok(self):''', '''    def test_a_path_with_whitespace_around_a_segment_is_not_ai_ok(self):
        """기본 거부·시험 면제·문서 면제를 공백 한 칸으로 속이지 못한다(N-M1) — 내부 폴더처럼 보이는 경로라도 입력 오류다."""
        for path in ApprovalValidityTest.SPACE_PATHS + ("docs /x.html", "docs/x.html "):
            for kind in ("blog", "desktop"):
                with self.subTest(path=repr(path), kind=kind):
                    self.assert_invalid(mp.classify_change(kind, [path], "", dict(DECLARED_OK)))
                    self.assert_invalid(mp.classify_change(kind, ["pipeline/a.py", path], "", dict(DECLARED_OK)))
                    self.assert_invalid(mp.classify_change(kind, [path], {path: "import requests" + chr(10)}, dict(DECLARED_OK)))
        self.assert_invalid(mp.classify_change("blog", [chr(0xA0) + "tests/page.html"], {"tests/page.html": ""}, dict(DECLARED_OK)))        # 키는 정상이어도 경로가 정상이 아니다
        self.assertEqual(mp.classify_change("blog", ["docs/x.html"], "", dict(DECLARED_OK)).tier, "ai_ok")

    def test_a_mapping_must_have_a_key_for_every_changed_file(self):
        """변경 파일 중 키가 빠진 파일의 바뀐 줄은 보이지 않는다 — 코드 파일의 키가 빠져도 통과하던 구멍(S-N2). 글이 없는 파일은 빈 글을 넣어야 한다."""
        paths = ["docs/x.md", "pipeline/y.py"]
        for given in ({"docs/x.md": "문서 한 줄" + chr(10)}, {"pipeline/y.py": "x = 1" + chr(10)}, {}, {"docs/x.md": "", "pipeline/z.py": ""}):
            with self.subTest(given=sorted(given)):
                result = mp.classify_change("blog", paths, given, dict(DECLARED_OK))
                self.assert_invalid(result)
        result = mp.classify_change("blog", paths, {"docs/x.md": "문서 한 줄" + chr(10)}, dict(DECLARED_OK))
        self.assertTrue(any("글이 없는 파일" in reason and "pipeline/y.py" in reason for reason in result.reasons), result.reasons)
        self.assertFalse(any("docs/x.md" in reason and "글이 없는 파일" in reason for reason in result.reasons))
        for given in ({"docs/x.md": "", "pipeline/y.py": ""}, {"docs/x.md": "문서", "pipeline/y.py": GOOD_TEXT}, {"./docs/x.md": "", "pipeline/y.py": ""},
                      {"docs/x.md": "", "pipeline" + chr(92) + "y.py": ""}):
            with self.subTest(ok=sorted(given)):
                self.assertEqual(mp.classify_change("blog", paths, given, dict(DECLARED_OK)).tier, "ai_ok")
        self.assert_invalid(mp.classify_change("blog", ["tests/t.py", "pipeline/y.py"], {"pipeline/y.py": ""}, dict(DECLARED_OK)))                         # 시험 파일의 키가 빠져도 마찬가지다(시험의 낱말 규칙이 안 보이지 않게)
        self.assert_invalid(mp.classify_change("blog", ["docs/x.md", "pipeline/y.py"], {"pipeline/y.py": ""}, dict(DECLARED_OK)))                          # 문서의 키가 빠져도 마찬가지다(문서의 비밀 모양이 안 보이지 않게)
        self.assertEqual(mp.classify_change("blog", ["tests/t.py", "docs/x.md"], {"tests/t.py": "", "docs/x.md": ""}, dict(DECLARED_OK)).tier, "ai_ok")
        self.assert_invalid(mp.classify_change("blog", ["old/a.py", "new/a.py"], {"new/a.py": "x = 1" + chr(10)}, dict(DECLARED_OK)))                  # 이름 바꾸기는 옛 경로의 키도 필요하다
        self.assertEqual(mp.classify_change("blog", ["pipeline/old_a.py", "pipeline/new_a.py"], {"pipeline/old_a.py": "", "pipeline/new_a.py": "x = 1" + chr(10)}, dict(DECLARED_OK)).tier, "ai_ok")

    def test_the_hidden_code_lines_attack_is_closed(self):
        """P 의 재현: 문서 키만 주고 코드 파일의 바뀐 줄(비밀 모양·외부 접속)을 숨기던 입력."""
        for hidden in ("import requests" + chr(10), FAKE_SECRETS["google"] + chr(10), "if PIPELINE_PAUSE:" + chr(10) + "    return" + chr(10)):
            result = mp.classify_change("blog", ["docs/x.md", "pipeline/y.py"], {"docs/x.md": "문서 한 줄" + chr(10)}, dict(DECLARED_OK))
            self.assert_invalid(result)
            self.assertEqual(mp.classify_change("blog", ["docs/x.md", "pipeline/y.py"], {"docs/x.md": "문서 한 줄" + chr(10), "pipeline/y.py": hidden}, dict(DECLARED_OK)).tier, "operator_only")

    def test_a_bad_changed_text_is_not_ai_ok(self):''')
rep('''        self.assertEqual(mp.classify_change("blog", ["pipeline/a.py", "pipeline/b.py"], {"pipeline/a.py": GOOD_TEXT}, dict(DECLARED_OK)).tier, "ai_ok")    # 글이 없는 파일은 괜찮다''',
    '''        self.assertEqual(mp.classify_change("blog", ["pipeline/a.py", "pipeline/b.py"], {"pipeline/a.py": GOOD_TEXT, "pipeline/b.py": ""}, dict(DECLARED_OK)).tier, "ai_ok")    # 글이 없는 파일은 빈 글''')

# ---- 재확인: 사전 {} 는 더는 '글 없음' 이 아니다
rep('''        facts["changed_text"] = {}
        self.assertTrue(mp.check_preconditions(facts).ok)''', '''        facts["changed_text"] = {path: "" for path in GOOD_PATHS}                                                       # 글이 없는 파일은 빈 글(키는 변경 파일마다 있어야 한다)
        self.assertTrue(mp.check_preconditions(facts).ok)
        for given in ({}, {GOOD_PATHS[0]: GOOD_TEXT}, {GOOD_PATHS[1]: GOOD_TEXT}):                                       # 키가 빠진 사전은 바뀐 줄을 다 볼 수 없어 분류를 다시 계산할 수 없다
            with self.subTest(given=sorted(given)):
                facts["changed_text"] = given
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("scope_matches",))
                self.assertIn("다시 계산하니", verdict.failures[0].reason)''')
rep('''("pr_draft", False), ("changed_text", ""), ("changed_text", "x"),
                        ("changed_text", {}))''', '''("pr_draft", False), ("changed_text", ""), ("changed_text", "x"))''')

# ---- 규칙 단어 시료
rep('''"sk_live_": ("blog", ["a.py"], "k = '" + "sk_live_" + "CANARY" + "a" * 18 + "'"), "sk_test_": ("blog", ["a.py"], "k = '" + "sk_test_" + "CANARY" + "a" * 18 + "'"),''',
    '''"sk_live_": ("blog", ["a.py"], "k = '" + "sk_live_" + "CANARY" + "a" * 18 + "'"), "sk_test_": ("blog", ["a.py"], "k = '" + "sk_test_" + "CANARY" + "a" * 18 + "'"),
            "deps.txt": ("blog", ["deps.txt"], ""), "Dockerfile": ("blog", ["Dockerfile"], ""), "Makefile": ("blog", ["Makefile"], ""),''')

# ---- 정확한 형식(I-N3)
rep('''    def test_the_merge_method_must_be_a_plain_str(self):''', '''    class EvilInt(int):
        """양수·0 이상·같음을 거짓으로 꾸미는 int 하위 형식."""

        def __gt__(self, other):
            return True

        def __ge__(self, other):
            return True

        def __eq__(self, other):
            return True

        def __ne__(self, other):
            return False

        def __hash__(self):
            return 1

    def test_numbers_must_be_exact_ints(self):
        """PR 번호·발견 수·남은 지적 수는 정확히 int 만 받는다 — 비교를 바꿔치는 int 하위 형식은 거절한다(I-N3, bool 거절 흐름은 그대로)."""
        for value in (self.EvilInt(-5), self.EvilInt(0), self.EvilInt(7)):
            with self.subTest(value=int(value)):
                ledger = mp.ApprovalLedger()
                self.assertFalse(ledger.consume("M075", value).ok)
                self.assertEqual(ledger.consumed_numbers, ())
                self.assertFalse(mp.ApprovalRecord("M075", value, SHA_A, SHA_A).valid)
                with self.assertRaises(ValueError):
                    mp.render_completion_notice("M075", value, "d" * 40, "초안 저장이 반영되었습니다.", "전체 통과", "이상 없음", "해당 병합 커밋 한 개를 되돌립니다.")
                with self.assertRaises(ValueError):
                    mp.render_explanation("M075", value, "c" * 40, ["pipeline/a.py"], *ANSWERS, classification=classify("blog", ["pipeline/a.py"], GOOD_TEXT))
                facts = good_facts()
                facts["approved_pr_number"] = facts["pr_number"] = value
                verdict = mp.check_preconditions(facts)
                self.assertEqual(verdict.failed_codes, ("number_match",))
                self.assertIn("양의 정수", verdict.failures[0].reason)
                facts = good_facts()
                facts["secret_findings"] = value                                                       # 발견 수가 0 이라고 우기는 하위 형식
                self.assertEqual(mp.check_preconditions(facts).failed_codes, ("no_secret_exposure",))
                facts = good_facts()
                facts["independent_verification"] = dict(facts["independent_verification"], open_required_findings=value)
                self.assertEqual(mp.check_preconditions(facts).failed_codes, ("independent_verified",))
        for value in (True, False, 1.0, "1", None):
            self.assertFalse(mp.ApprovalLedger().consume("M075", value).ok, repr(value))
        self.assertTrue(mp.ApprovalLedger().consume("M075", 198).ok)

    def test_the_repository_kind_must_be_a_plain_str(self):
        class Kind(str):
            pass

        for kind in (Kind("blog"), Kind("desktop"), self.Evil("blog"), self.Evil("desktop")):
            with self.subTest(kind=str.__repr__(kind)):
                result = mp.classify_change(kind, ["pipeline/a.py"], "", dict(DECLARED_OK))
                self.assertEqual((result.tier, "invalid_input" in result.extra_flags), ("operator_only", True))
                facts = good_facts()
                facts["repo_kind"] = kind
                self.assertEqual(mp.check_preconditions(facts).failed_codes, ("scope_matches",))
        self.assertEqual(mp.classify_change(str(Kind("blog")), ["pipeline/a.py"], "", dict(DECLARED_OK)).tier, "ai_ok")

    def test_the_merge_method_must_be_a_plain_str(self):''')
open(p, "w", encoding="utf-8", newline="").write(t)
print("ok")
