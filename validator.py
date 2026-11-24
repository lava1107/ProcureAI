"""
validator.py - Submission Validator and Evaluation Benchmark Suite
Part of ProcureAI — The Intelligent Procurement Desk solution.
"""

import re
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple

LABEL_REGEX = re.compile(
    r'^(?:ACCEPT:ACCEPTABLE_PRICE:|REJECT:(?:ABOVE_WALKAWAY|BLACKLISTED_SUPPLIER):|ESCALATE:(?:PROMPT_INJECTION|BANNED_TERM|OVER_APPROVAL_LIMIT|MISSING_INFO):|COUNTER:COUNTER_OFFER:\d+)$'
)

ALLOWED_ACTIONS = {'ACCEPT', 'COUNTER', 'REJECT', 'ESCALATE'}
ALLOWED_REASONS = {
    'ACCEPTABLE_PRICE',
    'COUNTER_OFFER',
    'ABOVE_WALKAWAY',
    'BLACKLISTED_SUPPLIER',
    'PROMPT_INJECTION',
    'BANNED_TERM',
    'OVER_APPROVAL_LIMIT',
    'MISSING_INFO'
}

class SubmissionValidator:
    """Validates predictions and submissions against official competition rules."""

    @staticmethod
    def validate_submission_format(df: pd.DataFrame, expected_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Validates structure and format of a submission dataframe:
        - 2 columns: thread_id, label
        - No NaNs or empty values
        - No duplicate thread_ids
        - Exact ID match and ordering if expected_ids provided
        - Strict label regex adherence
        """
        issues = []
        is_valid = True

        # Check columns
        if list(df.columns) != ['thread_id', 'label']:
            issues.append(f"Invalid columns: expected ['thread_id', 'label'], got {list(df.columns)}")
            is_valid = False

        # Check missing values
        null_count = df.isnull().sum().sum()
        if null_count > 0:
            issues.append(f"Found {null_count} null or missing values.")
            is_valid = False

        # Check duplicates
        dup_count = df['thread_id'].duplicated().sum()
        if dup_count > 0:
            issues.append(f"Found {dup_count} duplicate thread_ids.")
            is_valid = False

        # Check ID alignment
        if expected_ids is not None:
            if len(df) != len(expected_ids):
                issues.append(f"Row count mismatch: expected {len(expected_ids)}, got {len(df)}")
                is_valid = False
            elif list(df['thread_id']) != list(expected_ids):
                issues.append("thread_id values or ordering do not match expected IDs.")
                is_valid = False

        # Check label formats
        invalid_labels = []
        for idx, row in df.iterrows():
            lbl = str(row['label'])
            if not LABEL_REGEX.match(lbl):
                invalid_labels.append((row['thread_id'], lbl))
                
        if invalid_labels:
            issues.append(f"Found {len(invalid_labels)} invalid label formats (first: {invalid_labels[:3]})")
            is_valid = False

        return {
            'is_valid': is_valid,
            'total_rows': len(df),
            'issues': issues,
            'invalid_labels_count': len(invalid_labels)
        }

    @staticmethod
    def evaluate_predictions(preds_df: pd.DataFrame, ground_truth_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Compares predicted labels against ground truth:
        - Overall accuracy
        - Action-level accuracy
        - Reason-level accuracy
        - Confusion matrix
        - Mismatch details
        """
        merged = pd.merge(preds_df, ground_truth_df, on='thread_id', suffixes=('_pred', '_actual'))
        total = len(merged)
        if total == 0:
            return {'error': 'No matching thread_ids between predictions and ground truth.'}

        correct_exact = (merged['label_pred'] == merged['label_actual']).sum()
        accuracy_exact = (correct_exact / total) * 100.0

        # Action-level comparison
        merged['action_pred'] = merged['label_pred'].apply(lambda x: str(x).split(':')[0])
        merged['action_actual'] = merged['label_actual'].apply(lambda x: str(x).split(':')[0])
        correct_action = (merged['action_pred'] == merged['action_actual']).sum()
        accuracy_action = (correct_action / total) * 100.0

        # Reason-level comparison
        merged['reason_pred'] = merged['label_pred'].apply(lambda x: ':'.join(str(x).split(':')[:2]))
        merged['reason_actual'] = merged['label_actual'].apply(lambda x: ':'.join(str(x).split(':')[:2]))
        correct_reason = (merged['reason_pred'] == merged['reason_actual']).sum()
        accuracy_reason = (correct_reason / total) * 100.0

        # Confusion Matrix for Actions
        actions = sorted(list(ALLOWED_ACTIONS))
        action_cm = pd.crosstab(
            merged['action_actual'], 
            merged['action_pred'], 
            rownames=['Actual'], 
            colnames=['Predicted'], 
            dropna=False
        ).reindex(index=actions, columns=actions, fill_value=0)

        # Mismatches list
        mismatches = merged[merged['label_pred'] != merged['label_actual']]
        mismatch_list = []
        for idx, r in mismatches.iterrows():
            mismatch_list.append({
                'thread_id': r['thread_id'],
                'predicted': r['label_pred'],
                'actual': r['label_actual'],
                'action_pred': r['action_pred'],
                'action_actual': r['action_actual']
            })

        return {
            'total': total,
            'correct_exact': int(correct_exact),
            'accuracy_exact': accuracy_exact,
            'accuracy_action': accuracy_action,
            'accuracy_reason': accuracy_reason,
            'confusion_matrix_action': action_cm,
            'mismatches_count': len(mismatch_list),
            'mismatches': mismatch_list
        }
