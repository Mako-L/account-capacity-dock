import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'herdr-plugin'))
import capacity  # noqa: E402

ANSI = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')


def account(id, title, used, provider='Claude', status='live'):
    return {'id': id, 'provider': provider, 'title': title, 'status': status,
            'windows': [{'label': '5-hour', 'used': 10, 'resetAt': 7200},
                        {'label': 'Weekly · Fable', 'used': used, 'resetAt': 90000}]}


class RenderTests(unittest.TestCase):
    snapshot = {'updatedAt': 0, 'accounts': [account('a', 'alpha', 31), account('b', 'a-very-long-account-name', 100),
                                             account('c', 'hidden', 5)]}

    def test_fits_width_hides_accounts_and_places_rings(self):
        for rings in (False, True):
            lines, placed = capacity.render(self.snapshot, {'c'}, 30, 0, rings)
            plain = [ANSI.sub('', line) for line in lines]
            self.assertLessEqual(max(map(len, plain)), 30)
            self.assertNotIn('hidden', '\n'.join(plain))
            self.assertIn('31%', plain[2])
            self.assertIn('At limit', '\n'.join(plain))
            self.assertIn('2h00', '\n'.join(plain))
            self.assertEqual([row for row, _ in placed], [2, 7] if rings else [])

    def test_drops_detail_to_fit_height(self):
        lines, placed = capacity.render(self.snapshot, set(), 30, 0, True, height=9)
        self.assertEqual(len(lines), 9)
        self.assertEqual([row for row, _ in placed], [2, 4, 6])

    def test_narrow_pane_shows_only_ring_percent_and_name(self):
        lines, placed = capacity.render(self.snapshot, {'c'}, 14, 0, True)
        plain = [ANSI.sub('', line) for line in lines]
        self.assertEqual(plain[2:5], ['      31%', '      alpha', ''])
        self.assertEqual([row for row, _ in placed], [2, 5])
        self.assertNotIn('Weekly', '\n'.join(plain))

    def test_tiny_pane_shows_only_centred_rings(self):
        lines, placed = capacity.render(self.snapshot, {'c'}, 8, 0, True)
        self.assertEqual(lines, ['', '', '', '', '', '', ''])
        self.assertEqual([row for row, _ in placed], [1, 4])
        self.assertEqual(capacity.ring_place(8, 19), (3, 0))
        self.assertEqual(capacity.ring_place(7, 20), (2, 10))
        self.assertEqual(capacity.ring_place(30, 19), (2, 0))
        text = [ANSI.sub('', line) for line in capacity.render(self.snapshot, {'c'}, 8, 0)[0]]
        self.assertEqual(text[1], '  31%')

    def test_wide_pane_adds_plan_email_notes_and_today(self):
        snapshot = {'updatedAt': 0, 'accounts': [dict(account('a', 'alpha', 31, 'Codex'), plan='Pro', email='a@example.test',
                                                      message='Grok Bot usage unavailable',
                                                      localUsage={'tokens': 2.5e6, 'costUsd': 1.5})]}
        plain = '\n'.join(ANSI.sub('', line) for line in capacity.render(snapshot, set(), 60, 0)[0])
        for text in ('Codex · Pro · Available · a@example.test', 'Weekly · Fable', 'Grok Bot usage unavailable',
                     'Today · local Codex: 2.5M tokens · $1.50'):
            self.assertIn(text, plain)

    def test_tall_lists_keep_the_tightest_bar(self):
        lines = capacity.render(self.snapshot, set(), 40, 0, True, height=12)[0]
        bars = [ANSI.sub('', line) for line in lines if '━' in line or '─' in line]
        self.assertEqual(len(bars), 3)
        self.assertIn('Wk Fable', bars[1])

    def test_status_line_groups_percent_by_provider(self):
        snapshot = {'accounts': self.snapshot['accounts'] + [dict(account('d', 'pro', 7, 'Codex'), windows=[])]}
        self.assertEqual(capacity.status_line(snapshot, {'c'}), '✳ ◔31 ●100  ◎ ○—')

    def test_widgets_share_one_collector_run(self):
        import tempfile, threading, time
        from unittest.mock import patch
        calls = []

        def run(args, **_):
            calls.append(args)
            time.sleep(0.2)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(capacity, 'cache_dir', return_value=Path(directory)), \
                patch.object(capacity.subprocess, 'run', side_effect=run):
            threads = [threading.Thread(target=capacity.collect) for _ in range(8)]
            [thread.start() for thread in threads]
            [thread.join() for thread in threads]
            self.assertEqual(len(calls), 1)
            (Path(directory) / 'snapshot.json').write_text('{}')
            capacity.collect()
            self.assertEqual(len(calls), 1)
            capacity.collect(force=True)
            self.assertEqual(len(calls), 2)

    def test_ring_png_is_valid(self):
        png = capacity.ring_png(50, (48, 209, 88), capacity.icon_mask('Cursor', 36))
        self.assertTrue(png.startswith(b'\x89PNG') and png.endswith(b'IEND\xaeB`\x82'))


if __name__ == '__main__':
    unittest.main()
