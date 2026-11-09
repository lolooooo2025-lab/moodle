"""Plugin scheduled tasks (Moodle db/tasks.php pattern)."""
TASKS = [
    {
        "classname": "tool_backup.task.run_backup",
        "minute": "0", "hour": "3", "day": "*", "dayofweek": "*", "month": "*",
    },
]
