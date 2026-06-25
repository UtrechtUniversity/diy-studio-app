# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioConfig:
    block_duration: float
    channels: int
    device_index: int
    enable: bool
    init_threshold: float
    max_tap_length: float
    oversensitive: float
    undersensitive: float
    sample_rate: int


@dataclass(frozen=True)
class CloudStorageConfig:
    client_id: str
    login_timeout: int
    provider: str
    tenant_id: str


@dataclass (frozen=True)
class GuiConfig:
    browser_name: str
    browser_args: str
    browser_quit: bool
    color_primary: str
    color_secondary: str
    color_bg_content: str
    color_good: str
    color_menu_btn_fg_normal: str
    color_menu_btn_txt_normal: str
    color_menu_btn_txt_active: str
    color_menu_btn_txt_locked: str
    color_page_btn_fg_normal: str
    color_page_btn_fg_locked: str
    color_page_btn_txt_normal: str
    color_page_btn_txt_locked: str
    color_page_txt_1: str
    color_page_txt_2: str
    email_logs: bool
    gui_always_on_top: bool
    gui_offset_x: int
    gui_offset_y: int
    gui_rec_buttons_enabled: bool
    key_send_log: str
    key_toggle_greenscreen: str
    key_restart_recorder: str
    key_toggle_debug: str
    logo_file_name: str
    logo_height: int
    logo_width: int
    recorder_args: str
    studio_location: str
    telemetry: bool
    teleprompter_x: int
    teleprompter_y: int
    ultimatte_enabled: bool
    ultimatte_ip: str
    ultimatte_port: int
    webhost_url: str


@dataclass(frozen=True)
class Paths:
    assets_dir: str
    backup_dir: str
    browser_path: str
    download_dir: str
    ffmpeg_path: str
    private_key_path: str
    public_key_path: str
    record_dir: str
    recorder_path: str
    stats_file_path: str


@dataclass(frozen=True)
class PresentationConfig:
    app_name: str
    enable: bool
    teleprompter_x: int
    teleprompter_y: int


@dataclass (frozen=True)
class RecorderConfig:
    app: str
    ip: str
    enable_projector: bool
    password: str
    projector_monitor: int
    profile: str
    scene_collection: str


@dataclass(frozen=True)
class StreamDeckConfig:
    enable: bool
    ip: str
    port: int
