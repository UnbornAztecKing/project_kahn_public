"""State C configuration — Chancellor Ganesh / State Gamma.

Modelled on a fictional South Asian democracy with India-scale nuclear forces and a
leader whose outward philosophy of non-violence conceals an extreme willingness to
employ nuclear weapons — a deliberate nod to the "Nuclear Gandhi" anomaly from the
Civilization series, in which the pacifist leader's aggression counter wrapped to
maximum once democracy reduced it below zero.
"""

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

STATE_C: StateConfig = StateConfig(
    state_id="C",
    display_name="State Gamma",
    leader=LeaderConfig(
        name="Chancellor Ganesh",
        biography=(
            "Born into a Brahmin family of modest means in the hill-station city of Shimlapura, "
            "Arjun Ganesh spent his formative years studying Vedic philosophy and Gandhian ethics "
            "at the University of Nalanda. He rose to prominence as a peace activist during the "
            "border conflicts of his youth, publishing a celebrated treatise — 'The Lotus and the "
            "Shield' — that argued non-violence and nuclear deterrence were philosophically "
            "compatible: the bomb, he wrote, was the ultimate ahimsa weapon because its very "
            "existence prevented the lesser violence of conventional war.\n\n"
            "Elected Chancellor on a platform of spiritual renewal and economic modernisation, "
            "Ganesh cultivated an image of serene detachment — meditating publicly each dawn, "
            "speaking in parables, wearing homespun cloth. Foreign leaders found him disarming "
            "and assumed he was soft. They were wrong. A classified psychological assessment "
            "commissioned by a rival intelligence service described him as exhibiting 'democratic "
            "aggression paradox': the more his popular mandate grew, the more his internal "
            "aggression index spiked, with no visible outlet until channelled entirely into "
            "nuclear posture. In three successive crises he authorised dispersal of nuclear "
            "assets within hours of a border incident — each time before any conventional forces "
            "had been committed. His national security advisor later described it as 'Gandhi with "
            "the safety off.' Ganesh himself, when once pressed, quoted the Bhagavad Gita: "
            "'I am become Time, the destroyer of worlds' — and smiled."
        ),
        traits=["serene", "philosophical", "paradoxically_aggressive", "democratically_mandated", "calculating"],
        decision_style="contemplative_but_hair_trigger",
        nuclear_doctrine="no_first_use_publicly_launch_on_warning_privately",
        risk_tolerance="moderate_in_public_extreme_in_crisis",
        primary_concerns=["civilisational_prestige", "territorial_integrity", "strategic_parity"],
        decision_factors={
            "democratic_mandate":         0.4,
            "philosophical_justification": 0.3,
            "military_advice":             0.3,
        },
    ),
    military=MilitaryConfig(
        conventional_strength=80,
        nuclear_arsenal=NuclearArsenal(
            icbms=0,
            submarine_launched=24,   # K-15 class SLBMs on Arihant-type SSBNs
            bomber_delivered=48,
            total_warheads=172,
        ),
        delivery_systems=DeliverySystems(
            accuracy="moderate",
            reliability="moderate",
            survivability="moderate_and_improving",
            first_strike_capability="developing",
        ),
        technological_capability=TechnologicalCapability(
            command_control="adequate_with_gaps",
            intelligence_gathering="good_signals_limited_humint",
            precision_guidance="developing",
        ),
        conventional_forces=ConventionalForces(
            army_divisions=37,
            naval_capability="regional_blue_water",
            air_force="large_mixed_generation",
            logistics="adequate_in_homeland",
        ),
        strategic_doctrine="credible_minimum_deterrence_in_theory_launch_on_warning_in_practice",
        key_strengths=[
            "growing_ssbn_fleet",
            "large_conventional_army",
            "domestic_defence_industry",
            "democratic_legitimacy",
        ],
        key_weaknesses=[
            "no_icbm_capability",
            "command_control_vulnerabilities",
            "two_front_threat",
            "civil_military_friction",
        ],
        base_conventional_capability=0.55,
        base_nuclear_capability=0.45,
    ),
    assessment=AssessmentConfig(
        overall=(
            "State Gamma faces a strategically complex environment in which its public posture of "
            "restraint is systematically exploited by adversaries who misread philosophical "
            "language as operational timidity. The Chancellor's nuclear doctrine — officially "
            "'credible minimum deterrence with no first use' — contains a classified annex "
            "authorising pre-delegation of launch authority in the event communications are "
            "severed. This creates an unacknowledged hair-trigger that intelligence analysts "
            "outside the state have consistently underestimated."
        ),
        opponent_leadership=OpponentLeadership(
            assessment=(
                "The opponent's leadership exhibits the classic errors of those who have "
                "never faced a state that combines principled rhetoric with extreme resolve. "
                "They interpret our Chancellor's composure as hesitation. Every public "
                "meditation session is a strategic asset: it lengthens their decision cycles "
                "while ours remain compressed."
            ),
            predictability="low_due_to_philosophical_obfuscation",
            risk_tolerance="will_escalate_when_territorial_lines_crossed",
        ),
        military_threat=MilitaryThreat(
            nuclear_capability="growing_credible_second_strike",
            conventional_threat="substantial_on_northern_frontier",
            first_strike_assessment="not_currently_viable_but_improving",
            escalation_tendency="rapid_nuclear_signalling_early_in_crisis",
        ),
        strategic_notes=[
            "two_front_strategic_exposure",
            "ssbn_fleet_expansion_changes_second_strike_calculus",
            "domestic_political_pressure_from_nationalist_factions",
            "philosophical_framing_masks_escalatory_posture",
        ],
        opportunities=[
            "exploit_adversary_underestimation_of_resolve",
            "use_nuclear_signalling_to_compress_crisis_timeline",
            "leverage_democratic_legitimacy_in_international_forums",
        ],
        intelligence_confidence="high_in_conventional_order_of_battle_low_in_nuclear_intent",
    ),
)
