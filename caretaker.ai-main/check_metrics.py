import torch
try:
    ckpt = torch.load('backend/VideoMonitoring/fall_lstm.pth', map_location='cpu', weights_only=True)
except TypeError:
    ckpt = torch.load('backend/VideoMonitoring/fall_lstm.pth', map_location='cpu')

print(f"Metrics - Accuracy: {ckpt.get('val_accuracy')}, F1 Score: {ckpt.get('val_f1')}, Precision: {ckpt.get('val_precision')}, Recall: {ckpt.get('val_recall')}, Epoch: {ckpt.get('epoch')}")
