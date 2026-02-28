"""AI analysis skills for wargame events.

Each skill maps to a focused prompt template sent to a model provider.
The blocking API call is executed via ``asyncio.to_thread`` so it never
blocks the Textual event loop.

Two providers are supported:
  • Anthropic — any ``claude-*`` model string
  • Ollama    — any ``ollama:<model>`` model string (OpenAI-compat endpoint)

Usage::

    from slopr.skill_store import SkillStore
    skill_store = SkillStore(SkillStore.path_for(jsonl_path))
    skills = skill_store.applicable_skills(event)
    result = await run_skill(skills[0], event, context_events,
                             model="claude-sonnet-4-6",
                             max_tokens=1024,
                             temperature=1.0,
                             thinking="none")
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from slopr.skill_store import BUILTIN_SKILLS, Skill  # noqa: F401 — re-exported for callers

if TYPE_CHECKING:
    from slopr.models import GameEvent


# ── Backward-compat shims ─────────────────────────────────────────────────────

# Keep old names importable so existing callers don't break immediately.
AnalysisCommand = Skill  # type alias
COMMANDS = BUILTIN_SKILLS  # list alias


def applicable_commands(event: "GameEvent") -> list[Skill]:
    """Backward-compat wrapper — prefer ``SkillStore.applicable_skills()``."""
    phase = (event.phase or "").lower()
    return [
        s for s in BUILTIN_SKILLS
        if not s.applicable_phases or phase in s.applicable_phases
    ]


def applicable_skills(event: "GameEvent", skills: list[Skill]) -> list[Skill]:
    """Return skills from *skills* that apply to *event*'s phase."""
    phase = (event.phase or "").lower()
    return [
        s for s in skills
        if not s.applicable_phases or phase in s.applicable_phases
    ]


# ── Prompt helpers ────────────────────────────────────────────────────────────


def _format_event(evt: "GameEvent") -> str:
    """Render a single event as a compact text block for the prompt."""
    parts = [
        f"[T{evt.turn_number} | {evt.event_type.value} | {evt.phase}]",
        f"Title: {evt.title}",
    ]
    if evt.body:
        body_excerpt = evt.body[:800] + ("…" if len(evt.body) > 800 else "")
        parts.append(f"Body: {body_excerpt}")
    if evt.structured_data:
        import json
        sd_text = json.dumps(evt.structured_data, indent=2)
        if len(sd_text) > 600:
            sd_text = sd_text[:600] + "\n…"
        parts.append(f"Data: {sd_text}")
    return "\n".join(parts)


def _context_block(context_events: "list[GameEvent]") -> str:
    if not context_events:
        return "(no additional context events provided)"
    return "\n\n---\n\n".join(_format_event(e) for e in context_events[:8])


def _render_prompt(skill: Skill, event_block: str, context_block: str) -> str:
    """Substitute template placeholders for *skill*."""
    return skill.prompt_template.format(
        event_block=event_block,
        context_block=context_block,
    )


_SYSTEM_PROMPT = """\
You are an expert analyst of nuclear and conventional military crises, \
specializing in wargame simulation research.  You provide concise, \
substantive analysis grounded in the event data provided.  \
Do not add caveats about being an AI.  Keep responses under 400 words \
unless depth is essential."""


# ── API calls ────────────────────────────────────────────────────────────────

_OLLAMA_PREFIX = "ollama:"


def _sync_run_anthropic(
    skill_id: str,
    prompt: str,
    model: str,
    max_tokens: int,
    temperature: float,
    thinking: str,
) -> tuple[str, str, dict]:
    """Blocking Anthropic API call."""
    import anthropic  # soft import so missing dep doesn't break TUI at startup

    client = anthropic.Anthropic()
    kwargs: dict = dict(
        model=model,
        max_tokens=max_tokens,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    if thinking == "adaptive":
        kwargs["thinking"] = {"type": "adaptive"}
    else:
        kwargs["temperature"] = temperature
    response = client.messages.create(**kwargs)
    meta = {
        "input_tokens":  response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return prompt, response.content[0].text, meta


def _sync_run_ollama(
    skill_id: str,
    prompt: str,
    model: str,
    max_tokens: int,
    temperature: float,
) -> tuple[str, str, dict]:
    """Blocking Ollama API call via the OpenAI-compatible endpoint."""
    import openai  # soft import

    client = openai.OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama",  # Ollama ignores the key; required by openai SDK
    )
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
    )
    meta = {
        "input_tokens":  response.usage.prompt_tokens     if response.usage else 0,
        "output_tokens": response.usage.completion_tokens if response.usage else 0,
    }
    result_text = response.choices[0].message.content or "" if response.choices else ""
    return prompt, result_text, meta


def _sync_run(
    skill_id: str,
    prompt: str,
    model: str,
    max_tokens: int = 1024,
    temperature: float = 1.0,
    thinking: str = "none",
) -> tuple[str, str, dict]:
    """Dispatch to the correct provider backend.  Run via ``asyncio.to_thread``.

    Returns:
        A tuple of (prompt, result_text, metadata_dict).
    """
    if model.startswith(_OLLAMA_PREFIX):
        ollama_model = model[len(_OLLAMA_PREFIX):]
        return _sync_run_ollama(skill_id, prompt, ollama_model, max_tokens, temperature)
    return _sync_run_anthropic(skill_id, prompt, model, max_tokens, temperature, thinking)


async def run_skill(
    skill: Skill,
    event: "GameEvent",
    context_events: "list[GameEvent]",
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 1024,
    temperature: float = 1.0,
    thinking: str = "none",
) -> tuple[str, str, dict]:
    """Build a prompt from *skill*'s template and call the configured provider.

    The blocking API call is offloaded to a thread so the Textual event loop
    is not blocked.

    Args:
        skill: The skill to execute.
        event: The focal event to analyse.
        context_events: Nearby events for context (≤8 used).
        model: Model ID — ``claude-*`` for Anthropic, ``ollama:<name>`` for Ollama.
        max_tokens: Output token budget.
        temperature: Sampling temperature (ignored when *thinking* is "adaptive").
        thinking: "none" or "adaptive" (Anthropic only).

    Returns:
        A tuple of (prompt, result_text, metadata_dict).
    """
    event_block   = _format_event(event)
    context_block = _context_block(context_events)
    prompt        = _render_prompt(skill, event_block, context_block)
    return await asyncio.to_thread(
        _sync_run, skill.id, prompt, model, max_tokens, temperature, thinking
    )


async def run_command(
    command_id: str,
    event: "GameEvent",
    context_events: "list[GameEvent]",
    model: str = "claude-sonnet-4-6",
) -> tuple[str, str, dict]:
    """Backward-compat wrapper around :func:`run_skill`.

    Looks up *command_id* in ``BUILTIN_SKILLS``; falls back to the first
    built-in skill if not found.
    """
    skill = next((s for s in BUILTIN_SKILLS if s.id == command_id), BUILTIN_SKILLS[0])
    return await run_skill(skill, event, context_events, model)
