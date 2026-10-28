#!/usr/bin/env python3
"""Mako Capacity agents widget for a Herdr pane, in plain text: every agent, its timed steps and its subagents.

Keys: up/down or j/k move, enter opens a card, esc goes back, g goes to the agent's pane,
i shows idle agents, a shows recent activity, r refreshes, q quits. A click opens a row.
"""
import fcntl
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import textwrap
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capacity import ROOT, cache_dir, dim, fit, home, read_json, rgb  # noqa: E402

# The app's three colours: yellow while it works, red when it needs you, green when it finished.
YELLOW, RED, GREEN, GREY = (255, 214, 10), (255, 69, 58), (48, 209, 88), (142, 142, 147)
STATUS = {'working': (YELLOW, 'Working'), 'blocked': (RED, 'Needs you'), 'done': (GREEN, 'Finished'), 'idle': (GREY, 'Idle')}
PROVIDER = {'claude': ((230, 152, 96), 'CLAUDE'), 'codex': ((92, 214, 179), 'CODEX')}


def bold(text):
    return '\x1b[1m%s\x1b[22m' % text


def snapshot_path():
    return Path(os.environ.get('MAKO_AGENTS_SNAPSHOT') or cache_dir() / 'agents.json')


def settings():
    return read_json(home() / 'settings.json', {})


def save_setting(key, on):
    path = home() / 'settings.json'
    values = read_json(path, {})
    if on:
        values[key] = '1'
    else:
        values.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__('json').dumps(values, indent=2) + '\n')
    path.chmod(0o600)


def span(seconds):
    """A length of time, short: 45s, 12m, 3h 20m, 2d 4h. The same rule as the dock."""
    s = max(0, round(seconds))
    if s < 60:
        return f'{s}s'
    if s < 3600:
        return f'{s // 60}m'
    if s < 86400:
        return f'{s // 3600}h' + (f' {s % 3600 // 60}m' if s % 3600 >= 60 else '')
    return f'{s // 86400}d' + (f' {s % 86400 // 3600}h' if s % 86400 >= 3600 else '')


def run_time(item, running, now):
    started, updated = item.get('started'), item.get('updated')
    if not started:
        return ''
    if running:
        return f'Running for {span(now - started)}'
    return f'Took {span(updated - started)}' if updated else ''


def pie(value):
    return '○◔◑◕●'[min(4, max(0, round((value or 0) / 25)))]


def count(value):
    value = value or 0
    for size, unit in ((1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if value >= size:
            return f'{value / size:.1f}{unit}'
    return f'{value:.0f}'


def cost_line(usage):
    if not usage:
        return None
    cost = '$—' if usage.get('cost') is None else f"${usage['cost']:,.2f}"
    week = usage.get('weekPercent')
    share = '' if week is None else ' · <1% of a week' if week < 1 else f' · ~{week:.0f}% of a week'
    return cost + share


def width_of(text):
    """Visible width of a line with colour codes."""
    plain, skip = 0, False
    for char in text:
        if char == '\x1b':
            skip = True
        elif skip and char in 'mHJK':
            skip = False
        elif not skip:
            plain += 1
    return plain


def edge(left, right, width):
    """Left text, then right text against the right edge."""
    gap = width - width_of(left) - width_of(right)
    return left + ' ' * max(1, gap) + right


def sub_state(sub):
    if sub.get('running'):
        return YELLOW, 'Working'
    return (GREY, 'Idle') if sub.get('idle') else (GREEN, 'Finished')


def agent_live(agent):
    return agent.get('status') in ('working', 'blocked')


def shown_agents(snapshot, values):
    agents = snapshot.get('agents') or []
    if values.get('SHOW_IDLE_AGENTS') != '1':
        agents = [a for a in agents if a.get('status') != 'idle']
    return agents


def find_sub(subs, sub_id):
    for sub in subs or []:
        if sub.get('id') == sub_id:
            return sub
        found = find_sub(sub.get('children'), sub_id)
        if found:
            return found
    return None


class Screen:
    """Lines to draw, with the item each selectable line opens."""

    def __init__(self, width):
        self.width, self.lines, self.targets = width, [], []

    def add(self, text='', target=None):
        self.lines.append(text)
        self.targets.append(target)

    def wrap(self, text, indent='', style=lambda t: t, limit=3):
        rows = textwrap.wrap(text or '', max(8, self.width - len(indent))) or ['']
        for row in rows[:limit]:
            self.add(indent + style(row))


def list_view(agents, width, selected, now):
    screen = Screen(width)
    states = [a.get('status') for a in agents]
    running = sum(1 for a in agents for s in a.get('subagents') or [] if s.get('running'))
    summary = [f'{states.count("working")} working' if 'working' in states else '',
               f'{states.count("blocked")} need you' if 'blocked' in states else '',
               f'{running} subagents running' if running else '',
               f'{states.count("done")} finished' if 'done' in states else '']
    screen.add(edge(bold('Agents'), dim(fit(' · '.join(s for s in summary if s), max(0, width - 8))), width))
    screen.add()
    if not agents:
        screen.add(dim('No agents run now.'))
        return screen
    for index, agent in enumerate(agents):
        colour, label = STATUS.get(agent.get('status'), STATUS['idle'])
        mark = rgb(colour, pie(agent.get('progress') if agent.get('progress') is not None else 100 if agent.get('status') == 'done' else 8))
        pointer = rgb(colour, '›') if index == selected else ' '
        name = agent.get('name') or agent.get('project') or 'agent'
        pct = '' if agent.get('progress') is None else rgb(colour, f"{agent['progress']}%")
        title = agent.get('task') or agent.get('title') or name
        target = ('agent', agent['id'])
        if not agent_live(agent):
            text = fit(title, max(8, width - 18))
            screen.add(edge(f'{pointer}{mark} {bold(text) if index == selected else text}', dim(label), width), target)
            continue
        screen.add(edge(f'{pointer}{mark} {dim(fit(name, max(6, width - 20)))} {rgb(colour, label)}', pct, width), target)
        screen.add('   ' + bold(fit(title, width - 3)), target)
        steps = agent.get('stepCount')
        bar_width = max(6, width - 12)
        filled = round(bar_width * (agent.get('progress') or 0) / 100)
        screen.add('   ' + rgb(colour, '━' * filled) + dim('─' * (bar_width - filled)) +
                   (dim(f' {steps[0]}/{steps[1]}') if steps else ''), target)
        if agent.get('now'):
            screen.add('   ' + dim(fit('▸ ' + agent['now'], width - 3)), target)
        subs = [s for s in agent.get('subagents') or [] if s.get('running')]
        if subs:
            screen.add('   ' + rgb(YELLOW, f'{len(subs)} subagent{"s" if len(subs) > 1 else ""} running'), target)
        screen.add()
    return screen


def step_lines(screen, steps, colour, now):
    for step in steps:
        status = step.get('status')
        mark = rgb(GREEN, '●') if status == 'done' else rgb(colour, '◉') if status == 'active' else dim('○')
        took = span(step['took']) if step.get('took') else span(now - step['since']) if step.get('since') and status == 'active' else ''
        title = fit(step.get('title') or '', max(6, screen.width - 10))
        if status == 'active':
            title = rgb(colour, title)
        elif status != 'done':
            title = dim(title)
        screen.add(edge(f' {mark} {title}', dim(took), screen.width))


def detail_view(item, kind, width, selected, now, values):
    """The card of an agent or a subagent: task, timed steps, subagents, tokens."""
    screen = Screen(width)
    if kind == 'agent':
        colour, label = STATUS.get(item.get('status'), STATUS['idle'])
        running = agent_live(item)
        provider_colour, provider = PROVIDER.get(item.get('agent'), (GREY, (item.get('agent') or '').upper()))
        head = rgb(provider_colour, provider) + ' ' + rgb(colour, label)
        name = ' · '.join(x for x in (item.get('name'), item.get('tabName')) if x)
        title = item.get('task') or item.get('title') or name
        subs = item.get('subagents') or []
    else:
        colour, label = sub_state(item)
        running = bool(item.get('running'))
        kind_label = 'WORKFLOW' if item.get('kind') == 'workflow' else (item.get('name') or 'subagent').upper()
        head = dim(kind_label) + ' ' + rgb(colour, label) + (dim(' · ' + item['model']) if item.get('model') else '')
        name = item.get('name') if item.get('kind') == 'workflow' else ''
        title = item.get('description') or item.get('name') or 'Subagent'
        subs = item.get('children') or []
    progress = item.get('progress')
    pct = '' if progress is None else rgb(colour, f'{pie(progress)} {progress}%')
    screen.add(edge(dim('‹ esc') + '  ' + head, pct, width))
    if name:
        screen.add(dim(fit(name, width)))
    screen.add()
    screen.wrap(title, style=bold)
    step_now = item.get('now') if kind == 'agent' else item.get('step') if running else None
    if step_now:
        screen.add()
        screen.wrap('▸ ' + step_now, style=lambda t: rgb(colour, t), limit=2)
    steps = item.get('steps') or []
    if steps:
        done = sum(1 for s in steps if s.get('status') == 'done')
        screen.add()
        screen.add(dim(f'{"PHASES" if item.get("kind") == "workflow" else "STEPS"} · {done} OF {len(steps)}'))
        step_lines(screen, steps, colour, now)
    if subs:
        active = sum(1 for s in subs if s.get('running'))
        screen.add()
        screen.add(dim(f'SUBAGENTS · {len(subs)}' + (f', {active} RUNNING' if active else '')))
        for index, sub in enumerate(subs):
            sub_colour, sub_label = sub_state(sub)
            value = sub.get('progress')
            pointer = rgb(sub_colour, '›') if index == selected else ' '
            heading = sub.get('name') if sub.get('kind') == 'workflow' else sub.get('description') or sub.get('name') or 'Subagent'
            right = rgb(sub_colour, f'{value}%') if value is not None else ''
            text = fit(heading, max(6, width - 12))
            screen.add(edge(f'{pointer}{rgb(sub_colour, pie(value if value is not None else 20 if sub.get("running") else 100))} {bold(text) if index == selected else text}', right, width), ('sub', sub['id']))
            detail = sub.get('step') if sub.get('running') else sub_label
            extra = sub.get('summary') if sub.get('kind') == 'workflow' else None
            time_text = run_time(sub, sub.get('running'), now)
            screen.add('   ' + dim(fit(' · '.join(x for x in (('▸ ' + detail) if sub.get('running') and detail else detail, extra, time_text) if x), width - 3)), ('sub', sub['id']))
    usage = item.get('usage')
    total = item.get('totalUsage') if kind == 'agent' else None
    if usage or total:
        screen.add()
        screen.add(dim('TOKENS'))
        if usage:
            screen.add(edge(' This ' + ('agent' if kind == 'agent' else 'subagent'), cost_line(usage), width))
        if total and subs:
            screen.add(edge(' With subagents', cost_line(total), width))
        shown = total or usage
        screen.add(' ' + dim(fit(f"in {count(shown.get('input'))} · out {count(shown.get('output'))} · cache {count(shown.get('cacheRead'))} read · {count(shown.get('cacheWrite'))} write", width - 1)))
    activity = item.get('activity') or []
    if activity and values.get('SHOW_AGENT_ACTIVITY') == '1':
        screen.add()
        screen.add(dim('RECENT ACTIVITY'))
        for event in activity[-4:]:
            screen.add(' ' + dim(fit(('› ' if event.get('kind') == 'tool' else '“ ') + event.get('text', ''), width - 1)))
    screen.add()
    footer = [run_time(item, running, now)]
    if kind == 'agent' and item.get('pane'):
        footer.append('pane ' + item['pane'])
    screen.add(dim(fit(' · '.join(x for x in footer if x), width)))
    return screen


def refresh(force=False):
    """Run agents.py unless another process just did, or does it now. The dock and the GPUIX app run it too."""
    if os.environ.get('MAKO_AGENTS_SNAPSHOT'):
        return
    path = snapshot_path()
    try:
        if not force and time.time() - path.stat().st_mtime < 5:
            return
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.parent / '.agents.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return
        subprocess.run([sys.executable, str(ROOT / 'agents.py')], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=120, check=False)


def go_to_pane(pane):
    herdr = os.environ.get('HERDR_BIN_PATH', 'herdr')
    subprocess.run([herdr, 'agent', 'focus', pane], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)


def keys_of(data):
    """Split terminal input into key names and SGR mouse events (button, column, row)."""
    out, i = [], 0
    while i < len(data):
        if data.startswith('\x1b[<', i):
            end = next((j for j in range(i, len(data)) if data[j] in 'Mm'), None)
            if end is None:
                break
            try:
                button, column, row = (int(x) for x in data[i + 3:end].split(';'))
            except ValueError:
                button = -1
            if data[end] == 'M' and button in (0, 64, 65):
                out.append(('mouse', button, column, row))
            i = end + 1
        elif data.startswith('\x1b[A', i) or data.startswith('\x1bOA', i):
            out.append('up'); i += 3  # noqa: E702
        elif data.startswith('\x1b[B', i) or data.startswith('\x1bOB', i):
            out.append('down'); i += 3  # noqa: E702
        elif data.startswith('\x1b[C', i):
            out.append('enter'); i += 3  # noqa: E702
        elif data.startswith('\x1b[D', i):
            out.append('back'); i += 3  # noqa: E702
        elif data[i] == '\x1b':
            out.append('back'); i += 1  # noqa: E702
        else:
            out.append({'\r': 'enter', '\n': 'enter', 'l': 'enter', 'h': 'back', '\x7f': 'back',
                        'k': 'up', 'j': 'down'}.get(data[i], data[i]))
            i += 1
    return out


def main(start=()):
    import termios
    import tty
    wake_r, wake_w = os.pipe()
    wake = lambda *_: os.write(wake_w, b'.')  # noqa: E731
    signal.signal(signal.SIGWINCH, wake)

    def loop():
        seen = None
        while True:
            refresh()
            try:
                changed = snapshot_path().stat().st_mtime
            except OSError:
                changed = None
            if changed != seen:
                seen = changed
                wake()
            time.sleep(2)
    threading.Thread(target=loop, daemon=True).start()
    saved = termios.tcgetattr(sys.stdin) if sys.stdin.isatty() else None
    if saved:
        tty.setcbreak(sys.stdin)
    # Hide the cursor and turn on click and wheel reports in SGR form.
    sys.stdout.write('\x1b[?25l\x1b[?1000h\x1b[?1006h')
    # --open AGENT [SUBAGENT ...] starts with those cards open, for screenshots and scripts.
    stack = [('agent', start[0])] + [('sub', key) for key in start[1:]] if start else []
    selected, offset, last = 0, 0, None
    try:
        while True:
            size = shutil.get_terminal_size()
            width, height, now = max(20, size.columns - 1), size.lines, time.time()
            values = settings()
            agents = shown_agents(read_json(snapshot_path(), {}), values)
            # Each card in the stack is found again by its id, so a refresh keeps it open.
            item, kind = None, None
            while stack:
                kind, key = stack[-1]
                agent = next((a for a in agents if a['id'] == stack[0][1]), None)
                item = agent if kind == 'agent' else find_sub((agent or {}).get('subagents'), key)
                if item:
                    break
                stack.pop()
            screen = detail_view(item, kind, width, selected, now, values) if item else list_view(agents, width, selected, now)
            rows = [i for i, target in enumerate(screen.targets) if target]
            choices = list(dict.fromkeys(screen.targets[i] for i in rows))
            selected = min(selected, max(0, len(choices) - 1))
            body = height - 1
            if choices:
                first = screen.targets.index(choices[selected])
                last_row = len(screen.targets) - 1 - screen.targets[::-1].index(choices[selected])
                offset = min(max(offset, last_row - body + 1), first)
            offset = max(0, min(offset, len(screen.lines) - body))
            hint = 'esc back · ↑↓ · ⏎ open' if stack else '↑↓ · ⏎ open'
            hint += (' · g go to pane' if stack and kind == 'agent' else '') + ' · i idle · a activity · q quit'
            frame = '\x1b[H\x1b[2J' + '\n'.join(screen.lines[offset:offset + body]) + f'\x1b[{height};1H' + dim(fit(hint, width))
            if frame != last:
                last = frame
                sys.stdout.write(frame)
                sys.stdout.flush()
            ready = select.select([wake_r] + ([sys.stdin] if saved else []), [], [], 1)[0]
            if wake_r in ready:
                os.read(wake_r, 64)
            if sys.stdin not in ready:
                continue
            for key in keys_of(os.read(sys.stdin.fileno(), 256).decode(errors='ignore')):
                if isinstance(key, tuple):
                    _, button, _column, row = key
                    if button in (64, 65):
                        offset += -3 if button == 64 else 3
                        continue
                    target = screen.targets[offset + row - 1] if 0 <= offset + row - 1 < len(screen.targets) else None
                    if row == 1 and stack:
                        key = 'back'
                    elif target in choices:
                        selected = choices.index(target)
                        key = 'enter'
                    else:
                        continue
                if key == 'q':
                    return
                if key == 'up':
                    selected = max(0, selected - 1)
                elif key == 'down':
                    selected = min(len(choices) - 1, selected + 1) if choices else 0
                elif key == 'enter' and choices:
                    stack.append(choices[selected])
                    selected, offset = 0, 0
                elif key == 'back' and stack:
                    stack.pop()
                    selected, offset = 0, 0
                elif key == 'g' and stack and kind == 'agent' and item.get('pane'):
                    threading.Thread(target=go_to_pane, args=(item['pane'],), daemon=True).start()
                elif key == 'i':
                    save_setting('SHOW_IDLE_AGENTS', values.get('SHOW_IDLE_AGENTS') != '1')
                elif key == 'a':
                    save_setting('SHOW_AGENT_ACTIVITY', values.get('SHOW_AGENT_ACTIVITY') != '1')
                elif key == 'r':
                    threading.Thread(target=lambda: (refresh(True), wake()), daemon=True).start()
                last = None
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write('\x1b[?1000l\x1b[?1006l\x1b[?25h\x1b[0m\n')
        if saved:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, saved)


def render_text(width=46, height=None, open_ids=()):
    """The screen as plain lines with colour codes, for tests and screenshots."""
    values = settings()
    agents = shown_agents(read_json(snapshot_path(), {}), values)
    now = time.time()
    if not open_ids:
        return list_view(agents, width, 0, now).lines
    agent = next(a for a in agents if a['id'] == open_ids[0])
    item = agent if len(open_ids) == 1 else find_sub(agent.get('subagents'), open_ids[-1])
    return detail_view(item, 'agent' if len(open_ids) == 1 else 'sub', width, 0, now, values).lines


if __name__ == '__main__':
    if '--print' in sys.argv:
        args = [a for a in sys.argv[1:] if a != '--print']
        size = shutil.get_terminal_size()
        print('\n'.join(render_text(int(os.environ.get('COLUMNS', size.columns)), None, args)))
    elif '--open' in sys.argv:
        main(sys.argv[sys.argv.index('--open') + 1:])
    else:
        main()
