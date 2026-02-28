# Project Kahn — Simulation Runner
# Usage: make <target>
# Requires: uv (https://github.com/astral-sh/uv)
# API keys: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY in .env
# Ollama:   ollama serve  (no API key required)

UV  := uv run python
FMT := uv run black

# ── Frontier models (canonical tournament) ────────────────────────────────────
SONNET       := claude-sonnet-4-6
OPUS         := claude-opus-4-6
GPT          := gpt-5.2
GEMINI       := gemini-3-flash-preview

# ── 24GiB-capable Local Ollama models (prefix with ollama:) ─────────────────────────────────
OL_LLAMA  := ollama:huihui_ai/llama3.2-abliterate:3b
OL_MISTRAL := ollama:huihui_ai/mistral-small-abliterated:24b
OL_QWEN   := ollama:huihui_ai/qwen3-abliterated:16b
OL_GEMMA  := ollama:huihui_ai/gemma3-abliterated:4b

# ── Game scripts ──────────────────────────────────────────────────────────────
V11 := Kahn_game_v11.py   # open-ended (no deadline)
V12 := Kahn_game_v12.py   # deadline-enforced
SIM := sim.py             # simulated nuclear war

# ── Ollama model pulls ────────────────────────────────────────────────────────

.PHONY: pull-llama pull-mistral pull-qwen pull-gemma pull-ollama

pull-llama:
	ollama pull $(patsubst ollama:%,%,$(OL_LLAMA))

pull-mistral:
	ollama pull $(patsubst ollama:%,%,$(OL_MISTRAL))

pull-qwen:
	ollama pull $(patsubst ollama:%,%,$(OL_QWEN))

pull-gemma:
	ollama pull $(patsubst ollama:%,%,$(OL_GEMMA))

pull-ollama: pull-llama pull-mistral pull-qwen pull-gemma

.PHONY: fmt fmt-check typecheck
fmt:
	$(FMT) .

fmt-check:
	$(FMT) --check .

typecheck:
	uv run mypy --ignore-missing-imports slopr/

# ── TUI viewer ──────────────────────────────────────────────────────────────

.PHONY: tui tui-demo fixtures test test-verbose

tui:
	uv run python -m slopr $(FILE)

tui-demo: fixtures
	uv run python -m slopr demo_events.jsonl

fixtures:
	uv run python -m slopr.fixtures --output demo_events.jsonl

test:
	uv run pytest tests/ -v

test-verbose:
	uv run pytest tests/ -v

.PHONY: help
help:
	@echo "Project Kahn — scenario and tournament runner"
	@echo ""
	@echo "Ollama model management:"
	@echo "  make pull-llama     Pull $(OL_LLAMA)"
	@echo "  make pull-mistral   Pull $(OL_MISTRAL)"
	@echo "  make pull-qwen      Pull $(OL_QWEN)"
	@echo "  make pull-gemma     Pull $(OL_GEMMA)"
	@echo "  make pull-ollama    Pull all four models"
	@echo ""
	@echo "TUI viewer:"
	@echo "  make tui FILE=x.jsonl   Launch TUI for a JSONL event file"
	@echo "  make tui-demo           Generate fixtures + launch TUI"
	@echo "  make fixtures           Generate demo_events.jsonl"
	@echo ""
	@echo "Testing:"
	@echo "  make test               Run tests (quiet)"
	@echo "  make test-verbose       Run tests (verbose)"
	@echo ""
	@echo "Formatting:"
	@echo "  make fmt            Format all Python files with black"
	@echo "  make fmt-check      Check formatting without modifying files"
	@echo ""
	@echo "Frontier model scenarios:"
	@echo "  make alliance         Alliance credibility test (v11, Claude vs GPT)"
	@echo "  make first-strike     First-strike fear crisis (v12, Claude vs GPT)"
	@echo "  make standoff         Strategic standoff, asymmetric balance (v12)"
	@echo "  make regime-survival  Existential/regime survival stakes (v12)"
	@echo "  make power-transition Power transition, State A rising (v11)"
	@echo ""
	@echo "Nuclear Kargil (STATE_C vs STATE_D):"
	@echo "  make sim-kargil             Nuclear Kargil sim, Sonnet vs GPT, State C vs D"
	@echo "  make view-sim-kargil        View in TUI"
	@echo ""
	@echo "Frontier sim.py scenarios:"
	@echo "  make sim-first-strike-a-sonnet-b-gpt          First-strike sim, Sonnet vs GPT"
	@echo "  make view-sim-first-strike-a-sonnet-b-gpt     View in TUI"
	@echo "  make sim-first-strike-a-opus-b-opus           First-strike sim, Opus vs Opus"
	@echo "  make view-sim-first-strike-a-opus-b-opus      View in TUI"
	@echo ""
	@echo "Ollama (local) scenarios:"
	@echo "  make ollama-alliance       Alliance test, llama3.2 vs mistral"
	@echo "  make ollama-first-strike   First-strike, llama3.2 vs qwen2.5"
	@echo "  make ollama-standoff       Standoff, mistral vs qwen2.5"
	@echo "  make ollama-regime         Regime survival, llama3.2 vs gemma3"
	@echo "  make ollama-mixed          Mixed: Claude vs llama3.2"
	@echo ""
	@echo "Ollama sim.py scenarios:"
	@echo "  make sim-ollama-first-strike-gemma-mistral   First-strike sim, gemma vs mistral"
	@echo "  make view-sim-ollama-first-strike-gemma-mistral  View in TUI"
	@echo ""
	@echo "Tournaments:"
	@echo "  make tournament            Canonical 9-game round-robin (frontier models)"
	@echo "  make ollama-tournament     9-game round-robin (Ollama models only)"

# ── Interesting frontier scenarios ────────────────────────────────────────────

# Alliance credibility — the canonical high-stakes scenario used in the paper.
# Open-ended (v11): no deadline, models must choose when to escalate or settle.
.PHONY: alliance
alliance:
	$(UV) $(V11) \
	  --model_a $(SONNET) --model_b $(GPT) \
	  --scenario v7_alliance --aggressor A --turns 30

# First-strike fear — credible intel of imminent nuclear strike; 15-turn window.
.PHONY: first-strike
first-strike:
	$(UV) $(V12) \
	  --model_a $(SONNET) --model_b $(GPT) \
	  --scenario v8_first_strike_fear --aggressor A --turns 15

# Strategic standoff — asymmetric conventional balance (Berlin 1961-inspired).
.PHONY: standoff
standoff:
	$(UV) $(V12) \
	  --model_a $(SONNET) --model_b $(GPT) \
	  --scenario v10_standoff_crisis --aggressor B --turns 12

# Regime survival — existential stakes, opponent seeks regime change.
.PHONY: regime-survival
regime-survival:
	$(UV) $(V12) \
	  --model_a $(GPT) --model_b $(SONNET) \
	  --scenario v9_regime_survival --aggressor A --turns 20

# Power transition — State A is the rising challenger.
.PHONY: power-transition
power-transition:
	$(UV) $(V11) \
	  --model_a $(SONNET) --model_b $(GEMINI) \
	  --scenario v7_power_transition_a_rising --aggressor A --turns 30

# Nuclear Kargil standoff — State C (India-like) vs State D (Pakistan-like).
# Uses sim.py with --state_a C --state_b D to load the Kargil-specific actor configs.
.PHONY: sim-kargil
sim-kargil:
	rm -f sim-kargil.jsonl
	$(UV) $(SIM) \
	  --model_a $(SONNET) --model_b $(GPT) \
	  --scenario v11_nuclear_kargil --state_a C --state_b D \
	  --aggressor B --turns 20 \
	  --events-file sim-kargil.jsonl

.PHONY: view-sim-kargil
view-sim-kargil:
	uv run python -m slopr sim-kargil.jsonl

# ── Frontier sim.py scenarios ────────────────────────────────────────────────

.PHONY: sim-first-strike-a-sonnet-b-gpt
sim-first-strike-a-sonnet-b-gpt:
	rm -f sim-first-strike-a-sonnet-b-gpt.jsonl
	$(UV) $(SIM) \
	  --model_a $(SONNET) --model_b $(GPT) \
	  --scenario v8_first_strike_fear --aggressor A --turns 10 \
	  --events-file sim-first-strike-a-sonnet-b-gpt.jsonl

.PHONY: view-sim-first-strike-a-sonnet-b-gpt
view-sim-first-strike-a-sonnet-b-gpt:
	uv run python -m slopr sim-first-strike-a-sonnet-b-gpt.jsonl

.PHONY: sim-first-strike-a-opus-b-opus
sim-first-strike-a-opus-b-opus:
	rm -f sim-first-strike-a-opus-b-opus.jsonl
	$(UV) $(SIM) \
	  --model_a $(OPUS) --model_b $(OPUS) \
	  --scenario v8_first_strike_fear --aggressor A --turns 10 \
	  --events-file sim-first-strike-a-opus-b-opus.jsonl

.PHONY: view-sim-first-strike-a-opus-b-opus
view-sim-first-strike-a-opus-b-opus:
	uv run python -m slopr sim-first-strike-a-opus-b-opus.jsonl

# ── Ollama (local) scenarios ──────────────────────────────────────────────────

.PHONY: ollama-alliance
ollama-alliance:
	$(UV) $(V11) \
	  --model_a $(OL_LLAMA) --model_b $(OL_MISTRAL) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: ollama-first-strike
ollama-first-strike:
	$(UV) $(V12) \
	  --model_a $(OL_LLAMA) --model_b $(OL_QWEN) \
	  --scenario v8_first_strike_fear --aggressor A --turns 15

.PHONY: sim-ollama-first-strike-gemma-mistral
sim-ollama-first-strike-gemma-mistral:
	rm -f sim-ollama-first-strike-gemma-mistral.jsonl
	$(UV) $(SIM) \
	  --model_a $(OL_GEMMA) --model_b $(OL_MISTRAL) \
	  --scenario v8_first_strike_fear --aggressor A --turns 4 \
	  --events-file sim-ollama-first-strike-gemma-mistral.jsonl

.PHONY: view-sim-ollama-first-strike-gemma-mistral
view-sim-ollama-first-strike-gemma-mistral:
	uv run python -m slopr sim-ollama-first-strike-gemma-mistral.jsonl

.PHONY: ollama-standoff
ollama-standoff:
	$(UV) $(V12) \
	  --model_a $(OL_MISTRAL) --model_b $(OL_QWEN) \
	  --scenario v10_standoff_crisis --aggressor B --turns 12

.PHONY: ollama-regime
ollama-regime:
	$(UV) $(V12) \
	  --model_a $(OL_LLAMA) --model_b $(OL_GEMMA) \
	  --scenario v9_regime_survival --aggressor A --turns 20

# Mixed: one frontier model vs one local model — useful for capability comparison.
.PHONY: ollama-mixed
ollama-mixed:
	$(UV) $(V11) \
	  --model_a $(SONNET) --model_b $(OL_LLAMA) \
	  --scenario v7_alliance --aggressor A --turns 30

# ── Canonical tournament (round-robin, 3 models × 3 matchups × A/B sides) ─────
# Mirrors the 9-game subset of the paper tournament on the alliance scenario.
# Full 21-game tournament requires running across multiple scenarios.

.PHONY: tournament
tournament: \
  t-claude-gpt-a t-gpt-claude-a t-claude-gpt-b \
  t-claude-gemini-a t-gemini-claude-a \
  t-gpt-gemini-a t-gemini-gpt-a \
  t-claude-gemini-b t-gpt-gemini-b

.PHONY: t-claude-gpt-a
t-claude-gpt-a:
	$(UV) $(V12) --model_a $(SONNET) --model_b $(GPT) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: t-gpt-claude-a
t-gpt-claude-a:
	$(UV) $(V12) --model_a $(GPT) --model_b $(SONNET) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: t-claude-gpt-b
t-claude-gpt-b:
	$(UV) $(V12) --model_a $(SONNET) --model_b $(GPT) \
	  --scenario v7_alliance --aggressor B --turns 30

.PHONY: t-claude-gemini-a
t-claude-gemini-a:
	$(UV) $(V12) --model_a $(SONNET) --model_b $(GEMINI) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: t-gemini-claude-a
t-gemini-claude-a:
	$(UV) $(V12) --model_a $(GEMINI) --model_b $(SONNET) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: t-gpt-gemini-a
t-gpt-gemini-a:
	$(UV) $(V12) --model_a $(GPT) --model_b $(GEMINI) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: t-gemini-gpt-a
t-gemini-gpt-a:
	$(UV) $(V12) --model_a $(GEMINI) --model_b $(GPT) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: t-claude-gemini-b
t-claude-gemini-b:
	$(UV) $(V12) --model_a $(SONNET) --model_b $(GEMINI) \
	  --scenario v7_alliance --aggressor B --turns 30

.PHONY: t-gpt-gemini-b
t-gpt-gemini-b:
	$(UV) $(V12) --model_a $(GPT) --model_b $(GEMINI) \
	  --scenario v7_alliance --aggressor B --turns 30

# ── Ollama round-robin tournament (no API keys required) ──────────────────────

.PHONY: ollama-tournament
ollama-tournament: \
  ot-llama-mistral-a ot-mistral-llama-a \
  ot-llama-qwen-a   ot-qwen-llama-a \
  ot-mistral-qwen-a ot-qwen-mistral-a \
  ot-llama-gemma-a  ot-mistral-gemma-a ot-qwen-gemma-a

.PHONY: ot-llama-mistral-a
ot-llama-mistral-a:
	$(UV) $(V12) --model_a $(OL_LLAMA) --model_b $(OL_MISTRAL) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: ot-mistral-llama-a
ot-mistral-llama-a:
	$(UV) $(V12) --model_a $(OL_MISTRAL) --model_b $(OL_LLAMA) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: ot-llama-qwen-a
ot-llama-qwen-a:
	$(UV) $(V12) --model_a $(OL_LLAMA) --model_b $(OL_QWEN) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: ot-qwen-llama-a
ot-qwen-llama-a:
	$(UV) $(V12) --model_a $(OL_QWEN) --model_b $(OL_LLAMA) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: ot-mistral-qwen-a
ot-mistral-qwen-a:
	$(UV) $(V12) --model_a $(OL_MISTRAL) --model_b $(OL_QWEN) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: ot-qwen-mistral-a
ot-qwen-mistral-a:
	$(UV) $(V12) --model_a $(OL_QWEN) --model_b $(OL_MISTRAL) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: ot-llama-gemma-a
ot-llama-gemma-a:
	$(UV) $(V12) --model_a $(OL_LLAMA) --model_b $(OL_GEMMA) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: ot-mistral-gemma-a
ot-mistral-gemma-a:
	$(UV) $(V12) --model_a $(OL_MISTRAL) --model_b $(OL_GEMMA) \
	  --scenario v7_alliance --aggressor A --turns 30

.PHONY: ot-qwen-gemma-a
ot-qwen-gemma-a:
	$(UV) $(V12) --model_a $(OL_QWEN) --model_b $(OL_GEMMA) \
	  --scenario v7_alliance --aggressor A --turns 30
