from __future__ import annotations

import os
import random
from typing import NamedTuple

from proxystore.proxy import extract
from proxystore.proxy import Proxy

from academy.agent import action
from academy.agent import Agent
from academy.handle import Handle


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


class Node(Agent):
    def __init__(self, peer: Handle[Node] | None) -> None:
        self.peer = peer

    @action
    async def noop(self) -> None:
        return None

    @action
    async def process(self, payload: Data) -> Data:
        if self.peer is not None:
            return await self.peer.process(payload)
        else:
            # Force the proxy to resolve if it is one
            assert payload.len() > 0
            if isinstance(payload, Proxy):
                return extract(payload)
            else:
                return payload
