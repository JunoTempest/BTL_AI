from ultralytics import YOLO
import cv2

# nạp model
model = YOLO("runs/detect/train2/weights/best.pt")

# chạy thử với 1 ảnh
results = model.predict(source="datasets/test/images/images-1-_png.rf.546429a08b55d26942cad4df99319553.jpg", conf=0.3, device=0)

# hiển thị kết quả
for r in results:
    for box in r.boxes:
        print("BBox:", box.xyxy.tolist(), "Conf:", float(box.conf[0]))

results[0].show()  # mở cửa sổ ảnh có bbox
