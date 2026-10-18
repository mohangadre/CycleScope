from alembic import context
from cyclescope.config import Settings
from cyclescope.storage.database import make_engine
from cyclescope.storage.models import Base

target_metadata = Base.metadata


def run_migrations() -> None:
    engine = make_engine(Settings().database_url.get_secret_value())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations()
