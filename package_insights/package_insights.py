import os
from urllib.parse import quote as _urlquote
import sys
import click
import requests
import re
from typing import Optional
from enum import IntEnum

try:
    from .config import get_config
except ImportError:
    # Handle when run as script
    from config import get_config


class ExitCode(IntEnum):
    SUCCESS = 0
    QUARANTINED_DETECTED = 1
    PARSE_ERROR = 2
    MISSING_API_KEY = 3


# -----------------------------
# Helper Functions
# -----------------------------

def get_api_key() -> str:
    api_key = os.getenv('CLOUDSMITH_API_KEY')
    if not api_key:
        click.secho('❌ Missing API Key', fg='red', bold=True)
        click.echo('   CLOUDSMITH_API_KEY environment variable not set')
        click.secho('💡 Hint: export CLOUDSMITH_API_KEY=your_key_here', fg='blue')
        sys.exit(ExitCode.MISSING_API_KEY)
    return api_key


def build_headers(api_key: str) -> dict:
    return {
        'X-Api-Key': api_key,
        'Accept': 'application/json',
    }


def fetch_policies(workspace: str, headers: dict, api_root: str) -> dict:
    """Return a dict of policy_slug_perm -> policy object."""
    base_url = f"https://{api_root}/v2/workspaces/{workspace}/policies/"
    page = 1
    total_pages = None
    policies = {}

    while True:
        url = f"{base_url}?page={page}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            click.secho(f'⚠️  Failed to fetch policies (page {page}) (HTTP {resp.status_code})', fg='yellow')
            click.echo(f'   Response: {resp.text}')
            break
        try:
            data = resp.json()
        except ValueError:
            click.secho(f'⚠️  Invalid JSON while fetching policies (page {page})', fg='yellow')
            break
        for policy in data.get('results', []):
            slug = policy.get('slug_perm')
            if slug and slug not in policies:  # avoid duplicates if any
                policies[slug] = policy

        if total_pages is None:
            total_header = resp.headers.get('x-pagination-pagetotal')
            if total_header and total_header.isdigit():
                total_pages = int(total_header)
            else:
                # No pagination headers -> assume single page
                break
        page += 1
        if total_pages is not None and page > total_pages:
            break
    return policies

def fetch_policy_of_action(workspace: str, headers: dict, action_slug: str, api_root: str) -> str|None:
    """Return a dict of policy_slug_perm -> policy object."""
    base_url = f"https://{api_root}/v2/workspaces/{workspace}/policies/"
    page = 1
    total_pages = None

    while True:
        url = f"{base_url}?page={page}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            click.secho(f'⚠️  Failed to fetch policies (page {page}) (HTTP {resp.status_code})', fg='yellow')
            click.echo(f'   Response: {resp.text}')
            break
        try:
            data = resp.json()
        except ValueError:
            click.secho(f'⚠️  Invalid JSON while fetching policies (page {page})', fg='yellow')
            break
        for policy in data.get('results', []):
            slug = policy.get('slug_perm')
            actions_url = f"https://{api_root}/v2/workspaces/{workspace}/policies/{slug}/actions/"
            resp = requests.get(actions_url, headers=headers)
            if resp.status_code != 200:
                click.secho(f"⚠️  Could not fetch actions for policy '{slug}' (HTTP {resp.status_code})", fg='yellow')
                continue
            for action in resp.json().get('results', []):
                if action.get('slug_perm') == action_slug:
                    policy_name = policy.get('name', 'Unnamed Policy')
                    policy_desc = policy.get('description', 'No description available')
                    return (f"📋 Policy Name: {policy_name}\n"
                        f"🔗 Policy Slug: {slug}\n"
                        f"📝 Description: {policy_desc}")

        if total_pages is None:
            total_header = resp.headers.get('x-pagination-pagetotal')
            if total_header and total_header.isdigit():
                total_pages = int(total_header)
            else:
                # No pagination headers -> assume single page
                break
        page += 1
        if total_pages is not None and page > total_pages:
            break
    return None


def parse_package_entry(entry: str):
    if '==' in entry:
        return entry.split('==', 1)
    return entry, None


def find_package(workspace: str, repo: str, headers: dict, name: str, version: Optional[str], api_root: str):
    """Locate a package using Cloudsmith packages API."""
    base_url = f"https://{api_root}/packages/{workspace}/{repo}/"
    
    query_term = name if not version else f"name:{name} AND version:{version}"
    page = 1
    total_pages = None
    while True:
        url = f"{base_url}?sort=-date&query={_urlquote(query_term)}&page={page}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            click.secho(
                f"⚠️  Failed to list packages (page {page}) in {workspace}/{repo} (HTTP {resp.status_code})",
                fg='yellow'
            )
            click.echo(f'   Response: {resp.text}')
            return None
        try:
            packages = resp.json()
        except ValueError:
            click.secho(f"⚠️  Invalid JSON response for page {page}", fg='yellow')
            return None

        if isinstance(packages, dict) and 'results' in packages:
            packages_iter = packages.get('results', [])
        else:
            packages_iter = packages

        for pkg in packages_iter:
            if pkg.get('display_name') == name and (version is None or pkg.get('version') == version):
                return pkg

        if total_pages is None:
            total_header = resp.headers.get('x-pagination-pagetotal')
            if total_header and total_header.isdigit():
                total_pages = int(total_header)
            else:
                # No pagination headers -> assume single page; stop.
                break
        page += 1
        if total_pages is not None and page > total_pages:
            break
    return None


ACTION_SLUG_PERM_REGEX = re.compile(r"slug_perm '([A-Za-z0-9]+)'")


def extract_action_slug(status_reason: str) -> Optional[str]:
    if not status_reason:
        return None
    m = ACTION_SLUG_PERM_REGEX.search(status_reason)
    return m.group(1) if m else None


def find_policy_for_action_slug(policies: dict, action_slug: str, workspace: str, headers: dict, api_root: str) -> Optional[str]:
    """Iterate policies and their actions to find which policy contains the action slug."""
    if not action_slug:
        return None
    for policy_slug, policy in policies.items():
        actions_url = f"https://{api_root}/v2/workspaces/{workspace}/policies/{policy_slug}/actions/"
        resp = requests.get(actions_url, headers=headers)
        if resp.status_code != 200:
            click.secho(f"⚠️  Could not fetch actions for policy '{policy_slug}' (HTTP {resp.status_code})", fg='yellow')
            continue
        for action in resp.json().get('results', []):
            if action.get('slug_perm') == action_slug:
                policy_name = policy.get('name', 'Unnamed Policy')
                policy_desc = policy.get('description', 'No description available')
                return (f"📋 Policy Name: {policy_name}\n"
                       f"🔗 Policy Slug: {policy_slug}\n"
                       f"📝 Description: {policy_desc}")
    return None


def report_package(package_name: str, pkg: dict, policy_info: str, action_slug: str, follow_up: Optional[str] = None):
    status_str = pkg.get('status_str', 'Unknown')
    status_reason = pkg.get('status_reason', 'No reason provided')
    quarantined = pkg.get('is_quarantined', False)
    version = pkg.get('version')
    
    # Package info
    click.secho(f"📦 Package: {package_name}=={version} 📦", fg='white', bold=True)
    click.echo("-" * 40)
    
    if not quarantined:
        click.secho("🛑 Status: Likely Blocked", fg='green', bold=True)
        click.secho(f"🔍 Current Status: {status_str}", fg='blue')
        click.echo()
        click.secho("⚠️  IMPORTANT:", fg='yellow', bold=True)
        click.echo("   Package is likely blocked given 403 response.")
        click.echo("   This could be a transient issue or a policy restriction.")
        
        if follow_up:
            click.echo()
            click.secho("🎯 Next Steps:", fg='magenta', bold=True)
            click.echo(f"   {follow_up}")
        click.echo("=" * 60)
        return quarantined  # False
    
    # Quarantined package
    click.secho("🚫 Status: QUARANTINED", fg='red', bold=True)
    click.secho(f"📊 Package Status: {status_str}", fg='yellow')
    click.secho(f"💬 Reason: {status_reason}", fg='yellow')
    
    if action_slug:
        click.echo()
        click.secho(f"🔑 Action Slug: {action_slug}", fg='magenta')
    
    if policy_info:
        click.echo()
        click.secho("🛡️  POLICY DETAILS:", fg='blue', bold=True)
        for line in policy_info.split('\n'):
            click.echo(f"   {line}")
    else:
        click.echo()
        click.secho("🛡️  POLICY DETAILS:", fg='blue', bold=True)
        click.echo("   No associated policy found - this can happen when the action has occurred but since been deleted")
    
    if follow_up:
        click.echo()
        click.secho("🎯 Next Steps:", fg='magenta', bold=True)
        click.echo(f"   {follow_up}")
    
    click.echo("-" * 40)
    click.echo()

    return quarantined # True

# -----------------------------
# Parsers
# -----------------------------

class BaseFormatClientParser:
    """Base parser for a (package_format, client) pair.

    Subclasses should implement:
      log_matches_format_and_client(log_text): return True if the logs indicate this is the correct parser
      extract(log_text): yield raw tuples (workspace, repo, package, version)
      normalise_name(name)
      normalise_version(version)
    """
    package_format = "generic"
    client = "generic"
    
    def __init__(self, config):
        """Initialize parser with configuration object.
        
        Args:
            config: Configuration dict from get_config() containing domain settings
        """
        self.config = config

    def log_matches_format_and_client(self, log_text: str) -> bool:  # pragma: no cover - default
        return False

    def extract(self, log_text: str):  # pragma: no cover - default
        return []

    def normalise_name(self, name: str) -> str:
        return name

    def normalise_version(self, version: str) -> str:
        return version

    def parse(self, log_text: str):
        seen = set()
        results = []
        for workspace, repo, name, version in self.extract(log_text):
            normalised_name = self.normalise_name(name)
            normalised_version = self.normalise_version(version)
            tup = (workspace, repo, normalised_name, normalised_version)
            if tup not in seen:
                seen.add(tup)
                results.append(tup)
        return results


class PythonPipParser(BaseFormatClientParser):
    package_format = "python"
    client = "pip"

    def __init__(self, config):
        super().__init__(config)
        
        # Build regexes using download domain from config
        download_root = self.config['CLOUDSMITH_DOWNLOAD_ROOT']
        escaped_domain = re.escape(download_root)
        
        # Generic 403 tarball URL regex (moved from global scope)
        self.LOG_403_TARBALL_URL_RE = re.compile(
            rf"""
            (?:.*403.*?)?                              # Optional: any text before '403', non-greedy
            https://{escaped_domain}/                   # Match the base Cloudsmith URL
            [^/]+/                                     # Match the domain segment (not captured)
            ([^/]+)/                                   # Capture group 1: workspace
            ([^/]+)/                                   # Capture group 2: repo
            python/                                    # Match the 'python' segment
            ([A-Za-z0-9_.-]+)-                         # Capture group 3: package name
            ([0-9][A-Za-z0-9_.-]*)                     # Capture group 4: version (starts with a digit)
            \.                                         # Literal dot before extension
            (?:tar\.gz|zip|whl)                        # Match one of the allowed extensions
            """,
            re.VERBOSE
        )
        
        # Match name==version from error log
        self.ERROR_COULD_NOT_INSTALL_RE = re.compile(
            rf"ERROR: Could not install requirement\s+([A-Za-z0-9_.-]+)==([0-9][A-Za-z0-9_.-]*)\s+from\s+(https://{escaped_domain}/[^\s)]+)",
            re.IGNORECASE,
        )
        # Match name from error log (pip install called without specific version)
        self.ERROR_COULD_NOT_INSTALL_NO_VER_RE = re.compile(
            rf"ERROR: Could not install requirement\s+([A-Za-z0-9_.-]+)\s+from\s+(https://{escaped_domain}/[^\s)]+)",
            re.IGNORECASE,
        )
        self.WORKSPACE_REPO_FROM_URL_RE = re.compile(rf"https://{escaped_domain}/[^/]+/([^/]+)/([^/]+)/python/")
        # Extract from wheel filename e.g. python_gitlab-6.3.0-py3-none-any.whl
        self.ARTIFACT_FILENAME_RE = re.compile(r"/python/([A-Za-z0-9_.-]+)-([0-9][A-Za-z0-9_.-]*)-py[0-9]", re.IGNORECASE)

    def log_matches_format_and_client(self, log_text: str) -> bool:
        return "ERROR: Could not install requirement" in log_text and "python" in log_text

    def extract(self, log_text: str):
        # First: explicit version form
        matched = False
        for m in self.ERROR_COULD_NOT_INSTALL_RE.finditer(log_text):
            pkg, ver, url = m.groups()
            nsrp = self.WORKSPACE_REPO_FROM_URL_RE.search(url)
            if not nsrp:
                continue
            workspace, repo = nsrp.groups()
            yield (workspace, repo, pkg, ver)
            matched = True
        if matched:
            return

        # Second: no-version form; derive version from artifact filename if possible
        for m in self.ERROR_COULD_NOT_INSTALL_NO_VER_RE.finditer(log_text):
            pkg, url = m.groups()
            nsrp = self.WORKSPACE_REPO_FROM_URL_RE.search(url)
            if not nsrp:
                continue
            workspace, repo = nsrp.groups()
            ver = None
            art = self.ARTIFACT_FILENAME_RE.search(url)
            if art:
                wheel_name, wheel_ver = art.groups()
                ver = wheel_ver
            else:
                # As a fallback attempt to pull version from any artifact URL in log
                art2 = self.ARTIFACT_FILENAME_RE.search(log_text)
                if art2:
                    _, wheel_ver = art2.groups()
                    ver = wheel_ver
            if ver:
                yield (workspace, repo, pkg, ver)
                matched = True
        if matched:
            return

        # Fallback: artifact URLs
        for m in self.LOG_403_TARBALL_URL_RE.finditer(log_text):
            ns, rp, pkg, ver = m.groups()
            yield (ns, rp, pkg, ver)

    def normalise_name(self, name: str) -> str:
        # Keep original requested form (hyphens) if present; ensure underscores from artifact names
        # are converted to hyphens for consistency with pip requirement syntax.
        return name.replace('_', '-')

    def normalise_version(self, version: str) -> str:
        # Strip trailing wheel/platform qualifiers if they slipped in (defensive)
        if not version:
            return version
        # Match PEP 440-compliant version strings: X.Y, X.Y.Z, and optional pre/post/dev tags
        m = re.match(r"^(\d+\.\d+(?:\.\d+)?(?:[a-zA-Z0-9_.-]*)?)$", version)
        return m.group(1) if m else version


class NpmParser(BaseFormatClientParser):
    package_format = "npm"
    client = "npm"

    def __init__(self, config):
        super().__init__(config)
        
        # Build regexes using domains from config
        download_root = self.config['CLOUDSMITH_DOWNLOAD_ROOT']
        npm_root = self.config['CLOUDSMITH_NPM_ROOT']
        escaped_download_domain = re.escape(download_root)
        escaped_npm_domain = re.escape(npm_root)
        print(escaped_download_domain)
        print(escaped_npm_domain)
        
        # Match signed URL style (npm http fetch GET 403 ... dl.cloudsmith.io/signed/.../npm/<pkg>/<pkg>-<ver>.tgz)
        self.NPM_SIGNED_FETCH_RE = re.compile(
            rf"npm http fetch GET 403\s+(https://{escaped_download_domain}/[^\s]+/npm/([A-Za-z0-9_.-]+)/\2-([0-9]+\.[0-9]+\.[0-9]+[^/]*)\.tgz)",
            re.IGNORECASE,
        )
        # Match direct registry http fetch 403 lines (npm http fetch GET 403 https://npm.cloudsmith.io/ws/repo/<pkg>/-/<pkg>-<ver>.tgz)
        self.NPM_HTTP_DIRECT_FETCH_RE = re.compile(
            rf"npm http fetch GET 403\s+(https://{escaped_npm_domain}/[^\s]+/([A-Za-z0-9_.-]+)/-/\2-([0-9]+\.[0-9]+\.[0-9]+[^/]*)\.tgz)",
            re.IGNORECASE,
        )
        # Match npm.cloudsmith.io style (quarantine message version)
        self.NPM_DIRECT_FETCH_RE = re.compile(
            rf"npm error 403 403 Forbidden - GET (https://{escaped_npm_domain}/[^\s]+/([A-Za-z0-9_.-]+)/-/\2-([0-9]+\.[0-9]+\.[0-9]+[^/]*)\.tgz)",
            re.IGNORECASE,
        )
        # Generic 403 Forbidden GET (signed) in error line
        self.NPM_ERROR_SIGNED_RE = re.compile(
            rf"npm error 403 403 Forbidden - GET (https://{escaped_download_domain}/[^\s]+/npm/([A-Za-z0-9_.-]+)/\2-([0-9]+\.[0-9]+\.[0-9]+[^/]*)\.tgz)",
            re.IGNORECASE,
        )
        self.WORKSPACE_REPO_FROM_URL_RE = re.compile(rf"https://(?:{escaped_download_domain}|{escaped_npm_domain})/(?:signed/)?([^/]+)/([^/]+)/")

    def log_matches_format_and_client(self, log_text: str) -> bool:
        print(log_text)
        return 'npm ' in log_text and '403' in log_text

    def extract(self, log_text: str):
        matched = False
        patterns = [
            self.NPM_SIGNED_FETCH_RE,
            self.NPM_HTTP_DIRECT_FETCH_RE,
            self.NPM_DIRECT_FETCH_RE,
            self.NPM_ERROR_SIGNED_RE,
        ]
        for pattern in patterns:
            for m in pattern.finditer(log_text):
                full_url, pkg, ver = m.groups()
                ws_repo = self.WORKSPACE_REPO_FROM_URL_RE.search(full_url)
                if not ws_repo:
                    continue
                workspace, repo = ws_repo.groups()
                yield (workspace, repo, pkg, ver)
                matched = True
        if matched:
            return

    def normalise_name(self, name: str) -> str:
        return name  # npm names usually kept as-is (ignoring scoped packages for now)

    def normalise_version(self, version: str) -> str:
        return version


def parse_logs_for_all_details(log_text: str, config: dict, unique: bool = True):
    """Parse log output for all (workspace, repo, package, version) tuples.

    Args:
        log_text: The log text to parse
        config: Configuration dict with domain settings (from get_config())
        unique: Whether to return only unique results

    Extensible pipeline:
      1. Iterate registered parsers; the first whose log_matches_format_and_client() returns True is used.
      2. If that parser returns results, return them.
      3. If detection passes but no results extracted, fall through to next parser 
        - this allows us to try multiple parsers where similar errors occur 
        - TODO: it might make more sense to match package format and then iterate through multiple client parsers
      4. Return an empty list if no results found
    """
    # Create parsers with config object
    parsers = [
        PythonPipParser(config),
        NpmParser(config),
    ]
    
    for parser in parsers:
        if parser.log_matches_format_and_client(log_text):
            results = parser.parse(log_text)
            if results:
                return results
    return []


def _read_log_text(log):
    """Read log text from file or use raw string."""
    if os.path.exists(log):
        with open(log, 'r', encoding='utf-8', errors='ignore') as fh:
            return fh.read()
    return log

def _validate_log(log_text):
    """Validate log for 403 errors and Python package format."""
    if '403' not in log_text:
        click.secho('ℹ️  No 403 errors detected in log', fg='blue')
        click.echo('   Insights are currently only supported for 403 (Forbidden) errors')
        return False
    return True

def _handle_parse_error():
    """Handle error when package details cannot be parsed."""
    click.secho('❌ Unable to parse package details from log', fg='red', bold=True)
    click.echo('   Could not extract package name and version information')
    sys.exit(ExitCode.PARSE_ERROR)

def _handle_package_not_found(package_name, package_version, workspace, repo, follow_up):
    """Handle error when package is not found in repository."""
    click.secho(f'❌ Package not found: {package_name}=={package_version}', fg='red', bold=True)
    click.echo(f'   Not present in repository: {workspace}/{repo}')
    if follow_up:
        click.echo()
        click.secho("🎯 Next Steps:", fg='magenta', bold=True)
        click.echo(f"   {follow_up}")

@click.command()
@click.argument('log', nargs=1)
@click.option('--follow-up', 'follow_up', required=False, help='Custom follow-up instructions to display with results.')
@click.option('--api-domain', 'api_domain', required=False, default="api.cloudsmith.io",
              help='API domain override')
@click.option('--npm-domain', 'npm_domain', required=False, default="npm.cloudsmith.io",
              help='NPM domain override')
@click.option('--python-domain', 'python_domain', required=False, default="python.cloudsmith.io",
              help='Python/download domain override')
@click.option('--docker-domain', 'docker_domain', required=False, default="docker.cloudsmith.io",
              help='Docker domain override')
@click.option('--download-domain', 'download_domain', required=False, default="dl.cloudsmith.io",
              help='Download domain override')
def package_insights(log, follow_up, api_domain, npm_domain, python_domain, docker_domain, download_domain):
    """Parse a pip install log, derive package + workspace/repo, then look up quarantine/policy info."""

    config = get_config(
        api_domain=api_domain,
        npm_domain=npm_domain,
        python_domain=python_domain,
        docker_domain=docker_domain,
        download_domain=download_domain
    )

    print(config)
    
    log_text = _read_log_text(log)
    if not _validate_log(log_text):
        return
    matches = parse_logs_for_all_details(log_text, config, unique=True)
    if not matches:
        _handle_parse_error()
        return

    api_key = get_api_key()
    headers = build_headers(api_key)

    # Print Header
    click.echo("=" * 60)
    click.secho("☁️  CLOUDSMITH INSIGHTS ☁️", fg='cyan', bold=True)
    click.echo("=" * 60)

    # Track whether any quarantined package exists to triggered an exit code after loop.
    quarantined_detected = False
    for workspace, repo, package_name, package_version in matches:
        match = find_package(workspace, repo, headers, package_name, package_version, config["CLOUDSMITH_API_ROOT"])
        if match is None:
            # Report missing package but continue processing remaining packages.
            _handle_package_not_found(package_name, package_version, workspace, repo, follow_up)
            continue

        status_reason = match.get('status_reason', 'No reason provided')
        action_slug = extract_action_slug(status_reason)
        policy_info = None
        if action_slug:
            policy_info = fetch_policy_of_action(workspace, headers, action_slug, config["CLOUDSMITH_API_ROOT"])
        quarantined = report_package(
            package_name,
            match,
            policy_info,
            action_slug,
            follow_up=follow_up
        )
        if quarantined:
            quarantined_detected = True

    if quarantined_detected:
        # After reporting all, use exit code 1 to indicate at least one quarantined
        sys.exit(ExitCode.QUARANTINED_DETECTED)




if __name__ == '__main__':
    package_insights()
