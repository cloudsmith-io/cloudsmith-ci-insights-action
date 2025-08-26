import os
import sys
import click
import requests
import re
from typing import Optional


# -----------------------------
# Helper Functions
# -----------------------------

def get_api_key() -> str:
    api_key = os.getenv('CLOUDSMITH_API_KEY')
    if not api_key:
        click.secho('❌ Missing API Key', fg='red', bold=True)
        click.echo('   CLOUDSMITH_API_KEY environment variable not set')
        click.secho('💡 Hint: export CLOUDSMITH_API_KEY=your_key_here', fg='blue')
        sys.exit(1)
    return api_key


def build_headers(api_key: str) -> dict:
    return {
        'X-Api-Key': api_key,
        'Accept': 'application/json',
    }


def fetch_policies(namespace: str, headers: dict) -> dict:
    """Return a dict of policy_slug_perm -> policy object."""
    url = f"https://api.cloudsmith.io/v2/workspaces/{namespace}/policies/"
    resp = requests.get(url, headers=headers)
    policies = {}
    if resp.status_code == 200:
        for policy in resp.json().get('results', []):
            policies[policy.get('slug_perm')] = policy
    else:
        click.secho(f'⚠️  Failed to fetch policies (HTTP {resp.status_code})', fg='yellow')
        click.echo(f'   Response: {resp.text[:100]}...' if len(resp.text) > 100 else f'   Response: {resp.text}')
    return policies


def parse_package_entry(entry: str):
    if '==' in entry:
        return entry.split('==', 1)
    return entry, None


def list_repo_packages(namespace: str, repo: str, headers: dict):
    url = f"https://api.cloudsmith.io/packages/{namespace}/{repo}/?sort=-date"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        click.secho(f'⚠️  Failed to list packages in {namespace}/{repo} (HTTP {resp.status_code})', fg='yellow')
        click.echo(f'   Response: {resp.text[:100]}...' if len(resp.text) > 100 else f'   Response: {resp.text}')
        return None
    return resp.json()


def find_package(packages_data, name: str, version: Optional[str]):
    if not packages_data:
        return None
    for pkg in packages_data:
        if pkg.get('display_name') == name:
            if version:
                if pkg.get('version') == version:
                    return pkg
            else:
                return pkg
    return None


ACTION_SLUG_PERM_REGEX = re.compile(r"slug_perm '([A-Za-z0-9]+)'")


def extract_action_slug(status_reason: str) -> Optional[str]:
    if not status_reason:
        return None
    m = ACTION_SLUG_PERM_REGEX.search(status_reason)
    return m.group(1) if m else None


def find_policy_for_action_slug(policies: dict, action_slug: str, namespace: str, headers: dict) -> Optional[str]:
    """Iterate policies and their actions to find which policy contains the action slug."""
    if not action_slug:
        return None
    for policy_slug, policy in policies.items():
        actions_url = f"https://api.cloudsmith.io/v2/workspaces/{namespace}/policies/{policy_slug}/actions/"
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


def report_package(package_name: str, pkg: dict, policies: dict, namespace: str, headers: dict, follow_up: Optional[str] = None):
    status_str = pkg.get('status_str', 'Unknown')
    status_reason = pkg.get('status_reason', 'No reason provided')
    quarantined = pkg.get('is_quarantined', False)
    version = pkg.get('version')
    
    # Header with package info
    click.echo("=" * 60)
    click.secho("☁️  CLOUDSMITH INSIGHTS ☁️", fg='cyan', bold=True)
    click.echo("=" * 60)
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
        return
    
    # Quarantined package
    click.secho("🚫 Status: QUARANTINED", fg='red', bold=True)
    click.secho(f"📊 Package Status: {status_str}", fg='yellow')
    click.secho(f"💬 Reason: {status_reason}", fg='yellow')
    
    action_slug = extract_action_slug(status_reason)
    if action_slug:
        click.echo()
        click.secho(f"🔑 Action Slug: {action_slug}", fg='magenta')
    
    policy_info = find_policy_for_action_slug(policies, action_slug, namespace, headers) if action_slug else None
    if policy_info:
        click.echo()
        click.secho("🛡️  POLICY DETAILS:", fg='blue', bold=True)
        for line in policy_info.split('\n'):
            click.echo(f"   {line}")
    
    if follow_up:
        click.echo()
        click.secho("🎯 Next Steps:", fg='magenta', bold=True)
        click.echo(f"   {follow_up}")
    
    click.echo("=" * 60)
    click.secho("❌ PACKAGE QUARANTINED", fg='red', bold=True)
    sys.exit(1)


LOG_403_TARBALL_URL_RE = re.compile(
    r"""
    (?:.*403.*?)?                              # Optional: any text before '403', non-greedy
    https://dl\.cloudsmith\.io/                # Match the base Cloudsmith URL
    [^/]+/                                     # Match the domain segment (not captured)
    ([^/]+)/                                   # Capture group 1: namespace
    ([^/]+)/                                   # Capture group 2: repo
    python/                                    # Match the 'python' segment
    ([A-Za-z0-9_.-]+)-                         # Capture group 3: package name
    ([0-9][A-Za-z0-9_.-]*)                     # Capture group 4: version (starts with a digit)
    \.                                         # Literal dot before extension
    (?:tar\.gz|zip|whl)                        # Match one of the allowed extensions
    """,
    re.VERBOSE
)
def parse_log_for_details(log_text: str):
    """Extract namespace, repo, package name and version from log output."""

    m = LOG_403_TARBALL_URL_RE.search(log_text)
    if m:
        namespace, repo, pkg, ver = m.groups()
        return namespace, repo, pkg, ver
    return None, None, None, None


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
    if 'python' not in log_text:
        click.secho('ℹ️  Non-Python package detected', fg='blue') 
        click.echo('   Currently only Python package formats are supported')
        return False
    return True

def _handle_parse_error():
    """Handle error when package details cannot be parsed."""
    click.secho('❌ Unable to parse package details from log', fg='red', bold=True)
    click.echo('   Could not extract package name and version information')
    sys.exit(2)

def _handle_package_not_found(package_name, package_version, namespace, repo, follow_up):
    """Handle error when package is not found in repository."""
    click.secho(f'❌ Package not found: {package_name}=={package_version}', fg='red', bold=True)
    click.echo(f'   Not present in repository: {namespace}/{repo}')
    if follow_up:
        click.echo()
        click.secho("🎯 Next Steps:", fg='magenta', bold=True)
        click.echo(f"   {follow_up}")
    sys.exit(5)

@click.command()
@click.argument('log', nargs=1)
@click.option('--follow-up', 'follow_up', required=False, help='Custom follow-up instructions to display with results.')
def package_insights(log, follow_up):
    """Parse a pip install log, derive package + namespace/repo, then look up quarantine/policy info."""
    log_text = _read_log_text(log)
    if not _validate_log(log_text):
        return
    namespace, repo, package_name, package_version = parse_log_for_details(log_text)
    if not package_name:
        _handle_parse_error()
        return
    api_key = get_api_key()
    headers = build_headers(api_key)
    policies = fetch_policies(namespace, headers)
    packages_data = list_repo_packages(namespace, repo, headers)
    if packages_data is None:
        sys.exit(4)
    match = find_package(packages_data, package_name, package_version)
    if match:
        report_package(package_name, match, policies, namespace, headers, follow_up=follow_up)
    else:
        click.secho(f'❌ Package not found: {package_name}=={package_version}', fg='red', bold=True)
        click.echo(f'   Not present in repository: {namespace}/{repo}')
        if follow_up:
            click.echo()
            click.secho("🎯 Next Steps:", fg='magenta', bold=True)
            click.echo(f"   {follow_up}")
        sys.exit(5)



if __name__ == '__main__':
    package_insights()
