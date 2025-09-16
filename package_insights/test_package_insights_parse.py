import pytest
from package_insights.package_insights import parse_logs_for_all_details


@pytest.fixture
def config():
    from config import get_config
    return get_config() 


class TestPythonLogParsing:
    @pytest.mark.parametrize(
        "log_text,expected",
        [
            (
                """
                Looking in indexes: https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/workspace-name/repository-name/python/simple/
                Collecting python-gitlab==3.1.1
                WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'ReadTimeoutError("HTTPSConnectionPool(host='dl.cloudsmith.io', port=443): Read timed out. (read timeout=15)")': /pzvJ5VJQLGivg1uL/workspace-name/repository-name/python/python_gitlab-3.1.1-py3-none-any.whl
                ERROR: HTTP error 403 while getting https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/workspace-name/repository-name/python/python_gitlab-3.1.1-py3-none-any.whl#sha256=2a7de39c8976db6d0db20031e71b3e43d262e99e64b471ef09bf00482cd3d9fa (from https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/workspace-name/repository-name/python/simple/python-gitlab/) (requires-python:>=3.7.0)

                [notice] A new release of pip is available: 25.1.1 -> 25.2
                [notice] To update, run: pip install --upgrade pip
                ERROR: Could not install requirement python-gitlab==3.1.1 from https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/workspace-name/repository-name/python/python_gitlab-3.1.1-py3-none-any.whl#sha256=2a7de39c8976db6d0db20031e71b3e43d262e99e64b471ef09bf00482cd3d9fa because of HTTP error 403 Client Error: Forbidden for url: https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/workspace-name/repository-name/python/python_gitlab-3.1.1-py3-none-any.whl for URL https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/workspace-name/repository-name/python/python_gitlab-3.1.1-py3-none-any.whl#sha256=2a7de39c8976db6d0db20031e71b3e43d262e99e64b471ef09bf00482cd3d9fa (from https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/workspace-name/repository-name/python/simple/python-gitlab/) (requires-python:>=3.7.0)
                """,
                ("workspace-name", "repository-name", "python-gitlab", "3.1.1"),
            )
        ],
    )
    def test_python_parse_logs_for_all_details_success_cases(self, config, log_text, expected):
        all_matches = parse_logs_for_all_details(log_text, config, unique=True)
        assert all_matches and all_matches[0] == expected

    def test_python_multiple_matches_returns_in_order(self, config):
        log = (
            "ERROR: Could not install requirement firstpkg==1.0.0 from https://dl.cloudsmith.io/public/first/ns/python/firstpkg-1.0.0.tar.gz because of HTTP error 403 Client Error: Forbidden for url\n"
            "ERROR: Could not install requirement secondpkg==2.0.0 from https://dl.cloudsmith.io/public/second/ns/python/secondpkg-2.0.0.whl because of HTTP error 403 Client Error: Forbidden for url\n"
        )
        assert parse_logs_for_all_details(log, config)[0] == ("first", "ns", "firstpkg", "1.0.0")
        assert parse_logs_for_all_details(log, config) == [
            ("first", "ns", "firstpkg", "1.0.0"),
            ("second", "ns", "secondpkg", "2.0.0"),
        ]

    def test_python_multiple_matches_with_duplicates(self, config):
        log = (
            "ERROR: Could not install requirement dupkg==1.2.3 from https://dl.cloudsmith.io/public/acme/tools/python/dupkg-1.2.3.tar.gz because of HTTP error 403 Client Error: Forbidden for url\n"
            "ERROR: Could not install requirement dupkg==1.2.3 from https://dl.cloudsmith.io/public/acme/tools/python/dupkg-1.2.3.tar.gz because of HTTP error 403 Client Error: Forbidden for url\n"  # duplicate
            "ERROR: Could not install requirement other==2.0.0 from https://dl.cloudsmith.io/public/acme/tools/python/other-2.0.0.whl because of HTTP error 403 Client Error: Forbidden for url\n"
        )
        assert parse_logs_for_all_details(log, config) == [
            ("acme", "tools", "dupkg", "1.2.3"),
            ("acme", "tools", "other", "2.0.0"),
        ]

    def test_python_parse_logs_for_all_details_complex_name_and_version(self, config):
        log = "ERROR: Could not install requirement from https://dl.cloudsmith.io/public/acme/tools/python/my.pkg_name-12.0.0.post1.tar.gz because of HTTP error 403 Client Error: Forbidden for url"
        assert parse_logs_for_all_details(log, config)[0] == ("acme", "tools", "my.pkg-name", "12.0.0.post1")

    def test_python_parse_logs_for_all_details_no_version_in_error_line_but_artifact_present(self, config):
        log = (
            "ERROR: Could not install requirement python-gitlab from https://dl.cloudsmith.io/public/ws/repo/python/python_gitlab-6.3.0-py3-none-any.whl#sha256=abc because of HTTP error 403 Client Error: Forbidden for url"
        )
        assert parse_logs_for_all_details(log, config)[0] == ("ws", "repo", "python-gitlab", "6.3.0")

    def test_python_no_version_fallback_looks_elsewhere_for_artifact(self, config):
        # URL in error line lacks artifact filename so version must be discovered elsewhere in log
        log = (
            "ERROR: Could not install requirement fallbackpkg from https://dl.cloudsmith.io/public/ws2/repo2/python/simple/fallbackpkg/ because of HTTP error 403 Client Error: Forbidden for url\n"
            "Downloading https://dl.cloudsmith.io/public/ws2/repo2/python/fallbackpkg-2.4.0-py3-none-any.whl (15 kB)\n"
        )
        assert parse_logs_for_all_details(log, config)[0] == ("ws2", "repo2", "fallbackpkg", "2.4.0")

    def test_python_fallback_tarball_url_only(self, config):
        # Error line lacks package name or version so package info is discovered elsewhere in log
        log = "ERROR: Could not install requirement https://dl.cloudsmith.io/public/acme/observability/python/agentlib-1.9.0.tar.gz\n"

        assert parse_logs_for_all_details(log, config)[0] == ("acme", "observability", "agentlib", "1.9.0")


class TestNpmLogParsing:
    def test_parse_npm_signed_fetch_lines(self, config):
        log = (
            "npm http fetch GET 403 https://dl.cloudsmith.io/signed/workspace-name/repository-name/upstream/filename/npm/xml2js/xml2js-0.6.2.tgz?created=1&expires=2 10ms\n"
            "npm http fetch GET 403 https://dl.cloudsmith.io/signed/workspace-name/repository-name/upstream/filename/npm/jmespath/jmespath-0.16.0.tgz?created=1&expires=2 11ms\n"
            "npm error 403 403 Forbidden - GET https://npm.cloudsmith.io/workspace-name/repository-name/xmlbuilder/-/xmlbuilder-11.0.1.tgz - Package is quarantined.\n"
        )
        matches = parse_logs_for_all_details(log, config)
        assert ("workspace-name", "repository-name", "xml2js", "0.6.2") in matches
        assert ("workspace-name", "repository-name", "jmespath", "0.16.0") in matches

    def test_parse_npm_error_direct_quarantine_line(self, config):
        log = (
            "npm error code E403\n"
            "npm error 403 403 Forbidden - GET https://npm.cloudsmith.io/workspace-name/repository-name/xmlbuilder/-/xmlbuilder-11.0.1.tgz - Package is quarantined.\n"
        )
        matches = parse_logs_for_all_details(log, config)
        assert matches[0] == ("workspace-name", "repository-name", "xmlbuilder", "11.0.1")

    def test_parse_npm_error_signed_line(self, config):
        log = (
            "npm error code E403\n"
            "npm error 403 403 Forbidden - GET https://dl.cloudsmith.io/signed/workspace-name/repository-name/upstream/filename/npm/vary/vary-1.1.2.tgz?created=1&expires=2\n"
        )
        matches = parse_logs_for_all_details(log, config)
        assert matches[0] == ("workspace-name", "repository-name", "vary", "1.1.2")

    def test_parse_multiple_npm_direct_fetch_lines(self, config):
        log = (
            "npm http fetch GET 403 https://npm.cloudsmith.io/workspace-name/repository-name/xmlbuilder/-/xmlbuilder-11.0.1.tgz 10ms (cache skip)\n"
            "npm http fetch GET 403 https://npm.cloudsmith.io/workspace-name/repository-name/querystring/-/querystring-0.2.0.tgz 11ms (cache skip)\n"
            "npm http fetch GET 403 https://npm.cloudsmith.io/workspace-name/repository-name/url/-/url-0.10.3.tgz 12ms (cache skip)\n"
        )
        matches = parse_logs_for_all_details(log, config)
        assert ("workspace-name", "repository-name", "xmlbuilder", "11.0.1") in matches
        assert ("workspace-name", "repository-name", "querystring", "0.2.0") in matches
        assert ("workspace-name", "repository-name", "url", "0.10.3") in matches

    def test_parse_npm_detection_no_match_returns_empty(self, config):
        # Contains 'npm ' and '403' to trigger detection, but no recognized patterns
        log = (
            "npm WARN 403 rate limit exceeded for token\n"
            "npm info attempt registry ping\n"
        )
        assert parse_logs_for_all_details(log, config) == []

    def test_parse_npm_duplicate_signed_fetch_dedup(self, config):
        log = (
            "npm http fetch GET 403 https://dl.cloudsmith.io/signed/wsA/repoA/upstream/x/npm/dup/dup-0.1.0.tgz?created=1&expires=2 10ms\n"
            "npm http fetch GET 403 https://dl.cloudsmith.io/signed/wsA/repoA/upstream/x/npm/dup/dup-0.1.0.tgz?created=1&expires=2 11ms\n"  # duplicate
        )
        matches = parse_logs_for_all_details(log, config)
        assert matches == [("wsA", "repoA", "dup", "0.1.0")]


class TestLogParsing:
    # Test Parsing works with all parsers present

    def test_parse_python_error_single_package(self, config):
        log = (
            "ERROR: Could not install requirement foo==2.0.0 from https://dl.cloudsmith.io/public/acme/tools/python/foo-2.0.0.whl because of HTTP error 403 Client Error: Forbidden for url\n"
        )
        assert parse_logs_for_all_details(log, config) == [
            ("acme", "tools", "foo", "2.0.0"),
        ]

    def test_parse_npm_error_single_package(self, config):
        log = (
            "npm error code E403\n"
            "npm error 403 403 Forbidden - GET https://npm.cloudsmith.io/workspace-name/repository-name/xmlbuilder/-/xmlbuilder-11.0.1.tgz - Package is quarantined.\n"
        )
        matches = parse_logs_for_all_details(log, config)
        assert matches[0] == ("workspace-name", "repository-name", "xmlbuilder", "11.0.1")