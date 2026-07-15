from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from gemini_injection_lab.cli import main
from gemini_injection_lab.client import GeminiInteractionsClient
from gemini_injection_lab.custom_input import (
    CustomInputError,
    CustomInputStore,
    PDF_LIMIT,
    build_api_input,
)
from gemini_injection_lab.file_runner import run_file_live
from gemini_injection_lab.recorder import JsonlRecorder


class FakeInteractions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeSdk:
    def __init__(self, response):
        self.interactions = FakeInteractions(response)


def response(function_call=False):
    steps = [
        SimpleNamespace(type="model_output", id="m", status="done", text="answer")
    ]
    if function_call:
        steps.append(SimpleNamespace(
            type="function_call", id="f", status="done", name="unexpected",
            arguments={"sensitive": "not-shared"},
        ))
    return SimpleNamespace(
        status="completed", model="returned-model", steps=steps,
        usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
    )


@pytest.mark.parametrize(("name", "content"), [
    ("input.txt", "a\r\n日本語\n".encode()),
    ("input.md", "# title\r\nbody".encode()),
])
def test_text_is_passed_unchanged(tmp_path, name, content):
    (tmp_path / name).write_bytes(content)
    item = CustomInputStore(tmp_path).read(name)
    sdk = FakeSdk(response())
    run_file_live(item, "", "requested", GeminiInteractionsClient(sdk))
    assert sdk.interactions.calls[0]["input"].encode("utf-8") == content
    assert sdk.interactions.calls[0] == {
        "model": "requested", "input": content.decode(), "store": False
    }


def test_pdf_builds_inline_document_and_instruction(tmp_path):
    raw = b"%PDF-1.7\nfictional"
    (tmp_path / "a.pdf").write_bytes(raw)
    item = CustomInputStore(tmp_path).read("a.pdf")
    built = build_api_input(item, "instruction")
    assert built == [
        {"type": "document", "data": "JVBERi0xLjcKZmljdGlvbmFs", "mime_type": "application/pdf"},
        {"type": "text", "text": "instruction"},
    ]


def test_file_log_excludes_input_and_function_arguments(tmp_path):
    secret_text = "SYNTHETIC_INPUT_MARKER"
    (tmp_path / "a.txt").write_text(secret_text, encoding="utf-8")
    item = CustomInputStore(tmp_path).read("a.txt")
    record = run_file_live(item, "", "requested", GeminiInteractionsClient(FakeSdk(response(True))))
    log = tmp_path / "record.jsonl"
    with JsonlRecorder(log) as recorder:
        recorder.append(record)
    saved = log.read_text()
    assert secret_text not in saved
    assert "not-shared" not in saved
    assert record.unexpected_function_names == ["unexpected"]
    assert record.manual_review_required
    assert record.returned_model == "returned-model"
    assert record.response_text == "answer"


def test_pdf_log_excludes_base64(tmp_path):
    raw = b"%PDF-1.7\nfictional"
    (tmp_path / "a.pdf").write_bytes(raw)
    item = CustomInputStore(tmp_path).read("a.pdf")
    record = run_file_live(item, "instruction", "requested", GeminiInteractionsClient(FakeSdk(response())))
    log = tmp_path / "record.jsonl"
    with JsonlRecorder(log) as recorder:
        recorder.append(record)
    assert "JVBER" not in log.read_text()


@pytest.mark.parametrize("bad", ["/tmp/a.txt", "../a.txt", "x/../../a.txt", "", "a.txt\x00"])
def test_rejects_unsafe_paths(tmp_path, bad):
    with pytest.raises(CustomInputError):
        CustomInputStore(tmp_path).read(bad)


def test_rejects_file_and_parent_symlinks(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    (tmp_path / "link.txt").symlink_to(outside)
    with pytest.raises(CustomInputError):
        CustomInputStore(tmp_path).read("link.txt")
    real = tmp_path / "real"
    real.mkdir()
    (real / "x.txt").write_text("x")
    (tmp_path / "linked-dir").symlink_to(real, target_is_directory=True)
    with pytest.raises(CustomInputError):
        CustomInputStore(tmp_path).read("linked-dir/x.txt")


def test_rejects_special_file_without_blocking(tmp_path):
    fifo = tmp_path / "pipe.txt"
    os.mkfifo(fifo)
    with pytest.raises(CustomInputError):
        CustomInputStore(tmp_path).read("pipe.txt")


@pytest.mark.parametrize(("name", "content"), [
    ("bad.txt", b"\xff"),
    ("bad.pdf", b"not-pdf"),
    ("bad.csv", b"x"),
])
def test_rejects_invalid_content_or_format(tmp_path, name, content):
    (tmp_path / name).write_bytes(content)
    with pytest.raises(CustomInputError):
        CustomInputStore(tmp_path).read(name)


def test_rejects_oversize_before_read(tmp_path, monkeypatch):
    path = tmp_path / "big.pdf"
    with path.open("wb") as handle:
        handle.truncate(PDF_LIMIT + 1)
    read_called = False
    original = os.read
    def tracked(*args):
        nonlocal read_called
        read_called = True
        return original(*args)
    monkeypatch.setattr(os, "read", tracked)
    with pytest.raises(CustomInputError):
        CustomInputStore(tmp_path).read("big.pdf")
    assert not read_called


def test_dry_run_does_not_construct_client(monkeypatch, capsys):
    def forbidden(cls):
        raise AssertionError("client constructed")
    monkeypatch.setattr(GeminiInteractionsClient, "from_environment", classmethod(forbidden))
    assert main(["file-run", "model_name_test.txt"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["api_communication_performed"] is False
    assert output["store"] is False


def test_live_without_environment_gate_does_not_construct_client(monkeypatch):
    monkeypatch.delenv("GEMINI_ALLOW_NETWORK", raising=False)
    def forbidden(cls):
        raise AssertionError("client constructed")
    monkeypatch.setattr(GeminiInteractionsClient, "from_environment", classmethod(forbidden))
    with pytest.raises(SystemExit):
        main(["file-run", "model_name_test.txt", "--live"])


def test_environment_gate_without_live_remains_dry(monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_ALLOW_NETWORK", "1")
    monkeypatch.setattr(GeminiInteractionsClient, "from_environment", classmethod(lambda cls: (_ for _ in ()).throw(AssertionError())))
    assert main(["file-run", "model_name_test.txt"]) == 0
    assert json.loads(capsys.readouterr().out)["execution_mode"] == "dry_run"


def test_double_gate_reaches_one_live_call(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GEMINI_ALLOW_NETWORK", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "requested")
    sdk = FakeSdk(response())
    monkeypatch.setattr(GeminiInteractionsClient, "from_environment", classmethod(lambda cls: cls(sdk)))
    assert main(["file-run", "model_name_test.txt", "--live"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["returned_model"] == "returned-model"
    assert len(sdk.interactions.calls) == 1
    assert "tools" not in sdk.interactions.calls[0]
    assert "system_instruction" not in sdk.interactions.calls[0]
    assert "files" not in sdk.interactions.calls[0]
    log = Path(output["raw_log"])
    assert "synthetic-test-key" not in log.read_text()


def test_show_input_and_live_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        main(["file-run", "model_name_test.txt", "--live", "--show-input"])
