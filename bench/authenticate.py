from __future__ import annotations

import argparse
import asyncio

from academy.exchange import HttpExchangeFactory


async def main(url: str) -> None:
    async with await HttpExchangeFactory(
        url=url,
        auth_method='globus',
    ).create_user_client():
        print('Successfully authenticated and stored authentication token.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '--url',
        default='https://exchange.academy-agents.org',
        help='Exchange url',
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.url)))
