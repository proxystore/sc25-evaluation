from __future__ import annotations

import os
import random
from typing import NamedTuple

from aeris.behavior import action
from aeris.behavior import Behavior


def randbytes(size: int) -> bytes:
    if size <= 100_000_000:  # noqa: PLR2004
        return random.randbytes(size)
    else:
        return os.urandom(size)


class Data(NamedTuple):
    index: int
    raw: list[bytes]

    @classmethod
    def new(cls, size: int) -> Data:
        raw: list[bytes] = []
        chunk_size = 10_000
        for _ in range(size // chunk_size):
            raw.append(randbytes(chunk_size))
        raw.append(randbytes(size % chunk_size))
        return cls(index=0, raw=raw)

    def len(self) -> int:
        return sum(len(r) for r in self.raw)


class ReplyAgent(Behavior):
    @action
    def noop(self) -> None:
        return None

    @action
    def process(self, payload: Data) -> Data:
        return Data(payload.index + 1, payload.raw)
