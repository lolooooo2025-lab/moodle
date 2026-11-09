"""Plugin callbacks + navigation entries (Moodle lib.php pattern)."""

def navigation() -> list[dict]:
    """Menu entries this plugin adds to the admin area."""
    return [
        {"label_key": "backup.title", "url": "/admin/backups",
         "icon": "download", "role": "admin", "order": 90},
    ]
