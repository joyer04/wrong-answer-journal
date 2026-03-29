"""
tests/test_diagram_service.py
==============================
Tests for server-side diagram generation in services/diagram_service.py.
No mocking needed — sympy + matplotlib are available.
"""

import base64
import pytest
from services.diagram_service import generate_diagram_base64


def _is_valid_png_b64(b64_str: str) -> bool:
    """Check that decoded bytes start with PNG magic bytes."""
    data = base64.b64decode(b64_str)
    return data[:8] == b'\x89PNG\r\n\x1a\n'


class TestFunctionGraph:
    def test_simple_line(self):
        spec = {
            "type": "function_graph",
            "title": "y = x",
            "functions": [{"expr": "x", "label": "f(x)=x", "color": "#2563eb"}],
            "x_range": [-3, 3],
        }
        result = generate_diagram_base64(spec)
        assert isinstance(result, str)
        assert _is_valid_png_b64(result)

    def test_quadratic(self):
        spec = {
            "type": "function_graph",
            "functions": [{"expr": "x**2 - 4", "label": "f(x)=x\u00b2-4", "color": "#dc2626"}],
            "x_range": [-4, 4],
            "y_range": [-5, 5],
            "points": [{"x": 2, "y": 0, "label": "(2,0)"}],
        }
        result = generate_diagram_base64(spec)
        assert _is_valid_png_b64(result)

    def test_multiple_functions(self):
        spec = {
            "type": "function_graph",
            "functions": [
                {"expr": "x", "label": "y=x"},
                {"expr": "x**2", "label": "y=x\u00b2"},
            ],
            "x_range": [-3, 3],
        }
        result = generate_diagram_base64(spec)
        assert _is_valid_png_b64(result)

    def test_trig_function(self):
        spec = {
            "type": "function_graph",
            "functions": [{"expr": "sin(x)", "label": "sin(x)"}],
            "x_range": [-6.28, 6.28],
        }
        result = generate_diagram_base64(spec)
        assert _is_valid_png_b64(result)

    def test_malicious_expr_rejected(self):
        """Sympy should safely refuse arbitrary Python code."""
        spec = {
            "type": "function_graph",
            "functions": [{"expr": "__import__('os').system('id')", "label": "bad"}],
            "x_range": [-1, 1],
        }
        # Should not raise — the expression either fails to plot (logged)
        # or sympy rejects it. Either way, no exception propagates.
        # The function returns a valid PNG of a blank/minimal graph.
        result = generate_diagram_base64(spec)
        assert isinstance(result, str)  # still returns a figure


class TestTriangle:
    def test_basic_triangle(self):
        spec = {
            "type": "triangle",
            "vertices": {"A": [0, 0], "B": [4, 0], "C": [2, 3]},
            "labels": {"AB": "4"},
        }
        result = generate_diagram_base64(spec)
        assert _is_valid_png_b64(result)

    def test_right_triangle(self):
        spec = {
            "type": "triangle",
            "vertices": {"A": [0, 0], "B": [3, 0], "C": [0, 4]},
            "labels": {"AB": "3", "CA": "4", "BC": "5"},
            "right_angle_at": "A",
        }
        result = generate_diagram_base64(spec)
        assert _is_valid_png_b64(result)


class TestCircle:
    def test_basic_circle(self):
        spec = {
            "type": "circle",
            "center": [0, 0],
            "radius": 3,
            "title": "\uc6d0",
        }
        result = generate_diagram_base64(spec)
        assert _is_valid_png_b64(result)


class TestNumberLine:
    def test_basic_number_line(self):
        spec = {
            "type": "number_line",
            "range": [-3, 3],
            "points": [
                {"x": 1, "label": "1", "type": "closed"},
                {"x": -1, "label": "-1", "type": "open"},
            ],
        }
        result = generate_diagram_base64(spec)
        assert _is_valid_png_b64(result)


class TestUnknownType:
    def test_raises_for_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown diagram type"):
            generate_diagram_base64({"type": "hexagon"})
