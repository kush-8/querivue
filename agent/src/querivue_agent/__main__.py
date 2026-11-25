"""Package entry point for querivue-agent CLI."""

from .cli import main

if __name__ == "__main__":
    import asyncio
    import sys
    sys.exit(asyncio.run(main()))