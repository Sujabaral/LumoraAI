# ChatbotWebsite/chatbot/brain/distortions.py
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

NEGATIONS = {"not", "no", "never", "dont", "don't", "doesnt", "doesn't", "didnt", "didn't", "cant", "can't", "cannot"}

@dataclass
class DistortionHit:
    name: str
    evidence: str

def _has_negation_near(text: str, start: int, window: int = 18) -> bool:
    """Check if a negation word appears shortly before the match."""
    left = text[max(0, start - window):start]
    return any(re.search(rf"\b{re.escape(n)}\b", left) for n in NEGATIONS)

def detect_distortions(text: str) -> List[str]:
    hits = detect_distortions_with_evidence(text)
    return sorted({h.name for h in hits})

def detect_distortions_with_evidence(text: str) -> List[DistortionHit]:
    t = (text or "").lower()

    patterns: Dict[str, List[str]] = {
        # 1) All-or-nothing / black-and-white thinking
        "all_or_nothing": [
            r"\b(always|never|everyone|no one|nobody|everything|nothing)\b",
            r"\b(complete(ly)?|total(ly)?|entire(ly)?)\b",
            r"\b(all i do is|nothing but)\b",
        ],
        # 2) Catastrophizing (worst-case)
        "catastrophizing": [
            r"\b(worst|disaster|ruined|catastrophe|terrible)\b",
            r"\b(i can('t| not) handle this|i won't survive)\b",
            r"\b(no way out|it's over|my life is over)\b",
            r"\b(what if .* goes wrong)\b",
        ],
        # 3) Mind reading (assuming others' thoughts)
        "mind_reading": [
            r"\b(they (hate|think i'm|think i am)|everyone thinks|people think)\b",
            r"\b(they must be judging|they are judging me)\b",
            r"\b(i know they.* think)\b",
        ],
        # 4) Overgeneralization (one event → always happens)
        "overgeneralization": [
            r"\b(always happens|happens every time|every time)\b",
            r"\b(i always fail|i fail at everything)\b",
            r"\b(nothing ever works|everything goes wrong)\b",
            r"\b(this always|that always)\b",
        ],
        # 5) Should statements (rigid rules)
        "should_statements": [
            r"\b(i|we|they) (should|must|have to|need to) (always|never)?\b",
            r"\b(i shouldn't|i should not)\b",
            r"\b(people should|they should)\b",
        ],
        # 6) Labeling (global negative label)
        "labeling": [
            r"\b(i am|i'm) (a )?(failure|loser|idiot|stupid|useless|worthless|pathetic)\b",
            r"\b(i hate myself)\b",
            r"\b(i'm broken|i am broken)\b",
        ],
        # 7) Personalization (everything is my fault)
        "personalization": [
            r"\b(it('s| is) (all )?my fault)\b",
            r"\b(i blame myself)\b",
            r"\b(i caused this)\b",
        ],
        # 8) Emotional reasoning ("I feel it so it's true")
        "emotional_reasoning": [
            r"\b(i feel .* therefore it('s| is) true)\b",
            r"\b(i feel .* so it must be)\b",
            r"\b(because i feel .* it means)\b",
        ],
        # 9) Fortune telling (predicting negative future)
        "fortune_telling": [
            r"\b(i will fail|i'm going to fail|i am going to fail)\b",
            r"\b(it will go wrong|it won't work|it will not work)\b",
            r"\b(nothing will change)\b",
            r"\b(i'll never get better|i will never get better)\b",
        ],
    }

    results: List[DistortionHit] = []

    for name, pats in patterns.items():
        for p in pats:
            m = re.search(p, t)
            if not m:
                continue

            # avoid false positives when negated (e.g., "not always", "i'm not a failure")
            if _has_negation_near(t, m.start()):
                continue

            evidence = m.group(0)
            results.append(DistortionHit(name=name, evidence=evidence))
            break  # one hit per distortion is enough

    return results