from datetime import datetime

import httpx
from sqlalchemy import select

from rafeeq_robot.persistence.database import RobotDatabase
from rafeeq_robot.persistence.models import (
    LocalOccurrence,
    LocalRoutine,
    SyncState,
)


class SyncService:
    def __init__(self, database: RobotDatabase, client: httpx.Client) -> None:
        self.database = database
        self.client = client

    def synchronize(self) -> str:
        response = self.client.get("/device-api/v1/sync/snapshot")
        response.raise_for_status()
        snapshot = response.json()
        version = str(snapshot["configuration_version"])
        patient_id = str(snapshot["patient"]["id"])
        with self.database.session() as session, session.begin():
            for item in snapshot["routines"]:
                routine_id = str(item["id"])
                routine = session.get(LocalRoutine, routine_id)
                if routine is None:
                    routine = LocalRoutine(
                        id=routine_id,
                        patient_id=patient_id,
                        type=str(item["type"]),
                        title=str(item["title"]),
                        payload_json=item,
                        configuration_version=version,
                    )
                    session.add(routine)
                else:
                    routine.type = str(item["type"])
                    routine.title = str(item["title"])
                    routine.payload_json = item
                    routine.configuration_version = version
                for occurrence_data in item.get("occurrences", []):
                    occurrence_id = str(occurrence_data["id"])
                    occurrence = session.get(LocalOccurrence, occurrence_id)
                    if occurrence is None:
                        occurrence = LocalOccurrence(
                            id=occurrence_id,
                            routine_id=routine_id,
                            scheduled_at_utc=datetime.fromisoformat(
                                str(occurrence_data["scheduled_at_utc"]).replace("Z", "+00:00")
                            ),
                            status=str(occurrence_data["status"]),
                        )
                        session.add(occurrence)
                    elif occurrence.status not in ("completed", "missed", "skipped"):
                        occurrence.scheduled_at_utc = datetime.fromisoformat(
                            str(occurrence_data["scheduled_at_utc"]).replace("Z", "+00:00")
                        )
                        occurrence.status = str(occurrence_data["status"])
            state = session.get(SyncState, "configuration_version")
            if state is None:
                session.add(SyncState(key="configuration_version", value=version))
            else:
                state.value = version
        ack = self.client.post("/device-api/v1/sync/ack", json={"configuration_version": version})
        ack.raise_for_status()
        return version

    def routine_count(self) -> int:
        with self.database.session() as session:
            return len(list(session.scalars(select(LocalRoutine.id)).all()))
