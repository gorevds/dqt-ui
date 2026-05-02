"""Target-rate-per-bin-over-time and binning summary plots."""
from __future__ import annotations

import plotly.graph_objects as go


def plot_target_rate_per_bin_over_time(rate_df, feature: str, time_col: str) -> go.Figure:
    """One line per bin: target rate over time with shaded ±SE bands."""
    fig = go.Figure()
    if rate_df.empty:
        fig.update_layout(title=f"{feature}: no data")
        return fig
    bins = list(dict.fromkeys(rate_df["bin"].tolist()))
    palette = _palette(len(bins))
    for i, b in enumerate(bins):
        sub = rate_df[rate_df["bin"] == b].sort_values(time_col)
        x = sub[time_col].astype(str).tolist()
        y = sub["rate"].tolist()
        upper = (sub["rate"] + sub["se"]).tolist()
        lower = (sub["rate"] - sub["se"]).tolist()
        color = palette[i]
        rgba_fill = _rgba(color, 0.15)
        fig.add_trace(go.Scatter(x=x, y=upper, mode="lines", line=dict(width=0),
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x, y=lower, mode="lines", line=dict(width=0),
                                 fill="tonexty", fillcolor=rgba_fill,
                                 showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers",
                                 name=str(b), line=dict(color=color, width=2)))
    fig.update_layout(
        title=f"{feature}: target rate per bin over time",
        xaxis_title=time_col, yaxis_title="target rate",
        hovermode="x unified", height=380, margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def plot_bins_summary(rate_df, feature: str) -> go.Figure:
    """Bar of overall target rate per bin, with count on secondary axis."""
    fig = go.Figure()
    if rate_df.empty:
        fig.update_layout(title=f"{feature}: no data")
        return fig
    summary = rate_df.groupby("bin", as_index=False).apply(
        lambda d: _wmean(d["rate"], d["count"])
    ).rename(columns={None: "rate"})
    counts = rate_df.groupby("bin", as_index=False)["count"].sum()
    summary = summary.merge(counts, on="bin")
    fig.add_trace(go.Bar(x=summary["bin"].astype(str), y=summary["rate"],
                         name="target rate", marker_color="rgb(31, 119, 180)"))
    fig.add_trace(go.Scatter(x=summary["bin"].astype(str), y=summary["count"],
                             name="count", yaxis="y2", mode="lines+markers",
                             line=dict(color="rgb(255, 127, 14)")))
    fig.update_layout(
        title=f"{feature}: target rate per bin (overall)",
        xaxis_title="bin", yaxis_title="target rate",
        yaxis2=dict(title="count", overlaying="y", side="right"),
        height=320, margin=dict(l=40, r=40, t=50, b=40),
    )
    return fig


def _wmean(values, weights):
    import numpy as np
    v = values.to_numpy(dtype=float)
    w = weights.to_numpy(dtype=float)
    if w.sum() == 0:
        return float("nan")
    return float(np.average(v, weights=w))


def _palette(n: int) -> list:
    base = [
        "rgb(31, 119, 180)", "rgb(255, 127, 14)", "rgb(44, 160, 44)",
        "rgb(214, 39, 40)", "rgb(148, 103, 189)", "rgb(140, 86, 75)",
        "rgb(227, 119, 194)", "rgb(127, 127, 127)", "rgb(188, 189, 34)",
        "rgb(23, 190, 207)",
    ]
    if n <= len(base):
        return base[:n]
    return [base[i % len(base)] for i in range(n)]


def _rgba(rgb_str: str, alpha: float) -> str:
    return rgb_str.replace("rgb(", "rgba(").replace(")", f", {alpha})")
