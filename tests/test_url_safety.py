from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins" / "autoseo" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from url_safety import is_safe_ip, validate_url  # noqa: E402


def test_public_urls_pass_non_resolving_validation() -> None:
    assert validate_url("https://example.com/path?q=1")
    assert validate_url("http://www.example.org/")
    assert is_safe_ip("93.184.216.34")


def test_private_metadata_and_obfuscated_hosts_are_rejected() -> None:
    unsafe = (
        "http://localhost/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal./",
        "http://2130706433/",
        "http://0x7f000001/",
        "http://0177.0.0.1/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
    )
    for url in unsafe:
        assert not validate_url(url), url


def test_parser_confusion_and_non_http_schemes_are_rejected() -> None:
    unsafe = (
        "file:///etc/passwd",
        "ftp://example.com/file",
        "https://user:password@example.com/",
        "https://example.com\\@127.0.0.1/",
        "https://example.com%5c@127.0.0.1/",
        "https://example.com#@127.0.0.1/",
    )
    for url in unsafe:
        assert not validate_url(url), url
