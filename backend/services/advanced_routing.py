"""Advanced routing engine with learning, preferences, and fallback chains."""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from services.routing_engine import ROUTING_RULES
from collections import Counter

logger = logging.getLogger("paperclip.advanced_routing")


async def get_user_preferences(db: AsyncSession, username: str) -> dict:
    """Get user's saved routing preferences."""
    try:
        result = await db.execute(text("""
            SELECT preferred_terminal, preferred_hand, custom_routes, fallback_chain
            FROM user_preferences WHERE username = :username
        """), {"username": username})
        row = result.mappings().first()
        if row:
            return dict(row)
    except Exception as e:
        logger.warning(f"Failed to load user preferences: {e}")
    return {}


async def save_user_preference(db: AsyncSession, username: str, preferred_terminal: str = None, preferred_hand: str = None) -> None:
    """Save or update user routing preferences."""
    try:
        # Check if user exists
        check = await db.execute(text("""
            SELECT id FROM user_preferences WHERE username = :username
        """), {"username": username})

        if check.scalar():
            # Update
            updates = []
            params = {"username": username}
            if preferred_terminal:
                updates.append("preferred_terminal = :terminal")
                params["terminal"] = preferred_terminal
            if preferred_hand:
                updates.append("preferred_hand = :hand")
                params["hand"] = preferred_hand

            if updates:
                update_clause = ", ".join(updates) + ", updated_at = CURRENT_TIMESTAMP"
                await db.execute(text(f"""
                    UPDATE user_preferences SET {update_clause} WHERE username = :username
                """), params)
        else:
            # Insert
            await db.execute(text("""
                INSERT INTO user_preferences (username, preferred_terminal, preferred_hand)
                VALUES (:username, :terminal, :hand)
            """), {"username": username, "terminal": preferred_terminal, "hand": preferred_hand})

        await db.commit()
    except Exception as e:
        logger.error(f"Failed to save user preference: {e}")
        await db.rollback()


async def record_routing_decision(
    db: AsyncSession,
    username: str,
    instruction: str,
    keyword_matched: str,
    routed_to: str,
    routed_to_type: str,
    reason: str
) -> None:
    """Record routing decision for learning."""
    try:
        await db.execute(text("""
            INSERT INTO routing_history (username, instruction, keyword_matched, routed_to, routed_to_type, reason)
            VALUES (:username, :instruction, :keyword_matched, :routed_to, :routed_to_type, :reason)
        """), {
            "username": username,
            "instruction": instruction,
            "keyword_matched": keyword_matched,
            "routed_to": routed_to,
            "routed_to_type": routed_to_type,
            "reason": reason,
        })
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to record routing decision: {e}")
        await db.rollback()


async def get_routing_frequency(db: AsyncSession, username: str) -> dict:
    """Get frequency-based routing statistics for user (most commonly routed agents)."""
    try:
        result = await db.execute(text("""
            SELECT routed_to, routed_to_type, COUNT(*) as frequency
            FROM routing_history
            WHERE username = :username
            GROUP BY routed_to, routed_to_type
            ORDER BY frequency DESC
            LIMIT 5
        """), {"username": username})

        rows = result.mappings().all()
        return {f"{row['routed_to']}": {"type": row['routed_to_type'], "freq": row['frequency']} for row in rows}
    except Exception as e:
        logger.warning(f"Failed to get routing frequency: {e}")
    return {}


def calculate_word_similarity(text1: str, text2: str) -> float:
    """Simple word-level similarity (Jaccard index for words)."""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 or not words2:
        return 0.0

    intersection = len(words1 & words2)
    union = len(words1 | words2)
    return intersection / union if union > 0 else 0.0


async def route_command_advanced(
    instruction: str,
    db: AsyncSession | None = None,
    username: str | None = None,
    fallback_chain: list[tuple] | None = None
) -> tuple[str, str, str]:
    """
    Advanced routing with learning, preferences, and fallback.

    Returns: (agent_id, agent_type, reason)

    Priority order:
    1. User preferences (if saved)
    2. Frequency-based learning (if history exists)
    3. Keyword matching (default rules)
    4. Fallback chain (primary → secondary → default)
    """
    instruction_lower = instruction.lower().strip()
    reason = "default"

    # Priority 1: Check user preferences
    if db and username:
        prefs = await get_user_preferences(db, username)
        if prefs.get("preferred_terminal") or prefs.get("preferred_hand"):
            if prefs.get("preferred_terminal"):
                reason = "user_preference_terminal"
                return (prefs["preferred_terminal"], "terminal", reason)
            elif prefs.get("preferred_hand"):
                reason = "user_preference_hand"
                return (prefs["preferred_hand"], "hand", reason)

    # Priority 2: Check frequency-based routing (learning from history)
    if db and username:
        freq = await get_routing_frequency(db, username)
        if freq:
            # Get most frequent agent
            most_frequent = max(freq.items(), key=lambda x: x[1]["freq"])[0]
            most_freq_data = freq[most_frequent]
            reason = "frequency_based"
            return (most_frequent, most_freq_data["type"], reason)

    # Priority 3: Keyword matching (longest first for specificity)
    matched_keyword = None
    for phrase, (agent_id, agent_type) in sorted(
        ROUTING_RULES.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if phrase in instruction_lower:
            reason = f"keyword_match:{phrase}"
            matched_keyword = phrase
            return (agent_id, agent_type, reason)

    # Priority 4: NLP-like intent matching (word similarity)
    best_match = None
    best_score = 0.4  # Threshold
    for phrase in ROUTING_RULES.keys():
        score = calculate_word_similarity(instruction_lower, phrase)
        if score > best_score:
            best_score = score
            best_match = phrase

    if best_match:
        agent_id, agent_type = ROUTING_RULES[best_match]
        reason = f"intent_match:{best_match}({best_score:.2f})"
        return (agent_id, agent_type, reason)

    # Fallback chain or default
    if fallback_chain:
        for agent_id, agent_type in fallback_chain:
            reason = "fallback_chain"
            return (agent_id, agent_type, reason)

    # Final default
    reason = "default"
    return ("T1", "terminal", reason)
