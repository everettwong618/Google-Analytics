import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta

from hotel_checker import (
    DEFAULT_ADULTS,
    DEFAULT_ARRIVAL,
    DEFAULT_HOTEL_ID,
    DEFAULT_HOTEL_NAME,
    DEFAULT_NIGHTS,
    DEFAULT_ROOMS,
    build_booking_url,
    check_availability,
    load_check_history,
    save_check_result,
)

st.set_page_config(
    page_title="Hotel Availability",
    page_icon="🏨",
    layout="wide",
)

st.markdown(
    """
<style>
    .hotel-header {
        background: linear-gradient(135deg, #234e52 0%, #319795 100%);
        color: white;
        padding: 1.6rem 2rem;
        border-radius: 14px;
        margin-bottom: 1.2rem;
    }
    .hotel-header h1 { color: white !important; margin: 0; font-size: 1.65rem; }
    .hotel-header p { color: rgba(255,255,255,0.8); margin: 0.35rem 0 0; }
    .status-available {
        background: #c6f6d5; color: #22543d; padding: 1rem 1.2rem;
        border-radius: 10px; font-weight: 600; margin: 1rem 0;
    }
    .status-unavailable {
        background: #fed7d7; color: #742a2a; padding: 1rem 1.2rem;
        border-radius: 10px; font-weight: 600; margin: 1rem 0;
    }
    .status-error {
        background: #feebc8; color: #7b341e; padding: 1rem 1.2rem;
        border-radius: 10px; font-weight: 600; margin: 1rem 0;
    }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="hotel-header">
  <h1>🏨 Omni Hotel Availability Checker</h1>
  <p>Monitor room availability for your stay · manual check or auto-check every 24 hours</p>
</div>
""",
    unsafe_allow_html=True,
)

if "hotel_last_result" not in st.session_state:
    st.session_state.hotel_last_result = None


def run_check() -> None:
    result = check_availability(
        hotel_id=st.session_state.get("hotel_id", DEFAULT_HOTEL_ID),
        hotel_name=st.session_state.get("hotel_name", DEFAULT_HOTEL_NAME),
        arrival=st.session_state.get("hotel_arrival", DEFAULT_ARRIVAL),
        nights=st.session_state.get("hotel_nights", DEFAULT_NIGHTS),
        rooms=st.session_state.get("hotel_rooms", DEFAULT_ROOMS),
        adults=st.session_state.get("hotel_adults", DEFAULT_ADULTS),
    )
    save_check_result(result)
    st.session_state.hotel_last_result = result


def render_result(result) -> None:
    if result.error:
        st.markdown(f'<div class="status-error">⚠ {result.message}</div>', unsafe_allow_html=True)
    elif result.available:
        st.markdown(
            f'<div class="status-available">✅ {result.message}</div>',
            unsafe_allow_html=True,
        )
        st.success("Book soon — availability can change quickly.")
    else:
        st.markdown(
            f'<div class="status-unavailable">❌ {result.message}</div>',
            unsafe_allow_html=True,
        )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hotel", result.hotel_name)
    c2.metric("Arrival", result.arrival_date)
    c3.metric("Checkout", result.departure_date)
    c4.metric("Nights", result.nights)

    st.caption(
        f"Calendar status: **{result.status_text}** · "
        f"Checked at {result.checked_at_dt.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    st.link_button("Open booking page", result.booking_url, use_container_width=False)


with st.sidebar:
    st.markdown("### Stay settings")
    hotel_name = st.text_input("Hotel name", value=DEFAULT_HOTEL_NAME)
    hotel_id = st.text_input("Hotel ID", value=DEFAULT_HOTEL_ID)
    arrival = st.date_input("Arrival date", value=DEFAULT_ARRIVAL)
    nights = st.number_input("Nights", min_value=1, max_value=14, value=DEFAULT_NIGHTS)
    rooms = st.number_input("Rooms", min_value=1, max_value=5, value=DEFAULT_ROOMS)
    adults = st.number_input("Adults", min_value=1, max_value=8, value=DEFAULT_ADULTS)

    departure = arrival + timedelta(days=int(nights))
    st.caption(f"Stay: **{arrival.strftime('%b %d, %Y')}** → **{departure.strftime('%b %d, %Y')}**")

    st.session_state.hotel_name = hotel_name
    st.session_state.hotel_id = hotel_id
    st.session_state.hotel_arrival = arrival
    st.session_state.hotel_nights = int(nights)
    st.session_state.hotel_rooms = int(rooms)
    st.session_state.hotel_adults = int(adults)

    booking_url = build_booking_url(
        hotel_id, arrival, int(nights), int(rooms), int(adults)
    )
    st.link_button("View on Omni site", booking_url, use_container_width=True)

    st.markdown("---")
    st.markdown("### Auto-check")
    auto_check = st.toggle(
        "Check every 24 hours",
        key="hotel_auto_check",
        help="Re-runs the availability check once per day while this page is open.",
    )
    if auto_check:
        st.caption("Auto-check is on · runs every 24 hours on this page")

    st.markdown("---")
    st.caption(
        "Requires **Google Chrome** installed on this computer. "
        "The checker opens the real Omni booking site to read the calendar."
    )

col_main, col_history = st.columns([1.4, 1])

with col_main:
    st.markdown("### Current status")

    if st.button("Check availability now", type="primary", use_container_width=True):
        with st.spinner("Opening Omni booking calendar…"):
            run_check()
        st.rerun()

    result = st.session_state.hotel_last_result
    if result is None:
        history = load_check_history(limit=1)
        if history:
            st.info("Showing the most recent saved check. Click **Check availability now** to refresh.")
            from hotel_checker import AvailabilityResult

            result = AvailabilityResult(**history[-1])
        else:
            st.info("No checks yet. Click **Check availability now** to scan the Omni calendar.")

    if result is not None:
        if isinstance(result, dict):
            from hotel_checker import AvailabilityResult

            result = AvailabilityResult(**result)
        render_result(result)

with col_history:
    st.markdown("### Check history")
    history = load_check_history(limit=15)
    if not history:
        st.caption("Past checks will appear here.")
    else:
        rows = []
        for row in reversed(history):
            rows.append(
                {
                    "When": row["checked_at"],
                    "Available": "Yes" if row["available"] else "No",
                    "Status": row["status_text"][:40],
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


@st.fragment(run_every=86400 if st.session_state.get("hotel_auto_check") else None)
def auto_check_fragment():
    if not st.session_state.get("hotel_auto_check"):
        return
    with st.spinner("Running scheduled 24-hour availability check…"):
        run_check()
    result = st.session_state.hotel_last_result
    toast_msg = "Hotel availability auto-check finished"
    if result is not None:
        if isinstance(result, dict):
            available = result.get("available", False)
        else:
            available = result.available
        toast_msg += " · " + ("rooms available!" if available else "still unavailable")
    st.toast(toast_msg, icon="🏨")
    st.rerun()


auto_check_fragment()
