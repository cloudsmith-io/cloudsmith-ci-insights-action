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
    )
    ],
)
def test_parse_logs_for_all_details_success_cases(log_text, expected):
    all_matches = parse_logs_for_all_details(log_text, unique=True)
    assert all_matches and all_matches[0] == expected


def test_multiple_matches_returns_first():
    log = (
        "ERROR: Could not install requirement firstpkg==1.0.0 from https://dl.cloudsmith.io/public/first/ns/python/firstpkg-1.0.0.tar.gz because of HTTP error 403 Client Error: Forbidden for url\n"
        "ERROR: Could not install requirement secondpkg==2.0.0 from https://dl.cloudsmith.io/public/second/ns/python/secondpkg-2.0.0.whl because of HTTP error 403 Client Error: Forbidden for url\n"
    )
    assert parse_logs_for_all_details(log)[0] == ("first", "ns", "firstpkg", "1.0.0")
    assert parse_logs_for_all_details(log) == [
        ("first", "ns", "firstpkg", "1.0.0"),
        ("second", "ns", "secondpkg", "2.0.0"),
    ]


def test_multiple_matches_with_duplicates():
    log = (
        "ERROR: Could not install requirement dupkg==1.2.3 from https://dl.cloudsmith.io/public/acme/tools/python/dupkg-1.2.3.tar.gz because of HTTP error 403 Client Error: Forbidden for url\n"
        "ERROR: Could not install requirement dupkg==1.2.3 from https://dl.cloudsmith.io/public/acme/tools/python/dupkg-1.2.3.tar.gz because of HTTP error 403 Client Error: Forbidden for url\n"  # duplicate
        "ERROR: Could not install requirement other==2.0.0 from https://dl.cloudsmith.io/public/acme/tools/python/other-2.0.0.whl because of HTTP error 403 Client Error: Forbidden for url\n"
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



def test_parse_logs_for_all_details_complex_name_and_version():
    log = "ERROR: Could not install requirement from https://dl.cloudsmith.io/public/acme/tools/python/my.pkg_name-12.0.0.post1.tar.gz because of HTTP error 403 Client Error: Forbidden for url"
    assert parse_logs_for_all_details(log)[0] == ("acme", "tools", "my.pkg_name", "12.0.0.post1")
