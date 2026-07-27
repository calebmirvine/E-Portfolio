Made with HTML, CSS, and Bootstrap, for my final Project for Camosun's ICS 118 - Web Foundamentals.

A page that I can build onto in the future as further my skills, and can present to others about what I can accomplish with my Web Dev skills.
Key things about the webpage is the alternate Winter ❄️ theming, Web3Forms Mail Form API, and SVGs, and their animations.

## Resume (living YAML + role profiles)

Master inventory: [`resume/content.yaml`](resume/content.yaml)  
Role overlays: [`resume/profiles/`](resume/profiles/) (e.g. `default`, `r8dius-qe`)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt
python scripts/build_resume.py                    # default profile → site PDF + HTML
python scripts/build_resume.py --profile r8dius-qe  # role tailor → LaTeX only
latexmk -pdf Calebs_Resume.tex && mv Calebs_Resume.pdf Resume-r8dius-qe.pdf
```

That updates `Calebs_Resume.tex` (and for `default`, the `#resume` section in `index.html`). For the site PDF, build `default` then `latexmk -pdf Calebs_Resume.tex` and rename to `Resume.pdf`. Role-specific PDFs (e.g. `Resume-r8dius-qe.pdf`) are local application artifacts.

On push to `main`/`master` (when resume sources change), GitHub Actions regenerates the `.tex`, HTML section, and `Resume.pdf` from the `default` profile.

## Projects (GitHub pins)

The Projects section mirrors your [pinned repos](https://github.com/calebmirvine) on GitHub.

```bash
source .venv/bin/activate
python scripts/fetch_github_projects.py   # needs GITHUB_TOKEN or `gh auth login`
python scripts/build_projects.py
```

That writes `data/projects.json` and updates the `#projects` cards in `index.html`. CI also refreshes weekly (and on workflow dispatch).

### Project photos

Cards use the GitHub Open Graph image by default. To use your own screenshot:

1. Drop a file at `images/projects/<RepoName>.png` (also `.jpg` / `.webp` / `.gif`)
2. Re-run `python scripts/build_projects.py`

Or set a custom path / title in [`data/project_overrides.yaml`](data/project_overrides.yaml):

```yaml
MNIST-NN:
  image: images/NeNe.png
  title: MNIST Neural Net
```

