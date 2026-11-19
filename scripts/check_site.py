"""Quality gate for the generated site: fails the pipeline on broken output.

Checks: index.html exists, every HTML page has <title>, lang and viewport,
images have alt text, and every relative link/src points to a real file.
"""
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.problems = [], []
        self.has_title = self.has_viewport = self.has_lang = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.has_lang = True
        if tag == "title":
            self.has_title = True
        if tag == "meta" and a.get("name") == "viewport":
            self.has_viewport = True
        if tag == "img" and "alt" not in a:
            self.problems.append(f"<img src={a.get('src')!r}> has no alt text")
        for key in ("href", "src"):
            if a.get(key):
                self.refs.append(a[key])


def find_problems(site_dir: str = "site") -> list[str]:
    """Return a list of human-readable problems (empty list = pass)."""
    root = Path(site_dir)
    errors = []
    if not (root / "index.html").is_file():
        errors.append("missing index.html")

    for page in root.rglob("*.html"):
        p = PageParser()
        p.feed(page.read_text(encoding="utf-8"))
        name = page.relative_to(root)
        if not p.has_title:
            errors.append(f"{name}: missing <title>")
        if not p.has_viewport:
            errors.append(f"{name}: missing viewport meta (not mobile-friendly)")
        if not p.has_lang:
            errors.append(f"{name}: <html> has no lang attribute")
        errors += [f"{name}: {msg}" for msg in p.problems]
        for ref in p.refs:
            u = urlparse(ref)
            if u.scheme or ref.startswith(("#", "//")) or not u.path:
                continue
            target = (page.parent / u.path).resolve()
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                errors.append(f"{name}: broken link -> {ref}")
    return errors


def main(site_dir: str = "site") -> int:
    root = Path(site_dir)
    errors = find_problems(site_dir)
    if errors:
        print("Site check FAILED:")
        print("\n".join(f"  - {e}" for e in errors))
        return 1
    print(f"Site check passed ({len(list(root.rglob('*.html')))} pages).")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
