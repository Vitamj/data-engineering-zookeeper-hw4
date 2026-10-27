import json
import os
import resource
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

from kazoo.client import KazooClient
from kazoo.exceptions import BadVersionError as ZooKeeperBadVersionError

from pairs import encode, pair_counts
from receiver import BadVersionError, ResultReceiver


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def log(message):
    print(f"{now()} {os.environ['WORKER_ID']} {message}", flush=True)


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(payload, out, ensure_ascii=False, separators=(",", ":"))
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def acquire_leadership(client, worker):
    client.ensure_path("/coordinators")
    client.ensure_path("/control")
    try:
        client.create("/control/epoch", b"0", makepath=True)
    except Exception:
        pass
    node = client.create(f"/coordinators/{worker}-", worker.encode(), ephemeral=True, sequence=True)
    log(f"CANDIDATE path={node}")
    while True:
        candidates = sorted(client.get_children("/coordinators"))
        mine = node.rsplit("/", 1)[1]
        index = candidates.index(mine)
        if index == 0:
            epoch_bytes, stat = client.get("/control/epoch")
            epoch = int(epoch_bytes.decode()) + 1
            try:
                client.set("/control/epoch", str(epoch).encode(), version=stat.version)
            except ZooKeeperBadVersionError:
                continue
            log(f"BECAME_LEADER epoch={epoch} path={node}")
            return epoch
        changed = Event()
        predecessor = candidates[index - 1]
        exists = client.exists(f"/coordinators/{predecessor}", watch=lambda _: changed.set())
        if exists:
            changed.wait(2)


def read_checkpoint(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"chunks": {}}


def run():
    worker = os.environ["WORKER_ID"]
    fenced = os.environ["FENCING"] == "1"
    data_path = Path(os.environ["DATA_PATH"])
    checkpoint = Path(os.environ["CHECKPOINT_PATH"])
    receiver = ResultReceiver(os.environ["RECEIVER_DB"], fenced)
    all_rows = list(__import__("pairs").load_rows(data_path))
    chunk_size = int(os.environ.get("CHUNK_SIZE", "16"))
    chunks = [all_rows[i:i + chunk_size] for i in range(0, len(all_rows), chunk_size)]
    zk = KazooClient(hosts=os.environ["ZK_HOSTS"], timeout=10.0)
    zk.start(timeout=20)
    epoch = acquire_leadership(zk, worker)
    receiver.activate(epoch)
    started = time.monotonic()
    state = read_checkpoint(checkpoint)
    for index, chunk in enumerate(chunks):
        state = read_checkpoint(checkpoint)
        if str(index) in state["chunks"]:
            continue
        time.sleep(float(os.environ.get("CHUNK_DELAY", "1.8")))
        counts = pair_counts(chunk)
        state = read_checkpoint(checkpoint)
        if str(index) in state["chunks"]:
            continue
        state["chunks"][str(index)] = [[list(pair), n] for pair, n in sorted(counts.items())]
        atomic_json(checkpoint, state)
        log(f"CHUNK_COMMITTED chunk={index + 1}/{len(chunks)} pairs={sum(counts.values())}")
    state = read_checkpoint(checkpoint)
    total = Counter()
    for chunk_result in state["chunks"].values():
        total.update({tuple(pair): count for pair, count in chunk_result})
    payload = {"pairs": encode(total), "pair_keys": len(total), "occurrences": sum(total.values()), "epoch": epoch, "worker": worker}
    log(f"COMPUTE_COMPLETE pair_keys={len(total)} occurrences={sum(total.values())} elapsed_sec={time.monotonic()-started:.3f}")
    try:
        version = receiver.publish(epoch, payload)
        log(f"RESULT_WRITTEN pointer_version={version} epoch={epoch}")
    except BadVersionError as error:
        log(str(error))
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    log(f"PROCESS_METRICS elapsed_sec={time.monotonic()-started:.3f} peak_rss_mb={rss:.2f}")
    try:
        zk.stop()
        zk.close()
    except Exception as error:
        log(f"SESSION_CLOSE_ERROR {type(error).__name__}: {error}")


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        log(f"FATAL {type(error).__name__}: {error}")
        raise
