from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "autoseo"


def test_plugin_manifest_and_assets() -> None:
    manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "autoseo"
    assert manifest["version"] == "0.1.0"
    assert manifest["license"] == "MIT"
    assert manifest["repository"] == "https://github.com/HarrisonCho407/AutoSEO-codex"
    assert manifest["skills"] == "./skills/"

    interface = manifest["interface"]
    assert interface["displayName"] == "AutoSEO"
    assert 1 <= len(interface["defaultPrompt"]) <= 5
    assert interface["capabilities"] == ["Interactive", "Read", "Write"]
    for key in ("composerIcon", "logo"):
        asset = (PLUGIN / interface[key]).resolve()
        assert asset.is_file()
        assert asset.is_relative_to(PLUGIN.resolve())


def test_repository_marketplace_points_to_plugin() -> None:
    marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
    assert marketplace["name"] == "autoseo"
    assert marketplace["interface"]["displayName"] == "AutoSEO"
    assert len(marketplace["plugins"]) == 1
    entry = marketplace["plugins"][0]
    assert entry["name"] == "autoseo"
    assert entry["source"] == {"source": "local", "path": "./plugins/autoseo"}
    assert entry["policy"]["installation"] == "AVAILABLE"


def test_public_policy_documents_exist() -> None:
    for name in ("LICENSE", "README.md", "SECURITY.md", "PRIVACY.md", "TERMS.md"):
        assert (ROOT / name).is_file(), name
    for name in ("icon.svg", "logo.svg"):
        assert (PLUGIN / "assets" / name).stat().st_size > 100
