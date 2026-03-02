"""Pydantic models for state configuration.

All configuration required to run a simulation for one side — leader profile,
military capabilities, and strategic assessment — is expressed here as typed
Pydantic models.  The concrete instances (``STATE_A``, ``STATE_B``) live in
``config/state_a.py`` and ``config/state_b.py``.
"""

from __future__ import annotations

from pydantic import BaseModel


class NuclearArsenal(BaseModel):
    icbms: int
    submarine_launched: int
    bomber_delivered: int
    total_warheads: int


class DeliverySystems(BaseModel):
    accuracy: str
    reliability: str
    survivability: str
    first_strike_capability: str


class TechnologicalCapability(BaseModel):
    command_control: str
    intelligence_gathering: str
    precision_guidance: str


class ConventionalForces(BaseModel):
    army_divisions: int
    naval_capability: str
    air_force: str
    logistics: str


class MilitaryConfig(BaseModel):
    conventional_strength: int
    nuclear_arsenal: NuclearArsenal
    delivery_systems: DeliverySystems
    technological_capability: TechnologicalCapability
    conventional_forces: ConventionalForces
    strategic_doctrine: str
    key_strengths: list[str]
    key_weaknesses: list[str]
    # Simulation math inputs — previously hardcoded in get_base_military_capabilities()
    base_conventional_capability: float
    base_nuclear_capability: float
    # Multiplier applied to the base accident probability (1.0 = default; >1.0 = elevated risk)
    accident_rate_modifier: float = 1.0


class LeaderConfig(BaseModel):
    name: str
    biography: str
    traits: list[str]
    decision_style: str
    nuclear_doctrine: str
    risk_tolerance: str
    primary_concerns: list[str]
    decision_factors: dict[str, float]


class OpponentLeadership(BaseModel):
    assessment: str
    predictability: str
    risk_tolerance: str


class MilitaryThreat(BaseModel):
    nuclear_capability: str
    conventional_threat: str
    first_strike_assessment: str
    escalation_tendency: str


class AssessmentConfig(BaseModel):
    overall: str
    opponent_leadership: OpponentLeadership
    military_threat: MilitaryThreat
    # Normalised from strategic_concerns (State A) / strategic_assessment (State B)
    strategic_notes: list[str]
    # State B only; empty for State A
    opportunities: list[str] = []
    intelligence_confidence: str


class StateConfig(BaseModel):
    """Complete configuration for one side of the simulation."""

    state_id: str
    """Short uppercase identifier, e.g. 'A', 'B', 'C'.  Used internally."""
    display_name: str
    """Human-readable name shown in the UI and LLM prompts, e.g. 'State Alpha'."""
    leader: LeaderConfig
    military: MilitaryConfig
    assessment: AssessmentConfig
