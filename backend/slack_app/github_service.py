"""
GitHub API Service
Fetches project progress, commits, PRs, and issues from GitHub
for a linked workspace repository.
"""

import os
import logging
import urllib.request
import urllib.error
import json

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _get_token():
    token = os.environ.get('GITHUB_TOKEN', '')
    if not token or token == 'your_new_github_token_here':
        # Try reading from .env manually as fallback
        try:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env_path = os.path.join(base, '.env')
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('GITHUB_TOKEN='):
                        token = line.split('=', 1)[1].strip()
                        break
        except Exception:
            pass
    return token


def _github_get(path: str) -> dict | list | None:
    """Make an authenticated GET request to GitHub API."""
    token = _get_token()
    url = f"{GITHUB_API}{path}"
    req = urllib.request.Request(url, headers={
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'PilotAI-SlackBot/1.0',
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        logger.error(f"GitHub API HTTP error {e.code} for {path}: {e.reason}")
        return None
    except Exception as e:
        logger.error(f"GitHub API error for {path}: {e}")
        return None


def get_repo_info(owner: str, repo: str) -> dict | None:
    """Get basic repository metadata."""
    return _github_get(f"/repos/{owner}/{repo}")


def get_recent_commits(owner: str, repo: str, limit: int = 5) -> list:
    """Get the last N commits."""
    data = _github_get(f"/repos/{owner}/{repo}/commits?per_page={limit}")
    if not data:
        return []
    commits = []
    for c in data[:limit]:
        commits.append({
            'sha': c['sha'][:7],
            'message': c['commit']['message'].split('\n')[0][:80],
            'author': c['commit']['author']['name'],
            'date': c['commit']['author']['date'][:10],
        })
    return commits


def get_open_prs(owner: str, repo: str) -> dict:
    """Get open pull requests."""
    data = _github_get(f"/repos/{owner}/{repo}/pulls?state=open&per_page=5")
    if not data:
        return {'count': 0, 'items': []}
    return {
        'count': len(data),
        'items': [{'title': pr['title'], 'user': pr['user']['login'], 'number': pr['number']} for pr in data[:5]]
    }


def get_open_issues(owner: str, repo: str) -> dict:
    """Get open issues (excluding PRs)."""
    data = _github_get(f"/repos/{owner}/{repo}/issues?state=open&per_page=5")
    if not data:
        return {'count': 0, 'items': []}
    # GitHub issues endpoint includes PRs — filter them out
    issues_only = [i for i in data if 'pull_request' not in i]
    return {
        'count': len(issues_only),
        'items': [{'title': i['title'], 'number': i['number']} for i in issues_only[:5]]
    }


def get_contributors(owner: str, repo: str) -> list:
    """Get top contributors."""
    data = _github_get(f"/repos/{owner}/{repo}/contributors?per_page=5")
    if not data:
        return []
    return [{'login': c['login'], 'contributions': c['contributions']} for c in data[:5]]


def build_project_report(github_repo: str) -> dict:
    """
    Master function: given 'owner/repo', return a full project health report.
    Returns a dict with all relevant data, or an error key on failure.
    """
    if '/' not in github_repo:
        return {'error': f'Invalid repo format: "{github_repo}". Must be owner/repo-name.'}

    owner, repo = github_repo.strip().split('/', 1)

    info = get_repo_info(owner, repo)
    if not info:
        return {'error': f'Could not fetch repo "{github_repo}". Check the name and token.'}

    commits = get_recent_commits(owner, repo)
    prs = get_open_prs(owner, repo)
    issues = get_open_issues(owner, repo)
    contributors = get_contributors(owner, repo)

    return {
        'repo': github_repo,
        'full_name': info.get('full_name', github_repo),
        'description': info.get('description', ''),
        'stars': info.get('stargazers_count', 0),
        'forks': info.get('forks_count', 0),
        'open_issues_count': info.get('open_issues_count', 0),
        'default_branch': info.get('default_branch', 'main'),
        'last_push': (info.get('pushed_at') or '')[:10],
        'language': info.get('language', 'Unknown'),
        'url': info.get('html_url', ''),
        'commits': commits,
        'pull_requests': prs,
        'issues': issues,
        'contributors': contributors,
    }


def detect_github_intent(text: str) -> bool:
    """Detect if a message is asking about project/GitHub progress."""
    import re
    triggers = [
        r'\b(github|repo|repository)\b',
        r'\b(project progress|project status|project update)\b',
        r'\b(recent commits?|latest commits?)\b',
        r'\b(pull requests?|PRs?)\b',
        r'\b(open issues?)\b',
        r'\b(show.{0,20}progress|what.{0,20}progress|how.{0,20}project)\b',
        r'\b(contributors?|who.{0,10}working)\b',
    ]
    text_lower = text.lower()
    for pattern in triggers:
        if re.search(pattern, text_lower):
            return True
    return False
