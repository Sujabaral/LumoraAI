import json
import re

input_file = "./dialogpt_model/data/mental_health_dataset.json"
output_file = "./dialogpt_model/data/mental_health_dataset_fixed.json"

def auto_fix_json(input_file, output_file):
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 1️⃣ Remove trailing commas before closing brackets (common JSON issue)
    content = re.sub(r",\s*(\]|\})", r"\1", content)

    # 2️⃣ Add missing commas between objects in arrays
    # This looks for closing } followed by opening { without a comma
    content = re.sub(r"\}\s*\n\s*\{", r"},\n{", content)

    # 3️⃣ Try to load JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"Still JSON error at line {e.lineno}, column {e.colno}: {e.msg}")
        print("Saving partially fixed JSON to check manually...")
        with open(output_file, "w", encoding="utf-8") as f_out:
            f_out.write(content)
        return

    # 4️⃣ Save fixed JSON
    with open(output_file, "w", encoding="utf-8") as f_out:
        json.dump(data, f_out, indent=2, ensure_ascii=False)
    print(f"JSON fixed successfully ✅ Saved as {output_file}")

if __name__ == "__main__":
    auto_fix_json(input_file, output_file)
