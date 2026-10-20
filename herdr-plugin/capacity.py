#!/usr/bin/env python3
"""Mako Capacity widget for a Herdr pane: percent used per account."""
import base64
import json
import math
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import struct
import threading
import time
import zlib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from platform_paths import cache_dir  # noqa: E402

PROVIDER = {'Claude': (230, 152, 96), 'Codex': (92, 214, 179), 'Cursor': (179, 132, 242)}
STATES = {'loginRequired': 'Reconnect', 'rateLimited': 'Throttled', 'stale': 'Cached',
          'unavailable': 'Unavailable'}


def rgb(color, text):
    return '\x1b[38;2;%d;%d;%dm%s\x1b[0m' % (*color, text)


def dim(text):
    return '\x1b[2m%s\x1b[0m' % text


def used(account):
    # Same rule as the dock: Cursor shows Cursor Models, others the tightest window.
    values = [w['used'] for w in account.get('windows', [])
              if account['provider'] != 'Cursor' or w['label'] == 'Cursor Models']
    return max(values) if values else None


def signal_color(account, value):
    if account.get('status') == 'loginRequired':
        return (255, 159, 10)
    value = value or 0
    return (255, 69, 58) if value >= 100 else (255, 159, 10) if value >= 85 else \
        (255, 214, 10) if value >= 70 else (48, 209, 88)


def state(account, value):
    if account.get('status') == 'live':
        return 'At limit' if (value or 0) >= 100 else 'Available'
    return STATES.get(account.get('status'), 'Unknown')


def countdown(reset, now):
    if not reset:
        return ''
    left = int(reset - now)
    if left <= 0:
        return 'now'
    days, hours, minutes = left // 86400, left % 86400 // 3600, left % 3600 // 60
    return f'{days}d{hours}h' if days else f'{hours}h{minutes:02d}' if hours else f'{max(minutes, 1)}m'


def fit(text, width):
    return text if len(text) <= width else text[:max(width - 1, 0)] + '…'


# Cursor's cube from the dock (design.rs): white body, dark facet, 24-unit box.
CUBE = [(12, .13), (1.89, 5.68), (1.47, 6.4), (1.47, 17.59), (1.89, 18.31), (11.5, 23.86),
        (12.5, 23.86), (22.11, 18.31), (22.53, 17.59), (22.53, 6.4), (22.11, 5.68), (12.5, .13)]
FACET = [(2.66, 6.34), (21.21, 6.34), (21.51, 6.85), (12.23, 22.92), (12, 22.86), (12, 12.34),
         (11.7, 11.83), (2.59, 6.57)]


def png_alpha(path):
    """Decode an 8-bit RGBA, non-interlaced PNG (the dock's icons) into (width, height, alpha bytes)."""
    data, idat = Path(path).read_bytes(), b''
    width, height = struct.unpack('>II', data[16:24])
    position = 8
    while position < len(data):
        length, kind = struct.unpack('>I4s', data[position:position + 8])
        if kind == b'IDAT':
            idat += data[position + 8:position + 8 + length]
        position += length + 12
    raw, stride = zlib.decompress(idat), width * 4
    previous, alpha = bytearray(stride), bytearray()
    for y in range(height):
        kind, row = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            left = row[i - 4] if i >= 4 else 0
            up = previous[i]
            if kind == 1:
                row[i] = (row[i] + left) & 255
            elif kind == 2:
                row[i] = (row[i] + up) & 255
            elif kind == 3:
                row[i] = (row[i] + (left + up) // 2) & 255
            elif kind == 4:
                corner = previous[i - 4] if i >= 4 else 0
                guess = left + up - corner
                pa, pb, pc = abs(guess - left), abs(guess - up), abs(guess - corner)
                row[i] = (row[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)) & 255
        alpha += row[3::4]
        previous = row
    return width, height, alpha


def inside(points, x, y):
    result = False
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            result = not result
    return result


def icon_mask(provider, size):
    """Provider icon as size*size alpha values (0-1), 3x3 supersampled like the dock's white glyph."""
    samples = [(i + .5) / 3 for i in range(3)]
    if provider == 'Cursor':
        def coverage(x, y):
            return sum(inside(CUBE, (x + sx) / size * 24, (y + sy) / size * 24) and
                       not inside(FACET, (x + sx) / size * 24, (y + sy) / size * 24)
                       for sx in samples for sy in samples) / 9
    else:
        name = ROOT / 'Resources' / f'{provider.lower()}.png'
        if not name.exists():
            return [0.0] * size * size
        width, height, alpha = png_alpha(name)

        def coverage(x, y):
            return sum(alpha[int((y + sy) / size * height) * width + int((x + sx) / size * width)]
                       for sx in samples for sy in samples) / 9 / 255
    return [coverage(x, y) for y in range(size) for x in range(size)]


def ring_png(value, color, icon=None, size=96, icon_size=36):
    """Progress ring as PNG bytes: arc = percent used, provider icon (alpha mask) in the centre.

    The ring leaves a transparent margin, so stacked rings keep a gap even without blank rows.
    """
    pixels = bytearray(size * size * 4)
    centre, outer, inner = size / 2, size / 2 - 10, size / 2 - 20
    offset = (size - icon_size) // 2
    sweep = min(max(value or 0, 0), 100) / 100 * 2 * math.pi
    for y in range(size):
        for x in range(size):
            dx, dy = x + .5 - centre, y + .5 - centre
            distance = math.hypot(dx, dy)
            band = min(distance - inner, outer - distance) + .5
            ix, iy = x - offset, y - offset
            if band > 0:
                angle = math.atan2(dx, -dy) % (2 * math.pi)
                rgb_value = color if angle <= sweep else (62, 62, 70)
                alpha = min(band, 1)
            elif icon and 0 <= ix < icon_size and 0 <= iy < icon_size and icon[iy * icon_size + ix] > 0:
                rgb_value, alpha = (255, 255, 255), icon[iy * icon_size + ix]
            else:
                continue
            pixels[(y * size + x) * 4:(y * size + x + 1) * 4] = bytes((*rgb_value, round(alpha * 255)))
    rows = b''.join(b'\x00' + bytes(pixels[y * size * 4:(y + 1) * size * 4]) for y in range(size))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)) + \
        chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


def kitty_image(png, offset=0):
    """Kitty graphics escape that draws a 4x2-cell image without moving the cursor.

    offset shifts the image right by that many pixels inside its first cell.
    """
    data = base64.b64encode(png).decode()
    parts = [data[i:i + 4096] for i in range(0, len(data), 4096)]
    out = ''
    for index, part in enumerate(parts):
        more = int(index < len(parts) - 1)
        keys = f'f=100,a=T,c=4,r=2,C=1,q=2,X={offset},m={more}' if index == 0 else f'm={more}'
        out += f'\x1b_G{keys};{part}\x1b\\'
    return out


def count(value):
    return f'{value / 1e6:.1f}M' if value >= 1e6 else f'{value / 1e3:.1f}K' if value >= 1e3 else f'{value:.0f}'


RING_ONLY = 12


def ring_place(width, cell=0):
    """1-based column and pixel offset of each ring, centred when the pane shows rings only.

    cell is the cell width in pixels. An odd spare column splits between both sides.
    """
    if width >= RING_ONLY:
        return 2, 0
    if not cell:
        return (width - 4) // 2 + 1, 0
    left = max(width - 4, 0) * cell // 2
    return left // cell + 1, left % cell


def cell_width():
    import fcntl
    import termios
    try:
        _, columns, pixels, _ = struct.unpack('HHHH', fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, bytes(8)))
    except OSError:
        return 0
    return pixels // columns if columns else 0


def compact(accounts, width, rings, height):
    """Narrow pane: ring (or provider dot), percent and a short name per account.

    Under RING_ONLY columns it shows the centred ring alone (text fallback: percent).
    """
    indent = 6 if rings else 2
    for gap in (True, False):
        lines, placed = ([''] if width < RING_ONLY else [fit('Capacity', width), '']), []
        for account in accounts:
            value = used(account)
            if width < RING_ONLY:
                pct = '—' if value is None else f'{value:.0f}%'
                placed.append((len(lines), account))
                lines += ['', ''] if rings else [' ' * ((width - len(pct)) // 2) + rgb(signal_color(account, value), pct)]
                if gap:
                    lines.append('')
                continue
            lead = ' ' * indent if rings else rgb(PROVIDER.get(account['provider'], (200, 200, 200)), '●') + ' '
            placed.append((len(lines), account))
            lines.append(lead + rgb(signal_color(account, value), '—' if value is None else f'{value:.0f}%'))
            lines.append(' ' * indent + dim(fit(account.get('title') or '?', width - indent)))
            if gap:
                lines.append('')
        if height is None or len(lines) <= height:
            break
    return lines, placed if rings else []


def render(snapshot, hidden, width, now, rings=False, height=None):
    """Return (lines, ring rows). Plain text never exceeds width.

    Under 30 columns the pane is compact (ring and percent only). From 50
    columns it is extended: plan, email, full window labels, notes and today's
    local usage. With rings, each account keeps a 4x2-cell gap after a
    one-column margin on its first two rows, and ring rows lists (line index, account) for the
    image overlay. Detail drops (extras and blank lines, then all but the
    tightest window bar, then bars) until the result fits height.
    """
    width = max(width, 4)
    accounts = [a for a in snapshot.get('accounts', []) if a.get('id') not in hidden]
    if width < 30:
        return compact(accounts, width, rings, height)
    extended = width >= 50
    age = int(now - snapshot['updatedAt']) // 60 if snapshot.get('updatedAt') else None
    header = 'Mako Capacity'
    note = '' if age is None else 'now' if age < 1 else f'{age}m ago'
    label_width = 16 if extended else 9 if width < 40 else 13
    for detail in (3, 2, 1, 0):
        lines = [header + ' ' * (width - len(header) - len(note)) + dim(note) if len(header) + len(note) < width
                 else fit(header, width), '']
        placed = []
        if not accounts:
            lines.append(dim(fit('No accounts yet. Run the dock or collector.', width)))
        for account in accounts:
            value = used(account)
            color = signal_color(account, value)
            pct = '—' if value is None else f'{value:.0f}%'
            lead = '      ' if rings else rgb(PROVIDER.get(account['provider'], (200, 200, 200)), '●') + ' '
            indent = 6 if rings else 2
            title = fit(account.get('title') or account.get('email') or '?', width - len(pct) - indent - 1)
            gap = ' ' * (width - indent - len(title) - len(pct))
            placed.append((len(lines), account))
            lines.append(lead + title + gap + rgb(color, pct))
            info = [account['provider']]
            if extended and account.get('plan') and account['provider'] != 'Claude':
                info.append(account['plan'])
            info.append(state(account, value))
            if extended and detail == 3 and account.get('email'):
                info.append(account['email'])
            lines.append(' ' * indent + dim(fit(' · '.join(info), width - indent)))
            windows = account.get('windows', [])
            if detail == 1:
                windows = [max(windows, key=lambda w: w['used'])] if windows else []
            for window in windows if detail else []:
                label = window['label'] if extended else window['label'].replace('Weekly · ', 'Wk ')
                label = fit(label, label_width).ljust(label_width)
                reset = countdown(window.get('resetAt'), now)
                tail = (window.get('detail') or (reset and '↻ ' + reset)).rjust(12) if extended else reset.rjust(5)
                bar_width = width - 2 - label_width - 1 - 1 - 4 - 1 - len(tail)
                fill = round(min(max(window['used'], 0), 100) / 100 * bar_width)
                bar = rgb(signal_color({}, window['used']), '━' * fill) + dim('─' * (bar_width - fill))
                lines.append(f"  {label} {bar} {window['used']:3.0f}%{dim(' ' + tail)}")
            if detail == 3 and account.get('message') and (extended or account.get('status') != 'live'):
                lines.append('  ' + dim(fit(account['message'], width - 2)))
            if detail == 3 or not rings:
                lines.append('')
        if extended and detail == 3:
            # CodeBurn counts local usage per provider, not per account.
            today = {}
            for account in accounts:
                usage = account.get('localUsage') or {}
                if usage.get('tokens'):
                    today.setdefault(account['provider'], usage)
            for provider, usage in today.items():
                cost = '' if usage.get('costUsd') is None else f" · ${usage['costUsd']:.2f} API-equivalent"
                lines.append(dim(fit(f"Today · local {provider}: {count(usage['tokens'])} tokens{cost}", width)))
            if today:
                lines.append('')
        lines.append(dim(fit(f"r refresh · p {'unpin' if pinned() else 'pin'} · q quit", width)))
        if height is None or len(lines) <= height:
            break
    return lines, placed if rings else []


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def hidden_ids():
    home = Path(os.environ.get('MAKO_CAPACITY_HOME', Path.home() / '.mako-capacity'))
    return set(read_json(home / 'hidden.json', {}))


def pin_state():
    return Path(os.environ.get('HERDR_PLUGIN_STATE_DIR') or Path.home() / '.mako-capacity') / 'pinned-side'


def pinned():
    return pin_state().exists()


def toggle_pin():
    # This pane is the focused one for open.py, so pinning keeps it and unpinning spares it.
    subprocess.run([sys.executable, str(Path(__file__).with_name('open.py')), 'toggle'],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False,
                   env=dict(os.environ, HERDR_PLUGIN_CONTEXT_JSON='{}'))


def collect(force=False):
    """Run the collector unless another process just did, or is doing it now."""
    import fcntl
    snapshot = cache_dir() / 'snapshot.json'
    try:
        if not force and time.time() - snapshot.stat().st_mtime < 55:
            return
    except OSError:
        pass
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    with open(snapshot.parent / '.collect.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return
        args = [sys.executable, str(ROOT / 'collector.py'), '--skip-usage'] + (['--refresh'] if force else [])
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120, check=False)


def supports_graphics():
    """Ask the terminal for Kitty graphics support; Herdr answers when it is enabled."""
    if os.environ.get('MAKO_CAPACITY_RINGS') == '0' or not sys.stdin.isatty():
        return False
    sys.stdout.write('\x1b_Gi=31,s=1,v=1,a=q,t=d,f=24;AAAA\x1b\\\x1b[c')
    sys.stdout.flush()
    reply = b''
    while not reply.endswith(b'c') and select.select([sys.stdin], [], [], 1)[0]:
        reply += os.read(sys.stdin.fileno(), 256)
    return b'_Gi=31;OK' in reply


def main():
    import termios
    import tty
    wake_r, wake_w = os.pipe()
    wake = lambda *_: os.write(wake_w, b'.')  # noqa: E731
    resized = []
    signal.signal(signal.SIGWINCH, lambda *_: (resized.append(1), wake()))

    def poll(force=False):
        collect(force)
        wake()

    # ponytail: the collector skips accounts polled within five minutes, so a minute loop is cheap.
    def loop():
        while True:
            poll()
            time.sleep(60)
    threading.Thread(target=loop, daemon=True).start()
    saved = termios.tcgetattr(sys.stdin) if sys.stdin.isatty() else None
    if saved:
        tty.setcbreak(sys.stdin)
    rings = supports_graphics()
    cache, icons, last = {}, {}, None
    sys.stdout.write('\x1b[?25l')
    try:
        while True:
            size = shutil.get_terminal_size()
            lines, placed = render(read_json(cache_dir() / 'snapshot.json', {}), hidden_ids(), size.columns,
                                   time.time(), rings, size.lines)
            out = '\x1b_Ga=d,d=A,q=2\x1b\\' if rings else ''
            out += '\x1b[H\x1b[2J' + '\n'.join(lines[:size.lines])
            column, offset = ring_place(size.columns, cell_width())
            for row, account in placed:
                if row + 2 <= size.lines:
                    value = used(account)
                    key = (round(value or 0), signal_color(account, value), account['provider'], offset)
                    if key not in cache:
                        if key[2] not in icons:
                            icons[key[2]] = icon_mask(key[2], 36)
                        cache[key] = kitty_image(ring_png(key[0], key[1], icons[key[2]]), offset)
                    out += f'\x1b[{row + 1};{column}H' + cache[key]
            # Rewrite only on change: each frame resends every ring image to Herdr and its clients.
            if out != last or resized:
                resized.clear()
                last = out
                sys.stdout.write(out)
                sys.stdout.flush()
            ready = select.select([wake_r] + ([sys.stdin] if saved else []), [], [], 10)[0]
            if wake_r in ready:
                os.read(wake_r, 64)
            if sys.stdin in ready:
                key = sys.stdin.read(1)
                if key == 'q':
                    break
                if key == 'r':
                    threading.Thread(target=poll, args=(True,), daemon=True).start()
                if key == 'p':
                    threading.Thread(target=lambda: (toggle_pin(), wake()), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(('\x1b_Ga=d,d=A,q=2\x1b\\' if rings else '') + '\x1b[?25h\x1b[0m\n')
        if saved:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, saved)


MARK = {'Claude': '✳', 'Codex': '◎', 'Cursor': '⬡'}


def status_line(snapshot, hidden):
    """One plain line for Herdr's tab bar (it prints ANSI codes literally): mark, then a pie and percent per account."""
    groups = {}
    for account in snapshot.get('accounts', []):
        if account.get('id') in hidden:
            continue
        value = used(account)
        pie = '○' if value is None else '○◔◑◕●'[min(4, round(value / 25))]
        groups.setdefault(account['provider'], []).append(pie + ('—' if value is None else f'{value:.0f}'))
    return '  '.join(MARK.get(provider, provider[0]) + ' ' + ' '.join(values) for provider, values in groups.items())


if __name__ == '__main__':
    if '--status' in sys.argv:
        collect()
        print(status_line(read_json(cache_dir() / 'snapshot.json', {}), hidden_ids()))
    else:
        main()
