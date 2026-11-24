"""
data_loader.py - Data Ingestion and Playbook Configuration Loader
Part of ProcureAI — The Intelligent Procurement Desk solution.
"""

import os
import re
import pandas as pd
from typing import Dict, Any, List, Optional

# Base directory for playbook and competition files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROC_DIR = os.path.join(BASE_DIR, "the-procurement-desk")
PLAYBOOK_DIR = os.path.join(PROC_DIR, "playbook", "playbook")

class DataLoader:
    """Loads datasets and parses playbook rules dynamically from markdown files."""
    
    def __init__(self, base_dir: str = BASE_DIR):
        self.base_dir = base_dir
        self.proc_dir = os.path.join(base_dir, "the-procurement-desk")
        self.playbook_dir = os.path.join(self.proc_dir, "playbook", "playbook")
        
        # In-memory caches
        self.categories: Dict[str, Dict[str, Any]] = {}
        self.suppliers: Dict[str, Dict[str, Any]] = {}
        self.amendments: List[Dict[str, Any]] = []
        self.policies: Dict[str, str] = {}
        self.precedents: Dict[str, str] = {}
        
        self.load_playbook()

    def load_playbook(self):
        """Parse all markdown files inside categories, suppliers, amendments, policies, and precedents."""
        self._load_categories()
        self._load_suppliers()
        self._load_amendments()
        self._load_policies()
        self._load_precedents()

    def _load_categories(self):
        """Loads and parses category markdown files."""
        cat_dir = os.path.join(self.playbook_dir, "categories")
        if not os.path.exists(cat_dir):
            return
            
        for f in os.listdir(cat_dir):
            if not f.endswith(".md"):
                continue
            cat_name = f.replace(".md", "")
            path = os.path.join(cat_dir, f)
            with open(path, "r", encoding="utf-8") as fp:
                text = fp.read()
                
            info = {
                "name": cat_name,
                "unit": "",
                "gst": 0.18,
                "target": 0.0,
                "walkaway": 0.0,
                "R": 3,
                "beta": 1.0,
                "approval_limit": 1000000.0,
                "is_subscription": False,
                "billing_period": None,
                "pack_conversion": None,
                "raw_text": text
            }
            
            for line in text.splitlines():
                line = line.strip()
                if "**Normalized unit:**" in line:
                    unit_text = line.split("**Normalized unit:**")[1].strip()
                    info["unit"] = unit_text
                    if "per month" in unit_text:
                        info["is_subscription"] = True
                        info["billing_period"] = "month"
                    elif "per year" in unit_text:
                        info["is_subscription"] = True
                        info["billing_period"] = "year"
                elif "**GST rate:**" in line:
                    m = re.search(r'(\d+)%', line)
                    if m:
                        info["gst"] = float(m.group(1)) / 100.0
                elif "**Target price:**" in line:
                    m = re.search(r'[₹Rs\.]*\s*([\d,]+)', line)
                    if m:
                        info["target"] = float(m.group(1).replace(",", ""))
                elif "**Walk-away price:**" in line:
                    m = re.search(r'[₹Rs\.]*\s*([\d,]+)', line)
                    if m:
                        info["walkaway"] = float(m.group(1).replace(",", ""))
                elif "**Negotiation rounds (R):**" in line:
                    m = re.search(r'(\d+)', line.split("(R):")[1])
                    if m:
                        info["R"] = int(m.group(1))
                elif "**Concession exponent (β):**" in line:
                    m = re.search(r'([\d\.]+)', line.split("(β):")[1])
                    if m:
                        info["beta"] = float(m.group(1))
                elif "**Approval limit:**" in line:
                    m = re.search(r'[₹Rs\.]*\s*([\d,]+)', line)
                    if m:
                        info["approval_limit"] = float(m.group(1).replace(",", ""))
                elif "**Pack conversion:**" in line:
                    info["pack_conversion"] = line.split("**Pack conversion:**")[1].strip()
                    
            self.categories[cat_name] = info

    def _load_suppliers(self):
        """Loads and parses supplier markdown files."""
        sup_dir = os.path.join(self.playbook_dir, "suppliers")
        if not os.path.exists(sup_dir):
            return
            
        for f in os.listdir(sup_dir):
            if not f.endswith(".md"):
                continue
            path = os.path.join(sup_dir, f)
            with open(path, "r", encoding="utf-8") as fp:
                text = fp.read()
                
            name = None
            status = "Approved"
            notes = ""
            contract = None
            exchange_rates = {}
            price_caps = {}
            
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("# Supplier:"):
                    name = line.split("# Supplier:")[1].strip()
                elif line.startswith("- **Status:**"):
                    st = line.split("- **Status:**")[1].strip()
                    if "BLACKLISTED" in st.upper():
                        status = "BLACKLISTED"
                    elif "PROBATION" in st.upper():
                        status = "PROBATION"
                    else:
                        status = "Approved"
                elif line.startswith("- **Contract:**"):
                    contract = line.split("- **Contract:**")[1].strip()
                    # Check exchange rate in contract
                    m_fx = re.search(r'invoices in ([A-Z]{3}) are converted at [₹Rs\.]*\s*([\d\.]+)', contract, re.I)
                    if m_fx:
                        curr = m_fx.group(1).upper()
                        rate = float(m_fx.group(2))
                        exchange_rates[curr] = rate
                    # Check price cap in contract
                    # e.g. price cap for Catering of ₹400 per meal (replaces the walk-away price)
                    m_cap = re.search(r'price cap for ([A-Za-z\s\-]+) of [₹Rs\.]*\s*([\d,]+)', contract, re.I)
                    if m_cap:
                        cap_cat = m_cap.group(1).strip().lower().replace(" ", "-")
                        cap_val = float(m_cap.group(2).replace(",", ""))
                        price_caps[cap_cat] = cap_val
                elif line.startswith("- **Notes:**"):
                    notes = line.split("- **Notes:**")[1].strip()
                    
            if name:
                self.suppliers[name] = {
                    "name": name,
                    "status": status,
                    "contract": contract,
                    "exchange_rates": exchange_rates,
                    "price_caps": price_caps,
                    "notes": notes,
                    "raw_text": text
                }

    def _load_amendments(self):
        """Loads and parses amendments sorted by effective date."""
        amd_dir = os.path.join(self.playbook_dir, "amendments")
        if not os.path.exists(amd_dir):
            return
            
        items = []
        for f in os.listdir(amd_dir):
            if not f.endswith(".md"):
                continue
            path = os.path.join(amd_dir, f)
            with open(path, "r", encoding="utf-8") as fp:
                text = fp.read()
                
            amd_id = f.replace(".md", "")
            effective_date = ""
            category = ""
            field = ""
            val = 0.0
            
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("#"):
                    # Header: # AMD-01: Courier services
                    if ":" in line:
                        cat_title = line.split(":")[1].strip().lower().replace(" ", "-")
                        # map category name
                        if "courier" in cat_title:
                            category = "courier"
                        elif "cloud" in cat_title:
                            category = "cloud-servers"
                        elif "mobile" in cat_title:
                            category = "mobile-phones"
                        elif "catering" in cat_title:
                            category = "catering"
                        elif "paper" in cat_title:
                            category = "printer-paper"
                        elif "headset" in cat_title:
                            category = "headsets"
                        elif "led" in cat_title:
                            category = "led-lighting"
                        elif "monitor" in cat_title:
                            category = "monitors"
                elif line.startswith("- **Effective from:**"):
                    effective_date = line.split("**Effective from:**")[1].strip()
                elif line.startswith("- **Change:**"):
                    change_text = line.split("**Change:**")[1].strip()
                    if "walk-away price" in change_text:
                        field = "walkaway"
                    elif "target price" in change_text:
                        field = "target"
                    elif "approval limit" in change_text:
                        field = "approval_limit"
                    m = re.search(r'[₹Rs\.]*\s*([\d,]+)', change_text)
                    if m:
                        val = float(m.group(1).replace(",", ""))
                        
            items.append({
                "id": amd_id,
                "category": category,
                "date": effective_date,
                "field": field,
                "value": val,
                "raw_text": text
            })
            
        # Sort by effective date
        self.amendments = sorted(items, key=lambda x: x["date"])

    def _load_policies(self):
        """Loads policy markdown files."""
        pol_dir = os.path.join(self.playbook_dir, "policies")
        if not os.path.exists(pol_dir):
            return
        for f in os.listdir(pol_dir):
            if f.endswith(".md"):
                p_name = f.replace(".md", "")
                with open(os.path.join(pol_dir, f), "r", encoding="utf-8") as fp:
                    self.policies[p_name] = fp.read()

    def _load_precedents(self):
        """Loads precedent markdown files."""
        prec_dir = os.path.join(self.playbook_dir, "precedents")
        if not os.path.exists(prec_dir):
            return
        for f in os.listdir(prec_dir):
            if f.endswith(".md"):
                p_name = f.replace(".md", "")
                with open(os.path.join(prec_dir, f), "r", encoding="utf-8") as fp:
                    self.precedents[p_name] = fp.read()

    def get_effective_category_params(self, category: str, thread_date: str, supplier: Optional[str] = None) -> Dict[str, Any]:
        """Resolves target, walkaway, and approval limit applying dated amendments and supplier contract overrides."""
        if category not in self.categories:
            raise ValueError(f"Unknown category: {category}")
            
        base = self.categories[category].copy()
        target = float(base["target"])
        walkaway = float(base["walkaway"])
        approval_limit = float(base["approval_limit"])
        applied_amendments = []
        
        # Apply amendments whose effective date <= thread_date
        for amd in self.amendments:
            if amd["category"] == category and amd["date"] <= thread_date:
                applied_amendments.append(amd["id"])
                if amd["field"] == "target":
                    target = float(amd["value"])
                elif amd["field"] == "walkaway":
                    walkaway = float(amd["value"])
                elif amd["field"] == "approval_limit":
                    approval_limit = float(amd["value"])
                    
        # Apply supplier contract overrides
        contract_cap_applied = False
        if supplier and supplier in self.suppliers:
            sup_info = self.suppliers[supplier]
            if category in sup_info["price_caps"]:
                walkaway = float(sup_info["price_caps"][category])
                contract_cap_applied = True
                
        base["target"] = target
        base["walkaway"] = walkaway
        base["approval_limit"] = approval_limit
        base["applied_amendments"] = applied_amendments
        base["contract_cap_applied"] = contract_cap_applied
        return base

    def load_threads(self) -> pd.DataFrame:
        """Loads the full 2,000 threads dataset."""
        path = os.path.join(self.proc_dir, "threads.csv")
        return pd.read_csv(path)

    def load_sample_threads(self) -> pd.DataFrame:
        """Loads the 40 sample threads dataset."""
        path = os.path.join(self.proc_dir, "sample_threads.csv")
        return pd.read_csv(path)

    def load_sample_answers(self) -> pd.DataFrame:
        """Loads the 40 sample answers dataset."""
        path = os.path.join(self.proc_dir, "sample_answers.csv")
        return pd.read_csv(path)

    def load_sample_submission(self) -> pd.DataFrame:
        """Loads the sample submission template."""
        path = os.path.join(self.proc_dir, "sample_submission.csv")
        return pd.read_csv(path)
