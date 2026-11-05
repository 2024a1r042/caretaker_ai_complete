import json
import os

def normalize_metric(name):
    return name.lower().replace(" ", "").replace("_", "")

def compare_reports(pred, gt):
    tp, fp, fn = 0, 0, 0

    gt_map = {normalize_metric(x["metric"]): x["value"] for x in gt}
    pred_map = {normalize_metric(x["metric"]): x["value"] for x in pred}

    for metric in pred_map:
        if metric in gt_map:
            # allow small float differences
            if abs(pred_map[metric] - gt_map[metric]) < 0.01:
                tp += 1
            else:
                fp += 1
        else:
            fp += 1

    for metric in gt_map:
        if metric not in pred_map:
            fn += 1

    return tp, fp, fn

def evaluate_all(pred_dir, gt_dir):
    total_tp, total_fp, total_fn = 0, 0, 0

    files = [f for f in os.listdir(gt_dir) if f.endswith(".json")]
    for file in files:
        gt_path = os.path.join(gt_dir, file)
        pred_path = os.path.join(pred_dir, file)

        if not os.path.exists(pred_path):
            print(f"Missing prediction for {file}")
            continue

        with open(gt_path, 'r', encoding='utf-8') as f:
            gt = json.load(f)

        with open(pred_path, 'r', encoding='utf-8') as f:
            pred = json.load(f)

        tp, fp, fn = compare_reports(pred, gt)

        total_tp += tp
        total_fp += fp
        total_fn += fn

    precision = total_tp / (total_tp + total_fp + 1e-6)
    recall = total_tp / (total_tp + total_fn + 1e-6)

    print(f"\n=================================")
    print(f"        BENCHMARK RESULTS        ")
    print(f"=================================")
    print(f"Total Reports : {len(files)}")
    print(f"True Positives: {total_tp}")
    print(f"False Positive: {total_fp}")
    print(f"False Negative: {total_fn}")
    print(f"---------------------------------")
    print(f"Precision     : {precision:.3f} ({precision*100:.1f}%)")
    print(f"Recall        : {recall:.3f} ({recall*100:.1f}%)")
    print(f"=================================\n")

    return precision, recall


if __name__ == "__main__":
    evaluate_all("predictions/", "test_data/ground_truth/")
