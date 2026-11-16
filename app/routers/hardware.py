"""HTTP wrapper around HardAsk so RelayGrid can inspect the host machine."""

from fastapi import APIRouter

from app.schemas import HardwareAskRequest, HardwareAskResponse
from hardware_qa.discover import discover_capabilities
from hardware_qa.orchestrator import handle_turn
from hardware_qa.session import SessionState

router = APIRouter(prefix="/api/v1/hardware", tags=["hardware"])
_sessions: dict[str, SessionState] = {"default": SessionState()}


@router.post("/ask", response_model=HardwareAskResponse)
def ask_hardware(payload: HardwareAskRequest) -> HardwareAskResponse:
    caps = discover_capabilities(demo_mode=payload.demo)
    session = _sessions["default"]
    answer = handle_turn(payload.question, caps, session)
    return HardwareAskResponse(
        answer=answer,
        demo=caps.demo_mode,
        tools_available=len(caps.available_tools),
        tools_missing=caps.missing_tools,
    )
