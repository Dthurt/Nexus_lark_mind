"""Schema unit tests."""

from src.common.schemas import ChannelType, EventType, StandardTask, BusEvent


def test_standard_task_defaults(sample_task: StandardTask):
    assert sample_task.task_id.startswith("task_")
    assert sample_task.session_id.startswith("sess_")
    assert sample_task.channel == ChannelType.WEB
    assert sample_task.content == "hello nexus"


def test_bus_event_roundtrip(sample_task: StandardTask):
    event = BusEvent(
        event_type=EventType.TASK_CREATED,
        task_id=sample_task.task_id,
        session_id=sample_task.session_id,
        channel=sample_task.channel,
        payload={"x": 1},
    )
    data = event.model_dump(mode="json")
    restored = BusEvent.model_validate(data)
    assert restored.event_type == EventType.TASK_CREATED
    assert restored.payload["x"] == 1
