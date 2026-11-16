from hardware_qa.discover import discover_capabilities
from hardware_qa.orchestrator import handle_turn
from hardware_qa.session import SessionState


def test_demo_ram_answer():
    caps = discover_capabilities(demo_mode=True)
    reply = handle_turn("How much RAM do I have?", caps, SessionState())
    assert "GB RAM" in reply
    assert "demo mode" in reply.lower()
