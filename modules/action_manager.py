# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

"""
This is the backbone of the application. It contains a catalogue
of actions and workflows which can be triggered from elsewhere.
In a workflow, each next step will only trigger once the previous
step has finished.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from functools import partial
from operator import eq, ge, gt, le, lt

logger = logging.getLogger(__name__)


class ActionRequest:
    """Describes an action and its parameters."""
    def __init__(self, key, params=None):
        self.key = key
        self.params = dict(params) if params is not None else {}


class Compare(Enum):
    EQUAL = "equal"
    GREATER = "greater"
    LESS = "less"
    EQUAL_OR_GREATER = "equal or greater"
    EQUAL_OR_LESS = "equal or less"


_COMPARISONS = {
    Compare.EQUAL: eq,
    Compare.GREATER: gt,
    Compare.LESS: lt,
    Compare.EQUAL_OR_GREATER: ge,
    Compare.EQUAL_OR_LESS: le
}


@dataclass
class Condition:
    property: str
    operator: Compare = Compare.EQUAL
    value: int | str | bool = 0


@dataclass
class Registration:
    def __init__(self, manager, ref):
        self.manager = manager
        self.ref = ref


class Workflow:
    """From this class, Workflow definitions can be made.

    A Workflow is simply a list of Actions which will be queued;
    each next step is only executed once the previous step has
    completed.

    Only a single active run of a Workflow is allowed at a time.
    """
    def __init__(self, actions: list[ActionRequest]):
        self.actions = actions


class WorkflowExecution:
    """Specific workflow execution instances can be made from this"""
    def __init__(self, manager, workflow):
        self.active = False
        self.manager = manager
        self.workflow = workflow
        self.result = None
        self._pending_actions = workflow.actions.copy()
        self._current_execution = None

    def advance(self):
        """Queue the next action when no action is outstanding."""
        if not self.active or self._current_execution is not None:
            return

        if not self._pending_actions:
            self.manager._finish_workflow(
                self,
                ActionResult(success=True, workflow=self)
            )
            return

        request = self._pending_actions.pop(0)

        self._current_execution = self.manager.queue(
            request.key,
            params=request.params,
            workflow=self
        )

    def on_action_complete(self, execution, result):
        """Advance after success, or stop after failure."""
        if not self.active:
            return

        if execution is not self._current_execution:
            return

        self._current_execution = None

        if not result.success:
            self.manager._finish_workflow(self, result)
            return

        self.advance()


@dataclass
class ActionResult:
    success: bool = False
    workflow: WorkflowExecution | None = None
    error: str | None = None


class Action:
    """Allows creations of a prototype for each action.

    Every handler needs to be a callable which accepts
    an on_complete method as callback."""
    def __init__(self, manager, c, p):
        self.conditions = c
        self.manager = manager
        self.handlers = []
        self.required_params = p

    def register_method(self, manager, method):
        self.handlers.append(Registration(manager, method))

    def unregister_method(self, manager, method):
        for registration in self.handlers:
            if (
                registration.manager == manager
                and registration.method == method
            ):
              self.handlers.pop(registration)


class ActionExecution:
    def __init__(self, action, params, workflow=None):
        self._handler_failure = None
        self.active = False
        self.action = action
        self.params = dict(params)
        self.pending_handlers = set()
        self.workflow = workflow
        self.result = None

    def _record_completion(self, handler_id, result):
     """Record handler completion on the GUI thread."""
     if not self.active or handler_id not in self.pending_handlers:
         # Ignore duplicate or late callbacks.
         return

     self.pending_handlers.remove(handler_id)

     if not result.success and self._handler_failure is None:
         self._handler_failure = result

     if not self.pending_handlers:
         final_result = self._handler_failure
         if final_result is None:
             final_result = ActionResult(
                 success=True,
                 workflow=self.workflow
             )
         self.finalize(final_result)

    def _start_handlers(self):
        """Start all handlers after action validation succeeds."""
        handlers = tuple(self.action.handlers)

        # Prepare all tokens before invoking any handler, since a
        # handler may report completion immediately.
        self.pending_handlers = set(range(len(handlers)))

        if not handlers:
            self.finalize(
                ActionResult(success=True, workflow=self.workflow)
            )
            return

        for handler_id, registration in enumerate(handlers):
            callback = partial(self.on_complete, handler_id)

            try:
                registration.ref(
                    on_complete=callback,
                    **self.params
                )
            except Exception:
                callback(
                    ActionResult(
                        success=False,
                        workflow=self.workflow,
                        error="Action handler failed"
                    )
                )

    def finalize(self, result):
        # Runs when all registered methods have returned,
        # possible cleanup can happen here
        self.action.manager.on_execution_finished(self, result)

    def on_complete(self, handler_id, result):
        """Accept a handler's completion from any thread."""
        self.action.manager._queue_task(
            self._record_completion,
            handler_id,
            result
        )

    def start(self):
        """Validate parameters and current conditions before starting handlers."""
        error = None

        missing = [
            param
            for param in self.action.required_params
            if param not in self.params
        ]

        if "on_complete" in self.params:
            error = "Parameter name 'on_complete' is reserved"
        elif missing:
            error = f"Missing required parameters: {', '.join(missing)}"
        else:
            try:
                for condition in self.action.conditions:
                    actual = self.action.manager.get_property(
                        condition.property
                    )
                    compare = _COMPARISONS[condition.operator]

                    if not compare(actual, condition.value):
                        error = "Conditions not met"
                        break
            except Exception:
                error = "Could not evaluate conditions"

        if error is not None:
            self.finalize(
                ActionResult(
                    success=False,
                    workflow=self.workflow,
                    error=error
                )
            )
            return

        self._start_handlers()


class ActionManager:
    def __init__(self, workflows: list, queue_task):
        self._active_workflows = []
        self._queue_task = queue_task
        self._running = set()

        # Action definitions
        self.actions = {
            "audio.mic_check.start": Action(
                manager=self,
                c=[],
                p=[]
            ),
            "gui.change_state": Action(
                manager=self,
                c=[],
                p=["newstate"]
            ),
            "rec.start": Action(
                manager=self,
                c=[],
                p=[]
            ),
            "rec.show_output": Action(
                manager=self,
                c=[],
                p=[]
            ),
        }

        self.registered_properties = {}

        # Workflow definitions
        self.workflows = {
            "record": Workflow(
                actions=[
                    ActionRequest(
                        key="rec.start",
                        params={}
                    )
                ]
            )

        }

    def _finish_execution(self, execution, result):
        """Record completion and notify the workflow on the GUI thread."""
        if execution not in self._running:
            # Ignore duplicate or late completion notifications.
            return

        self._running.remove(execution)
        execution.active = False
        execution.result = result

        if execution.workflow is not None:
            execution.workflow.on_action_complete(execution, result)

    def _finish_workflow(self, execution, result):
        """Record completion and release the workflow on the GUI thread."""
        if execution not in self._active_workflows:
            return

        self._active_workflows.remove(execution)
        execution.active = False
        execution.result = result

    def _start_execution(self, execution):
        """Start an execution on the GUI thread without waiting for it."""
        self._running.add(execution)
        execution.active = True

        try:
            execution.start()
        except Exception:
            # Validation and handler failures should normally be handled
            # inside start(); this also catches unexpected startup
            # failures.
            self._finish_execution(
                execution,
                ActionResult(
                    success=False,
                    error="Action could not be started"
                )
            )

    def _start_workflow(self, workflow):
        """Start a workflow on the GUI thread, unless already active."""
        for execution in self._active_workflows:
            if execution.workflow is workflow:
                # Workflow is already running.
                # Return a message
                return

        execution = WorkflowExecution(manager=self, workflow=workflow)
        execution.active = True
        self._active_workflows.append(execution)
        execution.advance()

    def get_property(self, key):
        """Read a registered property's current value on the GUI thread."""
        return self.registered_properties[key]()

    def on_execution_finished(self, execution, result):
        """Submit a final result from any thread."""
        self._queue_task(self._finish_execution, execution, result)

    def queue(self, key, params=None, workflow=None) -> ActionExecution:
        """Submit an action for execution on the GUI thread."""
        action = self.actions.get(key)

        if action is None:
            raise ValueError(f"Unknown action: {key}")

        execution = ActionExecution(
            action,
            params if params is not None else {},
            workflow
        )

        self._queue_task(self._start_execution, execution)
        return execution

    def register_method(self, manager, method, key):
        """Add a method to the list of an Action's registers."""
        action = self.actions.get(key)
        if action is None:
            return
        action.register_method(manager, method)

    def register_property(self, key, getter):
        """Register a callable that returns the property's current value."""
        if key in self.registered_properties:
            raise ValueError(f"Property already registered: {key}")

        if not callable(getter):
            raise TypeError("Property getter must be callable")

        self.registered_properties[key] = getter

    def request_workflow(self, workflow):
        """Request a workflow start from any thread."""
        # Validate before scheduling so the caller receives configuration
        # errors directly, before any workflow actions execute.
        for request in workflow.actions:
            if request.key not in self.actions:
                raise ValueError(f"Unknown action: {request.key}")

        self._queue_task(self._start_workflow, workflow)

    def unregister_method(self, manager, method, key):
        action = self.actions.get(key)
        if action is None:
            return
        action.unregister_method(manager, method)

    def unregister_property(self, key):
        """Remove a registered property, if present."""
        self.registered_properties.pop(key, None)
