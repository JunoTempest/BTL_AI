from tkinter import Tk
from Controller.ctl import A_ctl as Controller
from GUI.mainview import Mainview

if __name__ == "__main__":
    window = Tk()
    ctl = Controller(model_path=r"runs\detect\train2\weights\best.pt")
    app = Mainview(window, ctl)
    window.mainloop()
