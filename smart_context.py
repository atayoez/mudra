"""Minimal, privacy-conscious AT-SPI context for the pinky gesture.

Mudra never reads selected text. It only asks:
- is the focused accessible object (or its focused text interface) selected?
- does it report one or more text selections?
- is it editable?

That is enough to choose Copy vs Paste without inspecting document contents.
"""


def decide_action(has_selection, editable):
    if has_selection:
        return "copy"
    if editable:
        return "paste"
    return None


class SmartCopyPasteContext:
    def __init__(self, enabled=True, max_nodes=2500):
        self.enabled = bool(enabled)
        self.max_nodes = max(100, int(max_nodes))
        self._pyatspi = None
        self._import_error = None

    def _load(self):
        if self._pyatspi is not None:
            return self._pyatspi
        if self._import_error is not None:
            return None
        try:
            import pyatspi
            self._pyatspi = pyatspi
            return pyatspi
        except Exception as exc:
            self._import_error = exc
            return None

    @staticmethod
    def _contains(obj, state):
        try:
            return obj.getState().contains(state)
        except Exception:
            return False

    def _active_window(self, pyatspi):
        desktop = pyatspi.Registry.getDesktop(0)
        for app in desktop:
            try:
                windows = list(app)
            except Exception:
                continue
            for window in windows:
                if self._contains(window, pyatspi.STATE_ACTIVE):
                    return window
        return None

    def _focused(self, root, pyatspi):
        if root is None:
            return None
        stack = [root]
        seen = 0
        while stack and seen < self.max_nodes:
            node = stack.pop()
            seen += 1
            if self._contains(node, pyatspi.STATE_FOCUSED):
                return node
            try:
                children = list(node)
            except Exception:
                children = []
            stack.extend(reversed(children))
        return None

    def decide(self):
        if not self.enabled:
            return None, "smart copy/paste disabled"

        pyatspi = self._load()
        if pyatspi is None:
            return None, "AT-SPI unavailable"

        try:
            focused = self._focused(self._active_window(pyatspi), pyatspi)
        except Exception:
            return None, "accessibility context unavailable"

        if focused is None:
            return None, "no accessible focused control"

        has_selection = self._contains(focused, pyatspi.STATE_SELECTED)
        editable = self._contains(focused, pyatspi.STATE_EDITABLE)

        # Query only the number of selections; never call getText/getSelection,
        # so Mudra does not read the selected contents.
        try:
            text = focused.queryText()
            has_selection = has_selection or text.getNSelections() > 0
        except Exception:
            pass

        action = decide_action(has_selection, editable)
        if action == "copy":
            return action, "selection detected"
        if action == "paste":
            return action, "editable control"
        return None, "nothing selected and focus is not editable"
