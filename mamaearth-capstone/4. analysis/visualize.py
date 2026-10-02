"""
Part 2 / Task 11 - Two visualizations (Matplotlib)

Run from the repo root, AFTER analysis/clean_and_eda.py:
    python analysis/visualize.py

It rebuilds the numbers from the raw CSVs (same cleaning rules as clean_and_eda.py), cross-checks
them against narrator/findings.json so the charts can never drift from the analysis, and saves:
    visualizations/return_rate_by_payment.png
    visualizations/monthly_revenue_trend.png
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # no display needed - works on any machine / server
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "visualizations"
OUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------- rebuild cleaned data
orders = pd.read_csv(DATA / "orders.csv")
products = pd.read_csv(DATA / "products.csv")
customers = pd.read_csv(DATA / "customers.csv")

orders["payment_method"] = orders["payment_method"].str.strip().str.upper()
dup_key = ["customer_id", "product_id", "order_date", "quantity",
           "discount_pct", "payment_method", "rating", "returned"]
orders = orders[~orders.duplicated(subset=dup_key, keep="first")].copy()
orders["discount_pct"] = orders["discount_pct"].fillna(0)
orders["rating"] = orders["rating"].fillna(orders["rating"].median())

df = orders.merge(products, on="product_id").merge(customers, on="customer_id")
df["order_value"] = df["quantity"] * df["price"] * (1 - df["discount_pct"] / 100)

q1, q3 = df["quantity"].quantile(0.25), df["quantity"].quantile(0.75)
iqr = q3 - q1
df["is_outlier"] = (df["quantity"] < q1 - 1.5 * iqr) | (df["quantity"] > q3 + 1.5 * iqr)

df["year_month"] = pd.to_datetime(df["order_date"]).dt.to_period("M").astype(str)

# ---------------------------------------------------------------- numbers for the charts
return_rate = (df.groupby("payment_method")["returned"].mean() * 100).round(1).sort_values(ascending=False)
monthly = df[~df["is_outlier"]].groupby("year_month")["order_value"].sum().round(2)  # outlier-corrected
peak_month = monthly.idxmax()

# ---------------------------------------------------------------- consistency check vs Part 2 export
findings = json.loads((ROOT / "narrator" / "findings.json").read_text(encoding="utf-8"))
assert findings["true_peak_month"]["month"] == peak_month, "visualize.py disagrees with findings.json (peak month)"
for k, v in findings["return_rate_by_payment"].items():
    assert abs(return_rate[k] - v) < 0.05, f"visualize.py disagrees with findings.json ({k} return rate)"

# ---------------------------------------------------------------- Chart 1: return rate by payment
fig, ax = plt.subplots(figsize=(8, 5.5))
colors = ["#B5452F" if m == return_rate.index[0] else "#7FA895" for m in return_rate.index]
bars = ax.bar(return_rate.index, return_rate.values, color=colors, width=0.55)
for bar, val in zip(bars, return_rate.values):
    ax.text(bar.get_x() + bar.get_width() / 2, val + 0.8, f"{val:.1f}%",
            ha="center", va="bottom", fontsize=12, fontweight="bold")

top_name, top_val = return_rate.index[0], return_rate.iloc[0]
multiple = round(top_val / return_rate["CARD"])
ax.set_title(f"{top_name} Returns at {top_val:.1f}% \u2014 {multiple}x Card", fontsize=15, fontweight="bold", pad=14)
ax.set_xlabel("Payment method")
ax.set_ylabel("Return rate (%)")
ax.set_ylim(0, top_val * 1.2)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "return_rate_by_payment.png", dpi=150)
plt.close(fig)

# ---------------------------------------------------------------- Chart 2: monthly revenue (corrected)
month_labels = pd.to_datetime(monthly.index + "-01").strftime("%b %Y")
peak_label = pd.to_datetime(peak_month + "-01").strftime("%B %Y")

fig, ax = plt.subplots(figsize=(9, 5.5))
ax.plot(month_labels, monthly.values, marker="o", linewidth=2.5, color="#2E6B4F")
ax.scatter([pd.to_datetime(peak_month + "-01").strftime("%b %Y")], [monthly[peak_month]],
           s=140, color="#E3A33B", zorder=5)
ax.annotate(f"Peak: \u20b9{monthly[peak_month]:,.2f}", xy=(list(monthly.index).index(peak_month), monthly[peak_month]),
            xytext=(0, 14), textcoords="offset points", ha="center", fontweight="bold")
ax.set_title(f"Outlier-Corrected Monthly Revenue \u2014 {peak_label} Is the True Peak", fontsize=14, fontweight="bold", pad=14)
ax.set_xlabel("Month")
ax.set_ylabel("Revenue (\u20b9)")
ax.set_ylim(0, monthly.max() * 1.18)
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
ax.grid(axis="y", alpha=0.3)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "monthly_revenue_trend.png", dpi=150)
plt.close(fig)

print("Saved:", (OUT / "return_rate_by_payment.png").relative_to(ROOT))
print("Saved:", (OUT / "monthly_revenue_trend.png").relative_to(ROOT))
