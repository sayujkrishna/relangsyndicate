import argparse
import sys
import qrcode

def get_level(s: str):
    """Map string error correction level to qrcode constant."""
    l = s.lower()
    if l == "l":
        return qrcode.constants.ERROR_CORRECT_L
    elif l == "m":
        return qrcode.constants.ERROR_CORRECT_M
    elif l == "h":
        return qrcode.constants.ERROR_CORRECT_H
    else:
        return None

def main():
    parser = argparse.ArgumentParser(description="Output QR code in terminal")
    parser.add_argument("-v", action="store_true", help="Output debugging information")
    parser.add_argument("-l", default="L", help="Error correction level [L, M, H]")
    parser.add_argument("-q", type=int, default=2, help="Size of quietzone border")
    parser.add_argument("-s", action="store_true", help="disable sixel format for output")
    parser.add_argument("args", nargs="*", help="Data to encode into QR code")

    args = parser.parse_args()

    level = get_level(args.l)
    content = " ".join(args.args)

    if not content:
        # Get input from stdin until EOF if no positional args provided
        content = sys.stdin.read()

    if level is None:
        sys.stderr.write(f"Invalid error correction level: {args.l}\n")
        sys.stderr.write("Valid options are [L, M, H]\n")
        sys.exit(1)

    if args.v:
        sys.stdout.write(f"Level: {args.l} \n")
        sys.stdout.write(f"Quietzone Border Size: {args.q} \n")
        sys.stdout.write(f"Encoded data: {'\n'.join(args.args)} \n")
        sys.stdout.write("\n")

    sys.stdout.write("\n")
    sys.stdout.flush()

    # Configure and generate QR code
    qr = qrcode.QRCode(
        version=None,
        error_correction=level,
        box_size=1,
        border=args.q,
    )
    qr.add_data(content)
    qr.make(fit=True)

    # Render terminal ascii/block QR code
    qr.print_ascii(out=sys.stdout, tty=True)

if __name__ == "__main__":
    main()
