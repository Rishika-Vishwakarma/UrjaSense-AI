"""Smart incident categorisation from report text (English + Hindi keywords).

This produces a SUGGESTED category only. It is a keyword-scoring heuristic,
not a verified cause. Only an authorised lineman/admin can record the official cause.
"""
import re

RULES = {
    "transformer_fault": ["transformer", "dp", "spark", "sparking", "blast", "burnt", "burning smell", "oil leak",
                          "ट्रांसफार्मर", "ट्रांसफॉर्मर", "धमाका", "चिंगारी", "जल गया"],
    "line_fault": ["wire", "line", "cable", "pole", "snapped", "fell", "fallen", "tripped", "fuse", "conductor", "tar",
                   "तार", "खंभा", "पोल", "केबल", "फ्यूज", "टूट"],
    "weather_related": ["storm", "rain", "lightning", "wind", "tree", "flood", "thunder", "hail",
                        "आंधी", "तूफान", "बारिश", "बिजली गिरी", "पेड़", "बाढ़", "ओले"],
    "planned_maintenance": ["maintenance", "planned", "scheduled", "notice", "shutdown",
                            "मरम्मत", "रखरखाव", "सूचना", "निर्धारित"],
    "local_fault": ["only my", "my house", "my home", "my meter", "mcb", "inverter", "neighbours have power",
                    "neighbors have power", "meter", "सिर्फ मेरे", "मेरे घर", "मीटर", "एमसीबी"],
}


def suggest_category(text: str | None) -> dict:
    t = (text or "").lower()
    if not t.strip():
        return {"category": "unknown", "confidence": 0.0, "verified": False}
    scores = {}
    for cat, words in RULES.items():
        s = sum(1 for w in words if re.search(re.escape(w.lower()), t))
        if s:
            scores[cat] = s
    if not scores:
        return {"category": "unknown", "confidence": 0.0, "verified": False}
    best = max(scores, key=scores.get)
    conf = round(scores[best] / sum(scores.values()), 2)
    return {"category": best, "confidence": conf, "verified": False}
