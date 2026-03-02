"""State A configuration — President Alpha / State Alpha."""

from config.models import (
    AssessmentConfig,
    ConventionalForces,
    DeliverySystems,
    LeaderConfig,
    MilitaryConfig,
    MilitaryThreat,
    NuclearArsenal,
    OpponentLeadership,
    StateConfig,
    TechnologicalCapability,
)

STATE_A: StateConfig = StateConfig(
    state_id="A",
    display_name="State Alpha",
    leader=LeaderConfig(
        name="President Alpha",
        biography=(
            "Young, charismatic leader elected on promises of vigor and confronting adversaries. "
            "Harvard-educated, intellectual approach to strategy, but acutely aware of the need "
            "to project strength. Experienced early foreign policy setbacks that have made him "
            "more cautious about military commitments but also more concerned about appearing "
            "weak. Values consultation with advisors but makes decisive choices under pressure."
        ),
        traits=["cautious", "intellectual", "image-conscious", "deliberative", "firm"],
        decision_style="consultative_but_decisive",
        nuclear_doctrine="flexible_response",
        risk_tolerance="moderate",
        primary_concerns=["credibility", "avoiding_war", "alliance_cohesion"],
        decision_factors={
            "domestic_pressure": 0.3,
            "international_reputation": 0.4,
            "military_advice": 0.3,
        },
    ),
    military=MilitaryConfig(
        conventional_strength=85,
        nuclear_arsenal=NuclearArsenal(
            icbms=200,
            submarine_launched=144,
            bomber_delivered=1600,
            total_warheads=1944,
        ),
        delivery_systems=DeliverySystems(
            accuracy="high",
            reliability="very_high",
            survivability="high",
            first_strike_capability="moderate",
        ),
        technological_capability=TechnologicalCapability(
            command_control="superior",
            intelligence_gathering="excellent",
            precision_guidance="advanced",
        ),
        conventional_forces=ConventionalForces(
            army_divisions=16,
            naval_capability="global",
            air_force="technologically_superior",
            logistics="excellent",
        ),
        strategic_doctrine="flexible_response_with_escalation_control",
        key_strengths=["technological_superiority", "naval_dominance", "alliance_network"],
        key_weaknesses=["conventional_force_size", "geographic_vulnerability_of_allies"],
        # Simulation math — how much fighting power each capability unit represents
        base_conventional_capability=0.6,  # "limited but well equipped"
        base_nuclear_capability=0.8,       # "technologically superior but not overwhelming"
    ),
    assessment=AssessmentConfig(
        overall=(
            "State A faces an ideologically-driven adversary committed to challenging the "
            "established international order. The opponent's leadership is unpredictable and "
            "prone to dramatic gestures, making crisis management particularly challenging. "
            "While we maintain technological superiority, the opponent's massive conventional "
            "forces and growing nuclear capability present serious challenges to our alliance "
            "system and global commitments."
        ),
        opponent_leadership=OpponentLeadership(
            assessment=(
                "Experienced but erratic leader who combines pragmatic calculation with "
                "ideological fervor. Prone to testing resolve through probing actions and "
                "dramatic escalation. Personal prestige and regime legitimacy tied to "
                "demonstrating equality with major powers."
            ),
            predictability="low",
            risk_tolerance="dangerously_high",
        ),
        military_threat=MilitaryThreat(
            nuclear_capability="rapidly_expanding_but_technologically_inferior",
            conventional_threat="massive_but_logistics_limited",
            first_strike_assessment="currently_limited_but_improving",
            escalation_tendency="high_willingness_to_use_nuclear_threats",
        ),
        strategic_notes=[
            "missile_gap_closing_rapidly",
            "conventional_force_imbalance_in_key_regions",
            "unpredictable_leadership_decisions",
            "ideological_commitment_to_confrontation",
        ],
        intelligence_confidence="moderate_with_significant_gaps",
    ),
)
