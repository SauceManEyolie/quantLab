#!/usr/bin/env python3
"""
QuantLab — start here.

    python3 run.py              normal: live market data
    python3 run.py --demo       offline: fabricated data, for trying the UI
    python3 run.py --port 9000  different port
    python3 run.py --test       run the test suite and exit
"""

import argparse
import os
import shutil
import sys
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description="QuantLab — free crypto backtesting")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--demo", action="store_true", help="use fabricated data (works offline)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--test", action="store_true", help="run the test suite and exit")
    args = ap.parse_args()

    if args.test:
        here = os.path.dirname(os.path.abspath(__file__))
        rc = os.system(f'"{sys.executable}" "{os.path.join(here, "tests", "test_all.py")}"') >> 8
        # The glossary tests need node; skip cleanly rather than failing if it
        # isn't installed, since it's a frontend-only concern.
        if shutil.which("node"):
            rc |= os.system(f'node "{os.path.join(here, "tests", "test_glossary.js")}"') >> 8
        else:
            print("  (node not found — skipping frontend glossary tests)\n")
        sys.exit(rc)

    try:
        import numpy, pandas  # noqa: F401
    except ImportError:
        print("\n  Missing dependencies. Run:\n\n      pip3 install pandas numpy\n")
        sys.exit(1)

    if args.demo:
        os.environ["QUANTLAB_DEMO"] = "1"
        print("\n  *** DEMO MODE — prices are fabricated. Do not trade off these numbers. ***")

    import server
    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    server.serve(args.host, args.port)


if __name__ == "__main__":
    main()
