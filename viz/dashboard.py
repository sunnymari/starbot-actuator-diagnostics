"""Live terminal dashboard: every joint's telemetry plus the detector's alerts.

    python -m viz.dashboard              # with the demo faults
    python -m viz.dashboard --no-faults  # all joints healthy
"""

import argparse
import time

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from diagnostics.live import LiveFeed
from diagnostics.config import CONFIG

FRAME_TIMEOUT_S = CONFIG["heartbeat_timeout_ms"] / 1000

STATUS_STYLE = {"OK": "green", "WARNING": "bold yellow", "CRITICAL": "bold red", "NO DATA": "bold grey70"}


def fmt(value, spec):
    return "—" if value is None else format(value, spec)


def joint_table(snapshot):
    table = Table(expand=True, header_style="bold magenta")
    table.add_column("CAN ID", style="dim")
    table.add_column("Joint")
    table.add_column("Temp °C", justify="right")
    table.add_column("Current A", justify="right")
    table.add_column("Pos err °", justify="right")
    table.add_column("Voltage V", justify="right")
    table.add_column("Last frame", justify="right")
    table.add_column("Status")

    for joint in snapshot["joints"]:
        age = joint["age_s"]
        age_text = Text(fmt(None if age is None else age * 1000, ".0f") + " ms",
                        style="red" if age is not None and age > FRAME_TIMEOUT_S else "dim")
        if not joint['has_frame']:
            age_text = Text('waiting for first frame', style='dim')
        status = joint["status"]
        table.add_row(
            f"0x{joint['can_id']:03X}",
            joint["name"],
            fmt(joint["temperature_c"], ".1f"),
            fmt(joint["current_a"], ".2f"),
            fmt(joint["position_error_deg"], "+.2f"),
            fmt(joint["voltage_v"], ".1f"),
            age_text,
            Text(status, style=STATUS_STYLE[status]),
        )
    return table


def alert_panel(snapshot):
    lines = Text()
    for entry in snapshot["log"][-10:]:
        lines.append(f"{entry['t']:6.1f}s  ", style="dim")
        lines.append(entry["text"] + "\n", style=STATUS_STYLE[entry["severity"]])
    if not lines:
        lines.append("no DTCs recorded", style="dim")
    return Panel(lines, title="Alerts", border_style="magenta")


def render(snapshot):
    header = Text(f"Optimus actuator diagnostics  ·  t = {snapshot['elapsed_s']:.0f} s", style="bold")
    faults = Text("injected: " + ("; ".join(snapshot["faults"]) or "none"), style="dim")
    return Group(header, faults, joint_table(snapshot), alert_panel(snapshot))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-faults", action="store_true", help="run with every joint healthy")
    args = parser.parse_args()

    feed = LiveFeed(faults=not args.no_faults).start()
    try:
        with Live(render(feed.snapshot()), refresh_per_second=4, screen=True) as live:
            while True:
                time.sleep(0.25)
                live.update(render(feed.snapshot()))
    except KeyboardInterrupt:
        pass
    finally:
        feed.stop()


if __name__ == "__main__":
    main()
