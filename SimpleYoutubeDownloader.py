import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import os
import re
import json
import sys


# ============================================================
# YouTube Downloader 1.0
# ============================================================

VERSION = "1.0"


# ============================================================
# FIND PROGRAM DIRECTORY
# ============================================================

if getattr(sys, "frozen", False):

    BASE_DIR = os.path.dirname(
        os.path.abspath(sys.executable)
    )

else:

    BASE_DIR = os.path.dirname(
        os.path.abspath(__file__)
    )


YTDLP = os.path.join(
    BASE_DIR,
    "yt-dlp.exe"
)

FFMPEG = os.path.join(
    BASE_DIR,
    "ffmpeg.exe"
)


# ============================================================
# HIDE CONSOLE WINDOWS ON WINDOWS
# ============================================================

if sys.platform == "win32":

    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW

else:

    CREATE_NO_WINDOW = 0


# ============================================================
# DEFAULT DOWNLOAD FOLDER
# ============================================================

DOWNLOAD_FOLDER = os.path.join(
    os.path.expanduser("~"),
    "Downloads"
)


# ============================================================
# GLOBAL VARIABLES
# ============================================================

video_info = None
checking_video = False


# ============================================================
# GUI HELPERS
# ============================================================

def set_status(text):

    root.after(
        0,
        lambda: status_label.config(
            text=text
        )
    )


def set_progress(value):

    root.after(
        0,
        lambda: progress_bar.config(
            value=value
        )
    )


def set_buttons(enabled):

    state = (
        "normal"
        if enabled
        else "disabled"
    )

    root.after(
        0,
        lambda: download_button.config(
            state=state
        )
    )


# ============================================================
# CHECK REQUIRED FILES
# ============================================================

def check_files():

    missing = []

    if not os.path.isfile(YTDLP):

        missing.append(
            "yt-dlp.exe"
        )

    if not os.path.isfile(FFMPEG):

        missing.append(
            "ffmpeg.exe"
        )

    if missing:

        messagebox.showerror(

            "Missing files",

            "The following files are missing:\n\n"
            + "\n".join(missing)
            + "\n\n"
            "Make sure they are in the same folder "
            "as the YouTube Downloader EXE."
        )

        return False

    return True


# ============================================================
# AUTOMATIC URL CHECK
# ============================================================

def url_changed(event=None):

    url = url_entry.get().strip()

    if not url:
        return

    if (
        "youtube.com/" not in url
        and
        "youtu.be/" not in url
    ):
        return

    check_video()


# ============================================================
# CHECK VIDEO
# ============================================================

def check_video():

    global checking_video

    if checking_video:
        return

    url = url_entry.get().strip()

    if not url:
        return

    if not check_files():
        return

    checking_video = True

    set_status(
        "Checking video qualities..."
    )

    set_progress(0)

    set_buttons(False)

    threading.Thread(
        target=get_video_info,
        args=(url,),
        daemon=True
    ).start()


# ============================================================
# GET VIDEO INFORMATION
# ============================================================

def get_video_info(url):

    global video_info

    command = [

        YTDLP,

        "--dump-single-json",

        "--skip-download",

        "--no-warnings",

        url
    ]

    try:

        result = subprocess.run(

            command,

            stdout=subprocess.PIPE,

            stderr=subprocess.STDOUT,

            text=True,

            encoding="utf-8",

            errors="replace",

            creationflags=CREATE_NO_WINDOW
        )

        if result.returncode != 0:

            root.after(

                0,

                lambda: check_failed(
                    result.stdout
                )
            )

            return

        video_info = json.loads(
            result.stdout
        )

        root.after(
            0,
            check_finished
        )

    except Exception as e:

        root.after(

            0,

            lambda: check_failed(
                str(e)
            )
        )


# ============================================================
# CHECK FAILED
# ============================================================

def check_failed(error):

    global checking_video

    checking_video = False

    set_buttons(True)

    set_status(
        "Could not check video."
    )

    messagebox.showerror(

        "Error",

        "yt-dlp could not read the video.\n\n"
        + error[-1500:]
    )


# ============================================================
# CHECK FINISHED
# ============================================================

def check_finished():

    global checking_video

    checking_video = False

    update_quality_list()

    set_buttons(True)

    set_progress(100)

    title = video_info.get(

        "title",

        "Unknown video"
    )

    duration = video_info.get(
        "duration"
    )

    duration_text = ""

    if duration:

        minutes = int(
            duration // 60
        )

        seconds = int(
            duration % 60
        )

        duration_text = (
            f" • {minutes}:{seconds:02d}"
        )

    set_status(

        f"Ready • {title}{duration_text}"
    )


# ============================================================
# QUALITY DETECTION
# ============================================================

def update_quality_list():

    if not video_info:
        return

    heights = set()

    for fmt in video_info.get(

        "formats",

        []
    ):

        height = fmt.get(
            "height"
        )

        vcodec = fmt.get(
            "vcodec"
        )

        # Only count formats that actually contain video
        if (

            height

            and

            vcodec

            and

            vcodec != "none"
        ):

            heights.add(
                int(height)
            )


    sorted_heights = sorted(

        heights,

        reverse=True
    )


    quality_names = {

        4320: "4320p (8K)",

        2160: "2160p (4K)",

        1440: "1440p",

        1080: "1080p",

        720: "720p",

        480: "480p",

        360: "360p",

        240: "240p",

        144: "144p"
    }


    available = [

        "Best available"
    ]


    for height in sorted_heights:

        if height in quality_names:

            available.append(

                quality_names[height]
            )

        else:

            available.append(

                f"{height}p"
            )


    if not available:

        available = [

            "Best available"
        ]


    quality_combo["values"] = available

    quality_combo.current(0)


# ============================================================
# GET SELECTED HEIGHT
# ============================================================

def get_height():

    quality = quality_combo.get()

    match = re.search(

        r"(\d+)p",

        quality
    )

    if match:

        return int(
            match.group(1)
        )

    return None


# ============================================================
# DOWNLOAD TYPE CHANGED
# ============================================================

def download_type_changed():

    download_type = (
        download_type_var.get()
    )


    # ========================================================
    # VIDEO
    # ========================================================

    if download_type == "Video":

        format_label.config(

            text="Video format:"
        )

        format_combo.config(

            state="readonly"
        )

        format_combo["values"] = [

            "Original",

            "MP4",

            "MKV",

            "WebM"
        ]

        format_combo.current(0)


        quality_label.pack(

            anchor="w"
        )

        quality_combo.pack(

            fill="x",

            pady=(5, 15)
        )


        thumbnail_check.pack(

            anchor="w",

            padx=30,

            pady=(0, 10)
        )


    # ========================================================
    # AUDIO
    # ========================================================

    elif download_type == "Audio":

        format_label.config(

            text="Audio format:"
        )

        format_combo.config(

            state="readonly"
        )

        format_combo["values"] = [

            "Original",

            "MP3",

            "OGG",

            "WAV"
        ]

        format_combo.current(0)


        quality_label.pack(

            anchor="w"
        )

        quality_combo.pack(

            fill="x",

            pady=(5, 15)
        )


        quality_combo["values"] = [

            "Best available"
        ]

        quality_combo.current(0)


        thumbnail_check.pack(

            anchor="w",

            padx=30,

            pady=(0, 10)
        )


    # ========================================================
    # THUMBNAIL
    # ========================================================

    else:

        format_label.config(

            text="Thumbnail format:"
        )

        format_combo.config(

            state="readonly"
        )

        format_combo["values"] = [

            "JPG",

            "PNG",

            "WebP"
        ]

        format_combo.current(0)


        quality_label.pack_forget()

        quality_combo.pack_forget()

        thumbnail_check.pack_forget()


# ============================================================
# FORMAT CHANGED
# ============================================================

def format_changed(event=None):

    download_type = (
        download_type_var.get()
    )

    selected_format = (
        format_combo.get()
    )

    if (

        download_type == "Video"

        and

        selected_format == "Original"
    ):

        set_status(
            "Original format selected"
        )


# ============================================================
# BROWSE DOWNLOAD FOLDER
# ============================================================

def browse_folder():

    global DOWNLOAD_FOLDER

    folder = filedialog.askdirectory(

        title="Choose download folder",

        initialdir=DOWNLOAD_FOLDER
    )

    if folder:

        DOWNLOAD_FOLDER = folder


        folder_entry.config(

            state="normal"
        )

        folder_entry.delete(

            0,

            tk.END
        )

        folder_entry.insert(

            0,

            DOWNLOAD_FOLDER
        )

        folder_entry.config(

            state="readonly"
        )


# ============================================================
# BUILD YT-DLP COMMAND
# ============================================================

def build_command():

    url = url_entry.get().strip()

    download_type = (
        download_type_var.get()
    )

    selected_format = (
        format_combo.get()
    )


    output = os.path.join(

        DOWNLOAD_FOLDER,

        "%(title)s.%(ext)s"
    )


    command = [

        YTDLP,

        "--newline",

        "--progress",

        "--no-warnings",

        # Faster fragmented downloads
        "-N",
        "8",

        # Retry settings
        "--retries",
        "10",

        "--fragment-retries",
        "10",

        # FFmpeg location
        "--ffmpeg-location",
        BASE_DIR,

        # Output filename
        "-o",
        output
    ]


    # ========================================================
    # THUMBNAIL
    # ========================================================

    if download_type == "Thumbnail":

        thumbnail_format = (

            selected_format.lower()
        )


        command += [

            "--skip-download",

            "--write-thumbnail",

            "--convert-thumbnails",

            thumbnail_format
        ]


        return command + [url]


    # ========================================================
    # AUDIO
    # ========================================================

    if download_type == "Audio":


        # ----------------------------------------------------
        # ORIGINAL
        # ----------------------------------------------------

        if selected_format == "Original":

            command += [

                "-f",

                "ba/b"
            ]


        # ----------------------------------------------------
        # MP3
        # ----------------------------------------------------

        elif selected_format == "MP3":

            command += [

                "-x",

                "--audio-format",

                "mp3",

                "--audio-quality",

                "0"
            ]


        # ----------------------------------------------------
        # OGG
        # ----------------------------------------------------

        elif selected_format == "OGG":

            command += [

                "-x",

                "--audio-format",

                "vorbis",

                "--audio-quality",

                "0"
            ]


        # ----------------------------------------------------
        # WAV
        # ----------------------------------------------------

        elif selected_format == "WAV":

            command += [

                "-x",

                "--audio-format",

                "wav"
            ]


        return command + [url]


    # ========================================================
    # VIDEO
    # ========================================================

    height = get_height()


    # ========================================================
    # ORIGINAL VIDEO
    # ========================================================

    if selected_format == "Original":

        if height:

            format_string = (

                f"bv*[height<={height}]+"

                f"ba/"

                f"b[height<={height}]"
            )

        else:

            format_string = (

                "bv*+ba/b"
            )


        command += [

            "-f",

            format_string
        ]


    # ========================================================
    # MP4
    # ========================================================

    elif selected_format == "MP4":

        if height:

            format_string = (

                f"bv*[height<={height}]"
                f"[ext=mp4]+"

                f"ba[ext=m4a]/"

                f"bv*[height<={height}]+ba/"

                f"b[height<={height}]"
            )

        else:

            format_string = (

                "bv*[ext=mp4]+"

                "ba[ext=m4a]/"

                "bv*+ba/b"
            )


        command += [

            "-f",

            format_string,

            "--merge-output-format",

            "mp4"
        ]


    # ========================================================
    # MKV
    # ========================================================

    elif selected_format == "MKV":

        if height:

            format_string = (

                f"bv*[height<={height}]+"

                f"ba/"

                f"b[height<={height}]"
            )

        else:

            format_string = (

                "bv*+ba/b"
            )


        command += [

            "-f",

            format_string,

            "--merge-output-format",

            "mkv"
        ]


    # ========================================================
    # WEBM
    # ========================================================

    elif selected_format == "WebM":

        if height:

            format_string = (

                f"bv*[height<={height}]+"

                f"ba/"

                f"b[height<={height}]"
            )

        else:

            format_string = (

                "bv*+ba/b"
            )


        command += [

            "-f",

            format_string,

            "--merge-output-format",

            "webm"
        ]


    # ========================================================
    # OPTIONAL THUMBNAIL
    # ========================================================

    if thumbnail_var.get():

        command += [

            "--write-thumbnail"
        ]


    return command + [url]


# ============================================================
# START DOWNLOAD
# ============================================================

def start_download():

    if not check_files():
        return


    url = url_entry.get().strip()

    if not url:

        messagebox.showwarning(

            "No URL",

            "Paste a YouTube URL first."
        )

        return


    set_buttons(False)

    set_progress(0)

    set_status(

        "Starting download..."
    )


    threading.Thread(

        target=download_worker,

        daemon=True
    ).start()


# ============================================================
# DOWNLOAD WORKER
# ============================================================

def download_worker():

    command = build_command()


    try:

        process = subprocess.Popen(

            command,

            stdout=subprocess.PIPE,

            stderr=subprocess.STDOUT,

            text=True,

            encoding="utf-8",

            errors="replace",

            # IMPORTANT:
            # Prevent yt-dlp from opening a console window
            creationflags=CREATE_NO_WINDOW
        )


        for line in process.stdout:

            line = line.strip()

            if not line:
                continue


            # =================================================
            # PERCENTAGE
            # =================================================

            percentage_match = re.search(

                r"(\d+(?:\.\d+)?)%",

                line
            )


            percentage = None


            if percentage_match:

                percentage = float(

                    percentage_match.group(1)
                )


                set_progress(

                    percentage
                )


            # =================================================
            # SPEED
            # =================================================

            speed_match = re.search(

                r"at\s+([^\s]+)",

                line
            )


            speed = (

                speed_match.group(1)

                if speed_match

                else None
            )


            # =================================================
            # ETA
            # =================================================

            eta_match = re.search(

                r"ETA\s+([^\s]+)",

                line
            )


            eta = (

                eta_match.group(1)

                if eta_match

                else None
            )


            # =================================================
            # STATUS
            # =================================================

            status = "Downloading..."


            if percentage is not None:

                status += (

                    f" {percentage:.1f}%"
                )


            if speed:

                status += (

                    f" • {speed}"
                )


            if eta:

                status += (

                    f" • ETA {eta}"
                )


            set_status(

                status
            )


        process.wait()


        # =====================================================
        # RESULT
        # =====================================================

        if process.returncode == 0:

            root.after(

                0,

                download_complete
            )

        else:

            root.after(

                0,

                download_failed
            )


    except Exception as e:

        root.after(

            0,

            lambda: download_exception(
                str(e)
            )
        )


# ============================================================
# DOWNLOAD COMPLETE
# ============================================================

def download_complete():

    set_progress(100)

    set_status(

        "Download complete!"
    )

    set_buttons(True)


    messagebox.showinfo(

        "Finished",

        "Download completed successfully."
    )


# ============================================================
# DOWNLOAD FAILED
# ============================================================

def download_failed():

    set_status(

        "Download failed."
    )

    set_buttons(True)


    messagebox.showerror(

        "Download failed",

        "yt-dlp was unable to complete the download."
    )


# ============================================================
# DOWNLOAD EXCEPTION
# ============================================================

def download_exception(error):

    set_status(

        "Error."
    )

    set_buttons(True)


    messagebox.showerror(

        "Error",

        error
    )


# ============================================================
# MAIN WINDOW
# ============================================================

root = tk.Tk()


root.title(

    "YouTube Downloader 1.0"
)


root.geometry(

    "650x520"
)


root.resizable(

    False,

    False
)


# ============================================================
# TITLE
# ============================================================

title_label = ttk.Label(

    root,

    text="YouTube Downloader 1.0",

    font=(

        "Segoe UI",

        18,

        "bold"
    )
)


title_label.pack(

    pady=(20, 15)
)


# ============================================================
# URL
# ============================================================

url_frame = ttk.Frame(

    root
)


url_frame.pack(

    fill="x",

    padx=30
)


ttk.Label(

    url_frame,

    text="Video URL:"
).pack(

    anchor="w"
)


url_entry = ttk.Entry(

    url_frame
)


url_entry.pack(

    fill="x",

    pady=(5, 15)
)


# Check automatically when leaving the URL field
url_entry.bind(

    "<FocusOut>",

    url_changed
)


# Check automatically when pressing Enter
url_entry.bind(

    "<Return>",

    url_changed
)


# ============================================================
# DOWNLOAD TYPE
# ============================================================

type_frame = ttk.LabelFrame(

    root,

    text="What do you want to download?"
)


type_frame.pack(

    fill="x",

    padx=30,

    pady=(0, 15)
)


download_type_var = tk.StringVar(

    value="Video"
)


ttk.Radiobutton(

    type_frame,

    text="Video",

    variable=download_type_var,

    value="Video",

    command=download_type_changed
).pack(

    side="left",

    padx=20,

    pady=10
)


ttk.Radiobutton(

    type_frame,

    text="Audio",

    variable=download_type_var,

    value="Audio",

    command=download_type_changed
).pack(

    side="left",

    padx=20,

    pady=10
)


ttk.Radiobutton(

    type_frame,

    text="Thumbnail",

    variable=download_type_var,

    value="Thumbnail",

    command=download_type_changed
).pack(

    side="left",

    padx=20,

    pady=10
)


# ============================================================
# OPTIONS
# ============================================================

options_frame = ttk.Frame(

    root
)


options_frame.pack(

    fill="x",

    padx=30
)


# ============================================================
# FORMAT
# ============================================================

format_frame = ttk.Frame(

    options_frame
)


format_frame.pack(

    side="left",

    fill="x",

    expand=True,

    padx=(0, 10)
)


format_label = ttk.Label(

    format_frame,

    text="Video format:"
)


format_label.pack(

    anchor="w"
)


format_combo = ttk.Combobox(

    format_frame,

    values=[

        "Original",

        "MP4",

        "MKV",

        "WebM"
    ],

    state="readonly"
)


format_combo.pack(

    fill="x",

    pady=(5, 15)
)


format_combo.current(0)


format_combo.bind(

    "<<ComboboxSelected>>",

    format_changed
)


# ============================================================
# QUALITY
# ============================================================

quality_frame = ttk.Frame(

    options_frame
)


quality_frame.pack(

    side="left",

    fill="x",

    expand=True,

    padx=(10, 0)
)


quality_label = ttk.Label(

    quality_frame,

    text="Quality:"
)


quality_label.pack(

    anchor="w"
)


quality_combo = ttk.Combobox(

    quality_frame,

    values=[

        "Best available"
    ],

    state="readonly"
)


quality_combo.pack(

    fill="x",

    pady=(5, 15)
)


quality_combo.current(0)


# ============================================================
# THUMBNAIL CHECKBOX
# ============================================================

thumbnail_var = tk.BooleanVar(

    value=False
)


thumbnail_check = ttk.Checkbutton(

    root,

    text="Also download thumbnail",

    variable=thumbnail_var
)


thumbnail_check.pack(

    anchor="w",

    padx=30,

    pady=(0, 10)
)


# ============================================================
# SAVE FOLDER
# ============================================================

folder_frame = ttk.Frame(

    root
)


folder_frame.pack(

    fill="x",

    padx=30
)


ttk.Label(

    folder_frame,

    text="Save to:"
).pack(

    anchor="w"
)


folder_row = ttk.Frame(

    folder_frame
)


folder_row.pack(

    fill="x",

    pady=(5, 15)
)


folder_entry = ttk.Entry(

    folder_row,

    state="readonly"
)


folder_entry.pack(

    side="left",

    fill="x",

    expand=True
)


folder_entry.config(

    state="normal"
)


folder_entry.insert(

    0,

    DOWNLOAD_FOLDER
)


folder_entry.config(

    state="readonly"
)


ttk.Button(

    folder_row,

    text="Browse",

    command=browse_folder
).pack(

    side="left",

    padx=(8, 0)
)


# ============================================================
# DOWNLOAD BUTTON
# ============================================================

download_button = ttk.Button(

    root,

    text="DOWNLOAD",

    command=start_download
)


download_button.pack(

    pady=(5, 15),

    ipadx=40,

    ipady=8
)


# ============================================================
# PROGRESS BAR
# ============================================================

progress_bar = ttk.Progressbar(

    root,

    orient="horizontal",

    length=590,

    mode="determinate",

    maximum=100
)


progress_bar.pack(

    pady=(0, 8)
)


# ============================================================
# STATUS
# ============================================================

status_label = ttk.Label(

    root,

    text="Ready"
)


status_label.pack()


# ============================================================
# INITIAL STATE
# ============================================================

download_type_changed()


# ============================================================
# START PROGRAM
# ============================================================

root.mainloop()