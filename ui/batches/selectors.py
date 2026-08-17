"""Dependent state synchronization for batch-first selectors."""


def synchronize_batch_selector_state(state, key, options):
    """Reset a child batch selection whenever its option scope changes."""
    options = list(options)
    signature_key = f"{key}__options_signature"
    signature = tuple(str(value) for value in options)
    if state.get(signature_key) != signature:
        if options:
            state[key] = options[0]
        else:
            state.pop(key, None)
        state[signature_key] = signature
        return True
    if key in state and state[key] not in options:
        state[key] = options[0] if options else None
        if not options:
            state.pop(key, None)
        return True
    return False
