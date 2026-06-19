# Survey Analytics Dashboard — Full Project Backup

> Backup of all key instructions, decisions, and setup steps from the build conversation.
> Kept separate from `CLAUDE.md` as a safety copy. If `CLAUDE.md` is lost, this file
> has everything needed to understand, run, and finish the project.

---

## 1. What we set out to build

A data-analytics tool for **Google Forms survey responses** that:
- Pulls the data (from Google Forms, live, or via CSV export)
- Auto-categorizes each question and plots the right kind of graph
- Organizes everything into a clean, presentable dashboard for a **professor / boss**

### Decisions made along the way
- **Data type:** survey responses (Likert scales, multiple choice, open text).
- **Output:** started as console + interactive HTML (`gp.py`), then moved to a full
  **Streamlit web app** (`app.py`) for a clean interface to present.
- **Interface:** Streamlit dashboard (chosen over plain script / notebook).
- **Multiple forms:** must support several forms, switch via dropdown, or compare all.
- **Auth:** switched from a **service account + API key** approach to
  **"Sign in with Google" (OAuth)** — this is what the boss explicitly requested.

---

## 2. What the app does (current state)

- **Auto-detects the type of every survey question** and picks the right chart:
  | Detected type | Chart |
  |---|---|
  | `categorical` (≤5 options) | donut pie |
  | `categorical` (>5 options) | horizontal bar |
  | `scale` (numeric 1–10, few values) | bar chart + red average line |
  | `numeric` | histogram |
  | `text` (free response) | listed under charts, not plotted |
  | `timestamp` | ignored |
- **Metric cards:** total responses, # questions, average completion %, # open-text fields.
- **Three tabs:** Charts · Raw Data (searchable) · Statistics (mean/median/std, top response).
- **Multiple forms:** save several forms, switch with a dropdown, or "Compare all".
- **Two data sources** (toggle in sidebar):
  1. **Google Forms (Live)** — reads the form's linked Google Sheet via Sign in with Google; auto-refreshes every 60 s.
  2. **CSV Upload** — upload one or more CSV exports; pick which to view.

---

## 3. Files in this project

| File | Purpose |
|---|---|
| `app.py` | The whole Streamlit application (main program). |
| `gp.py` | Older standalone CLI version (CSV in → HTML report out). Optional/legacy. |
| `requirements.txt` | Python dependencies. |
| `launch.bat` | Double-click to start the app (Windows). |
| `forms.json` | Saved forms: `{ "Form name": "Google Sheet URL" }`. Created/edited via the sidebar. |
| `client_secret.json` | **Secret.** One-time Google login setup file (OAuth Desktop app). Do NOT share/commit. |
| `authorized_user.json` | **Secret.** Cached login token, created after first login. Do NOT share. |
| `sample_survey.csv`, `sample_event.csv` | Test data for CSV mode (course survey + event registration). |
| `CLAUDE.md` | Primary project doc. |
| `PROJECT_BACKUP.md` | This backup file. |

---

## 4. How to run

1. Install dependencies (one time):
   ```
   pip install -r requirements.txt
   ```
2. Start the app — either:
   - double-click **`launch.bat`**, or
   - run: `python -m streamlit run app.py`
3. Open **http://localhost:8501** in a browser.

**If the page says "connection refused":** the server isn't running — relaunch with the step above.
This happened a few times during the build because background processes stopped; the fix
is always to relaunch (launch.bat is the most reliable because it runs in its own window).

---

## 5. Authentication — "Sign in with Google" (OAuth)

The app logs in with **your own Google account** so it can read any Sheet you own,
with **no sharing of individual sheets** and **no API key to paste**.

### IMPORTANT honest note (came up repeatedly)
"Sign in with Google" still requires a **one-time OAuth client registration** in Google
Cloud. This is **Google's rule for every app** that shows a Google login screen — it is
**not** something the app can skip. It is a ~2-minute, one-time setup, separate from the
old service-account/sharing hassle. It must be created in **your own Google account**
(it can't be done on your behalf).

### One-time setup
1. **console.cloud.google.com** → create/pick a project.
2. **APIs & Services → Library** → enable **Google Sheets API** and **Google Drive API**.
3. **OAuth consent screen** → **External** → fill app name + your email →
   add your Google account under **Test users** → Save.
4. **Credentials → Create credentials → OAuth client ID → Application type: Desktop app**
   → Create → **Download JSON**.
5. In the app sidebar, upload that JSON in the **"Upload Google login setup JSON"** box.
   The app saves it locally as **`client_secret.json`**.
6. In the sidebar → **Log in with Google** → a browser opens → log in once.
   A token is cached in `authorized_user.json`.
7. For each Google Form: **Responses tab → green Sheets icon** to link a Google Sheet.
   (No sharing needed — it's your own account.)
8. In the sidebar **➕ Add a form**: give it a name + paste the **Sheet** URL.

### Desktop app vs Web app client (open question to confirm)
- **Runs on your own computer, you/boss view your own forms** → use **Desktop app** client (current setup).
- **Hosted website where many different people sign in with their own Google accounts**
  → needs a **Web app** OAuth client + hosted redirect URI + consent-screen verification
  (a larger change — revisit if that's the real goal).

---

## 6. Critical gotcha — Form URL vs Sheet URL

The app reads the **responses spreadsheet**, NOT the form itself.
- ✅ Use the Responses Sheet URL: `https://docs.google.com/spreadsheets/d/.../edit`
- ❌ Do NOT use the Form URL: `https://docs.google.com/forms/d/e/.../viewform`

To get the Sheet URL: open the Form → **Responses** tab → green **Sheets** icon →
the spreadsheet opens → copy its URL from the browser address bar.

---

## 7. Notes / gotchas

- In OAuth "testing" publishing status, the login token expires about every **7 days** —
  just click **Log in with Google** again to re-login.
- The dashboard auto-refreshes cached data every **60 seconds**; the **Refresh Data**
  button (sidebar) forces an immediate refresh.
- Charts look sparse until the form has several responses — that's expected with little data.
- **History note:** an earlier version used a **service account** (`credentials.json` +
  sharing each Sheet with a `...iam.gserviceaccount.com` email). That worked but was
  replaced by Sign in with Google per the boss's request. `credentials.json` was removed.

---

## 8. To-do / possible next steps

- [ ] Confirm Desktop vs Web OAuth client based on how it will actually be used.
- [ ] Add export buttons (download charts as PNG, summary as CSV/PDF).
- [ ] Cross-form comparison charts (not just stacked dashboards) in "Compare all".
- [ ] Date-range / response filtering.
- [ ] Publish the OAuth app to avoid the 7-day token expiry.
- [ ] Deploy to Streamlit Community Cloud so it runs without a local machine.

---

## 9. Security

`client_secret.json` and `authorized_user.json` grant access to your Google account —
keep them private. If this folder is ever put in git, add both (plus any `credentials.json`)
to `.gitignore`.
