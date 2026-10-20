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
import urllib.parse
import urllib.request
from codeburn_usage import collect_usage
from platform_paths import cache_dir

HOME = Path.home()
CACHE = cache_dir() / 'snapshot.json'
SWITCHER = HOME / 'Library/Application Support/dev.hoangphan.AI-Account-Switcher'


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def setup_dir():
    return Path(os.environ.get('MAKO_CAPACITY_HOME', HOME / '.mako-capacity'))


def setting(key, default):
    return os.environ.get(key) or read_json(setup_dir() / 'settings.json').get(key) or default


def proxy_path(key, legacy):
    return Path(setting(key, HOME / legacy)).expanduser()


def proxy_base():
    """CLIProxyAPI address: PROXY_URL for a proxy on another machine, else the local Docker port."""
    return setting('PROXY_URL', '').rstrip('/') or 'http://127.0.0.1:' + str(setting('CLAUDE_PROXY_PORT', '8317'))


def management(path, method='GET'):
    """Call the CLIProxyAPI management API and return its JSON reply."""
    key = setting('PROXY_MANAGEMENT_KEY', '')
    if not key:
        env = proxy_path('CLAUDE_PROXY_DIR', 'claude-proxy') / 'management.env'
        found = re.search(r'^MANAGEMENT_PASSWORD=(.+)$', env.read_text() if env.exists() else '', re.M)
        key = found.group(1).strip() if found else ''
    if not key:
        raise RuntimeError('Proxy management key not found; set it in Mako settings.')
    request = urllib.request.Request(proxy_base() + '/v0/management/' + path, method=method,
                                     headers={'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.load(response)


WARNINGS = []  # ponytail: module-level, one collector run per process.


def remote_auths():
    """Mirror a remote proxy's login files into a private folder and return it.

    Only files whose modification time changed are downloaded again. If the
    proxy is unreachable, the last mirror stays in use.
    """
    mirror = setup_dir() / 'remote-auths'
    mirror.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        files = management('auth-files').get('files', [])
    except urllib.error.HTTPError as error:
        WARNINGS.append(f'Proxy at {proxy_base()} refused the management key (HTTP {error.code}).')
        return mirror
    except (OSError, ValueError, RuntimeError) as error:
        WARNINGS.append(f'Proxy at {proxy_base()} is not reachable; showing the last known logins.')
        return mirror
    index = read_json(mirror / '.index.json')
    names = set()
    for row in files:
        name = row.get('name') or ''
        if not name.endswith('.json') or '/' in name or row.get('type') not in ('claude', 'codex'):
            continue
        names.add(name)
        if index.get(name) != row.get('modtime') or not (mirror / name).exists():
            try:
                write_private(mirror / name, management('auth-files/download?name=' + urllib.parse.quote(name)))
                index[name] = row.get('modtime')
            except (OSError, ValueError, RuntimeError):
                continue
    for path in mirror.glob('*.json'):
        if path.name not in names:
            path.unlink()
    write_private(mirror / '.index.json', {name: index[name] for name in names if name in index})
    return mirror


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


PLANS = {'pro': 'Pro', 'prolite': 'Pro Lite', 'promax': 'Pro Max'}


def account(provider, email, identity, title=None, plan='', source=''):
    digest = hashlib.sha256((provider + ':' + str(identity)).encode()).hexdigest()[:16]
    return {'id': digest, 'provider': provider, 'email': email or 'Unknown account',
            'title': title or (email or 'Unknown account').split('@')[0], 'plan': plan,
            'source': source, 'status': 'unknown', 'message': '', 'windows': [],
            'fetchedAt': None, 'nextPollAt': 0, 'onDemandUsd': None}


def cursor_cli_account():
    cursor_dir = proxy_path('CURSOR_DIR', '.cursor')
    info = read_json(cursor_dir / 'cli-config.json').get('authInfo') or {}
    email = info.get('email') or 'Cursor CLI account'
    entry = account('Cursor', email, 'cli:' + (info.get('authId') or 'signed-out'), source='Cursor CLI')
    request = None
    try:
        if os.environ.get('AGENT_CLI_CREDENTIAL_STORE') == 'memory':
            token = ''
        elif os.environ.get('AGENT_CLI_CREDENTIAL_STORE') == 'file' or sys.platform != 'darwin':
            token = read_json(cursor_dir / 'auth.json').get('accessToken') or ''
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
    saved = {}
    for slot, row in sequence.items():
        identity = row.get('organizationUuid') or row.get('email') or slot
        title = row.get('title') or row.get('name')
        saved[identity] = (account('Claude', row.get('email'), identity, title, source='Claude saved account'), None)
    auths = remote_auths() if setting('PROXY_URL', '') else proxy_path('CLAUDE_PROXY_DIR', 'claude-proxy') / 'auths'
    # A proxy deletion must not resurrect an account from the legacy backup.
    claude = {} if auths.is_dir() else saved.copy()
    for path in sorted(auths.glob('*.json')):
        row = read_json(path)
        if row.get('type') != 'claude':
            continue
        identity = row.get('organization_uuid') or row.get('email') or path.name
        old = claude.get(identity) or saved.get(identity)
        entry = old[0] if old else account('Claude', row.get('email'), identity)
        entry['source'] = 'CLI proxy'
        entry['proxyRef'] = path.name
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
    for path in sorted(auths.glob('*.json')):
        row = read_json(path)
        if row.get('type') != 'codex':
            continue
        identity = row.get('account_id') or row.get('email') or path.name
        label = PLANS.get(row.get('plan_type'), row.get('plan_type') or '')
        entry = account('Codex', row.get('email'), identity, title=label or None, plan=label, source='CLI proxy')
        entry['proxyRef'] = path.name
        headers = {'Authorization': 'Bearer ' + row['access_token']} if row.get('access_token') else {}
        if headers and row.get('account_id'):
            headers['ChatGPT-Account-Id'] = row['account_id']
        codex[identity] = (entry, ('https://chatgpt.com/backend-api/wham/usage', headers) if headers else None)
    # The separate Codex proxy is legacy: read it only while CLIProxyAPI has no Codex login.
    # A remote proxy replaces the default local folder; an explicit CODEX_PROXY_DIR still applies.
    legacy = not codex and (not setting('PROXY_URL', '') or setting('CODEX_PROXY_DIR', ''))
    rows = read_json(proxy_path('CODEX_PROXY_DIR', 'codex-proxy') / 'data/accounts.json').get('accounts', []) if legacy else []
    for row in rows:
        identity = row.get('accountId') or row.get('email') or row.get('id')
        label = PLANS.get(row.get('planType'), row.get('planType') or '')
        entry = account('Codex', row.get('email'), identity, title=label or None, plan=label, source='Codex proxy')
        entry['windows'] = codex_windows(row.get('cachedQuota') or {})
        entry['fetchedAt'] = iso_timestamp(row.get('quotaFetchedAt'))
        entry['proxyRef'] = row.get('id')
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
        entry.update(status='loginRequired', message='Reconnect this account to read capacity.', windows=[], onDemandUsd=None, nextPollAt=now + 300)
        return entry
    if old:
        for key in ('windows', 'status', 'message', 'fetchedAt', 'nextPollAt', 'plan', 'onDemandUsd'):
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
            entry['plan'] = PLANS.get(data.get('plan_type'), data.get('plan_type') or entry['plan'])
        else:
            sand = None
            try:
                sand_url = 'https://api2.cursor.sh/aiserver.v1.DashboardService/GetSandUsageStatus'
                with urllib.request.urlopen(urllib.request.Request(sand_url, headers=headers, data=b'{}'), timeout=10) as response:
                    sand = json.load(response)
            except (OSError, ValueError, TimeoutError):
                pass
            entry['windows'] = cursor_windows(data, sand)
            spend = data.get('spendLimitUsage') or {}
            spent = spend.get('individualUsed')
            entry['onDemandUsd'] = spent / 100 if isinstance(spent, (int, float)) and not isinstance(spent, bool) and math.isfinite(spent) and spent >= 0 else None
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
            entry.update(status='loginRequired', message='Sign in again in the provider app or proxy.', windows=[], onDemandUsd=None)
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


def write_private(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.stem + '-')
    try:
        with os.fdopen(handle, 'w') as stream:
            json.dump(data, stream, separators=(',', ':'))
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def delete_from_proxy(entry):
    """Remove an account through its proxy's API so the running proxy forgets it too."""
    ref = entry.get('proxyRef')
    if entry['source'] == 'CLI proxy' and ref:
        try:
            management('auth-files?name=' + urllib.parse.quote(ref), method='DELETE')
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'The proxy refused the delete (HTTP {error.code}).') from error
        except (OSError, ValueError) as error:
            raise RuntimeError('The proxy is not reachable; start it and try again.') from error
        return
    if entry['provider'] == 'Codex' and ref:
        config = proxy_path('CODEX_PROXY_DIR', 'codex-proxy') / 'data/local.yaml'
        key = re.search(r'^\s*proxy_api_key:\s*["\']?([^"\'\s#]+)', config.read_text() if config.exists() else '', re.M)
        headers = {'Authorization': 'Bearer ' + key.group(1)} if key and key.group(1) != 'null' else {}
        url = 'http://127.0.0.1:{}/auth/accounts/{}'.format(
            setting('CODEX_PROXY_PORT', '8080'), urllib.parse.quote(ref, safe=''))
    else:
        raise RuntimeError('This account has no proxy entry to delete; hide it instead.')
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers=headers, method='DELETE'), timeout=12).close()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'{entry["provider"]} proxy refused the delete (HTTP {error.code}).') from error
    except (OSError, ValueError) as error:
        raise RuntimeError(f'{entry["provider"]} proxy is not reachable; start it and try again.') from error


def change_account(action, account_id):
    """Hide, restore, or permanently delete one account by its snapshot id."""
    hidden = read_json(setup_dir() / 'hidden.json')
    if action == 'restore':
        hidden.pop(account_id, None)
    else:
        entry = next((e for e, _ in discover() if e['id'] == account_id), None)
        if entry is None:
            raise RuntimeError('Account not found; it may already be removed.')
        if action == 'delete':
            delete_from_proxy(entry)
            hidden.pop(account_id, None)
        else:
            hidden[account_id] = f"{entry['provider']} · {entry['title']} · {entry['email']}"
    write_private(setup_dir() / 'hidden.json', hidden)


def collect(force=False, include_usage=True):
    cached = read_json(CACHE)
    previous = {a['id']: a for a in cached.get('accounts', [])}
    hidden = read_json(setup_dir() / 'hidden.json')
    discovered = [item for item in discover() if item[0]['id'] not in hidden]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(lambda item: fetch(item, previous, force), discovered))
    result.sort(key=lambda a: (['Claude', 'Codex', 'Cursor'].index(a['provider']), a['title'].lower()))
    if include_usage:
        usage = collect_usage(force)
    else:
        cached_usage = read_json(cache_dir() / 'codeburn-usage.json')
        usage = cached_usage.get('providers', {}) if cached_usage.get('day') == dt.date.today().isoformat() else {}
    for entry in result:
        entry['localUsage'] = usage.get(entry['provider'], {'status': 'partial', 'message': 'Indexing local usage…'})
    snapshot = {'updatedAt': time.time(), 'accounts': result, 'hidden': hidden,
                'warning': ' '.join(WARNINGS) or None}
    write_private(CACHE, snapshot)
    CACHE.parent.chmod(0o700)
    return snapshot


if __name__ == '__main__':
    for flag in ('--hide', '--restore', '--delete'):
        if flag in sys.argv:
            try:
                change_account(flag[2:], sys.argv[sys.argv.index(flag) + 1])
            except (RuntimeError, IndexError, OSError) as error:
                print(error, file=sys.stderr)
                sys.exit(1)
    print(json.dumps(collect('--refresh' in sys.argv, '--skip-usage' not in sys.argv), separators=(',', ':')))
