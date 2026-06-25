# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

"""
This module checks if the microphone is working by detecting an
incoming audio signal above a certain volume threshold.
It does not detect voices.
"""

import logging
import math
import os.path
import sounddevice as sd
import struct
import threading
from functools import partial
from time import sleep

logger = logging.getLogger(__name__)


class AudioManager:
    enabled = True
    managers: dict = {}

    def __init__(self, config):
        logger.info("AudioManager : init")

        self._find_audio_devices()

        self._lock = threading.RLock()
        self._timer_gen = 0

        self.FORMAT = "int16"
        self.SAMPLERATE = config.sample_rate
        self.INITIAL_TAP_THRESHOLD = config.init_threshold
        self.SHORT_NORMALIZE = (1.0/32768.0)
        self.INPUT_BLOCK_TIME = config.block_duration
        self.INPUT_FRAMES_PER_BLOCK = int(
            self.SAMPLERATE*self.INPUT_BLOCK_TIME
            )

        # If we get this many noisy blocks in a row, increase the threshold
        self.OVERSENSITIVE = config.oversensitive/self.INPUT_BLOCK_TIME
        # If we get this many quiet blocks in a row, decrease the threshold
        self.UNDERSENSITIVE = config.undersensitive/self.INPUT_BLOCK_TIME
        # If the noise was longer than this many blocks, it's not a 'tap'
        self.MAX_TAP_BLOCKS = config.max_tap_length/self.INPUT_BLOCK_TIME

        self.CHANNELS = config.channels

        sd.default.device = config.device_index
        sd.default.samplerate = self.SAMPLERATE

        self.noisycount = self.MAX_TAP_BLOCKS + 1
        self.quietcount = 0
        self.errorcount = 0
        self.mic_check_passed = False
        self.listening = False
        self.stream = None
        self.tap_threshold = self.INITIAL_TAP_THRESHOLD
        self.thread = None
        self.timer_id = None

        if not config.enable:
            AudioManager.enabled = False

    # =============================
    # Internal methods
    # =============================
    def _thr_listen(self):
        # Wait two seconds to not trigger it too soon
        sleep(2)
        while True:
            with self._lock:
                if (
                    self.mic_check_passed
                    or not self.listening
                    or self.stream is None
                ):
                    return
            self._listen()

    def _find_audio_devices(self):
        """Prints a list of available audio devices"""
        for device in sd.query_devices():
            logger.info(
                f"Found audio device {device['index']} {device['name']} - "
                f"max input channels: {device['max_input_channels']} - "
                f"max output channels: {device['max_output_channels']}"
            )

    def _get_rms( self, block ):
        # RMS amplitude is defined as the square root of the
        # mean over time of the square of the amplitude.
        # so we need to convert this string of bytes into
        # a string of 16-bit samples.

        # We will get one short out for each
        # two chars in the string.
        count = len(block) // 2
        if count == 0:
            return 0.0
        shorts = struct.unpack(f"{count}h", block)

        # Iterate over the block.
        sum_squares = 0.0
        for sample in shorts:
            # Sample is a signed short in +/- 32768.
            # Normalize it to 1.0
            n = sample * self.SHORT_NORMALIZE
            sum_squares += n*n

        return math.sqrt(sum_squares / count)

    def _listen(self):
        with self._lock:
            if (
                self.mic_check_passed
                or not self.listening
                or self.stream is None
            ):
                return

            # Make snapshot of stream (as stop_mic_check() might nullify it)
            stream = self.stream

        try:
            # logger.info("AudioManager : listening to microphone input")
            block, overflowed = stream.read(self.INPUT_FRAMES_PER_BLOCK)
            if overflowed:
                logger.warning("AudioManager : input overflow while listening")
        except (IOError, OSError) as e:
            self.errorcount += 1
            logger.error(
                f"AudioManager : {self.errorcount} error(s) "
                f"while listening: {e}"
            )
            self.noisycount = 1
            return

        amplitude = self._get_rms(block)
        if amplitude > self.tap_threshold:
            # Noisy block
            self.quietcount = 0
            self.noisycount += 1
            if self.noisycount > self.OVERSENSITIVE:
                # Turn down the sensitivity
                self.tap_threshold *= 1.1
        else:
            # Quiet block
            if 1 <= self.noisycount <= self.MAX_TAP_BLOCKS:
                self.sound_detected()
            self.noisycount = 0
            self.quietcount += 1
            if self.quietcount > self.UNDERSENSITIVE:
                # Turn up the sensitivity
                self.tap_threshold *= 0.9

    def _on_receive_timer_id(self, gen, after_id):
        if after_id is None:
            return

        if self._timer_gen != gen:
            # Received id for older timer, cancel
            self.route_call("gui_manager", "cancel_task_threadsafe", after_id)
            return

        self.timer_id = after_id

    def _on_timer_end(self):
        # Timer has ended, we need to force detection
        # so users will not be stuck on this
        # and can test sound themselves by doing
        # a test recording
        with self._lock:
            if self.mic_check_passed:
                return

            self.timer_id = None

        self.sound_detected(force_detection=True)

        # We need to display an error, though
        self.route_call("gui_manager", "show_error", 107)

    def _open_mic_stream(self, num_channels: int = 1):
        stream = None

        def do_open_stream(num_c):
            stream = sd.RawInputStream(
                blocksize=self.INPUT_FRAMES_PER_BLOCK,
                channels=num_c,
                dtype=self.FORMAT
            )
            stream.start()
            return stream

        try:
            stream = do_open_stream(num_channels)
        except OSError:
            if  num_channels != 1:
                # Try to change to one channel
                num_channels = 1
                stream = do_open_stream(1)
            else:
                logging.exception("AudioManager : can't open mic stream")

        return stream

    def _start_timer(self):
        with self._lock:
            if self.timer_id is not None:
                # Timer running already
                return

            self._timer_gen += 1
            gen = self._timer_gen

            def _on_timer_end_gen_check():
                if self._timer_gen != gen:
                    return
                self._on_timer_end()

        self.route_call(
            "gui_manager",
            "schedule_task_threadsafe",
            30000,
            _on_timer_end_gen_check,
            on_id=partial(self._on_receive_timer_id, gen)
        )

    # =============================
    # Public methods
    # =============================
    def start_mic_check(self):
        if not AudioManager.enabled:
            self.sound_detected(force_detection=True)
            return

        with self._lock:
            if self.mic_check_passed:
                return

            if self.listening and self.stream is not None:
                # Already listening, only start timer
                self._start_timer()
                return

            logger.info("AudioManager : starting mic check")
            self.listening = True
            self.stream = self._open_mic_stream(self.CHANNELS)

            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(
                    name="MicrophoneCheck",
                    target=self._thr_listen,
                    daemon=True
                )
                self.thread.start()

            self._start_timer()

    def stop_mic_check(self):
        with self._lock:
            logger.info("AudioManager : stopping mic check")
            self.listening = False
            self._timer_gen += 1
            timer_id = self.timer_id
            self.timer_id = None
            stream = self.stream
            self.stream = None
            thread = self.thread

        if timer_id is not None:
            self.route_call("gui_manager", "cancel_task_threadsafe", timer_id)
            timer_id = None

        if stream is not None:
            try:
                if getattr(stream, "active", False):
                    stream.stop()
            finally:
                stream.close()

        if (
            thread is not None
            and thread.is_alive()
            and threading.current_thread() is threading.main_thread()
        ):
            # Thread is joined when leaving the page, so it should always
            # be called from the main thread
            self.thread.join(timeout=5)

    def sound_detected(self, force_detection=False):
        with self._lock:
            if self.mic_check_passed:
                return

            if force_detection:
                logger.info("AudioManager : no sound detected : force pass")
            else:
                logger.info("AudioManager : sound detected")

            self.mic_check_passed = True
            self.listening = False

            timer_id = self.timer_id
            self.timer_id = None
            stream = self.stream
            self.stream = None

        if timer_id is not None:
            self.route_call("gui_manager", "cancel_task_threadsafe", timer_id)

        if stream is not None:
            try:
                if getattr(stream, "active", False):
                    stream.stop()
            finally:
                stream.close()

        self.route_call("gui_manager", "on_passed_soundcheck")

    # =============================
    # Outbound communication
    # =============================
    def route_call(self, manager, method, *args, **kwargs):
        gui_manager = AudioManager.managers.get("gui_manager")

        if not gui_manager:
            logger.error("AudioManager : gui_manager not registered")
            return

        match (manager, method):
            case ("gui_manager", "on_passed_soundcheck"):
                gui_manager.call_on_ui_thread(method)

            case ("gui_manager", "cancel_task_threadsafe"):
                gui_manager.cancel_task_threadsafe(*args, **kwargs)

            case ("gui_manager", "schedule_task_threadsafe"):
                return gui_manager.schedule_task_threadsafe(*args, **kwargs)

            case ("gui_manager", "show_error"):
                gui_manager.call_on_ui_thread(method, *args, **kwargs)
