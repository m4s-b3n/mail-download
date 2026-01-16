"""
Tests for MailArchiver class.
"""

from datetime import datetime
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from unittest.mock import MagicMock, patch

from imapclient.exceptions import IMAPClientError

from src.archiver import MailArchiver

# Test provider config that mimics GMX settings
TEST_PROVIDER_CONFIG = {
    "name": "Test Mail",
    "imap_host": "imap.test.com",
    "imap_port": 993,
    "ssl": True,
}


class TestMailArchiverConnection:
    """Tests for MailArchiver connection methods."""

    @patch("src.archiver.IMAPClient")
    def test_connect_success(self, mock_imap_class):
        """Successful connection should return True."""
        mock_client = MagicMock()
        mock_imap_class.return_value = mock_client

        archiver = MailArchiver("test@example.com", "password123", TEST_PROVIDER_CONFIG)
        result = archiver.connect()

        assert result is True
        mock_imap_class.assert_called_once_with(
            TEST_PROVIDER_CONFIG["imap_host"],
            port=TEST_PROVIDER_CONFIG["imap_port"],
            ssl=True,
        )
        mock_client.login.assert_called_once_with("test@example.com", "password123")
        assert archiver.client is mock_client

    @patch("src.archiver.IMAPClient")
    def test_connect_failure(self, mock_imap_class):
        """Failed connection should return False."""
        mock_imap_class.side_effect = IMAPClientError("Connection refused")

        archiver = MailArchiver("test@example.com", "wrong_password", TEST_PROVIDER_CONFIG)
        result = archiver.connect()

        assert result is False
        assert archiver.client is None

    @patch("src.archiver.IMAPClient")
    def test_connect_login_failure(self, mock_imap_class):
        """Failed login should return False."""
        mock_client = MagicMock()
        mock_client.login.side_effect = IMAPClientError("Invalid credentials")
        mock_imap_class.return_value = mock_client

        archiver = MailArchiver("test@example.com", "wrong_password", TEST_PROVIDER_CONFIG)
        result = archiver.connect()

        assert result is False

    def test_disconnect_when_connected(self, mock_imap_client):
        """Disconnect should logout when connected."""
        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        archiver.disconnect()

        mock_imap_client.logout.assert_called_once()

    def test_disconnect_when_not_connected(self):
        """Disconnect should handle case when not connected."""
        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = None

        # Should not raise
        archiver.disconnect()

    def test_disconnect_handles_exception(self, mock_imap_client):
        """Disconnect should handle logout exceptions gracefully."""
        mock_imap_client.logout.side_effect = IMAPClientError("Already disconnected")
        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        # Should not raise
        archiver.disconnect()


class TestMailArchiverFolders:
    """Tests for folder-related methods."""

    def test_list_folders_not_connected(self):
        """list_folders should return empty list when not connected."""
        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = None

        result = archiver.list_folders()

        assert not result

    def test_list_folders_success(self, mock_imap_client):
        """list_folders should return folder names with counts."""
        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        result = archiver.list_folders()

        assert len(result) == 4
        # Each folder should have (name, count) tuple
        folder_names = [f[0] for f in result]
        assert "INBOX" in folder_names
        assert "Sent" in folder_names

    def test_get_folder_message_count_not_connected(self):
        """get_folder_message_count should return 0 when not connected."""
        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = None

        result = archiver.get_folder_message_count("INBOX")

        assert result == 0

    def test_get_folder_message_count_success(self, mock_imap_client):
        """get_folder_message_count should return message count."""
        mock_imap_client.select_folder.return_value = {b"EXISTS": 42}
        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        result = archiver.get_folder_message_count("INBOX")

        assert result == 42
        mock_imap_client.select_folder.assert_called_with("INBOX", readonly=True)


class TestMailArchiverDownload:
    """Tests for email download functionality."""

    def test_download_folder_not_connected(self, temp_download_dir):
        """download_folder should return (0, 0) when not connected."""
        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = None

        result = archiver.download_folder("INBOX", temp_download_dir)

        assert result == (0, 0)

    def test_download_folder_empty(self, mock_imap_client, temp_download_dir):
        """download_folder should handle empty folders."""
        mock_imap_client.select_folder.return_value = {b"EXISTS": 0}
        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        result = archiver.download_folder("EmptyFolder", temp_download_dir)

        assert result == (0, 0)

    def test_download_folder_dry_run(self, mock_imap_client, temp_download_dir):
        """download_folder in dry_run mode should not create files."""
        mock_imap_client.select_folder.return_value = {b"EXISTS": 5}
        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        result = archiver.download_folder("INBOX", temp_download_dir, dry_run=True)

        # Should return expected count without actually downloading
        assert result[0] == 5
        # No actual files should be created
        assert not any(temp_download_dir.iterdir())

    def test_download_folder_success(self, mock_imap_client, temp_download_dir, sample_email_simple):
        """download_folder should download emails successfully."""
        mock_imap_client.select_folder.return_value = {b"EXISTS": 1}
        mock_imap_client.search.return_value = [1]
        mock_imap_client.fetch.return_value = {
            1: {
                b"RFC822": sample_email_simple,
                b"INTERNALDATE": datetime(2024, 1, 15, 14, 30, 0),
            }
        }

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        emails, attachments = archiver.download_folder("INBOX", temp_download_dir)

        assert emails == 1
        assert attachments == 0
        # Check that email directory was created
        inbox_dir = temp_download_dir / "INBOX"
        assert inbox_dir.exists()

    def test_download_folder_with_attachment(self, mock_imap_client, temp_download_dir, sample_email_with_attachment):
        """download_folder should extract attachments."""
        mock_imap_client.select_folder.return_value = {b"EXISTS": 1}
        mock_imap_client.search.return_value = [1]
        mock_imap_client.fetch.return_value = {
            1: {
                b"RFC822": sample_email_with_attachment,
                b"INTERNALDATE": datetime(2024, 1, 15, 15, 0, 0),
            }
        }

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        emails, attachments = archiver.download_folder("INBOX", temp_download_dir)

        assert emails == 1
        assert attachments == 1

    def test_download_folder_handles_fetch_error(self, mock_imap_client, temp_download_dir, sample_email_simple):
        """download_folder should continue on individual message errors."""
        mock_imap_client.select_folder.return_value = {b"EXISTS": 2}
        mock_imap_client.search.return_value = [1, 2]

        # First message fails, second succeeds
        mock_imap_client.fetch.side_effect = [
            IMAPClientError("Fetch error"),
            {
                2: {
                    b"RFC822": sample_email_simple,
                    b"INTERNALDATE": datetime(2024, 1, 15, 14, 30, 0),
                }
            },
        ]

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        emails, _attachments = archiver.download_folder("INBOX", temp_download_dir)

        # Should still process the successful message
        assert emails == 1

    def test_download_folder_skips_existing_same_size(self, mock_imap_client, temp_download_dir, sample_email_simple):
        """download_folder should skip emails that exist with same size."""
        mock_imap_client.select_folder.return_value = {b"EXISTS": 1}
        mock_imap_client.search.return_value = [1]

        internal_date = datetime(2024, 1, 15, 14, 30, 0)
        mock_imap_client.fetch.return_value = {
            1: {
                b"RFC822": sample_email_simple,
                b"INTERNALDATE": internal_date,
            }
        }

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        # Pre-create the email file with same content (same size)
        inbox_dir = temp_download_dir / "INBOX"
        inbox_dir.mkdir(parents=True)
        date_str = internal_date.strftime("%Y%m%d_%H%M%S")
        email_dir = inbox_dir / f"{date_str}_1_Test Subject"
        email_dir.mkdir(parents=True)
        email_path = email_dir / "email.eml"
        email_path.write_bytes(sample_email_simple)

        # Download again - should skip
        emails, _attachments = archiver.download_folder("INBOX", temp_download_dir)

        # Email should be skipped (0 downloaded)
        assert emails == 0

    def test_download_folder_redownloads_different_size(self, mock_imap_client, temp_download_dir, sample_email_simple):
        """download_folder should redownload if existing file has different size."""
        mock_imap_client.select_folder.return_value = {b"EXISTS": 1}
        mock_imap_client.search.return_value = [1]

        internal_date = datetime(2024, 1, 15, 14, 30, 0)
        mock_imap_client.fetch.return_value = {
            1: {
                b"RFC822": sample_email_simple,
                b"INTERNALDATE": internal_date,
            }
        }

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        # Pre-create the email file with DIFFERENT content (different size)
        inbox_dir = temp_download_dir / "INBOX"
        inbox_dir.mkdir(parents=True)
        date_str = internal_date.strftime("%Y%m%d_%H%M%S")
        email_dir = inbox_dir / f"{date_str}_1_Test Subject"
        email_dir.mkdir(parents=True)
        email_path = email_dir / "email.eml"
        email_path.write_bytes(b"truncated or corrupted content")  # Different size!

        # Download again - should redownload
        emails, _attachments = archiver.download_folder("INBOX", temp_download_dir)

        # Email should be downloaded (not skipped)
        assert emails == 1
        # File should have correct content now
        assert email_path.read_bytes() == sample_email_simple


class TestMailArchiverTestConnection:
    """Tests for test_connection method."""

    def test_test_connection_not_connected(self):
        """test_connection should return False when not connected."""
        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = None

        result = archiver.test_connection()

        assert result is False

    def test_test_connection_success(self, mock_imap_client):
        """test_connection should return True on success."""
        mock_imap_client.capabilities.return_value = [b"IMAP4", b"IDLE"]
        mock_imap_client.list_folders.return_value = [
            ((b"\\HasNoChildren",), b"/", "INBOX"),
        ]
        mock_imap_client.select_folder.return_value = {b"EXISTS": 10}

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        result = archiver.test_connection()

        assert result is True
        mock_imap_client.capabilities.assert_called_once()

    def test_test_connection_failure(self, mock_imap_client):
        """test_connection should return False on error."""
        mock_imap_client.capabilities.side_effect = IMAPClientError("Connection lost")

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        result = archiver.test_connection()

        assert result is False


class TestMailArchiverDelete:
    """Tests for delete_folder_contents method."""

    def test_delete_not_connected(self):
        """delete_folder_contents should return 0 when not connected."""
        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = None

        result = archiver.delete_folder_contents("INBOX")

        assert result == 0

    def test_delete_empty_folder(self, mock_imap_client):
        """delete_folder_contents should handle empty folders."""
        mock_imap_client.select_folder.return_value = {b"EXISTS": 0}

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        result = archiver.delete_folder_contents("EmptyFolder")

        assert result == 0

    def test_delete_dry_run(self, mock_imap_client):
        """delete_folder_contents in dry_run should not delete."""
        mock_imap_client.select_folder.return_value = {b"EXISTS": 5}

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        archiver.client = mock_imap_client

        result = archiver.delete_folder_contents("INBOX", dry_run=True)

        assert result == 5
        mock_imap_client.delete_messages.assert_not_called()
        mock_imap_client.expunge.assert_not_called()


class TestMailArchiverAttachmentFilenames:
    """Tests for attachment filename sanitization with edge cases."""

    def test_save_attachment_with_newline_in_filename(self, tmp_path):
        """Attachment filenames with newlines should be sanitized."""
        # Create a multipart email with attachment containing newline in filename
        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "test@example.com"

        attachment = MIMEBase("application", "pdf")
        attachment.set_payload(b"PDF content here")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename="Marius\n Boden.pdf",
        )
        msg.attach(attachment)

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        email_dir = tmp_path / "email_dir"
        email_dir.mkdir()

        count = archiver._save_attachments(msg, email_dir)  # pylint: disable=protected-access

        assert count == 1
        # Check that the file was saved with sanitized name (no newline)
        saved_files = list(email_dir.iterdir())
        assert len(saved_files) == 1
        assert "\n" not in saved_files[0].name
        assert saved_files[0].name.endswith(".pdf")

    def test_save_attachment_with_special_characters(self, tmp_path):
        """Attachment filenames with special characters should be sanitized."""
        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "test@example.com"

        attachment = MIMEBase("application", "pdf")
        attachment.set_payload(b"PDF content")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename='Report: Q1/Q2 "Final" <draft>.pdf',
        )
        msg.attach(attachment)

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        email_dir = tmp_path / "email_dir"
        email_dir.mkdir()

        count = archiver._save_attachments(msg, email_dir)  # pylint: disable=protected-access

        assert count == 1
        saved_files = list(email_dir.iterdir())
        assert len(saved_files) == 1
        filename = saved_files[0].name
        # Verify no invalid filesystem characters
        assert ":" not in filename
        assert "/" not in filename
        assert '"' not in filename
        assert "<" not in filename
        assert ">" not in filename
        assert filename.endswith(".pdf")

    def test_save_attachment_with_control_characters(self, tmp_path):
        """Attachment filenames with control characters should be sanitized."""
        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "test@example.com"

        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(b"binary content")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename="file\x00\r\nname\t.txt",
        )
        msg.attach(attachment)

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        email_dir = tmp_path / "email_dir"
        email_dir.mkdir()

        count = archiver._save_attachments(msg, email_dir)  # pylint: disable=protected-access

        assert count == 1
        saved_files = list(email_dir.iterdir())
        assert len(saved_files) == 1
        filename = saved_files[0].name
        # Verify no control characters
        assert all(ord(c) >= 32 for c in filename)
        assert filename.endswith(".txt")

    def test_save_attachment_with_unicode_characters(self, tmp_path):
        """Attachment filenames with unicode (umlauts etc.) should be preserved."""
        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "test@example.com"

        attachment = MIMEBase("application", "pdf")
        attachment.set_payload(b"PDF content")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename="Vertrag_für_Müller.pdf",
        )
        msg.attach(attachment)

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        email_dir = tmp_path / "email_dir"
        email_dir.mkdir()

        count = archiver._save_attachments(msg, email_dir)  # pylint: disable=protected-access

        assert count == 1
        saved_files = list(email_dir.iterdir())
        assert len(saved_files) == 1
        # Unicode characters should be preserved
        assert "ü" in saved_files[0].name or "Muller" in saved_files[0].name
        assert saved_files[0].name.endswith(".pdf")

    def test_save_attachment_real_world_problematic_name(self, tmp_path):
        """Test with actual problematic filename from user's email."""
        msg = MIMEMultipart()
        msg["Subject"] = "Test"
        msg["From"] = "test@example.com"

        attachment = MIMEBase("application", "pdf")
        attachment.set_payload(b"Employment contract content")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename="Mustervertrag - XPIRIT Germany GmbH - Employment Agreement - Marius\n Boden.pdf",
        )
        msg.attach(attachment)

        archiver = MailArchiver("test@example.com", "password", TEST_PROVIDER_CONFIG)
        email_dir = tmp_path / "email_dir"
        email_dir.mkdir()

        count = archiver._save_attachments(msg, email_dir)  # pylint: disable=protected-access

        assert count == 1
        saved_files = list(email_dir.iterdir())
        assert len(saved_files) == 1
        filename = saved_files[0].name
        assert "\n" not in filename
        assert filename.endswith(".pdf")
        # Content should be saved correctly
        assert saved_files[0].read_bytes() == b"Employment contract content"
