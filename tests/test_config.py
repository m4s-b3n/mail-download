"""
Tests for provider configuration and loading functionality.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from src.archiver import MailArchiver
from src.config import (
    CONFIG_PATHS,
    get_default_provider,
    load_provider_config,
)


class TestLoadProviderConfig:
    """Tests for load_provider_config function."""

    def test_load_gmx_from_config_file(self, tmp_path):
        """Should load GMX config from YAML file."""
        config_content = """
providers:
  gmx:
    name: GMX Mail
    imap_host: imap.gmx.net
    imap_port: 993
    ssl: true
default: gmx
"""
        config_file = tmp_path / "providers.yaml"
        config_file.write_text(config_content)

        result = load_provider_config("gmx", config_file)

        assert result["name"] == "GMX Mail"
        assert result["imap_host"] == "imap.gmx.net"
        assert result["imap_port"] == 993
        assert result["ssl"] is True

    def test_load_gmail_from_config_file(self, tmp_path):
        """Should load Gmail config from YAML file."""
        config_content = """
providers:
  gmail:
    name: Google Gmail
    imap_host: imap.gmail.com
    imap_port: 993
    ssl: true
"""
        config_file = tmp_path / "providers.yaml"
        config_file.write_text(config_content)

        result = load_provider_config("gmail", config_file)

        assert result["name"] == "Google Gmail"
        assert result["imap_host"] == "imap.gmail.com"

    def test_load_unknown_provider_raises_error(self, tmp_path):
        """Should raise ValueError for unknown provider."""
        config_content = """
providers:
  gmx:
    name: GMX Mail
    imap_host: imap.gmx.net
    imap_port: 993
    ssl: true
"""
        config_file = tmp_path / "providers.yaml"
        config_file.write_text(config_content)

        with pytest.raises(ValueError) as exc_info:
            load_provider_config("unknown_provider", config_file)

        assert "Unknown provider 'unknown_provider'" in str(exc_info.value)
        assert "Available: gmx" in str(exc_info.value)

    def test_fallback_to_builtin_defaults_gmx(self, tmp_path):
        """Should use built-in defaults when no config file found."""
        # Use a non-existent config path
        nonexistent_path = tmp_path / "nonexistent" / "providers.yaml"

        result = load_provider_config("gmx", nonexistent_path)

        assert result["name"] == "GMX Mail"
        assert result["imap_host"] == "imap.gmx.net"
        assert result["imap_port"] == 993
        assert result["ssl"] is True

    def test_fallback_to_builtin_defaults_gmail(self, tmp_path):
        """Should use built-in defaults for Gmail when no config file."""
        nonexistent_path = tmp_path / "nonexistent" / "providers.yaml"

        result = load_provider_config("gmail", nonexistent_path)

        assert result["name"] == "Gmail"
        assert result["imap_host"] == "imap.gmail.com"

    def test_fallback_to_builtin_defaults_outlook(self, tmp_path):
        """Should use built-in defaults for Outlook when no config file."""
        nonexistent_path = tmp_path / "nonexistent" / "providers.yaml"

        result = load_provider_config("outlook", nonexistent_path)

        assert result["name"] == "Outlook"
        assert result["imap_host"] == "outlook.office365.com"

    def test_unknown_provider_without_config_raises_error(self, tmp_path):
        """Should raise error for unknown provider when no config file."""
        nonexistent_path = tmp_path / "nonexistent" / "providers.yaml"

        with pytest.raises(ValueError) as exc_info:
            load_provider_config("yahoo", nonexistent_path)

        assert "Unknown provider 'yahoo'" in str(exc_info.value)
        assert "no config file found" in str(exc_info.value)

    def test_custom_provider_uses_environment_variables(self, tmp_path):
        """Custom provider should substitute environment variables."""
        config_content = """
providers:
  custom:
    name: Custom IMAP Server
    imap_host: "${IMAP_HOST}"
    imap_port: "${IMAP_PORT:-993}"
    ssl: "${IMAP_SSL:-true}"
"""
        config_file = tmp_path / "providers.yaml"
        config_file.write_text(config_content)

        with patch.dict(
            os.environ,
            {"IMAP_HOST": "mail.example.com", "IMAP_PORT": "587", "IMAP_SSL": "false"},
        ):
            result = load_provider_config("custom", config_file)

        assert result["imap_host"] == "mail.example.com"
        assert result["imap_port"] == 587
        assert result["ssl"] is False

    def test_custom_provider_ssl_variations(self, tmp_path):
        """Custom provider should handle various SSL env values."""
        config_content = """
providers:
  custom:
    name: Custom
    imap_host: mail.test.com
    imap_port: 993
    ssl: true
"""
        config_file = tmp_path / "providers.yaml"
        config_file.write_text(config_content)

        # Test "yes" as true
        with patch.dict(os.environ, {"IMAP_SSL": "yes"}, clear=False):
            result = load_provider_config("custom", config_file)
            assert result["ssl"] is True

        # Test "1" as true
        with patch.dict(os.environ, {"IMAP_SSL": "1"}, clear=False):
            result = load_provider_config("custom", config_file)
            assert result["ssl"] is True

        # Test "no" as false
        with patch.dict(os.environ, {"IMAP_SSL": "no"}, clear=False):
            result = load_provider_config("custom", config_file)
            assert result["ssl"] is False

    def test_searches_default_config_paths(self):
        """Should search through default CONFIG_PATHS."""
        # Verify CONFIG_PATHS contains expected locations
        assert len(CONFIG_PATHS) == 3
        # First path should be relative to the module
        assert "config" in str(CONFIG_PATHS[0])
        assert "providers.yaml" in str(CONFIG_PATHS[0])


class TestGetDefaultProvider:
    """Tests for get_default_provider function."""

    def test_returns_default_from_config(self, tmp_path):
        """Should return default provider from config file."""
        config_content = """
providers:
  gmx:
    name: GMX
    imap_host: imap.gmx.net
    imap_port: 993
    ssl: true
  gmail:
    name: Gmail
    imap_host: imap.gmail.com
    imap_port: 993
    ssl: true
default: gmail
"""
        config_file = tmp_path / "providers.yaml"
        config_file.write_text(config_content)

        result = get_default_provider(config_file)

        assert result == "gmail"

    def test_returns_gmx_when_no_default_specified(self, tmp_path):
        """Should return 'gmx' when config has no default key."""
        config_content = """
providers:
  gmx:
    name: GMX
    imap_host: imap.gmx.net
    imap_port: 993
    ssl: true
"""
        config_file = tmp_path / "providers.yaml"
        config_file.write_text(config_content)

        result = get_default_provider(config_file)

        assert result == "gmx"

    def test_returns_gmx_when_no_config_file(self, tmp_path):
        """Should return 'gmx' when no config file exists."""
        nonexistent_path = tmp_path / "nonexistent" / "providers.yaml"

        result = get_default_provider(nonexistent_path)

        assert result == "gmx"


class TestMailArchiverWithProviderConfig:
    """Tests for MailArchiver initialization with provider config."""

    def test_archiver_uses_provider_host(self):
        """MailArchiver should use host from provider config."""
        config = {
            "name": "Test Provider",
            "imap_host": "imap.test.com",
            "imap_port": 993,
            "ssl": True,
        }

        archiver = MailArchiver("user@test.com", "password", config)

        assert archiver.imap_host == "imap.test.com"
        assert archiver.imap_port == 993
        assert archiver.ssl is True
        assert archiver.provider_name == "Test Provider"

    def test_archiver_uses_default_port(self):
        """MailArchiver should use default port when not specified."""
        config = {
            "name": "Minimal Config",
            "imap_host": "imap.minimal.com",
        }

        archiver = MailArchiver("user@test.com", "password", config)

        assert archiver.imap_port == 993  # default

    def test_archiver_uses_default_ssl(self):
        """MailArchiver should use default ssl=True when not specified."""
        config = {
            "name": "No SSL Config",
            "imap_host": "imap.test.com",
            "imap_port": 143,
        }

        archiver = MailArchiver("user@test.com", "password", config)

        assert archiver.ssl is True  # default

    def test_archiver_connects_with_config_settings(self):
        """MailArchiver.connect should use settings from config."""
        config = {
            "name": "Gmail",
            "imap_host": "imap.gmail.com",
            "imap_port": 993,
            "ssl": True,
        }

        with patch("src.archiver.IMAPClient") as mock_imap:
            mock_client = MagicMock()
            mock_imap.return_value = mock_client

            archiver = MailArchiver("user@gmail.com", "app-password", config)
            archiver.connect()

            mock_imap.assert_called_once_with("imap.gmail.com", port=993, ssl=True)
            mock_client.login.assert_called_once_with("user@gmail.com", "app-password")


class TestProviderConfigFile:
    """Tests to verify the actual config file structure."""

    def test_config_file_exists(self):
        """The providers.yaml config file should exist."""
        config_path = Path(__file__).parent.parent / "config" / "providers.yaml"
        assert config_path.exists(), f"Config file not found at {config_path}"

    def test_config_file_valid_yaml(self):
        """The providers.yaml should be valid YAML."""
        config_path = Path(__file__).parent.parent / "config" / "providers.yaml"

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        assert "providers" in config
        assert "default" in config

    def test_config_has_required_providers(self):
        """Config should have all expected providers."""
        config_path = Path(__file__).parent.parent / "config" / "providers.yaml"

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        providers = config["providers"]
        expected_providers = ["gmx", "gmail", "outlook", "yahoo", "icloud", "custom"]

        for provider in expected_providers:
            assert provider in providers, f"Missing provider: {provider}"

    def test_config_providers_have_required_fields(self):
        """Each provider should have required fields."""
        config_path = Path(__file__).parent.parent / "config" / "providers.yaml"

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        required_fields = ["name", "imap_host", "imap_port", "ssl"]

        for provider_name, provider_config in config["providers"].items():
            for field in required_fields:
                assert field in provider_config, f"Provider '{provider_name}' missing field: {field}"

    def test_config_default_is_valid_provider(self):
        """Default provider should be a valid provider in the config."""
        config_path = Path(__file__).parent.parent / "config" / "providers.yaml"

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        default = config["default"]
        providers = config["providers"]

        assert default in providers, f"Default provider '{default}' not in providers list"
