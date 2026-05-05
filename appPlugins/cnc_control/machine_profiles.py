# FlatCAM Plus CNC Control Module
# License: FlatCAM Plus CNC Control Module Non-Commercial License.
# See appPlugins/cnc_control/LICENSE.

import copy


DEFAULT_MACHINE_PROFILES = [
    {
        "name": "Default CNC",
        "safe_z": 5.0,
        "jog_feed": 1000,
        "probe_feed": 100,
        "spindle_max": 12000,
        "travel_x": 300.0,
        "travel_y": 300.0,
        "travel_z": 80.0,
    }
]


def default_machine_profiles():
    return copy.deepcopy(DEFAULT_MACHINE_PROFILES)


def _float_value(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _int_value(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def normalize_machine_profile(profile, fallback_name="Machine"):
    profile = dict(profile or {})
    name = str(profile.get("name", "")).strip() or fallback_name
    return {
        "name": name,
        "safe_z": _float_value(profile.get("safe_z"), 5.0),
        "jog_feed": max(1, _int_value(profile.get("jog_feed"), 1000)),
        "probe_feed": max(1, _int_value(profile.get("probe_feed"), 100)),
        "spindle_max": max(0, _int_value(profile.get("spindle_max"), 12000)),
        "travel_x": max(0.0, _float_value(profile.get("travel_x"), 300.0)),
        "travel_y": max(0.0, _float_value(profile.get("travel_y"), 300.0)),
        "travel_z": max(0.0, _float_value(profile.get("travel_z"), 80.0)),
    }


def normalize_machine_profiles(profiles):
    if not isinstance(profiles, list) or not profiles:
        profiles = default_machine_profiles()

    normalized = []
    used_names = set()
    for idx, profile in enumerate(profiles, start=1):
        item = normalize_machine_profile(profile, fallback_name=f"Machine {idx}")
        base_name = item["name"]
        name = base_name
        suffix = 2
        while name in used_names:
            name = f"{base_name} {suffix}"
            suffix += 1
        item["name"] = name
        used_names.add(name)
        normalized.append(item)

    return normalized or default_machine_profiles()
