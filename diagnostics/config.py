"""Editable synthetic demo limits; these are not manufacturer limits."""
import json
from pathlib import Path

CONFIG = json.loads(Path(__file__).with_name('rules.json').read_text())


def frame_age_s(last_seen, now, started_at):
    return max(0.0, now - (started_at if last_seen is None else last_seen))


def has_no_data(last_seen, now, started_at, timeout_ms):
    return last_seen is None or frame_age_s(last_seen, now, started_at) * 1000 > timeout_ms
