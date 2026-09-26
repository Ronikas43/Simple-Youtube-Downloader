import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import os
import re
import json
import sys
import shutil
import zipfile
import urllib.request
import urllib.error

# ============================================================
# YouTube Downloader 1.1.0
# ============================================================

VERSION = "1.1.0"

# Program directory (works both as script and frozen .exe)
BASE_DIR = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, "frozen", False) else __file__
))

YTDLP = os.path.join(BASE_DIR, "yt-dlp.exe")
FFMPEG = os.path.join(BASE_DIR, "ffmpeg.exe")
FFPROBE = os.path.join(BASE_DIR, "ffprobe.exe")

CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

DOWNLOAD_FOLDER = os.path.join(os.path.expanduser("~"), "Downloads")

# ============================================================
# UPDATER SETTINGS
# ============================================================

USER_AGENT = "Simple-Youtube-Downloader-Updater"

YTDLP_DIRECT_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
YTDLP_RELEASES_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"

FFMPEG_RELEASES_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
FFMPEG_ASSET_NAME = "ffmpeg-master-latest-win64-gpl.zip"

APP_RELEASES_API = "https://api.github.com/repos/Ronikas43/Simple-Youtube-Downloader/releases/latest"

UPDATE_STATE_FILE = os.path.join(BASE_DIR, "update_state.json")

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


def ask_yes_no_blocking(title, message):
    """Show a yes/no dialog from a background thread and block until answered."""
    result = {}
    event = threading.Event()

    def show():
        result["value"] = messagebox.askyesno(title, message)
        event.set()

    root.after(0, show)
    event.wait()
    return result.get("value", False)


def check_files():
    missing = [name for name, path in (("yt-dlp.exe", YTDLP), ("ffmpeg.exe", FFMPEG))
               if not os.path.isfile(path)]
    if missing:
        messagebox.showerror(
            "Missing files",
            "The following files are missing:\n\n" + "\n".join(missing) +
            "\n\nRestart the app to be prompted to download them, or place them "
            "in the same folder as the YouTube Downloader EXE."
        )
        return False
    return True


# ============================================================
# UPDATER
# ============================================================

def load_update_state():
    try:
        with open(UPDATE_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_update_state(state):
    try:
        with open(UPDATE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def download_file(url, dest_path, on_progress=None):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    with urllib.request.urlopen(request, timeout=30) as response:
        total = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        tmp_path = dest_path + ".tmp"

        with open(tmp_path, "wb") as f:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break

                f.write(chunk)
                downloaded += len(chunk)

                if on_progress and total:
                    on_progress(downloaded / total * 100)

    os.replace(tmp_path, dest_path)


def get_latest_release(repo_api_url):
    """Returns the latest release's JSON, or None if the repo has no releases."""
    request = urllib.request.Request(repo_api_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def fetch_latest_ffmpeg_asset():
    release = get_latest_release(FFMPEG_RELEASES_API)
    if not release:
        return None
    return next(
        (a for a in release.get("assets", []) if a.get("name") == FFMPEG_ASSET_NAME),
        None
    )


def install_ffmpeg_asset(asset):
    set_status("Downloading ffmpeg...")
    set_progress(0)

    zip_path = os.path.join(BASE_DIR, "_ffmpeg_update.zip")
    download_file(asset["browser_download_url"], zip_path, on_progress=set_progress)

    extracted = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            filename = os.path.basename(member)
            if filename in ("ffmpeg.exe", "ffprobe.exe"):
                target_path = os.path.join(BASE_DIR, filename)
                with archive.open(member) as source, open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)
                extracted.append(filename)

    os.remove(zip_path)

    if "ffmpeg.exe" in extracted:
        state = load_update_state()
        state["ffmpeg_asset_id"] = asset.get("id")
        save_update_state(state)

    set_progress(100)


def install_missing_files(missing):
    """Downloads whichever of yt-dlp.exe / ffmpeg.exe are missing. Returns the set installed."""
    installed = set()

    if "yt-dlp.exe" in missing:
        set_status("Downloading yt-dlp...")
        set_progress(0)
        download_file(YTDLP_DIRECT_URL, YTDLP, on_progress=set_progress)
        installed.add("yt-dlp.exe")

    if "ffmpeg.exe" in missing:
        asset = fetch_latest_ffmpeg_asset()
        if asset:
            install_ffmpeg_asset(asset)
            installed.add("ffmpeg.exe")

    return installed


def check_ytdlp_update_prompt():
    result = subprocess.run(
        [YTDLP, "--version"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        creationflags=CREATE_NO_WINDOW
    )
    installed = (result.stdout or "").strip().splitlines()[-1] if result.stdout else ""

    release = get_latest_release(YTDLP_RELEASES_API)
    latest = release.get("tag_name", "").lstrip("vV") if release else None

    if not latest or latest == installed:
        return

    wants_update = ask_yes_no_blocking(
        "yt-dlp update available",
        f"A new version of yt-dlp is available.\n\n"
        f"Installed: {installed or 'unknown'}\nLatest: {latest}\n\nUpdate now?"
    )

    if wants_update:
        set_status("Updating yt-dlp...")
        subprocess.run(
            [YTDLP, "-U"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW
        )


def check_ffmpeg_update_prompt():
    asset = fetch_latest_ffmpeg_asset()
    if not asset:
        return

    state = load_update_state()
    if state.get("ffmpeg_asset_id") == asset.get("id"):
        return

    wants_update = ask_yes_no_blocking(
        "ffmpeg update available",
        "A new build of ffmpeg is available.\n\nUpdate now?"
    )

    if wants_update:
        install_ffmpeg_asset(asset)


def cleanup_stale_update_files():
    """Removes leftovers from a previous update attempt that didn't finish."""
    if getattr(sys, "frozen", False):
        for suffix in (".new", ".new.tmp"):
            stray = sys.executable + suffix
            if os.path.isfile(stray):
                try:
                    os.remove(stray)
                except Exception:
                    pass

    stray_script = os.path.join(BASE_DIR, "_update.bat")
    if os.path.isfile(stray_script):
        try:
            os.remove(stray_script)
        except Exception:
            pass


def launch_self_update(new_path, target_path):
    """
    A running EXE can't be overwritten directly on Windows - it's locked
    while in use. Instead, write a small helper script that waits for this
    process to exit, swaps the new file into place, and deletes itself.
    Doesn't relaunch the app - the user reopens it themselves.
    """
    script_path = os.path.join(BASE_DIR, "_update.bat")

    script = (
        "@echo off\r\n"
        "setlocal\r\n"
        f'set "NEWFILE={new_path}"\r\n'
        f'set "TARGET={target_path}"\r\n'
        "set COUNT=0\r\n"
        ":retry\r\n"
        "set /a COUNT+=1\r\n"
        'move /y "%NEWFILE%" "%TARGET%" >NUL 2>&1\r\n'
        "if not errorlevel 1 goto done\r\n"
        "if %COUNT% GEQ 30 goto done\r\n"
        "timeout /t 1 /nobreak >NUL\r\n"
        "goto retry\r\n"
        ":done\r\n"
        'del "%~f0"\r\n'
    )

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    subprocess.Popen(
        ["cmd", "/c", script_path],
        creationflags=CREATE_NO_WINDOW,
        cwd=BASE_DIR
    )


def finish_update(latest):
    messagebox.showinfo(
        "Update downloaded",
        f"Updated to version {latest}.\n\nReopen the program to use the new version."
    )
    os._exit(0)


def apply_app_update(asset, latest):
    set_status("Downloading new app version...")
    set_progress(0)

    if not getattr(sys, "frozen", False):
        # Running as a plain .py file - there's no running EXE to swap out,
        # so just drop the new build next to it.
        new_path = os.path.join(BASE_DIR, asset["name"])
        download_file(asset["browser_download_url"], new_path, on_progress=set_progress)
        set_progress(100)
        root.after(0, lambda: messagebox.showinfo(
            "Update downloaded",
            f"Downloaded version {latest} to:\n{new_path}\n\nRun it to switch to the new version."
        ))
        return

    target_path = sys.executable
    new_path = target_path + ".new"

    download_file(asset["browser_download_url"], new_path, on_progress=set_progress)
    set_progress(100)

    launch_self_update(new_path, target_path)
    root.after(0, lambda: finish_update(latest))


def check_app_update_prompt():
    release = get_latest_release(APP_RELEASES_API)
    if not release:
        return  # no releases published on the repo yet

    latest = release.get("tag_name", "").lstrip("vV")
    if not latest or latest == VERSION:
        return

    asset = next(
        (a for a in release.get("assets", []) if a.get("name", "").lower().endswith(".exe")),
        None
    )
    if not asset:
        return  # release has no downloadable .exe attached

    wants_update = ask_yes_no_blocking(
        "Update available",
        f"A new version of Simple Youtube Downloader is available.\n\n"
        f"Installed: {VERSION}\nLatest: {latest}\n\nDownload and install it now?"
    )
    if not wants_update:
        return

    try:
        apply_app_update(asset, latest)
    except Exception as e:
        root.after(0, lambda: messagebox.showerror(
            "Update failed", f"Could not install the update:\n\n{e}"
        ))


def startup_checks():
    cleanup_stale_update_files()

    set_buttons(False)
    set_status("Checking files...")

    missing = [name for name, path in (("yt-dlp.exe", YTDLP), ("ffmpeg.exe", FFMPEG))
               if not os.path.isfile(path)]
    just_installed = set()

    if missing:
        wants_download = ask_yes_no_blocking(
            "Required files missing",
            "The following required files were not found:\n\n" + "\n".join(missing) +
            "\n\nDownload them now?"
        )

        if wants_download:
            try:
                just_installed = install_missing_files(missing)
            except Exception as e:
                root.after(0, lambda: messagebox.showerror(
                    "Download failed", f"Could not download required files:\n\n{e}"
                ))

    try:
        if os.path.isfile(YTDLP) and "yt-dlp.exe" not in just_installed:
            check_ytdlp_update_prompt()
    except (urllib.error.URLError, urllib.error.HTTPError):
        pass  # no internet / GitHub unreachable - skip silently
    except Exception:
        pass

    try:
        if os.path.isfile(FFMPEG) and "ffmpeg.exe" not in just_installed:
            check_ffmpeg_update_prompt()
    except (urllib.error.URLError, urllib.error.HTTPError):
        pass
    except Exception:
        pass

    try:
        check_app_update_prompt()
    except (urllib.error.URLError, urllib.error.HTTPError):
        pass
    except Exception:
        pass

    set_progress(0)
    set_buttons(True)
    set_status("Ready")


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
        no_audio_check.pack(anchor="w", padx=30, pady=(0, 5))

    elif download_type == "Audio":
        format_label.config(text="Audio format:")
        format_combo["values"] = ["Original", "MP3", "OGG", "WAV"]
        format_combo.current(0)
        quality_label.pack(anchor="w")
        quality_combo.pack(fill="x", pady=(5, 15))
        quality_combo["values"] = ["Best available"]
        quality_combo.current(0)
        thumbnail_check.pack(anchor="w", padx=30, pady=(0, 5))
        no_audio_check.pack_forget()

    else:  # Thumbnail
        format_label.config(text="Thumbnail format:")
        format_combo["values"] = ["JPG", "PNG", "WebP"]
        format_combo.current(0)
        quality_label.pack_forget()
        quality_combo.pack_forget()
        thumbnail_check.pack_forget()
        no_audio_check.pack_forget()


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
    no_audio = no_audio_var.get()

    if no_audio:
        # Video-only, no audio track. Prefer the requested container's native
        # codec, then fall back to any video-only stream (never fall back to
        # a combined format, since that would include audio).
        ext_pref = {"MP4": "[ext=mp4]", "WebM": "[ext=webm]"}.get(selected_format, "")
        command += ["-f", f"bv*{height_filter}{ext_pref}/bv*{height_filter}/bv*"]

        if selected_format in ("MP4", "MKV", "WebM"):
            command += ["--remux-video", selected_format.lower()]

    elif selected_format == "Original":
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
root.title(f"YouTube Downloader {VERSION}")
root.geometry("650x600")
root.resizable(False, False)

ttk.Label(root, text=f"YouTube Downloader {VERSION}",
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

no_audio_var = tk.BooleanVar(value=False)
no_audio_check = ttk.Checkbutton(root, text="Download without audio", variable=no_audio_var)

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
threading.Thread(target=startup_checks, daemon=True).start()

root.mainloop()