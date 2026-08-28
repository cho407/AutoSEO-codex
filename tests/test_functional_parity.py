from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "autoseo"
PARITY = PLUGIN / "data" / "feature-parity.json"
PLAYBOOKS = PLUGIN / "data" / "workflow-playbooks.json"

EXPECTED_CAPABILITIES = {
    "setup",
    "doctor",
    "audit",
    "page",
    "technical",
    "content",
    "content-brief",
    "schema",
    "geo",
    "images",
    "sitemap",
    "plan",
    "competitor-pages",
    "hreflang",
    "programmatic",
    "local",
    "maps",
    "backlinks",
    "cluster",
    "sxo",
    "drift",
    "ecommerce",
    "workflow",
    "google",
    "image-gen",
    "crawl",
    "search-data",
    "authority",
    "bing",
    "ai-citations",
    "ai-visibility",
    "unlighthouse",
}

EXPECTED_PROVIDER_COMMANDS = {
    "authority": {"metrics", "backlinks", "organic", "content"},
    "bing": {"links", "compare", "submit", "submit-batch", "verify-indexnow"},
    "search-data": {
        "serp",
        "serp-images",
        "serp-youtube",
        "youtube",
        "keywords",
        "demand",
        "difficulty",
        "intent",
        "trends",
        "backlinks",
        "competitors",
        "ranked",
        "intersection",
        "traffic",
        "subdomains",
        "trending",
        "onpage",
        "tech",
        "rdap",
        "content",
        "listings",
        "ai-results",
        "ai-mentions",
        "methods",
    },
    "crawl": {"crawl", "map", "scrape", "search"},
    "image-gen": {"og", "hero", "product", "infographic", "custom", "batch"},
    "ai-citations": {"citations", "prompts", "competitors", "alerts"},
    "ai-visibility": {"overview", "serp", "backlinks", "competitors"},
    "workflow": {"overview", "find", "leverage", "optimize", "win", "local", "catalog", "refresh"},
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_functional_parity_catalog_closes_every_baseline_capability() -> None:
    data = _load(PARITY)
    capabilities = {item["id"]: item for item in data["capabilities"]}

    assert data["schema_version"] == 1
    assert data["baseline_version"] == "2.2.5"
    assert set(capabilities) == EXPECTED_CAPABILITIES
    assert all(item["status"] == "supported" for item in capabilities.values())

    for item in capabilities.values():
        skill = PLUGIN / "skills" / item["skill"] / "SKILL.md"
        assert skill.is_file(), item["id"]
        for helper in item.get("helpers", []):
            assert (PLUGIN / "scripts" / helper).is_file(), helper


def test_every_subcommand_is_documented_and_routable() -> None:
    data = _load(PARITY)
    capabilities = {item["id"]: item for item in data["capabilities"]}
    command_guide = (ROOT / "docs" / "COMMANDS.md").read_text(encoding="utf-8")

    for capability, item in capabilities.items():
        skill_text = (PLUGIN / "skills" / item["skill"] / "SKILL.md").read_text(
            encoding="utf-8"
        )
        for command in item["subcommands"]:
            invocation = f"@autoseo {capability} {command}"
            assert invocation in skill_text, invocation
            assert invocation in command_guide, invocation


def test_provider_and_workflow_subcommand_inventories_are_complete() -> None:
    data = _load(PARITY)
    capabilities = {item["id"]: item for item in data["capabilities"]}

    for capability, expected in EXPECTED_PROVIDER_COMMANDS.items():
        item = capabilities[capability]
        assert set(item["subcommands"]) == expected


def test_workflow_catalog_has_all_41_original_autoseo_playbooks() -> None:
    data = _load(PLAYBOOKS)
    playbooks = data["playbooks"]

    assert data["schema_version"] == 1
    assert len(playbooks) == 41
    assert Counter(item["stage"] for item in playbooks) == {
        "find": 5,
        "leverage": 1,
        "optimize": 21,
        "win": 3,
        "local": 11,
    }
    assert len({item["id"] for item in playbooks}) == 41
    for item in playbooks:
        assert item["title"]
        assert item["triggers"]
        assert item["questions"]
        assert item["deliverables"]
        assert item["verification"]


def test_workflow_catalog_cli_validates_the_shipped_catalog() -> None:
    script = PLUGIN / "scripts" / "workflow_catalog.py"
    result = subprocess.run(
        [sys.executable, str(script), "validate", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["playbook_count"] == 41


def test_every_declared_source_is_available_without_a_paid_subscription() -> None:
    data = _load(PLUGIN / "data" / "free-sources.json")
    assert data["schema_version"] == 1
    assert len(data["sources"]) >= 10
    assert all(item["subscription_required"] is False for item in data["sources"])
    assert {item["access"] for item in data["sources"]} <= {
        "public",
        "codex-native",
        "free-account",
        "local",
    }
