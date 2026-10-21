import importlib.util
import base64
import io
import os
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import urllib.error
import urllib.parse

spec = importlib.util.spec_from_file_location('collector', Path(__file__).parents[1] / 'collector.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class CapacityParsingTests(unittest.TestCase):
    def test_discovery_reads_installed_proxy_paths_without_shell_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            setup = home / '.mako-capacity'
            setup.mkdir()
            claude = home / 'custom claude/auths'
            codex = home / 'custom codex/data'
            claude.mkdir(parents=True)
            codex.mkdir(parents=True)
            (setup / 'settings.json').write_text(json.dumps({
                'CLAUDE_PROXY_DIR': str(claude.parent), 'CODEX_PROXY_DIR': str(codex.parent)}))
            (claude / 'account.json').write_text(json.dumps({
                'type': 'claude', 'organization_uuid': 'org', 'email': 'claude@example.test',
                'access_token': 'private-claude'}))
            (codex / 'accounts.json').write_text(json.dumps({'accounts': [{
                'accountId': 'codex', 'email': 'codex@example.test', 'token': 'private-codex'}]}))
            with patch.object(collector, 'HOME', home), patch.dict(collector.os.environ, {}, clear=True), \
                    patch.object(collector, 'cursor_cli_account', return_value=(collector.account('Cursor', '', 'cli'), None)):
                rows = [entry for entry, _ in collector.discover()]
            self.assertEqual([entry['provider'] for entry in rows], ['Claude', 'Codex', 'Cursor'])
            self.assertEqual(rows[0]['email'], 'claude@example.test')
            self.assertEqual(rows[1]['email'], 'codex@example.test')
            self.assertNotIn('private-', json.dumps(rows))

    def test_cursor_cli_uses_cli_identity_and_keychain_not_editor(self):
        claims = {'sub': 'auth0|cli-user', 'exp': collector.time.time() + 3600}
        token = 'header.' + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode() + '.signature'
        with patch.object(collector, 'read_json', return_value={'authInfo': {'email': 'cli@example.test', 'authId': claims['sub']}}), \
                patch.object(collector.sys, 'platform', 'darwin'), \
                patch.dict(collector.os.environ, {'AGENT_CLI_CREDENTIAL_STORE': 'default'}), \
                patch.object(collector.subprocess, 'run', return_value=SimpleNamespace(stdout=token)) as keychain:
            entry, request = collector.cursor_cli_account()
        self.assertEqual(entry['email'], 'cli@example.test')
        self.assertEqual(entry['source'], 'Cursor CLI')
        self.assertEqual(request[1]['Authorization'], 'Bearer ' + token)
        self.assertTrue(request[0].endswith('/GetCurrentPeriodUsage'))
        self.assertIn('cursor-access-token', keychain.call_args.args[0])
        self.assertNotIn(token, json.dumps(entry))

    def test_cursor_cli_missing_login_clears_cached_quota_immediately(self):
        with patch.object(collector.subprocess, 'run', side_effect=OSError), \
                patch.object(collector, 'read_json', return_value={}):
            entry, request = collector.cursor_cli_account()
        old = dict(entry, status='live', windows=[{'label': 'Monthly', 'used': 60}], nextPollAt=collector.time.time()+300)
        result = collector.fetch((entry, request), {entry['id']: old})
        self.assertEqual(result['status'], 'loginRequired')
        self.assertEqual(result['windows'], [])

    def test_cursor_cli_file_store_does_not_use_stale_profile_or_keychain(self):
        token = 'header.' + base64.urlsafe_b64encode(json.dumps({'sub': 'auth0|new-user', 'exp': collector.time.time()+3600}).encode()).decode() + '.signature'
        with patch.dict(collector.os.environ, {'AGENT_CLI_CREDENTIAL_STORE': 'file'}), \
                patch.object(collector, 'read_json', side_effect=[{}, {'authInfo': {'email': 'old@example.test', 'authId': 'auth0|old-user'}}, {'accessToken': token}]), \
                patch.object(collector.subprocess, 'run') as keychain:
            entry, request = collector.cursor_cli_account()
        keychain.assert_not_called()
        self.assertEqual(entry['email'], 'Cursor CLI account')
        self.assertEqual(entry['id'], collector.account('Cursor', '', 'cli:auth0|new-user')['id'])
        self.assertIsNotNone(request)

    def test_unknown_and_boolean_values_do_not_become_zero_capacity(self):
        for value in (None, True, '0', float('nan'), float('inf')):
            self.assertIsNone(collector.percentage(value))
        self.assertEqual(collector.percentage(0), 0)
        self.assertEqual(collector.percentage(130), 100)

    def test_claude_includes_model_limit_and_inactive_zero_window(self):
        result = collector.claude_windows({
            'five_hour': {'utilization': 0, 'resets_at': None},
            'seven_day': {'utilization': 100, 'resets_at': '2026-10-04T13:00:00Z'},
            'limits': [{'kind': 'weekly_scoped', 'percent': 75,
                        'scope': {'model': {'display_name': 'Fable'}}, 'resets_at': None}],
        })
        self.assertEqual([(w['label'], w['used']) for w in result],
                         [('5-hour', 0), ('Weekly', 100), ('Weekly · Fable', 75)])
        self.assertIsNone(result[0]['resetAt'])
        self.assertEqual(result[1]['resetAt'], 1791118800)

    def test_codex_live_and_cached_payloads_preserve_the_window_duration(self):
        weekly = {'used_percent': 23, 'limit_window_seconds': 604800, 'reset_at': 1791418894}
        short = {'used_percent': 95, 'limit_window_seconds': 18000, 'reset_at': 1790870399}
        live = collector.codex_windows({'rate_limit': {'primary_window': weekly, 'secondary_window': short}})
        cached = collector.codex_windows({'rate_limit': weekly})
        self.assertEqual([(w['label'], w['used']) for w in live], [('5-hour', 95), ('Weekly', 23)])
        self.assertEqual(cached, [live[1]])

    def test_cursor_zero_usage_is_valid_but_missing_capacity_is_unknown(self):
        self.assertEqual(collector.cursor_windows({'planUsage': {}}), [])
        result = collector.cursor_windows({'planUsage': {'autoPercentUsed': 0}})
        self.assertEqual(result[0]['used'], 0)

    def test_cursor_matches_llimit_messages_grok_rounding_and_resets(self):
        result = collector.cursor_windows({
            'billingCycleEnd': '1791989574000',
            'planUsage': {'autoPercentUsed': 56.586, 'apiPercentUsed': 100},
            'autoModelSelectedDisplayMessage': "You've used 60% of your included total usage",
            'namedModelSelectedDisplayMessage': "You've used 100% of your included API usage",
            'spendLimitUsage': {'individualLimit': 2000, 'individualUsed': 500},
        }, {'usagePercent': 1.767891, 'nextResetTimestampUtc': '2026-10-05T15:26:53.586Z'})
        self.assertEqual([(w['label'], w['used']) for w in result],
                         [('Cursor Models', 60), ('Other Models', 100), ('Grok Bot', 2), ('On-demand', 25)])
        self.assertEqual(result[0]['resetAt'], 1791989574)
        self.assertNotEqual(result[2]['resetAt'], result[0]['resetAt'])
        self.assertEqual(result[3]['detail'], '$5 / $20')

    def test_cursor_positive_fractional_usage_is_visible(self):
        result = collector.cursor_windows({'planUsage': {'autoPercentUsed': 0.2, 'apiPercentUsed': None}})
        self.assertEqual([(w['label'], w['used']) for w in result], [('Cursor Models', 1)])

    def test_cursor_fetch_posts_dashboard_and_keeps_models_when_grok_unavailable(self):
        entry = collector.account('Cursor', 'cli@example.test', 'cli-user')
        response = unittest.mock.MagicMock()
        response.read.return_value = json.dumps({'planUsage': {'autoPercentUsed': 60}})
        with patch.object(collector.urllib.request, 'urlopen', side_effect=[response, TimeoutError]) as requests:
            result = collector.fetch((entry, ('https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage', {})), {}, True)
        self.assertEqual(result['status'], 'live')
        self.assertEqual(result['windows'][0]['used'], 60)
        self.assertIn('Grok Bot usage unavailable', result['message'])
        self.assertEqual(requests.call_args_list[0].args[0].data, b'{}')
        self.assertTrue(requests.call_args_list[1].args[0].full_url.endswith('/GetSandUsageStatus'))

    def test_transient_failure_retains_cached_quota_with_stale_status(self):
        entry = collector.account('Codex', 'test@example.test', 'test')
        old = dict(entry, windows=[{'label': 'Weekly', 'used': 45, 'resetAt': None}], fetchedAt=100, nextPollAt=0)
        with patch.object(collector.urllib.request, 'urlopen', side_effect=TimeoutError):
            result = collector.fetch((entry, ('https://example.test', {})), {entry['id']: old}, True)
        self.assertEqual(result['status'], 'stale')
        self.assertEqual(result['windows'][0]['used'], 45)
        self.assertEqual(result['fetchedAt'], 100)

    def test_authentication_failure_clears_cached_capacity(self):
        entry = collector.account('Claude', 'test@example.test', 'test')
        old = dict(entry, windows=[{'label': 'Weekly', 'used': 45, 'resetAt': None}], nextPollAt=0)
        error = urllib.error.HTTPError('https://example.test', 401, 'Unauthorized', {}, None)
        with patch.object(collector.urllib.request, 'urlopen', side_effect=error):
            result = collector.fetch((entry, ('https://example.test', {})), {entry['id']: old}, True)
        self.assertEqual(result['status'], 'loginRequired')
        self.assertEqual(result['windows'], [])

    def test_manual_refresh_respects_rate_limit_backoff(self):
        entry = collector.account('Claude', 'test@example.test', 'test')
        old = dict(entry, status='rateLimited', nextPollAt=collector.time.time() + 3600)
        with patch.object(collector.urllib.request, 'urlopen') as request:
            result = collector.fetch((entry, ('https://example.test', {})), {entry['id']: old}, True)
        request.assert_not_called()
        self.assertEqual(result['status'], 'rateLimited')

    def test_discovery_deduplicates_proxy_credentials_and_never_emits_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / '.claude-swap-backup').mkdir()
            (home / '.claude-swap-backup/sequence.json').write_text(json.dumps({'accounts': {
                '1': {'organizationUuid': 'org', 'email': 'test@example.test'},
                '4': {'organizationUuid': 'other', 'email': 'offline@example.test'},
            }}))
            auths = home / 'claude-proxy/auths'
            auths.mkdir(parents=True)
            for name, refresh in [('trial', ''), ('dedicated', 'private-refresh')]:
                (auths / (name + '.json')).write_text(json.dumps({'type': 'claude', 'organization_uuid': 'org',
                    'email': 'test@example.test', 'access_token': 'private-access', 'refresh_token': refresh}))
            with patch.object(collector, 'HOME', home), patch.object(collector.subprocess, 'run', side_effect=OSError):
                discovered = collector.discover()
            rows = [row for row, _ in discovered if row['provider'] == 'Claude']
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['email'], 'test@example.test')
            self.assertNotIn('private-access', json.dumps(rows))
            self.assertNotIn('private-refresh', json.dumps(rows))

    def test_proxy_deletion_removes_saved_and_cached_account_from_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            backup = home / '.claude-swap-backup'
            backup.mkdir()
            (backup / 'sequence.json').write_text(json.dumps({'accounts': {
                '1': {'organizationUuid': 'org', 'email': 'test@example.test', 'title': 'Work'},
            }}))
            auths = home / 'claude-proxy/auths'
            auths.mkdir(parents=True)
            credential = auths / 'account.json'
            credential.write_text(json.dumps({'type': 'claude', 'organization_uuid': 'org',
                                             'email': 'test@example.test'}))
            cache = home / 'cache/snapshot.json'
            with patch.object(collector, 'HOME', home), patch.object(collector, 'CACHE', cache), \
                    patch.dict(collector.os.environ, {}, clear=True), \
                    patch.object(collector, 'cache_dir', return_value=cache.parent), \
                    patch.object(collector, 'cursor_cli_account', return_value=(collector.account('Cursor', '', 'cli'), None)):
                before = collector.collect(include_usage=False)
                self.assertEqual([a['title'] for a in before['accounts'] if a['provider'] == 'Claude'], ['Work'])

                credential.unlink()
                after = collector.collect(include_usage=False)

            self.assertEqual([a['provider'] for a in after['accounts']], ['Cursor'])
            self.assertEqual(json.loads(cache.read_text())['accounts'], after['accounts'])
            self.assertTrue((backup / 'sequence.json').exists())

    def test_saved_accounts_remain_available_without_a_proxy_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            backup = home / '.claude-swap-backup'
            backup.mkdir()
            (backup / 'sequence.json').write_text(json.dumps({'accounts': {
                '1': {'organizationUuid': 'org', 'email': 'saved@example.test'},
            }}))
            with patch.object(collector, 'HOME', home), patch.dict(collector.os.environ, {}, clear=True), \
                    patch.object(collector, 'cursor_cli_account', return_value=(collector.account('Cursor', '', 'cli'), None)):
                rows = [entry for entry, _ in collector.discover() if entry['provider'] == 'Claude']

            self.assertEqual([row['email'] for row in rows], ['saved@example.test'])
            self.assertEqual(rows[0]['source'], 'Claude saved account')

    def test_codex_logins_in_cliproxy_replace_the_legacy_codex_proxy(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'claude-proxy/auths').mkdir(parents=True)
            (home / 'claude-proxy/auths/codex-a.json').write_text(json.dumps({
                'type': 'codex', 'account_id': 'acct', 'email': 'a@example.test', 'plan_type': 'promax',
                'access_token': 'private-codex'}))
            (home / 'codex-proxy/data').mkdir(parents=True)
            (home / 'codex-proxy/data/accounts.json').write_text(json.dumps({'accounts': [{
                'id': 'old', 'accountId': 'legacy', 'email': 'b@example.test', 'token': 'private-legacy'}]}))
            with patch.object(collector, 'HOME', home), patch.dict(collector.os.environ, {}, clear=True), \
                    patch.object(collector, 'cursor_cli_account', return_value=(collector.account('Cursor', '', 'cli'), None)):
                rows = [item for item in collector.discover() if item[0]['provider'] == 'Codex']

            self.assertEqual([(entry['title'], entry['proxyRef']) for entry, _ in rows], [('Pro Max', 'codex-a.json')])
            self.assertEqual(rows[0][1][1], {'Authorization': 'Bearer private-codex', 'ChatGPT-Account-Id': 'acct'})
            self.assertNotIn('private-', json.dumps([entry for entry, _ in rows]))

    def test_remote_proxy_logins_are_mirrored_privately_and_reused(self):
        files = {'claude-a.json': {'type': 'claude', 'organization_uuid': 'org', 'email': 'a@example.test',
                                   'access_token': 'private-claude', 'refresh_token': 'r'}}
        calls = []

        def urlopen(request, timeout):
            calls.append(request.full_url)
            self.assertEqual(request.get_header('Authorization'), 'Bearer remote-key')
            if request.full_url.endswith('/v0/management/auth-files'):
                body = {'files': [{'name': name, 'type': row['type'], 'modtime': 't1'} for name, row in files.items()]}
            else:
                body = files[urllib.parse.unquote(request.full_url.split('name=')[1])]
            return io.BytesIO(json.dumps(body).encode())
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            setup = home / '.mako-capacity'
            setup.mkdir()
            (setup / 'settings.json').write_text(json.dumps({
                'PROXY_URL': 'https://proxy.example.test:8317/', 'PROXY_MANAGEMENT_KEY': 'remote-key'}))
            with patch.object(collector, 'HOME', home), patch.dict(collector.os.environ, {}, clear=True), \
                    patch.object(collector.urllib.request, 'urlopen', side_effect=urlopen), \
                    patch.object(collector, 'cursor_cli_account', return_value=(collector.account('Cursor', '', 'cli'), None)):
                first = [entry for entry, _ in collector.discover() if entry['provider'] == 'Claude']
                second = [entry for entry, _ in collector.discover() if entry['provider'] == 'Claude']
            mirror = setup / 'remote-auths/claude-a.json'
            self.assertEqual([entry['email'] for entry in first], ['a@example.test'])
            self.assertEqual(first[0]['id'], second[0]['id'])
            self.assertEqual(sum('download' in url for url in calls), 1)
            self.assertTrue(all(url.startswith('https://proxy.example.test:8317/v0/management/') for url in calls))
            if os.name != 'nt':
                self.assertEqual(mirror.stat().st_mode & 0o777, 0o600)

    def test_expiring_first_quota_file_uses_auth_ids_and_window_lengths(self):
        entry = dict(collector.account('Claude', 'a@example.test', 'org'), source='CLI proxy', proxyRef='claude-a.json',
                     fetchedAt=0, windows=[{'label': '5-hour', 'used': 3, 'resetAt': None},
                                           {'label': 'Weekly', 'used': 41, 'resetAt': 3600},
                                           {'label': 'Weekly · Fable', 'used': 0, 'resetAt': None},
                                           {'label': 'Weekly · OAuth', 'used': 5, 'resetAt': None}])
        unlisted = dict(collector.account('Cursor', '', 'cli'), source='Cursor CLI', fetchedAt=0)
        quota = collector.expiring_first_quota([entry, unlisted])
        self.assertEqual(quota['schema'], 'expiring-first.quota.v1')
        self.assertEqual([a['auth_id'] for a in quota['accounts']], ['claude-a.json'])
        self.assertEqual([(w['window_minutes'], w['used_percent'], w['resets_at'], w.get('models'))
                          for w in quota['accounts'][0]['windows']],
                         [(300, 3, None, None), (10080, 41, '1970-01-01T01:00:00Z', None), (10080, 0, None, ['fable'])])
        self.assertNotIn('token', json.dumps(quota))

    def test_hidden_accounts_leave_the_snapshot_until_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            cache = home / 'cache/snapshot.json'
            cursor = collector.account('Cursor', 'cursor@example.test', 'cli')
            with patch.object(collector, 'HOME', home), patch.object(collector, 'CACHE', cache), \
                    patch.dict(collector.os.environ, {}, clear=True), \
                    patch.object(collector, 'cache_dir', return_value=cache.parent), \
                    patch.object(collector, 'cursor_cli_account', side_effect=lambda: (dict(cursor), None)):
                collector.change_account('hide', cursor['id'])
                hidden = collector.collect(include_usage=False)
                collector.change_account('restore', cursor['id'])
                restored = collector.collect(include_usage=False)

            self.assertEqual(hidden['accounts'], [])
            self.assertEqual(list(hidden['hidden']), [cursor['id']])
            self.assertEqual([a['id'] for a in restored['accounts']], [cursor['id']])

    def test_delete_uses_each_proxy_api_with_its_local_key(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'claude-proxy/auths').mkdir(parents=True)
            (home / 'claude-proxy/management.env').write_text('MANAGEMENT_PASSWORD=claude-secret\n')
            (home / 'claude-proxy/auths/claude-a.json').write_text(json.dumps({
                'type': 'claude', 'organization_uuid': 'org', 'email': 'a@example.test'}))
            (home / 'claude-proxy/auths/codex-b.json').write_text(json.dumps({
                'type': 'codex', 'account_id': 'codex', 'email': 'b@example.test'}))
            requests = []
            with patch.object(collector, 'HOME', home), patch.dict(collector.os.environ, {}, clear=True), \
                    patch.object(collector, 'cursor_cli_account', return_value=(collector.account('Cursor', '', 'cli'), None)), \
                    patch.object(collector.urllib.request, 'urlopen', side_effect=lambda request, timeout: requests.append(request) or io.BytesIO(b"{}")):
                for entry, _ in collector.discover()[:2]:
                    collector.change_account('delete', entry['id'])

            self.assertEqual([(r.get_method(), r.full_url, r.get_header('Authorization')) for r in requests], [
                ('DELETE', 'http://127.0.0.1:8317/v0/management/auth-files?name=claude-a.json', 'Bearer claude-secret'),
                ('DELETE', 'http://127.0.0.1:8317/v0/management/auth-files?name=codex-b.json', 'Bearer claude-secret')])


if __name__ == '__main__':
    unittest.main()
