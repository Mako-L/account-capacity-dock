import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location('collector', Path(__file__).parents[1] / 'collector.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class CapacityParsingTests(unittest.TestCase):
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
        self.assertEqual(collector.cursor_windows({'individualUsage': {'plan': {'limit': 0}}}), [])
        result = collector.cursor_windows({'individualUsage': {'plan': {'totalPercentUsed': 0}}})
        self.assertEqual(result[0]['used'], 0)

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
            with patch.object(collector, 'HOME', home):
                discovered = collector.discover()
            rows = [row for row, _ in discovered if row['provider'] == 'Claude']
            self.assertEqual(len(rows), 2)
            self.assertNotIn('private-access', json.dumps(rows))
            self.assertNotIn('private-refresh', json.dumps(rows))


if __name__ == '__main__':
    unittest.main()
