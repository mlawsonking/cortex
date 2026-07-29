#!/usr/bin/env python3
# validate-contracts.py - the P0 honesty gate: schema-validate every contract, check envelope integrity against
# the registry, and report real freshness. Pure stdlib (jsonschema is NOT installed on this box and this script
# deliberately adds no dependency to the production python env). Pure ASCII source.
#
# EXIT CODES (honest by design - consumed later by verify-brain.ps1 and the daily-audit task-health check):
#   0 = every registered contract present, envelope correct, schema-valid, and fresh where an SLO exists
#   2 = all valid, but at least one contract is STALE past its SLO      (data problem, not a code problem)
#   1 = at least one HARD failure: missing / unparseable / schema-invalid / envelope-mismatch / bad schema
#
# THE SCHEMA VALIDATOR IS DELIBERATELY STRICT ABOUT ITSELF: any keyword it does not implement is a hard error,
# not a silent skip. A validator that quietly ignores half a schema is worse than no validator - it reports green
# while checking nothing. Supported keyword set is SUPPORTED below.
import json, os, sys, re, datetime, time

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACTS = os.path.join(HERE, "contracts")
DATA = os.path.join(HERE, "data")
REGISTRY = os.path.join(CONTRACTS, "registry.json")

ANNOTATIONS = {"$schema", "$id", "title", "description", "examples", "default", "$comment"}
SUPPORTED = {"type", "enum", "const", "required", "properties", "additionalProperties",
             "items", "minItems", "maxItems", "minimum", "maximum", "minLength", "maxLength", "pattern"}

TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}


def check_schema_keywords(schema, path="#"):
    """Reject a schema that uses anything we do not actually enforce."""
    errs = []
    if not isinstance(schema, dict):
        return ["%s: schema node is not an object" % path]
    for k in schema:
        if k in ANNOTATIONS or k in SUPPORTED:
            continue
        errs.append("%s: unsupported schema keyword '%s' (this validator would silently not enforce it)" % (path, k))
    for k in ("properties",):
        for name, sub in (schema.get(k) or {}).items():
            errs += check_schema_keywords(sub, "%s/%s/%s" % (path, k, name))
    if isinstance(schema.get("items"), dict):
        errs += check_schema_keywords(schema["items"], path + "/items")
    ap = schema.get("additionalProperties")
    if isinstance(ap, dict):
        errs += check_schema_keywords(ap, path + "/additionalProperties")
    elif ap is not None and not isinstance(ap, bool):
        errs.append("%s: additionalProperties must be a boolean or a schema" % path)
    return errs


def validate(value, schema, path="$"):
    errs = []
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        for name in types:
            if name not in TYPES:
                return ["%s: schema declares unknown type '%s'" % (path, name)]
        if not any(TYPES[name](value) for name in types):
            return ["%s: expected %s, got %s" % (path, "|".join(types), type(value).__name__)]
    if "const" in schema and value != schema["const"]:
        errs.append("%s: expected const %r" % (path, schema["const"]))
    if "enum" in schema and value not in schema["enum"]:
        errs.append("%s: %r not in enum %r" % (path, value, schema["enum"]))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append("%s: shorter than minLength %d" % (path, schema["minLength"]))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append("%s: longer than maxLength %d" % (path, schema["maxLength"]))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append("%s: %r does not match /%s/" % (path, value[:40], schema["pattern"]))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append("%s: %r < minimum %r" % (path, value, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errs.append("%s: %r > maximum %r" % (path, value, schema["maximum"]))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append("%s: %d items < minItems %d" % (path, len(value), schema["minItems"]))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append("%s: %d items > maxItems %d" % (path, len(value), schema["maxItems"]))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(value):
                errs += validate(item, item_schema, "%s[%d]" % (path, i))
                if len(errs) > 40:
                    errs.append("%s: ... further item errors suppressed" % path)
                    break
    if isinstance(value, dict):
        for req in (schema.get("required") or []):
            if req not in value:
                errs.append("%s: missing required property '%s'" % (path, req))
        props = schema.get("properties") or {}
        for name, sub in props.items():
            if name in value:
                errs += validate(value[name], sub, "%s.%s" % (path, name))
        ap = schema.get("additionalProperties")
        extra = [k for k in value if k not in props]
        if ap is False and extra:
            errs.append("%s: unexpected properties %s (schema forbids extras - producer drift?)" % (path, sorted(extra)))
        elif isinstance(ap, dict):
            for k in extra:
                errs += validate(value[k], ap, "%s.%s" % (path, k))
    return errs


def parse_iso(s):
    try:
        return datetime.datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


def human_age(sec):
    if sec is None:
        return "?"
    if sec < 90:
        return "%ds" % int(sec)
    if sec < 5400:
        return "%.0fm" % (sec / 60.0)
    if sec < 172800:
        return "%.1fh" % (sec / 3600.0)
    return "%.1fd" % (sec / 86400.0)


def main():
    as_json = "--json" in sys.argv
    check_sources = "--check-sources" in sys.argv
    with open(REGISTRY, encoding="utf-8-sig") as fh:
        reg = json.load(fh)
    now = time.time()
    rows, hard, stale = [], 0, 0

    for name in sorted(reg["contracts"]):
        e = reg["contracts"][name]
        row = {"contract": name, "status": "OK", "age": None, "age_h": None, "slo_seconds": e.get("slo_seconds"),
               "version": e.get("version"), "errors": []}
        sp = os.path.join(CONTRACTS, e.get("schema") or (name + ".schema.json"))
        cp = os.path.join(DATA, name + ".json")
        try:
            with open(sp, encoding="utf-8-sig") as fh:
                schema = json.load(fh)
        except Exception as ex:
            row["status"] = "FAIL"
            row["errors"].append("schema unreadable (%s): %s" % (os.path.basename(sp), ex))
            rows.append(row)
            hard += 1
            continue
        kerr = check_schema_keywords(schema)
        if kerr:
            row["status"] = "FAIL"
            row["errors"] += kerr
            rows.append(row)
            hard += 1
            continue
        if not os.path.isfile(cp):
            row["status"] = "MISSING"
            row["errors"].append("no contract file at data\\%s.json (producer never ran?)" % name)
            rows.append(row)
            hard += 1
            continue
        try:
            with open(cp, encoding="utf-8-sig") as fh:
                env = json.load(fh)
        except Exception as ex:
            row["status"] = "FAIL"
            row["errors"].append("contract unparseable: %s" % ex)
            rows.append(row)
            hard += 1
            continue
        if not isinstance(env, dict) or "_meta" not in env or "data" not in env:
            row["status"] = "FAIL"
            row["errors"].append("not a contract envelope (need {_meta, data})")
            rows.append(row)
            hard += 1
            continue
        meta = env["_meta"]
        for k in ("contract", "version", "generated_at", "producer"):
            if k not in meta:
                row["errors"].append("_meta missing '%s'" % k)
        if meta.get("contract") != name:
            row["errors"].append("_meta.contract=%r but file is %s.json" % (meta.get("contract"), name))
        if meta.get("version") != e.get("version"):
            row["errors"].append("_meta.version=%r but registry says %r (re-emit needed)"
                                 % (meta.get("version"), e.get("version")))
        if meta.get("producer") != e.get("producer"):
            row["errors"].append("_meta.producer disagrees with registry")
        gen = parse_iso(str(meta.get("generated_at", "")))
        if gen is None:
            row["errors"].append("_meta.generated_at is not ISO-8601: %r" % meta.get("generated_at"))
        else:
            row["age"] = human_age(now - gen)
            row["age_h"] = round((now - gen) / 3600.0, 2)
        row["errors"] += validate(env["data"], schema, "$")
        if check_sources:
            sys.path.insert(0, os.path.join(HERE, "producers"))
            try:
                import wrap_files
                src = wrap_files.SOURCES.get(name)
                want = e.get("source")
                if src and want and ("wg\\" + src).lower() != str(want).lower():
                    row["errors"].append("registry source %r != wrap_files source %r" % (want, "wg\\" + src))
            except Exception as ex:
                row["errors"].append("source cross-check failed: %s" % ex)
        if row["errors"]:
            row["status"] = "FAIL"
            hard += 1
        elif e.get("slo_seconds") is not None and gen is not None and (now - gen) > e["slo_seconds"]:
            row["status"] = "STALE"
            stale += 1
        elif e.get("slo_seconds") is None:
            row["status"] = "SNAPSHOT"          # no schedule exists: valid, age shown, freshness never claimed
        rows.append(row)

    orphans = []
    if os.path.isdir(DATA):
        for f in sorted(os.listdir(DATA)):
            if f.endswith(".json") and not f.startswith("_") and f[:-5] not in reg["contracts"]:
                orphans.append(f)

    code = 1 if hard else (2 if stale else 0)
    if as_json:
        print(json.dumps({"generated_at": datetime.datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds"),
                          "exit_code": code, "hard_failures": hard, "stale": stale,
                          "contracts": rows, "orphans": orphans}, ensure_ascii=False, indent=1))
        return code
    print("%-16s %-9s %-8s %-9s %s" % ("CONTRACT", "STATUS", "AGE", "SLO", "NOTE"))
    print("-" * 78)
    for r in rows:
        slo = r["slo_seconds"]
        slotxt = "none" if slo is None else human_age(slo)
        note = r["errors"][0] if r["errors"] else ""
        print("%-16s %-9s %-8s %-9s %s" % (r["contract"], r["status"], r["age"] or "-", slotxt, note[:120]))
        for extra in r["errors"][1:]:
            print("%-16s %-9s %-8s %-9s %s" % ("", "", "", "", extra[:120]))
    if orphans:
        print("\nORPHANS (files in data\\ with no registry entry): %s" % ", ".join(orphans))
    print("\n%d contracts | %d hard failure(s) | %d stale | exit %d" % (len(rows), hard, stale, code))
    return code


if __name__ == "__main__":
    sys.exit(main())
