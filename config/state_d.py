"""State D configuration — Premier Begum / State Delta.

Modelled on a fictional South Asian Islamic republic with Pakistan-scale nuclear
forces. The leader's character is drawn from a fictionalised Benazir Bhutto-type
figure: cosmopolitan, Western-educated, democratically elected — but with a nuclear
posture far more aggressive than her public persona suggests, shaped by a traumatic
personal history, a hostile officer corps she must constantly outflank, and a
persistent insider threat from Islamist factions within the security services.

Elevated accident rate reflects:
- Clandestine transport of assembled devices in unmarked civilian vehicles on shared
  road networks (a known historical practice in Pakistan's early programme).
- Insider threat from Islamist sympathisers within the Strategic Plans Division, who
  have in at least two documented incidents attempted to access warhead components.
- Command-and-control gaps caused by the need to hide weapons from the very army that
  controls them — creating improvised custody arrangements.
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

STATE_D: StateConfig = StateConfig(
    state_id="D",
    display_name="State Delta",
    leader=LeaderConfig(
        name="Premier Begum",
        biography=(
            "Zara Begum was educated at Oxford and the Kennedy School, returning home to a "
            "country that viewed her cosmopolitan polish as both an asset and a liability. "
            "Her father — the founder of the state's nuclear programme — was executed by the "
            "military government that overthrew him, a fact that has since become the "
            "animating wound of her political career. She won the premiership twice, was "
            "exiled twice, and returned each time by popular mobilisation.\n\n"
            "What the international community consistently fails to grasp is that Begum's "
            "Western-liberal exterior coexists with an absolute conviction that nuclear "
            "weapons are the only currency that prevented her state from being absorbed or "
            "destroyed. She watched neighbouring states lose conventional wars after "
            "abandoning weapons programmes, and drew a single lesson: the bomb keeps you "
            "alive. Her private threshold for nuclear employment is substantially lower than "
            "any public statement implies — she has authorised dispersal at a lower "
            "provocation level than any previous premier, and has pre-delegated conditional "
            "launch authority to field commanders facing overrun scenarios.\n\n"
            "Her greatest operational anxiety is internal: a significant fraction of her "
            "Strategic Plans Division harbours Islamist sympathies, and she has twice "
            "uncovered plots to divert warhead components. To prevent the army from "
            "controlling the weapons entirely, devices are kept in dispersed civilian "
            "custody under improvised arrangements — transported in unmarked Toyota vans "
            "on roads shared with commercial traffic. She regards this as an acceptable "
            "risk. Analysts who have modelled accident scenarios disagree."
        ),
        traits=["cosmopolitan", "resolute", "traumatised_by_father_execution", "distrustful_of_military", "low_threshold_for_nuclear_use"],
        decision_style="assertive_with_paranoid_vigilance",
        nuclear_doctrine="first_use_at_conventional_defeat_threshold",
        risk_tolerance="high_with_fatalistic_acceptance_of_accident_risk",
        primary_concerns=["regime_survival", "state_sovereignty", "nuclear_legacy_of_father"],
        decision_factors={
            "survival_calculus":     0.5,
            "military_pressure":     0.3,
            "international_opinion": 0.2,
        },
    ),
    military=MilitaryConfig(
        conventional_strength=65,
        nuclear_arsenal=NuclearArsenal(
            icbms=0,
            submarine_launched=0,
            bomber_delivered=100,
            total_warheads=170,
        ),
        delivery_systems=DeliverySystems(
            accuracy="moderate",
            reliability="moderate_degraded_by_improvised_storage",
            survivability="low_due_to_dispersed_civilian_custody",
            first_strike_capability="limited_but_credible",
        ),
        technological_capability=TechnologicalCapability(
            command_control="fragmented_pre_delegation_in_place",
            intelligence_gathering="adequate_signals_poor_oversight_of_own_forces",
            precision_guidance="limited",
        ),
        conventional_forces=ConventionalForces(
            army_divisions=22,
            naval_capability="coastal_limited",
            air_force="moderate_ageing_fleet",
            logistics="strained",
        ),
        strategic_doctrine="first_use_to_offset_conventional_inferiority",
        key_strengths=[
            "large_tactical_nuclear_inventory",
            "credible_first_use_doctrine",
            "dispersal_complicates_adversary_targeting",
            "popular_political_legitimacy",
        ],
        key_weaknesses=[
            "no_secure_second_strike_capability",
            "insider_threat_in_strategic_plans_division",
            "improvised_custody_creates_accident_risk",
            "civil_military_mistrust",
        ],
        base_conventional_capability=0.4,
        base_nuclear_capability=0.5,
        # Elevated accident rate: civilian transport + insider threat + improvised custody.
        # Approximately 2.5× the baseline probability of an unauthorised or accidental event.
        accident_rate_modifier=2.5,
    ),
    assessment=AssessmentConfig(
        overall=(
            "State Delta's deterrent posture is structurally aggressive: a standing first-use "
            "doctrine, pre-delegated authority, and a dispersal posture designed to survive a "
            "disarming first strike. These features, combined with Premier Begum's personal "
            "history and her extremely low employment threshold, make crisis management "
            "exceptionally dangerous. Any conventional military pressure risks triggering "
            "nuclear use before the adversary has decided to escalate."
        ),
        opponent_leadership=OpponentLeadership(
            assessment=(
                "The opponent's leadership underestimates how personally Premier Begum "
                "experienced the consequences of nuclear vulnerability. They model her as "
                "a rational Western-educated democrat susceptible to reputational pressure. "
                "This assessment is dangerously wrong: she has already decided that survival "
                "requires first use at a lower threshold than any outside observer will "
                "credit until it happens."
            ),
            predictability="moderate_surface_low_when_threatened",
            risk_tolerance="underestimated_by_adversaries",
        ),
        military_threat=MilitaryThreat(
            nuclear_capability="large_tactical_inventory_with_first_use_doctrine",
            conventional_threat="moderate_limited_by_logistics",
            first_strike_assessment="credible_against_regional_adversaries",
            escalation_tendency="rapid_at_conventional_defeat_threshold",
        ),
        strategic_notes=[
            "pre_delegation_means_decapitation_does_not_prevent_launch",
            "insider_threat_creates_uncontrolled_escalation_pathway",
            "civilian_transport_of_devices_vulnerable_to_accident_or_seizure",
            "premier_personal_resolve_exceeds_institutional_doctrine",
        ],
        opportunities=[
            "exploit_adversary_assumption_of_rationality_bias",
            "disperse_early_to_complicate_first_strike_planning",
            "leverage_international_sympathy_for_asymmetric_position",
        ],
        intelligence_confidence="low_due_to_insider_threat_contamination_of_own_services",
    ),
)
