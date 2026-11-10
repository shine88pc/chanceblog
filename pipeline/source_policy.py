"""소스 정책 스위치(레지스트리 chance.source_policy)와 그 값이 켜졌을 때의 규칙 — 외부 콘텐츠를 읽는 방식을 한 값으로 정한다(docs/SOURCE_POLICY.md).

값
- `legacy`(기본 — 항목에 적지 않아도 같다): 지금과 같다. 이 모듈의 모든 함수가 입력을 그대로 돌려주거나 아무 일도 하지 않아 생성기의 출력이 바이트까지 이전과 같다.
- `allowlist`: 허용 목록(Source Registry)의 ACTIVE Provider 만 읽는다. 일반 웹 읽기(RSS 피드·기사 페이지 발췌·구글 뉴스 해석기)는 허용 목록에 무엇이 있든 하지 않고(관문이 항상 거부),
  외부 제목·요약·태그가 AI 프롬프트·이력(history.json 의 topic)·로그·실행 요약·탈락 기록에 들어가지 않으며, ACTIVE 콘텐츠 Provider 가 0 이면 초록으로 끝나는 '일 없음'
  결과 코드 SOURCE_POLICY_NO_ACTIVE_PROVIDER 로 끝난다(ALL_LANES_EMPTY 의 빨강과 구분).
켜는 것(`allowlist`)은 T3 다 — 이 변경은 pipeline/blogs.json 의 값을 바꾸지 않는다.

FACT(구조화 Fact 경로)와의 계약: allowlist 에서 후보가 흐름에 들어오려면 자체 제목(`own_title`)을 가져야 한다. 이력의 `topic`·프롬프트의 주제·로그·탈락 기록에 쓰이는 제목은 그 자체 제목뿐이고,
`own_title` 이 없는 후보(외부 기사 제목을 가진 후보)는 흐름에서 빠진다. 프롬프트에는 자체 제목만 가며(요약·링크·출처 이름·게시 시각·태그 없음) 그 밖의 근거는 Fact 로 바뀐다.
**제목 말고 후보의 `source`·`publisher_domain`·`citation`·`link` 칸은 이 모듈이 고치지도 검증하지도 않고 그대로 통과시킨다(D-175)** — 후보에 Provider 식별자 규약이 아직 없고 Registry 와 오늘을
받으려면 생성기 호출부를 바꿔야 해서다. 그래서 이 칸들도 후보를 만드는 쪽(FACT 2단계)이 우리가 정한 문자열(Registry 의 Provider 이름·호스트·`attribution_template`)로만 채우는 것이 계약이다
(tests/test_source_policy.py 가 통과 동작을 못박고 docs/SOURCE_POLICY.md 9절이 의무로 적는다). `legacy_policy_notice` 는 legacy 인데 AI 정책이 원문 외부 텍스트 입력 금지일 때 알릴 한 줄이다(호출하는 곳은 FACT 2단계 몫 — 생성기는 건드리지 않는다).

표준 라이브러리와 pipeline 의 다른 모듈만 쓴다. 입출력은 `chance_source_policy`(레지스트리 읽기)·`news_registry`/`idle_check`/`egress_gate`(허용 목록 읽기)뿐이고 시각은 읽지 않는다(오늘은 인자).
"""
from pipeline import egress, source_registry

LEGACY, ALLOWLIST = "legacy", "allowlist"
SOURCE_POLICIES = (LEGACY, ALLOWLIST)
DEFAULT_SOURCE_POLICY = LEGACY
NO_ACTIVE_OUTCOME = "SOURCE_POLICY_NO_ACTIVE_PROVIDER"
OWN_TITLE_KEY = "own_title"


def registry_errors(blog, label, platform):
    """레지스트리 검증(registry.validate_registry)이 부르는 규칙: source_policy 는 legacy·allowlist 중 하나이고 platform jekyll-git(Chance)에서만 쓴다. 적지 않았으면 문제 없음(legacy)."""
    if "source_policy" not in blog:
        return []
    value = blog["source_policy"]
    if not isinstance(value, str) or value not in SOURCE_POLICIES:
        return [f"{label}: source_policy는 {SOURCE_POLICIES} 중 하나여야 합니다: {str(value)[:40]!r}"]
    if platform != "jekyll-git":
        return [f"{label}: source_policy는 platform jekyll-git 에서만 쓸 수 있습니다(지금 platform: {platform!r}). Blogger·초안 패키지는 외부 본문을 읽지 않습니다."]
    return []


def chance_source_policy(registry_path=None, key="chance"):
    """레지스트리에서 chance 블로그의 source_policy('legacy'|'allowlist'). 항목에 적지 않았으면 legacy. 레지스트리를 읽지 못하거나 값이 올바르지 않으면 RegistryError 다 —
    값을 못 읽었다고 조용히 느슨한 쪽(legacy)으로 떨어지지 않고 멈춘다(drafts.chance_flow 와 같은 원칙)."""
    from pipeline import registry        # 지연 import: registry.py 가 이 모듈을 import 하므로 순환을 피한다
    blog = registry.get_blog(registry.load_registry(registry_path), key)
    value = blog.get("source_policy", DEFAULT_SOURCE_POLICY)
    if not isinstance(value, str) or value not in SOURCE_POLICIES:
        raise registry.RegistryError(f"레지스트리 source_policy 값이 올바르지 않습니다: {str(value)[:40]!r} ({' 또는 '.join(SOURCE_POLICIES)})")
    return value


def _today(today):
    """오늘 인자는 날짜(date·datetime·ISO 문자열)이거나 그것을 돌려주는 인자 없는 함수다 — 함수면 allowlist 일 때만 부른다(legacy 는 시계를 건드리지 않는다)."""
    return today() if callable(today) else today


def news_registry(mode, today, path=None):
    """allowlist 일 때만 허용 목록(Registry)을 읽어 돌려주고, legacy 면 None(읽지 않는다 — 이전과 같다). 허용 목록 파일을 읽지 못하면 SourceRegistryError 로 멈춘다."""
    if mode != ALLOWLIST:
        return None
    return source_registry.load_registry(path, _today(today))


def active_content_providers(registry):
    """ACTIVE 콘텐츠 Provider(class data) 목록. ACTIVE 는 규칙 A0 때문에 class data 뿐이다."""
    return [p for p in registry.active_providers() if p.provider_class == source_registry.ACTIVE_CLASS]


def idle_check(mode, report, today, out=print, registry=None, path=None):
    """allowlist 이고 ACTIVE 콘텐츠 Provider 가 0 이면 report["outcome"] 에 SOURCE_POLICY_NO_ACTIVE_PROVIDER 를 적고 True(= 호출한 쪽은 네트워크·모델 호출 없이 끝낸다).
    enabled 인데 ACTIVE 가 못 된 Provider 의 사유는 한 줄씩 out 으로 남긴다. legacy 면 아무 일도 하지 않고 False. ACTIVE 가 하나라도 있으면 False(일반 흐름이 계속된다)."""
    if mode != ALLOWLIST:
        return False
    reg = registry if registry is not None else source_registry.load_registry(path, _today(today))
    for line in reg.report_lines():
        out(line)
    if active_content_providers(reg):
        return False
    report["outcome"] = NO_ACTIVE_OUTCOME
    return True


def egress_gate(url, purpose, today=None, mode=None, registry=None, path=None):
    """외부 호출 관문(egress.check_url)을 allowlist 일 때만 거친다 — legacy 는 아무 일도 하지 않는다(이전과 같다). 허용이 아니면 EgressDenied(문구에 호스트·사유만).
    mode 를 안 주면 레지스트리에서 읽고, registry 를 안 주면 허용 목록 파일을 읽는다(today 필요). 호출 목록 시험(tests/test_egress.py)은 이 호출을 '관문을 거침'으로 인정하지 않는다(legacy 에서 아무 일도 하지 않는다) — 이 호출이 있는 곳은 등록 목록(egress.EGRESS_EXCEPTIONS)에 'allowlist 에서만 막힘'으로 올라 있다."""
    if (mode if mode is not None else chance_source_policy()) != ALLOWLIST:
        return
    egress.check_url(url, purpose, registry if registry is not None else source_registry.load_registry(path, _today(today)))


def own_title(item):
    """후보의 자체 제목(문자열, 앞뒤 공백 제거). 없으면 빈 문자열."""
    value = item.get(OWN_TITLE_KEY) if isinstance(item, dict) else None
    return value.strip() if isinstance(value, str) else ""


def prompt_inputs(mode, item, recent_titles):
    """프롬프트 조립부(build_post_prompt)가 쓰는 입력. legacy 는 그대로(같은 객체). allowlist 는 후보를 자체 제목만 가진 사본({"title": 자체 제목})으로 바꾸고 — 자체 제목이 없으면 None(= '검증된
    출처가 제공되지 않았습니다 — skip' 입력) — 외부 요약·제목·링크·출처 이름·게시 시각·태그·규칙 문구는 모두 뺀다. 최근 제목 목록은 부르는 쪽이 prompt_titles 로 이미 걸렀다."""
    if mode != ALLOWLIST:
        return item, recent_titles
    title = own_title(item)
    return ({"title": title} if title else None), recent_titles


def external_history_titles(history):
    """이력에서 '외부 글에서 온 제목'으로 보는 문자열 집합: 문자열 항목(출처를 알 수 없는 옛 형식)과, 자체 글 제목(kr_title·en_title)과 다른 topic 을 가진 dict 항목.
    출처 주소(source_url)가 없는 옛 항목(2026-10-19 두 건 — 외부 제목이 topic 인데 주소 칸이 없다)도 같다: 외부인지 모르면 외부로 본다(안전한 쪽 — '최근 다룬 제목'에서 빠질 뿐이다)."""
    out = set()
    for entry in history or ():
        if isinstance(entry, str):
            if entry.strip():
                out.add(entry.strip())
        elif isinstance(entry, dict):
            topic = entry.get("topic")
            if isinstance(topic, str) and topic.strip() and topic.strip() not in (str(entry.get("kr_title") or "").strip(), str(entry.get("en_title") or "").strip()):
                out.add(topic.strip())
    return out


LEGACY_AI_NOTICE = ("참고: source_policy 가 legacy 라 외부 기사 요약이 지금도 AI(Gemini) 입력으로 간다 — AI 처리기 정책(raw_source_text_allowed: false)과 어긋난 알려진 상태다. "
                    "allowlist 로 바꾸면 프롬프트 조립부가 자체 제목만 보낸다(docs/SOURCE_POLICY.md 10절).")


def legacy_policy_notice(mode, policy=None):
    """legacy 인데 AI 처리기 정책이 원문 외부 텍스트 입력 금지(raw_source_text_allowed: false)이면 알릴 한 줄(문자열), 아니면 None. 코드는 정책 파일을 실행 중에 읽지 않으므로 이 한 줄이 어긋남을 보이는 유일한 길이다 —
    부르는 곳은 FACT 2단계 연결 몫이다(생성기는 바꾸지 않았다: legacy 의 출력은 이전과 바이트까지 같아야 한다). policy 를 안 주면 정책 파일을 읽는다(AiProcessorPolicy)."""
    if mode != LEGACY:
        return None
    ai = policy if policy is not None else source_registry.load_ai_policy()
    return LEGACY_AI_NOTICE if ai.raw_source_text_allowed is False else None


def prompt_titles(mode, titles, history):
    """'최근 다룬 제목' 목록. legacy 는 그대로(같은 객체). allowlist 는 이력의 외부 글 제목을 뺀다(자체 글 제목만 남는다)."""
    if mode != ALLOWLIST:
        return titles
    external = external_history_titles(history)
    return [t for t in titles if t not in external]


def own_title_batches(mode, batches, on_drop=None):
    """(분야, 후보 목록) 흐름. legacy 는 그대로(같은 객체). allowlist 는 자체 제목(own_title)이 없는 후보를 빼고, 남은 후보의 title 을 자체 제목으로 바꾼다 — 그래서 이력의 topic·프롬프트의
    주제·로그·탈락 기록에는 자체 제목만 쓰인다. 빠진 후보 수는 on_drop(수)으로 알린다(제목은 알리지 않는다). 후보가 하나도 남지 않은 분야는 내보내지 않는다.
    제목 말고는 후보의 칸(source·publisher_domain·citation·link 등)을 그대로 통과시킨다 — 그 칸들이 우리가 정한 문자열인 것은 후보를 만드는 쪽의 몫이다(모듈 머리말의 계약, D-175)."""
    if mode != ALLOWLIST:
        return batches

    def filtered():
        for lane, found in batches:
            kept = [dict(item, title=own_title(item)) for item in found if own_title(item)]
            if len(kept) != len(found) and on_drop is not None:
                on_drop(len(found) - len(kept))
            if kept:
                yield lane, kept

    return filtered()
