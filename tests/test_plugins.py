"""Tests for the dqt.plugins API."""
from __future__ import annotations

import pytest

from dqt.plugins import (
    FeatureContext,
    apply_plugins,
    discover_metrics,
    register_metric,
    unregister_all,
)


@pytest.fixture(autouse=True)
def _clean_plugins():
    unregister_all()
    yield
    unregister_all()


class _IVStub:
    name = "iv"

    def compute(self, ctx: FeatureContext) -> dict:
        # Trivial IV-style stand-in: bin spread of rates.
        rates = ctx.bins_rate["rate"]
        return {"iv": float(rates.max() - rates.min())}


def test_register_metric_round_trip():
    register_metric(_IVStub())
    found = discover_metrics()
    assert any(isinstance(m, _IVStub) for m in found)


def test_register_metric_rejects_bad_object():
    with pytest.raises(TypeError, match="compute"):
        register_metric(object())


def test_register_metric_rejects_zero_arg_compute():
    class _ZeroArg:
        def compute(self):  # missing ctx parameter
            return {}

    with pytest.raises(TypeError, match="context argument"):
        register_metric(_ZeroArg())


def test_apply_plugins_skips_reserved_keys(binary_df):
    import pandas as pd

    from dqt.core.target_utils import TargetKind

    class _Bad:
        def compute(self, ctx):
            # Plugin tries to mute a real DRIFT verdict — must not work.
            return {"psi_max": 0.0, "iv": 0.42}

    rate = pd.DataFrame({"m": ["1", "2"], "bin": ["a", "a"], "rate": [0.1, 0.1],
                         "count": [100, 100], "se": [0.01, 0.01]})
    ctx = FeatureContext(
        df=binary_df, feature="x_num", time_col="m",
        target_col="target", target_kind=TargetKind.BINARY,
        is_numeric=True, bins_rate=rate, psi_table=pd.DataFrame(),
    )
    summary = {"psi_max": 0.5, "rate_range": 0.2}  # built-in values
    apply_plugins([_Bad()], ctx, summary)
    assert summary["psi_max"] == 0.5  # NOT overwritten by plugin's 0.0
    assert summary["iv"] == 0.42      # non-reserved key allowed


def test_apply_plugins_merges_into_summary(binary_df):
    import pandas as pd

    from dqt.core.quality import bins_target_rate_over_time, psi_over_time
    from dqt.core.target_utils import TargetKind

    df = binary_df.copy()
    df["m"] = df["date"].dt.to_period("M").astype(str)
    df["bin"] = pd.cut(df["x_num"].fillna(0), bins=3).astype(str)
    rate = bins_target_rate_over_time(df, "bin", "target", "m", TargetKind.BINARY)
    psi_t = psi_over_time(df, "x_num", "m")

    ctx = FeatureContext(
        df=df, feature="x_num", time_col="m",
        target_col="target", target_kind=TargetKind.BINARY,
        is_numeric=True, bins_rate=rate, psi_table=psi_t,
    )
    summary: dict = {}
    apply_plugins([_IVStub()], ctx, summary)
    assert "iv" in summary
    assert summary["iv"] >= 0


def test_apply_plugins_swallows_failure(binary_df):
    import pandas as pd

    from dqt.core.target_utils import TargetKind

    class _Broken:
        def compute(self, ctx):
            raise RuntimeError("kaboom")

    ctx = FeatureContext(
        df=binary_df, feature="x_num", time_col="date",
        target_col="target", target_kind=TargetKind.BINARY,
        is_numeric=True, bins_rate=pd.DataFrame(),
        psi_table=pd.DataFrame(),
    )
    summary = {"existing": 1}
    apply_plugins([_Broken()], ctx, summary)
    assert summary == {"existing": 1}  # broken plugin contributed nothing


def test_apply_plugins_ignores_non_dict_return(binary_df):
    import pandas as pd

    from dqt.core.target_utils import TargetKind

    class _BadReturn:
        def compute(self, ctx):
            return 42  # not a dict

    ctx = FeatureContext(
        df=binary_df, feature="x_num", time_col="date",
        target_col="target", target_kind=TargetKind.BINARY,
        is_numeric=True, bins_rate=pd.DataFrame(),
        psi_table=pd.DataFrame(),
    )
    summary = {"existing": 1}
    apply_plugins([_BadReturn()], ctx, summary)
    assert summary == {"existing": 1}


def test_pipeline_picks_up_registered_plugin(binary_df):
    """End-to-end: register a plugin, run analysis, see the new key."""
    register_metric(_IVStub())
    from dqt.app.pipeline import run_analysis

    result = run_analysis(
        df=binary_df.head(800), time_col="date", target_col="target",
        features=["x_num"], feature_kinds={"x_num": "numeric"},
        granularity="month",
    )
    summary = result["features"][0]["summary"]
    assert "iv" in summary
    summary_table_cols = result["summary_table"].columns.tolist()
    assert "iv" in summary_table_cols
