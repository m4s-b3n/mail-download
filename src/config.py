"""
Configuration handling for the mail archive tool.

Provides dataclasses for NAS and Mail configuration,
provider config loading, and time range parsing.
"""

import os
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console

console = Console()


# Default config file locations
CONFIG_PATHS = [
    Path(__file__).parent.parent / "config" / "providers.yaml",
    Path.home() / ".config" / "mail-archive" / "providers.yaml",
    Path("/etc/mail-archive/providers.yaml"),
]


@dataclass
class NASConfig:
    """Configuration for NAS connection."""

    host: str
    share: str
    username: str
    password: str
    base_path: str = "/mail-archive"

    @classmethod
    def from_env(cls) -> Optional["NASConfig"]:
        """Load NAS configuration from environment variables."""
        host = os.getenv("NAS_HOST")
        share = os.getenv("NAS_SHARE")
        username = os.getenv("NAS_USERNAME")
        password = os.getenv("NAS_PASSWORD")
        base_path = os.getenv("NAS_PATH", "/mail-archive")

        if not all([host, share, username, password]):
            return None

        # All values are validated above, cast to str
        return cls(
            host=str(host),
            share=str(share),
            username=str(username),
            password=str(password),
            base_path=base_path,
        )

    def get_folder_path(self, mail_account: str, folder_name: str) -> str:
        """Build the full NAS path for a mail folder."""
        return f"{self.base_path}/{mail_account}/{folder_name}"


@dataclass
class MailConfig:
    """Configuration for mail connection."""

    email: str
    password: str
    provider: str

    @classmethod
    def from_env(cls, provider: str) -> Optional["MailConfig"]:
        """Load mail configuration from environment variables."""
        email_addr = os.getenv("MAIL_EMAIL")
        password = os.getenv("MAIL_PASSWORD")

        if not email_addr or not password:
            return None

        return cls(email=email_addr, password=password, provider=provider)

    @property
    def account_name(self) -> str:
        """Get the account name (email without domain)."""
        return self.email.split("@")[0]


def parse_time_range(time_str: str) -> timedelta:
    """
    Parse a time range string into a timedelta.

    Supported formats:
        - 30D, 30d = 30 days
        - 6M, 6m = 6 months (approximated as 30 days each)
        - 1Y, 1y = 1 year (365 days)
        - 2W, 2w = 2 weeks

    Args:
        time_str: Time range string (e.g., '6M', '30D', '1Y')

    Returns:
        timedelta representing the time range

    Raises:
        ValueError: If the format is invalid
    """
    match = re.match(r"^(\d+)([DdMmYyWw])$", time_str.strip())
    if not match:
        raise ValueError(
            f"Invalid time range format: '{time_str}'. "
            "Use formats like: 30D (days), 6M (months), 1Y (years), 2W (weeks)"
        )

    value = int(match.group(1))
    unit = match.group(2).upper()

    if unit == "D":
        return timedelta(days=value)
    if unit == "W":
        return timedelta(weeks=value)
    if unit == "M":
        return timedelta(days=value * 30)  # Approximate months
    if unit == "Y":
        return timedelta(days=value * 365)  # Approximate years
    raise ValueError(f"Unknown time unit: {unit}")


def load_provider_config(provider: str, config_path: Optional[Path] = None) -> dict:
    """
    Load IMAP configuration for a mail provider.

    Args:
        provider: Provider name (e.g., 'gmx', 'gmail', 'outlook')
        config_path: Optional custom config file path

    Returns:
        dict with keys: name, imap_host, imap_port, ssl, description
    """
    # Find config file
    search_paths = [config_path] if config_path else CONFIG_PATHS
    config_file = _find_config_file(search_paths)

    if not config_file:
        return _get_builtin_provider_config(provider)

    return _load_provider_from_file(config_file, provider)


def _find_config_file(search_paths: list) -> Optional[Path]:
    """Find the first existing config file from the search paths."""
    for path in search_paths:
        if path and path.exists():
            return path
    return None


def _get_builtin_provider_config(provider: str) -> dict:
    """Get built-in default configuration for known providers."""
    defaults = {
        "gmx": {
            "name": "GMX Mail",
            "imap_host": "imap.gmx.net",
            "imap_port": 993,
            "ssl": True,
        },
        "gmail": {
            "name": "Gmail",
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "ssl": True,
        },
        "outlook": {
            "name": "Outlook",
            "imap_host": "outlook.office365.com",
            "imap_port": 993,
            "ssl": True,
        },
    }
    if provider in defaults:
        console.print(f"[dim]Using built-in defaults for {provider}[/dim]")
        return defaults[provider]
    raise ValueError(f"Unknown provider '{provider}' and no config file found")


def _load_provider_from_file(config_file: Path, provider: str) -> dict:
    """Load provider configuration from a YAML file."""
    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    providers = config.get("providers", {})

    if provider not in providers:
        available = ", ".join(providers.keys())
        raise ValueError(f"Unknown provider '{provider}'. Available: {available}")

    provider_config = providers[provider]

    # Handle custom provider with environment variable substitution
    if provider == "custom":
        provider_config = _apply_custom_provider_env(provider_config)

    console.print(f"[dim]Loaded provider config: {provider_config.get('name', provider)}[/dim]")
    return provider_config


def _apply_custom_provider_env(provider_config: dict) -> dict:
    """Apply environment variable substitution for custom provider."""
    provider_config["imap_host"] = os.getenv("IMAP_HOST", provider_config.get("imap_host", ""))
    provider_config["imap_port"] = int(os.getenv("IMAP_PORT", provider_config.get("imap_port", 993)))
    ssl_env = os.getenv("IMAP_SSL", str(provider_config.get("ssl", True)))
    provider_config["ssl"] = ssl_env.lower() in ("true", "1", "yes")
    return provider_config


def get_default_provider(config_path: Optional[Path] = None) -> str:
    """Get the default provider from config, or 'gmx' if not found."""
    search_paths = [config_path] if config_path else CONFIG_PATHS

    for path in search_paths:
        if path and path.exists():
            with open(path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("default", "gmx")

    return "gmx"
