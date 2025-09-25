from __future__ import annotations

import asyncio

from bench.remote_invocation.run import main

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
