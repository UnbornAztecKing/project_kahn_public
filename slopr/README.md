# SLOPR

A terminal UI for replaying and live-monitoring [Project Kahn](../README.md) wargame simulations. Built with [Textual](https://textual.textualize.io/).

```
uv run python -m slopr path/to/events.jsonl
```

---

## Contents

- [Installation](#installation)
- [Launching](#launching)
- [Interface overview](#interface-overview)
- [Turn sidebar](#turn-sidebar)
- [Content pane](#content-pane)
- [Split view](#split-view)
- [KPI bar](#kpi-bar)
- [Search](#search)
- [Live tailing](#live-tailing)
- [CLI reference](#cli-reference)
- [Key bindings](#key-bindings)
- [Event types](#event-types)
- [Architecture](#architecture)

---

## Installation

SLOPR is part of the `project-kahn-public` package and is installed with the rest of the project dependencies:

```bash
uv sync
```

No additional install step is required. The `slopr` entry point is registered automatically:

```bash
slopr path/to/events.jsonl          # if uv-managed scripts are on PATH
uv run python -m slopr events.jsonl  # always works
```

---

## Launching

```bash
# Open a completed simulation
uv run python -m slopr sim-first-strike.jsonl

# Start at a specific turn
uv run python -m slopr sim-first-strike.jsonl --turn 5

# Via make targets (defined in the root Makefile)
make tui FILE=sim-first-strike.jsonl
make view-sim-first-strike
make view-sim-ollama-first-strike-gemma-mistral
make tui-demo                   # regenerates demo fixture and opens it
```

---

## Interface overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Project Kahn — Wargame Viewer                            [Header]│
├──────────────┬──────────────────────────────────────────────────┤
│              │  ╔═ Project Kahn ══════════════════════════════╗  │
│  Turn 0  [1] │  ║  ██████╗ ██████╗  ...  (ASCII banner)      ║  │
│  Turn 1  [8] │  ╚════════════════════════════════════════════╝  │
│  Turn 2  [8] │                                                   │
│  Turn 3  [8] │  ╔═ Parameters ═══════════════════════════════╗  │
│   ...        │  ║  Scenario:    v8_first_strike_fear          ║  │
│              │  ║  Max turns:   15                            ║  │
│              │  ╚════════════════════════════════════════════╝  │
│              │                                                   │
│  [Sidebar]   │  ╔═ Forecast ══════════════════════════════════╗ │
│              │  ║  State A  │  State B                         ║ │
│              │  ║  LLM      │  LLM                             ║ │
│              │  ║  ...      │  ...    [Content pane]           ║ │
│              │  ╚════════════════════════════════════════════╝  │
├──────────────┴──────────────────────────────────────────────────┤
│ Terr: +0.1234 ↑  A Conv: 95.0%  B Conv: 89.0%  ...  [KPI bar]  │
├─────────────────────────────────────────────────────────────────┤
│ q Quit  / Search  ^F Find                              [Footer]  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Turn sidebar

The left panel lists every turn in the game. Each row shows the turn number and the count of events in brackets.

Markers appended to the turn label:

| Marker | Meaning |
|--------|---------|
| `*` | Turn contains at least one LLM decision |
| `~` | Turn contains at least one human-edited event |

**Navigation**: click a turn or use arrow keys + Enter to load it in the content pane. Turns can be expanded in the tree to reveal individual phase groups; clicking a phase jumps directly to it in the content pane.

---

## Content pane

The main area shows all events for the selected turn, grouped into collapsible sections by phase.

### Phase groups

Each bordered box corresponds to one phase. Group colors match the phase:

| Phase | Color |
|-------|-------|
| Project Kahn (turn 0 banner) | Gold |
| Parameters (game start) | Teal |
| Scenario (turn 0 briefing) | Green |
| State Profiles (turn 0) | Indigo |
| Initial State (carried forward) | Dark slate |
| Reflection | Cyan |
| Forecast | Blue |
| Signal | Purple |
| Action | Amber |
| End State | Steel grey |
| Game Over | Red |

Groups are collapsed/expanded by clicking their title bar.

### Turn 0

Turn 0 always opens with:
1. **ASCII banner** — centered Project Kahn art that reflows as the terminal is resized.
2. **Parameters** — game configuration (scenario, models, max turns, start balance).
3. **Scenario briefing** — full narrative context, stakes, pressure, and consequences.
4. **State A and State B profiles** — leader biography, nuclear doctrine, military capabilities, and intelligence assessments.

### Event cards

Each event is rendered as a card with:

- **Source badge** — `LLM` for model outputs, `EDIT` for human annotations; blank for simulation events.
- **Title** — colored by event type (phase = accent, state = primary, KPI = secondary, report = warning, game = success).
- **Metadata** — sequence number, event type, phase, timestamp, parent ID, and content hash.
- **Body** — formatted prose text (newlines doubled by default for readability).
- **Structured fields** — labeled key-value rows with per-side coloring (blue = State A, coral = State B).

---

## Split view

When the content pane is at least 100 columns wide (configurable), phases that contain both a State A and a State B event switch to a side-by-side grid layout. Fields from corresponding A and B events are aligned row-by-row so values at the same escalation ladder position sit next to each other.

A vertical divider separates the two sides. A header row labels each column **State A** / **State B**.

The layout switches automatically when the terminal is resized across the threshold — no reload required.

To disable split view or change the threshold:

```bash
uv run python -m slopr events.jsonl --split-width 0        # disable
uv run python -m slopr events.jsonl --split-width 140      # wider threshold
```

---

## KPI bar

The bottom-docked bar shows live indicators for the current turn:

| Indicator | Description |
|-----------|-------------|
| Territory | Balance (−5.0 to +5.0) with trend arrow |
| A Conv / B Conv | Conventional military power as a percentage |
| A Nuc / B Nuc | Nuclear military power as a percentage |
| A Action / B Action | Last escalation rung chosen |
| Gap A / Gap B | Signal-action gap (declared vs actual) |

Values are colored by threshold:

- **Green** — normal range
- **Yellow** — warning threshold crossed
- **Red** — critical threshold crossed (territory near ±5.0, power near 0)

**Clicking the KPI bar** opens a full-screen KPI history panel showing a scrollable table of all indicators across every turn. Click a row or press Enter to jump to that turn.

---

## Search

**Inline search** (`/`):

Opens a one-line search bar at the bottom of the screen. Type to search event titles and bodies across all turns; the first matching turn loads automatically. Press `/` or Escape to close.

**Full-screen modal** (`Ctrl+F`):

Opens a paginated search modal with a list of matching events (turn, sequence number, title, excerpt). Navigate results with arrow keys, press Enter to jump to the selected turn.

---

## Live tailing

SLOPR polls the source JSONL file every 100 ms using a background `Tailer`. When new events are detected:

1. The turn sidebar refreshes its index.
2. If the current turn has new events, the content pane reloads it in place.
3. If no turn was loaded yet, the first available turn loads automatically.

This means you can open SLOPR before or during a simulation and watch events appear in real time without any manual refresh.

```bash
# Terminal 1 — run the simulation
make sim-first-strike

# Terminal 2 — watch live
make view-sim-first-strike
```

---

## CLI reference

```
uv run python -m slopr [OPTIONS] JSONL_FILE
```

| Option | Default | Description |
|--------|---------|-------------|
| `--turn N` | first turn | Jump to turn N on startup |
| `--split-width N` | `100` | Min content pane width (columns) for A/B split layout; `0` disables |
| `--double-newlines` / `--no-double-newlines` | enabled | Double newlines in prose text for visual breathing room |
| `--wrap-indent N` | `0` | Indent continuation lines in prose text by N spaces |
| `--help` | — | Show help and exit |

---

## Key bindings

| Key | Action |
|-----|--------|
| `q` | Quit |
| `/` | Toggle inline search bar |
| `Ctrl+F` | Open full-screen search modal |
| `Tab` | Move focus to the next pane |
| `Shift+Tab` | Move focus to the previous pane |
| Arrow keys | Navigate within the focused pane |
| Enter | Select the focused item (turn, phase, search result) |
| Escape | Close modal / dismiss search |

---

## Event types

| Type | Emitted by | Description |
|------|-----------|-------------|
| `GAME_START` | Simulation | Game configuration — models, scenario, parameters |
| `PHASE_TRANSITION` | Simulation | Delimiter between turn phases (reflection / forecast / signal / action) |
| `LLM_DECISION` | LLM | Model output for one phase: reflections, forecasts, signals, or actions |
| `STATE_CHANGE` | Simulation | Territory and military power update after both sides act |
| `KPI_UPDATE` | Simulation | Numeric summary of all key performance indicators |
| `SITUATION_REPORT` | Simulation | Narrative assessment of the game state |
| `GAME_END` | Simulation | Final outcome, end reason, and total turns |
| `ANNOTATION` | Human | Out-of-band note attached to any event (shown with `EDIT` badge) |

---

## Architecture

```
slopr/
├── __main__.py         CLI entry point (click)
├── app.py              Textual App — layout, routing, live-tail wiring
├── models.py           Pydantic GameEvent model and enums
├── store.py            EventStore ABC + JSONLEventStore (read-only)
├── event_writer.py     EventWriter — append-only JSONL writer (used by sim.py)
├── fixtures.py         Demo fixture generator (python -m slopr.fixtures)
├── tail.py             Tailer — background file polling for live events
├── wargame.tcss        Textual CSS stylesheet
└── widgets/
    ├── banner.py        KahnBanner — centered ASCII art, reflows on resize
    ├── content_pane.py  ContentPane — main scroll area, event grouping, split view
    ├── kpi_bar.py       KPIBar — bottom-docked live indicators
    ├── kpi_panel.py     KPIPanel — full-screen KPI history modal
    ├── search_bar.py    SearchBar — inline one-line search
    ├── search_modal.py  SearchModal — full-screen paginated search
    └── turn_sidebar.py  TurnSidebar / TurnIndex — turn tree with phase navigation
```

### Data flow

```
sim.py ──JSONL──► EventWriter ──append──► events.jsonl
                                               │
                               Tailer ◄─poll───┘
                                  │
                            EventStore (read)
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼              ▼
               TurnSidebar   ContentPane      KPIBar
```

### Key design decisions

- **Streaming architecture**: Events are written one per line, flushed and fsynced immediately. The `Tailer` reads only new bytes on each poll, making live display efficient even for long games.
- **Immutable store**: `JSONLEventStore` is read-only. All mutations happen in `sim.py` via `EventWriter`. This separation allows the TUI to be safely opened while a simulation runs.
- **Responsive split view**: `ContentPane` tracks its last rendered mode (`_last_split`) and only rerenders on `Resize` events that cross the split threshold, avoiding unnecessary DOM rebuilds.
- **Aligned field grid**: In split view, `_event_rows()` extracts `(markup, css_class)` pairs for each rendered line of an event. `_build_aligned_pair()` zips A and B lists so fields at the same semantic position share a row in a `Horizontal` container, giving pixel-accurate alignment without a CSS grid.
- **Dynamic banner centering**: `KahnBanner` recomputes left padding on every `Resize` event using `content_size.width`, keeping the ASCII art horizontally centered as the terminal is resized.
