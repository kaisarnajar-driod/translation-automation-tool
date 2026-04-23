# Transync — Android Translation Automation Tool

A CLI and web-based tool that automates Android `strings.xml` localization. Add your Android projects, hit **Sync**, and Transync translates all new strings into your target languages using Google Translate — no API key required.

## Features

- **Multi-project management** — track multiple Android projects via CLI or web UI
- **Google Translate powered** — uses Google's Neural Machine Translation via `deep-translator` (free, no API key needed)
- **Smart diff detection** — only translates new strings (optionally detects modified strings too)
- **Placeholder safety** — validates that `%s`, `%1$s`, HTML tags survive translation; falls back to source on corruption
- **Incremental sync** — SQLite snapshot-based tracking avoids re-translating unchanged strings
- **Web dashboard** — dark-themed single-page UI to add projects, trigger syncs, and view results
- **Beautiful CLI** — Rich-powered tables, progress indicators, and colored output
- **Dry-run mode** — preview what would be translated without writing any files

## Architecture

```
┌──────────────────────────────────────────────────┐
│          CLI (Click + Rich)  /  Web UI (Flask)   │
└─────────────────────┬────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────┐
│              Sync Orchestrator                    │
└──┬────────────┬────────────┬─────────────────────┘
   │            │            │
┌──▼─────┐  ┌──▼─────┐  ┌───▼──────────────────┐
│  Diff  │  │  XML   │  │  Translation Service  │
│ Engine │  │ Proc.  │  │  └─ Google Translate   │
└────────┘  └────────┘  │     (deep-translator)  │
                        └────────────────────────┘
┌──────────────────────────────────────────────────┐
│               SQLite Database                    │
│       projects · sync_history · snapshots        │
└──────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.9+
- An Android project with `strings.xml` on your local machine

### Installation

```bash
# Clone the repo
git clone git@bitbucket.org:lktech/translation-automation-tool.git
cd translation-automation-tool

# Create a virtual environment and install
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Generate Config

```bash
transync init
```

This creates a `config.yaml` in the current directory. The default translation provider is `google_free` which requires no API key.

### Configuration

Edit `config.yaml` to set your target languages and preferences:

```yaml
target_languages: [hi, ar, fr, es, de]

translation:
  provider: "google_free"

sync:
  dry_run: false
  detect_modified: false
  sort_keys: true

database:
  path: "~/.transync/transync.db"
```

## How to Use

### Option 1: Web UI (Recommended)

Start the web server:

```bash
transync serve
# or specify a port
transync serve --port 9000
```

Open `http://localhost:8090` in your browser. From there you can:

1. **Add a project** — enter the project name, the local path to your Android project, the path to `strings.xml`, target languages, etc.
2. **Sync translations** — click the **Sync** button on any project to translate all new strings
3. **View results** — a modal shows how many new keys were translated and for how many languages
4. **Remove projects** — click **Remove** to stop tracking a project

### Option 2: CLI

```bash
# Add a project (pointing to a local Android project)
transync add my-app https://github.com/org/my-app.git \
  --path ~/projects/my-app \
  --branch main \
  --languages hi,ar,fr,es

# List all tracked projects
transync list

# Sync translations (translates new strings for all target languages)
transync sync my-app

# Dry run — see what would be translated without writing files
transync sync my-app --dry-run

# View sync history
transync history my-app

# Show current configuration
transync config
```

## CLI Commands

| Command  | Description                                |
|----------|--------------------------------------------|
| `init`   | Generate a `config.yaml` from defaults     |
| `add`    | Add an Android project to manage           |
| `remove` | Remove a project from management           |
| `list`   | List all managed projects                  |
| `sync`   | Run translation sync for a project         |
| `history`| Show sync history for a project            |
| `config` | Display current configuration              |
| `serve`  | Start the web UI server                    |

## Sync Workflow

When you run `transync sync <project>` (or click Sync in the web UI):

1. **Parse** — reads the current `values/strings.xml` from disk
2. **Snapshot** — loads the previous string state from the database (or falls back to the previous version of the file)
3. **Diff** — identifies new keys (and optionally modified keys if `detect_modified` is enabled)
4. **Translate** — sends new strings to Google Translate for each target language
5. **Validate** — checks that placeholders (`%s`, `%1$d`, etc.) and HTML tags are preserved in translated text
6. **Merge** — inserts translations into `values-{lang}/strings.xml` files
7. **Save** — stores a snapshot of the current strings for the next incremental sync

## Environment Variables

| Variable              | Description                                |
|-----------------------|--------------------------------------------|
| `TRANSYNC_CONFIG`     | Path to config file                        |
| `TRANSYNC_PROVIDER`   | Override translation provider              |
| `TRANSYNC_LOG_LEVEL`  | Override log level (DEBUG/INFO/WARNING)     |

## License

MIT
