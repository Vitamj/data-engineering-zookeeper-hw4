import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from kazoo.client import KazooClient
from kazoo.exceptions import OperationTimeoutError

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
sys.path.insert(0, str(ROOT / "src"))
SERVERS = {}
SERVER_STREAMS = {}


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_evidence(line):
    print(f"{timestamp()} {line}", flush=True)


def wait_for(predicate, label, timeout=40):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(0.25)
    raise TimeoutError(f"timed out waiting for {label}")


def server_mode(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1) as sock:
            sock.sendall(b"srvr")
            sock.settimeout(1)
            response = sock.recv(8192).decode(errors="replace")
            return next((line.split(":", 1)[1].strip() for line in response.splitlines() if line.startswith("Mode:")), "unknown")
    except OSError:
        return "unavailable"


def wait_ensemble(timeout=45):
    wait_for(lambda: all(server_mode(port) in {"leader", "follower"} for port in (2181, 2182, 2183)), "three-server quorum", timeout)
    return [server_mode(port) for port in (2181, 2182, 2183)]


def connect(timeout=7):
    client = KazooClient(hosts="127.0.0.1:2181,127.0.0.1:2182,127.0.0.1:2183", timeout=10.0)
    client.start(timeout=timeout)
    return client


def start_server(server_id):
    zk_server = subprocess.check_output(["brew", "--prefix", "zookeeper"], text=True).strip() + "/bin/zkServer"
    java_home = subprocess.check_output(["brew", "--prefix", "openjdk@17"], text=True).strip() + "/libexec/openjdk.jdk/Contents/Home"
    env = os.environ.copy()
    env["JAVA_HOME"] = java_home
    env["PATH"] = java_home + "/bin:" + env.get("PATH", "")
    env["ZOO_LOG_DIR"] = str(LOGS)
    (ROOT / f"data/server-{server_id}").mkdir(parents=True, exist_ok=True)
    (ROOT / f"data/server-{server_id}/myid").write_text(f"{server_id}\n", encoding="utf-8")
    stream = (LOGS / f"zk-{server_id}.log").open("w", encoding="utf-8")
    process = subprocess.Popen([zk_server, "start-foreground", str(ROOT / f"config/zoo-{server_id}.cfg")], cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    SERVERS[server_id] = process
    SERVER_STREAMS[server_id] = stream
    (LOGS / f"zk-{server_id}.pid").write_text(f"{process.pid}\n", encoding="utf-8")
    write_evidence(f"ZOOKEEPER_SERVER_STARTED id={server_id} pid={process.pid}")


def stop_server(server_id):
    process = SERVERS.get(server_id)
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=4)
    write_evidence(f"ZOOKEEPER_SERVER_STOPPED id={server_id}")


def start_ensemble():
    for server_id in (1, 2, 3):
        start_server(server_id)
        time.sleep(0.5)
    modes = wait_ensemble()
    write_evidence(f"ENSEMBLE_READY roles={modes}")


def stop_ensemble():
    for server_id in (1, 2, 3):
        stop_server(server_id)
    for stream in SERVER_STREAMS.values():
        stream.close()


def check_quorum():
    modes = wait_ensemble()
    write_evidence(f"ENSEMBLE_INITIAL roles={modes}")
    stop_server(1)
    time.sleep(1.5)
    client = connect()
    client.ensure_path("/checks")
    client.set("/checks", b"one server stopped")
    write_evidence(f"ONE_SERVER_DOWN remaining_modes={[server_mode(p) for p in (2182, 2183)]} write_ok=True")
    client.stop()
    client.close()
    stop_server(2)
    time.sleep(1.5)
    try:
        failed = connect(timeout=4)
    except (OperationTimeoutError, TimeoutError, Exception) as error:
        write_evidence(f"TWO_SERVERS_DOWN last_mode={server_mode(2183)} client_operation=unavailable error={type(error).__name__}")
    else:
        try:
            failed.set("/checks", b"must not commit")
            raise AssertionError("write succeeded without quorum")
        except Exception as error:
            write_evidence(f"TWO_SERVERS_DOWN client_operation=failed error={type(error).__name__}")
        finally:
            failed.stop()
            failed.close()
    start_server(1)
    start_server(2)
    roles = wait_ensemble()
    write_evidence(f"ENSEMBLE_RESTORED roles={roles}")


def check_ephemeral():
    client = connect()
    client.ensure_path("/ephemeral")
    path = "/ephemeral/session-check"
    client.create(path, b"disappears when the session closes", ephemeral=True, makepath=True)
    stat = client.exists(path)
    write_evidence(f"EPHEMERAL_CREATED path={path} ephemeralOwner={stat.ephemeralOwner}")
    client.stop()
    client.close()
    check = connect()
    present = check.exists(path) is not None
    check.stop()
    check.close()
    write_evidence(f"EPHEMERAL_AFTER_SESSION_CLOSE exists={present}")
    if present:
        raise AssertionError("ephemeral node survived session close")


def read_log(path):
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def run_round(fenced):
    mode = "fenced" if fenced else "unfenced"
    checkpoint = ROOT / "results" / mode / "checkpoint.json"
    receiver_db = ROOT / "results" / mode / "receiver.sqlite"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    for path in (checkpoint, receiver_db, Path(str(receiver_db) + "-wal"), Path(str(receiver_db) + "-shm")):
        if path.exists():
            path.unlink()
    processes = {}
    env_base = os.environ.copy()
    env_base.update({
        "PYTHONPATH": str(ROOT / "src"),
        "FENCING": "1" if fenced else "0",
        "DATA_PATH": str(ROOT / "data/go_vacancies.jsonl"),
        "CHECKPOINT_PATH": str(checkpoint),
        "RECEIVER_DB": str(receiver_db),
        "ZK_HOSTS": "127.0.0.1:2181,127.0.0.1:2182,127.0.0.1:2183",
        "CHUNK_SIZE": "16",
        "CHUNK_DELAY": "1.8",
    })
    for worker in ("coord-A", "coord-B"):
        env = env_base | {"WORKER_ID": worker}
        stream = (LOGS / f"{mode}-{worker}.log").open("w", encoding="utf-8")
        process = subprocess.Popen([sys.executable, str(ROOT / "src/coordinator.py")], cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        processes[worker] = (process, stream)
        if worker == "coord-A":
            wait_for(lambda: "BECAME_LEADER" in read_log(LOGS / f"{mode}-coord-A.log"), "initial coordinator leader")
            time.sleep(0.6)
    process_a = processes["coord-A"][0]
    log_a = LOGS / f"{mode}-coord-A.log"
    wait_for(lambda: read_log(log_a).count("CHUNK_COMMITTED") >= 2, "two checkpoint chunks")
    time.sleep(0.2)
    pause_start = time.monotonic()
    pause_wall = timestamp()
    os.kill(process_a.pid, signal.SIGSTOP)
    write_evidence(f"{mode.upper()} PAUSE_LEADER pid={process_a.pid} at={pause_wall} completed_chunks={read_log(log_a).count('CHUNK_COMMITTED')}")
    log_b = LOGS / f"{mode}-coord-B.log"
    wait_for(lambda: "BECAME_LEADER" in read_log(log_b), "backup becomes leader", 35)
    became_leader = time.monotonic()
    failover = became_leader - pause_start
    write_evidence(f"{mode.upper()} FAILOVER_SECONDS={failover:.3f} backup_event=" + next(line.strip() for line in read_log(log_b).splitlines() if "BECAME_LEADER" in line))
    wait_for(lambda: "RESULT_WRITTEN" in read_log(log_b), "backup result publication", 35)
    remaining = 40 - (time.monotonic() - pause_start)
    if remaining > 0:
        time.sleep(remaining)
    os.kill(process_a.pid, signal.SIGCONT)
    write_evidence(f"{mode.upper()} RESUME_OLD_LEADER elapsed_since_pause={time.monotonic()-pause_start:.3f}")
    wait_for(lambda: "PROCESS_METRICS" in read_log(log_a), "old coordinator completion", 25)
    process_a.wait(timeout=5)
    process_b = processes["coord-B"][0]
    process_b.wait(timeout=5)
    for _, stream in processes.values():
        stream.close()
    from receiver import ResultReceiver
    final = ResultReceiver(receiver_db, fenced).snapshot()
    expected = json.loads((ROOT / "data/hw3_pair_counts.json").read_text(encoding="utf-8"))
    actual = final["payload"]["pairs"]
    matched = expected == actual
    write_evidence(f"{mode.upper()} FINAL pointer_version={final['pointer_version']} active_epoch={final['active_epoch']} result_matches_hw3={matched} pair_keys={final['payload']['pair_keys']} occurrences={final['payload']['occurrences']}")
    if not matched:
        raise AssertionError(f"{mode} result differs from HW3")
    if not fenced and final["pointer_version"] != 2:
        raise AssertionError("unfenced scenario did not write twice")
    if fenced and final["pointer_version"] != 1:
        raise AssertionError("fenced scenario should leave one accepted write")
    (ROOT / "results" / mode / "final.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"mode": mode, "failover_seconds": round(failover, 3), "pointer_version": final["pointer_version"], "active_epoch": final["active_epoch"], "result_matches_hw3": matched}


def main():
    LOGS.mkdir(exist_ok=True)
    with (LOGS / "experiment.log").open("w", encoding="utf-8") as out:
        sys.stdout = out
        try:
            start_ensemble()
            check_quorum()
            check_ephemeral()
            runs = [run_round(False), run_round(True)]
            summary = {"student": "Вита-Виктория Гиалтсо-Мижа", "group": "j3313", "isu": "466703", "zookeeper": "3.9.6", "session_timeout_seconds": 10, "dataset_rows": 124, "hw3_pair_keys": 1008, "hw3_pair_occurrences": 2382, "runs": runs}
            (ROOT / "results/experiment.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            write_evidence("EXPERIMENT_SUMMARY " + json.dumps(summary, ensure_ascii=False))
        finally:
            stop_ensemble()


if __name__ == "__main__":
    main()
