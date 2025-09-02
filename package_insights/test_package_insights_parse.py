import pytest
from package_insights.package_insights import parse_logs_for_all_details


@pytest.mark.parametrize(
    "log_text,expected",
    [
        (
            """
            Looking in indexes: https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/mark-testing/python-stuff/python/simple/
            Collecting python-gitlab==3.1.1
            WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'ReadTimeoutError("HTTPSConnectionPool(host='dl.cloudsmith.io', port=443): Read timed out. (read timeout=15)")': /pzvJ5VJQLGivg1uL/mark-testing/python-stuff/python/python_gitlab-3.1.1-py3-none-any.whl
            ERROR: HTTP error 403 while getting https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/mark-testing/python-stuff/python/python_gitlab-3.1.1-py3-none-any.whl#sha256=2a7de39c8976db6d0db20031e71b3e43d262e99e64b471ef09bf00482cd3d9fa (from https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/mark-testing/python-stuff/python/simple/python-gitlab/) (requires-python:>=3.7.0)

            [notice] A new release of pip is available: 25.1.1 -> 25.2
            [notice] To update, run: pip install --upgrade pip
            ERROR: Could not install requirement python-gitlab==3.1.1 from https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/mark-testing/python-stuff/python/python_gitlab-3.1.1-py3-none-any.whl#sha256=2a7de39c8976db6d0db20031e71b3e43d262e99e64b471ef09bf00482cd3d9fa because of HTTP error 403 Client Error: Forbidden for url: https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/mark-testing/python-stuff/python/python_gitlab-3.1.1-py3-none-any.whl for URL https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/mark-testing/python-stuff/python/python_gitlab-3.1.1-py3-none-any.whl#sha256=2a7de39c8976db6d0db20031e71b3e43d262e99e64b471ef09bf00482cd3d9fa (from https://dl.cloudsmith.io/pzvJ5VJQLGivg1uL/mark-testing/python-stuff/python/simple/python-gitlab/) (requires-python:>=3.7.0)
            """,
            ("mark-testing", "python-stuff", "python-gitlab", "3.1.1"),
    ),
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
def test_parse_logs_for_all_details_success_cases(log_text, expected):
    all_matches = parse_logs_for_all_details(log_text, unique=True)
    assert all_matches and all_matches[0] == expected


def test_multiple_matches_returns_first():
    log = (
        "403 https://dl.cloudsmith.io/public/first/ns/python/firstpkg-1.0.0.tar.gz\n"
        "403 https://dl.cloudsmith.io/public/second/ns/python/secondpkg-2.0.0.whl\n"
    )
    assert parse_logs_for_all_details(log)[0] == ("first", "ns", "firstpkg", "1.0.0")
    assert parse_logs_for_all_details(log) == [
        ("first", "ns", "firstpkg", "1.0.0"),
        ("second", "ns", "secondpkg", "2.0.0"),
    ]


def test_multiple_matches_with_duplicates():
    log = (
        "403 https://dl.cloudsmith.io/public/acme/tools/python/dupkg-1.2.3.tar.gz\n"
        "403 https://dl.cloudsmith.io/public/acme/tools/python/dupkg-1.2.3.tar.gz\n"  # duplicate
        "403 https://dl.cloudsmith.io/public/acme/tools/python/other-2.0.0.whl\n"
    )
    # unique=True default removes duplicate
    assert parse_logs_for_all_details(log) == [
        ("acme", "tools", "dupkg", "1.2.3"),
        ("acme", "tools", "other", "2.0.0"),
    ]
    # unique=False keeps both occurrences
    assert parse_logs_for_all_details(log, unique=False) == [
        ("acme", "tools", "dupkg", "1.2.3"),
        ("acme", "tools", "dupkg", "1.2.3"),
        ("acme", "tools", "other", "2.0.0"),
    ]


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
def test_parse_logs_for_all_details_no_match(log_text):
    assert parse_logs_for_all_details(log_text) == []


def test_parse_logs_for_all_details_complex_name_and_version():
    log = "403 https://dl.cloudsmith.io/public/acme/tools/python/my.pkg_name-12.0.0.post1.tar.gz"
    assert parse_logs_for_all_details(log)[0] == ("acme", "tools", "my.pkg_name", "12.0.0.post1")
