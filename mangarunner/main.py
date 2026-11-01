import argparse
import os
import sys
import uvicorn

from mangarunner.config import load_config

def main():
    parser = argparse.ArgumentParser(description="Manga SMB Docker Runner & Dashboard")
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    server_parser = subparsers.add_parser("server", help="Run the FastAPI Web UI server")
    server_parser.add_argument("--host", default=None, help="Host to bind to (e.g. 0.0.0.0)")
    server_parser.add_argument("--port", type=int, default=None, help="Port to listen on (e.g. 7070)")
    server_parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    args = parser.parse_args()
    config = load_config()

    if args.subcommand == "server" or args.subcommand is None:
        host = args.host or config.server.host
        port = args.port or config.server.port
        print(f"Starting Manga SMB Suite on http://{host}:{port}")
        uvicorn.run(
            "mangarunner.api.app:app",
            host=host,
            port=port,
            reload=args.reload if hasattr(args, "reload") else False,
            log_level="info",
        )
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

