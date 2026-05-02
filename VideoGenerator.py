#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GM - Video Generator Tool
-------------------------
Automates the creation of simple videos from audio, a static visual,
and a logo intro using FFmpeg. Supports batch processing with smart
filename matching and flexible auto-detection of visuals.

Author: Gipstamusic
Version: 1.2.0
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkFont
import subprocess
import threading
import queue
import json
import os
import sys
import pathlib
import webbrowser
import re
import time
from datetime import datetime
from PIL import Image, UnidentifiedImageError

# --- Determine Paths ---

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # Fall back to the directory of the script
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def get_executable_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    elif __file__:
        return os.path.dirname(os.path.abspath(__file__))
    else:
        return os.getcwd()

APP_EXECUTABLE_DIR = get_executable_dir()

# --- Constants ---
APP_NAME = "GM - Video Generator Tool"
CONFIG_FILE_NAME = "config.json"
DEFAULT_ENGINE_DIR_NAME = "_engine"
ICON_FILE_NAME = "local.ico"

# Config goes next to the executable, assets go through resource_path
CONFIG_FILE_PATH = os.path.join(APP_EXECUTABLE_DIR, CONFIG_FILE_NAME)
DEFAULT_ENGINE_DIR = resource_path(DEFAULT_ENGINE_DIR_NAME)
ICON_FILE = resource_path(ICON_FILE_NAME)

IS_WINDOWS = sys.platform.startswith('win')
DEFAULT_FFMPEG_NAME = "ffmpeg.exe" if IS_WINDOWS else "ffmpeg"
DEFAULT_FFPROBE_NAME = "ffprobe.exe" if IS_WINDOWS else "ffprobe"

# --- Processing Configurations ---
HD_WIDTH = 1920
HD_HEIGHT = 1080
LOGO_MAX_DURATION = 60.0
LOGO_DURATION_INCREMENT = 0.5
BATCH_LIMIT = 20
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')
AUDIO_EXTENSIONS = ('.mp3', '.wav')
SMART_MATCH_DELIMITERS = [' - ', ' _ ', ' | ']
FRAME_RATES = ["30", "24", "25", "50", "60"]
DEFAULT_FPS = FRAME_RATES[0]

# --- Appearance & Theme ---
BG_COLOR = '#1E1E1E'
FG_COLOR = '#F5F5F5'
FG_DISABLED_COLOR = '#777777'
BG_WIDGET_COLOR = '#151515'
LOG_FG_COLOR = '#00FF99'
BTN_BG_COLOR = '#2D2D30'
BTN_FG_COLOR = '#F5F5F5'
ACCENT_COLOR = '#00FF99'
LINK_COLOR = '#6495ED'
BTN_ACTIVE_BG = '#3B3B3B'
LIST_SELECT_BG = '#3B3B3B'
ERROR_FG_COLOR = '#FF6347'
WARNING_FG_COLOR = '#FFA500'
TIMESTAMP_FG_COLOR = '#AAAAAA'

# --- Font ---
MAIN_FONT = ("Consolas", 10)
BOLD_FONT = ("Consolas", 10, "bold")
LOG_FONT = ("Consolas", 9)
LINK_FONT = ("Consolas", 8, "underline")

# --- Creator Info ---
HYPERLINK_URL = "https://lnk.bio/gipstamusic"
CREATOR_TEXT = "Made by Gipstamusic ♥"

# --- Custom Exceptions ---
class FFmpegError(Exception): pass
class FFprobeError(Exception): pass

# --- Main Application Class ---
class VideoGeneratorApp:

    def __init__(self, root_window):
        self.root = root_window
        self.root.title(f"{APP_NAME}")
        self.root.configure(bg=BG_COLOR)
        self.desired_min_width = 670
        self.desired_min_height = 680
        self.root.minsize(self.desired_min_width, self.desired_min_height)
        self.root.resizable(True, True)

        self._set_icon()
        self._apply_styles()

        # --- Tkinter Variables ---
        self.ffmpeg_path = tk.StringVar()
        self.ffprobe_path = tk.StringVar()
        self.logo_path = tk.StringVar()
        self.output_location_mode = tk.StringVar(value="mp3_dir")
        self.custom_output_path = tk.StringVar()
        self.logo_duration = tk.DoubleVar(value=1.0)
        self.frame_rate = tk.StringVar(value=DEFAULT_FPS)

        # --- Batch Processing State ---
        self.batch_audio_files = []
        self.batch_pairs = {}
        self.process_queue = queue.Queue()
        self.is_processing = False
        self.worker_thread = None
        self.dots_timer_id = None
        self.base_status_text = "Ready"
        self.dot_count = 0

        # --- Initialization ---
        self.settings = self._load_settings()
        self._apply_loaded_settings()

        if not self._check_ffmpeg_paths():
            messagebox.showerror("Critical Error", "FFmpeg/FFprobe could not be configured. The application cannot continue.", parent=self.root)
            self.root.quit()
            return

        self._create_widgets()
        self._layout_widgets()
        self._adjust_initial_size_for_screen()
        self._update_status_label(self.base_status_text)
        self._update_batch_counter_label()

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.after(100, self._check_queue)

    def _adjust_initial_size_for_screen(self):
        try:
            self.root.update_idletasks()
            screen_height = self.root.winfo_screenheight()
            screen_margin = 80
            available_height = screen_height - screen_margin
            desired_height = self.desired_min_height

            if desired_height > available_height:
                min_practical_height = 500
                new_height = max(available_height, min_practical_height)
                new_width = self.desired_min_width
                self.root.geometry(f"{new_width}x{new_height}")
                self.root.minsize(new_width, new_height)
        except Exception:
            pass

    def _set_icon(self):
        try:
            if os.path.exists(ICON_FILE):
                self.root.iconbitmap(ICON_FILE)
        except Exception:
            pass

    def _apply_styles(self):
        style = ttk.Style(self.root)
        self.root.option_add("*Font", MAIN_FONT)
        style.theme_use('clam')

        style.configure('.', background=BG_COLOR, foreground=FG_COLOR, borderwidth=0, focuscolor=BG_COLOR, font=MAIN_FONT)
        style.configure('TFrame', background=BG_COLOR)
        style.configure('TLabel', background=BG_COLOR, foreground=FG_COLOR, padding=5, font=MAIN_FONT)
        style.configure('TRadiobutton', background=BG_COLOR, foreground=FG_COLOR, font=MAIN_FONT, indicatorrelief='flat', padding=(5, 2))
        style.map('TRadiobutton',
                  background=[('active', BG_COLOR)],
                  indicatorcolor=[('selected', ACCENT_COLOR), ('!selected', FG_COLOR)],
                  foreground=[('disabled', FG_DISABLED_COLOR)])

        style.configure('TButton', background=BTN_BG_COLOR, foreground=BTN_FG_COLOR, borderwidth=0, relief='flat', padding=(10, 5), font=BOLD_FONT)
        style.map('TButton',
                  background=[('pressed', BTN_ACTIVE_BG), ('active', BTN_ACTIVE_BG), ('disabled', BG_WIDGET_COLOR)],
                  foreground=[('disabled', FG_DISABLED_COLOR)],
                  relief=[('pressed', 'flat'), ('!pressed', 'flat')])

        style.configure('Vertical.TScrollbar', background=BTN_BG_COLOR, troughcolor=BG_WIDGET_COLOR, borderwidth=0, arrowcolor=FG_COLOR, relief='flat', arrowsize=14)
        style.map('Vertical.TScrollbar', background=[('active', BTN_ACTIVE_BG)])
        style.configure('Horizontal.TScrollbar', background=BTN_BG_COLOR, troughcolor=BG_WIDGET_COLOR, borderwidth=0, arrowcolor=FG_COLOR, relief='flat', arrowsize=14)
        style.map('Horizontal.TScrollbar', background=[('active', BTN_ACTIVE_BG)])

    def _create_widgets(self):
        # Titles
        self.file_title_label = ttk.Label(self.root, text="Input Files", font=BOLD_FONT)
        self.settings_title_label = ttk.Label(self.root, text="Settings (Apply to All)", font=BOLD_FONT)
        self.output_title_label = ttk.Label(self.root, text="Output Location (For All)", font=BOLD_FONT)
        self.log_title_label = ttk.Label(self.root, text="Progress Log", font=BOLD_FONT)

        # Frames
        self.file_frame = ttk.Frame(self.root, style='TFrame', padding=5)
        self.batch_frame = ttk.Frame(self.root, style='TFrame', padding=5)
        self.settings_frame = ttk.Frame(self.root, style='TFrame', padding=5)
        self.output_frame = ttk.Frame(self.root, style='TFrame', padding=5)
        self.log_frame = ttk.Frame(self.root, style='TFrame')
        self.action_frame = ttk.Frame(self.root, style='TFrame')
        self.status_frame = ttk.Frame(self.root, style='TFrame')

        # File Inputs
        ttk.Label(self.file_frame, text="Audio Files (MP3/WAV):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.btn_browse_audio = ttk.Button(self.file_frame, text=f"Add Audio Files... (Max {BATCH_LIMIT})", command=self._browse_audio_files)
        self.btn_browse_audio.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="w")

        ttk.Label(self.file_frame, text="Logo Image (Optional):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.entry_logo = tk.Entry(self.file_frame, textvariable=self.logo_path, width=50,
                                   bg=BG_COLOR, fg=FG_COLOR, font=MAIN_FONT, borderwidth=0, relief='flat', 
                                   highlightthickness=0, insertbackground=FG_COLOR, 
                                   disabledbackground=BG_COLOR, disabledforeground=FG_DISABLED_COLOR)
        self.entry_logo.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.btn_browse_logo = ttk.Button(self.file_frame, text="Browse...", command=self._browse_logo)
        self.btn_browse_logo.grid(row=1, column=2, padx=5, pady=5)
        self.file_frame.columnconfigure(1, weight=1)

        # Batch List
        self.batch_listbox = tk.Listbox(self.batch_frame, height=8, width=70, selectmode=tk.SINGLE,
                                        bg=BG_WIDGET_COLOR, fg=FG_COLOR, font=MAIN_FONT, borderwidth=0, 
                                        highlightthickness=0, relief='flat', selectbackground=LIST_SELECT_BG, 
                                        selectforeground=FG_COLOR, activestyle='none')
        self.batch_scrollbar = ttk.Scrollbar(self.batch_frame, orient="vertical", command=self.batch_listbox.yview, style='Vertical.TScrollbar')
        self.batch_listbox.config(yscrollcommand=self.batch_scrollbar.set)
        self.btn_clear_batch = ttk.Button(self.batch_frame, text="Clear Batch List", command=self._clear_batch)

        self.batch_frame.columnconfigure(0, weight=1)
        self.batch_frame.rowconfigure(0, weight=1)
        self.batch_listbox.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.batch_scrollbar.grid(row=0, column=1, padx=(0,5), pady=5, sticky="ns")
        self.btn_clear_batch.grid(row=1, column=0, columnspan=2, pady=(5, 0))

        # Settings
        ttk.Label(self.settings_frame, text="Logo Duration (s):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.spin_logo_duration = tk.Spinbox(self.settings_frame, from_=0.5, to=LOGO_MAX_DURATION, increment=LOGO_DURATION_INCREMENT,
                                             textvariable=self.logo_duration, width=4, font=MAIN_FONT,
                                             bg=BG_COLOR, fg=FG_COLOR, buttonbackground=BTN_BG_COLOR, buttoncursor="hand2",
                                             disabledbackground=BG_COLOR, disabledforeground=FG_DISABLED_COLOR,
                                             borderwidth=0, relief='flat', highlightthickness=0, command=self._save_settings)
        self.spin_logo_duration.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(self.settings_frame, text="Frame Rate (fps):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.spin_frame_rate = tk.Spinbox(self.settings_frame, values=FRAME_RATES, textvariable=self.frame_rate,
                                          width=4, wrap=True, font=MAIN_FONT, bg=BG_COLOR, fg=FG_COLOR, 
                                          buttonbackground=BTN_BG_COLOR, buttoncursor="hand2",
                                          disabledbackground=BG_COLOR, disabledforeground=FG_DISABLED_COLOR,
                                          borderwidth=0, relief='flat', highlightthickness=0, command=self._save_settings)
        self.spin_frame_rate.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # Output Location
        self.rb_output_mp3 = ttk.Radiobutton(self.output_frame, text="Save in each Audio file's location",
                                             variable=self.output_location_mode, value="mp3_dir",
                                             command=self._update_output_location_widgets)
        self.rb_output_custom = ttk.Radiobutton(self.output_frame, text="Save all in custom location:",
                                                variable=self.output_location_mode, value="custom",
                                                command=self._update_output_location_widgets)
        self.entry_output_custom = tk.Entry(self.output_frame, textvariable=self.custom_output_path, width=40, state="disabled",
                                            bg=BG_COLOR, fg=FG_COLOR, font=MAIN_FONT, disabledbackground=BG_COLOR, 
                                            disabledforeground=FG_DISABLED_COLOR, borderwidth=0, relief='flat', 
                                            highlightthickness=0, insertbackground=FG_COLOR)
        self.btn_browse_output = ttk.Button(self.output_frame, text="Browse...", command=self._browse_output, state="disabled")

        self.output_frame.columnconfigure(1, weight=1)
        self.rb_output_mp3.grid(row=0, column=0, columnspan=3, padx=5, pady=2, sticky="w")
        self.rb_output_custom.grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.entry_output_custom.grid(row=1, column=1, padx=5, pady=2, sticky="ew")
        self.btn_browse_output.grid(row=1, column=2, padx=5, pady=2)

        # Action
        self.btn_generate = ttk.Button(self.action_frame, text="Generate Batch Video(s)", command=self._start_batch_generation_thread)
        self.btn_generate.pack()

        # Log
        self.log_text = tk.Text(self.log_frame, height=16, width=85, wrap="word", state="disabled",
                                bg=BG_WIDGET_COLOR, fg=LOG_FG_COLOR, font=LOG_FONT, borderwidth=0, 
                                highlightthickness=0, relief='flat', padx=5, pady=5, insertbackground=LOG_FG_COLOR)
        self.log_scrollbar = ttk.Scrollbar(self.log_frame, orient="vertical", command=self.log_text.yview, style='Vertical.TScrollbar')
        self.log_text.config(yscrollcommand=self.log_scrollbar.set)

        self.log_text.tag_configure("timestamp", foreground=TIMESTAMP_FG_COLOR)
        self.log_text.tag_configure("warning", foreground=WARNING_FG_COLOR)
        self.log_text.tag_configure("error", foreground=ERROR_FG_COLOR)
        
        try:
            log_tk_font = tkFont.Font(family=LOG_FONT[0], size=LOG_FONT[1])
            prefix_width = log_tk_font.measure("[HH:MM:SS] ")
            self.log_text.tag_configure("indent", lmargin1=prefix_width + 5, lmargin2=prefix_width + 5)
        except tk.TclError:
            self.log_text.tag_configure("indent", lmargin1=50, lmargin2=50)

        self.log_frame.rowconfigure(0, weight=1)
        self.log_frame.columnconfigure(0, weight=1)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_scrollbar.grid(row=0, column=1, sticky="ns")

        # Status Bar (Added width=60 to prevent jitter)
        self.status_label = ttk.Label(self.status_frame, text="Ready", anchor="w", width=60)
        self.link_label = tk.Label(self.status_frame, text=CREATOR_TEXT, foreground=LINK_COLOR,
                                   background=BG_COLOR, cursor="hand2", font=LINK_FONT)
        self.link_label.bind("<Button-1>", self._open_link)

        self.status_frame.columnconfigure(0, weight=1)
        self.status_frame.columnconfigure(1, weight=0)
        self.status_label.grid(row=0, column=0, padx=5, sticky="ew")
        self.link_label.grid(row=0, column=1, padx=(15, 5), sticky="e")

    def _layout_widgets(self):
        self.root.columnconfigure(0, weight=1)
        LOG_FRAME_ROW = 10
        self.root.rowconfigure(LOG_FRAME_ROW, weight=1)

        PAD_Y_SECTION = (10, 0)
        PAD_Y_FRAME = 5

        self.file_title_label.grid(row=0, column=0, padx=10, pady=(10,0), sticky="w")
        self.file_frame.grid(row=1, column=0, padx=10, pady=PAD_Y_FRAME, sticky="ew")

        batch_header_frame = ttk.Frame(self.root, style='TFrame')
        batch_header_frame.grid(row=2, column=0, padx=10, pady=PAD_Y_SECTION, sticky="ew")
        self.batch_title_label = ttk.Label(batch_header_frame, text="Batch Files Status", font=BOLD_FONT)
        self.batch_count_label = ttk.Label(batch_header_frame, text="(0 files)", font=MAIN_FONT)
        self.batch_title_label.grid(row=0, column=0, sticky="w")
        self.batch_count_label.grid(row=0, column=1, sticky="w", padx=5)

        self.batch_frame.grid(row=3, column=0, padx=10, pady=PAD_Y_FRAME, sticky="ew")

        self.settings_title_label.grid(row=4, column=0, padx=10, pady=PAD_Y_SECTION, sticky="w")
        self.settings_frame.grid(row=5, column=0, padx=10, pady=PAD_Y_FRAME, sticky="ew")

        self.output_title_label.grid(row=6, column=0, padx=10, pady=PAD_Y_SECTION, sticky="w")
        self.output_frame.grid(row=7, column=0, padx=10, pady=PAD_Y_FRAME, sticky="ew")

        self.action_frame.grid(row=8, column=0, padx=10, pady=10)

        self.log_title_label.grid(row=9, column=0, padx=10, pady=PAD_Y_SECTION, sticky="w")
        self.log_frame.grid(row=LOG_FRAME_ROW, column=0, padx=10, pady=PAD_Y_FRAME, sticky="nsew")

        self.status_frame.grid(row=11, column=0, padx=10, pady=(5, 10), sticky="ew")
        self._update_output_location_widgets()

    def _load_settings(self):
        defaults = {
            "ffmpeg_path": os.path.join(DEFAULT_ENGINE_DIR, DEFAULT_FFMPEG_NAME),
            "ffprobe_path": os.path.join(DEFAULT_ENGINE_DIR, DEFAULT_FFPROBE_NAME),
            "logo_path": "",
            "output_location_mode": "mp3_dir",
            "custom_output_path": "",
            "logo_duration": 1.0,
            "frame_rate": DEFAULT_FPS
        }
        try:
            if os.path.exists(CONFIG_FILE_PATH):
                with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    defaults.update({k: loaded[k] for k in defaults if k in loaded})
            return defaults
        except Exception:
            return defaults

    def _apply_loaded_settings(self):
        self.ffmpeg_path.set(self.settings.get("ffmpeg_path", ""))
        self.ffprobe_path.set(self.settings.get("ffprobe_path", ""))
        self.logo_path.set(self.settings.get("logo_path", ""))
        self.output_location_mode.set(self.settings.get("output_location_mode", "mp3_dir"))
        self.custom_output_path.set(self.settings.get("custom_output_path", ""))

        try:
            self.logo_duration.set(float(self.settings.get("logo_duration", 1.0)))
        except ValueError:
            self.logo_duration.set(1.0)

        loaded_fps = self.settings.get("frame_rate", DEFAULT_FPS)
        self.frame_rate.set(loaded_fps if loaded_fps in FRAME_RATES else DEFAULT_FPS)

    def _save_settings(self):
        if not hasattr(self, 'logo_path'):
            return
        try:
            current_settings = {
                "ffmpeg_path": self.ffmpeg_path.get(),
                "ffprobe_path": self.ffprobe_path.get(),
                "logo_path": self.logo_path.get(),
                "output_location_mode": self.output_location_mode.get(),
                "custom_output_path": self.custom_output_path.get(),
                "logo_duration": self.logo_duration.get(),
                "frame_rate": self.frame_rate.get()
            }
            with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(current_settings, f, indent=4)
        except Exception:
             pass

    def _update_output_location_widgets(self):
        if not hasattr(self, 'entry_output_custom'):
            return
        mode = self.output_location_mode.get()
        state = tk.NORMAL if mode == "custom" else tk.DISABLED
        try:
            self.entry_output_custom.config(state=state)
            self.btn_browse_output.config(state=state)
            self._save_settings()
        except Exception:
            pass

    def _prompt_for_executable(self, tool_name, default_exe_name):
        messagebox.showinfo("Executable Not Found", f"{tool_name} could not be found automatically.\n\nPlease locate the {tool_name} executable file (e.g., {default_exe_name}).", parent=self.root)
        file_path = filedialog.askopenfilename(
            title=f"Locate {tool_name} Executable",
            filetypes=[(f"{tool_name} Executable", default_exe_name), ("All Files", "*.*")],
            initialfile=default_exe_name,
            parent=self.root
        )
        if file_path and self._is_executable(file_path):
            return file_path
        elif file_path:
            messagebox.showwarning("Invalid File", f"The selected file is not a valid executable or could not be accessed:\n{file_path}", parent=self.root)
            return None
        return None

    def _check_ffmpeg_paths(self):
        ffmpeg_exe = self.ffmpeg_path.get()
        ffprobe_exe = self.ffprobe_path.get()
        engine_dir_path = DEFAULT_ENGINE_DIR
        paths_ok = True
        found_paths = {}

        if not self._is_executable(ffmpeg_exe):
            potential_ffmpeg = os.path.join(engine_dir_path, os.path.basename(DEFAULT_FFMPEG_NAME))
            if self._is_executable(potential_ffmpeg):
                found_paths["ffmpeg"] = potential_ffmpeg
                self._queue_log(f"[INFO] Found FFmpeg in default location: {potential_ffmpeg}")
            else:
                self._queue_log(f"[INFO] FFmpeg not found at '{ffmpeg_exe}' or '{potential_ffmpeg}', prompting user...")
                new_path = self._prompt_for_executable("FFmpeg", DEFAULT_FFMPEG_NAME)
                if new_path: found_paths["ffmpeg"] = new_path
                else: paths_ok = False

        if paths_ok and not self._is_executable(ffprobe_exe):
            current_ffmpeg_path = found_paths.get("ffmpeg", ffmpeg_exe)
            potential_ffprobe = None
            if self._is_executable(current_ffmpeg_path):
                potential_ffprobe = os.path.join(os.path.dirname(current_ffmpeg_path), DEFAULT_FFPROBE_NAME)

            if potential_ffprobe and self._is_executable(potential_ffprobe):
                 found_paths["ffprobe"] = potential_ffprobe
                 self._queue_log(f"[INFO] Found FFprobe relative to FFmpeg: {potential_ffprobe}")
            else:
                 potential_ffprobe_engine = os.path.join(engine_dir_path, os.path.basename(DEFAULT_FFPROBE_NAME))
                 if self._is_executable(potential_ffprobe_engine):
                     found_paths["ffprobe"] = potential_ffprobe_engine
                     self._queue_log(f"[INFO] Found FFprobe in default location: {potential_ffprobe_engine}")
                 else:
                    self._queue_log(f"[INFO] FFprobe not found at '{ffprobe_exe}', prompting user...")
                    new_path = self._prompt_for_executable("FFprobe", DEFAULT_FFPROBE_NAME)
                    if new_path: found_paths["ffprobe"] = new_path
                    else: paths_ok = False

        if found_paths:
            if "ffmpeg" in found_paths: self.ffmpeg_path.set(found_paths["ffmpeg"])
            if "ffprobe" in found_paths: self.ffprobe_path.set(found_paths["ffprobe"])
            self._save_settings()

        final_ffmpeg = self.ffmpeg_path.get()
        final_ffprobe = self.ffprobe_path.get()

        if not self._is_executable(final_ffmpeg) or not self._is_executable(final_ffprobe):
            return False

        if not self.is_processing:
            self._queue_log(f"[INFO] Using FFmpeg: {final_ffmpeg}")
            self._queue_log(f"[INFO] Using FFprobe: {final_ffprobe}")
        return True

    def _is_executable(self, path_str):
        return path_str and os.path.exists(path_str) and os.path.isfile(path_str)

    def _browse_audio_files(self):
        audio_patterns = ' '.join([f"*{ext}" for ext in AUDIO_EXTENSIONS])
        paths = filedialog.askopenfilenames(
            title=f"Select/Add Audio Files (Max {BATCH_LIMIT} Total)",
            filetypes=[("Audio Files", audio_patterns), ("All Files", "*.*")],
            parent=self.root
        )

        if paths:
            current_count = len(self.batch_audio_files)
            new_paths_obj = [pathlib.Path(p) for p in paths]
            added_count = 0
            skipped_duplicates = 0
            limit_reached = False

            for p_obj in new_paths_obj:
                 if p_obj not in self.batch_audio_files:
                      if current_count + added_count < BATCH_LIMIT:
                          self.batch_audio_files.append(p_obj)
                          added_count += 1
                      else:
                          limit_reached = True
                          break
                 else:
                      skipped_duplicates += 1

            if added_count > 0:
                self._queue_log(f"[INFO] Added {added_count} new audio file(s) to the batch.")
                if skipped_duplicates > 0:
                    self._queue_log(f"[INFO] Skipped {skipped_duplicates} duplicate file(s).", indent=1)
                if limit_reached:
                    messagebox.showwarning("Batch Limit Reached", f"Reached batch limit of {BATCH_LIMIT} files.\nCould not add all selected files.", parent=self.root)
                self._find_and_display_pairs()
            elif limit_reached:
                messagebox.showwarning("Batch Limit Reached", f"Batch limit of {BATCH_LIMIT} files has already been reached.", parent=self.root)
            
            self._update_batch_counter_label()

    def _browse_logo(self):
        image_patterns = ' '.join([f"*{ext}" for ext in IMAGE_EXTENSIONS])
        path = filedialog.askopenfilename(
            title="Select Logo Image",
            filetypes=[("Image Files", image_patterns), ("All Files", "*.*")],
            parent=self.root
        )
        if path:
            logo_path_obj = pathlib.Path(path)
            if self._validate_image_hd(logo_path_obj, "Logo"):
                self.logo_path.set(str(logo_path_obj))
                self._save_settings()

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select Custom Output Folder", parent=self.root)
        if path:
            self.custom_output_path.set(path)
            self._save_settings()

    def _clear_batch(self):
        self.batch_audio_files = []
        self.batch_pairs = {}
        self.batch_listbox.delete(0, tk.END)
        self._queue_log("[INFO] Batch list cleared.")
        self._update_batch_counter_label()

    def _open_link(self, event=None):
        try:
            webbrowser.open_new(HYPERLINK_URL)
        except Exception:
            pass

    def _find_matching_visual_by_name(self, audio_path: pathlib.Path) -> pathlib.Path | None:
        if not isinstance(audio_path, pathlib.Path): audio_path = pathlib.Path(audio_path)
        audio_dir = audio_path.parent
        audio_basename = audio_path.stem

        def find_case_insensitive(directory: pathlib.Path, target_name: str) -> pathlib.Path | None:
            try:
                if not directory.is_dir(): return None
                for item in os.listdir(directory):
                    if item.lower() == target_name.lower():
                        found_path = directory / item
                        if found_path.is_file(): return found_path
            except OSError: pass
            return None

        for ext in IMAGE_EXTENSIONS:
            visual_path = find_case_insensitive(audio_dir, f"{audio_basename}{ext}")
            if visual_path: return visual_path

        extracted_title = audio_basename
        for delimiter in SMART_MATCH_DELIMITERS:
            if delimiter in audio_basename:
                extracted_title = audio_basename.split(delimiter, 1)[0].strip()
                break

        if extracted_title != audio_basename:
            for ext in IMAGE_EXTENSIONS:
                visual_path = find_case_insensitive(audio_dir, f"{extracted_title}{ext}")
                if visual_path: return visual_path

        return None

    def _find_visual_for_single_audio(self, audio_path: pathlib.Path) -> pathlib.Path | None:
        if not isinstance(audio_path, pathlib.Path): audio_path = pathlib.Path(audio_path)
        audio_dir = audio_path.parent
        self._queue_log(f"   Attempting single-file auto-detect in: {audio_dir}", indent=1)
        found_hd_images = []

        try:
            if not audio_dir.is_dir(): return None
            for item_name in os.listdir(audio_dir):
                if item_name.lower().endswith(IMAGE_EXTENSIONS):
                    item_path = audio_dir / item_name
                    if item_path.is_file() and self._validate_image_hd(item_path, "Visual", silent=True):
                        found_hd_images.append(item_path)
        except OSError:
            return None

        if len(found_hd_images) == 1:
            self._queue_log(f"   SUCCESS: Found exactly one HD image via auto-detect: {found_hd_images[0].name}", indent=1)
            return found_hd_images[0]
        elif len(found_hd_images) > 1:
            self._queue_log(f"[WARNING] Found multiple HD images. Cannot auto-select.", level="warning", indent=1)
        return None

    def _find_and_display_pairs(self):
        self.batch_pairs = {}
        self.batch_listbox.delete(0, tk.END)

        if not self.batch_audio_files:
            self._update_batch_counter_label()
            return

        num_files_selected = len(self.batch_audio_files)
        is_single_mode = (num_files_selected == 1)
        allow_auto_detect_fallback = True
        is_batch_mode = not is_single_mode
        all_files_same_dir = False

        if is_batch_mode:
            try:
                first_parent_dir = self.batch_audio_files[0].parent
                all_files_same_dir = all(f.parent == first_parent_dir for f in self.batch_audio_files)
            except IndexError:
                 pass

            if all_files_same_dir:
                allow_auto_detect_fallback = False
                self._queue_log(f"[INFO] Batch mode. Using Name Matching ONLY.")
            else:
                self._queue_log(f"[INFO] Batch mode (mixed dirs). Using Name Match > Auto-Detect HD.")
        elif is_single_mode:
             self._queue_log("[INFO] Single file mode. Using Name Match > Auto-Detect HD.")

        found_count = 0
        for i, audio_path in enumerate(self.batch_audio_files):
            audio_path_str = str(audio_path)
            display_name = audio_path.name
            visual_path = None
            match_method = ""

            visual_path_name = self._find_matching_visual_by_name(audio_path)
            if visual_path_name:
                visual_path = visual_path_name
                match_method = "(Matched by Name)"
            elif allow_auto_detect_fallback:
                visual_path_single = self._find_visual_for_single_audio(audio_path)
                if visual_path_single:
                    visual_path = visual_path_single
                    match_method = "(Auto-Detected HD)"

            self.batch_pairs[audio_path_str] = str(visual_path) if visual_path else None

            if visual_path:
                self.batch_listbox.insert(tk.END, f"{display_name} -> Found: {visual_path.name} {match_method}")
                self.batch_listbox.itemconfig(i, {'fg': FG_COLOR})
                found_count += 1
            else:
                self.batch_listbox.insert(tk.END, f"{display_name} -> Visual NOT FOUND")
                self.batch_listbox.itemconfig(i, {'fg': ERROR_FG_COLOR})

        self._update_batch_counter_label()

    def _validate_image_hd(self, image_path_obj: pathlib.Path | str, image_type: str, silent: bool = False) -> bool:
        if not isinstance(image_path_obj, pathlib.Path):
             try: image_path_obj = pathlib.Path(image_path_obj)
             except TypeError: return False

        if not image_path_obj.is_file():
             if not silent: messagebox.showerror("Image Error", f"The specified {image_type} image does not exist.", parent=self.root)
             return False

        try:
            with Image.open(image_path_obj) as img:
                width, height = img.size
                if width >= HD_WIDTH and height >= HD_HEIGHT:
                    return True
                else:
                    if not silent: messagebox.showerror("Image Resolution Error", f"The {image_type} image is not HD ({HD_WIDTH}x{HD_HEIGHT} or larger).", parent=self.root)
                    return False
        except UnidentifiedImageError:
             if not silent: messagebox.showerror("Image Error", f"Could not open the {image_type} image.", parent=self.root)
             return False
        except Exception:
            return False

    def _start_batch_generation_thread(self):
        if self.is_processing: return
        self.is_processing = True
        self._set_ui_state(tk.DISABLED)

        def cleanup_and_return():
            self._set_ui_state(tk.NORMAL)
            self.is_processing = False
            return

        if not self._check_ffmpeg_paths(): return cleanup_and_return()

        try:
            logo_path_str = self.logo_path.get().strip()
            logo_path_obj = None
            # If the user supplied a string in the text box, validate it.
            if logo_path_str:
                logo_path_obj = pathlib.Path(logo_path_str)
                if not logo_path_obj.is_file() or not self._validate_image_hd(logo_path_obj, "Logo"):
                     messagebox.showerror("Input Error", "Please select a valid HD Logo Image.", parent=self.root)
                     return cleanup_and_return()
        except Exception: return cleanup_and_return()

        if self.output_location_mode.get() == "custom":
            try:
                custom_out_dir = pathlib.Path(self.custom_output_path.get())
                if not custom_out_dir.is_dir():
                     messagebox.showerror("Output Error", "The specified custom output directory is invalid.", parent=self.root)
                     return cleanup_and_return()
            except Exception: return cleanup_and_return()

        valid_pairs = {
            audio_p_str: pathlib.Path(visual_p_str)
            for audio_p_str, visual_p_str in self.batch_pairs.items() if visual_p_str
        }
        if not valid_pairs:
            messagebox.showerror("Input Error", "No audio/visual pairs found to process.", parent=self.root)
            return cleanup_and_return()

        self._queue_log("[INFO] Validating visual image dimensions for the batch...")
        hd_validated_pairs = {}
        for audio_p_str, visual_p_obj in valid_pairs.items():
            if self._validate_image_hd(visual_p_obj, "Visual", silent=True):
                hd_validated_pairs[audio_p_str] = visual_p_obj

        if len(hd_validated_pairs) == 0:
            messagebox.showerror("Input Error", "No valid pairs with HD visual images found.", parent=self.root)
            return cleanup_and_return()

        self._clear_log()
        self.update_status(f"Starting batch (0/{len(hd_validated_pairs)})...")
        
        # Log out the exact settings being used before starting
        self._queue_log(f"[INFO] Starting batch processing for {len(hd_validated_pairs)} valid pair(s)...")
        self._queue_log(f"[INFO] Logo: {logo_path_obj.name if logo_path_obj else 'None (Skipping Intro)'}", indent=1)
        self._queue_log(f"[INFO] Logo Duration: {self.logo_duration.get()}s", indent=1)
        self._queue_log(f"[INFO] Frame Rate: {self.frame_rate.get()} fps", indent=1)
        out_mode_desc = 'Audio File Directory' if self.output_location_mode.get() == 'mp3_dir' else 'Custom Directory'
        self._queue_log(f"[INFO] Output Mode: {out_mode_desc}", indent=1)
        self._queue_log("-" * 40)
        
        self.worker_thread = threading.Thread(
            target=self._run_batch_generation,
            args=(hd_validated_pairs, logo_path_obj),
            daemon=True
        )
        self.worker_thread.start()

    def _run_batch_generation(self, pairs_to_process: dict, logo_path_obj: pathlib.Path):
        success_count = 0
        fail_count = 0
        total_files = len(pairs_to_process)

        ffmpeg_exe = self.ffmpeg_path.get()
        ffprobe_exe = self.ffprobe_path.get()
        logo_file = str(logo_path_obj) if logo_path_obj else ""
        intro_duration = self.logo_duration.get()
        fps = self.frame_rate.get()
        out_mode = self.output_location_mode.get()
        custom_out_dir_base = None

        if out_mode == 'custom':
            custom_out_dir_base = pathlib.Path(self.custom_output_path.get())

        for i, (audio_file_str, visual_file_obj) in enumerate(pairs_to_process.items()):
            current_file_num = i + 1
            try:
                audio_file_obj = pathlib.Path(audio_file_str)
                visual_file = str(visual_file_obj)
                base_name = audio_file_obj.stem
            except Exception:
                fail_count += 1
                continue

            self.update_status(f"Processing {current_file_num}/{total_files}: {base_name}...")
            self._queue_log(f"Processing file {current_file_num}/{total_files}: {audio_file_obj.name}")
            self.process_queue.put(("start_dots", None))
            temp_dir = None

            try:
                output_dir = custom_out_dir_base if out_mode == "custom" else audio_file_obj.parent
                output_path = output_dir / f"{base_name}.mp4"
                output_dir.mkdir(parents=True, exist_ok=True)

                timestamp_str = time.strftime("%Y%m%d%H%M%S")
                safe_base_name = re.sub(r'[^\w\-]+', '_', base_name)[:50]
                temp_dir_name = f"_temp_{safe_base_name}_{timestamp_str}"
                temp_dir = output_dir / temp_dir_name
                temp_dir.mkdir(parents=True, exist_ok=True)

                self.__run_single_video_generation(
                    audio_file_str, visual_file, logo_file, output_path, temp_dir,
                    intro_duration, fps, ffmpeg_exe, ffprobe_exe
                )
                success_count += 1
                self._queue_log(f"Finished file {current_file_num}/{total_files}: {output_path.name}")
                self._queue_log(f"Saved to: {output_path}", indent=1)

            except Exception as e:
                self._queue_log(f"Failed file {current_file_num}/{total_files}: {audio_file_obj.name}", level="error")
                self._queue_log(f"Reason: {e}", indent=1, level="error")
                fail_count += 1

            finally:
                self.process_queue.put(("stop_dots", None))
                if temp_dir and temp_dir.exists():
                    try:
                        for item in temp_dir.iterdir():
                             try: item.unlink()
                             except FileNotFoundError: pass
                        temp_dir.rmdir()
                    except OSError: pass
                
                if current_file_num < total_files:
                    self._queue_log("-" * 40)

        summary = {"success": success_count, "fail": fail_count, "total": total_files}
        self.process_queue.put(("finish", summary))

    def __run_single_video_generation(self, audio_file: str, visual_file: str, logo_file: str,
                                      output_path: pathlib.Path, temp_dir: pathlib.Path,
                                      intro_duration: float, fps: str,
                                      ffmpeg_exe: str, ffprobe_exe: str):
        
        # FFmpeg concat demuxer helper for escaping single quotes in paths securely
        def escape_concat_path(path_str):
            return path_str.replace("'", r"'\''")

        temp_intro_path = temp_dir / "temp_intro.mp4"
        temp_main_path = temp_dir / "temp_main.mp4"
        parts_file_path = temp_dir / "parts.txt"

        # 1. Get Audio Duration
        self._queue_log("Getting audio duration...", indent=1)
        cmd_probe = [
            ffprobe_exe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", audio_file
        ]
        stdout, stderr = self._run_subprocess(cmd_probe, tool="FFprobe")
        audio_duration_str = ""
        try:
            audio_duration_str = stdout.strip()
            audio_duration = float(audio_duration_str)
            self._queue_log(f"Audio Duration: {audio_duration:.3f}s", indent=1)
        except ValueError as e:
            raise FFprobeError(f"Could not parse valid duration. Error: {e}") from e

        # 2. Generate Intro Video (Logo)
        if logo_file:
            self._queue_log("Generating intro video...", indent=1)
            fade_out_start = max(0, intro_duration - 0.3)
            cmd_intro = [
                ffmpeg_exe, "-y", "-loop", "1", "-t", str(intro_duration), "-i", logo_file,
                "-vf", (f"scale={HD_WIDTH}:{HD_HEIGHT}:force_original_aspect_ratio=decrease,"
                        f"pad={HD_WIDTH}:{HD_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
                        f"fps={fps},format=pix_fmts=yuv420p,fade=t=out:st={fade_out_start:.3f}:d=0.3"),
                "-c:v", "libx264", "-preset", "medium", "-tune", "stillimage",
                "-pix_fmt", "yuv420p", "-loglevel", "warning", str(temp_intro_path)
            ]
            self._run_subprocess(cmd_intro, tool="FFmpeg (intro)")

        # 3. Generate Main Video (Visual)
        self._queue_log("Generating main video...", indent=1)
        cmd_main = [
            ffmpeg_exe, "-y", "-loop", "1", "-t", str(audio_duration), "-i", visual_file,
            "-vf", (f"scale={HD_WIDTH}:{HD_HEIGHT}:force_original_aspect_ratio=decrease,"
                    f"pad={HD_WIDTH}:{HD_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
                    f"fps={fps},format=pix_fmts=yuv420p,fade=t=in:st=0:d=0.3"),
            "-c:v", "libx264", "-preset", "medium", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-loglevel", "warning", str(temp_main_path)
        ]
        self._run_subprocess(cmd_main, tool="FFmpeg (main)")

        if logo_file:
            # 4. Create escaped file list for FFmpeg concat demuxer
            self._queue_log("Creating parts file for merge...", indent=1)
            try:
                intro_posix = escape_concat_path(temp_intro_path.as_posix())
                main_posix = escape_concat_path(temp_main_path.as_posix())
                with open(parts_file_path, 'w', encoding='utf-8') as f:
                    f.write(f"file '{intro_posix}'\n")
                    f.write(f"file '{main_posix}'\n")
            except IOError as e:
                raise IOError(f"Failed to write FFmpeg parts file: {e}") from e

            # 5. Concatenate videos and add audio
            self._queue_log("Merging Intro, Video, and Audio...", indent=1)
            cmd_final_copy = [
                ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", str(parts_file_path),
                "-i", audio_file, "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
                "-shortest", "-movflags", "+faststart", "-loglevel", "warning", str(output_path)
            ]
            try:
                self._run_subprocess(cmd_final_copy, tool="FFmpeg (merge/copy)")
            except FFmpegError:
                 self._queue_log("Video stream copy failed, attempting re-encode...", indent=1, level="warning")
                 cmd_final_reencode = [
                    ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", str(parts_file_path),
                    "-i", audio_file, "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "320k", "-shortest", "-movflags", "+faststart",
                    "-loglevel", "warning", str(output_path)
                 ]
                 self._run_subprocess(cmd_final_reencode, tool="FFmpeg (merge/re-encode)")
        else:
            # Merge Main Video + Audio directly (no concat needed)
            self._queue_log("Merging Video and Audio directly...", indent=1)
            cmd_final_direct = [
                ffmpeg_exe, "-y", "-i", str(temp_main_path), "-i", audio_file,
                "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
                "-shortest", "-movflags", "+faststart", "-loglevel", "warning", str(output_path)
            ]
            self._run_subprocess(cmd_final_direct, tool="FFmpeg (merge direct)")

    def _run_subprocess(self, command_list: list, tool="Subprocess") -> tuple[str, str]:
        # Log the command being run, quoting arguments with spaces
        log_cmd = ' '.join(f'"{arg}"' if ' ' in str(arg) else str(arg) for arg in command_list)
        self._queue_log(f"Running: {log_cmd}", indent=2)

        creationflags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
        try:
            process = subprocess.run(
                command_list, capture_output=True, text=True,
                encoding='utf-8', errors='replace', check=True, creationflags=creationflags
            )
            return process.stdout, process.stderr
        except FileNotFoundError:
            self._queue_log(f"ERROR: Command '{command_list[0]}' not found.", indent=2, level="error")
            raise OSError(f"Command not found: '{command_list[0]}'.") from None
        except subprocess.CalledProcessError as e:
            # Grab exactly what FFmpeg errored out with and push it to the logs
            stderr_snippet = e.stderr.strip() if e.stderr else "(No stderr output)"
            if len(stderr_snippet) > 500:
                stderr_snippet = stderr_snippet[:500] + "\n... (output truncated)"
            
            self._queue_log(f"ERROR during: {log_cmd}", indent=2, level="error")
            self._queue_log(f"Output/Error: {stderr_snippet}", indent=3, level="error")
            
            if tool.startswith("FFmpeg"): raise FFmpegError(f"{tool} failed.") from e
            elif tool.startswith("FFprobe"): raise FFprobeError(f"{tool} failed.") from e
            else: raise

    def _set_ui_state(self, new_state):
        widgets_to_toggle = [
            self.btn_browse_audio, self.btn_browse_logo, self.btn_clear_batch,
            self.entry_logo, self.spin_logo_duration, self.spin_frame_rate,
            self.rb_output_mp3, self.rb_output_custom, self.btn_generate
        ]
        listbox_state = 'disabled' if new_state == tk.DISABLED else 'normal'

        try:
            for widget in widgets_to_toggle:
                 if widget: widget.config(state=new_state)
            if hasattr(self, 'batch_listbox') and self.batch_listbox:
                 self.batch_listbox.config(state=listbox_state)

            custom_entry_state = tk.NORMAL if new_state == tk.NORMAL and self.output_location_mode.get() == "custom" else tk.DISABLED
            if hasattr(self, 'entry_output_custom') and self.entry_output_custom:
                 self.entry_output_custom.config(state=custom_entry_state)
            if hasattr(self, 'btn_browse_output') and self.btn_browse_output:
                 self.btn_browse_output.config(state=custom_entry_state)
        except Exception:
            pass

    def _check_queue(self):
        try:
            while True:
                message_type, data = self.process_queue.get_nowait()
                if message_type == "log": self._update_log(data.get("msg"), indent=data.get("indent", 0), level=data.get("level", "info"))
                elif message_type == "status": self._update_status_label(data)
                elif message_type == "error_popup": messagebox.showerror("Processing Error", data, parent=self.root)
                elif message_type == "start_dots": self._start_dots_timer()
                elif message_type == "stop_dots": self._stop_dots_timer()
                elif message_type == "finish": self._batch_generation_finished(data)
        except queue.Empty:
            pass
        finally:
            if hasattr(self, 'root') and self.root.winfo_exists():
                self.root.after(100, self._check_queue)

    def _queue_log(self, message: str, indent: int = 0, level: str = "info"):
        if not hasattr(self, 'root'): return
        try: self.process_queue.put(("log", {"msg": message, "indent": indent, "level": level}))
        except Exception: pass

    def _update_log(self, message: str, indent: int = 0, level: str = "info"):
        now_str = datetime.now().strftime("%H:%M:%S")
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, f"[{now_str}] ", ("timestamp",))
            tag_list = ["indent"]
            if level.lower() in ["warning", "error"]: tag_list.append(level.lower())
            self.log_text.insert(tk.END, f"{message}\n", tuple(tag_list))
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        except Exception:
            pass

    def _clear_log(self):
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete('1.0', tk.END)
            self.log_text.config(state=tk.DISABLED)
        except Exception:
            pass

    def update_status(self, message: str):
        if not hasattr(self, 'root'): return
        try: self.process_queue.put(("status", message))
        except Exception: pass

    def _update_status_label(self, message: str):
        if message != self.base_status_text:
             if self.dots_timer_id: self._stop_dots_timer()
             self.base_status_text = message
             self.dot_count = 0
        try:
             status_display = self.base_status_text
             if self.dots_timer_id: 
                 # Pad the dots with empty spaces so the text length never changes
                 dots = "." * self.dot_count
                 status_display += f"{dots:<5}" 
                 
             if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                self.status_label.config(text=status_display)
        except Exception:
             pass

    def _update_batch_counter_label(self):
        if not hasattr(self, 'batch_count_label'): return
        try:
            count = len(self.batch_audio_files)
            if self.batch_count_label.winfo_exists():
                self.batch_count_label.config(text=f"({count} file{'s' if count != 1 else ''})")
        except Exception:
            pass

    def _update_dots(self):
        if not self.is_processing or not self.dots_timer_id:
            return self._stop_dots_timer()
        self.dot_count = (self.dot_count % 5) + 1
        self._update_status_label(self.base_status_text)
        if hasattr(self, 'root') and self.root.winfo_exists():
            self.dots_timer_id = self.root.after(500, self._update_dots)
        else:
            self.dots_timer_id = None

    def _start_dots_timer(self):
        if not self.dots_timer_id and self.is_processing:
             self._stop_dots_timer()
             self.dot_count = 0
             self._update_status_label(self.base_status_text)
             if hasattr(self, 'root') and self.root.winfo_exists():
                 self.dots_timer_id = self.root.after(500, self._update_dots)

    def _stop_dots_timer(self):
        if self.dots_timer_id:
            try:
                if hasattr(self, 'root') and self.root: self.root.after_cancel(self.dots_timer_id)
            except Exception: pass
            finally:
                 self.dots_timer_id = None
                 self.dot_count = 0
                 if hasattr(self, 'base_status_text'): self._update_status_label(self.base_status_text)

    def _batch_generation_finished(self, summary: dict):
        self._stop_dots_timer()
        self.is_processing = False
        self._set_ui_state(tk.NORMAL)
        try:
             success_count = summary.get("success", 0)
             fail_count = summary.get("fail", 0)
             final_message = f"Batch Done! {success_count}/{summary.get('total', 0)} succeeded."
             if fail_count > 0: final_message += f" ({fail_count} failed - see log)"
             self.update_status(final_message)
             if fail_count > 0 or success_count > 0 :
                 messagebox.showinfo("Batch Complete", final_message, parent=self.root)
        except Exception:
             pass

    def _on_closing(self):
        if self.is_processing:
            if messagebox.askokcancel("Quit", "Processing is in progress. Are you sure you want to quit?", parent=self.root):
                self._stop_dots_timer()
                self.root.destroy()
        else:
            self._stop_dots_timer()
            self.root.destroy()

# --- Main Execution Guard ---
if __name__ == "__main__":
    if IS_WINDOWS:
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try: windll.user32.SetProcessDPIAware()
            except Exception: pass

    main_root = tk.Tk()
    app = VideoGeneratorApp(main_root)
    main_root.mainloop()