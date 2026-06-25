# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import logging
import os
import shutil
import sys
import threading
import time
from modules.encryption import VideoEncryptor

logger = logging.getLogger(__name__)


class SystemManager:
    managers: dict = {}

    def __init__(
        self, paths, log_listener, backup_days
    ):
        self.MIN_REQ_HDD_SPACE = 50000000000 # 50 GiB
        self.BACKUP_DAYS = backup_days

        self.rec_dir_base = paths.record_dir
        self.rec_dir_good = os.path.join(paths.record_dir, "good")
        self.rec_dir_temp = os.path.join(paths.record_dir, "temp")
        self.rec_dir_bad = os.path.join(paths.record_dir, "bad")
        self.download_dir = paths.download_dir
        self.backup_dir = paths.backup_dir
        self.log_listener = log_listener

        # Check if these directories exist.
        # If not, try to create them and flag a warning
        all_dirs = [
            self.rec_dir_base,
            self.rec_dir_good,
            self.rec_dir_temp,
            self.rec_dir_bad,
            paths.download_dir,
            paths.backup_dir,
            paths.assets_dir
        ]

        for dir in all_dirs:
            if not os.path.isdir(dir):
                self._create_dir(dir)

        self.encrypt_queue_finished = False

        self.encryptor = VideoEncryptor(
            public_key_path=paths.public_key_path,
            private_key_path=paths.private_key_path,
            encrypt_folder=self.backup_dir,
            on_complete=self._on_file_encrypted
        )

        self.shutdown_type = "s"

    # =============================
    # Internal methods
    # =============================
    def _create_dir(self, dir):
        """Create a directory on disk"""
        try:
            os.makedirs(dir, exist_ok=True)
            logger.info(f"SystemManager : created directory {dir}")
        except PermissionError:
            logger.error(
                "SystemManager : no permission to create directory "
                + dir)
            self.route_call("gui_manager", "show_error", 305, True)
        except Exception as e:
            logger.error(
                "SystemManager : error while creating directory "
                f"{dir}: {e}"
            )
            self.route_call("gui_manager", "show_error", 305, True)

    def _encrypt_files(self):
        """Will try to encrypt all files in /backup directory and returns
        the total amount of jobs"""
        amnt = 0
        try:
            amnt = self.encryptor.encrypt_all_files()
        except FileNotFoundError as e:
            logger.error(f"SystemManager : public key not found : {e}")
            self.route_call("gui_manager", "show_error", 106)
            amnt = 0
        except Exception as e:
            logger.error(f"SystemManager : encryption failed : {e}")
            self.route_call("gui_manager", "show_error", 106)
            amnt = 0
        return amnt

    def _on_file_encrypted(self, input, success, num_remaining, err):
        if not success:
            logger.error(
                f"SystemManager : encryption failed for file {input} : {err}"
            )
            self.route_call("gui_manager", "show_error", 106)
            return

        if num_remaining >= 0:
            # Update info on screen
            self.route_call("gui_manager", "update_shutdown_info", num_remaining)

        if num_remaining == 0:
            self.encrypt_queue_finished = True

    def _thr_auto_shutdown(self):
        """Wait for uploads to finish, then encrypt backup files before shutting down"""
        seconds_passed = 0

        # Restart upload queue, if necessary:
        self.route_call("cloud_manager", "restart_upload_queue")

        while not (
            self.route_call("cloud_manager", "all_uploads_done")
        ):
            # Wait a second before checking again
            time.sleep(1)
            seconds_passed += 1
            # Stop waiting after 30 minutes
            if seconds_passed >= 1800:
                self.route_call("gui_manager", "show_error", 406)
                break

        # Start encryption of files
        amnt = self._encrypt_files()

        if amnt == 0:
            self.encrypt_queue_finished = True

        # Wait for encryption to finish
        seconds_passed = 0

        while not (
            self.encrypt_queue_finished
        ):
            time.sleep(1)
            seconds_passed += 1
            # Stop waiting after 30 minutes
            if seconds_passed >= 1800:
                self.route_call("gui_manager", "show_error", 106)
                break

        # Initiate the actual shutdown
        self._shutdown()

    def _shutdown(self):
        """The actual shutdown procedure - no more checks"""
        self.clear_temporary_folders()
        self.route_call("cloud_manager", "logout")
        self.route_call("cloud_manager", "shutdown")
        self.route_call("gui_manager", "quit_browser")
        self.route_call("gui_manager", "close_window")

        # shutdown_type should be either "s" or "r"
        shutdown_type = (self.shutdown_type or "").lower()
        if shutdown_type not in("s", "r"):
            shutdown_type = "s"

        logger.info("SystemManager : shutdown : exiting application")

        try:
            self.log_listener.stop()
        except Exception:
            pass

        # Exit the app. Shutdown and reboot are handled by the
        # AppManager script based on exit code. sys.exit() can only
        # be called from the main thread!
        def _exit_app(t):
            if t == "s":
                sys.exit(0)
            elif t == "r":
                sys.exit(100)

        self.route_call(
            "gui_manager", "schedule_task_threadsafe",
            0, _exit_app, shutdown_type
        )

    def _clear_target_folder(self, folder):
        for filename in os.listdir(folder):

            file_path = os.path.join(folder, filename)

            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)

            except Exception as e:
                logger.error(
                    "SystemManager : clear_temporary_folders : Failed : %s" % (e)
                )

    def _delete_old_files(self, dir):
        # One day is 86400 seconds
        cutoff_time = time.time() - (self.BACKUP_DAYS * 86400)

        for filename in os.listdir(dir):
            path = os.path.join(dir, filename)

            if os.path.isfile(path):
                # getmtime is, apparently, more reliable than getctime
                # on different platforms
                modified_time = os.path.getmtime(path)

                # Is it older than self.BACKUP_DAYS?
                if modified_time < cutoff_time:
                    try:
                        # Delete the file
                        os.remove(path)
                        logger.info("SystemManager : removed backup file "
                                     + filename)
                    except Exception as e:
                        logger.warning("SystemManager : couldn't remove "
                                        + f"backup file: {filename}: {e}")

    # =============================
    # Public methods
    # =============================
    def check_available_hdd_space(self):
        hdd = shutil.disk_usage(self.backup_dir)

        if hdd.free >= self.MIN_REQ_HDD_SPACE:
            logger.info("SystemManager : check_available_hdd_space : Success")
            self.route_call("gui_manager",
                            "log_record_activity",
                            "Diskspace check passed")
            return True
        else:
            # Start deleting backup files until
            # we meet the minimum requirement
            files = sorted(os.listdir(self.backup_dir))
            for filename in files:
                path = os.path.join(self.backup_dir, filename)

                if os.path.isfile(path):
                    try:
                        os.remove(path)
                        logger.info("SystemManager : removed backup file "
                                     + filename)
                    except Exception as e:
                        logger.warning("SystemManager : couldn't remove "
                                        + f"backup file: {filename}: {e}")

                hdd = shutil.disk_usage(self.backup_dir)

                if hdd.free >= self.MIN_REQ_HDD_SPACE:
                    logger.info("SystemManager : enough hard drive space "
                                 + "after removing backup files")
                    return True

            logger.info("SystemManager : check_available_hdd_space : Failed")
            self.route_call("gui_manager", "show_error", 301, True)
            self.route_call("gui_manager",
                            "log_record_activity",
                            "* Not enough disk space *")
            return False

    def clear_temporary_folders(self, shutdown=False):
        logger.info("SystemManager : clearing temporary folders")

        # Move any files that were left behind (in case of a crash)
        # in the temp recording folder to the backup folder
        for filename in os.listdir(self.rec_dir_temp):
            self.backup_file(filename)

        self._clear_target_folder(self.rec_dir_good)
        self._clear_target_folder(self.rec_dir_temp)
        self._clear_target_folder(self.rec_dir_bad)
        self._clear_target_folder(self.download_dir)

        # Clear backup files older than an X amount of days
        self._delete_old_files(self.backup_dir)

        # Clear old log files - temporarily disabled for testing purposes
        # self._delete_old_files("logs")

    def copy_videoplayer(self):
        html_dir = os.path.join(os.getcwd(), "assets", "html")

        # Copy videoplay.html and icons to Recordings base folder
        # if files are newer
        files = [
            "videoplayer.html",
            "pause-button.svg",
            "play-button.svg"
        ]

        for file in files:
            try:
                src_path = os.path.join(html_dir, file)
                src_time = float(0)

                if os.path.isfile(src_path):
                    src_time = os.path.getmtime(src_path)
                else:
                    logger.error(f"SystemManager : could not find {src_path}")

                dest_path = os.path.join(self.rec_dir_base, file)
                dest_time = float(0)

                if os.path.isfile(dest_path):
                    dest_time = os.path.getmtime(dest_path)

                if src_time < 0.1 and dest_time < 0.1:
                    logger.critical(f"SystemManager : {file} not found in both "
                                     "src and dest folders. Can't copy.")
                    self.route_call("gui_manager", "show_error", 307)
                    break

                if src_time > dest_time:
                    logger.info(f"SystemManager : copying {file} to "
                                f"{self.rec_dir_base} (newer version found)")
                    shutil.copy(src_path, dest_path)

            except Exception as e:
                logger.warning("SystemManager : "
                                + f"Couldn't copy {file} to rec dir: {e}")

    def backup_file(self, name):
        logger.info("SystemManager : backup_file : " + name )
        file = os.path.join(self.rec_dir_temp, name)
        backup =  os.path.join(self.backup_dir, name)
        try:
            if os.path.isfile(file):
                shutil.copy(file, backup)
            else:
                logger.error(
                    "SystemManager : backup_file : Failed : no file : " + file
                )

        except Exception as e:
            logger.error("SystemManager : backup_file : Failed : %s" % (e))

    def start_auto_shutdown(self):
        logger.info("SystemManager : starting shutdown checks")
        threading.Thread(
            name="ShutdownThread",
            target=self._thr_auto_shutdown,
            daemon=True
            ).start()

    # =============================
    # Outbound communication
    # =============================
    def route_call(self, manager, method, *args, **kwargs):
        cloud_manager = SystemManager.managers.get("cloud_manager")
        gui_manager = SystemManager.managers.get("gui_manager")

        if not cloud_manager:
            logger.error("SystemManager : cloud_manager not registered")
            return

        if not gui_manager:
            logger.error("SystemManager : gui_manager not registered")
            return

        match (manager, method):
            case ("cloud_manager", "all_uploads_done"):
                return cloud_manager.all_uploads_done()

            case ("cloud_manager", "logout"):
                cloud_manager.logout()

            case ("cloud_manager", "restart_upload_queue"):
                cloud_manager.restart_upload_queue()

            case ("cloud_manager", "shutdown"):
                cloud_manager.shutdown()

            case ("gui_manager", "close_window"):
                gui_manager.close_window()

            case ("gui_manager", "log_record_activity"):
                gui_manager.call_on_ui_thread(method, args[0])

            case ("gui_manager", "quit_browser"):
                gui_manager.call_on_ui_thread(method)

            case ("gui_manager", "schedule_task_threadsafe"):
                gui_manager.schedule_task_threadsafe(*args, **kwargs)

            case ("gui_manager", "show_error"):
                gui_manager.call_on_ui_thread(method, *args, **kwargs)

            case ("gui_manager", "update_shutdown_info"):
                gui_manager.call_on_ui_thread(method, num_encrypt=args[0])
