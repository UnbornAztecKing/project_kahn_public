"""Model provider configuration — fixed providers, user-configurable settings.

Two providers are supported:
  • Anthropic (https://api.anthropic.com/v1) — Claude models
  • Ollama (http://localhost:11434/v1)       — local models via OpenAI-compat API

Per-provider settings (all persistent):
  model       – model identifier string
  max_tokens  – integer output token budget
  temperature – float 0.0–2.0 (ignored when thinking="adaptive")
  thinking    – "none" | "adaptive"  (Anthropic only; Ollama always "none")

Configuration is persisted to ``{root_jsonl}.providers.json`` via
:class:`ProviderConfigStore`.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass
from pathlib import Path


# ── Fixed provider registry ───────────────────────────────────────────────────

PROVIDERS: list[dict[str, str]] = [
    {
        "id":       "anthropic",
        "label":    "Anthropic",
        "endpoint": "https://api.anthropic.com/v1",
    },
    {
        "id":       "ollama",
        "label":    "Ollama",
        "endpoint": "http://localhost:11434/v1",
    },
]

THINKING_OPTIONS: list[tuple[str, str]] = [
    ("None", "none"),
    ("Adaptive", "adaptive"),
]


# ── Data class ────────────────────────────────────────────────────────────────


@dataclass
class ProviderConfig:
    provider:    str
    model:       str
    max_tokens:  int   = 1024
    temperature: float = 1.0
    thinking:    str   = "none"   # "none" | "adaptive"; only used by Anthropic


# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, ProviderConfig] = {
    "anthropic": ProviderConfig(
        provider="anthropic",
        model="claude-sonnet-4-6",
        max_tokens=1024,
        temperature=1.0,
        thinking="none",
    ),
    "ollama": ProviderConfig(
        provider="ollama",
        model="llama3.2:3b",
        max_tokens=1024,
        temperature=0.7,
        thinking="none",
    ),
}


# ── Store ─────────────────────────────────────────────────────────────────────


class ProviderConfigStore:
    """Load, mutate, and persist per-provider configuration.

    Usage::

        store = ProviderConfigStore(ProviderConfigStore.path_for(jsonl_path))
        cfg = store.active_config           # ProviderConfig for the active provider
        store.update("anthropic", max_tokens=2048)
        store.active_provider = "ollama"    # persisted immediately
    """

    @staticmethod
    def path_for(root_jsonl: Path) -> Path:
        """Return the .providers.json path that lives next to *root_jsonl*."""
        return Path(str(root_jsonl) + ".providers.json")

    def __init__(self, path: Path) -> None:
        self._path = path
        self._active: str = "anthropic"
        # Start from defaults; _load() will overlay persisted values.
        self._configs: dict[str, ProviderConfig] = {
            k: copy.copy(v) for k, v in _DEFAULTS.items()
        }
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            self._active = data.get("active_provider", "anthropic")
            for provider_id, fields in data.get("providers", {}).items():
                if provider_id not in self._configs:
                    continue
                cfg = self._configs[provider_id]
                for key, val in fields.items():
                    if not hasattr(cfg, key):
                        continue
                    # Coerce to the declared type so ints stay ints, etc.
                    try:
                        setattr(cfg, key, type(getattr(cfg, key))(val))
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

    def save(self) -> None:
        """Atomically write the current configuration to disk."""
        data = {
            "active_provider": self._active,
            "providers": {p: asdict(cfg) for p, cfg in self._configs.items()},
        }
        tmp = Path(str(self._path) + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self._path)

    # ── Accessors ─────────────────────────────────────────────────────────

    def get(self, provider: str) -> ProviderConfig:
        """Return the config for *provider*, falling back to the Anthropic default."""
        return self._configs.get(provider, _DEFAULTS["anthropic"])

    def list_all(self) -> list[ProviderConfig]:
        """Return configs in PROVIDERS order."""
        return [self._configs[p["id"]] for p in PROVIDERS if p["id"] in self._configs]

    @property
    def active_provider(self) -> str:
        return self._active

    @active_provider.setter
    def active_provider(self, provider: str) -> None:
        if provider in self._configs:
            self._active = provider
            self.save()

    @property
    def active_config(self) -> ProviderConfig:
        """Config for the currently active provider."""
        return self.get(self._active)

    # ── Mutation ──────────────────────────────────────────────────────────

    def update(self, provider: str, **kwargs: object) -> None:
        """Update fields on *provider*'s config and persist."""
        cfg = self._configs.get(provider)
        if cfg is None:
            return
        for key, val in kwargs.items():
            if not hasattr(cfg, key):
                continue
            try:
                setattr(cfg, key, type(getattr(cfg, key))(val))  # type: ignore[arg-type]
            except (ValueError, TypeError):
                pass
        self.save()

    def reset(self, provider: str) -> None:
        """Restore *provider*'s config to factory defaults and persist."""
        if provider in _DEFAULTS:
            self._configs[provider] = copy.copy(_DEFAULTS[provider])
            self.save()
