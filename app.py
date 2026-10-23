# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import configparser
import customtkinter as ctk
import logging
import logging.handlers
import queue
import shlex
import sys
from config import (
    AudioConfig, CloudStorageConfig, GuiConfig, Paths, PresentationConfig,
    RecorderConfig, StreamDeckConfig
)
from ctypes import windll
from datetime import datetime
from os import mkdir, path, rename
from pathlib import Path
from modules.state_manager import StateManager
from modules.gui import GuiManager
from modules.recorder import RecorderManager, Action
from modules.stream_deck import StreamDeckManager
from modules.audio import AudioManager
from modules.presentation import PresentationManager
from modules.cloud_storage import CloudStorageManager
from modules.system import SystemManager

app_version: str = "0.0.0"
APP_VERSION_FILE: str = "app_version.txt"
CONFIG_DIR = "config"
CONFIG_FILE: str = "config.cfg"
CONFIG_PATH = path.join(CONFIG_DIR, CONFIG_FILE)
CONFIG_EXAMPLE_FILE: str = "config_example.cfg"
CONFIG_EXAMPLE_PATH = path.join(CONFIG_DIR, CONFIG_EXAMPLE_FILE)
LOGS_DIR: str = "logs"

# ===============================
# Logging
# ===============================
# Look for logs directory
if not path.isdir(LOGS_DIR):
    try:
        mkdir(LOGS_DIR)
        print("Logs directory created")
    except Exception as e:
        print(f"Failed to create logs directory: {e}")

# Enable logging
logger = logging.getLogger(__name__)
log_filename = path.join(
    LOGS_DIR,
    f"log_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
)

formatting = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
file_handler = logging.FileHandler(log_filename, encoding="utf-8")
file_handler.setFormatter(formatting)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatting)
log_queue = queue.Queue(-1)
log_queue_handler = logging.handlers.QueueHandler(log_queue)
log_queue_listener = logging.handlers.QueueListener(
    log_queue, console_handler, file_handler, respect_handler_level=True
)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers = [log_queue_handler]
log_queue_listener.start()

def handle_uncaught_exception(e_type, e_value, e_traceback):
    logger.critical(
        "Uncaught exception, application will terminate. ",
        exc_info=(e_type, e_value, e_traceback)
    )

sys.excepthook = handle_uncaught_exception

# ===============================
# Get application version
# ===============================
# Look for app_version.txt
if not path.isfile(APP_VERSION_FILE):
    try:
        with open(APP_VERSION_FILE, "w") as f:
            f.write(app_version)
            logger.info(f"Wrote tag {app_version} to {APP_VERSION_FILE}")
    except IOError as e:
        logger.error(f"Failed to create app version file: {e}")
    except Exception as e:
        logger.error(f"Failed to create app version file: {e}")

# Get app version number
try:
    with open(APP_VERSION_FILE, "r") as f:
        app_version = f.read().strip()
except Exception as e:
    logger.warning(f"Can't open app version file: {e}")

logger.info(f"DIY Studio App {app_version}")

# ===============================
# Configuration
# ===============================
# Look for config/config.cfg
if not path.isfile(CONFIG_PATH):
    if path.isfile(CONFIG_EXAMPLE_PATH):
        try:
            rename(CONFIG_EXAMPLE_PATH, CONFIG_PATH)
            logger.info("Created config.cfg from example file")
        except Exception as e:
            logger.critical(f"Failed to create configuration file: {e}")
            sys.exit(1)
    else:
        logger.critical("Could not create config file")
        sys.exit(1)

# Read config file
config = configparser.ConfigParser()
read_config = config.read(CONFIG_PATH)
if not read_config:
    logger.critical(
        f"Config file not found or can't be read at {CONFIG_PATH}"
    )
    sys.exit(1)

# There are two websocket connections that need to be made:
# 1) To server of recorder app      >> RecorderManager
# 2) From Stream Deck plugin client >> StreamDeckManager
#
# Then there's a regular socket connection to Ultimatte that
# opens before sending a message and closes immediately after
LOCALHOST = config.get("ip", "localhost")

studio = config.get("studio", "location")
logger.info(f"Location: {studio}")

# Setup config objects for each manager
streamdeck_config = StreamDeckConfig(
    enable=config.getboolean("features", "streamdeck", fallback=False),
    ip=LOCALHOST,
    port=config.getint("port", "streamdeck", fallback=4468)
)

presentation_config = PresentationConfig(
    app_name=config.get("presentation", "app", fallback="PowerPoint"),
    enable=config.getboolean("features", "powerpoint", fallback=False),
    teleprompter_x=config.getint(
        "interface", "teleprompter_offset_x", fallback=0
        ),
    teleprompter_y=config.getint(
        "interface", "teleprompter_offset_y", fallback=-1080
        )
)

audio_config = AudioConfig(
    block_duration=config.getfloat("mic", "block_duration", fallback=0.05),
    channels=config.getint("mic", "channels", fallback=1),
    device_index=config.getint("mic", "device_index", fallback=1),
    enable=config.getboolean("features", "mic_check", fallback=True),
    init_threshold=config.getfloat("mic", "init_threshold", fallback=0.05),
    max_tap_length=config.getfloat("mic", "max_length_of_tap", fallback=0.15),
    oversensitive=config.getfloat(
            "mic", "blocks_top_threshold_reset", fallback=15
        ),
    undersensitive=config.getfloat(
            "mic", "blocks_bot_threshold_reset", fallback=120
        ),
    sample_rate=config.getint("mic", "sample_rate", fallback=48000)
)

cloud_storage_config = CloudStorageConfig(
    client_id=config.get("cloud_storage", "client_id", fallback=""),
    login_timeout=config.getint("cloud_storage", "login_timeout", fallback=90),
    provider=config.get("cloud_storage", "provider", fallback="OneDrive"),
    tenant_id=config.get("cloud_storage", "tenant_id", fallback="")
)

paths = Paths(
    assets_dir=config.get(
            "paths", "assets_dir", fallback=path.join("assets", "static")
        ).replace("$HOME", str(Path.home())),
    backup_dir=config.get("paths", "backup_dir"),
    browser_path=config.get("paths", "browser_path"),
    download_dir=config.get("paths", "download_dir").replace(
            "$HOME", str(Path.home())
        ),
    ffmpeg_path=config.get("paths", "ffmpeg_path"),
    private_key_path=config.get("paths", "private_key_path"),
    public_key_path=config.get("paths", "public_key_path"),
    record_dir=config.get("paths", "record_dir"),
    recorder_path=config.get("paths", "recorder_path"),
    stats_file_path=config.get("paths", "stats_file")
)

gui_config = GuiConfig(
    browser_name=config.get("browser", "name", fallback="No browser"),
    browser_args=shlex.split(config.get("browser", "args", fallback="")),
    browser_quit=config.getboolean(
        "browser", "close_at_logout", fallback=True
        ),
    color_primary=config.get("colors", "primary", fallback="#ffcd00"),
    color_secondary=config.get("colors", "secondary", fallback="#001240"),
    color_bg_content=config.get("colors", "bg_content", fallback="#e8e8e8"),
    color_good=config.get("colors", "good", fallback="#00ff12"),
    color_menu_btn_fg_normal=config.get(
        "colors", "menu_btn_fg_normal", fallback="#ffffff"
        ),
    color_menu_btn_txt_normal=config.get(
        "colors", "menu_btn_txt_normal", fallback="#000000"
        ),
    color_menu_btn_txt_active=config.get(
        "colors", "menu_btn_txt_active", fallback="#ffffff"
        ),
    color_menu_btn_txt_locked=config.get(
        "colors", "menu_btn_txt_locked", fallback="#666666"
        ),
    color_page_btn_fg_normal=config.get(
        "colors", "page_btn_fg_normal", fallback="#ffffff"
        ),
    color_page_btn_fg_locked=config.get(
        "colors", "page_btn_fg_locked", fallback="#cccccc"
        ),
    color_page_btn_txt_normal=config.get(
        "colors", "page_btn_txt_normal", fallback="#000000"
        ),
    color_page_btn_txt_locked=config.get(
        "colors", "page_btn_txt_locked", fallback="#666666"
        ),
    color_page_txt_1=config.get("colors", "page_txt_1", fallback="#000000"),
    color_page_txt_2=config.get("colors", "page_txt_2", fallback="#ffffff"),
    email_logs=config.getboolean("features", "email_logs", fallback=False),
    gui_always_on_top=config.getboolean(
        "interface", "always_on_top", fallback=False
        ),
    gui_offset_x=config.getint("interface", "app_offset_x", fallback=0),
    gui_offset_y=config.getint("interface", "app_offset_y", fallback=0),
    gui_rec_buttons_enabled=config.getboolean(
        "interface", "gui_rec_buttons_enabled", fallback=False
        ),
    key_send_log="<" + config.get("keybindings","send_log") + ">",
    key_toggle_greenscreen="<" + config.get(
        "keybindings","toggle_greenscreen"
        ) + ">",
    key_restart_recorder="<" + config.get("keybindings","reboot_obs") + ">",
    key_toggle_debug="<" + config.get("keybindings","toggle_debug") + ">",
    logo_file_name=config.get(
            "logo", "file_name", fallback="logo.png"
        ),
    logo_height=config.getint("logo", "height", fallback=240),
    logo_width=config.getint("logo", "width", fallback=595),
    recorder_args=shlex.split(
            config.get("recorder", "args", fallback="--portable")
        ),
    studio_location=config.get(
        "studio", "location", fallback="Unknown location"
        ),
    telemetry=config.getboolean("features", "telemetry", fallback=False),
    teleprompter_x=config.getint(
        "interface", "teleprompter_offset_x", fallback=0
        ),
    teleprompter_y=config.getint(
        "interface", "teleprompter_offset_y", fallback=-1080
        ),
    ultimatte_enabled=config.getboolean(
        "features", "ultimatte", fallback=False
        ),
    ultimatte_ip=config.get("ip", "ultimatte", fallback="192.168.10.1"),
    ultimatte_port=config.getint("port", "ultimatte", fallback=9998),
    webhost_url=config.get("ip", "webhost", fallback="")
)

recorder_config = RecorderConfig(
    app=config.get("recorder", "app", fallback="OBS"),
    ip=LOCALHOST,
    enable_projector=config.getboolean(
        "recorder", "projector", fallback=False
        ),
    password=config.get("recorder", "password", fallback=""),
    projector_monitor=config.getint(
        "recorder", "projector_monitor", fallback=0
        ),
    profile=config.get(
            "recorder", "profile", fallback="Profile_v1"
        ),
    scene_collection=config.get(
            "recorder", "scene_collection", fallback="SceneCollection_v1"
        )
)

# ===============================
# Windll setup
# ===============================
# Move mouse cursor to correct screen
# (this assumes a monitor resolution of 1920x1080)
# and give console window a name, so it can be minimized
try:
    x = config.getint("interface", "app_offset_x") + 960
    y = config.getint("interface", "app_offset_y") + 540
    windll.user32.SetCursorPos(x, y)
    windll.kernel32.SetConsoleTitleW("DIY Studio App Console")
except Exception as e:
    logger.error(f"Can't move mouse cursor or set console title: {e}")

# ===============================
# Create root Tkinter window
# ===============================
root_window = ctk.CTk()

# ===============================
# Instantiate managers
# ===============================
system_manager = SystemManager(
    paths=paths,
    log_listener=log_queue_listener,
    backup_days=config.getint(
            "backup", "duration_in_days", fallback=14
    )
)

state_manager = StateManager()

recorder_manager = RecorderManager(
    config=recorder_config,
    paths=paths
)

gui_manager = GuiManager(
    window=root_window,
    app_version=app_version,
    config=gui_config,
    cloud_config=cloud_storage_config,
    log_filename=log_filename,
    paths=paths
)

audio_manager = AudioManager(
    config=audio_config
)

cloud_manager = CloudStorageManager(
    enable=config.getboolean("features", "cloud_storage", fallback=True),
    config=cloud_storage_config,
    paths=paths
)

presentation_manager = PresentationManager(
    root_window=root_window,
    config=presentation_config,
    assets_dir=paths.assets_dir
)

streamdeck_manager = StreamDeckManager(
    root_window=root_window,
    config=streamdeck_config
)

# ===============================
# Assign managers to each other
# ===============================
AudioManager.managers = {
    "gui_manager": gui_manager
}

SystemManager.managers = {
    "cloud_manager": cloud_manager,
    "gui_manager": gui_manager
}

GuiManager.managers = {
    "streamdeck_manager": streamdeck_manager,
    "cloud_manager": cloud_manager,
    "presentation_manager": presentation_manager,
    "recorder_manager": recorder_manager,
    "state_manager": state_manager,
    "system_manager": system_manager
}

CloudStorageManager.managers = {
    "presentation_manager": presentation_manager,
    "state_manager": state_manager,
    "gui_manager": gui_manager
}

PresentationManager.managers = {
    "gui_manager": gui_manager
}

RecorderManager.managers = {
    "streamdeck_manager": streamdeck_manager,
    "system_manager": system_manager,
    "cloud_manager": cloud_manager,
    "state_manager": state_manager,
    "gui_manager": gui_manager
}

StateManager.managers = {
    "audio_manager": audio_manager,
    "streamdeck_manager": streamdeck_manager,
    "system_manager": system_manager,
    "cloud_manager": cloud_manager,
    "presentation_manager": presentation_manager,
    "recorder_manager": recorder_manager,
    "gui_manager": gui_manager
}

StreamDeckManager.managers = {
    "presentation_manager": presentation_manager,
    "recorder_manager": recorder_manager,
    "state_manager": state_manager,
    "gui_manager": gui_manager
}

# Clear all files & copy videoplayer.html to rec/good folder
system_manager.clear_temporary_folders()
system_manager.copy_videoplayer()

# Connect to recorder app
recorder_manager.set_action(Action.CONNECTING)

# ===============================
# Start Tkinter loop
# ===============================
logger.info("Starting Tkinter main loop")
root_window.mainloop()
