"""The action vocabulary: what a planner step looks like and how actions are declared."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ActionCall(BaseModel):
    """One planner step. Unknown keys are an error so drift is caught, not ignored."""

    model_config = ConfigDict(extra="forbid")

    reasoning: str = ""
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class AnswerParams(BaseModel):
    """Terminal: reply to the user."""

    text: str


class ClarifyParams(BaseModel):
    """Terminal: ask the user one question."""

    question: str


class NoParams(BaseModel):
    """For actions that take nothing."""


TERMINAL_ACTIONS: dict[str, type[BaseModel]] = {"answer": AnswerParams, "clarify": ClarifyParams}


class ActionHandler(Protocol):
    """Executes an action against the channel's context object."""

    def __call__(self, ctx: Any, params: Any) -> Any:
        """Run the action and return a JSON-serialisable result."""
        ...


class DescribeHandler(Protocol):
    """Resolves a proposed mutation into a Proposal before anything executes."""

    def __call__(self, ctx: Any, params: Any) -> "Proposal":
        """Summarise for confirmation, or resolve without a mutation."""
        ...


@dataclass(frozen=True)
class Proposal:
    """The outcome of describing a mutation before it runs.

    Exactly one field is set. `summary` asks the user to confirm; `resolved`
    means no mutation is needed after all (the ceiling guard uses this to
    turn a payment into an escalation record).
    """

    summary: str | None = None
    resolved: Any = None


@dataclass(frozen=True)
class ActionSpec:
    """A registered action: schema, handler, and whether it needs confirmation."""

    name: str
    description: str
    params: type[BaseModel]
    handler: ActionHandler
    mutation: bool = False
    describe: DescribeHandler | None = None

    def __post_init__(self) -> None:
        """A mutation without describe() could never be confirmed; reject it at import time."""
        if self.mutation and self.describe is None:
            raise ValueError(f"mutation '{self.name}' must provide describe()")


def _params_outline(model: type[BaseModel]) -> str:
    """Compact `name: type (required?) — description` lines from a model's JSON schema."""
    schema = model.model_json_schema()
    required = set(schema.get("required", []))
    lines = []
    for name, prop in schema.get("properties", {}).items():
        kind = prop.get("type") or " | ".join(o.get("type", "null") for o in prop.get("anyOf", []))
        flag = "required" if name in required else "optional"
        note = f" — {prop['description']}" if prop.get("description") else ""
        lines.append(f"    {name}: {kind} ({flag}){note}")
    return "\n".join(lines) or "    (none)"


class Registry:
    """An ordered set of actions plus the two terminals, rendered for the planner."""

    def __init__(self, specs: Iterable[ActionSpec]) -> None:
        """Index specs by name."""
        self._specs = {spec.name: spec for spec in specs}

    def get(self, name: str) -> ActionSpec | None:
        """Lookup by action name."""
        return self._specs.get(name)

    def names(self) -> list[str]:
        """Action names in declaration order."""
        return list(self._specs)

    def specs(self) -> list[ActionSpec]:
        """All specs in declaration order."""
        return list(self._specs.values())

    def prompt_catalog(self) -> str:
        """The action list as the planner sees it, terminals included."""
        blocks = [
            f"- {spec.name}: {spec.description}\n  parameters:\n{_params_outline(spec.params)}"
            for spec in self._specs.values()
        ]
        blocks.append(
            "- answer: reply to the user and stop\n"
            "  parameters:\n"
            "    text: string (required)"
        )
        blocks.append(
            "- clarify: ask the user one question and stop\n"
            "  parameters:\n"
            "    question: string (required)"
        )
        return "\n".join(blocks)
