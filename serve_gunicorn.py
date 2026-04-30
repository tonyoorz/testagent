"""
Production server entry point.

Usage:
    # Default (4 workers)
    python serve_gunicorn.py

    # Custom
    GUNICORN_WORKERS=8 python serve_gunicorn.py --port 8051

    # With Redis
    REDIS_URL=redis://localhost:6379/0 python serve_gunicorn.py
"""
import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="Run DTSV with Gunicorn")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8051")))
    parser.add_argument("--workers", type=int, default=int(os.environ.get("GUNICORN_WORKERS", "4")))
    args = parser.parse_args()

    os.environ.setdefault("DISABLE_RELOADER", "1")
    os.environ.setdefault("HOST", args.host)
    os.environ.setdefault("PORT", str(args.port))
    os.environ.setdefault("DEFECT_EXPLORE_FAST_START", "1")

    try:
        from gunicorn.app.base import BaseApplication
    except ImportError:
        print("❌ gunicorn not installed. Run: pip install gunicorn")
        sys.exit(1)

    from defect_explore import server

    class StandaloneApplication(BaseApplication):
        def __init__(self, app, options=None):
            self.options = options or {}
            self.application = app
            super().__init__()

        def load_config(self):
            config = {
                key: value for key, value in self.options.items()
                if key in self.cfg.settings and value is not None
            }
            for key, value in config.items():
                self.cfg.set(key.lower(), value)

        def load(self):
            return self.application

    options = {
        "bind": f"{args.host}:{args.port}",
        "workers": args.workers,
        "threads": 2,
        "timeout": 120,
        "worker_class": "gthread",
        "accesslog": "-",
        "errorlog": "-",
        "loglevel": "info",
        "max_requests": 1000,
        "max_requests_jitter": 50,
    }

    print("=" * 50)
    print(f"🚀 Starting DTSV with Gunicorn")
    print(f"   Host: {args.host}:{args.port}")
    print(f"   Workers: {args.workers}")
    print(f"   Redis: {os.environ.get('REDIS_URL', 'not configured')}")
    print("=" * 50)

    StandaloneApplication(server, options).run()


if __name__ == "__main__":
    main()
