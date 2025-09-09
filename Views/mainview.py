from tkinter import *
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk
import re
from Model.Data import sql

PLATE_CANON = re.compile(r'^([1-9]\d)([A-Z]{1,2})(\d)(\d{4,5})$')

def _to_canonical(pretty: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', pretty.upper())

def _extract_fields(pretty: str):
    s = _to_canonical(pretty)
    m = PLATE_CANON.match(s)
    if not m:
        return None
    prov_code, letters, group_digit, last = m.groups()
    ten_tinh   = sql.lay_tinh(prov_code)  # <— chỉ "63", "70", ...
    seri       = letters + group_digit                  # chỉ chữ
    ma_ca_nhan = last                     # 4–5 số cuối
    return ten_tinh, seri, ma_ca_nhan

class Mainview:
    def __init__(self, window, controller):
        self.window = window
        self.controller = controller
        self.window.title("Phần mềm nhận diện biển số xe")
        self.window.state("zoomed")
        self.window.configure(bg="white")

        # ============ LAYOUT ============ #
        self.frame_menu = Frame(self.window, bg="white")
        self.frame_menu.place(x=0, y=0, width=220, height=800)

        self.frame_main = Frame(self.window, bg="white")
        self.frame_main.place(x=200, y=0, width=1980, height=800)

        self.frame_lap = Frame(self.frame_main, bg="#D3D3D3", bd=3, relief="solid")
        self.frame_lap.place(x=10, y=50, width=1200, height=670)

        self.frame_img = Frame(self.frame_lap, bg="white", bd=3, relief="solid")
        self.frame_img.place(x=70, y=50, width=480, height=350)
        self.frame_img.bind("<Button-1>", lambda event: self.load_image())

        self.frame_img2 = Frame(self.frame_lap, bg="white", bd=3, relief="solid")
        self.frame_img2.place(x=653, y=50, width=480, height=350)

        self.label_intro = Label(
            self.frame_main, text="NHẬN DIỆN BIỂN SỐ XE",
            font=("Times New Roman", 20, "bold"), fg="#000000", bg="white"
        )
        self.label_intro.place(x=450, y=10)

        self.label_1 = Label(self.frame_lap, text="Ảnh tải lên",
                             font=("Times New Roman", 18, "bold"),
                             fg="#000000", bg="#D3D3D3")
        self.label_1.place(x=250, y=405)

        self.label_2 = Label(self.frame_lap, text="Ảnh biển số đọc được",
                             font=("Times New Roman", 18, "bold"),
                             fg="#000000", bg="#D3D3D3")
        self.label_2.place(x=780, y=405)

        self.btn_open = Button(
            self.window, text="NHẬN DIỆN", font=("Times New Roman", 13),
            bg="#6FA8DC", fg="white", command=self.detect_plate
        )
        self.btn_open.place(x=765, y=460, width=100, height=45)

        self.c = Canvas(self.frame_lap, width=70, height=80, bg="#D3D3D3", highlightthickness=0)
        self.c.place(x=565, y=190)
        self.c.create_line(10, 40, 60, 40, width=6, capstyle="round", arrow=LAST, arrowshape=(20, 22, 10))

        self.label_3 = Label(self.frame_lap, text="Thông tin về biển số: ",
                             font=("Times New Roman", 20, "bold"),
                             fg="#000000", bg="#D3D3D3")
        self.label_3.place(x=70, y=460)

        self.label_4 = Label(self.frame_lap, text="Mã biển số: ",
                             font=("Times New Roman", 16, "bold"),
                             fg="#000000", bg="#D3D3D3")
        self.label_4.place(x=70, y=510)

        self.label_5 = Label(self.frame_lap, text="Tỉnh thành: ",
                             font=("Times New Roman", 16, "bold"),
                             fg="#000000", bg="#D3D3D3")
        self.label_5.place(x=70, y=540)

        self.label_6a = Label(self.frame_lap, text="Seri cấp phát: ",
                              font=("Times New Roman", 16, "bold"),
                              fg="#000000", bg="#D3D3D3")
        self.label_6a.place(x=70, y=570)

        self.label_6b = Label(self.frame_lap, text="Mã cá nhân: ",
                              font=("Times New Roman", 16, "bold"),
                              fg="#000000", bg="#D3D3D3")
        self.label_6b.place(x=70, y=600)

        # khung hiển thị ảnh biển số (crop)
        self.label_img2 = Label(self.frame_img2, bg="white")
        self.label_img2.pack(fill="both", expand=True)

        self.buttons = [
            Button(self.frame_menu, text="Trang chủ", font=("Times New Roman", 14),
                   command=self.controller.home),
            Button(self.frame_menu, text="Tải ảnh lên", font=("Times New Roman", 14),
                   command=self.load_image),
            Button(self.frame_menu, text="Lịch sử", font=("Times New Roman", 14)),
            Button(self.frame_menu, text="Đọc biển số", font=("Times New Roman", 14)),
            Button(self.frame_menu, text="Tra cứu", font=("Times New Roman", 14)),
            Button(self.frame_menu, text="Thoát", bg="#FF6666", fg="white",
                   font=("Times New Roman", 14, "bold"), command=self.window.quit),
            Button(self.frame_menu, text="Vẽ xe tự động", font=("Times New Roman", 14)),
        ]
        self.place_buttons()

        # giữ reference ảnh hiển thị để tránh GC
        self.img_label = None         # ảnh bên trái (gốc/bbox)
        self.img_left_tk = None
        self.img_right_tk = None      # ảnh crop bên phải
        self.file_path = None

    # ============ FUNCTIONS ============ #
    def place_buttons(self):
        gap = 65
        for i, btn in enumerate(self.buttons):
            btn.place(x=25, y=(i + 0.8) * gap, width=150, height=50)

    def load_image(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.webp")]
        )
        if not file_path:
            return

        # hiển thị ảnh gốc ở khung trái
        img = Image.open(file_path).resize((480, 350))
        self.img_left_tk = ImageTk.PhotoImage(img)
        self.file_path = file_path

        if self.img_label:
            self.img_label.config(image=self.img_left_tk)
            self.img_label.image = self.img_left_tk
        else:
            self.img_label = Label(self.frame_img, image=self.img_left_tk, bg="white")
            self.img_label.pack(expand=True, fill="both")

    def detect_plate(self):
        if not self.file_path:
            messagebox.showwarning("Cảnh báo", "Chưa chọn ảnh!")
            return

        try:
            # lấy 4 giá trị từ Controller: crop_tk, text, vis_tk, conf
            img_crop_tk, text, img_vis_tk, conf = self.controller.detect_plate(self.file_path)
        except Exception as e:
            messagebox.showerror("Lỗi", str(e))
            return

        # hiển thị crop bên phải
        if img_crop_tk:
            self.label_img2.config(image=img_crop_tk)
            self.label_img2.image = img_crop_tk
            self.img_right_tk = img_crop_tk

        # cập nhật ảnh bên trái thành ảnh có bbox + text
        if img_vis_tk:
            if self.img_label:
                self.img_label.config(image=img_vis_tk)
                self.img_label.image = img_vis_tk
            else:
                self.img_label = Label(self.frame_img, image=img_vis_tk, bg="white")
                self.img_label.pack(expand=True, fill="both")

        # cập nhật text
        if text:
            self.label_4.config(text=f"Mã biển số: {text}")

        # --- cập nhật Tỉnh, Seri, Mã cá nhân ---
        fields = _extract_fields(text)
        if fields:
            ten_tinh, seri, ma_cn = fields
            self.label_5.config(text=f"Tỉnh thành: {ten_tinh}")
            self.label_6a.config(text=f"Seri cấp phát: {seri}")
            self.label_6b.config(text=f"Mã cá nhân: {ma_cn}")
        else:
            self.label_5.config(text="Tỉnh thành: Không xác định")
            self.label_6a.config(text="Seri cấp phát: -")
            self.label_6b.config(text="Mã cá nhân: -")

