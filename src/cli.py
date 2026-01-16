"""
Command-line interface for the mail archive tool.

Provides argument parsing and the main entry point,
with handlers for different operations.
"""

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from pathvalidate import sanitize_filename
from rich.console import Console
from rich.prompt import Prompt

from .archiver import MailArchiver
from .config import (
    MailConfig,
    NASConfig,
    get_default_provider,
    load_provider_config,
    parse_time_range,
)
from .uploader import NASUploader
from .utils import delete_directory

console = Console()


@dataclass
class DownloadOptions:
    """Options for downloading emails."""

    folder: Optional[str]
    output: str
    since: Optional[str]
    overwrite: bool
    clean: bool
    delete_local: bool


@dataclass
class UploadContext:
    """Context for NAS upload operation."""

    nas_config: NASConfig
    mail_config: MailConfig
    folder_name: str
    local_folder: Path
    emails_count: int


@dataclass
class TestOptions:
    """Options for connection testing."""

    mail: bool
    nas: bool


@dataclass
class ProviderOptions:
    """Options for mail provider configuration."""

    name: Optional[str]
    config_path: Optional[str]


@dataclass
class CLIArgs:
    """Parsed command-line arguments."""

    list_folders: bool
    download: DownloadOptions
    nas: bool
    dry_run: bool
    interactive: bool
    provider: ProviderOptions
    test: TestOptions


def parse_args() -> CLIArgs:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Mail Archive Download Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list                     List all mail folders
  %(prog)s --folder INBOX             Download INBOX folder locally
  %(prog)s --folder INBOX --nas       Download and upload to NAS
  %(prog)s --folder INBOX --dry-run   Show what would be downloaded
  %(prog)s --folder INBOX --clean     Delete folder contents after download
  %(prog)s --provider gmail           Use Gmail instead of default provider
  %(prog)s --test-mail                Test IMAP connection
  %(prog)s --test-nas                 Test NAS SMB connection
  %(prog)s --test-mail --test-nas     Test both connections
        """,
    )

    _add_arguments(parser)
    args = parser.parse_args()

    download_options = DownloadOptions(
        folder=args.folder,
        output=args.output,
        since=args.since,
        overwrite=args.overwrite,
        clean=args.clean,
        delete_local=args.delete_local,
    )

    test_options = TestOptions(
        mail=args.test_mail,
        nas=args.test_nas,
    )

    provider_options = ProviderOptions(
        name=args.provider,
        config_path=args.config,
    )

    return CLIArgs(
        list_folders=args.list,
        download=download_options,
        nas=args.nas,
        dry_run=args.dry_run,
        interactive=args.interactive,
        provider=provider_options,
        test=test_options,
    )


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    """Add all command line arguments to the parser."""
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List all mail folders and their message counts",
    )
    parser.add_argument(
        "--folder",
        "-f",
        type=str,
        help="Folder name to download (use --list to see available folders)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="./downloads",
        help="Local output directory (default: ./downloads)",
    )
    parser.add_argument(
        "--nas",
        action="store_true",
        help="Upload to NAS after downloading",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files on NAS (default: skip existing)",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be done without actually doing it",
    )
    parser.add_argument(
        "--clean",
        "-c",
        action="store_true",
        help="Delete emails from folder. With --since: clean only (no download)",
    )
    parser.add_argument(
        "--since",
        type=str,
        help="With --clean: delete emails older than this (e.g., 6M, 1Y, 30D, 2W)",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Interactive mode: select folder from list",
    )
    parser.add_argument(
        "--provider",
        "-p",
        type=str,
        help="Mail provider (gmx, gmail, outlook, yahoo, icloud, custom). Default from config or gmx",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to providers config file",
    )
    parser.add_argument(
        "--test-mail",
        action="store_true",
        help="Test mail IMAP connection and exit",
    )
    parser.add_argument(
        "--test-nas",
        action="store_true",
        help="Test NAS SMB connection and exit",
    )
    parser.add_argument(
        "--delete-local",
        action="store_true",
        help="Delete local files after successful NAS upload",
    )


def select_folder_interactive(folders: list[tuple[str, str | int]]) -> Optional[str]:
    """Let user select a folder interactively."""
    while True:
        choice = Prompt.ask("\nEnter folder number (or 'q' to quit)", default="1")

        if choice.lower() == "q":
            return None

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(folders):
                return folders[idx][0]
            console.print("[red]Invalid selection. Please try again.[/red]")
        except ValueError:
            console.print("[red]Please enter a number or 'q' to quit.[/red]")


def handle_nas_only_test(args: CLIArgs, nas_config: Optional[NASConfig]) -> None:
    """Handle --test-nas without --test-mail."""
    if nas_config is None:
        console.print("[red]Error: NAS credentials not configured[/red]")
        console.print("Set NAS_HOST, NAS_SHARE, NAS_USERNAME, NAS_PASSWORD in your environment")
        sys.exit(1)

    uploader = NASUploader(nas_config)
    success = uploader.test_connection(dry_run=args.dry_run)
    sys.exit(0 if success else 1)


def handle_connection_tests(
    args: CLIArgs,
    archiver: MailArchiver,
    nas_config: Optional[NASConfig],
) -> None:
    """Handle --test-mail and optionally --test-nas."""
    mail_success = archiver.test_connection()

    if not args.test.nas:
        sys.exit(0 if mail_success else 1)

    # Also test NAS
    if nas_config is None:
        console.print("\n[red]Error: NAS credentials not configured[/red]")
        console.print("Set NAS_HOST, NAS_SHARE, NAS_USERNAME, NAS_PASSWORD in your environment")
        sys.exit(1)

    uploader = NASUploader(nas_config)
    nas_success = uploader.test_connection(dry_run=args.dry_run)

    # Summary
    console.print("\n[bold]Connection Test Summary[/bold]")
    mail_status = "[green]✓ Passed[/green]" if mail_success else "[red]✗ Failed[/red]"
    nas_status = "[green]✓ Passed[/green]" if nas_success else "[red]✗ Failed[/red]"
    console.print(f"  Mail: {mail_status}")
    console.print(f"  NAS:  {nas_status}")
    sys.exit(0 if (mail_success and nas_success) else 1)


def validate_nas_before_download(
    args: CLIArgs,
    nas_config: Optional[NASConfig],
    mail_config: MailConfig,
    folder_name: str,
) -> bool:
    """Validate NAS connection before downloading. Returns True if valid."""
    if nas_config is None:
        console.print("[red]Error: NAS credentials not configured[/red]")
        console.print("Set NAS_HOST, NAS_SHARE, NAS_USERNAME, NAS_PASSWORD in your environment")
        return False

    folder_safe_name = sanitize_filename(folder_name)
    nas_folder_path = nas_config.get_folder_path(mail_config.account_name, folder_safe_name)
    nas_display_path = nas_folder_path.replace("/", "\\").lstrip("\\")
    console.print(f"[dim]NAS target: \\\\{nas_config.host}\\{nas_config.share}\\{nas_display_path}[/dim]")

    # Test NAS connection before downloading (unless dry-run)
    if not args.dry_run:
        console.print("[dim]Validating NAS connection...[/dim]")
        test_uploader = NASUploader(nas_config)
        if not test_uploader.test_connection(dry_run=True):
            console.print("[red]Error: NAS connection failed. Fix NAS settings before downloading.[/red]")
            return False
        console.print("[green]✓ NAS connection validated[/green]")

    return True


def handle_nas_upload(args: CLIArgs, context: UploadContext) -> bool:
    """Handle NAS upload after download. Returns True if successful."""
    if args.dry_run:
        _show_nas_dry_run(context.nas_config, context.mail_config, context.folder_name, args)
        return True

    if context.emails_count == 0:
        return False

    folder_safe_name = sanitize_filename(context.folder_name)
    nas_folder_path = context.nas_config.get_folder_path(context.mail_config.account_name, folder_safe_name)
    upload_config = NASConfig(
        host=context.nas_config.host,
        share=context.nas_config.share,
        username=context.nas_config.username,
        password=context.nas_config.password,
        base_path=nas_folder_path,
    )
    uploader = NASUploader(upload_config)
    files_uploaded, _ = uploader.upload_directory(
        context.local_folder, dry_run=args.dry_run, overwrite=args.download.overwrite
    )
    upload_success = files_uploaded > 0

    # Delete local files after successful upload if requested
    if upload_success and args.download.delete_local:
        console.print(f"[dim]Cleaning up local files: {context.local_folder}[/dim]")
        if delete_directory(context.local_folder):
            console.print("[green]✓ Local files deleted[/green]")

    return upload_success


def _show_nas_dry_run(
    nas_config: Optional[NASConfig],
    mail_config: MailConfig,
    folder_name: str,
    args: CLIArgs,
) -> None:
    """Show dry run info for NAS upload."""
    folder_safe_name = sanitize_filename(folder_name)
    nas_host = nas_config.host if nas_config else "not-configured"
    nas_share = nas_config.share if nas_config else "not-configured"
    nas_path = nas_config.base_path if nas_config else "/mail-archive"
    nas_full_path = f"{nas_path}/{mail_config.account_name}/{folder_safe_name}"
    console.print(f"\n[cyan]DRY RUN: Would upload to NAS: \\\\{nas_host}\\{nas_share}{nas_full_path}[/cyan]")
    console.print(f"[cyan]Overwrite existing: {'Yes' if args.download.overwrite else 'No (skip)'}[/cyan]")
    if args.download.delete_local:
        console.print("[cyan]Would delete local files after upload[/cyan]")


def handle_clean_operation(
    args: CLIArgs,
    archiver: MailArchiver,
    folder_name: str,
    emails_count: int,
) -> None:
    """Handle --clean operation."""
    since_date = None
    if args.download.since:
        try:
            delta = parse_time_range(args.download.since)
            since_date = datetime.now() - delta
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    if args.dry_run:
        archiver.delete_folder_contents(folder_name, dry_run=True, since_date=since_date)
    elif emails_count > 0:
        console.print("\n[bold yellow]Clean mode enabled[/bold yellow]")
        if since_date:
            console.print(f"[yellow]Deleting emails older than: {since_date.strftime('%Y-%m-%d')}[/yellow]")
        archiver.delete_folder_contents(folder_name, dry_run=False, since_date=since_date)
    else:
        console.print("[yellow]Skipping clean: no emails were downloaded[/yellow]")


@dataclass
class SummaryData:
    """Data for final summary display."""

    emails_count: int
    attachments_count: int
    upload_success: bool
    nas_config: Optional[NASConfig]
    output_path: Path


def show_final_summary(args: CLIArgs, summary: SummaryData) -> None:
    """Show final operation summary."""
    if args.dry_run:
        return

    console.print("\n[bold green]✓ Archive complete![/bold green]")
    console.print(f"  Emails: {summary.emails_count}")
    console.print(f"  Attachments: {summary.attachments_count}")

    show_nas = args.nas and summary.upload_success and args.download.delete_local and summary.nas_config is not None
    if show_nas and summary.nas_config:
        console.print(f"  Location: NAS ({summary.nas_config.host})")
    else:
        console.print(f"  Location: {summary.output_path.absolute()}")


def main():
    """Main entry point for the mail archive tool."""
    args = parse_args()

    # Determine provider
    config_path = Path(args.provider.config_path) if args.provider.config_path else None
    provider = args.provider.name or os.getenv("MAIL_PROVIDER") or get_default_provider(config_path)

    # Load configurations
    mail_config = MailConfig.from_env(provider)
    nas_config = NASConfig.from_env()

    # Handle NAS-only test
    if args.test.nas and not args.test.mail:
        handle_nas_only_test(args, nas_config)

    # Check mail credentials
    if mail_config is None:
        console.print("[red]Error: MAIL_EMAIL and MAIL_PASSWORD environment variables are required[/red]")
        console.print("Set them in your environment or create a secrets.env file")
        sys.exit(1)

    # Load provider config
    try:
        provider_config = load_provider_config(provider, config_path)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    # Create archiver and connect
    archiver = MailArchiver(mail_config.email, mail_config.password, provider_config)

    if not archiver.connect():
        sys.exit(1)

    try:
        _execute_main_operation(args, archiver, mail_config, nas_config)
    finally:
        archiver.disconnect()


def _execute_main_operation(
    args: CLIArgs,
    archiver: MailArchiver,
    mail_config: MailConfig,
    nas_config: Optional[NASConfig],
) -> None:
    """Execute the main operation based on arguments."""
    # Handle connection tests
    if args.test.mail:
        handle_connection_tests(args, archiver, nas_config)

    # List folders
    folders = archiver.list_folders()

    if args.list_folders or (not args.download.folder and not args.interactive):
        archiver.display_folders(folders)
        if not args.interactive:
            console.print("\n[dim]Use --folder <name> to download a folder, or --interactive for selection[/dim]")
            return

    # Select folder
    folder_name = _select_folder(args, archiver, folders)
    if not folder_name:
        return

    # Validate folder exists
    folder_names = [f[0] for f in folders]
    if folder_name not in folder_names:
        console.print(f"[red]Folder '{folder_name}' not found[/red]")
        console.print(f"Available folders: {', '.join(folder_names)}")
        return

    # Validate NAS before download if needed
    if args.nas and not validate_nas_before_download(args, nas_config, mail_config, folder_name):
        return

    # Clean-only mode: delete emails without downloading
    if args.download.clean and args.download.since and not args.nas:
        _clean_only(args, archiver, folder_name)
        return

    # Download and process
    _download_and_process(args, archiver, mail_config, nas_config, folder_name)


def _clean_only(
    args: CLIArgs,
    archiver: MailArchiver,
    folder_name: str,
) -> None:
    """Clean emails from folder without downloading."""
    console.print(f"\n[bold]Selected folder: [green]{folder_name}[/green][/bold]")
    console.print("[bold yellow]Clean-only mode (no download)[/bold yellow]")

    since_date = None
    if args.download.since:
        try:
            delta = parse_time_range(args.download.since)
            since_date = datetime.now() - delta
            console.print(f"[yellow]Will delete emails older than: {since_date.strftime('%Y-%m-%d')}[/yellow]")
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    archiver.delete_folder_contents(folder_name, dry_run=args.dry_run, since_date=since_date)

    if not args.dry_run:
        console.print("\n[bold green]✓ Clean complete![/bold green]")


def _select_folder(
    args: CLIArgs,
    archiver: MailArchiver,
    folders: list[tuple[str, str | int]],
) -> Optional[str]:
    """Select folder from args or interactively."""
    folder_name = args.download.folder

    if args.interactive and not folder_name:
        archiver.display_folders(folders)
        folder_name = select_folder_interactive(folders)
        if not folder_name:
            console.print("[yellow]No folder selected. Exiting.[/yellow]")
            return None

    if not folder_name:
        console.print("[red]No folder specified. Use --folder or --interactive[/red]")
        return None

    return folder_name


def _download_and_process(
    args: CLIArgs,
    archiver: MailArchiver,
    mail_config: MailConfig,
    nas_config: Optional[NASConfig],
    folder_name: str,
) -> None:
    """Download folder and handle NAS upload and cleanup."""
    console.print(f"\n[bold]Selected folder: [green]{folder_name}[/green][/bold]")

    # Download emails
    output_path = Path(args.download.output)
    emails_count, attachments_count = archiver.download_folder(folder_name, output_path, dry_run=args.dry_run)

    folder_safe_name = sanitize_filename(folder_name)
    local_folder = output_path / folder_safe_name
    upload_success = False

    # Upload to NAS if requested
    if args.nas and nas_config:
        context = UploadContext(
            nas_config=nas_config,
            mail_config=mail_config,
            folder_name=folder_name,
            local_folder=local_folder,
            emails_count=emails_count,
        )
        upload_success = handle_nas_upload(args, context)

    # Clean folder if requested
    if args.download.clean:
        handle_clean_operation(args, archiver, folder_name, emails_count)

    # Summary
    summary = SummaryData(
        emails_count=emails_count,
        attachments_count=attachments_count,
        upload_success=upload_success,
        nas_config=nas_config,
        output_path=output_path,
    )
    show_final_summary(args, summary)


if __name__ == "__main__":
    main()
