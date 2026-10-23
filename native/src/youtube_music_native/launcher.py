"""Keep background helpers free of Qt imports, including in packaged executables."""

import sys
from pathlib import Path


if __name__ == "__main__" and not __package__:
    package_dir = Path(__file__).resolve().parent
    # Direct script execution must not shadow stdlib modules such as queue.
    sys.path[:] = [entry for entry in sys.path if Path(entry).resolve() != package_dir]
    sys.path.insert(0, str(package_dir.parent))
    __package__ = "youtube_music_native"


FLAGS = {"provider": "--provider-worker", "player": "--player-worker"}


def application_command():
    frozen = getattr(sys, "frozen", False) or hasattr(sys.modules.get("__main__"), "__compiled__")
    return [sys.executable] if frozen else [sys.executable, str(Path(__file__).resolve())]


def process_command(role):
    return [*application_command(), FLAGS[role]]


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args == [FLAGS["provider"]]:
        from .worker import main as worker_main

        return worker_main()
    if args == [FLAGS["player"]]:
        from .compat import main as player_main

        return player_main(["play"])
    from .app import main as app_main

    return app_main(args)


def compat_main():
    args = sys.argv[1:]
    if args in ([FLAGS["provider"]], [FLAGS["player"]]):
        return main(args)
    from .compat import main as check_main

    return check_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
