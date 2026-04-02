import json

# load mindfulness exercises from json file
with open("ChatbotWebsite/static/mindfulness/mindfulness.json") as file:
    mindfulness_exercises = json.load(file)


import re

def normalize_title(t: str) -> str:
    # remove duration (8:12) and lowercase
    t = re.sub(r"\s*\(\d{1,2}:\d{2}\)\s*$", "", t or "").strip().lower()
    return t

def get_description(title):
    target = normalize_title(title)

    for exercise in mindfulness_exercises["mindfulness_exercises"]:
        stored = normalize_title(exercise["title"])

        if stored == target:
            return exercise["description"], exercise["file_name"]

    return None