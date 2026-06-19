"""Check Omni Hotels booking calendar for room availability."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Optional

HERE = os.path.dirname(__file__)
HISTORY_FILE = os.path.join(HERE, "hotel_check_history.json")

DEFAULT_HOTEL_ID = "110009"
DEFAULT_HOTEL_NAME = "Omni Nashville Hotel"
DEFAULT_ARRIVAL = date(2027, 7, 14)
DEFAULT_NIGHTS = 4
DEFAULT_ROOMS = 1
DEFAULT_ADULTS = 2

BOOKING_BASE = "https://bookings.omnihotels.com/calendar/hotel"


@dataclass
class AvailabilityResult:
    available: bool
    hotel_name: str
    hotel_id: str
    arrival_date: str
    departure_date: str
    nights: int
    status_text: str
    message: str
    checked_at: str
    booking_url: str
    error: Optional[str] = None

    @property
    def checked_at_dt(self) -> datetime:
        return datetime.fromisoformat(self.checked_at)


def build_booking_url(
    hotel_id: str = DEFAULT_HOTEL_ID,
    arrival: date = DEFAULT_ARRIVAL,
    nights: int = DEFAULT_NIGHTS,
    rooms: int = DEFAULT_ROOMS,
    adults: int = DEFAULT_ADULTS,
) -> str:
    return (
        f"{BOOKING_BASE}/{hotel_id}/arrival/{arrival.isoformat()}/nights/{nights}/"
        f"rooms/{rooms}/adults/{adults}/children/empty/flexisearch/0/"
        f"promocode/none/extras/none"
    )


def load_check_history(limit: int = 20) -> list[dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE) as f:
        rows = json.load(f)
    return rows[-limit:]


def save_check_result(result: AvailabilityResult) -> None:
    history = load_check_history(limit=500)
    history.append(asdict(result))
    with open(HISTORY_FILE, "w") as f:
        json.dump(history[-200:], f, indent=2)


def _matches_arrival_day(text: str, arrival: date) -> bool:
    cleaned = " ".join(text.split())
    month_abbr = arrival.strftime("%b")
    day = arrival.day
    if re.search(rf"\b{month_abbr}\s+0?{day}\b", cleaned, re.I):
        return True
    if cleaned.startswith(f"{day} ") or cleaned == str(day):
        return True
    return bool(re.match(rf"^{day}\b", cleaned))


def _cell_is_available(class_name: str, text: str) -> bool:
    if "calendar-date--disabled" in class_name:
        return False
    if "not available" in text.lower():
        return False
    return True


def check_availability(
    hotel_id: str = DEFAULT_HOTEL_ID,
    hotel_name: str = DEFAULT_HOTEL_NAME,
    arrival: date = DEFAULT_ARRIVAL,
    nights: int = DEFAULT_NIGHTS,
    rooms: int = DEFAULT_ROOMS,
    adults: int = DEFAULT_ADULTS,
) -> AvailabilityResult:
    from playwright.sync_api import sync_playwright

    departure = arrival + timedelta(days=nights)
    booking_url = build_booking_url(hotel_id, arrival, nights, rooms, adults)
    checked_at = datetime.now().isoformat(timespec="seconds")
    last_error = None

    with sync_playwright() as playwright:
        browser = None
        page = None

        for headless in (True, False):
            try:
                browser = playwright.chromium.launch(
                    channel="chrome",
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                page = browser.new_page(
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                )
                page.goto(booking_url, wait_until="domcontentloaded", timeout=90000)
                time.sleep(10)

                title = page.title().lower()
                body_preview = page.inner_text("body")[:600].lower()
                blocked = (
                    "cloudflare" in title
                    or "blocked" in body_preview
                    or "attention required" in title
                )
                if blocked:
                    browser.close()
                    browser = None
                    page = None
                    last_error = "Booking site blocked automated access."
                    continue
                break
            except Exception as exc:
                last_error = str(exc)
                if browser is not None:
                    browser.close()
                    browser = None
                    page = None

        if page is None:
            return AvailabilityResult(
                available=False,
                hotel_name=hotel_name,
                hotel_id=hotel_id,
                arrival_date=arrival.isoformat(),
                departure_date=departure.isoformat(),
                nights=nights,
                status_text="Check failed",
                message=last_error or "Could not open booking page. Install Google Chrome and try again.",
                checked_at=checked_at,
                booking_url=booking_url,
                error=last_error,
            )

        try:
            page_title = page.title()
            if "|" in page_title:
                parts = [part.strip() for part in page_title.split("|")]
                if len(parts) >= 2 and parts[1]:
                    hotel_name = parts[1]

            cells = page.locator(".calendar-date")
            count = cells.count()
            if count == 0:
                raise RuntimeError("Calendar did not load. The booking page layout may have changed.")

            status_text = "Date not found on calendar"
            available = False
            for i in range(count):
                cell = cells.nth(i)
                text = cell.inner_text().strip()
                class_name = cell.get_attribute("class") or ""
                if _matches_arrival_day(text, arrival):
                    status_text = " ".join(text.split())
                    available = _cell_is_available(class_name, text)
                    break

            if available:
                message = (
                    f"Rooms appear available for {arrival.strftime('%b %d, %Y')} "
                    f"to {departure.strftime('%b %d, %Y')} ({nights} nights)."
                )
            elif "not found" in status_text.lower():
                message = (
                    f"Could not find {arrival.strftime('%b %d, %Y')} on the calendar. "
                    "Try checking again or open the booking link manually."
                )
            else:
                message = (
                    f"No rooms available for arrival {arrival.strftime('%b %d, %Y')} "
                    f"({nights} nights, checkout {departure.strftime('%b %d, %Y')})."
                )

            return AvailabilityResult(
                available=available,
                hotel_name=hotel_name,
                hotel_id=hotel_id,
                arrival_date=arrival.isoformat(),
                departure_date=departure.isoformat(),
                nights=nights,
                status_text=status_text,
                message=message,
                checked_at=checked_at,
                booking_url=booking_url,
            )
        except Exception as exc:
            return AvailabilityResult(
                available=False,
                hotel_name=hotel_name,
                hotel_id=hotel_id,
                arrival_date=arrival.isoformat(),
                departure_date=departure.isoformat(),
                nights=nights,
                status_text="Check failed",
                message=str(exc),
                checked_at=checked_at,
                booking_url=booking_url,
                error=str(exc),
            )
        finally:
            if browser is not None:
                browser.close()
