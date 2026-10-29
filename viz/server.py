"""Serve the demo: python -m viz.server [--port 8000] [--scenario]."""
import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from diagnostics.live import LiveFeed

WEB_DIR = Path(__file__).parent / 'web'


class Handler(SimpleHTTPRequestHandler):
    feed = None

    def send_json(self, body, status=200):
        data = json.dumps(body, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/state':
            selected = parse_qs(url.query).get('joint', [None])[0]
            self.send_json(self.feed.snapshot(selected))
        else:
            super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != '/control':
            return self.send_json({'error': 'Unknown endpoint'}, 404)
        # Local controls accept same-origin JSON; browsers cannot post cross-origin forms.
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            return self.send_json({'error': 'Origin does not match this viewer'}, 403)
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send_json({'error': 'Expected application/json'}, 415)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError('Invalid request size')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected a JSON object')
            result = self.feed.control(body.get('action'), body.get('joint'), body.get('fault'))
        except (ValueError, TypeError) as error:
            return self.send_json({'error': str(error)}, 400)
        self.send_json(result)

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--scenario', action='store_true', help='run the original timed fault scenario')
    modes.add_argument('--no-faults', action='store_true', help='healthy start (the default); manual controls still work')
    args = parser.parse_args()
    feed = LiveFeed(faults=args.scenario).start()
    Handler.feed = feed
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, directory=str(WEB_DIR)))
    except OSError:
        feed.stop()
        raise
    print(f'3D viewer at http://localhost:{args.port}  (Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        feed.stop()


if __name__ == '__main__':
    main()
