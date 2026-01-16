# Mail Archive Download Tool

[![Tests](https://github.com/m4s-b3n/mail-download/actions/workflows/test.yml/badge.svg)](https://github.com/m4s-b3n/mail-download/actions/workflows/test.yml)
[![Release](https://github.com/m4s-b3n/mail-download/actions/workflows/release.yml/badge.svg)](https://github.com/m4s-b3n/mail-download/actions/workflows/release.yml)

A Docker-based tool to download and archive emails from various mail providers (GMX, Gmail, Outlook, Yahoo, iCloud). Supports localStorage and NAS upload via SMB.

## Features

- 📧 **Multi-Provider Support**: GMX, Gmail, Outlook, Yahoo, iCloud, or custom IMAP servers
- 📁 **Folder Listing**: View all mail folders with message counts
- 💾 **Email Download**: Download complete emails (.eml) and attachments
- 🗄️ **NAS Upload**: Upload archives to NAS via SMB (organized by account/folder)
- 🔍 **Dry Run Mode**: Preview what would be downloaded without changes
- 🗑️ **Clean Mode**: Delete folder contents after download (with confirmation)
- 🐳 **Docker First**: Designed to run as a container for easy deployment
- ⏭️ **Skip Existing**: Don't overwrite files on NAS (optional `--overwrite` flag)

## Quick Start

### Prerequisites

- Docker
- Mail account with IMAP access enabled (GMX, Gmail, Outlook, etc.)

### Pull the Image

```bash
docker pull ghcr.io/m4s-b3n/mail-archive:latest
```

Or build locally:

```bash
git clone https://github.com/m4s-b3n/gmx-archive-download.git
cd gmx-archive-download
docker build -t mail-archive .
```

### Configuration

Create an environment file for your credentials:

```bash
# Create secrets file
cat > .env << 'EOF'
MAIL_EMAIL=your@email.com
MAIL_PASSWORD=your-app-password
MAIL_PROVIDER=gmx

# For NAS upload (optional)
NAS_HOST=192.168.1.100
NAS_SHARE=backup
NAS_USERNAME=admin
NAS_PASSWORD=secret
NAS_PATH=/mail-archive
EOF
```

#### Environment Variables

| Variable        | Description                                | Required       |
| --------------- | ------------------------------------------ | -------------- |
| `MAIL_EMAIL`    | Your email address                         | ✅             |
| `MAIL_PASSWORD` | Your password or app password              | ✅             |
| `MAIL_PROVIDER` | Provider name (default: gmx)               | Optional       |
| `NAS_HOST`      | NAS IP/hostname                            | For NAS upload |
| `NAS_SHARE`     | SMB share name                             | For NAS upload |
| `NAS_USERNAME`  | NAS username                               | For NAS upload |
| `NAS_PASSWORD`  | NAS password                               | For NAS upload |
| `NAS_PATH`      | Path within share (default: /mail-archive) | Optional       |

## Usage

All examples assume you have a `.env` file with your credentials.

### Test Connections

```bash
# Test mail connection
docker run --rm --env-file .env ghcr.io/m4s-b3n/mail-archive:latest --test-mail

# Test NAS connection
docker run --rm --env-file .env ghcr.io/m4s-b3n/mail-archive:latest --test-nas

# Test both
docker run --rm --env-file .env ghcr.io/m4s-b3n/mail-archive:latest --test-mail --test-nas
```

### List All Folders

```bash
docker run --rm --env-file .env ghcr.io/m4s-b3n/mail-archive:latest --list
```

### Download a Folder

```bash
# Download INBOX to local ./downloads directory
docker run --rm --env-file .env \
  -v $(pwd)/downloads:/app/downloads \
  ghcr.io/m4s-b3n/mail-archive:latest --folder INBOX

# Download to custom directory
docker run --rm --env-file .env \
  -v /path/to/archive:/app/downloads \
  ghcr.io/m4s-b3n/mail-archive:latest --folder INBOX
```

### Interactive Mode

Select a folder from a menu:

```bash
docker run --rm -it --env-file .env \
  -v $(pwd)/downloads:/app/downloads \
  ghcr.io/m4s-b3n/mail-archive:latest --interactive
```

### Upload to NAS

Download and upload directly to NAS:

```bash
# Download and upload to NAS (keeps local copy)
docker run --rm --env-file .env \
  -v $(pwd)/downloads:/app/downloads \
  ghcr.io/m4s-b3n/mail-archive:latest --folder INBOX --nas

# Upload to NAS and delete local files after
docker run --rm --env-file .env ghcr.io/m4s-b3n/mail-archive:latest --folder INBOX --nas --delete-local

# Overwrite existing files on NAS
docker run --rm --env-file .env ghcr.io/m4s-b3n/mail-archive:latest --folder INBOX --nas --overwrite
```

Files are organized on NAS as: `<NAS_PATH>/<mail_account>/<folder_name>/`  
Example: `/mail-archive/john.doe/INBOX/`

### Interactive Mode with NAS Upload (Recommended)

The recommended way to archive emails to your NAS:

```bash
docker run --rm -it --env-file .env ghcr.io/m4s-b3n/mail-archive:latest --interactive --nas
```

This will:

1. Show a table of all folders with message counts
2. Let you select a folder by number
3. Download all emails and attachments
4. Upload to NAS at: `<NAS_PATH>/<mail_account>/<folder_name>`
5. Skip files that already exist on NAS (use `--overwrite` to replace)

### Dry Run Mode

Preview what would be downloaded without actually downloading:

```bash
docker run --rm --env-file .env ghcr.io/m4s-b3n/mail-archive:latest --folder INBOX --dry-run
docker run --rm -it --env-file .env ghcr.io/m4s-b3n/mail-archive:latest --interactive --nas --dry-run
```

### Clean Folder After Download

Delete all emails from folder after successful download (requires confirmation):

```bash
docker run --rm -it --env-file .env ghcr.io/m4s-b3n/mail-archive:latest --folder INBOX --nas --clean
```

### Clean Only (No Download)

Use `--clean --since` to delete old emails directly from the server without downloading:

```bash
# Delete emails older than 6 months (no download)
docker run --rm -it --env-file .env \
  ghcr.io/m4s-b3n/mail-archive:latest --folder INBOX --clean --since 6M

# Delete emails older than 1 year (interactive folder selection)
docker run --rm -it --env-file .env \
  ghcr.io/m4s-b3n/mail-archive:latest --interactive --clean --since 1Y

# Preview what would be deleted (dry run)
docker run --rm --env-file .env \
  ghcr.io/m4s-b3n/mail-archive:latest --folder INBOX --clean --since 6M --dry-run
```

Supported time formats: `30D` (days), `2W` (weeks), `6M` (months), `1Y` (years)

### Download, Upload to NAS, then Clean

Use `--clean` with `--nas` to download, upload to NAS, then delete from server:

```bash
# Download to NAS, then delete from server
docker run --rm -it --env-file .env \
  ghcr.io/m4s-b3n/mail-archive:latest --folder INBOX --nas --clean

# Only clean emails older than 6 months after archiving
docker run --rm -it --env-file .env \
  ghcr.io/m4s-b3n/mail-archive:latest --folder INBOX --nas --clean --since 6M
```

### Using Different Providers

```bash
# Gmail (requires app password)
docker run --rm --env-file .env \
  -e MAIL_PROVIDER=gmail \
  ghcr.io/m4s-b3n/mail-archive:latest --list

# Outlook
docker run --rm --env-file .env \
  -e MAIL_PROVIDER=outlook \
  ghcr.io/m4s-b3n/mail-archive:latest --interactive --nas

# Custom IMAP server
docker run --rm --env-file .env \
  -e MAIL_PROVIDER=custom \
  -e MAIL_IMAP_HOST=mail.example.com \
  -e MAIL_IMAP_PORT=993 \
  ghcr.io/m4s-b3n/mail-archive:latest --folder INBOX
```

## Output Structure

Downloaded emails are organized as follows:

```text
downloads/
└── FolderName/
    ├── 20240115_143022_123_Email_Subject/
    │   ├── email.eml
    │   ├── document.pdf
    │   └── image.jpg
    └── 20240115_150845_124_Another_Email/
        ├── email.eml
        └── report.xlsx
```

On NAS:

```text
<NAS_PATH>/
└── <mail_account>/
    └── <folder_name>/
        └── (same structure as above)

Example: /mail-archive/john.doe/INBOX/
```

## Command Line Reference

```text
usage: mail-archive [-h] [--list] [--folder FOLDER] [--output OUTPUT]
                    [--nas] [--overwrite] [--delete-local] [--dry-run]
                    [--clean] [--since SINCE] [--interactive]
                    [--provider PROVIDER] [--config CONFIG]
                    [--test-mail] [--test-nas]

options:
  -h, --help            show this help message and exit
  --list, -l            List all mail folders and their message counts
  --folder FOLDER, -f FOLDER
                        Folder name to download
  --output OUTPUT, -o OUTPUT
                        Local output directory (default: ./downloads)
  --nas                 Upload to NAS after downloading
  --overwrite           Overwrite existing files on NAS (default: skip)
  --delete-local        Delete local files after successful NAS upload
  --dry-run, -n         Show what would be done without doing it
  --clean, -c           Delete emails from folder. With --since: clean only
  --since SINCE         With --clean: delete emails older than this
                        (e.g., 6M, 1Y, 30D, 2W). Without --nas: no download
  --interactive, -i     Interactive mode: select folder from list
  --provider PROVIDER, -p PROVIDER
                        Mail provider (gmx, gmail, outlook, yahoo, icloud, custom)
  --config CONFIG       Path to providers config file
  --test-mail           Test IMAP connection and exit
  --test-nas            Test NAS SMB connection and exit
```

## Supported Providers

| Provider | IMAP Host             | Notes                   |
| -------- | --------------------- | ----------------------- |
| GMX      | imap.gmx.net          | Default provider        |
| Gmail    | imap.gmail.com        | Requires app password   |
| Outlook  | outlook.office365.com | Microsoft 365           |
| Yahoo    | imap.mail.yahoo.com   | Requires app password   |
| iCloud   | imap.mail.me.com      | Requires app password   |
| Custom   | (from env vars)       | Set MAIL_IMAP_HOST/PORT |

## Security Notes

- Never commit your `.env` file to version control
- Use app passwords instead of your main password (required for Gmail, Yahoo, iCloud)
- The Docker image runs as a non-root user

---

## Development

### Development Prerequisites

- Python 3.12+
- pip

### Setup

```bash
# Clone the repository
git clone https://github.com/m4s-b3n/gmx-archive-download.git
cd gmx-archive-download

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running Locally

```bash
# Set environment variables
export MAIL_EMAIL="your@email.com"
export MAIL_PASSWORD="your-app-password"

# Or source from file
source .secrets/secrets.env

# Run the tool
python -m src.cli --list
python -m src.cli --folder INBOX
python -m src.cli --interactive --nas
```

### Running Tests

```bash
pytest tests/ -v
```

### Linting

```bash
pylint --rcfile=.github/linters/.python-lint src/
```

### Building Docker Image

```bash
docker build -t mail-archive .
```

## License

MIT License - See [LICENSE](LICENSE) for details
