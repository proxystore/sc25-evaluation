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
    raw: bytes

    @classmethod
    def new(cls, size: int) -> Data:
        return cls(raw=randbytes(size))

    def len(self) -> int:
        return len(self.raw)


class AcademyStateActor(Agent):
    def __init__(self, state_size: int) -> None:
        self.state = Data.new(state_size)

    @action
    async def noop(self) -> None:
        return None

    @action
    async def read(self, idx: int = 0) -> bytes:
        return self.state.raw[idx : idx + 1]


def globus_compute_init_state(state_size: int, path: str) -> None:
    basedir, _ = os.path.split(path)
    os.makedirs(basedir, exist_ok=True)
    state = Data.new(state_size)
    with open(path, 'wb') as fp:
        fp.write(state.raw)


def globus_compute_read(path: str, idx: int = 0) -> bytes:
    with open(path, 'rb') as fp:
        raw = fp.read()
    return raw[idx : idx + 1]


def globus_compute_clean_state(path: str) -> None:
    os.remove(path)
