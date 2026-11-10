"""Plugin admin settings nodes (Moodle settings.php pattern)."""
SETTINGS = [
    {"name": "enabled", "default": "1", "label_key": "backup.setting_enabled", "type": "bool"},
    {"name": "keep_days", "default": "30", "label_key": "backup.setting_keep_days", "type": "int", "min": 1, "max": 365},
    {"name": "include_uploads", "default": "0", "label_key": "backup.setting_include_uploads", "type": "bool"},
]
