import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import codeburn_usage as usage
from platform_paths import cache_dir


def payload(**fields):
    current = dict(inputTokens=100, outputTokens=20, cacheReadTokens=50,
                   cacheWriteTokens=5, cost=1.25, estimatedCostUSD=0, unpricedModels=[])
    current.update(fields)
    return {'current': current}


class UsageTests(unittest.TestCase):
    def test_token_total_includes_each_cache_category_once(self):
        result = usage.summarize(payload(), 'Claude', 100)
        self.assertEqual(result['tokens'], 175)
        self.assertEqual(result['costUsd'], 1.25)
        self.assertEqual(result['status'], 'live')

    def test_unknown_values_never_become_zero_and_partial_cost_is_marked(self):
        result = usage.summarize(dict(payload(cacheWriteTokens=None, cost=True), hydration={'complete': False}), 'Cursor', 100)
        self.assertIsNone(result['tokens'])
        self.assertIsNone(result['costUsd'])
        self.assertEqual(result['status'], 'partial')
        for value in (True, -1, float('nan'), float('inf')):
            self.assertIsNone(usage.number(value))
        self.assertEqual(usage.number(0), 0)

    def test_stdio_reports_are_scoped_cached_and_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = [{'ready': True}] + [{'id': provider, 'ok': True,
                       'output': json.dumps(dict(payload(), private_transcript='do not store'))}
                       for provider in usage.PROVIDERS]
            response = subprocess.CompletedProcess([], 0, stdout='\n'.join(map(json.dumps, frames)), stderr='')
            with patch.object(usage, 'cache_dir', return_value=root / 'cache'), \
                    patch.object(usage.shutil, 'which', return_value='codeburn'), \
                    patch.object(usage.subprocess, 'run', return_value=response) as run, \
                    patch.dict(os.environ, {'MAKO_CAPACITY_HOME': str(root / 'setup')}):
                result = usage.collect_usage(True)
                self.assertEqual(result['Codex']['tokens'], 175)
                requests = [json.loads(line) for line in run.call_args.kwargs['input'].splitlines()]
                self.assertEqual([row['args'][row['args'].index('--provider')+1] for row in requests], ['claude', 'codex', 'cursor-agent'])
                self.assertNotIn('do not store', (root / 'cache/codeburn-usage.json').read_text())
                usage.collect_usage()
                self.assertEqual(run.call_count, 1)
                run.side_effect = subprocess.TimeoutExpired('codeburn', 55)
                stale = usage.collect_usage(True)
                self.assertEqual(stale['Codex']['tokens'], 175)
                self.assertEqual(stale['Codex']['status'], 'stale')

    def test_platform_cache_paths_match_native_host_conventions(self):
        with patch.dict(os.environ, {}, clear=True):
            home = Path('/example/home')
            self.assertEqual(cache_dir(home, 'darwin'), home / 'Library/Application Support/Mako Capacity')
            self.assertEqual(cache_dir(home, 'linux'), home / '.cache/mako-capacity')
            self.assertEqual(cache_dir(home, 'win32'), home / 'AppData/Local/mako-capacity')


if __name__ == '__main__':
    unittest.main()
