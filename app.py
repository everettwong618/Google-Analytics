import os
import json
import io
import re
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from typing import Optional

st.set_page_config(
    page_title="Survey Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    footer { visibility: hidden; }
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

    .app-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
        color: white;
        padding: 1.8rem 2.2rem;
        border-radius: 14px;
        margin-bottom: 1.5rem;
    }
    .app-header h1 { color: white !important; margin: 0; font-size: 1.75rem; font-weight: 700; }
    .app-header p  { color: rgba(255,255,255,0.75); margin: 0.35rem 0 0; font-size: 0.95rem; }

    [data-testid="metric-container"] {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }

    .status-ok   { color: #38a169; font-weight: 600; }
    .status-err  { color: #e53e3e; font-weight: 600; }
    .step        { background: #f7fafc; border-left: 3px solid #4299e1;
                   padding: 0.5rem 0.75rem; margin: 0.4rem 0;
                   border-radius: 0 6px 6px 0; font-size: 0.82rem; }
</style>
""", unsafe_allow_html=True)

COLOR_SEQ = px.colors.qualitative.Set2
HERE = os.path.dirname(__file__)
CLIENT_SECRET_FILE = os.path.join(HERE, "client_secret.json")
TOKEN_FILE = os.path.join(HERE, "authorized_user.json")
FORMS_FILE = os.path.join(HERE, "forms.json")

OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
FORMS_BODY_READONLY_SCOPE = "https://www.googleapis.com/auth/forms.body.readonly"

FORM_MIME = "application/vnd.google-apps.form"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
SHEET_URL_TEMPLATE = "https://docs.google.com/spreadsheets/d/{sheet_id}/edit"


class ReconsentRequired(Exception):
    """Saved login token is missing permissions or cannot be refreshed."""


def load_forms() -> dict:
    if os.path.exists(FORMS_FILE):
        with open(FORMS_FILE) as f:
            return json.load(f)
    return {}


def save_forms(forms: dict):
    with open(FORMS_FILE, "w") as f:
        json.dump(forms, f, indent=2)


def merge_forms(discovered: dict, existing: dict) -> dict:
    """Keep manually added sheets that are not part of the latest Google sync."""
    merged = dict(discovered)
    discovered_urls = set(discovered.values())
    for name, url in existing.items():
        if name not in merged and url not in discovered_urls:
            merged[name] = url
    return merged


def load_stored_credentials():
    from google.oauth2.credentials import Credentials

    # Use scopes saved in the token file only — do not override with OAUTH_SCOPES.
    return Credentials.from_authorized_user_file(TOKEN_FILE)


def granted_scopes() -> set[str]:
    if not os.path.exists(TOKEN_FILE):
        return set()
    return set(load_stored_credentials().scopes or [])


def get_credentials():
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request

    creds = load_stored_credentials()
    missing = set(OAUTH_SCOPES) - granted_scopes()
    if missing:
        raise ReconsentRequired(
            "Your saved Google login is missing permissions. "
            "Log out, then log in again."
        )
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        except RefreshError as exc:
            raise ReconsentRequired(
                "Your Google login expired and could not be refreshed. "
                "Log out, then log in again."
            ) from exc
    return creds


def credentials_need_reconsent() -> bool:
    if not os.path.exists(TOKEN_FILE):
        return True
    return not set(OAUTH_SCOPES).issubset(granted_scopes())


def _drive_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _list_drive_files(drive, query: str) -> list[dict]:
    files = []
    page_token = None
    while True:
        response = drive.files().list(
            q=query,
            fields="nextPageToken, files(id, name)",
            pageSize=100,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return files


def _linked_sheet_via_forms_api(
    forms_api, form_id: str
) -> tuple[Optional[str], Optional[str]]:
    form = forms_api.forms().get(formId=form_id).execute()
    title = (form.get("info") or {}).get("title")
    return form.get("linkedSheetId"), title


def _linked_sheet_via_drive(
    drive, form_id: str, fallback_name: str
) -> tuple[Optional[str], str]:
    meta = drive.files().get(
        fileId=form_id,
        fields="id,name,parents",
        supportsAllDrives=True,
    ).execute()
    title = (meta.get("name") or fallback_name).strip() or fallback_name
    parents = meta.get("parents") or []

    exact_names = [f"{title} (Responses)", f"{title}(Responses)"]
    for name in exact_names:
        query = (
            f"mimeType='{SHEET_MIME}' and trashed=false "
            f"and name='{_drive_escape(name)}'"
        )
        matches = _list_drive_files(drive, query)
        if matches:
            return matches[0]["id"], title

    if parents:
        parent = parents[0]
        query = (
            f"mimeType='{SHEET_MIME}' and trashed=false "
            f"and '{parent}' in parents"
        )
        folder_sheets = _list_drive_files(drive, query)
        for sheet in folder_sheets:
            sheet_name = sheet.get("name", "")
            lower = sheet_name.lower()
            if "response" in lower and title.lower() in lower:
                return sheet["id"], title
        for sheet in folder_sheets:
            if sheet.get("name", "").lower().startswith("form responses"):
                return sheet["id"], title

    short_title = _drive_escape(title[:60])
    query = (
        f"mimeType='{SHEET_MIME}' and trashed=false "
        f"name contains '{short_title}' and name contains 'Response'"
    )
    fuzzy_matches = _list_drive_files(drive, query)
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]["id"], title

    return None, title


def _unique_form_name(title: str, form_id: str, used: set[str]) -> str:
    name = (title or "Untitled form").strip() or "Untitled form"
    if name not in used:
        used.add(name)
        return name
    suffix = f" ({form_id[:8]})"
    candidate = f"{name}{suffix}"
    n = 2
    while candidate in used:
        candidate = f"{name}{suffix}-{n}"
        n += 1
    used.add(candidate)
    return candidate


@st.cache_data(ttl=300, show_spinner=False)
def discover_google_forms(token_mtime: float) -> tuple[dict, list[str]]:
    """List Google Forms in Drive and match each to its response spreadsheet."""
    from googleapiclient.discovery import build

    creds = get_credentials()
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    forms_api = None
    if FORMS_BODY_READONLY_SCOPE in granted_scopes():
        forms_api = build("forms", "v1", credentials=creds, cache_discovery=False)

    form_files = _list_drive_files(
        drive, f"mimeType='{FORM_MIME}' and trashed=false"
    )

    discovered = {}
    skipped = []
    used_names = set()

    for item in form_files:
        form_id = item["id"]
        fallback_name = item.get("name", "Untitled form")
        linked_sheet_id = None
        title = fallback_name

        if forms_api is not None:
            try:
                linked_sheet_id, api_title = _linked_sheet_via_forms_api(forms_api, form_id)
                if api_title:
                    title = api_title
            except Exception:
                linked_sheet_id = None

        if not linked_sheet_id:
            try:
                linked_sheet_id, title = _linked_sheet_via_drive(
                    drive, form_id, fallback_name
                )
            except Exception as e:
                skipped.append(f"{fallback_name}: could not inspect form ({e})")
                continue

        if not linked_sheet_id:
            skipped.append(
                f"{title}: no linked response sheet found "
                "(open the form in Google → Responses → Link to Sheets)"
            )
            continue

        name = _unique_form_name(title, form_id, used_names)
        discovered[name] = SHEET_URL_TEMPLATE.format(sheet_id=linked_sheet_id)

    return discovered, skipped


def sync_forms_from_google() -> tuple[int, list[str]]:
    token_mtime = os.path.getmtime(TOKEN_FILE) if os.path.exists(TOKEN_FILE) else 0.0
    discover_google_forms.clear()
    discovered, skipped = discover_google_forms(token_mtime)
    merged = merge_forms(discovered, load_forms())
    save_forms(merged)
    return len(discovered), skipped


def run_google_login_and_sync():
    login_with_google()
    st.cache_resource.clear()
    st.cache_data.clear()
    return sync_forms_from_google()


def is_oauth_client_secret(uploaded_bytes: bytes) -> bool:
    try:
        data = json.loads(uploaded_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return "installed" in data


# ── helpers ───────────────────────────────────────────────────────────────────

def classify(series):
    name = series.name.lower()
    if "timestamp" in name:
        return "timestamp"
    n = series.count()
    if n == 0:
        return "empty"
    n_unique = series.nunique()
    numeric = pd.to_numeric(series, errors="coerce")
    n_num = numeric.notna().sum()
    if n_num / n >= 0.8:
        if n_unique <= 10 and numeric.min() >= 1 and numeric.max() <= 10:
            return "scale"
        return "numeric"
    if n_unique <= 20 and n_unique / n < 0.6:
        return "categorical"
    return "text"


def make_chart(df, col, ctype):
    if ctype == "categorical":
        counts = df[col].value_counts().reset_index()
        counts.columns = ["Response", "Count"]
        if len(counts) <= 5:
            fig = px.pie(counts, names="Response", values="Count", hole=0.38,
                         color_discrete_sequence=COLOR_SEQ)
            fig.update_traces(textposition="inside", textinfo="percent+label",
                              textfont_size=12)
        else:
            counts = counts.sort_values("Count")
            fig = px.bar(counts, x="Count", y="Response", orientation="h",
                         text="Count", color="Response",
                         color_discrete_sequence=COLOR_SEQ)
            fig.update_layout(showlegend=False)
    elif ctype == "scale":
        num = pd.to_numeric(df[col], errors="coerce").dropna()
        counts = num.value_counts().sort_index().reset_index()
        counts.columns = ["Rating", "Count"]
        fig = px.bar(counts, x="Rating", y="Count", text="Count",
                     color_discrete_sequence=["#4299e1"])
        avg = num.mean()
        fig.add_vline(x=avg, line_dash="dash", line_color="#e53e3e",
                      annotation_text=f"avg {avg:.1f}",
                      annotation_position="top right",
                      annotation_font_color="#e53e3e")
        fig.update_layout(showlegend=False)
    elif ctype == "numeric":
        num = pd.to_numeric(df[col], errors="coerce").dropna()
        fig = px.histogram(num, nbins=min(20, num.nunique()),
                           labels={"value": col},
                           color_discrete_sequence=["#4299e1"])
        fig.update_layout(showlegend=False)

    fig.update_layout(
        title=dict(text=f"<b>{col[:60]}</b>", font=dict(size=13, color="#2d3748"), x=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#fafafa",
        margin=dict(t=44, b=16, l=16, r=16),
        font=dict(family="'Segoe UI', Arial, sans-serif", size=12),
        xaxis=dict(gridcolor="#ebebeb", linecolor="#e2e8f0"),
        yaxis=dict(gridcolor="#ebebeb", linecolor="#e2e8f0"),
        height=340,
    )
    return fig


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Treat blank strings like missing answers throughout the dashboard."""
    return df.replace(r"^\s*$", pd.NA, regex=True)


def build_stats(df: pd.DataFrame, types: dict) -> pd.DataFrame:
    rows = []
    total = len(df)

    for col, ctype in types.items():
        if ctype in ("timestamp", "empty"):
            continue

        n = df[col].count()
        completion = n / total * 100 if total else 0
        row = {
            "Question": col[:65],
            "Type": ctype,
            "Answered": n,
            "Missing": total - n,
            "Completion": f"{completion:.0f}%",
            "Mean": "", "Median": "", "Std Dev": "", "Top Response": "",
        }
        if ctype in ("scale", "numeric"):
            num = pd.to_numeric(df[col], errors="coerce")
            if num.notna().any():
                row["Mean"] = f"{num.mean():.2f}"
                row["Median"] = f"{num.median():.1f}"
                row["Std Dev"] = f"{num.std():.2f}" if num.notna().sum() > 1 else ""
        elif ctype == "categorical":
            top = df[col].value_counts()
            if len(top):
                row["Top Response"] = f"{top.index[0]} ({top.iloc[0]}x)"
        rows.append(row)

    return pd.DataFrame(rows)


def csv_download(dataframe: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    dataframe.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def safe_key(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
    return value or "dashboard"


def filter_by_date_range(df: pd.DataFrame, types: dict, key_prefix: str) -> pd.DataFrame:
    timestamp_cols = [col for col, ctype in types.items() if ctype == "timestamp"]
    if not timestamp_cols:
        return df

    timestamp_col = timestamp_cols[0]
    dates = pd.to_datetime(df[timestamp_col], errors="coerce")
    valid_dates = dates.dropna()
    if valid_dates.empty:
        return df

    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()
    selected_range = st.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key=f"{key_prefix}_date_range",
    )

    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = selected_range
        mask = dates.dt.date.between(start_date, end_date)
        filtered_df = df[mask.fillna(False)]
        if len(filtered_df) != len(df):
            st.caption(f"{len(filtered_df)} of {len(df)} responses in selected date range")
        return filtered_df

    return df


def login_with_google():
    """Open a browser, log the user in, and cache the token. Run on button click."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    with open(CLIENT_SECRET_FILE) as f:
        secret = json.load(f)
    if "installed" not in secret:
        kind = "service account" if secret.get("type") == "service_account" else "the wrong type"
        raise ValueError(
            f"client_secret.json looks like {kind}. You need an "
            "OAuth client ID of type 'Desktop app' (its JSON has an \"installed\" section)."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, OAUTH_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


@st.cache_resource(show_spinner=False)
def get_client():
    """Return an authorized gspread client from the cached token (refreshing if needed)."""
    import gspread

    return gspread.authorize(get_credentials())


@st.cache_data(ttl=15, show_spinner=False)
def fetch_sheet(sheet_url: str) -> pd.DataFrame:
    # Short TTL so each auto-refresh tick (>=30s) always pulls fresh data,
    # while rapid UI interactions (search, tab switches) still hit the cache.
    client = get_client()
    records = client.open_by_url(sheet_url).sheet1.get_all_records()
    return pd.DataFrame(records)


def is_connected() -> bool:
    return os.path.exists(TOKEN_FILE)


def render_dashboard(df: pd.DataFrame, key_prefix: str = "dashboard"):
    df = normalize_df(df)
    if df.empty:
        st.warning("This data source has no responses yet.")
        return

    key_prefix = safe_key(key_prefix)
    types = {col: classify(df[col]) for col in df.columns}
    df = filter_by_date_range(df, types, key_prefix)
    if df.empty:
        st.warning("No responses match the selected date range.")
        return

    types = {col: classify(df[col]) for col in df.columns}
    plottable = [c for c, t in types.items() if t not in ("timestamp", "empty", "text")]
    text_cols  = [c for c, t in types.items() if t == "text"]
    question_cols = [c for c, t in types.items() if t not in ("timestamp", "empty")]
    q_count    = sum(1 for t in types.values() if t not in ("timestamp", "empty"))
    completion = df[question_cols].notna().mean().mean() * 100 if question_cols else 0.0
    stats_df = build_stats(df, types)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Responses", f"{len(df):,}")
    c2.metric("Questions", q_count)
    c3.metric("Avg Completion", f"{completion:.0f}%")
    c4.metric("Open-Text Fields", len(text_cols))

    st.markdown("<br>", unsafe_allow_html=True)

    tab_charts, tab_data, tab_stats = st.tabs(["  Charts  ", "  Raw Data  ", "  Statistics  "])

    with tab_charts:
        if not plottable:
            st.info("No plottable columns detected.")
        else:
            left, right = st.columns(2, gap="medium")
            panes = [left, right]
            for i, col_name in enumerate(plottable):
                fig = make_chart(df, col_name, types[col_name])
                panes[i % 2].plotly_chart(fig, width="stretch")
            if text_cols:
                st.markdown("---")
                st.caption("OPEN-TEXT RESPONSES")
                for col in text_cols:
                    with st.expander(col):
                        for s in df[col].dropna().tolist():
                            st.markdown(f"- {s}")

    with tab_data:
        search = st.text_input(
            "Filter rows",
            placeholder="Type to search across all columns…",
            key=f"{key_prefix}_search",
        )
        display_df = df
        if search:
            mask = df.apply(
                lambda r: r.astype(str).str.contains(search, case=False, regex=False, na=False)
            ).any(axis=1)
            display_df = df[mask]
            st.caption(f"{len(display_df)} of {len(df)} rows shown")
        st.dataframe(display_df, width="stretch", height=460)
        st.download_button(
            "Download filtered CSV",
            data=csv_download(display_df),
            file_name="survey_responses_filtered.csv",
            mime="text/csv",
            key=f"{key_prefix}_filtered_csv",
            use_container_width=True,
        )

    with tab_stats:
        st.dataframe(stats_df, width="stretch", height=460)
        st.download_button(
            "Download statistics CSV",
            data=csv_download(stats_df),
            file_name="survey_statistics.csv",
            mime="text/csv",
            key=f"{key_prefix}_stats_csv",
            use_container_width=True,
        )


# ── sidebar ───────────────────────────────────────────────────────────────────

auto_on = False
refresh_secs = None
app_section = "Survey Analytics"

with st.sidebar:
    st.markdown("### Section")
    app_section = st.radio(
        "Section",
        ["Survey Analytics", "Hotel Availability"],
        horizontal=True,
        label_visibility="collapsed",
    )
    st.markdown("---")

if app_section == "Hotel Availability":
    from hotel_page import render_hotel_checker

    render_hotel_checker()
    st.stop()

with st.sidebar:
    st.markdown("### Data Source")
    source = st.radio(
        "Choose data source",
        ["Google Forms (Live)", "CSV Upload"],
    )

    st.markdown("---")

    if source == "Google Forms (Live)":
        has_secret = os.path.exists(CLIENT_SECRET_FILE)

        if not has_secret:
            st.info("Google login needs one quick setup file before the Log in with Google button can work. This is not an API key.")
            st.markdown('<span class="status-err">Google login setup missing</span>',
                        unsafe_allow_html=True)
            uploaded_secret = st.file_uploader("Upload Google login setup JSON", type=["json"])
            if uploaded_secret:
                secret_bytes = uploaded_secret.read()
                if is_oauth_client_secret(secret_bytes):
                    with open(CLIENT_SECRET_FILE, "wb") as f:
                        f.write(secret_bytes)
                    st.success("Google login setup saved. Reloading...")
                    st.rerun()
                else:
                    st.error("That does not look like the right Google login setup file. Create an OAuth client ID with application type Desktop app, then upload that JSON.")
        elif is_connected():
            st.markdown('<span class="status-ok">Logged in with Google</span>',
                        unsafe_allow_html=True)
            if credentials_need_reconsent():
                st.warning(
                    "Your saved login is out of date. "
                    "Log out and sign in again, then click **Sync forms from Google**."
                )
            if st.button("Log out of Google", use_container_width=True):
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                st.cache_resource.clear()
                st.cache_data.clear()
                st.rerun()
        else:
            st.markdown('<span class="status-err">Not logged in with Google</span>',
                        unsafe_allow_html=True)
            st.caption("A browser window will open so you can log in with your Google account.")
            if st.button("Log in with Google", use_container_width=True):
                try:
                    with st.spinner("Signing in and loading your Google Forms…"):
                        found, skipped = run_google_login_and_sync()
                    st.success(f"Logged in! Found {found} form(s) with linked response sheets.")
                    if skipped:
                        st.info("Some forms were skipped:\n\n" + "\n".join(f"- {s}" for s in skipped))
                    st.rerun()
                except Exception as e:
                    st.error(f"Google sign-in failed: {e}")
                    st.info("If the setup file is wrong, delete client_secret.json from this folder and upload the Desktop app OAuth JSON.")

        st.markdown("---")
        forms = load_forms()

        if is_connected() and not credentials_need_reconsent():
            if st.button("Sync forms from Google", use_container_width=True):
                try:
                    with st.spinner("Loading forms from your Google account…"):
                        found, skipped = sync_forms_from_google()
                    forms = load_forms()
                    st.success(f"Synced {found} form(s) from Google ({len(forms)} total in app).")
                    if skipped:
                        st.info("Skipped:\n\n" + "\n".join(f"- {s}" for s in skipped))
                    st.rerun()
                except ReconsentRequired as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Could not sync forms: {e}")
                    st.info(
                        "If sync keeps failing, log out and sign in again. "
                        "Forms must also have **Responses → Link to Sheets** enabled in Google Forms."
                    )

        # --- pick which saved form(s) to view ---
        if forms:
            st.markdown("**Your forms**")
            view_mode = st.radio(
                "View", ["Single form", "Compare all"],
                horizontal=True,
            )
            if view_mode == "Single form":
                selected_form = st.selectbox("Select form", list(forms.keys()))
            else:
                selected_form = None
        else:
            view_mode = "Single form"
            selected_form = None
            if is_connected() and not credentials_need_reconsent():
                st.caption("No forms with linked response sheets found yet. Click **Sync forms from Google** above.")
            else:
                st.caption("Sign in with Google to load your forms automatically.")

        st.markdown("**Refresh**")
        if st.button("Refresh now", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        auto_on = st.toggle(
            "Auto-refresh",
            key="auto_refresh_on",
            help="When on, the dashboard re-pulls the latest responses on a timer.",
        )
        if auto_on:
            interval_label = st.selectbox(
                "Refresh every",
                ["30 seconds", "1 minute", "5 minutes"],
                index=1,
                key="auto_refresh_interval",
            )
            refresh_secs = {"30 seconds": 30, "1 minute": 60,
                            "5 minutes": 300}[interval_label]
            st.caption(f"Auto-refresh on · every {interval_label.lower()}")
        else:
            refresh_secs = None
            st.caption("Auto-refresh off · turn on to poll for new responses")

        # --- add / remove forms ---
        with st.expander("➕ Add a form manually"):
            st.caption("Optional — use this if you want to add a response sheet URL by hand.")
            new_name = st.text_input("Form name", placeholder="e.g. Course Feedback")
            new_url = st.text_input("Google Sheet URL",
                                    placeholder="https://docs.google.com/spreadsheets/d/…")
            if st.button("Save form", use_container_width=True):
                if new_name and new_url and "docs.google.com/spreadsheets" in new_url:
                    forms[new_name] = new_url
                    save_forms(forms)
                    st.success(f"Added '{new_name}'")
                    st.rerun()
                elif new_name and new_url:
                    st.warning("Paste the linked Google Sheets URL, not the Google Form URL.")
                else:
                    st.warning("Enter both a name and a URL.")

        if forms:
            with st.expander("🗑️ Remove a form"):
                to_remove = st.selectbox("Form to remove", list(forms.keys()), key="rm")
                if st.button("Remove", use_container_width=True):
                    forms.pop(to_remove, None)
                    save_forms(forms)
                    st.rerun()

        st.markdown("---")
        with st.expander("Setup guide (one-time)"):
            st.markdown("""
<div class="step"><b>No API key needed.</b> This app uses Google OAuth, so you log in with your Google account.</div>
<div class="step">1. Go to <b>console.cloud.google.com</b> → create a project</div>
<div class="step">2. APIs & Services → Library → Enable <b>Google Sheets API</b> and <b>Google Drive API</b></div>
<div class="step">3. APIs & Services → OAuth consent screen → External → fill app name + your email → add yourself under <b>Test users</b></div>
<div class="step">4. Credentials → Create credentials → <b>OAuth client ID</b> → type <b>Desktop app</b></div>
<div class="step">5. Download the JSON and upload it above as the Google login setup file</div>
<div class="step">6. Click <b>Log in with Google</b> above → your forms import automatically</div>
<div class="step">7. For each form, link responses to a Sheet if needed: Google Form → Responses → Sheets icon</div>
<div class="step">8. Use <b>Sync forms from Google</b> anytime to pick up new forms ✓</div>
""", unsafe_allow_html=True)

    else:
        uploaded_csvs = st.file_uploader("Upload CSV file(s)", type=["csv"],
                                         accept_multiple_files=True)
        selected_csv = None
        if uploaded_csvs:
            names = [f.name for f in uploaded_csvs]
            chosen = st.selectbox("Select file", names)
            selected_csv = next(f for f in uploaded_csvs if f.name == chosen)

# ── header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="app-header">
  <h1>📊 Survey Analytics Dashboard</h1>
  <p>Live Google Forms data · Interactive charts · Optional auto-refresh in the sidebar</p>
</div>
""", unsafe_allow_html=True)

# ── main ──────────────────────────────────────────────────────────────────────

if source == "Google Forms (Live)":
    if not os.path.exists(CLIENT_SECRET_FILE):
        st.warning("Google login is not configured yet.")
        st.write("Add the Google login setup file in the sidebar once. After that, this app uses **Log in with Google** with no API key or pasted code.")
    elif not is_connected():
        st.info("Click **Log in with Google** in the sidebar. Your forms will load automatically after sign-in.")
        if st.button("Log in with Google", type="primary"):
            try:
                with st.spinner("Signing in and loading your Google Forms…"):
                    found, skipped = run_google_login_and_sync()
                st.success(f"Logged in! Found {found} form(s) with linked response sheets.")
                if skipped:
                    st.info("Some forms were skipped:\n\n" + "\n".join(f"- {s}" for s in skipped))
                st.rerun()
            except Exception as e:
                st.error(f"Google sign-in failed: {e}")
    elif credentials_need_reconsent():
        st.warning("Log out and sign in again to refresh your Google login, then sync your forms.")
    elif not forms:
        st.info(
            "No Google Forms with linked response sheets were found. "
            "In each form, open **Responses → Link to Sheets**, then click **Sync forms from Google** in the sidebar."
        )
        if st.button("Sync forms from Google", type="primary"):
            try:
                with st.spinner("Loading forms from your Google account…"):
                    found, skipped = sync_forms_from_google()
                if found:
                    st.success(f"Found {found} form(s).")
                    st.rerun()
                else:
                    st.warning("Still no forms with linked response sheets.")
                    if skipped:
                        st.info("\n".join(f"- {s}" for s in skipped))
            except ReconsentRequired as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Could not sync forms: {e}")
    else:
        @st.fragment(run_every=refresh_secs)
        def live_forms():
            if view_mode == "Compare all":
                st.subheader("Comparing all forms")
                interval_note = ""
                if auto_on and refresh_secs:
                    interval_note = f" · auto-refresh every {refresh_secs}s"
                st.caption(f"Last updated {datetime.now().strftime('%H:%M:%S')}{interval_note}")
                summary_rows = []
                loaded_forms = []
                for name, url in forms.items():
                    try:
                        df = fetch_sheet(url)
                        loaded_forms.append((name, df))
                        summary_rows.append({"Form": name, "Responses": len(df),
                                             "Questions": df.shape[1], "Status": "✓ connected"})
                    except Exception as e:
                        summary_rows.append({"Form": name, "Responses": "—",
                                             "Questions": "—", "Status": f"✗ {e}"})
                summary_df = pd.DataFrame(summary_rows)

                # cross-form comparison chart: responses per form
                if loaded_forms:
                    comp = pd.DataFrame({"Form": [n for n, _ in loaded_forms],
                                         "Responses": [len(d) for _, d in loaded_forms]})
                    comp = comp.sort_values("Responses", ascending=True)
                    fig = px.bar(comp, x="Responses", y="Form", orientation="h",
                                 text="Responses", color="Form",
                                 color_discrete_sequence=COLOR_SEQ)
                    fig.update_layout(
                        title=dict(text="<b>Responses by form</b>",
                                   font=dict(size=14, color="#2d3748"), x=0),
                        showlegend=False, height=max(180, 60 * len(comp)),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#fafafa",
                        margin=dict(t=44, b=16, l=16, r=16),
                    )
                    st.plotly_chart(fig, width="stretch")

                st.dataframe(summary_df, width="stretch")
                st.download_button(
                    "Download comparison summary CSV",
                    data=csv_download(summary_df),
                    file_name="survey_comparison_summary.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
                st.markdown("---")
                for name, df in loaded_forms:
                    st.markdown(f"### {name}")
                    render_dashboard(df, key_prefix=f"compare_{name}")
                    st.markdown("---")
            else:
                try:
                    with st.spinner("Fetching latest responses…"):
                        df = fetch_sheet(forms[selected_form])
                    interval_note = ""
                    if auto_on and refresh_secs:
                        interval_note = f" · auto-refresh every {refresh_secs}s"
                    st.caption(f"**{selected_form}** · {len(df)} responses · "
                               f"last updated {datetime.now().strftime('%H:%M:%S')}{interval_note}")
                    render_dashboard(df, key_prefix=f"live_{selected_form}")
                except Exception as e:
                    st.error(f"Could not connect: {e}")
                    st.info("Make sure you're logged in and the Sheet belongs to your account.")

        live_forms()

else:
    if selected_csv is None:
        st.info("Upload one or more CSV files in the sidebar to get started.")
    else:
        df = pd.read_csv(selected_csv)
        st.caption(f"**{selected_csv.name}** · {len(df)} responses")
        render_dashboard(df, key_prefix=f"csv_{selected_csv.name}")
