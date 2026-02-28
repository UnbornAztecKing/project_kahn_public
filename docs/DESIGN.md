# SLOPR — Design Document

**S**trategic **L**everage & **O**perational **P**rojection **R**eckoner

A terminal UI for replaying and live-monitoring [Project Kahn](../README.md) wargame simulations.

---

## 1. Project Overview

SLOPR is a Textual-based terminal application that reads JSONL event streams produced by `sim.py` and renders them as an interactive, navigable wargame viewer.

**Key design principle**: SLOPR is a *viewer*, not a simulation runner. Events are written by `sim.py` via `EventWriter`; SLOPR reads them. This separation enables live-tail watching of an in-progress simulation without risking data corruption.

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

---

## 2. Architecture

### Module Map

```
slopr/
├── __main__.py         CLI entry point (click)
├── app.py              WargameApp — layout, routing, live-tail wiring
├── models.py           GameEvent (Pydantic v2) + EventType/EventSource enums
├── store.py            EventStore ABC + JSONLEventStore (read-only JSONL)
├── event_writer.py     EventWriter — append-only JSONL writer (used by sim.py)
├── fixtures.py         Demo fixture generator
├── tail.py             Tailer — background file polling for live events
├── task_store.py       TaskStore — JSONL-backed persistence for analysis tasks
├── analysis.py         Analysis commands + async Anthropic API caller
├── branches.py         BranchStore — branch manifest + fork logic
├── sim_queue.py        SimQueue — JSONL-backed queue for sim subprocess jobs
├── wargame.tcss        Textual CSS stylesheet
└── widgets/
    ├── banner.py           KahnBanner — centered ASCII art
    ├── content_pane.py     ContentPane — main scroll area, event grouping, split view
    ├── turn_sidebar.py     TurnSidebar / TurnIndex — turn tree + PaneNavBar
    ├── kpi_bar.py          KPIBar — bottom-docked live indicators
    ├── kpi_panel.py        KPIPanel — full-screen KPI history modal
    ├── search_bar.py       SearchBar — inline one-line search
    ├── search_modal.py     SearchModal — full-screen paginated search
    ├── branch_manager.py   BranchManager — branch tree + spawn/edit/delete buttons
    ├── branch_pane.py      BranchPane — full-width branch exploration pane
    ├── edit_event_modal.py EditEventModal — modal for editing events + branching
    ├── context_menu.py     ContextMenuScreen — right-click analysis menu
    ├── sim_manager_pane.py SimManagerPane — sim job queue table + live log
    └── tasks_pane.py       TasksPane — analysis task log + detail panel
```

### Data Flow

Events flow one-way from simulation to display:

1. `sim.py` writes `GameEvent` objects as JSONL lines via `EventWriter`
2. `JSONLEventStore` reads and indexes the JSONL file into memory
3. `Tailer` polls the JSONL file every 100 ms for new bytes, calling `EventStore.append()`
4. `WargameApp` routes user interactions (turn selection, branch operations, analysis commands) to the appropriate widgets

### Pane Architecture

The main display area uses a CSS class toggle (`--active`) to switch between four full-width panes:

| Pane ID | Widget | Shortcut |
|---------|--------|----------|
| `#pane-events` | `ContentPane` | default |
| `#pane-branches` | `BranchPane` | Ctrl+B |
| `#pane-sims` | `SimManagerPane` | Ctrl+S |
| `#pane-tasks` | `TasksPane` | Ctrl+T |

---

## 3. UI Philosophy

### Information Density Over Chrome

SLOPR uses a borderless, dark terminal aesthetic inspired by toolong. Every pixel serves data. No decorative borders, no status bars beyond the Textual Header/Footer.

### Color-Coded Phases

Each turn phase has a dedicated color used consistently in both the `TurnSidebar` tree and the `ContentPane` group borders:

| Phase | Color | Hex |
|-------|-------|-----|
| Reflection | Cyan-teal | `#00bcd4` |
| Forecast | Blue | `#42a5f5` |
| Signal | Purple | `#ab47bc` |
| Action | Amber | `#ffa726` |
| End State | Steel grey | `#90a4ae` |
| Initial State | Dark slate | `#546e7a` |
| Parameters | Teal | `#26a69a` |
| Game / Scenario | Green | `#4caf50` |
| Profiles | Indigo | `#7986cb` |
| Game Over | Red | `#ef5350` |
| Banner | Gold | `#daa520` |

Side coloring (A = blue `#5b9cf5`, B = coral `#f55b5b`) is used in split-view headers and KPI columns.

### Keyboard-First Navigation

All primary operations have keyboard shortcuts. The mouse is fully supported for clicking turns, events, and KPIs, but the entire application is navigable without leaving the keyboard.

### Minimal Modals

Modals are used only where a blocking decision is required (edit event, spawn sim, search). Non-blocking information is shown inline (KPI bar, task list, annotation cards).

---

## 4. Key Design Decisions

### Streaming Architecture

Events are written one per line, flushed and fsynced immediately by `EventWriter`. The `Tailer` reads only new bytes on each poll, making live display efficient even for long games. This allows SLOPR to be opened before or during a simulation.

### Immutable Event Store

`JSONLEventStore` is read-only. All mutations happen in `sim.py` via `EventWriter`. This separation means the TUI can be safely opened while a simulation runs — there is no risk of the TUI corrupting the event file.

### Responsive Split View

`ContentPane` tracks its last rendered mode (`_last_split`) and only rerenders on `Resize` events that cross the split threshold. This avoids unnecessary DOM rebuilds on minor resize events.

### Aligned Field Grid

In split view, `_event_rows()` extracts `(markup, css_class)` pairs for each rendered line of an event. `_build_aligned_pair()` zips A and B lists so fields at the same semantic position share a `Horizontal` row, giving pixel-accurate alignment without a CSS grid.

### Branch System

Branches fork the event stream at a specific event, allowing analysts to explore alternative decision paths without modifying the original simulation. Each branch:
- Has a JSONL file containing all events up to the fork point
- Can have an `edited_event` and `peer_edited_event` recording what the analyst changed
- Can spawn a new simulation from the fork point via `branches.spawn_sim()`

### Annotation Tree-Pipe Rendering

`ANNOTATION` events (added by analysts via right-click) are rendered as `AnnotationCard` widgets with `└─`/`├─` tree-pipe prefixes, positioned immediately after their parent `EventCard`. In split view, annotation rows are aligned alongside the A/B event grid.

### Task Persistence

Analysis tasks (right-click LLM commands) are persisted to `{sim}.jsonl.tasks.jsonl` via `TaskStore`. This means task results survive TUI restarts and can be reviewed later. Each task stores the full prompt, result text, token counts, and elapsed time.

---

## 5. Implemented Features

1. **JSONL event stream** — `sim.py` writes events; SLOPR reads and displays them
2. **Turn sidebar** — tree navigation with phase leaves and status glyphs (`*` LLM, `†` annotation, `~` edit)
3. **Content pane** — collapsible phase groups with per-type event cards
4. **Split A/B view** — side-by-side field-aligned layout above the split threshold (default: 100 columns)
5. **KPI bar** — bottom-docked live indicators with color-coded thresholds
6. **KPI history panel** — full-screen scrollable table (click KPI bar)
7. **Inline search** — `/` opens one-line search; first match loads automatically
8. **Full-screen search modal** — `Ctrl+F` opens paginated result list
9. **Live tailing** — 100 ms poll; sidebar and content pane update as new events arrive
10. **Branch system** — fork at any event; spawn sims from branches; manage via `Ctrl+B`
11. **Sim manager** — queue view with live log and cancel/retry controls (`Ctrl+S`)
12. **Analysis commands** — right-click any event for LLM analysis; results saved as annotations
13. **Task pane** — running log of analysis tasks with metadata/prompt/result detail (`Ctrl+T`)
14. **Annotation cards** — `└─`/`├─` tree-pipe rendering after parent events (vertical + split view)
15. **Branch body diff** — `difflib.unified_diff` in branch detail panel
16. **Task persistence** — `TaskStore` saves tasks to `{sim}.jsonl.tasks.jsonl`

---

## 6. Style Guide

### CSS Conventions

- All styles in `slopr/wargame.tcss`
- `DEFAULT_CSS` on widgets only for layout invariants (height, display)
- External `.tcss` for all color and spacing rules
- Class names: `kebab-case`, prefixed by context (`.event-*`, `.split-*`, `.kpi-*`, `.ann-*`)
- Never use inline styles in widget code

### Widget Naming

- Public widgets: `PascalCase` (e.g., `ContentPane`, `KPIBar`)
- Private helpers: `_PascalCase` (e.g., `_SplitPair`)
- Messages: `PascalCase` ending in noun (e.g., `TurnSelected`, `EventCardDoubleClicked`)

### Message Naming

- `{Source}{Verb}{Object}` pattern where practical
- Always include the relevant data object as an attribute
- Post to parent via `self.post_message()` — never call handlers directly

---

## 7. Extension Guide

### Adding a New Pane

1. Create a widget class in `slopr/widgets/your_pane.py`
2. Add it to `WargameApp.compose()` with `classes="main-pane"` and a unique `id`
3. Add a `Binding` in `BINDINGS` and an `action_switch_*()` method
4. Add a `NavTab` in `PaneNavBar` (`turn_sidebar.py`)
5. Add CSS for the pane in `wargame.tcss`

### Adding a New EventType Renderer

1. Add the new `EventType` value to `slopr/models.py`
2. In `EventCard.compose()`, add a branch to `_render_*()` for the new type
3. Add a phase group CSS class in `wargame.tcss` (`.group-yourtype { border: round #hexcolor; }`)
4. Map the new type to a group label in `_group_events()` (`content_pane.py`)
5. Add a color entry to `turn_sidebar._PHASE_COLORS` dict

### Adding a New Analysis Command

1. Add an `AnalysisCommand` to `COMMANDS` in `slopr/analysis.py`
2. Add a prompt builder branch in `_build_prompt()`
3. The command will automatically appear in the right-click context menu for applicable phases
