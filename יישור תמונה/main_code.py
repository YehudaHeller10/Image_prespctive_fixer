import tkinter as tk
from tkinter import filedialog, messagebox, Menu, ttk
from PIL import Image, ImageTk
import cv2
import numpy as np
import os


class PerspectiveCorrectionApp:
    def __init__(self, master):
        self.master = master
        master.title("כלי לתיקון פרספקטיבה בתמונה")
        master.geometry("1000x700")

        self.master.tk.call('tk', 'scaling', 1.3)
        try:
            self.master.tk.call('encoding', 'system', 'utf-8')
        except tk.TclError:
            pass

        self.style = ttk.Style()
        self.style.configure("TButton", font=("Arial", 10), padding=5)
        self.style.configure("TLabel", font=("Arial", 10))
        self.master.option_add('*TCombobox*Listbox.font', ('Arial', 10))

        self.image_path = None
        self.original_image_cv = None
        self.processed_image_cv = None
        self.points = []
        self.image_on_canvas = None
        self.display_image_pil = None
        self.canvas_dots = []
        self.dot_numbers = []

        # New: Define prompts for point marking order
        self.point_prompts = ["שמאל למעלה", "ימין למעלה", "ימין למטה", "שמאל למטה"]

        self.zoom_factor = 1.0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.canvas_image_x_offset = 0
        self.canvas_image_y_offset = 0

        self.marking_mode_active = False

        self.full_transform_fit_to_frame_var = tk.BooleanVar(value=True)

        main_frame = ttk.Frame(master)
        main_frame.pack(expand=tk.YES, fill=tk.BOTH, padx=10, pady=5)

        menubar = Menu(master)
        filemenu = Menu(menubar, tearoff=0)
        filemenu.add_command(label="טען תמונה", command=self.open_image)
        filemenu.add_command(label="שמור תמונה מעובדת", command=self.save_image)
        filemenu.add_command(label="אפס נקודות ותצוגה", command=lambda: self.reset_points(update_status=True,
                                                                                          reset_view_and_mode=True))
        filemenu.add_separator()
        filemenu.add_command(label="יציאה", command=master.quit)
        menubar.add_cascade(label="קובץ", menu=filemenu)

        helpmenu = Menu(menubar, tearoff=0)
        helpmenu.add_command(label="הוראות", command=self.show_instructions)
        helpmenu.add_command(label="אודות", command=self.show_about)
        menubar.add_cascade(label="עזרה", menu=helpmenu)
        master.config(menu=menubar)

        toolbar = ttk.Frame(main_frame)
        toolbar.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))

        self.chk_full_transform_mode = ttk.Checkbutton(
            toolbar,
            text="עוות מלא: התאם למסגרת מקורית",
            variable=self.full_transform_fit_to_frame_var
        )
        self.chk_full_transform_mode.pack(side=tk.RIGHT, padx=(5, 15), pady=5)

        self.btn_process_full = ttk.Button(toolbar, text="עוות תמונה מלאה", command=self.process_image_full_transform,
                                           state=tk.DISABLED)
        self.btn_process_full.pack(side=tk.RIGHT, padx=(5, 0), pady=5)

        self.btn_process_crop = ttk.Button(toolbar, text="יישור קטע נבחר", command=self.process_image_cropped,
                                           state=tk.DISABLED)
        self.btn_process_crop.pack(side=tk.RIGHT, padx=(5, 0), pady=5)

        self.btn_toggle_marking_mode = ttk.Button(toolbar, text="התחל סימון", command=self.toggle_marking_mode)
        self.btn_toggle_marking_mode.pack(side=tk.RIGHT, padx=(5, 0), pady=5)

        self.reset_btn = ttk.Button(toolbar, text="אפס נקודות", command=lambda: self.reset_points(update_status=True,
                                                                                                  reset_view_and_mode=True))
        self.reset_btn.pack(side=tk.RIGHT, padx=(5, 0), pady=5)

        save_btn = ttk.Button(toolbar, text="שמור תמונה", command=self.save_image)
        save_btn.pack(side=tk.RIGHT, padx=(5, 0), pady=5)

        open_btn = ttk.Button(toolbar, text="טען תמונה", command=self.open_image)
        open_btn.pack(side=tk.RIGHT, padx=(0, 5), pady=5)

        # --- New: Marking Order Instruction Label ---
        self.marking_order_instruction_label = ttk.Label(
            main_frame,
            text="סדר סימון: 1. שמאל למעלה -> 2. ימין למעלה -> 3. ימין למטה -> 4. שמאל למטה",
            anchor=tk.E,
            font=("Arial", 9, "italic"),
            justify=tk.RIGHT
        )
        self.marking_order_instruction_label.pack(side=tk.TOP, fill=tk.X, pady=(2, 8),
                                                  padx=5)  # Added little more pady bottom
        # --- End New ---

        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(expand=tk.YES, fill=tk.BOTH)

        self.canvas = tk.Canvas(canvas_frame, background="#f0f0f0", highlightthickness=0)
        self.canvas.pack(expand=tk.YES, fill=tk.BOTH)
        self.canvas.bind("<Button-1>", self.add_point_on_canvas)
        self.canvas.bind("<MouseWheel>", self.zoom_image)
        self.canvas.bind("<Button-4>", self.zoom_image)
        self.canvas.bind("<Button-5>", self.zoom_image)
        self.canvas.bind("<B2-Motion>", self.pan_image_motion)
        self.canvas.bind("<ButtonPress-2>", self.pan_image_start)
        self.canvas.bind("<ButtonRelease-2>", self.pan_image_end)

        status_frame = ttk.Frame(main_frame)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        self.status_label = ttk.Label(status_frame, text="טען תמונה כדי להתחיל.", anchor=tk.E)
        self.status_label.pack(side=tk.RIGHT, fill=tk.X, padx=5, pady=2)

        self.canvas_width = 0
        self.canvas_height = 0
        self.displayed_image_width = 0
        self.displayed_image_height = 0

        self.update_marking_mode_ui()
        self.master.bind("<Configure>", self.on_window_resize)
        self.master.after(200, self.show_welcome_message_if_first_time)

    def update_marking_mode_ui(self):
        if self.marking_mode_active:
            self.btn_toggle_marking_mode.config(text="הפסק סימון")
            if self.original_image_cv is not None and len(self.points) < 4:
                self.canvas.config(cursor="crosshair")
            else:
                self.canvas.config(cursor="")
        else:
            self.btn_toggle_marking_mode.config(text="התחל סימון")
            self.canvas.config(cursor="")

    def toggle_marking_mode(self):
        if self.original_image_cv is None:
            messagebox.showwarning("מצב סימון", "יש לטעון תמונה תחילה.", parent=self.master)
            self.status_label.config(text="יש לטעון תמונה לפני הפעלת מצב סימון.")
            return

        if len(self.points) == 4 and not self.marking_mode_active:
            messagebox.showinfo("מצב סימון", "כבר נבחרו 4 נקודות. בצע עיבוד או אפס נקודות כדי לסמן מחדש.",
                                parent=self.master)
            self.status_label.config(text="4 נקודות נבחרו. בצע עיבוד או אפס נקודות.")
            return

        self.marking_mode_active = not self.marking_mode_active
        self.update_marking_mode_ui()

        if self.marking_mode_active:
            if len(self.points) < 4:
                current_point_idx = len(self.points)
                self.status_label.config(
                    text=f"מצב סימון פעיל. סמן נקודה: {self.point_prompts[current_point_idx]} ({current_point_idx + 1}/4).")
            else:  # Should not happen if logic above is correct, but as a safeguard
                self.status_label.config(text="מצב סימון פעיל, אך כל הנקודות כבר נבחרו.")
        else:
            if len(self.points) < 4:
                self.status_label.config(text="מצב סימון כבוי. לחץ 'התחל סימון' לבחירת נקודות.")
            else:  # 4 points selected, and user turned mode off
                self.status_label.config(text="4 נקודות נבחרו. מצב סימון כבוי. בצע עיבוד או אפס נקודות.")

    def disable_processing_buttons(self):
        if hasattr(self, 'btn_process_crop'):
            self.btn_process_crop.config(state=tk.DISABLED)
        if hasattr(self, 'btn_process_full'):
            self.btn_process_full.config(state=tk.DISABLED)
        if hasattr(self, 'chk_full_transform_mode'):
            self.chk_full_transform_mode.config(state=tk.DISABLED)

    def enable_processing_buttons(self):
        if hasattr(self, 'btn_process_crop'):
            self.btn_process_crop.config(state=tk.NORMAL)
        if hasattr(self, 'btn_process_full'):
            self.btn_process_full.config(state=tk.NORMAL)
        if hasattr(self, 'chk_full_transform_mode'):
            self.chk_full_transform_mode.config(state=tk.NORMAL)

    def show_welcome_message_if_first_time(self):
        if not hasattr(self, '_welcome_message_shown'):
            messagebox.showinfo("ברוכים הבאים",
                                "ברוכים הבאים לכלי לתיקון פרספקטיבה בתמונה!\n\n"
                                "1. התחל על ידי טעינת תמונה.\n"
                                "2. לחץ על 'התחל סימון' וסמן ארבע נקודות על התמונה בסדר הבא:\n"
                                "   - שמאל למעלה\n"
                                "   - ימין למעלה\n"
                                "   - ימין למטה\n"
                                "   - שמאל למטה\n"
                                "3. בחר את סוג העיבוד הרצוי.\n\n"
                                "למידע נוסף, בחר 'הוראות' מתפריט 'עזרה'.",
                                parent=self.master)
            self._welcome_message_shown = True
            self.status_label.config(text="ברוכים הבאים! טען תמונה כדי להתחיל.")

    def show_instructions(self):
        instructions = """
        הוראות שימוש:
        1. טען תמונה: לחץ על כפתור "טען תמונה" או בחר "קובץ" -> "טען תמונה".
        2. הפעל סימון: לחץ על כפתור "התחל סימון". סמן העכבר ישתנה לצלב.
        3. סמן 4 נקודות על התמונה בסדר הבא:
           - נקודה 1: פינה שמאלית-עליונה של האזור הרצוי.
           - נקודה 2: פינה ימנית-עליונה של האזור הרצוי.
           - נקודה 3: פינה ימנית-תחתונה של האזור הרצוי.
           - נקודה 4: פינה שמאלית-תחתונה של האזור הרצוי.
           (לאחר סימון 4 נקודות, מצב הסימון יכבה אוטומטית).
        4. בחר סוג עיבוד: "יישור קטע נבחר" או "עוות תמונה מלאה".
           - עבור "עוות תמונה מלאה", סמן את תיבת הסימון "התאם למסגרת מקורית" אם ברצונך שהתוצאה תתאים בגודלה לתמונה המקורית. אם תיבה זו לא מסומנת, גודל התוצאה יותאם לתוכן המעוות, ויכול להיות גדול מהמקור.
        5. שמור תמונה: אם התוצאה משביעת רצון, שמור באמצעות "שמור תמונה".
        6. אפס נקודות: מנקה את הנקודות ומפעיל מחדש מצב סימון.
        7. הפסק סימון: ניתן לכבות ולהדליק את מצב הסימון בכל שלב באמצעות הכפתור הייעודי.

        ניווט בתמונה (זום ופאן):
        - זום: גלגלת העכבר.
        - פאן: לחצן אמצעי של העכבר + גרירה.
        """
        messagebox.showinfo("הוראות שימוש", instructions, parent=self.master)

    def show_about(self):
        about_text = """
        כלי לתיקון פרספקטיבה בתמונה
        גרסה 1.6
        (הנחיית סדר סימון משופרת)

        יישום זה מאפשר למשתמשים לתקן עיוותי פרספקטיבה בתמונות
        על ידי בחירת ארבע נקודות המגדירות את האזור הרצוי,
        ולבחור בין יישור הקטע הנבחר או עיוות של התמונה כולה
        באופן שמתאים אותה למסגרת המקורית, או באופן ששומר על
        גודל התוכן המעוות ומוסיף שוליים שחורים במידת הצורך.

        נבנה ע"י יהודה הלר
        מייל: yehudah@volcani.agri.gov.il
        """
        messagebox.showinfo("אודות היישום", about_text, parent=self.master)

    def pan_image_start(self, event):
        self.canvas.config(cursor="fleur")
        self.pan_start_x = event.x
        self.pan_start_y = event.y

    def pan_image_motion(self, event):
        if self.image_on_canvas:
            dx = event.x - self.pan_start_x
            dy = event.y - self.pan_start_y
            self.canvas_image_x_offset += dx
            self.canvas_image_y_offset += dy
            current_image = self.get_current_image_to_display()
            if current_image is not None:
                redraw_dots = self.get_current_image_to_display() is self.original_image_cv or self.marking_mode_active
                self.display_cv_image(current_image, clear_dots=False, redraw_existing_dots=redraw_dots)
            self.pan_start_x = event.x
            self.pan_start_y = event.y

    def pan_image_end(self, event):
        self.canvas.config(cursor="")

    def zoom_image(self, event):
        current_img_for_zoom = self.get_current_image_to_display()
        if current_img_for_zoom is None: return

        canvas_x, canvas_y = event.x, event.y
        img_top_left_on_canvas_x_before_zoom = (
                                                       self.canvas_width / 2 + self.canvas_image_x_offset) - self.displayed_image_width / 2
        img_top_left_on_canvas_y_before_zoom = (
                                                       self.canvas_height / 2 + self.canvas_image_y_offset) - self.displayed_image_height / 2
        x_on_displayed_img_before_zoom = canvas_x - img_top_left_on_canvas_x_before_zoom
        y_on_displayed_img_before_zoom = canvas_y - img_top_left_on_canvas_y_before_zoom
        ratio_x_on_img = x_on_displayed_img_before_zoom / self.displayed_image_width if self.displayed_image_width > 0 else 0.5
        ratio_y_on_img = y_on_displayed_img_before_zoom / self.displayed_image_height if self.displayed_image_height > 0 else 0.5

        zoom_change_factor = 1.1
        if event.num == 5 or event.delta < 0:
            self.zoom_factor /= zoom_change_factor
        elif event.num == 4 or event.delta > 0:
            self.zoom_factor *= zoom_change_factor
        self.zoom_factor = max(0.1, min(self.zoom_factor, 10.0))

        img_original_height, img_original_width = current_img_for_zoom.shape[:2]
        canvas_aspect_ratio = self.canvas_width / self.canvas_height if self.canvas_height > 0 else 1
        image_aspect_ratio = img_original_width / img_original_height if img_original_height > 0 else 1

        if image_aspect_ratio > canvas_aspect_ratio:
            base_display_width_no_zoom = self.canvas_width
            base_display_height_no_zoom = int(
                base_display_width_no_zoom / image_aspect_ratio) if image_aspect_ratio > 0 else 0
        else:
            base_display_height_no_zoom = self.canvas_height
            base_display_width_no_zoom = int(base_display_height_no_zoom * image_aspect_ratio)

        new_displayed_width = base_display_width_no_zoom * self.zoom_factor
        new_displayed_height = base_display_height_no_zoom * self.zoom_factor
        new_x_on_displayed_img = ratio_x_on_img * new_displayed_width
        new_y_on_displayed_img = ratio_y_on_img * new_displayed_height

        self.canvas_image_x_offset = canvas_x - (self.canvas_width / 2) + (
                new_displayed_width / 2) - new_x_on_displayed_img
        self.canvas_image_y_offset = canvas_y - (self.canvas_height / 2) + (
                new_displayed_height / 2) - new_y_on_displayed_img

        redraw_dots = self.get_current_image_to_display() is self.original_image_cv or self.marking_mode_active
        self.display_cv_image(current_img_for_zoom, clear_dots=False, redraw_existing_dots=redraw_dots)

    def get_current_image_to_display(self):
        if self.processed_image_cv is not None and not self.points:
            return self.processed_image_cv
        elif self.original_image_cv is not None:
            return self.original_image_cv
        return None

    def on_window_resize(self, event=None):
        if self.canvas.winfo_width() <= 1 or self.canvas.winfo_height() <= 1:
            self.master.after(50, self.on_window_resize)
            return
        self.canvas_width = self.canvas.winfo_width()
        self.canvas_height = self.canvas.winfo_height()
        current_image_to_resize = self.get_current_image_to_display()
        if current_image_to_resize is not None:
            redraw_dots = self.get_current_image_to_display() is self.original_image_cv or self.marking_mode_active
            self.display_cv_image(current_image_to_resize, clear_dots=False, redraw_existing_dots=redraw_dots)

    def open_image(self):
        path = filedialog.askopenfilename(
            parent=self.master, title="בחר קובץ תמונה",
            filetypes=(("קבצי תמונה", "*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tiff;*.JFIF"), ("כל הקבצים", "*.*"))
        )
        if path:
            self.image_path = path
            try:
                img_array = np.fromfile(path, np.uint8)
                self.original_image_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if self.original_image_cv is None:
                    raise ValueError("לא ניתן לטעון את התמונה.")

                self.processed_image_cv = None
                self.zoom_factor = 1.0
                self.canvas_image_x_offset = 0
                self.canvas_image_y_offset = 0

                self.master.update_idletasks()
                self.canvas_width = self.canvas.winfo_width()
                self.canvas_height = self.canvas.winfo_height()

                self.reset_points(update_status=False, reset_view=True, reset_view_and_mode=True)
                self.display_cv_image(self.original_image_cv, clear_dots=True)

                if self.marking_mode_active:  # Should be true due to reset_points
                    current_point_idx = len(self.points)  # Should be 0
                    self.status_label.config(
                        text=f"נטענה: {os.path.basename(self.image_path)}. "
                             f"סמן נקודה: {self.point_prompts[current_point_idx]} ({current_point_idx + 1}/4).")
                else:  # Fallback
                    self.status_label.config(text=f"נטענה: {os.path.basename(self.image_path)}. לחץ 'התחל סימון'.")

            except Exception as e:
                messagebox.showerror("שגיאה בפתיחת תמונה", f"אירעה שגיאה: {e}", parent=self.master)
                self.status_label.config(text="שגיאה בטעינת התמונה. נסה שוב.")
                self.original_image_cv = None
                self.disable_processing_buttons()
                self.marking_mode_active = False
                self.update_marking_mode_ui()

    def display_cv_image(self, cv_image, clear_dots=True, redraw_existing_dots=False):
        if cv_image is None:
            self.canvas.delete("all")
            self.image_on_canvas = None
            self.display_image_pil = None
            self.displayed_image_width = 0
            self.displayed_image_height = 0
            if clear_dots:
                self.clear_all_dots_from_canvas(clear_logical_points=True)
            return

        if clear_dots:
            self.clear_all_dots_from_canvas(clear_logical_points=True)
        elif not redraw_existing_dots:
            self.canvas.delete("point_marker")
            self.canvas_dots = []
            self.dot_numbers = []

        image_rgb = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        pil_image_original_size = Image.fromarray(image_rgb)
        img_original_width, img_original_height = pil_image_original_size.size

        if self.canvas.winfo_width() <= 1 or self.canvas.winfo_height() <= 1:
            self.master.update_idletasks()
            self.canvas_width = self.canvas.winfo_width()
            self.canvas_height = self.canvas.winfo_height()
            if self.canvas_width <= 1 or self.canvas_height <= 1:
                self.master.after(50, lambda: self.display_cv_image(cv_image, clear_dots, redraw_existing_dots))
                return

        canvas_aspect_ratio = self.canvas_width / self.canvas_height if self.canvas_height > 0 else 1
        image_aspect_ratio = img_original_width / img_original_height if img_original_height > 0 else 1

        if image_aspect_ratio > canvas_aspect_ratio:
            base_display_width = self.canvas_width
            base_display_height = int(base_display_width / image_aspect_ratio) if image_aspect_ratio > 0 else 0
        else:
            base_display_height = self.canvas_height
            base_display_width = int(base_display_height * image_aspect_ratio)

        self.displayed_image_width = int(base_display_width * self.zoom_factor)
        self.displayed_image_height = int(base_display_height * self.zoom_factor)
        if self.displayed_image_width <= 0: self.displayed_image_width = 1
        if self.displayed_image_height <= 0: self.displayed_image_height = 1

        try:
            resized_pil_image = pil_image_original_size.resize(
                (self.displayed_image_width, self.displayed_image_height),
                Image.LANCZOS)
        except ValueError:
            resized_pil_image = pil_image_original_size.resize(
                (self.displayed_image_width, self.displayed_image_height),
                Image.NEAREST)

        self.display_image_pil = ImageTk.PhotoImage(resized_pil_image)
        self.canvas.delete("all")
        center_x = self.canvas_width / 2 + self.canvas_image_x_offset
        center_y = self.canvas_height / 2 + self.canvas_image_y_offset
        self.image_on_canvas = self.canvas.create_image(center_x, center_y, anchor=tk.CENTER,
                                                        image=self.display_image_pil)

        if redraw_existing_dots or (
                not clear_dots and self.points and self.get_current_image_to_display() is self.original_image_cv):
            self.redraw_dots_on_canvas()

    def add_point_on_canvas(self, event):
        if not self.marking_mode_active:
            if self.original_image_cv is not None and len(self.points) < 4:
                self.status_label.config(text="מצב סימון כבוי. לחץ 'התחל סימון' כדי לבחור נקודות.")
            return

        if self.original_image_cv is None:
            self.status_label.config(text="יש לטעון תמונה תחילה.")
            return

        if self.processed_image_cv is not None and self.points:
            self.status_label.config(text="התמונה כבר עובדה. אפס נקודות או טען תמונה חדשה להתחיל מחדש.")
            return

        if len(self.points) >= 4:
            self.status_label.config(text="כבר נבחרו 4 נקודות. בחר סוג עיבוד או אפס נקודות.")
            self.marking_mode_active = False
            self.update_marking_mode_ui()
            return

        canvas_click_x, canvas_click_y = event.x, event.y
        img_actual_display_top_left_x = (
                                                self.canvas_width / 2 + self.canvas_image_x_offset) - self.displayed_image_width / 2
        img_actual_display_top_left_y = (
                                                self.canvas_height / 2 + self.canvas_image_y_offset) - self.displayed_image_height / 2
        img_actual_display_bottom_right_x = img_actual_display_top_left_x + self.displayed_image_width
        img_actual_display_bottom_right_y = img_actual_display_top_left_y + self.displayed_image_height

        if not (img_actual_display_top_left_x <= canvas_click_x < img_actual_display_bottom_right_x and \
                img_actual_display_top_left_y <= canvas_click_y < img_actual_display_bottom_right_y):
            self.status_label.config(text="יש ללחוץ בתוך גבולות התמונה.")
            return

        x_on_displayed_img = canvas_click_x - img_actual_display_top_left_x
        y_on_displayed_img = canvas_click_y - img_actual_display_top_left_y

        current_img_for_coords = self.original_image_cv
        if current_img_for_coords is None: return

        original_height_cv, original_width_cv = current_img_for_coords.shape[:2]
        original_x = int((
                                 x_on_displayed_img / self.displayed_image_width) * original_width_cv) if self.displayed_image_width > 0 else 0
        original_y = int((
                                 y_on_displayed_img / self.displayed_image_height) * original_height_cv) if self.displayed_image_height > 0 else 0

        self.points.append((original_x, original_y))
        # point_number is the count of points *after* adding the current one (1, 2, 3, or 4)
        point_number = len(self.points)

        dot_radius = 6
        dot_fill_color = "#FF4500"
        dot_outline_color = "white"
        text_color = "white"

        dot_id = self.canvas.create_oval(
            canvas_click_x - dot_radius, canvas_click_y - dot_radius,
            canvas_click_x + dot_radius, canvas_click_y + dot_radius,
            fill=dot_fill_color, outline=dot_outline_color, width=2, tags="point_marker"
        )
        self.canvas_dots.append(dot_id)

        text_id = self.canvas.create_text(
            canvas_click_x, canvas_click_y,
            text=str(point_number), fill=text_color, font=("Arial", 13, "bold"),
            tags="point_marker"
        )
        self.dot_numbers.append(text_id)

        if point_number < 4:
            point_just_marked_description = self.point_prompts[point_number - 1]
            next_point_to_mark_idx = point_number
            self.status_label.config(
                text=f"נבחרה: {point_just_marked_description} ({point_number}/4). "
                     f"כעת סמן: {self.point_prompts[next_point_to_mark_idx]}.")
        else:  # point_number == 4
            point_just_marked_description = self.point_prompts[point_number - 1]  # Last point marked (index 3)
            self.status_label.config(
                text=f"נבחרה: {point_just_marked_description} (4/4). כל 4 הנקודות נבחרו. בחר סוג עיבוד.")
            self.enable_processing_buttons()
            self.marking_mode_active = False
            self.update_marking_mode_ui()

    def redraw_dots_on_canvas(self):
        self.canvas.delete("point_marker")
        self.canvas_dots = []
        self.dot_numbers = []

        if self.original_image_cv is None or not self.points:
            return
        if self.get_current_image_to_display() is not self.original_image_cv:
            return

        original_height_cv, original_width_cv = self.original_image_cv.shape[:2]
        img_top_left_on_canvas_x = (self.canvas_width / 2 + self.canvas_image_x_offset) - self.displayed_image_width / 2
        img_top_left_on_canvas_y = (
                                           self.canvas_height / 2 + self.canvas_image_y_offset) - self.displayed_image_height / 2

        dot_radius = 6
        dot_fill_color = "#FF4500"
        dot_outline_color = "white"
        text_color = "white"

        for i, (p_orig_x, p_orig_y) in enumerate(self.points):
            x_on_displayed_img = (
                                         p_orig_x / original_width_cv) * self.displayed_image_width if original_width_cv > 0 else 0
            y_on_displayed_img = (
                                         p_orig_y / original_height_cv) * self.displayed_image_height if original_height_cv > 0 else 0
            canvas_x = img_top_left_on_canvas_x + x_on_displayed_img
            canvas_y = img_top_left_on_canvas_y + y_on_displayed_img

            dot_id = self.canvas.create_oval(
                canvas_x - dot_radius, canvas_y - dot_radius, canvas_x + dot_radius, canvas_y + dot_radius,
                fill=dot_fill_color, outline=dot_outline_color, width=2, tags="point_marker"
            )
            self.canvas_dots.append(dot_id)
            text_id = self.canvas.create_text(
                canvas_x, canvas_y, text=str(i + 1), fill=text_color, font=("Arial", 13, "bold"),
                tags="point_marker"
            )
            self.dot_numbers.append(text_id)

    def clear_all_dots_from_canvas(self, clear_logical_points=True):
        self.canvas.delete("point_marker")
        self.canvas_dots = []
        self.dot_numbers = []
        if clear_logical_points:
            self.points = []

    def reset_points(self, update_status=True, reset_view=True, reset_view_and_mode=False):
        if reset_view_and_mode:
            reset_view = True

        self.clear_all_dots_from_canvas(clear_logical_points=True)
        self.disable_processing_buttons()

        if self.original_image_cv is not None:
            self.processed_image_cv = None
            if reset_view:
                self.zoom_factor = 1.0
                self.canvas_image_x_offset = 0
                self.canvas_image_y_offset = 0
            self.display_cv_image(self.original_image_cv, clear_dots=False, redraw_existing_dots=False)

            if reset_view_and_mode:
                self.marking_mode_active = True

            self.update_marking_mode_ui()

            if update_status:
                if self.marking_mode_active:
                    current_point_idx = len(self.points)  # Should be 0 after clear_logical_points
                    self.status_label.config(
                        text=f"הנקודות אופסו. סמן נקודה: {self.point_prompts[current_point_idx]} ({current_point_idx + 1}/4).")
                else:
                    self.status_label.config(text="הנקודות אופסו. לחץ 'התחל סימון' לבחירה מחדש.")
        elif update_status:
            self.status_label.config(text="אין תמונה טעונה לאיפוס נקודות.")
            self.marking_mode_active = False
            self.update_marking_mode_ui()

    def process_image_cropped(self):
        if len(self.points) != 4 or self.original_image_cv is None:
            messagebox.showwarning("יישור קטע", "יש לסמן 4 נקודות על תמונה מקורית בסדר המבוקש.",
                                   parent=self.master)  # Updated message
            self.status_label.config(
                text="סמן 4 נקודות (שמאל למעלה, ימין למעלה, ימין למטה, שמאל למטה).")  # Updated message
            return
        try:
            src_points_np = np.float32(self.points)
            width_top = np.linalg.norm(src_points_np[0] - src_points_np[1])
            width_bottom = np.linalg.norm(src_points_np[3] - src_points_np[2])
            max_width = max(int(width_top), int(width_bottom))

            height_left = np.linalg.norm(src_points_np[0] - src_points_np[3])
            height_right = np.linalg.norm(src_points_np[1] - src_points_np[2])
            max_height = max(int(height_left), int(height_right))

            if max_width <= 0 or max_height <= 0:
                messagebox.showerror("שגיאה בחישוב מידות", "לא ניתן לחשב מידות חוקיות.", parent=self.master)
                self.status_label.config(text="שגיאה בחישוב מידות יעד. אפס ונסה שוב.")
                self.clear_all_dots_from_canvas(clear_logical_points=True)
                self.disable_processing_buttons()
                self.marking_mode_active = False
                self.update_marking_mode_ui()
                return

            dst_points_np = np.float32(
                [[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]])
            perspective_matrix = cv2.getPerspectiveTransform(src_points_np, dst_points_np)
            self.processed_image_cv = cv2.warpPerspective(self.original_image_cv, perspective_matrix,
                                                          (max_width, max_height), flags=cv2.INTER_LANCZOS4)

            self.clear_all_dots_from_canvas(clear_logical_points=True)
            self.disable_processing_buttons()
            self.marking_mode_active = False
            self.update_marking_mode_ui()

            self.zoom_factor = 1.0
            self.canvas_image_x_offset = 0
            self.canvas_image_y_offset = 0
            self.display_cv_image(self.processed_image_cv, clear_dots=True)
            self.status_label.config(text="יישור קטע הושלם. ניתן לשמור או לאפס נקודות.")

        except Exception as e:
            messagebox.showerror("שגיאה ביישור קטע", f"אירעה שגיאה: {e}", parent=self.master)
            self.status_label.config(text="שגיאה ביישור קטע. נסה לאפס נקודות.")
            self.disable_processing_buttons()
            self.marking_mode_active = False
            self.update_marking_mode_ui()

    def process_image_full_transform(self):
        if len(self.points) != 4 or self.original_image_cv is None:
            messagebox.showwarning("עיוות תמונה מלאה", "יש לסמן 4 נקודות על תמונה מקורית בסדר המבוקש.",
                                   # Updated message
                                   parent=self.master)
            self.status_label.config(
                text="סמן 4 נקודות (שמאל למעלה, ימין למעלה, ימין למטה, שמאל למטה).")  # Updated message
            return

        try:
            src_points_np = np.float32(self.points)
            original_height, original_width = self.original_image_cv.shape[:2]

            width_top = np.linalg.norm(src_points_np[0] - src_points_np[1])
            width_bottom = np.linalg.norm(src_points_np[3] - src_points_np[2])
            rect_width = max(int(width_top), int(width_bottom))

            height_left = np.linalg.norm(src_points_np[0] - src_points_np[3])
            height_right = np.linalg.norm(src_points_np[1] - src_points_np[2])
            rect_height = max(int(height_left), int(height_right))

            if rect_width <= 0 or rect_height <= 0:
                messagebox.showerror("שגיאה בחישוב מידות", "לא ניתן לחשב מידות חוקיות עבור המרובע הנבחר.",
                                     parent=self.master)
                self.status_label.config(text="שגיאה בחישוב מידות מרובע. אפס ונסה שוב.")
                self.disable_processing_buttons()
                self.marking_mode_active = False
                self.update_marking_mode_ui()
                return

            center_src_x = np.mean(src_points_np[:, 0])
            center_src_y = np.mean(src_points_np[:, 1])

            dst_ideal_tl_x = center_src_x - rect_width / 2
            dst_ideal_tl_y = center_src_y - rect_height / 2
            dst_ideal_tr_x = center_src_x + rect_width / 2
            dst_ideal_tr_y = center_src_y - rect_height / 2
            dst_ideal_br_x = center_src_x + rect_width / 2
            dst_ideal_br_y = center_src_y + rect_height / 2
            dst_ideal_bl_x = center_src_x - rect_width / 2
            dst_ideal_bl_y = center_src_y + rect_height / 2

            dst_points_ideal_shape = np.float32([
                [dst_ideal_tl_x, dst_ideal_tl_y],
                [dst_ideal_tr_x, dst_ideal_tr_y],
                [dst_ideal_br_x, dst_ideal_br_y],
                [dst_ideal_bl_x, dst_ideal_bl_y]
            ])

            M1 = cv2.getPerspectiveTransform(src_points_np, dst_points_ideal_shape)
            if M1 is None:
                raise ValueError("לא ניתן לחשב את טרנספורמציית הפרספקטיבה הראשונית. ייתכן שהנקודות קו-לינאריות.")

            status_text = ""  # Initialize status_text
            if self.full_transform_fit_to_frame_var.get():
                dst_tl_x = center_src_x - rect_width / 2
                dst_tl_y = center_src_y - rect_height / 2
                dst_tr_x = center_src_x + rect_width / 2
                dst_tr_y = center_src_y - rect_height / 2
                dst_br_x = center_src_x + rect_width / 2
                dst_br_y = center_src_y + rect_height / 2
                dst_bl_x = center_src_x - rect_width / 2
                dst_bl_y = center_src_y + rect_height / 2

                dst_points_rect_in_place = np.float32([
                    [dst_tl_x, dst_tl_y],
                    [dst_tr_x, dst_tr_y],
                    [dst_br_x, dst_br_y],
                    [dst_bl_x, dst_bl_y]
                ])

                perspective_matrix_fit = cv2.getPerspectiveTransform(src_points_np, dst_points_rect_in_place)
                if perspective_matrix_fit is None:
                    raise ValueError("לא ניתן לחשב את טרנספורמציית ההתאמה למסגרת.")

                self.processed_image_cv = cv2.warpPerspective(
                    self.original_image_cv,
                    perspective_matrix_fit,
                    (original_width, original_height),
                    flags=cv2.INTER_LANCZOS4,
                    borderMode=cv2.BORDER_REPLICATE
                )
                status_text = "הפרספקטיבה של כל התמונה שונתה והותאמה למסגרת המקורית. ניתן לשמור."
            else:
                original_img_corners = np.float32([
                    [0, 0],
                    [original_width - 1, 0],
                    [original_width - 1, original_height - 1],
                    [0, original_height - 1]
                ]).reshape(-1, 1, 2)

                transformed_img_corners = cv2.perspectiveTransform(original_img_corners, M1)
                if transformed_img_corners is None:
                    raise ValueError("לא ניתן היה לבצע טרנספורמציה על פינות התמונה.")

                min_x_warped = np.min(transformed_img_corners[:, 0, 0])
                max_x_warped = np.max(transformed_img_corners[:, 0, 0])
                min_y_warped = np.min(transformed_img_corners[:, 0, 1])
                max_y_warped = np.max(transformed_img_corners[:, 0, 1])

                warped_content_width = int(max_x_warped - min_x_warped)
                warped_content_height = int(max_y_warped - min_y_warped)

                if warped_content_width <= 0 or warped_content_height <= 0:
                    raise ValueError("לתמונה שעברה טרנספורמציה אין מידות חוקיות (רוחב או גובה קטן מדי).")

                translation_matrix = np.float32([
                    [1, 0, -min_x_warped],
                    [0, 1, -min_y_warped],
                    [0, 0, 1]
                ])
                M_final = translation_matrix @ M1

                self.processed_image_cv = cv2.warpPerspective(
                    self.original_image_cv,
                    M_final,
                    (warped_content_width, warped_content_height),
                    flags=cv2.INTER_LANCZOS4,
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=(0, 0, 0)
                )
                status_text = "הפרספקטיבה של כל התמונה שונתה (גודל הפלט בהתאם לתוכן). ניתן לשמור."

            self.clear_all_dots_from_canvas(clear_logical_points=True)
            self.disable_processing_buttons()
            self.marking_mode_active = False
            self.update_marking_mode_ui()

            self.zoom_factor = 1.0
            self.canvas_image_x_offset = 0
            self.canvas_image_y_offset = 0
            self.display_cv_image(self.processed_image_cv, clear_dots=True)
            self.status_label.config(text=status_text)

        except ValueError as ve:
            error_message = f"אירעה שגיאה בחישוב הטרנספורמציה: {ve}\nייתכן שהנקודות שנבחרו אינן תקינות או קו-לינאריות."
            messagebox.showerror("שגיאה בעיבוד", error_message, parent=self.master)
            self.status_label.config(text="שגיאה בעיבוד. נסה נקודות אחרות או אפס.")
            self.disable_processing_buttons()
            self.marking_mode_active = False
            self.update_marking_mode_ui()
        except Exception as e:
            messagebox.showerror("שגיאה בשינוי פרספקטיבה מלאה", f"אירעה שגיאה בלתי צפויה: {e}", parent=self.master)
            self.status_label.config(text="שגיאה בשינוי פרספקטיבה מלאה. נסה לאפס נקודות.")
            self.disable_processing_buttons()
            self.marking_mode_active = False
            self.update_marking_mode_ui()

    def save_image(self):
        if self.processed_image_cv is None:
            messagebox.showwarning("שמירת תמונה", "אין תמונה מעובדת לשמירה.", parent=self.master)
            self.status_label.config(text="אין תמונה מעובדת לשמירה.")
            return

        original_filename = os.path.basename(self.image_path) if self.image_path else "image"
        base_name, ext = os.path.splitext(original_filename)
        suggested_filename = f"{base_name}_corrected.png"

        file_path = filedialog.asksaveasfilename(
            parent=self.master, initialfile=suggested_filename, defaultextension=".png",
            filetypes=(("PNG files", "*.png"), ("JPEG files", "*.jpg;*.jpeg"), ("BMP files", "*.bmp"),
                       ("TIFF files", "*.tiff"), ("JFIF files", "*.jfif"), ("All files", "*.*")),
            title="שמור תמונה מעובדת כ..."
        )
        if file_path:
            try:
                file_ext_for_encode = os.path.splitext(file_path)[1].lower()
                if file_ext_for_encode not in [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".jfif"]:
                    file_ext_for_encode = ".png"

                is_success, im_buf_arr = cv2.imencode(file_ext_for_encode, self.processed_image_cv)
                if is_success:
                    im_buf_arr.tofile(file_path)
                    self.status_label.config(text=f"התמונה נשמרה ב: {file_path}")
                    messagebox.showinfo("שמירה הושלמה", f"התמונה נשמרה בהצלחה:\n{file_path}", parent=self.master)
                else:
                    raise Exception(f"שגיאה בקידוד התמונה לסיומת {file_ext_for_encode.upper()}.")
            except Exception as e:
                messagebox.showerror("שגיאה בשמירת תמונה", f"אירעה שגיאה: {e}", parent=self.master)
                self.status_label.config(text="שגיאה בשמירת התמונה.")


if __name__ == '__main__':
    root = tk.Tk()
    app = PerspectiveCorrectionApp(root)
    root.mainloop()