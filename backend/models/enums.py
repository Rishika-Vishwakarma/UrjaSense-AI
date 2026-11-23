"""Domain constants (status workflow, priorities, categories)."""
STATUSES = ["REPORTED", "VERIFIED", "ASSIGNED", "REPAIR_IN_PROGRESS", "RESOLVED"]
ACTIVE_STATUSES = STATUSES[:-1]
PRIORITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
LANGUAGES = ["en", "hi"]   # add more Indian languages here + frontend/js/i18n files

STATUS_LABELS_HI = {
    "REPORTED": "रिपोर्ट किया गया", "VERIFIED": "सत्यापित", "ASSIGNED": "सौंपा गया",
    "REPAIR_IN_PROGRESS": "मरम्मत जारी", "RESOLVED": "समाधान हो गया",
}
STATUS_LABELS_EN = {
    "REPORTED": "Reported", "VERIFIED": "Verified", "ASSIGNED": "Assigned",
    "REPAIR_IN_PROGRESS": "Repair in progress", "RESOLVED": "Resolved",
}

# Allowed forward transitions and who may perform them
TRANSITIONS = {
    "REPORTED": {"VERIFIED": {"admin"}},
    "VERIFIED": {"ASSIGNED": {"admin"}},
    "ASSIGNED": {"REPAIR_IN_PROGRESS": {"lineman", "admin"}},
    "REPAIR_IN_PROGRESS": {"RESOLVED": {"lineman", "admin"}},
}
