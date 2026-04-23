# Transync — Android Translation Automation Tool

A production-grade CLI tool that manages multiple Git-based Android projects and automates localization sync for `strings.xml` resources.

## Features

- **Multi-project management** — track multiple Android Git repos
- **Smart diff detection** — only translate new or modified strings
- **Pluggable translation** — OpenAI/GPT, DeepL, Google Translate, or custom providers
- **Placeholder safety** — validates `%s`, `%1$s`, HTML tags survive translation
- **Git automation** — branch creation, commit, push (or dry-run)
- **Incremental sync** — snapshot-based tracking avoids re-translating
- **Beautiful CLI** — Rich-powered tables and progress indicators

## Architecture

```
┌─────────────────────────────────────────────┐
│                CLI (Click + Rich)            │
└────────────────┬────────────────────────────┘
                 │
┌────────────────▼────────────────────────────┐
│           Sync Orchestrator                  │
└──┬──────┬──────┬──────┬─────────────────────┘
   │      │      │      │
┌──▼──┐ ┌─▼──┐ ┌▼───┐ ┌▼──────────────────┐
│ Git │ │Diff│ │ XML│ │ Translation Svc    │
│ Svc │ │Eng.│ │Proc│ │ ├─ OpenAI Provider │
└─────┘ └────┘ └────┘ │ ├─ DeepL Provider  │
                       │ ├─ Google Provider │
                       │ └─ Mock Provider   │
                       └────────────────────┘
┌─────────────────────────────────────────────┐
│         SQLite Database                      │
│   projects · sync_history · snapshots        │
└─────────────────────────────────────────────┘
```

## Quick Start

### Installation

```bash
# Clone and install
git clone <this-repo>
cd android-translation-automation-tool
pip install -e ".[dev]"

# Generate config
transync init
```

### Configuration

Edit `config.yaml`:

```yaml
target_languages: [hi, ar, fr, es, de]

translation:
  provider: "openai"
  openai:
    api_key: ""  # or set OPENAI_API_KEY env var
```

### Usage

```bash
# Add a project
transync add my-app https://github.com/org/my-app.git \
  --path ~/projects/my-app \
  --branch main \
  --languages hi,ar,fr,es

# List projects
transync list

# Sync translations
transync sync my-app

# Dry run (no commit)
transync sync my-app --dry-run

# View sync history
transync history my-app

# Show config
transync config

# Remove a project
transync remove my-app
```

## CLI Commands

| Command   | Description                                    |
|-----------|------------------------------------------------|
| `init`    | Generate a `config.yaml` from defaults         |
| `add`     | Add a project (Git repo) to manage             |
| `remove`  | Remove a project                               |
| `list`    | List all managed projects                      |
| `sync`    | Run translation sync for a project             |
| `history` | Show sync history for a project                |
| `config`  | Display current configuration                  |

## Sync Workflow

When you run `transync sync <project>`:

1. **Pull** — ensures clean repo, pulls latest from remote
2. **Parse** — reads current `values/strings.xml`
3. **Snapshot** — loads previous string state from DB (or git history)
4. **Diff** — identifies new/modified keys
5. **Translate** — sends new strings to translation provider for each language
6. **Merge** — inserts translations into `values-{lang}/strings.xml`
7. **Commit & Push** — stages, commits, pushes (or creates branch)
8. **Save** — stores snapshot for next incremental sync

## Translation Providers

### OpenAI (default)
Uses GPT models with a specialized system prompt that preserves placeholders and HTML.

```bash
export OPENAI_API_KEY="sk-..."
```

### DeepL
```bash
export DEEPL_API_KEY="..."
```

Update config: `translation.provider: "deepl"`

### Google Translate
```bash
export GOOGLE_TRANSLATE_API_KEY="..."
```

Update config: `translation.provider: "google"`

### Mock (for testing)
Returns `[lang] original text` — useful for dry runs and testing.

Update config: `translation.provider: "mock"`

## Environment Variables

| Variable                    | Description                         |
|-----------------------------|-------------------------------------|
| `OPENAI_API_KEY`            | OpenAI API key                      |
| `DEEPL_API_KEY`             | DeepL API key                       |
| `GOOGLE_TRANSLATE_API_KEY`  | Google Translate API key            |
| `TRANSYNC_CONFIG`           | Path to config file                 |
| `TRANSYNC_PROVIDER`         | Override translation provider       |
| `TRANSYNC_LOG_LEVEL`        | Override log level (DEBUG/INFO/...) |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check transync/ tests/

# Type check
mypy transync/
```

## License

MIT
