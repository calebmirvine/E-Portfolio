#!/usr/bin/env python3
"""Fetch pinned GitHub repos for calebmirvine into data/projects.json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "projects.json"

GITHUB_USER = "calebmirvine"
EXCLUDE_REPOS = {"E-Portfolio", "e-portfolio"}
FALLBACK_LIMIT = 6

GRAPHQL_URL = "https://api.github.com/graphql"
REST_REPOS_URL = f"https://api.github.com/users/{GITHUB_USER}/repos"

PINNED_QUERY = """
query($login: String!) {
  user(login: $login) {
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes {
        ... on Repository {
          name
          description
          url
          homepageUrl
          stargazerCount
          updatedAt
          isFork
          primaryLanguage { name }
          repositoryTopics(first: 8) {
            nodes { topic { name } }
          }
          owner { login }
        }
      }
    }
  }
}
"""


def resolve_token() -> str | None:
    env = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env:
        return env.strip()
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None


def api_request(
    url: str,
    *,
    token: str | None,
    data: dict | None = None,
) -> dict | list:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{GITHUB_USER}-portfolio-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API HTTP {exc.code}: {detail}") from exc


def normalize_repo(raw: dict, *, source: str) -> dict | None:
    name = raw.get("name") or ""
    if not name or name in EXCLUDE_REPOS or name.lower() in {n.lower() for n in EXCLUDE_REPOS}:
        return None
    if raw.get("isFork") or raw.get("fork"):
        return None

    if source == "graphql":
        language = (raw.get("primaryLanguage") or {}).get("name")
        topics = [
            node["topic"]["name"]
            for node in (raw.get("repositoryTopics") or {}).get("nodes") or []
            if node and node.get("topic")
        ]
        owner = (raw.get("owner") or {}).get("login") or GITHUB_USER
        url = raw.get("url") or f"https://github.com/{owner}/{name}"
        homepage = raw.get("homepageUrl") or ""
        stars = raw.get("stargazerCount") or 0
        updated = raw.get("updatedAt") or ""
        description = raw.get("description") or ""
    else:
        language = raw.get("language")
        topics = raw.get("topics") or []
        owner = (raw.get("owner") or {}).get("login") or GITHUB_USER
        url = raw.get("html_url") or f"https://github.com/{owner}/{name}"
        homepage = raw.get("homepage") or ""
        stars = raw.get("stargazers_count") or 0
        updated = raw.get("updated_at") or ""
        description = raw.get("description") or ""

    image = f"https://opengraph.githubassets.com/1/{owner}/{name}"

    return {
        "name": name,
        "description": description.strip() or "No description provided.",
        "url": url,
        "homepage": homepage.strip(),
        "language": language,
        "stars": stars,
        "topics": topics,
        "updated_at": updated,
        "image": image,
        "owner": owner,
    }


def fetch_pinned(token: str | None) -> list[dict]:
    if not token:
        raise RuntimeError("No token available for GraphQL pinnedItems")

    payload = api_request(
        GRAPHQL_URL,
        token=token,
        data={"query": PINNED_QUERY, "variables": {"login": GITHUB_USER}},
    )
    if "errors" in payload:
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")

    nodes = (
        ((payload.get("data") or {}).get("user") or {})
        .get("pinnedItems", {})
        .get("nodes")
        or []
    )
    projects = []
    for node in nodes:
        if not node:
            continue
        item = normalize_repo(node, source="graphql")
        if item:
            projects.append(item)
    if not projects:
        raise RuntimeError("No pinned repositories returned")
    return projects


def fetch_recent(token: str | None) -> list[dict]:
    query = urllib.parse.urlencode(
        {"sort": "updated", "direction": "desc", "per_page": "30", "type": "owner"}
    )
    payload = api_request(f"{REST_REPOS_URL}?{query}", token=token)
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected REST response: {payload!r}")

    projects = []
    for raw in payload:
        item = normalize_repo(raw, source="rest")
        if item:
            projects.append(item)
        if len(projects) >= FALLBACK_LIMIT:
            break
    if not projects:
        raise RuntimeError("REST fallback returned no repositories")
    return projects


def main() -> int:
    token = resolve_token()
    source = "pinned"
    try:
        projects = fetch_pinned(token)
        print(f"Fetched {len(projects)} pinned repos for {GITHUB_USER}")
    except Exception as exc:
        print(f"Pinned fetch failed ({exc}); using recent public repos fallback", file=sys.stderr)
        source = "recent"
        projects = fetch_recent(token)
        print(f"Fetched {len(projects)} recent repos for {GITHUB_USER}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "user": GITHUB_USER,
        "source": source,
        "projects": projects,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
