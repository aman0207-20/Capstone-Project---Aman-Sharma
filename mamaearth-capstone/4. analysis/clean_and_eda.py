"""
Part 2 - Python/Pandas data wrangling & EDA  (Mamaearth Returns & Growth Intelligence Pipeline)

Run from the repo root:
    python analysis/clean_and_eda.py

Reads the RAW csv files in data/ (never edited by hand), prints every intermediate
result, and at the very end writes narrator/findings.json for Part 3.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FINDINGS_PATH = ROOT / "narrator" / "findings.json"

pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 30)


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def corr_band(r):
    """Taught correlation-strength bands: 0-0.19 / 0.2-0.39 / 0.4-0.69 / 0.7-1.0 (on |r|)."""
    a = abs(r)
    if a < 0.2:
        return "negligible"
    if a < 0.4:
        return "weak"
    if a < 0.7:
        return "moderate"
    return "strong"


# ---------------------------------------------------------------------------
# Task 1 - Load and inspect
# ---------------------------------------------------------------------------
section("TASK 1 - Load and inspect")
customers = pd.read_csv(DATA / "customers.csv")
products = pd.read_csv(DATA / "products.csv")
orders = pd.read_csv(DATA / "orders.csv")

print("customers.shape:", customers.shape)
print("products.shape :", products.shape)
print("orders.shape   :", orders.shape)  # expected (180, 9)
print("\nMissing values in raw orders:")
print(orders.isnull().sum())

# ---------------------------------------------------------------------------
# Task 2 - Standardize payment_method casing
# ---------------------------------------------------------------------------
section("TASK 2 - Standardize payment_method casing")
print("Raw unique values:", list(orders["payment_method"].unique()))
print("Number of raw distinct values:", orders["payment_method"].nunique())  # expected 7

orders["payment_method"] = orders["payment_method"].str.strip().str.upper()

print("\nAfter .str.strip().str.upper():", list(orders["payment_method"].unique()))
print("Number of distinct values:", orders["payment_method"].nunique())  # expected 3
print(orders["payment_method"].value_counts())  # CARD 70, UPI 55, COD 55

# ---------------------------------------------------------------------------
# Task 3 - Remove duplicate orders
# ---------------------------------------------------------------------------
section("TASK 3 - Remove duplicate orders")
dup_key = ["customer_id", "product_id", "order_date", "quantity",
           "discount_pct", "payment_method", "rating", "returned"]  # everything except order_id
dup_mask = orders.duplicated(subset=dup_key, keep="first")
dropped = orders[dup_mask].copy()  # kept for the Task 5 reconciliation
print("Duplicate rows flagged:", int(dup_mask.sum()))  # expected 5
print("Dropped order_ids     :", dropped["order_id"].tolist())  # O0176..O0180

orders_clean = orders[~dup_mask].copy().reset_index(drop=True)
print("orders_clean.shape    :", orders_clean.shape)  # expected (175, 9)

# ---------------------------------------------------------------------------
# Task 4 - Impute missing values (on the de-duplicated frame)
# ---------------------------------------------------------------------------
section("TASK 4 - Impute missing values")
disc_missing = int(orders_clean["discount_pct"].isnull().sum())
print("discount_pct missing rows:", disc_missing)  # expected 12
orders_clean["discount_pct"] = orders_clean["discount_pct"].fillna(0)  # rule: no promo code applied

rating_missing = int(orders_clean["rating"].isnull().sum())
rating_median = orders_clean["rating"].median()  # median of non-null ratings
print("rating median (before imputing):", rating_median)  # expected 3.0
print("rating missing rows:", rating_missing)  # expected 15
orders_clean["rating"] = orders_clean["rating"].fillna(rating_median)

print("\nNulls after imputation:")
print(orders_clean[["discount_pct", "rating"]].isnull().sum().to_dict())  # both 0

# ---------------------------------------------------------------------------
# Task 5 - Merge and reconcile against Part 1
# ---------------------------------------------------------------------------
section("TASK 5 - Merge and reconcile against Part 1")
df = (orders_clean
      .merge(products, on="product_id", how="left")
      .merge(customers, on="customer_id", how="left"))
df["order_value"] = df["quantity"] * df["price"] * (1 - df["discount_pct"] / 100)

cleaned_total = round(df["order_value"].sum(), 2)
print("Merged frame shape:", df.shape)
print(f"Cleaned total revenue (175 rows): {cleaned_total:,.2f}")  # expected 97,358.30

# Independent check: order_value of the 5 dropped duplicates
dropped_m = dropped.merge(products, on="product_id", how="left")
dropped_m["discount_pct"] = dropped_m["discount_pct"].fillna(0)
dropped_m["order_value"] = dropped_m["quantity"] * dropped_m["price"] * (1 - dropped_m["discount_pct"] / 100)
dup_value = round(dropped_m["order_value"].sum(), 2)
print("\nOrder value of the 5 dropped duplicate rows:")
print(dropped_m[["order_id", "quantity", "price", "discount_pct", "order_value"]].to_string(index=False))
print(f"Sum of dropped-row order_value: {dup_value:,.2f}")  # expected 2,501.90

# Raw total (what SQL Report (a) sees: all 180 rows, NULL discount treated as 0)
raw_m = (orders.merge(products, on="product_id", how="left"))
raw_m["order_value"] = raw_m["quantity"] * raw_m["price"] * (1 - raw_m["discount_pct"].fillna(0) / 100)
raw_total = round(raw_m["order_value"].sum(), 2)
delta = round(raw_total - cleaned_total, 2)
print(f"\nRaw total (SQL Report a, 180 rows): {raw_total:,.2f}")
print(f"Delta (raw - cleaned)             : {delta:,.2f}")
assert abs(delta - dup_value) < 0.005, "Delta must equal the duplicates' order_value"

print(
    "\nRECONCILIATION NOTE:\n"
    f"Part 1 Report (a) shows a raw revenue of Rs {raw_total:,.2f} across 180 orders, while this pipeline's cleaned "
    f"revenue is Rs {cleaned_total:,.2f} across 175 orders. The gap of Rs {delta:,.2f} is fully explained by the 5 "
    f"duplicate (double-submit) orders O0176-O0180 removed in Task 3: their combined order_value, summed "
    f"independently, is exactly Rs {dup_value:,.2f}. It is NOT caused by imputing discount_pct or rating - filling "
    "missing discounts with 0 matches how SQL already treated them (COALESCE), and ratings do not enter "
    "order_value at all, so imputation changes no revenue total."
)

# ---------------------------------------------------------------------------
# Task 6 - IQR outlier detection on quantity
# ---------------------------------------------------------------------------
section("TASK 6 - IQR outlier detection on quantity")
q1 = df["quantity"].quantile(0.25)
q3 = df["quantity"].quantile(0.75)
iqr = q3 - q1
lower = q1 - 1.5 * iqr
upper = q3 + 1.5 * iqr
print(f"Q1 = {q1}, Q3 = {q3}, IQR = {iqr}, lower = {lower}, upper = {upper}")

df["is_outlier"] = (df["quantity"] < lower) | (df["quantity"] > upper)  # flagged, NOT dropped
outliers = df[df["is_outlier"]]
print(f"Outlier rows: {len(outliers)}")  # expected 2
print(outliers[["order_id", "order_date", "quantity", "order_value"]].to_string(index=False))
print("Rows are flagged (is_outlier) and kept in the dataset.")

# ---------------------------------------------------------------------------
# Task 7 - Hypothesis: does COD have a higher return rate?
# ---------------------------------------------------------------------------
section("TASK 7 - Hypothesis: COD has a higher return rate than Card/UPI")
print("HYPOTHESIS: Cash-on-Delivery (COD) orders have a higher return rate than Card or UPI orders.")
pay = df.groupby("payment_method")["returned"].agg(["count", "mean"])
pay["return_rate_pct"] = (pay["mean"] * 100).round(1)
print(pay)
cod_highest = pay["return_rate_pct"].idxmax() == "COD"
print(f"\nRESULT: {'CONFIRMED' if cod_highest else 'REJECTED'} -> "
      f"COD {pay.loc['COD', 'return_rate_pct']}% vs CARD {pay.loc['CARD', 'return_rate_pct']}% "
      f"vs UPI {pay.loc['UPI', 'return_rate_pct']}%")
print("Hypothesis status: Confirmed" if cod_highest else "Hypothesis status: Rejected")

# ---------------------------------------------------------------------------
# Task 8 - Multi-level segmentation
# ---------------------------------------------------------------------------
section("TASK 8 - Multi-level segmentation (payment_method x city_tier)")
seg = df.groupby(["payment_method", "city_tier"])["returned"].agg(["count", "mean"])
seg["return_rate_pct"] = (seg["mean"] * 100).round(1)
print(seg)
top_idx = seg["return_rate_pct"].idxmax()
top = seg.loc[top_idx]
print(f"\nHIGHEST-RISK SEGMENT: {top_idx[0]} + Tier-{top_idx[1]} cities -> "
      f"{top['return_rate_pct']}% return rate ({int(top['count'])} orders)")
cod_t1 = seg.loc[("COD", 1)]
cod_t2 = seg.loc[("COD", 2)]
print(f"COD risk is not uniform: Tier-1 COD = {int(cod_t1['count'])} orders at {cod_t1['return_rate_pct']}%, "
      f"Tier-2 COD = {int(cod_t2['count'])} orders at {cod_t2['return_rate_pct']}%. "
      "A single blended COD rate hides where the problem is concentrated.")

# ---------------------------------------------------------------------------
# Task 9 - Correlation analysis
# ---------------------------------------------------------------------------
section("TASK 9 - Correlation analysis")
cols = ["rating", "returned", "discount_pct", "quantity"]
corr = df[cols].corr()
print(corr.round(3))
print("\nPairwise strength (bands: <0.2 negligible, 0.2-0.39 weak, 0.4-0.69 moderate, >=0.7 strong):")
for i in range(len(cols)):
    for j in range(i + 1, len(cols)):
        r = corr.iloc[i, j]
        print(f"  {cols[i]:>13} vs {cols[j]:<13} r = {r:+.3f}  -> {corr_band(r)}")
r_disc_ret = corr.loc["discount_pct", "returned"]
# Busted = the data does not support the claim (relationship is negligible, |r| < 0.2)
verdict = "Busted" if abs(r_disc_ret) < 0.2 else "Confirmed"
print(f"\nHYPOTHESIS 'higher discounts reduce returns': discount_pct vs returned r = {r_disc_ret:+.3f} "
      f"({corr_band(r_disc_ret)}) -> {verdict}")

# ---------------------------------------------------------------------------
# Task 10 - Outlier-corrected time series
# ---------------------------------------------------------------------------
section("TASK 10 - Outlier-corrected monthly revenue")
df["order_date"] = pd.to_datetime(df["order_date"])
df["year_month"] = df["order_date"].dt.to_period("M").astype(str)

monthly_with = df.groupby("year_month")["order_value"].sum().round(2)
monthly_without = df[~df["is_outlier"]].groupby("year_month")["order_value"].sum().round(2)

print("(1) Monthly revenue INCLUDING the 2 outlier orders:")
print(monthly_with.map("{:,.2f}".format).to_string())
print("\n(2) Monthly revenue EXCLUDING the 2 outlier orders (outlier-corrected):")
print(monthly_without.map("{:,.2f}".format).to_string())

apparent_peak = monthly_with.idxmax()
true_peak = monthly_without.idxmax()
print(f"\nWith outliers the highest month looks like {apparent_peak} ({monthly_with[apparent_peak]:,.2f}).")
print(f"INSIGHT: January's apparent lead is an artifact of the two bulk orders landing in January "
      f"(O0011 on 2026-01-28 with quantity 25, O0098 on 2026-01-10 with quantity 30). Excluding them, January "
      f"drops from {monthly_with['2026-01']:,.2f} to {monthly_without['2026-01']:,.2f}, and "
      f"{true_peak} ({monthly_without[true_peak]:,.2f}) is the genuine peak month (March).")

# ---------------------------------------------------------------------------
# Export for Part 3 - narrator/findings.json  (never hand-typed)
# ---------------------------------------------------------------------------
section("EXPORT - narrator/findings.json")
rr = pay["return_rate_pct"]
findings = {
    "cleaned_total_revenue_inr": float(cleaned_total),
    "raw_total_revenue_inr": float(raw_total),
    "duplicate_reconciliation_delta_inr": float(delta),
    "return_rate_by_payment": {"COD": float(rr["COD"]), "CARD": float(rr["CARD"]), "UPI": float(rr["UPI"])},
    "highest_risk_segment": {
        "payment_method": str(top_idx[0]),
        "city_tier": int(top_idx[1]),
        "return_rate_pct": float(top["return_rate_pct"]),
    },
    "true_peak_month": {"month": str(true_peak), "revenue_inr": float(monthly_without[true_peak])},
    "outlier_inflated_month": {
        "month": str(apparent_peak),
        "apparent_revenue_inr": float(monthly_with[apparent_peak]),
        "corrected_revenue_inr": float(monthly_without[apparent_peak]),
    },
}
FINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
FINDINGS_PATH.write_text(json.dumps(findings, indent=2), encoding="utf-8")
print(json.dumps(findings, indent=2))
print(f"\nWrote {FINDINGS_PATH.relative_to(ROOT)}")
