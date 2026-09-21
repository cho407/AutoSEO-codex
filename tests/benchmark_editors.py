"""Opt-in local fixture benchmark; never opens an account or publishes.

Run: .venv/bin/python tests/benchmark_editors.py --runs 10 --warmup 2
Compare the same machine/runtime/fixture before and after a change. Times exclude
browser startup, login, content generation and real network/media transfer.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(os.environ.get("AUTOSEO_BENCH_PLUGIN_ROOT", ROOT / "plugins/autoseo")) / "scripts"))

import naver_editor  # noqa: E402
import tistory_editor  # noqa: E402


def run(runs=10, warmup=2, platform_filter="all"):
    from PIL import Image
    from playwright.sync_api import sync_playwright

    platforms = [p for p in ("naver", "tistory") if platform_filter in {"all", p}]
    samples = {f"{platform}/{case}": [] for platform in platforms
               for case in ("article", "title")}
    with tempfile.TemporaryDirectory(prefix="autoseo-editor-bench-") as directory, sync_playwright() as pw:
        root = Path(directory)
        asset = root / "sample.png"
        Image.new("RGB", (1600, 900), "#e4ece9").save(asset)
        second_asset = root / "sample-two.png"
        Image.new("RGB", (1600, 900), "#e4e9ec").save(second_asset)
        assets = [asset, second_asset]
        browser = pw.chromium.launch(headless=True)
        try:
            for platform, module in (("naver", naver_editor), ("tistory", tistory_editor)):
                if platform not in platforms:
                    continue
                for case in ("article", "title"):
                    for iteration in range(warmup + runs):
                        page = browser.new_page()
                        page.route("https://**", lambda route: route.fulfill(body=asset.read_bytes(), content_type="image/png"))
                        page.goto((ROOT / f"tests/fixtures/{platform}_editor.html").as_uri())
                        if platform == "tistory":
                            page.evaluate("""() => {
                                let serial = 0;
                                document.querySelector('#image-input').addEventListener('change', () => {
                                    const images = document.querySelectorAll('#basic-body img');
                                    images[images.length - 1].src = `https://blog.kakaocdn.net/dn/local-fixture/uploaded-${++serial}.jpg`;
                                });
                            }""")
                        # Normalize legacy Cmd+End caret semantics on macOS for
                        # both runs. Otherwise the old 20-block run cannot finish.
                        page.evaluate("""() => document.addEventListener('keydown', e => {
                            if (e.key !== 'End' || !(e.ctrlKey || e.metaKey) || !e.target.isContentEditable) return;
                            e.preventDefault();
                            const lines = e.target.querySelectorAll('p');
                            const range = document.createRange();
                            range.selectNodeContents(lines[lines.length - 1] || e.target); range.collapse(false);
                            const s = getSelection(); s.removeAllRanges(); s.addRange(range);
                        })""")
                        data = root / f"{platform}-{case}-{iteration}"
                        catalog = module.FeatureCatalog.load()
                        driver_type = getattr(module, "PlaywrightNaverDriver" if platform == "naver" else "PlaywrightTistoryDriver")
                        driver = driver_type(page, catalog=catalog, data_dir=data)
                        document = {
                            "schema_version": 1, "document_id": "benchmark",
                            "title": "일상 기록을 위한 블로그 작성 안내",
                            "blocks": [{"id": f"p-{i}", "type": "paragraph",
                                        "text": f"{i + 1}번째 문단: 주제에 맞는 근거와 설명을 정확하게 전달합니다.",
                                        **({"style": {"bold": i % 3 == 0, "alignment": "left"}}
                                           if platform == "naver" else {})} for i in range(20)],
                            "tags": ["블로그", "글쓰기", "콘텐츠", "정리", "안내"],
                            "publish_settings": {"mode": "draft"},
                        }
                        if platform == "naver":
                            document["blocks"] += [{"id": f"photo-{i}", "type": "photo", "path": str(assets[i])} for i in range(2)]
                        else:
                            document["blocks"] += [{"id": f"photo-{i}", "type": "image", "media_id": f"m-{i}"} for i in range(2)]
                            document["media"] = [{"id": f"m-{i}", "path": str(assets[i]), "alt": "테스트 색상 면"} for i in range(2)]
                        start = time.perf_counter()
                        if case == "title":
                            operation = {"feature_id": "title", "operation_id": "title-only", "payload": {"text": document["title"]}}
                            driver.execute(operation)
                            assert driver.verify(operation)
                        elif platform == "naver":
                            result = module.EditorAutomation(module.CheckpointStore(data)).apply(document, driver)
                            assert result["save_state"] == "acknowledged"
                        else:
                            result = module.TistoryEditorAutomation(module.CheckpointStore(data)).apply(
                                document, driver, prepared_media={f"m-{i}": assets[i] for i in range(2)})
                            assert result["save_state"] == "acknowledged"
                        elapsed = (time.perf_counter() - start) * 1000
                        if iteration >= warmup:
                            samples[f"{platform}/{case}"].append(round(elapsed, 2))
                        assert page.evaluate("window.publishClicks || 0") == 0
                        page.close()
        finally:
            browser.close()
    return {"schema_version": 1, "runs": runs, "warmup": warmup,
            "scope": "local fixtures; no LLM, account, publication or network latency",
            "samples_ms": samples,
            "median_ms": {key: round(statistics.median(values), 2) for key, values in samples.items()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--platform", choices=["all", "naver", "tistory"], default="all")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.runs <= 30 or not 0 <= args.warmup <= 5:
        parser.error("runs must be 1-30 and warmup 0-5")
    report = json.dumps(run(args.runs, args.warmup, args.platform), ensure_ascii=False, indent=2)
    if args.output:
        from file_safety import write_text_safely
        write_text_safely(args.output, report, extensions={".json"})
    print(report)
