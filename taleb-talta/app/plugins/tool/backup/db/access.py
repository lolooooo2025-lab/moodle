"""Plugin capability definitions (Moodle db/access.php pattern)."""
CAPABILITIES = {
    "tool/backup:manage": {
        "captype": "manage",
        "roles": ["owner", "admin"],
    },
}
