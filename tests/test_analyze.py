import json
from dataclasses import asdict
from pathlib import Path

import pytest

from lib import analyze


def get_prefixes() -> list[str]:
    """Discover available test prefixes from testdata directory."""
    return sorted(
        p.stem.removesuffix("_analyze_input")
        for p in Path("testdata").glob("*analyze_input.html")
    )


@pytest.mark.parametrize("prefix", get_prefixes())
def test_e2e(prefix: str) -> None:
    print(f"THROMER {prefix=}")
    data = Path(f"testdata/{prefix}_analyze_input.html").read_text()
    expected_text = Path(f"testdata/{prefix}_analyze_e2e_expected.txt").read_text()
    expected = expected_text.splitlines()
    actual = analyze.analyze(data)
    assert actual == expected


@pytest.mark.parametrize("prefix", get_prefixes())
def test_process_data(prefix: str) -> None:
    data = Path(f"testdata/{prefix}_analyze_input.html").read_text()
    with Path(f"testdata/{prefix}_analyze_process_expected.json").open("r") as f:
        expected = json.load(f)  # pyright: ignore[reportAny]
    actual_data = analyze.process_data(data)
    actual = asdict(actual_data)
    # with Path(f"testdata/{prefix}_analyze_process_actual.json").open("w") as f:
    #    json.dump(actual, f)
    assert actual == expected
