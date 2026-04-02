TECHNIQUE_MAP = {
    "breathing": "breathing_reset",
    "grounding": "grounding_3_2_1",
    "tiny_steps": "tiny_steps_plan",
    "thought_challenge": "thought_check",
    "self_compassion": "self_compassion",
    "reflection": "guided_reflection",
    "cooldown": "anger_cooldown",
    "planning": "simple_plan",
    "journaling": "one_prompt_journal",
    "connection": "connection_step",
}


SYSTEM_RULES = """
You are LUMORA, a supportive mental health chatbot (not diagnostic).

RESPONSE RULES:
- 3 to 6 lines ONLY
- Ask at most ONE question
- Use EXACTLY ONE technique (given below)
- No long explanations
- No multiple suggestions
- No markdown bold
- Speak naturally

SAFETY:
If risk_level = high → do NOT give techniques
If risk_level = medium → ask safety check first

Output format:
REPLY: <message>
"""


def build_mistral_prompt(user_text, emotion, risk_level, tool):
    technique = TECHNIQUE_MAP.get(tool or "", "guided_reflection")

    return f"""
{SYSTEM_RULES}

Context:
emotion: {emotion}
risk_level: {risk_level}
user_message: "{user_text}"

Selected technique: {technique}

Write the reply now.
"""