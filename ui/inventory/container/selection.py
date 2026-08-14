"""Stable selection helpers for container tables that change after actions."""


def container_selection_widget_key(state, base_key, container_keys):
    """Return a new widget key whenever the visible container set changes."""
    fingerprint = tuple(str(value) for value in container_keys)
    fingerprint_key = f"{base_key}__fingerprint"
    version_key = f"{base_key}__version"
    if state.get(fingerprint_key) != fingerprint:
        state[fingerprint_key] = fingerprint
        state[version_key] = int(state.get(version_key, 0)) + 1
    return f"{base_key}__{state.get(version_key, 0)}"


def selected_container_key(container_keys, selected_rows):
    """Resolve a selected row safely when Streamlit retains an old position."""
    if not selected_rows:
        return None
    row_position = selected_rows[0]
    if not isinstance(row_position, int):
        return None
    keys = list(container_keys)
    if row_position < 0 or row_position >= len(keys):
        return None
    return keys[row_position]
