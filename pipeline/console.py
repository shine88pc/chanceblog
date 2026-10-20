"""콘솔 출력 안전장치.

Windows 한국어 콘솔(cp949)은 '—'·이모지 같은 문자를 표현하지 못해, 그런 문자를 print 하면 CLI가 예외로 멈춘다
(CI의 Linux는 UTF-8이라 드러나지 않는다). CLI 진입점(main) 첫 줄에서 safe_output() 을 부르면
표현할 수 없는 문자만 '?'로 바뀌고 한글은 그대로 출력된다.
"""
import sys


def safe_output():
    """stdout/stderr 가 인코딩하지 못하는 문자를 예외 대신 '?'로 대체하도록 바꾼다(되돌릴 필요 없음)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # StringIO·캡처 스트림에는 없다
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):
            pass
