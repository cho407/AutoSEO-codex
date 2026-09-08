"""Bounded local UI hints: catalog aliases and frame indexes, never account text."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from editor_safety import digest
from file_safety import read_text_limited


def editor_body(page, platform: str, *, kind: str | None = None):
    """One visible body across frames, shared by readiness and driver access."""
    selectors = {
        "naver": [("naver", ".se-main-container")],
        "tistory": [
            ("basic", ".ProseMirror[contenteditable=true], .tt_article_useless_p_margin[contenteditable=true], #editor [contenteditable=true], body#tinymce[contenteditable=true]"),
            ("codemirror5", ".CodeMirror"),
            ("codemirror6", ".cm-content[contenteditable=true]"),
            ("textarea", "textarea[aria-label*='본문'], textarea[name=content], textarea#editor-textarea"),
        ],
    }
    if platform not in selectors:
        raise ValueError("unsupported editor platform")
    matches = []
    for frame in page.frames:
        if frame != page.main_frame and not frame.frame_element().is_visible():
            continue
        for name, selector in selectors[platform]:
            if kind == "source" and name == "basic" or kind == "basic" and name != "basic":
                continue
            candidates = frame.locator(selector)
            for index in range(candidates.count()):
                node = candidates.nth(index)
                if not node.is_visible():
                    continue
                if name in {"basic", "textarea", "codemirror6"} and not node.is_editable():
                    continue
                if name == "basic" and node.evaluate("node => !!node.closest('.CodeMirror, .cm-editor, .cm-content')"):
                    continue
                if name == "naver" and not node.locator("[contenteditable=true]:visible").count():
                    continue
                matches.append((name, node))
    if len(matches) > 1:
        raise ValueError("editor body is ambiguous across visible controls or frames")
    return matches[0] if matches else None


def editor_ready(page, platform: str, resolver) -> bool:
    try:
        body = editor_body(page, platform)
    except ValueError as exc:
        raise resolver.ambiguous_error(str(exc)) from exc
    if body is None:
        return False
    try:
        _, title = resolver.locate("title")
        return title.is_visible() and title.is_editable()
    except resolver.ambiguous_error:
        raise
    except resolver.ui_error:
        return False


def rich_body_snapshot(root) -> dict:
    """In-memory rendered content and inline formatting; persist only its hash."""
    return root.evaluate("""root => {
        if ([...root.querySelectorAll('img')].some(n => !n.complete || !n.naturalWidth))
            throw new Error('image loading is incomplete');
        const style = node => {
            const s = getComputedStyle(node);
            return [s.fontFamily, s.fontSize, s.fontWeight, s.fontStyle,
                s.textDecorationLine, s.color, s.backgroundColor, s.textAlign,
                s.lineHeight, s.verticalAlign];
        };
        const decorations = node => {
            const lines = new Set();
            // Text decorations paint through descendants without being inherited.
            for (let parent = node.parentElement; parent && root.contains(parent); parent = parent.parentElement) {
                for (const line of getComputedStyle(parent).textDecorationLine.split(' '))
                    if (line && line !== 'none') lines.add(line);
            }
            return [...lines].sort();
        };
        const runs = [], walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
            const node = walker.currentNode;
            if (!node.nodeValue.trim()) continue;
            runs.push({text: node.nodeValue, style: style(node.parentElement), decorations: decorations(node)});
        }
        const elements = [...root.querySelectorAll('p,h1,h2,h3,h4,h5,h6,li,td,th,blockquote,img,a,table,hr,video,iframe')]
            .map(n => ({tag: n.tagName, text: n.innerText || '', style: style(n),
                attributes: ['src','href','alt','title','width','height','colspan','rowspan']
                    .map(key => [key, n.getAttribute(key)])}));
        return {text: root.innerText, elements, runs};
    }""")


def browser_signature(page) -> str:
    try:
        return digest(page.evaluate("navigator.userAgent"))
    except Exception:
        return "unknown"


def ui_signature(page) -> str:
    """Structure only; exclude input values, URLs, free text and frame names."""
    try:
        return digest([frame.evaluate("""() => ({
            editor: !!document.querySelector('.se-main-container, .ProseMirror, .CodeMirror, .cm-content, textarea[name=content]'),
            tiny: !!document.querySelector('body#tinymce[contenteditable=true]'),
            roles: [...document.querySelectorAll('[role]')].map(n => n.getAttribute('role')).sort()
        })""") for frame in page.frames])
    except Exception:
        return "unknown"


def load_map(path: Path, page, catalog) -> dict | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        value = json.loads(read_text_limited(path, extensions={".json"}))
        observed = datetime.fromisoformat(value["observed_at"])
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        origin = urlsplit(str(page.url))
        if (
            value.get("schema_version") != 1 or value.get("catalog_version") != catalog.catalog_version
            or value.get("catalog_hash") != digest(catalog.features)
            or value.get("editor_origin") != f"{origin.scheme}://{origin.hostname}"
            or value.get("browser_signature") != browser_signature(page)
            or value.get("ui_signature") != ui_signature(page)
            or not 0 <= age <= 7 * 86400
            or not isinstance(value.get("features"), dict)
        ):
            return None
        return value
    except (ValueError, TypeError, KeyError, OSError):
        return None


def build_map(page, catalog, resolver, editor_url: str) -> dict:
    origin = urlsplit(editor_url)
    return {
        "schema_version": 1, "catalog_version": catalog.catalog_version,
        "catalog_hash": digest(catalog.features),
        "editor_origin": f"{origin.scheme}://{origin.hostname}",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "browser_signature": browser_signature(page), "ui_signature": ui_signature(page),
        "features": {key: resolver.probe(key) for key in catalog.features},
        "verification": "ui-observed-not-live-verified",
        "note": "Local control hints only. No document text, account data, cookies, or arbitrary selectors.",
    }


def scopes(page, feature: dict):
    """Scope dialogs and toolbars before document controls; include editor frames."""
    frames = getattr(page, "frames", None)
    if not isinstance(frames, list):
        return [(0, "document", page)]
    active = []
    for index, frame in enumerate(frames):
        if frame == page.main_frame or frame.locator(
            ".se-main-container, .ProseMirror, .CodeMirror, .cm-content, "
            "body#tinymce[contenteditable=true], textarea[name=content]"
        ).count():
            active.append((index, frame))
    category = feature.get("category")
    scoped = []
    for index, frame in active:
        if category != "text" and feature["id"] not in {"title", "paragraph", "body-source"}:
            for name, selector in (("dialog", "[role=dialog]:visible"), ("toolbar", "[role=toolbar]:visible")):
                matches = frame.locator(selector)
                for offset in range(matches.count()):
                    scoped.append((index, name, matches.nth(offset)))
    return [*scoped, *((index, "document", frame) for index, frame in active)]


def dialog_scope(page):
    matches = []
    for frame in page.frames:
        dialogs = frame.locator("[role=dialog]:visible")
        matches.extend(dialogs.nth(index) for index in range(dialogs.count()))
    if len(matches) > 1:
        raise ValueError("multiple active editor dialogs; reconcile before continuing")
    return matches[0] if matches else page


def locate(resolver, feature_id: str, *, allow_shortcut: bool = False):
    """Preserve role/name → label → shortcut → DOM; cached hints only rank aliases."""
    feature = resolver.catalog.feature(feature_id)
    contract = feature["locator"]
    names = list(contract.get("names") or ([contract["name"]] if contract.get("name") else []))
    hint = (getattr(resolver, "compatibility", None) or {}).get("features", {}).get(feature_id, {})
    if hint.get("name") in names:
        names.remove(hint["name"])
        names.insert(0, hint["name"])
    candidates = scopes(resolver.page, feature)

    def find(strategy, name, factory):
        for kind in ("dialog", "toolbar", "document"):
            found = []
            for index, scope, root in candidates:
                if scope != kind:
                    continue
                control = factory(root)
                count = resolver._count(control)
                if count > 1:
                    resolver._unique(control, f"{feature_id} in {scope}")
                if count == 1:
                    found.append((index, scope, control))
            if len(found) > 1:
                raise resolver.ambiguous_error(f"multiple frames matched {feature_id}")
            if found:
                index, scope, control = found[0]
                resolver.last_resolution = {"strategy": strategy, "name": name,
                                            "frame_index": index, "scope": scope}
                return strategy, control
        return None

    if contract.get("role"):
        for name in names:
            result = find("role-name", name, lambda root: root.get_by_role(contract["role"], name=name, exact=True))
            if result:
                return result
    for label in contract.get("labels") or []:
        result = find("korean-label", label, lambda root: root.get_by_text(label, exact=True))
        if result:
            return result
    if allow_shortcut and contract.get("shortcut"):
        # Shortcuts need a positively identified focused editor; no global blind presses.
        try:
            focused = resolver.page.evaluate("!!document.activeElement?.closest('[contenteditable=true], textarea, input')")
        except Exception:
            focused = False
        if focused:
            resolver.last_resolution = {"strategy": "shortcut", "name": None}
            return "shortcut", contract["shortcut"]
    if contract.get("dom_fallback"):
        result = find("dom-fallback", None, lambda root: root.locator(contract["dom_fallback"]))
        if result:
            return result
    raise resolver.ui_error(f"no unique editor control found for {feature_id}")
