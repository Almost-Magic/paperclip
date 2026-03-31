"""Command routing logic — determines which terminal/hand handles a task."""

import logging

logger = logging.getLogger("paperclip.routing_engine")


# Routing rules: keyword → (terminal_id, terminal_type)
ROUTING_RULES = {
    "fix": ("T1", "terminal"),
    "test": ("H11", "hand"),
    "write prd": ("T4", "terminal"),
    "write spec": ("T4", "terminal"),
    "research": ("H10", "hand"),
    "build cloud": ("T6", "terminal"),
    "audit": ("H3", "hand"),
    "audit security": ("H3", "hand"),
    "database": ("H4", "hand"),
    "devops": ("H5", "hand"),
    "documentation": ("H6", "hand"),
    "backup": ("H7", "hand"),
    "integration": ("H9", "hand"),
}


def route_command(instruction: str) -> tuple[str, str]:
    """
    Analyse instruction and return (agent_id, agent_type).

    Args:
        instruction: User instruction (e.g., "fix CK-MANI", "test Baldrick")

    Returns:
        (agent_id, agent_type) where agent_type is 'terminal' or 'hand'
        Default: ("T1", "terminal") if no match found
    """
    instruction_lower = instruction.lower().strip()

    # Check for exact phrase matches first (longest first)
    for phrase, (agent_id, agent_type) in sorted(
        ROUTING_RULES.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if phrase in instruction_lower:
            logger.info(f"Routed '{instruction}' to {agent_id} (matched '{phrase}')")
            return (agent_id, agent_type)

    # Default to T1 (Guru)
    logger.info(f"Routed '{instruction}' to T1 (default)")
    return ("T1", "terminal")
