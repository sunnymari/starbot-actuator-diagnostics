"""Serves the 3D robot viewer and the live joint state.

    python -m viz.server        # then open http://localhost:8000

GET /state returns LiveFeed.snapshot() as JSON; everything else comes from viz/web/.
Put your Blender export at viz/web/robot.glb and the viewer uses it instead of
the built-in placeholder robot.
"""

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from diagnostics.live import LiveFeed

WEB_DIR = Path(__file__).parent / "web"


class Handler(SimpleHTTPRequestHandler):
    feed = None

    def do_GET(self):
        if self.path.split("?")[0] == "/state":
            body = json.dumps(self.feed.snapshot()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def log_message(self, format, *args):
        pass  # the viewer polls /state 4 times a second; keep the terminal quiet


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-faults", action="store_true", help="run with every joint healthy")
    args = parser.parse_args()

    Handler.feed = LiveFeed(faults=not args.no_faults).start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(WEB_DIR)))
    print(f"3D viewer at http://localhost:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        Handler.feed.stop()


if __name__ == "__main__":
    main()
