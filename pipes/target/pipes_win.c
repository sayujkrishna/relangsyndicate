/*
 * pipes_win.c - A native Windows port of pipes-py (itself a Python
 * rewrite of pipes.sh), built entirely on the Win32 console API.
 *
 * No curses / PDCurses dependency: this talks directly to the
 * console via GetStdHandle / WriteConsoleW / SetConsoleTextAttribute,
 * so it builds with just a plain Windows C toolchain and runs
 * natively in PowerShell, cmd.exe, or Windows Terminal.
 *
 * Build (MinGW-w64, e.g. from MSYS2 or w64devkit):
 *     gcc -O2 -Wall -Wextra -o pipes.exe pipes_win.c
 *
 * Build (MSVC, from a "Developer PowerShell for VS"):
 *     cl /O2 /W4 pipes_win.c
 *
 * Run:
 *     .\pipes.exe
 *
 * Same keys and flags as the Python version:
 *   P/O steadier/twitchier, F/D faster/slower, B toggle bold,
 *   C toggle color, K toggle keep-style, Esc or ? to quit.
 *   -p pipes  -f fps  -s steady  -r limit  -R random-start
 *   -B no-bold  -C no-color  -P pipe-style(0-9)  -K keep-style
 *   -S save-config  -v version  -h help
 */

#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <conio.h>
#include <ctype.h>
#include <direct.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wchar.h>

#define PIPES_VERSION "2.0.0"

/* ===================== types.py equivalent ========================= */

#define MAX_COLORS      64
#define MAX_PIPE_TYPES  64

typedef enum {
    DIR_UP    = 0,
    DIR_RIGHT = 1,
    DIR_DOWN  = 2,
    DIR_LEFT  = 3
} Direction;

typedef struct {
    int  pipes;
    int  fps;
    int  steady;
    int  limit;
    bool random_start;
    bool bold;
    bool color;
    bool keep_style;

    int colors[MAX_COLORS];
    int colors_count;

    int pipe_types[MAX_PIPE_TYPES];
    int pipe_types_count;
} PipeConfig;

typedef struct {
    int       x;
    int       y;
    Direction direction;
    int       pipe_type;
    int       color;
    WORD      attr;
} Pipe;

/* ===================== renderer.py equivalent ======================= */

/* Same 10 glyph sets as the Python/curses version, written with \u
 * escapes so the file stays plain ASCII on disk -- no source-encoding
 * surprises in whatever editor/compiler you use on Windows. Each is
 * padded/truncated to 16 wide characters, exactly like Python's
 * `(pipe_set + " " * 16)[:16]`.
 */
#define SET_WIDTH 16
#define NUM_PIPE_SETS 10

static const wchar_t *RAW_SETS[NUM_PIPE_SETS] = {
    L"\u2503\u250F \u2513\u251B\u2501\u2513  \u2517\u2503\u251B\u2517 \u250F\u2501",
    L"\u2502\u256D \u256E\u256F\u2500\u256E  \u2570\u2502\u256F\u2570 \u256D\u2500",
    L"\u2502\u250C \u2510\u2518\u2500\u2510  \u2514\u2502\u2518\u2514 \u250C\u2500",
    L"\u2551\u2554 \u2557\u255D\u2550\u2557  \u255A\u2551\u255D\u255A \u2554\u2550",
    L"|+ ++-+  +|++ +-",
    L"|/ \\ /-\\  \\|/\\ /-",
    L".o ....  .... .o",
    L".o oo.o  o.oo o.",
    L"-\\ /\\|/  /-\\/ \\|",
    L"\u257F\u250D \u2511\u251A\u257C\u2512  \u2515\u257D\u2519\u2516 \u250E\u257E",
};

static wchar_t SETS[NUM_PIPE_SETS * SET_WIDTH];

static void prepare_sets(void) {
    for (int i = 0; i < NUM_PIPE_SETS; i++) {
        size_t n = wcslen(RAW_SETS[i]);
        for (int j = 0; j < SET_WIDTH; j++) {
            SETS[i * SET_WIDTH + j] = (j < (int)n) ? RAW_SETS[i][j] : L' ';
        }
    }
}

/* Curses-style 8-color palette (0=black .. 7=white) mapped to Win32
 * console FOREGROUND_* bit combinations. `color % 8` mirrors
 * renderer.py's `color % max_colors` (max_colors capped at 8).
 */
static const WORD FG_BITS[8] = {
    0,                                                   /* 0 black   */
    FOREGROUND_RED,                                      /* 1 red     */
    FOREGROUND_GREEN,                                    /* 2 green   */
    FOREGROUND_RED | FOREGROUND_GREEN,                   /* 3 yellow  */
    FOREGROUND_BLUE,                                     /* 4 blue    */
    FOREGROUND_RED | FOREGROUND_BLUE,                    /* 5 magenta */
    FOREGROUND_GREEN | FOREGROUND_BLUE,                  /* 6 cyan    */
    FOREGROUND_RED | FOREGROUND_GREEN | FOREGROUND_BLUE, /* 7 white   */
};

typedef struct {
    HANDLE hOut;
    WORD   default_attr; /* attribute the console had before we started */
    int    origin_x, origin_y; /* top-left of the visible window, in buffer coords */
    int    width, height;      /* visible window size */
    PipeConfig *config;
} Renderer;

static void renderer_get_geometry(Renderer *r) {
    CONSOLE_SCREEN_BUFFER_INFO csbi;
    GetConsoleScreenBufferInfo(r->hOut, &csbi);
    r->origin_x = csbi.srWindow.Left;
    r->origin_y = csbi.srWindow.Top;
    r->width = csbi.srWindow.Right - csbi.srWindow.Left + 1;
    r->height = csbi.srWindow.Bottom - csbi.srWindow.Top + 1;
}

static void renderer_init(Renderer *r, PipeConfig *config) {
    r->hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    r->config = config;
    prepare_sets();

    CONSOLE_SCREEN_BUFFER_INFO csbi;
    GetConsoleScreenBufferInfo(r->hOut, &csbi);
    r->default_attr = csbi.wAttributes;

    CONSOLE_CURSOR_INFO cci;
    GetConsoleCursorInfo(r->hOut, &cci);
    cci.bVisible = FALSE;
    SetConsoleCursorInfo(r->hOut, &cci);

    renderer_get_geometry(r);
}

/* Get the display attribute for a given color (curses's
 * get_color_attr): background bits are preserved from whatever the
 * console had at startup; foreground bits come from the 8-color
 * palette; bold adds FOREGROUND_INTENSITY.
 */
static WORD renderer_get_color_attr(const Renderer *r, int color) {
    if (!r->config->color) {
        return r->default_attr;
    }
    int idx = ((color % 8) + 8) % 8;
    WORD attr = (WORD)((r->default_attr & 0xFFF0) | FG_BITS[idx]);
    if (r->config->bold) {
        attr |= FOREGROUND_INTENSITY;
    }
    return attr;
}

static void renderer_draw_pipe(Renderer *r, const Pipe *pipe, Direction old_direction, Direction new_direction) {
    int base = pipe->pipe_type * SET_WIDTH;
    int index = base + old_direction * 4 + new_direction;
    wchar_t ch = (index >= 0 && index < NUM_PIPE_SETS * SET_WIDTH) ? SETS[index] : L'?';

    COORD pos;
    pos.X = (SHORT)(r->origin_x + pipe->x);
    pos.Y = (SHORT)(r->origin_y + pipe->y);

    /* Out-of-bounds writes just fail quietly on Windows (no exception
     * to suppress), mirroring curses's contextlib.suppress(curses.error). */
    SetConsoleCursorPosition(r->hOut, pos);
    SetConsoleTextAttribute(r->hOut, pipe->attr);
    DWORD written;
    WriteConsoleW(r->hOut, &ch, 1, &written, NULL);
}

static void renderer_clear(Renderer *r) {
    DWORD written;
    for (int row = 0; row < r->height; row++) {
        COORD start;
        start.X = (SHORT)r->origin_x;
        start.Y = (SHORT)(r->origin_y + row);
        FillConsoleOutputCharacterW(r->hOut, L' ', (DWORD)r->width, start, &written);
        FillConsoleOutputAttribute(r->hOut, r->default_attr, (DWORD)r->width, start, &written);
    }
}

/* ===================== config.py equivalent ========================= */

static void get_config_dir(char *buf, size_t buflen) {
    const char *local_app_data = getenv("LOCALAPPDATA");
    if (local_app_data == NULL) {
        local_app_data = ".";
    }
    snprintf(buf, buflen, "%s\\pipes-py", local_app_data);
}

static void get_config_file(char *buf, size_t buflen) {
    char dir[1024];
    get_config_dir(dir, sizeof(dir));
    snprintf(buf, buflen, "%s\\config.json", dir);
}

static void mkdir_p(const char *path) {
    char tmp[1024];
    size_t len = strlen(path);
    if (len == 0 || len >= sizeof(tmp)) {
        return;
    }
    strcpy(tmp, path);
    for (size_t i = 1; i < len; i++) {
        if (tmp[i] == '\\' || tmp[i] == '/') {
            char saved = tmp[i];
            tmp[i] = '\0';
            _mkdir(tmp);
            tmp[i] = saved;
        }
    }
    _mkdir(tmp);
}

static void default_config(PipeConfig *out) {
    out->pipes = 1;
    out->fps = 75;
    out->steady = 13;
    out->limit = 2000;
    out->random_start = false;
    out->bold = true;
    out->color = true;
    out->keep_style = false;

    static const int default_colors[] = {1, 2, 3, 4, 5, 6, 7, 0};
    out->colors_count = (int)(sizeof(default_colors) / sizeof(default_colors[0]));
    memcpy(out->colors, default_colors, sizeof(default_colors));

    out->pipe_types_count = 1;
    out->pipe_types[0] = 0;
}

/* Minimal JSON reader/writer -- understands exactly the flat shape
 * save_config() below produces (ints, bools, flat arrays of ints).
 * Same tradeoff config.py implicitly makes: it only ever reads a file
 * it wrote itself, falling back to defaults on anything else. */

typedef struct {
    const char *s;
    size_t pos;
    size_t len;
} JsonParser;

static void skip_ws(JsonParser *p) {
    while (p->pos < p->len && isspace((unsigned char)p->s[p->pos])) p->pos++;
}
static bool expect_char(JsonParser *p, char c) {
    skip_ws(p);
    if (p->pos < p->len && p->s[p->pos] == c) { p->pos++; return true; }
    return false;
}
static bool parse_key(JsonParser *p, char *buf, size_t buflen) {
    skip_ws(p);
    if (p->pos >= p->len || p->s[p->pos] != '"') return false;
    p->pos++;
    size_t i = 0;
    while (p->pos < p->len && p->s[p->pos] != '"') {
        if (i + 1 < buflen) buf[i++] = p->s[p->pos];
        p->pos++;
    }
    buf[i] = '\0';
    if (p->pos >= p->len) return false;
    p->pos++;
    return true;
}
static bool parse_number(JsonParser *p, long *out) {
    skip_ws(p);
    size_t start = p->pos;
    if (p->pos < p->len && (p->s[p->pos] == '-' || p->s[p->pos] == '+')) p->pos++;
    while (p->pos < p->len && isdigit((unsigned char)p->s[p->pos])) p->pos++;
    if (p->pos == start) return false;
    *out = strtol(p->s + start, NULL, 10);
    return true;
}
static bool parse_bool(JsonParser *p, bool *out) {
    skip_ws(p);
    if (p->pos + 4 <= p->len && strncmp(p->s + p->pos, "true", 4) == 0) { p->pos += 4; *out = true; return true; }
    if (p->pos + 5 <= p->len && strncmp(p->s + p->pos, "false", 5) == 0) { p->pos += 5; *out = false; return true; }
    return false;
}
static bool parse_int_array(JsonParser *p, int *arr, int max, int *count) {
    if (!expect_char(p, '[')) return false;
    *count = 0;
    skip_ws(p);
    if (p->pos < p->len && p->s[p->pos] == ']') { p->pos++; return true; }
    while (1) {
        long val;
        if (!parse_number(p, &val)) return false;
        if (*count < max) arr[(*count)++] = (int)val;
        skip_ws(p);
        if (p->pos < p->len && p->s[p->pos] == ',') { p->pos++; continue; }
        break;
    }
    return expect_char(p, ']');
}
static bool skip_value(JsonParser *p) {
    skip_ws(p);
    if (p->pos >= p->len) return false;
    char c = p->s[p->pos];
    if (c == '"') {
        p->pos++;
        while (p->pos < p->len && p->s[p->pos] != '"') p->pos++;
        if (p->pos >= p->len) return false;
        p->pos++;
        return true;
    }
    if (c == '[') {
        int dummy[MAX_COLORS]; int count;
        return parse_int_array(p, dummy, MAX_COLORS, &count);
    }
    if (c == 't' || c == 'f') {
        bool dummy;
        return parse_bool(p, &dummy);
    }
    long dummy;
    return parse_number(p, &dummy);
}

static bool parse_config_json(const char *text, size_t len, PipeConfig *out) {
    JsonParser p = {text, 0, len};
    if (!expect_char(&p, '{')) return false;
    skip_ws(&p);
    if (p.pos < p.len && p.s[p.pos] == '}') { p.pos++; return true; }

    while (1) {
        char key[64];
        if (!parse_key(&p, key, sizeof(key))) return false;
        if (!expect_char(&p, ':')) return false;

        long ival; bool bval;
        if (strcmp(key, "pipes") == 0) { if (!parse_number(&p, &ival)) return false; out->pipes = (int)ival; }
        else if (strcmp(key, "fps") == 0) { if (!parse_number(&p, &ival)) return false; out->fps = (int)ival; }
        else if (strcmp(key, "steady") == 0) { if (!parse_number(&p, &ival)) return false; out->steady = (int)ival; }
        else if (strcmp(key, "limit") == 0) { if (!parse_number(&p, &ival)) return false; out->limit = (int)ival; }
        else if (strcmp(key, "random_start") == 0) { if (!parse_bool(&p, &bval)) return false; out->random_start = bval; }
        else if (strcmp(key, "bold") == 0) { if (!parse_bool(&p, &bval)) return false; out->bold = bval; }
        else if (strcmp(key, "color") == 0) { if (!parse_bool(&p, &bval)) return false; out->color = bval; }
        else if (strcmp(key, "keep_style") == 0) { if (!parse_bool(&p, &bval)) return false; out->keep_style = bval; }
        else if (strcmp(key, "colors") == 0) { if (!parse_int_array(&p, out->colors, MAX_COLORS, &out->colors_count)) return false; }
        else if (strcmp(key, "pipe_types") == 0) { if (!parse_int_array(&p, out->pipe_types, MAX_PIPE_TYPES, &out->pipe_types_count)) return false; }
        else { if (!skip_value(&p)) return false; }

        skip_ws(&p);
        if (p.pos < p.len && p.s[p.pos] == ',') { p.pos++; continue; }
        break;
    }
    return expect_char(&p, '}');
}

static void load_config(PipeConfig *out) {
    char config_file[1024];
    get_config_file(config_file, sizeof(config_file));

    default_config(out);

    FILE *f = fopen(config_file, "rb");
    if (f == NULL) return;

    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return; }
    long size = ftell(f);
    if (size < 0) { fclose(f); return; }
    rewind(f);

    char *buf = malloc((size_t)size + 1);
    if (buf == NULL) { fclose(f); return; }

    size_t read = fread(buf, 1, (size_t)size, f);
    fclose(f);
    buf[read] = '\0';

    PipeConfig parsed = *out;
    bool ok = parse_config_json(buf, read, &parsed);
    free(buf);
    if (ok) *out = parsed;
}

static void save_config(const PipeConfig *config) {
    char config_dir[1024], config_file[1024];
    get_config_dir(config_dir, sizeof(config_dir));
    get_config_file(config_file, sizeof(config_file));

    mkdir_p(config_dir);

    FILE *f = fopen(config_file, "w");
    if (f == NULL) return;

    fprintf(f, "{\n");
    fprintf(f, "  \"pipes\": %d,\n", config->pipes);
    fprintf(f, "  \"fps\": %d,\n", config->fps);
    fprintf(f, "  \"steady\": %d,\n", config->steady);
    fprintf(f, "  \"limit\": %d,\n", config->limit);
    fprintf(f, "  \"random_start\": %s,\n", config->random_start ? "true" : "false");
    fprintf(f, "  \"bold\": %s,\n", config->bold ? "true" : "false");
    fprintf(f, "  \"color\": %s,\n", config->color ? "true" : "false");
    fprintf(f, "  \"keep_style\": %s,\n", config->keep_style ? "true" : "false");
    fprintf(f, "  \"colors\": [");
    for (int i = 0; i < config->colors_count; i++) fprintf(f, "%d%s", config->colors[i], (i + 1 < config->colors_count) ? ", " : "");
    fprintf(f, "],\n");
    fprintf(f, "  \"pipe_types\": [");
    for (int i = 0; i < config->pipe_types_count; i++) fprintf(f, "%d%s", config->pipe_types[i], (i + 1 < config->pipe_types_count) ? ", " : "");
    fprintf(f, "]\n");
    fprintf(f, "}\n");

    fclose(f);
}

/* ===================== pipes.py equivalent =========================== */

typedef struct {
    Renderer    renderer;
    PipeConfig *config;
    Pipe       *pipes;
    int         pipes_count;
    int         height, width;
    long        count;
    DWORD       delay_ms;
} PipesScreen;

static void init_pipes(PipesScreen *ps) {
    ps->pipes_count = ps->config->pipes;
    ps->pipes = malloc(sizeof(Pipe) * (size_t)ps->pipes_count);

    for (int i = 0; i < ps->pipes_count; i++) {
        Direction direction;
        int x, y;
        if (ps->config->random_start) {
            direction = (Direction)(rand() % 4);
            x = (ps->width > 0) ? rand() % ps->width : 0;
            y = (ps->height > 0) ? rand() % ps->height : 0;
        } else {
            direction = DIR_UP;
            x = ps->width / 2;
            y = ps->height / 2;
        }

        int pipe_type = ps->config->pipe_types[rand() % ps->config->pipe_types_count];
        int color = ps->config->colors[rand() % ps->config->colors_count];

        ps->pipes[i].x = x;
        ps->pipes[i].y = y;
        ps->pipes[i].direction = direction;
        ps->pipes[i].pipe_type = pipe_type;
        ps->pipes[i].color = color;
        ps->pipes[i].attr = renderer_get_color_attr(&ps->renderer, color);
    }
}

static void pipes_screen_init(PipesScreen *ps, PipeConfig *config) {
    ps->config = config;
    ps->pipes = NULL;
    ps->pipes_count = 0;

    renderer_init(&ps->renderer, config);
    ps->height = ps->renderer.height;
    ps->width = ps->renderer.width;
    ps->count = 0;
    ps->delay_ms = (DWORD)(1000.0 / (double)config->fps);

    init_pipes(ps);
}

static void pipes_screen_destroy(PipesScreen *ps) {
    free(ps->pipes);
    ps->pipes = NULL;
}

static void update_pipe_colors(PipesScreen *ps) {
    for (int i = 0; i < ps->pipes_count; i++) {
        ps->pipes[i].attr = renderer_get_color_attr(&ps->renderer, ps->pipes[i].color);
    }
}

/* Python's `%` always returns non-negative for a positive divisor;
 * C's can return negative for a negative left operand. */
static int py_mod(int a, int b) {
    int r = a % b;
    return (r < 0) ? r + b : r;
}

static void update_pipes(PipesScreen *ps) {
    for (int i = 0; i < ps->pipes_count; i++) {
        Pipe *pipe = &ps->pipes[i];
        int x = pipe->x, y = pipe->y;
        Direction old_direction = pipe->direction;

        if (old_direction % 2) {
            x += -(int)old_direction + 2;
        } else {
            y += (int)old_direction - 1;
        }

        if (x < 0 || x >= ps->width || y < 0 || y >= ps->height) {
            if (!ps->config->keep_style) {
                pipe->pipe_type = ps->config->pipe_types[rand() % ps->config->pipe_types_count];
                pipe->color = ps->config->colors[rand() % ps->config->colors_count];
                pipe->attr = renderer_get_color_attr(&ps->renderer, pipe->color);
            }
            x = (ps->width > 0) ? py_mod(x, ps->width) : 0;
            y = (ps->height > 0) ? py_mod(y, ps->height) : 0;
        }

        Direction new_direction = old_direction;
        if (rand() % ps->config->steady <= 1) {
            int turn = 2 * (rand() % 2) - 1;
            new_direction = (Direction)py_mod((int)old_direction + turn, 4);
        }

        renderer_draw_pipe(&ps->renderer, pipe, old_direction, new_direction);

        pipe->x = x;
        pipe->y = y;
        pipe->direction = new_direction;
    }
}

static bool handle_key(PipesScreen *ps, int key) {
    char key_char = '\0';
    if (key >= 0 && key <= 255) key_char = (char)toupper(key);

    if (key_char == 'P' && ps->config->steady < 15) {
        ps->config->steady += 1;
    } else if (key_char == 'O' && ps->config->steady > 3) {
        ps->config->steady -= 1;
    } else if (key_char == 'F' && ps->config->fps < 100) {
        ps->config->fps += 1;
        ps->delay_ms = (DWORD)(1000.0 / (double)ps->config->fps);
    } else if (key_char == 'D' && ps->config->fps > 20) {
        ps->config->fps -= 1;
        ps->delay_ms = (DWORD)(1000.0 / (double)ps->config->fps);
    } else if (key_char == 'B') {
        ps->config->bold = !ps->config->bold;
        update_pipe_colors(ps);
    } else if (key_char == 'C') {
        ps->config->color = !ps->config->color;
        update_pipe_colors(ps);
    } else if (key_char == 'K') {
        ps->config->keep_style = !ps->config->keep_style;
    } else if (key_char == '?' || key == 27) {
        return false;
    }
    return true;
}

static volatile sig_atomic_t g_interrupted = 0;
static void on_sigint(int signum) { (void)signum; g_interrupted = 1; }

static bool pipes_screen_update(PipesScreen *ps) {
    if (_kbhit()) {
        int key = _getch();
        if (!handle_key(ps, key)) return false;
    }

    renderer_get_geometry(&ps->renderer);
    if (ps->renderer.width != ps->width || ps->renderer.height != ps->height) {
        ps->width = ps->renderer.width;
        ps->height = ps->renderer.height;
        renderer_clear(&ps->renderer);
    }

    update_pipes(ps);

    ps->count += ps->pipes_count;
    if (ps->config->limit > 0 && ps->count >= ps->config->limit) {
        renderer_clear(&ps->renderer);
        ps->count = 0;
    }

    Sleep(ps->delay_ms);
    return true;
}

/* ===================== __main__.py equivalent ========================= */

static int clamp_int(int value, int lo, int hi) {
    if (value < lo) return lo;
    if (value > hi) return hi;
    return value;
}

static void print_usage(const char *prog) {
    printf("usage: %s [-h] [-p PIPES] [-f FPS] [-s STEADY] [-r LIMIT] [-R] [-B] [-C]\n", prog);
    printf("               [-P {0-9}] [-K] [-S] [-v]\n\n");
    printf("Basically pipes.sh but rewritten in C (Windows console build)\n\n");
    printf("options:\n");
    printf("  -h, --help            show this help message and exit\n");
    printf("  -p, --pipes PIPES     number of pipes\n");
    printf("  -f, --fps FPS         frames per second (20-100)\n");
    printf("  -s, --steady STEADY   steadiness (5-15)\n");
    printf("  -r, --limit LIMIT     character limit before reset\n");
    printf("  -R, --random          random start\n");
    printf("  -B, --no-bold         disable bold\n");
    printf("  -C, --no-color        disable color\n");
    printf("  -P, --pipe-style N    change pipe style (0-9)\n");
    printf("  -K, --keep-style      keep style on wrap\n");
    printf("  -S, --save-config     save current settings as default\n");
    printf("  -v, --version         show program's version number and exit\n");
}

typedef struct {
    bool have_pipes; int pipes;
    bool have_fps; int fps;
    bool have_steady; int steady;
    bool have_limit; int limit;
    bool random_start;
    bool no_bold;
    bool no_color;
    bool have_pipe_style; int pipe_style;
    bool keep_style;
    bool save_config_flag;
} Args;

/* Simple hand-rolled argv parser (no getopt on stock Windows toolchains).
 * Supports the same short flags as the Python version, plus a few
 * common long-option spellings. */
static void parse_args(int argc, char **argv, Args *args) {
    memset(args, 0, sizeof(*args));

    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        const char *val = NULL;

        #define NEXT_VAL() (val = (i + 1 < argc) ? argv[++i] : NULL)

        if (!strcmp(a, "-h") || !strcmp(a, "--help")) {
            print_usage(argv[0]); exit(0);
        } else if (!strcmp(a, "-p") || !strcmp(a, "--pipes")) {
            NEXT_VAL(); if (val) { args->have_pipes = true; args->pipes = atoi(val); }
        } else if (!strcmp(a, "-f") || !strcmp(a, "--fps")) {
            NEXT_VAL(); if (val) { args->have_fps = true; args->fps = atoi(val); }
        } else if (!strcmp(a, "-s") || !strcmp(a, "--steady")) {
            NEXT_VAL(); if (val) { args->have_steady = true; args->steady = atoi(val); }
        } else if (!strcmp(a, "-r") || !strcmp(a, "--limit")) {
            NEXT_VAL(); if (val) { args->have_limit = true; args->limit = atoi(val); }
        } else if (!strcmp(a, "-R") || !strcmp(a, "--random")) {
            args->random_start = true;
        } else if (!strcmp(a, "-B") || !strcmp(a, "--no-bold")) {
            args->no_bold = true;
        } else if (!strcmp(a, "-C") || !strcmp(a, "--no-color")) {
            args->no_color = true;
        } else if (!strcmp(a, "-P") || !strcmp(a, "--pipe-style")) {
            NEXT_VAL();
            if (val) {
                int v = atoi(val);
                if (v < 0 || v > 9) {
                    fprintf(stderr, "%s: error: -P/--pipe-style must be 0-9\n", argv[0]);
                    exit(2);
                }
                args->have_pipe_style = true; args->pipe_style = v;
            }
        } else if (!strcmp(a, "-K") || !strcmp(a, "--keep-style")) {
            args->keep_style = true;
        } else if (!strcmp(a, "-S") || !strcmp(a, "--save-config")) {
            args->save_config_flag = true;
        } else if (!strcmp(a, "-v") || !strcmp(a, "--version")) {
            printf("pipes-c v%s\n", PIPES_VERSION); exit(0);
        } else {
            fprintf(stderr, "%s: error: unrecognized argument: %s\n", argv[0], a);
            print_usage(argv[0]);
            exit(2);
        }
        #undef NEXT_VAL
    }
}

static void run_pipes(PipeConfig *config) {
    PipesScreen pipes;
    pipes_screen_init(&pipes, config);

    while (!g_interrupted && pipes_screen_update(&pipes)) {
        /* loop */
    }

    pipes_screen_destroy(&pipes);
}

int main(int argc, char **argv) {
    Args args;
    parse_args(argc, argv, &args);

    PipeConfig config;
    load_config(&config);

    if (args.have_pipes) config.pipes = (args.pipes > 1) ? args.pipes : 1;
    if (args.have_fps) config.fps = clamp_int(args.fps, 20, 100);
    if (args.have_steady) config.steady = clamp_int(args.steady, 5, 15);
    if (args.have_limit) config.limit = (args.limit > 0) ? args.limit : 0;
    if (args.random_start) config.random_start = true;
    if (args.no_bold) config.bold = false;
    if (args.no_color) config.color = false;
    if (args.keep_style) config.keep_style = true;
    if (args.have_pipe_style) {
        config.pipe_types[0] = args.pipe_style;
        config.pipe_types_count = 1;
    }

    if (args.save_config_flag) save_config(&config);

    srand((unsigned int)time(NULL));
    signal(SIGINT, on_sigint);

    /* Save/restore the console mode & cursor visibility around the
     * animation, mirroring curses.wrapper()'s setup/teardown. */
    HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    CONSOLE_CURSOR_INFO original_cursor;
    GetConsoleCursorInfo(hOut, &original_cursor);
    CONSOLE_SCREEN_BUFFER_INFO original_csbi;
    GetConsoleScreenBufferInfo(hOut, &original_csbi);

    run_pipes(&config);

    SetConsoleTextAttribute(hOut, original_csbi.wAttributes);
    SetConsoleCursorInfo(hOut, &original_cursor);

    return 0;
}
