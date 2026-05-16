# Hermes Runtime

## Installed State

Hermes was not on `PATH` at the start of this sprint. The upstream repo was cloned locally:

- Repo: `external/hermes-agent`
- Version: `0.13.0`
- Runtime: `external/hermes-agent/.venv`
- Command used by scripts: `external\hermes-agent\.venv\Scripts\hermes.exe`
- Official repo: `https://github.com/NousResearch/hermes-agent`

Hermes config locations on this Windows machine:

- Config: `C:\Users\hacke\.hermes\config.yaml`
- Secrets: `C:\Users\hacke\.hermes\.env`

## Selected Model

Current free-only OpenRouter setup:

```yaml
model:
  default: openai/gpt-oss-20b:free
  provider: openrouter
  base_url: https://openrouter.ai/api/v1
```

The project `.env` also uses:

```env
OPENROUTER_ENABLED=true
OPENROUTER_MODEL=openai/gpt-oss-20b:free
HERMES_PROVIDER=openrouter
HERMES_MODEL=openai/gpt-oss-20b:free
HERMES_BASE_URL=https://openrouter.ai/api/v1
```

Do not put real keys in docs or `.env.example`. Keep `OPENROUTER_API_KEY` in local `.env` files only.

## Verification Result

- `hermes --version`: passed, Hermes Agent v0.13.0.
- `hermes doctor`: config and `.env` exist; optional messaging/search/browser dependencies are not fully configured.
- Direct OpenRouter API smoke: `openai/gpt-oss-20b:free` returned `OK`.
- Hermes one-shot smoke: passed when `OPENROUTER_API_KEY`, `HERMES_INFERENCE_PROVIDER=openrouter`, and `HERMES_INFERENCE_MODEL=openai/gpt-oss-20b:free` are loaded into the process environment.
- TraderV1 project plugin smoke: passed. Hermes used the read-only `traderv1_shadow_gap_summary` tool and returned `gap_report_required`.

Use:

```bat
scripts\run-hermes.bat -z "Reply with exactly OK."
```

`run-hermes.bat` loads `OPENROUTER_API_KEY` from `C:\Users\hacke\.hermes\.env` or `WalletScarper\.env` without printing it.

## TraderV1 Tool Boundary

Project plugin:

```text
.hermes\plugins\traderv1_operator
```

Launcher behavior:

- `scripts\run-hermes.bat` sets `HERMES_ENABLE_PROJECT_PLUGINS=1`.
- The default toolset is `traderv1_operator`.
- `hermes tools list` shows `traderv1_operator` enabled for CLI.

Available project tools:

- `traderv1_project_health` runs the read-only project health check.
- `traderv1_latest_reports` reads deterministic report files from `docs\implementation-progress\reports`.
- `traderv1_shadow_gap_summary` summarizes the latest acceptance and shadow-gap JSON reports.

These tools are read-only wrappers. They do not create ledger rows, edit reports, place orders, or change configuration.

## Install Or Repair

If Hermes is missing:

```powershell
git clone https://github.com/NousResearch/hermes-agent.git external\hermes-agent
cd external\hermes-agent
uv venv .venv --python 3.11
uv pip install -e .
```

Native Windows install is supported by Hermes upstream but marked early beta. WSL2 remains the safer path for full Hermes features.

## Setup Commands

Interactive setup:

```bat
external\hermes-agent\.venv\Scripts\hermes.exe setup
```

Model picker:

```bat
external\hermes-agent\.venv\Scripts\hermes.exe model
```

Config inspection:

```bat
external\hermes-agent\.venv\Scripts\hermes.exe config show
external\hermes-agent\.venv\Scripts\hermes.exe doctor
```

## Free Local Provider Alternative

Ollama is installed and its OpenAI-compatible endpoint responds at:

```text
http://localhost:11434/v1
```

Installed local models:

- `phi4:latest`
- `phi4-mini:latest`

Ollama is not selected because the operator requested OpenRouter free models. If OpenRouter free routing is rate-limited, Ollama remains the local fallback.

## Hermes Boundaries

Hermes is allowed to inspect reports, summarize calibration, suggest next actions, and call safe typed tools. Hermes must not trade, mutate ledgers, create authoritative risk checks, calculate canonical P&L, claim profitability, or bypass deterministic services.
