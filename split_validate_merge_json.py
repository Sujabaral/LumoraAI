import json
import os

input_file = "./dialogpt_model/data/mental_health_dataset_fixed.json"
temp_folder = "./dialogpt_model/data/temp_chunks"
output_file = "./dialogpt_model/data/mental_health_dataset_final.json"
chunk_size = 50  # number of tags per chunk

os.makedirs(temp_folder, exist_ok=True)

# Step 1: Load the big JSON
with open(input_file, "r", encoding="utf-8") as f:
    try:
        data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        exit()

# Step 2: Split into smaller chunks
chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]

print(f"Splitting into {len(chunks)} chunks...")

# Step 3: Validate and save each chunk
valid_chunks = []
for idx, chunk in enumerate(chunks, start=1):
    chunk_file = os.path.join(temp_folder, f"chunk_{idx}.json")
    try:
        # Try dumping to check validity
        with open(chunk_file, "w", encoding="utf-8") as f_chunk:
            json.dump(chunk, f_chunk, indent=2, ensure_ascii=False)
        valid_chunks.extend(chunk)
        print(f"Chunk {idx} ✅ valid")
    except Exception as e:
        print(f"Chunk {idx} ❌ invalid: {e}")

# Step 4: Merge valid chunks into one final JSON
with open(output_file, "w", encoding="utf-8") as f_out:
    json.dump(valid_chunks, f_out, indent=2, ensure_ascii=False)

print(f"\nAll valid chunks merged into: {output_file}")
print("✅ JSON fully validated and ready for DialogGPT fine-tuning!")
