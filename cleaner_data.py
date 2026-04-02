import json5
import json
import os

dataset_paths = [
    "dialogpt_model/data/mental_health_dataset_1.json",
    "dialogpt_model/data/mental_health_dataset_2.json",
    "dialogpt_model/data/mental_health_dataset_3.json"
]

output_file = "dialogpt_model/data/mental_health_dataset_final_clean.json"
os.makedirs(os.path.dirname(output_file), exist_ok=True)

merged_data = {}

for path in dataset_paths:
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        data = json5.loads(text)  # tolerant parser
        print(f"✅ Loaded {path} with {len(data)} items")
        for item in data:
            tag = item.get("tag")
            dialogues = item.get("dialogues", [])
            if not tag or not dialogues:
                continue
            if tag not in merged_data:
                merged_data[tag] = set()
            for dialogue in dialogues:
                merged_data[tag].add(json.dumps(dialogue, ensure_ascii=False))
    except Exception as e:
        print(f"⚠ Failed to load {path}: {e}")

# Convert back to list
final_dataset = []
for tag, dialogues_set in merged_data.items():
    dialogues_list = [json.loads(d) for d in dialogues_set]
    final_dataset.append({
        "tag": tag,
        "dialogues": dialogues_list
    })

# Save final merged dataset
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(final_dataset, f, indent=2, ensure_ascii=False)

print(f"✅ Fully cleaned merged dataset saved to: {output_file}")
print(f"✅ Total tags: {len(final_dataset)}")
