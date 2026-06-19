# Survey Analytics Dashboard

A Streamlit web app that pulls Google Forms responses (live or via CSV) and turns
them into an interactive dashboard — charts, summary statistics, and a searchable
data table. Built to be presentable to a professor / boss.

---

## What it does

- **Auto-detects the type of every survey question** and picks the right chart:
  | Detected type | Chart |
  |---|---|
  | `categorical` (≤5 options) | donut pie |
  | `categorical` (>5 options) | horizontal bar |
  | `scale` (numeric 1–10, few values) | bar chart + red average line |
  | `numeric` | histogram |
  | `text` (free response) | listed under charts, not plotted |
  | `timestamp` | ignored |
- **Metric cards**: total responses, # questions, average completion %, # open-text fields.
- **Three tabs**: Charts · Raw Data (searchable) · Statistics (mean/median/std, top response).
- **Multiple forms**: save several forms, switch with a dropdown, or "Compare all".
- **Two data sources** (toggle in sidebar):
  1. **Google Forms (Live)** — pulls from the form's linked Google Sheet, auto-refreshes every 60 s.
  2. **CSV Upload** — upload one or more CSV exports; pick which to view.

---

## Files

| File | Purpose |
|---|---|
| `app.py` | The whole Streamlit application. |
| `gp.py` | Older standalone CLI version (CSV in → HTML report out). Optional/legacy. |
| `requirements.txt` | Python dependencies. |
| `launch.bat` | Double-click to start the app (Windows). |
| `forms.json` | Saved forms: `{ "Form name": "Google Sheet URL" }`. Created/edited via the sidebar. |
| `client_secret.json` | **Secret.** One-time Google login setup file (OAuth Desktop app). Do NOT share or commit. |
| `authorized_user.json` | **Secret.** Cached login token, created after first connect. Do NOT share. |
| `sample_survey.csv`, `sample_event.csv` | Test data for CSV mode. |

---

## How to run

1. Install dependencies (one time):
   ```
   pip install -r requirements.txt
   ```
2. Start the app — either:
   - double-click **`launch.bat`**, or
   - run: `python -m streamlit run app.py`
3. Open **http://localhost:8501** in a browser.

If the page says "connection refused", the server isn't running — relaunch with the step above.

---

## Authentication (Google Forms Live mode) — OAuth "log in with Google"

The app logs in with **your own Google account**, so you can read any Sheet you own
without sharing it. One-time setup:

This is **not** an API-key setup. Google still requires a one-time OAuth Desktop
client JSON file so this local app is allowed to show a Google login screen, but
after that you use the **Log in with Google** button and sign in through the browser.

1. **console.cloud.google.com** → create a project.
2. **APIs & Services → Library** → enable **Google Sheets API** and **Google Drive API**.
3. **OAuth consent screen** → External → fill in app name + your email →
   add your own Google account under **Test users**.
4. **Credentials → Create credentials → OAuth client ID → type "Desktop app"** → download JSON.
5. Upload the downloaded JSON in the app sidebar as the Google login setup file.
   The app saves it locally as **`client_secret.json`**.
6. In the app sidebar → **Log in with Google** → a browser opens → log in once.
   A token is cached in `authorized_user.json`.
7. For each Google Form: **Responses tab → green Sheets icon** to link a Google Sheet.
   (No sharing needed — it's your own account.)
8. In the sidebar **➕ Add a form**: give it a name + paste the **Sheet** URL
   (must be a `spreadsheets` URL, NOT a `forms` URL).

### Important URL distinction
- ✅ Responses Sheet (use this): `https://docs.google.com/spreadsheets/d/.../edit`
- ❌ Form itself (do NOT use):   `https://docs.google.com/forms/d/e/.../viewform`

### Notes / gotchas
- In OAuth "testing" publishing status, the login token expires about every **7 days** —
  just click **Log in with Google** again to re-login.
- The dashboard auto-refreshes cached data every **60 seconds**; the **Refresh Data**
  button forces an immediate refresh.

---

## To-do / possible next steps

- [ ] Add export buttons (download charts as PNG, summary as CSV/PDF).
- [ ] Cross-form comparison charts (not just stacked dashboards) in "Compare all".
- [ ] Date-range / response filtering.
- [ ] Publish the OAuth app (or use a service account) to avoid the 7-day token expiry.
- [ ] Deploy to Streamlit Community Cloud so it runs without a local machine.

---

## Security

`client_secret.json` and `authorized_user.json` grant access to your Google account —
keep them private. If this folder is ever put in git, add both (plus `credentials.json`)
to `.gitignore`.
