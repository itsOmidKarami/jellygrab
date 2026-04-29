"""Pure-function tests for the 30nama scraper.

These cover the parsing/extraction helpers that operate on already-fetched
payloads — no network, no FlareSolverr, no cookies. The goal is to lock in
the contract between 30nama's response shapes and our SearchResult /
DownloadOption dataclasses, so a future change to those shapes fails CI
loudly instead of silently returning empty results.
"""
from scrapers.nama.scraper import (
    DownloadOption,
    SearchResult,
    _extract_item_id,
    _extract_item_id_from_url,
    _parse_fs_json,
    _parse_movie_options_api,
    _parse_search_api,
    _parse_series_packs,
    _quality_from_url,
)


class TestQualityFromUrl:
    def test_recognizes_common_markers(self):
        assert _quality_from_url("https://x/foo.1080p.mkv") == "1080p"
        assert _quality_from_url("HTTPS://X/FOO.720P.MKV") == "720p"
        assert _quality_from_url("https://x/Movie.2160p.WEB-DL.mkv") == "2160p"

    def test_falls_back_to_unknown(self):
        assert _quality_from_url("https://x/movie.mkv") == "unknown"
        assert _quality_from_url("") == "unknown"


class TestExtractItemIdFromUrl:
    def test_movie_url(self):
        assert _extract_item_id_from_url("https://30nama.com/movie/6276/Iron-Man-2008") == "6276"

    def test_series_url(self):
        assert _extract_item_id_from_url("https://30nama.com/series/12345/some-slug") == "12345"

    def test_alt_paths(self):
        assert _extract_item_id_from_url("https://30nama.com/serie/99/x") == "99"
        assert _extract_item_id_from_url("https://30nama.com/movies/42/x") == "42"

    def test_query_string_does_not_swallow_id(self):
        assert (
            _extract_item_id_from_url("https://30nama.com/movie/777/slug?section=download")
            == "777"
        )

    def test_no_match(self):
        assert _extract_item_id_from_url("https://30nama.com/about") is None


class TestExtractItemId:
    def test_prefers_url_over_html(self):
        # URL has 111, HTML has 222 — URL wins.
        html = '<div data-movie-id="222"></div>'
        assert _extract_item_id("https://30nama.com/movie/111/slug", html) == "111"

    def test_data_attr_fallback(self):
        html = '<div data-series-id="2024"></div>'
        assert _extract_item_id("https://30nama.com/somewhere", html) == "2024"

    def test_json_field_fallback(self):
        html = '{"movie_id": "555"}'
        assert _extract_item_id("https://30nama.com/somewhere", html) == "555"

    def test_returns_none_when_nothing_matches(self):
        assert _extract_item_id("https://30nama.com/nope", "<div></div>") is None


class TestParseFsJson:
    def test_raw_json(self):
        assert _parse_fs_json('{"a": 1}') == {"a": 1}

    def test_flaresolverr_envelope(self):
        wrapped = (
            "<html><head></head><body>"
            '<pre>{"result": {"download": []}}</pre>'
            "</body></html>"
        )
        assert _parse_fs_json(wrapped) == {"result": {"download": []}}

    def test_empty_returns_none(self):
        assert _parse_fs_json("") is None
        assert _parse_fs_json("   ") is None

    def test_garbage_returns_none(self):
        assert _parse_fs_json("not json and no pre tag") is None


class TestParseSearchApi:
    def test_parses_movie_and_series(self):
        body = {
            "result": {
                "posts": [
                    {
                        "id": 6276,
                        "title": "Iron Man 2008",
                        "is_series": False,
                        "image": {"poster": {"medium": "https://x/p.jpg"}},
                    },
                    {
                        "id": 12345,
                        "title": "Severance",
                        "title_type": "series",
                        "image": {"poster": {"large": "https://x/s.jpg"}},
                    },
                ]
            }
        }
        results = _parse_search_api(body)
        assert len(results) == 2
        movie, series = results
        assert isinstance(movie, SearchResult)
        assert movie.kind == "movie"
        assert movie.title == "Iron Man"
        assert movie.year == "2008"
        assert "/movie/6276/" in movie.detail_url
        assert series.kind == "series"
        assert series.year is None
        assert "/series/12345/" in series.detail_url

    def test_skips_posts_without_id(self):
        body = {"result": {"posts": [{"title": "no id"}, {"id": 1, "title": "ok"}]}}
        assert [r.title for r in _parse_search_api(body)] == ["ok"]

    def test_handles_missing_shapes(self):
        assert _parse_search_api({}) == []
        assert _parse_search_api({"result": {}}) == []
        assert _parse_search_api({"result": {"posts": []}}) == []


class TestParseMovieOptionsApi:
    def test_flat_download_list(self):
        body = {
            "result": {
                "download": [
                    {
                        "dl": "https://cdn/movie.1080p.mkv",
                        "quality": "1080p",
                        "size": "2.1GB",
                        "encoder": "Pahe",
                    }
                ]
            }
        }
        opts = _parse_movie_options_api(body)
        assert len(opts) == 1
        assert isinstance(opts[0], DownloadOption)
        assert opts[0].url == "https://cdn/movie.1080p.mkv"
        assert opts[0].quality == "1080p"
        assert opts[0].size == "2.1GB"

    def test_link_array_shape_takes_first(self):
        body = {
            "result": {
                "download": [
                    {
                        "quality": "720p",
                        "link": [{"dl": "https://cdn/a.mkv"}, {"dl": "https://cdn/b.mkv"}],
                    }
                ]
            }
        }
        opts = _parse_movie_options_api(body)
        assert opts[0].url == "https://cdn/a.mkv"

    def test_quality_fallback_inferred_from_url(self):
        body = {"result": {"download": [{"dl": "https://cdn/movie.720p.mkv"}]}}
        assert _parse_movie_options_api(body)[0].quality == "720p"

    def test_skips_entries_without_url(self):
        body = {"result": {"download": [{"quality": "1080p"}, {"dl": "https://cdn/x.mkv"}]}}
        assert len(_parse_movie_options_api(body)) == 1


class TestParseSeriesPacks:
    def test_pack_with_episodes(self):
        body = {
            "result": {
                "download": [
                    {
                        "season": 1,
                        "quality": "1080p",
                        "size": "8GB",
                        "link": [
                            {"episode": 1, "dl": "https://cdn/s01e01.mkv"},
                            {"episode": 2, "dl": "https://cdn/s01e02.mkv"},
                        ],
                    }
                ]
            }
        }
        opts = _parse_series_packs(body)
        assert len(opts) == 1
        pack = opts[0]
        assert pack.season == "1"
        assert pack.quality == "1080p"
        assert pack.episodes == [
            {"episode": "1", "url": "https://cdn/s01e01.mkv"},
            {"episode": "2", "url": "https://cdn/s01e02.mkv"},
        ]

    def test_skips_packs_with_no_dl_links(self):
        body = {"result": {"download": [{"season": 1, "link": [{"episode": 1}]}]}}
        assert _parse_series_packs(body) == []
