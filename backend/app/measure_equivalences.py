"""One-time migration of the former fixed measure aliases into editable settings."""
import json
from pathlib import Path
from .models import SearchSettings
from .search import default_search_config


def initialize_measure_equivalences(db):
    row = db.get(SearchSettings, 1)
    if row is not None and row.config.get("measure_equivalences") is not None:
        return False  # An explicitly empty list is an operator decision too.
    initial = json.loads((Path(__file__).parent / "data" / "search_measure_equivalences.json").read_text())
    if row is None:
        row = SearchSettings(id=1, config=default_search_config())
        db.add(row)
    row.config = {**row.config, "measure_equivalences": initial}
    db.flush()
    return True
