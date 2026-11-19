"""Built-in condition monitors. Importing this package registers them with app.engine.monitors.REGISTRY."""
from app.monitors import (
    beds,  # noqa: F401
    ed,  # noqa: F401
    equipment,  # noqa: F401
    insurance,  # noqa: F401
    lab,  # noqa: F401
    pharmacy,  # noqa: F401
    radiology,  # noqa: F401
    revenue,  # noqa: F401
    staffing,  # noqa: F401
)
