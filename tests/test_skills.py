from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "autoseo"
SKILLS = PLUGIN / "skills"

REQUIRED_SKILLS = {
    "autoseo",
    "autoseo-ahrefs",
    "autoseo-audit",
    "autoseo-backlinks",
    "autoseo-bing",
    "autoseo-cluster",
    "autoseo-competitor-pages",
    "autoseo-content",
    "autoseo-content-brief",
    "autoseo-dataforseo",
    "autoseo-drift",
    "autoseo-ecommerce",
    "autoseo-firecrawl",
    "autoseo-geo",
    "autoseo-google",
    "autoseo-hreflang",
    "autoseo-image-gen",
    "autoseo-images",
    "autoseo-local",
    "autoseo-maps",
    "autoseo-page",
    "autoseo-performance",
    "autoseo-plan",
    "autoseo-profound",
    "autoseo-programmatic",
    "autoseo-schema",
    "autoseo-seranking",
    "autoseo-sitemap",
    "autoseo-sxo",
    "autoseo-technical",
    "autoseo-unlighthouse",
    "autoseo-visual",
    "autoseo-workflow",
}
TEXT_SUFFIXES = {".md", ".py", ".json", ".txt", ".toml", ".yml", ".yaml"}
IGNORED_PARTS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}


def _frontmatter(text: str) -> tuple[set[str], str]:
    assert text.startswith("---\n")
    end = text.find("\n---\n", 4)
    assert end > 4
    block = text[4:end]
    keys = {
        line.split(":", 1)[0]
        for line in block.splitlines()
        if line and not line[0].isspace() and ":" in line
    }
    name_match = re.search(r"(?m)^name:\s*([^\s]+)\s*$", block)
    assert name_match
    assert re.search(r"(?m)^description:\s*(?:>.*|\S.*)$", block)
    return keys, name_match.group(1)


def test_complete_skill_inventory() -> None:
    actual = {path.name for path in SKILLS.iterdir() if path.is_dir()}
    assert actual == REQUIRED_SKILLS


def test_skill_frontmatter_is_codex_native() -> None:
    for directory in sorted(SKILLS.iterdir()):
        if not directory.is_dir():
            continue
        skill = directory / "SKILL.md"
        assert skill.is_file(), directory.name
        keys, name = _frontmatter(skill.read_text(encoding="utf-8"))
        assert keys == {"name", "description"}, directory.name
        assert name == directory.name


def test_skill_local_markdown_references_exist() -> None:
    pattern = re.compile(r"`((?:\.\./autoseo/)?references/[A-Za-z0-9_./-]+\.md)`")
    for skill_file in SKILLS.glob("*/SKILL.md"):
        text = skill_file.read_text(encoding="utf-8")
        for reference in pattern.findall(text):
            target = (skill_file.parent / reference).resolve()
            assert target.is_relative_to(SKILLS.resolve())
            assert target.is_file(), f"{skill_file.parent.name}: {reference}"


def test_no_upstream_or_assistant_product_names_outside_readmes() -> None:
    banned = re.compile(
        "|".join(("clau" + "de", "anth" + "ropic", "agri" + "ci", "dan" + "iel")),
        re.IGNORECASE,
    )
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if (
            path.name.lower() == "readme.md"
            or any(part in IGNORED_PARTS or part.endswith(".egg-info") for part in path.parts)
        ):
            continue
        assert not banned.search(path.read_text(encoding="utf-8")), path


def test_no_stale_installers_or_cross_product_paths() -> None:
    banned = re.compile(
        r"codex-blog|nanobanana|Codex Banana|\.\.@autoseo|"
        r"extensions/(?:dataforseo|banana)|install\.(?:sh|ps1)",
        re.IGNORECASE,
    )
    for path in PLUGIN.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            assert not banned.search(path.read_text(encoding="utf-8")), path
