"""Browser availability tests with GUI, processes, and networking mocked."""

import ast
import importlib.util
import sys
import threading
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]


class FakeButton:
    """Keep button state and bindings without creating a Tk widget."""

    def __init__(self, parent=None, **kwargs):
        self.values = {"state": "normal", **kwargs}
        self.bindings = {}
        self.configurations = []

    def configure(self, **kwargs):
        self.values.update(kwargs)
        self.configurations.append(kwargs)

    def cget(self, name):
        return self.values[name]

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def unbind(self, *args):
        raise AssertionError("Start should not need to unbind its handlers")

    def place(self, **kwargs):
        pass

    def place_forget(self):
        pass


class FakePageBase:
    """Supply the login page's data and styles without initializing Tk."""

    def __init__(self, parent, ui_elements):
        self.language = "en"
        self.padding = {
            "page_padding_content_y": 100,
            "page_padding_buttons_y": 20,
        }
        self.text = {
            "pagetext": {
                "login": {
                    f"text_{index}": {
                        "en": f"English login {index}",
                        "nl": f"Dutch login {index}",
                    }
                    for index in range(1, 9)
                }
            },
            "pagebuttons": {
                "start": {"en": "Start", "nl": "Start"},
                "logout": {"en": "Logout", "nl": "Uitloggen"},
            },
        }
        self.text_style = {}
        self.btn_style_normal = {
            "state": "normal",
            "width": 370,
            "height": 76,
            "fg_color": "normal",
        }
        self.btn_style_locked = {
            "state": "disabled",
            "fg_color": "locked",
        }
        self.btn_style_hover = {
            "state": "normal",
            "fg_color": "hover",
        }

    def setup_title_by_pagename(self, name):
        pass

    def change_language(self, lang):
        self.language = lang

    def hover(self, button):
        button.configure(**self.btn_style_hover)

    def unhover(self, button):
        button.configure(**self.btn_style_normal)


def _load_module(monkeypatch, name, relative_path):
    """Load the real module after its side-effectful imports are mocked."""
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gui_types():
    """Load real GUI methods without importing optional integrations."""
    path = ROOT / "modules" / "gui.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    pages = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Pages"
    )
    gui = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GuiManager"
    )
    names = {"can_start_session", "on_browser_availability_changed", "_tick"}
    methods = [
        node for node in gui.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    # Compile the existing methods verbatim; skip GUI construction and imports.
    isolated_gui = ast.ClassDef(
        name="GuiManager",
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
        type_params=[],
    )
    namespace = {"Enum": Enum, "time": lambda: 100.0}
    module = ast.Module(body=[pages, isolated_gui], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"),
         namespace)
    return SimpleNamespace(
        GuiManager=namespace["GuiManager"],
        Pages=namespace["Pages"],
    )


@pytest.fixture
def context(monkeypatch, gui_types):
    """Connect the real browser and login page using fake GUI widgets."""
    monkeypatch.setitem(sys.modules, "pywinctl", Mock())
    monkeypatch.setitem(
        sys.modules, "pywintypes", SimpleNamespace(error=OSError)
    )
    browser_module = _load_module(
        monkeypatch, "_test_browser_notifications", "modules/browser.py"
    )
    monkeypatch.setattr(browser_module, "logger", Mock())
    monkeypatch.setattr(
        browser_module.subprocess, "Popen",
        Mock(side_effect=AssertionError("Browser launch must be mocked")),
    )
    monkeypatch.setattr(
        browser_module, "ThreadingHTTPServer",
        Mock(side_effect=AssertionError("HTTP listener must be mocked")),
    )

    gui = gui_types.GuiManager()
    gui.managers = {"cloud_manager": SimpleNamespace(enabled=True)}
    gui.window = Mock()
    gui.cancel_task = Mock()
    gui.queue_task = Mock()
    gui.on_forward = Mock()
    gui.on_logout = Mock()
    gui.tick_active = True
    gui.queue_event = threading.Event()
    gui.queue_scheduled = False
    gui._process_queue = Mock()

    browser = browser_module.Browser(gui, "Test browser", "browser.exe", [],
                                    True)
    gui.browser = browser
    browser._get_browser_processes = Mock(return_value=[])
    browser.get_visible_browser_windows = Mock(return_value=[])
    browser._start_ready_server = Mock(
        return_value="http://127.0.0.1:12345/loading.html"
    )
    browser._start_process = Mock(
        return_value=Mock(poll=Mock(return_value=0))
    )
    browser._stop_ready_server = Mock()

    monkeypatch.setitem(
        sys.modules, "customtkinter",
        SimpleNamespace(CTkButton=FakeButton, CTkLabel=FakeButton),
    )
    monkeypatch.setitem(
        sys.modules, "modules.gui_pages.base",
        SimpleNamespace(PageBase=FakePageBase),
    )
    login_module = _load_module(
        monkeypatch, "_test_login_notifications",
        "modules/gui_pages/login_1.py",
    )
    login_module.PageLogin1.manager = gui
    page = login_module.PageLogin1(None, None)
    gui.pages = {gui_types.Pages.LOGIN1: page}

    events = []

    def notify():
        events.append(browser.state)
        gui.on_browser_availability_changed()

    browser.on_availability_changed = notify
    gui.on_browser_availability_changed()
    return SimpleNamespace(
        browser=browser, gui=gui, page=page, events=events,
        browser_module=browser_module,
    )


def test_ready_notification_enables_start(context):
    assert context.page.btn_start.cget("state") == "disabled"
    assert context.page.label_text.cget("text") == "English login 8"
    context.browser._set_state("ready")
    assert context.page.btn_start.cget("state") == "normal"
    assert context.page.label_text.cget("text") == "English login 1"
    assert context.events == ["ready"]


def test_repeated_state_does_not_notify(context):
    context.browser._set_state("ready")
    context.browser._set_state("ready")
    assert context.events == ["ready"]


def test_state_callback_is_optional(context):
    context.browser.on_availability_changed = None
    context.browser._set_state("ready")
    assert context.browser.state == "ready"


@pytest.mark.parametrize(
    "state", ["starting", "stopping", "failed", "closed", "stopped"]
)
def test_unavailable_browser_locks_start(context, state):
    context.browser._set_state("ready")
    context.browser._set_state(state)
    assert context.page.btn_start.cget("state") == "disabled"
    assert context.page.label_text.cget("text") == "English login 8"


@pytest.mark.parametrize("ready", [False, True])
def test_language_change_preserves_readiness_message(context, ready):
    if ready:
        context.browser._set_state("ready")
    context.page.change_language("nl")
    expected = "Dutch login 1" if ready else "Dutch login 8"
    assert context.page.label_text.cget("text") == expected


@pytest.mark.parametrize("phase", [2, 3, 4])
def test_readiness_change_preserves_other_phase_messages(context, phase):
    type(context.page).phase = phase
    context.page.label_text.configure(text="Current session message")
    context.browser._set_state("ready")
    context.browser._set_state("stopping")
    assert context.page.label_text.cget("text") == "Current session message"


def test_logout_refreshes_waiting_message_when_already_disabled(context):
    context.page.set_authenticated()
    context.page.logout()
    assert context.page.btn_start.cget("state") == "disabled"
    assert context.page.label_text.cget("text") == "English login 8"


def test_guarded_hover_cannot_unlock_start(context):
    button = context.page.btn_start
    enter = button.bindings["<Enter>"]
    leave = button.bindings["<Leave>"]
    enter(None)
    leave(None)
    assert button.cget("state") == "disabled"

    context.browser._set_state("ready")
    enter(None)
    assert button.cget("fg_color") == "hover"
    leave(None)
    assert button.cget("fg_color") == "normal"

    context.browser._set_state("stopping")
    enter(None)
    leave(None)
    assert button.cget("state") == "disabled"
    assert button.cget("fg_color") == "locked"
    assert button.bindings["<Enter>"] is enter
    assert button.bindings["<Leave>"] is leave


def test_gui_tick_does_not_poll_login_readiness(context):
    context.gui.can_start_session = Mock(wraps=context.gui.can_start_session)
    context.page.update_start_button = Mock(
        wraps=context.page.update_start_button
    )
    for _ in range(100):
        context.gui._tick()

    context.gui.can_start_session.assert_not_called()
    context.page.update_start_button.assert_not_called()
    assert context.gui.window.after.call_count == 100

    context.browser._set_state("ready")
    context.page.update_start_button.assert_called_once()
    assert context.page.btn_start.cget("state") == "normal"


def test_startup_success_notifies(context):
    context.browser.state = "starting"
    context.browser.ready_event.set()
    context.browser._poll_startup()
    assert context.events == ["ready"]
    assert context.page.btn_start.cget("state") == "normal"


def test_startup_timeout_notifies(context, monkeypatch):
    context.browser.state = "starting"
    context.browser.deadline = 90.0
    monkeypatch.setattr(context.browser_module, "monotonic", lambda: 100.0)
    context.browser._poll_startup()
    assert context.events == ["failed"]


@pytest.mark.parametrize("failure", ["listener", "process"])
def test_startup_failures_notify(context, failure):
    if failure == "listener":
        context.browser._start_ready_server.side_effect = OSError()
    else:
        context.browser._start_process.return_value = None
    context.browser.launch()
    assert context.events == ["failed"]


def test_restart_notifies_through_stop_and_startup(context):
    process = Mock()
    process.is_running.return_value = True
    context.browser._get_browser_processes.return_value = [process]
    context.browser.state = "ready"
    context.gui.on_browser_availability_changed()

    context.browser.quit_and_restart()
    assert context.events == ["stopping"]
    assert context.page.btn_start.cget("state") == "disabled"

    process.is_running.return_value = False
    context.browser._get_browser_processes.return_value = []
    context.browser._poll_quit()
    assert context.events == ["stopping", "stopped", "starting"]

    context.browser.ready_event.set()
    context.browser._poll_startup()
    assert context.events[-1] == "ready"
    assert context.page.btn_start.cget("state") == "normal"


def test_shutdown_locks_start_during_restart_without_cloud(context):
    context.gui.managers["cloud_manager"].enabled = False
    context.page.refresh()
    assert context.page.btn_start.cget("state") == "normal"
    assert context.page.label_text.cget("text") == "English login 1"

    context.browser.state = "stopping"
    context.browser.shutdown()
    assert context.browser.shutting_down
    assert context.events == ["stopping"]
    assert context.page.btn_start.cget("state") == "disabled"


def test_listener_cleanup_notifies_closed(context):
    context.browser.close = False
    context.browser.state = "ready"
    callback = Mock()
    context.browser.shutdown(callback)
    finish = context.browser._stop_ready_server.call_args.args[0]
    finish()
    assert context.events[-1] == "closed"
    assert context.page.btn_start.cget("state") == "disabled"
    callback.assert_called_once_with()


def test_page_refresh_handles_late_cloud_registration(context):
    context.gui.managers.clear()
    context.browser._set_state("ready")
    assert context.page.btn_start.cget("state") == "disabled"

    context.gui.managers["cloud_manager"] = SimpleNamespace(enabled=True)
    context.page.refresh()
    assert context.page.btn_start.cget("state") == "normal"


def test_console_minimization_targets_the_matching_window():
    """Exercise the startup loop without constructing the rest of the GUI."""
    path = ROOT / "modules" / "gui.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    gui = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GuiManager"
    )
    constructor = next(
        node for node in gui.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    loop = next(
        node for node in constructor.body
        if isinstance(node, ast.For)
        and ast.unparse(node.iter) == "window_manager.getAllTitles()"
    )
    console = Mock()
    namespace = {
        "window": object(),
        "window_manager": SimpleNamespace(
            getAllTitles=Mock(return_value=["python"]),
            getWindowsWithTitle=Mock(return_value=[console]),
        ),
    }
    module = ast.Module(body=[loop], type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)
    console.minimize.assert_called_once_with()
