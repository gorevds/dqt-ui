"""Feature distribution plots over time."""
from __future__ import annotations

import plotly.graph_objects as go


def plot_numeric_distribution_over_time(dist_df, feature: str, time_col: str) -> go.Figure:
    """Quantile bands (5/25/50/75/95) over time for a numeric feature."""
    fig = go.Figure()
    if dist_df.empty:
        fig.update_layout(title=f"{feature}: no data")
        return fig
    x = dist_df[time_col].astype(str).tolist()
    fig.add_trace(go.Scatter(x=x, y=dist_df["q95"], mode="lines", name="q95", line=dict(width=0)))
    fig.add_trace(go.Scatter(x=x, y=dist_df["q5"], mode="lines", name="q5", fill="tonexty",
                             fillcolor="rgba(31, 119, 180, 0.15)", line=dict(width=0)))
    fig.add_trace(go.Scatter(x=x, y=dist_df["q75"], mode="lines", name="q75", line=dict(width=0)))
    fig.add_trace(go.Scatter(x=x, y=dist_df["q25"], mode="lines", name="q25", fill="tonexty",
                             fillcolor="rgba(31, 119, 180, 0.30)", line=dict(width=0)))
    fig.add_trace(go.Scatter(x=x, y=dist_df["q50"], mode="lines+markers", name="median",
                             line=dict(color="rgb(31, 119, 180)", width=2)))
    fig.update_layout(
        title=f"{feature}: distribution over time (quantile bands)",
        xaxis_title=time_col, yaxis_title=feature,
        hovermode="x unified", height=350, margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def plot_categorical_share_over_time(share_df, feature: str, time_col: str) -> go.Figure:
    """Stacked share of top-k categories per time bucket."""
    fig = go.Figure()
    if share_df.empty:
        fig.update_layout(title=f"{feature}: no data")
        return fig
    pivot = share_df.pivot_table(index=time_col, columns="category", values="share", fill_value=0)
    pivot = pivot.sort_index()
    for col in pivot.columns:
        fig.add_trace(go.Bar(x=pivot.index.astype(str), y=pivot[col], name=str(col)))
    fig.update_layout(
        barmode="stack",
        title=f"{feature}: category share over time",
        xaxis_title=time_col, yaxis_title="share",
        height=350, margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig
