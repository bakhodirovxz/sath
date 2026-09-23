"""SIM-02: maxsus formula — ro'yxat, butun son, daraja va pow() chegaralari."""

import pytest
from ges_sim import custom


def _ev(src: str, **env):
    return custom.evaluate(custom.compile_expr(src), dict(env))


def _tpl(expr: str, steps: int = 1, outputs=("x",)) -> dict:
    return {"steps": steps, "step": [{"target": "x", "expr": expr}], "outputs": list(outputs)}


@pytest.mark.parametrize(
    "src",
    [
        "[0] * 10**9",
        "10**9 * [0]",
        "[0] * 1000001",
        "[1, 2] * 600000",
        "pow(2, 10**9)",
        "pow(10, 5000)",
        "pow(3, 1001)",
        "2 ** 1001",
        "10 ** 1000 * 10 ** 1000 * 10 ** 1000",
        "round(5, -10**9)",
        "sum([[0] * 1000] * 1000, [])",
    ],
)
def test_resource_bombs_rejected(src):
    with pytest.raises(ValueError):
        _ev(src)


def test_repeated_squaring_capped():
    t = {
        "steps": 50,
        "init": {"x": "10**100"},
        "step": [{"target": "x", "expr": "x * x"}],
        "outputs": [],
    }
    with pytest.raises(ValueError, match="katta"):
        custom.run(t, {})


def test_list_doubling_capped():
    t = {"steps": 40, "init": {"x": "[0]"}, "step": [{"target": "x", "expr": "x + x"}], "outputs": []}
    with pytest.raises(ValueError, match="Ro'yxat"):
        custom.run(t, {})


def test_series_cells_capped():
    with pytest.raises(ValueError, match="Natija juda katta"):
        custom.run(_tpl("[i] * 1000000", steps=10), {})


def test_normal_expressions_still_work():
    assert _ev("pow(2, 10)") == 1024
    assert _ev("pow(2.0, 0.5)") == pytest.approx(2**0.5)
    assert _ev("pow(3, 4, 5)") == 1
    assert _ev("round(3.14159, 2)") == 3.14
    assert _ev("round(2.6)") == 3
    assert _ev("sum([1, 2, 3])") == 6 and _ev("sum([1, 2], 10)") == 13
    assert _ev("len([0] * 1000)") == 1000
    assert _ev("10 ** 300") == 10**300
    out = custom.run(custom.example_template(), {})
    assert out["summary"]["H_max"] >= 900
