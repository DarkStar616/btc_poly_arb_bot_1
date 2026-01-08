from ..health import Gate

def check_entry_gates(health_mgr, spread_bps, max_spread, logger=None):
    """
    Return True if ENTRY is allowed.
    Log reasons why not.
    """
    status = health_mgr.status
    
    # Check Critical States
    if status.state != health_mgr.config.health.state.RUNNING: # Wait, enum access
        # Enum is BotState.RUNNING. 
        # But we access via class usually?
        # health_mgr is BotHealth instance
        # state is BotState enum
        if status.state.value != "RUNNING":
             return False, f"Bot State: {status.state.value}"

    # Check Gates
    if not status.active_gates:
         # No gates active?
         # Check dynamic ones passed in args
         pass
    else:
         # Some gates active
         # If ANY gate is active, we usually block entry?
         # Some like SPREAD_HIGH are dynamic.
         return False, f"Active Gates: {[g.value for g in status.active_gates]}"

    # Check Spread
    if spread_bps > max_spread:
        health_mgr.set_gate(Gate.SPREAD_HIGH)
        return False, f"Spread High: {spread_bps} > {max_spread}"
    else:
        health_mgr.clear_gate(Gate.SPREAD_HIGH)
    
    return True, "OK"
