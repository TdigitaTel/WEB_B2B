"""Read-only per-line provenance and fulfilment marks, stored independently of header linkage."""

def line_marks(item):
    removed = bool(item.exit_removed_at)
    return {"created_in_web": item.created_in_web,
            "entered_in_exit": item.exit_entered_at is not None,
            "exit_entered_at": item.exit_entered_at,
            "removed_in_exit": removed, "will_not_be_served": removed}
