"""Central tool registry for Jarvis."""
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Tool:
    name: str
    description: str
    func: Callable
    parameters: dict = field(default_factory=dict)
    requires_confirmation: bool = False


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters
            }
            for t in self._tools.values()
        ]

    def tool_list_for_prompt(self) -> str:
        lines = []
        for t in self._tools.values():
            params = ", ".join(f"{k}: {v}" for k, v in t.parameters.items())
            lines.append(f"- {t.name}({params}): {t.description}")
        return "\n".join(lines)

    async def execute(self, name: str, **kwargs) -> Any:
        tool = self._tools.get(name)
        if not tool:
            return f"Unbekanntes Tool: {name}"
        try:
            import asyncio
            if asyncio.iscoroutinefunction(tool.func):
                return await tool.func(**kwargs)
            else:
                return tool.func(**kwargs)
        except Exception as e:
            return f"Tool-Fehler [{name}]: {e}"
