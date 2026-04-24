# Transync — Translation Automation Tool

A CLI and web-based tool that automates string localization across projects. Add your Android, iOS, React, or Backend projects, configure target languages, hit **Sync**, and Transync translates all new strings using Google Translate — no API key required.

## Features

- **Multi-platform support** — Android (XML), iOS (.lproj), React (JSON), Java Backend (JSON), and more — auto-detected from the strings file path
- **Google Translate powered** — uses Google's Neural Machine Translation via `deep-translator` (free, no API key needed)
- **Smart diff detection** — translates new strings, optionally detects modified strings, and automatically removes deleted strings from all language files
- **Placeholder safety** — validates that `%s`, `%1$s`, HTML tags survive translation; falls back to source on corruption
- **Incremental sync** — SQLite snapshot-based tracking avoids re-translating unchanged strings
- **Web dashboard** — dark-themed single-page UI to add projects, trigger syncs, and view results
- **Beautiful CLI** — Rich-powered tables, progress indicators, and colored output
- **Dry-run mode** — preview what would be translated without writing any files
- **Per-project languages** — each project defines its own set of target languages

## Supported Platforms

Transync auto-detects your platform from the `strings_path` you provide and writes translated files to the correct location:

| Platform       | Source `strings_path` example                     | Translated output for `hi`                          |
|----------------|---------------------------------------------------|-----------------------------------------------------|
| **Android**    | `app/src/main/res/values/strings.xml`             | `app/src/main/res/values-hi/strings.xml`            |
| **iOS**        | `MyApp/en.lproj/Localizable.strings`              | `MyApp/hi.lproj/Localizable.strings`                |
| **React**      | `src/locales/en/strings.json`                     | `src/locales/hi/strings.json`                       |
| **Java Backend** | `src/main/resources/i18n/en/strings.json`       | `src/main/resources/i18n/hi/strings.json`           |

Detection rules (checked in order):
1. Parent directory is `values` or `values-*` — uses Android convention (`values-{lang}/`)
2. Parent directory ends with `.lproj` — uses iOS convention (`{lang}.lproj/`)
3. Everything else — uses generic folder-per-language convention (`{lang}/`)

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
│  Diff  │  │  File  │  │  Translation Service  │
│ Engine │  │ Proc.  │  │  └─ Google Translate   │
└────────┘  │XML/JSON│  │     (deep-translator)  │
            └────────┘  └────────────────────────┘
┌──────────────────────────────────────────────────┐
│               SQLite Database                    │
│       projects · sync_history · snapshots        │
└──────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.9+

### Installation

```bash
# Clone the repo
git clone git@bitbucket.org:lktech/translation-automation-tool.git
cd translation-automation-tool

# Install
pip install -e .
```

### Generate Config

```bash
transync init
```

This creates a `config.yaml` in the current directory. The default translation provider is `google_free` which requires no API key.

### Configuration

Edit `config.yaml` to set your preferences:

```yaml
translation:
  provider: "google_free"

sync:
  dry_run: false
  detect_modified: false
  sort_keys: true

database:
  path: "~/.transync/transync.db"
```

Target languages are configured per-project when you add them (via the web UI or CLI), not globally in the config file.

## How to Use

### Option 1: Web UI (Recommended)

Start the web server:

```bash
transync serve
# or specify a port
transync serve --port 9000
```

Open `http://localhost:8090` in your browser. From there you can:

1. **Add a project** — enter the project name, local path, strings file path (platform auto-detected), and target languages
2. **Sync translations** — click the **Sync** button on any project to translate new strings and remove deleted ones
3. **View results** — a modal shows how many keys were added, modified, removed, and for how many languages
4. **Remove projects** — click **Remove** to stop tracking a project

### Option 2: CLI

```bash
# Add an Android project
transync add my-android-app https://github.com/org/my-app.git \
  --path ~/projects/my-app \
  --strings-path app/src/main/res/values/strings.xml \
  --branch main \
  --languages hi,ar,fr,es

# Add an iOS project
transync add my-ios-app https://github.com/org/my-ios-app.git \
  --path ~/projects/my-ios-app \
  --strings-path MyApp/en.lproj/Localizable.strings \
  --languages hi,ar,fr,es

# Add a React project (JSON)
transync add my-react-app https://github.com/org/my-react-app.git \
  --path ~/projects/my-react-app \
  --strings-path src/locales/en/strings.json \
  --languages hi,ar,fr,es

# List all tracked projects
transync list

# Sync translations (translates new strings for all target languages)
transync sync my-android-app

# Dry run — see what would be translated without writing files
transync sync my-react-app --dry-run

# View sync history
transync history my-ios-app

# Show current configuration
transync config
```

## CLI Commands

| Command  | Description                                |
|----------|--------------------------------------------|
| `init`   | Generate a `config.yaml` from defaults     |
| `add`    | Add a project to manage                    |
| `remove` | Remove a project from management           |
| `list`   | List all managed projects                  |
| `sync`   | Run translation sync for a project         |
| `history`| Show sync history for a project            |
| `config` | Display current configuration              |
| `serve`  | Start the web UI server                    |

## Sync Workflow

When you run `transync sync <project>` (or click Sync in the web UI):

1. **Parse** — reads the current strings file from disk (XML or JSON, auto-detected)
2. **Snapshot** — loads the previous string state from the database (or falls back to the previous version of the file)
3. **Diff** — identifies new, modified (if enabled), and removed keys
4. **Translate** — sends new/modified strings to Google Translate for each target language
5. **Validate** — checks that placeholders (`%s`, `%1$d`, etc.) and HTML tags are preserved in translated text
6. **Merge** — inserts translations into platform-specific language files
7. **Remove** — deletes removed keys from all language files
8. **Save** — stores a snapshot of the current strings for the next incremental sync

## Environment Variables

| Variable              | Description                                |
|-----------------------|--------------------------------------------|
| `TRANSYNC_CONFIG`     | Path to config file                        |
| `TRANSYNC_PROVIDER`   | Override translation provider              |
| `TRANSYNC_LOG_LEVEL`  | Override log level (DEBUG/INFO/WARNING)     |

## License

Copyright (c) Lenskart. All rights reserved.

This software is proprietary and confidential. Unauthorized copying, distribution, or use of this software, via any medium, is strictly prohibited.
