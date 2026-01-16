"""
NAS upload functionality via SMB.

Provides the NASUploader class for uploading files to a NAS
using the SMB protocol.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console

from .config import NASConfig
from .utils import create_progress_bar

if TYPE_CHECKING:
    from collections.abc import Callable

console = Console()


@dataclass
class FileUploadContext:
    """Context for a single file upload operation."""

    smbclient: Any
    local_path: Path
    overwrite: bool
    created_dirs: set


@dataclass
class _SMBClientCache:
    """Cache holder for lazy-loaded smbclient module."""

    module: Any = None


_smb_cache = _SMBClientCache()


def _get_smbclient():
    """Lazy load smbclient module."""
    if _smb_cache.module is None:
        try:
            import smbclient  # pylint: disable=import-outside-toplevel

            _smb_cache.module = smbclient
        except ImportError as err:
            raise ImportError("smbprotocol not installed. Run: pip install smbprotocol") from err
    return _smb_cache.module


class NASUploader:
    """Upload files to QNAP NAS via SMB."""

    def __init__(self, config: NASConfig):
        """
        Initialize NASUploader with configuration.

        Args:
            config: NASConfig dataclass with connection settings
        """
        self.host = config.host
        self.share = config.share
        self.username = config.username
        self.password = config.password
        # Normalize path: strip slashes and convert forward slashes to backslashes
        self.base_path = config.base_path.strip("/").replace("/", "\\").rstrip("\\")

    def _ensure_directory_exists(self, remote_dir: str, makedirs_func: "Callable") -> None:
        """
        Ensure a remote directory exists, creating it and all parents if needed.

        Args:
            remote_dir: The full UNC path to the directory
            makedirs_func: The smbclient.makedirs function
        """
        try:
            makedirs_func(remote_dir, exist_ok=True)
        except OSError as e:
            # If makedirs fails, try creating directories one level at a time
            if "No such file" in str(e) or "0xc000003a" in str(e):
                self._create_directories_incrementally(remote_dir, makedirs_func)

    def _create_directories_incrementally(self, remote_dir: str, makedirs_func: "Callable") -> None:
        """Create directories one level at a time for problematic SMB servers."""
        parts = remote_dir.replace("/", "\\").split("\\")
        # Skip empty parts and host/share (first 4 parts: '', '', host, share)
        if len(parts) > 4:
            current_path = "\\\\" + parts[2] + "\\" + parts[3]
            for part in parts[4:]:
                if part:
                    current_path = current_path + "\\" + part
                    try:
                        makedirs_func(current_path, exist_ok=True)
                    except OSError:
                        pass  # Directory might already exist

    def upload_directory(self, local_path: Path, dry_run: bool = False, overwrite: bool = False) -> tuple[int, int]:
        """
        Upload a directory to the NAS.

        Args:
            local_path: Local directory to upload
            dry_run: If True, only show what would be uploaded
            overwrite: If True, overwrite existing files; if False, skip them

        Returns: (files_uploaded, total_size_bytes)
        """
        try:
            smbclient = _get_smbclient()
        except ImportError:
            console.print("[red]smbprotocol not installed. Run: pip install smbprotocol[/red]")
            return (0, 0)

        files_to_upload, total_size = self._collect_files(local_path)

        if dry_run:
            return self._show_upload_dry_run(files_to_upload, total_size, overwrite)

        return self._execute_upload(smbclient, local_path, files_to_upload, overwrite)

    def _collect_files(self, local_path: Path) -> tuple[list[Path], int]:
        """Collect files to upload and calculate total size."""
        files_to_upload = [f for f in local_path.rglob("*") if f.is_file()]
        total_size = sum(f.stat().st_size for f in files_to_upload)
        return files_to_upload, total_size

    def _show_upload_dry_run(self, files_to_upload: list[Path], total_size: int, overwrite: bool) -> tuple[int, int]:
        """Display dry run information."""
        console.print("\n[cyan]DRY RUN MODE - Would upload:[/cyan]")
        console.print(f"Files: [yellow]{len(files_to_upload)}[/yellow]")
        console.print(f"Total size: [yellow]{total_size / (1024 * 1024):.2f} MB[/yellow]")
        console.print(f"Destination: [blue]\\\\{self.host}\\{self.share}\\{self.base_path}[/blue]")
        console.print(f"Overwrite existing: [yellow]{'Yes' if overwrite else 'No (skip)'}[/yellow]")
        return (len(files_to_upload), total_size)

    def _execute_upload(
        self,
        smbclient,
        local_path: Path,
        files_to_upload: list[Path],
        overwrite: bool,
    ) -> tuple[int, int]:
        """Execute the actual upload to NAS."""
        try:
            smbclient.register_session(self.host, username=self.username, password=self.password)
            self._create_base_directory(smbclient)

            return self._upload_files_with_progress(smbclient, local_path, files_to_upload, overwrite)

        except OSError as e:
            console.print(f"[red]NAS connection failed: {e}[/red]")
            return (0, 0)

    def _create_base_directory(self, smbclient) -> None:
        """Create the base directory structure on NAS."""
        base_remote_path = f"\\\\{self.host}\\{self.share}\\{self.base_path}"
        console.print(f"[dim]Creating base directory: {base_remote_path}[/dim]")
        self._ensure_directory_exists(base_remote_path, smbclient.makedirs)

    def _upload_files_with_progress(
        self,
        smbclient,
        local_path: Path,
        files_to_upload: list[Path],
        overwrite: bool,
    ) -> tuple[int, int]:
        """Upload files with progress bar."""
        files_uploaded = 0
        files_skipped = 0
        total_size = 0
        created_dirs: set[str] = set()
        ctx = FileUploadContext(
            smbclient=smbclient,
            local_path=local_path,
            overwrite=overwrite,
            created_dirs=created_dirs,
        )

        with create_progress_bar() as progress:
            task = progress.add_task("Uploading to NAS...", total=len(files_to_upload))

            for local_file in files_to_upload:
                result = self._upload_single_file(ctx, local_file)
                if result == "uploaded":
                    files_uploaded += 1
                    total_size += local_file.stat().st_size
                elif result == "skipped":
                    files_skipped += 1
                progress.advance(task)

        self._show_upload_summary(files_uploaded, files_skipped)
        return (files_uploaded, total_size)

    def _upload_single_file(
        self,
        ctx: FileUploadContext,
        local_file: Path,
    ) -> str:
        """Upload a single file. Returns 'uploaded', 'skipped', or 'error'."""
        relative_path = local_file.relative_to(ctx.local_path)
        remote_path = f"\\\\{self.host}\\{self.share}\\{self.base_path}\\{relative_path}"
        remote_path = remote_path.replace("/", "\\")

        remote_dir = self._get_parent_directory(remote_path)
        if remote_dir not in ctx.created_dirs:
            self._ensure_directory_exists(remote_dir, ctx.smbclient.makedirs)
            ctx.created_dirs.add(remote_dir)

        if not ctx.overwrite and self._file_exists_on_nas(ctx.smbclient, remote_path):
            return "skipped"

        return self._write_file_to_nas(ctx.smbclient, local_file, remote_path)

    def _get_parent_directory(self, remote_path: str) -> str:
        """Get parent directory from a remote path."""
        last_sep = remote_path.rfind("\\")
        if last_sep > 0:
            return remote_path[:last_sep]
        return remote_path

    def _file_exists_on_nas(self, smbclient, remote_path: str) -> bool:
        """Check if a file exists on the NAS."""
        try:
            smbclient.stat(remote_path)
            return True
        except OSError:
            return False

    def _write_file_to_nas(self, smbclient, local_file: Path, remote_path: str) -> str:
        """Write a file to the NAS. Returns 'uploaded' or 'error'."""
        try:
            with open(local_file, "rb") as src:
                with smbclient.open_file(remote_path, mode="wb") as dst:
                    dst.write(src.read())
            return "uploaded"
        except OSError as e:
            console.print(f"[red]Failed to upload {local_file.name}: {e}[/red]")
            return "error"

    def _show_upload_summary(self, files_uploaded: int, files_skipped: int) -> None:
        """Show upload completion summary."""
        console.print(f"[green]✓ Uploaded {files_uploaded} files to NAS[/green]")
        if files_skipped > 0:
            console.print(f"[yellow]  Skipped {files_skipped} existing files (use --overwrite to replace)[/yellow]")

    def test_connection(self, dry_run: bool = False) -> bool:
        """
        Test the NAS SMB connection.

        Returns: True if connection test passed
        """
        self._print_connection_info()

        if dry_run:
            console.print("[yellow]DRY RUN: Would test connection to NAS[/yellow]")
            return True

        try:
            smbclient = _get_smbclient()
        except ImportError:
            console.print("[red]✗ smbprotocol not installed. Run: pip install smbprotocol[/red]")
            return False

        try:
            return self._run_connection_tests(smbclient)
        except OSError as e:
            console.print(f"[red]✗ NAS connection test failed: {e}[/red]")
            return False

    def _print_connection_info(self) -> None:
        """Print NAS connection information."""
        console.print("\n[bold cyan]NAS Connection Test[/bold cyan]")
        console.print("─" * 40)
        console.print(f"[cyan]Host:[/cyan] {self.host}")
        console.print(f"[cyan]Share:[/cyan] {self.share}")
        console.print(f"[cyan]Base path:[/cyan] {self.base_path or '(root)'}")
        console.print(f"[cyan]Username:[/cyan] {self.username}")
        console.print("─" * 40)

    def _run_connection_tests(self, smbclient) -> bool:
        """Run all connection tests."""
        self._test_smb_session(smbclient)
        self._test_share_access(smbclient)
        self._test_base_path_access(smbclient)
        self._test_share_info(smbclient)

        console.print("─" * 40)
        console.print("[bold green]✓ All NAS connection tests passed![/bold green]")
        return True

    def _test_smb_session(self, smbclient) -> None:
        """Test SMB session establishment."""
        console.print("[cyan]Testing SMB session...[/cyan]")
        smbclient.register_session(self.host, username=self.username, password=self.password)
        console.print("[green]✓ SMB session established[/green]")

    def _test_share_access(self, smbclient) -> None:
        """Test share accessibility."""
        console.print("[cyan]Testing share access...[/cyan]")
        share_path = f"\\\\{self.host}\\{self.share}"
        items = smbclient.listdir(share_path)
        console.print(f"[green]✓ Share accessible ({len(items)} items in root)[/green]")

    def _test_base_path_access(self, smbclient) -> None:
        """Test base path access if specified."""
        if not self.base_path:
            return

        console.print("[cyan]Testing base path access...[/cyan]")
        full_path = f"\\\\{self.host}\\{self.share}\\{self.base_path}"
        try:
            items = smbclient.listdir(full_path)
            console.print(f"[green]✓ Base path exists ({len(items)} items)[/green]")
        except FileNotFoundError:
            console.print("[yellow]⚠ Base path does not exist (will be created on upload)[/yellow]")

    def _test_share_info(self, smbclient) -> None:
        """Test share info access."""
        console.print("[cyan]Checking share info...[/cyan]")
        share_path = f"\\\\{self.host}\\{self.share}"
        try:
            smbclient.stat(share_path)
            console.print("[green]✓ Share is accessible[/green]")
        except OSError:
            console.print("[yellow]⚠ Could not get share stats (may still work)[/yellow]")
