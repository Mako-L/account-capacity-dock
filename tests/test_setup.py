import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
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


if __name__ == '__main__':
    unittest.main()
