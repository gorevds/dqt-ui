"""Plugin API: third-party metrics that augment the per-feature summary.

Reserved keys
-------------

The following summary keys are produced by the built-in pipeline and
must not be overwritten by plugins; ``apply_plugins`` skips writes that
would shadow them and emits a warning:

* ``rate_range``, ``stability_mean``, ``stability_min``,
  ``psi_mean``, ``psi_max``.

Severity logic gates on these specific keys, so a plugin that
accidentally returned ``{"psi_max": 0}`` could silently mute a real
DRIFT verdict in CI. Reserve a namespace (``my_metric.<key>``) for
cross-cutting metrics if you need to.



Plugins are discovered through Python entry points under the
``dqt.metrics`` group. A plugin is anything with a ``compute(context) ->
dict`` callable; the returned dict is merged into the feature's summary
and shows up in the summary table and the HTML report.

Registering a plugin from a third-party package
-----------------------------------------------

In your package's ``pyproject.toml``::

    [project.entry-points."dqt.metrics"]
    iv_score = "my_pkg.metrics:IVMetric"

Then::

    # my_pkg/metrics.py
    from dqt.plugins import FeatureContext

    class IVMetric:
        name = "iv"

        def compute(self, ctx: FeatureContext) -> dict:
            iv_value = _compute_iv(ctx.bins_rate)
            return {"iv": iv_value}

DQT discovers the plugin on first analysis and calls ``IVMetric().compute(ctx)``
for every feature. Whatever the plugin returns is merged into the
per-feature summary (and therefore into the summary table and the
verdict text).

Programmatic registration (tests / one-offs)
--------------------------------------------

::

    from dqt.plugins import register_metric, FeatureContext
    register_metric(my_metric_instance)

The programmatic registry is consulted *before* entry points and is
useful when plugin discovery would slow down a unit test.
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Optional

import pandas as pd

from dqt.core.target_utils import TargetKind

_log = logging.getLogger(__name__)
_PROGRAMMATIC: List[Any] = []  # plugins registered via register_metric()
RESERVED_SUMMARY_KEYS = frozenset({
    "rate_range",
    "stability_mean",
    "stability_min",
    "psi_mean",
    "psi_max",
})


@dataclass(frozen=True)
class FeatureContext:
    """Inputs every plugin metric receives. Stable contract — backwards
    incompatible changes will be flagged in CHANGELOG."""

    df: pd.DataFrame
    feature: str
    time_col: str
    target_col: str
    target_kind: TargetKind
    is_numeric: bool
    bins_rate: pd.DataFrame  # output of bins_target_rate_over_time
    psi_table: pd.DataFrame  # output of psi_over_time


def register_metric(plugin: Any) -> None:
    """Register a plugin instance for the current process. Call from
    tests / notebooks. Cleared by ``unregister_all()``.
    """
    if not hasattr(plugin, "compute") or not callable(plugin.compute):
        raise TypeError(
            f"Plugin {plugin!r} must expose a compute(ctx) callable"
        )
    # Verify ``compute`` accepts a context argument — catches a common
    # typo (``def compute(self):``) at registration instead of mid-analysis.
    # On a bound method ``inspect.signature`` already drops ``self``, so an
    # empty parameter list means the plugin forgot the context parameter.
    try:
        sig = inspect.signature(plugin.compute)
        accepts_ctx = any(
            p.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.VAR_POSITIONAL,
            )
            for p in sig.parameters.values()
        )
    except (TypeError, ValueError):  # builtin-bound methods etc.
        accepts_ctx = True  # introspection failed, give the plugin the benefit of the doubt
    if not accepts_ctx:
        raise TypeError(
            f"Plugin {plugin!r}.compute must take a context argument"
        )
    _PROGRAMMATIC.append(plugin)


def unregister_all() -> None:
    """Drop all programmatically registered plugins. Tests use this."""
    _PROGRAMMATIC.clear()


def discover_metrics() -> List[Any]:
    """Return the list of metrics in invocation order: programmatic
    registrations first, then entry-point plugins under ``dqt.metrics``.
    """
    out: list = list(_PROGRAMMATIC)
    out.extend(_discover_entry_points())
    return out


def _discover_entry_points() -> List[Any]:
    try:
        from importlib.metadata import entry_points  # py3.10+ shape
    except ImportError:  # pragma: no cover
        return []
    eps: Iterable
    try:
        eps = entry_points(group="dqt.metrics")  # py3.10+
    except TypeError:  # pragma: no cover — py3.9 fallback
        eps = entry_points().get("dqt.metrics", [])
    out: list = []
    for ep in eps:
        try:
            cls = ep.load()
            instance = cls() if isinstance(cls, type) else cls
            if not hasattr(instance, "compute"):
                _log.warning("dqt.metrics plugin %s has no compute(); skipped", ep)
                continue
            out.append(instance)
        except Exception:  # noqa: BLE001 — broken plugin must not crash analyse
            _log.exception("could not load dqt.metrics plugin %s", ep)
    return out


def apply_plugins(
    metrics: List[Any],
    context: FeatureContext,
    summary: dict,
    on_error: Optional[Callable[[Any, BaseException], None]] = None,
) -> dict:
    """Run every plugin's ``compute(ctx)`` and merge the resulting dict
    into ``summary``. A failing plugin is logged and skipped — analysis
    must finish even if a third-party metric blows up.
    """
    for plugin in metrics:
        try:
            extra = plugin.compute(context)
        except Exception as exc:  # noqa: BLE001
            if on_error is not None:
                on_error(plugin, exc)
            _log.exception("plugin %r failed on feature %s",
                           plugin, context.feature)
            continue
        if not isinstance(extra, dict):
            _log.warning(
                "plugin %r returned %s, expected dict; skipped on feature %s",
                plugin, type(extra).__name__, context.feature,
            )
            continue
        # Plugins can introduce new keys but must not shadow reserved
        # ones — severity gating relies on the built-in values.
        for key, value in extra.items():
            skey = str(key)
            if skey in RESERVED_SUMMARY_KEYS:
                _log.warning(
                    "plugin %r tried to overwrite reserved summary key %r "
                    "on feature %s; ignored",
                    plugin, skey, context.feature,
                )
                continue
            summary[skey] = value
    return summary
