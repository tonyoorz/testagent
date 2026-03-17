import argparse
import os


def parse_args():
    parser = argparse.ArgumentParser(description="Run Defect Explore with Waitress")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"), help="Bind host")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8051")), help="Bind port")
    parser.add_argument(
        "--threads",
        type=int,
        default=int(os.environ.get("WAITRESS_THREADS", "8")),
        help="Waitress worker threads",
    )
    parser.add_argument(
        "--connection-limit",
        type=int,
        default=int(os.environ.get("WAITRESS_CONNECTION_LIMIT", "100")),
        help="Maximum active client connections",
    )
    parser.add_argument(
        "--channel-timeout",
        type=int,
        default=int(os.environ.get("WAITRESS_CHANNEL_TIMEOUT", "120")),
        help="Idle connection timeout in seconds",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    os.environ.setdefault("DEBUG", "False")
    os.environ.setdefault("DISABLE_RELOADER", "1")
    os.environ.setdefault("HOST", args.host)
    os.environ.setdefault("PORT", str(args.port))
    os.environ.setdefault("DEFECT_EXPLORE_FAST_START", "1")

    try:
        from waitress import serve
    except ImportError as exc:
        raise SystemExit(
            "Waitress is not installed. Run 'python -m pip install waitress' or install from requirements.txt."
        ) from exc

    from defect_explore import server

    print("=" * 50)
    print("Starting Defect Explore with Waitress")
    print("=" * 50)
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Threads: {args.threads}")
    print(f"Connection limit: {args.connection_limit}")
    print(f"Channel timeout: {args.channel_timeout}s")
    print(f"Fast start: {os.environ.get('DEFECT_EXPLORE_FAST_START', '1')}")
    print("=" * 50)

    serve(
        server,
        host=args.host,
        port=args.port,
        threads=args.threads,
        connection_limit=args.connection_limit,
        channel_timeout=args.channel_timeout,
    )


if __name__ == "__main__":
    main()