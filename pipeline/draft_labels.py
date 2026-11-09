"""초안 라벨의 이름·색·설명 — 한 곳(R2-5, 2026-11-09).

초안 1건 = GitHub 이슈 1개 또는 PR 1개. 라벨 `초안`(발행 대기)과 `채널:<채널 라벨>`(어느 채널의 글인가)을 붙이고, 쓰지 않을 초안은 라벨 `폐기` 또는 닫기로 알린다.
이 라벨을 만드는 코드가 세 곳이었다 — Chance 승인 PR(pipeline/drafts.py), 티스토리·네이버 초안 이슈(pipeline/publishers/issue_package.py), 확인 필요 모음의 라벨 만들기(pipeline/inbox.py).
같은 이름의 라벨에 색·설명이 서로 달랐고(예: `초안` 이 d4c5f9·fbca04·c2e0c6) 라벨은 먼저 만든 쪽의 것이 남아서, 어떤 모습이 될지는 어느 쪽이 먼저 돌았는지에 달려 있었다.
이제 셋이 모두 이 표만 읽는다. 순수 상수와 함수뿐이다(입출력 없음, 다른 pipeline 모듈을 가져오지 않는다 — 어느 모듈에서 가져와도 순환하지 않게).

값을 바꾸면 docs/OPS_INBOX.md §3-1 의 라벨 표와 docs/ARCHITECTURE.md §4-4 의 PR 표를 같이 고친다(시험이 문서와 이 값을 대조한다). 이미 저장소에 있는 라벨은 이름만 보고
색·설명을 바꾸지 않으므로(운영자가 손으로 바꾼 색을 되돌리지 않으려는 것) 이 표는 **새로 만드는 라벨**에만 쓰인다.
"""

DRAFT_LABEL = "초안"
DISCARD_LABEL = "폐기"
CHANNEL_LABEL_PREFIX = "채널:"

LABEL_NAME_MAX = 50              # GitHub 라벨 이름 길이 한도
DESCRIPTION_MAX = 100            # GitHub 라벨 설명 길이 한도

DRAFT_COLOR = "c2e0c6"           # 연한 초록 — 발행을 기다린다
DISCARD_COLOR = "cfd3d7"         # 회색 — 쓰지 않는다
CHANNEL_COLOR = "bfdadc"         # 연한 하늘색 — 채널 표시(모든 채널이 같은 색이다)

# (이름, 색, 설명) — 초안·폐기. 설명은 운영자가 휴대폰에서 라벨을 고를 때 읽는 쉬운 말이다.
# `초안` 라벨은 초안 이슈(티스토리·네이버: 본문을 복사해 직접 발행한 뒤 이슈를 닫는다)와 초안 PR(Chance: 병합하면 공개)이 함께 쓰므로, 어느 쪽에도 틀리지 않게
# 두 경우의 '끝나는 방법'을 나란히 적는다(R2 수정 P3 — 예전 문장 '읽고 승인하면 공개됩니다'는 이슈 초안에는 맞지 않았다: 이슈는 승인해도 공개되지 않는다).
BASE_LABELS = (
    (DRAFT_LABEL, DRAFT_COLOR, "AI가 만든 초안으로 발행을 기다리는 글 — PR 은 병합하고, 이슈는 직접 발행하면 끝납니다"),
    (DISCARD_LABEL, DISCARD_COLOR, "쓰지 않기로 한 초안 — 붙이면 발행 대기 목록에서 빠집니다"),
)
CHANNEL_DESCRIPTION = "초안이 속한 채널: {label}"


def channel_label_name(label):
    """채널 라벨(레지스트리 channel.label) → 초안에 붙이는 GitHub 라벨 이름(예: `채널:티스토리`)."""
    return f"{CHANNEL_LABEL_PREFIX}{label}"


def channel_spec(label):
    """채널 라벨 하나의 (라벨 이름, 색, 설명). 설명은 GitHub 한도(100자) 안으로 자른다."""
    return channel_label_name(label), CHANNEL_COLOR, CHANNEL_DESCRIPTION.format(label=label)[:DESCRIPTION_MAX]


def style_of(name):
    """라벨 이름 → (색, 설명). 초안·폐기와 `채널:<라벨>` 만 안다 — 모르는 이름이면 None(호출한 쪽이 정한 대체 값을 쓴다)."""
    for base_name, color, description in BASE_LABELS:
        if name == base_name:
            return color, description
    if isinstance(name, str) and name.startswith(CHANNEL_LABEL_PREFIX) and name[len(CHANNEL_LABEL_PREFIX):].strip():
        _name, color, description = channel_spec(name[len(CHANNEL_LABEL_PREFIX):])
        return color, description
    return None


def specs_for(channel_labels):
    """초안 라벨 한 벌 [(이름, 색, 설명)] — `초안`과 주어진 채널 라벨마다 `채널:<라벨>`(순서 그대로, 중복은 한 번). 폐기는 운영자가 붙이는 라벨이라 넣지 않는다."""
    out, seen = [BASE_LABELS[0]], {BASE_LABELS[0][0].casefold()}
    for label in channel_labels:
        spec = channel_spec(label)
        if spec[0].casefold() not in seen:
            seen.add(spec[0].casefold())
            out.append(spec)
    return tuple(out)
