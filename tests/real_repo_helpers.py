"""진짜 저장소 트리에 검증기 전체(`run_checks`)를 돌린 결과를 한 프로세스 안에서 한 번만 계산해 나눠 쓰는 시험 도우미(속도 전용 — 시험 수·단언은 그대로).

여러 시험 모듈이 '진짜 저장소에 검증기를 돌리면 오류가 0(·특정 규칙의 지적이 없음)' 을 각자 확인했고 한 번에 약 7초씩 걸렸다(모든 파일을 읽어 비밀 모양을 훑고 모든 파이썬 파일을 컴파일한다).
같은 인자·같은 트리·같은 검증기 상태에서는 결과가 같으므로 처음 한 번만 돌리고 나머지는 그 값을 쓴다.

- 임시 사본·변이 사본에는 쓰지 않는다. 그런 시험은 자기 폴더를 인자로 `vr.run_checks` 를 직접 부른다(변이가 잡히는지가 시험의 요점이라 나눠 쓰면 안 된다).
- 열쇠는 (폴더의 절대 경로, 기준 커밋, 검증기 상태, 트리 지문)이다. 검증기 상태는 검증기 모듈의 이름 공간(함수·상수·`yaml` 등)의 표시 글이라 시험이 `mock.patch` 로 검증기의 어느 한 군데를 바꿔 둔 동안에는
  다른 열쇠가 된다. 트리 지문은 검증기가 보는 파일 목록과 각 파일의 **내용 해시**다 — 크기·수정 시각만 보면 같은 크기의 제자리 수정이 같은 시각 눈금 안에 일어났을 때(또는 수정 시각을 되돌렸을 때)
  낡은 값을 주므로 내용을 읽는다(검증기가 읽지 않는 크기 한도 `vr.MAX_TEXT_BYTES` 를 넘는 파일만 크기·수정 시각). 비용은 파일 약 700개·약 20MB 에 한 번 읽어 sha1 — 이 PC 에서 CPU 0.2초, 진짜 CI 에서는 그 아래이고
  이 도우미가 아끼는 검증기 한 번(진짜 CI 약 7초)의 3% 안쪽이다.
- 기준 커밋을 주는 호출(0 으로만 된 값이 아닌 것)은 나누지 않고 매번 새로 계산한다 — 그때 검증기는 git 기록을 읽는데 그것은 트리 지문이 못 보는 입력이다.
- 돌려주는 것은 `Finding` 의 새 복사본 목록이다 — 받는 쪽이 목록이나 항목을 고쳐도 나눠 쓰는 값은 그대로다(다른 시험으로 새지 않는다).
순서에 기대지 않는다: 어느 시험이 먼저 불러도 같은 값이고, 한 모듈만 따로 돌려도 첫 호출이 직접 계산한다.
"""
import hashlib
import sys
from pathlib import Path

import _bootstrap

ROOT = _bootstrap.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import validate_repo as vr  # noqa: E402

_SHARED = {}


_SEP = bytes([0])


def tree_stamp(root):
    """검증기가 보는 트리의 지문(sha1 글자 40개): 파일 목록과 각 파일의 내용. 검증기가 읽지 않는 큰 파일(`vr.MAX_TEXT_BYTES` 초과)만 내용 대신 (크기, 수정 시각 ns).
    sha1 은 보안이 아니라 '바뀌었는가' 를 가리는 용도라 가장 싼 것을 쓴다(`usedforsecurity=False`)."""
    root = Path(root)
    digest = hashlib.sha1(usedforsecurity=False)
    for rel in vr.list_files(root):
        digest.update(rel.encode("utf-8", "replace") + _SEP)
        path = root / rel
        try:
            info = path.stat()
            if info.st_size <= vr.MAX_TEXT_BYTES:
                digest.update(path.read_bytes())
            else:
                digest.update(f"?{info.st_size}:{info.st_mtime_ns}".encode("ascii"))
        except OSError:
            digest.update(b"?-")
        digest.update(_SEP)
    return digest.hexdigest()


def validator_state():
    """검증기 모듈의 이름 공간 지문 — 함수·상수·`yaml` 을 시험이 `mock.patch` 로 바꿔 두었으면 달라진다(함수의 표시 글에는 주소가 있고 상수는 값이 글자로 나온다)."""
    digest = hashlib.sha256()
    for name, value in sorted(vars(vr).items()):
        if name.startswith("__"):
            continue
        try:
            shown = repr(value)
        except Exception:      # noqa: BLE001 — 표시 글을 못 만드는 객체는 종류와 주소로 구분한다
            shown = f"{type(value).__name__}@{id(value)}"
        digest.update(f"{name}={shown}\0".encode("utf-8", "replace"))
    return digest.hexdigest()


def run_checks_once(root=None, base=None):
    """`vr.run_checks(root, base)` 와 같은 결과(Finding 의 새 복사본 목록) — 같은 열쇠에서는 프로세스 안에서 한 번만 계산한다. root 를 안 주면 진짜 저장소다.
    기준 커밋(0 으로만 된 값이 아닌 것)을 주면 검증기가 git 기록을 읽어 트리 지문이 못 보는 입력이 생기므로 나누지 않고 매번 새로 계산한다."""
    root = Path(root or ROOT).resolve()
    if base and set(base) != {"0"}:
        return vr.run_checks(root, base)
    key = (str(root), base, validator_state(), tree_stamp(root))
    found = _SHARED.get(key)
    if found is None:
        found = tuple((f.level, f.check, f.message, f.path) for f in vr.run_checks(root, base))
        _SHARED[key] = found
    return [vr.Finding(*item) for item in found]
