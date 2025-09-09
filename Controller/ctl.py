from __future__ import annotations
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import subprocess
import easyocr
import cv2
import re
from pathlib import Path
from datetime import datetime
from ultralytics import YOLO
from Model.Data import sql

# ===== Paths / model =====
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR     = PROJECT_ROOT / "runs"
MODEL_DIR    = PROJECT_ROOT / "Model" / "weights"
HISTORY_DIR  = PROJECT_ROOT / "history"
HISTORY_DIR.mkdir(exist_ok=True)

def _find_latest_best(runs_root: Path):
    cands = list((runs_root / "detect").glob("*/weights/best.pt"))
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None

# ===== Plate helpers =====
PLATE_CANON = re.compile(r'^([1-9]\d)([A-Z]{1,2})(\d)(\d{4,5})$')
def _norm(s: str) -> str:
    s = s.upper().replace(" ", "").replace("-", "").replace(".", "")
    return ''.join(ch for ch in s if ch.isalnum())
def _pretty(canon: str) -> str:
    m = PLATE_CANON.match(canon)
    if not m: return canon
    prov, letters, d1, last = m.groups()
    last_fmt = f"{last[:3]}.{last[3:]}" if len(last)==5 else f"{last[:2]}.{last[2:]}"
    return f"{prov}-{letters}{d1} {last_fmt}"
def _format_from_raw(raw: str) -> str:
    s = re.sub(r'[^A-Z0-9.\-\s]', '', raw.upper())
    m = re.search(r'([1-9]\d)\s*-?\s*([A-Z]{1,2})\s*(\d)\s*(\d{3})[.\s]?(\d{2})', s)
    if m:
        prov, letters, d1, d3, d2 = m.groups()
        letters = ''.join(ch for ch in letters if ch not in "IOQ")
        cand = _norm(f"{prov}{letters[:2]}{d1}{d3+d2}")
        return _pretty(cand) if PLATE_CANON.match(cand) else raw
    m = re.search(r'([1-9]\d)\s*-?\s*([A-Z]{1,2})\s*(\d)\s*(\d{4,5})', s)
    if m:
        prov, letters, d1, tail = m.groups()
        letters = ''.join(ch for ch in letters if ch not in "IOQ")
        cand = _norm(f"{prov}{letters[:2]}{d1}{tail[-5:]}")
        return _pretty(cand) if PLATE_CANON.match(cand) else raw
    s0 = _norm(s)
    return _pretty(s0) if PLATE_CANON.match(s0) else raw

def _cv2_to_tk(img_bgr, size, upscale=False):
    h, w = img_bgr.shape[:2]
    sx = size[0]/w; sy = size[1]/h
    scale = min(sx, sy)
    if not upscale: scale = min(scale, 1.0)
    nw, nh = max(1,int(w*scale)), max(1,int(h*scale))
    if (nw,nh) != (w,h):
        img_bgr = cv2.resize(img_bgr, (nw,nh),
                             interpolation=cv2.INTER_CUBIC if upscale else cv2.INTER_AREA)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    return ImageTk.PhotoImage(Image.fromarray(img_rgb))

# ===== Controller =====
class A_ctl:
    def __init__(self, window=None, model_path=None):
        self.window = window
        self._last_crop_bgr = None  # giữ ảnh crop gần nhất để lưu lịch sử

        try:
            self.reader = easyocr.Reader(['en'], gpu=True)
        except Exception:
            self.reader = easyocr.Reader(['en'], gpu=False)

        mp = Path(model_path) if model_path else (_find_latest_best(RUNS_DIR) or (MODEL_DIR / "best.pt"))
        if not mp or not mp.exists():
            raise FileNotFoundError("Không tìm thấy best.pt")
        self.detector = YOLO(mp.as_posix())

    def home(self):
        if self.window:
            self.window.destroy()
        subprocess.run(["python", "main.py"])

    def open_image(self):
        file_path = filedialog.askopenfilename(
            title="Chọn ảnh",
            filetypes=[("Image Files", "*.jpg;*.jpeg;*.png;*.bmp")]
        )
        if not file_path:
            return None, None
        img = Image.open(file_path)
        img_resized = img.resize((480, 350), Image.LANCZOS)
        return ImageTk.PhotoImage(img_resized), file_path

    def detect_plate(self, file_path):
        """Trả (crop_tk, text, vis_tk, conf)."""
        if not file_path:
            messagebox.showwarning("Cảnh báo", "Chưa chọn ảnh!")
            return None, "", None, 0.0

        img = cv2.imread(file_path)
        if img is None:
            messagebox.showerror("Lỗi", "Không đọc được ảnh!")
            return None, "", None, 0.0

        det = self.detector.predict(source=img, conf=0.18, device='cpu', verbose=False)[0]
        if len(det.boxes) == 0:
            messagebox.showinfo("Thông báo", "Không phát hiện biển số!")
            return None, "", None, 0.0

        i = int(det.boxes.conf.argmax())
        x1, y1, x2, y2 = map(int, det.boxes.xyxy[i].tolist())
        conf = float(det.boxes.conf[i])

        # crop + nới 12%
        h, w = img.shape[:2]
        dw, dh = int((x2-x1)*0.12), int((y2-y1)*0.12)
        x1 = max(0, x1-dw); y1 = max(0, y1-dh)
        x2 = min(w-1, x2+dw); y2 = min(h-1, y2+dh)
        plate = img[y1:y2, x1:x2]
        self._last_crop_bgr = plate.copy()

        # preprocess gọn
        g = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)
        g = cv2.createCLAHE(2.0, (8,8)).apply(g)
        thr = cv2.adaptiveThreshold(g,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY,31,10)

        res = self.reader.readtext(
            thr, detail=1,
            allowlist='0123456789ABCDEFGHJKLMNPRSTUVWXYZ-. ',
            paragraph=False, text_threshold=0.55, low_text=0.3, link_threshold=0.3
        )
        raw = " ".join([t[1] for t in res]) if res else ""
        text = _format_from_raw(raw) if raw else ""

        # ảnh hiển thị
        crop_tk = _cv2_to_tk(plate, (640,400), upscale=True)
        vis = img.copy()
        cv2.rectangle(vis, (x1,y1), (x2,y2), (0,255,0), 2)
        cv2.putText(vis, text, (x1, max(0,y1-10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2, cv2.LINE_AA)
        vis_tk = _cv2_to_tk(vis, (480,350), upscale=False)

        return crop_tk, text, vis_tk, conf

    # === Lưu lịch sử (kèm ảnh) ===
    def history(self, bien_so: str) -> int:
        img_path = None
        try:
            if self._last_crop_bgr is not None:
                safe = re.sub(r'[^A-Z0-9]', '', bien_so.upper())
                fname = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe}.jpg"
                fpath = HISTORY_DIR / fname
                cv2.imwrite(str(fpath), self._last_crop_bgr)
                img_path = str(fpath)
        except Exception as e:
            print("Save history image error:", e)
        return sql.luu_lich_su(bien_so, img_path)

Controller = A_ctl
