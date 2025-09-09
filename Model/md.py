import easyocr
import cv2
import numpy as np

class PlateModel:
    def __init__(self):
        self.reader = easyocr.Reader(['en'])
    def cnn(self, img):
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_blur = cv2.GaussianBlur(img_rgb, (3, 3), 1.0)
        kn = np.array([[-1,-1,-1],
                       [ 0, 0, 0],
                       [ 1, 1, 1]], dtype=np.float32)

        kd = np.array([[-1, 0, 1],
                       [-1, 0, 1],
                       [-1, 0, 1]], dtype=np.float32)

        gray = cv2.cvtColor(img_blur, cv2.COLOR_RGB2GRAY).astype(np.float32)
        h = cv2.filter2D(gray, -1, kn)
        v = cv2.filter2D(gray, -1, kd)
        m = cv2.convertScaleAbs(np.sqrt(h**2 + v**2))
        k = np.array([[ 0, -1,  0],
                      [-1,  5, -1],
                      [ 0, -1,  0]], dtype=np.float32)
        sharpen = cv2.filter2D(img_rgb, -1, k)
        return cv2.cvtColor(sharpen, cv2.COLOR_RGB2BGR)


    def detect_plate(self, file_path):
        img = cv2.imread(file_path)
        if img is None:
            return None
        img_filtered = self.cnn(img)
        results = self.reader.readtext(img_filtered)
        if not results:
            return None

        texts = [res[1] for res in results]
        plate_text = " ".join(texts)
        return plate_text, img_filtered
