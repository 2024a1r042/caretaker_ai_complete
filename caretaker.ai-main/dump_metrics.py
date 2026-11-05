import torch
try:
    ckpt = torch.load('backend/VideoMonitoring/fall_lstm.pth', map_location='cpu', weights_only=True)
except TypeError:
    ckpt = torch.load('backend/VideoMonitoring/fall_lstm.pth', map_location='cpu')

with open("metrics.txt", "w") as f:
    f.write(f"Accuracy: {ckpt.get('val_accuracy')}\n")
    f.write(f"F1 Score: {ckpt.get('val_f1')}\n")
    f.write(f"Precision: {ckpt.get('val_precision')}\n")
    f.write(f"Recall: {ckpt.get('val_recall')}\n")
