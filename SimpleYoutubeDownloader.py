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
# Simple Youtube Downloader 1.2.0
# ============================================================

VERSION = "1.2.0"

# Program directory (works both as script and frozen .exe) - this is where the
# app's own EXE lives, and is only used for self-updating the app itself.
BASE_DIR = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, "frozen", False) else __file__
))


def get_data_dir():
    """
    Folder for yt-dlp/ffmpeg and update-state data, kept out of the app's own
    folder (e.g. Program Files) so nothing extra gets dropped next to the EXE
    and so the app doesn't need admin rights to write there.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")

    data_dir = os.path.join(base, "Simple Youtube Downloader")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


DATA_DIR = get_data_dir()

YTDLP = os.path.join(DATA_DIR, "yt-dlp.exe")
FFMPEG = os.path.join(DATA_DIR, "ffmpeg.exe")
FFPROBE = os.path.join(DATA_DIR, "ffprobe.exe")

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

UPDATE_STATE_FILE = os.path.join(DATA_DIR, "update_state.json")

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
            "\n\nRestart the app to be prompted to download them, or place them in:\n"
            f"{DATA_DIR}"
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

    zip_path = os.path.join(DATA_DIR, "_ffmpeg_update.zip")
    download_file(asset["browser_download_url"], zip_path, on_progress=set_progress)

    extracted = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            filename = os.path.basename(member)
            if filename in ("ffmpeg.exe", "ffprobe.exe"):
                target_path = os.path.join(DATA_DIR, filename)
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
            f"\n\nThey'll be saved to:\n{DATA_DIR}\n\nDownload them now?"
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


def url_pasted(event=None):
    # <<Paste>> fires slightly before the entry's text is actually updated
    # on some platforms, so give it a moment before reading the field.
    root.after(10, url_changed)


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
# QUALITY DETECTION (video resolution + fps + audio sample rate)
# ============================================================

QUALITY_NAMES = {
    4320: "4320p (8K)", 2160: "2160p (4K)", 1440: "1440p",
    1080: "1080p", 720: "720p", 480: "480p", 360: "360p",
    240: "240p", 144: "144p"
}

# Populated once a video has been checked; used to cap the quality/fps
# pickers to what the video actually offers, for both tabs at once so
# switching between Video/Audio doesn't need a re-check.
detected_heights = []
detected_max_fps = None
detected_audio_khz = []
detected_max_khz = None


def update_quality_list():
    global detected_heights, detected_max_fps, detected_audio_khz, detected_max_khz

    if not video_info:
        return

    formats = video_info.get("formats", [])

    heights = {
        int(fmt["height"]) for fmt in formats
        if fmt.get("height") and fmt.get("vcodec") and fmt.get("vcodec") != "none"
    }
    detected_heights = sorted(heights, reverse=True)

    fps_values = {
        round(fmt["fps"]) for fmt in formats
        if fmt.get("fps") and fmt.get("vcodec") and fmt.get("vcodec") != "none"
    }
    detected_max_fps = max(fps_values) if fps_values else None

    khz_values = {
        round(fmt["asr"] / 1000, 1) for fmt in formats
        if fmt.get("asr") and fmt.get("acodec") and fmt.get("acodec") != "none"
    }
    detected_audio_khz = sorted(khz_values, reverse=True)
    detected_max_khz = max(khz_values) if khz_values else None

    # Populate whichever tab is active now; the other tab's picker is
    # rebuilt from the same cached detection the moment the user switches
    # to it, so nothing needs to be re-checked on click.
    if download_type_var.get() == "Video":
        apply_video_quality_options()
    elif download_type_var.get() == "Audio":
        apply_audio_quality_options()

    apply_fps_options()


def apply_video_quality_options():
    available = ["Best available"] + [
        QUALITY_NAMES.get(h, f"{h}p") for h in detected_heights
    ]
    quality_combo["values"] = available
    quality_combo.current(0)


def get_height():
    match = re.search(r"(\d+)p", quality_combo.get())
    return int(match.group(1)) if match else None


# ============================================================
# FPS SELECTION (video only)
# ============================================================

FPS_PRESET_VALUES = [60, 50, 48, 30, 25, 24, 20, 10]
ABSOLUTE_MAX_FPS = 60


def get_fps_cap():
    """The highest fps the user is allowed to pick: the checked video's own
    max fps if known (you can't ask for more fps than the source has),
    otherwise the app's absolute ceiling."""
    if detected_max_fps:
        return min(detected_max_fps, ABSOLUTE_MAX_FPS)
    return ABSOLUTE_MAX_FPS


def apply_fps_options():
    """Rebuilds the fps preset list so nothing above the checked video's own
    fps (or the absolute 60fps ceiling) is selectable."""
    cap = get_fps_cap()
    allowed = [v for v in FPS_PRESET_VALUES if v <= cap]
    values = ["Original"] + [str(v) for v in allowed] + ["Custom"]

    current = fps_combo.get()
    fps_combo["values"] = values
    fps_combo.set(current if current in values else "Original")

    fps_selection_changed()
    clamp_fps_entry()


def fps_selection_changed(event=None):
    if fps_combo.get() == "Custom":
        fps_custom_entry.pack(fill="x", pady=(5, 5))
    else:
        fps_custom_entry.pack_forget()


def clamp_fps_entry(event=None):
    """Keeps the custom fps entry numeric and capped at the checked video's fps."""
    raw = fps_custom_entry.get().strip()
    digits = "".join(ch for ch in raw if ch.isdigit())

    if digits != raw:
        fps_custom_entry.delete(0, tk.END)
        fps_custom_entry.insert(0, digits)
        raw = digits

    if not raw:
        return

    cap = get_fps_cap()
    value = int(raw)
    if value > cap:
        fps_custom_entry.delete(0, tk.END)
        fps_custom_entry.insert(0, str(cap))
    elif value < 1:
        fps_custom_entry.delete(0, tk.END)
        fps_custom_entry.insert(0, "1")


def get_fps():
    """Returns the fps cap to use, or None for no limit."""
    if download_type_var.get() != "Video":
        return None

    selection = fps_combo.get()
    cap = get_fps_cap()

    if selection == "Original":
        return None

    if selection == "Custom":
        value = fps_custom_entry.get().strip()
        if value.isdigit() and int(value) > 0:
            return min(int(value), cap)
        return None

    if selection.isdigit():
        return min(int(selection), cap)

    return None


# ============================================================
# AUDIO SAMPLE RATE SELECTION (audio only)
# ============================================================

AUDIO_PRESET_VALUES = [48, 44.1, 32, 24, 16, 12, 8]
MAX_KHZ = 48.0


def get_khz_cap():
    """The highest sample rate the user is allowed to pick: the checked
    video's own max sample rate if known, otherwise the app's ceiling."""
    if detected_max_khz:
        return min(detected_max_khz, MAX_KHZ)
    return MAX_KHZ


def _khz_label(value):
    return str(int(value)) if float(value).is_integer() else str(value)


def apply_audio_quality_options():
    """Rebuilds the kHz preset list so nothing above the checked video's own
    sample rate (or the app's 48kHz ceiling) is selectable."""
    cap = get_khz_cap()
    allowed = [v for v in AUDIO_PRESET_VALUES if v <= cap]
    values = ["Best available"] + [_khz_label(v) for v in allowed] + ["Custom"]

    current = quality_combo.get()
    quality_combo["values"] = values
    quality_combo.set(current if current in values else "Best available")

    quality_selection_changed()
    clamp_khz_entry()


def quality_selection_changed(event=None):
    """Shows the custom kHz entry only in Audio mode with 'Custom' picked."""
    if download_type_var.get() == "Audio" and quality_combo.get() == "Custom":
        khz_custom_entry.pack(fill="x", pady=(5, 5))
    else:
        khz_custom_entry.pack_forget()


def clamp_khz_entry(event=None):
    """Keeps the custom kHz entry numeric (one decimal point allowed) and capped."""
    raw = khz_custom_entry.get().strip()

    cleaned = []
    seen_dot = False
    for ch in raw:
        if ch.isdigit():
            cleaned.append(ch)
        elif ch == "." and not seen_dot:
            cleaned.append(ch)
            seen_dot = True
    cleaned = "".join(cleaned)

    if cleaned != raw:
        khz_custom_entry.delete(0, tk.END)
        khz_custom_entry.insert(0, cleaned)
        raw = cleaned

    if not raw or raw == ".":
        return

    try:
        value = float(raw)
    except ValueError:
        return

    cap = get_khz_cap()
    if value > cap:
        khz_custom_entry.delete(0, tk.END)
        khz_custom_entry.insert(0, _khz_label(cap))


def get_khz():
    """Returns the audio sample-rate cap in kHz to use, or None for no limit."""
    if download_type_var.get() != "Audio":
        return None

    selection = quality_combo.get()
    cap = get_khz_cap()

    if selection == "Best available":
        return None

    if selection == "Custom":
        value = khz_custom_entry.get().strip()
        try:
            parsed = float(value)
        except ValueError:
            return None
        return min(parsed, cap) if parsed > 0 else None

    try:
        return min(float(selection), cap)
    except ValueError:
        return None


# ============================================================
# DOWNLOAD TYPE / FORMAT UI
# ============================================================

def download_type_changed():
    download_type = download_type_var.get()

    if download_type == "Video":
        format_label.config(text="Video format:")
        format_combo["values"] = ["Original", "MP4", "MKV", "WebM"]
        format_combo.current(0)
        quality_label.config(text="Quality:")
        quality_label.pack(anchor="w")
        quality_combo.pack(fill="x", pady=(5, 10))
        khz_custom_entry.pack_forget()
        apply_video_quality_options()
        fps_frame.pack(fill="x", pady=(0, 10))
        apply_fps_options()
        no_audio_check.pack(anchor="w", pady=(0, 5))

    elif download_type == "Audio":
        format_label.config(text="Audio format:")
        format_combo["values"] = ["Original", "MP3", "OGG", "WAV"]
        format_combo.current(0)
        quality_label.config(text="Quality (kHz):")
        quality_label.pack(anchor="w")
        quality_combo.pack(fill="x", pady=(5, 10))
        apply_audio_quality_options()
        fps_frame.pack_forget()
        fps_custom_entry.pack_forget()
        no_audio_check.pack_forget()

    else:  # Thumbnail
        format_label.config(text="Thumbnail format:")
        format_combo["values"] = ["JPG", "PNG", "WebP"]
        format_combo.current(0)
        quality_label.pack_forget()
        quality_combo.pack_forget()
        khz_custom_entry.pack_forget()
        fps_frame.pack_forget()
        fps_custom_entry.pack_forget()
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
        "--ffmpeg-location", DATA_DIR,
        "-o", output
    ]

    # -------------------- THUMBNAIL --------------------
    if download_type == "Thumbnail":
        command += ["--skip-download", "--write-thumbnail",
                    "--convert-thumbnails", selected_format.lower()]
        return command + [url]

    # -------------------- AUDIO --------------------
    if download_type == "Audio":
        khz = get_khz()
        # Filter to existing streams at or under the chosen sample rate
        # instead of forcing a resample - same approach as the video
        # height/fps filters, so "Original" audio really does stay original.
        asr_filter = f"[asr<={int(round(khz * 1000))}]" if khz else ""
        audio_selector = f"ba{asr_filter}/ba/b"

        if selected_format == "Original":
            command += ["-f", audio_selector]
        elif selected_format == "MP3":
            command += ["-f", audio_selector, "-x", "--audio-format", "mp3", "--audio-quality", "0"]
        elif selected_format == "OGG":
            command += ["-f", audio_selector, "-x", "--audio-format", "vorbis", "--audio-quality", "0"]
        elif selected_format == "WAV":
            command += ["-f", audio_selector, "-x", "--audio-format", "wav"]
        return command + [url]

    # -------------------- VIDEO --------------------
    height = get_height()
    height_filter = f"[height<={height}]" if height else ""

    fps = get_fps()
    fps_filter = f"[fps<={fps}]" if fps else ""

    filters = height_filter + fps_filter

    no_audio = no_audio_var.get()

    if no_audio:
        # Video-only, no audio track. Prefer the requested container's native
        # codec, then fall back to any video-only stream (never fall back to
        # a combined format, since that would include audio).
        ext_pref = {"MP4": "[ext=mp4]", "WebM": "[ext=webm]"}.get(selected_format, "")
        command += ["-f", f"bv*{filters}{ext_pref}/bv*{filters}/bv*"]

        if selected_format in ("MP4", "MKV", "WebM"):
            command += ["--remux-video", selected_format.lower()]

    elif selected_format == "Original":
        # Prefer a video+audio pair from the same container family (mp4+m4a,
        # then webm+webm) before falling back to any combo. Without this,
        # yt-dlp could pick a video track whose native container doesn't
        # match its paired audio, so the merged output's extension could
        # differ unpredictably from what "Download without audio" would give
        # for the very same video track.
        command += [
            "-f",
            f"bv*{filters}[ext=mp4]+ba[ext=m4a]/"
            f"bv*{filters}[ext=webm]+ba[ext=webm]/"
            f"bv*{filters}+ba/b{filters}"
        ]

    elif selected_format == "MP4":
        command += [
            "-f", f"bv*{filters}[ext=mp4]+ba[ext=m4a]/bv*{filters}+ba/b{filters}",
            "--merge-output-format", "mp4"
        ]

    elif selected_format in ("MKV", "WebM"):
        command += [
            "-f", f"bv*{filters}+ba/b{filters}",
            "--merge-output-format", "mkv" if selected_format == "MKV" else "webm"
        ]

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
root.title(f"Simple Youtube Downloader {VERSION}")
root.geometry("650x680")
root.resizable(False, False)

ttk.Label(root, text=f"Simple Youtube Downloader {VERSION}",
          font=("Segoe UI", 18, "bold")).pack(pady=(20, 15))

# ---- URL ----
url_frame = ttk.Frame(root)
url_frame.pack(fill="x", padx=30)
ttk.Label(url_frame, text="Video URL:").pack(anchor="w")

url_entry = ttk.Entry(url_frame)
url_entry.pack(fill="x", pady=(5, 15))
url_entry.bind("<FocusOut>", url_changed)
url_entry.bind("<Return>", url_changed)
url_entry.bind("<<Paste>>", url_pasted)
url_entry.bind("<Button-2>", url_pasted)  # middle-click paste (Linux)

# ---- DOWNLOAD TYPE ----
type_frame = ttk.LabelFrame(root, text="What do you want to download?")
type_frame.pack(fill="x", padx=30, pady=(0, 15))

download_type_var = tk.StringVar(value="Video")

for label, value in (("Video", "Video"), ("Audio", "Audio"), ("Thumbnail", "Thumbnail")):
    ttk.Radiobutton(type_frame, text=label, variable=download_type_var, value=value,
                     command=download_type_changed).pack(side="left", padx=20, pady=10)

# ---- OPTIONS (format + quality, and everything that belongs with them) ----
# Everything below - format, quality, fps and "no audio" - lives inside one
# fixed-position options block so toggling between tabs never reshuffles
# where things sit on the screen.
options_block = ttk.Frame(root)
options_block.pack(fill="x", padx=30, pady=(0, 15))

options_frame = ttk.Frame(options_block)
options_frame.pack(fill="x")

format_frame = ttk.Frame(options_frame)
format_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))

format_label = ttk.Label(format_frame, text="Video format:")
format_label.pack(anchor="w")

format_combo = ttk.Combobox(format_frame, values=["Original", "MP4", "MKV", "WebM"], state="readonly")
format_combo.pack(fill="x", pady=(5, 10))
format_combo.current(0)
format_combo.bind("<<ComboboxSelected>>", format_changed)

quality_frame = ttk.Frame(options_frame)
quality_frame.pack(side="left", fill="x", expand=True, padx=(10, 0))

quality_label = ttk.Label(quality_frame, text="Quality:")
quality_label.pack(anchor="w")

quality_combo = ttk.Combobox(quality_frame, values=["Best available"], state="readonly")
quality_combo.pack(fill="x", pady=(5, 10))
quality_combo.current(0)
quality_combo.bind("<<ComboboxSelected>>", quality_selection_changed)

# Custom sample-rate entry, only shown in Audio mode with "Custom" picked.
khz_custom_entry = ttk.Entry(quality_frame)
khz_custom_entry.insert(0, "44.1")
khz_custom_entry.bind("<KeyRelease>", clamp_khz_entry)
khz_custom_entry.bind("<FocusOut>", clamp_khz_entry)
# Not packed here - quality_selection_changed() shows it when needed.

# ---- FPS (video only) - kept right under format/quality, not off at the
# bottom of the window, so it reads as one options block with them.
fps_frame = ttk.Frame(options_block)

ttk.Label(fps_frame, text="FPS:").pack(anchor="w")

fps_combo = ttk.Combobox(fps_frame, values=["Original"] + [str(v) for v in FPS_PRESET_VALUES] + ["Custom"], state="readonly")
fps_combo.pack(fill="x", pady=(5, 0))
fps_combo.current(0)
fps_combo.bind("<<ComboboxSelected>>", fps_selection_changed)

fps_custom_entry = ttk.Entry(fps_frame)
fps_custom_entry.insert(0, "30")
fps_custom_entry.bind("<KeyRelease>", clamp_fps_entry)
fps_custom_entry.bind("<FocusOut>", clamp_fps_entry)
# Not packed here - fps_selection_changed() shows it only when "Custom" is picked.

# ---- CHECKBOXES ----
no_audio_var = tk.BooleanVar(value=False)
no_audio_check = ttk.Checkbutton(options_block, text="Download without audio", variable=no_audio_var)

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