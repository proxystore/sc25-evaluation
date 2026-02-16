from __future__ import annotations

import os
import random
from typing import NamedTuple

from academy.agent import action
from academy.agent import Agent


def randbytes(size: int) -> bytes:
    if size <= 100_000_000:  # noqa: PLR2004
        return random.randbytes(size)
    else:
        return os.urandom(size)


class Data(NamedTuple):
    msg_index: int
    raw: list[bytes]

    @classmethod
    def new(cls, size: int) -> Data:
        raw: list[bytes] = []
        chunk_size = 10_000
        for _ in range(size // chunk_size):
            raw.append(randbytes(chunk_size))
        raw.append(randbytes(size % chunk_size))
        return cls(msg_index=0, raw=raw)

    def len(self) -> int:
        return sum(len(r) for r in self.raw)


class ReplyAgent(Agent):
    @action
    async def noop(self) -> str:
        return 'None'

    @action
    async def process(self, payload: Data) -> Data:
        return Data(payload.msg_index + 1, payload.raw)
