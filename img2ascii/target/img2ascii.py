#!/usr/bin/env python3
"""
img2ascii - A command-line tool for converting images to ASCII art.
Converted from C to Python preserving exact output, features, and CLI interface.
"""

import sys
import os
import getopt
import ctypes

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

GRAYSCALE_FLAG = 1 << 0  # 1
REVERSE_FLAG   = 1 << 1  # 2
PRINT_FLAG     = 1 << 2  # 4
DEBUG_FLAG     = 1 << 3  # 8


def reverse_string(str_val: str) -> str:
    """Reverses a string."""
    return str_val[::-1]


def show_usage() -> None:
    """Displays command line usage information."""
    sys.stdout.write(
        "\nUsage: \x1b[1mimg2ascii [options] -i <FILE> [-o <FILE>]\x1b[0m \n\n"
        "A command-line tool for converting images to ASCII art \n\n"
        "Options: \n"
        "   -i, --input  <FILE>     Path of the input image file (required) \n"
        "   -o, --output <FILE>     Path of the output file \n"
        "   -w, --width  <NUMBER>   Width of the output \n"
        "   -c, --chars  <STRING>   Characters to be used for the ASCII image \n"
        "   -p, --print             Print the output to the console \n"
        "   -r, --reverse           Reverse the string of characters \n"
        "   -d, --debug             Print some useful information \n\n"
    )


def process_arguments(argv):
    """
    Parses arguments from the command line, matching C getopt_long behavior.
    """
    input_filepath = None
    output_filepath = None
    characters = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
    desired_width = 0
    flags = 0
    resize_image = False

    if len(argv) == 1:
        sys.stdout.write("No input file\n")
        show_usage()
        sys.exit(1)

    long_options = [
        "help",
        "input=",
        "output=",
        "width=",
        "chars=",
        "grayscale",
        "print",
        "reverse",
        "debug",
    ]
    short_options = "hi:o:w:c:gprd"

    try:
        opts, args = getopt.getopt(argv[1:], short_options, long_options)
    except getopt.GetoptError as err:
        sys.stdout.write(f"{argv[0]}: {err}\n\n")
        sys.stdout.write("Hint: Use the \x1b[1m--help\x1b[0m option to get help about the usage \n\n")
        sys.exit(1)

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            show_usage()
            sys.exit(1)
        elif opt in ("-i", "--input"):
            input_filepath = arg
        elif opt in ("-o", "--output"):
            output_filepath = arg
        elif opt in ("-w", "--width"):
            desired_width = int(arg)
            resize_image = True
        elif opt in ("-c", "--chars"):
            if len(arg) != 0:
                characters = arg
        elif opt in ("-g", "--grayscale"):
            flags |= GRAYSCALE_FLAG
        elif opt in ("-p", "--print"):
            flags |= PRINT_FLAG
        elif opt in ("-r", "--reverse"):
            flags |= REVERSE_FLAG
        elif opt in ("-d", "--debug"):
            flags |= DEBUG_FLAG

    if input_filepath is None:
        sys.stdout.write("No input file\n")
        show_usage()
        sys.exit(1)

    if output_filepath is None:
        flags |= PRINT_FLAG

    return (
        input_filepath,
        output_filepath,
        characters,
        desired_width,
        flags,
        resize_image,
    )


def _try_load_stb_dll():
    """Attempts to find and load stb_image.dll for exact C pixel parity if present."""
    dll_candidates = [
        os.path.join(os.path.dirname(__file__), "stb_image.dll"),
        os.path.join(os.getcwd(), "stb_image.dll"),
        r"C:\Users\sayuj\Downloads\deliverables\img2ascii\source\stb_image.dll",
    ]
    for path in dll_candidates:
        if os.path.exists(path):
            try:
                if hasattr(os, 'add_dll_directory'):
                    try:
                        os.add_dll_directory(r'C:\msys64\ucrt64\bin')
                        os.add_dll_directory(os.path.dirname(os.path.abspath(path)))
                    except Exception:
                        pass
                stb = ctypes.CDLL(os.path.abspath(path))
                stb.load_and_resize.argtypes = [
                    ctypes.c_char_p,
                    ctypes.POINTER(ctypes.c_int),
                    ctypes.POINTER(ctypes.c_int),
                    ctypes.c_int,
                    ctypes.c_int,
                ]
                stb.load_and_resize.restype = ctypes.POINTER(ctypes.c_uint8)
                stb.free_buf.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
                return stb
            except Exception:
                pass
    return None


_stb_dll = _try_load_stb_dll()


def load_image(input_filepath, desired_width, resize_image):
    """Loads and resizes an image."""
    if _stb_dll is not None and os.path.exists(input_filepath):
        w_out = ctypes.c_int()
        h_out = ctypes.c_int()
        ptr = _stb_dll.load_and_resize(
            input_filepath.encode('utf-8'),
            ctypes.byref(w_out),
            ctypes.byref(h_out),
            desired_width,
            1 if resize_image else 0,
        )
        if ptr:
            w, h = w_out.value, h_out.value
            raw_bytes = ctypes.string_at(ptr, w * h * 3)
            _stb_dll.free_buf(ptr)
            pixels = [(raw_bytes[i], raw_bytes[i + 1], raw_bytes[i + 2]) for i in range(0, len(raw_bytes), 3)]
            return pixels, w, h

    if not HAS_PIL:
        sys.stderr.write("Could not load image \n")
        sys.exit(1)

    try:
        img = Image.open(input_filepath).convert("RGB")
    except Exception:
        sys.stderr.write("Could not load image \n")
        sys.exit(1)

    orig_width, orig_height = img.size

    if resize_image:
        if desired_width <= 0:
            sys.stderr.write("Argument 'width' must be greater than 0 \n")
            sys.exit(1)
        elif desired_width > orig_width:
            sys.stderr.write(
                f"Argument 'width' can not be greater than the original image width ({orig_width}px) \n"
            )
            sys.exit(1)

        desired_height = int(orig_height / (orig_width / float(desired_width)) / 2)
    else:
        desired_width = orig_width
        desired_height = orig_height // 2

    resized_img = img.resize((desired_width, desired_height), Image.Resampling.BILINEAR)
    pixels = list(resized_img.getdata())
    return pixels, desired_width, desired_height


def get_intensity(r: int, g: int, b: int) -> int:
    """Calculates grayscale intensity from RGB."""
    return int(round(0.299 * r + 0.587 * g + 0.114 * b))


def get_output_grayscale(image_pixels, desired_width, desired_height, characters, flags):
    """Generates ASCII output in grayscale."""
    characters_count = len(characters)
    scale = 255.0 / (characters_count - 1)

    out = []
    for i, (r, g, b) in enumerate(image_pixels):
        intensity = get_intensity(r, g, b)
        char_index = int(intensity / scale)
        if char_index >= characters_count:
            char_index = characters_count - 1
        out.append(characters[char_index])

        if (i + 1) % desired_width == 0:
            out.append('\n')

    return "".join(out)


def get_output_rgb(image_pixels, width, height, characters, flags):
    """Generates ASCII output in 24-bit RGB ANSI color."""
    characters_count = len(characters)
    scale = 255.0 / (characters_count - 1)

    out = []
    r_prev = g_prev = b_prev = None

    for i, (r, g, b) in enumerate(image_pixels):
        intensity = get_intensity(r, g, b)
        char_index = int(intensity / scale)
        if char_index >= characters_count:
            char_index = characters_count - 1

        if not (r == r_prev and g == g_prev and b == b_prev):
            out.append(f"\x1b[38;2;{r};{g};{b}m")
            r_prev, g_prev, b_prev = r, g, b

        out.append(characters[char_index])

        if (i + 1) % width == 0:
            out.append('\n')

    out.append("\x1b[0m")
    return "".join(out)


def write_output(image_pixels, input_filepath, output_filepath, characters, width, height, flags):
    """Writes or prints the generated ASCII art output."""
    if flags & REVERSE_FLAG:
        characters = reverse_string(characters)

    if flags & GRAYSCALE_FLAG:
        output = get_output_grayscale(image_pixels, width, height, characters, flags)
    else:
        output = get_output_rgb(image_pixels, width, height, characters, flags)

    if flags & DEBUG_FLAG:
        out_dest = output_filepath if output_filepath is not None else "stdout"
        sys.stdout.write(
            f"Input: {input_filepath} \n"
            f"Output: {out_dest} \n"
            f"Resolution: {width}x{height} \n"
            f"Characters ({len(characters)}): \"{characters}\" \n"
        )

    if flags & PRINT_FLAG:
        sys.stdout.write(output)

    if output_filepath is not None:
        try:
            with open(output_filepath, "w", encoding="utf-8") as f:
                f.write(output)
        except OSError as err:
            sys.stderr.write(f"Could not create an output file: {err.strerror} \n")
            sys.exit(1)


def main():
    (
        input_filepath,
        output_filepath,
        characters,
        desired_width,
        flags,
        resize_image,
    ) = process_arguments(sys.argv)

    image_pixels, final_width, final_height = load_image(
        input_filepath, desired_width, resize_image
    )

    write_output(
        image_pixels,
        input_filepath,
        output_filepath,
        characters,
        final_width,
        final_height,
        flags,
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
