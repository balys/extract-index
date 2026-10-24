"""Field types, request / gold / row validation, and answer value normalisation.

Validators return a list of problems (empty means valid). Gold values must already be in their
canonical form; answers are normalised leniently (see `normalise`) before scoring.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any

TYPES = ("text", "number", "date", "time", "datetime", "duration", "list", "estimate", "forecast")
SCORED_TYPES = ("text", "number", "date", "time", "datetime", "duration", "list")
ITEM_TYPES = ("text", "number", "date")
DURATION_UNITS = ("seconds", "minutes", "hours", "days", "weeks", "months", "years")
FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$")
ROW_ID_RE = re.compile(r"^[a-z0-9]+-\d{5}$")
META_KEYS = ("source", "split", "source_id", "license")

_SPEC_KEYS = {"type", "instructions", "unit", "integer", "decimals", "items", "min", "max", "step",
              "scale", "null_threshold", "horizon", "interval"}
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_TIME_RE = re.compile(r"^(\d{2}):(\d{2})(?::(\d{2}))?$")
_DATETIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}(?::\d{2})?)$")


# ---------------------------------------------------------------- requests

def validate_field_spec(name: str, spec: Any) -> list[str]:
    where = f"field {name!r}"
    if not isinstance(name, str) or not FIELD_NAME_RE.match(name):
        return [f"{where}: bad field name"]
    if not isinstance(spec, dict):
        return [f"{where}: spec is not an object"]
    problems = []
    t = spec.get("type")
    if t not in TYPES:
        return [f"{where}: unknown type {t!r}"]
    extra = set(spec) - _SPEC_KEYS
    if extra:
        problems.append(f"{where}: unknown keys {sorted(extra)}")
    if "instructions" in spec and not (isinstance(spec["instructions"], str) and spec["instructions"].strip()):
        problems.append(f"{where}: instructions must be a non-empty string")
    if "unit" in spec and not isinstance(spec["unit"], str):
        problems.append(f"{where}: unit must be a string")
    if t == "duration" and spec.get("unit", "seconds") not in DURATION_UNITS:
        problems.append(f"{where}: duration unit must be one of {DURATION_UNITS}")
    if "integer" in spec:
        if not isinstance(spec["integer"], bool):
            problems.append(f"{where}: integer must be a boolean")
        if t not in ("number", "duration"):
            problems.append(f"{where}: integer is for numbers and durations")
    if "decimals" in spec:
        d = spec["decimals"]
        if not (isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6):
            problems.append(f"{where}: decimals must be an integer 0-6")
        if t not in ("number", "duration") and not (t == "list" and spec.get("items") == "number"):
            problems.append(f"{where}: decimals is for numbers, durations and number lists")
    if t == "list":
        if spec.get("items") not in ITEM_TYPES:
            problems.append(f"{where}: list needs items in {ITEM_TYPES}")
    elif "items" in spec:
        problems.append(f"{where}: items is for lists")
    if t in ("estimate", "forecast"):
        if "min" not in spec or "max" not in spec:
            problems.append(f"{where}: {t} needs min and max")
    return problems


def validate_request(request: Any) -> list[str]:
    if not isinstance(request, dict):
        return ["request is not an object"]
    problems = []
    extra = set(request) - {"state", "fields", "reference_date"}
    if extra:
        problems.append(f"request: unknown keys {sorted(extra)}")
    state = request.get("state")
    if not (isinstance(state, str) and state.strip()):
        problems.append("request: state must be a non-empty string")
    fields = request.get("fields")
    if not (isinstance(fields, dict) and fields):
        problems.append("request: fields must be a non-empty object")
    else:
        for name, spec in fields.items():
            problems += validate_field_spec(name, spec)
    if "reference_date" in request and not is_date(request["reference_date"]):
        problems.append("request: reference_date must be YYYY-MM-DD")
    return problems


# ---------------------------------------------------------------- canonical value forms

def is_date(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    m = _DATE_RE.match(v)
    if not m:
        return False
    try:
        dt.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return False
    return True


def is_time(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    m = _TIME_RE.match(v)
    return bool(m) and int(m[1]) < 24 and int(m[2]) < 60 and (m[3] is None or int(m[3]) < 60)


def is_datetime(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    m = _DATETIME_RE.match(v)
    return bool(m) and is_date(m[1]) and is_time(m[2])


def is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def is_canonical(t: str, v: Any) -> bool:
    """True if `v` (not None) is in the canonical form for scalar type `t`."""
    if t == "text":
        return isinstance(v, str) and bool(v.strip())
    if t in ("number", "duration"):
        return is_number(v)
    if t == "date":
        return is_date(v)
    if t == "time":
        return is_time(v)
    if t == "datetime":
        return is_datetime(v)
    return False


# ---------------------------------------------------------------- gold and rows

def _gold_value_problems(where: str, spec: dict, value: Any) -> list[str]:
    if value is None:
        return []
    t = spec["type"]
    if t == "list":
        if not isinstance(value, list):
            return [f"{where}: list gold must be an array or null"]
        if not value:
            return [f"{where}: empty gold list must be stored as null"]
        bad = [x for x in value if not is_canonical(spec["items"], x)]
        return [f"{where}: bad {spec['items']} items {bad[:3]}"] if bad else []
    if t in SCORED_TYPES:
        return [] if is_canonical(t, value) else [f"{where}: {value!r} is not a canonical {t}"]
    return [f"{where}: type {t} is not scored in this edition"]


def validate_gold(fields: dict, gold: Any) -> list[str]:
    if not isinstance(gold, dict):
        return ["gold is not an object"]
    problems = []
    missing = set(fields) - set(gold)
    extra = set(gold) - set(fields)
    if missing:
        problems.append(f"gold: missing fields {sorted(missing)}")
    if extra:
        problems.append(f"gold: fields not in the request {sorted(extra)}")
    for name in fields.keys() & gold.keys():
        g, spec, where = gold[name], fields[name], f"gold {name!r}"
        if not isinstance(g, dict) or "value" not in g:
            problems.append(f"{where}: must be an object with a value")
            continue
        unknown = set(g) - {"value", "alternatives", "item_alternatives"}
        if unknown:
            problems.append(f"{where}: unknown keys {sorted(unknown)}")
        problems += _gold_value_problems(where, spec, g["value"])
        alts = g.get("alternatives")
        if alts is not None:
            if not isinstance(alts, list) or g["value"] is None:
                problems.append(f"{where}: alternatives must be a list, next to a non-null value")
            else:
                for a in alts:
                    if a is None:
                        problems.append(f"{where}: null alternative")
                    else:
                        problems += _gold_value_problems(f"{where} alternative", spec, a)
        ia = g.get("item_alternatives")
        if ia is not None:
            v = g["value"]
            if spec["type"] != "list" or not isinstance(v, list) or not isinstance(ia, list) or len(ia) != len(v):
                problems.append(f"{where}: item_alternatives must parallel a list value")
            else:
                for forms in ia:
                    if not isinstance(forms, list) or not all(is_canonical(spec["items"], x) for x in forms):
                        problems.append(f"{where}: bad item_alternatives entry {forms!r}")
    return problems


def validate_row(row: Any, test: str | None = None) -> list[str]:
    if not isinstance(row, dict):
        return ["row is not an object"]
    problems = []
    rid = row.get("id")
    if not (isinstance(rid, str) and ROW_ID_RE.match(rid)):
        problems.append(f"bad row id {rid!r}")
    if test is not None and row.get("test") != test:
        problems.append(f"row test {row.get('test')!r} != {test!r}")
    if isinstance(rid, str) and isinstance(row.get("test"), str) and not rid.startswith(row["test"] + "-"):
        problems.append(f"row id {rid!r} does not start with its test")
    problems += validate_request(row.get("request"))
    fields = (row.get("request") or {}).get("fields")
    if isinstance(fields, dict) and fields:
        problems += validate_gold(fields, row.get("gold"))
    meta = row.get("meta")
    if not isinstance(meta, dict) or any(k not in meta for k in META_KEYS):
        problems.append(f"meta must have {META_KEYS}")
    return [f"{rid}: {p}" for p in problems]


# ---------------------------------------------------------------- answers

_CURRENCY_RE = re.compile(r"[$€£¥₹₩₽¢₺₫฿]|^(?:[A-Z]{3}|Rp\.?)\s*|\s*(?:[A-Z]{3})$")
_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def parse_number(v: Any) -> float | None:
    """A number, or a numeric string with `,` thousands separators, `%` or currency marks."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    if not isinstance(v, str):
        return None
    s = v.strip().replace("−", "-").replace(" ", " ")
    s = _CURRENCY_RE.sub("", s).strip()
    s = s.rstrip("%").strip().replace(",", "").replace(" ", "")
    if not _NUMBER_RE.match(s):
        return None
    x = float(s)
    return x if math.isfinite(x) else None


_ISO_DT_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2})(:\d{2})?(?:\.\d+)?)?\s*(?:Z|[+-]\d{2}:?\d{2})?$")
_ISO_TIME_RE = re.compile(r"^T?(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*(?:Z|[+-]\d{2}:?\d{2})?$")


def norm_date(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    m = _ISO_DT_RE.match(v.strip())
    return m[1] if m and is_date(m[1]) else None


def norm_time(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    m = _ISO_TIME_RE.match(v.strip())
    if not m:
        return None
    out = f"{int(m[1]):02d}:{m[2]}" + (f":{m[3]}" if m[3] else "")
    return out if is_time(out) else None


def norm_datetime(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    m = _ISO_DT_RE.match(v.strip())
    if not m or not m[2]:
        return None
    out = f"{m[1]}T{m[2]}{m[3] or ''}"
    return out if is_datetime(out) else None


class WrongForm(ValueError):
    """The answer value is not in a form its field type accepts."""


def _norm_scalar(t: str, v: Any) -> Any:
    if t == "text":
        if isinstance(v, str):
            return v.strip()
        if is_number(v):
            return str(int(v)) if float(v).is_integer() else str(v)
        raise WrongForm(f"text value {v!r}")
    if t in ("number", "duration"):
        x = parse_number(v)
        if x is None:
            raise WrongForm(f"{t} value {v!r}")
        return x
    norm = {"date": norm_date, "time": norm_time, "datetime": norm_datetime}.get(t)
    if norm is None:
        raise WrongForm(f"type {t} is not scored")
    out = norm(v)
    if out is None:
        raise WrongForm(f"{t} value {v!r}")
    return out


def normalise(spec: dict, value: Any) -> Any:
    """Canonical form of an answer value for its field spec, or raise `WrongForm`.

    `None` stays `None`. Lists keep their order; an item in the wrong form becomes `None`
    (it then matches nothing). An empty list stays `[]`.
    """
    if value is None:
        return None
    t = spec["type"]
    if t == "list":
        if not isinstance(value, list):
            raise WrongForm(f"list value {value!r}")
        out = []
        for item in value:
            try:
                out.append(None if item is None else _norm_scalar(spec["items"], item))
            except WrongForm:
                out.append(None)
        return out
    return _norm_scalar(t, value)


def answer_value(answer: Any) -> Any:
    """The `value` of one answer object, or raise `WrongForm` if the object is malformed."""
    if not isinstance(answer, dict) or "value" not in answer:
        raise WrongForm("answer must be an object with a value")
    return answer["value"]


def validate_response(fields: dict, response: Any) -> list[str]:
    """Problems with an engine response, for engine authors (`{"answers": {...}}`)."""
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        return ["response must be an object with an answers object"]
    answers = response["answers"]
    problems = [f"missing answer for {n!r}" for n in fields if n not in answers]
    for name, spec in fields.items():
        if name not in answers:
            continue
        try:
            normalise(spec, answer_value(answers[name]))
        except WrongForm as e:
            problems.append(f"{name!r}: {e}")
    return problems
