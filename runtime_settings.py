"""Validation for settings that the local Electron dashboard may change.

This module is deliberately pure Python so the policy can be unit-tested without
opening a camera, /dev/uinput or a GUI.
"""

SETTING_SPECS = {
    "tap_lift": {"type": "float", "min": 0.05, "max": 0.30},
    "tap_return": {"type": "float", "min": 0.01, "max": 0.12},
    "tap_cooldown": {"type": "float", "min": 0.05, "max": 0.80},
    "thumb_lift": {"type": "float", "min": 0.05, "max": 0.35},
    "thumb_return": {"type": "float", "min": 0.01, "max": 0.15},
    "four_finger_scroll": {"type": "bool"},
    "scroll_rest": {"type": "float", "min": 0.02, "max": 0.20},
    "scroll_start": {"type": "float", "min": 0.001, "max": 0.03},
    "scroll_speed": {"type": "float", "min": 10.0, "max": 300.0},
    "scroll_release": {"type": "float", "min": 0.05, "max": 0.60},
    "invert_scroll": {"type": "bool"},
    "smart_pinky": {"type": "bool"},
    "median": {"type": "int", "min": 1, "max": 9},
    "mincutoff": {"type": "float", "min": 0.10, "max": 5.0},
    "beta": {"type": "float", "min": 0.0, "max": 0.30},
    "conf": {"type": "float", "min": 0.40, "max": 0.95},
}


def _normalize_value(key, value):
    spec = SETTING_SPECS[key]
    kind = spec["type"]

    if kind == "bool":
        if type(value) is not bool:
            raise TypeError(f"{key} must be true or false")
        return value

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be numeric")

    if kind == "int":
        number = int(value)
        if float(number) != float(value):
            raise TypeError(f"{key} must be a whole number")
    else:
        number = float(value)

    if not spec["min"] <= number <= spec["max"]:
        raise ValueError(
            f"{key} must be between {spec['min']} and {spec['max']}")
    return number


def _validate_combination(values):
    if values["tap_return"] >= values["tap_lift"]:
        raise ValueError(
            "tap_return must be smaller than tap_lift")
    if values["thumb_return"] >= values["thumb_lift"]:
        raise ValueError(
            "thumb_return must be smaller than thumb_lift")


def normalize_updates(current, updates):
    """Return normalized updates after validating the resulting full state."""
    if not isinstance(updates, dict):
        raise TypeError("settings update must be an object")

    candidate = dict(current)
    accepted = {}
    for key, value in updates.items():
        if key not in SETTING_SPECS:
            raise KeyError(f"unsupported dashboard setting: {key}")
        normalized = _normalize_value(key, value)
        candidate[key] = normalized
        accepted[key] = normalized

    missing = set(SETTING_SPECS) - set(candidate)
    if missing:
        raise ValueError(
            "current setting state is incomplete: " + ", ".join(sorted(missing)))

    _validate_combination(candidate)
    return accepted


def values_from_args(args):
    values = {key: getattr(args, key) for key in SETTING_SPECS}
    normalized = {}
    for key, value in values.items():
        normalized[key] = _normalize_value(key, value)
    _validate_combination(normalized)
    return normalized
