import streamlit as st
import pandas as pd
from datetime import timedelta

from hotel_checker import (
    DEFAULT_ADULTS,
    DEFAULT_ARRIVAL,
    DEFAULT_HOTEL_ID,
    DEFAULT_HOTEL_NAME,
    DEFAULT_NIGHTS,
    DEFAULT_ROOMS,
    AvailabilityResult,
    build_booking_url,
    check_availability,
    load_check_history,
    save_check_result,
)

st.set_page_config(
    page_title="Hotel Availability",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded",
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
  <p>Pick your dates below, then click Check availability</p>
</div>
""",
    unsafe_allow_html=True,
)

if "hotel_last_result" not in st.session_state:
    st.session_state.hotel_last_result = None


def run_check(
    hotel_id: str,
    hotel_name: str,
    arrival,
    nights: int,
    rooms: int,
    adults: int,
) -> None:
    result = check_availability(
        hotel_id=hotel_id,
        hotel_name=hotel_name,
        arrival=arrival,
        nights=nights,
        rooms=rooms,
        adults=adults,
    )
    save_check_result(result)
    st.session_state.hotel_last_result = result


def render_result(result: AvailabilityResult) -> None:
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


st.markdown("### 1 · Choose your stay")
st.caption("Set the hotel and date range you want to monitor.")

c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
with c1:
    hotel_name = st.text_input("Hotel", value=DEFAULT_HOTEL_NAME, key="hotel_name_input")
with c2:
    arrival = st.date_input("Arrival date", value=DEFAULT_ARRIVAL, key="hotel_arrival_input")
with c3:
    nights = st.number_input("Nights", min_value=1, max_value=14, value=DEFAULT_NIGHTS, key="hotel_nights_input")
with c4:
    rooms = st.number_input("Rooms", min_value=1, max_value=5, value=DEFAULT_ROOMS, key="hotel_rooms_input")
with c5:
    adults = st.number_input("Adults", min_value=1, max_value=8, value=DEFAULT_ADULTS, key="hotel_adults_input")

with st.expander("Advanced (hotel ID)"):
    hotel_id = st.text_input("Hotel ID", value=DEFAULT_HOTEL_ID, key="hotel_id_input")

departure = arrival + timedelta(days=int(nights))
booking_url = build_booking_url(hotel_id, arrival, int(nights), int(rooms), int(adults))

info_left, info_right = st.columns([3, 1])
with info_left:
    st.info(
        f"Checking **{hotel_name}** · "
        f"**{arrival.strftime('%b %d, %Y')}** → **{departure.strftime('%b %d, %Y')}** "
        f"({int(nights)} nights)"
    )
with info_right:
    st.link_button("View on Omni site", booking_url, use_container_width=True)

st.markdown("### 2 · Run a check")
check_col, auto_col = st.columns([1, 1])
with check_col:
    check_now = st.button("Check availability now", type="primary", use_container_width=True)
with auto_col:
    auto_check = st.toggle(
        "Auto-check every 24 hours",
        key="hotel_auto_check",
        help="Re-runs while this page stays open in your browser.",
    )

if check_now:
    with st.spinner("Opening Omni booking calendar…"):
        run_check(hotel_id, hotel_name, arrival, int(nights), int(rooms), int(adults))
    st.rerun()

st.caption("Requires Google Chrome installed on this computer.")

st.markdown("---")
st.markdown("### 3 · Result")

result = st.session_state.hotel_last_result
if result is None:
    history = load_check_history(limit=1)
    if history:
        st.info("Showing your most recent saved check. Click **Check availability now** to refresh.")
        result = AvailabilityResult(**history[-1])
    else:
        st.info("No checks yet. Set your dates above, then click **Check availability now**.")

if result is not None:
    if isinstance(result, dict):
        result = AvailabilityResult(**result)
    render_result(result)

st.markdown("---")
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
                "Arrival": row["arrival_date"],
                "Nights": row["nights"],
                "Status": row["status_text"][:40],
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


@st.fragment(run_every=86400 if st.session_state.get("hotel_auto_check") else None)
def auto_check_fragment():
    if not st.session_state.get("hotel_auto_check"):
        return
    with st.spinner("Running scheduled 24-hour availability check…"):
        run_check(
            st.session_state.get("hotel_id_input", DEFAULT_HOTEL_ID),
            st.session_state.get("hotel_name_input", DEFAULT_HOTEL_NAME),
            st.session_state.get("hotel_arrival_input", DEFAULT_ARRIVAL),
            int(st.session_state.get("hotel_nights_input", DEFAULT_NIGHTS)),
            int(st.session_state.get("hotel_rooms_input", DEFAULT_ROOMS)),
            int(st.session_state.get("hotel_adults_input", DEFAULT_ADULTS)),
        )
    result = st.session_state.hotel_last_result
    available = False
    if result is not None:
        available = result.available if isinstance(result, AvailabilityResult) else result.get("available", False)
    st.toast(
        "Auto-check finished · " + ("rooms available!" if available else "still unavailable"),
        icon="🏨",
    )
    st.rerun()


auto_check_fragment()
