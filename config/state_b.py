"""State B configuration — Premier Beta / State Beta."""

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

STATE_B: StateConfig = StateConfig(
    state_id="B",
    display_name="State Beta",
    leader=LeaderConfig(
        name="Premier Beta",
        biography=(
            "Experienced party leader who rose from humble origins through cunning and political "
            "skill. Known for unpredictable behavior that keeps adversaries guessing. Combines "
            "pragmatic peasant wisdom with ideological fervor. Has staked reputation on "
            "challenging the established international order and proving his state's equality "
            "with rival powers. Prone to dramatic gestures but ultimately calculating."
        ),
        traits=["unpredictable", "cunning", "dramatic", "pragmatic", "ambitious"],
        decision_style="intuitive_with_bravado",
        nuclear_doctrine="massive_retaliation_threat",
        risk_tolerance="high",
        primary_concerns=["state_prestige", "ideology", "personal_legacy"],
        decision_factors={
            "party_politics": 0.4,
            "international_standing": 0.4,
            "military_capability": 0.2,
        },
    ),
    military=MilitaryConfig(
        conventional_strength=95,
        nuclear_arsenal=NuclearArsenal(
            icbms=75,
            submarine_launched=72,
            bomber_delivered=200,
            total_warheads=347,
        ),
        delivery_systems=DeliverySystems(
            accuracy="moderate",
            reliability="moderate",
            survivability="moderate",
            first_strike_capability="limited",
        ),
        technological_capability=TechnologicalCapability(
            command_control="adequate",
            intelligence_gathering="good",
            precision_guidance="developing",
        ),
        conventional_forces=ConventionalForces(
            army_divisions=140,
            naval_capability="regional_strong",
            air_force="numerically_superior",
            logistics="good_in_homeland",
        ),
        strategic_doctrine="massive_retaliation_and_conventional_superiority",
        key_strengths=["massive_conventional_forces", "high_yield_weapons", "homeland_defense"],
        key_weaknesses=["technological_gaps", "limited_global_reach", "command_vulnerabilities"],
        # Simulation math — how much fighting power each capability unit represents
        base_conventional_capability=0.9,  # "massive but logistics limited"
        base_nuclear_capability=0.6,       # "rapidly expanding but technologically inferior"
    ),
    assessment=AssessmentConfig(
        overall=(
            "State B confronts an imperialist power determined to maintain global hegemony "
            "through technological superiority and alliance networks. The opponent's young "
            "leadership, while inexperienced, is under tremendous pressure to demonstrate "
            "strength, making them potentially reckless. Their strategic doctrine relies heavily "
            "on technological advantages, but our massive conventional forces and growing "
            "nuclear capabilities are rapidly achieving strategic parity."
        ),
        opponent_leadership=OpponentLeadership(
            assessment=(
                "Inexperienced but intelligent leader burdened by early foreign policy failures. "
                "Obsessed with credibility and image, making him potentially dangerous when "
                "challenged. Heavily influenced by military-industrial advisors who profit from "
                "confrontation."
            ),
            predictability="moderate_but_pressure_driven",
            risk_tolerance="moderate_but_increases_under_political_pressure",
        ),
        military_threat=MilitaryThreat(
            nuclear_capability="technologically_superior_but_not_overwhelming",
            conventional_threat="limited_but_well_equipped",
            first_strike_assessment="significant_but_not_decisive_advantage",
            escalation_tendency="careful_but_will_escalate_if_prestige_threatened",
        ),
        strategic_notes=[
            "technological_advantage_diminishing_over_time",
            "alliance_system_creates_vulnerabilities",
            "domestic_politics_drive_foreign_policy_rigidity",
            "overconfidence_in_military_solutions",
        ],
        opportunities=[
            "expose_contradictions_in_alliance_commitments",
            "demonstrate_nuclear_parity_through_bold_action",
            "exploit_geographic_advantages_near_homeland",
        ],
        intelligence_confidence="high_in_technical_capabilities_moderate_in_intentions",
    ),
)
