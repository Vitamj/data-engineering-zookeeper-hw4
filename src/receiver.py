import json
import sqlite3
from pathlib import Path


class BadVersionError(Exception):
    pass


class ResultReceiver:
    def __init__(self, path, fenced):
        self.path = Path(path)
        self.fenced = fenced
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS receiver (id INTEGER PRIMARY KEY CHECK(id=1), active_epoch INTEGER NOT NULL, pointer_version INTEGER NOT NULL, payload TEXT)")
            db.execute("INSERT OR IGNORE INTO receiver(id, active_epoch, pointer_version, payload) VALUES(1, 0, 0, NULL)")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level="IMMEDIATE")
        db.row_factory = sqlite3.Row
        return db

    def reset(self):
        with self._connect() as db:
            db.execute("UPDATE receiver SET active_epoch=0, pointer_version=0, payload=NULL WHERE id=1")

    def activate(self, epoch):
        with self._connect() as db:
            db.execute("UPDATE receiver SET active_epoch=MAX(active_epoch, ?) WHERE id=1", (epoch,))

    def publish(self, epoch, payload):
        with self._connect() as db:
            row = db.execute("SELECT active_epoch, pointer_version FROM receiver WHERE id=1").fetchone()
            if self.fenced and epoch != row["active_epoch"]:
                raise BadVersionError(f"BadVersionError: request epoch={epoch}, active_epoch={row['active_epoch']}")
            version = row["pointer_version"] + 1
            db.execute("UPDATE receiver SET pointer_version=?, payload=? WHERE id=1", (version, json.dumps(payload, ensure_ascii=False, separators=(",", ":"))))
            return version

    def snapshot(self):
        with self._connect() as db:
            row = db.execute("SELECT active_epoch, pointer_version, payload FROM receiver WHERE id=1").fetchone()
            return {"active_epoch": row["active_epoch"], "pointer_version": row["pointer_version"], "payload": json.loads(row["payload"]) if row["payload"] else None}
