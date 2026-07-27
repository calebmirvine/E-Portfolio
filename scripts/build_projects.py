#!/usr/bin/env python3
"""Inject GitHub project cards into index.html from data/projects.json."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "projects.json"
OVERRIDES_PATH = ROOT / "data" / "project_overrides.yaml"
IMAGES_DIR = ROOT / "images" / "projects"
HTML_PATH = ROOT / "index.html"
TEMPLATES = ROOT / "templates"

PROJECTS_START = "<!-- PROJECTS:START -->"
PROJECTS_END = "<!-- PROJECTS:END -->"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def load_projects() -> dict:
    if not JSON_PATH.exists():
        raise SystemExit(
            f"Missing {JSON_PATH.relative_to(ROOT)}. Run scripts/fetch_github_projects.py first."
        )
    with JSON_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "projects" not in data:
        raise SystemExit("projects.json must contain a top-level 'projects' list")
    return data


def load_overrides() -> dict:
    if not OVERRIDES_PATH.exists():
        return {}
    with OVERRIDES_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SystemExit("project_overrides.yaml must be a mapping of repo name → fields")
    return data


def find_local_image(repo_name: str) -> str | None:
    """Return a site-relative path if images/projects/<RepoName>.* exists."""
    for ext in IMAGE_EXTENSIONS:
        candidate = IMAGES_DIR / f"{repo_name}{ext}"
        if candidate.is_file():
            return f"images/projects/{repo_name}{ext}"
    # Case-insensitive fallback
    if IMAGES_DIR.is_dir():
        lower = repo_name.lower()
        for path in IMAGES_DIR.iterdir():
            if path.suffix.lower() in IMAGE_EXTENSIONS and path.stem.lower() == lower:
                return f"images/projects/{path.name}"
    return None


def resolve_image(project: dict, override: dict) -> str:
    # 1) Explicit override path
    override_image = (override.get("image") or "").strip()
    if override_image:
        local = ROOT / override_image
        if local.is_file():
            return override_image
        print(
            f"Warning: override image not found for {project.get('name')}: {override_image}",
            file=sys.stderr,
        )

    # 2) Convention: images/projects/<RepoName>.*
    local_image = find_local_image(str(project.get("name") or ""))
    if local_image:
        return local_image

    # 3) GitHub Open Graph preview
    return project.get("image") or ""


def apply_overrides(data: dict) -> dict:
    overrides = load_overrides()
    projects = []
    for project in data.get("projects") or []:
        name = project.get("name") or ""
        override = overrides.get(name) or {}
        if not isinstance(override, dict):
            override = {}

        merged = dict(project)
        if override.get("title"):
            merged["display_name"] = str(override["title"]).strip()
        else:
            merged["display_name"] = name

        if override.get("description"):
            merged["description"] = str(override["description"]).strip()

        merged["image"] = resolve_image(project, override)
        merged["image_is_local"] = not str(merged["image"]).startswith("http")
        projects.append(merged)

    data = dict(data)
    data["projects"] = projects
    return data


def render_section(data: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env.get_template("projects_section.html.j2").render(
        projects=data.get("projects") or [],
        user=data.get("user") or "calebmirvine",
        source=data.get("source") or "pinned",
    )


def update_html(section: str) -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    if PROJECTS_START not in html or PROJECTS_END not in html:
        raise SystemExit(
            f"{HTML_PATH.name} is missing {PROJECTS_START} / {PROJECTS_END} markers"
        )
    pattern = re.compile(
        r"[ \t]*" + re.escape(PROJECTS_START) + r".*?" + re.escape(PROJECTS_END),
        re.DOTALL,
    )
    indented = "\n".join(
        ("            " + line if line else line)
        for line in section.strip("\n").splitlines()
    )
    updated, count = pattern.subn(indented, html, count=1)
    if count != 1:
        raise SystemExit("Failed to replace projects section in index.html")
    HTML_PATH.write_text(updated, encoding="utf-8")
    print(f"Updated projects section in {HTML_PATH.relative_to(ROOT)}")


def main() -> int:
    data = apply_overrides(load_projects())
    update_html(render_section(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
