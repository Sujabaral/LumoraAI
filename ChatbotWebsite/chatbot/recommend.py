def recommend(risk_level, trend_label, phq9_sev=None, gad7_sev=None):
    recs = []

    if risk_level == "high":
        recs.append(("crisis", "Reach out to a trusted person now + helpline numbers."))

    if trend_label == "declining":
        recs.append(("coping", "Try 3-minute breathing + grounding exercise."))
        recs.append(("journal", "Write: what triggered this mood today? one small step tomorrow."))

    if phq9_sev in ("moderate", "moderately severe", "severe"):
        recs.append(("support", "Consider scheduling a professional consultation."))

    if gad7_sev in ("moderate", "severe"):
        recs.append(("mindfulness", "Short guided mindfulness (5 min) + reduce caffeine today."))

    if not recs:
        recs.append(("maintenance", "Keep a mood log + one gratitude entry today."))

    return recs[:4]
