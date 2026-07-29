# brain_contracts.py - the contract envelope, the atomic writer, and the registry loader.
# P0 of the Cortex brain app (see wg\GAMEPLAN-BRAIN-APP.md). Pure stdlib, pure ASCII source.
#
# ONE envelope shape for every contract file in wg\brain\data\:
#     {"_meta": {contract, version, generated_at, producer, slo_seconds, emitted_at, source}, "data": <payload>}
#
# HONESTY RULES encoded here (guardrail 5 - "never a plausible-looking lie"):
#   * generated_at  = when the DATA was produced. For a wrapped/cached producer that is the SOURCE FILE's mtime,
#                     NOT the moment we copied it. Copying stale data never makes it fresh.
#   * emitted_at    = when this envelope was written. Only ever used for debugging drift.
#   * slo_seconds   = the freshness contract. null means "no schedule exists - render the age, never claim fresh".
#   * writes are atomic (tmp + os.replace) so a reader never sees a half-written contract.
#
# Encoding: files are written UTF-8 WITHOUT a BOM, ensure_ascii=False. Every reader in this repo opens local JSON
# with encoding="utf-8-sig" (handles both BOM and BOM-less) per the house minefield rule.
import json, os, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
DATA = os.path.join(BRAIN, "data")
CONTRACTS = os.path.join(BRAIN, "contracts")
REGISTRY = os.path.join(CONTRACTS, "registry.json")

_reg_cache = {"t": 0.0, "d": None}


def iso(ts=None):
    """Local-time ISO-8601 with a UTC offset, second precision (matches oracle.json's style)."""
    if ts is None:
        ts = time.time()
    return datetime.datetime.fromtimestamp(float(ts)).astimezone().isoformat(timespec="seconds")


def load_registry(force=False):
    """The registry is the source of truth for version/producer/slo. Cached 30s (a regen re-reads it anyway)."""
    if not force and _reg_cache["d"] is not None and (time.time() - _reg_cache["t"]) < 30:
        return _reg_cache["d"]
    with open(REGISTRY, encoding="utf-8-sig") as fh:
        reg = json.load(fh)
    _reg_cache["d"] = reg
    _reg_cache["t"] = time.time()
    return reg


def entry(name):
    reg = load_registry()
    e = reg["contracts"].get(name)
    if e is None:
        raise KeyError("contract not in registry: %s (add it to contracts\\registry.json first)" % name)
    return e


def read_json(path):
    """Read a local JSON file tolerating a UTF-8 BOM. Returns None on any failure (caller decides)."""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except Exception:
        return None


def mtime(path):
    try:
        return os.path.getmtime(path)
    except Exception:
        return None


def write_contract(name, data, generated_at_ts=None, source=None):
    """Write data as a contract envelope. generated_at_ts is a unix ts; None means 'produced right now'.

    Returns the written path. Raises on registry/IO problems - callers in the render path must wrap in try/except
    so a contract failure can never affect the served page.
    """
    e = entry(name)
    now = time.time()
    meta = {
        "contract": name,
        "version": e["version"],
        "generated_at": iso(now if generated_at_ts is None else generated_at_ts),
        "producer": e["producer"],
        "slo_seconds": e.get("slo_seconds"),
        "emitted_at": iso(now),
        "source": source if source is not None else e.get("source"),
    }
    envelope = {"_meta": meta, "data": data}
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, name + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(envelope, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return path


def contract_source_mtime(name):
    """The source mtime recorded in an already-written contract (used to skip pointless rewrites)."""
    cur = read_json(os.path.join(DATA, name + ".json"))
    try:
        return cur["_meta"].get("source_mtime")
    except Exception:
        return None


def write_wrapped(name, data, src_path):
    """Wrap an existing producer's output. generated_at = the SOURCE file's mtime (its real age)."""
    e = entry(name)
    st = mtime(src_path)
    now = time.time()
    meta = {
        "contract": name,
        "version": e["version"],
        "generated_at": iso(now if st is None else st),
        "producer": e["producer"],
        "slo_seconds": e.get("slo_seconds"),
        "emitted_at": iso(now),
        "source": e.get("source"),
        "source_mtime": st,
    }
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, name + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"_meta": meta, "data": data}, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return path
