"""허용 경로 접두어 경계: 확장자가 있는 파일 경로는 완전 일치만 받는다(BP-S1-12, 결함 D-420). 네트워크 없이 돈다.

배경: path_matches 는 접두어가 `/` 로 끝나지 않으면 `경로 == 접두어` 또는 `경로가 접두어 + "/" 로 시작`을 받았다 — 허용 경로 `/products/noaa-scales.json` 에 `/products/noaa-scales.json/anything` 이 통과했다.
어댑터가 요청 경로를 제품 파일 하나로 못박고(생성 주소는 어댑터가 만든다) NOAA 쪽에서는 404 일 뿐이라 실제 요청으로 이어지지는 않았지만, 파일 이름 뒤에 경로가 이어질 수는 없으므로 닫는다.
기존 허용 경로는 전부 그대로 통과한다(레지스트리의 모든 허용 경로 대조).
"""
import datetime
import re
import unittest

import _bootstrap  # noqa: F401
from pipeline import egress
from pipeline import source_registry as sr

TODAY = datetime.date(2026, 11, 23)
NOAA_HOST = "services.swpc.noaa.gov"


class PathMatchesFilePrefixTest(unittest.TestCase):
    def test_a_file_path_prefix_accepts_only_the_exact_path(self):
        for prefix in ("/products/noaa-scales.json", "/en/rss.xml", "/n1/rss/dai-quo/0-eng.atom", "/openapi/index/index.jsp", "/brd/m_580/view.do", "/press/2026/10/20261018-1_j.html"):
            with self.subTest(prefix=prefix):
                self.assertTrue(sr.path_matches(prefix, (prefix,)))
                for tail in ("/anything", "/", "/x/y", "/..", "x", ".evil", "2"):
                    self.assertFalse(sr.path_matches(prefix + tail, (prefix,)), prefix + tail)

    def test_the_audit_probe_case(self):
        self.assertFalse(sr.path_matches("/products/noaa-scales.json/anything", ("/products/noaa-scales.json",)))
        self.assertTrue(sr.path_matches("/products/noaa-scales.json", ("/products/noaa-scales.json",)))

    def test_directory_and_extensionless_prefixes_keep_the_old_boundary_rule(self):
        cases = [("/feed", ("/feed",), True), ("/feed/x", ("/feed",), True), ("/feedback", ("/feed",), False), ("/api/x", ("/api/",), True), ("/api", ("/api/",), True),
                 ("/node/2/rss_en", ("/node/2/rss_en",), True), ("/node/2/rss_en/x", ("/node/2/rss_en",), True), ("/noaa-scales-explanation/x", ("/noaa-scales-explanation",), True),
                 ("/v1.0/items", ("/v1.0",), True),                                   # 글자로 시작하지 않는 '확장자' 는 버전 조각이다 — 파일이 아니다
                 ("/data/v2/x", ("/data/v2",), True), ("/", (), True), ("/anything", (), True)]
        for path, prefixes, expected in cases:
            with self.subTest(path=path, prefixes=prefixes):
                self.assertEqual(sr.path_matches(path, prefixes), expected)

    def test_a_mixed_prefix_list_still_matches_when_any_prefix_does(self):
        prefixes = ("/products/noaa-scales.json", "/news/", "/feed")
        self.assertTrue(sr.path_matches("/products/noaa-scales.json", prefixes))
        self.assertFalse(sr.path_matches("/products/noaa-scales.json/anything", prefixes))
        self.assertTrue(sr.path_matches("/news/a", prefixes))
        self.assertTrue(sr.path_matches("/feed/a", prefixes))


class FileExtensionLimitTest(unittest.TestCase):
    """2차 검증 필수-2(변이 Q25): '파일 경로' 판정의 확장자 길이 한도를 현재 값으로 못박는다 — 점 뒤가 글자로 시작하는 영문·숫자 1–8자는 파일이고 9자부터는 파일이 아니다.
    왜 8인가(근거): 8 은 이 일을 할 때 정한 휴리스틱 한도다 — 흔한 파일 확장자(do·xml·jsp·atom·json·html·shtml·geojson 7자·markdown 8자)가 모두 들고, 점 뒤가 그보다 긴 영문·숫자 꼬리는
    확장자라기보다 이름의 일부(슬래시 없이 끝나는 `/api/v1.release9` 같은 버전·꼬리 이름)로 보는 편이 낫다고 보았다. 레지스트리의 실제 확장자는 2–4자라 지금은 한도에 닿지 않는다(아래 시험이 확인).
    틀리는 방향은 둘 다 안전한 쪽이 아니다: 한도보다 긴 '확장자'는 파일로 읽히지 않아 옛 규칙(하위 경로 허용)이 그대로 남고, 한도 안의 꼬리 이름은 파일로 읽혀 하위 경로가 거부된다.
    그래서 한도를 바꾸려면(예: 9자 이상 확장자를 가진 접두어를 허용 목록에 넣는 날) 이 시험과 근거를 함께 고친다 — 근거가 없는 값 변경은 하지 않고 현재 값을 못박기만 한다."""
    LIMIT = 8

    def test_an_extension_of_one_to_eight_characters_is_a_file_and_nine_or_more_is_not(self):
        for length in range(1, self.LIMIT + 1):
            prefix = "/data/name." + "a" * length
            with self.subTest(length=length):
                self.assertTrue(sr.path_matches(prefix, (prefix,)))
                self.assertFalse(sr.path_matches(prefix + "/child", (prefix,)), prefix)           # 파일 — 뒤 조각 거부
        for length in (self.LIMIT + 1, self.LIMIT + 2, 20):
            prefix = "/data/name." + "a" * length
            with self.subTest(length=length):
                self.assertTrue(sr.path_matches(prefix, (prefix,)))
                self.assertTrue(sr.path_matches(prefix + "/child", (prefix,)), prefix)            # 파일이 아님 — 옛 접두 규칙(하위 경로 허용)

    def test_digits_count_toward_the_limit_but_the_first_character_must_be_a_letter(self):
        self.assertFalse(sr.path_matches("/d/x.a1b2c3d4/child", ("/d/x.a1b2c3d4",)))              # 글자 + 숫자 7 = 8자: 파일
        self.assertTrue(sr.path_matches("/d/x.a1b2c3d4e/child", ("/d/x.a1b2c3d4e",)))             # 9자: 파일 아님
        self.assertTrue(sr.path_matches("/d/x.1abc/child", ("/d/x.1abc",)))                       # 숫자로 시작: 파일 아님(버전 조각)

    def test_common_real_world_extensions_up_to_eight_characters_are_files(self):
        for extension in ("do", "xml", "jsp", "atom", "json", "html", "shtml", "jsonld", "geojson", "markdown", "torrent"):
            prefix = f"/files/report.{extension}"
            with self.subTest(extension=extension):
                self.assertTrue(sr.path_matches(prefix, (prefix,)))
                self.assertFalse(sr.path_matches(prefix + "/anything", (prefix,)), prefix)


class RegistryPathsTest(unittest.TestCase):
    def setUp(self):
        self.registry = sr.load_registry(today=TODAY)

    def test_every_file_extension_in_the_real_registry_is_inside_the_limit(self):
        """레지스트리의 실제 허용 경로 확장자(.json·.xml·.atom·.html·.jsp·.do …)는 모두 한도 안이고 파일로 읽힌다 — 9자 이상 확장자가 들어오면 이 시험이 알려 한도·근거를 다시 보게 한다."""
        lengths = set()
        for provider in self.registry.providers():
            for access in provider.access:
                for prefix in access.paths:
                    found = re.search(r"\.([A-Za-z][A-Za-z0-9]*)$", prefix.rsplit("/", 1)[-1])
                    if prefix.endswith("/") or not found:
                        continue
                    with self.subTest(provider=provider.provider_id, prefix=prefix):
                        lengths.add(len(found.group(1)))
                        self.assertLessEqual(len(found.group(1)), FileExtensionLimitTest.LIMIT, prefix)
                        self.assertTrue(sr._FILE_LIKE_PREFIX.search(prefix), prefix)
        self.assertIn(4, lengths)                                                                     # .json·.atom·.html — 빈 그릇이 아니다
        self.assertLessEqual(max(lengths), FileExtensionLimitTest.LIMIT)

    def all_prefixes(self):
        found = []
        for provider in self.registry.providers():
            for access in provider.access:
                for prefix in access.paths:
                    found.append((provider.provider_id, access, prefix))
        return found

    def test_every_allowed_path_of_the_real_registry_still_passes_as_itself(self):
        found = self.all_prefixes()
        self.assertGreater(len(found), 50)
        for provider_id, access, prefix in found:
            with self.subTest(provider=provider_id, prefix=prefix):
                self.assertTrue(sr.path_matches(prefix.rstrip("/") or "/", access.paths) or prefix == "/", prefix)
                self.assertTrue(sr.path_matches(prefix, access.paths), prefix)

    def test_directory_prefixes_still_accept_a_child_and_file_prefixes_do_not(self):
        files, directories = 0, 0
        for provider_id, access, prefix in self.all_prefixes():
            with self.subTest(provider=provider_id, prefix=prefix):
                if prefix.endswith("/"):
                    directories += 1
                    self.assertTrue(sr.path_matches(prefix + "child", access.paths), prefix)
                elif sr._FILE_LIKE_PREFIX.search(prefix):
                    files += 1
                    self.assertFalse(sr.path_matches(prefix + "/child", (prefix,)), prefix)
                else:
                    self.assertTrue(sr.path_matches(prefix + "/child", (prefix,)), prefix)          # 확장자 없는 접두어는 이전과 같다
        self.assertGreater(files, 15)                                                                 # 파일 경로가 실제로 많다(탐지가 빈 그릇이 아니다)
        self.assertGreater(directories, 10)

    def test_the_gate_allows_the_noaa_product_files_and_denies_a_tail_after_them(self):
        noaa = self.registry.get("noaa_swpc_json")
        paths = [prefix for access in noaa.access for prefix in access.paths]
        self.assertIn("/products/noaa-scales.json", paths)
        for path in paths:
            with self.subTest(path=path):
                egress.check_url(f"https://{NOAA_HOST}{path}", "fact", self.registry)                       # 정확한 경로는 통과(예외가 나면 실패)
                with self.assertRaises(egress.EgressDenied):
                    egress.check_url(f"https://{NOAA_HOST}{path}/anything", "fact", self.registry)


if __name__ == "__main__":
    unittest.main()
