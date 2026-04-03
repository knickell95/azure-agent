from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any


@dataclass
class Tool:
    """Wraps an Azure operation as an Anthropic tool definition + callable."""

    name: str
    description: str
    input_schema: dict
    func: Callable[..., str]
    # Mark operations that delete or irreversibly change resources.
    # The agent confirms with the user before executing these.
    destructive: bool = False

    @property
    def definition(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def execute(self, **kwargs: Any) -> str:
        try:
            return self.func(**kwargs)
        except Exception as exc:
            return f"[Azure error] {type(exc).__name__}: {exc}"
