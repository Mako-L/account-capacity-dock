import json
import re
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

    def test_steps_keep_how_long_they_took(self):
        def plan(at, *statuses):
            todos = [{'content': name, 'activeForm': name, 'status': status} for name, status in zip(('Read', 'Fix', 'Test'), statuses)]
            return assistant({'type': 'tool_use', 'id': at, 'name': 'TodoWrite', 'input': {'todos': todos}}, at=at)
        events = [plan('2026-10-22T10:00:00Z', 'in_progress', 'pending', 'pending'),
                  plan('2026-10-22T10:05:00Z', 'completed', 'in_progress', 'pending'),
                  # Test jumps straight to done: it started at the previous plan update.
                  plan('2026-10-22T10:07:00Z', 'completed', 'completed', 'completed')]
        steps = agents.as_steps(agents.read_claude(events)['todos'])
        self.assertEqual([s['took'] for s in steps], [300, 120, 120])

    def test_observer_steps_get_times_from_when_the_dock_saw_them(self):
        agent = {'id': 'a', 'status': 'working', 'steps': [{'title': 'Fix', 'status': 'active'}], 'subagents': []}
        times = agents.clock_steps([agent], {}, 100)
        self.assertEqual(agent['steps'][0]['since'], 100)
        agent = {'id': 'a', 'status': 'working', 'steps': [{'title': 'Fix', 'status': 'done'}, {'title': 'Test', 'status': 'done'}], 'subagents': []}
        agents.clock_steps([agent], times, 160)
        # Test showed up done in the same refresh that Fix ended: the dock never saw it run, so no time.
        self.assertEqual([s.get('took') for s in agent['steps']], [60, None])

    def test_a_step_the_observer_renames_as_it_finishes_keeps_its_time(self):
        times = agents.clock_steps([{'id': 'a', 'status': 'working', 'steps': [{'title': 'Read', 'status': 'active'}], 'subagents': []}], {}, 100)
        agent = {'id': 'a', 'status': 'working', 'steps': [{'title': 'Read the code', 'status': 'done'}, {'title': 'Fix', 'status': 'active'}], 'subagents': []}
        agents.clock_steps([agent], times, 160)
        self.assertEqual(agent['steps'][0]['took'], 60)

    def test_a_stopped_agent_stops_its_active_step_clock(self):
        agent = {'id': 'a', 'status': 'idle', 'updated': 400, 'steps': [{'title': 'Fix', 'status': 'active', 'since': 100}], 'subagents': []}
        agents.clock_steps([agent], {}, 9000)
        self.assertEqual(agent['steps'][0], {'title': 'Fix', 'status': 'active', 'took': 300})

    def test_the_run_time_counts_from_the_last_request(self):
        events = [{'type': 'user', 'timestamp': '2026-10-22T10:00:00Z', 'message': {'content': 'first job'}},
                  {'type': 'user', 'timestamp': '2026-10-22T12:00:00Z', 'message': {'content': 'second job'}}]
        self.assertEqual(agents.read_claude(events)['asked'], agents.stamp(events[1]))

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


class SubagentTreeTests(unittest.TestCase):
    def write(self, path, events, meta=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(json.dumps(e) + '\n' for e in events))
        if meta is not None:
            path.with_name(path.stem + '.meta.json').write_text(json.dumps(meta))

    def test_nested_and_workflow_subagents_form_a_tree_in_start_order(self):
        with tempfile.TemporaryDirectory() as folder:
            transcript = Path(folder) / 'session.jsonl'
            transcript.write_text('')
            root = Path(folder) / 'session' / 'subagents'
            call = [{'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 't1', 'name': 'Read', 'input': {'file_path': '/a/b.py'}}]}}]
            self.write(root / 'agent-a1.jsonl', call, {'agentType': 'reviewer', 'description': 'Review the change'})
            self.write(root / 'agent-a2.jsonl', call, {'agentType': 'fork', 'description': 'Check one file', 'parentAgentId': 'a1'})
            flow = root / 'workflows' / 'wf_1'
            self.write(flow / 'agent-w1.jsonl', call, {'agentType': 'general-purpose'})
            self.write(flow / 'journal.jsonl', [{'type': 'started', 'agentId': 'w1', 'label': 'tests:api'}])

            def parse(path, reader, size):
                found = reader(agents.tail_events(path, size))
                found['pending'] = [agents.tool_step(n, d) for n, d, _ in found['pending'].values()]
                return found, os.stat(path).st_mtime

            tree = agents.subagent_tree(str(transcript), os.stat(transcript).st_mtime + 1, parse)
        names = {n['id']: n for n in tree}
        self.assertEqual(set(names), {'agent-a1', 'wf_1'})
        self.assertEqual([c['description'] for c in names['agent-a1']['children']], ['Check one file'])
        self.assertTrue(names['agent-a1']['running'])
        self.assertEqual(names['agent-a1']['step'], 'Read b.py')
        self.assertEqual(names['wf_1']['kind'], 'workflow')
        self.assertEqual([c['name'] for c in names['wf_1']['children']], ['tests:api'])

    def test_a_workflow_keeps_agents_older_than_the_recent_window(self):
        with tempfile.TemporaryDirectory() as folder:
            transcript = Path(folder) / 'session.jsonl'
            transcript.write_text('')
            flow = Path(folder) / 'session' / 'subagents' / 'workflows' / 'wf_1'
            call = [{'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'done'}]}}]
            for name in ('agent-old', 'agent-new'):
                self.write(flow / f'{name}.jsonl', call, {'agentType': 'general-purpose'})
            self.write(flow / 'journal.jsonl', [{'type': 'started', 'agentId': 'old', 'label': 'a', 'phase': 'Build'},
                                                {'type': 'started', 'agentId': 'new', 'label': 'b', 'phase': 'Check'}])
            now = os.stat(transcript).st_mtime + 60
            old = now - agents.SUB_RECENT - 3600
            os.utime(flow / 'agent-old.jsonl', (old, old))

            def parse(path, reader, size):
                found = reader(agents.tail_events(path, size))
                found['pending'] = []
                return found, os.stat(path).st_mtime

            tree = agents.subagent_tree(str(transcript), now, parse)
        self.assertEqual(sorted(c['name'] for c in tree[0]['children']), ['a', 'b'])

    def test_a_subagent_inside_a_long_call_still_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            transcript = Path(folder) / 'session.jsonl'
            transcript.write_text('')
            root = Path(folder) / 'session' / 'subagents'
            def call(id):
                return {'type': 'assistant', 'isSidechain': True, 'message': {'content': [{'type': 'tool_use', 'id': id, 'name': 'Bash', 'input': {'command': 'pnpm build'}}]}}
            closed = {'type': 'user', 'isSidechain': True, 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'a'}]}}
            self.write(root / 'agent-wait.jsonl', [call('a'), closed, call('b')], {'agentType': 'general-purpose'})
            self.write(root / 'agent-done.jsonl', [call('a'), closed], {'agentType': 'general-purpose'})
            now = os.stat(transcript).st_mtime + 600

            def parse(path, reader, size):
                found = reader(agents.tail_events(path, size))
                found['pending'] = [agents.tool_step(n, d) for n, d, _ in found['pending'].values()]
                return found, os.stat(path).st_mtime

            tree = {n['id']: n for n in agents.subagent_tree(str(transcript), now, parse)}
        self.assertTrue(tree['agent-wait']['running'])
        self.assertFalse(tree['agent-done']['running'])


class UsageTests(unittest.TestCase):
    def test_a_message_counts_once_and_new_lines_add_on(self):
        def line(id, out):
            return json.dumps({'type': 'assistant', 'message': {'id': id, 'model': 'priced', 'usage': {
                'input_tokens': 10, 'output_tokens': out, 'cache_read_input_tokens': 100, 'cache_creation_input_tokens': 5}}}) + '\n'
        price = {'inputCostPerToken': 1, 'outputCostPerToken': 2, 'cacheReadCostPerToken': 0.1, 'cacheWriteCostPerToken': 1}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(agents, '_prices', {'priced': price}), \
                mock.patch.dict(agents.USAGE, clear=True):
            path = Path(folder) / 's.jsonl'
            path.write_text(line('m1', 4) + line('m1', 4))
            first = dict(agents.claude_usage(str(path)))
            with path.open('a') as handle:
                handle.write(line('m2', 6))
            second = agents.claude_usage(str(path))
        self.assertEqual((first['input'], first['output'], first['cacheRead'], first['cacheWrite']), (10, 4, 100, 5))
        self.assertAlmostEqual(first['cost'], 10 + 8 + 10 + 5)
        self.assertEqual(second['output'], 10)
        self.assertIsNone(agents.sum_usage([second, {'input': 1, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0, 'cost': None}])['cost'])


class WeekShareTests(unittest.TestCase):
    def test_an_agent_share_of_a_week_comes_from_what_a_full_week_costs(self):
        # Accounts that used 50% and 100% of their week for 100 USD and 300 USD: a week costs 200 or 300, middle 300.
        snapshot = {'accounts': [{'provider': 'Claude', 'windows': [{'label': 'Weekly', 'used': 50, 'spent': {'costUsd': 100}}]},
                                 {'provider': 'Claude', 'windows': [{'label': 'Weekly', 'used': 100, 'spent': {'costUsd': 300}}]}]}
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'snapshot.json').write_text(json.dumps(snapshot))
            usage = {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0, 'cost': 30}
            agent = {'id': 'a', 'agent': 'claude', 'usage': usage, 'subagents': []}
            with mock.patch.object(agents, 'cache_dir', return_value=Path(folder)):
                self.assertEqual(agents.week_share([agent]), {'claude': 300})
        self.assertEqual(agent['usage']['weekPercent'], 10)


class ClaudeSessionTests(unittest.TestCase):
    def test_a_session_file_whose_pid_was_reused_is_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            sessions = Path(folder) / 'sessions'
            sessions.mkdir()
            pid = os.getpid()
            (sessions / 'new.json').write_text(json.dumps({'pid': pid, 'sessionId': 'new', 'startedAt': 2_000_000_000_000}))
            (sessions / 'old.json').write_text(json.dumps({'pid': pid, 'sessionId': 'old', 'startedAt': 1_000_000_000_000}))
            checked = {}
            with mock.patch.object(agents, 'claude_dirs', return_value=[Path(folder)]), \
                    mock.patch.object(agents, 'process_starts', return_value={pid: 1_900_000_000}):
                found = agents.claude_sessions(checked)
            with mock.patch.object(agents, 'claude_dirs', return_value=[Path(folder)]), \
                    mock.patch.object(agents, 'process_starts', side_effect=AssertionError('ps ran again')):
                again = agents.claude_sessions(checked)
        self.assertEqual([s['sessionId'] for s in found], ['new'])
        self.assertEqual([s['sessionId'] for s in again], ['new'])
        self.assertEqual(found[0]['root'], folder)


class ObserverInputTests(unittest.TestCase):
    def test_sends_only_events_after_the_last_report(self):
        found = {'prompt': 'Fix login', 'activity': [
            {'at': 10, 'text': 'Read old.py', 'kind': 'tool'}, {'at': 20, 'text': 'Edit new.py', 'kind': 'tool'}]}
        previous = {'result': {'task': 'Fix login', 'steps': []}, 'last_event': 10, 'prompt': 'Fix login'}
        text, events = agents.observer_input({'agent': 'claude', 'cwd': '/x/app'}, found, previous)
        self.assertEqual([e['text'] for e in events], ['Edit new.py'])
        self.assertNotIn('Read old.py', text)
        self.assertNotIn('Request from the person', text)
        self.assertIn('Your last report', text)


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


class AgentsTextWidgetTests(unittest.TestCase):
    def setUp(self):
        if sys.platform == 'win32':
            self.skipTest('The text widget runs inside Herdr on macOS and Linux only.')
        sys.path.insert(0, str(ROOT / 'herdr-plugin'))
        import agents_tui
        self.tui = agents_tui

    def test_cards_show_timed_steps_subagents_in_order_and_cost(self):
        now = 1_000_000
        sub = lambda id, running=False, idle=False: {'id': id, 'name': id, 'description': id, 'running': running, 'idle': idle,
                                                     'progress': 50 if running else 100, 'started': now - 600, 'updated': now - 60}
        agent = {'id': 'w1:p1', 'agent': 'claude', 'name': 'shop', 'status': 'working', 'task': 'Fix login', 'progress': 50,
                 'started': now - 3600, 'pane': 'w1:p1',
                 'steps': [{'title': 'Read', 'status': 'done', 'took': 240}, {'title': 'Write', 'status': 'active', 'since': now - 90}],
                 'subagents': [sub('busy', running=True), sub('ended'), sub('waiting', idle=True)],
                 'usage': {'input': 1, 'output': 2, 'cacheRead': 3, 'cacheWrite': 4, 'cost': 2.5, 'weekPercent': 3.2},
                 'totalUsage': {'input': 1, 'output': 2, 'cacheRead': 3, 'cacheWrite': 4, 'cost': 4.0, 'weekPercent': 5}}
        plain = lambda lines: [re.sub(r'\x1b\[[0-9;]*m', '', line) for line in lines]
        card = plain(self.tui.detail_view(agent, 'agent', 46, 0, now, {}).lines)
        text = '\n'.join(card)
        self.assertIn('4m', next(line for line in card if 'Read' in line))
        self.assertIn('1m', next(line for line in card if 'Write' in line))
        self.assertLess(text.index('busy'), text.index('ended'))
        self.assertLess(text.index('ended'), text.index('waiting'))
        self.assertIn('$4.00 · ~5% of a week', text)
        self.assertIn('Running for 1h', text)
        self.assertTrue(all(len(line) <= 46 for line in card))
        self.assertEqual(self.tui.list_view([agent, dict(agent, id='w2', status='idle')], 46, 0, now).targets.count(('agent', 'w2')), 1)

    def test_keys_read_arrows_escape_and_clicks(self):
        self.assertEqual(self.tui.keys_of('\x1b[A\x1b[Bj\r\x1bq'), ['up', 'down', 'down', 'enter', 'back', 'q'])
        self.assertEqual(self.tui.keys_of('\x1b[<0;5;7M\x1b[<0;5;7m\x1b[<65;1;1M'), [('mouse', 0, 5, 7), ('mouse', 65, 1, 1)])


if __name__ == '__main__':
    unittest.main()
