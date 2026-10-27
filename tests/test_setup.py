import importlib.util
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('capacity_cli', Path(__file__).parents[1] / 'scripts/capacity.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class SetupTests(unittest.TestCase):
    def test_repeat_initialization_preserves_credentials_and_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            with patch.object(cli, 'STATE', state), patch.object(cli, 'SETTINGS', state / 'settings.json'), \
                    patch.dict(os.environ, {}, clear=True):
                cli.initialize()
                key = (state / 'claude-proxy/client-key').read_text()
                credential = state / 'claude-proxy/auths/account.json'
                credential.write_text('{"access_token":"private"}')
                config = state / 'claude-proxy/config.yaml'
                config.write_text('user config')
                cli.initialize()
                self.assertEqual(config.read_text(), 'user config')
                self.assertEqual((state / 'claude-proxy/client-key').read_text(), key)
                self.assertEqual(json.loads(credential.read_text())['access_token'], 'private')
                if os.name != 'nt':  # Windows has no Unix permission bits.
                    self.assertEqual((state / 'settings.json').stat().st_mode & 0o777, 0o600)

    def test_paths_with_spaces_and_port_overrides_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            custom = (state / 'custom proxy').resolve()
            with patch.object(cli, 'STATE', state), patch.object(cli, 'SETTINGS', state / 'settings.json'), \
                    patch.dict(os.environ, {'CLAUDE_PROXY_DIR': str(custom), 'CLAUDE_PROXY_PORT': '18317'}, clear=True):
                cli.initialize()
            with patch.object(cli, 'STATE', state), patch.object(cli, 'SETTINGS', state / 'settings.json'), \
                    patch.dict(os.environ, {}, clear=True):
                self.assertEqual(cli.paths()['CLAUDE_PROXY_DIR'], str(custom))
                self.assertEqual(cli.settings()['CLAUDE_PROXY_PORT'], '18317')
                with patch.object(cli, 'run') as run:
                    cli.compose('up', '-d')
                self.assertEqual(run.call_args.kwargs['env']['CLAUDE_PROXY_DIR'], str(custom))
                self.assertEqual(run.call_args.kwargs['env']['CLAUDE_PROXY_PORT'], '18317')


    def test_remote_proxy_is_saved_only_after_it_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            with patch.object(cli, 'STATE', state), patch.object(cli, 'SETTINGS', state / 'settings.json'), \
                    patch.dict(os.environ, {}, clear=True):
                with patch.object(cli, 'management', return_value={'files': [{}, {}]}):
                    cli.use_proxy('https://proxy.example.test:8317/', 'key')
                self.assertEqual(cli.remote(), 'https://proxy.example.test:8317')
                with patch.object(cli, 'management', side_effect=RuntimeError('HTTP 401')):
                    with self.assertRaises(RuntimeError):
                        cli.use_proxy('https://other.example.test', 'wrong')
                self.assertEqual(cli.remote(), 'https://proxy.example.test:8317')
                with self.assertRaises(ValueError):
                    cli.use_proxy('ftp://proxy.example.test', 'key')
                cli.use_proxy('local', '')
                self.assertEqual(cli.remote(), '')



class CredentialTests(unittest.TestCase):
    def fake_proxies(self, stores):
        def management(path, body=None, proxy=None):
            store = stores[proxy[0]]
            if path == 'auth-files':
                return {'files': [{'name': name} for name in store]}
            name = cli.urllib.parse.unquote(path.split('name=')[1])
            if path.startswith('auth-files/download'):
                return store[name]
            store[name] = body
            return {'status': 'ok'}
        return mock.patch.object(cli, 'management', side_effect=management)

    def test_copy_moves_every_login_and_skips_ones_the_target_has(self):
        stores = {'a': {'claude-x.json': {'type': 'claude'}, 'codex-y.json': {'type': 'codex'}, '../bad.json': {}},
                  'b': {'codex-y.json': {'type': 'old'}}}
        with self.fake_proxies(stores):
            bundle = cli.export_credentials(('a', 'k'))
            added, skipped = cli.import_credentials(bundle, ('b', 'k'))
        self.assertEqual(sorted(bundle['files']), ['claude-x.json', 'codex-y.json'])
        self.assertEqual((added, skipped), (['claude-x.json'], ['codex-y.json']))
        self.assertEqual(stores['b']['codex-y.json'], {'type': 'old'})

    def test_replace_overwrites_and_a_foreign_file_is_refused(self):
        stores = {'b': {'codex-y.json': {'type': 'old'}}}
        bundle = {'format': cli.CREDENTIALS_FORMAT, 'files': {'codex-y.json': {'type': 'codex'}}}
        with self.fake_proxies(stores):
            cli.import_credentials(bundle, ('b', 'k'), replace=True)
            with self.assertRaises(ValueError):
                cli.import_credentials({'files': {}}, ('b', 'k'))
        self.assertEqual(stores['b']['codex-y.json'], {'type': 'codex'})

    @unittest.skipIf(sys.platform == 'win32', 'POSIX permissions')
    def test_an_export_file_is_readable_only_by_its_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'out.json'
            path.write_text('{}')
            path.chmod(0o644)
            cli.write_secret(path, {'files': {}})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
