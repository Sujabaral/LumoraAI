import re

def contains_any(text: str, patterns: list[str]) -> bool:
    return any(p in text for p in patterns)


def normalize(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t


def auto_label(text: str) -> str | None:
    if not text:
        return None

    t = normalize(text)

    # --------------------------------------------------
    # 1️⃣ SUICIDAL (highest priority — safety critical)
    # --------------------------------------------------
    suicidal_patterns = [
        "want to die", "kill myself", "end my life",
        "dont want to live", "do not want to live",
        "tired of living", "end it all", "suicide",
        "better off dead", "no reason to live",
        "i should die", "i wish i was dead",
        "life is pointless"
    ]
    if contains_any(t, suicidal_patterns):
        return "suicidal"

    # --------------------------------------------------
    # 2️⃣ ANXIETY (fear / panic / worry)
    # --------------------------------------------------
    anxiety_patterns = [
        "anxious", "panic", "panic attack",
        "cant breathe", "cannot breathe",
        "heart racing", "racing heart",
        "tight chest", "short of breath",
        "overthinking", "overthink",
        "worry", "worried", "constant worry",
        "uneasy", "restless", "nervous",
        "shaking", "trembling",
        "scared for no reason",
        "something bad will happen",
        "i cant relax", "i cannot relax"
    ]
    if contains_any(t, anxiety_patterns):
        return "anxiety"

    # --------------------------------------------------
    # 3️⃣ STRESS (pressure / workload / burnout)
    # --------------------------------------------------
    stress_patterns = [
        "stressed", "stress", "pressure",
        "overwhelmed", "too much work",
        "too many assignments", "too much to do",
        "busy all the time",
        "burnout", "burned out",
        "exhausted from work",
        "cant handle everything",
        "too many responsibilities",
        "deadline", "due tomorrow",
        "exam stress", "academic stress",
        "college pressure", "family pressure",
        "workload", "burden"
    ]
    if contains_any(t, stress_patterns):
        return "stress"

    # --------------------------------------------------
    # 4️⃣ SADNESS (low mood / hopelessness)
    # --------------------------------------------------
    sadness_patterns = [
        "sad", "empty", "hopeless",
        "nothing helps", "depressed",
        "no motivation", "feel worthless",
        "i hate myself", "feel alone",
        "lonely", "crying",
        "feel numb", "no energy"
    ]
    if contains_any(t, sadness_patterns):
        return "sadness"

    # --------------------------------------------------
    # 5️⃣ GREETING
    # --------------------------------------------------
    greetings = [
        "hi", "hello", "hey", "namaste",
        "good morning", "good evening"
    ]
    if t in greetings:
        return "greeting"

    # --------------------------------------------------
    # 6️⃣ GRATITUDE
    # --------------------------------------------------
    gratitude_patterns = [
        "thanks", "thank you", "helped",
        "appreciate it", "that helped"
    ]
    if contains_any(t, gratitude_patterns):
        return "gratitude"

    # --------------------------------------------------
    # 7️⃣ DEFAULT
    # --------------------------------------------------
    return "general"