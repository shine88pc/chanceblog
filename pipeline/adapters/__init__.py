"""구조화 Fact 경로의 Provider 어댑터 — API·CSV·JSON 같은 구조화 응답만 읽는다.

- `base`: 어댑터 계약(`StructuredAdapter` — 주소 만들기·가져오기·읽기)과 오류(`AdapterError`), JSON·CSV 읽기 도구.
  네트워크는 **주입된 `opener`** 로만 쓰고 직접 `urlopen` 을 부르지 않는다(SRC 의 외부 호출 관문이 나중에 `opener` 를 감싼다).
- `mock_stats`: 시험용 가짜 Provider(`provider_id = "mock_stats"`). 오프라인 고정 데이터, 실제 기관 이름·주소 없음.

**실제 Provider 어댑터는 아직 없다** — 어떤 Provider 를 켤지는 운영자 결정 대기이고, 켜기 전에 이용 조건 7칸이 모두 확인돼야 한다.
새 어댑터를 만들 때는 docs/FACT_PATH.md 의 '어댑터 작성 체크리스트'를 따른다. HTML·RSS 본문 파서는 두지 않는다(시험이 지킨다).
"""
