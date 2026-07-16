from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rafeeq_robot.persistence.database import RobotDatabase
from rafeeq_robot.persistence.models import LocalEvent, OutboxRecord


class OutboxService:
    def __init__(
        self,
        database: RobotDatabase,
        device_id: str,
        patient_id: str,
        client: httpx.Client | None = None,
    ) -> None:
        self.database = database
        self.device_id = device_id
        self.patient_id = patient_id
        self.client = client

    def record(self, event_type: str, payload: dict[str, object]) -> LocalEvent:
        with self.database.session() as session, session.begin():
            event = self.record_in_session(session, event_type, payload)
        return event

    def record_in_session(
        self,
        session: Session,
        event_type: str,
        payload: dict[str, object],
        occurred_at: datetime | None = None,
    ) -> LocalEvent:
        now = occurred_at or datetime.now(timezone.utc)
        sequence = session.scalar(select(func.count()).select_from(LocalEvent)) or 0
        event = LocalEvent(
            event_id=str(uuid4()),
            event_type=event_type,
            device_id=self.device_id,
            patient_id=self.patient_id,
            occurred_at=now,
            sequence=sequence + 1,
            payload_json=payload,
        )
        session.add(event)
        session.add(
            OutboxRecord(
                event_id=event.event_id,
                status="pending",
                next_attempt_at=now,
            )
        )
        return event

    def publish_pending(self) -> int:
        if self.client is None:
            return 0
        now = datetime.now(timezone.utc)
        with self.database.session() as session:
            records = list(
                session.scalars(
                    select(OutboxRecord)
                    .where(OutboxRecord.status == "pending", OutboxRecord.next_attempt_at <= now)
                    .order_by(OutboxRecord.next_attempt_at)
                    .limit(100)
                ).all()
            )
            if not records:
                return 0
            event_ids = [record.event_id for record in records]
            events = list(
                session.scalars(select(LocalEvent).where(LocalEvent.event_id.in_(event_ids))).all()
            )
            payload = {
                "events": [
                    {
                        "schema_version": 1,
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "device_id": event.device_id,
                        "patient_id": event.patient_id,
                        "occurred_at": event.occurred_at.replace(
                            tzinfo=event.occurred_at.tzinfo or timezone.utc
                        ).isoformat(),
                        "sequence": event.sequence,
                        "payload": event.payload_json,
                    }
                    for event in events
                ]
            }
            try:
                response = self.client.post("/device-api/v1/events/batch", json=payload)
                response.raise_for_status()
                acknowledged = {item["event_id"] for item in response.json()["items"]}
                for record in records:
                    if record.event_id in acknowledged:
                        record.status = "synced"
                        record.last_error = None
                session.commit()
                return len(acknowledged)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                for record in records:
                    record.attempts += 1
                    delay = min(300, 2 ** min(record.attempts, 8))
                    record.next_attempt_at = now + timedelta(seconds=delay)
                    record.last_error = str(exc)[:1000]
                session.commit()
                return 0
