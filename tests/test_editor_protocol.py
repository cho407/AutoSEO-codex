from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/autoseo/scripts"))

from editor_protocol import (  # noqa: E402
    capabilities,
    compact_result,
    decide_operation,
    document_plan,
)


@pytest.mark.parametrize("facts,expected", [
    ({}, "execute"),
    ({"guided": True}, "guide"),
    ({"pending": True, "verified": True}, "record"),
    ({"pending": True, "unchanged": True}, "execute"),
    ({"pending": True}, "reconcile"),
    ({"pending": True, "save": True, "verified": True}, "reconcile"),
    ({"completed": True, "verified": True}, "skip"),
    ({"completed": True}, "reconcile"),
    ({"completed": True, "save": True}, "skip"),
    ({"publication": True}, "approval-required"),
    ({"unavailable": True}, "stop"),
])
def test_decisions_fail_closed(facts, expected):
    assert decide_operation(**facts) == expected


def test_json_facts_cannot_inject_actions():
    with pytest.raises(ValueError):
        decide_operation(pending="false")
    with pytest.raises(ValueError):
        decide_operation(selector="button")


def test_compact_output_does_not_echo_content_or_full_checkpoint():
    checkpoint = {"document_id": "sample", "save_state": "acknowledged",
                  "completed_operation_ids": [str(i) for i in range(1000)],
                  "source_hash": "hash", "pending_operation_id": None,
                  "diagnostic_files": ["private/path.png"], "body": "PRIVATE DRAFT"}
    result = compact_result(checkpoint, platform="naver")
    assert result["completed_operations"] == 1000
    assert result["requires_attention"] is False
    encoded = json.dumps(result, ensure_ascii=False)
    assert len(encoded.encode()) < 4096
    assert "PRIVATE" not in encoded and "path.png" not in encoded


def test_unknown_save_is_not_reported_as_success():
    assert compact_result({"save_state": "saving", "pending_operation_id": "op"},
                          platform="tistory")["requires_attention"] is True


@pytest.mark.parametrize("platform", ["naver", "tistory"])
def test_complete_catalog_and_plan_without_browser(tmp_path, platform):
    import naver_editor
    import tistory_editor
    from test_naver_editor import _document as naver_doc
    from test_tistory_editor import _document as tistory_doc

    module = naver_editor if platform == "naver" else tistory_editor
    value = naver_doc() if platform == "naver" else tistory_doc(tmp_path, with_media=False)
    result = document_plan(value, platform=platform)
    assert result["writes_performed"] is False
    assert result["operations"]["draft-save"] == 1
    assert value["title"] not in json.dumps(result, ensure_ascii=False)
    catalog = module.FeatureCatalog.load()
    assert {f["id"] for f in capabilities(catalog)["features"]} == set(catalog.features)
