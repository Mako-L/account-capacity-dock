#!/usr/bin/env python3
"""Read account capacity without refreshing or changing provider credentials."""
import base64
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HOME = Path.home()
CACHE = HOME / 'Library/Application Support/Mako Capacity/snapshot.json'
SWITCHER = HOME / 'Library/Application Support/dev.hoangphan.AI-Account-Switcher'


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def iso_timestamp(value):
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, AttributeError):
        return None


def percentage(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return min(100.0, max(0.0, float(value))) if math.isfinite(value) else None


def window(label, used, reset=None):
    value = percentage(used)
    return None if value is None else {'label': label, 'used': value, 'resetAt': iso_timestamp(reset)}


def claude_windows(data):
    labels = {'five_hour': '5-hour', 'seven_day': 'Weekly', 'seven_day_opus': 'Weekly · Opus',
              'seven_day_sonnet': 'Weekly · Sonnet', 'seven_day_oauth_apps': 'Weekly · OAuth'}
    result = []
    for key, label in labels.items():
        row = data.get(key)
        if isinstance(row, dict):
            item = window(label, row.get('utilization'), row.get('resets_at'))
            if item:
                result.append(item)
    for row in data.get('limits') or []:
        if row.get('kind') == 'weekly_scoped':
            name = ((row.get('scope') or {}).get('model') or {}).get('display_name')
            if name and not any(w['label'] == 'Weekly · ' + name for w in result):
                item = window('Weekly · ' + name, row.get('percent'), row.get('resets_at'))
                if item:
                    result.append(item)
    return result


def codex_windows(data):
    result = []
    rate = data.get('rate_limit') or {}
    candidates = [rate.get('primary_window'), rate.get('secondary_window')]
    if 'used_percent' in rate:
        candidates.append(rate)
    secondary = data.get('secondary_rate_limit') or {}
    candidates += [secondary.get('primary_window'), secondary.get('secondary_window')]
    for row in candidates:
        if not isinstance(row, dict):
            continue
        seconds = row.get('limit_window_seconds')
        label = 'Weekly' if seconds == 604800 else '5-hour' if seconds == 18000 else 'Daily' if seconds == 86400 else 'Quota'
        item = window(label, row.get('used_percent'), row.get('reset_at'))
        if item and item not in result:
            result.append(item)
    return sorted(result, key=lambda w: w['label'] == 'Weekly')


def cursor_windows(data, sand=None):
    plan = data.get('planUsage') or {}
    try:
        reset = float(data['billingCycleEnd']) / 1000
    except (KeyError, TypeError, ValueError):
        reset = None
    result = []
    for key, label, message in [
            ('autoPercentUsed', 'Cursor Models', 'autoModelSelectedDisplayMessage'),
            ('apiPercentUsed', 'Other Models', 'namedModelSelectedDisplayMessage')]:
        match = re.search(r"You've used (\d+)%", data.get(message) or '')
        raw = int(match.group(1)) if match else plan.get(key)
        # Match LLimit's display rounding, including positive usage below 1%.
        used = percentage(raw)
        if used is not None:
            used = min(100, max(1, math.floor(used + 0.5))) if used > 0 else 0
        item = window(label, used, reset)
        if item:
            result.append(item)
    if sand:
        used = percentage(sand.get('usagePercent'))
        if used is not None:
            used = max(1, math.floor(used + 0.5)) if used > 0 else 0
            result.append(window('Grok Bot', used, sand.get('nextResetTimestampUtc')))
    spend = data.get('spendLimitUsage') or {}
    used, limit = spend.get('individualUsed', 0), spend.get('individualLimit')
    if percentage(used) is not None and isinstance(limit, (int, float)) and limit > 0:
        item = window('On-demand', used / limit * 100, reset)
        item['detail'] = '${:g} / ${:g}'.format(used / 100, limit / 100)
        result.append(item)
    return result


def account(provider, email, identity, title=None, plan='', source=''):
    digest = hashlib.sha256((provider + ':' + str(identity)).encode()).hexdigest()[:16]
    return {'id': digest, 'provider': provider, 'email': email or 'Unknown account',
            'title': title or (email or 'Unknown account').split('@')[0], 'plan': plan,
            'source': source, 'status': 'unknown', 'message': '', 'windows': [],
            'fetchedAt': None, 'nextPollAt': 0}


def cursor_cli_account():
    info = read_json(HOME / '.cursor/cli-config.json').get('authInfo') or {}
    email = info.get('email') or 'Cursor CLI account'
    entry = account('Cursor', email, 'cli:' + (info.get('authId') or 'signed-out'), source='Cursor CLI')
    request = None
    try:
        if os.environ.get('AGENT_CLI_CREDENTIAL_STORE') == 'memory':
            token = ''
        elif os.environ.get('AGENT_CLI_CREDENTIAL_STORE') == 'file':
            token = read_json(HOME / '.cursor/auth.json').get('accessToken') or ''
        else:
            result = subprocess.run(
                ['/usr/bin/security', 'find-generic-password', '-a', 'cursor-user',
                 '-s', 'cursor-access-token', '-w'],
                capture_output=True, text=True, timeout=5, check=True)
            token = result.stdout.strip()
        claims = json.loads(base64.urlsafe_b64decode(token.split('.')[1] + '==='))
        subject = claims['sub']
        # Cached CLI profile information can outlive a login. Never label another
        # token's usage with that stale email or reuse the previous account's quota.
        if info.get('authId') != subject:
            email = 'Cursor CLI account'
        entry = account('Cursor', email, 'cli:' + subject, source='Cursor CLI')
        if claims.get('exp', 0) > time.time() + 60:
            request = ('https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage', {
                'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                'Connect-Protocol-Version': '1'})
    except (OSError, subprocess.SubprocessError, ValueError, IndexError, KeyError, TypeError):
        pass
    return entry, request


def discover():
    result = []
    sequence = read_json(HOME / '.claude-swap-backup/sequence.json').get('accounts', {})
    claude = {}
    for slot, row in sequence.items():
        identity = row.get('organizationUuid') or row.get('email') or slot
        title = None
        claude[identity] = (account('Claude', row.get('email'), identity, title, source='Claude saved account'), None)
    for path in sorted((HOME / 'claude-proxy/auths').glob('*.json')):
        row = read_json(path)
        if row.get('type') != 'claude':
            continue
        identity = row.get('organization_uuid') or row.get('email') or path.name
        old = claude.get(identity)
        entry = old[0] if old else account('Claude', row.get('email'), identity)
        entry['source'] = 'Claude proxy'
        entry['plan'] = row.get('organization_name') or ''
        token = row.get('access_token')
        previous_token = old[1] if old else None
        if token and (not previous_token or row.get('refresh_token')):
            claude[identity] = (entry, ('https://api.anthropic.com/api/oauth/usage', {
                'Authorization': 'Bearer ' + token, 'anthropic-beta': 'oauth-2025-04-20'}))
        else:
            claude[identity] = old or (entry, None)
    result.extend(claude.values())
    codex = {}
    rows = read_json(HOME / 'codex-proxy/data/accounts.json').get('accounts', [])
    for row in rows:
        identity = row.get('accountId') or row.get('email') or row.get('id')
        label = {'pro': 'Pro', 'prolite': 'Pro Lite', 'promax': 'Pro Max'}.get(row.get('planType'), row.get('planType') or '')
        entry = account('Codex', row.get('email'), identity, title=label or None, plan=label, source='Codex proxy')
        entry['windows'] = codex_windows(row.get('cachedQuota') or {})
        entry['fetchedAt'] = iso_timestamp(row.get('quotaFetchedAt'))
        headers = {'Authorization': 'Bearer ' + row['token']} if row.get('token') else {}
        if row.get('accountId'):
            headers['ChatGPT-Account-Id'] = row['accountId']
        codex[identity] = (entry, ('https://chatgpt.com/backend-api/wham/usage', headers) if headers else None)
    result.extend(codex.values())
    result.append(cursor_cli_account())
    return result


def fetch(item, previous, force=False):
    entry, request = item
    now = time.time()
    old = previous.get(entry['id'])
    if request is None:
        entry.update(status='loginRequired', message='Reconnect this account to read capacity.', windows=[], nextPollAt=now + 300)
        return entry
    if old:
        for key in ('windows', 'status', 'message', 'fetchedAt', 'nextPollAt', 'plan'):
            if key in old:
                entry[key] = old[key]
        if now < old.get('nextPollAt', 0) and (not force or old.get('status') == 'rateLimited'):
            return entry
    entry['nextPollAt'] = now + 300
    try:
        url, headers = request
        headers = dict(headers, **{'Accept': 'application/json', 'User-Agent': 'CodeBurn'})
        body = b'{}' if entry['provider'] == 'Cursor' else None
        response = urllib.request.urlopen(urllib.request.Request(url, headers=headers, data=body), timeout=12)
        with response:
            data = json.load(response)
        if entry['provider'] == 'Claude':
            entry['windows'] = claude_windows(data)
        elif entry['provider'] == 'Codex':
            entry['windows'] = codex_windows(data)
            entry['plan'] = {'pro': 'Pro', 'prolite': 'Pro Lite', 'promax': 'Pro Max'}.get(data.get('plan_type'), data.get('plan_type') or entry['plan'])
        else:
            sand = None
            try:
                sand_url = 'https://api2.cursor.sh/aiserver.v1.DashboardService/GetSandUsageStatus'
                with urllib.request.urlopen(urllib.request.Request(sand_url, headers=headers, data=b'{}'), timeout=10) as response:
                    sand = json.load(response)
            except (OSError, ValueError, TimeoutError):
                pass
            entry['windows'] = cursor_windows(data, sand)
            if sand:
                entry['plan'] = sand.get('cursorPlanName') or entry['plan']
        entry.update(status='live' if entry['windows'] else 'unknown', fetchedAt=now, message='')
        if entry['provider'] == 'Cursor' and sand is None:
            entry['message'] = 'Grok Bot usage unavailable; retrying later.'
        if not entry['windows']:
            entry['message'] = 'The provider did not return a measurable quota.'
        if entry['provider'] == 'Cursor' and entry['plan'].lower() == 'free':
            entry['message'] = 'Free plan · no paid usage allowance'
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            entry.update(status='loginRequired', message='Sign in again in the provider app or proxy.', windows=[])
        elif error.code == 429:
            retry = error.headers.get('Retry-After')
            try:
                delay = max(300, float(retry))
            except (TypeError, ValueError):
                delay = 300
            entry.update(status='rateLimited', message='Usage check throttled; retrying later.', nextPollAt=now + delay)
        else:
            entry.update(status='stale' if entry['windows'] else 'unavailable', message=f'Provider unavailable (HTTP {error.code}).')
    except (OSError, ValueError, TimeoutError):
        entry.update(status='stale' if entry['windows'] else 'unavailable', message='Usage check unavailable; retrying later.')
    return entry


def collect(force=False):
    cached = read_json(CACHE)
    previous = {a['id']: a for a in cached.get('accounts', [])}
    discovered = discover()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(lambda item: fetch(item, previous, force), discovered))
    result.sort(key=lambda a: (['Claude', 'Codex', 'Cursor'].index(a['provider']), a['title'].lower()))
    snapshot = {'updatedAt': time.time(), 'accounts': result}
    CACHE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    CACHE.parent.chmod(0o700)
    handle, name = tempfile.mkstemp(dir=CACHE.parent, prefix='.snapshot-')
    try:
        with os.fdopen(handle, 'w') as stream:
            json.dump(snapshot, stream, separators=(',', ':'))
        os.replace(name, CACHE)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return snapshot


if __name__ == '__main__':
    print(json.dumps(collect('--refresh' in sys.argv), separators=(',', ':')))
