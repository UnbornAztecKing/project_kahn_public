# Project Kahn: Strategic Interaction Between Frontier AI Models

This repository contains the simulation code and tournament data for "Strategic Interaction Between Frontier AI Models: A Computational Approach to Crisis Escalation".

## Paper

**AI Arms and Influence: Frontier Models Exhibit Sophisticated Reasoning in Simulated Nuclear Crises**

The paper is available on arXiv: [link to be added]

## Repository Contents

### Game Code
- `Kahn_game_v11.py` - Open-ended scenario variant (no explicit deadline)
- `Kahn_game_v12.py` - Deadline scenario variant (explicit time pressure)
- `sim.py` - Modularized simulation with JSONL event streaming for the TUI
- `scenarios.py` - Scenario definitions and prompt generation

### SLOPR
- `slopr/` - Terminal UI viewer for replaying and live-monitoring simulations

### Actor Configuration
- `config/` - Typed Pydantic actor definitions (replaces legacy JSON files)
  - `config/models.py` - Shared `StateConfig` / `MilitaryConfig` / `LeaderConfig` models
  - `config/state_a.py` - State Alpha (US-scale nuclear force)
  - `config/state_b.py` - State Beta (Russia-scale nuclear force)
  - `config/state_c.py` - State Gamma (India-scale force; "Nuclear Gandhi" leader paradox)
  - `config/state_d.py` - State Delta (Pakistan-scale force; elevated accident rate)

### Tournament Data
The `tournament_results/` directory contains CSV logs from all 21 games in the tournament, featuring:
- **Claude Sonnet 4** (claude-sonnet-4-20250514)
- **GPT-5.2** (gpt-5.2)
- **Gemini 3 Flash** (gemini-3-flash-preview)

Each CSV contains turn-by-turn data including:
- Model actions and signals
- Territory changes
- Military attrition
- Full model reasoning/rationales

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) for dependency management
- API keys for Anthropic, OpenAI, and/or Google (Gemini) — **or** a local [Ollama](https://ollama.com) server (no API key required)

## Setup

```bash
# Install dependencies
uv sync

# Copy and populate API keys (optional if using Ollama only)
cp .env.example .env   # or create .env manually
```

`.env` format:
```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434/v1   # default; override if needed
```

## Running Simulations

### Quick start with `make`

```bash
make help               # list all targets

# Frontier model scenarios
make alliance           # Alliance credibility test, Claude vs GPT (v11, open-ended)
make first-strike       # First-strike crisis (v12, 15-turn deadline)
make standoff           # Asymmetric standoff (v12, 12-turn deadline)
make regime-survival    # Existential stakes (v12, 20-turn deadline)
make power-transition   # Rising/declining power dynamic (v11)

# Canonical tournament (9 games, frontier models, alliance scenario)
make tournament

# Ollama (local, no API key required)
make ollama-alliance
make ollama-tournament
```

### Direct invocation

```bash
# v11 — open-ended (no deadline)
uv run python Kahn_game_v11.py \
  --model_a claude-sonnet-4-20250514 \
  --model_b gpt-5.2 \
  --scenario v7_alliance \
  --aggressor A \
  --turns 30

# v12 — deadline-enforced
uv run python Kahn_game_v12.py \
  --model_a claude-sonnet-4-20250514 \
  --model_b gpt-5.2 \
  --scenario v8_first_strike_fear \
  --aggressor A \
  --turns 15
```

Available `--scenario` values:

| Key | Name | Deadline |
|-----|------|---------|
| `v6_baseline` | Territorial Dispute (Baseline) | none |
| `v7_alliance` | Alliance Leadership Test | none |
| `v7_resource` | Strategic Resource Race | 15 turns |
| `v7_strait` | Strategic Chokepoint Crisis | 20 turns |
| `v7_power_transition` | Power Transition Crisis | none |
| `v7_power_transition_a_rising` | Power Transition (State A Rising) | none |
| `v7_power_transition_b_rising` | Power Transition (State B Rising) | none |
| `v7_land_grab` | Pre-Ceasefire Land Grab | 18 turns |
| `v8_first_strike_fear` | First Strike Crisis | 15 turns |
| `v9_regime_survival` | Regime Survival Crisis | 20 turns |
| `v10_standoff_crisis` | Strategic Standoff Crisis | 12 turns |
| `v11_nuclear_kargil` | Nuclear Kargil Standoff | 20 turns |

## Simulation Module (`sim.py`)

`sim.py` is a modularized version of the game engine that streams structured events to a JSONL file as the simulation runs. This event stream powers SLOPR and enables post-hoc analysis.

### Event streaming

Every simulation action — phase transitions, LLM decisions, state changes, KPI updates, and situation reports — is emitted as a `GameEvent` and appended to a JSONL file via `EventWriter`. Each write is flushed and fsynced immediately, so the TUI can tail the file in real time.

```bash
# Run a simulation and write events to a JSONL file
uv run python sim.py \
  --model_a claude-sonnet-4-6 --model_b gpt-5.2 \
  --scenario v8_first_strike_fear --aggressor A --turns 15 \
  --events-file sim-first-strike.jsonl

# Or use make targets
make sim-first-strike                          # frontier models
make sim-ollama-first-strike-gemma-mistral     # local Ollama models
```

### Three-phase decision architecture

Each turn executes three phases per side:

1. **Reflection** — assess opponent credibility and own forecasting ability using decision history
2. **Forecast** — predict the opponent's next escalation action with confidence and miscalculation risk
3. **Decision** — choose a signal (public posture, 0–1000) and an action (actual escalation, 0–1000), with a consistency statement comparing the action to the forecast

After both sides act, the engine updates territory balance, military power, and checks for victory or game-ending conditions (nuclear exchange, territorial control at ±5.0, or scenario deadline).

### Key mechanics

- **Escalation ladder**: 0 (diplomatic) to 1000 (strategic nuclear war), with nuclear multipliers scaling territory impact up to 15×
- **Gating**: Strategic threats (850/950) are scored as 350 until any 450+ tactical use occurs, preventing costless bluffing
- **Military attrition**: Conventional and nuclear effectiveness degrade through combat based on relative capabilities
- **Memory systems**: Rolling 5-turn decision memory, persistent peak-betrayal memory (Kahneman effect), and escalation pattern tracking

### CLI options

| Flag | Description | Default |
|------|-------------|---------|
| `--model_a` | Model for State A (required) | — |
| `--model_b` | Model for State B (required) | — |
| `--scenario` | Scenario key (see table above) | `v7_alliance` |
| `--aggressor` | Which side is the aggressor (`A` or `B`) | `A` |
| `--turns` | Maximum number of turns | `50` |
| `--start_balance` | Initial territory balance (−5.0 to +5.0) | `0.0` |
| `--events-file` | JSONL output path (`-` for stdout, omit to skip) | `None` |
| `--state_a` | Actor key for Side A (see Actor registry below) | `A` |
| `--state_b` | Actor key for Side B (see Actor registry below) | `B` |

## Actors

The simulation supports arbitrary actor pairings. Each actor is a `StateConfig` Pydantic instance that encodes leader biography, nuclear posture, military capabilities, and an escalation-risk modifier.

### Built-in actors

| Key | Display name | Inspiration | Notes |
|-----|-------------|-------------|-------|
| `A` | State Alpha | US-scale | Large triad, high conventional strength, moderate risk tolerance |
| `B` | State Beta | Russia-scale | Large triad, strong conventional forces, high-risk doctrine |
| `C` | State Gamma | India-scale | Growing SSBN fleet, 172 warheads, "Nuclear Gandhi" paradox leader |
| `D` | State Delta | Pakistan-scale | First-use at conventional defeat, pre-delegated field authority, `accident_rate_modifier=2.5` |

### Selecting actors

Pass `--state_a` and `--state_b` to `sim.py` with any registered key:

```bash
uv run python sim.py \
  --model_a claude-sonnet-4-6 --model_b gpt-5.2 \
  --scenario v11_nuclear_kargil \
  --state_a C --state_b D \
  --aggressor B --turns 20 \
  --events-file sim-kargil.jsonl

# Or use the Makefile target
make sim-kargil
```

### Adding a new actor

1. Create `config/state_e.py` following the pattern in `config/state_c.py`.
2. Register it in `config/__init__.py`:
   ```python
   from config.state_e import STATE_E
   REGISTRY["E"] = STATE_E
   ```
3. Pass `--state_a E` or `--state_b E` to `sim.py`.

The `accident_rate_modifier` field in `MilitaryConfig` multiplies the base accident probability for that actor's turns. Default is `1.0`; State D uses `2.5` to model improvised civilian-vehicle transport and Islamist insider threats in its Strategic Plans Division.

## SLOPR

SLOPR is a terminal-based viewer for replaying and live-monitoring Project Kahn simulation event streams. It is built with [Textual](https://textual.textualize.io/) and provides a keyboard-driven, borderless interface for navigating game events turn by turn. See [`slopr/README.md`](slopr/README.md) for full documentation.

### Quick start

```bash
# View a completed simulation
uv run python -m slopr sim-first-strike.jsonl

# Jump directly to turn 5
uv run python -m slopr sim-first-strike.jsonl --turn 5

# Or use make targets
make tui FILE=path/to/events.jsonl
make view-sim-first-strike
```

### Live monitoring

SLOPR polls its source file every 100 ms. Start a simulation in one terminal and open SLOPR in another — events appear as they stream:

```bash
# Terminal 1
make sim-first-strike

# Terminal 2
make view-sim-first-strike
```

### Capabilities

| Feature | Description |
|---------|-------------|
| Turn sidebar | Navigable index of all turns; `*` = LLM decisions, `~` = edited events |
| Event cards | Type-colored, per-side rendering (blue = State A, coral = State B) |
| Split view | Side-by-side A/B layout when the pane is wide enough (configurable) |
| KPI bar | Live territory balance, military power, signal/action values, trend arrows |
| KPI history panel | Click the KPI bar to open a full turn-by-turn table |
| Search | `/` quick search · `Ctrl+F` full-screen modal with paginated results |
| Phase navigation | Click a phase in the sidebar to jump directly to it |
| Live tail | Automatically picks up new events without restart |

### Key bindings

| Key | Action |
|-----|--------|
| `q` | Quit |
| `/` | Toggle inline search |
| `Ctrl+F` | Open search modal |
| `Ctrl+B` | Toggle branch manager panel |
| `Tab` / `Shift+Tab` | Move focus between sidebar and content pane |

### Branch manager

Double-clicking any event card opens an edit modal. You must provide a branch label to commit; an annotation is optional. On commit, a new branch JSONL is created containing all events up to the fork point, and the branch appears in the panel opened by `Ctrl+B`. From the branch manager you can spawn a background simulation to continue from the fork, or delete branches. The branch manifest is stored as `{filename}.branches` alongside the source JSONL (e.g. `sim-kargil.jsonl.branches`), and branch event logs are named `{root_stem}.{label-slug}.jsonl`. The manifest auto-creates on first branch commit.

## Using Ollama (local models, no API key)

Ollama exposes an OpenAI-compatible API on `http://localhost:11434/v1`. The game code uses the `ollama:` model prefix to route calls there automatically.

### 1. Start the Ollama server

```bash
ollama serve
```

To allow connections from other machines:
```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

### 2. Pull models

The Makefile defines the four models used in simulation targets and provides
individual pull commands for each:

```bash
make pull-llama    # huihui_ai/llama3.2-abliterate:3b
make pull-mistral  # huihui_ai/mistral-small-abliterated:24b
make pull-qwen     # huihui_ai/qwen3-abliterated:16b
make pull-gemma    # huihui_ai/gemma3-abliterated:4b

make pull-ollama   # pull all four sequentially
```

The pull targets are derived directly from the `OL_*` variables at the top of
the Makefile, so updating a model there automatically updates the pull command —
no second edit required.

To pull a model not in the Makefile directly:

```bash
ollama pull <model-name>
```

### 3. Run a simulation

Prefix the model name with `ollama:`:

```bash
uv run python Kahn_game_v11.py \
  --model_a ollama:llama3.2 \
  --model_b ollama:mistral \
  --scenario v7_alliance \
  --aggressor A \
  --turns 30
```

Mixed frontier + local:

```bash
uv run python Kahn_game_v11.py \
  --model_a claude-sonnet-4-20250514 \
  --model_b ollama:llama3.2 \
  --scenario v7_alliance \
  --aggressor A \
  --turns 30
```

Full Ollama round-robin tournament:

```bash
make ollama-tournament
```

### 4. Override the Ollama URL

If Ollama is running on a different host or port, set `OLLAMA_BASE_URL` in `.env`:

```
OLLAMA_BASE_URL=http://192.168.1.50:11434/v1
```

## Citation

If you use this code or data, please cite:

```bibtex
@article{payne2026arms,
  title={AI Arms and Influence: Frontier Models Exhibit Sophisticated Reasoning in Simulated Nuclear Crises},
  author={Payne, Kenneth},
  journal={arXiv preprint},
  year={2026}
}
```

## License

This work is licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) (Creative Commons Attribution-NonCommercial 4.0 International).

You are free to share and adapt this material for non-commercial purposes, provided you give appropriate credit. For commercial licensing inquiries, contact Kenneth Payne.

See [LICENSE](LICENSE) for details.

## Contact

Kenneth Payne - [institution/email to be added]
