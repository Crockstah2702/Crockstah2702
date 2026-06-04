"""Advanced calculator with symbolic math support."""
import logging
import re

logger = logging.getLogger(__name__)


def calculate(expression: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        import sympy
        from sympy import (
            symbols, solve, diff, integrate, simplify, expand,
            factor, sqrt, pi, E, I, oo, latex, N
        )
        from sympy.parsing.sympy_parser import (
            parse_expr, standard_transformations, implicit_multiplication_application
        )

        transformations = standard_transformations + (implicit_multiplication_application,)

        # Check if it's an equation to solve
        if "=" in expression and "==" not in expression:
            lhs, rhs = expression.split("=", 1)
            x = symbols("x")
            try:
                expr = parse_expr(f"({lhs.strip()}) - ({rhs.strip()})",
                                   transformations=transformations,
                                   local_dict={"x": x})
                solutions = solve(expr, x)
                if solutions:
                    sol_str = ", ".join(str(s) for s in solutions)
                    return f"Lösung: x = {sol_str}"
                return "Keine Lösung gefunden."
            except Exception:
                pass

        # Handle derivative
        if "d/dx" in expression.lower() or "ableitung" in expression.lower():
            expr_str = re.sub(r"d/dx|ableitung von", "", expression, flags=re.IGNORECASE).strip()
            x = symbols("x")
            expr = parse_expr(expr_str, transformations=transformations, local_dict={"x": x})
            result = diff(expr, x)
            return f"Ableitung: {result} = {simplify(result)}"

        # Handle integral
        if "integral" in expression.lower() or "∫" in expression:
            expr_str = re.sub(r"integral|∫", "", expression, flags=re.IGNORECASE).strip()
            x = symbols("x")
            expr = parse_expr(expr_str, transformations=transformations, local_dict={"x": x})
            result = integrate(expr, x)
            return f"Integral: {result} + C"

        # Regular evaluation
        x, y, z = symbols("x y z")
        expr = parse_expr(expression, transformations=transformations,
                          local_dict={"x": x, "y": y, "z": z, "pi": pi, "e": E})

        simplified = simplify(expr)
        numeric = N(simplified)

        # Check if numeric is close to an integer
        try:
            if abs(numeric - round(float(numeric))) < 1e-10:
                return f"{float(numeric):.0f}"
            return f"{simplified} ≈ {float(numeric):.6g}"
        except Exception:
            return str(simplified)

    except ImportError:
        # Fallback to basic eval
        return _safe_eval(expression)
    except Exception as e:
        return _safe_eval(expression)


def _safe_eval(expression: str) -> str:
    """Fallback calculator using safe eval."""
    import math
    safe_dict = {
        k: v for k, v in math.__dict__.items() if not k.startswith("_")
    }
    safe_dict.update({"abs": abs, "round": round, "pow": pow})
    try:
        result = eval(expression, {"__builtins__": {}}, safe_dict)
        return str(result)
    except Exception as e:
        return f"Berechnungsfehler: {e}"


def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common units."""
    conversions = {
        # Length
        ("km", "m"): 1000, ("m", "km"): 0.001,
        ("m", "cm"): 100, ("cm", "m"): 0.01,
        ("m", "ft"): 3.28084, ("ft", "m"): 0.3048,
        ("km", "miles"): 0.621371, ("miles", "km"): 1.60934,
        ("inch", "cm"): 2.54, ("cm", "inch"): 0.393701,
        # Weight
        ("kg", "g"): 1000, ("g", "kg"): 0.001,
        ("kg", "lbs"): 2.20462, ("lbs", "kg"): 0.453592,
        # Temperature handled separately
        # Speed
        ("kmh", "ms"): 1/3.6, ("ms", "kmh"): 3.6,
        ("kmh", "mph"): 0.621371, ("mph", "kmh"): 1.60934,
    }

    # Temperature conversions
    from_unit = from_unit.lower().strip()
    to_unit = to_unit.lower().strip()

    if from_unit in ["°c", "celsius", "c"] and to_unit in ["°f", "fahrenheit", "f"]:
        return f"{value}°C = {value * 9/5 + 32:.2f}°F"
    if from_unit in ["°f", "fahrenheit", "f"] and to_unit in ["°c", "celsius", "c"]:
        return f"{value}°F = {(value - 32) * 5/9:.2f}°C"
    if from_unit in ["°c", "celsius", "c"] and to_unit in ["k", "kelvin"]:
        return f"{value}°C = {value + 273.15:.2f}K"

    factor = conversions.get((from_unit, to_unit))
    if factor:
        result = value * factor
        return f"{value} {from_unit} = {result:.4g} {to_unit}"
    return f"Unbekannte Einheiten: {from_unit} → {to_unit}"
