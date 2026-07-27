#!/usr/bin/env python3
"""Generate Calebs_Resume.tex and the index.html resume section from resume/ sources."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
RESUME_DIR = ROOT / "resume"
CONTENT_PATH = RESUME_DIR / "content.yaml"
PROFILES_DIR = RESUME_DIR / "profiles"
TEMPLATES = RESUME_DIR / "templates"
TEX_OUT = ROOT / "Calebs_Resume.tex"
HTML_PATH = ROOT / "index.html"

RESUME_START = "<!-- RESUME:START -->"
RESUME_END = "<!-- RESUME:END -->"


def latex_escape(value: object) -> str:
    """Escape special LaTeX characters in plain text."""
    if value is None:
        return ""
    text = str(value)
    # Backslash must be first
    replacements = (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def latex_braced(value: object) -> str:
    """Escape text and wrap in a LaTeX argument group {...}."""
    return "{" + latex_escape(value) + "}"


def latex_href(value: object) -> str:
    """Build \\href{url}{display} from a (url, display) pair."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise TypeError("href filter expects a (url, display) pair")
    url, display = value
    return f"\\href{{{url}}}{{{latex_escape(display)}}}"


def html_dates(value: object) -> str:
    """Convert LaTeX en-dash dates to a web-friendly form."""
    if value is None:
        return ""
    return str(value).replace(" -- ", " – ").replace("--", "–")


def tel_href(value: object) -> str:
    """Build a tel: href from a display phone number."""
    if value is None:
        return ""
    digits = re.sub(r"[^\d+]", "", str(value))
    if digits and not digits.startswith("+"):
        # Assume North American numbers without country code
        if len(re.sub(r"\D", "", digits)) == 10:
            digits = "+1" + re.sub(r"\D", "", digits)
    return digits


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a mapping at the top level")
    return data


def index_by_id(items: list[dict], label: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in items:
        item_id = item.get("id")
        if not item_id:
            raise SystemExit(f"Missing id on {label} entry: {item!r}")
        if item_id in out:
            raise SystemExit(f"Duplicate {label} id: {item_id}")
        out[str(item_id)] = item
    return out


def select_bullets(
    source_bullets: list[dict],
    bullet_ids: list[str] | None,
    *,
    context: str,
) -> list[Any]:
    """Return bullets in profile order; flatten experience/project bullets to text."""
    by_id = index_by_id(source_bullets, f"{context} bullet")
    if bullet_ids is None:
        selected = source_bullets
    else:
        selected = []
        for bid in bullet_ids:
            if bid not in by_id:
                raise SystemExit(f"Unknown bullet id '{bid}' in {context}")
            selected.append(by_id[bid])

    flattened: list[Any] = []
    for bullet in selected:
        if "prefix" in bullet:
            flattened.append(
                {
                    "prefix": bullet.get("prefix"),
                    "text": bullet["text"],
                }
            )
        else:
            flattened.append(bullet["text"])
    return flattened


def merge_resume(content: dict, profile: dict) -> dict:
    """Merge master inventory with a role profile into render-ready data."""
    include = profile.get("include") or {}
    if not isinstance(include, dict):
        raise SystemExit("profile include must be a mapping")

    skills_by_id = index_by_id(content.get("skills") or [], "skill")
    skill_ids = profile.get("skills")
    if not isinstance(skill_ids, list):
        raise SystemExit("profile must define skills as a list of skill ids")
    skills = []
    for sid in skill_ids:
        if sid not in skills_by_id:
            raise SystemExit(f"Unknown skill id in profile: {sid}")
        skill = skills_by_id[sid]
        skills.append({"category": skill["category"], "detail": skill["detail"]})

    education_out = []
    edu_include = include.get("education")
    all_edu_bullet_ids: set[str] = set()
    for edu in content.get("education") or []:
        for bullet in edu.get("bullets") or []:
            if bullet.get("id"):
                all_edu_bullet_ids.add(str(bullet["id"]))
    if isinstance(edu_include, list):
        for bid in edu_include:
            if bid not in all_edu_bullet_ids:
                raise SystemExit(f"Unknown education bullet id in profile: {bid}")

    for edu in content.get("education") or []:
        edu_id = edu.get("id", "education")
        source_bullets = edu.get("bullets") or []
        if isinstance(edu_include, list):
            by_id = index_by_id(source_bullets, f"education:{edu_id} bullet")
            ordered_ids = [bid for bid in edu_include if bid in by_id]
            bullets = select_bullets(
                source_bullets, ordered_ids, context=f"education:{edu_id}"
            )
        else:
            bullets = select_bullets(source_bullets, None, context=f"education:{edu_id}")
        if isinstance(edu_include, list) and not bullets:
            continue
        education_out.append(
            {
                "institution": edu["institution"],
                "location": edu["location"],
                "degree": edu["degree"],
                "dates": edu["dates"],
                "bullets": bullets,
            }
        )

    jobs_by_id = index_by_id(content.get("experience") or [], "experience")
    exp_include = include.get("experience") or {}
    if not isinstance(exp_include, dict):
        raise SystemExit("include.experience must be a mapping of job id -> bullet ids")

    experience_out = []
    # Preserve profile job order when include lists jobs; else master order
    job_order = list(exp_include.keys()) if exp_include else list(jobs_by_id.keys())
    for job_id in job_order:
        if job_id not in jobs_by_id:
            raise SystemExit(f"Unknown experience id in profile: {job_id}")
        job = jobs_by_id[job_id]
        bullet_ids = exp_include.get(job_id) if exp_include else None
        if exp_include and bullet_ids is None:
            continue
        if isinstance(bullet_ids, list) and len(bullet_ids) == 0:
            continue
        bullets = select_bullets(
            job.get("bullets") or [],
            bullet_ids if isinstance(bullet_ids, list) else None,
            context=f"experience:{job_id}",
        )
        if not bullets:
            continue
        experience_out.append(
            {
                "title": job["title"],
                "dates": job["dates"],
                "organization": job["organization"],
                "location": job["location"],
                "bullets": bullets,
            }
        )

    projects_by_id = index_by_id(content.get("projects") or [], "project")
    proj_include = include.get("projects") or {}
    if not isinstance(proj_include, dict):
        raise SystemExit("include.projects must be a mapping of project id -> bullet ids")

    projects_out = []
    proj_order = list(proj_include.keys()) if proj_include else list(projects_by_id.keys())
    for proj_id in proj_order:
        if proj_id not in projects_by_id:
            raise SystemExit(f"Unknown project id in profile: {proj_id}")
        project = projects_by_id[proj_id]
        bullet_ids = proj_include.get(proj_id) if proj_include else None
        if proj_include and bullet_ids is None:
            continue
        if isinstance(bullet_ids, list) and len(bullet_ids) == 0:
            continue
        bullets = select_bullets(
            project.get("bullets") or [],
            bullet_ids if isinstance(bullet_ids, list) else None,
            context=f"project:{proj_id}",
        )
        if not bullets:
            continue
        projects_out.append(
            {
                "name": project["name"],
                "tech": project["tech"],
                "dates": project["dates"],
                "bullets": bullets,
            }
        )

    for key in ("objective", "qualifications"):
        if key not in profile:
            raise SystemExit(f"profile missing required key: {key}")

    show_interests = profile.get("show_interests", True)
    interests = content.get("interests", "") if show_interests else ""

    return {
        "basics": content["basics"],
        "objective": profile["objective"],
        "qualifications": profile["qualifications"],
        "skills": skills,
        "education": education_out,
        "experience": experience_out,
        "projects": projects_out,
        "interests": interests,
        "show_interests": bool(show_interests and interests),
    }


def load_merged(profile_name: str) -> dict:
    if not CONTENT_PATH.exists():
        raise SystemExit(f"Missing {CONTENT_PATH}")
    profile_path = PROFILES_DIR / f"{profile_name}.yaml"
    if not profile_path.exists():
        available = sorted(p.stem for p in PROFILES_DIR.glob("*.yaml"))
        raise SystemExit(
            f"Missing profile {profile_path}. Available: {', '.join(available) or '(none)'}"
        )
    return merge_resume(load_yaml(CONTENT_PATH), load_yaml(profile_path))


def make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        # HTML template uses |e explicitly; LaTeX must not be autoescaped.
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["latex"] = latex_escape
    env.filters["braced"] = latex_braced
    env.filters["href"] = latex_href
    env.filters["html_dates"] = html_dates
    env.filters["tel"] = tel_href
    return env


def render_tex(env: Environment, data: dict) -> str:
    return env.get_template("resume.tex.j2").render(**data)


def render_html_section(env: Environment, data: dict) -> str:
    # Template already includes START/END markers
    rendered = env.get_template("resume_section.html.j2").render(**data)
    # Normalize leading whitespace so repeated builds stay stable
    lines = rendered.strip("\n").splitlines()
    return "\n".join(lines) + "\n"


def write_tex(content: str) -> None:
    TEX_OUT.write_text(content, encoding="utf-8")
    print(f"Wrote {TEX_OUT.relative_to(ROOT)}")


def update_html(section: str) -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    if RESUME_START not in html or RESUME_END not in html:
        raise SystemExit(
            f"{HTML_PATH.name} is missing {RESUME_START} / {RESUME_END} markers"
        )
    pattern = re.compile(
        r"[ \t]*" + re.escape(RESUME_START) + r".*?" + re.escape(RESUME_END),
        re.DOTALL,
    )
    # Keep resume block indented inside the container
    indented = "\n".join(
        ("            " + line if line else line) for line in section.strip("\n").splitlines()
    )
    updated, count = pattern.subn(indented, html, count=1)
    if count != 1:
        raise SystemExit("Failed to replace resume section in index.html")
    HTML_PATH.write_text(updated, encoding="utf-8")
    print(f"Updated resume section in {HTML_PATH.relative_to(ROOT)}")


def ensure_markers() -> None:
    """If markers are missing, wrap the existing resume content once."""
    html = HTML_PATH.read_text(encoding="utf-8")
    if RESUME_START in html and RESUME_END in html:
        return

    # Insert markers around the resume body (header through download button)
    start_anchor = "            <!-- Resume Start-->"
    if start_anchor not in html:
        raise SystemExit(
            "Cannot auto-insert markers: expected '<!-- Resume Start-->' in index.html"
        )
    # There are two "End of Resume Section" comments; place END after the download block
    download_end = (
        '            <div class="text-center py-5">\n'
        '                <a href="Resume.pdf" class="btn btn-primary btn-lg" download="Resume.pdf">\n'
        '                    <i class="bi bi-download"></i> Download</a>\n'
        "            </div>\n"
        "            <!-- End of Resume Section -->"
    )
    if download_end not in html:
        raise SystemExit("Cannot auto-insert markers: download block not found")

    html = html.replace(start_anchor, f"{RESUME_START}\n{start_anchor}", 1)
    html = html.replace(download_end, f"{download_end}\n{RESUME_END}", 1)
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Inserted {RESUME_START}/{RESUME_END} markers into index.html")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        default="default",
        help="Profile name under resume/profiles/ (default: default)",
    )
    parser.add_argument(
        "--ensure-markers",
        action="store_true",
        help="Insert RESUME markers into index.html if missing, then build",
    )
    parser.add_argument(
        "--tex-only",
        action="store_true",
        help="Write LaTeX only; skip updating index.html (for non-default profiles)",
    )
    args = parser.parse_args()

    if args.ensure_markers:
        ensure_markers()

    try:
        data = load_merged(args.profile)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 1

    env = make_env()
    write_tex(render_tex(env, data))
    if args.tex_only or args.profile != "default":
        if args.profile != "default" and not args.tex_only:
            print(
                f"Profile '{args.profile}': wrote LaTeX only "
                "(HTML/site uses --profile default)."
            )
    else:
        update_html(render_html_section(env, data))
    print(f"Built profile: {args.profile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
