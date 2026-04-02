def phq9_severity(score: int) -> str:
    if score <= 4: return "minimal"
    if score <= 9: return "mild"
    if score <= 14: return "moderate"
    if score <= 19: return "moderately severe"
    return "severe"

def gad7_severity(score: int) -> str:
    if score <= 4: return "minimal"
    if score <= 9: return "mild"
    if score <= 14: return "moderate"
    return "severe"
