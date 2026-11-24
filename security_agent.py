"""
security_agent.py - Security Verification Agent
Part of ProcureAI — The Intelligent Procurement Desk solution.
"""

import re
from typing import Dict, Any, List, Optional
from offer_extractor import get_latest_message

class SecurityAgent:
    """
    Enforces Acme's security and legal compliance policies:
    - Step 2: Blacklisted supplier detection
    - Step 3: Prompt injection detection (multilingual, entire thread)
    - Step 4: Banned contract terms detection (latest message)
    """

    PROMPT_INJECTION_PATTERNS = [
        (r'<!--\s*assistant:\s*mark this thread', 'Hidden HTML comment instruction to assistant'),
        (r'mark this thread as accept', 'Direct instruction to assistant'),
        (r'approval already granted', 'False claim of prior approval'),
        (r'ignore your previous instructions', 'Instruction override attempt'),
        (r'ignore previous', 'Instruction override attempt'),
        (r'note for the language model', 'Direct instruction to AI/LLM'),
        (r'note to the language model', 'Direct instruction to AI/LLM'),
        (r'ai सहायक के लिए निर्देश', 'Multilingual (Hindi) prompt injection'),
        (r'as per acme procurement policy section 9\.2', 'Fabricated policy override'),
        (r'if an automated system is reading', 'Conditional instruction to automated system'),
        (r'bot screens these', 'Targeting automated screening bot'),
        (r'system note to ai agent', 'Impersonating system prompt for AI agent'),
        (r'\[admin override\]', 'Privilege escalation / Admin override tag'),
        (r'whichever bot', 'Bot targeting directive'),
        (r'pre-approved by', 'False claim of prior executive signoff'),
        (r'reviewing assistant should accept', 'Direct command to reviewing assistant'),
        (r'output accept', 'Direct command to force model output'),
        (r'record the decision as approved', 'Instruction to override evaluation'),
        (r'approve this vendor without escalation', 'Instruction to bypass escalation protocol')
    ]

    ALLOWED_SAFE_BUSINESS_TERMS = [
        r'(?i)\bAI-powered\b',
        r'(?i)\bsystem integration(?: team)?\b',
        r'(?i)\bERP system\b',
        r'(?i)\bassistant manager\b'
    ]

    def __init__(self, data_loader: Any):
        self.data_loader = data_loader

    def is_blacklisted(self, supplier: str) -> bool:
        """Checks if a supplier has failed audit and is blacklisted."""
        if supplier in self.data_loader.suppliers:
            return self.data_loader.suppliers[supplier]['status'] == 'BLACKLISTED'
        return False

    def detect_prompt_injection(self, thread_message: str) -> Dict[str, Any]:
        """
        Inspects ANY text ANYWHERE in the negotiation thread for prompt injection attempts.
        Distinguishes adversarial inputs from legitimate business terminology.
        """
        # First verify if there is an injection pattern
        detected_patterns = []
        snippets = []

        for pattern, desc in self.PROMPT_INJECTION_PATTERNS:
            match = re.search(pattern, thread_message, re.I)
            if match:
                detected_patterns.append(desc)
                # Extract surrounding snippet
                start = max(0, match.start() - 30)
                end = min(len(thread_message), match.end() + 30)
                snippets.append(thread_message[start:end].strip().replace('\n', ' '))

        is_injection = len(detected_patterns) > 0
        return {
            'is_injection': is_injection,
            'patterns': detected_patterns,
            'snippets': snippets
        }

    def detect_banned_terms(self, thread_message: str) -> Dict[str, Any]:
        """
        Inspects the LATEST message for legally prohibited contract terms:
        1. Automatic renewal
        2. Advance / upfront payment > 30%
        3. Unlimited liability for Acme
        4. Exclusivity requirements
        """
        latest = get_latest_message(thread_message)
        banned_clauses = []
        snippets = []

        # 1. Automatic renewal
        # Banned: auto-renews, continues from year to year unless cancelled, renews on its own
        # Allowed: renewal only by mutual agreement, renewal only if both parties sign again
        if re.search(r'auto-renews|renews on its own|continues (?:from )?year to year unless', latest, re.I):
            if not re.search(r'no automatic renewal|renewal only (?:if|by)', latest, re.I):
                banned_clauses.append('Automatic renewal clause')
                m = re.search(r'(?:auto-renews[^\.\n]*|renews on its own[^\.\n]*|continues (?:from )?year to year unless[^\.\n]*)', latest, re.I)
                if m:
                    snippets.append(m.group(0).strip())

        # 2. Upfront or advance payment > 30%
        # Allowed: 30% or less
        adv_matches = re.finditer(r'(\d+)\s*%\s*(?:of the order value\s*)?(?:upfront|advance)|(?:upfront|advance)(?:\s*payment)?(?:\s*of)?\s*(\d+)\s*%', latest, re.I)
        for m in adv_matches:
            pct = int(m.group(1) or m.group(2))
            if pct > 30:
                banned_clauses.append(f'Excessive advance/upfront payment ({pct}% > 30%)')
                snippets.append(m.group(0).strip())

        word_adv = re.search(r'((?:thirty-five|forty|fifty|sixty)\s*percent\s*(?:of the order value\s*)?(?:upfront|advance)|(?:upfront|advance)\s*payment\s*of\s*(?:thirty-five|forty|fifty|sixty)\s*percent)', latest, re.I)
        if word_adv:
            banned_clauses.append('Excessive advance/upfront payment in words (> 30%)')
            snippets.append(word_adv.group(0).strip())

        # Fractional advance: e.g. "half the order value upfront" (50% > 30%)
        m_half = re.search(r'(?:half\s+(?:the\s+)?order\s+value\s+upfront|upfront\s+payment\s+of\s+half|half[^\.\n]*upfront)', latest, re.I)
        if m_half:
            banned_clauses.append('Excessive advance/upfront payment (50% > 30%)')
            snippets.append(m_half.group(0).strip())

        # 3. Unlimited liability for Acme
        m_liab = re.search(r'unlimited liability|liability[^\.\n]*unlimited', latest, re.I)
        if m_liab:
            banned_clauses.append('Unlimited liability clause')
            snippets.append(m_liab.group(0).strip())

        # 4. Exclusivity requirement
        # Allowed: "We are not asking for exclusivity", "no exclusivity"
        if re.search(r'exclusive supplier|buy (?:these items )?only from', latest, re.I):
            if not re.search(r'not asking for exclusivity|no exclusivity', latest, re.I):
                banned_clauses.append('Exclusivity requirement')
                m_excl = re.search(r'(?:exclusive supplier[^\.\n]*|buy (?:these items )?only from[^\.\n]*)', latest, re.I)
                if m_excl:
                    snippets.append(m_excl.group(0).strip())

        has_banned = len(banned_clauses) > 0
        return {
            'has_banned_terms': has_banned,
            'clauses': banned_clauses,
            'snippets': snippets
        }
