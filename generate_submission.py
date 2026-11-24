"""
generate_submission.py - End-to-End Prediction and Submission Pipeline
Part of ProcureAI — The Intelligent Procurement Desk solution.
"""

import os
import sys
import pandas as pd
from agent import ProcurementAgent
from validator import SubmissionValidator

def main():
    print("=" * 70)
    print(" PROCUREAI — INTELLIGENT PROCUREMENT DESK")
    print(" Official Competition Prediction & Submission Generator")
    print("=" * 70)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    agent = ProcurementAgent(base_dir=base_dir)

    # -------------------------------------------------------------
    # PHASE 1: Validate against 40 Sample Answers
    # -------------------------------------------------------------
    print("\n[PHASE 1] Testing on 40 labelled sample threads...")
    sample_threads = agent.data_loader.load_sample_threads()
    sample_answers = agent.data_loader.load_sample_answers()

    sample_preds = agent.generate_submission_df(sample_threads)
    eval_report = SubmissionValidator.evaluate_predictions(sample_preds, sample_answers)

    print(f"Sample Exact Accuracy: {eval_report['correct_exact']}/{eval_report['total']} ({eval_report['accuracy_exact']:.2f}%)")
    print(f"Action-wise Accuracy:  {eval_report['accuracy_action']:.2f}%")
    print(f"Reason-code Accuracy:  {eval_report['accuracy_reason']:.2f}%")
    print("\nAction Confusion Matrix:")
    print(eval_report['confusion_matrix_action'])

    if eval_report['mismatches_count'] > 0:
        print(f"\n[WARNING] Found {eval_report['mismatches_count']} sample mismatches:")
        for m in eval_report['mismatches']:
            print(f"  Thread {m['thread_id']}: Predicted={m['predicted']} | Expected={m['actual']}")
        sys.exit(1)
    else:
        print("\n>>> ALL 40 SAMPLE THREADS VERIFIED WITH 100.0% EXACT ACCURACY! <<<")

    # -------------------------------------------------------------
    # PHASE 2: Process All 2,000 Real Competition Threads
    # -------------------------------------------------------------
    print("\n[PHASE 2] Processing all 2,000 threads from threads.csv...")
    threads_df = agent.data_loader.load_threads()
    sample_sub_template = agent.data_loader.load_sample_submission()

    print(f"Loaded {len(threads_df)} threads. Running procurement agent pipeline...")
    submission_df = agent.generate_submission_df(threads_df)

    # -------------------------------------------------------------
    # PHASE 3: Strict Validation of Submission File
    # -------------------------------------------------------------
    print("\n[PHASE 3] Validating submission against competition constraints...")
    expected_ids = list(sample_sub_template['thread_id'])
    val_res = SubmissionValidator.validate_submission_format(submission_df, expected_ids=expected_ids)

    if not val_res['is_valid']:
        print("[ERROR] Submission validation failed!")
        for issue in val_res['issues']:
            print(f" - {issue}")
        sys.exit(1)

    print(">>> SUBMISSION FORMAT VALIDATION PASSED! <<<")
    print(f"Total Rows: {val_res['total_rows']}")
    print("Columns: ['thread_id', 'label']")
    print("All IDs match sample_submission.csv in exact order.")
    print("Zero nulls, zero duplicates, all labels conform strictly to regex.")

    # -------------------------------------------------------------
    # PHASE 4: Export submission.csv
    # -------------------------------------------------------------
    out_path_root = os.path.join(base_dir, "submission.csv")
    out_path_proc = os.path.join(base_dir, "the-procurement-desk", "submission.csv")

    submission_df.to_csv(out_path_root, index=False)
    submission_df.to_csv(out_path_proc, index=False)
    print(f"\n[PHASE 4] Exported submission files to:")
    print(f" - {out_path_root}")
    print(f" - {out_path_proc}")

    # Summary Statistics
    print("\n=== PREDICTION SUMMARY (2,000 Records) ===")
    actions = submission_df['label'].apply(lambda x: x.split(':')[0])
    reasons = submission_df['label'].apply(lambda x: ':'.join(x.split(':')[:2]))
    
    print("\nAction Distribution:")
    for act, cnt in actions.value_counts().items():
        print(f"  {act:<10}: {cnt:>4} ({cnt/len(submission_df)*100:>5.1f}%)")

    print("\nReason Breakdown:")
    for rsn, cnt in reasons.value_counts().items():
        print(f"  {rsn:<30}: {cnt:>4} ({cnt/len(submission_df)*100:>5.1f}%)")

    counter_rows = submission_df[submission_df['label'].str.startswith('COUNTER:')]
    counter_prices = counter_rows['label'].apply(lambda x: int(x.split(':')[2]))
    print(f"\nCounter Offers Statistics ({len(counter_rows)} total):")
    print(f"  Min counter price:  ₹{counter_prices.min():,}")
    print(f"  Median counter:     ₹{counter_prices.median():,}")
    print(f"  Mean counter:       ₹{counter_prices.mean():,.2f}")
    print(f"  Max counter price:  ₹{counter_prices.max():,}")

    print("\n" + "=" * 70)
    print(" SUCCESS: Complete pipeline executed and validated successfully.")
    print("=" * 70)

if __name__ == '__main__':
    main()
