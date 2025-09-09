import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import models, transforms
from PIL import Image
THIET_BI = torch.device("cuda" if torch.cuda.is_available() else "cpu")
class DatasetBienSo(Dataset):
    def __init__(self, img_dir, label_dir, transform=None):
        self.img_dir = img_dir
        self.label_dir = label_dir
        self.transform = transform
        self.images = [f for f in os.listdir(img_dir) if f.endswith(".jpg")]

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        # lấy tên file ảnh
        img_name = self.images[idx]
        img_path = os.path.join(self.img_dir, img_name)
        label_path = os.path.join(
            self.label_dir, img_name.replace(".jpg", ".txt")
        )
        # đọc ảnh RGB
        image = Image.open(img_path).convert("RGB")
        if self.transform:
            image = self.transform(image)
        # đọc nhãn YOLO từ file .txt
        class_id = 0
        if os.path.exists(label_path):
            with open(label_path, "r") as f:
                first_line = f.readline().strip().split()
                if len(first_line) == 5:
                    # YOLO format: class x_center y_center width height
                    class_id = int(first_line[0])

        return image, class_id
# 3. collate_fn để gom batch
def collate_fn(batch):
    images = []
    targets = []
    for img, box in batch:
        images.append(img)
        targets.append(box)
    images = torch.stack(images, 0)  # ảnh thì stack được
    return images, targets  # box giữ nguyên list
# 4. Biến đổi ảnh
bien_doi_anh = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
])
# 5. Load dataset Roboflow
train_dataset = DatasetBienSo(
    "datasets/train/images", "datasets/train/labels", transform=bien_doi_anh
)
val_dataset = DatasetBienSo(
    "datasets/valid/images", "datasets/valid/labels", transform=bien_doi_anh
)
train_loader = DataLoader(
    train_dataset, batch_size=4, shuffle=True, collate_fn=collate_fn
)
val_loader = DataLoader(
    val_dataset, batch_size=4, shuffle=False, collate_fn=collate_fn
)
# 6. Model ResNet50 (trích đặc trưng)
resnet50 = models.resnet50(weights="IMAGENET1K_V1")
trich_dac_trung = nn.Sequential(*list(resnet50.children())[:-1]).to(THIET_BI)
model = nn.Sequential(
    trich_dac_trung,
    nn.Flatten(),
    nn.Linear(2048, 128),
    nn.ReLU(),
    nn.Linear(128, 2)  # ví dụ: 2 lớp (có biển số / không)
).to(THIET_BI)
# 7. Hàm mất mát + Optimizer
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=0.001)
# 8. Training loop
for epoch in range(50):
    model.train()
    for imgs, boxes in train_loader:
        imgs = imgs.to(THIET_BI)
        labels = torch.tensor(boxes, dtype=torch.long).to(THIET_BI)

        outputs = model(imgs)
        loss = criterion(outputs, labels)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    print(f"Epoch {epoch+1}, Loss: {loss.item():.4f}")
print("Huấn luyện xong!")
