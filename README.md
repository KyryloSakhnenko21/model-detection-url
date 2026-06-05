# 🛡️ URL Shield — Malicious URL Detection with Machine Learning

> **Academic Project** · Artificial Intelligence applied to Cybersecurity · ESTCB · IPCB · 2025/2026  
> **Authors:** Kyrylo Sakhnenko & Rodrigo Figueiredo · **Supervisor:** Prof. Alexandre Fonte

[![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)](https://python.org)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-RandomForest-orange)](https://scikit-learn.org)
[![Flask](https://img.shields.io/badge/Flask-Web%20App-lightgrey?logo=flask)](https://flask.palletsprojects.com)
[![Chrome Extension](https://img.shields.io/badge/Chrome-Extension%20MV3-yellow?logo=googlechrome)](https://developer.chrome.com/docs/extensions)

---

## 📋 Overview

URL Shield is a complete end-to-end Machine Learning pipeline for detecting malicious URLs (phishing, malware). The system extracts **27 lexical features** directly from the URL string — no external lookups required — and classifies URLs in real time using a **Random Forest** model trained on ~153,000 URLs.

The project was built in multiple layers following a **Defense in Depth** strategy:

```
Layer 1 — Web App              → Manual URL analysis with feature explanation
Layer 2 — Browser Extension    → Automatic analysis of all links on any webpage
Layer 3 — Network Monitor      → Real-time HTTP traffic capture and classification
Layer 4 — Wireshark Dashboard  → Offline analysis of .pcap capture files
Layer 5 — Email Analysis       → Focused link analysis inside Gmail messages
```

---

## 📊 Model Performance

| Metric | Value |
|--------|-------|
| Accuracy | 94.65% |
| Precision | 93.68% |
| Recall | 88.71% |
| F1-Score | 91.13% |
| **AUC-ROC** | **98.40%** |

Training dataset: ~153,000 URLs · Algorithm: Random Forest (500 trees, 27 features)

---

## 🚀 Quick Start

### Prerequisites
```bash
pip install flask joblib pandas scikit-learn scapy
```
> **Windows:** [Npcap](https://npcap.com/) is required for network monitoring (installed automatically with Wireshark).

### Run the application
```bash
# Must run as Administrator (required for network packet capture)
cd app/
python app.py
```
Open your browser at **http://localhost:5000**

### Install the browser extension
1. Open Chrome → `chrome://extensions`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked** → select the `extension/` folder
4. The URL Shield icon appears in the Chrome toolbar

---

## 📁 Repository Structure

```
url-shield/
│
├── app/                          # Flask web application
│   ├── app.py                    # Main app: routes, scapy monitor, SSE alerts
│   ├── treino_semanal.py         # Weekly model retraining script
│   ├── modelo_rf_final.pkl       # Trained Random Forest model (Git LFS)
│   ├── novos_links.json          # Feedback data for continuous learning
│   ├── templates/
│   │   ├── index.html            # URL analysis page
│   │   ├── monitor.html          # Real-time network monitor page
│   │   └── wireshark.html        # Wireshark dashboard page
│   └── .github/
│       └── workflows/
│           └── treino_semanal.yml  # Automated weekly retraining (GitHub Actions)
│
├── extension/                    # Chrome Extension (Manifest V3)
│   ├── manifest.json
│   ├── background.js             # Service worker: SSE listener + Flask requests
│   ├── content.js                # Page script: link extraction + Gmail email mode
│   ├── popup.html                # Extension popup UI
│   ├── popup.js                  # Popup logic
│   └── icons/
│
├── data-pipeline/                # Data processing & model training notebooks
│   ├── 01_data_cleaning.ipynb
│   ├── 02_normalization.ipynb
│   ├── 03_feature_engineering.ipynb
│   ├── 04_model_training.ipynb
│   ├── 04b_model_training_lexical.ipynb
│   ├── 05_model_optimization.ipynb
│   ├── 06_final_model.ipynb
│   ├── 07_wireshark_analysis.ipynb
│   └── figures/                  # Generated plots and charts
│
├── models/                       # Saved model files (Git LFS)
│   ├── modelo_rf_lexical.pkl     # Intermediate model (10 features)
│   └── modelo_rf_final.pkl       # Final model (27 features, ~153k URLs)
│
├── reports/                      # Project reports (PDF)
│   ├── Cap05_Data_Cleaning.pdf
│   ├── Cap06_Model_Training.pdf
│   ├── Cap07_Optimization.pdf
│   ├── Cap08_Final_Model.pdf
│   ├── Cap09_Web_Application.pdf
│   ├── Cap10_Browser_Extension.pdf
│   ├── Cap11_Wireshark.pdf
│   ├── Cap12_Network_Monitor.pdf
│   └── Cap13_Dashboard.pdf
│
├── README.md                     # This file (English)
├── README.pt.md                  # Portuguese version
├── .gitignore
└── .gitattributes                # Git LFS config for .pkl files
```

---

## ✨ Key Features

### 🌐 Web Application (3 pages)
- **Analyse URL** — Classify any URL instantly with probability bars and top-5 feature importance explanation
- **Real-time Monitor** — Live HTTP traffic capture via scapy; malicious URLs trigger SSE alerts across the app and extension
- **Wireshark Dashboard** — Upload `.pcap` files, classify all HTTP URLs, interactive filterable table, donut/bar charts, CSV export, persistent analysis history

### 🧩 Chrome Extension
- Automatic link analysis on every page (1.5s after load)
- Red highlight on malicious links with probability tooltip
- **Gmail mode** — analyses only links inside the open email, ignoring Gmail UI elements
- Real-time network alerts panel in the popup (SSE from Flask)
- Persistent alerts across page navigation (sessionStorage)
- "✓ Benign" feedback button integrated with continuous learning pipeline

### 🤖 Continuous Learning Pipeline
- User corrections collected via "✓ Benign" button
- Auto-labelling of high-confidence predictions (>95% probability)
- **GitHub Actions** workflow runs every Sunday at midnight UTC
- `warm_start=True` adds 50 new trees to the existing model without full retraining
- Updated model auto-committed back to the repository

---

## 🔬 27 Lexical Features

All features are extracted from the URL string only — no DNS, no WHOIS, no external APIs:

| Category | Features |
|----------|----------|
| Length | `url_length`, `domain_length`, `path_length` |
| Counts | `n_dots`, `n_hyphens`, `n_subdomains`, `n_digits`, `n_slashes`, `n_equals`, `n_ampersands`, `n_percent`, `n_underscores`, `n_params` |
| Ratios | `digit_ratio`, `special_char_ratio` |
| Structure | `path_depth`, `has_https`, `has_ip`, `has_at`, `http_in_path` |
| Flags | `suspicious_tld`, `is_shortener`, `suspicious_port`, `consecutive_digits` |
| Text | `suspicious_words` (login, verify, paypal, bank, password…) |
| Entropy | `domain_entropy`, `url_entropy` |

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| ML Model | scikit-learn RandomForestClassifier |
| Web Framework | Flask (Python 3.13) |
| Network Capture | scapy + Npcap |
| Real-time Alerts | Server-Sent Events (SSE) |
| Browser Extension | Chrome Manifest V3 |
| Automated Retraining | GitHub Actions |
| Large File Storage | Git LFS (.pkl models) |
| Data Processing | pandas, numpy |
| Charts | matplotlib, seaborn, Chart.js |

---

## 📄 Academic Context

This project was developed as **Project II** for the Bachelor's degree in Computer Engineering at ESTCB · IPCB (Instituto Politécnico de Castelo Branco), in the course unit *Artificial Intelligence applied to Cybersecurity*.

---

*🇵🇹 [Versão em Português disponível aqui](README.pt.md)*
