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
                self.assertEqual((state / 'settings.json').stat().st_mode & 0o777, 0o600)

    def test_paths_with_spaces_and_port_overrides_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            custom = (state / 'custom proxy').resolve()
            with patch.object(cli, 'STATE', state), patch.object(cli, 'SETTINGS', state / 'settings.json'), \
                    patch.dict(os.environ, {'CLAUDE_PROXY_DIR': str(custom), 'CODEX_PROXY_PORT': '18080'}, clear=True):
                cli.initialize()
            with patch.object(cli, 'STATE', state), patch.object(cli, 'SETTINGS', state / 'settings.json'), \
                    patch.dict(os.environ, {}, clear=True):
                self.assertEqual(cli.paths()['CLAUDE_PROXY_DIR'], str(custom))
                self.assertEqual(cli.settings()['CODEX_PROXY_PORT'], '18080')
                with patch.object(cli, 'run') as run:
                    cli.compose('up', '-d')
                self.assertEqual(run.call_args.kwargs['env']['CLAUDE_PROXY_DIR'], str(custom))
                self.assertEqual(run.call_args.kwargs['env']['CODEX_PROXY_PORT'], '18080')


if __name__ == '__main__':
    unittest.main()
