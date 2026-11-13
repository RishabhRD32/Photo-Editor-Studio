# PHOTO EDITOR STUDIO — VERSION 1.0

**Created by Rishabdev Tripathi**

## OVERVIEW

A standalone desktop photo editor built with Python, Tkinter, and Pillow.  
The app works offline; images are processed locally on your computer.

## FEATURES

- Open/change images using a file picker
- Brightness, contrast, sharpness and color saturation sliders
- Reset each adjustment individually or reset all adjustments
- Undo and redo (up to 12 previous states)
- Interactive crop: drag a selection rectangle over the preview
- Custom width and height with optional aspect-ratio lock
- Rotate left/right by 90 degrees; flip horizontally or vertically
- Blur, emboss, edge enhancement, grayscale, and sepia effects
- Side-by-side before/after comparison
- Save as PNG, JPEG, WebP, BMP, or TIFF
- JPEG/WebP quality setting
- Image information: file name, current dimensions, format, color mode, and on-disk file size
- Keyboard shortcuts
- About page with app name, version, and author
- Resizable window and scrollable control panel
- Optional file drag-and-drop support

## REQUIREMENTS

- Python 3.10 or newer recommended
- Pillow 9.1 or newer
- Tkinter (included with most standard Windows Python installations)

## INSTALL REQUIRED DEPENDENCY

Open PowerShell or Command Prompt in the folder containing the script, then run:

```powershell
python -m pip install --upgrade pillow
```

## OPTIONAL: ENABLE DRAG-AND-DROP

```powershell
python -m pip install tkinterdnd2
```

If `tkinterdnd2` is not installed, open images using the **Open Image** button or `Ctrl+O`.

## RUN

```powershell
python photo_editor_studio.py
```

## KEYBOARD SHORTCUTS

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open image |
| `Ctrl+S` | Save As |
| `Ctrl+Shift+S` | Save As |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+R` | Reset to original |
| `Ctrl+Shift+C` | Compare before/after |
| `Esc` | Cancel crop selection |
| `F1` | About page |

## HOW TO CROP

1. Open an image.
2. Click **Select Crop Area**.
3. Drag over the portion of the image you want to keep.
4. Release the mouse; the crop is applied. Use **Undo** to reverse it.

## HOW TO RESIZE

1. Edit the **Width** or **Height** field.
2. Leave **Maintain aspect ratio** checked to preserve the original ratio.
3. Uncheck it only when stretching/distorting the image is intended.
4. Click **Apply Custom Resize**.

## NOTES

- The initial opened image remains available as the 'before' image in Compare.
- Save quality applies to JPEG and WebP. PNG uses lossless compression.
- Undo/redo history is limited to 12 states to reduce memory usage.
- Images are processed locally; this app does not upload pictures to a server.
- Very large resize requests are limited to help prevent accidental excessive memory use.
