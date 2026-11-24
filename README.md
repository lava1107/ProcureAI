# PROCUREAI — Intelligent Procurement Desk
## Kaggle Competition Solution: DATA SPRINT 2.0 — THE PROCUREMENT DESK

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Accuracy](https://img.shields.io/badge/Sample%20Accuracy-100.0%25-brightgreen.svg)]()
[![Validation](https://img.shields.io/badge/Submission%20Validation-PASSED-success.svg)]()
[![License](https://img.shields.io/badge/License-MIT-blue.svg)]()

An end-to-end Agentic AI system built to automate Acme Corporation's procurement negotiations across 2,000 multi-turn supplier threads. The agent strictly complies with Acme's official procurement playbook, evaluates price concession curves, intercepts prompt injections and banned legal clauses, enforces spending authorization limits, and generates official decisions: `ACCEPT`, `COUNTER`, `REJECT`, or `ESCALATE`.

---

## 📋 Table of Contents
1. [Project Overview](#project-overview)
2. [Folder & File Architecture](#folder--file-architecture)
3. [The Official Decision Procedure](#the-official-decision-procedure)
4. [Specialized Agent Modules](#specialized-agent-modules)
5. [Concession Schedule Mathematics](#concession-schedule-mathematics)
6. [Security & Threat Defense](#security--threat-defense)
7. [Validation & Benchmark Results](#validation--benchmark-results)
8. [Submission File Details](#submission-file-details)
9. [Web Prototype (Streamlit & Standalone)](#web-prototype)
10. [Quickstart & Reproduction Guide](#quickstart--reproduction-guide)

---

## 🏢 Project Overview

Acme Corporation operates a procurement desk that handles supplier negotiations across **15 spend categories** and **40 approved/probationary/blacklisted suppliers**. Human negotiators follow an official playbook consisting of core policies, category-specific pricing limits, dated amendments, negotiated supplier contract overrides, and past precedent rulings.

This agentic AI solution ingests 2,000 raw supplier negotiation threads and autonomously determines the optimal next action and reason code:
```
ACTION:REASON:COUNTER_PRICE
```

### Allowed Decision Outcomes:
- `ACCEPT:ACCEPTABLE_PRICE:`
- `COUNTER:COUNTER_OFFER:<PRICE>`
- `REJECT:ABOVE_WALKAWAY:`
- `REJECT:BLACKLISTED_SUPPLIER:`
- `ESCALATE:PROMPT_INJECTION:`
- `ESCALATE:BANNED_TERM:`
- `ESCALATE:OVER_APPROVAL_LIMIT:`
- `ESCALATE:MISSING_INFO:`

---

## 🗂️ Folder & File Architecture

```
ProcureAI/
├── the-procurement-desk/
│   ├── playbook/
│   │   └── playbook/
│   │       ├── amendments/          # AMD-01 to AMD-09 (dated category changes)
│   │       ├── categories/          # 15 category markdown specification pages
│   │       ├── policies/            # 7 core operational & legal policies
│   │       ├── precedents/          # P-01 to P-08 case law decisions
│   │       ├── suppliers/           # 40 supplier profiles and contracts
│   │       └── README.md            # Playbook overview
│   ├── sample_answers.csv           # 40 ground truth training labels
│   ├── sample_submission.csv        # 2,000-row format specification
│   ├── sample_threads.csv           # 40 development negotiation threads
│   ├── threads.csv                  # 2,000 competition evaluation threads
│   └── submission.csv               # Generated competition submission
├── data_loader.py                   # Dynamic markdown playbook and CSV parser
├── offer_extractor.py               # Latest offer segmentation & NLP price normalizer
├── security_agent.py                # Prompt injection & banned legal terms detector
├── policy_engine.py                 # Concession schedule and rule decision engine
├── agent.py                         # Master Procurement Agent orchestrator
├── validator.py                     # Competition submission and benchmark validator
├── generate_submission.py           # Production execution script
├── app.py                           # Multi-page Streamlit & FastAPI web prototype
├── requirements.txt                 # Python dependencies
├── submission.csv                   # Validated submission output
└── README.md                        # Complete solution documentation
```

---

## ⚖️ The Official Decision Procedure

Per `policies/decision-procedure.md`, rules must be evaluated in strict numerical order (**the first rule that fires wins**):

```mermaid
flowchart TD
    Start([Receive Thread]) --> Step1{1. Missing Information?}
    Step1 -- Yes: No price, unlisted currency, or subscription missing period --> EscMissing["ESCALATE:MISSING_INFO:"]
    Step1 -- No --> Step2{2. Blacklisted Supplier?}
    Step2 -- Yes: Failed audit --> RejBlacklist["REJECT:BLACKLISTED_SUPPLIER:"]
    Step2 -- No --> Step3{3. Prompt Injection?}
    Step3 -- Yes: In thread --> EscInjection["ESCALATE:PROMPT_INJECTION:"]
    Step3 -- No --> Step4{4. Banned Contract Terms?}
    Step4 -- Yes: In latest message --> EscBanned["ESCALATE:BANNED_TERM:"]
    Step4 -- No --> Step5{5. Price Decision: p <= L(r)?}
    Step5 -- No & Final Round: r = R --> RejWalkaway["REJECT:ABOVE_WALKAWAY:"]
    Step5 -- No & r < R --> Counter["COUNTER:COUNTER_OFFER:L(r)"]
    Step5 -- Yes: p <= L(r) --> Step6{6. Deal Value > Limit?}
    Step6 -- Yes: p * Q > Limit --> EscLimit["ESCALATE:OVER_APPROVAL_LIMIT:"]
    Step6 -- No: Within Limit --> Accept["ACCEPT:ACCEPTABLE_PRICE:"]
```

---

## 🤖 Specialized Agent Modules

### 1. Negotiation Reader & Thread Segmenter (`offer_extractor.py`)
- Splits multi-turn threads into individual messages (`[Earlier message — ...]`, `[Latest message — ...]`).
- Respects the competition rule: **ONLY THE LATEST OFFER COUNTS**.
- When an offer states `"a further X% off our previous quote"`, reliably searches only earlier quotes from that supplier.

### 2. Price Normalization Agent (`offer_extractor.py`)
- Converts written English numbers to floats (`"twenty-six thousand four hundred"` → `26400.0`).
- Resolves Indian numeric notations (`"₹1.2 lakh"` → `120000.0`, `"₹18.5k"` → `18500.0`).
- Implements Precedent P-01: ranges (`"between ₹X and ₹Y"`) are evaluated at the upper bound `Y`.
- Implements Precedents P-02 & P-05: free items (`"1 free for every K paid"`) evaluated as `p * K / (K + 1)`.
- Handles corrections (`"CORRECTION — the price should read X, not Y"`).
- Normalizes pack and dozen units (LED fixtures per pack of 4, printer paper per ream of 10 boxes, dozens).
- Normalizes subscription periods (monthly ↔ yearly).
- Converts foreign currencies (USD: 84.5, EUR: 91.0, GBP: 106.0; supplier contract rates override table rates).
- Excludes GST (Catering 5%, Printer Paper 12%, other categories 18%).

### 3. Security Agent (`security_agent.py`)
- **Multilingual Prompt Injection Defense**: Blocks adversarial injections in English and Hindi (`AI सहायक के लिए निर्देश`), roleplay attempts, fake policy citations (`Acme policy section 9.2`), executive impersonations (`pre-approved by CFO`), and override tags (`[admin override]`).
- Whitelists legitimate business expressions: `"AI-powered"`, `"system integration team"`, `"ERP system"`, `"assistant manager"`.
- **Prohibited Contract Terms**: Detects automatic renewal clauses, upfront payments above 30%, unlimited liability, and exclusivity clauses in the latest message.
- **Supplier Sanctions**: Enforces instant rejection for blacklisted vendors (*GreenLeaf Facility Care*, *Lumen Workspace*, *Orbit Electronics*).

### 4. Policy Engine (`policy_engine.py`)
- Resolves effective parameters dynamically by applying dated amendments (effective date $\le$ thread date).
- Applies supplier-specific contract price caps (e.g. *Helix CRM* Catering cap ₹400).
- Applies **Probation Rule (Step 7)**: For vendors on PROBATION (*Banyan Guarding*, *Jade Express*, *Vertex Mobile*, *Zephyr SaaS*), Acme makes zero concessions ($L(r) = \text{target}$ in all rounds).
- Computes spending authorization limits: $\text{deal value} = p \times \text{quantity}$ (single billing period for subscriptions).

---

## 📐 Concession Schedule Mathematics

Acceptable level $L(r)$ at round $r$ is computed via:
$$L(r) = \text{target} + (\text{walkaway} - \text{target}) \times \left(\frac{r - 1}{R - 1}\right)^\beta$$

- Round 1: $L(1) = \text{target}$
- Final round $R$: $L(R) = \text{walkaway}$
- Probation suppliers: $L(r) = \text{target}$ for all $r$
- Counter-offer rounding: whole rupees, $x.5$ rounded up ($\lfloor L(r) + 0.5 \rfloor$).

---

## 📊 Validation & Benchmark Results

### 1. Test Against 40 Sample Threads
Running `generate_submission.py` evaluates all 40 sample records against `sample_answers.csv`:

| Evaluation Metric | Score | Performance |
|---|---|---|
| **Exact Overall Accuracy** | **40 / 40** | **100.0%** |
| **Action Accuracy** | **40 / 40** | **100.0%** |
| **Reason Code Accuracy** | **40 / 40** | **100.0%** |
| **Counter Price Accuracy** | **10 / 10** | **100.0%** |

#### Confusion Matrix:
```
Predicted     ACCEPT    COUNTER    ESCALATE    REJECT
Actual
ACCEPT             7          0           0         0
COUNTER            0         10           0         0
ESCALATE           0          0          16         0
REJECT             0          0           0         7
```

---

## 📈 Submission File Details

The final `submission.csv` contains all 2,000 predictions for `threads.csv`:

### Action Distribution (2,000 Records):
- **COUNTER**: 662 (33.1%)
- **ESCALATE**: 622 (31.1%)
- **ACCEPT**: 373 (18.6%)
- **REJECT**: 343 (17.2%)

### Reason Code Breakdown:
| Reason Code | Count | Share |
|---|---|---|
| `COUNTER:COUNTER_OFFER` | 662 | 33.1% |
| `ACCEPT:ACCEPTABLE_PRICE` | 373 | 18.6% |
| `ESCALATE:OVER_APPROVAL_LIMIT` | 282 | 14.1% |
| `REJECT:ABOVE_WALKAWAY` | 238 | 11.9% |
| `ESCALATE:PROMPT_INJECTION` | 143 | 7.1% |
| `ESCALATE:BANNED_TERM` | 106 | 5.3% |
| `REJECT:BLACKLISTED_SUPPLIER` | 105 | 5.2% |
| `ESCALATE:MISSING_INFO` | 91 | 4.5% |

### Counter Offer Pricing Distribution:
- **Min Counter**: ₹160 (Courier services)
- **Median Counter**: ₹14,000
- **Mean Counter**: ₹26,643.48
- **Max Counter**: ₹106,121 (Cloud servers)

---

## 🖥️ Web Prototype (ProcureAI Application)

The application features 7 interactive operational pages:
1. **Dashboard**: Executive summary, key performance indicators, decision distribution charts.
2. **Negotiation Explorer**: Search and filter 2,000 threads by supplier, category, round, or outcome; inspect thread transcripts and highlighted latest offers.
3. **AI Decision Center**: Real-time evaluation of any thread with a full 6-step audit trail, evidence snippets, and rule citations.
4. **Security Center**: Threat intelligence on 143 intercepted prompt injections, 3 blacklisted suppliers, and 106 prohibited contract terms.
5. **Playbook Viewer**: Interactive browser for 15 spend categories, 40 supplier profiles, 9 amendments, and 8 precedent case studies.
6. **Analytics**: Visual spend category breakdowns, supplier behavioral patterns, and concession curves.
7. **Submission Center**: Real-time validation verification against Kaggle constraints and direct CSV download.

---

## 🚀 Quickstart & Reproduction Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Prediction Pipeline & Verification
```bash
python generate_submission.py
```
This tests all 40 sample threads (100% exact match), processes all 2,000 competition records, validates formatting constraints, and exports `submission.csv`.

### 3. Launch Web Application
With Streamlit installed:
```bash
streamlit run app.py
```

Or run directly with Python (uses embedded high-performance server):
```bash
python app.py
```
Open your browser at `http://localhost:8501`.
