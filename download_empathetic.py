from datasets import load_dataset
import json
from collections import defaultdict

# Load dataset
dataset = load_dataset("empathetic_dialogues")

output_path = "empathetic_dialogues_clean.json"

# Conversations stored by conv_id
convos = defaultdict(list)

# Each split: train, validation, test
for split in ["train", "validation", "test"]:
    for example in dataset[split]:

        conv_id = example["conv_id"]
        text = example["utterance"].replace("\n", " ").strip()

        # skip empty texts
        if len(text) < 2:
            continue

        convos[conv_id].append(text)

# Convert to list of conversations
final = [dialog for dialog in convos.values() if len(dialog) > 1]

# Save JSON
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(final, f, indent=2, ensure_ascii=False)

print(f"Saved {len(final)} cleaned conversations to {output_path}")
