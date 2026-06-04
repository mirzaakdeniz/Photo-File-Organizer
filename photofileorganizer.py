import os
import shutil
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps
import send2trash

class PhotoSorterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Photo Sorter")
        self.root.geometry("900x750")
        self.root.minsize(700, 600)
        
        # Load configuration
        self.config_file = "config.json"
        self.config = self.load_config()
        
        # Application state
        self.source_dir = self.config.get("source_dir", "")
        self.mappings = self.config.get("mappings", {str(i): "" for i in range(1, 10)})
        
        # Keep mappings as strings in internal state
        self.mappings = {str(k): v for k, v in self.mappings.items()}
        for i in range(1, 10):
            if str(i) not in self.mappings:
                self.mappings[str(i)] = ""
                
        self.photos = []
        self.current_index = 0
        self.last_viewed_photo = ""
        self.current_image_obj = None
        self.resize_job = None
        
        # GIF Animation state
        self.gif_frames = []
        self.gif_durations = []
        self.gif_frame_index = 0
        self.gif_animation_id = None
        
        # Setup modern ttk styles
        self.setup_styles()
        
        # Main container
        self.main_container = tk.Frame(self.root, bg="#f5f6fa")
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # Create screens
        self.config_frame = tk.Frame(self.main_container, bg="#f5f6fa")
        self.viewer_frame = tk.Frame(self.main_container, bg="#1e272e") # Dark background for photos
        
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
            "mappings": self.mappings
        }
        try:
            with open(self.config_file, "w") as f:
                json.dump(config_data, f, indent=4)
        except Exception as e:
            print(f"Error saving config.json: {e}")

    # ================= CONFIGURATION SCREEN =================
    def show_config_screen(self):
        # Cancel any active GIF animations
        self.cancel_gif_animation()
        
        # Unbind viewer hotkeys
        try:
            self.root.unbind("<Left>")
            self.root.unbind("<Right>")
            self.root.unbind("<Escape>")
            self.root.unbind("<Delete>")
            self.root.unbind("<r>")
            self.root.unbind("<R>")
            for i in range(1, 10):
                self.root.unbind(str(i))
                self.root.unbind(f"<KP_{i}>")
        except Exception:
            pass

        # Clean frames
        self.viewer_frame.pack_forget()
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
        src_entry = ttk.Entry(src_card, textvariable=self.src_entry_var, state="readonly", font=("Segoe UI", 10))
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
            # Label
            lbl = ttk.Label(map_card, text=f"Key {key} Destination:", style="Mapping.TLabel")
            lbl.grid(row=idx, column=0, sticky="w", pady=6, padx=(0, 10))
            
            # Entry
            var = tk.StringVar(value=self.mappings.get(key, ""))
            self.mapping_vars[key] = var
            entry = ttk.Entry(map_card, textvariable=var, state="readonly", font=("Segoe UI", 10))
            entry.grid(row=idx, column=1, sticky="ew", pady=6, padx=(0, 10))
            
            # Buttons frame
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

    def browse_source_dir(self):
        dir_selected = filedialog.askdirectory(title="Select Source Folder with Images")
        if dir_selected:
            new_dir = os.path.normpath(dir_selected)
            if new_dir != self.source_dir:
                self.source_dir = new_dir
                self.current_index = 0
                self.last_viewed_photo = ""
                self.src_entry_var.set(self.source_dir)
                self.save_config()

    def browse_dest_dir(self, key):
        dir_selected = filedialog.askdirectory(title=f"Select Destination Folder for Key {key}")
        if dir_selected:
            self.mappings[key] = os.path.normpath(dir_selected)
            self.mapping_vars[key].set(self.mappings[key])
            self.save_config()

    def clear_dest_dir(self, key):
        self.mappings[key] = ""
        self.mapping_vars[key].set("")
        self.save_config()

    # ================= VIEWER SCREEN =================
    def start_viewer(self):
        # Validation
        if not self.source_dir or not os.path.exists(self.source_dir):
            messagebox.showerror("Error", "Please select a valid Source Folder first!")
            return
            
        # At least one destination mapping must be set
        active_mappings = {k: v for k, v in self.mappings.items() if v}
        if not active_mappings:
            messagebox.showwarning(
                "No Mappings", 
                "You haven't assigned any destination folders to numbers 1-9.\n\n"
                "You can still browse images using left/right arrows, but moving files won't be possible."
            )
            
        # Load photos
        supported_exts = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
        try:
            all_files = os.listdir(self.source_dir)
            self.photos = [
                os.path.join(self.source_dir, f) for f in all_files 
                if f.lower().endswith(supported_exts) and os.path.isfile(os.path.join(self.source_dir, f))
            ]
            self.photos.sort() # alphabetical sorting
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read source folder:\n{e}")
            return
            
        if not self.photos:
            messagebox.showinfo("No Photos Found", f"No supported images found in:\n{self.source_dir}\n\nSupported extensions: {', '.join(supported_exts)}")
            return
            
        # Save mappings from vars just in case they were modified
        for key in range(1, 10):
            self.mappings[str(key)] = self.mapping_vars[str(key)].get()
        self.save_config()
        
        # Determine starting index:
        # 1. Try to find the last viewed photo if it still exists in the list
        if hasattr(self, 'last_viewed_photo') and self.last_viewed_photo in self.photos:
            self.current_index = self.photos.index(self.last_viewed_photo)
        else:
            # 2. Otherwise, keep the current index if it's within bounds, else clamp to the end
            if self.current_index >= len(self.photos):
                self.current_index = max(0, len(self.photos) - 1)
                
        self.show_viewer_screen()

    def show_viewer_screen(self):
        self.config_frame.pack_forget()
        self.viewer_frame.pack(fill=tk.BOTH, expand=True)
        
        # Clear existing viewer frame children to rebuild cleanly
        for widget in self.viewer_frame.winfo_children():
            widget.destroy()
            
        # 1. Top Panel (Control / Info bar)
        top_bar = tk.Frame(self.viewer_frame, bg="#2f3640", height=50)
        top_bar.pack(fill="x", side="top", ipady=5)
        top_bar.pack_propagate(False)
        
        back_btn = ttk.Button(top_bar, text="◀  Back to Settings", command=self.show_config_screen, style="Back.TButton")
        back_btn.pack(side="left", padx=15, pady=5)
        
        self.info_label = tk.Label(top_bar, text="", font=("Segoe UI", 11, "bold"), bg="#2f3640", fg="white")
        self.info_label.pack(side="left", padx=20)
        
        help_label = tk.Label(top_bar, text="[←] Previous  |  [→] Next  |  [1-9] Move Image  |  [R] Rotate  |  [Del] Trash  |  [Esc] Settings", font=("Segoe UI", 9, "italic"), bg="#2f3640", fg="#bdc3c7")
        help_label.pack(side="right", padx=15)
        
        # 2. Main Photo Display Canvas
        self.canvas = tk.Canvas(self.viewer_frame, bg="#1e272e", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 3. Bottom Panel (Mappings Status Bar)
        self.bottom_bar = tk.Frame(self.viewer_frame, bg="#2f3640", height=40)
        self.bottom_bar.pack(fill="x", side="bottom")
        
        self.update_mappings_bar()
        
        # 4. Status overlay message (transient text shown at the bottom of the canvas)
        self.status_msg_id = None
        
        # 5. Event bindings
        self.root.bind("<Left>", self.prev_image)
        self.root.bind("<Right>", self.next_image)
        self.root.bind("<Escape>", lambda e: self.show_config_screen())
        self.root.bind("<Delete>", self.delete_current_image)
        self.root.bind("<r>", self.rotate_current_image)
        self.root.bind("<R>", self.rotate_current_image)
        
        # Bind numbers 1-9 (both main keyboard and keypad)
        for i in range(1, 10):
            self.root.bind(str(i), self.handle_num_press)
            self.root.bind(f"<KP_{i}>", self.handle_num_press)
            
        # Bind canvas resize to scale image dynamically
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        
        # Show first image
        self.display_current_image()

    def update_mappings_bar(self):
        # Clear bottom bar
        for widget in self.bottom_bar.winfo_children():
            widget.destroy()
            
        active_items = []
        for i in range(1, 10):
            key = str(i)
            path = self.mappings.get(key, "")
            if path:
                folder_name = os.path.basename(path)
                if not folder_name:  # For root directory like "D:\"
                    folder_name = path
                active_items.append(f"[{key}]: {folder_name}")
                
        bar_text = "Active Folders:   " + "   |   ".join(active_items) if active_items else "No folders mapped. Press [Esc] to assign folders to 1-9."
        lbl = tk.Label(self.bottom_bar, text=bar_text, font=("Segoe UI", 10), bg="#2f3640", fg="#ecf0f1", anchor="w", padx=15)
        lbl.pack(fill="both", expand=True)

    def display_current_image(self):
        if not self.photos:
            self.show_empty_viewer()
            return
            
        # Index bounds check
        if self.current_index < 0:
            self.current_index = 0
        elif self.current_index >= len(self.photos):
            self.current_index = len(self.photos) - 1
            
        photo_path = self.photos[self.current_index]
        self.last_viewed_photo = photo_path
        filename = os.path.basename(photo_path)
        
        # Update Top Info Bar text
        self.info_label.config(text=f"Photo {self.current_index + 1} of {len(self.photos)}  —  {filename}")
        
        # Load and resize
        self.load_and_draw_image(photo_path)

    def load_and_draw_image(self, path):
        # Cancel any active GIF animation loops
        self.cancel_gif_animation()
        
        # Check if the file is an animated GIF
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
                
                # Start GIF animation
                self.animate_gif()
                return
            except Exception as e:
                print(f"Error loading animated GIF: {e}")
                self.cancel_gif_animation()
                # Fallback to static render
                
        try:
            # Clear previous background images
            self.canvas.delete("bg_image")
            
            # Open the image
            img = Image.open(path)
            
            # Rotate/Transpose based on EXIF tag so photos taken vertically display correctly
            img = ImageOps.exif_transpose(img)
            
            # Get canvas size
            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            
            # Default fallback size if canvas isn't rendered yet
            if canvas_w <= 1 or canvas_h <= 1:
                canvas_w = 800
                canvas_h = 600
                
            img_w, img_h = img.size
            
            # Calculate proportional scale factor
            ratio = min(canvas_w / img_w, canvas_h / img_h)
            
            # Keep it reasonable and don't scale up past 100% unless it's very tiny
            if ratio < 1.0 or (img_w < 300 and img_h < 300):
                new_w = max(int(img_w * ratio), 1)
                new_h = max(int(img_h * ratio), 1)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            # Create photoimage
            self.current_image_obj = ImageTk.PhotoImage(img)
            
            # Center on canvas
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
        # Debounce/delay image resizing to smooth out user window-drag resizing
        if self.resize_job:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(100, self.do_resized_draw)

    def do_resized_draw(self):
        if self.photos and self.current_index < len(self.photos):
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
        # Deletes old overlay if it exists
        self.canvas.delete("toast")
        
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        
        # Display an elegant translucent status toast in the bottom center
        rect_id = self.canvas.create_rectangle(
            canvas_w // 2 - 250, canvas_h - 60,
            canvas_w // 2 + 250, canvas_h - 20,
            fill=bg_color, outline="", tags="toast"
        )
        text_id = self.canvas.create_text(
            canvas_w // 2, canvas_h - 40,
            text=text, fill="white", font=("Segoe UI", 10, "bold"), tags="toast"
        )
        
        # Auto hide after 1.5 seconds
        self.root.after(1500, lambda: self.canvas.delete("toast"))

    def handle_num_press(self, event):
        if not self.photos:
            return
            
        key = event.char
        if not key or key not in self.mappings:
            # Fallback if event.char is empty (e.g. from keypad bind keysym like KP_1)
            keysym = event.keysym
            if keysym.startswith("KP_") and keysym[3:].isdigit():
                key = keysym[3:]
            else:
                return
                
        dest_dir = self.mappings.get(key, "")
        if not dest_dir:
            self.show_status_toast(f"Key [{key}] has no folder mapped!", bg_color="#e74c3c")
            return
            
        # Get path of current photo
        photo_path = self.photos[self.current_index]
        filename = os.path.basename(photo_path)
        
        # Prepare destination path
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, filename)
        
        # Handle duplicates safely by appending suffix
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(os.path.join(dest_dir, f"{base}_{counter}{ext}")):
                counter += 1
            dest_path = os.path.join(dest_dir, f"{base}_{counter}{ext}")
            filename = os.path.basename(dest_path)
            
        try:
            # Perform Move
            shutil.move(photo_path, dest_path)
            
            # Show visual confirmation
            self.show_status_toast(f"Moved {filename} to Key {key} folder")
            
            # Remove photo from local tracking list
            del self.photos[self.current_index]
            
            # Advance to next image (index stays same because we deleted item, 
            # but if we were on the last item, we decrement to stay within bounds)
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
            # Clear previous background image
            self.canvas.delete("bg_image")
            
            # Get current frame
            frame = self.gif_frames[self.gif_frame_index]
            
            # Get canvas size
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
                
            # Create PhotoImage
            self.current_image_obj = ImageTk.PhotoImage(frame_resized)
            
            # Draw on canvas
            self.canvas.create_image(canvas_w // 2, canvas_h // 2, anchor="center", image=self.current_image_obj, tags="bg_image")
            
            # Schedule next frame
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
            # Send to recycle bin/trash
            send2trash.send2trash(photo_path)
            
            # Show toast confirmation
            self.show_status_toast(f"Moved {filename} to Recycle Bin", bg_color="#e74c3c")
            
            # Remove photo from local tracking list
            del self.photos[self.current_index]
            
            # Advance to next image
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
        
        # Check if currently playing an animated GIF
        if self.gif_frames:
            # Rotate in-memory frames for visual playback
            self.gif_frames = [frame.transpose(Image.Transpose.ROTATE_270) for frame in self.gif_frames]
            # Toast visual feedback
            self.show_status_toast("Rotated GIF in-memory (not saved to disk)", bg_color="#3498db")
            return
            
        # For static images, rotate and save to disk
        try:
            # 1. Open, load, and close the file to avoid lock
            with Image.open(photo_path) as img:
                # Apply EXIF orientation first so rotation is relative to upright view
                img = ImageOps.exif_transpose(img)
                # Rotate 90 degrees clockwise (ROTATE_270 is 270 counter-clockwise = 90 clockwise)
                rotated_img = img.transpose(Image.Transpose.ROTATE_270)
                
            # 2. Save back to disk
            rotated_img.save(photo_path)
            
            # Show toast confirmation
            self.show_status_toast("Rotated photo 90° CW", bg_color="#3498db")
            
            # 3. Reload and draw
            self.display_current_image()
            
        except Exception as e:
            messagebox.showerror("Error Rotating Photo", f"Could not rotate image:\n{e}")

# ================= MAIN RUNNER =================
if __name__ == "__main__":
    root = tk.Tk()
    app = PhotoSorterApp(root)
    
    # Enable clean escape / close behavior
    def on_closing():
        # Unbind everything to avoid errors during destroy
        try:
            app.cancel_gif_animation()
            root.unbind("<Left>")
            root.unbind("<Right>")
            root.unbind("<Escape>")
            root.unbind("<Delete>")
            root.unbind("<r>")
            root.unbind("<R>")
            for i in range(1, 10):
                root.unbind(str(i))
                root.unbind(f"<KP_{i}>")
        except Exception:
            pass
        root.destroy()
        
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
