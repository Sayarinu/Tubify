"""Keep background helpers free of Qt imports, including in packaged executables."""

import sys


FLAGS = {"provider": "--provider-worker", "player": "--player-worker"}


def process_command(role):
    frozen = getattr(sys, "frozen", False) or hasattr(sys.modules.get("__main__"), "__compiled__")
    prefix = [sys.executable] if frozen else [sys.executable, "-m", "youtube_music_native"]
    return [*prefix, FLAGS[role]]


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
