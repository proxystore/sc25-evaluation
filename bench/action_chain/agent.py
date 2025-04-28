from __future__ import annotations

import os
import random
from typing import NamedTuple

from academy.behavior import action
from academy.behavior import Behavior
from academy.handle import Handle
from proxystore.proxy import extract
from proxystore.proxy import Proxy


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


class Node(Behavior):
    def __init__(self, peer: Handle[Node] | None) -> None:
        self.peer = peer

    @action
    def noop(self) -> None:
        return None

    @action
    def process(self, payload: Data) -> Data:
        if self.peer is not None:
            return self.peer.action('process', payload).result()
        else:
            # Force the proxy to resolve if it is one
            assert payload.len() > 0
            if isinstance(payload, Proxy):
                return extract(payload)
            else:
                return payload
