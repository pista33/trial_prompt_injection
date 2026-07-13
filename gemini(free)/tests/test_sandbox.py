from pathlib import Path

import pytest

from gemini_injection_lab.sandbox import SandboxViolation, SecureDocumentStore


def test_reads_regular_utf8_file(tmp_path: Path):
    root = tmp_path / "sandbox"
    root.mkdir()
    (root / "doc.txt").write_text("安全な文書", encoding="utf-8")
    text, raw = SecureDocumentStore(root).read_registered("doc.txt")
    assert text == "安全な文書"
    assert raw == "安全な文書".encode()


@pytest.mark.parametrize(
    "path", ["../secret.txt", "/tmp/secret.txt", "a/b.txt", "..\\secret.txt", "", ".."]
)
def test_rejects_unregistered_path_forms(tmp_path: Path, path: str):
    root = tmp_path / "sandbox"
    root.mkdir()
    with pytest.raises(SandboxViolation):
        SecureDocumentStore(root).read_registered(path)


def test_rejects_symbolic_link(tmp_path: Path):
    root = tmp_path / "sandbox"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (root / "link.txt").symlink_to(outside)
    with pytest.raises(SandboxViolation):
        SecureDocumentStore(root).read_registered("link.txt")


def test_rejects_oversized_and_non_utf8(tmp_path: Path):
    root = tmp_path / "sandbox"
    root.mkdir()
    (root / "large.txt").write_bytes(b"12345")
    (root / "binary.txt").write_bytes(b"\xff")
    store = SecureDocumentStore(root, max_bytes=4)
    with pytest.raises(SandboxViolation):
        store.read_registered("large.txt")
    with pytest.raises(SandboxViolation):
        SecureDocumentStore(root).read_registered("binary.txt")
