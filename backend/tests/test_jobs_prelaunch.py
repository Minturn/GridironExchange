from datetime import timedelta

from app import jobs
from app.db import utcnow


class _KeepOpen:
    """Yield the test session to a `with SessionLocal() as s:` block without closing it."""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *a):
        return False


def _wire(monkeypatch, session):
    calls = {"n": 0}
    monkeypatch.setattr(jobs, "SessionLocal", lambda: _KeepOpen(session))
    monkeypatch.setattr(jobs, "SleeperProvider", lambda: object())
    monkeypatch.setattr(jobs.sync_service, "sync_players", lambda s, p: calls.__setitem__("n", calls["n"] + 1) or 7)
    return calls


def _set_bell(session, league, minutes_ahead):
    raw = (utcnow() + timedelta(minutes=minutes_ahead)).isoformat()
    league.settings_json = {**(league.settings_json or {}), "market_opens_at": raw}
    session.commit()
    return raw


def test_prelaunch_sync_fires_once_inside_the_window(monkeypatch, session, league):
    calls = _wire(monkeypatch, session)
    raw = _set_bell(session, league, 30)  # bell in 30 min — inside the 60-min window

    jobs.job_prelaunch_sync()
    assert calls["n"] == 1
    assert (league.settings_json or {}).get("prelaunch_synced_for") == raw

    jobs.job_prelaunch_sync()  # already stamped for this bell → no re-sync
    assert calls["n"] == 1


def test_prelaunch_sync_skips_when_bell_is_far_off(monkeypatch, session, league):
    calls = _wire(monkeypatch, session)
    _set_bell(session, league, 180)  # 3 hours out — outside the window

    jobs.job_prelaunch_sync()
    assert calls["n"] == 0
    assert "prelaunch_synced_for" not in (league.settings_json or {})
