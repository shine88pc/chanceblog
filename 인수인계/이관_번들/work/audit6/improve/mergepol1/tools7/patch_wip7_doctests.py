p = "C:/work/ai/improve_wt_mergepol1/tests/test_merge_policy_docs.py"
t = open(p, encoding="utf-8", newline="").read()


def rep(old, new, count=1):
    global t
    assert t.count(old) == count, (t.count(old), old[:100])
    t = t.replace(old, new)


rep('''        (7, "AI 가 읽고 따르는 규칙 문서 10개도 운영자 전용입니다"),''', '''        (7, "AI 가 읽고 따르는 규칙 문서 18개도 운영자 전용입니다"),
        (7, "용어 사전(`docs/GLOSSARY.md`)은 규칙이 아니라 사전이라 넣지 않았습니다"),
        (7, "- **운영자 확인 대기 항목**: 용어 사전 `docs/GLOSSARY.md` 를 규칙 문서 목록에 넣을지"),
        (7, "`openssl s_client`·`socat`·`aria2c`·`npm publish`·`docker push`·`pip install` 같은 것도 따로 잡지 않습니다"),
        (7, "'모름' 문구는 목록에 있는 문구와 **정확히 같을 때만** 거절합니다"),
        (7, "**어느 구간이든 앞뒤에 공백(유니코드 공백 포함)이 있는 경로**"),
        (7, "맨 앞의 공백 한 칸이 `docs` 같은 내부 폴더 이름처럼 보이게 하던 우회를 이렇게 막습니다"),
        (7, "**키가 모두 변경 파일 목록에 있어야 하고 변경 파일마다 키가 있어야**"),
        (7, "이름 안에 `requirements` 가 든 `dev-requirements.txt`·`pip-requirements.in` 도"),''')
rep('''        (6, "빠진 값은 실패"),''', '''        (6, "빠진 값은 실패"),
        (6, "이 함수가 스스로 다시 계산하는 것은 변경 분류와 머리 커밋 일치뿐이고 나머지 값은 모양만 확인합니다"),
        (6, "그래서 값은 GitHub 에서 직접 읽는 신뢰할 수 있는 워크플로가 만든 것이어야 합니다(§11-3)"),''')
rep('''        (11, "**병합을 호출하기 직전마다** 병합 이력 전체로 `evaluate_trial` 을 돌려"),''', '''        (11, "**병합을 호출하기 직전마다** 병합 이력 전체로 `evaluate_trial` 을 돌려"),
        (11, "- **값의 출처**(켜기 전의 필수 조건):"),
        (11, "`repo_kind`·`changed_text`·`checks`·`required_checks`·`independent_verification`·`has_conflict`·`secret_findings`·`pr_state`·`pr_draft`·`previous_merge_main_check` 는 GitHub 에서 직접 읽는 신뢰할 수 있는 워크플로가 만든 값이어야 합니다"),
        (11, "변경 파일마다 키가 있어야 합니다(글이 없는 파일은 빈 글)"),''')
rep('''    def test_the_first_tree_word_is_explained(self):''', '''    def test_sections_six_eight_nine_and_ten_say_first_that_they_describe_the_behaviour_after_turning_it_on(self):
        """§5 처럼 §6·§8·§9·§10 도 머리에 '켜진 뒤의 동작이며 지금은 꺼져 있다' 한 줄을 둔다(I-N7)."""
        for number, title in ((6, "병합 직전 재확인 8조건"), (8, "병합 방식 제한"), (9, "사후 처리"), (10, "첫 운영 3건 시험과 즉시 중지")):
            with self.subTest(section=number):
                lines = SECTIONS[number].split("\\n")
                self.assertEqual(lines[0], "## %d. %s" % (number, title))
                self.assertEqual(lines[1], "")
                self.assertTrue(lines[2].startswith("이 절은 켜진 뒤의 동작이며 지금은 꺼져 있습니다."), (number, lines[2]))
        self.assertIn("main 에 직접 push 하지 않는다는 원칙은 꺼져 있는 지금도 그대로입니다", SECTIONS[8].split("\\n")[2])

    def test_the_first_tree_word_is_explained(self):''')
rep('''        for phrase in ("거절 목록으로 구현했습니다", "글의 **모양**만 봅니다", "`pipeline/profiles/`", "`conftest.py`", "`sitecustomize.py`", "`tests/_bootstrap.py`", "`pipeline/__init__.py`",
                       "문자열을 쪼개 붙이거나", "선언 6항목은 사람이 정하는 값", "하나를 지워도 결과가 같습니다", "총괄(AI)의 판단 — 운영자 확인 대기"):''',
    '''        for phrase in ("거절 목록으로 구현했습니다", "글의 **모양**만 봅니다", "`pipeline/profiles/`", "`conftest.py`", "`sitecustomize.py`", "`tests/_bootstrap.py`", "`pipeline/__init__.py`",
                       "문자열을 쪼개 붙이거나", "선언 6항목은 사람이 정하는 값", "하나를 지워도 결과가 같습니다", "총괄(AI)의 판단 — 운영자 확인 대기", "`docs/GLOSSARY.md`", "`pipeline/shadow_run.py`",
                       "`pipeline/drafts.py`", "`openssl s_client`", "`docker push`", "`'row.id'`", "`'pipeline.store'`", "정확히 같을 때만", "이름 없는 무작위 문자열 모양의 비밀"):''')
open(p, "w", encoding="utf-8", newline="").write(t)
print("ok")
