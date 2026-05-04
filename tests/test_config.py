import json

from dqt.config import DEFAULT, Config, Thresholds, severity_for


def test_defaults():
    t = DEFAULT.thresholds
    assert t.psi_red == 0.25
    assert t.psi_yellow == 0.10
    assert t.stability_red == 0.60
    assert t.missing_red == 0.50


def test_severity_red_when_psi_high():
    assert severity_for(psi_max=0.4, stability_min=1.0, missing_max=0.0) == "red"


def test_severity_yellow_when_psi_mid():
    assert severity_for(psi_max=0.15, stability_min=1.0, missing_max=0.0) == "yellow"


def test_severity_green_when_clean():
    assert severity_for(psi_max=0.05, stability_min=0.95, missing_max=0.05) == "green"


def test_severity_red_via_stability():
    assert severity_for(psi_max=0.0, stability_min=0.4, missing_max=0.0) == "red"


def test_severity_red_via_missing():
    assert severity_for(psi_max=0.0, stability_min=1.0, missing_max=0.7) == "red"


def test_severity_handles_none():
    # NaN / None values shouldn't crash and shouldn't trigger thresholds.
    assert severity_for(psi_max=None, stability_min=None, missing_max=0.0) == "green"
    assert severity_for(psi_max=float("nan"), stability_min=1.0, missing_max=0.0) == "green"


def test_per_feature_override(tmp_path):
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps({
        "thresholds": {"psi_yellow": 0.10, "psi_red": 0.25},
        "per_feature": {
            "tight_feature": {"psi_yellow": 0.03, "psi_red": 0.08},
        },
    }))
    cfg = Config.load(cfg_path)
    # Default for an unknown feature.
    default = cfg.for_feature("any_other")
    assert isinstance(default, Thresholds)
    assert default.psi_red == 0.25
    # Override applies for the specific feature.
    tight = cfg.for_feature("tight_feature")
    assert tight.psi_red == 0.08
    assert severity_for(psi_max=0.10, stability_min=1.0, missing_max=0.0,
                          thresholds=tight) == "red"
    assert severity_for(psi_max=0.10, stability_min=1.0, missing_max=0.0,
                          thresholds=default) == "yellow"


def test_load_returns_default_when_missing(tmp_path):
    cfg = Config.load(tmp_path / "nonexistent.yaml")
    assert cfg.thresholds.psi_red == 0.25
