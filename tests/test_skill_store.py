"""Tests for SkillStore — CRUD, persistence, and builtin management."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopr.skill_store import BUILTIN_SKILLS, Skill, SkillStore


# ── Helpers ───────────────────────────────────────────────────────────────────


def _store(tmp_path: Path) -> SkillStore:
    """Return a fresh SkillStore backed by a temp path (no file yet)."""
    return SkillStore(tmp_path / "game.jsonl.skills.json")


def _custom_skill(**kw) -> Skill:
    defaults = dict(
        id="",  # will be assigned by add()
        label="My custom skill",
        applicable_phases=["action"],
        prompt_template="Analyze this: {event_block}\n\nContext: {context_block}",
        builtin=False,
    )
    defaults.update(kw)
    return Skill(**defaults)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_skill_store_creates_with_builtins(tmp_path: Path) -> None:
    """Fresh store (no file) initialises with exactly the built-in skills."""
    store = _store(tmp_path)
    skills = store.list_all()
    assert len(skills) == len(BUILTIN_SKILLS)
    assert all(s.builtin for s in skills)
    builtin_ids = {s.id for s in BUILTIN_SKILLS}
    assert {s.id for s in skills} == builtin_ids


def test_skill_store_add_custom(tmp_path: Path) -> None:
    """add() appends a new custom skill and list_all returns n+1 skills."""
    store = _store(tmp_path)
    n_before = len(store.list_all())

    new_skill = _custom_skill(label="My test skill")
    stored = store.add(new_skill)

    all_skills = store.list_all()
    assert len(all_skills) == n_before + 1
    assert stored.id  # UUID was assigned
    assert not stored.builtin
    assert stored.label == "My test skill"
    # The stored skill is retrievable
    assert store.get(stored.id) is not None


def test_skill_store_update(tmp_path: Path) -> None:
    """update() changes the label of a skill (custom or builtin)."""
    store = _store(tmp_path)

    custom = store.add(_custom_skill(label="Original label"))
    store.update(custom.id, label="Updated label")

    retrieved = store.get(custom.id)
    assert retrieved is not None
    assert retrieved.label == "Updated label"


def test_skill_store_delete_custom(tmp_path: Path) -> None:
    """delete() removes a custom skill; builtin count is unchanged."""
    store = _store(tmp_path)
    n_builtins = len(BUILTIN_SKILLS)

    custom = store.add(_custom_skill())
    assert len(store.list_all()) == n_builtins + 1

    store.delete(custom.id)
    assert len(store.list_all()) == n_builtins
    assert store.get(custom.id) is None


def test_skill_store_delete_builtin_raises(tmp_path: Path) -> None:
    """delete() raises ValueError for built-in skills."""
    store = _store(tmp_path)
    builtin_id = BUILTIN_SKILLS[0].id

    with pytest.raises(ValueError, match="built-in"):
        store.delete(builtin_id)

    # Builtin is still present
    assert store.get(builtin_id) is not None


def test_skill_store_persistence(tmp_path: Path) -> None:
    """Custom skill survives save + reload (new SkillStore instance)."""
    path = tmp_path / "game.jsonl.skills.json"

    store1 = SkillStore(path)
    custom = store1.add(_custom_skill(label="Persistent skill"))
    custom_id = custom.id

    # Create a second instance loading from the same file
    store2 = SkillStore(path)
    retrieved = store2.get(custom_id)
    assert retrieved is not None
    assert retrieved.label == "Persistent skill"
    assert not retrieved.builtin
    # Builtins are still present
    assert len(store2.list_all()) == len(BUILTIN_SKILLS) + 1
