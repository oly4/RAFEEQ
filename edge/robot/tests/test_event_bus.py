from rafeeq_robot.application.event_bus import EventBus
from rafeeq_robot.domain.events import DomainEvent


def test_event_bus_delivers_subscribed_event() -> None:
    received: list[str] = []
    bus = EventBus()
    bus.subscribe("sos_pressed", lambda event: received.append(event.event_type))
    bus.publish(DomainEvent(event_type="sos_pressed"))
    assert received == ["sos_pressed"]
