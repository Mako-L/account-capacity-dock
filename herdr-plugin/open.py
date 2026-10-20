#!/usr/bin/env python3
"""Dock the capacity pane at the left or right edge of a tab, or pin it so it follows you.

open.py right|left          dock in the focused tab
open.py pin right|left      dock now, then move with you to every tab you focus
open.py unpin               stop following and close the widget in other tabs
open.py toggle              pin (keeping this tab's widget and its side) or unpin
open.py ensure              event hook: move the pinned widget into the focused tab

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
WIDTH = int(os.environ.get('MAKO_CAPACITY_WIDTH', '36'))
STATE = Path(os.environ.get('HERDR_PLUGIN_STATE_DIR') or Path.home() / '.mako-capacity') / 'pinned-side'
LABEL = 'Capacity'


def herdr(*args):
    return json.loads(subprocess.run([HERDR, *args], capture_output=True, text=True, check=True).stdout)['result']


def focused_pane():
    context = json.loads(os.environ.get('HERDR_PLUGIN_CONTEXT_JSON') or '{}')
    return context.get('focused_pane_id') or os.environ.get('HERDR_PANE_ID') or \
        herdr('pane', 'current')['pane']['pane_id']


def dock(side, pane, widget=None):
    """Put widget (a pane ID), or a new widget, at the side edge of pane's tab."""
    layout = herdr('pane', 'layout', '--pane', pane)['layout']
    # Split the outermost pane on that side, preferring the tallest one.
    edge = (lambda p: p['rect']['x'] + p['rect']['width']) if side == 'right' else (lambda p: -p['rect']['x'])
    target = max(layout['panes'], key=lambda p: (edge(p), p['rect']['height']))
    total = target['rect']['width']
    share = min(max(WIDTH / total, 0.15), 0.5)
    opened = widget or herdr('plugin', 'pane', 'open', '--plugin', 'mako-capacity', '--entrypoint', 'capacity',
                             '--placement', 'tab', '--no-focus')['plugin_pane']['pane']['pane_id']
    # ponytail: plugin panes take no split ratio, so open in a tab and move it with an exact ratio.
    ratio = 1 - share if side == 'right' else share
    moved = herdr('pane', 'move', opened, '--tab', layout['tab_id'], '--split', 'right',
                  '--target-pane', target['pane_id'], '--ratio', f'{ratio:.3f}', '--no-focus')
    new = moved['move_result']['pane']['pane_id']
    if side == 'left':
        herdr('pane', 'swap', '--source-pane', new, '--target-pane', target['pane_id'])
    return new


def widgets():
    return [p for p in herdr('pane', 'list')['panes'] if p.get('label') == LABEL]


def ensure():
    side = STATE.read_text().strip() if STATE.exists() else ''
    if side not in ('left', 'right'):
        return
    pane = focused_pane()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    # Tab switches arrive in bursts; one hook at a time keeps a single widget.
    with open(STATE.with_suffix('.lock'), 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tab = herdr('pane', 'layout', '--pane', pane)['layout']['tab_id']
        found = widgets()
        if any(p['tab_id'] == tab for p in found):
            return
        # Close copies left by older versions, then bring the remaining one here.
        for extra in found[1:]:
            herdr('pane', 'close', extra['pane_id'])
        print(dock(side, pane, found[0]['pane_id'] if found else None))


def side_of(widget, pane):
    layout = herdr('pane', 'layout', '--pane', pane)['layout']
    left = min(p['rect']['x'] for p in layout['panes'])
    rect = next(p['rect'] for p in layout['panes'] if p['pane_id'] == widget['pane_id'])
    return 'left' if rect['x'] == left else 'right'


def main(args):
    if args[:1] == ['ensure']:
        return ensure()
    if args[:1] == ['toggle']:
        if STATE.exists():
            return main(['unpin'])
        pane = focused_pane()
        tab = herdr('pane', 'layout', '--pane', pane)['layout']['tab_id']
        widget = next((w for w in widgets() if w['tab_id'] == tab), None)
        if widget is None:
            return main(['pin', 'right'])
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(side_of(widget, pane))
        return
    if args[:1] == ['unpin']:
        STATE.unlink(missing_ok=True)
        tab = herdr('pane', 'layout', '--pane', focused_pane())['layout']['tab_id']
        for pane in widgets():
            if pane['tab_id'] != tab:
                herdr('pane', 'close', pane['pane_id'])
        return
    if args[:1] == ['pin']:
        side = args[1] if len(args) > 1 else 'right'
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(side)
        pane = focused_pane()
        tab = herdr('pane', 'layout', '--pane', pane)['layout']['tab_id']
        found = widgets()
        for extra in found[1:]:
            herdr('pane', 'close', extra['pane_id'])
        # Re-dock even a widget in this tab, so it moves to the chosen side.
        print(dock(side, pane, found[0]['pane_id'] if found else None))
        return
    print(dock(args[0] if args else 'right', focused_pane()))


if __name__ == '__main__':
    main(sys.argv[1:])
