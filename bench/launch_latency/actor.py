from __future__ import annotations

from aeris.behavior import action
from aeris.behavior import Behavior


class AerisActor(Behavior):
    @action
    def noop(self) -> None:
        return None
