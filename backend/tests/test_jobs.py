import sqlite3

from app import jobs


def test_db_backup_creates_valid_snapshot(tmp_path, monkeypatch):
    db = tmp_path / "gridx.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (42)")
    con.commit()
    con.close()

    monkeypatch.setattr(jobs.settings, "database_url", f"sqlite:///{db}")
    jobs.job_backup_db()

    backups = list((tmp_path / "backups").glob("gridx-*.db"))
    assert len(backups) == 1
    b = sqlite3.connect(backups[0])
    assert b.execute("SELECT x FROM t").fetchone()[0] == 42  # real copy of the data
    b.close()


def test_db_backup_noop_for_non_sqlite(monkeypatch):
    monkeypatch.setattr(jobs.settings, "database_url", "postgresql+psycopg2://x/y")
    jobs.job_backup_db()  # must just return, never raise
