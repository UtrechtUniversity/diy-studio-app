"""Test action scheduling without GUI or integration side effects."""

from queue import Empty, Queue
from threading import Thread

from modules.action_manager import (
    ActionManager,
    ActionRequest,
    ActionResult,
    Workflow,
)


class FakeGuiQueue:
    """Run queued callbacks manually without creating a GUI."""

    def __init__(self):
        self.tasks = Queue()

    def queue_task(self, func, *args, **kwargs):
        """Accept a callback from any thread."""
        self.tasks.put((func, args, kwargs))

    def run_pending(self):
        """Process queued callbacks on the test's main thread."""
        while True:
            try:
                func, args, kwargs = self.tasks.get_nowait()
            except Empty:
                return

            func(*args, **kwargs)


def test_workflow_waits_without_blocking_independent_actions():
    """Wait for workflow completion while allowing independent actions."""
    gui = FakeGuiQueue()
    manager = ActionManager(workflows=[], queue_task=gui.queue_task)

    started = []
    callbacks = {}

    def handler(newstate, on_complete):
        started.append(newstate)
        callbacks[newstate] = on_complete

    manager.register_method(None, handler, "gui.change_state")

    workflow = Workflow([
        ActionRequest("gui.change_state", {"newstate": "first"}),
        ActionRequest("gui.change_state", {"newstate": "second"}),
    ])

    manager.request_workflow(workflow)
    gui.run_pending()

    # The second workflow action must wait.
    assert started == ["first"]

    independent = manager.queue(
        "gui.change_state",
        {"newstate": "independent"},
    )
    gui.run_pending()

    assert started == ["first", "independent"]

    # Simulate completion arriving from a worker thread.
    worker = Thread(
        target=callbacks["first"],
        args=(ActionResult(success=True),),
    )
    worker.start()
    worker.join(timeout=2)

    assert not worker.is_alive()

    # Workflow state cannot advance until the GUI queue processes it.
    assert started == ["first", "independent"]

    gui.run_pending()
    assert started == ["first", "independent", "second"]

    callbacks["second"](ActionResult(success=True))
    callbacks["independent"](ActionResult(success=True))
    gui.run_pending()

    assert independent.result.success

    # A completed workflow can run again.
    manager.request_workflow(workflow)
    gui.run_pending()

    assert started == ["first", "independent", "second", "first"]

