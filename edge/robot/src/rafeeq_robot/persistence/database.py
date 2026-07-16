from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from rafeeq_robot.persistence.migrations import run_migrations


class RobotDatabase:
    def __init__(self, path: str) -> None:
        database_path = Path(path)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(
            f"sqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        run_migrations(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self.sessions()
