from __future__ import annotations
import sqlite3
from pathlib import Path
import re
from datetime import datetime

# === Đường dẫn CSDL ===
DB_PATH = Path(__file__).resolve().parent / "bien_so.db"

# === Helpers ===
def _conn():
    conn = sqlite3.connect(DB_PATH.as_posix())
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_schema():
    """Tạo bảng nếu chưa có + đảm bảo có cột image_path trong lịch sử."""
    with _conn() as c:
        # bảng mã tỉnh -> tên tỉnh
        c.execute("""
            CREATE TABLE IF NOT EXISTS tinh(
                MaTinh  TEXT PRIMARY KEY,
                TenTinh TEXT NOT NULL
            )
        """)
        # bảng lịch sử
        c.execute("""
            CREATE TABLE IF NOT EXISTS lichsu(
                ID        INTEGER PRIMARY KEY AUTOINCREMENT,
                BienSo    TEXT NOT NULL,
                TenTinh   TEXT NOT NULL,
                NgayGio   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                ImagePath TEXT
            )
        """)
        # nếu version cũ chưa có cột ImagePath thì thêm
        cols = [r["name"] for r in c.execute("PRAGMA table_info(lichsu)").fetchall()]
        if "ImagePath" not in cols:
            c.execute("ALTER TABLE lichsu ADD COLUMN ImagePath TEXT")
        c.commit()

# === API tỉnh/thành ===
def lay_tinh(ma_or_plate: str) -> str:
    """
    Nhận vào 2 số mã tỉnh hoặc cả chuỗi biển -> trả về tên tỉnh.
    Tự mở/đóng DB mỗi lần gọi (không dùng connection toàn cục).
    """
    s = str(ma_or_plate).strip().upper()
    m = re.match(r"^([1-9]\d)", s)
    ma_tinh = m.group(1) if m else s[:2]

    _ensure_schema()
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT TenTinh FROM tinh WHERE MaTinh=?",
                (ma_tinh,)
            ).fetchone()
            return row["TenTinh"] if row else "Không xác định"
    except Exception as e:
        print("DB error lay_tinh:", e)
        return "Không xác định"

# === API lịch sử ===
def luu_lich_su(bien_so: str, image_path: str | None = None) -> int:
    """Lưu 1 bản ghi lịch sử, trả về id bản ghi.
       Truyền NgayGio = datetime('now','localtime') để tránh lỗi NOT NULL."""
    _ensure_schema()
    ten_tinh = lay_tinh(bien_so)
    with _conn() as c:
        cur = c.execute(
            """
            INSERT INTO lichsu (BienSo, TenTinh, NgayGio, ImagePath)
            VALUES (?, ?, datetime('now','localtime'), ?)
            """,
            (bien_so, ten_tinh, image_path)
        )
        c.commit()
        return int(cur.lastrowid)

def get_lich_su(limit: int = 200) -> list[dict]:
    """Lấy danh sách lịch sử (mới nhất trước)."""
    _ensure_schema()
    with _conn() as c:
        rows = c.execute(
            "SELECT ID, BienSo, TenTinh, NgayGio, ImagePath "
            "FROM lichsu ORDER BY ID DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

# ====== (tuỳ chọn) seed nhanh một số mã tỉnh nếu DB trống ======
_SEED = [
    ('29','Hà Nội'), ('30','Hà Nội'), ('31','Hà Nội'), ('32','Hà Nội'), ('33','Hà Nội'),
    ('50','TP Hồ Chí Minh'),('51','TP Hồ Chí Minh'),('59','TP Hồ Chí Minh'),
    ('63','Đồng Tháp'), ('60','Đồng Nai'), ('70','Tây Ninh'),
    ('12','Lạng Sơn'), ('35','Ninh Bình'), ('66','Đồng Tháp'),
]
def _maybe_seed_tinh():
    _ensure_schema()
    with _conn() as c:
        cur = c.execute("SELECT COUNT(1) AS n FROM tinh").fetchone()
        if (cur["n"] or 0) < 10:
            c.executemany("INSERT OR IGNORE INTO tinh(MaTinh, TenTinh) VALUES(?,?)", _SEED)
            c.commit()
_maybe_seed_tinh()
