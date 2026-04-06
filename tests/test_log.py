"""Tests for structured logging."""

import json
import sys
from io import StringIO

from virtual_reviewer import log as vr_log


class TestStructuredLog:
    def test_info_writes_jsonl_to_stderr(self, capsys):
        vr_log.info("test_module", "test_event", "hello")
        captured = capsys.readouterr()
        assert captured.out == ""  # nothing on stdout
        entry = json.loads(captured.err.strip())
        assert entry["severity"] == "INFO"
        assert entry["module"] == "test_module"
        assert entry["event"] == "test_event"
        assert entry["message"] == "hello"
        assert "timestamp" in entry

    def test_extra_fields(self, capsys):
        vr_log.info(
            "intake",
            "file_loaded",
            "Loaded file",
            path="/tmp/test.png",
            size=1234,
        )
        captured = capsys.readouterr()
        entry = json.loads(captured.err.strip())
        assert entry["path"] == "/tmp/test.png"
        assert entry["size"] == 1234

    def test_application_id(self, capsys):
        vr_log.info(
            "brain",
            "assessment",
            "Done",
            application_id="APP-0001",
        )
        captured = capsys.readouterr()
        entry = json.loads(captured.err.strip())
        assert entry["application_id"] == "APP-0001"

    def test_warn_and_error(self, capsys):
        vr_log.warn("mod", "evt", "warning")
        vr_log.error("mod", "evt", "error")
        captured = capsys.readouterr()
        lines = captured.err.strip().split("\n")
        assert json.loads(lines[0])["severity"] == "WARN"
        assert json.loads(lines[1])["severity"] == "ERROR"
