"""
Mail archiving functionality.

Provides the MailArchiver class for connecting to IMAP servers,
listing folders, and downloading emails with attachments.
"""

import email
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from pathvalidate import sanitize_filename

from .utils import create_progress_bar, decode_mime_header

console = Console()


class MailArchiver:
    """Main class for archiving mail from any IMAP server."""

    def __init__(self, email_address: str, password: str, provider_config: dict):
        self.email_address = email_address
        self.password = password
        self.imap_host = provider_config["imap_host"]
        self.imap_port = provider_config.get("imap_port", 993)
        self.ssl = provider_config.get("ssl", True)
        self.provider_name = provider_config.get("name", "Mail Server")
        self.client: Optional[IMAPClient] = None

    def connect(self) -> bool:
        """Connect to IMAP server."""
        try:
            console.print(f"[cyan]Connecting to {self.imap_host}...[/cyan]")
            self.client = IMAPClient(self.imap_host, port=self.imap_port, ssl=self.ssl)
            self.client.login(self.email_address, self.password)
            console.print("[green]✓ Successfully connected and logged in[/green]")
            return True
        except IMAPClientError as e:
            console.print(f"[red]✗ Failed to connect: {e}[/red]")
            return False
        except OSError as e:
            console.print(f"[red]✗ Network error: {e}[/red]")
            return False

    def disconnect(self):
        """Disconnect from the IMAP server."""
        if self.client:
            try:
                self.client.logout()
                console.print("[cyan]Disconnected from server[/cyan]")
            except IMAPClientError:
                pass

    def list_folders(self) -> list[tuple[str, str | int]]:
        """List all mail folders."""
        if not self.client:
            return []

        folders = []
        for _flags, _delimiter, name in self.client.list_folders():
            msg_count = self._get_folder_count_safe(name)
            folders.append((name, msg_count))

        return folders

    def _get_folder_count_safe(self, folder_name: str) -> str | int:
        """Get message count for a folder, returning '?' on error."""
        if not self.client:
            return "?"
        try:
            select_info = self.client.select_folder(folder_name, readonly=True)
            return select_info.get(b"EXISTS", 0)
        except IMAPClientError:
            return "?"

    def display_folders(self, folders: list[tuple[str, str | int]]) -> None:
        """Display folders in a nice table."""
        table = Table(title=f"{self.provider_name} Folders")
        table.add_column("#", style="cyan", justify="right")
        table.add_column("Folder Name", style="green")
        table.add_column("Messages", style="yellow", justify="right")

        for idx, (name, count) in enumerate(folders, 1):
            table.add_row(str(idx), name, str(count))

        console.print(table)

    def get_folder_message_count(self, folder_name: str) -> int:
        """Get the number of messages in a folder."""
        if not self.client:
            return 0

        try:
            select_info = self.client.select_folder(folder_name, readonly=True)
            return select_info.get(b"EXISTS", 0)
        except IMAPClientError as e:
            console.print(f"[red]Error selecting folder: {e}[/red]")
            return 0

    def download_folder(self, folder_name: str, output_path: Path, dry_run: bool = False) -> tuple[int, int]:
        """
        Download all emails and attachments from a folder.

        Returns: (emails_downloaded, attachments_downloaded)
        """
        if not self.client:
            return (0, 0)

        total_messages = self._select_folder_for_download(folder_name)
        if total_messages is None:
            return (0, 0)

        if total_messages == 0:
            console.print(f"[yellow]No messages in folder '{folder_name}'[/yellow]")
            return (0, 0)

        if dry_run:
            return self._show_dry_run_info(folder_name, total_messages, output_path)

        # Create output directory
        folder_output = self._create_folder_output_dir(folder_name, output_path)

        # Download messages
        messages = self.client.search(["ALL"])
        return self._download_messages(messages, folder_name, folder_output)

    def _select_folder_for_download(self, folder_name: str) -> Optional[int]:
        """Select a folder and return message count, or None on error."""
        if not self.client:
            return None
        try:
            select_info = self.client.select_folder(folder_name, readonly=True)
            return select_info.get(b"EXISTS", 0)
        except IMAPClientError as e:
            console.print(f"[red]Error selecting folder '{folder_name}': {e}[/red]")
            return None

    def _show_dry_run_info(self, folder_name: str, total_messages: int, output_path: Path) -> tuple[int, int]:
        """Show dry run information and return counts."""
        console.print("\n[cyan]DRY RUN MODE[/cyan]")
        console.print(f"Folder: [green]{folder_name}[/green]")
        console.print(f"Messages to download: [yellow]{total_messages}[/yellow]")
        console.print(f"Output path: [blue]{output_path}[/blue]")
        return (total_messages, 0)

    def _create_folder_output_dir(self, folder_name: str, output_path: Path) -> Path:
        """Create and return the output directory for a folder."""
        folder_safe_name = sanitize_filename(folder_name)
        folder_output = output_path / folder_safe_name
        folder_output.mkdir(parents=True, exist_ok=True)
        return folder_output

    def _download_messages(self, messages: list, folder_name: str, folder_output: Path) -> tuple[int, int]:
        """Download all messages with progress bar."""
        emails_downloaded = 0
        emails_skipped = 0
        attachments_downloaded = 0

        with create_progress_bar() as progress:
            task = progress.add_task(f"Downloading from {folder_name}...", total=len(messages))

            for uid in messages:
                result, attach_count = self._process_single_message(uid, folder_output)
                if result == "downloaded":
                    emails_downloaded += 1
                    attachments_downloaded += attach_count
                elif result == "skipped":
                    emails_skipped += 1
                progress.advance(task)

        self._show_download_summary(emails_downloaded, attachments_downloaded, emails_skipped)
        return (emails_downloaded, attachments_downloaded)

    def _process_single_message(self, uid: int, folder_output: Path) -> tuple[str, int]:
        """
        Process a single message.

        Returns: tuple of (status, attachment_count) where status is
                 'downloaded', 'skipped', or 'error'
        """
        if not self.client:
            return ("error", 0)
        try:
            raw_messages = self.client.fetch([uid], ["RFC822", "INTERNALDATE"])

            if uid not in raw_messages:
                return ("error", 0)

            raw_email = raw_messages[uid][b"RFC822"]
            internal_date = raw_messages[uid].get(b"INTERNALDATE", datetime.now())
            msg = email.message_from_bytes(raw_email)

            email_dir = self._create_email_directory(msg, uid, internal_date, folder_output)
            email_path = email_dir / "email.eml"

            # Check if email already exists with same size
            if self._should_skip_email(email_path, raw_email):
                return ("skipped", 0)

            email_dir.mkdir(parents=True, exist_ok=True)
            with open(email_path, "wb") as f:
                f.write(raw_email)

            # Extract attachments
            attachment_count = self._save_attachments(msg, email_dir)
            return ("downloaded", attachment_count)

        except IMAPClientError as e:
            console.print(f"[red]Error processing message {uid}: {e}[/red]")
            return ("error", 0)

    def _create_email_directory(self, msg, uid: int, internal_date: datetime, folder_output: Path) -> Path:
        """Create directory path for an email."""
        subject = decode_mime_header(msg.get("Subject", "No Subject"))
        date_str = internal_date.strftime("%Y%m%d_%H%M%S")
        safe_subject = sanitize_filename(subject)[:50]
        email_dir_name = f"{date_str}_{uid}_{safe_subject}"
        return folder_output / email_dir_name

    def _should_skip_email(self, email_path: Path, raw_email: bytes) -> bool:
        """Check if email should be skipped (same name and size)."""
        if email_path.exists():
            existing_size = email_path.stat().st_size
            return existing_size == len(raw_email)
        return False

    def _save_attachments(self, msg, email_dir: Path) -> int:
        """Save attachments from an email. Returns count of attachments saved."""
        attachments_count = 0

        if not msg.is_multipart():
            return 0

        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" not in content_disposition and "inline" not in content_disposition:
                continue

            filename = part.get_filename()
            if not filename:
                continue

            saved = self._save_single_attachment(part, filename, email_dir)
            if saved:
                attachments_count += 1

        return attachments_count

    def _save_single_attachment(self, part, filename: str, email_dir: Path) -> bool:
        """Save a single attachment. Returns True if saved."""
        filename = decode_mime_header(filename)
        filename = sanitize_filename(filename)
        attachment_path = email_dir / filename

        # Handle duplicate filenames
        counter = 1
        while attachment_path.exists():
            name, ext = os.path.splitext(filename)
            attachment_path = email_dir / f"{name}_{counter}{ext}"
            counter += 1

        payload = part.get_payload(decode=True)
        if payload and isinstance(payload, bytes):
            with open(attachment_path, "wb") as f:
                f.write(payload)
            return True
        return False

    def _show_download_summary(self, emails_downloaded: int, attachments_downloaded: int, emails_skipped: int):
        """Show download completion summary."""
        console.print(
            f"\n[green]✓ Downloaded {emails_downloaded} emails and {attachments_downloaded} attachments[/green]"
        )
        if emails_skipped > 0:
            console.print(f"[yellow]  Skipped {emails_skipped} existing emails (same name and size)[/yellow]")

    def test_connection(self) -> bool:
        """
        Test the IMAP connection by listing folders and checking capabilities.

        Returns: True if connection test passed
        """
        if not self.client:
            console.print("[red]✗ Not connected to server[/red]")
            return False

        console.print(f"\n[bold cyan]{self.provider_name} Connection Test[/bold cyan]")
        console.print("─" * 40)

        try:
            self._test_capabilities()
            self._test_folder_listing()
            self._test_inbox_access()
            self._show_account_info()

            console.print("─" * 40)
            console.print("[bold green]✓ All connection tests passed![/bold green]")
            return True

        except IMAPClientError as e:
            console.print(f"[red]✗ Connection test failed: {e}[/red]")
            return False

    def _test_capabilities(self):
        """Test server capabilities."""
        console.print("[cyan]Testing server capabilities...[/cyan]")
        capabilities = self.client.capabilities()
        console.print(f"[green]✓ Server capabilities: {len(capabilities)} features[/green]")

    def _test_folder_listing(self):
        """Test folder listing."""
        console.print("[cyan]Testing folder listing...[/cyan]")
        folders = self.client.list_folders()
        folder_count = len(list(folders))
        console.print(f"[green]✓ Found {folder_count} folders[/green]")

    def _test_inbox_access(self):
        """Test INBOX access."""
        console.print("[cyan]Testing INBOX access...[/cyan]")
        select_info = self.client.select_folder("INBOX", readonly=True)
        msg_count = select_info.get(b"EXISTS", 0)
        console.print(f"[green]✓ INBOX accessible ({msg_count} messages)[/green]")

    def _show_account_info(self):
        """Show account info."""
        console.print("[cyan]Checking account info...[/cyan]")
        console.print(f"[green]✓ Logged in as: {self.email_address}[/green]")

    def delete_folder_contents(
        self,
        folder_name: str,
        dry_run: bool = False,
        since_date: Optional[datetime] = None,
    ) -> int:
        """
        Delete messages in a folder.

        Args:
            folder_name: Name of the folder to clean
            dry_run: If True, only show what would be deleted
            since_date: If provided, only delete messages older than this date

        Returns: Number of messages deleted
        """
        if not self.client:
            return 0

        total_messages = self._select_folder_for_delete(folder_name)
        if total_messages is None or total_messages == 0:
            if total_messages == 0:
                console.print(f"[yellow]No messages in folder '{folder_name}'[/yellow]")
            return 0

        messages, filter_desc = self._search_messages_for_delete(since_date)

        if len(messages) == 0:
            console.print(f"[yellow]No messages to delete ({filter_desc}) in folder '{folder_name}'[/yellow]")
            return 0

        if dry_run:
            return self._show_delete_dry_run(folder_name, filter_desc, messages, total_messages)

        if not self._confirm_deletion(folder_name, filter_desc, messages, total_messages):
            return 0

        return self._execute_deletion(messages, folder_name)

    def _select_folder_for_delete(self, folder_name: str) -> Optional[int]:
        """Select folder for deletion, returns message count or None on error."""
        if not self.client:
            return None
        try:
            select_info = self.client.select_folder(folder_name, readonly=False)
            return select_info.get(b"EXISTS", 0)
        except IMAPClientError as e:
            console.print(f"[red]Error selecting folder '{folder_name}': {e}[/red]")
            return None

    def _search_messages_for_delete(self, since_date: Optional[datetime]) -> tuple[list, str]:
        """Search for messages to delete based on criteria."""
        if not self.client:
            return [], "no client"
        if since_date:
            date_str = since_date.strftime("%d-%b-%Y")
            messages = self.client.search(["BEFORE", date_str])
            filter_desc = f"older than {since_date.strftime('%Y-%m-%d')}"
        else:
            messages = self.client.search(["ALL"])
            filter_desc = "all messages"
        return messages, filter_desc

    def _show_delete_dry_run(self, folder_name: str, filter_desc: str, messages: list, total_messages: int) -> int:
        """Show dry run info for deletion."""
        console.print("\n[cyan]DRY RUN MODE - Would delete:[/cyan]")
        console.print(f"Folder: [green]{folder_name}[/green]")
        console.print(f"Filter: [yellow]{filter_desc}[/yellow]")
        console.print(f"Messages to delete: [red]{len(messages)}[/red] (of {total_messages} total)")
        return len(messages)

    def _confirm_deletion(self, folder_name: str, filter_desc: str, messages: list, total_messages: int) -> bool:
        """Get user confirmation for deletion."""
        console.print(f"\n[bold red]⚠ WARNING: This will permanently delete {len(messages)} messages![/bold red]")
        console.print(f"Folder: [green]{folder_name}[/green]")
        console.print(f"Filter: [yellow]{filter_desc}[/yellow]")
        console.print(f"Total in folder: {total_messages}")

        if not Confirm.ask("[red]Are you sure you want to delete these messages?[/red]"):
            console.print("[yellow]Deletion cancelled[/yellow]")
            return False

        if not Confirm.ask("[red]This action cannot be undone. Type 'yes' to confirm deletion[/red]"):
            console.print("[yellow]Deletion cancelled[/yellow]")
            return False

        return True

    def _execute_deletion(self, messages: list, folder_name: str) -> int:
        """Execute the actual deletion of messages."""
        if not self.client:
            return 0
        with create_progress_bar() as progress:
            task = progress.add_task("Deleting messages...", total=len(messages))

            self.client.delete_messages(messages)
            progress.update(task, completed=len(messages) // 2)

            self.client.expunge()
            progress.update(task, completed=len(messages))

        console.print(f"[green]✓ Deleted {len(messages)} messages from '{folder_name}'[/green]")
        return len(messages)
