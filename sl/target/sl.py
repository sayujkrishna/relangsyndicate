#!/usr/bin/env python3
# ========================================
#    sl.py: SL version 5.02  (Python port)
#        Ported from sl.c
#        Original Copyright 1993,1998,2014
#                  Toyoda Masashi
#                  (mtoyoda@acm.org)
#        Last Modified: 2014/06/03
# ========================================
#
# Direct, function-for-function translation of the provided sl.c.
# The ASCII-art string constants below come from the original sl.h
# (they were not included in the pasted sl.c, so they were pulled
# from the upstream project so the output matches exactly).

import time

# ---- curses.h stand-ins (only OK/ERR were actually used) ----
OK = 0
ERR = -1

# ---------------------------------------------------------------
# sl.h constants
# ---------------------------------------------------------------
D51HEIGHT = 10
D51FUNNEL = 7
D51LENGTH = 83
D51PATTERNS = 6

D51STR1 = "      ====        ________                ___________ "
D51STR2 = "  _D _|  |_______/        \\__I_I_____===__|_________| "
D51STR3 = "   |(_)---  |   H\\________/ |   |        =|___ ___|   "
D51STR4 = "   /     |  |   H  |  |     |   |         ||_| |_||   "
D51STR5 = "  |      |  |   H  |__--------------------| [___] |   "
D51STR6 = "  | ________|___H__/__|_____/[][]~\\_______|       |   "
D51STR7 = "  |/ |   |-----------I_____I [][] []  D   |=======|__ "

D51WHL11 = "__/ =| o |=-~~\\  /~~\\  /~~\\  /~~\\ ____Y___________|__ "
D51WHL12 = " |/-=|___|=    ||    ||    ||    |_____/~\\___/        "
D51WHL13 = "  \\_/      \\O=====O=====O=====O_/      \\_/            "

D51WHL21 = "__/ =| o |=-~~\\  /~~\\  /~~\\  /~~\\ ____Y___________|__ "
D51WHL22 = " |/-=|___|=O=====O=====O=====O   |_____/~\\___/        "
D51WHL23 = "  \\_/      \\__/  \\__/  \\__/  \\__/      \\_/            "

D51WHL31 = "__/ =| o |=-O=====O=====O=====O \\ ____Y___________|__ "
D51WHL32 = " |/-=|___|=    ||    ||    ||    |_____/~\\___/        "
D51WHL33 = "  \\_/      \\__/  \\__/  \\__/  \\__/      \\_/            "

D51WHL41 = "__/ =| o |=-~O=====O=====O=====O\\ ____Y___________|__ "
D51WHL42 = " |/-=|___|=    ||    ||    ||    |_____/~\\___/        "
D51WHL43 = "  \\_/      \\__/  \\__/  \\__/  \\__/      \\_/            "

D51WHL51 = "__/ =| o |=-~~\\  /~~\\  /~~\\  /~~\\ ____Y___________|__ "
D51WHL52 = " |/-=|___|=   O=====O=====O=====O|_____/~\\___/        "
D51WHL53 = "  \\_/      \\__/  \\__/  \\__/  \\__/      \\_/            "

D51WHL61 = "__/ =| o |=-~~\\  /~~\\  /~~\\  /~~\\ ____Y___________|__ "
D51WHL62 = " |/-=|___|=    ||    ||    ||    |_____/~\\___/        "
D51WHL63 = "  \\_/      \\_O=====O=====O=====O/      \\_/            "

D51DEL = "                                                      "

COAL01 = "                              "
COAL02 = "                              "
COAL03 = "    _________________         "
COAL04 = "   _|                \\_____A  "
COAL05 = " =|                        |  "
COAL06 = " -|                        |  "
COAL07 = "__|________________________|_ "
COAL08 = "|__________________________|_ "
COAL09 = "   |_D__D__D_|  |_D__D__D_|   "
COAL10 = "    \\_/   \\_/    \\_/   \\_/    "

COALDEL = "                              "

LOGOHEIGHT = 6
LOGOFUNNEL = 4
LOGOLENGTH = 84
LOGOPATTERNS = 6

LOGO1 = "     ++      +------ "
LOGO2 = "     ||      |+-+ |  "
LOGO3 = "   /---------|| | |  "
LOGO4 = "  + ========  +-+ |  "

LWHL11 = " _|--O========O~\\-+  "
LWHL12 = "//// \\_/      \\_/    "

LWHL21 = " _|--/O========O\\-+  "
LWHL22 = "//// \\_/      \\_/    "

LWHL31 = " _|--/~O========O-+  "
LWHL32 = "//// \\_/      \\_/    "

LWHL41 = " _|--/~\\------/~\\-+  "
LWHL42 = "//// \\_O========O    "

LWHL51 = " _|--/~\\------/~\\-+  "
LWHL52 = "//// \\O========O/    "

LWHL61 = " _|--/~\\------/~\\-+  "
LWHL62 = "//// O========O_/    "

LCOAL1 = "____                 "
LCOAL2 = "|   \\@@@@@@@@@@@     "
LCOAL3 = "|    \\@@@@@@@@@@@@@_ "
LCOAL4 = "|                  | "
LCOAL5 = "|__________________| "
LCOAL6 = "   (O)       (O)     "

LCAR1 = "____________________ "
LCAR2 = "|  ___ ___ ___ ___ | "
LCAR3 = "|  |_| |_| |_| |_| | "
LCAR4 = "|__________________| "
LCAR5 = "|__________________| "
LCAR6 = "   (O)        (O)    "

DELLN = "                     "

C51HEIGHT = 11
C51FUNNEL = 7
C51LENGTH = 87
C51PATTERNS = 6

C51DEL = "                                                       "

C51STR1 = "        ___                                            "
C51STR2 = "       _|_|_  _     __       __             ___________"
C51STR3 = "    D__/   \\_(_)___|  |__H__|  |_____I_Ii_()|_________|"
C51STR4 = "     | `---'   |:: `--'  H  `--'         |  |___ ___|  "
C51STR5 = "    +|~~~~~~~~++::~~~~~~~H~~+=====+~~~~~~|~~||_| |_||  "
C51STR6 = "    ||        | ::       H  +=====+      |  |::  ...|  "
C51STR7 = "|    | _______|_::-----------------[][]-----|       |  "

C51WH61 = "| /~~ ||   |-----/~~~~\\  /[I_____I][][] --|||_______|__"
C51WH62 = "------'|oOo|==[]=-     ||      ||      |  ||=======_|__"
C51WH63 = "/~\\____|___|/~\\_|   O=======O=======O  |__|+-/~\\_|     "
C51WH64 = "\\_/         \\_/  \\____/  \\____/  \\____/      \\_/       "

C51WH51 = "| /~~ ||   |-----/~~~~\\  /[I_____I][][] --|||_______|__"
C51WH52 = "------'|oOo|===[]=-    ||      ||      |  ||=======_|__"
C51WH53 = "/~\\____|___|/~\\_|    O=======O=======O |__|+-/~\\_|     "
C51WH54 = "\\_/         \\_/  \\____/  \\____/  \\____/      \\_/       "

C51WH41 = "| /~~ ||   |-----/~~~~\\  /[I_____I][][] --|||_______|__"
C51WH42 = "------'|oOo|===[]=- O=======O=======O  |  ||=======_|__"
C51WH43 = "/~\\____|___|/~\\_|      ||      ||      |__|+-/~\\_|     "
C51WH44 = "\\_/         \\_/  \\____/  \\____/  \\____/      \\_/       "

C51WH31 = "| /~~ ||   |-----/~~~~\\  /[I_____I][][] --|||_______|__"
C51WH32 = "------'|oOo|==[]=- O=======O=======O   |  ||=======_|__"
C51WH33 = "/~\\____|___|/~\\_|      ||      ||      |__|+-/~\\_|     "
C51WH34 = "\\_/         \\_/  \\____/  \\____/  \\____/      \\_/       "

C51WH21 = "| /~~ ||   |-----/~~~~\\  /[I_____I][][] --|||_______|__"
C51WH22 = "------'|oOo|=[]=- O=======O=======O    |  ||=======_|__"
C51WH23 = "/~\\____|___|/~\\_|      ||      ||      |__|+-/~\\_|     "
C51WH24 = "\\_/         \\_/  \\____/  \\____/  \\____/      \\_/       "

C51WH11 = "| /~~ ||   |-----/~~~~\\  /[I_____I][][] --|||_______|__"
C51WH12 = "------'|oOo|=[]=-      ||      ||      |  ||=======_|__"
C51WH13 = "/~\\____|___|/~\\_|  O=======O=======O   |__|+-/~\\_|     "
C51WH14 = "\\_/         \\_/  \\____/  \\____/  \\____/      \\_/       "


# ---------------------------------------------------------------
# globals (mirrors the file-scope C globals)
# ---------------------------------------------------------------
ACCIDENT = 0
LOGO = 0
FLY = 0
C51 = 0
DANCE = 0
RAND = 0

COLS = 0
LINES = 0
N = 0

output_map = None  # bytearray, mirrors char *output_map


def count():
    global LOGO, C51
    offset = 21
    if LOGO >= 1:
        mn = -LOGOLENGTH - 1 - offset * (LOGO - 1)
    elif C51 == 1:
        mn = -D51LENGTH - 1  # NOTE: identical to original sl.c (this branch is
                              # actually dead code there too -- C51==1 always
                              # falls into the "not LOGO" D51/C51 case below in
                              # add_sl, but count() itself only checks C51==1
                              # exactly as the C source does, bug-for-bug)
    else:
        mn = -D51LENGTH - 1
    return mn


def addch_modify(y, x, c):
    global output_map, COLS, LINES
    if y < 0 or x < 0 or x >= COLS or y >= LINES:
        return ERR
    output_map[y * (COLS + 1) + x] = ord(c)
    return OK


def my_mvaddstr(y, x, s):
    i = 0
    # skip characters while x < 0, matching the C pointer-walk
    while x < 0:
        if i >= len(s):
            return ERR
        i += 1
        x += 1
    while i < len(s):
        if addch_modify(y, x, s[i]) == ERR:
            return ERR
        i += 1
        x += 1
    return OK


def option(s):
    global ACCIDENT, LOGO, FLY, C51, DANCE, RAND
    i = 0
    while i < len(s) and s[i] != '-':
        ch = s[i]
        i += 1
        if ch == 'l':
            LOGO += 1
        elif ch == 'a':
            ACCIDENT = 1
        elif ch == 'F':
            FLY = 1
        elif ch == 'c':
            C51 = 1
        elif ch == 'd':
            DANCE = 1
        elif ch == 'r':
            RAND = 1
        else:
            pass


def window_init(c, l, arg):
    global COLS, LINES, N, ACCIDENT, LOGO, FLY, C51, DANCE, RAND, output_map
    COLS = c
    LINES = l

    ACCIDENT = LOGO = FLY = C51 = DANCE = RAND = 0

    i = 0
    while i < len(arg):
        if arg[i] == '-':
            option(arg[i + 1:])
        i += 1

    if RAND == 1:
        import random
        random.seed(time.time())
        ACCIDENT |= random.randint(0, 1)
        LOGO |= random.randint(0, 1)
        FLY |= random.randint(0, 1)
        C51 |= random.randint(0, 1)
        DANCE |= random.randint(0, 1)

    N = -count() + COLS - 1

    output_map = bytearray(b' ' * (LINES * (COLS + 1)))
    for x in range(LINES):
        output_map[x * (COLS + 1) + COLS] = ord('\n')
    output_map[LINES * (COLS + 1) - 1] = 0


def window_destroy():
    global output_map
    output_map = None


def my_output():
    for x in range(N):
        map_modify(x)
        # printf("%s\n", output_map) -- the buffer is NUL-terminated at its
        # very last byte, so print everything up to (not including) that byte
        print(output_map[:-1].decode('ascii', errors='replace'))
        time.sleep(0.01)  # usleep(10000)


def map_modify(mod):
    x = -mod + COLS - 1
    if LOGO >= 1:
        add_sl(x)
    elif C51 == 1:
        add_C51(x)
    else:
        add_D51(x)


def add_sl(x):
    sl = [
        [LOGO1, LOGO2, LOGO3, LOGO4, LWHL11, LWHL12, DELLN],
        [LOGO1, LOGO2, LOGO3, LOGO4, LWHL21, LWHL22, DELLN],
        [LOGO1, LOGO2, LOGO3, LOGO4, LWHL31, LWHL32, DELLN],
        [LOGO1, LOGO2, LOGO3, LOGO4, LWHL41, LWHL42, DELLN],
        [LOGO1, LOGO2, LOGO3, LOGO4, LWHL51, LWHL52, DELLN],
        [LOGO1, LOGO2, LOGO3, LOGO4, LWHL61, LWHL62, DELLN],
    ]
    coal = [LCOAL1, LCOAL2, LCOAL3, LCOAL4, LCOAL5, LCOAL6, DELLN]
    car = [LCAR1, LCAR2, LCAR3, LCAR4, LCAR5, LCAR6, DELLN]

    offset = 21
    py1 = py2 = py3 = 0
    yoffset = 0

    y = LINES // 2 - 3

    if FLY == 1:
        y = (x // 6) + LINES - (COLS // 6) - LOGOHEIGHT
        py1, py2, py3 = 2, 4, 6

    for i in range(LOGOHEIGHT + 1):
        my_mvaddstr(y + i, x,
                    sl[(LOGOLENGTH + offset * (LOGO - 1) + x) // 3 % LOGOPATTERNS][i])
        my_mvaddstr(y + i + py1, x + 21, coal[i])
        for j in range(LOGO + 1):
            yoffset = 2 * j * FLY
            my_mvaddstr(y + i + py3 + yoffset, x + 42 + offset * j, car[i])

    if ACCIDENT == 1:
        add_man(y + 1, x + 14)
        for j in range(LOGO + 1):
            yoffset = FLY * (2 + 2 * j)
            add_man(y + 1 + py2 + yoffset, x + 45 + offset * j)
            add_man(y + 1 + py2 + yoffset, x + 53 + offset * j)

    if DANCE == 1 and ACCIDENT == 0 and FLY == 0:
        add_mdancer(y - 2, x + 21)
        for j in range(LOGO + 1):
            add_mdancer(y + py2 - 2, x + 45 + offset * j)
            add_mdancer(y + py2 - 2, x + 50 + offset * j)
            add_mdancer(y + py2 - 2, x + 55 + offset * j)

    add_smoke(y - 1, x + LOGOFUNNEL)
    return OK


def add_D51(x):
    d51 = [
        [D51STR1, D51STR2, D51STR3, D51STR4, D51STR5, D51STR6, D51STR7,
         D51WHL11, D51WHL12, D51WHL13, D51DEL],
        [D51STR1, D51STR2, D51STR3, D51STR4, D51STR5, D51STR6, D51STR7,
         D51WHL21, D51WHL22, D51WHL23, D51DEL],
        [D51STR1, D51STR2, D51STR3, D51STR4, D51STR5, D51STR6, D51STR7,
         D51WHL31, D51WHL32, D51WHL33, D51DEL],
        [D51STR1, D51STR2, D51STR3, D51STR4, D51STR5, D51STR6, D51STR7,
         D51WHL41, D51WHL42, D51WHL43, D51DEL],
        [D51STR1, D51STR2, D51STR3, D51STR4, D51STR5, D51STR6, D51STR7,
         D51WHL51, D51WHL52, D51WHL53, D51DEL],
        [D51STR1, D51STR2, D51STR3, D51STR4, D51STR5, D51STR6, D51STR7,
         D51WHL61, D51WHL62, D51WHL63, D51DEL],
    ]
    coal = [COAL01, COAL02, COAL03, COAL04, COAL05,
            COAL06, COAL07, COAL08, COAL09, COAL10, COALDEL]

    dy = 0
    y = LINES // 2 - 5

    if FLY == 1:
        y = (x // 7) + LINES - (COLS // 7) - D51HEIGHT
        dy = 1

    for i in range(D51HEIGHT + 1):
        my_mvaddstr(y + i, x, d51[(D51LENGTH + x) % D51PATTERNS][i])
        my_mvaddstr(y + i + dy, x + 53, coal[i])

    if ACCIDENT == 1:
        add_man(y + 2, x + 43)
        add_man(y + 2, x + 47)

    if DANCE == 1 and ACCIDENT == 0 and FLY == 0:
        add_mdancer(y - 2, x + 43)
        add_fdancer(y - 2, x + 48)

    add_smoke(y - 1, x + D51FUNNEL)
    return OK


def add_C51(x):
    c51 = [
        [C51STR1, C51STR2, C51STR3, C51STR4, C51STR5, C51STR6, C51STR7,
         C51WH11, C51WH12, C51WH13, C51WH14, C51DEL],
        [C51STR1, C51STR2, C51STR3, C51STR4, C51STR5, C51STR6, C51STR7,
         C51WH21, C51WH22, C51WH23, C51WH24, C51DEL],
        [C51STR1, C51STR2, C51STR3, C51STR4, C51STR5, C51STR6, C51STR7,
         C51WH31, C51WH32, C51WH33, C51WH34, C51DEL],
        [C51STR1, C51STR2, C51STR3, C51STR4, C51STR5, C51STR6, C51STR7,
         C51WH41, C51WH42, C51WH43, C51WH44, C51DEL],
        [C51STR1, C51STR2, C51STR3, C51STR4, C51STR5, C51STR6, C51STR7,
         C51WH51, C51WH52, C51WH53, C51WH54, C51DEL],
        [C51STR1, C51STR2, C51STR3, C51STR4, C51STR5, C51STR6, C51STR7,
         C51WH61, C51WH62, C51WH63, C51WH64, C51DEL],
    ]
    coal = [COALDEL, COAL01, COAL02, COAL03, COAL04, COAL05,
            COAL06, COAL07, COAL08, COAL09, COAL10, COALDEL]

    dy = 0
    y = LINES // 2 - 5

    if FLY == 1:
        y = (x // 7) + LINES - (COLS // 7) - C51HEIGHT
        dy = 1

    for i in range(C51HEIGHT + 1):
        my_mvaddstr(y + i, x, c51[(C51LENGTH + x) % C51PATTERNS][i])
        my_mvaddstr(y + i + dy, x + 55, coal[i])

    if ACCIDENT == 1:
        add_man(y + 3, x + 45)
        add_man(y + 3, x + 49)

    if DANCE == 1 and ACCIDENT == 0 and FLY == 0:
        add_mdancer(y - 1, x + 45)
        add_fdancer(y - 1, x + 50)

    add_smoke(y - 1, x + C51FUNNEL)
    return OK


def add_man(y, x):
    man = [["", "(O)"], ["Help!", "\\O/"]]
    for i in range(2):
        my_mvaddstr(y + i, x, man[(LOGOLENGTH + x) // 12 % 2][i])


def add_fdancer(y, x):
    fdancer = [["\\\\0", "/\\", "|\\"], ["0//", "/\\", "/|"]]
    efdancer = [["   ", "  ", "  "], ["   ", "  ", "  "]]
    for i in range(3):
        my_mvaddstr(y + i, x + 1, efdancer[(LOGOLENGTH + x) // 12 % 2][i])
        my_mvaddstr(y + i, x, fdancer[(LOGOLENGTH + x) // 12 % 2][i])


def add_mdancer(y, x):
    mdancer = [["_O_", " #", "/\\"], ["(0)", " #", "/\\"], ["(O_", " #", "/\\"]]
    emdancer = [["   ", "  ", "  "], ["   ", "  ", "  "], ["   ", "  ", "  "]]
    for i in range(3):
        my_mvaddstr(y + i, x + 1, emdancer[(LOGOLENGTH + x) // 12 % 3][i])
        my_mvaddstr(y + i, x, mdancer[(LOGOLENGTH + x) // 12 % 3][i])


def add_smoke(y, x):
    SMOKEPTNS = 16

    # "static" state, attached to the function object -- mirrors the
    # C `static` locals inside add_smoke()
    if not hasattr(add_smoke, "S"):
        add_smoke.S = [{"y": 0, "x": 0, "ptrn": 0, "kind": 0} for _ in range(1000)]
        add_smoke.sum = 0

    Smoke = [
        ["(   )", "(    )", "(    )", "(   )", "(  )",
         "(  )", "( )", "( )", "()", "()",
         "O", "O", "O", "O", "O",
         " "],
        ["(@@@)", "(@@@@)", "(@@@@)", "(@@@)", "(@@)",
         "(@@)", "(@)", "(@)", "@@", "@@",
         "@", "@", "@", "@", "@",
         " "],
    ]
    Eraser = ["     ", "      ", "      ", "     ", "    ",
              "    ", "   ", "   ", "  ", "  ",
              " ", " ", " ", " ", " ",
              " "]
    dy = [2, 1, 1, 1, 0, 0, 0, 0, 0, 0,
          0, 0, 0, 0, 0, 0]
    dx = [-2, -1, 0, 1, 1, 1, 1, 1, 2, 2,
          2, 2, 2, 3, 3, 3]

    if x % 4 == 0:
        S = add_smoke.S
        for i in range(add_smoke.sum):
            my_mvaddstr(S[i]["y"], S[i]["x"], Eraser[S[i]["ptrn"]])
            S[i]["y"] -= dy[S[i]["ptrn"]]
            S[i]["x"] += dx[S[i]["ptrn"]]
            S[i]["ptrn"] += 1 if S[i]["ptrn"] < SMOKEPTNS - 1 else 0
            my_mvaddstr(S[i]["y"], S[i]["x"], Smoke[S[i]["kind"]][S[i]["ptrn"]])

        my_mvaddstr(y, x, Smoke[add_smoke.sum % 2][0])
        S[add_smoke.sum]["y"] = y
        S[add_smoke.sum]["x"] = x
        S[add_smoke.sum]["ptrn"] = 0
        S[add_smoke.sum]["kind"] = add_smoke.sum % 2
        add_smoke.sum += 1


# ---------------------------------------------------------------
# int main(int argc, char *argv[])
# {
#     windowInit(83,47,"-r");
#     my_output();
#     windowDestroy();
#     printf("OK\n");
#     return 0;
# }
#
# (commented out in the original sl.c -- kept as a comment here too,
# for parity. An equivalent, runnable version is provided below.)
# ---------------------------------------------------------------
if __name__ == "__main__":
    window_init(83, 47, "-r")
    my_output()
    window_destroy()
    print("OK")
