#!/usr/bin/env python3
"""Dock the capacity pane at the left or right edge of a tab, or pin it so it follows you.

open.py right|left [app|agents]      dock in the focused tab
open.py pin right|left [app|agents]  dock now, then move with you to every tab you focus
open.py unpin [agents]               stop following and close the widget in other tabs
open.py toggle [app|agents]          pin (keeping this tab's widget and its side) or unpin
open.py ensure                       event hook: move the pinned widgets into the focused tab

With app, a new widget is the GPUIX app instead of the text widget.
With agents, the widget is the agents view, pinned apart from the capacity widget.

A pinned widget is one process that moves between tabs. One copy per tab cost
about 24 MB each and ran the collector once per copy.
"""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

HERDR = os.environ.get('HERDR_BIN_PATH', 'herdr')
STATE_DIR = Path(os.environ.get('HERDR_PLUGIN_STATE_DIR') or Path.home() / '.mako-capacity')


class Kind:
    """One widget family: its pin state file, its pane title and its width in cells."""

    def __init__(self, state, label, width, entry):
        self.state, self.label, self.width, self.entry = STATE_DIR / state, label, width, entry


CAPACITY = Kind('pinned-side', 'Capacity', int(os.environ.get('MAKO_CAPACITY_WIDTH', '36')), 'capacity')
AGENTS = Kind('pinned-agents', 'Agents', int(os.environ.get('MAKO_AGENTS_WIDTH', '46')), 'agents')


def herdr(*args):
    return json.loads(subprocess.run([HERDR, *args], capture_output=True, text=True, check=True).stdout)['result']


def focused_pane():
    context = json.loads(os.environ.get('HERDR_PLUGIN_CONTEXT_JSON') or '{}')
    return context.get('focused_pane_id') or os.environ.get('HERDR_PANE_ID') or \
        herdr('pane', 'current')['pane']['pane_id']


def dock(side, pane, widget=None, entry='capacity', kind=CAPACITY):
    """Put widget (a pane ID), or a new widget, at the side edge of pane's tab."""
    layout = herdr('pane', 'layout', '--pane', pane)['layout']
    # Split the outermost pane on that side, preferring the tallest one.
    edge = (lambda p: p['rect']['x'] + p['rect']['width']) if side == 'right' else (lambda p: -p['rect']['x'])
    target = max(layout['panes'], key=lambda p: (edge(p), p['rect']['height']))
    total = target['rect']['width']
    share = min(max(kind.width / total, 0.15), 0.5)
    opened = widget or herdr('plugin', 'pane', 'open', '--plugin', 'mako-capacity', '--entrypoint', entry,
                             '--placement', 'tab', '--no-focus')['plugin_pane']['pane']['pane_id']
    # ponytail: plugin panes take no split ratio, so open in a tab and move it with an exact ratio.
    ratio = 1 - share if side == 'right' else share
    moved = herdr('pane', 'move', opened, '--tab', layout['tab_id'], '--split', 'right',
                  '--target-pane', target['pane_id'], '--ratio', f'{ratio:.3f}', '--no-focus')
    new = moved['move_result']['pane']['pane_id']
    if side == 'left':
        herdr('pane', 'swap', '--source-pane', new, '--target-pane', target['pane_id'])
    return new


def widgets(kind):
    return [p for p in herdr('pane', 'list')['panes'] if p.get('label') == kind.label]


def pinned(kind=CAPACITY):
    """(side, entrypoint) of the pinned widget; side is empty when nothing is pinned."""
    words = (kind.state.read_text().split() if kind.state.exists() else []) + ['', kind.entry]
    return words[0], words[1]


def pin(side, entry, kind=CAPACITY):
    kind.state.parent.mkdir(parents=True, exist_ok=True)
    kind.state.write_text(f'{side} {entry}')


def ensure():
    pinned_kinds = [(kind, *pinned(kind)) for kind in (CAPACITY, AGENTS)]
    pinned_kinds = [k for k in pinned_kinds if k[1] in ('left', 'right')]
    if not pinned_kinds:
        return
    pane = focused_pane()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # Tab switches arrive in bursts; one hook at a time keeps a single widget.
    with open(STATE_DIR / 'pinned-side.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tab = herdr('pane', 'layout', '--pane', pane)['layout']['tab_id']
        for kind, side, entry in pinned_kinds:
            found = widgets(kind)
            if any(p['tab_id'] == tab for p in found):
                continue
            # Close copies left by older versions, then bring the remaining one here.
            for extra in found[1:]:
                herdr('pane', 'close', extra['pane_id'])
            print(dock(side, pane, found[0]['pane_id'] if found else None, entry, kind))


def side_of(widget, pane):
    layout = herdr('pane', 'layout', '--pane', pane)['layout']
    left = min(p['rect']['x'] for p in layout['panes'])
    rect = next(p['rect'] for p in layout['panes'] if p['pane_id'] == widget['pane_id'])
    return 'left' if rect['x'] == left else 'right'


def main(args):
    kind = AGENTS if 'agents' in args else CAPACITY
    # 'app' picks the GPUIX app. 'text' picks the plain-text agents widget.
    entry = 'app' if 'app' in args else 'agents-text' if kind is AGENTS and 'text' in args else kind.entry
    args = [a for a in args if a not in ('app', 'agents', 'text')]
    if args[:1] == ['ensure']:
        return ensure()
    if args[:1] == ['toggle']:
        if kind.state.exists():
            return main(['unpin', kind.entry])
        pane = focused_pane()
        tab = herdr('pane', 'layout', '--pane', pane)['layout']['tab_id']
        widget = next((w for w in widgets(kind) if w['tab_id'] == tab), None)
        if widget is None:
            return main(['pin', 'right', entry])
        pin(side_of(widget, pane), entry, kind)
        return
    if args[:1] == ['unpin']:
        kind.state.unlink(missing_ok=True)
        tab = herdr('pane', 'layout', '--pane', focused_pane())['layout']['tab_id']
        for pane in widgets(kind):
            if pane['tab_id'] != tab:
                herdr('pane', 'close', pane['pane_id'])
        return
    if args[:1] == ['pin']:
        side = args[1] if len(args) > 1 else 'right'
        pin(side, entry, kind)
        pane = focused_pane()
        found = widgets(kind)
        for extra in found[1:]:
            herdr('pane', 'close', extra['pane_id'])
        # Re-dock even a widget in this tab, so it moves to the chosen side.
        print(dock(side, pane, found[0]['pane_id'] if found else None, entry, kind))
        return
    print(dock(args[0] if args else 'right', focused_pane(), entry=entry, kind=kind))


if __name__ == '__main__':
    main(sys.argv[1:])
