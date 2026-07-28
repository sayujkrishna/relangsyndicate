#!/usr/bin/env python3
"""
Asciiquarium in Python
Converted from the Perl ASCIIquarium by Kirk Baucom.
"""

import os
import sys
import time
import random
import argparse
import signal

# Windows ANSI support setup
if sys.platform == "win32":
    import msvcrt
    import ctypes
    kernel32 = ctypes.windll.kernel32
    # Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004)
    mode = ctypes.c_ulong()
    hStdOut = kernel32.GetStdHandle(-11) # STD_OUTPUT_HANDLE
    if kernel32.GetConsoleMode(hStdOut, ctypes.byref(mode)):
        kernel32.SetConsoleMode(hStdOut, mode.value | 0x0004)
else:
    import select
    import termios
    import tty

VERSION = "1.1"

# Depth levels matching Perl %depth dictionary
DEPTH = {
    'guiText': 0,
    'gui': 1,
    'shark': 2,
    'fish_start': 3,
    'fish_end': 20,
    'seaweed': 21,
    'castle': 22,
    'water_line3': 2,
    'water_gap3': 3,
    'water_line2': 4,
    'water_gap2': 5,
    'water_line1': 6,
    'water_gap1': 7,
    'water_line0': 8,
    'water_gap0': 9,
}

# ANSI Color codes mapping
ANSI_COLORS = {
    'k': '\033[30m',   # Black
    'K': '\033[90m',   # Dark Gray / Bright Black
    'r': '\033[31m',   # Red
    'R': '\033[91m',   # Bright Red
    'g': '\033[32m',   # Green
    'G': '\033[92m',   # Bright Green
    'y': '\033[33m',   # Yellow
    'Y': '\033[93m',   # Bright Yellow
    'b': '\033[34m',   # Blue
    'B': '\033[94m',   # Bright Blue
    'm': '\033[35m',   # Magenta
    'M': '\033[95m',   # Bright Magenta
    'c': '\033[36m',   # Cyan
    'C': '\033[96m',   # Bright Cyan
    'w': '\033[37m',   # White
    'W': '\033[97m',   # Bright White
    'RESET': '\033[0m',
}

# Map alias strings to color codes
COLOR_ALIASES = {
    'BLACK': 'K',
    'RED': 'R',
    'GREEN': 'G',
    'YELLOW': 'Y',
    'BLUE': 'B',
    'MAGENTA': 'M',
    'CYAN': 'C',
    'WHITE': 'W',
}


def get_color_code(char_code, default_color='W'):
    """Resolve color code string to ANSI sequence."""
    if not char_code or char_code == ' ':
        char_code = COLOR_ALIASES.get(default_color, default_color)
    return ANSI_COLORS.get(char_code, ANSI_COLORS.get('W'))


def rand_color(color_mask):
    """Replace numbers 1-9 in color_mask with random colors."""
    colors = ['c', 'C', 'r', 'R', 'y', 'Y', 'b', 'B', 'g', 'G', 'm', 'M']
    res = list(color_mask)
    for i in range(len(res)):
        if res[i].isdigit() and res[i] != '0':
            res[i] = random.choice(colors)
    return "".join(res)


class Entity:
    """Represents an animated or static ASCII entity on screen."""
    def __init__(self, name=None, type_name="", shape=None, color=None, position=None,
                 callback=None, callback_args=None, die_offscreen=False,
                 die_frame=0, die_time=0, death_cb=None, physical=False,
                 coll_handler=None, default_color='W', auto_trans=True,
                 transparent=' ', depth=10):
        self.name = name or f"entity_{random.random()}"
        self.type = type_name
        self.position = list(position) if position else [0, 0, 0]  # [x, y, z]
        self.depth = depth if depth is not None else self.position[2]
        self.callback = callback
        self.callback_args = callback_args or [0, 0, 0]
        self.die_offscreen = die_offscreen
        self.die_frame = die_frame
        self.die_time = die_time
        self.death_cb = death_cb
        self.physical = physical
        self.coll_handler = coll_handler
        self.default_color = default_color
        self.auto_trans = auto_trans
        self.transparent = transparent

        self.frame_index = 0
        self.tick_counter = 0
        self.dead = False
        self.collisions_list = []

        # Parse shape and color into list of frames (each frame is a list of lines)
        if isinstance(shape, str):
            self.shapes = [shape.strip('\n').split('\n')]
        elif isinstance(shape, list):
            self.shapes = [s.strip('\n').split('\n') if isinstance(s, str) else s for s in shape]
        else:
            self.shapes = [[""]]

        if isinstance(color, str):
            self.colors = [color.strip('\n').split('\n')]
        elif isinstance(color, list):
            self.colors = [c.strip('\n').split('\n') if isinstance(c, str) else c for c in color]
        else:
            self.colors = None

    @property
    def x(self):
        return float(self.position[0])

    @x.setter
    def x(self, val):
        self.position[0] = float(val)

    @property
    def y(self):
        return float(self.position[1])

    @y.setter
    def y(self, val):
        self.position[1] = float(val)

    @property
    def z(self):
        return self.position[2]

    @property
    def height(self):
        lines = self.shapes[self.frame_index % len(self.shapes)]
        return len(lines)

    @property
    def width(self):
        lines = self.shapes[self.frame_index % len(self.shapes)]
        return max((len(line) for line in lines), default=0)

    def kill(self):
        self.dead = True

    def collisions(self):
        return self.collisions_list

    def move_entity(self, animation):
        """Move entity based on callback_args speed [dx, dy, dz, frame_speed]."""
        dx = self.callback_args[0] if len(self.callback_args) > 0 else 0
        dy = self.callback_args[1] if len(self.callback_args) > 1 else 0

        self.x += dx
        self.y += dy

        # Check offscreen death
        if self.die_offscreen:
            if (dx > 0 and self.x > animation.width) or \
               (dx < 0 and self.x + self.width < 0) or \
               (dy > 0 and self.y > animation.height) or \
               (dy < 0 and self.y + self.height < 0):
                self.kill()


class AnimationEngine:
    """Core animation manager handling entities, tick loop, rendering and collision."""
    def __init__(self):
        self.entities = []
        self.paused = False
        self.update_term_size()

    def update_term_size(self):
        try:
            size = os.get_terminal_size()
            self.width = size.columns
            self.height = size.lines
        except Exception:
            self.width = 80
            self.height = 24

    def add_entity(self, entity):
        self.entities.append(entity)

    def new_entity(self, **kwargs):
        ent = Entity(**kwargs)
        self.add_entity(ent)
        return ent

    def del_entity(self, entity):
        if entity in self.entities:
            self.entities.remove(entity)

    def remove_all_entities(self):
        self.entities.clear()

    def get_entities_of_type(self, type_name):
        return [e for e in self.entities if e.type == type_name and not e.dead]

    def animate(self):
        """Advance animation state by 1 tick."""
        if self.paused:
            return

        now = time.time()
        for ent in list(self.entities):
            if ent.dead:
                continue

            # Check time-based death
            if ent.die_time > 0 and now >= ent.die_time:
                ent.kill()
                continue

            # Update entity tick and frame index
            ent.tick_counter += 1
            frame_speed = ent.callback_args[3] if len(ent.callback_args) > 3 else 1
            if frame_speed > 0 and ent.tick_counter % max(1, int(1 / frame_speed)) == 0:
                ent.frame_index += 1

            # Check frame-based death
            if ent.die_frame > 0 and ent.tick_counter >= ent.die_frame:
                ent.kill()
                continue

            # Execute callback
            if ent.callback:
                ent.callback(ent, self)
            else:
                ent.move_entity(self)

        # Handle physical collisions
        physical_ents = [e for e in self.entities if e.physical and not e.dead]
        for i in range(len(physical_ents)):
            for j in range(i + 1, len(physical_ents)):
                e1, e2 = physical_ents[i], physical_ents[j]
                if self.check_collision(e1, e2):
                    e1.collisions_list.append(e2)
                    e2.collisions_list.append(e1)

        # Invoke collision handlers
        for ent in physical_ents:
            if ent.collisions_list and ent.coll_handler and not ent.dead:
                ent.coll_handler(ent, self)
            ent.collisions_list.clear()

        # Process deaths and death callbacks
        for ent in list(self.entities):
            if ent.dead:
                self.del_entity(ent)
                if ent.death_cb:
                    ent.death_cb(ent, self)

    def check_collision(self, e1, e2):
        """Bounding box collision check."""
        x1, y1 = int(e1.x), int(e1.y)
        w1, h1 = e1.width, e1.height

        x2, y2 = int(e2.x), int(e2.y)
        w2, h2 = e2.width, e2.height

        return not (x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1)

    def redraw_screen(self):
        """Render buffer to terminal screen."""
        self.update_term_size()

        # Create screen buffer: matrix of (char, color_code)
        buf = [[(' ', ANSI_COLORS['W']) for _ in range(self.width)] for _ in range(self.height)]

        # Sort entities by Z depth descending (higher depth value = background, drawn first)
        sorted_entities = sorted([e for e in self.entities if not e.dead],
                                 key=lambda e: (e.depth if e.depth is not None else e.z),
                                 reverse=True)

        for ent in sorted_entities:
            cur_shape = ent.shapes[ent.frame_index % len(ent.shapes)]
            cur_color = ent.colors[ent.frame_index % len(ent.colors)] if ent.colors else None

            start_y = int(ent.y)
            start_x = int(ent.x)

            for r_idx, line in enumerate(cur_shape):
                py = start_y + r_idx
                if py < 0 or py >= self.height:
                    continue

                color_line = cur_color[r_idx] if (cur_color and r_idx < len(cur_color)) else ""

                for c_idx, char in enumerate(line):
                    px = start_x + c_idx
                    if px < 0 or px >= self.width:
                        continue

                    # Transparency handling
                    if ent.auto_trans and char == ent.transparent:
                        continue

                    char_color = color_line[c_idx] if c_idx < len(color_line) else ' '
                    ansi_code = get_color_code(char_color, ent.default_color)

                    buf[py][px] = (char, ansi_code)

        # Build output string with minimal ANSI state changes
        out = []
        out.append("\033[H")  # Move cursor to top-left (1,1)
        current_ansi = None

        for r in range(self.height):
            for c in range(self.width):
                ch, ansi = buf[r][c]
                if ansi != current_ansi:
                    out.append(ansi)
                    current_ansi = ansi
                out.append(ch)

        out.append(ANSI_COLORS['RESET'])
        sys.stdout.write("".join(out))
        sys.stdout.flush()


# --- Entity Builders ---

def add_environment(anim):
    water_line_segment = [
        r"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
        r"^^^^ ^^^  ^^^   ^^^    ^^^^      ",
        r"^^^^      ^^^^     ^^^    ^^     ",
        r"^^      ^^^^      ^^^    ^^^^^^  "
    ]

    segment_size = len(water_line_segment[0])
    segment_repeat = int(anim.width / segment_size) + 2

    for i in range(len(water_line_segment)):
        tiled_seg = water_line_segment[i] * segment_repeat
        anim.new_entity(
            name=f"water_seg_{i}",
            type_name="waterline",
            shape=tiled_seg,
            position=[0, i + 5, DEPTH[f'water_line{i}']],
            default_color='CYAN',
            depth=22,
            physical=True,
        )


def add_castle(anim):
    castle_image = r"""
               T~~
               |
              /^\
             /   \
 _   _   _  /     \  _   _   _
[ ]_[ ]_[ ]/ _   _ \[ ]_[ ]_[ ]
|_=__-_ =_|_[ ]_[ ]_|_=-___-__|
 | _- =  | =_ = _    |= _=   |
 |= -[]  |- = _ =    |_-=_[] |
 | =_    |= - ___    | =_ =  |
 |=  []- |-  /| |\   |=_ =[] |
 |- =_   | =| | | |  |- = -  |
 |_______|__|_|_|_|__|_______|
"""

    castle_mask = r"""
                RR

              yyy
             y   y
            y     y
           y       y



              yyy
             yy yy
            y y y y
            yyyyyyy
"""
    anim.new_entity(
        name="castle",
        shape=castle_image,
        color=castle_mask,
        position=[anim.width - 32, anim.height - 13, DEPTH['castle']],
        default_color='BLACK',
    )


def add_all_seaweed(anim):
    seaweed_count = int(anim.width / 15)
    for _ in range(seaweed_count):
        add_seaweed(None, anim)


def add_seaweed(old_seaweed, anim):
    height = random.randint(3, 6)
    f1, f2 = "", ""
    for i in range(1, height + 1):
        left_side = i % 2
        if left_side:
            f1 += "(\n"
            f2 += " )\n"
        else:
            f1 += " )\n"
            f2 += "(\n"

    seaweed_image = [f1, f2]
    x = random.randint(1, max(1, anim.width - 2))
    y = anim.height - height
    anim_speed = random.uniform(0.05, 0.3)

    anim.new_entity(
        name=f"seaweed_{random.random()}",
        shape=seaweed_image,
        position=[x, y, DEPTH['seaweed']],
        callback_args=[0, 0, 0, anim_speed],
        die_time=time.time() + random.randint(4 * 60, 12 * 60),
        death_cb=add_seaweed,
        default_color='GREEN',
    )


def add_bubble(fish, anim):
    cb_args = fish.callback_args
    bubble_pos = [fish.x, fish.y, fish.z]

    if cb_args[0] > 0:
        bubble_pos[0] += fish.width
    bubble_pos[1] += int(fish.height / 2)
    bubble_pos[2] -= 1

    anim.new_entity(
        shape=['.', 'o', 'O', 'O', 'O'],
        type_name='bubble',
        position=bubble_pos,
        callback_args=[0, -1, 0, 0.1],
        die_offscreen=True,
        physical=True,
        coll_handler=bubble_collision,
        default_color='CYAN',
    )


def bubble_collision(bubble, anim):
    for col_obj in bubble.collisions():
        if col_obj.type == 'waterline':
            bubble.kill()
            break


def add_splat(anim, pos):
    x, y, z = pos
    splat_image = [
        "\n   .\n  ***\n   '\n",
        "\n \",*;`\n \"*,**\n *\"'~'\n",
        "\n  , ,\n \" \",\"'\n *\" *'\"\n  \" ; .\n",
        "\n* ' , ' `\n' ` * . '\n ' `' \",' \n* ' \" * .\n\" * ', '\n"
    ]
    anim.new_entity(
        shape=splat_image,
        position=[x - 4, y - 2, z - 2],
        default_color='RED',
        callback_args=[0, 0, 0, 0.25],
        transparent=' ',
        die_frame=15,
    )


def add_all_fish(anim, new_fish=True):
    screen_size = (anim.height - 9) * anim.width
    fish_count = max(1, int(screen_size / 350))
    for _ in range(fish_count):
        add_fish(None, anim, new_fish=new_fish)


def add_fish(old_fish, anim, new_fish=True):
    if new_fish and random.randint(0, 12) > 8:
        add_new_fish(old_fish, anim)
    else:
        add_old_fish(old_fish, anim)


def add_new_fish(old_fish, anim):
    fish_image = [
        # Fish 0 Right
        r"""
   \
  / \
>=_('>
  \_/
   /
""", r"""
   1
  1 1
663745
  111
   3
""",
        # Fish 0 Left
        r"""
  /
 / \
<')_=<
 \_/
  \
""", r"""
  2
 111
547366
 111
  3
""",
        # Fish 1 Right
        r"""
     ,
     }\
\  .'  `\
}}<   ( 6>
/  `,  .'
     }/
     '
""", r"""
     2
     22
6  11  11
661   7 45
6  11  11
     33
     3
""",
        # Fish 1 Left
        r"""
    ,
   /\{
 /'  `.  /
<6 )   >{{
 `.  ,'  \
   /\{
    `
""", r"""
    2
   22
 11  11  6
54 7   166
 11  11  6
   33
    3
""",
        # Fish 2 Right
        r"""
            \'`.
             )  \
(`.      _.-`' ' '`-.
 \ `..`        (o) \_
  >  ><     (((       (
 / .` `._      /_|  /'
(.       `-. _  _.-`
            /__/'
""", r"""
            1111
             1  1
111      11111 1 1111
 1 11  11        141 11
  1  11     777       5
 1 11  111      333  11
111       111 1  1111
            11111
""",
        # Fish 2 Left
        r"""
       .'`/
      /  (
  .-'` ` `'-._      .')
_/ (o)        '..  /
)       )))     ><  <
`\  |_\      _.'  '. \
  '-._  _ .-'       .)
      `\__\
""", r"""
       1111
      1  1
  1111 1 11111      111
11 141        11  11 1
5       777     11  1
11  333      111  11 1
  1111  1 111       111
      11111
""",
        # Fish 3 Right
        r"""
       ,--,_
__    _\.---'-.
\ '.-"     // o\
/_.'-._    \\  /
       `"--(/"`
""", r"""
       22222
66    121111211
6 6111     77 41
6661111    77  1
       11113311
""",
        # Fish 3 Left
        r"""
    _,--,
 .-'---./_    __
/o \\     "-.' /
\  //    _.-'._\
 `" Wyndham--"`
""", r"""
    22222
 112111121    66
14 77     1116 6
1  77    1111666
 11331111
"""
    ]

    add_fish_entity(anim, fish_image)


def add_old_fish(old_fish, anim):
    fish_image = [
        # Fish 0 Right
        r"""
       \
     ...\..,
\  /'       \
 >=     (  ' >
/  \      / /
    `"'"'/''
""", r"""
       2
     1112111
6  11       1
 66     7  4 5
6  1      3 1
    11111311
""",
        # Fish 0 Left
        r"""
      /
  ,../...
 /       '\  /
< '  )     =<
 \ \      /  \
  `'\'"'"'
""", r"""
      2
  1112111
 1       11  6
5 4  7     66
 1 3      1  6
  11311111
""",
        # Fish 1 Right
        r"""
    \
\ /--\
>=  (o>
/ \__/
    /
""", r"""
    2
6 1111
66  745
6 1111
    3
""",
        # Fish 1 Left
        r"""
  /
 /--\ /
<o)  =<
 \__/ \
  \
""", r"""
  2
 1111 6
547  66
 1111 6
  3
""",
        # Fish 2 Right
        r"""
       \:.
\;,   ,;\\\\\,,
  \\\\\;;:::::::o
  ///;;::::::::<
 /;` ``/////``
""", r"""
       222
666   1122211
  6661111111114
  66611111111115
 666 113333311
""",
        # Fish 2 Left
        r"""
      .:/
   ,,///;,   ,;/
 o:::::::;;///
>::::::::;;\\\\\
  ''\\\\\\\\\'' ';\
""", r"""
      222
   1122211   666
 4111111111666
51111111111666
  113333311 666
""",
        # Tiny Fish Right
        r"""
  __
><_'>
   '
""", r"""
  11
61145
   3
""",
        # Tiny Fish Left
        r"""
 __
<'_><
 `
""", r"""
 11
54116
 3
"""
    ]

    add_fish_entity(anim, fish_image)


def add_fish_entity(anim, fish_image):
    total_fish = int(len(fish_image) / 2)
    fish_num = random.randint(0, total_fish - 1)
    fish_index = fish_num * 2

    speed = random.uniform(0.25, 2.25)
    depth = random.randint(DEPTH['fish_start'], DEPTH['fish_end'])

    color_mask = fish_image[fish_index + 1]
    color_mask = color_mask.replace('4', 'W')
    color_mask = rand_color(color_mask)

    if fish_num % 2:
        speed *= -1

    fish_obj = Entity(
        type_name='fish',
        shape=fish_image[fish_index],
        auto_trans=True,
        color=color_mask,
        position=[0, 0, depth],
        callback=fish_callback,
        callback_args=[speed, 0, 0],
        die_offscreen=True,
        death_cb=add_fish,
        physical=True,
        coll_handler=fish_collision,
    )

    max_height = 9
    min_height = max(max_height + 1, anim.height - fish_obj.height)
    fish_obj.y = random.randint(max_height, min_height)

    if fish_num % 2:
        fish_obj.x = anim.width - 2
    else:
        fish_obj.x = 1 - fish_obj.width

    anim.add_entity(fish_obj)


def fish_callback(fish, anim):
    if random.randint(0, 100) > 97:
        add_bubble(fish, anim)
    fish.move_entity(anim)


def fish_collision(fish, anim):
    for col_obj in fish.collisions():
        if col_obj.type == 'teeth' and fish.height <= 5:
            add_splat(anim, col_obj.position)
            fish.kill()
            break


def add_shark(old_ent, anim):
    shark_image = [
        r"""
                              __
                             ( `\
  ,                          )   `\
;' `.                        (     `\__
 ;   `.             __..---''          `~~~~-._
  `.   `.____...--''                       (b  `--._
    >                     _.-'      .((      ._     )
  .`.-`--...__         .-'     -.___.....-(|/|/|/|/'
 ;.'         `. ...----`.___.',,,_______......---'
 '           '-'
""", r"""
                     __
                    /' )
                  /'   (                          ,
              __/'     )                        .' `;
      _.-~~~~'          ``---..__             .'   ;
 _.--'  b)                       ``--...____.'   .'
(     _.      )).      `-._                     <
 `\|\|\|\|)-.....___.-     ` me-        __...--'-.'.
   `---......_______,,,`.___.'----... .'         `.;
                                     `-`           
"""
    ]

    shark_mask = [
        "\n\n\n\n\n                                           cR\n \n                                          cWWWWWWWW\n\n",
        "\n\n\n\n\n        Rc\n\n  WWWWWWWWc\n\n"
    ]

    dir_flag = random.randint(0, 1)
    x = -53
    y = random.randint(9, max(10, anim.height - 19))
    teeth_x = -9
    teeth_y = y + 7
    speed = 2.0

    if dir_flag:
        speed *= -1
        x = anim.width - 2
        teeth_x = x + 9

    anim.new_entity(
        type_name='teeth',
        shape="*",
        position=[teeth_x, teeth_y, DEPTH['shark'] + 1],
        depth=DEPTH['fish_end'] - DEPTH['fish_start'],
        callback_args=[speed, 0, 0],
        physical=True,
    )

    anim.new_entity(
        type_name="shark",
        color=shark_mask[dir_flag],
        shape=shark_image[dir_flag],
        auto_trans=True,
        position=[x, y, DEPTH['shark']],
        default_color='WHITE',
        callback_args=[speed, 0, 0],
        die_offscreen=True,
        death_cb=shark_death,
    )


def shark_death(shark, anim):
    for obj in anim.get_entities_of_type('teeth'):
        anim.del_entity(obj)
    random_object(shark, anim)


def add_ship(old_ent, anim):
    ship_image = [
        r"""
     |    |    |
    )_)  )_)  )_)
   )___))___))___)\
  )____)____)_____)\\\
_____|____|____|____\\\\\__
\                   /
""", r"""
         |    |    |
        (_(  (_(  (_(
      /(___((___((___(
    //(_____(____(____(
__///____|____|____|_____
    \                   /
"""
    ]

    ship_mask = [
        r"""
     y    y    y

                  w
                   ww
yyyyyyyyyyyyyyyyyyyywwwyy
y                   y
""", r"""
         y    y    y

      w
    ww
yywwwyyyyyyyyyyyyyyyyyyyy
    y                   y
"""
    ]

    dir_flag = random.randint(0, 1)
    x = -24
    speed = 1.0
    if dir_flag:
        speed *= -1
        x = anim.width - 2

    anim.new_entity(
        color=ship_mask[dir_flag],
        shape=ship_image[dir_flag],
        auto_trans=True,
        position=[x, 0, DEPTH['water_gap1']],
        default_color='WHITE',
        callback_args=[speed, 0, 0],
        die_offscreen=True,
        death_cb=random_object,
    )


def add_whale(old_ent, anim):
    whale_image = [
        r"""
        .-----:
      .'       `.
,    /       (o) \
\`._/          ,__)
""", r"""
    :-----.
  .'       `.
 / (o)       \    ,
(__,          \_.'/
"""
    ]

    whale_mask = [
        r"""
             C C
           CCCCCCC
           C  C  C
        BBBBBBB
      BB       BB
B    B       BWB B
BBBBB          BBBB
""", r"""
   C C
 CCCCCCC
 C  C  C
    BBBBBBB
  BB       BB
 B BWB       B    B
BBBB          BBBBB
"""
    ]

    water_spout = [
        "\n\n   :",
        "\n   :\n   :",
        "  . .\n  -:-\n   :",
        "  . .\n .-:-.\n   :",
        "  . .\n'.-:-.`\n'  :  '",
        "\n .- -.\n;  :  ;",
        "\n\n;     ;"
    ]

    dir_flag = random.randint(0, 1)
    speed = 1.0

    if dir_flag:
        spout_align = 1
        speed *= -1
        x = anim.width - 2
    else:
        spout_align = 11
        x = -18

    whale_anim = []
    whale_anim_mask = []

    for _ in range(5):
        whale_anim.append("\n\n\n" + whale_image[dir_flag])
        whale_anim_mask.append(whale_mask[dir_flag])

    for spout_frame in water_spout:
        aligned_spout = ("\n" + ' ' * spout_align).join(spout_frame.split('\n'))
        whale_anim.append(aligned_spout + whale_image[dir_flag])
        whale_anim_mask.append(whale_mask[dir_flag])

    anim.new_entity(
        color=whale_anim_mask,
        shape=whale_anim,
        auto_trans=True,
        position=[x, 0, DEPTH['water_gap2']],
        default_color='WHITE',
        callback_args=[speed, 0, 0, 1],
        die_offscreen=True,
        death_cb=random_object,
    )


def add_monster(old_ent, anim, new_monster=True):
    if new_monster:
        add_new_monster(old_ent, anim)
    else:
        add_old_monster(old_ent, anim)


def add_new_monster(old_ent, anim):
    monster_image = [
        [
            r"""
         _ _                       _ _       _a_a
       _{.`=`.}_      _ _        _{.`=`.}_    {/ ''\_
 _    {.'  _  '.}    {.`'`.}    {.'  _  '.}  {|  ._oo)
{ \  {/  .' '.  \}  {/ .-. \}  {/  .' '.  \} {/  |
""",
            r"""
                      _ _                    _a_a
  _      _ _        _{.`=`.}_      _ _      {/ ''\_
 { \    {.`'`.}    {.'  _  '.}    {.`'`.}    {|  ._oo)
  \ \  {/ .-. \}  {/  .' '.  \}  {/ .-. \}   {/  |
"""
        ],
        [
            r"""
   a_a_       _ _                       _ _
 _/'' \}    _{.`=`.}_      _ _        _{.`=`.}_
(oo_.  |}  {.'  _  '.}    {.`'`.}    {.'  _  '.}    _
    |  \} {/  .' '.  \}  {/ .-. \}  {/  .' '.  \}  / }
""",
            r"""
   a_a_                    _   _
 _/'' \}      _ _        _{.`=`.}_      _ _      _
(oo_.  |}    {.`'`.}    {.'  _  '.}    {.`'`.}    / }
    |  \}   {/ .-. \}  {/  .' '.  \}  {/ .-. \}  / /
"""
        ]
    ]

    monster_mask = [
        "\n" * 4 + " " * 48 + "W W\n",
        "\n" * 4 + "   W W\n"
    ]

    dir_flag = random.randint(0, 1)
    speed = 2.0
    if dir_flag:
        speed *= -1
        x = anim.width - 2
    else:
        x = -54

    anim_mask = [monster_mask[dir_flag], monster_mask[dir_flag]]

    anim.new_entity(
        shape=monster_image[dir_flag],
        auto_trans=True,
        color=anim_mask,
        position=[x, 2, DEPTH['water_gap2']],
        callback_args=[speed, 0, 0, 0.25],
        death_cb=random_object,
        die_offscreen=True,
        default_color='GREEN',
    )


def add_old_monster(old_ent, anim):
    monster_image = [
        [
            r"""
                                                          ____
            __                                           /   o  \
          /    \        _                     _         /     ____ >
  _      |  __  |     /   \        _        /   \      |     |
 | \     |  ||  |    |     |     /   \     |     |     |     |
""", r"""
                                                          ____
                                             __          /   o  \
             _                     _        /    \      /     ____ >
   _        /   \        _        /   \    |  __  |    |     |
  | \      |     |     /   \     |     |   |  ||  |    |     |
""", r"""
                                                          ____
                                  __                    /   o  \
 _                      _        /    \        _       /     ____ >
| \          _        /   \     |  __  |     /   \    |     |
 \ \        /   \    |     |    |  ||  |    |     |   |     |
""", r"""
                                                          ____
                       __                               /   o  \
  _          _        /    \        _                  /     ____ >
 | \        /   \    |  __  |     /   \        _      |     |
  \ \      |     |   |  ||  |    |     |     /   \    |     |
"""
        ],
        [
            r"""
    ____
  /  o   \                                          __
< ____     \       _                     _         /    \
      |     |    /   \        _        /   \      |  __  |      _
      |     |   |     |     /   \     |     |     |  ||  |     / |
""", r"""
    ____
  /  o   \         __
< ____     \     /    \       _                     _
      |     |   |  __  |    /   \        _        /   \       _
      |     |   |  ||  |   |     |     /   \     |     |     / |
""", r"""
    ____
  /  o   \                    __
< ____     \       _        /    \       _                      _
      |     |    /   \     |  __  |    /   \        _          / |
      |     |   |     |    |  ||  |   |     |     /   \       / /
""", r"""
    ____
  /  o   \                               __
< ____     \                  _        /    \       _          _
      |     |      _        /   \     |  __  |    /   \       / |
      |     |    /   \     |     |    |  ||  |   |     |     / /
"""
        ]
    ]

    monster_mask = [
        "\n\n                                                            W\n",
        "\n\n     W\n"
    ]

    dir_flag = random.randint(0, 1)
    speed = 2.0
    if dir_flag:
        speed *= -1
        x = anim.width - 2
    else:
        x = -64

    anim_mask = [monster_mask[dir_flag]] * 4

    anim.new_entity(
        shape=monster_image[dir_flag],
        auto_trans=True,
        color=anim_mask,
        position=[x, 2, DEPTH['water_gap2']],
        callback_args=[speed, 0, 0, 0.25],
        death_cb=random_object,
        die_offscreen=True,
        default_color='GREEN',
    )


def add_big_fish(old_ent, anim, new_fish=True):
    if new_fish and random.randint(0, 2) > 1:
        add_big_fish_2(old_ent, anim)
    else:
        add_big_fish_1(old_ent, anim)


def add_big_fish_1(old_ent, anim):
    big_fish_image = [
        r"""
 ______
`""-.  `````-----.....__
     `.  .      .       `-.
       :     .     .       `.
 ,     :   .    .          _ :
: `.   :                  (@) `._
 `. `..'     .     =`-.       .__)
   ;     .        =  ~  :     .-"
 .' .'`.   .    .  =.-'  `._ .'
: .'   :               .   .'
 '   .'  .    .     .   .-'
   .'____....----''.'=.'
   ""             .'.'
               ''"'`
""", r"""
                           ______
          __.....-----'''''  .-""'
       .-'       .      .  .'
     .'       .     .     :
    : _          .    .   :     ,
 _.' (@)                  :   .' :
(__.       .-'=     .     `..' .'
 "-.     :  ~  =        .     ;
   `. _.'  `-.=  .    .   .'`. `.
     `.   .               :   `. :
       `-.   .     .    .  `.   `
          `.=`.``----....____`.
            `.`.             ""
              '`"``
"""
    ]

    big_fish_mask = [
        r"""
 111111
11111  11111111111111111
     11  2      2       111
       1     2     2       11
 1     1   2    2          1 1
1 11   1                  1W1 111
 11 1111     2     1111       1111
   1     2        1  1  1     111
 11 1111   2    2  1111  111 11
1 11   1               2   11
 1   11  2    2     2   111
   111111111111111111111
   11             1111
               11111
""", r"""
                           111111
          11111111111111111  11111
       111       2      2  11
     11       2     2     1
    1 1          2    2   1     1
 111 1W1                  1   11 1
1111       1111     2     1111 11
 111     1  1  1        2     1
   11 111  1111  2    2   1111 11
     11   2               1   11 1
       111   2     2    2  11   1
          111111111111111111111
            1111             11
              11111
"""
    ]

    dir_flag = random.randint(0, 1)
    speed = 3.0
    if dir_flag:
        x = anim.width - 1
        speed *= -1
    else:
        x = -34

    max_height = 9
    min_height = max(max_height + 1, anim.height - 15)
    y = random.randint(max_height, min_height)
    color_mask = rand_color(big_fish_mask[dir_flag])

    anim.new_entity(
        shape=big_fish_image[dir_flag],
        auto_trans=True,
        color=color_mask,
        position=[x, y, DEPTH['shark']],
        callback_args=[speed, 0, 0],
        death_cb=random_object,
        die_offscreen=True,
        default_color='YELLOW',
    )


def add_big_fish_2(old_ent, anim):
    big_fish_image = [
        r"""
                _ _ _
             .='\\ \\ \\`"=,
           .'\\ \\ \\ \\ \\ \\ \\
\'=._     / \\ \\ \\_\\_\\_\\_\\_\\
\'=._'.  /\\ \\,-"`- _ - _ - '-.
  \`=._\|'.\/- _ - _ - _ - _- \
  ;"= ._\=./_ -_ -_ {`"=_    @ \
   ;="_-_=- _ -  _ - {"=_"-     \
   ;_=_--_.,          {_.='   .-/
  ;.="` / ';\        _.     _.-`
  /_.='/ \/ /;._ _ _{.-;`/"`
/._=_.'   '/ / / / /{.= /
/.='      `'./_/_.=`{_/
""", r"""
            _ _ _
        ,="`/ / /'=.
       / / / / / / /'.
      /_/_/_/_/_/ / / \     _.='/
   .-' - _ - _ -`"-,/ /\  .'_.='/
  / -_ - _ - _ - _ -\/.'|/_.=`/
 / @    _="\} _- _- _\.=/_. =";
/     -"_="\} - _  - _ -=_-_"=;
\-.   '=._\}          ,._--_=_;
 `-._     ._        /;' \ `"=.;
     `"\`;-.\}_ _ _.;\ \/ \'=._\
        \ =.\}\ \ \ \ \'   '._=_.\
         \_\}`=._\_\.'     '=.\
"""
    ]

    big_fish_mask = [
        r"""
                1 1 1
             1111 1 11111
           111 1 1 1 1 1 1
11111     1 1 1 11111111111
1111111  11 111112 2 2 2 2 111
  111111111112 2 2 2 2 2 2 22 1
  111 1111 12 22 22 11111    W 1
   11111112 2 2  2 2 111111     1
   111111111          11111   111
  11111 11111        11     1111
  111111 11 1111 1 111111111
1111111   11 1 1 1 1111 1
1111       1111111111111
""", r"""
            1 1 1
        11111 1 1111
       1 1 1 1 1 1 111
      11111111111 1 1 1     11111
   111 2 2 2 2 211111 11  1111111
  1 22 2 2 2 2 2 2 211111111111
 1 W    11111 22 22 2111111 111
1     111111 2 2  2 2 21111111
111   11111          111111111
 1111     11        111 1 11111
     111111111 1 1111 11 111111
        1 1111 1 1 1 11   1111111
         1111111111111       1111
"""
    ]

    dir_flag = random.randint(0, 1)
    speed = 2.5
    if dir_flag:
        x = anim.width - 1
        speed *= -1
    else:
        x = -33

    max_height = 9
    min_height = max(max_height + 1, anim.height - 14)
    y = random.randint(max_height, min_height)
    color_mask = rand_color(big_fish_mask[dir_flag])

    anim.new_entity(
        shape=big_fish_image[dir_flag],
        auto_trans=True,
        color=color_mask,
        position=[x, y, DEPTH['shark']],
        callback_args=[speed, 0, 0],
        death_cb=random_object,
        die_offscreen=True,
        default_color='YELLOW',
    )


RANDOM_OBJECT_BUILDERS = [
    add_ship,
    add_whale,
    add_monster,
    add_big_fish,
    add_shark,
]


def random_object(dead_object, anim):
    builder = random.choice(RANDOM_OBJECT_BUILDERS)
    builder(dead_object, anim)


def get_key_nonblocking():
    """Non-blocking keyboard input check across platforms."""
    if sys.platform == "win32":
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            try:
                return ch.decode('utf-8', errors='ignore').lower()
            except Exception:
                return ""
        return ""
    else:
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            return sys.stdin.read(1).lower()
        return ""


def main():
    parser = argparse.ArgumentParser(description="ASCIIquarium in Python")
    parser.add_argument("-c", "--classic", action="store_true", help="Classic mode (no new fish or monsters)")
    parser.add_argument("-v", "--version", action="version", version=f"asciiquarium {VERSION}")
    args = parser.parse_args()

    new_fish = not args.classic
    new_monster = not args.classic

    # Prepare terminal settings
    old_settings = None
    if sys.platform != "win32":
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())

    # Hide cursor & clear screen
    sys.stdout.write("\033[?25l\033[2J")
    sys.stdout.flush()

    anim = AnimationEngine()

    try:
        while True:
            add_environment(anim)
            add_castle(anim)
            add_all_seaweed(anim)
            add_all_fish(anim, new_fish=new_fish)
            random_object(None, anim)

            anim.redraw_screen()

            while True:
                key = get_key_nonblocking()

                if key == 'q':
                    return
                elif key == 'r':
                    break  # Reset/redraw all objects
                elif key == 'p':
                    anim.paused = not anim.paused

                anim.animate()
                anim.redraw_screen()

                time.sleep(0.08)  # ~12 FPS loop timing

            anim.update_term_size()
            anim.remove_all_entities()

    finally:
        # Restore terminal & show cursor
        sys.stdout.write("\033[?25h\033[0m\033[2J\033[H")
        sys.stdout.flush()
        if old_settings and sys.platform != "win32":
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


if __name__ == "__main__":
    main()
