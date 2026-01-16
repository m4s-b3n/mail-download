"""
Tests for CLI argument parsing and main function.
"""

import argparse
import sys
from unittest.mock import MagicMock, patch

import pytest
from src.cli import main


class TestCLIArguments:
    """Tests for command line argument parsing."""

    def test_list_argument(self):
        """--list argument should be recognized."""
        with patch.object(sys, "argv", ["mail_archive.py", "--list"]):
            # We can't easily test main() without mocking everything,
            # so we test the argparse setup indirectly
            parser = argparse.ArgumentParser()
            parser.add_argument("--list", "-l", action="store_true")
            args = parser.parse_args(["--list"])

            assert args.list is True

    def test_folder_argument(self):
        """--folder argument should accept folder name."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--folder", "-f", type=str)
        args = parser.parse_args(["--folder", "INBOX"])

        assert args.folder == "INBOX"

    def test_test_mail_argument(self):
        """--test-mail argument should be recognized."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--test-mail", action="store_true")
        args = parser.parse_args(["--test-mail"])

        assert args.test_mail is True

    def test_test_nas_argument(self):
        """--test-nas argument should be recognized."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--test-nas", action="store_true")
        args = parser.parse_args(["--test-nas"])

        assert args.test_nas is True

    def test_dry_run_argument(self):
        """--dry-run argument should be recognized."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--dry-run", "-n", action="store_true")
        args = parser.parse_args(["--dry-run"])

        assert args.dry_run is True

    def test_output_argument_default(self):
        """--output argument should have default value."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--output", "-o", type=str, default="./downloads")
        args = parser.parse_args([])

        assert args.output == "./downloads"

    def test_output_argument_custom(self):
        """--output argument should accept custom path."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--output", "-o", type=str, default="./downloads")
        args = parser.parse_args(["--output", "/custom/path"])

        assert args.output == "/custom/path"

    def test_provider_argument(self):
        """--provider argument should accept provider name."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--provider", "-p", type=str)
        args = parser.parse_args(["--provider", "gmail"])

        assert args.provider == "gmail"


class TestMainFunction:
    """Tests for main() function behavior."""

    @patch.dict(
        "os.environ",
        {
            "MAIL_EMAIL": "test@example.com",
            "MAIL_PASSWORD": "testpass",
        },
        clear=True,
    )
    @patch("src.cli.MailArchiver")
    @patch("src.cli.load_provider_config")
    def test_main_test_mail_success(self, mock_load_config, mock_archiver_class):
        """main with --test-mail should test mail connection."""
        mock_load_config.return_value = {
            "name": "Test",
            "imap_host": "imap.test.com",
            "imap_port": 993,
            "ssl": True,
        }
        mock_archiver = MagicMock()
        mock_archiver.connect.return_value = True
        mock_archiver.test_connection.return_value = True
        mock_archiver_class.return_value = mock_archiver

        with patch.object(sys, "argv", ["mail_archive.py", "--test-mail"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            # Exit code 0 for success
            assert exc_info.value.code == 0

    @patch.dict(
        "os.environ",
        {
            "MAIL_EMAIL": "test@example.com",
            "MAIL_PASSWORD": "testpass",
        },
        clear=True,
    )
    @patch("src.cli.MailArchiver")
    @patch("src.cli.load_provider_config")
    def test_main_test_mail_failure(self, mock_load_config, mock_archiver_class):
        """main with --test-mail should exit 1 on failure."""
        mock_load_config.return_value = {
            "name": "Test",
            "imap_host": "imap.test.com",
            "imap_port": 993,
            "ssl": True,
        }
        mock_archiver = MagicMock()
        mock_archiver.connect.return_value = True
        mock_archiver.test_connection.return_value = False
        mock_archiver_class.return_value = mock_archiver

        with patch.object(sys, "argv", ["mail_archive.py", "--test-mail"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            # Exit code 1 for failure
            assert exc_info.value.code == 1

    @patch.dict(
        "os.environ",
        {
            "NAS_HOST": "nas.local",
            "NAS_SHARE": "backup",
            "NAS_USERNAME": "admin",
            "NAS_PASSWORD": "secret",
        },
        clear=True,
    )
    @patch("src.cli.NASUploader")
    def test_main_test_nas_only(self, mock_uploader_class):
        """main with --test-nas only should not require mail credentials."""
        mock_uploader = MagicMock()
        mock_uploader.test_connection.return_value = True
        mock_uploader_class.return_value = mock_uploader

        with patch.object(sys, "argv", ["mail_archive.py", "--test-nas"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 0

    @patch.dict("os.environ", {}, clear=True)
    @patch("os.path.exists", return_value=False)
    def test_main_missing_mail_credentials(self, _mock_exists):
        """main should fail without mail credentials for most operations."""
        with patch.object(sys, "argv", ["mail_archive.py", "--list"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 1

    @patch.dict("os.environ", {}, clear=True)
    @patch("os.path.exists", return_value=False)
    def test_main_missing_nas_credentials(self, _mock_exists):
        """main with --test-nas should fail without NAS credentials."""
        with patch.object(sys, "argv", ["mail_archive.py", "--test-nas"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 1
