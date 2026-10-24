import sys

TTY = sys.stdout.isatty()


def c(code, s):
    return f"\033[{code}m{s}\033[0m" if TTY else s


dim = lambda s: c("2", s)
bold = lambda s: c("1", s)
green = lambda s: c("32", s)
yellow = lambda s: c("33", s)
red = lambda s: c("31", s)
cyan = lambda s: c("36", s)


def die(msg):
    """Exit with msg, named for the bin that runs."""
    import os
    print(f"{os.path.basename(sys.argv[0])}: {msg}", file=sys.stderr)
    sys.exit(1)
