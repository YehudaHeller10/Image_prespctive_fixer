import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np


class PerspectiveApp:
    def __init__(self, root):
        self.root = root
        self.root.title("מדידת מרחק אחרי תיקון פרספקטיבה")

        # Zoom and Pan
        self.zoom = 1.0
        self.min_zoom = 0.05
        self.max_zoom = 20.0
        self._pan_start_x = None
        self._pan_start_y = None

        # Images and state
        self.image_path = None
        self.img_original_bgr = None
        self.img_transformed_bgr = None
        self.photo_img = None

        self.points = []
        self.measure_points = []
        self.calibrated = False
        self.scale = None

        # Control Frame
        control_frame = tk.Frame(root)
        control_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

        # --- BEGIN MODIFICATION FOR ENTRY TRACING ---
        self.width_cm_var = tk.StringVar()
        self.height_cm_var = tk.StringVar()

        # Call _update_button_states whenever the content of the StringVars changes
        self.width_cm_var.trace_add("write", self._on_entry_change)
        self.height_cm_var.trace_add("write", self._on_entry_change)

        tk.Label(control_frame, text="רוחב ייחוס (ס\"מ):").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.entry_width_cm = tk.Entry(control_frame, width=10, textvariable=self.width_cm_var)
        self.entry_width_cm.grid(row=0, column=1, padx=5, pady=2)

        tk.Label(control_frame, text="גובה ייחוס (ס\"מ):").grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.entry_height_cm = tk.Entry(control_frame, width=10, textvariable=self.height_cm_var)
        self.entry_height_cm.grid(row=1, column=1, padx=5, pady=2)
        # --- END MODIFICATION FOR ENTRY TRACING ---

        self.load_button = tk.Button(control_frame, text="טען תמונה", command=self.load_image)
        self.load_button.grid(row=0, column=2, padx=5, pady=2, rowspan=2, ipady=5)

        self.perspective_button = tk.Button(control_frame, text="בצע תיקון פרספקטיבה", command=self.do_perspective,
                                            state=tk.DISABLED)
        self.perspective_button.grid(row=0, column=3, padx=5, pady=2, rowspan=2, ipady=5)

        self.measure_button = tk.Button(control_frame, text="אפשר/אפס מדידה", command=self.enable_measure_mode,
                                        state=tk.DISABLED)
        self.measure_button.grid(row=0, column=4, padx=5, pady=2, rowspan=2, ipady=5)

        self.status_bar = tk.Label(root, text="טען תמונה כדי להתחיל", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas = tk.Canvas(root, cursor="cross", bg="gray")
        self.canvas.pack(expand=True, fill=tk.BOTH)

        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Button-4>", self.on_mousewheel)
        self.canvas.bind("<Button-5>", self.on_mousewheel)
        self.canvas.bind("<ButtonPress-2>", self.on_pan_start)
        self.canvas.bind("<B2-Motion>", self.on_pan_move)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_end)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.root.bind("<Configure>", self.on_root_resize)

        # Initial call to set button states correctly if app starts with some values (not typical here)
        self._update_button_states()

    # --- NEW METHOD TO HANDLE ENTRY CHANGES ---
    def _on_entry_change(self, *args):
        # The trace passes arguments like (name, index, mode), we don't need them.
        self._update_button_states()

    def _update_status(self, message):
        self.status_bar.config(text=message)

    def _update_button_states(self):
        # Use the StringVars to get current values
        width_val = self.width_cm_var.get()
        height_val = self.height_cm_var.get()

        # Check if image is loaded before accessing its properties
        img_loaded = self.img_original_bgr is not None

        can_do_perspective = len(self.points) == 4 and \
                             img_loaded and \
                             width_val and \
                             height_val

        # Debug print to help diagnose state issues:
        # print(f"Updating button states: points={len(self.points)}, img_loaded={img_loaded}, width='{width_val}', height='{height_val}', can_do_perspective={can_do_perspective}, calibrated={self.calibrated}")

        self.perspective_button.config(state=tk.NORMAL if can_do_perspective else tk.DISABLED)
        self.measure_button.config(state=tk.NORMAL if self.calibrated else tk.DISABLED)

    def load_image(self):
        file_path = filedialog.askopenfilename(
            title="בחר קובץ תמונה",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.tiff;*.webp"), ("All files", "*.*")]
        )
        if not file_path:
            return

        img = cv2.imread(file_path)
        if img is None:
            messagebox.showerror("שגיאה", "לא ניתן לטעון את התמונה. בדוק שהקובץ תקין ושהנתיב נכון.")
            return

        self.image_path = file_path
        self.img_original_bgr = img
        self.img_transformed_bgr = None
        self.calibrated = False
        self.scale = None
        self.points = []
        self.measure_points = []

        # Clear entry fields when loading a new image
        self.width_cm_var.set("")
        self.height_cm_var.set("")

        self.zoom = 1.0
        self.canvas.delete("all")

        self._update_status(f"תמונה נטענה: {file_path}. בחר 4 נקודות על אובייקט ייחוס והזן מידותיו.")
        self.display_image(self.img_original_bgr, fit_to_canvas=True)
        # _update_button_states() will be called by display_image via _redraw_annotations,
        # and also by StringVars being cleared if that happens after display_image starts.
        # Explicit call here ensures it reflects cleared entries immediately if needed.
        self._update_button_states()

    def display_image(self, img_bgr_to_display, fit_to_canvas=False):
        if img_bgr_to_display is None:
            self.canvas.delete("all")
            self._update_status("אין תמונה להצגה.")
            # Ensure buttons are updated if no image is displayed
            if not hasattr(self, 'called_from_load_or_perspective'):  # Avoid redundant calls
                self._update_button_states()
            return

        self.called_from_load_or_perspective = fit_to_canvas  # A flag to manage updates

        img_h_orig, img_w_orig = img_bgr_to_display.shape[:2]

        if fit_to_canvas:
            if self.canvas.winfo_width() <= 1 or self.canvas.winfo_height() <= 1:
                self.root.after(50, lambda: self.display_image(img_bgr_to_display, True))
                return

            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()

            scale_w = canvas_w / img_w_orig
            scale_h = canvas_h / img_h_orig
            self.zoom = min(scale_w, scale_h)
            self.zoom = max(self.min_zoom, min(self.zoom, self.max_zoom))

        img_rgb = cv2.cvtColor(img_bgr_to_display, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)

        zoomed_w = int(img_w_orig * self.zoom)
        zoomed_h = int(img_h_orig * self.zoom)

        resampling_filter = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS
        img_resized_pil = pil_img.resize((zoomed_w, zoomed_h), resampling_filter)

        self.photo_img = ImageTk.PhotoImage(img_resized_pil)
        self.canvas.delete("all")
        self.canvas.config(scrollregion=(0, 0, zoomed_w, zoomed_h))
        self.canvas.create_image(0, 0, image=self.photo_img, anchor="nw", tags="displayed_image")

        self._redraw_annotations()  # This will call _update_button_states()

        if hasattr(self, 'called_from_load_or_perspective'):
            del self.called_from_load_or_perspective

    def _redraw_annotations(self):
        self.canvas.delete("annotation")

        marker_radius_canvas = 5

        if not self.calibrated and self.img_original_bgr is not None:
            for i, (x_orig, y_orig) in enumerate(self.points):
                x_cv = x_orig * self.zoom
                y_cv = y_orig * self.zoom
                self.canvas.create_oval(x_cv - marker_radius_canvas, y_cv - marker_radius_canvas,
                                        x_cv + marker_radius_canvas, y_cv + marker_radius_canvas,
                                        outline='red', width=2, tags=("annotation", "perspective_point"))
                self.canvas.create_text(x_cv + marker_radius_canvas, y_cv - marker_radius_canvas,
                                        text=str(i + 1), fill='red', anchor='nw',
                                        font=('Arial', 10, 'bold'), tags=("annotation", "perspective_point_text"))

            if len(self.points) == 4:
                poly_pts_scaled = []
                for (x_orig, y_orig) in self.points:
                    poly_pts_scaled.extend([x_orig * self.zoom, y_orig * self.zoom])
                self.canvas.create_polygon(poly_pts_scaled, outline='blue', fill='', width=2,
                                           tags=("annotation", "perspective_polygon"))

        if self.calibrated and self.img_transformed_bgr is not None:
            for i, (x_transformed, y_transformed) in enumerate(self.measure_points):
                x_cv = x_transformed * self.zoom
                y_cv = y_transformed * self.zoom
                self.canvas.create_oval(x_cv - marker_radius_canvas, y_cv - marker_radius_canvas,
                                        x_cv + marker_radius_canvas, y_cv + marker_radius_canvas,
                                        outline='lime green', width=2, tags=("annotation", "measure_point"))

            if len(self.measure_points) == 2:
                p1_trans, p2_trans = self.measure_points[0], self.measure_points[1]
                dist_px = np.hypot(p2_trans[0] - p1_trans[0], p2_trans[1] - p1_trans[1])
                if self.scale is not None and self.scale > 0:  # Ensure scale is valid
                    dist_cm = dist_px / self.scale
                    dist_text = f"{dist_cm:.3f} ס\"מ"
                else:
                    dist_text = "שגיאת קנה מידה"

                x1_cv, y1_cv = p1_trans[0] * self.zoom, p1_trans[1] * self.zoom
                x2_cv, y2_cv = p2_trans[0] * self.zoom, p2_trans[1] * self.zoom

                mid_x_cv = (x1_cv + x2_cv) / 2
                mid_y_cv = (y1_cv + y2_cv) / 2

                self.canvas.create_line(x1_cv, y1_cv, x2_cv, y2_cv, fill='lime green', width=2,
                                        tags=("annotation", "measure_line"))
                self.canvas.create_text(mid_x_cv + 10, mid_y_cv, text=dist_text,
                                        fill='lime green', font=('Arial', 14, 'bold'), anchor='w',
                                        tags=("annotation", "measure_text"))

        # Crucial: update button states after any potential change in points, calibration, etc.
        self._update_button_states()

    def order_points(self, pts):
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect

    def do_perspective(self):
        if len(self.points) != 4:
            messagebox.showwarning("שגיאה", "יש לבחור בדיוק 4 נקודות ייחוס.")
            return

        try:
            # Get values from StringVars
            w_cm = float(self.width_cm_var.get())
            h_cm = float(self.height_cm_var.get())
            if w_cm <= 0 or h_cm <= 0:
                raise ValueError("Dimensions must be positive.")
        except ValueError:
            messagebox.showerror("קלט לא חוקי", "מידות רוחב וגובה הייחוס חייבות להיות מספרים חיוביים.")
            return

        src_pts_np = np.array(self.points, dtype=np.float32)
        src_ordered = self.order_points(src_pts_np)

        ref_obj_pixels_per_cm = 75.0
        max_dim_ref_obj_px = 1500.0

        if w_cm > 0: ref_obj_pixels_per_cm = min(ref_obj_pixels_per_cm, max_dim_ref_obj_px / w_cm)
        if h_cm > 0: ref_obj_pixels_per_cm = min(ref_obj_pixels_per_cm, max_dim_ref_obj_px / h_cm)

        rect_w_px = int(round(w_cm * ref_obj_pixels_per_cm))
        rect_h_px = int(round(h_cm * ref_obj_pixels_per_cm))

        dst_rect_pts = np.array([
            [0, 0],
            [rect_w_px - 1, 0],
            [rect_w_px - 1, rect_h_px - 1],
            [0, rect_h_px - 1]
        ], dtype=np.float32)

        M = cv2.getPerspectiveTransform(src_ordered, dst_rect_pts)

        h_orig, w_orig = self.img_original_bgr.shape[:2]

        original_img_corners = np.array([
            [0, 0], [w_orig - 1, 0],
            [w_orig - 1, h_orig - 1], [0, h_orig - 1]
        ], dtype=np.float32)

        original_img_corners_reshaped = original_img_corners.reshape(-1, 1, 2)
        transformed_img_corners = cv2.perspectiveTransform(original_img_corners_reshaped, M)

        min_x_transformed = np.min(transformed_img_corners[:, 0, 0])
        max_x_transformed = np.max(transformed_img_corners[:, 0, 0])
        min_y_transformed = np.min(transformed_img_corners[:, 0, 1])
        max_y_transformed = np.max(transformed_img_corners[:, 0, 1])

        output_w_px = int(np.ceil(max_x_transformed - min_x_transformed))
        output_h_px = int(np.ceil(max_y_transformed - min_y_transformed))

        translation_matrix = np.array([
            [1, 0, -min_x_transformed],
            [0, 1, -min_y_transformed],
            [0, 0, 1]
        ], dtype=np.float32)

        M_final = translation_matrix @ M

        self.img_transformed_bgr = cv2.warpPerspective(self.img_original_bgr, M_final, (output_w_px, output_h_px),
                                                       flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)

        self.calibrated = True
        self.scale = ref_obj_pixels_per_cm
        self.measure_points = []

        self._update_status(f"פרספקטיבה תוקנה. קנה מידה: {self.scale:.3f} פיקסלים/ס\"מ. לחץ 'אפשר/אפס מדידה'.")
        self.display_image(self.img_transformed_bgr, fit_to_canvas=True)
        self.enable_measure_mode()

    def enable_measure_mode(self):
        if not self.calibrated:
            messagebox.showwarning("נדרש כיול", "יש לבצע תיקון פרספקטיבה תחילה.")
            return
        self.measure_points = []
        current_img = self.img_transformed_bgr if self.calibrated else self.img_original_bgr
        if current_img is not None:
            self.display_image(current_img)
        self._update_status("מצב מדידה פעיל. בחר 2 נקודות למדוד מרחק.")
        self._update_button_states()  # Ensure button states are correct

    def on_canvas_click(self, event):
        current_img_displaying = self.img_transformed_bgr if self.calibrated else self.img_original_bgr
        if current_img_displaying is None:
            return

        img_x_coord = int(self.canvas.canvasx(event.x) / self.zoom)
        img_y_coord = int(self.canvas.canvasy(event.y) / self.zoom)

        h_disp, w_disp = current_img_displaying.shape[:2]
        if not (0 <= img_x_coord < w_disp and 0 <= img_y_coord < h_disp):
            return

        if not self.calibrated:
            if len(self.points) >= 4:
                messagebox.showinfo("מידע", "נבחרו 4 נקודות. לחץ 'בצע תיקון פרספקטיבה' או טען תמונה מחדש לאיפוס.")
                # No change to points, button state will remain based on current entries
                self._update_button_states()  # Re-check in case entries changed without focus out
                return
            self.points.append((img_x_coord, img_y_coord))
            if len(self.points) == 4:
                self._update_status("נבחרו 4 נקודות. הזן מידות ולחץ 'בצע תיקון פרספקטיבה'.")
            else:
                self._update_status(f"נבחרה נקודה {len(self.points)}/4. בחר נקודות נוספות.")
        else:
            if len(self.measure_points) >= 2:
                self.measure_points = []

            self.measure_points.append((img_x_coord, img_y_coord))
            if len(self.measure_points) == 1:
                self._update_status("נקודה ראשונה למדידה נבחרה. בחר נקודה שנייה.")
            elif len(self.measure_points) == 2:
                self._update_status("מדידה הושלמה. לחץ שוב להתחלת מדידה חדשה.")

        # display_image will call _redraw_annotations, which calls _update_button_states
        self.display_image(current_img_displaying)

    def on_mousewheel(self, event):
        if self.img_original_bgr is None and self.img_transformed_bgr is None: return  # Check if any image is loaded

        if event.num == 4 or event.delta > 0:
            factor = 1.1
        elif event.num == 5 or event.delta < 0:
            factor = 0.9
        else:
            return

        new_zoom = self.zoom * factor
        self.zoom = max(self.min_zoom, min(new_zoom, self.max_zoom))

        current_img = self.img_transformed_bgr if self.calibrated else self.img_original_bgr
        if current_img is not None:
            self.display_image(current_img)

    def on_pan_start(self, event):
        self.canvas.scan_mark(event.x, event.y)
        self.canvas.config(cursor="fleur")

    def on_pan_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def on_pan_end(self, event):
        self.canvas.config(cursor="cross")

    def on_root_resize(self, event=None):
        current_img = self.img_transformed_bgr if self.calibrated else self.img_original_bgr
        if current_img is not None:
            self.display_image(current_img, fit_to_canvas=False)


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1000x750")
    app = PerspectiveApp(root)
    root.mainloop()