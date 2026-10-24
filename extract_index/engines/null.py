"""The null engine: every field `null`. A floor for the board and a smoke test for the kit."""

from __future__ import annotations

from . import Engine


class NullEngine(Engine):
    name = "null"

    def __call__(self, request: dict) -> dict:
        return {"answers": {name: {"type": spec["type"], "value": None, "p_null": 1.0}
                            for name, spec in request["fields"].items()}}

    def info(self) -> dict:
        return {"name": self.name, "description": "answers null for every field"}
