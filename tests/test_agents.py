import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agents  # noqa: E402


def assistant(*blocks, at='2026-10-22T10:00:00Z'):
    return {'type': 'assistant', 'timestamp': at, 'message': {'content': list(blocks)}}


class ClaudeTranscriptTests(unittest.TestCase):
    def test_reads_prompt_todos_and_the_running_tool(self):
        events = [
            {'type': 'ai-title', 'aiTitle': 'Add webhooks'},
            {'type': 'user', 'message': {'content': 'add webhook handling for failed payments'}},
            assistant({'type': 'tool_use', 'id': 't1', 'name': 'TodoWrite', 'input': {'todos': [
                {'content': 'Read the routes', 'activeForm': 'Reading the routes', 'status': 'completed'},
                {'content': 'Run the tests', 'activeForm': 'Running the tests', 'status': 'in_progress'}]}}),
            {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 't1'}]}},
            assistant({'type': 'text', 'text': 'Now the tests.'},
                      {'type': 'tool_use', 'id': 't2', 'name': 'Bash', 'input': {'command': 'pnpm test', 'description': 'Run the payment tests'}}),
        ]
        found = agents.read_claude(events)
        self.assertEqual(found['title'], 'Add webhooks')
        self.assertEqual(found['prompt'], 'add webhook handling for failed payments')
        self.assertEqual([t['status'] for t in found['todos']], ['completed', 'in_progress'])
        self.assertEqual([call[0] for call in found['pending'].values()], ['Bash'])
        self.assertEqual(found['activity'][-1]['text'], 'Run the payment tests')
        self.assertEqual(found['last_text'], 'Now the tests.')

    def test_hook_and_meta_messages_are_not_the_prompt(self):
        events = [
            {'type': 'user', 'message': {'content': 'fix the login crash'}},
            {'type': 'user', 'isMeta': True, 'message': {'content': 'meta text'}},
            {'type': 'user', 'message': {'content': '<command-name>/clear</command-name>'}},
        ]
        self.assertEqual(agents.read_claude(events)['prompt'], 'fix the login crash')

    def test_tool_steps_read_like_short_sentences(self):
        self.assertEqual(agents.tool_step('Edit', {'file_path': '/a/b/stripe.ts'}), 'Edit stripe.ts')
        self.assertEqual(agents.tool_step('Agent', {'description': 'Review retries'}), 'Subagent: Review retries')
        self.assertEqual(agents.tool_step('mcp__github__create_issue', {}), 'Create issue')


class CodexRolloutTests(unittest.TestCase):
    def test_plan_becomes_steps_and_open_calls_stay_pending(self):
        def item(payload):
            return {'timestamp': '2026-10-22T10:00:00Z', 'payload': payload}
        events = [
            item({'type': 'user_message', 'message': 'add dark mode tokens'}),
            item({'type': 'function_call', 'name': 'update_plan', 'call_id': 'p', 'arguments': json.dumps(
                {'plan': [{'step': 'List colours', 'status': 'completed'}, {'step': 'Define tokens', 'status': 'in_progress'}]})}),
            item({'type': 'function_call', 'name': 'shell', 'call_id': 'c1', 'arguments': json.dumps({'command': ['rg', 'color']})}),
            item({'type': 'function_call_output', 'call_id': 'c1'}),
            item({'type': 'function_call', 'name': 'shell', 'call_id': 'c2', 'arguments': json.dumps({'command': ['pnpm', 'build']})}),
        ]
        found = agents.read_codex(events)
        self.assertEqual(found['prompt'], 'add dark mode tokens')
        self.assertEqual([t['title'] for t in found['todos']], ['List colours', 'Define tokens'])
        self.assertEqual(list(found['pending']), ['c2'])
        self.assertEqual(found['activity'][-1]['text'], 'pnpm build')


class ReportTests(unittest.TestCase):
    def test_report_keeps_the_task_and_clear_removes_it(self):
        with tempfile.TemporaryDirectory() as home, \
                mock.patch.dict(os.environ, {'MAKO_CAPACITY_HOME': home, 'HERDR_PANE_ID': 'w1:p2'}):
            path = agents.write_report('Read the code', task='Fix login', done=1, total=4)
            agents.write_report('Write the fix', done=2, total=4)
            data = json.loads(path.read_text())
            self.assertEqual((data['task'], data['step'], data['done'], data['total']), ('Fix login', 'Write the fix', 2, 4))
            self.assertEqual(path.name, 'w1_p2.json')
            agents.write_report(None, clear=True)
            self.assertFalse(path.exists())


class AgentsWidgetPinTests(unittest.TestCase):
    def test_agents_widget_pins_apart_from_the_capacity_widget(self):
        sys.path.insert(0, str(ROOT / 'herdr-plugin'))
        if sys.platform == 'win32':
            self.skipTest('open.py runs inside Herdr on macOS and Linux only.')
        import open as opener
        with tempfile.TemporaryDirectory() as state:
            for kind in (opener.CAPACITY, opener.AGENTS):
                kind.state = Path(state) / kind.state.name
            opener.pin('right', 'agents', opener.AGENTS)
            self.assertEqual(opener.pinned(opener.AGENTS), ('right', 'agents'))
            self.assertEqual(opener.pinned(opener.CAPACITY), ('', 'capacity'))


if __name__ == '__main__':
    unittest.main()
