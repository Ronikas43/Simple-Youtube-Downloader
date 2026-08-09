import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import os
import re
import json
import sys

# ============================================================
# YouTube Downloader 1.0.1
# ============================================================

VERSION = "1.0.1"

# Program directory (works both as script and frozen .exe)
BASE_DIR = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, "frozen", False) else __file__
))

YTDLP = os.path.join(BASE_DIR, "yt-dlp.exe")
FFMPEG = os.path.join(BASE_DIR, "ffmpeg.exe")

CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

DOWNLOAD_FOLDER = os.path.join(os.path.expanduser("~"), "Downloads")

# ============================================================
# GLOBAL STATE
# ============================================================

video_info = None
checking_video = False


# ============================================================
# GUI HELPERS
# ============================================================

def set_status(text):
    root.after(0, lambda: status_label.config(text=text))


def set_progress(value):
    value = max(0, min(100, value))
    root.after(0, lambda: progress_bar.config(value=value))


def set_buttons(enabled):
    state = "normal" if enabled else "disabled"
    root.after(0, lambda: download_button.config(state=state))


def check_files():
    missing = [name for name, path in (("yt-dlp.exe", YTDLP), ("ffmpeg.exe", FFMPEG))
               if not os.path.isfile(path)]
    if missing:
        messagebox.showerror(
            "Missing files",
            "The following files are missing:\n\n" + "\n".join(missing) +
            "\n\nMake sure they are in the same folder as the YouTube Downloader EXE."
        )
        return False
    return True


# ============================================================
# VIDEO CHECK
# ============================================================

def url_changed(event=None):
    url = url_entry.get().strip()
    if url and ("youtube.com/" in url or "youtu.be/" in url):
        check_video()


def check_video():
    global checking_video

    if checking_video:
        return

    url = url_entry.get().strip()
    if not url or not check_files():
        return

    checking_video = True
    set_status("Checking video qualities...")
    set_progress(0)
    set_buttons(False)

    threading.Thread(target=get_video_info, args=(url,), daemon=True).start()


def get_video_info(url):
    global video_info

    command = [YTDLP, "--dump-single-json", "--skip-download", "--no-warnings", url]

    try:
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW
        )

        if result.returncode != 0:
            root.after(0, lambda: check_failed(result.stdout))
            return

        video_info = json.loads(result.stdout)
        root.after(0, check_finished)

    except Exception as e:
        root.after(0, lambda: check_failed(str(e)))


def check_failed(error):
    global checking_video
    checking_video = False
    set_buttons(True)
    set_status("Could not check video.")
    messagebox.showerror("Error", "yt-dlp could not read the video.\n\n" + error[-1500:])


def check_finished():
    global checking_video
    checking_video = False

    update_quality_list()
    set_buttons(True)
    set_progress(100)

    title = video_info.get("title", "Unknown video")
    duration = video_info.get("duration")

    duration_text = ""
    if duration:
        minutes, seconds = int(duration // 60), int(duration % 60)
        duration_text = f" • {minutes}:{seconds:02d}"

    set_status(f"Ready • {title}{duration_text}")


# ============================================================
# QUALITY DETECTION
# ============================================================

QUALITY_NAMES = {
    4320: "4320p (8K)", 2160: "2160p (4K)", 1440: "1440p",
    1080: "1080p", 720: "720p", 480: "480p", 360: "360p",
    240: "240p", 144: "144p"
}


def update_quality_list():
    if not video_info:
        return

    heights = {
        int(fmt["height"]) for fmt in video_info.get("formats", [])
        if fmt.get("height") and fmt.get("vcodec") and fmt.get("vcodec") != "none"
    }

    available = ["Best available"] + [
        QUALITY_NAMES.get(h, f"{h}p") for h in sorted(heights, reverse=True)
    ]

    quality_combo["values"] = available
    quality_combo.current(0)


def get_height():
    match = re.search(r"(\d+)p", quality_combo.get())
    return int(match.group(1)) if match else None


# ============================================================
# DOWNLOAD TYPE / FORMAT UI
# ============================================================

def download_type_changed():
    download_type = download_type_var.get()

    if download_type == "Video":
        format_label.config(text="Video format:")
        format_combo["values"] = ["Original", "MP4", "MKV", "WebM"]
        format_combo.current(0)
        quality_label.pack(anchor="w")
        quality_combo.pack(fill="x", pady=(5, 15))
        thumbnail_check.pack(anchor="w", padx=30, pady=(0, 5))

    elif download_type == "Audio":
        format_label.config(text="Audio format:")
        format_combo["values"] = ["Original", "MP3", "OGG", "WAV"]
        format_combo.current(0)
        quality_label.pack(anchor="w")
        quality_combo.pack(fill="x", pady=(5, 15))
        quality_combo["values"] = ["Best available"]
        quality_combo.current(0)
        thumbnail_check.pack(anchor="w", padx=30, pady=(0, 5))

    else:  # Thumbnail
        format_label.config(text="Thumbnail format:")
        format_combo["values"] = ["JPG", "PNG", "WebP"]
        format_combo.current(0)
        quality_label.pack_forget()
        quality_combo.pack_forget()
        thumbnail_check.pack_forget()


def format_changed(event=None):
    if download_type_var.get() == "Video" and format_combo.get() == "Original":
        set_status("Original format selected")


# ============================================================
# FOLDER
# ============================================================

def browse_folder():
    global DOWNLOAD_FOLDER

    folder = filedialog.askdirectory(title="Choose download folder", initialdir=DOWNLOAD_FOLDER)
    if folder:
        DOWNLOAD_FOLDER = folder
        folder_entry.config(state="normal")
        folder_entry.delete(0, tk.END)
        folder_entry.insert(0, DOWNLOAD_FOLDER)
        folder_entry.config(state="readonly")


# ============================================================
# BUILD YT-DLP COMMAND
# ============================================================

def build_command():
    url = url_entry.get().strip()
    download_type = download_type_var.get()
    selected_format = format_combo.get()
    output = os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s")

    command = [
        YTDLP,
        "--newline", "--progress", "--no-warnings",
        "-N", "8",
        "--retries", "10", "--fragment-retries", "10",
        "--ffmpeg-location", BASE_DIR,
        "-o", output
    ]

    # -------------------- THUMBNAIL --------------------
    if download_type == "Thumbnail":
        command += ["--skip-download", "--write-thumbnail",
                    "--convert-thumbnails", selected_format.lower()]
        return command + [url]

    # -------------------- AUDIO --------------------
    if download_type == "Audio":
        if selected_format == "Original":
            command += ["-f", "ba/b"]
        elif selected_format == "MP3":
            command += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
        elif selected_format == "OGG":
            command += ["-x", "--audio-format", "vorbis", "--audio-quality", "0"]
        elif selected_format == "WAV":
            command += ["-x", "--audio-format", "wav"]
        return command + [url]

    # -------------------- VIDEO --------------------
    height = get_height()
    height_filter = f"[height<={height}]" if height else ""

    if selected_format == "Original":
        command += ["-f", f"bv*{height_filter}+ba/b{height_filter}"]

    elif selected_format == "MP4":
        command += [
            "-f", f"bv*{height_filter}[ext=mp4]+ba[ext=m4a]/bv*{height_filter}+ba/b{height_filter}",
            "--merge-output-format", "mp4"
        ]

    elif selected_format in ("MKV", "WebM"):
        command += [
            "-f", f"bv*{height_filter}+ba/b{height_filter}",
            "--merge-output-format", "mkv" if selected_format == "MKV" else "webm"
        ]

    if thumbnail_var.get():
        command += ["--write-thumbnail"]

    return command + [url]


# ============================================================
# DOWNLOAD
# ============================================================

def start_download():
    if not check_files():
        return

    url = url_entry.get().strip()
    if not url:
        messagebox.showwarning("No URL", "Paste a YouTube URL first.")
        return

    set_buttons(False)
    set_progress(0)
    set_status("Starting download...")

    threading.Thread(target=download_worker, daemon=True).start()


def download_worker():
    command = build_command()
    output_lines = []

    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            bufsize=1, universal_newlines=True,
            creationflags=CREATE_NO_WINDOW
        )

        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue

            output_lines.append(line)

            percentage_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            speed_match = re.search(r"at\s+([^\s]+)", line)
            eta_match = re.search(r"ETA\s+([^\s]+)", line)

            if percentage_match:
                try:
                    set_progress(float(percentage_match.group(1)))
                except ValueError:
                    pass

            status = get_status_text(line)

            if percentage_match:
                try:
                    status += f" {float(percentage_match.group(1)):.1f}%"
                except ValueError:
                    pass

            if speed_match:
                status += f" • {speed_match.group(1)}"
            if eta_match:
                status += f" • ETA {eta_match.group(1)}"

            set_status(status)

        process.wait()

        if process.returncode == 0:
            root.after(0, download_complete)
        else:
            error_text = "\n".join(output_lines[-25:])
            root.after(0, lambda: download_failed(error_text))

    except Exception as e:
        root.after(0, lambda: download_exception(str(e)))


def get_status_text(line):
    if "Merging" in line:
        return "Merging files..."
    if "Downloading" in line:
        return "Downloading..."
    if "Fixing" in line:
        return "Processing..."
    return "Downloading..."


def download_complete():
    set_progress(100)
    set_buttons(True)
    set_status("Download complete!")
    messagebox.showinfo("Finished", "Download completed successfully.")


def download_failed(error_text=""):
    set_status("Download failed.")
    set_buttons(True)
    messagebox.showerror(
        "Download failed",
        "yt-dlp was unable to complete the download.\n\n"
        + (error_text[-1500:] if error_text else "Check the URL and try again.")
    )


def download_exception(error):
    set_status("Error.")
    set_buttons(True)
    messagebox.showerror("Error", error)


# ============================================================
# MAIN WINDOW
# ============================================================

root = tk.Tk()
root.title("YouTube Downloader 1.0.1")
root.geometry("650x600")
root.resizable(False, False)

ttk.Label(root, text="YouTube Downloader 1.0.1",
          font=("Segoe UI", 18, "bold")).pack(pady=(20, 15))

# ---- URL ----
url_frame = ttk.Frame(root)
url_frame.pack(fill="x", padx=30)
ttk.Label(url_frame, text="Video URL:").pack(anchor="w")

url_entry = ttk.Entry(url_frame)
url_entry.pack(fill="x", pady=(5, 15))
url_entry.bind("<FocusOut>", url_changed)
url_entry.bind("<Return>", url_changed)

# ---- DOWNLOAD TYPE ----
type_frame = ttk.LabelFrame(root, text="What do you want to download?")
type_frame.pack(fill="x", padx=30, pady=(0, 15))

download_type_var = tk.StringVar(value="Video")

for label, value in (("Video", "Video"), ("Audio", "Audio"), ("Thumbnail", "Thumbnail")):
    ttk.Radiobutton(type_frame, text=label, variable=download_type_var, value=value,
                     command=download_type_changed).pack(side="left", padx=20, pady=10)

# ---- OPTIONS ----
options_frame = ttk.Frame(root)
options_frame.pack(fill="x", padx=30)

format_frame = ttk.Frame(options_frame)
format_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))

format_label = ttk.Label(format_frame, text="Video format:")
format_label.pack(anchor="w")

format_combo = ttk.Combobox(format_frame, values=["Original", "MP4", "MKV", "WebM"], state="readonly")
format_combo.pack(fill="x", pady=(5, 15))
format_combo.current(0)
format_combo.bind("<<ComboboxSelected>>", format_changed)

quality_frame = ttk.Frame(options_frame)
quality_frame.pack(side="left", fill="x", expand=True, padx=(10, 0))

quality_label = ttk.Label(quality_frame, text="Quality:")
quality_label.pack(anchor="w")

quality_combo = ttk.Combobox(quality_frame, values=["Best available"], state="readonly")
quality_combo.pack(fill="x", pady=(5, 15))
quality_combo.current(0)

# ---- CHECKBOXES ----
thumbnail_var = tk.BooleanVar(value=False)
thumbnail_check = ttk.Checkbutton(root, text="Also download thumbnail", variable=thumbnail_var)

# ---- SAVE FOLDER ----
folder_frame = ttk.Frame(root)
folder_frame.pack(fill="x", padx=30, pady=(5, 0))
ttk.Label(folder_frame, text="Save to:").pack(anchor="w")

folder_row = ttk.Frame(folder_frame)
folder_row.pack(fill="x", pady=(5, 15))

folder_entry = ttk.Entry(folder_row)
folder_entry.pack(side="left", fill="x", expand=True)
folder_entry.insert(0, DOWNLOAD_FOLDER)
folder_entry.config(state="readonly")

ttk.Button(folder_row, text="Browse", command=browse_folder).pack(side="left", padx=(8, 0))

# ---- DOWNLOAD BUTTON ----
download_button = ttk.Button(root, text="DOWNLOAD", command=start_download)
download_button.pack(pady=(5, 15), ipadx=40, ipady=8)

# ---- PROGRESS / STATUS ----
progress_bar = ttk.Progressbar(root, orient="horizontal", length=590, mode="determinate", maximum=100)
progress_bar.pack(pady=(0, 8))

status_label = ttk.Label(root, text="Ready")
status_label.pack()

# ---- INIT ----
download_type_changed()

root.mainloop()