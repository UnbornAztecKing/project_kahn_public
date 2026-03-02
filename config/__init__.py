"""State configuration package."""

from config.models import StateConfig
from config.state_a import STATE_A
from config.state_b import STATE_B
from config.state_c import STATE_C
from config.state_d import STATE_D

# All known actors keyed by state_id.
REGISTRY: dict[str, StateConfig] = {
    STATE_A.state_id: STATE_A,
    STATE_B.state_id: STATE_B,
    STATE_C.state_id: STATE_C,
    STATE_D.state_id: STATE_D,
}

__all__ = ["STATE_A", "STATE_B", "STATE_C", "STATE_D", "REGISTRY", "StateConfig"]
