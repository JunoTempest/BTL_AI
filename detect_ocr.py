# detect_ocr.py  (EasyOCR only)
from __future__ import annotations
from ultralytics import YOLO
import cv2, numpy as np, re
from pathlib import Path
import easyocr

# ===== Config =====
CLASS_NAME = "bien so"
VN_PLATE_REGEX = re.compile(r'([1-9]\d)[A-Z]{1,2}\d{4,5}')
BASE = Path(__file__).resolve().parent

# --------- utils ----------
def find_first_image(folder: Path) -> Path | None:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    for p in folder.iterdir():
        if p.suffix.lower() in exts:
            return p
    return None

def find_latest_best(weights_root: Path) -> Path | None:
    cands = list(weights_root.glob("detect/*/weights/best.pt"))
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None

def normalize_text(s: str) -> str:
    s = s.upper().replace(" ", "")
    return (s.replace("O","0").replace("Q","0")
             .replace("I","1").replace("Z","2").replace("S","5"))

def score_text(s: str) -> float:
    s0 = normalize_text(s)
    return (len(s0)/10.0) + (1.0 if VN_PLATE_REGEX.search(s0) else 0.0)

def crop_expand(img, xyxy, expand=0.12):
    h, w = img.shape[:2]
    x1, y1, x2, y2 = map(int, xyxy)
    dw, dh = int((x2-x1)*expand), int((y2-y1)*expand)
    x1 = max(0, x1-dw); y1 = max(0, y1-dh)
    x2 = min(w-1, x2+dw); y2 = min(h-1, y2+dh)
    return img[y1:y2, x1:x2]

def deskew_by_min_area_rect(crop_bgr):
    g = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (3,3), 0)
    e = cv2.Canny(g, 50, 150)
    ys, xs = np.where(e > 0)
    if len(xs) < 50:
        return crop_bgr
    rect = cv2.minAreaRect(np.column_stack((xs, ys)).astype(np.float32))
    angle = rect[2]
    if angle < -45: angle += 90
    if abs(angle) < 2:
        return crop_bgr
    (h, w) = crop_bgr.shape[:2]
    M = cv2.getRotationMatrix2D((w/2, h/2), angle, 1.0)
    return cv2.warpAffine(crop_bgr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

def prep_variants(crop_bgr):
    out = []
    h, w = crop_bgr.shape[:2]
    scale = max(2.0, 300 / max(1, min(h, w)))  # cạnh ngắn ≥ ~300px
    big = cv2.resize(crop_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    g = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
    g = cv2.createCLAHE(2.0, (8,8)).apply(g)
    out.append(g)

    thr = cv2.adaptiveThreshold(g,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,25,10)
    out.append(thr)
    out.append(255 - thr)

    k = np.ones((2,2), np.uint8)
    out.append(cv2.morphologyEx(thr, cv2.MORPH_CLOSE, k, iterations=1))
    out.append(cv2.morphologyEx(255-thr, cv2.MORPH_CLOSE, k, iterations=1))
    return out

def split_two_lines(crop_bgr):
    g = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (3,3), 0)
    binv = cv2.adaptiveThreshold(g,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,25,10)
    hist = binv.sum(axis=1).astype(np.float32)
    h = binv.shape[0]
    s, e = int(0.35*h), int(0.65*h)
    if e - s < 10: return None, None
    cut = s + int(np.argmin(hist[s:e]))
    if cut <= 10 or h-cut <= 10:
        return None, None
    return crop_bgr[:cut, :], crop_bgr[cut:, :]

# --------- OCR (EasyOCR) ----------
def ocr_easy_multi(reader: easyocr.Reader, images):
    best_text, best_score = "", -1
    for im in images:
        for ang in [0, -7, 7, -12, 12]:
            if ang != 0:
                (h, w) = im.shape[:2]
                M = cv2.getRotationMatrix2D((w/2, h/2), ang, 1.0)
                im2 = cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            else:
                im2 = im
            res = reader.readtext(
                im2, detail=1,
                allowlist='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ',
                paragraph=False, text_threshold=0.5, low_text=0.3, link_threshold=0.3,
            )
            raw = " ".join([t[1] for t in res]) if res else ""
            sc = score_text(raw)
            if sc > best_score:
                best_score, best_text = sc, raw
    return best_text

# ===================== MAIN =====================
if __name__ == "__main__":
    # chọn ảnh & model tự động
    img_dir = BASE / "datasets" / "test" / "images"
    img_path = find_first_image(img_dir)
    if not img_path:
        raise FileNotFoundError(f"Không thấy ảnh trong {img_dir}")
    model_path = find_latest_best(BASE / "runs")
    if not model_path:
        raise FileNotFoundError("Không tìm thấy weights best.pt trong runs/detect/*/weights/")
    print(f"Using image: {img_path}")
    print(f"Using model: {model_path}")

    # 1) Detect
    model = YOLO(model_path.as_posix())
    det = model.predict(source=img_path.as_posix(), conf=0.25, device=0, verbose=False)[0]
    if len(det.boxes) == 0:
        print("Không tìm thấy biển số"); exit(0)
    i_best = int(det.boxes.conf.argmax())
    xyxy = det.boxes.xyxy[i_best].tolist()
    conf = float(det.boxes.conf[i_best])
    print("BBox:", xyxy, "Conf:", conf)

    # 2) Crop + nắn + phóng to
    img = cv2.imread(img_path.as_posix())
    crop = crop_expand(img, xyxy, expand=0.12)
    crop = deskew_by_min_area_rect(crop)

    # 3) EasyOCR
    try:
        reader = easyocr.Reader(['en'], gpu=True)
    except Exception:
        reader = easyocr.Reader(['en'], gpu=False)

    preps = prep_variants(crop)
    text_raw = ocr_easy_multi(reader, preps)

    # 3b) nếu yếu → thử tách 2 dòng
    if len(normalize_text(text_raw)) < 6:
        t, b = split_two_lines(crop)
        if t is not None:
            t1 = ocr_easy_multi(reader, prep_variants(t))
            t2 = ocr_easy_multi(reader, prep_variants(b))
            cand = [text_raw, t1+t2, f"{t1} {t2}"]
            text_raw = max(cand, key=score_text)

    text_norm = normalize_text(text_raw)
    m = VN_PLATE_REGEX.search(text_norm)
    final_text = m.group(0) if m else text_norm

    print("OCR raw:", text_raw.strip())
    print("Biển số:", final_text)

    # 4) Hiển thị
    x1,y1,x2,y2 = map(int, xyxy)
    vis = img.copy()
    cv2.rectangle(vis, (x1,y1), (x2,y2), (0,255,0), 2)
    cv2.putText(vis, final_text, (x1, max(0,y1-10)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2, cv2.LINE_AA)

    cv2.imshow("Anh goc", img)
    cv2.imshow("BBox + Text", vis)
    cv2.imshow("Crop", crop)
    for i, p in enumerate(preps[:3]):
        cv2.imshow(f"Prep {i}", p)
    cv2.waitKey(0); cv2.destroyAllWindows()
