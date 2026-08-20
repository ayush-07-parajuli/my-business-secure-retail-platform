"""CSV export helpers for report pages."""

from __future__ import annotations

import csv
from io import StringIO

from flask import Response


def build_csv_response(*, filename: str, headers: list[str], rows: list[list]) -> Response:
    """Create a downloadable CSV response."""

    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)

    output = stream.getvalue()
    stream.close()

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
