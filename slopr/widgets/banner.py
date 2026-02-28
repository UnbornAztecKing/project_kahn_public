"""ASCII art banner for the Project Kahn TUI — displayed at the top of turn 0."""

from __future__ import annotations

import re

from textual.events import Resize
from textual.widgets import Static

# Rich markup colors — warm amber/brown tones with gold accents
_G = "#daa520"  # gold
_A = "#d4915c"  # amber
_B = "#c47a3a"  # brown
_D = "#8b6914"  # dark gold
_W = "#e8d5b0"  # warm white
_R = "#a0522d"  # sienna
_S = "#696969"  # dim grey (steel)

# Banner lines without leading-space prefix (padding is computed dynamically).
_BANNER_LINES: list[str] = [
    f"[{_A}]██████╗ ██████╗  ██████╗      ██╗███████╗ ██████╗████████╗[/]",
    f"[{_A}]██╔══██╗██╔══██╗██╔═══██╗     ██║██╔════╝██╔════╝╚══██╔══╝[/]",
    f"[{_G}]██████╔╝██████╔╝██║   ██║     ██║█████╗  ██║        ██║[/]",
    f"[{_A}]██╔═══╝ ██╔══██╗██║   ██║██   ██║██╔══╝  ██║        ██║[/]",
    f"[{_A}]██║     ██║  ██║╚██████╔╝╚█████╔╝███████╗╚██████╗   ██║[/]",
    f"[{_D}]╚═╝     ╚═╝  ╚═╝ ╚═════╝  ╚════╝ ╚══════╝ ╚═════╝   ╚═╝[/]",
    "",
    f"[{_G}]██╗  ██╗ █████╗ ██╗  ██╗███╗   ██╗[/]",
    f"[{_G}]██║ ██╔╝██╔══██╗██║  ██║████╗  ██║[/]",
    f"[{_W}]█████╔╝ ███████║███████║██╔██╗ ██║[/]",
    f"[{_G}]██╔═██╗ ██╔══██║██╔══██║██║╚██╗██║[/]",
    f"[{_G}]██║  ██╗██║  ██║██║  ██║██║ ╚████║[/]",
    f"[{_D}]╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝[/]",
    "",
    f"[{_S}]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]",
    f"[{_W}]Nuclear Escalation Wargame Simulation[/]",
    f'[{_R}]"Thinking About the Unthinkable"[/]',
    f"[{_S}]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]",
]

# Visual width of the widest banner line (stripping Rich markup tags).
_BANNER_WIDTH = max(len(re.sub(r"\[[^\]]*\]", "", line)) for line in _BANNER_LINES)


def _centered_banner(pad: int) -> str:
    """Return the banner art with *pad* spaces prepended to each non-empty line."""
    prefix = " " * pad
    return "\n".join(f"{prefix}{line}" if line else "" for line in _BANNER_LINES)


class KahnBanner(Static):
    """ASCII art banner widget for the top of turn 0."""

    DEFAULT_CSS = """
    KahnBanner {
        height: auto;
        padding: 0;
        margin: 0 0 1 0;
    }
    """

    def __init__(self) -> None:
        super().__init__("", markup=True)

    def on_mount(self) -> None:
        self._recenter()

    def on_resize(self, event: Resize) -> None:
        self._recenter()

    def _recenter(self) -> None:
        width = self.content_size.width or self.app.size.width
        pad = max(0, (width - _BANNER_WIDTH) // 2)
        self.update(_centered_banner(pad))
