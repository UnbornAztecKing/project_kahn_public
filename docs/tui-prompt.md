# Wargame TUI Implementation Prompt

Apply the intended changes to sim.py as the entry point for the new TUI simulation application.
Create an idiomatic structure for a well-factored application, library, and utilities.

## Context

I have a turn-based wargame simulation that uses LLMs to evaluate decisions driving game state progression. Currently it logs excerpts of LLM output to flat text. I need two things:

1. **An event-stream output layer**: The simulation must write each event to a JSONL file as it occurs, enabling headless execution, file tailing, and S3 streaming.
2. **A Python TUI viewer**: A Textual-based application that reads the event stream and presents game states, LLM decisions, simulation-caused state changes, and KPIs in a navigable, attributed interface.

The TUI is a *viewer first*. It does not run the simulation — it reads the event stream. The simulation runs headless and writes events. The TUI tails the output directory or loads a completed game.

## Technology Stack

- **TUI Framework**: Textual (by Textualize) — latest stable release
- **Python**: 3.11+
- **Testing**: pytest + Textual's built-in `pilot` testing framework
- **Data Model**: Pydantic v2 for all structured data
- **Event Storage**: JSONL files (one event per line) as the canonical format; SQLite as an optional indexed read cache for the TUI
- **CLI**: `click` or `typer` for the entry point

## Reference Implementations

When implementing widgets and layout patterns, consult these production Textual applications for idiomatic patterns. Read their source on GitHub when unsure about a design choice:

| App | Repo | Study for |
|-----|------|-----------|
| **Toolong** | `github.com/Textualize/toolong` | Log tailing, inline search bar (`/` then `n`/`N`), virtualized line rendering, LRU line cache |
| **Posting** | `github.com/darrenburns/posting` | Multi-pane layout, `ContentSwitcher` for view↔edit, inline row editing, compact/standard spacing, custom keymaps |
| **Harlequin** | `github.com/tconbeer/harlequin` | Sidebar tree ↔ content pane selection protocol, `OptionList` for fast text-only lists, adapter plugin pattern |
| **Dolphie** | `github.com/charles-001/dolphie` | KPI dashboard with sparklines, threshold-based coloring, panel toggling, record/replay to SQLite |
| **Toad** | `github.com/batrachianai/toad` | Streaming Markdown (re-render last block only), conversation-as-document navigation, `@` fuzzy file picker |
| **Textual docs** | `textual.textualize.io/blog/2024/09/15/anatomy-of-a-textual-user-interface/` | Canonical `compose()` + CSS + `@work()` + message pattern for LLM-backed apps |
| **Textual widgets** | `textual.textualize.io/widget_gallery/` | Full widget reference: `OptionList`, `Tree`, `Collapsible`, `ContentSwitcher`, `DataTable`, `Log` |

---

## Part 1: Event Stream Architecture

### Event Model

Every simulation event is a self-contained JSON object written as one line to a JSONL file. Events are the *source of truth* — the TUI, SQLite cache, and any downstream consumer all derive from this stream.

```python
# models.py
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import hashlib, uuid

class EventType(str, Enum):
    """Discriminator for the event stream."""
    GAME_START = "game_start"           # initial scenario setup
    SITUATION_REPORT = "situation_report"  # narrative state description
    LLM_DECISION = "llm_decision"       # a single LLM evaluation
    STATE_CHANGE = "state_change"       # simulation engine mutated game state
    KPI_UPDATE = "kpi_update"           # KPI snapshot after a phase
    PHASE_TRANSITION = "phase_transition"  # turn/phase boundary marker
    ANNOTATION = "annotation"           # human or system note

class EventSource(str, Enum):
    """Who produced this event — critical for attribution in the TUI."""
    SIMULATION = "simulation"   # the game engine / physics
    LLM = "llm"                 # an LLM evaluation
    HUMAN = "human"             # manual edit or annotation
    SYSTEM = "system"           # phase transitions, bookkeeping

class GameEvent(BaseModel):
    """Single event in the simulation stream. One line in JSONL output."""
    model_config = {"frozen": True}

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None       # links to prior event in causal chain
    sequence_number: int                   # monotonic within a game run
    turn_number: int
    phase: str                             # e.g. "planning", "execution", "assessment"
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    event_type: EventType
    source: EventSource                    # WHO produced this event
    source_detail: str = ""                # e.g. model name, engine subsystem

    title: str                             # short summary for sidebar display
    body: str = ""                         # full content (sitrep text, LLM output, delta description)
    structured_data: dict[str, Any] = {}   # parsed decisions, KPI values, state deltas

    content_hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            h = hashlib.sha256(f"{self.body}:{self.sequence_number}".encode()).hexdigest()[:16]
            object.__setattr__(self, "content_hash", h)
```

### JSONL Writer (simulation side)

```python
# event_writer.py
import json, os, fcntl
from pathlib import Path
from datetime import datetime

class EventWriter:
    """Append-only JSONL writer. One file per game run.
    
    Usage in simulation:
        writer = EventWriter(output_dir / f"game_{run_id}.jsonl")
        writer.write(event)  # fsync after each write for tail safety
    """
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a", encoding="utf-8")
        self._seq = 0

    def write(self, event: GameEvent) -> None:
        line = event.model_dump_json() + "\n"
        self._fh.write(line)
        self._fh.flush()
        os.fsync(self._fh.fileno())  # ensures `tail -f` and inotify see the write
        self._seq += 1

    def close(self) -> None:
        self._fh.close()
```

The simulation writes events immediately as they occur. This enables:
- **Headless execution**: `python -m wargame_sim --output-dir ./runs/run_001/`
- **Live tailing**: `tail -f ./runs/run_001/game.jsonl | jq .title`
- **S3 streaming**: pipe through `aws s3 cp - s3://bucket/runs/run_001/game.jsonl` or use a watcher that uploads completed files
- **TUI viewing**: `python -m vorpal ./runs/run_001/game.jsonl` (loads completed) or `python -m vorpal --tail ./runs/run_001/game.jsonl` (live follow)

### JSONL Reader / Store Interface

```python
# store.py
from abc import ABC, abstractmethod
from typing import Optional

class EventStore(ABC):
    """Read interface over the event stream. TUI depends only on this."""

    @abstractmethod
    def get_event(self, event_id: str) -> GameEvent: ...

    @abstractmethod
    def get_events(
        self,
        turn: Optional[int] = None,
        event_type: Optional[EventType] = None,
        source: Optional[EventSource] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GameEvent]:
        """Filtered, paginated event retrieval."""
        ...

    @abstractmethod
    def get_turn_numbers(self) -> list[int]:
        """Distinct turn numbers in order."""
        ...

    @abstractmethod
    def get_turn_summary(self, turn: int) -> dict:
        """Aggregate info for sidebar display: phase, event count, has_llm, has_edit."""
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 50) -> list[GameEvent]:
        """Full-text search across event titles and bodies."""
        ...

    @abstractmethod
    def get_latest_sequence(self) -> int:
        """Highest sequence number seen — used for tail polling."""
        ...


class JSONLEventStore(EventStore):
    """Reads directly from JSONL file. Builds an in-memory index on load.
    For games < 10K events this is fast enough. For larger games, 
    SQLiteCacheStore wraps this with FTS5 indexing."""
    ...

class SQLiteCacheStore(EventStore):
    """SQLite-backed read cache with FTS5. Built from JSONL on first open,
    then incrementally updated when tailing."""
    ...
```

---

## Part 2: TUI Application

### UI Principles (derived from reference apps)

1. **Attribution is paramount.** Every piece of content in the main pane must show WHO produced it — simulation engine, LLM (which model), or human edit. Use distinct visual markers:
   - `EventSource.SIMULATION` → `$primary` left border + "⚙ SIM" badge
   - `EventSource.LLM` → `$accent` left border + "🤖 model_name" badge
   - `EventSource.HUMAN` → `$warning` left border + "✏ EDIT" badge
   - `EventSource.SYSTEM` → `$text-muted` left border + no badge (phase transitions are structural, not content)

2. **Semantic CSS variables only.** Never hardcode colors. Use `$primary`, `$secondary`, `$accent`, `$warning`, `$error`, `$success`, `$background`, `$surface`, `$panel`, `$text`, `$text-muted`, `$boost`. This gives you dark/light theme support for free.

3. **OptionList for the sidebar, not ListView.** `OptionList` is lighter for text-only items, supports keyboard type-to-search natively, and renders faster with hundreds of items. `ListView` is for heterogeneous child widgets.

4. **ContentSwitcher for view↔edit.** Inside any widget that will later support editing (Phase 2), use `ContentSwitcher(initial="view")` with a `Static` child and a `TextArea` child. This avoids remount flicker and focus loss. See Posting's inline edit pattern.

5. **Two-tier search.** `/` opens a bottom-docked `SearchBar` (not a modal) for incremental filter + `n`/`N` navigation through matches — this is the Toolong pattern. `Ctrl+F` opens a full modal `Screen` for complex queries with paginated results. The search bar state persists across open/close.

6. **Messages up, attributes down.** Widgets communicate to parents via `Message` subclasses. Parents update children by setting attributes or calling methods. Define a `EventSelected(Message)` with `event_id: str` that both the sidebar `OptionList` and future `Tree` widget post — `ContentPane` handles this message and never inspects which widget posted it.

7. **KPI coloring on the widget background**, not just text. Use `$success-muted`/`$warning-muted`/`$error-muted` for the indicator background and the corresponding `$text-*` variable for foreground. Add trend arrows: `▲` green / `▼` red / `─` gray. Put KPIs in a `HorizontalScroll` container so overflow scrolls rather than wrapping.

8. **Responsive at narrow widths.** Use Textual CSS `@media (width < 80)` to hide the sidebar and show a keybind (`ctrl+t`) that pushes a `TurnSelectorScreen` overlay. This is the Posting pattern.

9. **Register commands in the CommandPalette** (`ctrl+p`). Implement `get_system_commands()` on the App to register: "Go to turn N", "Search events", "Toggle KPI bar", "Toggle sidebar", "Switch theme". This gives discoverability without overloading keybindings.

10. **Support `--compact` mode.** Toggle via CLI flag or runtime `app.add_class("compact")`. Compact: 0 padding, no sparklines, collapsible headers only. Standard (default): padded, sparklines visible.

### TUI Layout

```
┌────────────────────────────────────────────────────────────────────┐
│ [Header] Wargame Viewer — Turn 14 / Assessment         [?] [⏵▐▐] │
├─────────────────────┬──────────────────────────────────────────────┤
│ Event Index         │  Event Stream                                │
│ (sidebar)           │                                              │
│                     │  ⚙ SIM  State Change: Blue advances to 4423  │
│  Turn 1  (3 events) │  ├─ body text with delta details...          │
│  Turn 2  (5 events) │                                              │
│  Turn 3  (4 events) │  🤖 claude-sonnet  LLM Decision              │
│  ...                │  ├─ "Based on force disposition..."           │
│ ▸Turn 14 (6 events)◀│  ├─ Decision: advance → OBJ_ALPHA (82%)      │
│                     │  ├─ Reasoning: Favorable force ratio...       │
│                     │  └─ 1,847 tok · 3.2s                         │
│                     │                                              │
│                     │  ⚙ SIM  State Change: Attrition applied       │
│                     │  ├─ Blue casualties: 12 → 15                  │
│                     │  ├─ Red casualties: 8 → 14                    │
│                     │                                              │
│                     │  📊 KPI Update                                │
│                     │  ├─ Force Ratio: 1.3:1 (▲+0.1)               │
│                     │  └─ Attrition: 12% (▼-2%)                    │
│                     │                                              │
├─────────────────────┴──────────────────────────────────────────────┤
│ KPI: Force Ratio 1.3:1 ▲ │ Attrition 12% ▼ │ Supply 78% ▼ │ ...  │
├────────────────────────────────────────────────────────────────────┤
│ [Footer] /: search  q: quit  ↑↓: nav  tab: focus  c: collapse     │
└────────────────────────────────────────────────────────────────────┘
```

The main content pane is a **vertical scroll of event cards for the selected turn**, not a single text block. Each card is visually attributed to its source. This makes it immediately clear what the simulation did vs what the LLM recommended vs what a human overrode.

### Widget Hierarchy

```
WargameApp(App)
├── Header (built-in)
├── MainContainer (Horizontal)
│   ├── TurnSidebar (Container, width: 1fr, max-width: 30)
│   │   └── TurnIndex (OptionList)
│   │       └── one option per turn: "Turn N (M events)" with phase/edit glyphs
│   └── ContentPane (VerticalScroll, width: 3fr)
│       └── EventCard (Widget) × N per selected turn
│           ├── SourceBadge (Static: icon + source label + source_detail)
│           ├── EventTitle (Static: title text)
│           └── EventBody (ContentSwitcher)
│               ├── BodyView (Static: body text, id="view")
│               └── BodyEdit (TextArea, id="edit")  # hidden until Phase 2
├── KPIBar (HorizontalScroll, dock: bottom, height: 3)
│   └── KPIIndicator (Widget) × N
│       ├── name + value + trend arrow
│       └── sparkline (last 20 turns, hidden in compact mode)
├── SearchBar (Input, dock: bottom, display: none until `/`)
└── Footer (built-in)
```

### Key Bindings

| Key | Action |
|-----|--------|
| `j`/`k` or `↑`/`↓` | Navigate turn index |
| `Enter` | Select turn, populate event stream |
| `/` | Toggle bottom search bar (incremental filter) |
| `n` / `N` | Next/previous search match |
| `Ctrl+F` | Full search modal with paginated results |
| `Ctrl+P` | Command palette |
| `Escape` | Close search bar or modal |
| `q` | Quit |
| `Tab` / `Shift+Tab` | Cycle focus: sidebar → content → KPI |
| `c` | Collapse/expand all event card bodies |
| `1`-`9` | Jump to Nth event card in current turn |
| `Ctrl+T` | Turn selector overlay (when sidebar hidden on narrow terminal) |

### EventCard Rendering by Type

Each `EventCard` renders differently based on `event_type` and `source`:

| EventType | Source | Rendering |
|-----------|--------|-----------|
| `SITUATION_REPORT` | SIMULATION | Full narrative text, `$primary` left border |
| `LLM_DECISION` | LLM | Model badge + raw output in `Collapsible`, parsed decision table (action/target/confidence) always visible above fold, reasoning summary, token count + latency in footer |
| `STATE_CHANGE` | SIMULATION | Delta description (what changed and by how much), compact key→value diff format |
| `KPI_UPDATE` | SIMULATION | Mini-table of KPI name/value/trend, threshold coloring per row |
| `PHASE_TRANSITION` | SYSTEM | Thin horizontal rule with "─── Turn N · Phase ───" centered, `$text-muted` |
| `ANNOTATION` | HUMAN | Edit note with `$warning` highlight, full width |

---

## Implementation Order & Checkpoints

### Step 1: Project scaffolding + models

```
vorpal/
├── __init__.py
├── models.py           # GameEvent, EventType, EventSource, KPI pydantic models
├── event_writer.py     # EventWriter: append-only JSONL writer (simulation side)
├── store.py            # EventStore ABC + JSONLEventStore + SQLiteCacheStore
├── app.py              # WargameApp
├── widgets/
│   ├── __init__.py
│   ├── turn_sidebar.py # TurnSidebar + TurnIndex (OptionList)
│   ├── content_pane.py # ContentPane + EventCard
│   ├── kpi_bar.py      # KPIBar + KPIIndicator
│   ├── search_bar.py   # Bottom-docked incremental search
│   └── search_modal.py # Full search Screen
├── wargame.tcss        # All styling — semantic variables only
└── fixtures.py         # Test data generator
tests/
├── __init__.py
├── test_models.py
├── test_writer.py
├── test_store.py
├── test_app.py
└── conftest.py
pyproject.toml          # entry points: vorpal, wargame-sim (future)
README.md
```

**Checkpoint 1**: `pytest tests/test_models.py tests/test_writer.py` passes.
- Models serialize to/from JSON correctly
- Content hash is deterministic
- Frozen model prevents mutation
- `EventWriter` creates JSONL file, each line is valid JSON, `fsync` is called
- Written events can be read back line-by-line and deserialized

### Step 2: Event stores

Implement `JSONLEventStore` (reads JSONL into memory index) and `SQLiteCacheStore` (FTS5 on title+body).

**Checkpoint 2**: `pytest tests/test_store.py` passes.
- JSONL round-trip: write N events → load store → retrieve by ID, turn, type, source
- `get_turn_numbers()` returns sorted distinct turns
- `get_turn_summary()` returns correct event counts and flags
- `search()` returns FTS matches ranked by relevance
- `get_latest_sequence()` tracks highest seq correctly
- SQLite cache matches JSONL store results exactly
- Edge cases: empty file, single event, 500+ events

### Step 3: Test data generator

`fixtures.py` with `generate_sample_game(n_turns: int = 20) -> list[GameEvent]` that produces a realistic event stream:
- Each turn has: 1 `PHASE_TRANSITION`, 1 `SITUATION_REPORT`, 2-3 `LLM_DECISION`s from different models, 1-2 `STATE_CHANGE`s, 1 `KPI_UPDATE`
- KPIs trend realistically across turns
- At least one `ANNOTATION` event (human edit)
- Source attribution is correct on every event
- Also writes the events to a JSONL file for manual inspection

**Checkpoint 3**: Generated data passes Pydantic validation, both stores ingest it, `get_turn_summary` matches expected event counts.

### Step 4: Core TUI — sidebar + content pane with attributed event cards

Implement `WargameApp`, `TurnSidebar` (with `OptionList`), `ContentPane` (with `EventCard`s).

The critical behavior: selecting a turn in the sidebar populates the content pane with a vertical scroll of `EventCard` widgets, each visually attributed to its source via a colored left border and source badge.

Post a `TurnSelected(Message)` from sidebar. `ContentPane` handles it, queries `store.get_events(turn=N)`, clears and rebuilds `EventCard` children.

**Checkpoint 4**: `pytest tests/test_app.py` with Textual `pilot`:
- App mounts without error
- Sidebar shows turns with event counts
- Selecting turn populates event cards
- Event cards show correct source badges and left-border colors
- `LLM_DECISION` cards show model name, confidence, latency
- `STATE_CHANGE` cards show delta description
- `PHASE_TRANSITION` renders as thin separator
- Arrow keys navigate sidebar, content pane scrolls

### Step 5: KPI bar

Implement `KPIBar` with `HorizontalScroll`, `KPIIndicator` widgets with threshold-based background coloring and trend arrows.

**Checkpoint 5**: KPIs render, threshold colors work, trend arrows correct, KPI bar updates on turn selection, sparklines show trailing window.

### Step 6: Search (both tiers)

Bottom-docked `SearchBar` on `/` (incremental filter of sidebar + `n`/`N` navigation). Full `SearchModal` on `Ctrl+F` with paginated results.

**Checkpoint 6**: `/` opens search bar, typing filters sidebar, `n`/`N` cycles, `Escape` closes. `Ctrl+F` opens modal, results clickable, navigates to turn.

### Step 7: Tail mode

Implement `--tail` flag: the TUI watches the JSONL file for new lines (via polling or `watchfiles`), appends new events to the store, and updates the sidebar/content if the user is viewing the latest turn.

**Checkpoint 7**: Start TUI with `--tail`, append events to JSONL from a separate process, TUI picks them up within 1 second, sidebar updates, KPI bar updates.

### Step 8: Integration test + demo mode

Full integration: generate fixture data → write JSONL → launch TUI → navigate → search → verify KPIs → quit.

```bash
# Demo with generated data
python -m vorpal --demo

# View a completed game
python -m vorpal ./runs/run_001/game.jsonl

# Tail a live game
python -m vorpal --tail ./runs/run_001/game.jsonl
```

**Checkpoint 8**: All tests pass. Manual smoke test confirms: events are visually attributed, LLM decisions show model/confidence/latency, state changes show deltas, KPIs color correctly, search works both tiers, tail mode updates live.

---

## Phase 2 & 3 Design Considerations (design now, implement later)

### Phase 2: Edit & Gate
- `EventCard` already has `ContentSwitcher` with view/edit children
- Editing creates a new `GameEvent` with `source=HUMAN`, `event_type=ANNOTATION`, `parent_id` pointing to the edited event
- The simulation runner polls `get_latest_sequence()` and blocks until it sees a human-gated event (or proceeds automatically in ungated mode)
- New events from edits are written to the same JSONL file via `EventWriter`

### Phase 3: Branch Tree Explorer
- `TurnSidebar` swaps `OptionList` for `Tree[GameEvent]` showing the event DAG
- Both post the same `TurnSelected(Message)` — `ContentPane` is unchanged
- Branch points are events with multiple children (detected via `parent_id` grouping)

---

## CSS Rules

In `wargame.tcss`, use only semantic variables. Example structure:

```css
/* Source attribution borders */
EventCard { margin: 0 0 1 0; padding: 0 1; }
EventCard.source-simulation { border-left: thick $primary; }
EventCard.source-llm { border-left: thick $accent; }
EventCard.source-human { border-left: thick $warning; }
EventCard.source-system { border-left: thick $text-muted; }

/* KPI thresholds */
.kpi-normal { background: $success-muted; color: $text-success; }
.kpi-warning { background: $warning-muted; color: $text-warning; }
.kpi-critical { background: $error-muted; color: $text-error; }

/* Sidebar */
TurnSidebar { width: 1fr; max-width: 30; min-width: 20; }
ContentPane { width: 3fr; }

/* Responsive */
@media (width < 80) {
    TurnSidebar { display: none; }
    ContentPane { width: 1fr; }
}

/* Compact mode */
.compact EventCard { margin: 0; padding: 0; }
.compact KPIBar { height: 1; }
.compact .sparkline { display: none; }

/* Phase transition separator */
EventCard.phase-transition {
    border: none;
    height: 1;
    content-align: center middle;
    color: $text-muted;
    background: $surface;
}
```

## Code Quality

- Type hints on all signatures — `typing` generics, not bare `dict`/`list`
- Google-style docstrings on all public classes and methods
- No `# type: ignore` without explanation
- `ruff` clean (default rules)
- All styling in `.tcss` (except dynamic KPI threshold classes toggled via `add_class`/`remove_class`)
- `logging` stdlib — no print statements
- Every `Message` subclass has a docstring explaining when it is posted

## Execute

Begin at Step 1. After each checkpoint, run the tests and confirm they pass before proceeding. If a test fails, fix it before moving on. Report what you built and what the test results were at each checkpoint.
