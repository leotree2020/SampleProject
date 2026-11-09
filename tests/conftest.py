import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marketcast.data import generate_synthetic  # noqa: E402


@pytest.fixture(scope="session")
def stock_df():
    return generate_synthetic(n=900, seed=7)


@pytest.fixture(scope="session")
def fx_df():
    return generate_synthetic(n=900, seed=11, asset_type="forex")
