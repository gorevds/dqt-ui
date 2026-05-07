"""Tests for SessionStore — TTL eviction, LRU cap, disk persistence."""
from __future__ import annotations

import time

import pandas as pd
import pytest

from dqt.app.store import SessionStore


def _store(**kwargs) -> SessionStore:
    # No background sweeper in tests — we drive sweep() manually.
    kwargs.setdefault("start_sweeper", False)
    return SessionStore(**kwargs)


def test_create_and_get():
    s = _store()
    sess = s.create()
    assert sess.sid
    assert s.get(sess.sid) is sess
    assert s.get("missing") is None
    assert s.get(None) is None


def test_get_or_create_minted_when_unknown():
    s = _store()
    sess = s.get_or_create("nonexistent")
    assert sess.sid != "nonexistent"  # a fresh sid is minted, original is not adopted


def test_reset_replaces_session_in_place():
    s = _store()
    sess1 = s.create()
    sess1.df = pd.DataFrame({"x": [1, 2]})
    sess2 = s.reset(sess1.sid)
    assert sess2.sid == sess1.sid
    assert sess2.df is None  # state wiped
    assert s.get(sess1.sid) is sess2  # store updated


def test_ttl_eviction_via_sweep():
    s = _store(ttl_seconds=1)
    sess = s.create()
    sess.last_seen = time.time() - 100  # well past the TTL
    evicted = s.sweep()
    assert evicted == 1
    assert s.get(sess.sid) is None


def test_lru_cap_evicts_oldest_first():
    s = _store(max_sessions=2)
    a = s.create()
    b = s.create()
    s.create()  # adding the third must evict ``a``
    assert s.get(a.sid) is None
    assert s.get(b.sid) is not None


def test_get_promotes_recency_so_lru_cap_keeps_active_session():
    s = _store(max_sessions=2)
    a = s.create()
    b = s.create()
    # Touch ``a`` so it is now the more-recently-used; ``b`` becomes oldest.
    s.get(a.sid)
    s.create()  # third session evicts oldest = b
    assert s.get(a.sid) is not None
    assert s.get(b.sid) is None


def test_disk_persistence_round_trip(tmp_path):
    s = _store(persist_dir=str(tmp_path))
    sess = s.create()
    sess.df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    sess.filename = "input.csv"
    sess.columns_meta = {"time": "a", "target": "b", "features": []}
    sess.settings = {"max_bins": 5}
    s.save(sess)

    # New store points at the same dir → previous session re-emerges.
    s2 = _store(persist_dir=str(tmp_path))
    restored = s2.get(sess.sid)
    assert restored is not None
    assert restored.filename == "input.csv"
    assert restored.columns_meta["time"] == "a"
    assert restored.settings["max_bins"] == 5
    pd.testing.assert_frame_equal(restored.df, sess.df)


def test_disk_persistence_drops_stale_on_restore(tmp_path):
    s = _store(persist_dir=str(tmp_path), ttl_seconds=1)
    sess = s.create()
    sess.last_seen = time.time() - 100  # already past TTL
    s.save(sess)

    # Fresh store with the same TTL must NOT resurrect a stale session,
    # and should also clean up the on-disk artefacts.
    s2 = _store(persist_dir=str(tmp_path), ttl_seconds=1)
    assert s2.get(sess.sid) is None
    assert not (tmp_path / f"{sess.sid}.json").exists()
    assert not (tmp_path / f"{sess.sid}.parquet").exists()


def test_reset_deletes_disk_artefacts(tmp_path):
    s = _store(persist_dir=str(tmp_path))
    sess = s.create()
    sess.df = pd.DataFrame({"x": [1]})
    s.save(sess)
    assert (tmp_path / f"{sess.sid}.parquet").exists()

    s.reset(sess.sid)
    # Reset wipes content; new session's df is None so the parquet should be gone.
    assert not (tmp_path / f"{sess.sid}.parquet").exists()


@pytest.mark.parametrize("env_set", [False, True])
def test_env_dir_picked_up(monkeypatch, env_set, tmp_path):
    if env_set:
        monkeypatch.setenv("DQT_SESSION_DIR", str(tmp_path / "envdir"))
    else:
        monkeypatch.delenv("DQT_SESSION_DIR", raising=False)
    s = _store()
    if env_set:
        assert (tmp_path / "envdir").exists()
        assert s._persist_dir is not None
    else:
        assert s._persist_dir is None


def test_persist_handles_numpy_scalars(tmp_path):
    """Numpy ints/floats / pandas timestamps in settings must not break persistence."""
    import numpy as np

    s = _store(persist_dir=str(tmp_path))
    sess = s.create()
    sess.settings = {
        "max_bins": np.int64(7),
        "min_samples_leaf": np.float32(0.05),
        "stamp": pd.Timestamp("2026-01-01"),
    }
    s.save(sess)

    s2 = _store(persist_dir=str(tmp_path))
    restored = s2.get(sess.sid)
    assert restored is not None
    assert restored.settings["max_bins"] == 7
    assert abs(restored.settings["min_samples_leaf"] - 0.05) < 1e-6


def test_restore_ignores_unrelated_files(tmp_path):
    # Pollute the dir with an unrelated json — must not crash or be picked up.
    (tmp_path / "not-a-session.json").write_text("{}", encoding="utf-8")
    (tmp_path / "abc.json").write_text("{}", encoding="utf-8")

    s = _store(persist_dir=str(tmp_path))
    sess = s.create()
    sess.df = pd.DataFrame({"x": [1]})
    s.save(sess)

    s2 = _store(persist_dir=str(tmp_path))
    # Only the legitimate sid should be loaded.
    assert s2.get(sess.sid) is not None
    assert (tmp_path / "not-a-session.json").exists()  # unrelated file untouched


def test_stop_is_responsive(monkeypatch):
    """Calling stop() must release the sweeper thread quickly, not after 5 min."""
    import dqt.app.store as store_mod

    monkeypatch.setattr(store_mod, "_SWEEP_INTERVAL_S", 30)  # would otherwise be 300
    s = SessionStore(ttl_seconds=10, start_sweeper=True)
    try:
        assert s._sweeper is not None and s._sweeper.is_alive()
        s.stop()
        s._sweeper.join(timeout=2.0)
        assert not s._sweeper.is_alive(), "sweeper should exit promptly after stop()"
    finally:
        s.stop()
