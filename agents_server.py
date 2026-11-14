#!/usr/bin/env python3
"""Serve the agents dock snapshot read-only to the phone app, behind the proxy management key.

GET /v0/agents with `Authorization: Bearer <management key>` returns the agents in agents.json without
prompts, transcripts, folders or replies. The dock writes agents.json every few seconds; when it is not
running, this server collects a fresh snapshot itself at most every STALE seconds.

    python3 agents_server.py                      # this Mac only, port 8318
    python3 agents_server.py --host 0.0.0.0       # also the LAN and Tailscale addresses
"""
import argparse
import hmac
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import agents
from collector import proxy_path, setting

STALE = 20
STEP_LIMIT = 30
FIELDS = ('id', 'agent', 'name', 'tabName', 'project', 'status', 'title', 'task', 'now', 'progress', 'stepCount',
          'updated', 'started')
LOCK = threading.Lock()


def management_key():
    """The key collector.management() sends to the proxy, so the phone uses one key for both."""
    key = setting('PROXY_MANAGEMENT_KEY', '')
    if key:
        return key
    env = proxy_path('CLAUDE_PROXY_DIR', 'claude-proxy') / 'management.env'
    found = re.search(r'^MANAGEMENT_PASSWORD=(.+)$', env.read_text() if env.exists() else '', re.M)
    return found.group(1).strip() if found else ''


def public(agent):
    """The parts of an agent the phone shows; everything that can carry code or private text stays on the Mac."""
    item = {key: agent.get(key) for key in FIELDS}
    item['steps'] = [{'title': step.get('title'), 'status': step.get('status')}
                     for step in (agent.get('steps') or [])[:STEP_LIMIT]]
    subagents = agent.get('subagents') or []
    item['subagents'] = {'running': sum(1 for sub in subagents if sub.get('running')), 'total': len(subagents)}
    return item


def snapshot(now=None):
    now = time.time() if now is None else now
    with LOCK:
        data = agents.read_json(agents.SNAPSHOT)
        if now - float(data.get('at') or 0) > STALE:
            data = agents.collect()
    return {'at': data.get('at'), 'agents': [public(agent) for agent in data.get('agents') or []]}


class Handler(BaseHTTPRequestHandler):
    server_version = 'MakoAgents/1'

    def reply(self, status, body):
        payload = json.dumps(body, separators=(',', ':')).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802 (http.server names)
        if self.path.split('?')[0] != '/v0/agents':
            return self.reply(404, {'error': 'not found'})
        key = management_key()
        sent = self.headers.get('Authorization', '').removeprefix('Bearer ').strip()
        if not key or not hmac.compare_digest(sent.encode(), key.encode()):
            return self.reply(401, {'error': 'missing or wrong management key'})
        try:
            return self.reply(200, snapshot())
        except Exception as error:  # a broken snapshot must not take the server down
            return self.reply(500, {'error': type(error).__name__})

    def log_message(self, format, *args):  # noqa: A002
        # Paths and status codes only; the Authorization header never reaches the log.
        print(f'{self.address_string()} {format % args}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--host', default='127.0.0.1', help='address to listen on (0.0.0.0 for the LAN)')
    parser.add_argument('--port', type=int, default=8318)
    args = parser.parse_args()
    if not management_key():
        raise SystemExit('Proxy management key not found; set it in Mako settings.')
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'Serving agents on http://{args.host}:{args.port}/v0/agents', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
