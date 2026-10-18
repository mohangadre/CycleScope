import subprocess
import sys
from datetime import date
from pathlib import Path

from cyclescope.config import Settings
from cyclescope.providers.factory import make_provider
from cyclescope.providers.synthetic import SyntheticProvider


def test_research_fixture_is_labeled_and_reproducibly_generated(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "research.csv"
    subprocess.run(
        [
            sys.executable,
            str(root / "tools/generate_research_fixtures.py"),
            "--output",
            str(output),
        ],
        check=True,
    )
    assert (
        output.read_bytes() == (root / "src/cyclescope/data/synthetic_research_v1.csv").read_bytes()
    )
    provider = make_provider(Settings(market_data_provider="synthetic_research"))
    assert isinstance(provider, SyntheticProvider)
    for symbol in ("SPY", "QQQ", "NVDA", "MU"):
        batch = provider.get_daily_bars(symbol, date(2020, 1, 2), date(2024, 12, 31))
        assert len(batch.bars) == 720
        assert batch.provider == batch.data_version == "synthetic-research-v1"
        assert batch.data_kind == "synthetic"
