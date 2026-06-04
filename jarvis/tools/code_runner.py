"""Safe Python code execution tool."""
import asyncio
import io
import logging
import os
import signal
import sys
import textwrap
import traceback
from contextlib import redirect_stdout, redirect_stderr
from typing import Optional

logger = logging.getLogger(__name__)

BLOCKED_IMPORTS = {
    "subprocess", "os.system", "socket", "ctypes",
    "importlib", "__import__", "eval", "exec"
}


def _is_safe(code: str) -> tuple[bool, str]:
    """Basic safety check for code."""
    dangerous = [
        "import subprocess", "import socket", "import ctypes",
        "os.system(", "os.popen(", "shutil.rmtree", "__import__",
        "open('/etc", "open('/sys", "open('/proc",
        "requests.post", "requests.get",  # allow with flag
    ]
    for d in dangerous:
        if d in code:
            return False, f"Blockierter Code erkannt: '{d}'"
    return True, ""


async def run_python(code: str, timeout: int = 30) -> str:
    """Execute Python code in a sandboxed environment."""
    safe, reason = _is_safe(code)
    if not safe:
        return f"Sicherheitsfehler: {reason}"

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    # Allowed builtins
    safe_globals = {
        "__builtins__": {
            "print": print,
            "len": len, "range": range, "enumerate": enumerate,
            "zip": zip, "map": map, "filter": filter,
            "sorted": sorted, "reversed": reversed,
            "list": list, "dict": dict, "set": set, "tuple": tuple,
            "str": str, "int": int, "float": float, "bool": bool,
            "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
            "isinstance": isinstance, "type": type, "hasattr": hasattr,
            "getattr": getattr, "setattr": setattr,
            "True": True, "False": False, "None": None,
            "__name__": "__main__",
        }
    }

    # Add safe imports
    import math, random, datetime, json, re, collections, itertools, functools
    safe_globals["math"] = math
    safe_globals["random"] = random
    safe_globals["datetime"] = datetime
    safe_globals["json"] = json
    safe_globals["re"] = re
    safe_globals["collections"] = collections
    safe_globals["itertools"] = itertools
    safe_globals["functools"] = functools

    # Allow numpy/pandas if available
    try:
        import numpy as np
        safe_globals["np"] = np
        safe_globals["numpy"] = np
    except ImportError:
        pass
    try:
        import pandas as pd
        safe_globals["pd"] = pd
        safe_globals["pandas"] = pd
    except ImportError:
        pass

    output_lines = []

    def safe_print(*args, **kwargs):
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        output_lines.append(sep.join(str(a) for a in args))

    safe_globals["__builtins__"]["print"] = safe_print

    try:
        compiled = compile(textwrap.dedent(code), "<jarvis>", "exec")
        local_vars = {}

        def execute():
            exec(compiled, safe_globals, local_vars)

        # Run with timeout
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, execute),
            timeout=timeout
        )

        # Capture last expression value if any
        result_parts = output_lines.copy()

        # Show last variable if it's a meaningful result
        meaningful_vars = {
            k: v for k, v in local_vars.items()
            if not k.startswith("_") and not callable(v)
        }
        if meaningful_vars and not output_lines:
            for k, v in list(meaningful_vars.items())[-3:]:
                result_parts.append(f"{k} = {repr(v)}")

        if not result_parts:
            return "Code ausgeführt (kein Output)."
        return "\n".join(result_parts)

    except asyncio.TimeoutError:
        return f"Zeitüberschreitung nach {timeout}s."
    except SyntaxError as e:
        return f"Syntaxfehler: {e}"
    except Exception as e:
        tb = traceback.format_exc()
        short_tb = "\n".join(tb.splitlines()[-5:])
        return f"Fehler: {type(e).__name__}: {e}\n{short_tb}"


def format_code_result(code: str, result: str) -> str:
    return f"```python\n{code}\n```\n**Output:**\n```\n{result}\n```"
