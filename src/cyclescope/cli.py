import argparse
import json
import sys
from datetime import date

from sqlalchemy.exc import SQLAlchemyError

from cyclescope.config import Settings
from cyclescope.domain.errors import CycleScopeError
from cyclescope.domain.models import CATALOG, CORE_CATALOG, SECTOR_CATALOG, DateRange
from cyclescope.providers.factory import make_provider
from cyclescope.services.ingestion import ingest
from cyclescope.storage.database import make_engine


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CycleScope explicit, atomic market-data ingestion"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    loader = commands.add_parser("ingest")
    loader.add_argument("--symbol", choices=[item.symbol for item in CATALOG], action="append")
    loader.add_argument("--universe", choices=("core", "sectors", "all"), default="core")
    loader.add_argument("--start", type=date.fromisoformat, required=True)
    loader.add_argument("--end", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    engine = None
    try:
        settings = Settings()
        period = DateRange(start=args.start, end=args.end)
        provider = make_provider(settings)
        engine = make_engine(settings.database_url.get_secret_value())
        universe = {
            "core": CORE_CATALOG,
            "sectors": (CORE_CATALOG[0], *SECTOR_CATALOG),
            "all": CATALOG,
        }
        for symbol in args.symbol or [item.symbol for item in universe[args.universe]]:
            run_id = ingest(engine, provider, symbol, period)
            print(
                json.dumps(
                    {"symbol": symbol, "run_id": str(run_id), "data_kind": provider.data_kind}
                )
            )
    except CycleScopeError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": str(exc)}}), file=sys.stderr)
        sys.exit(1)
    except SQLAlchemyError:
        print("Database unavailable; configure DATABASE_URL and run migrations", file=sys.stderr)
        sys.exit(1)
    except ValueError:
        print("Invalid configuration or date range", file=sys.stderr)
        sys.exit(1)
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
