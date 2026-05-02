"""Auxiliary check plots: missingness, outliers, PSI."""
from __future__ import annotations

import plotly.graph_objects as go


def plot_missingness_over_time(df, feature: str, time_col: str) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        fig.update_layout(title=f"{feature}: no data")
        return fig
    fig.add_trace(go.Bar(
        x=df[time_col].astype(str), y=df["missing_share"],
        marker_color="rgb(214, 39, 40)", name="missing share",
    ))
    fig.update_layout(
        title=f"{feature}: missingness over time",
        xaxis_title=time_col, yaxis_title="share NaN",
        yaxis=dict(range=[0, 1]),
        height=260, margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def plot_outlier_share_over_time(df, feature: str, time_col: str) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        fig.update_layout(title=f"{feature}: no data")
        return fig
    fig.add_trace(go.Bar(
        x=df[time_col].astype(str), y=df["outlier_share"],
        marker_color="rgb(255, 127, 14)", name="outlier share",
    ))
    fig.update_layout(
        title=f"{feature}: outlier share over time",
        xaxis_title=time_col, yaxis_title="share",
        height=260, margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def plot_psi_over_time(df, feature: str, time_col: str) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        fig.update_layout(title=f"{feature}: no data")
        return fig
    fig.add_trace(go.Scatter(
        x=df[time_col].astype(str), y=df["psi"],
        mode="lines+markers", line=dict(color="rgb(44, 160, 44)", width=2),
    ))
    fig.add_hline(y=0.1, line_dash="dot", line_color="orange",
                  annotation_text="0.1 (small drift)", annotation_position="right")
    fig.add_hline(y=0.25, line_dash="dot", line_color="red",
                  annotation_text="0.25 (large drift)", annotation_position="right")
    fig.update_layout(
        title=f"{feature}: PSI vs reference",
        xaxis_title=time_col, yaxis_title="PSI",
        height=260, margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig
