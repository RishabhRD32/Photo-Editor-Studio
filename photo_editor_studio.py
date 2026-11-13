from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageTk

APP_NAME = "Photo Editor Studio"
APP_VERSION = "1.0"
APP_AUTHOR = "Rishabdev Tripathi"
HISTORY_LIMIT = 12
MAX_RESIZE_DIMENSION = 20_000
MAX_RESIZE_PIXELS = 100_000_000

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore

    DND_AVAILABLE = True
except ImportError:
    DND_FILES = None  # type: ignore[assignment]
    TkinterDnD = None  # type: ignore[assignment,misc]
    DND_AVAILABLE = False


class PhotoEditor:
    """Tkinter photo editor with history, crop selection, resize controls and previews."""

    OPEN_FILE_TYPES = [
        ("Supported images", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp"),
        ("All files", "*.*"),
    ]
    SAVE_FILE_TYPES = [
        ("PNG image", "*.png"),
        ("JPEG image", "*.jpg *.jpeg"),
        ("WebP image", "*.webp"),
        ("BMP image", "*.bmp"),
        ("TIFF image", "*.tif *.tiff"),
    ]
    SAVE_FORMATS = {
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".webp": "WEBP",
        ".bmp": "BMP",
        ".tif": "TIFF",
        ".tiff": "TIFF",
    }
    ADJUSTMENT_KEYS = ("brightness", "contrast", "sharpness", "color")

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{APP_NAME}  |  Version {APP_VERSION}")
        self.root.geometry("1200x780")
        self.root.minsize(950, 620)
        self.root.configure(bg="#f3f5f8")

        self.original_image: Image.Image | None = None
        self.base_image: Image.Image | None = None
        self.preview_image: Image.Image | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.current_path: Path | None = None
        self.source_format = "Unknown"

        self._undo_stack: list[dict[str, object]] = []
        self._redo_stack: list[dict[str, object]] = []
        self._last_committed_state: dict[str, object] | None = None
        self._slider_history_pending = False
        self._slider_history_job: str | None = None
        self._suspend_slider_callbacks = False
        self._resize_update_lock = False
        self._last_resize_axis = "width"

        self.brightness_var = tk.DoubleVar(value=1.0)
        self.contrast_var = tk.DoubleVar(value=1.0)
        self.sharpness_var = tk.DoubleVar(value=1.0)
        self.color_var = tk.DoubleVar(value=1.0)
        self.jpeg_quality_var = tk.IntVar(value=92)
        self.resize_width_var = tk.StringVar(value="")
        self.resize_height_var = tk.StringVar(value="")
        self.keep_ratio_var = tk.BooleanVar(value=True)

        self.status_var = tk.StringVar(value="Open an image to begin editing.")
        self.file_info_var = tk.StringVar(value="No image loaded")
        self.dimensions_var = tk.StringVar(value="—")
        self.format_var = tk.StringVar(value="—")
        self.mode_var = tk.StringVar(value="—")
        self.size_var = tk.StringVar(value="—")
        self.quality_value_var = tk.StringVar(value="92")

        self.crop_mode = False
        self._crop_start: tuple[float, float] | None = None
        self._crop_rect_id: int | None = None
        self._display_box: tuple[float, float, float, float] | None = None

        self.compare_window: tk.Toplevel | None = None
        self.compare_original_canvas: tk.Canvas | None = None
        self.compare_current_canvas: tk.Canvas | None = None
        self.compare_original_photo: ImageTk.PhotoImage | None = None
        self.compare_current_photo: ImageTk.PhotoImage | None = None

        self._build_style()
        self._build_menu()
        self._build_interface()
        self._bind_shortcuts()
        self._setup_drag_and_drop()

    # ------------------------------------------------------------------ UI
    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#f3f5f8")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("TLabel", background="#f3f5f8", foreground="#202938", font=("Segoe UI", 9))
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), foreground="#162338")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 9), foreground="#5b6575")
        style.configure("Section.TLabelframe", background="#ffffff", padding=8)
        style.configure("Section.TLabelframe.Label", background="#ffffff", foreground="#23344d", font=("Segoe UI", 10, "bold"))
        style.configure("TButton", padding=(8, 5), font=("Segoe UI", 9))
        style.configure("Primary.TButton", padding=(10, 6), font=("Segoe UI", 9, "bold"))
        style.configure("Info.TLabel", background="#ffffff", foreground="#475569", font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#e8edf4", foreground="#334155", padding=(10, 5))

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self.root)
        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Open Image…", accelerator="Ctrl+O", command=self.open_image)
        file_menu.add_command(label="Save As…", accelerator="Ctrl+Shift+S", command=self.save_image)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menu_bar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menu_bar, tearoff=False)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", command=self.redo)
        edit_menu.add_command(label="Reset to Original", accelerator="Ctrl+R", command=self.reset_image)
        edit_menu.add_separator()
        edit_menu.add_command(label="Compare Before / After", accelerator="Ctrl+Shift+C", command=self.open_compare)
        edit_menu.add_command(label="Cancel Crop Selection", accelerator="Esc", command=self.cancel_crop)
        menu_bar.add_cascade(label="Edit", menu=edit_menu)

        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(label="Keyboard Shortcuts", command=self.show_shortcuts)
        help_menu.add_command(label="About Photo Editor Studio", accelerator="F1", command=self.show_about)
        menu_bar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menu_bar)

    def _build_interface(self) -> None:
        header = ttk.Frame(self.root, padding=(14, 10, 14, 8))
        header.pack(fill="x")
        heading = ttk.Frame(header)
        heading.pack(side="left", fill="x", expand=True)
        ttk.Label(heading, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(heading, text="Simple, offline image editing", style="Subtitle.TLabel").pack(anchor="w", pady=(1, 0))

        toolbar = ttk.Frame(header)
        toolbar.pack(side="right")
        ttk.Button(toolbar, text="Open Image", command=self.open_image, style="Primary.TButton").pack(side="left", padx=3)
        ttk.Button(toolbar, text="Save As", command=self.save_image).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Undo", command=self.undo).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Redo", command=self.redo).pack(side="left", padx=3)
        ttk.Button(toolbar, text="Compare", command=self.open_compare).pack(side="left", padx=3)
        ttk.Button(toolbar, text="About", command=self.show_about).pack(side="left", padx=3)

        main = ttk.Panedwindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        preview_frame = ttk.LabelFrame(main, text="Image Preview", style="Section.TLabelframe", padding=8)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(preview_frame, background="#e6ebf2", highlightthickness=0, cursor="arrow")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self._draw_preview())
        self.canvas.bind("<ButtonPress-1>", self._crop_press)
        self.canvas.bind("<B1-Motion>", self._crop_drag)
        self.canvas.bind("<ButtonRelease-1>", self._crop_release)

        preview_footer = ttk.Frame(preview_frame)
        preview_footer.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        preview_footer.columnconfigure(0, weight=1)
        self.preview_hint_var = tk.StringVar(value="Open an image, then use the controls to edit it.")
        ttk.Label(preview_footer, textvariable=self.preview_hint_var, style="Subtitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(preview_footer, text="Select Crop Area", command=self.toggle_crop_mode).grid(row=0, column=1, padx=(8, 0))

        controls_host = ttk.Frame(main, width=350)
        controls_host.columnconfigure(0, weight=1)
        controls_host.rowconfigure(0, weight=1)
        self.controls_canvas = tk.Canvas(controls_host, width=330, background="#f3f5f8", highlightthickness=0, borderwidth=0)
        controls_scrollbar = ttk.Scrollbar(controls_host, orient="vertical", command=self.controls_canvas.yview)
        self.controls_canvas.configure(yscrollcommand=controls_scrollbar.set)
        self.controls_canvas.grid(row=0, column=0, sticky="nsew")
        controls_scrollbar.grid(row=0, column=1, sticky="ns")
        self.controls_inner = ttk.Frame(self.controls_canvas, padding=(0, 0, 5, 0))
        self._controls_window_id = self.controls_canvas.create_window((0, 0), window=self.controls_inner, anchor="nw")
        self.controls_inner.bind("<Configure>", self._update_controls_scrollregion)
        self.controls_canvas.bind("<Configure>", self._resize_controls_inner)
        self.root.bind_all("<MouseWheel>", self._on_global_mousewheel, add="+")
        self.root.bind_all("<Button-4>", lambda event: self._on_global_linux_mousewheel(event, -1), add="+")
        self.root.bind_all("<Button-5>", lambda event: self._on_global_linux_mousewheel(event, 1), add="+")

        self._build_controls(self.controls_inner)
        main.add(preview_frame, weight=4)
        main.add(controls_host, weight=1)
        # Start with a comfortable preview-to-controls ratio.
        self.root.after(120, lambda: self._set_initial_sash(main))

        ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel", anchor="w").pack(fill="x", side="bottom")

    def _set_initial_sash(self, pane: ttk.Panedwindow) -> None:
        try:
            width = pane.winfo_width()
            if width > 600:
                pane.sashpos(0, int(width * 0.73))
        except tk.TclError:
            pass

    def _build_controls(self, parent: ttk.Frame) -> None:
        file_section = ttk.LabelFrame(parent, text="File", style="Section.TLabelframe")
        file_section.pack(fill="x", pady=(0, 8))
        ttk.Button(file_section, text="Open / Change Image…", command=self.open_image).pack(fill="x", pady=3)
        ttk.Button(file_section, text="Save Edited Image As…", command=self.save_image).pack(fill="x", pady=3)
        ttk.Button(file_section, text="Reset to Original", command=self.reset_image).pack(fill="x", pady=3)

        adjust_section = ttk.LabelFrame(parent, text="Adjustments", style="Section.TLabelframe")
        adjust_section.pack(fill="x", pady=(0, 8))
        self._add_slider(adjust_section, "Brightness", "brightness", self.brightness_var)
        self._add_slider(adjust_section, "Contrast", "contrast", self.contrast_var)
        self._add_slider(adjust_section, "Sharpness", "sharpness", self.sharpness_var)
        self._add_slider(adjust_section, "Color saturation", "color", self.color_var)
        ttk.Button(adjust_section, text="Reset All Adjustments", command=self.reset_adjustments).pack(fill="x", pady=(5, 1))

        resize_section = ttk.LabelFrame(parent, text="Resize & Crop", style="Section.TLabelframe")
        resize_section.pack(fill="x", pady=(0, 8))
        dimensions = ttk.Frame(resize_section)
        dimensions.pack(fill="x", pady=(0, 5))
        ttk.Label(dimensions, text="Width").grid(row=0, column=0, sticky="w")
        ttk.Label(dimensions, text="Height").grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.resize_width_entry = ttk.Entry(dimensions, textvariable=self.resize_width_var, width=10)
        self.resize_height_entry = ttk.Entry(dimensions, textvariable=self.resize_height_var, width=10)
        self.resize_width_entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.resize_height_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(2, 0))
        dimensions.columnconfigure(0, weight=1)
        dimensions.columnconfigure(1, weight=1)
        self.resize_width_entry.bind("<KeyRelease>", lambda _e: self._resize_dimension_changed("width"))
        self.resize_height_entry.bind("<KeyRelease>", lambda _e: self._resize_dimension_changed("height"))
        ttk.Checkbutton(resize_section, text="Maintain aspect ratio", variable=self.keep_ratio_var).pack(anchor="w", pady=(0, 5))
        ttk.Button(resize_section, text="Apply Custom Resize", command=self.resize_image).pack(fill="x", pady=2)
        ttk.Button(resize_section, text="Select Crop Area on Image", command=self.toggle_crop_mode).pack(fill="x", pady=2)
        ttk.Label(resize_section, text="Tip: drag a rectangle over the image to crop.", style="Subtitle.TLabel", wraplength=280).pack(anchor="w", pady=(4, 0))

        transform_section = ttk.LabelFrame(parent, text="Transformations", style="Section.TLabelframe")
        transform_section.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(transform_section)
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="Rotate Left 90°", command=self.rotate_left).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(row, text="Rotate Right 90°", command=self.rotate_right).pack(side="left", fill="x", expand=True, padx=(3, 0))
        ttk.Button(transform_section, text="Flip Horizontally", command=self.flip_horizontal).pack(fill="x", pady=2)
        ttk.Button(transform_section, text="Flip Vertically", command=self.flip_vertical).pack(fill="x", pady=2)

        effects_section = ttk.LabelFrame(parent, text="Effects", style="Section.TLabelframe")
        effects_section.pack(fill="x", pady=(0, 8))
        ttk.Button(effects_section, text="Blur", command=self.apply_blur).pack(fill="x", pady=2)
        ttk.Button(effects_section, text="Emboss", command=self.apply_emboss).pack(fill="x", pady=2)
        ttk.Button(effects_section, text="Edge Enhancement", command=self.apply_edge_enhance).pack(fill="x", pady=2)
        ttk.Button(effects_section, text="Grayscale", command=self.apply_grayscale).pack(fill="x", pady=2)
        ttk.Button(effects_section, text="Sepia", command=self.apply_sepia).pack(fill="x", pady=2)

        save_section = ttk.LabelFrame(parent, text="Save Quality", style="Section.TLabelframe")
        save_section.pack(fill="x", pady=(0, 8))
        quality_row = ttk.Frame(save_section)
        quality_row.pack(fill="x")
        ttk.Label(quality_row, text="JPEG / WebP quality").pack(side="left")
        ttk.Label(quality_row, textvariable=self.quality_value_var, width=4, anchor="e").pack(side="right")
        self.quality_scale = tk.Scale(
            save_section,
            from_=50,
            to=100,
            orient="horizontal",
            resolution=1,
            showvalue=False,
            variable=self.jpeg_quality_var,
            command=self._on_quality_change,
            highlightthickness=0,
            background="#ffffff",
            activebackground="#dbeafe",
            troughcolor="#dce3ed",
        )
        self.quality_scale.pack(fill="x")
        ttk.Label(save_section, text="Higher quality usually means a larger file.", style="Subtitle.TLabel", wraplength=280).pack(anchor="w")

        info_section = ttk.LabelFrame(parent, text="Image Information", style="Section.TLabelframe")
        info_section.pack(fill="x", pady=(0, 8))
        self._info_row(info_section, "File", self.file_info_var)
        self._info_row(info_section, "Dimensions", self.dimensions_var)
        self._info_row(info_section, "Format", self.format_var)
        self._info_row(info_section, "Color mode", self.mode_var)
        self._info_row(info_section, "File size on disk", self.size_var)

        about_note = ttk.Label(parent, text=f"{APP_NAME} v{APP_VERSION}\nCreated by {APP_AUTHOR}", style="Subtitle.TLabel", justify="center")
        about_note.pack(fill="x", pady=(4, 12))

    def _info_row(self, parent: ttk.LabelFrame, title: str, variable: tk.StringVar) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=f"{title}:", style="Info.TLabel", width=17).pack(side="left", anchor="nw")
        ttk.Label(row, textvariable=variable, style="Info.TLabel", wraplength=160, justify="left").pack(side="left", fill="x", expand=True, anchor="w")

    def _add_slider(self, parent: ttk.LabelFrame, label: str, key: str, variable: tk.DoubleVar) -> None:
        section = ttk.Frame(parent)
        section.pack(fill="x", pady=3)
        line = ttk.Frame(section)
        line.pack(fill="x")
        ttk.Label(line, text=label).pack(side="left")
        ttk.Button(line, text="Reset", width=6, command=lambda k=key: self.reset_adjustment(k)).pack(side="right")
        slider = tk.Scale(
            section,
            from_=0.0,
            to=2.0,
            resolution=0.1,
            orient="horizontal",
            variable=variable,
            showvalue=True,
            command=lambda value, k=key: self._on_slider_change(k, value),
            highlightthickness=0,
            background="#ffffff",
            activebackground="#dbeafe",
            troughcolor="#dce3ed",
        )
        slider.pack(fill="x")

    # ---------------------------------------------------------- file handling
    def open_image(self) -> None:
        filename = filedialog.askopenfilename(title="Open Image", filetypes=self.OPEN_FILE_TYPES)
        if filename:
            self._load_image_path(filename)

    def _load_image_path(self, filename: str | os.PathLike[str]) -> None:
        try:
            path = Path(filename).expanduser()
            with Image.open(path) as source:
                fmt = source.format or path.suffix.lstrip(".").upper() or "Unknown"
                transposed = ImageOps.exif_transpose(source)
                if "A" in transposed.getbands() or transposed.mode in {"P", "LA"} and "transparency" in transposed.info:
                    loaded = transposed.convert("RGBA")
                elif transposed.mode == "L":
                    loaded = transposed.copy()
                else:
                    loaded = transposed.convert("RGB")
            self._cancel_pending_history_job()
            self.current_path = path
            self.source_format = str(fmt).upper()
            self.original_image = loaded.copy()
            self.base_image = loaded.copy()
            self._reset_slider_values()
            self._set_crop_mode(False)
            self._render_current()
            self._sync_resize_fields()
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._slider_history_pending = False
            self._last_committed_state = self._capture_state()
            self.root.title(f"{APP_NAME} — {path.name}")
            self.status_var.set(f"Opened {path.name} · {loaded.width} × {loaded.height}")
        except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            messagebox.showerror("Unable to open image", f"The selected file could not be opened.\n\n{exc}", parent=self.root)

    def save_image(self) -> None:
        if self.preview_image is None:
            messagebox.showinfo("No image", "Open an image before saving.", parent=self.root)
            return
        initial_name = f"{self.current_path.stem}_edited.png" if self.current_path else "edited_image.png"
        filename = filedialog.asksaveasfilename(
            title="Save Edited Image",
            initialfile=initial_name,
            defaultextension=".png",
            filetypes=self.SAVE_FILE_TYPES,
        )
        if not filename:
            return
        target = Path(filename)
        suffix = target.suffix.lower()
        if not suffix:
            target = target.with_suffix(".png")
            suffix = ".png"
        image_format = self.SAVE_FORMATS.get(suffix)
        if not image_format:
            messagebox.showerror(
                "Unsupported format",
                "Choose PNG, JPEG, WebP, BMP, or TIFF as the output format.",
                parent=self.root,
            )
            return
        try:
            output = self.preview_image.copy()
            options: dict[str, object] = {}
            if image_format == "JPEG":
                if output.mode not in {"RGB", "L"}:
                    if "A" in output.getbands():
                        rgba = output.convert("RGBA")
                        white = Image.new("RGB", rgba.size, "white")
                        white.paste(rgba, mask=rgba.getchannel("A"))
                        output = white
                    else:
                        output = output.convert("RGB")
                options.update(quality=int(self.jpeg_quality_var.get()), optimize=True, progressive=True)
            elif image_format == "WEBP":
                options.update(quality=int(self.jpeg_quality_var.get()), method=6)
            elif image_format == "PNG":
                options.update(optimize=True)
            elif image_format == "BMP" and output.mode not in {"RGB", "L"}:
                output = output.convert("RGB")
            output.save(target, format=image_format, **options)
            self.current_path = target
            self.source_format = image_format
            self._update_info()
            self.root.title(f"{APP_NAME} — {target.name}")
            self.status_var.set(f"Saved {target.name} · {self._format_bytes(target.stat().st_size)}")
            messagebox.showinfo("Image saved", f"Your edited image has been saved to:\n\n{target}", parent=self.root)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("Unable to save image", f"The image could not be saved.\n\n{exc}", parent=self.root)

    def _setup_drag_and_drop(self) -> None:
        if not DND_AVAILABLE:
            self.preview_hint_var.set("Open an image to edit. Optional drag-and-drop: install tkinterdnd2.")
            return
        try:
            self.canvas.drop_target_register(DND_FILES)
            self.canvas.dnd_bind("<<Drop>>", self._on_drop_file)
            self.root.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
            self.root.dnd_bind("<<Drop>>", self._on_drop_file)  # type: ignore[attr-defined]
        except (tk.TclError, AttributeError):
            self.status_var.set("Drag-and-drop setup was unavailable; use Open Image instead.")

    def _on_drop_file(self, event: tk.Event) -> str:
        try:
            dropped = self.root.tk.splitlist(event.data)  # type: ignore[attr-defined]
            if dropped:
                self._load_image_path(dropped[0])
        except (tk.TclError, AttributeError, IndexError) as exc:
            messagebox.showerror("Drag-and-drop failed", f"Could not read the dropped file.\n\n{exc}", parent=self.root)
        return "break"

    # ------------------------------------------------------ image adjustments
    def _on_slider_change(self, key: str, value: str) -> None:
        if self._suspend_slider_callbacks or self.base_image is None:
            return
        if not self._slider_history_pending:
            if self._last_committed_state is not None:
                self._append_history(self._undo_stack, self._last_committed_state)
                self._redo_stack.clear()
            self._slider_history_pending = True
        self._cancel_pending_history_job()
        self._slider_history_job = self.root.after(450, self._finish_slider_gesture)
        self._render_current()

    def _finish_slider_gesture(self) -> None:
        self._slider_history_job = None
        self._slider_history_pending = False
        self._last_committed_state = self._capture_state() if self.base_image is not None else None

    def _cancel_pending_history_job(self) -> None:
        if self._slider_history_job is not None:
            try:
                self.root.after_cancel(self._slider_history_job)
            except tk.TclError:
                pass
            self._slider_history_job = None

    def _flush_slider_history(self) -> None:
        if self._slider_history_pending:
            self._cancel_pending_history_job()
            self._finish_slider_gesture()

    def _reset_slider_values(self) -> None:
        self._suspend_slider_callbacks = True
        try:
            self.brightness_var.set(1.0)
            self.contrast_var.set(1.0)
            self.sharpness_var.set(1.0)
            self.color_var.set(1.0)
        finally:
            self._suspend_slider_callbacks = False

    def _adjustment_values(self) -> dict[str, float]:
        return {
            "brightness": float(self.brightness_var.get()),
            "contrast": float(self.contrast_var.get()),
            "sharpness": float(self.sharpness_var.get()),
            "color": float(self.color_var.get()),
        }

    def _render_current(self) -> None:
        if self.base_image is None:
            self.preview_image = None
            self._draw_preview()
            self._update_info()
            self._redraw_compare()
            return
        try:
            image = self.base_image.copy()
            image = ImageEnhance.Brightness(image).enhance(float(self.brightness_var.get()))
            image = ImageEnhance.Contrast(image).enhance(float(self.contrast_var.get()))
            image = ImageEnhance.Sharpness(image).enhance(float(self.sharpness_var.get()))
            image = ImageEnhance.Color(image).enhance(float(self.color_var.get()))
            self.preview_image = image
            self._draw_preview()
            self._update_info()
            self._redraw_compare()
            self.preview_hint_var.set(f"{image.width} × {image.height} pixels · {'Crop mode: drag to select' if self.crop_mode else 'Ready to edit'}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Image processing error", f"Could not update image preview.\n\n{exc}", parent=self.root)

    def reset_adjustment(self, key: str) -> None:
        if key not in self.ADJUSTMENT_KEYS or self.base_image is None:
            return
        self._flush_slider_history()
        current = self._capture_state()
        if abs(float(self._adjustment_values()[key]) - 1.0) < 1e-8:
            return
        self._append_history(self._undo_stack, current)
        self._redo_stack.clear()
        var = self._var_for_adjustment(key)
        self._suspend_slider_callbacks = True
        try:
            var.set(1.0)
        finally:
            self._suspend_slider_callbacks = False
        self._render_current()
        self._last_committed_state = self._capture_state()
        self.status_var.set(f"Reset {key} adjustment.")

    def reset_adjustments(self) -> None:
        if self.base_image is None:
            self._no_image_message()
            return
        self._flush_slider_history()
        values = self._adjustment_values()
        if all(abs(values[key] - 1.0) < 1e-8 for key in self.ADJUSTMENT_KEYS):
            self.status_var.set("All adjustments are already at their default values.")
            return
        self._push_undo_current()
        self._reset_slider_values()
        self._render_current()
        self._last_committed_state = self._capture_state()
        self.status_var.set("Reset all adjustment sliders.")

    def _var_for_adjustment(self, key: str) -> tk.DoubleVar:
        return {
            "brightness": self.brightness_var,
            "contrast": self.contrast_var,
            "sharpness": self.sharpness_var,
            "color": self.color_var,
        }[key]

    def _on_quality_change(self, value: str) -> None:
        self.quality_value_var.set(str(int(float(value))))

    # --------------------------------------------------------- edit history
    def _capture_state(self) -> dict[str, object]:
        return {
            "base_image": self.base_image.copy() if self.base_image is not None else None,
            "adjustments": self._adjustment_values(),
        }

    def _append_history(self, stack: list[dict[str, object]], state: dict[str, object]) -> None:
        # Copy image pixels so later edits cannot mutate prior history states.
        copied = {
            "base_image": state["base_image"].copy() if isinstance(state.get("base_image"), Image.Image) else None,
            "adjustments": dict(state.get("adjustments", {})),
        }
        stack.append(copied)
        if len(stack) > HISTORY_LIMIT:
            del stack[0 : len(stack) - HISTORY_LIMIT]

    def _push_undo_current(self) -> None:
        if self.base_image is None:
            return
        self._append_history(self._undo_stack, self._capture_state())
        self._redo_stack.clear()

    def _restore_state(self, state: dict[str, object]) -> None:
        base = state.get("base_image")
        self.base_image = base.copy() if isinstance(base, Image.Image) else None
        values = state.get("adjustments", {})
        if not isinstance(values, dict):
            values = {}
        self._suspend_slider_callbacks = True
        try:
            self.brightness_var.set(float(values.get("brightness", 1.0)))
            self.contrast_var.set(float(values.get("contrast", 1.0)))
            self.sharpness_var.set(float(values.get("sharpness", 1.0)))
            self.color_var.set(float(values.get("color", 1.0)))
        finally:
            self._suspend_slider_callbacks = False
        self._set_crop_mode(False)
        self._render_current()
        self._sync_resize_fields()
        self._last_committed_state = self._capture_state() if self.base_image is not None else None

    def undo(self) -> None:
        self._flush_slider_history()
        if not self._undo_stack or self.base_image is None:
            self.status_var.set("Nothing to undo.")
            return
        current = self._capture_state()
        previous = self._undo_stack.pop()
        self._append_history(self._redo_stack, current)
        self._restore_state(previous)
        self.status_var.set("Undo completed.")

    def redo(self) -> None:
        self._flush_slider_history()
        if not self._redo_stack or self.base_image is None:
            self.status_var.set("Nothing to redo.")
            return
        current = self._capture_state()
        next_state = self._redo_stack.pop()
        self._append_history(self._undo_stack, current)
        self._restore_state(next_state)
        self.status_var.set("Redo completed.")

    def _apply_transform(self, operation: Callable[[Image.Image], Image.Image], description: str) -> None:
        if self.preview_image is None:
            self._no_image_message()
            return
        self._flush_slider_history()
        self._push_undo_current()
        try:
            transformed = operation(self.preview_image.copy())
            if transformed.width < 1 or transformed.height < 1:
                raise ValueError("The operation returned an empty image.")
            self.base_image = transformed.copy()
            self._reset_slider_values()
            self._set_crop_mode(False)
            self._render_current()
            self._sync_resize_fields()
            self._last_committed_state = self._capture_state()
            self.status_var.set(f"Applied {description} · {transformed.width} × {transformed.height}")
        except (OSError, ValueError, TypeError) as exc:
            # Leave the prior image intact if processing failed; remove the undo entry
            # added for an operation that did not take place.
            if self._undo_stack:
                self._undo_stack.pop()
            messagebox.showerror("Image processing error", f"Could not apply {description.lower()}.\n\n{exc}", parent=self.root)

    def rotate_left(self) -> None:
        self._apply_transform(lambda image: image.rotate(90, expand=True), "Rotate left 90°")

    def rotate_right(self) -> None:
        self._apply_transform(lambda image: image.rotate(-90, expand=True), "Rotate right 90°")

    def flip_horizontal(self) -> None:
        self._apply_transform(ImageOps.mirror, "Flip horizontally")

    def flip_vertical(self) -> None:
        self._apply_transform(ImageOps.flip, "Flip vertically")

    def apply_blur(self) -> None:
        self._apply_transform(lambda image: image.filter(ImageFilter.BLUR), "Blur")

    def apply_emboss(self) -> None:
        self._apply_transform(lambda image: image.filter(ImageFilter.EMBOSS), "Emboss")

    def apply_edge_enhance(self) -> None:
        self._apply_transform(lambda image: image.filter(ImageFilter.FIND_EDGES), "Edge enhancement")

    def apply_grayscale(self) -> None:
        def grayscale(image: Image.Image) -> Image.Image:
            converted = ImageOps.grayscale(image.convert("RGB"))
            if "A" in image.getbands():
                rgb = Image.merge("RGB", (converted, converted, converted)).convert("RGBA")
                rgb.putalpha(image.getchannel("A"))
                return rgb
            return converted
        self._apply_transform(grayscale, "Grayscale")

    def apply_sepia(self) -> None:
        def sepia(image: Image.Image) -> Image.Image:
            rgba = image.convert("RGBA") if "A" in image.getbands() else image.convert("RGB")
            rgb = rgba.convert("RGB")
            sepia_image = ImageOps.colorize(ImageOps.grayscale(rgb), black="#2b1b0e", white="#f4dfb5")
            if "A" in image.getbands():
                sepia_image.putalpha(rgba.getchannel("A"))
            return sepia_image
        self._apply_transform(sepia, "Sepia")

    def reset_image(self) -> None:
        if self.original_image is None:
            self._no_image_message()
            return
        self._flush_slider_history()
        current = self._capture_state()
        original_base = self.base_image.copy() if self.base_image is not None else None
        current_values = self._adjustment_values()
        already_original = (
            original_base is not None
            and self.original_image.size == original_base.size
            and original_base.tobytes() == self.original_image.tobytes()
            and all(abs(current_values[key] - 1.0) < 1e-8 for key in self.ADJUSTMENT_KEYS)
        )
        if already_original:
            self.status_var.set("The image is already at its original state.")
            return
        self._append_history(self._undo_stack, current)
        self._redo_stack.clear()
        self.base_image = self.original_image.copy()
        self._reset_slider_values()
        self._set_crop_mode(False)
        self._render_current()
        self._sync_resize_fields()
        self._last_committed_state = self._capture_state()
        self.status_var.set("Restored the original opened image. Use Undo to restore the previous edits.")

    def _no_image_message(self) -> None:
        messagebox.showinfo("No image loaded", "Open an image before using this feature.", parent=self.root)

    # ------------------------------------------------------- resize & cropping
    def _sync_resize_fields(self) -> None:
        if self.preview_image is None:
            self.resize_width_var.set("")
            self.resize_height_var.set("")
            return
        self._resize_update_lock = True
        try:
            self.resize_width_var.set(str(self.preview_image.width))
            self.resize_height_var.set(str(self.preview_image.height))
        finally:
            self._resize_update_lock = False

    def _resize_dimension_changed(self, axis: str) -> None:
        if self._resize_update_lock or not self.keep_ratio_var.get() or self.preview_image is None:
            self._last_resize_axis = axis
            return
        self._last_resize_axis = axis
        try:
            ratio = self.preview_image.width / self.preview_image.height
            self._resize_update_lock = True
            if axis == "width":
                value = int(self.resize_width_var.get())
                if value > 0:
                    self.resize_height_var.set(str(max(1, round(value / ratio))))
            else:
                value = int(self.resize_height_var.get())
                if value > 0:
                    self.resize_width_var.set(str(max(1, round(value * ratio))))
        except (ValueError, ZeroDivisionError):
            pass
        finally:
            self._resize_update_lock = False

    def resize_image(self) -> None:
        if self.preview_image is None:
            self._no_image_message()
            return
        try:
            width = int(self.resize_width_var.get().strip())
            height = int(self.resize_height_var.get().strip())
        except ValueError:
            messagebox.showwarning("Invalid dimensions", "Enter a whole number for both width and height.", parent=self.root)
            return
        if width < 1 or height < 1 or width > MAX_RESIZE_DIMENSION or height > MAX_RESIZE_DIMENSION:
            messagebox.showwarning(
                "Dimensions out of range",
                f"Width and height must each be between 1 and {MAX_RESIZE_DIMENSION:,} pixels.",
                parent=self.root,
            )
            return
        if width * height > MAX_RESIZE_PIXELS:
            messagebox.showwarning(
                "Image too large",
                f"The requested size exceeds the safety limit of {MAX_RESIZE_PIXELS:,} pixels.",
                parent=self.root,
            )
            return
        if self.keep_ratio_var.get() and self.preview_image is not None:
            original_ratio = self.preview_image.width / self.preview_image.height
            if self._last_resize_axis == "width":
                height = max(1, round(width / original_ratio))
                self.resize_height_var.set(str(height))
            else:
                width = max(1, round(height * original_ratio))
                self.resize_width_var.set(str(width))
        self._apply_transform(lambda image: image.resize((width, height), Image.Resampling.LANCZOS), f"Resize to {width} × {height}")

    def toggle_crop_mode(self) -> None:
        if self.preview_image is None:
            self._no_image_message()
            return
        if self.crop_mode:
            self.cancel_crop()
            return
        self._set_crop_mode(True)
        self.status_var.set("Crop mode: drag across the image to select and apply a crop.")
        self.preview_hint_var.set("Crop mode active · drag a rectangle over the image · press Esc to cancel")

    def _set_crop_mode(self, enabled: bool) -> None:
        self.crop_mode = enabled
        self._crop_start = None
        self._crop_rect_id = None
        if hasattr(self, "canvas"):
            self.canvas.delete("crop-selection")
            self.canvas.configure(cursor="crosshair" if enabled else "arrow")
        if not enabled and hasattr(self, "preview_hint_var"):
            if self.preview_image is not None:
                self.preview_hint_var.set(f"{self.preview_image.width} × {self.preview_image.height} pixels · Ready to edit")
        if hasattr(self, "canvas"):
            self._draw_preview()

    def cancel_crop(self, _event: tk.Event | None = None) -> str | None:
        if self.crop_mode:
            self._set_crop_mode(False)
            self.status_var.set("Crop selection cancelled.")
        return "break" if _event is not None else None

    def _crop_press(self, event: tk.Event) -> None:
        if not self.crop_mode or self.preview_image is None or self._display_box is None:
            return
        left, top, right, bottom = self._display_box
        x, y = float(event.x), float(event.y)
        if not (left <= x <= right and top <= y <= bottom):
            return
        self._crop_start = (x, y)
        self.canvas.delete("crop-selection")
        self._crop_rect_id = self.canvas.create_rectangle(
            x, y, x, y, outline="#ef4444", width=2, dash=(5, 3), tags="crop-selection"
        )

    def _crop_drag(self, event: tk.Event) -> None:
        if not self.crop_mode or self._crop_start is None or self._display_box is None or self._crop_rect_id is None:
            return
        left, top, right, bottom = self._display_box
        x = min(max(float(event.x), left), right)
        y = min(max(float(event.y), top), bottom)
        self.canvas.coords(self._crop_rect_id, self._crop_start[0], self._crop_start[1], x, y)

    def _crop_release(self, event: tk.Event) -> None:
        if not self.crop_mode or self._crop_start is None or self.preview_image is None or self._display_box is None:
            return
        left, top, right, bottom = self._display_box
        x1d, y1d = self._crop_start
        x2d = min(max(float(event.x), left), right)
        y2d = min(max(float(event.y), top), bottom)
        x1d, x2d = sorted((x1d, x2d))
        y1d, y2d = sorted((y1d, y2d))
        shown_width = max(right - left, 1.0)
        shown_height = max(bottom - top, 1.0)
        if x2d - x1d < 4 or y2d - y1d < 4:
            self._set_crop_mode(False)
            self.status_var.set("Crop selection was too small; try selecting a larger area.")
            return
        image_width, image_height = self.preview_image.size
        crop_box = (
            max(0, min(image_width - 1, int((x1d - left) * image_width / shown_width))),
            max(0, min(image_height - 1, int((y1d - top) * image_height / shown_height))),
            max(1, min(image_width, round((x2d - left) * image_width / shown_width))),
            max(1, min(image_height, round((y2d - top) * image_height / shown_height))),
        )
        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            self._set_crop_mode(False)
            self.status_var.set("Invalid crop selection. Try again.")
            return
        self._apply_transform(lambda image: image.crop(crop_box), "Interactive crop")

    # ---------------------------------------------------------- visual display
    def _draw_preview(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        self._display_box = None
        if self.preview_image is None:
            self.canvas.create_text(
                width // 2,
                height // 2,
                text="Open an image to start editing\n\nPNG · JPEG · WebP · BMP · TIFF · GIF",
                fill="#64748b",
                font=("Segoe UI", 13),
                justify="center",
            )
            self.preview_photo = None
            return
        available = (max(width - 24, 1), max(height - 24, 1))
        display_copy = ImageOps.contain(self.preview_image.copy(), available, method=Image.Resampling.LANCZOS)
        shown_width, shown_height = display_copy.size
        x0 = (width - shown_width) / 2
        y0 = (height - shown_height) / 2
        self._display_box = (x0, y0, x0 + shown_width, y0 + shown_height)
        self.preview_photo = ImageTk.PhotoImage(display_copy)
        self.canvas.create_image(x0, y0, image=self.preview_photo, anchor="nw")
        if self.crop_mode:
            self.canvas.create_text(
                width // 2, 12, text="DRAG TO CROP · ESC TO CANCEL", fill="#b91c1c", font=("Segoe UI", 9, "bold")
            )

    def _on_global_mousewheel(self, event: tk.Event) -> None:
        try:
            x0 = self.controls_canvas.winfo_rootx()
            x1 = x0 + self.controls_canvas.winfo_width()
            if x0 <= event.x_root <= x1 and getattr(event, "delta", 0):
                units = int(-1 * (event.delta / 120))
                if units == 0:
                    units = -1 if event.delta > 0 else 1
                self.controls_canvas.yview_scroll(units, "units")
        except (AttributeError, tk.TclError):
            pass

    def _on_global_linux_mousewheel(self, event: tk.Event, direction: int) -> str | None:
        try:
            x0 = self.controls_canvas.winfo_rootx()
            x1 = x0 + self.controls_canvas.winfo_width()
            if x0 <= event.x_root <= x1:
                self.controls_canvas.yview_scroll(direction, "units")
                return "break"
        except (AttributeError, tk.TclError):
            pass
        return None

    def _update_controls_scrollregion(self, _event: tk.Event | None = None) -> None:
        self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox("all"))

    def _resize_controls_inner(self, event: tk.Event) -> None:
        self.controls_canvas.itemconfigure(self._controls_window_id, width=event.width)

    def _update_info(self) -> None:
        if self.preview_image is None:
            self.file_info_var.set("No image loaded")
            self.dimensions_var.set("—")
            self.format_var.set("—")
            self.mode_var.set("—")
            self.size_var.set("—")
            return
        self.file_info_var.set(self.current_path.name if self.current_path else "Unsaved image")
        self.dimensions_var.set(f"{self.preview_image.width:,} × {self.preview_image.height:,} px")
        self.format_var.set(self.source_format)
        self.mode_var.set(self.preview_image.mode)
        try:
            self.size_var.set(self._format_bytes(self.current_path.stat().st_size) if self.current_path and self.current_path.exists() else "Not saved yet")
        except OSError:
            self.size_var.set("Unavailable")

    @staticmethod
    def _format_bytes(size: int) -> str:
        amount = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if amount < 1024 or unit == "TB":
                return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{size} B"

    # --------------------------------------------------------- compare preview
    def open_compare(self) -> None:
        if self.original_image is None or self.preview_image is None:
            self._no_image_message()
            return
        if self.compare_window is not None and self.compare_window.winfo_exists():
            self.compare_window.deiconify()
            self.compare_window.lift()
            self._redraw_compare()
            return
        window = tk.Toplevel(self.root)
        self.compare_window = window
        window.title("Before / After Comparison")
        window.geometry("1100x600")
        window.minsize(700, 400)
        container = ttk.Frame(window, padding=10)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(1, weight=1)
        ttk.Label(container, text="BEFORE · Original", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 6), padx=(0, 5))
        ttk.Label(container, text="AFTER · Current edits", font=("Segoe UI", 11, "bold")).grid(row=0, column=1, sticky="w", pady=(0, 6), padx=(5, 0))
        self.compare_original_canvas = tk.Canvas(container, background="#e6ebf2", highlightthickness=0)
        self.compare_current_canvas = tk.Canvas(container, background="#e6ebf2", highlightthickness=0)
        self.compare_original_canvas.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        self.compare_current_canvas.grid(row=1, column=1, sticky="nsew", padx=(5, 0))
        self.compare_original_canvas.bind("<Configure>", lambda _e: self._redraw_compare())
        self.compare_current_canvas.bind("<Configure>", lambda _e: self._redraw_compare())
        ttk.Label(container, text="The left pane shows the initially opened image. The right pane shows your current edits.", style="Subtitle.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        window.protocol("WM_DELETE_WINDOW", self._close_compare)
        self._redraw_compare()

    def _draw_compare_canvas(self, canvas: tk.Canvas, image: Image.Image, side: str) -> ImageTk.PhotoImage:
        canvas.delete("all")
        width, height = max(canvas.winfo_width(), 1), max(canvas.winfo_height(), 1)
        preview = ImageOps.contain(image.copy(), (max(width - 16, 1), max(height - 16, 1)), method=Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(preview)
        canvas.create_image(width // 2, height // 2, image=photo, anchor="center")
        canvas.create_text(8, 8, text=f"{side}: {image.width} × {image.height}", anchor="nw", fill="#334155", font=("Segoe UI", 9, "bold"))
        return photo

    def _redraw_compare(self) -> None:
        if self.compare_window is None:
            return
        try:
            if not self.compare_window.winfo_exists() or self.original_image is None or self.preview_image is None:
                return
            if self.compare_original_canvas is not None:
                self.compare_original_photo = self._draw_compare_canvas(self.compare_original_canvas, self.original_image, "Original")
            if self.compare_current_canvas is not None:
                self.compare_current_photo = self._draw_compare_canvas(self.compare_current_canvas, self.preview_image, "Edited")
        except tk.TclError:
            pass

    def _close_compare(self) -> None:
        if self.compare_window is not None:
            try:
                self.compare_window.destroy()
            except tk.TclError:
                pass
        self.compare_window = None
        self.compare_original_canvas = None
        self.compare_current_canvas = None
        self.compare_original_photo = None
        self.compare_current_photo = None

    # ---------------------------------------------------------- about / help
    def show_about(self) -> None:
        about = tk.Toplevel(self.root)
        about.title(f"About {APP_NAME}")
        about.geometry("430x340")
        about.resizable(False, False)
        about.transient(self.root)
        about.grab_set()
        body = ttk.Frame(about, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="PHOTO EDITOR STUDIO", font=("Segoe UI", 17, "bold"), foreground="#1d4ed8").pack(pady=(4, 4))
        ttk.Label(body, text=f"Version {APP_VERSION}", font=("Segoe UI", 10, "bold")).pack(pady=(0, 16))
        ttk.Separator(body).pack(fill="x", pady=(0, 14))
        ttk.Label(body, text="A simple desktop tool for editing and exporting images.", wraplength=350, justify="center").pack(pady=5)
        ttk.Label(body, text=f"Created by {APP_AUTHOR}", font=("Segoe UI", 10, "bold")).pack(pady=(15, 5))
        ttk.Label(body, text="Built with Python, Tkinter, and Pillow.", style="Subtitle.TLabel").pack(pady=3)
        ttk.Label(body, text="Thank you for using this tool.", font=("Segoe UI", 10, "italic")).pack(pady=(12, 14))
        ttk.Button(body, text="Close", command=about.destroy).pack()

    def show_shortcuts(self) -> None:
        shortcuts = (
            "Ctrl + O       Open image\n"
            "Ctrl + S       Save As\n"
            "Ctrl + Shift + S       Save As\n"
            "Ctrl + Z       Undo\n"
            "Ctrl + Y       Redo\n"
            "Ctrl + R       Reset to original\n"
            "Ctrl + Shift + C       Compare before / after\n"
            "Esc       Cancel crop selection\n"
            "F1       About Photo Editor Studio\n\n"
            "For interactive cropping, choose Select Crop Area and drag a rectangle on the image."
        )
        messagebox.showinfo("Keyboard Shortcuts", shortcuts, parent=self.root)

    def _bind_shortcuts(self) -> None:
        self.root.bind_all("<Control-o>", lambda _e: self.open_image())
        self.root.bind_all("<Control-s>", lambda _e: self.save_image())
        self.root.bind_all("<Control-Shift-s>", lambda _e: self.save_image())
        self.root.bind_all("<Control-z>", lambda _e: self.undo())
        self.root.bind_all("<Control-y>", lambda _e: self.redo())
        self.root.bind_all("<Control-r>", lambda _e: self.reset_image())
        self.root.bind_all("<Control-Shift-c>", lambda _e: self.open_compare())
        self.root.bind_all("<Escape>", self.cancel_crop)
        self.root.bind_all("<F1>", lambda _e: self.show_about())


def create_root() -> tk.Tk:
    """Use a TkinterDnD root when the optional dependency is installed."""
    if DND_AVAILABLE and TkinterDnD is not None:
        try:
            return TkinterDnD.Tk()
        except (tk.TclError, RuntimeError):
            pass
    return tk.Tk()


def main() -> None:
    root = create_root()
    PhotoEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
