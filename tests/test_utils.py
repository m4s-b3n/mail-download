"""
Tests for utility functions.
"""

from datetime import timedelta

import pytest
from src.config import (
    MailConfig,
    NASConfig,
    parse_time_range,
)
from src.utils import (
    decode_mime_header,
    delete_directory,
)


class TestParseTimeRange:
    """Tests for parse_time_range function."""

    def test_parse_days(self):
        """Should parse day values correctly."""
        result = parse_time_range("30D")
        assert result == timedelta(days=30)

    def test_parse_days_lowercase(self):
        """Should handle lowercase unit."""
        result = parse_time_range("15d")
        assert result == timedelta(days=15)

    def test_parse_weeks(self):
        """Should parse week values correctly."""
        result = parse_time_range("2W")
        assert result == timedelta(weeks=2)

    def test_parse_weeks_lowercase(self):
        """Should handle lowercase unit."""
        result = parse_time_range("4w")
        assert result == timedelta(weeks=4)

    def test_parse_months(self):
        """Should parse month values (approximated as 30 days)."""
        result = parse_time_range("6M")
        assert result == timedelta(days=180)  # 6 * 30

    def test_parse_months_lowercase(self):
        """Should handle lowercase unit."""
        result = parse_time_range("3m")
        assert result == timedelta(days=90)  # 3 * 30

    def test_parse_years(self):
        """Should parse year values (approximated as 365 days)."""
        result = parse_time_range("1Y")
        assert result == timedelta(days=365)

    def test_parse_years_lowercase(self):
        """Should handle lowercase unit."""
        result = parse_time_range("2y")
        assert result == timedelta(days=730)  # 2 * 365

    def test_parse_with_whitespace(self):
        """Should handle leading/trailing whitespace."""
        result = parse_time_range("  30D  ")
        assert result == timedelta(days=30)

    def test_invalid_format_no_unit(self):
        """Should raise ValueError for missing unit."""
        with pytest.raises(ValueError, match="Invalid time range format"):
            parse_time_range("30")

    def test_invalid_format_no_number(self):
        """Should raise ValueError for missing number."""
        with pytest.raises(ValueError, match="Invalid time range format"):
            parse_time_range("D")

    def test_invalid_format_invalid_unit(self):
        """Should raise ValueError for invalid unit."""
        with pytest.raises(ValueError, match="Invalid time range format"):
            parse_time_range("30X")

    def test_invalid_format_empty(self):
        """Should raise ValueError for empty string."""
        with pytest.raises(ValueError, match="Invalid time range format"):
            parse_time_range("")


class TestDecodeMimeHeader:
    """Tests for decode_mime_header function."""

    def test_decode_plain_text(self):
        """Plain text headers should be returned as-is."""
        result = decode_mime_header("Simple Subject")
        assert result == "Simple Subject"

    def test_decode_none(self):
        """None should return empty string."""
        result = decode_mime_header(None)
        assert result == ""

    def test_decode_utf8_base64(self):
        """UTF-8 Base64 encoded headers should be decoded."""
        # "Test" encoded as UTF-8 Base64
        encoded = "=?utf-8?b?VGVzdA==?="
        result = decode_mime_header(encoded)
        assert result == "Test"

    def test_decode_utf8_quoted_printable(self):
        """UTF-8 quoted-printable headers should be decoded."""
        encoded = "=?utf-8?q?Test_Subject?="
        result = decode_mime_header(encoded)
        assert result == "Test Subject"

    def test_decode_mixed_encoding(self):
        """Headers with mixed plain and encoded parts should work."""
        # Some mail clients mix plain and encoded parts
        result = decode_mime_header("Re: =?utf-8?b?VGVzdA==?=")
        assert "Test" in result

    def test_decode_iso8859(self):
        """ISO-8859-1 encoded headers should be decoded."""
        encoded = "=?iso-8859-1?q?Caf=E9?="
        result = decode_mime_header(encoded)
        assert result == "Café"


class TestDeleteDirectory:
    """Tests for delete_directory function."""

    def test_delete_existing_directory(self, tmp_path):
        """Should delete directory and return True."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("content")

        result = delete_directory(test_dir)

        assert result is True
        assert not test_dir.exists()

    def test_delete_nested_directory(self, tmp_path):
        """Should delete nested directories."""
        test_dir = tmp_path / "parent" / "child" / "grandchild"
        test_dir.mkdir(parents=True)
        (test_dir / "file.txt").write_text("content")
        parent = tmp_path / "parent"

        result = delete_directory(parent)

        assert result is True
        assert not parent.exists()

    def test_delete_nonexistent_directory(self, tmp_path):
        """Should return False for nonexistent directory."""
        nonexistent = tmp_path / "does_not_exist"

        result = delete_directory(nonexistent)

        assert result is False


class TestNASConfig:
    """Tests for NASConfig dataclass."""

    def test_from_env_with_all_vars(self, monkeypatch):
        """Should create NASConfig when all env vars are set."""
        monkeypatch.setenv("NAS_HOST", "nas.local")
        monkeypatch.setenv("NAS_SHARE", "backup")
        monkeypatch.setenv("NAS_USERNAME", "admin")
        monkeypatch.setenv("NAS_PASSWORD", "secret")
        monkeypatch.setenv("NAS_PATH", "/archive")

        config = NASConfig.from_env()

        assert config is not None
        assert config.host == "nas.local"
        assert config.share == "backup"
        assert config.username == "admin"
        assert config.password == "secret"
        assert config.base_path == "/archive"

    def test_from_env_missing_required(self, monkeypatch):
        """Should return None when required vars are missing."""
        monkeypatch.setenv("NAS_HOST", "nas.local")
        # Missing NAS_SHARE, NAS_USERNAME, NAS_PASSWORD
        monkeypatch.delenv("NAS_SHARE", raising=False)
        monkeypatch.delenv("NAS_USERNAME", raising=False)
        monkeypatch.delenv("NAS_PASSWORD", raising=False)

        config = NASConfig.from_env()

        assert config is None

    def test_from_env_default_path(self, monkeypatch):
        """Should use default path when NAS_PATH not set."""
        monkeypatch.setenv("NAS_HOST", "nas.local")
        monkeypatch.setenv("NAS_SHARE", "backup")
        monkeypatch.setenv("NAS_USERNAME", "admin")
        monkeypatch.setenv("NAS_PASSWORD", "secret")
        monkeypatch.delenv("NAS_PATH", raising=False)

        config = NASConfig.from_env()

        assert config is not None
        assert config.base_path == "/mail-archive"

    def test_get_folder_path(self):
        """Should build correct folder path."""
        config = NASConfig(
            host="nas.local",
            share="backup",
            username="admin",
            password="secret",
            base_path="/mail-archive",
        )

        path = config.get_folder_path("john", "INBOX")

        assert path == "/mail-archive/john/INBOX"


class TestMailConfig:
    """Tests for MailConfig dataclass."""

    def test_from_env_with_all_vars(self, monkeypatch):
        """Should create MailConfig when all env vars are set."""
        monkeypatch.setenv("MAIL_EMAIL", "test@example.com")
        monkeypatch.setenv("MAIL_PASSWORD", "secret123")

        config = MailConfig.from_env("gmail")

        assert config is not None
        assert config.email == "test@example.com"
        assert config.password == "secret123"
        assert config.provider == "gmail"

    def test_from_env_missing_email(self, monkeypatch):
        """Should return None when email is missing."""
        monkeypatch.delenv("MAIL_EMAIL", raising=False)
        monkeypatch.setenv("MAIL_PASSWORD", "secret123")

        config = MailConfig.from_env("gmail")

        assert config is None

    def test_from_env_missing_password(self, monkeypatch):
        """Should return None when password is missing."""
        monkeypatch.setenv("MAIL_EMAIL", "test@example.com")
        monkeypatch.delenv("MAIL_PASSWORD", raising=False)

        config = MailConfig.from_env("gmail")

        assert config is None

    def test_account_name_property(self):
        """Should return email without domain."""
        config = MailConfig(email="john.doe@example.com", password="secret", provider="gmail")

        assert config.account_name == "john.doe"

    def test_account_name_simple_email(self):
        """Should handle simple email addresses."""
        config = MailConfig(email="admin@company.co.uk", password="secret", provider="outlook")

        assert config.account_name == "admin"
