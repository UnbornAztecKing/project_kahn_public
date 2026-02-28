"""Skill definitions and persistent storage.

A :class:`Skill` is a reusable prompt template that can be applied to game
events.  :class:`SkillStore` persists skills to a JSON file alongside the
root JSONL, initialises with built-in skills, and supports CRUD for custom
user-defined skills.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from slopr.models import GameEvent


# ── Skill dataclass ───────────────────────────────────────────────────────────


@dataclass
class Skill:
    """A named, phase-filtered prompt template."""

    id: str
    label: str
    applicable_phases: list[str]
    """Phases this skill applies to.  Empty list = all phases."""
    prompt_template: str
    """{event_block} and {context_block} placeholders are substituted at runtime."""
    builtin: bool = field(default=False, compare=False)
    glyph: str = field(default="", compare=False)
    """Short Unicode glyph shown in context menu, TagCard title, and sidebar."""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Skill":
        return Skill(
            id=d["id"],
            label=d["label"],
            applicable_phases=d.get("applicable_phases", []),
            prompt_template=d.get("prompt_template", ""),
            builtin=d.get("builtin", False),
            glyph=d.get("glyph", ""),
        )


# ── Built-in skills ───────────────────────────────────────────────────────────

BUILTIN_SKILLS: list[Skill] = [
    Skill(
        id="analyze_event",
        label="Analyze this event",
        applicable_phases=[],
        prompt_template=(
            "Analyze the following wargame event.  Explain what it reveals about "
            "the strategic situation, actor intentions, and likely downstream "
            "consequences.\n\n"
            "FOCAL EVENT:\n{event_block}\n\n"
            "CONTEXT EVENTS (chronological):\n{context_block}"
        ),
        builtin=True,
        glyph="★",
    ),
    Skill(
        id="compare_ab",
        label="Compare A vs B",
        applicable_phases=["action", "signal", "forecast", "reflection"],
        prompt_template=(
            "Compare the perspectives and behaviors of Actor A and Actor B as "
            "revealed in the following event and its context.  Identify asymmetries "
            "in information, intent, risk tolerance, or capability.\n\n"
            "FOCAL EVENT:\n{event_block}\n\n"
            "CONTEXT EVENTS:\n{context_block}"
        ),
        builtin=True,
        glyph="⇄",
    ),
    Skill(
        id="escalation_risk",
        label="Assess escalation risk",
        applicable_phases=["action", "signal"],
        prompt_template=(
            "Assess the escalation risk introduced by the following action or signal.  "
            "Consider misperception likelihood, commitment traps, and available "
            "off-ramps.  Rate risk as Low / Medium / High and justify.\n\n"
            "FOCAL EVENT:\n{event_block}\n\n"
            "CONTEXT EVENTS:\n{context_block}"
        ),
        builtin=True,
        glyph="⬆",
    ),
    Skill(
        id="leader_psychology",
        label="Leader psychology",
        applicable_phases=["reflection", "forecast"],
        prompt_template=(
            "Analyze the psychology and decision-making of the leader(s) depicted "
            "in this event.  Consider cognitive biases, emotional state, time "
            "pressure, and the influence of prior events on their reasoning.\n\n"
            "FOCAL EVENT:\n{event_block}\n\n"
            "CONTEXT EVENTS:\n{context_block}"
        ),
        builtin=True,
        glyph="ψ",
    ),
    Skill(
        id="counterfactual",
        label="What if… (alternative)",
        applicable_phases=[],
        prompt_template=(
            "Propose a plausible alternative decision or action at the point of this "
            "event.  Describe what would have needed to be different and trace the "
            "likely divergent path for the next 2–3 turns.\n\n"
            "FOCAL EVENT:\n{event_block}\n\n"
            "CONTEXT EVENTS:\n{context_block}"
        ),
        builtin=True,
        glyph="◇",
    ),
]

_BUILTIN_MAP: dict[str, Skill] = {s.id: s for s in BUILTIN_SKILLS}


# ── SkillStore ────────────────────────────────────────────────────────────────


class SkillStore:
    """Persist and manage skill definitions alongside a JSONL game file.

    On first use (no JSON file) the store is seeded with :data:`BUILTIN_SKILLS`.
    Custom skills are persisted; built-ins are always re-seeded from the
    in-process ``BUILTIN_SKILLS`` list (so code changes to templates take effect
    automatically unless the user has customised a skill).
    """

    @staticmethod
    def path_for(root_jsonl: Path) -> Path:
        """Return the skills file path for *root_jsonl*."""
        return Path(str(root_jsonl) + ".skills.json")

    def __init__(self, path: Path) -> None:
        self._path = path
        self._skills: list[Skill] = []
        self._by_id: dict[str, Skill] = {}
        self._load()

    # ── Private ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load skills from disk; fall back to built-ins if file missing."""
        custom: list[Skill] = []
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for d in data.get("skills", []):
                    s = Skill.from_dict(d)
                    if not s.builtin:
                        custom.append(s)
            except Exception:
                pass  # corrupt file → start fresh with built-ins only

        # Always seed built-ins first (preserves order), then append custom
        self._skills = list(BUILTIN_SKILLS) + custom
        self._by_id = {s.id: s for s in self._skills}

    # ── Query ────────────────────────────────────────────────────────────

    def list_all(self) -> list[Skill]:
        """Return all skills (built-ins first, then custom)."""
        return list(self._skills)

    def get(self, skill_id: str) -> Skill | None:
        """Return skill by id, or ``None``."""
        return self._by_id.get(skill_id)

    def applicable_skills(self, event: "GameEvent") -> list[Skill]:
        """Return skills whose ``applicable_phases`` include *event*'s phase."""
        phase = (event.phase or "").lower()
        return [
            s for s in self._skills
            if not s.applicable_phases or phase in s.applicable_phases
        ]

    # ── Mutations ────────────────────────────────────────────────────────

    def add(self, skill: Skill) -> Skill:
        """Add a new custom skill (assigns a fresh UUID id).

        Returns the stored skill with its assigned id.
        """
        new_id = str(uuid.uuid4())
        stored = Skill(
            id=new_id,
            label=skill.label,
            applicable_phases=list(skill.applicable_phases),
            prompt_template=skill.prompt_template,
            builtin=False,
            glyph=skill.glyph,
        )
        self._skills.append(stored)
        self._by_id[new_id] = stored
        self.save()
        return stored

    def update(self, skill_id: str, **kwargs) -> None:
        """Update mutable fields of skill *skill_id*.

        Accepted kwargs: ``label``, ``applicable_phases``, ``prompt_template``.
        Raises :class:`ValueError` if *skill_id* not found.
        """
        skill = self._by_id.get(skill_id)
        if skill is None:
            raise ValueError(f"Skill '{skill_id}' not found")
        updated = Skill(
            id=skill.id,
            label=kwargs.get("label", skill.label),
            applicable_phases=kwargs.get("applicable_phases", list(skill.applicable_phases)),
            prompt_template=kwargs.get("prompt_template", skill.prompt_template),
            builtin=skill.builtin,
            glyph=kwargs.get("glyph", skill.glyph),
        )
        idx = next(i for i, s in enumerate(self._skills) if s.id == skill_id)
        self._skills[idx] = updated
        self._by_id[skill_id] = updated
        self.save()

    def delete(self, skill_id: str) -> None:
        """Delete a custom skill.

        Raises :class:`ValueError` if the skill is built-in or not found.
        """
        skill = self._by_id.get(skill_id)
        if skill is None:
            raise ValueError(f"Skill '{skill_id}' not found")
        if skill.builtin:
            raise ValueError(f"Cannot delete built-in skill '{skill_id}'")
        self._skills = [s for s in self._skills if s.id != skill_id]
        del self._by_id[skill_id]
        self.save()

    def reset_builtin(self, skill_id: str) -> None:
        """Restore a built-in skill to its default template.

        Raises :class:`ValueError` if *skill_id* is not a built-in skill.
        """
        original = _BUILTIN_MAP.get(skill_id)
        if original is None:
            raise ValueError(f"'{skill_id}' is not a built-in skill")
        idx = next((i for i, s in enumerate(self._skills) if s.id == skill_id), None)
        if idx is None:
            self._skills.append(original)
        else:
            self._skills[idx] = original
        self._by_id[skill_id] = original
        self.save()

    def save(self) -> None:
        """Atomically write skills to disk (custom skills only; built-ins re-seeded on load)."""
        payload = {
            "skills": [
                s.to_dict() for s in self._skills
                # Persist all (built-ins too, so user edits survive restart)
            ]
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._path)
