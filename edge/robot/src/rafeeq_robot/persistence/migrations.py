from sqlalchemy import Engine, text

from rafeeq_robot.persistence.models import Base

MIGRATION_VERSION = 1


def run_migrations(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
        )
        current = connection.scalar(text("SELECT MAX(version) FROM schema_migrations")) or 0
        if current < MIGRATION_VERSION:
            Base.metadata.create_all(connection)
            connection.execute(
                text(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (:version, CURRENT_TIMESTAMP)"
                ),
                {"version": MIGRATION_VERSION},
            )
