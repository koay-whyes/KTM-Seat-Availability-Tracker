from __future__ import annotations

from datetime import datetime
from typing import Any


def build_analytics_summary(train_data: list[dict[str, Any]]) -> list[str]:
    if not train_data:
        return ["No services found in the latest scrape."]

    available_services = sum(
        1
        for train in train_data
        if ''.join(filter(str.isdigit, train.get('seats_left', ''))) not in ('', '0')
    )
    sold_out_services = sum(
        1
        for train in train_data
        if ''.join(filter(str.isdigit, train.get('seats_left', ''))) in ('', '0')
    )

    departure_times = []
    fares = []
    for train in train_data:
        try:
            departure_times.append(datetime.strptime(train['departure'], "%H:%M").time())
        except Exception:
            pass

        try:
            fare_value = ''.join(ch for ch in train.get('fare', '') if ch.isdigit() or ch == '.')
            if fare_value:
                fares.append(float(fare_value))
        except Exception:
            pass

    lines = [
        f"Total services found: {len(train_data)}",
        f"Services with seats left: {available_services}",
        f"Sold out services: {sold_out_services}",
    ]

    if departure_times:
        lines.append(f"Earliest departure: {min(departure_times).strftime('%H:%M')}")
        lines.append(f"Latest departure: {max(departure_times).strftime('%H:%M')}")

    if fares:
        lines.append(f"Fare range: MYR {min(fares):.2f} - MYR {max(fares):.2f}")

    return lines
