"""Discover only explicitly supported feature modules present in this checkout."""

from importlib import import_module
from importlib.util import find_spec
from types import ModuleType

FEATURE_MODULES = {
    "signal_timeline": "app.signals.feature",
    "professor_aggregation": "app.professor.feature",
    "dropbox_integration": "app.dropbox.feature",
}


def installed_features(
    enabled_features: tuple[str, ...] | None = None,
) -> list[ModuleType]:
    """Return installed fixed-catalog modules; reject requested features that are absent."""
    names = enabled_features if enabled_features is not None else tuple(FEATURE_MODULES)
    modules = []
    for name in names:
        if name not in FEATURE_MODULES:
            raise ValueError("Unknown backend feature.")
        path = FEATURE_MODULES[name]
        if find_spec(path) is not None:
            modules.append(import_module(path))
        elif enabled_features is not None:
            raise ValueError("Requested backend feature is not present in this checkout.")
    return modules
