"""Small, deterministic editor decision table and content-free result protocol."""
from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

FACTS = frozenset({"publication", "unavailable", "pending", "save", "completed", "verified", "unchanged", "guided"})
ACTIONS = frozenset({"approval-required", "stop", "skip", "reconcile", "record", "guide", "execute"})


@lru_cache(maxsize=1)
def _rules():
    # Only the shipped file is read. A document cannot supply executable rules.
    path = Path(__file__).resolve().parent.parent / "data/editor-decision-tree.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1 or not value.get("rules"):
        raise ValueError("unsupported editor decision table")
    for rule in value["rules"]:
        if set(rule) != {"when", "action"} or rule["action"] not in ACTIONS:
            raise ValueError("unsupported editor decision")
        if not isinstance(rule["when"], dict) or set(rule["when"]) - FACTS:
            raise ValueError("unsupported editor condition")
        if any(type(v) is not bool for v in rule["when"].values()):
            raise ValueError("editor conditions must be boolean")
    return value["rules"]


def decide_operation(**facts) -> str:
    if set(facts) - FACTS or any(type(v) is not bool for v in facts.values()):
        raise ValueError("editor facts must be allowlisted booleans")
    for rule in _rules():
        if all(facts.get(key, False) is value for key, value in rule["when"].items()):
            return rule["action"]
    return "stop"


def operation_decision(checkpoint, operation, driver) -> str:
    """Inspect only facts needed by the rule; normal writes need no extra snapshot.

    bind_surface and record_operation still verify/hash the surface at the start
    and after every operation. A pending operation additionally checks whether
    the surface changed; uncertain saves are never repeated.
    """
    completed = operation["operation_id"] in checkpoint.get("completed_operation_ids", [])
    pending = checkpoint.get("pending_operation_id") == operation["operation_id"]
    save = operation["feature_id"] == "draft-save"
    verified = bool(driver.verify(operation)) if (pending or completed) and not save else False
    unchanged = bool(pending and not verified and not save and hasattr(driver, "snapshot_hash")
                     and driver.snapshot_hash() == checkpoint.get("surface_hash"))
    return decide_operation(completed=completed, pending=pending, save=save,
                            verified=verified, unchanged=unchanged,
                            guided=bool(operation.get("guided")),
                            publication=operation["feature_id"] in {"publish", "schedule-publish"})


def compact_result(checkpoint: dict, *, platform: str, elapsed_ms: float | None = None) -> dict:
    result = {
        "schema_version": 1, "platform": platform,
        "document_id": checkpoint.get("document_id"),
        "save_state": checkpoint.get("save_state", "not-saved"),
        "completed_operations": len(checkpoint.get("completed_operation_ids", [])),
        "publish_state": checkpoint.get("publish_state", "not-requested"),
        "requires_attention": bool(checkpoint.get("pending_operation_id") or checkpoint.get("last_error_type")
                                   or checkpoint.get("save_state") != "acknowledged"),
    }
    # URLs and diagnostic paths stay in the private checkpoint, not model context.
    if elapsed_ms is not None:
        result["editor_elapsed_ms"] = round(elapsed_ms, 2)
    result["diagnostic_count"] = len(checkpoint.get("diagnostic_files", []))
    result["error_type"] = checkpoint.get("last_error_type")
    return result


def capabilities(catalog) -> dict:
    return {"schema_version": 1, "catalog_version": catalog.catalog_version,
            "features": [{"id": item["id"], "status": item["status"],
                          "handler": item.get("handler")}
                         for item in catalog.features.values()],
            "publication": "separate-per-document-approval",
            "rules": _rules()}


def document_plan(document: dict, *, platform: str) -> dict:
    if platform == "naver":
        from naver_document import build_operations
        operations = build_operations(document)
        features = Counter(op["feature_id"] for op in operations)
        guided = sorted({op["feature_id"] for op in operations if op.get("guided")})
    elif platform == "tistory":
        # Upload URLs are unknown until the editor confirms them. Do not invent
        # URLs or produce operation IDs for a source body that does not exist yet.
        features = Counter({"editor-mode": 1, "title": 1, "body-source": 1, "tags": 1, "draft-save": 1})
        if document.get("media"):
            features["media-upload"] = len(document["media"])
        guided = []
    else:
        raise ValueError("unsupported editor platform")
    return {"schema_version": 1, "platform": platform, "document_id": document["document_id"],
            "layout_preset": document.get("layout_preset", "legacy-unspecified"),
            "format": document.get("format", "native-editor"),
            "operations": dict(features), "guided_features": guided,
            "generated_image_checks_required": len(document.get("generated_images", [])),
            "default_boundary": "draft-save", "model_calls_during_normal_execution": 0,
            "publication": "separate-per-document-approval", "writes_performed": False}
