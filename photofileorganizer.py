import os
import sys
import shutil
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps
import send2trash


class PhotoSorterApp:
    ZOOM_LEVELS = [60, 80, 100, 120, 150, 180, 220, 270, 330, 400]  # thumbnail sizes (px)
    DEFAULT_THUMB = 150
    DRAG_THRESHOLD = 5   # px the pointer must move before a click turns into a box-drag

    ZOOM_IN_KEYS = ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>")
    ZOOM_OUT_KEYS = ("<Control-minus>", "<Control-KP_Subtract>")
    ZOOM_RESET_KEYS = ("<Control-Key-0>", "<Control-KP_0>")

    # THUMB / CELL / CELL_PAD are instance attributes (set by set_thumb_size)
    # because the thumbnail size can be changed with Ctrl +/-.

    def __init__(self, root):
        self.root = root
        self.root.title("Simple Photo Sorter")
        self.root.geometry("1100x800")
        self.root.minsize(700, 600)

        # Load configuration
        self.config_file = "config.json"
        self.config = self.load_config()

        # Gallery zoom (thumbnail size)
        try:
            size = int(self.config.get("thumb_size", self.DEFAULT_THUMB))
        except (TypeError, ValueError):
            size = self.DEFAULT_THUMB
        self.set_thumb_size(size)

        # Application state
        self.source_dir = self.config.get("source_dir", "")
        self.mappings = self.config.get("mappings", {str(i): "" for i in range(1, 10)})

        # Keep mappings as strings in internal state
        self.mappings = {str(k): v for k, v in self.mappings.items()}
        for i in range(1, 10):
            if str(i) not in self.mappings:
                self.mappings[str(i)] = ""

        self.mode = "config"  # "config" | "gallery" | "viewer"
        self.photos = []
        self.current_index = 0
        self.last_viewed_photo = ""
        self.current_image_obj = None
        self.resize_job = None
        self.canvas = None

        # Gallery state
        self.selected = set()
        self.thumb_cache = {}
        self.gallery_canvas = None
        self.gallery_items = {}
        self.gallery_cols = 1
        self.gallery_xoff = 0
        self.gallery_total_h = 1
        self.thumb_job = None
        self.gallery_resize_job = None
        self.last_clicked_index = None
        self.gallery_info_label = None
        self._drag = None            # active click / box-selection gesture
        self._autoscroll_job = None
        self._click_undo = None      # (path, was_selected) of the last plain click

        # GIF Animation state
        self.gif_frames = []
        self.gif_durations = []
        self.gif_frame_index = 0
        self.gif_animation_id = None

        # Subfolder search state
        self.subfolder_search_var = None
        self.subfolder_buttons_frame = None
        self.subfolder_panel = None
        self.source_subfolders = []

        # Setup modern ttk styles
        self.setup_styles()

        # Main container
        self.main_container = tk.Frame(self.root, bg="#f5f6fa")
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # Create screens
        self.config_frame = tk.Frame(self.main_container, bg="#f5f6fa")
        self.gallery_frame = tk.Frame(self.main_container, bg="#1e272e")
        self.viewer_frame = tk.Frame(self.main_container, bg="#1e272e")  # Dark background for photos

        # Show configuration screen initially
        self.show_config_screen()

    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Colors
        bg_light = "#f5f6fa"
        primary = "#3498db"
        primary_active = "#2980b9"
        accent = "#2ecc71"
        accent_active = "#27ae60"
        dark_gray = "#2f3640"

        # Configure Ttk Styles
        self.style.configure(".", background=bg_light, font=("Segoe UI", 10))
        self.style.configure("TLabel", background=bg_light, foreground=dark_gray)
        self.style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), foreground="#2c3e50")
        self.style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground="#34495e")
        self.style.configure("Mapping.TLabel", font=("Segoe UI", 10, "bold"), foreground="#34495e")

        # Accent button (Start sorting)
        self.style.configure("Action.TButton", font=("Segoe UI", 11, "bold"), background=accent, foreground="white")
        self.style.map("Action.TButton",
            background=[("active", accent_active)],
            foreground=[("active", "white")]
        )

        # Standard buttons
        self.style.configure("Browse.TButton", font=("Segoe UI", 9), background=primary, foreground="white")
        self.style.map("Browse.TButton",
            background=[("active", primary_active)],
            foreground=[("active", "white")]
        )

        self.style.configure("Clear.TButton", font=("Segoe UI", 9), background="#e74c3c", foreground="white")
        self.style.map("Clear.TButton",
            background=[("active", "#c0392b")],
            foreground=[("active", "white")]
        )

        self.style.configure("Back.TButton", font=("Segoe UI", 9, "bold"), background="#7f8c8d", foreground="white")
        self.style.map("Back.TButton",
            background=[("active", "#95a5a6")],
            foreground=[("active", "white")]
        )

        self.style.configure("Tool.TButton", font=("Segoe UI", 9, "bold"), background="#3d4f5c", foreground="white")
        self.style.map("Tool.TButton",
            background=[("active", "#5d6d7e")],
            foreground=[("active", "white")]
        )

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config.json: {e}")
        return {}

    def save_config(self):
        config_data = {
            "source_dir": self.source_dir,
            "mappings": self.mappings,
            "thumb_size": self.THUMB
        }
        try:
            with open(self.config_file, "w") as f:
                json.dump(config_data, f, indent=4)
        except Exception as e:
            print(f"Error saving config.json: {e}")

    # ================= HOTKEY HELPERS =================
    def unbind_hotkeys(self, keep_escape=False):
        try:
            if not keep_escape:
                self.root.unbind("<Escape>")
            self.root.unbind("<Left>")
            self.root.unbind("<Right>")
            self.root.unbind("<Delete>")
            self.root.unbind("<r>")
            self.root.unbind("<R>")
            self.root.unbind("<Control-a>")
            self.root.unbind("<Control-A>")
            for seq in self.ZOOM_IN_KEYS + self.ZOOM_OUT_KEYS + self.ZOOM_RESET_KEYS:
                self.root.unbind(seq)
            for i in range(1, 10):
                self.root.unbind(str(i))
                self.root.unbind(f"<KP_{i}>")
        except Exception:
            pass

    def bind_hotkeys(self):
        self.unbind_hotkeys()
        if self.mode == "gallery":
            self.root.bind("<Escape>", lambda e: self.show_config_screen())
            self.root.bind("<Delete>", self.delete_selected_images)
            self.root.bind("<Control-a>", self.select_all)
            self.root.bind("<Control-A>", self.select_all)
            for seq in self.ZOOM_IN_KEYS:
                self.root.bind(seq, lambda e: self.zoom_gallery(+1))
            for seq in self.ZOOM_OUT_KEYS:
                self.root.bind(seq, lambda e: self.zoom_gallery(-1))
            for seq in self.ZOOM_RESET_KEYS:
                self.root.bind(seq, lambda e: self.reset_gallery_zoom())
            for i in range(1, 10):
                self.root.bind(str(i), self.gallery_num_press)
                self.root.bind(f"<KP_{i}>", self.gallery_num_press)
        elif self.mode == "viewer":
            self.root.bind("<Left>", self.prev_image)
            self.root.bind("<Right>", self.next_image)
            self.root.bind("<Escape>", lambda e: self.show_gallery_screen())
            self.root.bind("<Delete>", self.delete_current_image)
            self.root.bind("<r>", self.rotate_current_image)
            self.root.bind("<R>", self.rotate_current_image)
            for i in range(1, 10):
                self.root.bind(str(i), self.handle_num_press)
                self.root.bind(f"<KP_{i}>", self.handle_num_press)

    def _key_from_event(self, event):
        key = event.char
        if not key or key not in self.mappings:
            keysym = event.keysym
            if keysym.startswith("KP_") and keysym[3:].isdigit():
                return keysym[3:]
            return None
        return key

    def active_canvas(self):
        return self.gallery_canvas if self.mode == "gallery" else self.canvas

    # ================= CONFIGURATION SCREEN =================
    def show_config_screen(self):
        # Cancel any active GIF animations / gallery jobs
        self.cancel_gif_animation()
        self._cancel_gallery_jobs()
        self.mode = "config"

        # Unbind hotkeys
        self.unbind_hotkeys()

        # Clean frames
        self.viewer_frame.pack_forget()
        self.gallery_frame.pack_forget()
        self.config_frame.pack(fill=tk.BOTH, expand=True, padx=25, pady=25)

        # Clear existing config frame children to rebuild cleanly
        for widget in self.config_frame.winfo_children():
            widget.destroy()

        # Title Header
        header = ttk.Label(self.config_frame, text="Simple Photo Sorter Settings", style="Header.TLabel")
        header.pack(anchor="w", pady=(0, 20))

        # Source Directory Card/Frame
        src_card = tk.LabelFrame(self.config_frame, text=" 1. Select Source Folder ", font=("Segoe UI", 10, "bold"), bg="#f5f6fa", fg="#34495e", padx=15, pady=15)
        src_card.pack(fill="x", pady=(0, 20))

        self.src_entry_var = tk.StringVar(value=self.source_dir)
        self.src_entry_var.trace_add("write", self._on_source_text_changed)

        src_entry = ttk.Entry(src_card, textvariable=self.src_entry_var, font=("Segoe UI", 10))
        src_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        src_btn = ttk.Button(src_card, text="Browse Source...", command=self.browse_source_dir, style="Browse.TButton")
        src_btn.pack(side="right")

        # Mappings Card/Frame
        map_card = tk.LabelFrame(self.config_frame, text=" 2. Map Keys 1 - 9 to Destination Folders (leave unassigned folders blank) ", font=("Segoe UI", 10, "bold"), bg="#f5f6fa", fg="#34495e", padx=15, pady=15)
        map_card.pack(fill="both", expand=True, pady=(0, 20))

        # Create grid for key mappings
        map_card.grid_columnconfigure(1, weight=1)

        self.mapping_vars = {}
        for idx in range(1, 10):
            key = str(idx)
            lbl = ttk.Label(map_card, text=f"Key {key} Destination:", style="Mapping.TLabel")
            lbl.grid(row=idx, column=0, sticky="w", pady=6, padx=(0, 10))

            var = tk.StringVar(value=self.mappings.get(key, ""))
            var.trace_add("write", lambda *args, k=key: self._on_mapping_text_changed(k))
            self.mapping_vars[key] = var

            entry = ttk.Entry(map_card, textvariable=var, font=("Segoe UI", 10))
            entry.grid(row=idx, column=1, sticky="ew", pady=6, padx=(0, 10))

            btn_frame = tk.Frame(map_card, bg="#f5f6fa")
            btn_frame.grid(row=idx, column=2, sticky="e", pady=6)

            browse_btn = ttk.Button(btn_frame, text="Browse...", command=lambda k=key: self.browse_dest_dir(k), style="Browse.TButton")
            browse_btn.pack(side="left", padx=(0, 5))

            clear_btn = ttk.Button(btn_frame, text="Clear", command=lambda k=key: self.clear_dest_dir(k), style="Clear.TButton")
            clear_btn.pack(side="left")

        # Action Buttons frame
        act_frame = tk.Frame(self.config_frame, bg="#f5f6fa")
        act_frame.pack(fill="x", side="bottom")

        start_btn = ttk.Button(act_frame, text="Start Photo Sorter  ▶", command=self.start_viewer, style="Action.TButton")
        start_btn.pack(side="right", ipadx=15, ipady=5)

    def _clean_path(self, path_str):
        """Tırnak işaretlerini ve baştaki/sondaki boşlukları temizler."""
        if not path_str:
            return ""
        return path_str.strip().strip('"').strip("'")

    def _on_source_text_changed(self, *args):
        cleaned = self._clean_path(self.src_entry_var.get())
        if cleaned != self.source_dir:
            self.source_dir = cleaned
            self.current_index = 0
            self.last_viewed_photo = ""
            self.save_config()

    def _on_mapping_text_changed(self, key):
        if key in self.mapping_vars:
            cleaned = self._clean_path(self.mapping_vars[key].get())
            if self.mappings.get(key) != cleaned:
                self.mappings[key] = cleaned
                self.save_config()

    def browse_source_dir(self):
        dir_selected = filedialog.askdirectory(title="Select Source Folder with Images")
        if dir_selected:
            new_dir = os.path.normpath(dir_selected)
            self.src_entry_var.set(new_dir)

    def browse_dest_dir(self, key):
        dir_selected = filedialog.askdirectory(title=f"Select Destination Folder for Key {key}")
        if dir_selected:
            self.mapping_vars[key].set(os.path.normpath(dir_selected))

    def clear_dest_dir(self, key):
        self.mapping_vars[key].set("")

    # ================= START =================
    def start_viewer(self):
        # Kaynak klasör kontrolü
        self.source_dir = self._clean_path(self.src_entry_var.get())
        if not self.source_dir or not os.path.exists(self.source_dir):
            messagebox.showerror("Error", "Please provide a valid Source Folder path!")
            return

        # Hedef klasörleri son kez temizle ve kaydet
        for k in range(1, 10):
            key = str(k)
            self.mappings[key] = self._clean_path(self.mapping_vars[key].get())
        self.save_config()

        # At least one destination mapping must be set
        active_mappings = {k: v for k, v in self.mappings.items() if v}
        if not active_mappings:
            messagebox.showwarning(
                "No Mappings",
                "You haven't assigned any destination folders to numbers 1-9.\n\n"
                "You can still browse images, and move them using the subfolder panel, "
                "but number keys won't move anything."
            )

        # Load photos
        supported_exts = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
        try:
            all_files = os.listdir(self.source_dir)
            self.photos = [
                os.path.join(self.source_dir, f) for f in all_files
                if f.lower().endswith(supported_exts) and os.path.isfile(os.path.join(self.source_dir, f))
            ]
            self.photos.sort()  # alphabetical sorting
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read source folder:\n{e}")
            return

        if not self.photos:
            messagebox.showinfo("No Photos Found", f"No supported images found in:\n{self.source_dir}\n\nSupported extensions: {', '.join(supported_exts)}")
            return

        # Fresh gallery state
        self.selected = set()
        self.thumb_cache = {}
        self.last_clicked_index = None

        # Determine starting index (used to scroll the gallery to the last viewed photo)
        if self.last_viewed_photo in self.photos:
            self.current_index = self.photos.index(self.last_viewed_photo)
        else:
            if self.current_index >= len(self.photos):
                self.current_index = max(0, len(self.photos) - 1)

        self.show_gallery_screen()

    # ================= GALLERY SCREEN =================
    def show_gallery_screen(self):
        self.cancel_gif_animation()
        self._cancel_gallery_jobs()
        self.mode = "gallery"

        self.config_frame.pack_forget()
        self.viewer_frame.pack_forget()
        self.gallery_frame.pack(fill=tk.BOTH, expand=True)

        for widget in self.gallery_frame.winfo_children():
            widget.destroy()

        # Drop selections of photos that no longer exist
        self.selected = self.selected & set(self.photos)

        # 1. Top bar
        top_bar = tk.Frame(self.gallery_frame, bg="#2f3640", height=50)
        top_bar.pack(fill="x", side="top", ipady=5)
        top_bar.pack_propagate(False)

        back_btn = ttk.Button(top_bar, text="◀  Settings", command=self.show_config_screen, style="Back.TButton")
        back_btn.pack(side="left", padx=15, pady=5)

        self.gallery_info_label = tk.Label(top_bar, text="", font=("Segoe UI", 11, "bold"), bg="#2f3640", fg="white")
        self.gallery_info_label.pack(side="left", padx=20)

        clear_btn = ttk.Button(top_bar, text="Clear Selection", command=self.clear_selection, style="Tool.TButton")
        clear_btn.pack(side="right", padx=(0, 15), pady=5)
        all_btn = ttk.Button(top_bar, text="Select All", command=self.select_all, style="Tool.TButton")
        all_btn.pack(side="right", padx=(0, 8), pady=5)

        # 1b. Help row
        help_row = tk.Frame(self.gallery_frame, bg="#232a30", height=40)
        help_row.pack(fill="x", side="top")
        help_row.pack_propagate(False)
        help_label = tk.Label(
            help_row,
            text=("[Click] Select / Unselect  |  [Drag] Box select  |  [Right-drag or Ctrl+Drag] Box unselect  |  "
                  "[Shift+Click] Range  |  [Double-click] Open\n"
                  "[1-9] Move selected  |  [Del] Trash selected  |  [Ctrl +/-  or  Ctrl+Wheel] Thumbnail size  |  "
                  "[Ctrl+0] Reset size  |  [Ctrl+A] Select all  |  [Esc] Settings"),
            font=("Segoe UI", 8, "italic"), bg="#232a30", fg="#bdc3c7", justify="left", anchor="w"
        )
        help_label.pack(side="left", padx=15, fill="y")

        # 3. Bottom bar (packed before the middle area so it is never squeezed out)
        self.bottom_bar = tk.Frame(self.gallery_frame, bg="#2f3640", height=40)
        self.bottom_bar.pack(fill="x", side="bottom")
        self.update_mappings_bar()

        # 2. Middle: gallery canvas + scrollbar + subfolder panel
        middle_frame = tk.Frame(self.gallery_frame, bg="#1e272e")
        middle_frame.pack(fill="both", expand=True)

        self.subfolder_panel = tk.Frame(middle_frame, bg="#2f3640", width=200)
        self.subfolder_panel.pack(fill="y", side="right", padx=(5, 10), pady=5)
        self.subfolder_panel.pack_propagate(False)
        self.build_subfolder_panel("📁 Move Selected to Subfolder")

        scrollbar = ttk.Scrollbar(middle_frame, orient="vertical", command=self._gallery_yview)
        scrollbar.pack(side="right", fill="y", pady=5)

        self.gallery_canvas = tk.Canvas(middle_frame, bg="#1e272e", highlightthickness=0,
                                        yscrollcommand=scrollbar.set, yscrollincrement=60)
        self.gallery_canvas.pack(fill="both", expand=True, side="left", padx=(10, 0), pady=5)

        cv = self.gallery_canvas
        cv.bind("<Configure>", self._on_gallery_configure)
        # Left button: click toggles a photo, drag draws a box that SELECTS.
        cv.bind("<ButtonPress-1>", lambda e: self._drag_press(e, True))
        cv.bind("<B1-Motion>", self._drag_motion)
        cv.bind("<ButtonRelease-1>", lambda e: self._drag_release(e, True))
        cv.bind("<Double-Button-1>", self._on_gallery_double_click)
        # Right button (Ctrl + left button also works): drag draws a box that UNSELECTS.
        for b in ((2, 3) if sys.platform == "darwin" else (3,)):
            cv.bind(f"<ButtonPress-{b}>", lambda e: self._drag_press(e, False))
            cv.bind(f"<B{b}-Motion>", self._drag_motion)
            cv.bind(f"<ButtonRelease-{b}>", lambda e: self._drag_release(e, False))
        cv.bind("<MouseWheel>", self._on_gallery_wheel)
        cv.bind("<Button-4>", self._on_gallery_wheel)
        cv.bind("<Button-5>", self._on_gallery_wheel)

        self._set_focus_outline("canvas")
        self.bind_hotkeys()
        self.root.focus_set()

        self.root.update_idletasks()
        self.layout_gallery()
        if self.photos:
            self._scroll_gallery_to(min(self.current_index, len(self.photos) - 1))

    def _cancel_gallery_jobs(self):
        self._drag_cancel()
        for attr in ("thumb_job", "gallery_resize_job"):
            job = getattr(self, attr, None)
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)

    def _gallery_yview(self, *args):
        self.gallery_canvas.yview(*args)
        self._schedule_thumbs()

    def _on_gallery_wheel(self, event):
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
            if abs(event.delta) >= 120:
                step *= abs(event.delta) // 120

        # Ctrl + wheel = change thumbnail size (wheel up = bigger)
        if event.state & 0x0004:
            self.zoom_gallery(+1 if step < 0 else -1, event)
            return

        self.gallery_canvas.yview_scroll(step, "units")
        self._schedule_thumbs()
        if self._drag and self._drag["active"]:
            self._drag_update()

    def _on_gallery_configure(self, event):
        if self.gallery_resize_job:
            self.root.after_cancel(self.gallery_resize_job)
        self.gallery_resize_job = self.root.after(120, self._do_gallery_resize)

    def _do_gallery_resize(self):
        self.gallery_resize_job = None
        if self.mode == "gallery":
            self.layout_gallery()

    def layout_gallery(self, top=None):
        cv = self.gallery_canvas
        if cv is None:
            return
        self._drag_cancel()
        try:
            if top is None:
                top = cv.canvasy(0)
            cv.delete("all")
        except tk.TclError:
            return
        self.gallery_items = {}

        w = cv.winfo_width()
        if w <= 1:
            w = 800
        cell = self.CELL
        self.gallery_cols = cols = max(1, w // cell)
        self.gallery_xoff = (w - cols * cell) // 2

        n = len(self.photos)
        rows = (n + cols - 1) // cols
        self.gallery_total_h = max(rows * cell, 1)
        cv.configure(scrollregion=(0, 0, w, self.gallery_total_h))

        if n == 0:
            cv.create_text(
                w // 2, max(cv.winfo_height(), 200) // 2,
                text="🎉 All photos sorted!\n\nNo more images in source directory.",
                fill="#2ecc71", font=("Segoe UI", 16, "bold"), justify="center"
            )
            self.update_gallery_info()
            return

        for i, p in enumerate(self.photos):
            self._create_cell(i, p)

        # Restore scroll position
        h = cv.winfo_height()
        max_top = max(0, self.gallery_total_h - h)
        cv.yview_moveto(min(top, max_top) / self.gallery_total_h)

        self.update_gallery_info()
        self._schedule_thumbs()

    def _create_cell(self, i, path):
        cv = self.gallery_canvas
        cols, cell, pad = self.gallery_cols, self.CELL, self.CELL_PAD
        x = self.gallery_xoff + (i % cols) * cell
        y = (i // cols) * cell

        rect = cv.create_rectangle(x + pad, y + pad, x + cell - pad, y + cell - pad,
                                   fill="#2f3640", outline="#1e272e", width=3)
        img = cv.create_image(x + cell // 2, y + cell // 2, anchor="center")
        r = 11 if self.THUMB >= 100 else 8   # smaller check badge on small thumbnails
        bx, by = x + cell - pad - (r + 7), y + pad + (r + 7)
        badge = cv.create_oval(bx - r, by - r, bx + r, by + r,
                               fill="#3498db", outline="white", width=2, state="hidden")
        btxt = cv.create_text(bx, by, text="✓", fill="white",
                              font=("Segoe UI", 11 if r == 11 else 8, "bold"), state="hidden")
        self.gallery_items[path] = (rect, img, badge, btxt)

        thumb = self.thumb_cache.get(path)
        if thumb:
            cv.itemconfig(img, image=thumb)
        elif thumb is False:
            cv.create_text(x + cell // 2, y + cell // 2, text="⚠", fill="#e74c3c",
                           font=("Segoe UI", 20))

        if path in self.selected:
            self._apply_selection_visual(path, True)

    def _apply_selection_visual(self, path, selected):
        items = self.gallery_items.get(path)
        if not items:
            return
        rect, _img, badge, btxt = items
        cv = self.gallery_canvas
        try:
            cv.itemconfig(rect, outline="#3498db" if selected else "#1e272e",
                          fill="#2c4a63" if selected else "#2f3640")
            state = "normal" if selected else "hidden"
            cv.itemconfig(badge, state=state)
            cv.itemconfig(btxt, state=state)
        except tk.TclError:
            pass

    def _set_selected(self, path, state):
        if state:
            self.selected.add(path)
        else:
            self.selected.discard(path)
        self._apply_selection_visual(path, state)

    def _refresh_all_selection_visuals(self):
        for p in self.gallery_items:
            self._apply_selection_visual(p, p in self.selected)
        self.update_gallery_info()

    def update_gallery_info(self):
        try:
            if self.gallery_info_label is not None:
                self.gallery_info_label.config(
                    text=f"{len(self.photos)} photos  —  {len(self.selected)} selected"
                )
        except tk.TclError:
            pass

    def selected_in_order(self):
        return [p for p in self.photos if p in self.selected]

    def select_all(self, event=None):
        if self.mode != "gallery":
            return
        self.selected = set(self.photos)
        self._refresh_all_selection_visuals()

    def clear_selection(self):
        self.selected = set()
        self._refresh_all_selection_visuals()

    def _index_at(self, event):
        cv = self.gallery_canvas
        x = cv.canvasx(event.x) - self.gallery_xoff
        y = cv.canvasy(event.y)
        if x < 0 or y < 0:
            return None
        col = int(x // self.CELL)
        row = int(y // self.CELL)
        if col >= self.gallery_cols:
            return None
        idx = row * self.gallery_cols + col
        if idx >= len(self.photos):
            return None
        return idx

    # ---- click / box-drag selection ----
    def _drag_press(self, event, left):
        """Mouse button pressed on the gallery. Whether it is a click or a box-drag
        is decided later, by how far the pointer moves before the button is released."""
        self._on_canvas_click()
        cv = self.gallery_canvas
        # left button = select box, right button (or Ctrl + left) = unselect box
        mode = "select" if left and not (event.state & 0x0004) else "unselect"
        self._drag = {
            "left": left,
            "mode": mode,
            "x0": cv.canvasx(event.x), "y0": cv.canvasy(event.y),   # box anchor (canvas coords)
            "wx": event.x, "wy": event.y,                           # pointer (widget coords)
            "press": (event.x, event.y),
            "state": event.state,
            "idx": self._index_at(event),
            "base": set(self.selected),     # selection as it was before the drag started
            "inbox": set(),
            "rect": None,
            "active": False,
        }

    def _drag_motion(self, event):
        d = self._drag
        if not d:
            return
        d["wx"], d["wy"] = event.x, event.y
        if not d["active"]:
            if (abs(event.x - d["press"][0]) < self.DRAG_THRESHOLD and
                    abs(event.y - d["press"][1]) < self.DRAG_THRESHOLD):
                return
            d["active"] = True
        self._drag_update()
        if self._autoscroll_job is None:
            self._autoscroll_job = self.root.after(30, self._drag_autoscroll_tick)

    def _drag_update(self):
        """Redraw the rubber band and apply it to the selection."""
        d = self._drag
        cv = self.gallery_canvas
        if not d or not d["active"] or cv is None:
            return
        x1, y1 = cv.canvasx(d["wx"]), cv.canvasy(d["wy"])
        left, right = sorted((d["x0"], x1))
        top, bottom = sorted((d["y0"], y1))

        color = "#3498db" if d["mode"] == "select" else "#e74c3c"
        if d["rect"] is None:
            opts = {} if sys.platform == "darwin" else {"fill": color, "stipple": "gray12"}
            d["rect"] = cv.create_rectangle(left, top, right, bottom, outline=color, width=2, **opts)
        else:
            cv.coords(d["rect"], left, top, right, bottom)
        cv.tag_raise(d["rect"])

        inbox = set(self._paths_in_rect(left, top, right, bottom))
        if inbox == d["inbox"]:
            return
        changed = inbox ^ d["inbox"]
        d["inbox"] = inbox
        if d["mode"] == "select":
            self.selected = d["base"] | inbox
        else:
            self.selected = d["base"] - inbox
        for p in changed:
            self._apply_selection_visual(p, p in self.selected)
        self.update_gallery_info()

    def _paths_in_rect(self, left, top, right, bottom):
        """Photos whose card overlaps the rectangle (canvas coordinates)."""
        n = len(self.photos)
        if n == 0:
            return []
        cols, cell, pad = self.gallery_cols, self.CELL, self.CELL_PAD
        left -= self.gallery_xoff
        right -= self.gallery_xoff
        c0 = max(0, int(left // cell))
        c1 = min(cols - 1, int(right // cell))
        r0 = max(0, int(top // cell))
        r1 = min((n - 1) // cols, int(bottom // cell))
        found = []
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                idx = r * cols + c
                if idx >= n:
                    break
                # test against the card itself, not the gap between cards
                if (left < c * cell + cell - pad and right > c * cell + pad and
                        top < r * cell + cell - pad and bottom > r * cell + pad):
                    found.append(self.photos[idx])
        return found

    def _drag_autoscroll_tick(self):
        """Scroll the gallery while the pointer is held near (or beyond) its top/bottom edge."""
        self._autoscroll_job = None
        d = self._drag
        cv = self.gallery_canvas
        if not d or not d["active"] or cv is None:
            return
        try:
            h = cv.winfo_height()
            zone = 40
            dy = 0
            if d["wy"] < zone:
                dy = -min(40, (zone - d["wy"]) // 2 + 4)
            elif d["wy"] > h - zone:
                dy = min(40, (d["wy"] - (h - zone)) // 2 + 4)
            if dy:
                top = cv.canvasy(0)
                max_top = max(0, self.gallery_total_h - h)
                new_top = min(max(top + dy, 0), max_top)
                if new_top != top:
                    cv.yview_moveto(new_top / self.gallery_total_h)
                    self._drag_update()
                    self._schedule_thumbs()
        except tk.TclError:
            return
        self._autoscroll_job = self.root.after(30, self._drag_autoscroll_tick)

    def _drag_release(self, event, left):
        d = self._drag
        if not d or d["left"] != left:
            return
        was_box = d["active"]
        self._drag_cancel()          # stops auto-scroll and removes the rubber band
        if was_box:
            self.last_clicked_index = None
            return                   # the box already changed the selection
        if not left:
            return                   # a plain right-click does nothing

        # Plain left click (no drag): toggle that photo, Shift = select range
        idx = d["idx"]
        if idx is None or idx >= len(self.photos):
            return
        shift = bool(d["state"] & 0x0001)
        if shift and self.last_clicked_index is not None and self.last_clicked_index < len(self.photos):
            a, b = sorted((self.last_clicked_index, idx))
            for p in self.photos[a:b + 1]:
                self._set_selected(p, True)
            self._click_undo = None
        else:
            p = self.photos[idx]
            was_selected = p in self.selected
            self._set_selected(p, not was_selected)
            self._click_undo = (p, was_selected)
        self.last_clicked_index = idx
        self.update_gallery_info()

    def _drag_cancel(self):
        if self._autoscroll_job:
            try:
                self.root.after_cancel(self._autoscroll_job)
            except Exception:
                pass
            self._autoscroll_job = None
        d = self._drag
        self._drag = None
        if d and d.get("rect") is not None and self.gallery_canvas is not None:
            try:
                self.gallery_canvas.delete(d["rect"])
            except tk.TclError:
                pass

    def _on_gallery_double_click(self, event):
        idx = self._index_at(event)
        if idx is None:
            return
        # the first click of the double-click toggled this photo: put it back
        if self._click_undo and self._click_undo[0] == self.photos[idx]:
            self._set_selected(*self._click_undo)
        self._click_undo = None
        self.open_viewer_at(idx)

    def _scroll_gallery_to(self, idx):
        cv = self.gallery_canvas
        row = idx // self.gallery_cols
        y = row * self.CELL
        h = cv.winfo_height()
        top = cv.canvasy(0)
        if y < top or y + self.CELL > top + h:
            target = max(0, y - (h - self.CELL) // 2)
            cv.yview_moveto(target / self.gallery_total_h)
            self._schedule_thumbs()

    # ---- zoom (thumbnail size) ----
    def set_thumb_size(self, size):
        """Snap to the nearest zoom level and update the cell metrics."""
        size = min(self.ZOOM_LEVELS, key=lambda s: abs(s - size))
        self.THUMB = size
        self.CELL_PAD = max(3, size // 25)
        self.CELL = size + 2 * self.CELL_PAD + 8     # 150 -> pad 6, cell 170

    def zoom_gallery(self, direction, event=None, target=None):
        """Make thumbnails bigger (+1) or smaller (-1). The photo under the pointer
        (or in the middle of the view when used from the keyboard) stays in place."""
        if self.mode != "gallery" or self.gallery_canvas is None:
            return
        levels = self.ZOOM_LEVELS
        cur = levels.index(self.THUMB)
        new = target if target is not None else min(max(cur + direction, 0), len(levels) - 1)
        if new == cur:
            if target is None:
                self.show_status_toast(
                    "Maximum thumbnail size" if direction > 0 else "Minimum thumbnail size",
                    bg_color="#7f8c8d")
            return

        cv = self.gallery_canvas
        n = len(self.photos)
        w = cv.winfo_width()
        if w <= 1:
            w = 800
        h = cv.winfo_height()
        new_top = None
        if n:
            ax = event.x if event is not None else w // 2
            ay = event.y if event is not None else h // 2
            old_cell, old_cols = self.CELL, self.gallery_cols
            cx = cv.canvasx(ax) - self.gallery_xoff
            cy = cv.canvasy(ay)
            col = min(max(int(cx // old_cell), 0), old_cols - 1)
            row = max(int(cy // old_cell), 0)
            idx = min(row * old_cols + col, n - 1)
            row = idx // old_cols
            fy = (cy - row * old_cell) / old_cell        # where inside the card the anchor is

            self.set_thumb_size(levels[new])
            new_cols = max(1, w // self.CELL)
            rows = (n + new_cols - 1) // new_cols
            new_top = (idx // new_cols + fy) * self.CELL - ay
            new_top = min(max(new_top, 0), max(0, rows * self.CELL - h))
        else:
            self.set_thumb_size(levels[new])

        self.thumb_cache = {}            # thumbnails have to be re-made at the new size
        self.layout_gallery(new_top)
        self.save_config()
        self.show_status_toast(f"Thumbnail size: {self.THUMB}px  ({self.gallery_cols} per row)",
                               bg_color="#3498db")

    def reset_gallery_zoom(self):
        self.zoom_gallery(0, target=self.ZOOM_LEVELS.index(
            min(self.ZOOM_LEVELS, key=lambda s: abs(s - self.DEFAULT_THUMB))))

    # ---- thumbnails ----
    def make_thumb(self, path):
        try:
            with Image.open(path) as img:
                if img.format == "JPEG":
                    img.draft("RGB", (self.THUMB * 2, self.THUMB * 2))
                img = ImageOps.exif_transpose(img)
                img.thumbnail((self.THUMB, self.THUMB), Image.Resampling.LANCZOS)
                if img.mode not in ("RGB", "RGBA", "L"):
                    img = img.convert("RGBA")
                return ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"Thumbnail error for {path}: {e}")
            return False

    def _schedule_thumbs(self):
        if self.thumb_job is None and self.mode == "gallery":
            self.thumb_job = self.root.after(10, self._load_visible_thumbs)

    def _load_visible_thumbs(self):
        self.thumb_job = None
        if self.mode != "gallery" or not self.photos or self.gallery_canvas is None:
            return
        cv = self.gallery_canvas
        try:
            top = cv.canvasy(0)
            h = cv.winfo_height()
        except tk.TclError:
            return

        cols, cell = self.gallery_cols, self.CELL
        first = max(0, int(top // cell) - 1) * cols
        last = min(len(self.photos), (int((top + h) // cell) + 2) * cols)

        loaded = 0
        for i in range(first, last):
            p = self.photos[i]
            if p in self.thumb_cache:
                continue
            t = self.make_thumb(p)
            self.thumb_cache[p] = t
            items = self.gallery_items.get(p)
            if items:
                if t:
                    cv.itemconfig(items[1], image=t)
                else:
                    cx, cy = cv.coords(items[1])
                    cv.create_text(cx, cy, text="⚠", fill="#e74c3c", font=("Segoe UI", 20))
            loaded += 1
            if loaded >= 8:
                break

        if loaded >= 8:
            self.thumb_job = self.root.after(5, self._load_visible_thumbs)
        else:
            self._evict_thumbs(first, last)

    def _evict_thumbs(self, first, last):
        # keep the cache within ~250 MB of decoded thumbnails, whatever the zoom level
        hi = max(60, min(700, 250_000_000 // (self.THUMB * self.THUMB * 4)))
        lo = int(hi * 0.7)
        if len(self.thumb_cache) <= hi:
            return
        keep = set(self.photos[first:last])
        for p in list(self.thumb_cache.keys()):
            if len(self.thumb_cache) <= lo:
                break
            if p in keep or self.thumb_cache[p] is False:
                continue
            del self.thumb_cache[p]
            items = self.gallery_items.get(p)
            if items:
                try:
                    self.gallery_canvas.itemconfig(items[1], image="")
                except tk.TclError:
                    pass

    # ---- moving / deleting from gallery ----
    def _unique_dest(self, dest_dir, filename):
        dest_path = os.path.join(dest_dir, filename)
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(os.path.join(dest_dir, f"{base}_{counter}{ext}")):
                counter += 1
            dest_path = os.path.join(dest_dir, f"{base}_{counter}{ext}")
        return dest_path

    def _remove_photos(self, paths):
        s = set(paths)
        if not s:
            return
        self.photos = [p for p in self.photos if p not in s]
        self.selected -= s
        for p in s:
            self.thumb_cache.pop(p, None)
        if self.current_index >= len(self.photos):
            self.current_index = max(0, len(self.photos) - 1)
        self.last_clicked_index = None
        if self.mode == "gallery":
            self.layout_gallery()

    def move_paths(self, paths, dest_dir, label):
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not create destination folder:\n{e}")
            return

        moved, errors = [], []
        for p in paths:
            try:
                dest = self._unique_dest(dest_dir, os.path.basename(p))
                shutil.move(p, dest)
                moved.append(p)
            except Exception as e:
                errors.append(f"{os.path.basename(p)}: {e}")

        self._remove_photos(moved)

        if moved:
            n = len(moved)
            self.show_status_toast(f"Moved {n} photo{'s' if n != 1 else ''} to {label}")
        if errors:
            messagebox.showerror(
                "Error Moving Files",
                f"{len(errors)} file(s) could not be moved:\n\n" + "\n".join(errors[:5])
            )

    def gallery_num_press(self, event):
        key = self._key_from_event(event)
        if key is None or not self.photos:
            return

        paths = self.selected_in_order()
        if not paths:
            self.show_status_toast("No photos selected! Click photos to select them.", bg_color="#e74c3c")
            return

        dest_dir = self.mappings.get(key, "")
        if not dest_dir:
            self.show_status_toast(f"Key [{key}] has no folder mapped!", bg_color="#e74c3c")
            return

        label = os.path.basename(dest_dir) or dest_dir
        self.move_paths(paths, dest_dir, f"[{key}] {label}")

    def delete_selected_images(self, event=None):
        paths = self.selected_in_order()
        if not paths:
            self.show_status_toast("No photos selected!", bg_color="#e74c3c")
            return
        if len(paths) > 1 and not messagebox.askyesno(
            "Move to Recycle Bin", f"Move {len(paths)} selected photos to the Recycle Bin?"
        ):
            return

        done, errors = [], []
        for p in paths:
            try:
                send2trash.send2trash(p)
                done.append(p)
            except Exception as e:
                errors.append(f"{os.path.basename(p)}: {e}")

        self._remove_photos(done)
        if done:
            n = len(done)
            self.show_status_toast(f"Moved {n} photo{'s' if n != 1 else ''} to Recycle Bin", bg_color="#e74c3c")
        if errors:
            messagebox.showerror(
                "Error Deleting Files",
                f"{len(errors)} file(s) could not be deleted:\n\n" + "\n".join(errors[:5])
            )

    def open_viewer_at(self, idx):
        self.current_index = idx
        self.show_viewer_screen()

    # ================= VIEWER SCREEN =================
    def show_viewer_screen(self):
        self._cancel_gallery_jobs()
        self.mode = "viewer"
        self.config_frame.pack_forget()
        self.gallery_frame.pack_forget()
        self.viewer_frame.pack(fill=tk.BOTH, expand=True)

        # Clear existing viewer frame children to rebuild cleanly
        for widget in self.viewer_frame.winfo_children():
            widget.destroy()

        # 1. Top Panel (Control / Info bar)
        top_bar = tk.Frame(self.viewer_frame, bg="#2f3640", height=50)
        top_bar.pack(fill="x", side="top", ipady=5)
        top_bar.pack_propagate(False)

        back_btn = ttk.Button(top_bar, text="◀  Back to Gallery", command=self.show_gallery_screen, style="Back.TButton")
        back_btn.pack(side="left", padx=15, pady=5)

        self.info_label = tk.Label(top_bar, text="", font=("Segoe UI", 11, "bold"), bg="#2f3640", fg="white")
        self.info_label.pack(side="left", padx=20)

        help_label = tk.Label(top_bar, text="[←] Previous  |  [→] Next  |  [1-9] Move Image  |  [R] Rotate  |  [Del] Trash  |  [Esc] Gallery", font=("Segoe UI", 9, "italic"), bg="#2f3640", fg="#bdc3c7")
        help_label.pack(side="right", padx=15)

        # 2. Middle area: canvas + subfolder search panel side by side
        middle_frame = tk.Frame(self.viewer_frame, bg="#1e272e")
        middle_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # 2a. Main Photo Display Canvas
        self.canvas = tk.Canvas(middle_frame, bg="#1e272e", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, side="left", padx=(10, 0), pady=5)

        # 2b. Subfolder Search Panel (right side)
        self.subfolder_panel = tk.Frame(middle_frame, bg="#2f3640", width=200)
        self.subfolder_panel.pack(fill="y", side="right", padx=(5, 10), pady=5)
        self.subfolder_panel.pack_propagate(False)
        self.build_subfolder_panel("📁 Move to Subfolder")

        # 3. Bottom Panel (Mappings Status Bar)
        self.bottom_bar = tk.Frame(self.viewer_frame, bg="#2f3640", height=40)
        self.bottom_bar.pack(fill="x", side="bottom")

        self.update_mappings_bar()

        # 4. Status overlay message
        self.status_msg_id = None

        # 5. Event bindings
        self.bind_hotkeys()

        # Bind canvas resize to scale image dynamically
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        # Clicking the canvas gives it "focus"
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        # Set initial focus state to canvas
        self._set_focus_outline("canvas")
        self.root.focus_set()

        # Show first image
        self.display_current_image()

    def build_subfolder_panel(self, title="📁 Move to Subfolder"):
        panel = self.subfolder_panel

        title_lbl = tk.Label(panel, text=title, font=("Segoe UI", 10, "bold"),
                             bg="#2f3640", fg="#ecf0f1", anchor="w", wraplength=180, justify="left")
        title_lbl.pack(fill="x", padx=8, pady=(10, 4))

        search_frame = tk.Frame(panel, bg="#2f3640")
        search_frame.pack(fill="x", padx=8, pady=(0, 6))

        self.subfolder_search_var = tk.StringVar()
        self.subfolder_search_var.trace_add("write", self._on_subfolder_search_change)

        search_entry = tk.Entry(search_frame, textvariable=self.subfolder_search_var,
                                font=("Segoe UI", 10), bg="#3d4f5c", fg="white",
                                insertbackground="white", relief="flat", bd=4)
        search_entry.pack(fill="x")
        search_entry.bind("<FocusIn>", self._on_search_focus_in)
        search_entry.bind("<FocusOut>", self._on_search_focus_out)
        self.subfolder_search_entry = search_entry

        self.search_hint_lbl = tk.Label(panel, text="Type to filter folders…",
                                        font=("Segoe UI", 8, "italic"),
                                        bg="#2f3640", fg="#7f8c8d", anchor="w")
        self.search_hint_lbl.pack(fill="x", padx=8, pady=(0, 4))

        list_container = tk.Frame(panel, bg="#2f3640")
        list_container.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        scrollbar = tk.Scrollbar(list_container, orient="vertical", bg="#3d4f5c",
                                 troughcolor="#2f3640", activebackground="#5d6d7e")
        scrollbar.pack(side="right", fill="y")

        self.subfolder_canvas = tk.Canvas(list_container, bg="#2f3640",
                                          highlightthickness=0,
                                          yscrollcommand=scrollbar.set)
        self.subfolder_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.subfolder_canvas.yview)

        self.subfolder_buttons_frame = tk.Frame(self.subfolder_canvas, bg="#2f3640")
        self.subfolder_canvas_window = self.subfolder_canvas.create_window(
            (0, 0), window=self.subfolder_buttons_frame, anchor="nw"
        )

        self.subfolder_buttons_frame.bind("<Configure>", self._on_subfolder_frame_resize)
        self.subfolder_canvas.bind("<Configure>", self._on_subfolder_canvas_resize)

        self.refresh_subfolders()

    def _on_subfolder_frame_resize(self, event):
        self.subfolder_canvas.configure(scrollregion=self.subfolder_canvas.bbox("all"))

    def _on_subfolder_canvas_resize(self, event):
        self.subfolder_canvas.itemconfig(self.subfolder_canvas_window, width=event.width)

    def _on_search_focus_in(self, event):
        self.unbind_hotkeys(keep_escape=True)
        self._set_focus_outline("search")

    def _on_search_focus_out(self, event):
        self.bind_hotkeys()
        self._set_focus_outline("canvas")

    def _set_focus_outline(self, active):
        canvas_color = "white" if active == "canvas" else "#2f3640"
        panel_color = "white" if active == "search" else "#1e272e"
        try:
            self.active_canvas().config(highlightthickness=2, highlightbackground=canvas_color)
            self.subfolder_panel.config(highlightthickness=2, highlightbackground=panel_color,
                                        highlightcolor=panel_color)
        except Exception:
            pass

    def _on_canvas_click(self, event=None):
        self._on_search_focus_out(None)
        self.root.focus()

    def refresh_subfolders(self):
        self.source_subfolders = []
        if self.source_dir and os.path.isdir(self.source_dir):
            try:
                entries = os.scandir(self.source_dir)
                self.source_subfolders = sorted(
                    [e.name for e in entries if e.is_dir()],
                    key=lambda s: s.lower()
                )
            except Exception as e:
                print(f"Error scanning subfolders: {e}")
        self.filter_subfolder_buttons("")

    def _on_subfolder_search_change(self, *args):
        query = self.subfolder_search_var.get().strip()
        self.filter_subfolder_buttons(query)

    def filter_subfolder_buttons(self, query):
        for widget in self.subfolder_buttons_frame.winfo_children():
            widget.destroy()

        query_lower = query.lower()
        matched = [name for name in self.source_subfolders
                   if name.lower().startswith(query_lower)] if query else self.source_subfolders

        if not matched:
            no_lbl = tk.Label(self.subfolder_buttons_frame,
                              text="No matching folders" if query else "No subfolders found",
                              font=("Segoe UI", 9, "italic"),
                              bg="#2f3640", fg="#7f8c8d", anchor="w", wraplength=170)
            no_lbl.pack(fill="x", pady=4)
            return

        for folder_name in matched:
            folder_path = os.path.join(self.source_dir, folder_name)
            btn = tk.Button(
                self.subfolder_buttons_frame,
                text=folder_name,
                font=("Segoe UI", 9),
                bg="#3d4f5c", fg="#ecf0f1",
                activebackground="#2980b9", activeforeground="white",
                relief="flat", bd=0, anchor="w", padx=8, pady=5,
                cursor="hand2", wraplength=170,
                command=lambda p=folder_path, n=folder_name: self.move_to_subfolder(p, n)
            )
            btn.pack(fill="x", pady=2)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#2980b9"))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#3d4f5c"))

    def move_to_subfolder(self, dest_dir, folder_name):
        if not self.photos:
            return

        # Gallery mode: move all selected photos
        if self.mode == "gallery":
            paths = self.selected_in_order()
            if not paths:
                self.show_status_toast("No photos selected!", bg_color="#e74c3c")
                return
            self.move_paths(paths, dest_dir, f"📁 {folder_name}")
            if self.subfolder_search_var:
                self.subfolder_search_var.set("")
            return

        # Viewer mode: move current photo
        photo_path = self.photos[self.current_index]
        filename = os.path.basename(photo_path)

        os.makedirs(dest_dir, exist_ok=True)
        dest_path = self._unique_dest(dest_dir, filename)
        filename = os.path.basename(dest_path)

        try:
            shutil.move(photo_path, dest_path)
            self.show_status_toast(f"Moved to 📁 {folder_name}")

            del self.photos[self.current_index]
            self.selected.discard(photo_path)
            self.thumb_cache.pop(photo_path, None)

            if self.photos:
                if self.current_index >= len(self.photos):
                    self.current_index = len(self.photos) - 1
                self.display_current_image()
            else:
                self.show_empty_viewer()

            if self.subfolder_search_var:
                self.subfolder_search_var.set("")

        except Exception as e:
            messagebox.showerror("Error Moving File", f"Could not move {filename}:\n{e}")

    def update_mappings_bar(self):
        for widget in self.bottom_bar.winfo_children():
            widget.destroy()

        active_items = []
        for i in range(1, 10):
            key = str(i)
            path = self.mappings.get(key, "")
            if path:
                folder_name = os.path.basename(path)
                if not folder_name:
                    folder_name = path
                active_items.append(f"[{key}]: {folder_name}")

        bar_text = "Active Folders:   " + "   |   ".join(active_items) if active_items else "No folders mapped. Open Settings to assign folders to 1-9."
        lbl = tk.Label(self.bottom_bar, text=bar_text, font=("Segoe UI", 10), bg="#2f3640", fg="#ecf0f1", anchor="w", padx=15)
        lbl.pack(fill="both", expand=True)

    def display_current_image(self):
        if not self.photos:
            self.show_empty_viewer()
            return

        if self.current_index < 0:
            self.current_index = 0
        elif self.current_index >= len(self.photos):
            self.current_index = len(self.photos) - 1

        photo_path = self.photos[self.current_index]
        self.last_viewed_photo = photo_path
        filename = os.path.basename(photo_path)

        self.info_label.config(text=f"Photo {self.current_index + 1} of {len(self.photos)}  —  {filename}")
        self.load_and_draw_image(photo_path)

    def load_and_draw_image(self, path):
        self.cancel_gif_animation()

        is_gif = path.lower().endswith('.gif')
        is_animated = False
        if is_gif:
            try:
                img = Image.open(path)
                is_animated = getattr(img, "is_animated", False) and img.n_frames > 1
            except Exception:
                is_animated = False

        if is_animated:
            try:
                img = Image.open(path)
                for frame_num in range(img.n_frames):
                    img.seek(frame_num)
                    self.gif_frames.append(img.copy())
                    dur = img.info.get('duration', 100)
                    if not dur or dur <= 0:
                        dur = 100
                    self.gif_durations.append(dur)

                self.animate_gif()
                return
            except Exception as e:
                print(f"Error loading animated GIF: {e}")
                self.cancel_gif_animation()

        try:
            self.canvas.delete("bg_image")
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)

            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()

            if canvas_w <= 1 or canvas_h <= 1:
                canvas_w = 800
                canvas_h = 600

            img_w, img_h = img.size
            ratio = min(canvas_w / img_w, canvas_h / img_h)

            if ratio < 1.0 or (img_w < 300 and img_h < 300):
                new_w = max(int(img_w * ratio), 1)
                new_h = max(int(img_h * ratio), 1)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            self.current_image_obj = ImageTk.PhotoImage(img)
            self.canvas.create_image(canvas_w // 2, canvas_h // 2, anchor="center", image=self.current_image_obj, tags="bg_image")

        except Exception as e:
            self.canvas.delete("bg_image")
            self.canvas.create_text(
                self.canvas.winfo_width() // 2,
                self.canvas.winfo_height() // 2,
                text=f"Failed to load image:\n{os.path.basename(path)}\n\n{e}",
                fill="#e74c3c",
                font=("Segoe UI", 12, "bold"),
                justify="center",
                tags="bg_image"
            )

    def on_canvas_resize(self, event):
        if self.resize_job:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(100, self.do_resized_draw)

    def do_resized_draw(self):
        if self.mode == "viewer" and self.photos and self.current_index < len(self.photos):
            self.load_and_draw_image(self.photos[self.current_index])

    def show_empty_viewer(self):
        self.canvas.delete("bg_image")
        self.info_label.config(text="No photos left!")

        self.canvas.create_text(
            self.canvas.winfo_width() // 2,
            self.canvas.winfo_height() // 2,
            text="🎉 All photos sorted!\n\nNo more images in source directory.",
            fill="#2ecc71",
            font=("Segoe UI", 16, "bold"),
            justify="center",
            tags="bg_image"
        )

    # ================= EVENT HANDLERS =================
    def prev_image(self, event=None):
        if not self.photos:
            return
        self.current_index = (self.current_index - 1) % len(self.photos)
        self.display_current_image()

    def next_image(self, event=None):
        if not self.photos:
            return
        self.current_index = (self.current_index + 1) % len(self.photos)
        self.display_current_image()

    def show_status_toast(self, text, bg_color="#2ecc71"):
        cv = self.active_canvas()
        if cv is None:
            return
        try:
            cv.delete("toast")

            canvas_w = cv.winfo_width()
            canvas_h = cv.winfo_height()
            y0 = cv.canvasy(0)

            cv.create_rectangle(
                canvas_w // 2 - 250, y0 + canvas_h - 60,
                canvas_w // 2 + 250, y0 + canvas_h - 20,
                fill=bg_color, outline="", tags="toast"
            )
            cv.create_text(
                canvas_w // 2, y0 + canvas_h - 40,
                text=text, fill="white", font=("Segoe UI", 10, "bold"), tags="toast"
            )

            self.root.after(1500, lambda c=cv: self._clear_toast(c))
        except tk.TclError:
            pass

    def _clear_toast(self, cv):
        try:
            cv.delete("toast")
        except tk.TclError:
            pass

    def handle_num_press(self, event):
        if not self.photos:
            return

        key = self._key_from_event(event)
        if key is None:
            return

        dest_dir = self.mappings.get(key, "")
        if not dest_dir:
            self.show_status_toast(f"Key [{key}] has no folder mapped!", bg_color="#e74c3c")
            return

        photo_path = self.photos[self.current_index]

        os.makedirs(dest_dir, exist_ok=True)
        dest_path = self._unique_dest(dest_dir, os.path.basename(photo_path))
        filename = os.path.basename(dest_path)

        try:
            shutil.move(photo_path, dest_path)
            self.show_status_toast(f"Moved {filename} to Key {key} folder")

            del self.photos[self.current_index]
            self.selected.discard(photo_path)
            self.thumb_cache.pop(photo_path, None)

            if self.photos:
                if self.current_index >= len(self.photos):
                    self.current_index = len(self.photos) - 1
                self.display_current_image()
            else:
                self.show_empty_viewer()

        except Exception as e:
            messagebox.showerror("Error Moving File", f"Could not move file {filename}:\n{e}")

    def animate_gif(self):
        if not self.gif_frames:
            return

        try:
            self.canvas.delete("bg_image")
            frame = self.gif_frames[self.gif_frame_index]

            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            if canvas_w <= 1 or canvas_h <= 1:
                canvas_w = 800
                canvas_h = 600

            img_w, img_h = frame.size
            ratio = min(canvas_w / img_w, canvas_h / img_h)

            if ratio < 1.0 or (img_w < 300 and img_h < 300):
                new_w = max(int(img_w * ratio), 1)
                new_h = max(int(img_h * ratio), 1)
                frame_resized = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)
            else:
                frame_resized = frame

            self.current_image_obj = ImageTk.PhotoImage(frame_resized)
            self.canvas.create_image(canvas_w // 2, canvas_h // 2, anchor="center", image=self.current_image_obj, tags="bg_image")

            duration = self.gif_durations[self.gif_frame_index]
            self.gif_frame_index = (self.gif_frame_index + 1) % len(self.gif_frames)

            self.gif_animation_id = self.root.after(duration, self.animate_gif)
        except Exception as e:
            print(f"Error in animate_gif: {e}")

    def cancel_gif_animation(self):
        if self.gif_animation_id:
            try:
                self.root.after_cancel(self.gif_animation_id)
            except Exception:
                pass
            self.gif_animation_id = None
        self.gif_frames = []
        self.gif_durations = []
        self.gif_frame_index = 0

    def delete_current_image(self, event=None):
        if not self.photos:
            return

        photo_path = self.photos[self.current_index]
        filename = os.path.basename(photo_path)

        try:
            send2trash.send2trash(photo_path)
            self.show_status_toast(f"Moved {filename} to Recycle Bin", bg_color="#e74c3c")

            del self.photos[self.current_index]
            self.selected.discard(photo_path)
            self.thumb_cache.pop(photo_path, None)

            if self.photos:
                if self.current_index >= len(self.photos):
                    self.current_index = len(self.photos) - 1
                self.display_current_image()
            else:
                self.show_empty_viewer()

        except Exception as e:
            messagebox.showerror("Error Deleting File", f"Could not move file {filename} to Recycle Bin:\n{e}")

    def rotate_current_image(self, event=None):
        if not self.photos:
            return

        photo_path = self.photos[self.current_index]

        if self.gif_frames:
            self.gif_frames = [frame.transpose(Image.Transpose.ROTATE_270) for frame in self.gif_frames]
            self.show_status_toast("Rotated GIF in-memory (not saved to disk)", bg_color="#3498db")
            return

        try:
            with Image.open(photo_path) as img:
                img = ImageOps.exif_transpose(img)
                rotated_img = img.transpose(Image.Transpose.ROTATE_270)

            rotated_img.save(photo_path)
            self.thumb_cache.pop(photo_path, None)  # thumbnail is stale now
            self.show_status_toast("Rotated photo 90° CW", bg_color="#3498db")
            self.display_current_image()

        except Exception as e:
            messagebox.showerror("Error Rotating Photo", f"Could not rotate image:\n{e}")


# ================= MAIN RUNNER =================
if __name__ == "__main__":
    root = tk.Tk()
    app = PhotoSorterApp(root)

    def on_closing():
        try:
            app.cancel_gif_animation()
            app._cancel_gallery_jobs()
            app.unbind_hotkeys()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
