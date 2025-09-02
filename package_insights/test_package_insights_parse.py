import pytest
from package_insights.package_insights import parse_log_for_details


@pytest.mark.parametrize(
    "log_text,expected",
    [
        (
            "ERROR 403 while downloading https://dl.cloudsmith.io/public/myspace/myrepo/python/pkgname-1.2.3.tar.gz (for user)",
            ("myspace", "myrepo", "pkgname", "1.2.3"),
        ),
        (
            # Should still parse even without explicit 403 in the same line
            "Downloading https://dl.cloudsmith.io/public/team/repo/python/cool_pkg-0.9.0rc1.whl ...",
            ("team", "repo", "cool_pkg", "0.9.0rc1"),
        ),
        (
            "Some preface ... 403 Forbidden: https://dl.cloudsmith.io/public/ns/rp/python/another.pkg-10.4.zip end",
            ("ns", "rp", "another.pkg", "10.4"),
        ),
        (
            "403 GET https://dl.cloudsmith.io/public/org/rp-python/python/my_pkg_name-1.0b2.tar.gz",
            ("org", "rp-python", "my_pkg_name", "1.0b2"),
        ),
    ],
)
def test_parse_log_for_details_success_cases(log_text, expected):
    assert parse_log_for_details(log_text) == expected


def test_multiple_matches_returns_first():
    log = (
        "403 https://dl.cloudsmith.io/public/first/ns/python/firstpkg-1.0.0.tar.gz\n"
        "403 https://dl.cloudsmith.io/public/second/ns/python/secondpkg-2.0.0.whl\n"
    )
    assert parse_log_for_details(log) == ("first", "ns", "firstpkg", "1.0.0")


@pytest.mark.parametrize(
    "log_text",
    [
        "No relevant URLs here",
        # Version starts with 'v' (pattern requires digit at start of version)
        "403 https://dl.cloudsmith.io/public/ns/repo/python/pkgname-v1.2.3.tar.gz",
        # Missing python segment
        "403 https://dl.cloudsmith.io/public/ns/repo/pkgname-1.2.3.tar.gz",
        # Not a supported extension
        "403 https://dl.cloudsmith.io/public/ns/repo/python/pkgname-1.2.3.txt",
    ],
)
def test_parse_log_for_details_no_match(log_text):
    assert parse_log_for_details(log_text) == (None, None, None, None)


def test_parse_log_for_details_complex_name_and_version():
    log = "403 https://dl.cloudsmith.io/public/acme/tools/python/my.pkg_name-12.0.0.post1.tar.gz"
    assert parse_log_for_details(log) == ("acme", "tools", "my.pkg_name", "12.0.0.post1")
