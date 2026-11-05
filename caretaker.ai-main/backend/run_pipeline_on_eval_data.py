import os
import json
from services.lab_parser import parse_report
from utils.summarizer import extract_text_from_bytes

def run_predictions():
    os.makedirs("predictions", exist_ok=True)
    report_dir = "test_data/reports"
    
    for filename in os.listdir(report_dir):
        if not filename.endswith(".pdf"):
            continue
            
        file_path = os.path.join(report_dir, filename)
        with open(file_path, "rb") as f:
            b = f.read()
            
        print(f"Processing {filename}...")
        # Force layout=True by properly routing through our PDF extractor
        text = extract_text_from_bytes(b, mime="application/pdf")
        
        # We exclusively pass text to the lab parser, skipping Gemini LLM fallback for benchmark
        parsed = parse_report(text)
        
        # We specifically extract the deterministic rule-matched rows
        lab_rows = parsed["rows"]
        
        # Run through our canonical mapper to get standardized names
        from services.lab_normalizer import normalize_and_validate
        
        # Map back to benchmark expected keys and use raw values (before auto unit-conversion)
        KEY_MAP = {
            "Fasting Glucose": "glucose_fasting",
            "HbA1c": "hba1c",
            "HDL": "hdl_cholesterol",
            "LDL": "ldl_cholesterol",
            "Vitamin D": "vitamin_d",
            "Creatinine": "creatinine"
        }
        
        preds = []
        for row in lab_rows:
            norm = normalize_and_validate(row.get("raw_name"), row.get("value"), row.get("unit"), source="regex")
            if norm:
                benchmark_key = KEY_MAP.get(norm["metric_name"], norm["metric_name"])
                preds.append({
                    "metric": benchmark_key,
                    "value": norm["metric_value"]  # Use raw value (to avoid penalizing for correct unit conversions)
                })
            
        pred_path = os.path.join("predictions", filename.replace(".pdf", ".json"))
        with open(pred_path, "w") as f:
            json.dump(preds, f, indent=2)

if __name__ == "__main__":
    run_predictions()
    print("Predictions generated.")
