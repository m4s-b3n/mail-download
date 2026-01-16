"""
Utility functions for the mail archive tool.

Provides common functions for MIME decoding and file operations.
"""

import shutil
from email.header import decode_header
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)

console = Console()


def decode_mime_header(header_value: str) -> str:
    """Decode a MIME-encoded header value."""
    if header_value is None:
        return ""

    decoded_parts = []
    for part, encoding in decode_header(header_value):
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(encoding or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(part)

    return "".join(decoded_parts)


def delete_directory(path: Path) -> bool:
    """
    Delete a directory and all its contents.

    Args:
        path: Path to the directory to delete

    Returns:
        True if deletion was successful
    """
    try:
        if path.exists():
            shutil.rmtree(path)
            return True
        return False
    except OSError as e:
        console.print(f"[red]Failed to delete {path}: {e}[/red]")
        return False


def create_progress_bar() -> Progress:
    """Create a standard progress bar instance."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )
