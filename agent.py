"""
agent.py - Main Procurement AI Agent Coordinator
Part of ProcureAI — The Intelligent Procurement Desk solution.
"""

import pandas as pd
from typing import Dict, Any, Union, Optional
from data_loader import DataLoader
from offer_extractor import OfferExtractor
from security_agent import SecurityAgent
from policy_engine import PolicyEngine

class ProcurementAgent:
    """
    Intelligent Procurement Desk AI Agent for Acme Corporation.
    Coordinates Offer Extraction, Security Auditing, and Policy Evaluation.
    """

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.data_loader = DataLoader(base_dir=base_dir)
        else:
            self.data_loader = DataLoader()
            
        self.offer_extractor = OfferExtractor(self.data_loader)
        self.security_agent = SecurityAgent(self.data_loader)
        self.policy_engine = PolicyEngine(self.data_loader, self.offer_extractor, self.security_agent)

    def decide(self, thread_data: Union[Dict[str, Any], pd.Series]) -> Dict[str, Any]:
        """
        Evaluates a single negotiation thread.
        Accepts a dict or a pandas Series containing thread fields.
        Returns a rich decision dictionary.
        """
        if isinstance(thread_data, pd.Series):
            thread_data = thread_data.to_dict()
        return self.policy_engine.evaluate(thread_data)

    def process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Runs the procurement agent across an entire DataFrame of negotiation threads.
        Returns a DataFrame enriched with decision metrics and explanations.
        """
        results = []
        for idx, row in df.iterrows():
            decision = self.decide(row)
            results.append(decision)
            
        res_df = pd.DataFrame(results)
        # Merge back with original columns if not already included
        for col in df.columns:
            if col not in res_df.columns:
                res_df[col] = df[col].values
        return res_df

    def generate_submission_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generates the minimal two-column submission DataFrame: thread_id, label.
        Preserves original row order.
        """
        sub_rows = []
        for idx, row in df.iterrows():
            decision = self.decide(row)
            sub_rows.append({
                'thread_id': decision['thread_id'],
                'label': decision['label']
            })
        return pd.DataFrame(sub_rows)
