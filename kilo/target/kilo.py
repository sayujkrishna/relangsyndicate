#!/usr/bin/env python3
"""Kilo - A very simple text editor in Python, ported from the C version
by Salvatore Sanfilippo (antirez). Uses VT100 escape sequences directly,
no curses dependency.
"""
import sys
import os
import time
import ctypes
import struct
import termios
import signal

KILO_VERSION = "0.0.1"

# Syntax highlight types
HL_NORMAL = 0
HL_NONPRINT = 1
HL_COMMENT = 2
HL_MLCOMMENT = 3
HL_KEYWORD1 = 4
HL_KEYWORD2 = 5
HL_STRING = 6
HL_NUMBER = 7
HL_MATCH = 8

HL_HIGHLIGHT_STRINGS = 1 << 0
HL_HIGHLIGHT_NUMBERS = 1 << 1


class EditorSyntax:
    def __init__(self, filematch, keywords, scs, mcs, mce, flags):
        self.filematch = filematch
        self.keywords = keywords
        self.scs = scs
        self.mcs = mcs
        self.mce = mce
        self.flags = flags


C_HL_extensions = [".c", ".h", ".cpp", ".hpp", ".cc"]
C_HL_keywords = [
    "auto", "break", "case", "continue", "default", "do", "else", "enum",
    "extern", "for", "goto", "if", "register", "return", "sizeof", "static",
    "struct", "switch", "typedef", "union", "volatile", "while", "NULL",
    "alignas", "alignof", "and", "and_eq", "asm", "bitand", "bitor", "class",
    "compl", "constexpr", "const_cast", "deltype", "delete", "dynamic_cast",
    "explicit", "export", "false", "friend", "inline", "mutable", "namespace",
    "new", "noexcept", "not", "not_eq", "nullptr", "operator", "or", "or_eq",
    "private", "protected", "public", "reinterpret_cast", "static_assert",
    "static_cast", "template", "this", "thread_local", "throw", "true", "try",
    "typeid", "typename", "virtual", "xor", "xor_eq",
    "int|", "long|", "double|", "float|", "char|", "unsigned|", "signed|",
    "void|", "short|", "auto|", "const|", "bool|",
]

HLDB = [
    EditorSyntax(C_HL_extensions, C_HL_keywords, "//", "/*", "*/",
                 HL_HIGHLIGHT_STRINGS | HL_HIGHLIGHT_NUMBERS),
]
HLDB_ENTRIES = len(HLDB)

# Key codes
CTRL_C = 3
CTRL_D = 4
CTRL_F = 6
CTRL_H = 8
TAB = 9
CTRL_L = 12
ENTER = 13
CTRL_Q = 17
CTRL_S = 19
CTRL_U = 21
ESC = 27
BACKSPACE = 127
ARROW_LEFT = 1000
ARROW_RIGHT = 1001
ARROW_UP = 1002
ARROW_DOWN = 1003
DEL_KEY = 1004
HOME_KEY = 1005
END_KEY = 1006
PAGE_UP = 1007
PAGE_DOWN = 1008


class ERow:
    def __init__(self, idx, chars):
        self.idx = idx
        self.chars = chars
        self.size = len(chars)
        self.render = ""
        self.rsize = 0
        self.hl = None
        self.hl_oc = 0


class EditorConfig:
    def __init__(self):
        self.cx = 0
        self.cy = 0
        self.rowoff = 0
        self.coloff = 0
        self.screenrows = 0
        self.screencols = 0
        self.numrows = 0
        self.rawmode = 0
        self.row = []
        self.dirty = 0
        self.filename = None
        self.statusmsg = ""
        self.statusmsg_time = 0
        self.syntax = None


E = EditorConfig()
ORIG_TERMIOS = None


def disable_raw_mode(fd):
    if E.rawmode:
        termios.tcsetattr(fd, termios.TCSAFLUSH, ORIG_TERMIOS)
        E.rawmode = 0


def editor_at_exit():
    disable_raw_mode(sys.stdin.fileno())


def enable_raw_mode(fd):
    global ORIG_TERMIOS
    if E.rawmode:
        return 0
    if not os.isatty(fd):
        return -1
    ORIG_TERMIOS = termios.tcgetattr(fd)
    import atexit
    atexit.register(editor_at_exit)
    raw = termios.tcgetattr(fd)
    raw[0] &= ~(termios.BRKINT | termios.ICRNL | termios.INPCK | termios.ISTRIP | termios.IXON)
    raw[1] &= ~(termios.OPOST)
    raw[2] |= termios.CS8
    raw[3] &= ~(termios.ECHO | termios.ICANON | termios.IEXTEN | termios.ISIG)
    raw[6][termios.VMIN] = 0
    raw[6][termios.VTIME] = 1
    termios.tcsetattr(fd, termios.TCSAFLUSH, raw)
    E.rawmode = 1
    return 0


def editor_read_key(fd):
    while True:
        c = os.read(fd, 1)
        if not c:
            continue
        b = c[0]
        if b == ESC:
            seq = os.read(fd, 1) if True else b''
            # We need to read with timeout; use simple approach
            import select
            rlist, _, _ = select.select([fd], [], [], 0.1)
            if not rlist:
                return ESC
            seq1 = os.read(fd, 1)[0]
            if not rlist:
                # didn't get second byte in time
                return ESC
            rlist2, _, _ = select.select([fd], [], [], 0.05)
            seq2 = b''
            if rlist2:
                seq2 = os.read(fd, 1)[0]
            # ESC [ sequences
            if seq1 == ord('['):
                if ord('0') <= seq2 <= ord('9'):
                    if seq2 == ord('~'):
                        # we already consumed two bytes after ESC, need more for third
                        pass
                    # Try to read the terminating char
                    rlist3, _, _ = select.select([fd], [], [], 0.05)
                    seq3 = b''
                    if rlist3:
                        seq3 = os.read(fd, 1)[0]
                    if seq3 == ord('~'):
                        if seq2 == ord('3'):
                            return DEL_KEY
                        if seq2 == ord('5'):
                            return PAGE_UP
                        if seq2 == ord('6'):
                            return PAGE_DOWN
                else:
                    if seq2 == ord('A'):
                        return ARROW_UP
                    if seq2 == ord('B'):
                        return ARROW_DOWN
                    if seq2 == ord('C'):
                        return ARROW_RIGHT
                    if seq2 == ord('D'):
                        return ARROW_LEFT
                    if seq2 == ord('H'):
                        return HOME_KEY
                    if seq2 == ord('F'):
                        return END_KEY
            elif seq1 == ord('O'):
                if seq2 == ord('H'):
                    return HOME_KEY
                if seq2 == ord('F'):
                    return END_KEY
            return ESC
        return b


def get_cursor_position(ifd, ofd):
    os.write(ofd, b"\x1b[6n")
    buf = b''
    while True:
        c = os.read(ifd, 1)
        if not c:
            break
        buf += c
        if c == b'R':
            break
    # Parse ESC [ rows ; cols R
    try:
        s = buf.decode('utf-8', errors='ignore')
        if s.startswith('\x1b[') and s.endswith('R'):
            parts = s[2:-1].split(';')
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return -1, -1


def get_window_size(ifd, ofd):
    try:
        # get window size fallback
        rows, cols = struct.unpack('hh', res[:4])
        if cols > 0:
            return rows, cols
    except Exception:
        pass
    # Fallback: cursor position query
    orig_row, orig_col = get_cursor_position(ifd, ofd)
    if orig_row == -1:
        return -1, -1
    os.write(ofd, b"\x1b[999C\x1b[999B")
    rows, cols = get_cursor_position(ifd, ofd)
    seq = "\x1b[%d;%dH" % (orig_row, orig_col)
    os.write(ofd, seq.encode())
    return rows, cols


def is_separator(c):
    if c == '\0':
        return True
    if c.isspace():
        return True
    return c in ",.()+-/*=~%[];"


def editor_row_has_open_comment(row):
    if row.hl is not None and row.rsize and row.hl[row.rsize - 1] == HL_MLCOMMENT:
        if row.rsize < 2:
            return True
        if not (row.render[row.rsize - 2] == '*' and row.render[row.rsize - 1] == '/'):
            return True
    return False


def editor_update_syntax(row):
    row.hl = [HL_NORMAL] * row.rsize
    if E.syntax is None:
        return
    keywords = E.syntax.keywords
    scs = E.syntax.scs
    mcs = E.syntax.mcs
    mce = E.syntax.mce

    i = 0
    p_idx = 0
    chars = row.render
    # Skip leading whitespace
    while p_idx < len(chars) and chars[p_idx].isspace():
        p_idx += 1
    i = p_idx
    prev_sep = True
    in_string = ''
    in_comment = False

    if row.idx > 0 and editor_row_has_open_comment(E.row[row.idx - 1]):
        in_comment = True

    while p_idx < len(chars):
        c = chars[p_idx]
        # Handle // comments
        if prev_sep and c == scs[0] and p_idx + 1 < len(chars) and chars[p_idx + 1] == scs[1]:
            for k in range(p_idx, row.rsize):
                row.hl[k] = HL_COMMENT
            return
        # Handle multi line comments
        if in_comment:
            row.hl[p_idx] = HL_MLCOMMENT
            if c == mce[0] and p_idx + 1 < len(chars) and chars[p_idx + 1] == mce[1]:
                row.hl[p_idx + 1] = HL_MLCOMMENT
                p_idx += 2
                in_comment = False
                prev_sep = True
                continue
            else:
                prev_sep = False
                p_idx += 1
                continue
        elif c == mcs[0] and p_idx + 1 < len(chars) and chars[p_idx + 1] == mcs[1]:
            row.hl[p_idx] = HL_MLCOMMENT
            row.hl[p_idx + 1] = HL_MLCOMMENT
            p_idx += 2
            in_comment = True
            prev_sep = False
            continue
        # Handle "" and ''
        if in_string:
            row.hl[p_idx] = HL_STRING
            if c == '\\' and p_idx + 1 < len(chars):
                row.hl[p_idx + 1] = HL_STRING
                p_idx += 2
                prev_sep = False
                continue
            if c == in_string:
                in_string = ''
            p_idx += 1
            continue
        else:
            if c == '"' or c == "'":
                in_string = c
                row.hl[p_idx] = HL_STRING
                p_idx += 1
                prev_sep = False
                continue
        # Non printable
        if not c.isprintable():
            row.hl[p_idx] = HL_NONPRINT
            p_idx += 1
            prev_sep = False
            continue
        # Numbers
        if (c.isdigit() and (prev_sep or (p_idx > 0 and row.hl[p_idx - 1] == HL_NUMBER))) or \
           (c == '.' and p_idx > 0 and row.hl[p_idx - 1] == HL_NUMBER):
            row.hl[p_idx] = HL_NUMBER
            p_idx += 1
            prev_sep = False
            continue
        # Keywords
        if prev_sep:
            matched = False
            for kw in keywords:
                klen = len(kw)
                kw2 = kw[-1] == '|'
                if kw2:
                    klen -= 1
                if chars[p_idx:p_idx + klen] == kw[:klen] and \
                   (p_idx + klen >= len(chars) or is_separator(chars[p_idx + klen])):
                    hl_type = HL_KEYWORD2 if kw2 else HL_KEYWORD1
                    for k in range(p_idx, p_idx + klen):
                        row.hl[k] = hl_type
                    p_idx += klen
                    matched = True
                    break
            if matched:
                prev_sep = False
                continue
        prev_sep = is_separator(c)
        p_idx += 1

    oc = editor_row_has_open_comment(row)
    if row.hl_oc != oc and row.idx + 1 < E.numrows:
        editor_update_syntax(E.row[row.idx + 1])
    row.hl_oc = oc


def editor_syntax_to_color(hl):
    if hl in (HL_COMMENT, HL_MLCOMMENT):
        return 36
    if hl == HL_KEYWORD1:
        return 33
    if hl == HL_KEYWORD2:
        return 32
    if hl == HL_STRING:
        return 35
    if hl == HL_NUMBER:
        return 31
    if hl == HL_MATCH:
        return 34
    return 37


def editor_select_syntax_highlight(filename):
    for s in HLDB:
        for pat in s.filematch:
            idx = filename.find(pat)
            if idx >= 0:
                if pat[0] != '.' or idx + len(pat) == len(filename):
                    E.syntax = s
                    return
    E.syntax = None


def editor_update_row(row):
    del row.render
    row.render = ""
    row.rsize = 0
    tabs = 0
    for j in range(row.size):
        if row.chars[j] == '\t':
            tabs += 1
    out = []
    for j in range(row.size):
        if row.chars[j] == '\t':
            out.append(' ')
            while (len(out) + 1) % 8 != 0:
                out.append(' ')
        else:
            out.append(row.chars[j])
    row.render = ''.join(out)
    row.rsize = len(row.render)
    editor_update_syntax(row)


def editor_insert_row(at, s):
    if at > E.numrows:
        return
    new_row = ERow(at, s)
    E.row.insert(at, new_row)
    for j in range(at + 1, E.numrows + 1):
        E.row[j].idx += 1
    editor_update_row(new_row)
    E.numrows += 1
    E.dirty += 1


def editor_free_row(row):
    del row.render
    del row.chars
    row.hl = None


def editor_del_row(at):
    if at >= E.numrows:
        return
    editor_free_row(E.row[at])
    del E.row[at]
    for j in range(at, E.numrows - 1):
        E.row[j].idx = j
    E.numrows -= 1
    E.dirty += 1


def editor_rows_to_string():
    total = 0
    for row in E.row:
        total += row.size + 1
    buf = []
    for row in E.row:
        buf.append(row.chars)
        buf.append('\n')
    return ''.join(buf), total


def editor_row_insert_char(row, at, c):
    if at > row.size:
        padlen = at - row.size
        row.chars = row.chars + ' ' * (padlen + 1)
        row.size = len(row.chars)
    else:
        row.chars = row.chars[:at] + c + row.chars[at:]
        row.size += 1
    editor_update_row(row)
    E.dirty += 1


def editor_row_append_string(row, s):
    row.chars = row.chars + s
    row.size += len(s)
    editor_update_row(row)
    E.dirty += 1


def editor_row_del_char(row, at):
    if row.size <= at:
        return
    row.chars = row.chars[:at] + row.chars[at + 1:]
    editor_update_row(row)
    row.size -= 1
    E.dirty += 1


def editor_insert_char(c):
    filerow = E.rowoff + E.cy
    filecol = E.coloff + E.cx
    if filerow >= E.numrows:
        while E.numrows <= filerow:
            editor_insert_row(E.numrows, "")
    row = E.row[filerow]
    editor_row_insert_char(row, filecol, c)
    if E.cx == E.screencols - 1:
        E.coloff += 1
    else:
        E.cx += 1
    E.dirty += 1


def editor_insert_newline():
    filerow = E.rowoff + E.cy
    filecol = E.coloff + E.cx
    if filerow >= E.numrows:
        if filerow == E.numrows:
            editor_insert_row(filerow, "")
        return
    row = E.row[filerow]
    if filecol >= row.size:
        filecol = row.size
    if filecol == 0:
        editor_insert_row(filerow, "")
    else:
        editor_insert_row(filerow + 1, row.chars[filecol:])
        row = E.row[filerow]
        row.chars = row.chars[:filecol]
        row.size = len(row.chars)
        editor_update_row(row)
    if E.cy == E.screenrows - 1:
        E.rowoff += 1
    else:
        E.cy += 1
    E.cx = 0
    E.coloff = 0


def editor_del_char():
    filerow = E.rowoff + E.cy
    filecol = E.coloff + E.cx
    row = E.row[filerow] if filerow < E.numrows else None
    if row is None or (filecol == 0 and filerow == 0):
        return
    if filecol == 0:
        prev_row = E.row[filerow - 1]
        filecol = prev_row.size
        editor_row_append_string(prev_row, row.chars)
        editor_del_row(filerow)
        if E.cy == 0:
            E.rowoff -= 1
        else:
            E.cy -= 1
        E.cx = filecol
        if E.cx >= E.screencols:
            shift = (E.screencols - E.cx) + 1
            E.cx -= shift
            E.coloff += shift
    else:
        editor_row_del_char(row, filecol - 1)
        if E.cx == 0 and E.coloff:
            E.coloff -= 1
        else:
            E.cx -= 1
    E.dirty += 1


def editor_open(filename):
    E.dirty = 0
    E.filename = filename
    try:
        with open(filename, 'r', encoding='utf-8', errors='replace') as fp:
            for line in fp:
                line = line.rstrip('\n').rstrip('\r')
                editor_insert_row(E.numrows, line)
    except FileNotFoundError:
        return 1
    except Exception:
        return 1
    E.dirty = 0
    return 0


def editor_save():
    buf, length = editor_rows_to_string()
    try:
        with open(E.filename, 'w', encoding='utf-8') as fp:
            fp.write(buf)
        E.dirty = 0
        editor_set_status_message("%d bytes written on disk" % length)
        return 0
    except Exception as e:
        editor_set_status_message("Can't save! I/O error: %s" % str(e))
        return 1


class ABuf:
    def __init__(self):
        self.b = b''
        self.len = 0

    def append(self, s, length=None):
        if isinstance(s, str):
            s = s.encode()
        if length is None:
            length = len(s)
        self.b = self.b + s[:length]
        self.len = len(self.b)


def editor_refresh_screen():
    ab = ABuf()
    ab.append(b"\x1b[?25l")
    ab.append(b"\x1b[H")
    for y in range(E.screenrows):
        filerow = E.rowoff + y
        if filerow >= E.numrows:
            if E.numrows == 0 and y == E.screenrows // 3:
                welcome = "Kilo editor -- verison %s\x1b[0K\r\n" % KILO_VERSION
                welcomelen = len(welcome)
                padding = (E.screencols - welcomelen) // 2
                if padding:
                    ab.append(b"~")
                    padding -= 1
                while padding > 0:
                    ab.append(b" ")
                    padding -= 1
                ab.append(welcome)
            else:
                ab.append(b"~\x1b[0K\r\n")
            continue
        r = E.row[filerow]
        ln = r.rsize - E.coloff
        current_color = -1
        if ln > 0:
            if ln > E.screencols:
                ln = E.screencols
            c = r.render[E.coloff:]
            hl = r.hl[E.coloff:]
            for j in range(ln):
                if hl[j] == HL_NONPRINT:
                    ab.append(b"\x1b[7m")
                    if ord(c[j]) <= 26:
                        sym = '@' + c[j]
                    else:
                        sym = '?'
                    ab.append(sym)
                    ab.append(b"\x1b[0m")
                elif hl[j] == HL_NORMAL:
                    if current_color != -1:
                        ab.append(b"\x1b[39m")
                        current_color = -1
                    ab.append(c[j])
                else:
                    color = editor_syntax_to_color(hl[j])
                    if color != current_color:
                        current_color = color
                        ab.append(b"\x1b[%dm" % color)
                    ab.append(c[j])
        ab.append(b"\x1b[39m")
        ab.append(b"\x1b[0K")
        ab.append(b"\r\n")

    # First status row
    ab.append(b"\x1b[0K")
    ab.append(b"\x1b[7m")
    fn = E.filename if E.filename else ""
    status = "%.20s - %d lines %s" % (fn, E.numrows, "(modified)" if E.dirty else "")
    rstatus = "%d/%d" % (E.rowoff + E.cy + 1, E.numrows)
    ln = len(status)
    if ln > E.screencols:
        ln = E.screencols
    ab.append(status[:ln])
    while ln < E.screencols:
        if E.screencols - ln == len(rstatus):
            ab.append(rstatus)
            break
        ab.append(b" ")
        ln += 1
    ab.append(b"\x1b[0m\r\n")

    # Second status row
    ab.append(b"\x1b[0K")
    if E.statusmsg and time.time() - E.statusmsg_time < 5:
        msg = E.statusmsg[:E.screencols]
        ab.append(msg)

    # Cursor position
    cx = 1
    filerow = E.rowoff + E.cy
    if filerow < E.numrows:
        row = E.row[filerow]
        for j in range(E.coloff, E.cx + E.coloff):
            if j < row.size and row.chars[j] == '\t':
                cx += 7 - (cx % 8)
            cx += 1
    ab.append(b"\x1b[%d;%dH" % (E.cy + 1, cx))
    ab.append(b"\x1b[?25h")
    sys.stdout.buffer.write(ab.b)
    sys.stdout.flush()


def editor_set_status_message(fmt, *args):
    E.statusmsg = fmt % args if args else fmt
    E.statusmsg_time = time.time()


def editor_find(fd):
    KILO_QUERY_LEN = 256
    query = ""
    qlen = 0
    last_match = -1
    find_next = 0
    saved_hl_line = -1
    saved_hl = None

    def restore_hl():
        nonlocal saved_hl, saved_hl_line
        if saved_hl is not None:
            E.row[saved_hl_line].hl = saved_hl
            saved_hl = None

    saved_cx = E.cx
    saved_cy = E.cy
    saved_coloff = E.coloff
    saved_rowoff = E.rowoff

    while True:
        editor_set_status_message("Search: %s (Use ESC/Arrows/Enter)", query)
        editor_refresh_screen()
        c = editor_read_key(fd)
        if c in (DEL_KEY, CTRL_H, BACKSPACE):
            if qlen != 0:
                qlen -= 1
                query = query[:qlen]
            last_match = -1
        elif c == ESC or c == ENTER:
            if c == ESC:
                E.cx = saved_cx
                E.cy = saved_cy
                E.coloff = saved_coloff
                E.rowoff = saved_rowoff
            restore_hl()
            editor_set_status_message("")
            return
        elif c == ARROW_RIGHT or c == ARROW_DOWN:
            find_next = 1
        elif c == ARROW_LEFT or c == ARROW_UP:
            find_next = -1
        elif 32 <= c < 127:
            if qlen < KILO_QUERY_LEN:
                query += chr(c)
                qlen = len(query)
                last_match = -1
        if last_match == -1:
            find_next = 1
        if find_next:
            match_row = -1
            match_offset = 0
            current = last_match
            for i in range(E.numrows):
                current += find_next
                if current == -1:
                    current = E.numrows - 1
                elif current == E.numrows:
                    current = 0
                idx = E.row[current].render.find(query)
                if idx >= 0:
                    match_row = current
                    match_offset = idx
                    break
            find_next = 0
            restore_hl()
            if match_row >= 0:
                row = E.row[match_row]
                last_match = match_row
                if row.hl:
                    saved_hl_line = match_row
                    saved_hl = list(row.hl)
                    row.hl[match_offset:match_offset + qlen] = [HL_MATCH] * qlen
                E.cy = 0
                E.cx = match_offset
                E.rowoff = match_row
                E.coloff = 0
                if E.cx > E.screencols:
                    diff = E.cx - E.screencols
                    E.cx -= diff
                    E.coloff += diff


def editor_move_cursor(key):
    filerow = E.rowoff + E.cy
    filecol = E.coloff + E.cx
    row = E.row[filerow] if filerow < E.numrows else None

    if key == ARROW_LEFT:
        if E.cx == 0:
            if E.coloff:
                E.coloff -= 1
            elif filerow > 0:
                E.cy -= 1
                E.cx = E.row[filerow - 1].size
                if E.cx > E.screencols - 1:
                    E.coloff = E.cx - E.screencols + 1
                    E.cx = E.screencols - 1
        else:
            E.cx -= 1
    elif key == ARROW_RIGHT:
        if row and filecol < row.size:
            if E.cx == E.screencols - 1:
                E.coloff += 1
            else:
                E.cx += 1
        elif row and filecol == row.size:
            E.cx = 0
            E.coloff = 0
            if E.cy == E.screenrows - 1:
                E.rowoff += 1
            else:
                E.cy += 1
    elif key == ARROW_UP:
        if E.cy == 0:
            if E.rowoff:
                E.rowoff -= 1
        else:
            E.cy -= 1
    elif key == ARROW_DOWN:
        if filerow < E.numrows:
            if E.cy == E.screenrows - 1:
                E.rowoff += 1
            else:
                E.cy += 1
    filerow = E.rowoff + E.cy
    filecol = E.coloff + E.cx
    row = E.row[filerow] if filerow < E.numrows else None
    rowlen = row.size if row else 0
    if filecol > rowlen:
        E.cx -= filecol - rowlen
        if E.cx < 0:
            E.coloff += E.cx
            E.cx = 0


KILO_QUIT_TIMES = 3
QUIT_TIMES = KILO_QUIT_TIMES


def editor_process_keypress(fd):
    global QUIT_TIMES
    c = editor_read_key(fd)
    if c == ENTER:
        editor_insert_newline()
    elif c == CTRL_C:
        pass
    elif c == CTRL_Q:
        if E.dirty and QUIT_TIMES:
            editor_set_status_message("WARNING!!! File has unsaved changes. Press Ctrl-Q %d more times to quit.", QUIT_TIMES)
            QUIT_TIMES -= 1
            return
        sys.exit(0)
    elif c == CTRL_S:
        editor_save()
    elif c == CTRL_F:
        editor_find(fd)
    elif c == BACKSPACE or c == CTRL_H or c == DEL_KEY:
        editor_del_char()
    elif c == PAGE_UP or c == PAGE_DOWN:
        if c == PAGE_UP and E.cy != 0:
            E.cy = 0
        elif c == PAGE_DOWN and E.cy != E.screenrows - 1:
            E.cy = E.screenrows - 1
        times = E.screenrows
        while times > 0:
            editor_move_cursor(ARROW_UP if c == PAGE_UP else ARROW_DOWN)
            times -= 1
    elif c in (ARROW_UP, ARROW_DOWN, ARROW_LEFT, ARROW_RIGHT):
        editor_move_cursor(c)
    elif c == CTRL_L:
        pass
    elif c == ESC:
        pass
    else:
        editor_insert_char(chr(c))
    QUIT_TIMES = KILO_QUIT_TIMES


def update_window_size():
    rows, cols = get_window_size(sys.stdin.fileno(), sys.stdout.fileno())
    if rows == -1:
        rows = 24
        cols = 80
    E.screenrows = rows - 2
    E.screencols = cols


def handle_sig_winch(signum, frame):
    update_window_size()
    if E.cy > E.screenrows:
        E.cy = E.screenrows - 1
    if E.cx > E.screencols:
        E.cx = E.screencols - 1
    editor_refresh_screen()


def init_editor():
    E.cx = 0
    E.cy = 0
    E.rowoff = 0
    E.coloff = 0
    E.numrows = 0
    E.row = []
    E.dirty = 0
    E.filename = None
    E.syntax = None
    update_window_size()
    signal.signal(signal.SIGWINCH, handle_sig_winch)


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("Usage: kilo <filename>\n")
        sys.exit(1)
    init_editor()
    editor_select_syntax_highlight(sys.argv[1])
    editor_open(sys.argv[1])
    enable_raw_mode(sys.stdin.fileno())
    editor_set_status_message("HELP: Ctrl-S = save | Ctrl-Q = quit | Ctrl-F = find")
    while True:
        editor_refresh_screen()
        editor_process_keypress(sys.stdin.fileno())


if __name__ == '__main__':
    main()

