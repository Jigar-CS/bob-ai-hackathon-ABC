"""
Retrain all PortPulse ML models on a large synthetic dataset.

Generates 15,000 realistic port-operations training samples using domain-
knowledge-based distributions (not pure random), then trains and evaluates
5 models:

  1. risk_model            — RandomForestClassifier (congestion risk: LOW/MEDIUM/HIGH)
  2. wait_model            — GradientBoostingRegressor (vessel wait hours)
  3. demurrage_model       — GradientBoostingRegressor (demurrage cost USD)
  4. crane_productivity_model — RandomForestRegressor (moves per hour)
  5. anomaly_model         — IsolationForest (outlier/anomaly detection)
  + risk_label_encoder     — LabelEncoder for risk classes

All models are saved to src/portpulse/ml/ as .pkl files (overwriting existing).
Run from the project root:
    python scripts/train_models.py
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

# ── Ensure project src is importable ─────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
MODEL_DIR = PROJECT_ROOT / "src" / "portpulse" / "ml"

warnings.filterwarnings("ignore", category=UserWarning)

import numpy as np
import pandas as pd

# ── Seed for reproducibility ──────────────────────────────────────────────────
RNG = np.random.default_rng(seed=42)
N = 15_000  # training samples

print(f"[1/7]  Generating {N:,} synthetic training samples …")

# ─────────────────────────────────────────────────────────────────────────────
# Feature generation — realistic port-operations distributions
# ─────────────────────────────────────────────────────────────────────────────

# Number of berths (3–12) and vessels in queue (1–30)
n_berths  = RNG.integers(3, 13, size=N)
n_vessels = RNG.integers(1, 31, size=N)

# Vessel size distribution: bimodal (feeder ~2k TEU, large ~10k TEU)
feeder_mask = RNG.random(N) < 0.45
size_teu = np.where(
    feeder_mask,
    RNG.integers(1000, 7000, size=N),      # feeder / small
    RNG.integers(7000, 24001, size=N),     # large / ULCV
)

# Priority: P1 ~30%, P2 ~45%, P3 ~25%
priority = RNG.choice([1, 2, 3], size=N, p=[0.30, 0.45, 0.25])

# Crane count per berth (1–8), correlated with berth capacity class
crane_count = RNG.integers(1, 9, size=N)

# Berth capacity: roughly 1.3–2× the largest vessel that could fit
berth_capacity_teu = np.clip(
    size_teu + RNG.integers(2000, 12000, size=N),
    5000, 28000
).astype(int)

# Cargo type: 0=general, 1=reefer, 2=bulk, 3=hazmat
cargo_type = RNG.choice([0, 1, 2, 3], size=N, p=[0.55, 0.20, 0.15, 0.10])
cargo_type_hazmat = (cargo_type == 3).astype(int)

# ─────────────────────────────────────────────────────────────────────────────
# Derived targets with realistic domain relationships
# ─────────────────────────────────────────────────────────────────────────────

# --- Congestion / risk window features ---
# Each sample represents one 24-h forecast window
incoming_teu = n_vessels * (size_teu // RNG.integers(2, 6, size=N)).clip(500)
total_capacity_teu = n_berths * berth_capacity_teu
utilization_ratio = np.clip(incoming_teu / (total_capacity_teu + 1), 0.0, 1.5)
day_index = RNG.integers(1, 4, size=N)

risk_level_int = np.where(utilization_ratio > 0.80, 2, np.where(utilization_ratio > 0.50, 1, 0))
# 0=LOW, 1=MEDIUM, 2=HIGH
risk_labels = np.array(["LOW", "MEDIUM", "HIGH"])[risk_level_int]

# --- Wait time (hours) ---
# Key drivers: priority, n_vessels/n_berths ratio, size vs berth capacity
queue_pressure = np.clip(n_vessels / (n_berths + 0.5), 0, 8)
capacity_fit   = np.clip(size_teu / (berth_capacity_teu + 1), 0.05, 1.0)
crane_eff      = np.clip(4.0 / (crane_count + 0.1), 0.4, 4.0)  # fewer cranes → longer wait

# Priority factor: P1=0.4×, P2=1.0×, P3=1.8×
priority_mult = np.where(priority == 1, 0.40, np.where(priority == 2, 1.0, 1.80))

wait_hours = np.clip(
    queue_pressure * 1.8
    + capacity_fit * 3.0
    + crane_eff * 1.2
    + priority_mult * 2.5
    - n_berths * 0.4
    + RNG.normal(0, 0.8, size=N),   # operational noise
    0.0,
    36.0
)

# --- Effective dwell time (hours) ---
avg_dwell = RNG.uniform(12, 48, size=N)
crane_mult = np.clip(4.0 / (crane_count + 0.1), 0.5, 2.0)
effective_dwell = np.clip(avg_dwell * crane_mult + RNG.normal(0, 2, size=N), 4.0, 120.0)

# --- Demurrage cost (USD) ---
# $0.05–$0.25/TEU-hour; hazmat adds 40% surcharge; priority surcharge
base_rate = np.where(
    cargo_type_hazmat == 1,
    RNG.uniform(0.15, 0.35, size=N),
    RNG.uniform(0.04, 0.12, size=N),
)
p_surcharge = np.where(priority == 1, 1.3, np.where(priority == 2, 1.0, 0.85))
demurrage_cost = np.clip(
    wait_hours * size_teu * base_rate * p_surcharge
    + RNG.normal(0, 50, size=N),
    0.0,
    None,
)

# --- Crane productivity (moves/hour) ---
# Base ~25 moves/hr per crane; vessel size reduces throughput per crane
base_moves = 25.0
crane_prod = np.clip(
    crane_count * base_moves
    * np.clip(1.0 - size_teu / 60000, 0.4, 1.0)  # large vessels slower
    * np.where(cargo_type_hazmat == 1, 0.75, 1.0)  # hazmat -25%
    + RNG.normal(0, 5, size=N),
    5.0,
    250.0,
)

# --- Anomaly label: -1 anomaly, 1 normal (IsolationForest convention) ---
# Real anomalies: extreme dwell, extreme wait, very small vessels in large berths
_anomaly_score = (
    (wait_hours > 20).astype(float) * 3
    + (effective_dwell > 100).astype(float) * 2
    + ((berth_capacity_teu / (size_teu + 1)) > 4).astype(float) * 1.5
    + RNG.uniform(0, 1, size=N)
)
anomaly_label = np.where(_anomaly_score > 5.5, -1, 1)

print(f"         Risk distribution : LOW={np.sum(risk_level_int==0):,}  "
      f"MEDIUM={np.sum(risk_level_int==1):,}  HIGH={np.sum(risk_level_int==2):,}")
print(f"         Wait range        : {wait_hours.min():.1f}–{wait_hours.max():.1f} h  "
      f"mean={wait_hours.mean():.2f}h")
print(f"         Demurrage range   : ${demurrage_cost.min():.0f}–${demurrage_cost.max():.0f}  "
      f"mean=${demurrage_cost.mean():.0f}")
print(f"         Crane range       : {crane_prod.min():.0f}–{crane_prod.max():.0f} moves/hr")
print(f"         Anomalies         : {np.sum(anomaly_label==-1):,} / {N:,}")

# ─────────────────────────────────────────────────────────────────────────────
# Build DataFrames (keeps feature names for sklearn ≥ 1.0 validation)
# ─────────────────────────────────────────────────────────────────────────────

from sklearn.ensemble import (
    GradientBoostingRegressor,
    IsolationForest,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    mean_absolute_error,
    r2_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

import joblib

# ── 1. Congestion Risk Classifier ────────────────────────────────────────────
print("\n[2/7]  Training congestion risk classifier …")
X_risk = pd.DataFrame({
    "vessel_count":       n_vessels,
    "incoming_teu":       incoming_teu,
    "total_capacity_teu": total_capacity_teu,
    "day_index":          day_index,
    "utilization_ratio":  utilization_ratio.round(4),
})
y_risk = risk_labels

le = LabelEncoder()
y_risk_enc = le.fit_transform(y_risk)

X_r_train, X_r_test, y_r_train, y_r_test = train_test_split(
    X_risk, y_risk_enc, test_size=0.15, random_state=42, stratify=y_risk_enc
)

risk_model = RandomForestClassifier(
    n_estimators=300,
    max_depth=12,
    min_samples_leaf=5,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1,
)
risk_model.fit(X_r_train, y_r_train)
y_r_pred = risk_model.predict(X_r_test)
acc = accuracy_score(y_r_test, y_r_pred)
print(f"         Accuracy on hold-out: {acc:.3f}")
print(classification_report(y_r_test, y_r_pred, target_names=le.classes_, zero_division=0))

# ── 2. Wait-Time Regressor ────────────────────────────────────────────────────
print("[3/7]  Training wait-time regressor …")
X_wait = pd.DataFrame({
    "size_teu":          size_teu,
    "priority":          priority,
    "crane_count":       crane_count,
    "berth_capacity_teu": berth_capacity_teu,
    "n_berths":          n_berths,
    "n_vessels":         n_vessels,
})
y_wait = wait_hours

X_w_train, X_w_test, y_w_train, y_w_test = train_test_split(
    X_wait, y_wait, test_size=0.15, random_state=42
)
wait_model = GradientBoostingRegressor(
    n_estimators=400,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    random_state=42,
)
wait_model.fit(X_w_train, y_w_train)
y_w_pred = wait_model.predict(X_w_test)
print(f"         MAE : {mean_absolute_error(y_w_test, y_w_pred):.3f} h")
print(f"         R²  : {r2_score(y_w_test, y_w_pred):.3f}")

# ── 3. Demurrage Regressor ────────────────────────────────────────────────────
print("[4/7]  Training demurrage-cost regressor …")
X_dem = pd.DataFrame({
    "wait_hours":         wait_hours,
    "priority":           priority,
    "size_teu":           size_teu,
    "cargo_type_hazmat":  cargo_type_hazmat,
})
y_dem = demurrage_cost

X_d_train, X_d_test, y_d_train, y_d_test = train_test_split(
    X_dem, y_dem, test_size=0.15, random_state=42
)
demurrage_model = GradientBoostingRegressor(
    n_estimators=400,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    random_state=42,
)
demurrage_model.fit(X_d_train, y_d_train)
y_d_pred = demurrage_model.predict(X_d_test)
print(f"         MAE : ${mean_absolute_error(y_d_test, y_d_pred):.1f}")
print(f"         R²  : {r2_score(y_d_test, y_d_pred):.3f}")

# ── 4. Crane Productivity Regressor ──────────────────────────────────────────
print("[5/7]  Training crane-productivity regressor …")
X_crane = pd.DataFrame({
    "crane_count":        crane_count,
    "size_teu":           size_teu,
    "priority":           priority,
    "berth_capacity_teu": berth_capacity_teu,
})
y_crane = crane_prod

X_c_train, X_c_test, y_c_train, y_c_test = train_test_split(
    X_crane, y_crane, test_size=0.15, random_state=42
)
crane_model = RandomForestRegressor(
    n_estimators=300,
    max_depth=12,
    min_samples_leaf=5,
    random_state=42,
    n_jobs=-1,
)
crane_model.fit(X_c_train, y_c_train)
y_c_pred = crane_model.predict(X_c_test)
print(f"         MAE : {mean_absolute_error(y_c_test, y_c_pred):.2f} moves/hr")
print(f"         R²  : {r2_score(y_c_test, y_c_pred):.3f}")

# ── 5. Anomaly Detector ───────────────────────────────────────────────────────
print("[6/7]  Training anomaly detector (IsolationForest) …")
X_anom = pd.DataFrame({
    "size_teu":             size_teu,
    "effective_dwell_hours": effective_dwell,
    "wait_hours":            wait_hours,
    "crane_count":           crane_count,
    "priority":              priority,
})

# IsolationForest is unsupervised; train only on 'normal' samples for better contamination
normal_mask = anomaly_label == 1
anomaly_model = IsolationForest(
    n_estimators=200,
    contamination=0.05,   # expected ~5% anomaly rate in production
    random_state=42,
    n_jobs=-1,
)
anomaly_model.fit(X_anom[normal_mask])

# Evaluate on full dataset
anom_pred = anomaly_model.predict(X_anom)
true_anomaly = anomaly_label
tp = np.sum((anom_pred == -1) & (true_anomaly == -1))
fp = np.sum((anom_pred == -1) & (true_anomaly == 1))
fn = np.sum((anom_pred == 1) & (true_anomaly == -1))
precision = tp / (tp + fp + 1e-9)
recall    = tp / (tp + fn + 1e-9)
print(f"         Precision: {precision:.3f}  Recall: {recall:.3f}")
print(f"         Flagged {np.sum(anom_pred == -1):,} anomalies in {N:,} samples")

# ── 6. Save all models ────────────────────────────────────────────────────────
print("\n[7/7]  Saving models to", MODEL_DIR)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
joblib.dump(risk_model,     MODEL_DIR / "risk_model.pkl")
joblib.dump(le,             MODEL_DIR / "risk_label_encoder.pkl")
joblib.dump(wait_model,     MODEL_DIR / "wait_model.pkl")
joblib.dump(demurrage_model, MODEL_DIR / "demurrage_model.pkl")
joblib.dump(crane_model,    MODEL_DIR / "crane_productivity_model.pkl")
joblib.dump(anomaly_model,  MODEL_DIR / "anomaly_model.pkl")
print("  [OK]  risk_model.pkl")
print("  [OK]  risk_label_encoder.pkl")
print("  [OK]  wait_model.pkl")
print("  [OK]  demurrage_model.pkl")
print("  [OK]  crane_productivity_model.pkl")
print("  [OK]  anomaly_model.pkl")
print("\n=== Training complete ===")
print(f"  Samples used : {N:,}")
print(f"  Risk classes : {list(le.classes_)}")
print("  All models saved with named feature columns (no sklearn feature_names warnings).")
