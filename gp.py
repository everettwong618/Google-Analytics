import sys
import os
import pandas as pd
import plotly.express as px

COLOR_SEQ = px.colors.qualitative.Set2


def load_csv(path):
    return pd.read_csv(path)


def classify_column(series):
    name_lower = series.name.lower()
    if "timestamp" in name_lower:
        return "timestamp"

    n_total = series.count()
    if n_total == 0:
        return "empty"

    n_unique = series.nunique()
    numeric = pd.to_numeric(series, errors="coerce")
    n_numeric = numeric.notna().sum()

    if n_numeric / n_total >= 0.8:
        if n_unique <= 10 and numeric.min() >= 1 and numeric.max() <= 10:
            return "scale"
        return "numeric"

    if n_unique <= 20 and n_unique / n_total < 0.6:
        return "categorical"

    return "text"


def print_summary(df, types):
    total = len(df)
    questions = sum(1 for t in types.values() if t not in ("timestamp", "empty"))
    print(f"\n{'='*62}")
    print(f"  SURVEY REPORT  |  {total} responses  |  {questions} questions")
    print(f"{'='*62}")

    for col, ctype in types.items():
        if ctype in ("timestamp", "empty"):
            continue

        n_answered = df[col].notna().sum()
        pct = n_answered / total * 100
        print(f"\n  {col[:72]}")
        print(f"  [{ctype}]  answered: {n_answered}/{total} ({pct:.0f}%)")

        if ctype in ("scale", "numeric"):
            num = pd.to_numeric(df[col], errors="coerce")
            print(f"  avg {num.mean():.2f}  |  median {num.median():.1f}  |  std {num.std():.2f}")

        elif ctype == "categorical":
            for val, cnt in df[col].value_counts().items():
                bar = "#" * int(cnt / total * 30)
                print(f"  {str(val)[:38]:<38} {cnt:>4} ({cnt/total*100:>4.1f}%) {bar}")

        elif ctype == "text":
            sample = df[col].dropna().iloc[0] if n_answered > 0 else ""
            print(f"  open text — sample: \"{str(sample)[:70]}\"")


def build_report(df, types, output_path):
    figures = []

    for col, ctype in types.items():
        if ctype in ("timestamp", "empty", "text"):
            continue

        if ctype == "categorical":
            counts = df[col].value_counts().reset_index()
            counts.columns = ["Response", "Count"]

            if len(counts) <= 5:
                fig = px.pie(
                    counts, names="Response", values="Count",
                    title=col, hole=0.3,
                    color_discrete_sequence=COLOR_SEQ,
                )
                fig.update_traces(textposition="inside", textinfo="percent+label")
            else:
                counts = counts.sort_values("Count")
                fig = px.bar(
                    counts, x="Count", y="Response", orientation="h",
                    title=col, text="Count",
                    color="Response", color_discrete_sequence=COLOR_SEQ,
                )
                fig.update_layout(showlegend=False)

            figures.append(fig)

        elif ctype == "scale":
            num = pd.to_numeric(df[col], errors="coerce").dropna()
            counts = num.value_counts().sort_index().reset_index()
            counts.columns = ["Rating", "Count"]
            fig = px.bar(
                counts, x="Rating", y="Count", title=col,
                text="Count", color_discrete_sequence=["#636efa"],
            )
            avg = num.mean()
            fig.add_vline(
                x=avg, line_dash="dash", line_color="red",
                annotation_text=f"avg {avg:.1f}", annotation_position="top right",
            )
            fig.update_layout(showlegend=False)
            figures.append(fig)

        elif ctype == "numeric":
            num = pd.to_numeric(df[col], errors="coerce").dropna()
            fig = px.histogram(
                num, title=col, nbins=20,
                labels={"value": col},
                color_discrete_sequence=["#636efa"],
            )
            fig.update_layout(showlegend=False)
            figures.append(fig)

    if not figures:
        print("No plottable columns detected.")
        return

    html = _render_html(figures, len(df))
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nReport saved: {output_path}")


def _render_html(figures, n_responses):
    cards = []
    for i, fig in enumerate(figures):
        fig.update_layout(margin=dict(t=50, b=20, l=20, r=20))
        include_js = "cdn" if i == 0 else False
        cards.append(fig.to_html(full_html=False, include_plotlyjs=include_js))

    grid = "\n".join(f'<div class="card">{c}</div>' for c in cards)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Survey Report</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f0f2f5; padding: 24px; color: #1a1a2e; }}
  header {{ text-align: center; margin-bottom: 28px; }}
  header h1 {{ font-size: 1.8rem; color: #2c3e50; }}
  header p {{ color: #777; margin-top: 6px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
           gap: 20px; max-width: 1400px; margin: 0 auto; }}
  .card {{ background: #fff; border-radius: 12px; padding: 16px;
           box-shadow: 0 2px 10px rgba(0,0,0,0.07); }}
</style>
</head>
<body>
<header>
  <h1>Survey Analytics Report</h1>
  <p>{n_responses} responses</p>
</header>
<div class="grid">
{grid}
</div>
</body>
</html>"""


def main():
    if len(sys.argv) < 2:
        print("Usage: python gp.py <survey.csv>")
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)

    print(f"Loading {path} ...")
    df = load_csv(path)
    types = {col: classify_column(df[col]) for col in df.columns}

    print_summary(df, types)
    out = os.path.splitext(path)[0] + "_report.html"
    build_report(df, types, out)


if __name__ == "__main__":
    main()
