"""Read only CodeBurn's local, provider-scoped token/cost summaries."""
import datetime as dt
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import sys
from platform_paths import cache_dir

PROVIDERS = {'Claude': 'claude', 'Codex': 'codex', 'Cursor': 'cursor-agent'}
TOKEN_FIELDS = ('inputTokens', 'outputTokens', 'cacheReadTokens', 'cacheWriteTokens')


def read_json(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def summarize(payload, provider, now):
    current = payload.get('current')
    if not isinstance(current, dict):
        raise ValueError('Missing CodeBurn current summary')
    counters = {key: number(current.get(key)) for key in TOKEN_FIELDS}
    # Unknown counters must not turn into zero or a deceptively complete total.
    tokens = number(sum(counters.values())) if all(value is not None for value in counters.values()) else None
    partial = payload.get('hydration', {}).get('complete') is False
    return dict(counters, provider=provider, tokens=tokens, costUsd=number(current.get('cost')),
                estimated=(number(current.get('estimatedCostUSD')) or 0) > 0,
                unpricedModels=len(current.get('unpricedModels') or []),
                status='partial' if partial else 'stale' if payload.get('stale') else 'live',
                fetchedAt=now, message='')


def collect_usage(force=False):
    home = Path.home()
    setup = Path(os.environ.get('MAKO_CAPACITY_HOME', home / '.mako-capacity'))
    settings = read_json(setup / 'settings.json')
    command = settings.get('CODEBURN_COMMAND')
    if not (isinstance(command, list) and len(command) == 2 and all(isinstance(item, str) for item in command)):
        executable = shutil.which('codeburn')
        command = [executable] if executable else None
    cache = cache_dir() / 'codeburn-usage.json'
    old = read_json(cache)
    day = dt.date.today().isoformat()
    now = time.time()
    if old.get('day') == day and now < old.get('nextPollAt', 0) and not force:
        return old.get('providers', {})

    providers = {}
    requests = [{'id': label, 'args': ['status', '--format', 'menubar-json', '--scope', 'local',
                                     '--provider', identifier, '--period', 'today',
                                     '--no-optimize', '--no-timeline']}
                for label, identifier in PROVIDERS.items()]
    if command:
        try:
            # One process shares CodeBurn's parse caches across the three queries.
            # Progressive mode is safe because the UI marks partial totals.
            result = subprocess.run(command + ['serve', '--stdio'],
                                    input=''.join(json.dumps(request) + '\n' for request in requests),
                                    capture_output=True, text=True, timeout=600, check=True,
                                    env=dict(os.environ, CODEBURN_SERVE_PROGRESSIVE='1',
                                             CODEBURN_SERVE_DRAIN_MS='600000',
                                             CODEBURN_CACHE_DIR=str(setup / 'codeburn-cache')))
            for line in result.stdout.splitlines():
                response = json.loads(line)
                provider = response.get('id')
                if provider in PROVIDERS and response.get('ok') and response.get('output'):
                    providers[provider] = summarize(json.loads(response['output']), provider, now)
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
            pass
    for provider in PROVIDERS:
        if provider not in providers:
            previous = old.get('providers', {}).get(provider, {}) if old.get('day') == day else {}
            providers[provider] = dict(previous, status='stale' if previous.get('fetchedAt') else 'unavailable',
                                       message='CodeBurn usage unavailable; retrying later.' if command else 'Install CodeBurn with the setup CLI.')
    cache.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle, name = tempfile.mkstemp(dir=cache.parent, prefix='.codeburn-usage-')
    try:
        with os.fdopen(handle, 'w') as stream:
            json.dump({'day': day, 'nextPollAt': now + 300, 'providers': providers}, stream, separators=(',', ':'))
        os.replace(name, cache)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return providers


if __name__ == '__main__':
    print(json.dumps(collect_usage('--refresh' in sys.argv), separators=(',', ':')))
