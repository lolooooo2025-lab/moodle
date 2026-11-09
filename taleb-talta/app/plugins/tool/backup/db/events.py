"""Plugin event observers (Moodle db/events.php pattern)."""

async def on_user_registered(payload: dict):
    """Example observer: react to a core event without touching core code."""
    # In a real backup tool this might schedule an incremental snapshot.
    # Kept side-effect-free here; proves the observer wiring works.
    return None

OBSERVERS = {
    "user.registered": on_user_registered,
}
