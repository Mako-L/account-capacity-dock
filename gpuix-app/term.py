#!/usr/bin/env python3
"""Run a GPUIX terminal app inside Herdr without the lag.

GPUIX draws each frame as one Kitty graphics image the size of the pane. Herdr
copies every frame several times and, when its file path is off, streams it to
the terminal as text: about 19 MB a frame for a full-screen pane on a Retina
screen. This relay runs the app in its own pseudo-terminal and tells it the pane
has MAKO_TERMINAL_SCALE (default 0.5) of its real pixels, so each frame carries
a quarter of the pixels. It adds c= and r= to the frame so the terminal scales
the image back up to fill the pane, and scales mouse and resize reports to match.

It also drops plain pointer motion, which only repaints hover states, unless
MAKO_TERMINAL_HOVER=1. Herdr 0.8 forwards mouse reports in character cells, so
with MAKO_CONVERT_MOUSE=1 the relay rewrites each one to the pixel centre of its
cell. Everything else, keys included, passes through as is.

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
RESIZE = re.compile(rb'\x1b\[48;(\d+);(\d+);(\d+);(\d+)t')
FRAME = b'\x1b_Ga=T,i=1,p=1,'
KEEP_HOVER = os.environ.get('MAKO_TERMINAL_HOVER') == '1'
CONVERT_MOUSE = os.environ.get('MAKO_CONVERT_MOUSE') == '1'
SCALE = float(os.environ.get('MAKO_TERMINAL_SCALE') or 0.5)


def winsize(fd):
    return struct.unpack('HHHH', fcntl.ioctl(fd, termios.TIOCGWINSZ, bytes(8)))


def drop_motion(data):
    """Drop plain pointer motion (button code 35). Every move would repaint hover states and send
    a whole new frame through Herdr, which made the app lag. Presses, drags and the wheel stay."""
    return re.sub(rb'\x1b\[<35;\d+;\d+M', b'', data)


def app_size(size):
    """The pane as the app sees it: same cells, SCALE of the pixels."""
    rows, cols, xpix, ypix = size
    return rows, cols, int(xpix * SCALE), int(ypix * SCALE)


def scale_input(data):
    """Scale pixel mouse reports and in-band resize reports to the app's pixels."""
    data = MOUSE.sub(lambda m: b'\x1b[<%s;%d;%d%s' % (
        m[1], int(int(m[2]) * SCALE), int(int(m[3]) * SCALE), m[4]), data)
    return RESIZE.sub(lambda m: b'\x1b[48;%s;%s;%d;%dt' % (
        m[1], m[2], int(int(m[3]) * SCALE), int(int(m[4]) * SCALE)), data)


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
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', *app_size(size)))

    def resized(*_):
        nonlocal size
        size = winsize(stdin)
        # Setting the size on the master signals SIGWINCH to the app.
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', *app_size(size)))
    signal.signal(signal.SIGWINCH, resized)

    saved = termios.tcgetattr(stdin)
    tty.setraw(stdin)
    pending, held = b'', b''
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
                out = held + out
                # Keep a frame header split across two reads until it is whole.
                cut = out.rfind(b'\x1b', max(0, len(out) - len(FRAME)))
                out, held = (out[:cut], out[cut:]) if cut != -1 and FRAME.startswith(out[cut:]) else (out, b'')
                # Display the smaller frame over the whole pane.
                out = out.replace(FRAME, FRAME + b'c=%d,r=%d,' % (size[1], size[0]))
                os.write(sys.stdout.fileno(), out)
            if stdin in ready:
                data = pending + os.read(stdin, 1 << 16)
                # Keep a report split across two reads until it is complete.
                cut = data.rfind(b'\x1b[<')
                if cut != -1 and not re.search(rb'[Mm]', data[cut:]):
                    data, pending = data[:cut], data[cut:]
                else:
                    pending, held = b'', b''
                data = data if KEEP_HOVER else drop_motion(data)
                data = to_pixels(data, app_size(size)) if CONVERT_MOUSE else scale_input(data)
                if data:
                    os.write(master, data)
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
