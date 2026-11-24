"""
policy_engine.py - Procurement Policy Evaluation Engine
Part of ProcureAI — The Intelligent Procurement Desk solution.
"""

import math
from typing import Dict, Any, Optional

class PolicyEngine:
    """
    Evaluates Acme Corporation's official procurement negotiation rules.
    Strictly follows policies/decision-procedure.md:
    1. Missing information
    2. Blacklisted supplier
    3. Prompt injection
    4. Banned contract terms
    5. Price decision (L(r) concession schedule, final round walkaway, probation rule)
    6. Approval limits
    """

    def __init__(self, data_loader: Any, offer_extractor: Any, security_agent: Any):
        self.data_loader = data_loader
        self.offer_extractor = offer_extractor
        self.security_agent = security_agent

    def compute_concession_schedule(self, target: float, walkaway: float, r: int, R: int, beta: float, is_probation: bool = False) -> float:
        """
        Computes acceptable level L(r):
        L(r) = target + (walkaway − target) × ((r − 1) / (R − 1)) ^ β
        Special rule for PROBATION suppliers: Acme makes no concessions:
        acceptable level L(r) equals target in every round.
        """
        if is_probation:
            return float(target)
            
        if r <= 1:
            return float(target)
        if r >= R:
            return float(walkaway)
            
        ratio = (r - 1.0) / (R - 1.0)
        return float(target + (walkaway - target) * math.pow(ratio, beta))

    def evaluate(self, thread_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates a single negotiation record and returns a detailed decision dictionary.
        """
        thread_id = str(thread_data['thread_id'])
        date = str(thread_data['date'])
        supplier = str(thread_data['supplier'])
        category = str(thread_data['category'])
        quantity = int(thread_data['quantity'])
        round_num = int(thread_data['round'])
        message = str(thread_data['supplier_message'])
        our_last_counter = thread_data.get('our_last_counter', None)

        decision = {
            'thread_id': thread_id,
            'action': '',
            'reason': '',
            'counter_price': None,
            'label': '',
            'p': None,
            'L_r': None,
            'deal_value': None,
            'approval_limit': None,
            'rule_step': 0,
            'rule_name': '',
            'explanation': '',
            'evidence': ''
        }

        # -------------------------------------------------------------
        # STEP 1: Missing information
        # No usable price in the supplier's latest offer (no number,
        # subscription price with no billing period, or unlisted currency)
        # -------------------------------------------------------------
        extraction = self.offer_extractor.extract(message, category, supplier, quantity, date)
        if extraction['error'] in ['UNSUPPORTED_CURRENCY', 'NO_BILLING_PERIOD', 'NO_USABLE_PRICE']:
            err = extraction['error']
            decision.update({
                'action': 'ESCALATE',
                'reason': 'MISSING_INFO',
                'counter_price': None,
                'label': 'ESCALATE:MISSING_INFO:',
                'rule_step': 1,
                'rule_name': 'Missing information',
                'explanation': f'Supplier offer lacks necessary pricing details: {err}.',
                'evidence': extraction.get('latest_message', '')[:120]
            })
            return decision

        p = extraction['normalized_price']
        decision['p'] = p

        # -------------------------------------------------------------
        # STEP 2: Blacklisted supplier
        # Supplier failed audit and is blacklisted -> REJECT, BLACKLISTED_SUPPLIER
        # -------------------------------------------------------------
        if self.security_agent.is_blacklisted(supplier):
            decision.update({
                'action': 'REJECT',
                'reason': 'BLACKLISTED_SUPPLIER',
                'counter_price': None,
                'label': 'REJECT:BLACKLISTED_SUPPLIER:',
                'rule_step': 2,
                'rule_name': 'Blacklisted supplier',
                'explanation': f'Supplier {supplier} is blacklisted by Acme (failed audit).',
                'evidence': f'Status: BLACKLISTED in suppliers/{supplier.lower().replace(" ", "-")}.md'
            })
            return decision

        # -------------------------------------------------------------
        # STEP 3: Prompt injection
        # Any text anywhere in the thread aimed at AI, bot, system,
        # reviewer, or claiming override/pre-approval
        # -------------------------------------------------------------
        inj_check = self.security_agent.detect_prompt_injection(message)
        if inj_check['is_injection']:
            patterns_str = ', '.join(inj_check['patterns'])
            evidence_str = inj_check['snippets'][0] if inj_check['snippets'] else ''
            decision.update({
                'action': 'ESCALATE',
                'reason': 'PROMPT_INJECTION',
                'counter_price': None,
                'label': 'ESCALATE:PROMPT_INJECTION:',
                'rule_step': 3,
                'rule_name': 'Prompt injection',
                'explanation': f'Adversarial prompt injection detected in thread: {patterns_str}.',
                'evidence': evidence_str
            })
            return decision

        # -------------------------------------------------------------
        # STEP 4: Banned contract terms
        # Any banned contract terms in latest message (auto renewal,
        # upfront > 30%, unlimited liability, exclusivity)
        # -------------------------------------------------------------
        banned_check = self.security_agent.detect_banned_terms(message)
        if banned_check['has_banned_terms']:
            clauses_str = ', '.join(banned_check['clauses'])
            evidence_str = banned_check['snippets'][0] if banned_check['snippets'] else ''
            decision.update({
                'action': 'ESCALATE',
                'reason': 'BANNED_TERM',
                'counter_price': None,
                'label': 'ESCALATE:BANNED_TERM:',
                'rule_step': 4,
                'rule_name': 'Banned contract terms',
                'explanation': f'Prohibited legal clause detected in latest message: {clauses_str}.',
                'evidence': evidence_str
            })
            return decision

        # -------------------------------------------------------------
        # STEP 5 & 7: Price decision and Concession Schedule
        # Dynamic category parameters + dated amendments + supplier contracts
        # -------------------------------------------------------------
        cat_params = self.data_loader.get_effective_category_params(category, date, supplier)
        target = cat_params['target']
        walkaway = cat_params['walkaway']
        R = cat_params['R']
        beta = cat_params['beta']
        approval_limit = cat_params['approval_limit']
        decision['approval_limit'] = approval_limit

        is_probation = (supplier in self.data_loader.suppliers and 
                        self.data_loader.suppliers[supplier]['status'] == 'PROBATION')

        L_r = self.compute_concession_schedule(target, walkaway, round_num, R, beta, is_probation=is_probation)
        decision['L_r'] = L_r

        # Comparison
        if p <= L_r:
            # Step 6: Approval limit check
            deal_value = p * quantity
            decision['deal_value'] = deal_value
            if deal_value > approval_limit:
                decision.update({
                    'action': 'ESCALATE',
                    'reason': 'OVER_APPROVAL_LIMIT',
                    'counter_price': None,
                    'label': 'ESCALATE:OVER_APPROVAL_LIMIT:',
                    'rule_step': 6,
                    'rule_name': 'Approval limit exceeded',
                    'explanation': f'Offer is acceptable (₹{p:.2f} <= ₹{L_r:.2f}), but deal value ₹{deal_value:,.2f} exceeds approval limit ₹{approval_limit:,.2f}.',
                    'evidence': f'Deal Value: ₹{deal_value:,.2f} > Limit: ₹{approval_limit:,.2f}'
                })
                return decision
            else:
                decision.update({
                    'action': 'ACCEPT',
                    'reason': 'ACCEPTABLE_PRICE',
                    'counter_price': None,
                    'label': 'ACCEPT:ACCEPTABLE_PRICE:',
                    'rule_step': 6,
                    'rule_name': 'Acceptable deal',
                    'explanation': f'Offer ₹{p:.2f} is at or below benchmark level ₹{L_r:.2f} and deal value ₹{deal_value:,.2f} is within approval limit ₹{approval_limit:,.2f}.',
                    'evidence': f'Price ₹{p:.2f} <= Level ₹{L_r:.2f}'
                })
                return decision
        else:
            # p > L_r
            if round_num >= R:
                # Final round walk-away
                decision.update({
                    'action': 'REJECT',
                    'reason': 'ABOVE_WALKAWAY',
                    'counter_price': None,
                    'label': 'REJECT:ABOVE_WALKAWAY:',
                    'rule_step': 5,
                    'rule_name': 'Final round walk-away',
                    'explanation': f'Final round (r={round_num} of {R}): Supplier price ₹{p:.2f} exceeds walk-away limit ₹{walkaway:.2f}.',
                    'evidence': f'Final Round Price ₹{p:.2f} > Walkaway ₹{walkaway:.2f}'
                })
                return decision
            else:
                # Counter-offer rounded to nearest whole rupee (x.5 up)
                counter_p = int(math.floor(L_r + 0.5))
                decision.update({
                    'action': 'COUNTER',
                    'reason': 'COUNTER_OFFER',
                    'counter_price': counter_p,
                    'label': f'COUNTER:COUNTER_OFFER:{counter_p}',
                    'rule_step': 5,
                    'rule_name': 'Counter offer',
                    'explanation': f'Supplier price ₹{p:.2f} exceeds acceptable level ₹{L_r:.2f}. Countering at round-{round_num} benchmark ₹{counter_p}.',
                    'evidence': f'Round {round_num} benchmark L(r) = ₹{L_r:.2f} -> Counter: ₹{counter_p}'
                })
                return decision
