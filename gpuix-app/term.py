#!/usr/bin/env python3
"""Run a GPUIX terminal app inside Herdr with working mouse input.

GPUIX asks the terminal for SGR pixel mouse reports (mode 1016). Herdr forwards
mouse reports in character cells instead, so every click and wheel event lands
near the top-left corner. This relay runs the app in its own pseudo-terminal,
passes all output through unchanged, and rewrites each incoming mouse report from
cells to the pixel centre of that cell. Everything else, keys included, passes
through as is.

    python3 term.py bun app.tsx --view=accounts
"""
import fcntl
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import tty

MOUSE = re.compile(rb'\x1b\[<(\d+);(\d+);(\d+)([Mm])')
KEEP_HOVER = os.environ.get('MAKO_TERMINAL_HOVER') == '1'


def winsize(fd):
    return struct.unpack('HHHH', fcntl.ioctl(fd, termios.TIOCGWINSZ, bytes(8)))


def drop_motion(data):
    """Drop plain pointer motion (button code 35). Every move would repaint hover states and send
    a whole new frame through Herdr, which made the app lag. Presses, drags and the wheel stay."""
    return re.sub(rb'\x1b\[<35;\d+;\d+M', b'', data)


def to_pixels(data, size):
    """Rewrite SGR cell reports to pixel reports for a pane of rows x cols in xpix x ypix."""
    rows, cols, xpix, ypix = size
    if not (rows and cols and xpix and ypix):
        return data
    cell_w, cell_h = xpix / cols, ypix / rows

    def convert(match):
        button, col, row, kind = match.groups()
        x = int((int(col) - 0.5) * cell_w)
        y = int((int(row) - 0.5) * cell_h)
        return b'\x1b[<%s;%d;%d%s' % (button, x, y, kind)
    return MOUSE.sub(convert, data)


def main(argv):
    if not argv:
        sys.exit(__doc__)
    stdin = sys.stdin.fileno()
    size = winsize(stdin)
    pid, master = pty.fork()
    if pid == 0:
        os.execvp(argv[0], argv)
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', *size))

    def resized(*_):
        nonlocal size
        size = winsize(stdin)
        # Setting the size on the master signals SIGWINCH to the app.
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', *size))
    signal.signal(signal.SIGWINCH, resized)

    saved = termios.tcgetattr(stdin)
    tty.setraw(stdin)
    pending = b''
    try:
        while True:
            try:
                ready = select.select([stdin, master], [], [])[0]
            except InterruptedError:
                continue
            if master in ready:
                try:
                    out = os.read(master, 1 << 16)
                except OSError:
                    break
                if not out:
                    break
                os.write(sys.stdout.fileno(), out)
            if stdin in ready:
                data = pending + os.read(stdin, 1 << 16)
                # Keep a report split across two reads until it is complete.
                cut = data.rfind(b'\x1b[<')
                if cut != -1 and not re.search(rb'[Mm]', data[cut:]):
                    data, pending = data[:cut], data[cut:]
                else:
                    pending = b''
                data = data if KEEP_HOVER else drop_motion(data)
                if data:
                    os.write(master, to_pixels(data, size))
    finally:
        termios.tcsetattr(stdin, termios.TCSADRAIN, saved)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    _, status = os.waitpid(pid, 0)
    sys.exit(os.waitstatus_to_exitcode(status))


if __name__ == '__main__':
    main(sys.argv[1:])
