import random
import json
import os
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

styles = getSampleStyleSheet()

METRICS = [
    ("Creatinine", "mg/dL", (0.7, 1.3), "creatinine"),
    ("Glucose Fasting", "mg/dL", (70, 140), "glucose_fasting"),
    ("HbA1c", "%", (4.0, 8.0), "hba1c"),
    ("HDL Cholesterol", "mg/dL", (30, 60), "hdl_cholesterol"),
    ("LDL Cholesterol", "mg/dL", (80, 160), "ldl_cholesterol"),
    ("Vitamin D", "nmol/L", (50, 150), "vitamin_d"),
]

def generate_report(i):
    os.makedirs("test_data/reports", exist_ok=True)
    os.makedirs("test_data/ground_truth", exist_ok=True)

    doc = SimpleDocTemplate(f"test_data/reports/report_{i}.pdf")
    elements = []

    gt = []

    elements.append(Paragraph(f"Patient: Benchmark Dummy", styles['Heading1']))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(f"Diagnostic Laboratory Test Report", styles['Normal']))
    elements.append(Spacer(1, 10))

    # To test hard mode:
    for name, unit, (low, high), key in METRICS:
        value = round(random.uniform(low, high), 2)
        
        # Hard mode 1: Broken lines
        if random.random() > 0.8:
            elements.append(Paragraph(name, styles['Normal']))
            elements.append(Paragraph(f"{value} {unit}", styles['Normal']))
        else:
            # introduce slight format variation
            line = f"{name} {value} {unit}"
            if random.random() > 0.4:
                line += f" {low} - {high}"
            # Hard mode 3: Missing units
            if random.random() > 0.8:
                line = f"{name} {value}"
            elements.append(Paragraph(line, styles['Normal']))

        gt.append({
            "metric": key,
            "value": value
        })
        
        # Hard mode 2: Noise injection
        if random.random() > 0.7:
             elements.append(Paragraph("Interpretation: Value reflects normal physiological variance.", styles['Normal']))

    doc.build(elements)

    with open(f"test_data/ground_truth/report_{i}.json", "w") as f:
        json.dump(gt, f, indent=2)

if __name__ == "__main__":
    for i in range(1, 21):
        generate_report(i)
    print("Generated 20 benchmark reports.")
