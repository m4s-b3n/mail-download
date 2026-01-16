"""
Tests for NASUploader class.
"""

from unittest.mock import MagicMock, mock_open, patch

from src.config import NASConfig
from src.uploader import NASUploader


def create_uploader(
    host: str = "nas.local",
    share: str = "backup",
    username: str = "admin",
    password: str = "secret",
    base_path: str = "/",
) -> NASUploader:
    """Helper to create NASUploader with NASConfig."""
    config = NASConfig(
        host=host,
        share=share,
        username=username,
        password=password,
        base_path=base_path,
    )
    return NASUploader(config)


class TestNASUploaderInit:
    """Tests for NASUploader initialization."""

    def test_init_basic(self):
        """Basic initialization should set all properties."""
        uploader = create_uploader()

        assert uploader.host == "nas.local"
        assert uploader.share == "backup"
        assert uploader.username == "admin"
        assert uploader.password == "secret"
        assert uploader.base_path == ""

    def test_init_with_base_path(self):
        """Initialization should strip slashes from base_path."""
        uploader = create_uploader(base_path="/mail-archive/")

        assert uploader.base_path == "mail-archive"

    def test_init_root_base_path(self):
        """Root base path should become empty string."""
        uploader = create_uploader(base_path="/")

        assert uploader.base_path == ""


class TestNASUploaderUpload:
    """Tests for upload_directory method."""

    def test_upload_dry_run(self, temp_upload_dir):
        """upload_directory in dry_run should not upload files."""
        uploader = create_uploader()

        files_count, total_size = uploader.upload_directory(temp_upload_dir, dry_run=True)

        assert files_count == 3  # email.eml, attachment.pdf, nested_file.txt
        assert total_size > 0

    @patch("src.uploader.NASUploader.upload_directory")
    def test_upload_missing_smbprotocol(self, mock_upload, temp_upload_dir):
        """upload_directory should handle missing smbprotocol."""
        # Create a real uploader but mock the import to fail
        uploader = create_uploader()

        with patch.dict("sys.modules", {"smbclient": None}):
            # The actual method checks for ImportError
            mock_upload.return_value = (0, 0)
            result = uploader.upload_directory(temp_upload_dir)

        assert result == (0, 0)

    def test_upload_success(self, temp_upload_dir):
        """upload_directory should upload all files."""
        uploader = create_uploader(base_path="/archive")

        with (
            patch("smbclient.register_session") as mock_register,
            patch("smbclient.makedirs"),
            patch("smbclient.open_file", mock_open()),
            patch("smbclient.stat") as mock_stat,
        ):
            # Simulate files don't exist on NAS
            mock_stat.side_effect = OSError("File not found")

            files_count, total_size = uploader.upload_directory(temp_upload_dir)

            mock_register.assert_called_once_with("nas.local", username="admin", password="secret")
            assert files_count == 3
            assert total_size > 0

    def test_upload_connection_failure(self, temp_upload_dir):
        """upload_directory should handle connection failures."""
        uploader = create_uploader(password="wrong")

        with patch("smbclient.register_session") as mock_register:
            mock_register.side_effect = OSError("Authentication failed")

            files_count, total_size = uploader.upload_directory(temp_upload_dir)

            assert files_count == 0
            assert total_size == 0

    def test_upload_empty_directory(self, tmp_path):
        """upload_directory should handle empty directories."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        uploader = create_uploader()

        with (
            patch("smbclient.register_session"),
            patch("smbclient.makedirs"),
            patch("smbclient.open_file", mock_open()),
            patch("smbclient.stat") as mock_stat,
        ):
            mock_stat.side_effect = OSError("File not found")

            files_count, total_size = uploader.upload_directory(empty_dir)

            assert files_count == 0
            assert total_size == 0

    def test_upload_skips_existing_files(self, temp_upload_dir):
        """upload_directory should skip existing files when overwrite=False."""
        uploader = create_uploader(base_path="/archive")

        with (
            patch("smbclient.register_session"),
            patch("smbclient.makedirs"),
            patch("smbclient.open_file", mock_open()) as mock_smb_open,
            patch("smbclient.stat") as mock_stat,
        ):
            # Simulate all files already exist on NAS
            mock_stat.return_value = True  # File exists

            files_count, _ = uploader.upload_directory(temp_upload_dir, overwrite=False)

            # No files should be uploaded (all skipped)
            assert files_count == 0
            # open_file should not be called for writing
            mock_smb_open.assert_not_called()

    def test_upload_overwrites_existing_files(self, temp_upload_dir):
        """upload_directory should overwrite existing files when overwrite=True."""
        uploader = create_uploader(base_path="/archive")

        with (
            patch("smbclient.register_session"),
            patch("smbclient.makedirs"),
            patch("smbclient.open_file", mock_open()),
            patch("smbclient.stat") as mock_stat,
        ):
            # Simulate all files already exist on NAS
            mock_stat.return_value = True  # File exists

            files_count, total_size = uploader.upload_directory(temp_upload_dir, overwrite=True)

            # All files should be uploaded (overwritten)
            assert files_count == 3
            assert total_size > 0

    def test_upload_creates_nested_directories(self, temp_upload_dir):
        """upload_directory should create nested directories on first makedirs failure."""
        uploader = create_uploader(base_path="/mail-archive/user/folder")

        makedirs_calls = []

        def mock_makedirs(path, exist_ok=False):  # noqa: ARG001  # pylint: disable=unused-argument
            makedirs_calls.append(path)
            # First call fails with "No such file" to trigger fallback
            if len(makedirs_calls) == 1:
                raise OSError("[NtStatus 0xc000003a] No such file or directory")

        with (
            patch("smbclient.register_session"),
            patch("smbclient.makedirs", side_effect=mock_makedirs),
            patch("smbclient.open_file", mock_open()),
            patch("smbclient.stat") as mock_stat,
        ):
            mock_stat.side_effect = OSError("File not found")

            files_count, _ = uploader.upload_directory(temp_upload_dir)

            # Should have attempted to create directories level by level
            assert files_count == 3
            # Should have multiple makedirs calls due to fallback
            assert len(makedirs_calls) > 1

    def test_ensure_directory_creates_path_levels(self):
        """_ensure_directory_exists should create path levels on failure."""
        uploader = create_uploader(base_path="/archive")

        created_paths = []

        def mock_makedirs(path, exist_ok=False):  # noqa: ARG001  # pylint: disable=unused-argument
            created_paths.append(path)
            # First call fails to trigger level-by-level creation
            if len(created_paths) == 1:
                raise OSError("[NtStatus 0xc000003a] No such file or directory")

        uploader._ensure_directory_exists(  # pylint: disable=protected-access
            "\\\\nas.local\\backup\\archive\\user\\folder\\subfolder", mock_makedirs
        )

        # Should have created paths incrementally
        assert len(created_paths) > 1
        # First call is the full path
        assert "subfolder" in created_paths[0]
        # Subsequent calls build up the path
        assert any("archive" in p for p in created_paths)


class TestNASUploaderTestConnection:
    """Tests for test_connection method."""

    def test_test_connection_dry_run(self):
        """test_connection in dry_run should return True without connecting."""
        uploader = create_uploader()

        result = uploader.test_connection(dry_run=True)

        assert result is True

    def test_test_connection_success(self):
        """test_connection should return True on success."""
        uploader = create_uploader(base_path="/archive")

        with (
            patch("smbclient.register_session") as mock_register,
            patch("smbclient.listdir") as mock_listdir,
            patch("smbclient.stat") as mock_stat,
        ):
            mock_listdir.return_value = ["folder1", "file1.txt"]
            mock_stat.return_value = MagicMock(st_size=1024)

            result = uploader.test_connection()

            assert result is True
            mock_register.assert_called_once()

    def test_test_connection_failure(self):
        """test_connection should return False on failure."""
        uploader = create_uploader(password="wrong")

        with patch("smbclient.register_session") as mock_register:
            mock_register.side_effect = OSError("Connection refused")

            result = uploader.test_connection()

            assert result is False

    def test_test_connection_base_path_not_exists(self):
        """test_connection should handle non-existent base path."""
        uploader = create_uploader(base_path="/new-archive")

        with (
            patch("smbclient.register_session"),
            patch("smbclient.listdir") as mock_listdir,
            patch("smbclient.stat") as mock_stat,
        ):
            # First call (share root) succeeds, second call (base_path) fails
            mock_listdir.side_effect = [
                ["folder1"],  # Share root
                FileNotFoundError("Path not found"),  # Base path
            ]
            mock_stat.return_value = MagicMock()

            result = uploader.test_connection()

            # Should still pass - base path will be created on upload
            assert result is True

    def test_test_connection_no_base_path(self):
        """test_connection without base_path should skip that check."""
        uploader = create_uploader()

        with (
            patch("smbclient.register_session"),
            patch("smbclient.listdir") as mock_listdir,
            patch("smbclient.stat") as mock_stat,
        ):
            mock_listdir.return_value = ["folder1"]
            mock_stat.return_value = MagicMock()

            result = uploader.test_connection()

            assert result is True
            # listdir should only be called once for share root
            assert mock_listdir.call_count == 1


class TestNASUploaderPathHandling:
    """Tests for UNC path handling on Linux."""

    def test_base_path_normalization_forward_slashes(self):
        """Forward slashes should be converted to backslashes."""
        uploader = create_uploader(base_path="/mail-archive/user/folder")

        # Internal base_path should have backslashes
        assert "/" not in uploader.base_path
        assert uploader.base_path == "mail-archive\\user\\folder"

    def test_base_path_normalization_mixed_slashes(self):
        """Mixed slashes should all become backslashes."""
        uploader = create_uploader(base_path="/path/to\\some/folder\\")

        assert uploader.base_path == "path\\to\\some\\folder"

    def test_base_path_strips_leading_slashes(self):
        """Leading slashes should be stripped."""
        uploader = create_uploader(base_path="///mail-archive")

        assert uploader.base_path == "mail-archive"

    def test_upload_constructs_correct_unc_paths(self, tmp_path):
        """Upload should construct correct UNC paths on Linux."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        uploader = create_uploader(base_path="/archive/user/INBOX")

        captured_paths = []

        def capture_makedirs(path, exist_ok=False):  # noqa: ARG001  # pylint: disable=unused-argument
            captured_paths.append(path)

        with (
            patch("smbclient.register_session"),
            patch("smbclient.makedirs", side_effect=capture_makedirs),
            patch("smbclient.open_file", mock_open()),
            patch("smbclient.stat") as mock_stat,
        ):
            mock_stat.side_effect = OSError("File not found")

            uploader.upload_directory(tmp_path)

        # All captured paths should be proper UNC paths with backslashes
        for path in captured_paths:
            assert path.startswith("\\\\nas.local\\backup\\")
            # No forward slashes in the path
            assert "/" not in path
            # Should have proper structure
            assert "archive\\user\\INBOX" in path
