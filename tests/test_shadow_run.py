"""그림자 실행(SHADOW_RUN=1, pipeline/shadow_run.py + generator.py 의 연결)의 시험. 네트워크 없이 돈다.

못박는 것:
1. 인터페이스: 환경 변수(SHADOW_RUN·SHADOW_OUT·SHADOW_COUNT)와 출력 파일 형식(SHADOW_OUT/<번호>/<날짜>-KR-<시각>.md·-EN-.md·result.json, run.json — 측정 도구가 변환 없이 읽는 이름) — docs/QUALITY_GATE.md.
2. 정지 우회는 이 모드 안에서만(변수는 그대로): SHADOW_RUN 이 없으면 PIPELINE_PAUSE 에 그대로 멈춘다.
3. 읽기 전용이 코드로 강제된다: 쓰기 함수·subprocess 를 감시자로 바꿔 한 번도 안 불리는지, 임시 저장소 폴더의 바이트가 그대로인지, 쓰기를 시도하면 ShadowViolation 으로 빨강이 되는지,
   파일 쓰기(open·pathlib·os·shutil·tempfile 어느 길이든)를 파이썬 감사 훅이 Python 3.10·3.12 모두에서 막는지.
4. 오프라인 측정 도구(quality_shadow)에는 연결하지 않는다.
"""
import ast
import contextlib
import datetime
import hashlib
import importlib
import importlib.util
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _bootstrap
import generator as g
import quality_gate_helpers as h
from pipeline import registry, shadow_run
from test_generator_quality_gate import GenerationBase, OFF_BOTH, OFF_KO, candidate_item, model_json
from test_generator_slots import run_captured

ROOT = _bootstrap.ROOT
SHADOW_MODULE = ROOT / "pipeline" / "shadow_run.py"
# 생성기 시험 도구(GenerationBase)가 고정한 시각(2026-10-28 10:12:00 KST)에서 시도 번호마다 1초씩 뒤. 글 파일 이름 = 날짜-종류(KR·EN)-시각 6자리.
KO_NAMES = {"01": "2026-10-28-KR-101200.md", "02": "2026-10-28-KR-101201.md", "03": "2026-10-28-KR-101202.md"}
EN_NAMES = {number: name.replace("-KR-", "-EN-") for number, name in KO_NAMES.items()}


def snapshot(folder):
    """폴더 안 모든 파일의 {상대 경로: sha256}(폴더 이름도 포함)."""
    found = {}
    for path in sorted(Path(folder).rglob("*")):
        found[path.relative_to(folder).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "<dir>"
    return found


class BoomPopen:
    """프로세스를 만들면 시험이 실패하는 대역(subprocess.Popen 자리)."""

    def __init__(self, *args, **kwargs):
        raise AssertionError("프로세스를 만들었다")


class ConfigTest(unittest.TestCase):
    def test_count_defaults_and_limits(self):
        self.assertEqual(shadow_run.resolve_count({}), (3, []))
        self.assertEqual(shadow_run.resolve_count({"SHADOW_COUNT": ""}), (3, []))
        self.assertEqual(shadow_run.resolve_count({"SHADOW_COUNT": " 4 "}), (4, []))
        self.assertEqual(shadow_run.resolve_count({"SHADOW_COUNT": "5"}), (5, []))
        self.assertEqual(shadow_run.resolve_count({"SHADOW_COUNT": "1"}), (1, []))
        count, notes = shadow_run.resolve_count({"SHADOW_COUNT": "6"})
        self.assertEqual((count, len(notes)), (5, 1))
        for raw in ("0", "-2", "abc", "2.5", "3개"):
            with self.subTest(raw=raw):
                count, notes = shadow_run.resolve_count({"SHADOW_COUNT": raw})
                self.assertEqual((count, len(notes)), (3, 1))
        self.assertEqual(shadow_run.resolve_count(None), (3, []))

    def test_out_dir_must_be_an_absolute_empty_or_new_folder_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            repo = tmp / "repo"
            repo.mkdir()
            (tmp / "empty").mkdir()
            (tmp / "busy").mkdir()
            (tmp / "busy" / "old.txt").write_text("이전 결과", encoding="utf-8")
            (tmp / "file.txt").write_text("파일", encoding="utf-8")
            roots = [repo]
            self.assertEqual(shadow_run.resolve_out_dir({"SHADOW_OUT": str(tmp / "new" / "out")}, roots), (tmp / "new" / "out").resolve())
            self.assertEqual(shadow_run.resolve_out_dir({"SHADOW_OUT": str(tmp / "empty")}, roots), (tmp / "empty").resolve())
            bad = {"": "없음", "relative/out": "상대 경로", str(repo): "저장소 작업 폴더", str(repo / "sub" / "out"): "저장소 안", str(tmp): "저장소의 조상",
                   str(tmp / "busy"): "비어 있지 않은 폴더", str(tmp / "file.txt"): "파일", str(Path(tmp.anchor)): "디스크 맨 위", "C:/x\x00y": "널 글자"}
            for raw, why in bad.items():
                with self.subTest(why=why):
                    with self.assertRaises(shadow_run.ShadowConfigError):
                        shadow_run.resolve_out_dir({"SHADOW_OUT": raw}, roots)
            with self.assertRaises(shadow_run.ShadowConfigError):
                shadow_run.resolve_out_dir({}, roots)
            with self.assertRaises(shadow_run.ShadowConfigError):
                shadow_run.resolve_out_dir(None, roots)

    def test_a_dot_dot_path_that_lands_inside_the_repository_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            sneaky = str(Path(tmp) / "elsewhere" / ".." / "repo" / "out")
            with self.assertRaises(shadow_run.ShadowConfigError):
                shadow_run.resolve_out_dir({"SHADOW_OUT": sneaky}, [repo])

    def test_the_parent_of_the_repository_is_refused_because_it_is_a_parent_not_because_it_is_busy(self):
        """조상 폴더는 항상 비어 있지 않다(저장소가 들어 있다). 그래서 '비어 있지 않음'이 아니라 '저장소 작업 폴더 밖이어야 함' 으로 거절되는지 사유를 본다(조상 검사를 빼도 다른 사유로 거절되어 시험이 모르고 지나가지 않게)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            for raw in (tmp, str(Path(tmp).parent)):
                with self.subTest(raw=raw):
                    with self.assertRaisesRegex(shadow_run.ShadowConfigError, "저장소 작업 폴더 밖"):
                        shadow_run.resolve_out_dir({"SHADOW_OUT": raw}, [repo])

    def test_extended_prefix_and_unc_values_are_refused_on_every_platform(self):
        bs = chr(92)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            inner = str(repo / "out")
            for raw in (bs * 2 + "?" + bs + inner, bs * 2 + "." + bs + inner, bs * 2 + "?" + bs + "UNC" + bs + "server" + bs + "share", bs * 2 + "server" + bs + "share" + bs + "out",
                        "//?/" + inner.replace(bs, "/"), "//server/share/out"):
                with self.subTest(raw=raw):
                    with self.assertRaisesRegex(shadow_run.ShadowConfigError, "로컬 절대 경로"):
                        shadow_run.resolve_out_dir({"SHADOW_OUT": raw}, [repo])

    def test_a_sibling_folder_whose_name_starts_with_the_repository_name_is_not_inside_it(self):
        """'repo' 와 'repo-out' 은 다른 폴더다 — 이름 앞부분이 같다고 저장소 안으로 보고 거절하면 러너의 임시 폴더 이름이 우연히 겹칠 때 그림자 실행이 까닭 없이 멈춘다."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            for name in ("repo-out", "repo2", "repository"):
                with self.subTest(name=name):
                    out = Path(tmp) / name / "out"
                    self.assertEqual(shadow_run.resolve_out_dir({"SHADOW_OUT": str(out)}, [repo]), out.resolve())

    @staticmethod
    def make_link(link, target):
        """폴더 링크를 만든다(POSIX: 심볼릭 링크, Windows: 관리자 권한이 필요 없는 정션). 만들 수 없으면 False."""
        try:
            if os.name == "nt":
                done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
                return done.returncode == 0
            os.symlink(str(target), str(link), target_is_directory=True)
            return True
        except OSError:
            return False

    def test_a_link_into_the_repository_is_followed_and_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            link = Path(tmp) / "alias"
            if not self.make_link(link, repo):
                self.skipTest("이 환경에서는 폴더 링크를 만들 수 없다")
            for raw in (str(link / "out"), str(link)):
                with self.subTest(raw=raw):
                    with self.assertRaises(shadow_run.ShadowConfigError):
                        shadow_run.resolve_out_dir({"SHADOW_OUT": raw}, [repo])

    @unittest.skipUnless(os.name == "nt", "대소문자를 가리지 않는 파일 시스템(Windows)에서만")
    def test_upper_and_lower_case_spellings_of_the_repository_are_the_same_folder_on_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "Repo"
            repo.mkdir()
            for raw in (str(repo / "out").upper(), str(repo / "out").lower()):
                with self.subTest(raw=raw):
                    with self.assertRaises(shadow_run.ShadowConfigError):
                        shadow_run.resolve_out_dir({"SHADOW_OUT": raw}, [repo])

    @unittest.skipUnless(os.name == "nt", "8.3 짧은 이름은 Windows 에서만")
    def test_an_8_3_short_name_of_the_repository_is_resolved_to_the_real_folder_on_windows(self):
        with tempfile.TemporaryDirectory(prefix="long_repository_directory_name_") as tmp:
            repo = Path(tmp) / "repository_with_a_long_name"
            repo.mkdir()
            done = subprocess.run('for %I in ("' + str(repo) + '") do @echo %~sI', shell=True, capture_output=True, text=True)
            short = done.stdout.strip()
            if done.returncode != 0 or not short or short.lower() == str(repo).lower():
                self.skipTest("이 볼륨은 8.3 짧은 이름을 만들지 않는다")
            # 짧은 이름으로 쓴 SHADOW_OUT, 그리고 저장소 쪽을 짧은 이름으로 준 경우(반대 방향)도 같은 폴더로 본다
            for raw, roots in ((str(Path(short) / "out"), [repo]), (short, [repo]), (str(repo / "out"), [Path(short)])):
                with self.subTest(raw=raw, root=str(roots[0])):
                    with self.assertRaises(shadow_run.ShadowConfigError):
                        shadow_run.resolve_out_dir({"SHADOW_OUT": raw}, roots)

    def test_the_writer_only_writes_under_its_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "out"
            writer = shadow_run.ShadowWriter(root)
            written = writer.write("01/post_ko.md", "본문")
            self.assertEqual(written.read_text(encoding="utf-8"), "본문")
            self.assertEqual(sorted(p.name for p in (root / "01").iterdir()), ["post_ko.md"])      # 임시 파일이 남지 않는다
            writer.write_json("run.json", {"b": 1, "a": "가"})
            self.assertEqual((root / "run.json").read_text(encoding="utf-8"), '{\n  "a": "가",\n  "b": 1\n}\n')
            bad_paths = ["../x.txt", "01/../../x.txt", "/abs/x.txt", "", ".", "01/../x.txt", "../out/x.txt"]          # 뒤의 둘은 풀면 결과 폴더 안에 머무는 '..' — 그래도 거절한다(경로에 .. 가 있으면 늘 잘못된 경로)
            if os.name == "nt":
                bad_paths.append("C:/abs/x.txt")          # 윈도우에서는 드라이브 글자 경로가 절대 경로다(리눅스에서는 아래 따로 확인 — 거기서는 그냥 상대 경로다)
            for bad in bad_paths:
                with self.subTest(path=bad):
                    with self.assertRaises(shadow_run.ShadowViolation):
                        writer.write(bad, "x")
            if os.name != "nt":
                # 리눅스·맥에서 'C:/abs/x.txt' 는 콜론이 든 폴더 이름일 뿐인 상대 경로라 거절하지 않지만, 결과 폴더 밖으로 나가지도 못한다
                self.assertIn(writer.root, writer.target("C:/abs/x.txt").parents)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["out"])


class ReadOnlyGuardTest(unittest.TestCase):
    """read_only(): 쓰기 함수·git·gh 프로세스·SHADOW_OUT 밖에 쓰는 open 을 막고, 빠져나오면 모두 원래대로 돌려놓는다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.out = self.tmp / "out"
        self.out.mkdir()
        self.fake = SimpleNamespace(write_text_atomic=lambda *a: "real", write_history=lambda *a: "real", write_step_summary=lambda *a: "real",
                                    trigger_download=lambda *a: "real", fix_images=lambda *a: "real", pick_images=lambda *a, **k: "real")

    def test_the_generator_write_functions_raise_inside_and_are_restored_after(self):
        originals = {name: getattr(self.fake, name) for name in vars(self.fake)}
        with shadow_run.read_only(self.fake, self.out):
            for name in originals:
                with self.subTest(name=name):
                    with self.assertRaises(shadow_run.ShadowViolation):
                        getattr(self.fake, name)("x")
        for name, function in originals.items():
            self.assertIs(getattr(self.fake, name), function)

    def test_a_missing_name_is_skipped_not_invented(self):
        partial = SimpleNamespace(write_text_atomic=lambda *a: "real")
        with shadow_run.read_only(partial, self.out):
            self.assertFalse(hasattr(partial, "write_history"))
            with self.assertRaises(shadow_run.ShadowViolation):
                partial.write_text_atomic("x")

    def test_git_and_gh_processes_are_refused_but_other_commands_pass_through(self):
        with shadow_run.read_only(self.fake, self.out):
            for command in (["git", "status"], ["gh", "pr", "list"], ["C:/Program Files/Git/cmd/git.exe", "push"], "git add -A", ["/usr/bin/gh", "api"], ("git", "log")):
                with self.subTest(command=command):
                    with self.assertRaises(shadow_run.ShadowViolation):
                        subprocess.Popen(command)
            with self.assertRaises(shadow_run.ShadowViolation):
                subprocess.run(["git", "status"])
            with self.assertRaises(shadow_run.ShadowViolation):
                subprocess.check_output(["gh", "--version"])
            with self.assertRaises(shadow_run.ShadowViolation):
                os.system("git status")
            with self.assertRaises(shadow_run.ShadowViolation):
                os.popen("gh auth status")
            done = subprocess.run([sys.executable, "-c", "print('ok')"], capture_output=True, text=True)       # git·gh 가 아닌 명령은 막지 않는다
            self.assertEqual(done.stdout.strip(), "ok")

    def test_open_for_writing_outside_the_out_folder_is_refused_and_reading_and_inside_writing_are_allowed(self):
        outside = self.tmp / "outside.txt"
        outside.write_text("읽기용", encoding="utf-8")
        with shadow_run.read_only(self.fake, self.out):
            for mode in ("w", "a", "x", "r+", "wb", "ab"):
                with self.subTest(mode=mode):
                    with self.assertRaises(shadow_run.ShadowViolation):
                        open(self.tmp / f"never-{mode}.txt", mode)
            with self.assertRaises(shadow_run.ShadowViolation):
                outside.write_text("덮어쓰기", encoding="utf-8")
            with self.assertRaises(shadow_run.ShadowViolation):
                (self.tmp / "p.bin").write_bytes(b"x")
            with self.assertRaises(shadow_run.ShadowViolation):
                with open(self.out / ".." / "sneaky.txt", "w"):
                    pass
            self.assertEqual(outside.read_text(encoding="utf-8"), "읽기용")                    # 읽기는 막지 않는다
            with open(self.out / "ok.txt", "w", encoding="utf-8") as fh:                         # SHADOW_OUT 아래 쓰기는 된다
                fh.write("안")
            (self.out / "ok2.txt").write_text("안", encoding="utf-8")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["out", "outside.txt"])
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["ok.txt", "ok2.txt"])

    def test_everything_is_restored_even_when_the_body_raises(self):
        import builtins
        before = (subprocess.Popen, os.system, os.popen, builtins.open, io.open, shutil.copy2)
        with self.assertRaises(KeyError):
            with shadow_run.read_only(self.fake, self.out):
                self.assertIsNot(shutil.copy2, before[-1])                                  # 구간 안에서는 바꿔 끼워져 있고
                self.assertIsNot(subprocess.Popen, before[0])
                self.assertEqual(shadow_run._GUARDS, [shadow_run._normal(self.out)])      # 출력 폴더가 켜져 있다
                raise KeyError("본문에서 예외")
        self.assertEqual((subprocess.Popen, os.system, os.popen, builtins.open, io.open, shutil.copy2), before)
        self.assertEqual(shadow_run._GUARDS, [])
        (self.tmp / "after.txt").write_text("복구 뒤에는 쓸 수 있다", encoding="utf-8")


class WriteViolationFunctionTest(unittest.TestCase):
    """write_violation(): 파이썬 감사 이벤트 하나를 보고 '출력 폴더(SHADOW_OUT) 밖의 파일을 바꾸는 일인가'를 판정하는 순수 함수(파일을 건드리지 않는다)."""

    # 감시하는 이벤트마다 '경로가 p 일 때 이벤트 인자'를 만드는 식. shadow_run._PATH_EVENTS 에 이벤트를 더하면 여기에도 한 줄을 더해야 시험이 통과한다.
    EVENTS = {
        "open": lambda p: (p, "w", 33665),
        "os.mkdir": lambda p: (p, 511, -1),
        "os.remove": lambda p: (p, -1),
        "os.rmdir": lambda p: (p, -1),
        "os.truncate": lambda p: (p, 0),
        "os.chmod": lambda p: (p, 438, -1),
        "os.chown": lambda p: (p, 0, 0, -1),
        "os.utime": lambda p: (p, None, None, -1),
        "os.mkfifo": lambda p: (p, 438, -1),
        "os.mknod": lambda p: (p, 438, 0, -1),
        "os.setxattr": lambda p: (p, "user.x", b"v", 0),
        "os.removexattr": lambda p: (p, "user.x"),
        "os.rename": lambda p: (p, p, -1, -1),
        "os.symlink": lambda p: ("target", p, -1),
        "os.link": lambda p: (p, p, -1, -1),
        "sqlite3.connect": lambda p: (p,),
        "shutil.copyfile": lambda p: ("source", p),
        "shutil.copymode": lambda p: ("source", p),
        "shutil.copystat": lambda p: ("source", p),
        "shutil.copytree": lambda p: ("source", p),
        "shutil.move": lambda p: (p, p),
        "shutil.rmtree": lambda p: (p, None),
        "shutil.chown": lambda p: (p, "user", "group"),
        "shutil.make_archive": lambda p: (p, "zip", None, None),
        "shutil.unpack_archive": lambda p: ("archive.zip", p, None),
    }

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.out = self.base / "out"
        self.out.mkdir()
        self.root = shadow_run._normal(self.out)
        self.inside = str(self.out / "01" / "post_ko.md")
        self.outside = str(self.base / "repo" / "history.json")

    def verdict(self, event, *args):
        return shadow_run.write_violation(event, args, self.root)

    def test_every_watched_event_has_a_row_in_this_table(self):
        self.assertEqual(set(self.EVENTS), set(shadow_run._PATH_EVENTS) | {"open"})

    def test_every_watched_event_is_refused_outside_and_allowed_inside(self):
        for event, make in self.EVENTS.items():
            with self.subTest(event=event):
                self.assertIn(event, self.verdict(event, *make(self.outside)))
                self.assertIsNone(self.verdict(event, *make(self.inside)))

    def test_a_rename_or_move_is_refused_when_either_end_is_outside(self):
        for event in ("os.rename", "shutil.move"):
            with self.subTest(event=event):
                args = (lambda a, b: (a, b, -1, -1)) if event == "os.rename" else (lambda a, b: (a, b))
                self.assertIsNotNone(self.verdict(event, *args(self.inside, self.outside)))
                self.assertIsNotNone(self.verdict(event, *args(self.outside, self.inside)))
                self.assertIsNone(self.verdict(event, *args(self.inside, self.inside + ".x")))

    def test_a_symbolic_link_is_judged_by_the_path_it_creates_but_a_hard_link_by_both_ends(self):
        # 심볼릭 링크: 안에 만들어 두어도 열 때 실경로(밖)로 풀려 막히므로 만드는 경로만 본다.
        self.assertIsNone(self.verdict("os.symlink", self.outside, self.inside, -1))
        self.assertIsNotNone(self.verdict("os.symlink", self.inside, self.outside, -1))
        # 하드링크: 저장소 파일에 SHADOW_OUT 안의 이름을 붙이면 그 이름으로 연 파일이 저장소 파일을 바꾼다 — 원본이 밖이면 거절한다.
        self.assertIsNotNone(self.verdict("os.link", self.outside, self.inside, -1, -1))
        self.assertIsNotNone(self.verdict("os.link", self.inside, self.outside, -1, -1))
        self.assertIsNone(self.verdict("os.link", self.inside, self.inside + ".x", -1, -1))

    def test_every_directory_number_position_pairs_with_a_watched_path_position(self):
        for event, positions in shadow_run._DIR_FD_POSITIONS.items():
            with self.subTest(event=event):
                self.assertIn(event, shadow_run._PATH_EVENTS)
                self.assertEqual(len(positions), len(shadow_run._PATH_EVENTS[event]))

    def test_a_short_name_with_a_directory_number_is_judged_by_that_folder(self):
        # 리눅스의 shutil.rmtree 는 os.rmdir(이름, dir_fd=번호) 로 지운다 — 짧은 이름은 번호가 가리키는 폴더 기준이다
        cases = (("os.rmdir", ("03", 9)), ("os.remove", ("c.txt", 9)), ("os.mkdir", ("03", 511, 9)), ("os.rename", ("a", "b", 9, 9)), ("os.symlink", ("target", "link", 9)))
        for base, refused in ((str(self.out / "04"), False), (str(self.base / "repo"), True), (None, True)):
            with mock.patch.object(shadow_run, "_dir_fd_base", return_value=base):
                for event, args in cases:
                    with self.subTest(base=base, event=event):
                        self.assertEqual(self.verdict(event, *args) is not None, refused)
        with mock.patch.object(shadow_run, "_dir_fd_base", return_value=str(self.out / "04")):
            self.assertIsNotNone(self.verdict("os.rmdir", self.outside, 9))                 # 절대 경로는 번호와 상관없이 그 경로로 판정한다
            self.assertIsNone(self.verdict("os.rmdir", self.inside, 9))
            for no_number in (-1, None, True):                                                 # 번호가 없는 호출은 지금까지처럼 현재 폴더 기준이다(시험 프로세스의 현재 폴더는 결과 폴더 밖)
                with self.subTest(no_number=no_number):
                    self.assertIsNotNone(self.verdict("os.rmdir", "03", no_number))

    def test_a_directory_number_that_cannot_be_resolved_is_refused(self):
        self.assertIsNotNone(self.verdict("os.rmdir", "03", 987654))                      # 열려 있지 않은 번호 — 폴더를 풀 수 없으면 막는다(fail closed)

    @unittest.skipUnless(os.path.isdir("/proc/self/fd"), "리눅스의 /proc/self/fd 가 있을 때만")
    def test_a_real_directory_number_on_linux_resolves_to_its_folder(self):
        inside_dir, elsewhere = self.out / "04", self.base / "repo"
        inside_dir.mkdir()
        elsewhere.mkdir()
        inside_fd, outside_fd = os.open(str(inside_dir), os.O_RDONLY), os.open(str(elsewhere), os.O_RDONLY)
        self.addCleanup(os.close, inside_fd)
        self.addCleanup(os.close, outside_fd)
        self.assertIsNone(self.verdict("os.rmdir", "03", inside_fd))
        self.assertIsNone(self.verdict("os.remove", "c.txt", inside_fd))
        self.assertIsNotNone(self.verdict("os.rmdir", "03", outside_fd))
        self.assertIsNotNone(self.verdict("os.remove", "c.txt", outside_fd))

    def test_reading_is_never_refused(self):
        platform_read = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0) | getattr(os, "O_CLOEXEC", 0)          # 윈도우 32896(O_BINARY|O_NOINHERIT), 리눅스 O_CLOEXEC — 깃발 숫자는 운영체제마다 달라 숫자로 못박지 않는다
        for args in ((self.outside, "r", platform_read), (self.outside, "r", 0), (self.outside, None, os.O_RDONLY), (self.outside, None, 0)):
            with self.subTest(args=args):
                self.assertIsNone(self.verdict("open", *args))

    def test_write_intent_is_read_from_the_mode_or_from_the_flags(self):
        for mode in ("w", "a", "x", "r+"):
            with self.subTest(mode=mode):
                self.assertIsNotNone(self.verdict("open", self.outside, mode, 0))                      # flags 가 0 이어도 모드로 안다
        for flags in (os.O_WRONLY, os.O_RDWR, os.O_APPEND, os.O_CREAT, os.O_TRUNC, os.O_EXCL, os.O_WRONLY | os.O_CREAT):
            with self.subTest(flags=flags):
                self.assertIsNotNone(self.verdict("open", self.outside, None, flags))                  # 모드가 없는 os.open 은 flags 로 안다

    @unittest.skipUnless(hasattr(os, "O_TEMPORARY"), "O_TEMPORARY(닫을 때 삭제)는 Windows 에만 있다")
    def test_a_delete_on_close_open_is_a_write_even_when_it_only_reads(self):
        self.assertIsNotNone(self.verdict("open", self.outside, None, os.O_RDONLY | os.O_TEMPORARY))
        self.assertIsNone(self.verdict("open", self.inside, None, os.O_RDONLY | os.O_TEMPORARY))      # SHADOW_OUT 안의 파일은 자기 결과라 괜찮다
        self.assertIn(os.O_TEMPORARY, [flag for flag in (os.O_TEMPORARY,) if shadow_run._WRITE_FLAGS & flag])

    def test_open_file_numbers_and_non_paths_are_not_checked(self):
        self.assertIsNone(self.verdict("open", 7, "w", 1))
        self.assertIsNone(self.verdict("os.truncate", 7, 0))
        self.assertIsNone(self.verdict("os.utime", None, None, None, -1))

    def test_only_the_platforms_null_device_is_allowed(self):
        names = {os.devnull, os.devnull.upper()}
        for name in names:
            with self.subTest(name=name):
                self.assertIsNone(self.verdict("open", name, None, os.O_RDWR))
        if os.name != "nt":          # Linux 에서 상대 경로 'nul' 은 일반 파일이다 — 널 장치가 아니라 저장소 쪽 파일이므로 쓰기를 막는다
            self.assertIsNotNone(self.verdict("open", "nul", None, os.O_RDWR))
            self.assertIsNotNone(self.verdict("open", "NUL", "w", 1))

    def test_the_bytecode_cache_exception_is_only_what_python_does_when_it_first_imports_a_module(self):
        cache = self.base / "repo" / "__pycache__"
        tmp_pyc, pyc = str(cache / "m.cpython-312.pyc.140234"), str(cache / "m.cpython-312.pyc")
        create = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        self.assertIsNone(self.verdict("os.mkdir", str(cache), 511, -1))                      # __pycache__ 폴더를 새로 만들기
        self.assertIsNone(self.verdict("open", tmp_pyc, None, create))                        # 임시 .pyc.숫자 파일 쓰기
        self.assertIsNone(self.verdict("open", pyc, None, create))
        self.assertIsNone(self.verdict("os.rename", tmp_pyc, pyc, -1, -1))                    # 임시 파일을 .pyc 로 바꾸기
        self.assertIsNone(self.verdict("os.remove", tmp_pyc, -1))                             # 쓰다 만 임시 파일 정리
        # 좁힌 것: 폴더 삭제·진짜 .pyc 삭제·다른 변경·다른 이름·캐시 밖의 .pyc 는 막는다
        self.assertIsNotNone(self.verdict("os.rmdir", str(cache), -1))
        self.assertIsNotNone(self.verdict("os.remove", pyc, -1))
        self.assertIsNotNone(self.verdict("os.chmod", pyc, 438, -1))
        self.assertIsNotNone(self.verdict("os.truncate", pyc, 0))
        self.assertIsNotNone(self.verdict("os.mkdir", str(self.base / "repo" / "__pycache__x"), 511, -1))
        self.assertIsNotNone(self.verdict("open", str(cache / "notes.txt"), "w", 1))
        self.assertIsNotNone(self.verdict("open", str(self.base / "repo" / "module.pyc"), "w", 1))
        self.assertIsNotNone(self.verdict("os.rename", pyc, str(self.base / "repo" / "other.txt"), -1, -1))
        self.assertIsNotNone(self.verdict("os.rename", str(self.base / "repo" / "history.json"), pyc, -1, -1))

    def test_an_in_memory_sqlite_database_is_not_a_file(self):
        for name in (":memory:", ""):
            self.assertIsNone(self.verdict("sqlite3.connect", name))
        self.assertIsNotNone(self.verdict("sqlite3.connect", self.outside))
        self.assertIsNotNone(self.verdict("sqlite3.connect", "file:evil.db?mode=rwc"))
        self.assertIsNotNone(self.verdict("open", ":memory:", "w", 1))          # 예외는 sqlite3.connect 이벤트에서만이다

    def test_dot_dot_tricks_and_look_alike_folders_do_not_get_through(self):
        self.assertIsNotNone(self.verdict("open", str(self.out / ".." / "evil.txt"), "w", 1))
        self.assertIsNone(self.verdict("open", str(self.out / "01" / ".." / "02" / "x.txt"), "w", 1))
        self.assertIsNotNone(self.verdict("open", str(self.base / "out-other" / "x.txt"), "w", 1))   # 앞부분 글자만 같은 다른 폴더
        self.assertIsNotNone(self.verdict("open", "relative-name.txt", "w", 1))                          # 상대 경로는 지금 작업 폴더 기준(저장소 쪽)이다

    def test_unreadable_paths_and_missing_arguments_are_refused_not_skipped(self):
        self.assertIsNotNone(self.verdict("os.mkdir", "bad\x00path", 511, -1))
        self.assertIsNotNone(self.verdict("open", object(), "w", 1))
        self.assertIsNotNone(self.verdict("os.mkdir"))

    def test_other_events_are_not_judged(self):
        for event in ("socket.connect", "import", "os.listdir", "os.scandir", "sys.addaudithook", "subprocess.Popen", "os.system"):
            with self.subTest(event=event):
                self.assertIsNone(self.verdict(event, self.outside))          # 파일 판정(write_violation)은 프로세스 이벤트를 보지 않는다 — 프로세스는 process_violation


class ProcessViolationFunctionTest(unittest.TestCase):
    """process_violation(): 프로세스를 만드는 이벤트가 git·gh 를 부르는 일인가(프로그램 이름이 첫 낱말이 아니어도, 순수 함수)."""

    EVENTS = {
        "subprocess.Popen": lambda cmd: (None, cmd, None, None),
        "os.system": lambda cmd: (cmd,),
        "os.exec": lambda cmd: (cmd if isinstance(cmd, str) else cmd[0], cmd, None),
        "os.posix_spawn": lambda cmd: (cmd if isinstance(cmd, str) else cmd[0], cmd, None),
        "os.spawn": lambda cmd: (0, cmd if isinstance(cmd, str) else cmd[0], cmd, None),
    }

    def test_every_watched_process_event_refuses_git_and_gh_and_passes_other_programs(self):
        self.assertEqual(set(self.EVENTS), set(shadow_run._PROCESS_EVENTS))
        for event, make in self.EVENTS.items():
            for bad in (["git", "status"], ["gh", "pr", "list"], ["cmd", "/c", "git", "log"], "git add -A", "echo x && git log", ["C:/Program Files/Git/cmd/git.exe", "push"]):
                with self.subTest(event=event, bad=bad):
                    self.assertIn("git·gh", shadow_run.process_violation(event, make(bad)) or "")
            for good in (["python", "-c", "print(1)"], "echo hello", ["C:/Program Files/Git/usr/bin/bash.exe", "-c", "echo hi"], ["python", "tools/digit.py", "--git-dir=x"]):
                with self.subTest(event=event, good=good):
                    self.assertIsNone(shadow_run.process_violation(event, make(good)))

    def test_names_joined_to_the_next_word_by_ampersand_or_pipe_without_spaces_are_still_found(self):
        for event, make in self.EVENTS.items():
            for bad in ("x&&git log", "echo hi|git commit", "true||gh pr list", "a&git status", "ls|gh api", "(git status)", "x;git log"):
                with self.subTest(event=event, bad=bad):
                    self.assertIn("git·gh", shadow_run.process_violation(event, make(bad)) or "")
            for good in ("digit&&echo ok", "echo a|cat", "legit|tee out", "a&b|c"):          # git·gh 가 낱말로 없으면 통과(digit·legit 안의 git 은 다른 낱말)
                with self.subTest(event=event, good=good):
                    self.assertIsNone(shadow_run.process_violation(event, make(good)))
        self.assertEqual(shadow_run._command_tokens("x&&git|gh;y"), ["x", "git", "gh", "y"])

    def test_other_events_and_unreadable_arguments(self):
        self.assertIsNone(shadow_run.process_violation("open", ("git", "w", 1)))
        self.assertIsNone(shadow_run.process_violation("socket.connect", ("git",)))
        self.assertIsNotNone(shadow_run.process_violation("os.system", ()))          # 인자가 모자라면 막는다(fail closed)
        self.assertIsNone(shadow_run.process_violation("subprocess.Popen", (None, None, None, None)))          # 명령이 없으면 막을 이름도 없다


class WriteBlockInsideTheGuardTest(unittest.TestCase):
    """read_only() 안에서는 open 뿐 아니라 pathlib·os·shutil·tempfile 어느 길로도 SHADOW_OUT 밖을 바꿀 수 없다(파이썬 감사 훅 — 3.10 의 pathlib 이 io.open 을 미리 쥐고 있어
    함수를 바꿔 끼우는 방식이 놓친 곳까지). 구간이 끝나면 다시 쓸 수 있다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.out = self.tmp / "out"
        self.out.mkdir()
        self.existing = self.tmp / "existing.txt"
        self.existing.write_text("원본", encoding="utf-8")
        self.folder = self.tmp / "folder"
        self.folder.mkdir()
        (self.folder / "f.txt").write_text("안", encoding="utf-8")
        self.pycache = self.tmp / "__pycache__"
        self.pycache.mkdir()
        self.fake = SimpleNamespace()

    def attempts(self):
        t = self.tmp
        attempts = {
            "open w": lambda: open(t / "n1.txt", "w"),
            "open a": lambda: open(t / "n1.txt", "a"),
            "io.open wb": lambda: io.open(t / "n2.bin", "wb"),
            "Path.open w": lambda: (t / "n3.txt").open("w"),
            "Path.write_text": lambda: (t / "n4.txt").write_text("x"),
            "Path.write_bytes": lambda: (t / "n5.bin").write_bytes(b"x"),
            "Path.touch": lambda: (t / "n6.txt").touch(),
            "Path.mkdir": lambda: (t / "d1").mkdir(),
            "os.mkdir": lambda: os.mkdir(t / "d2"),
            "os.makedirs": lambda: os.makedirs(t / "d3" / "d4"),
            "os.open": lambda: os.open(t / "n7.bin", os.O_WRONLY | os.O_CREAT),
            "os.remove": lambda: os.remove(self.existing),
            "Path.unlink": lambda: self.existing.unlink(),
            "os.rename": lambda: os.rename(self.existing, t / "renamed.txt"),
            "os.replace": lambda: os.replace(self.existing, t / "replaced.txt"),
            "Path.rename": lambda: self.existing.rename(t / "renamed2.txt"),
            "os.rmdir": lambda: os.rmdir(self.folder),
            "os.truncate": lambda: os.truncate(self.existing, 0),
            "os.chmod": lambda: os.chmod(self.existing, 0o666),
            "os.utime": lambda: os.utime(self.existing, None),
            "os.symlink": lambda: os.symlink("existing.txt", t / "link"),
            "os.link": lambda: os.link(self.existing, t / "hard"),
            "os.link into out": lambda: os.link(self.existing, self.out / "hard-in"),          # 하드링크로 저장소 파일을 SHADOW_OUT 안으로 들여오는 길(들여온 뒤 쓰면 저장소 파일이 바뀐다)
            "os.rmdir __pycache__": lambda: os.rmdir(self.pycache),
            "shutil.rmtree __pycache__": lambda: shutil.rmtree(self.pycache),
            "sqlite3.connect": lambda: sqlite3.connect(str(t / "x.db")),
            "shutil.copyfile": lambda: shutil.copyfile(self.existing, t / "copy1.txt"),
            "shutil.copy2": lambda: shutil.copy2(self.existing, t / "copy2.txt"),
            "shutil.copytree": lambda: shutil.copytree(self.folder, t / "tree"),
            "shutil.move": lambda: shutil.move(str(self.existing), str(t / "moved.txt")),
            "shutil.rmtree": lambda: shutil.rmtree(self.folder),
            "tempfile.mkstemp": lambda: tempfile.mkstemp(dir=str(t)),
            "tempfile.mkdtemp": lambda: tempfile.mkdtemp(dir=str(t)),
        }
        if hasattr(os, "O_TEMPORARY"):          # Windows: 읽기로 열어도 닫을 때 파일이 지워진다(감사 이벤트 깃발에 쓰기 표시가 없어 따로 본다)
            attempts["os.open O_TEMPORARY"] = lambda: os.open(self.existing, os.O_RDONLY | os.O_TEMPORARY)
        return attempts

    def test_every_way_of_changing_something_outside_is_refused_and_nothing_changes(self):
        before = snapshot(self.tmp)
        with shadow_run.read_only(self.fake, self.out):
            for name, attempt in self.attempts().items():
                with self.subTest(name=name):
                    with self.assertRaises(shadow_run.ShadowViolation):
                        attempt()
        self.assertEqual(snapshot(self.tmp), before)
        self.assertEqual(self.existing.read_text(encoding="utf-8"), "원본")

    def test_the_same_changes_inside_the_out_folder_work_and_reading_outside_works(self):
        with shadow_run.read_only(self.fake, self.out):
            (self.out / "01").mkdir()
            (self.out / "01" / "a.txt").write_text("안", encoding="utf-8")
            with open(self.out / "01" / "b.txt", "w", encoding="utf-8") as fh:
                fh.write("안")
            os.makedirs(self.out / "02" / "03")
            shutil.copyfile(self.out / "01" / "a.txt", self.out / "02" / "c.txt")
            shutil.copy2(self.out / "01" / "a.txt", self.out / "02" / "c2.txt")
            (self.out / "02" / "c2.txt").unlink()
            os.replace(self.out / "02" / "c.txt", self.out / "02" / "d.txt")
            (self.out / "02" / "d.txt").unlink()
            shutil.copytree(self.out / "02", self.out / "04")
            shutil.rmtree(self.out / "04")
            handle, name = tempfile.mkstemp(dir=str(self.out))
            os.close(handle)
            os.remove(name)
            self.assertEqual(self.existing.read_text(encoding="utf-8"), "원본")                      # 밖의 파일을 읽는 것은 된다
            self.assertEqual(os.listdir(self.folder), ["f.txt"])
            shutil.copyfile(self.existing, self.out / "copy-of-existing.txt")                       # 밖에서 읽어 안에 쓰는 것도 된다
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["01", "02", "copy-of-existing.txt"])

    def test_nothing_is_blocked_after_the_guard_ends_and_the_hook_stays_inert(self):
        with shadow_run.read_only(self.fake, self.out):
            pass
        self.assertEqual(shadow_run._GUARDS, [])
        (self.tmp / "after.txt").write_text("구간 밖에서는 쓴다", encoding="utf-8")
        os.makedirs(self.tmp / "after-dir")
        with self.assertRaises(KeyError):                                                            # 예외로 빠져나와도 같다
            with shadow_run.read_only(self.fake, self.out):
                raise KeyError("본문에서 예외")
        self.assertEqual(shadow_run._GUARDS, [])
        (self.tmp / "after2.txt").write_text("예외 뒤에도 쓴다", encoding="utf-8")
        self.assertEqual(len(shadow_run._HOOK), 1)                                                   # 훅은 한 번만 달린다
        shutil.copy2(self.existing, self.tmp / "after-copy.txt")                                     # 바꿔 끼운 copy2 도 구간이 끝나면 원래대로다
        self.assertEqual((self.tmp / "after-copy.txt").read_text(encoding="utf-8"), "원본")

    def test_a_nested_guard_judges_by_the_innermost_out_folder(self):
        inner = self.tmp / "inner"
        inner.mkdir()
        with shadow_run.read_only(self.fake, self.out):
            with shadow_run.read_only(self.fake, inner):
                (inner / "ok.txt").write_text("x", encoding="utf-8")
                with self.assertRaises(shadow_run.ShadowViolation):
                    (self.out / "no.txt").write_text("x", encoding="utf-8")
            (self.out / "yes.txt").write_text("x", encoding="utf-8")                                 # 안쪽 구간이 끝나면 바깥 구간의 폴더로 돌아온다
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["yes.txt"])

    def test_python_may_still_write_its_own_bytecode_cache_while_importing(self):
        (self.tmp / "shadow_probe_module.py").write_text("VALUE = 7\n", encoding="utf-8")
        sys.path.insert(0, str(self.tmp))
        self.addCleanup(sys.path.remove, str(self.tmp))
        self.addCleanup(sys.modules.pop, "shadow_probe_module", None)
        importlib.invalidate_caches()
        with mock.patch.object(sys, "dont_write_bytecode", False), shadow_run.read_only(self.fake, self.out):
            module = importlib.import_module("shadow_probe_module")
        self.assertEqual(module.VALUE, 7)
        self.assertTrue((self.tmp / "__pycache__").is_dir())                                         # 캐시는 만들어졌다(막지 않는다)

    def test_git_and_gh_are_refused_by_name_anywhere_in_the_command(self):
        commands = (["cmd", "/c", "git", "status"], "echo x && git log", ["powershell", "-Command", "git status"], ["sh", "-c", "git status"], ["env", "GIT_X=1", "git", "log"],
                    "cmd /c gh pr list", ["C:/Program Files/Git/cmd/git.exe", "push"], ["python", "-c", "import subprocess; subprocess.run(['git', 'status'])"])
        with shadow_run.read_only(self.fake, self.out):
            for command in commands:
                with self.subTest(command=command):
                    with self.assertRaises(shadow_run.ShadowViolation):
                        subprocess.Popen(command)
            with self.assertRaises(shadow_run.ShadowViolation):
                os.system("cmd /c git status")
            with self.assertRaises(shadow_run.ShadowViolation):
                os.popen("echo x | git log")

    def test_a_popen_taken_before_the_guard_is_still_stopped_by_the_hook(self):
        """`from subprocess import Popen` 으로 미리 쥔 클래스는 바꿔 끼운 Popen 을 거치지 않는다 — 감사 이벤트(subprocess.Popen)에서 막는다."""
        held_before = subprocess.Popen
        with shadow_run.read_only(self.fake, self.out):
            with self.assertRaises(shadow_run.ShadowViolation):
                held_before(["git", "--version"])
            with self.assertRaises(shadow_run.ShadowViolation):
                held_before(["cmd", "/c", "git", "--version"])
            if os.name == "nt":
                with self.assertRaises(shadow_run.ShadowViolation):
                    os.spawnv(os.P_WAIT, "git", ["git", "--version"])
            else:
                # 리눅스·맥의 os.spawnv 는 파이썬 코드가 fork 한 자식에서 execv 를 부른다 — 감사 훅의 예외는 자식 안에서 일어나 자식이 127 로 끝나고 부모에는 예외가 오지 않는다(git 은 실행되지 않는다)
                self.assertNotEqual(os.spawnv(os.P_WAIT, "git", ["git", "--version"]), 0)
                self.assertEqual(os.spawnv(os.P_WAIT, sys.executable, [sys.executable, "-c", "pass"]), 0)          # 대조: git·gh 가 아닌 프로그램은 같은 구간에서 정상으로 돈다

    def test_a_child_process_that_discards_its_input_and_errors_still_starts(self):
        with shadow_run.read_only(self.fake, self.out):
            done = subprocess.run([sys.executable, "-c", "print('ok')"], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        self.assertEqual(done.stdout.strip(), "ok")


class ShadowRunBase(GenerationBase):
    """g.main() 을 SHADOW_RUN=1 로 돌린다. 저장소 자리(작업 폴더)는 임시 폴더, 결과 폴더는 그 밖의 다른 임시 폴더."""

    def setUp(self):
        super().setUp()
        out_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(out_tmp.cleanup)
        self.out_root = Path(out_tmp.name) / "shadow-out"
        self.patch_value("EVENT_NAME", "")

    def lane_items(self, per_lane=3):
        """분야마다 서로 다른 후보 항목(제목·주소가 모두 다르다) {분야: [항목]}."""
        items, n = {}, 0
        for lane in g.EDITORIAL_LANES:
            items[lane] = []
            for _ in range(per_lane):
                items[lane].append(candidate_item(n))
                n += 1
        return items

    @staticmethod
    def every(items_by_lane):
        return [item for items in items_by_lane.values() for item in items]

    def run_shadow(self, items_by_lane=None, responses=None, raw=None, env=None, settings=OFF_BOTH, gemini_model="gemini-test-model", after_call=None, pair=True):
        """responses: 후보 제목 → 모델 JSON(dict), raw: 후보 제목 → 모델이 보낸 글(JSON 이 아닌 것). 빠진 후보는 통과하는 기본 응답."""
        items_by_lane = self.lane_items() if items_by_lane is None else items_by_lane
        table = {item["title"]: json.dumps(model_json(item, pair=pair), ensure_ascii=False) for item in self.every(items_by_lane)}
        table.update({title: json.dumps(value, ensure_ascii=False) for title, value in (responses or {}).items()})
        table.update(raw or {})
        prompts = []

        def fake_gemini(prompt):
            prompts.append(prompt)
            key = next((title for title in table if title in prompt), None)
            if key is None:
                raise AssertionError("가짜 Gemini 가 모르는 후보")
            g.CALL_LOG.records.append(SimpleNamespace(outcome="ok", served_model=gemini_model, model="요청 모델"))
            if after_call:
                after_call()
            return SimpleNamespace(text=table[key])

        def fake_fetch(editorial_lane=None, stats=None, deadline=None, clock=None):
            found = list(items_by_lane.get(editorial_lane, []))
            if stats is not None:
                stats.setdefault("sources", []).append({"name": "x", "fetched": len(found), "kept": len(found), "drops": {}})
            return found

        environment = {"SHADOW_RUN": "1", "SHADOW_OUT": str(self.out_root)}
        environment.update(env or {})
        patches = [mock.patch.dict(os.environ, environment), mock.patch.object(registry, "chance_settings", return_value=settings), mock.patch.object(g, "call_gemini_with_fallback", fake_gemini),
                   mock.patch.object(g, "fetch_news_items", fake_fetch), mock.patch.object(g, "get_client", side_effect=AssertionError("가짜 Gemini 만 쓴다")),
                   mock.patch.object(g.CALL_LOG, "records", [])]
        for patcher in patches:
            patcher.start()
        try:
            value, out = run_captured(g.main)
        finally:
            for patcher in reversed(patches):
                patcher.stop()
        return SimpleNamespace(value=value, out=out, prompts=prompts)

    def results(self):
        return {path.parent.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(self.out_root.glob("*/result.json"))}

    def bad_numbers(self, items_by_lane):
        """모든 후보의 국문 본문에 근거에 없는 숫자를 넣은 응답(어떤 후보가 시도돼도 Gate 에 걸린다)."""
        return {item["title"]: model_json(item, ko=h.ko_body(link=item["link"]).replace("1,250,000가구", "9,999,999가구")) for item in self.every(items_by_lane)}


class InterfaceTest(ShadowRunBase):
    def test_the_pause_variable_is_skipped_only_in_this_mode_and_stays_untouched(self):
        with mock.patch.dict(os.environ, {"PIPELINE_PAUSE": "true", "SHADOW_RUN": ""}):
            self.assertTrue(g._pause_on())
            self.assertFalse(g.shadow_run_on())
        with mock.patch.dict(os.environ, {"PIPELINE_PAUSE": "true", "SHADOW_RUN": "1"}):
            self.assertFalse(g._pause_on())
            self.assertTrue(g.shadow_run_on())
            self.assertEqual(os.environ["PIPELINE_PAUSE"], "true")

    ON_VALUES = ("1", "true", "True", "TRUE", "yes", "YES", "on", "ON", "enabled", "Enabled", " 1 ", "\ttrue\n")
    OFF_VALUES = ("", "0", "false", "False", "no", "NO", "off", "OFF", "disabled", "Disabled", " ", " off ", "\n")
    UNRECOGNIZED = ("2", "garbage", "enable", "y", "n", "t", "f", "truee", "on1", "maybe", "1 1", "yes please", "-1", "0.0", "none", "null")

    def test_the_flag_values_are_read_the_same_way_in_every_case_and_space(self):
        for raw in self.ON_VALUES:
            with self.subTest(on=raw), mock.patch.dict(os.environ, {"SHADOW_RUN": raw}):
                self.assertTrue(g.shadow_run_on())
                self.assertFalse(g.shadow_run_unrecognized())
        for raw in self.OFF_VALUES:
            with self.subTest(off=raw), mock.patch.dict(os.environ, {"SHADOW_RUN": raw}):
                self.assertFalse(g.shadow_run_on())
                self.assertFalse(g.shadow_run_unrecognized())
        for raw in self.UNRECOGNIZED:
            with self.subTest(unrecognized=raw), mock.patch.dict(os.environ, {"SHADOW_RUN": raw}):
                self.assertFalse(g.shadow_run_on())
                self.assertTrue(g.shadow_run_unrecognized())
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop("SHADOW_RUN", None)
            self.assertFalse(g.shadow_run_on())
            self.assertFalse(g.shadow_run_unrecognized())

    def test_the_on_values_include_every_value_the_pause_variable_reads_as_on(self):
        self.assertTrue({"1", "true", "yes", "on"} <= g.SHADOW_RUN_ON_VALUES)
        self.assertEqual(g.SHADOW_RUN_ON_VALUES & g.SHADOW_RUN_OFF_VALUES, frozenset())
        self.assertEqual(g.SHADOW_RUN_ON_VALUES, frozenset({"1", "true", "yes", "on", "enabled"}))
        self.assertEqual(g.SHADOW_RUN_OFF_VALUES, frozenset({"", "0", "false", "no", "off", "disabled"}))

    def test_an_unrecognized_value_is_refused_with_exit_code_two_before_anything_runs_even_when_paused(self):
        for pause in ("", "true"):
            for raw in ("garbage", "2", "enable"):
                with self.subTest(pause=pause, raw=raw):
                    buffer = io.StringIO()
                    env = {"SHADOW_RUN": raw, "PIPELINE_PAUSE": pause, "SHADOW_OUT": str(self.out_root)}
                    with mock.patch.dict(os.environ, env), mock.patch.object(g, "run_shadow", side_effect=AssertionError("그림자 경로를 탔다")), \
                            mock.patch.object(g, "generate_blog_posts", side_effect=AssertionError("일반 실행을 탔다")), \
                            mock.patch.object(g, "write_step_summary", side_effect=AssertionError("요약을 썼다")), contextlib.redirect_stdout(buffer):
                        with self.assertRaises(SystemExit) as caught:
                            g.main()
                    self.assertEqual(caught.exception.code, 2)
                    self.assertIn("::error::SHADOW_RUN 값을 알 수 없어 실행하지 않습니다", buffer.getvalue())
        self.assertFalse(self.out_root.exists())

    def test_every_off_value_leaves_a_paused_repository_paused_and_never_runs_the_shadow_path(self):
        for raw in ("", "0", "false", "no", "off", "disabled", " OFF "):
            with self.subTest(raw=raw):
                with mock.patch.dict(os.environ, {"PIPELINE_PAUSE": "on", "SHADOW_RUN": raw, "SHADOW_OUT": str(self.out_root)}), \
                        mock.patch.object(g, "run_shadow", side_effect=AssertionError("그림자 경로를 탔다")):
                    value, out = run_captured(g.main)
                self.assertIn("[SKIP] code=PAUSED", out)
        self.assertFalse(self.out_root.exists())

    def test_every_on_value_runs_the_shadow_path_even_when_the_pause_variable_is_on(self):
        for raw in ("1", "true", "yes", "on", "enabled", "ON"):
            with self.subTest(raw=raw):
                shutil.rmtree(self.out_root, ignore_errors=True)
                result = self.run_shadow(env={"PIPELINE_PAUSE": "on", "SHADOW_RUN": raw, "SHADOW_COUNT": "1"})
                self.assertNotIn("[SKIP] code=PAUSED", result.out)
                self.assertIn("SHADOW_DONE attempts=1", result.out)

    def test_without_the_flag_a_paused_run_still_stops_and_calls_nothing(self):
        calls = []
        with mock.patch.dict(os.environ, {"PIPELINE_PAUSE": "true", "SHADOW_RUN": "", "SHADOW_OUT": str(self.out_root)}), \
                mock.patch.object(g, "call_gemini_with_fallback", lambda prompt: calls.append(prompt)), mock.patch.object(g, "run_shadow", side_effect=AssertionError("그림자 경로를 탔다")), \
                mock.patch.object(g, "fetch_news_items", side_effect=AssertionError("수집을 했다")):
            value, out = run_captured(g.main)
        self.assertIn("[SKIP] code=PAUSED", out)
        self.assertEqual(calls, [])
        self.assertFalse(self.out_root.exists())

    def test_with_the_flag_a_paused_repository_still_produces_the_shadow_files(self):
        result = self.run_shadow(env={"PIPELINE_PAUSE": "true"})
        self.assertNotIn("[SKIP] code=PAUSED", result.out)
        self.assertIn("PIPELINE_PAUSE 가 켜져 있지만 그림자 실행은 읽기 전용이라 건너뛰지 않습니다", result.out)
        self.assertIn("SHADOW_DONE attempts=3", result.out)
        self.assertEqual(sorted(p.name for p in self.out_root.iterdir()), ["01", "02", "03", "run.json"])

    def test_the_pause_notice_is_printed_for_every_value_the_pause_variable_reads_as_on_and_only_then(self):
        notice = "PIPELINE_PAUSE 가 켜져 있지만 그림자 실행은 읽기 전용이라 건너뛰지 않습니다"
        for pause, expected in (("1", True), ("true", True), ("yes", True), ("on", True), (" ON ", True), ("", False), ("0", False), ("off", False), ("no", False)):
            with self.subTest(pause=pause):
                shutil.rmtree(self.out_root, ignore_errors=True)
                result = self.run_shadow(env={"PIPELINE_PAUSE": pause, "SHADOW_COUNT": "1"})
                self.assertEqual(notice in result.out, expected)

    def test_the_output_format_is_what_the_docs_define(self):
        self.run_shadow()
        for number in ("01", "02", "03"):
            self.assertEqual(sorted(p.name for p in (self.out_root / number).iterdir()), [EN_NAMES[number], KO_NAMES[number], "result.json"])
        result = self.results()["01"]
        self.assertEqual(sorted(result), ["attempt", "files", "gate", "generated_at", "hold_codes", "hold_reasons", "lane", "languages", "model", "outcome", "passed",
                                          "published", "schema", "source_domain", "source_name", "source_text_chars", "source_url", "title_en", "title_ko", "validation"])
        self.assertIs(result["passed"], True)
        self.assertEqual((result["schema"], result["attempt"], result["outcome"]), (1, 1, "PASSED"))
        self.assertEqual(result["hold_reasons"], [])
        self.assertEqual(result["source_text_chars"], len(h.SUMMARY))
        self.assertEqual(result["model"], "gemini-test-model")
        self.assertIn(result["lane"], g.EDITORIAL_LANES)
        self.assertTrue(result["source_url"].startswith(h.LINK))
        self.assertEqual(result["languages"], ["ko", "en"])
        self.assertEqual(result["files"], {"ko": "2026-10-28-KR-101200.md", "en": "2026-10-28-EN-101200.md"})      # 이름 모양을 못박는다(측정 도구가 읽는 이름)
        self.assertEqual(result["validation"], {"ok": True, "reason": ""})
        self.assertEqual(result["gate"]["input"], "validated")
        self.assertEqual(result["generated_at"], "2026-10-28T10:12:00+09:00")
        run = json.loads((self.out_root / "run.json").read_text(encoding="utf-8"))
        self.assertEqual((run["requested"], run["attempts"], run["passed"], run["outcome"]), (3, 3, 3, "COMPLETED"))
        self.assertEqual(len(run["attempts_summary"]), 3)

    def test_the_post_files_are_the_finished_text_without_the_placeholder_photo(self):
        self.run_shadow()
        ko = (self.out_root / "01" / KO_NAMES["01"]).read_text(encoding="utf-8")
        en = (self.out_root / "01" / EN_NAMES["01"]).read_text(encoding="utf-8")
        for text in (ko, en):
            self.assertTrue(text.startswith("---\nlayout: post\n"))
            self.assertIn("source_url: ", text)
            self.assertIn("description: ", text)
            self.assertNotIn("example.invalid", text)
            self.assertNotIn("![Thumbnail]", text)
            self.assertTrue(text.endswith("\n"))
        self.assertIn("lang: ko", ko)
        self.assertIn("lang: en", en)

    def test_a_held_candidate_has_its_codes_and_still_gets_its_post_files(self):
        items = self.lane_items()
        self.run_shadow(items, self.bad_numbers(items))
        self.assertEqual(len(self.results()), 3)
        for folder, result in self.results().items():
            with self.subTest(folder=folder):
                self.assertEqual((result["passed"], result["outcome"]), (False, "HELD"))
                self.assertIn("QG1-NUMBER", result["hold_codes"])
                self.assertTrue(result["hold_reasons"][0].startswith("QG1-NUMBER 국문:"), result["hold_reasons"])
                self.assertEqual(result["validation"]["ok"], True)
                self.assertTrue((self.out_root / folder / KO_NAMES[folder]).exists())
                self.assertTrue((self.out_root / folder / EN_NAMES[folder]).exists())
        run = json.loads((self.out_root / "run.json").read_text(encoding="utf-8"))
        self.assertEqual((run["passed"], run["held_or_rejected"]), (0, 3))

    def test_a_candidate_that_fails_the_existing_validation_is_recorded_with_its_raw_text(self):
        items = self.lane_items()
        thin = {item["title"]: {**model_json(item), "kr_content": h.front("t", "ko") + "짧은 본문 " + f"[원문]({item['link']})"} for item in self.every(items)}
        self.run_shadow(items, thin)
        for folder, result in self.results().items():
            with self.subTest(folder=folder):
                self.assertEqual((result["passed"], result["outcome"]), (False, "REJECTED_BODY"))
                self.assertFalse(result["validation"]["ok"])
                self.assertIn("최소 편집 분량", result["validation"]["reason"])
                self.assertTrue(result["hold_reasons"][0].startswith("REJECT-BODY:"))
                self.assertEqual(result["gate"]["input"], "raw")
                self.assertIn("QG3-LENGTH", result["hold_codes"])        # 검증에 실패한 글에도 Gate 를 돌려 본다
                self.assertIn("짧은 본문", (self.out_root / folder / KO_NAMES[folder]).read_text(encoding="utf-8"))

    def test_a_model_skip_is_recorded_without_post_files(self):
        items = self.lane_items()
        skips = {item["title"]: {"skip": True, "reason": "이미 다룬 소재"} for item in self.every(items)}
        self.run_shadow(items, skips)
        for folder, result in self.results().items():
            self.assertEqual((result["passed"], result["outcome"]), (False, "REJECTED_SKIP"))
            self.assertTrue(result["hold_reasons"][0].startswith("REJECT-SKIP:"))
            self.assertEqual(sorted(p.name for p in (self.out_root / folder).iterdir()), ["result.json"])
            self.assertEqual(result["files"], {})

    def test_an_answer_that_is_not_json_is_recorded_as_a_format_rejection(self):
        items = self.lane_items()
        self.run_shadow(items, raw={item["title"]: "이것은 JSON 이 아닙니다" for item in self.every(items)})
        for folder, result in self.results().items():
            self.assertEqual((result["passed"], result["outcome"]), (False, "REJECTED_FORMAT"))
            self.assertTrue(result["hold_reasons"][0].startswith("REJECT-FORMAT:"))
            self.assertEqual(sorted(p.name for p in (self.out_root / folder).iterdir()), ["result.json"])

    def test_a_generated_title_that_is_close_to_an_existing_one_is_recorded_as_similar(self):
        self.set_history([{"date": "2026-10-20", "topic": "예전 글", "kr_title": h.KO_TITLE, "source_url": "https://other.example/a"}])
        self.run_shadow(env={"SHADOW_COUNT": "1"})
        result = self.results()["01"]
        self.assertEqual((result["passed"], result["outcome"]), (False, "REJECTED_SIMILAR"))
        self.assertTrue(result["hold_reasons"][0].startswith("REJECT-SIMILAR:"))

    def test_a_missing_nested_out_folder_is_created_before_the_read_only_part_starts(self):
        self.out_root = self.out_root / "deeper" / "still"            # 두 단계가 없다 — 읽기 전용 구간 안에서는 출력 폴더의 위 폴더를 만들 수 없다
        result = self.run_shadow()
        self.assertIn("SHADOW_DONE attempts=3", result.out)
        self.assertTrue((self.out_root / "run.json").is_file())

    def test_the_count_variable_limits_the_attempts(self):
        self.run_shadow(env={"SHADOW_COUNT": "1"})
        self.assertEqual(sorted(self.results()), ["01"])
        self.assertEqual(json.loads((self.out_root / "run.json").read_text(encoding="utf-8"))["requested"], 1)

    def test_five_attempts_span_lanes_and_more_than_five_is_cut_to_five(self):
        result = self.run_shadow(env={"SHADOW_COUNT": "9"})
        self.assertEqual(sorted(self.results()), ["01", "02", "03", "04", "05"])
        self.assertIn("::notice::SHADOW_COUNT 가 상한을 넘어 5건으로 줄입니다", result.out)
        self.assertEqual(len(result.prompts), 5)
        self.assertGreaterEqual(len({r["lane"] for r in self.results().values()}), 2)

    def test_the_same_article_in_two_lanes_is_evaluated_once(self):
        shared = candidate_item(7)
        result = self.run_shadow({lane: [shared] for lane in g.EDITORIAL_LANES}, env={"SHADOW_COUNT": "5"})
        self.assertEqual(sorted(self.results()), ["01"])
        self.assertEqual(len(result.prompts), 1)

    def test_the_gate_is_applied_even_when_the_registry_gate_is_off(self):
        items = self.lane_items()
        self.run_shadow(items, self.bad_numbers(items), settings=OFF_BOTH)
        self.assertTrue(all("QG1-NUMBER" in r["hold_codes"] for r in self.results().values()))

    def test_korean_only_setting_makes_no_english_file_and_asks_the_model_for_korean_only(self):
        result = self.run_shadow(settings=OFF_KO, pair=False, env={"SHADOW_COUNT": "2"})
        for number in ("01", "02"):
            self.assertEqual(sorted(p.name for p in (self.out_root / number).iterdir()), [KO_NAMES[number], "result.json"])
        self.assertEqual(self.results()["01"]["languages"], ["ko"])
        self.assertEqual(self.results()["01"]["files"], {"ko": KO_NAMES["01"]})
        self.assertTrue(self.results()["01"]["passed"], self.results()["01"]["hold_reasons"])
        self.assertTrue(all("en_content" not in prompt and "한국어로 작성하세요" in prompt for prompt in result.prompts))

    def test_no_candidate_at_all_is_a_warning_with_a_run_file_not_a_failure(self):
        result = self.run_shadow({lane: [] for lane in g.EDITORIAL_LANES})
        run = json.loads((self.out_root / "run.json").read_text(encoding="utf-8"))
        self.assertEqual((run["attempts"], run["outcome"]), (0, "NO_CANDIDATES"))
        self.assertIn("::warning::그림자 실행: 평가할 후보가 없었습니다", result.out)
        self.assertIsNone(result.value)

    def test_a_missing_or_bad_out_folder_stops_with_exit_code_two_before_any_model_call(self):
        for env in ({"SHADOW_OUT": ""}, {"SHADOW_OUT": "relative/out"}, {"SHADOW_OUT": str(self.root)}, {"SHADOW_OUT": str(ROOT / "shadow-out")}):
            with self.subTest(env=env):
                calls = []
                with mock.patch.dict(os.environ, {"SHADOW_RUN": "1", **env}), mock.patch.object(g, "call_gemini_with_fallback", lambda prompt: calls.append(prompt)):
                    value, out = run_captured(g.main)
                self.assertIsInstance(value, SystemExit)
                self.assertEqual(value.code, 2)
                self.assertIn("::error::그림자 실행 설정 오류", out)
                self.assertEqual(calls, [])
        self.assertFalse((ROOT / "shadow-out").exists())

    def test_a_missing_model_key_stops_like_the_normal_run(self):
        self.patch_value("STUB_GEMINI", True)
        with mock.patch.dict(os.environ, {"SHADOW_RUN": "1", "SHADOW_OUT": str(self.out_root)}):
            with self.assertRaises(RuntimeError) as caught:
                run_captured(g.main)
        self.assertIn("GEMINI_API_KEY", str(caught.exception))
        self.assertFalse(self.out_root.exists())

    def test_the_stub_model_works_for_a_dry_practice_of_the_interface(self):
        self.patch_value("STUB_GEMINI", True)
        self.patch_value("DRY_RUN", True)
        items = self.lane_items()
        with mock.patch.dict(os.environ, {"SHADOW_RUN": "1", "SHADOW_OUT": str(self.out_root), "SHADOW_COUNT": "1"}), mock.patch.object(registry, "chance_settings", return_value=OFF_BOTH), \
                mock.patch.object(g, "fetch_news_items", lambda editorial_lane=None, stats=None, deadline=None, clock=None: list(items.get(editorial_lane, []))):
            value, out = run_captured(g.main)
        self.assertEqual(self.results()["01"]["model"], "stub")
        self.assertIn("SHADOW_DONE attempts=1", out)

    def test_an_all_models_failed_error_is_an_infrastructure_failure_that_propagates(self):
        items = self.lane_items()

        def failing(prompt):
            raise RuntimeError("모든 Gemini 모델 호출 실패")

        with mock.patch.dict(os.environ, {"SHADOW_RUN": "1", "SHADOW_OUT": str(self.out_root)}), mock.patch.object(registry, "chance_settings", return_value=OFF_BOTH), \
                mock.patch.object(g, "call_gemini_with_fallback", failing), mock.patch.object(g, "fetch_news_items", lambda editorial_lane=None, stats=None, deadline=None, clock=None: list(items.get(editorial_lane, []))):
            with self.assertRaises(RuntimeError):
                run_captured(g.main)
        self.assertFalse((self.out_root / "run.json").exists())

    def test_text_from_the_model_in_the_result_file_is_one_line(self):
        items = self.lane_items()
        evil = {item["title"]: {**model_json(item), "kr_title": "::error::제목\n##[group] 줄바꿈"} for item in self.every(items)}
        self.run_shadow(items, evil)
        for result in self.results().values():
            self.assertNotIn("\n", result["title_ko"])
            self.assertNotIn("::error::", result["title_ko"])
            self.assertNotIn("##[", result["title_ko"])


class MeasuringToolInterfaceTest(ShadowRunBase):
    """그림자 결과(SHADOW_OUT)를 오프라인 측정 도구가 변환 없이 읽는가. 측정 도구는 `*.md` 를 재귀로 읽고 파일 이름 `YYYY-MM-DD-KR|EN-HHMMSS` 의 (날짜, 시각) 으로 국문·영문 쌍을 맞춘다
    (이름 규칙을 여기에 복사해 계약으로 못박는다 — 도구가 같은 저장소에 있으면 아래 마지막 시험이 진짜 도구로 한 번 더 확인한다)."""

    FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(KR|EN|AI)(?:-(\d{6}))?$")

    def pairs_of(self, root):
        groups = {}
        for path in sorted(Path(root).rglob("*.md")):
            found = self.FILENAME.match(path.stem)
            self.assertIsNotNone(found, f"측정 도구가 읽을 수 없는 이름: {path.name}")
            date, kind, key = found.groups()
            self.assertTrue(key, "쌍 키(시각 6자리)가 없다")
            groups.setdefault((date, key), {}).setdefault(kind, []).append(path)
        return groups

    def test_every_post_file_name_has_the_date_kind_and_key_the_tool_pairs_by_and_each_attempt_is_one_pair(self):
        self.run_shadow()
        groups = self.pairs_of(self.out_root)
        self.assertEqual(len(groups), 3)                                          # 시도 셋 = 쌍 셋(키가 겹치지 않는다)
        for (date, key), pair in groups.items():
            self.assertEqual({kind: len(paths) for kind, paths in pair.items()}, {"KR": 1, "EN": 1})
            self.assertEqual(pair["KR"][0].parent, pair["EN"][0].parent)          # 한 쌍은 같은 시도 폴더에 있다
        self.assertEqual(sorted(key for _date, key in groups), ["101200", "101201", "101202"])

    def test_a_korean_only_run_has_only_kr_names_and_still_unique_keys(self):
        self.run_shadow(settings=OFF_KO, pair=False, env={"SHADOW_COUNT": "3"})
        groups = self.pairs_of(self.out_root)
        self.assertEqual(len(groups), 3)
        self.assertTrue(all(set(pair) == {"KR"} for pair in groups.values()))

    def test_the_stamp_of_each_attempt_is_one_second_after_the_previous_one_and_the_names_follow_the_generators_pattern(self):
        now = datetime.datetime(2026, 11, 9, 23, 59, 59, tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
        names = [shadow_run.post_filename("ko", shadow_run.attempt_stamp(now, n)) for n in (1, 2, 3)]
        self.assertEqual(names, ["2026-11-09-KR-235959.md", "2026-11-10-KR-000000.md", "2026-11-10-KR-000001.md"])      # 자정을 넘겨도 이름은 겹치지 않는다
        self.assertEqual(shadow_run.post_filename("en", now), "2026-11-09-EN-235959.md")
        with self.assertRaises(KeyError):
            shadow_run.post_filename("ja", now)
        for name in names:
            self.assertIsNotNone(self.FILENAME.match(name[:-3]))

    def test_the_real_measuring_tool_pairs_the_output_when_it_is_in_this_tree(self):
        if importlib.util.find_spec("pipeline." + "quality_shadow") is None:
            self.skipTest("측정 도구가 이 저장소에 아직 없다(별도 변경으로 들어온다) — 합친 트리에서 돈다")
        tool = importlib.import_module("pipeline." + "quality_shadow")
        self.run_shadow()
        posts, problems = tool.collect_posts(self.out_root)
        pairs, unpaired = tool.pair_posts(posts)
        self.assertEqual((len(posts), len(pairs), len(unpaired), problems), (6, 3, 0, []))
        self.assertTrue(all(post.lang in ("ko", "en") for post in posts))


class ReadOnlyGuaranteeTest(ShadowRunBase):
    def test_no_write_function_is_called_and_the_repository_folder_stays_byte_identical(self):
        (self.root / "history.json").write_bytes(json.dumps([{"date": "2026-10-20", "topic": "오래된 글", "kr_title": "오래된 제목", "source_url": "https://other.example/a"}], ensure_ascii=False).encode("utf-8"))
        (self.root / "_posts").mkdir(exist_ok=True)
        (self.root / "_posts" / "old.md").write_bytes("---\ntitle: 옛 글\n---\n본문\n".encode("utf-8"))
        before = snapshot(self.root)
        summary = self.root.parent / "summary-should-stay-empty.md"
        spies = {name: mock.Mock(name=name) for name in ("write_text_atomic", "write_history", "write_step_summary", "trigger_download", "fix_images", "pick_images")}
        with mock.patch.multiple(g, **spies), mock.patch.object(subprocess, "Popen", BoomPopen), mock.patch.object(subprocess, "run", side_effect=AssertionError("프로세스를 만들었다")), \
                mock.patch.object(os, "system", side_effect=AssertionError("셸을 불렀다")), mock.patch.object(os, "popen", side_effect=AssertionError("셸을 불렀다")), \
                mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}):
            result = self.run_shadow(env={"PIPELINE_PAUSE": "true"})
        self.assertIn("SHADOW_DONE attempts=3", result.out)
        for name, spy in spies.items():
            self.assertEqual(spy.call_count, 0, name)
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(summary.exists())

    def test_only_the_out_folder_gets_files_and_only_the_documented_ones(self):
        self.run_shadow()
        names = sorted(p.relative_to(self.out_root).as_posix() for p in self.out_root.rglob("*") if p.is_file())
        expected = ["run.json"] + [f"{n}/{f}" for n in ("01", "02", "03") for f in (EN_NAMES[n], KO_NAMES[n], "result.json")]
        self.assertEqual(names, sorted(expected))

    def test_an_attempt_to_write_inside_the_run_ends_in_a_violation_not_in_a_write(self):
        stray = self.root / "stray.txt"
        with self.assertRaises(shadow_run.ShadowViolation):
            self.run_shadow(after_call=lambda: g.write_text_atomic(stray, "몰래 쓰기"))
        self.assertFalse(stray.exists())

    def test_an_attempt_to_open_a_file_for_writing_inside_the_run_ends_in_a_violation(self):
        stray = self.root / "stray2.txt"

        def sneaky():
            with open(stray, "w", encoding="utf-8") as fh:
                fh.write("몰래")

        with self.assertRaises(shadow_run.ShadowViolation):
            self.run_shadow(after_call=sneaky)
        self.assertFalse(stray.exists())

    def test_an_attempt_to_run_git_inside_the_run_ends_in_a_violation(self):
        with mock.patch.object(subprocess, "Popen", BoomPopen):          # 가드가 없어도 실제 프로세스는 만들어지지 않게 한다
            with self.assertRaises(shadow_run.ShadowViolation):
                self.run_shadow(after_call=lambda: subprocess.run(["git", "status"]))

    def test_the_generator_write_functions_also_refuse_by_themselves_in_this_mode(self):
        """read_only 가 없어도(다른 경로에서 불려도) SHADOW_RUN=1 이면 DRY_RUN 과 같은 쓰기 차단이 걸려 있다."""
        target = self.root / "x.txt"
        url = "https://images.unsplash.com/photo-shadow-guard"
        with mock.patch.dict(os.environ, {"SHADOW_RUN": "1"}):
            value, out = run_captured(g.write_text_atomic, target, "내용")
            self.assertFalse(target.exists())
            self.assertIn("[SHADOW_RUN] 쓰기 생략", out)
            run_captured(g.write_history, [{"a": 1}])
            self.assertFalse((self.root / "history.json").exists())
            summary = self.root / "summary.md"
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}):
                g.write_step_summary("요약")
            self.assertFalse(summary.exists())
            g._download_locations[g.image_key(url)] = "https://api.unsplash.com/photos/abcdefgh/download"
            self.addCleanup(g._download_locations.pop, g.image_key(url), None)
            self.patch_value("STUB_UNSPLASH", False)
            with mock.patch.object(g.urllib.request, "urlopen") as urlopen:
                self.real_trigger_download(url)
                self.assertEqual(urlopen.call_count, 0)
        with mock.patch.dict(os.environ, {"SHADOW_RUN": ""}):
            g.write_text_atomic(target, "평소에는 쓴다")
            self.assertEqual(target.read_text(encoding="utf-8"), "평소에는 쓴다")
            with mock.patch.object(g.urllib.request, "urlopen") as urlopen:          # 같은 조건에서 SHADOW_RUN 만 없으면 요청이 나간다 — 막은 것은 이 변수다
                self.real_trigger_download(url)
                self.assertEqual(urlopen.call_count, 1)

    def test_the_shadow_module_has_no_write_or_process_calls_of_its_own(self):
        text = SHADOW_MODULE.read_text(encoding="utf-8")
        for banned in ("draft_flow", "from pipeline import drafts", "import drafts", "write_text_atomic(", "write_history(", "msvcrt", "ctypes", "quality_shadow"):
            self.assertNotIn(banned, text, banned)
        tree = ast.parse(text)
        calls = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"]
        self.assertEqual(calls, [])          # subprocess.<함수>(...) 호출이 하나도 없다(Popen 은 git·gh 를 막는 것으로 바꿔 끼울 뿐이다)


class NotConnectedToTheShadowMeasuringToolTest(unittest.TestCase):
    def test_no_runtime_file_names_the_offline_measuring_tool(self):
        for name in ("generator.py", "pipeline/shadow_run.py", "pipeline/quality_gate.py", "pipeline/run.py", "pipeline/registry.py"):
            self.assertNotIn("quality_shadow", (ROOT / name).read_text(encoding="utf-8"), name)
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            if path.name != "chance-shadow.yml":          # 그림자 워크플로(다른 담당이 만든다)의 두 번째 단계만 별도 프로세스로 부를 수 있다
                self.assertNotIn("quality_shadow", path.read_text(encoding="utf-8"), path.name)


class DefaultUnchangedTest(GenerationBase):
    """SHADOW_RUN 이 없으면 이전과 같다: main() 은 일반 실행으로 가고 그림자 경로·쓰기 차단은 걸리지 않는다."""

    def test_a_normal_scheduled_run_writes_the_post_as_before_and_never_touches_the_shadow_path(self):
        item = candidate_item()
        self.patch_value("EVENT_NAME", "schedule")
        self.patch_value("SLOT_HOURS", [9, 18])
        self.patch_value("draft_flow_on", lambda: False)
        with mock.patch.dict(os.environ, {"SHADOW_RUN": "", "PIPELINE_PAUSE": ""}), mock.patch.object(g, "run_shadow", side_effect=AssertionError("그림자 경로를 탔다")):
            result = self.run_generation(OFF_BOTH, [item], {item["title"]: model_json(item)}, call=g.main)
        self.assertIsNone(result.error)
        self.assertEqual(len([path for path, _ in result.written if path.endswith(".md")]), 2)
        self.assertEqual(len(self.history()), 1)

    def test_the_write_functions_are_not_blocked_without_the_flag(self):
        target = self.root / "plain.txt"
        with mock.patch.dict(os.environ, {"SHADOW_RUN": ""}):
            g.write_text_atomic(target, "쓴다")
        self.assertEqual(target.read_text(encoding="utf-8"), "쓴다")


if __name__ == "__main__":
    unittest.main()
