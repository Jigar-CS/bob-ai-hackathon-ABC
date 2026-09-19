# PortPulse Test Datasets & ML Evaluation Suite

Directory: [tests/testingdataset](file:///d:/IBM/bob-ai-hackathon-ABC/tests/testingdataset)

This directory contains test datasets, evaluation runners, and expected JSON outputs for the current version of PortPulse.

---

## 📁 Datasets Included

### 1. `vessels_dataset_1_la_lb_surge.csv`
- **Scenario**: High-Volume Port Congestion Surge (LA/Long Beach Backlog).
- **Vessel Count**: 25 vessels.
- **Vessel Size**: 7,000 TEU to 20,000 TEU (ULCVs).
- **Destinations**: `LA/Long Beach`, `Port of Oakland`, `Port of Seattle`, `Port of San Diego`.
- **Features Tested**: Queue stacking, high-volume TEU congestion, priority-1 emergency berth jumping, and alternate port rerouting.

### 2. `vessels_dataset_2_global_multiport.csv`
- **Scenario**: Global Multi-Port Operations & Weather Route Disruptions.
- **Vessel Count**: 25 vessels.
- **Origins & Destinations**: Multi-port routes across Rotterdam, Hamburg, Dubai, Singapore, Santos, Sydney, Shanghai, Ningbo, Busan, LA/Long Beach.
- **Features Tested**: Multi-waypoint marine weather delays, dynamic berth slot gap-filling, berth waiting queue position tracking, and global alternate port recommendations.

---

## ⚙️ Evaluation Script & Expected JSON Outputs

- **Runner Script**: [evaluate_both_datasets.py](file:///d:/IBM/bob-ai-hackathon-ABC/tests/testingdataset/evaluate_both_datasets.py)
  - Run via: `python tests/testingdataset/evaluate_both_datasets.py`
- **Output JSON 1**: [dataset_1_ml_output.json](file:///d:/IBM/bob-ai-hackathon-ABC/tests/testingdataset/dataset_1_ml_output.json)
- **Output JSON 2**: [dataset_2_ml_output.json](file:///d:/IBM/bob-ai-hackathon-ABC/tests/testingdataset/dataset_2_ml_output.json)

---

## 📊 Summary of ML Pipeline Features Active in Datasets

| Feature | Description | ML Model / Engine |
| :--- | :--- | :--- |
| **Berth Queue Tracking** | Identifies `BERTHED` vs `QUEUED (#1, #2)` and `queued_behind` vessel name | `BerthAllocationOptimizer` |
| **Slot Gap-Filling** | Re-allocates freed berth slots to non-delayed vessels when weather delays occur | Weather-Adjusted Arrival Scheduler |
| **Dynamic Multi-Port Rerouting** | Computes route waypoints and alternate ports per dynamic destination | `weather_predictor.py` + `port_ranking_model.pkl` |
| **Demurrage & Productivity** | Computes predicted demurrage ($) and crane handling moves/hr | `demurrage_cost_model.pkl` + `crane_productivity_model.pkl` |
| **Anomaly Detection** | Flags unusual dwell/wait operational patterns | `IsolationForest` (`anomaly_model.pkl`) |
