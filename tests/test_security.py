"""Tests for security hardening."""

import pytest

from virtual_reviewer.brain import _count_risks, run
from virtual_reviewer.models import (
    ExpertVerdict,
    Finding,
    OverallVerdict,
    RiskSummary,
    Severity,
    Verdict,
)


class TestVerdictOverride:
    """Test that semantic validation overrides unsafe LLM verdicts."""

    def test_count_risks(self):
        findings = [
            Finding(
                regulation_ref="1.1",
                target_field="a",
                severity=Severity.critical,
                finding="critical issue",
            ),
            Finding(
                regulation_ref="1.2",
                target_field="b",
                severity=Severity.high,
                finding="high issue",
            ),
            Finding(
                regulation_ref="1.3",
                target_field="c",
                severity=Severity.high,
                finding="another high",
            ),
        ]
        summary = _count_risks(findings)
        assert summary.critical == 1
        assert summary.high == 2
        assert summary.medium == 0


class TestFileLoading:
    def test_path_traversal_blocked(self, tmp_path):
        from virtual_reviewer.llm import load_file_as_part

        # Create a file outside the allowed base dir
        secret = tmp_path / "outside" / "secret.png"
        secret.parent.mkdir()
        secret.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        allowed = tmp_path / "allowed"
        allowed.mkdir()

        with pytest.raises(ValueError, match="Path traversal"):
            load_file_as_part(str(secret), base_dir=str(allowed))

    def test_allowed_path_works(self, tmp_path):
        from virtual_reviewer.llm import load_file_as_part

        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        part = load_file_as_part(str(img), base_dir=str(tmp_path))
        assert part is not None

    def test_file_size_limit(self, tmp_path):
        from virtual_reviewer.llm import MAX_FILE_SIZE, load_file_as_part

        big_file = tmp_path / "huge.png"
        big_file.write_bytes(b"\x89PNG" + b"\x00" * (MAX_FILE_SIZE + 1))

        with pytest.raises(ValueError, match="File too large"):
            load_file_as_part(str(big_file), base_dir=str(tmp_path))

    def test_disallowed_mime_type(self, tmp_path):
        from virtual_reviewer.llm import load_file_as_part

        exe = tmp_path / "evil.exe"
        exe.write_bytes(b"MZ" + b"\x00" * 100)

        with pytest.raises(ValueError, match="Unsupported file type"):
            load_file_as_part(str(exe), base_dir=str(tmp_path))
