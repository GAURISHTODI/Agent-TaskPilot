"""Task state machine and per-state tool allowlist.

There is no send_message / pay / book tool. Those names exist only so that an attempt to use one raises.
"""

STATES = [
    "NEW", "CLASSIFIED", "NEEDS_INFO", "READY_TO_PLAN", "PLANNED", "AWAITING_APPROVAL", "IN_EXECUTION",
    "AWAITING_VENDOR", "CUSTOMER_UPDATE_DRAFTED", "COMPLETED", "ESCALATED_TO_HUMAN",
]
ESC = "ESCALATED_TO_HUMAN"
TRANSITIONS = {
    "NEW": {"CLASSIFIED"},
    "CLASSIFIED": {"NEEDS_INFO", "READY_TO_PLAN"},
    "NEEDS_INFO": {"NEEDS_INFO", "READY_TO_PLAN"},
    "READY_TO_PLAN": {"PLANNED"},
    "PLANNED": {"AWAITING_APPROVAL"},
    "AWAITING_APPROVAL": {"IN_EXECUTION"},
    "IN_EXECUTION": {"AWAITING_VENDOR"},
    "AWAITING_VENDOR": {"AWAITING_VENDOR", "CUSTOMER_UPDATE_DRAFTED"},
    "CUSTOMER_UPDATE_DRAFTED": {"COMPLETED"},
    "COMPLETED": set(),
    ESC: {"COMPLETED"},
}
ALL = set(STATES)
LATE = {"IN_EXECUTION", "AWAITING_VENDOR", "CUSTOMER_UPDATE_DRAFTED"}
TOOL_ALLOWLIST: dict[str, set[str]] = {
    "search_vendors": {"PLANNED"},
    "get_customer_prefs": ALL,
    "draft_vendor_message": {"PLANNED"},
    "draft_customer_update": LATE,
    "request_approval": {"PLANNED", "AWAITING_APPROVAL"} | LATE,
    "escalate_to_human": ALL,
}
BANNED_TOOLS = {"send_message", "pay", "book"}


class BannedAction(Exception):
    """An irreversible action (send/pay/book) was requested. Only a human can do these, in the console."""


class ToolNotAllowed(Exception):
    pass


class InvalidTransition(Exception):
    pass


def check_transition(src: str, dst: str) -> None:
    if dst == ESC and src != "COMPLETED":
        return
    if dst not in TRANSITIONS.get(src, set()):
        raise InvalidTransition(f"{src} -> {dst}")


class ToolGate:
    """All tool use goes through here. Records what actually executed, for audits and the injection eval."""

    def __init__(self):
        self.executed: list[str] = []
        self.blocked: list[tuple[str, str]] = []

    def call(self, state: str, name: str, fn, *args, **kwargs):
        if name in BANNED_TOOLS:
            self.blocked.append((name, "banned"))
            raise BannedAction(name)
        if name not in TOOL_ALLOWLIST:
            self.blocked.append((name, "unknown"))
            raise ToolNotAllowed(f"unknown tool {name}")
        if state not in TOOL_ALLOWLIST[name]:
            self.blocked.append((name, f"not allowed in {state}"))
            raise ToolNotAllowed(f"{name} not allowed in {state}")
        self.executed.append(name)
        return fn(*args, **kwargs)
