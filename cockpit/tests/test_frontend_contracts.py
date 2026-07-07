"""
Static frontend contract tests — catch the JSX defect classes pytest can't see
by executing Python code. Born from the 2026-07-07 Admin-tab bug: the nav
button called setTab("admin") but tabFromHash() rejected any tab not in NAV,
so the click silently bounced back. All 143 backend tests were green.

These parse the JSX sources as text. They are deliberately regex-based (no JS
runtime needed) and fail loudly if the anchors they rely on disappear, so a
refactor can't silently disable them.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

JS_DIR = Path(__file__).resolve().parent.parent / "static" / "js"
APP = (JS_DIR / "app.jsx").read_text(encoding="utf-8")
COMPONENTS = (JS_DIR / "components.jsx").read_text(encoding="utf-8")


def _icon_glyphs():
    """Icon names defined in the components.jsx stroke-icon map."""
    body = COMPONENTS.split("function Icon")[1].split("}[name]")[0]
    names = set(re.findall(r"^\s+(\w+):", body, re.M))
    assert len(names) >= 10, "Icon glyph map anchor lost — update this test"
    return names


def _nav_ids():
    """Tab ids declared in NAV_ALL (the filterable main nav)."""
    m = re.search(r"NAV_ALL = \[(.*?)\];", APP, re.S)
    assert m, "NAV_ALL anchor lost — update this test"
    ids = set(re.findall(r'id:\s*"(\w+)"', m.group(1)))
    assert ids, "NAV_ALL parsed empty"
    return ids


def _valid_tab_extras():
    """Tab ids the hash validator accepts beyond NAV (special cases)."""
    m = re.search(r"function _isValidTab\((.*?)\n\}", APP, re.S)
    if not m:
        return set()
    return set(re.findall(r'===\s*"(\w+)"', m.group(1)))


def test_every_routable_tab_is_accepted_by_the_hash_validator():
    """THE Admin-tab bug: a tab reachable via TAB_TO_HASH/setTab must be either
    in NAV_ALL or an explicit _isValidTab special case — otherwise clicking its
    button sets the hash, tabFromHash() rejects it, and the tab bounces back."""
    m = re.search(r"TAB_TO_HASH = \{(.*?)\};", APP, re.S)
    assert m, "TAB_TO_HASH anchor lost — update this test"
    routable = set(re.findall(r"(\w+):", m.group(1)))
    accepted = _nav_ids() | _valid_tab_extras()
    orphans = routable - accepted
    assert not orphans, (
        f"tabs routable via hash but rejected by tabFromHash(): {orphans} — "
        "clicking their nav button will silently bounce back to the first tab"
    )


def test_tab_hash_maps_are_mutually_consistent():
    t2h = dict(
        re.findall(
            r'(\w+):\s*"(#\w+)"',
            re.search(r"TAB_TO_HASH = \{(.*?)\};", APP, re.S).group(1),
        )
    )
    h2t = dict(
        re.findall(
            r'"(#\w+)":\s*"(\w+)"',
            re.search(r"HASH_TO_TAB = \{(.*?)\};", APP, re.S).group(1),
        )
    )
    assert {v: k for k, v in t2h.items()} == h2t, "TAB_TO_HASH and HASH_TO_TAB diverged"


def test_all_icon_names_exist_in_glyph_map():
    """An unknown Icon name renders an empty SVG — invisible button icons."""
    glyphs = _icon_glyphs()
    missing = {}
    for f in JS_DIR.glob("*.jsx"):
        for n in re.findall(r"Icon name=[\"']([\w-]+)", f.read_text(encoding="utf-8")):
            if n not in glyphs:
                missing.setdefault(n, set()).add(f.name)
    assert not missing, f"Icon names without a glyph: {missing}"


def test_admin_view_registered_in_bundle():
    """view-admin.jsx must be in boot.js's JSX_FILES before app.jsx (which
    references <AdminView/>), or the bundle throws at eval time."""
    boot = (JS_DIR / "boot.js").read_text(encoding="utf-8")
    m = re.search(r"JSX_FILES\s*=\s*\[(.*?)\]", boot, re.S)
    files = re.findall(r'"([^"]+)"', m.group(1))
    assert "view-admin.jsx" in files, "view-admin.jsx missing from bundle"
    assert files.index("view-admin.jsx") < files.index("app.jsx")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_jsx_bundle_compiles():
    """Compile the exact bundle boot.js will eval, with the vendored Babel —
    a JSX syntax error in ANY view bricks the whole SPA for every user."""
    script = r"""
const fs = require('fs');
const Babel = require('./static/vendor/babel.min.js');
const boot = fs.readFileSync('static/js/boot.js', 'utf8');
const m = boot.match(/JSX_FILES\s*=\s*\[([^\]]+)\]/);
const files = m[1].match(/"[^"]+"|'[^']+'/g).map(s => s.slice(1, -1));
const code = files.map(f => fs.readFileSync('static/js/' + f, 'utf8')).join('\n;\n');
Babel.transform(code, {presets: ['react']});
new Function(boot);
console.log('OK');
"""
    r = subprocess.run(
        ["node", "-e", script],
        cwd=str(JS_DIR.parent.parent),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0 and "OK" in r.stdout, (
        f"bundle compile failed:\n{r.stderr[:2000]}"
    )
