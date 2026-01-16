"""
Pytest fixtures and configuration for mail archive tests.
"""

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_imap_client():
    """Create a mock IMAP client with common methods."""
    client = MagicMock()

    # Mock capabilities
    client.capabilities.return_value = [b"IMAP4rev1", b"IDLE", b"NAMESPACE"]

    # Mock folder listing
    client.list_folders.return_value = [
        ((b"\\HasNoChildren",), b"/", "INBOX"),
        ((b"\\HasNoChildren",), b"/", "Sent"),
        ((b"\\HasNoChildren",), b"/", "Drafts"),
        ((b"\\HasNoChildren", b"\\Trash"), b"/", "Trash"),
    ]

    # Mock select_folder
    client.select_folder.return_value = {
        b"EXISTS": 5,
        b"RECENT": 0,
        b"UIDVALIDITY": 12345,
    }

    # Mock search
    client.search.return_value = [1, 2, 3, 4, 5]

    return client


@pytest.fixture
def sample_email_simple():
    """Create a simple email without attachments."""
    msg = MIMEText("This is a test email body.")
    msg["Subject"] = "Test Subject"
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Date"] = "Mon, 15 Jan 2024 14:30:00 +0000"
    return msg.as_bytes()


@pytest.fixture
def sample_email_with_attachment():
    """Create an email with an attachment."""
    msg = MIMEMultipart()
    msg["Subject"] = "Email with Attachment"
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Date"] = "Mon, 15 Jan 2024 15:00:00 +0000"

    # Add body
    body = MIMEText("This email has an attachment.")
    msg.attach(body)

    # Add attachment
    attachment = MIMEBase("application", "octet-stream")
    attachment.set_payload(b"PDF file content here")
    encoders.encode_base64(attachment)
    attachment.add_header("Content-Disposition", "attachment", filename="document.pdf")
    msg.attach(attachment)

    return msg.as_bytes()


@pytest.fixture
def sample_email_mime_encoded():
    """Create an email with MIME-encoded headers."""
    msg = MIMEText("Email with special characters in subject.")
    # MIME-encoded subject: "Tëst Sübject with Ümläuts"
    msg["Subject"] = "=?utf-8?b?VMOrc3QgU8O8YmplY3Qgd2l0aCDDnG1sw6R1dHM=?="
    msg["From"] = "=?utf-8?b?U2VuZGVyIE5hbWU=?= <sender@example.com>"
    msg["To"] = "recipient@example.com"
    return msg.as_bytes()


@pytest.fixture
def mock_smb_session():
    """Create mock SMB session functions."""
    with (
        patch("smbclient.register_session") as mock_register,
        patch("smbclient.listdir") as mock_listdir,
        patch("smbclient.stat") as mock_stat,
        patch("smbclient.open_file") as mock_open,
        patch("smbclient.makedirs") as mock_makedirs,
    ):
        mock_listdir.return_value = ["folder1", "folder2", "file1.txt"]
        mock_stat.return_value = MagicMock(st_size=1024)

        yield {
            "register_session": mock_register,
            "listdir": mock_listdir,
            "stat": mock_stat,
            "open_file": mock_open,
            "makedirs": mock_makedirs,
        }


@pytest.fixture
def temp_download_dir(tmp_path):
    """Create a temporary download directory."""
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    return download_dir


@pytest.fixture
def temp_upload_dir(tmp_path):
    """Create a temporary directory with files to upload."""
    upload_dir = tmp_path / "to_upload"
    upload_dir.mkdir()

    # Create some test files
    (upload_dir / "email.eml").write_bytes(b"Email content")
    (upload_dir / "attachment.pdf").write_bytes(b"PDF content")

    subdir = upload_dir / "subfolder"
    subdir.mkdir()
    (subdir / "nested_file.txt").write_text("Nested content")

    return upload_dir
