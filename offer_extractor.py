"""
offer_extractor.py - Latest Offer Extraction and Price Normalization Agent
Part of ProcureAI — The Intelligent Procurement Desk solution.
"""

import re
from typing import Tuple, Optional, Dict, Any, List

def words_to_num(text: str) -> Optional[int]:
    """Converts written English numbers (e.g. 'twenty-six thousand four hundred') to integers."""
    units = {
        'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
        'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19,
        'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
        'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90
    }
    scales = {
        'hundred': 100,
        'thousand': 1000,
        'lakh': 100000,
        'lakhs': 100000,
        'crore': 10000000,
        'crores': 10000000
    }
    
    tokens = text.lower().replace('-', ' ').replace(',', ' ').split()
    total = 0
    current = 0
    found_any = False
    
    for token in tokens:
        if token in units:
            current += units[token]
            found_any = True
        elif token in scales:
            found_any = True
            scale = scales[token]
            if token == 'hundred':
                current = (current if current != 0 else 1) * 100
            else:
                current = (current if current != 0 else 1) * scale
                total += current
                current = 0
        elif token in ['and']:
            continue
            
    total += current
    return total if found_any else None

def extract_raw_number(s: Any) -> Optional[float]:
    """Extracts a numeric float value from string containing commas, words, k, or lakh notation."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
        
    s_clean = str(s).replace(',', '').strip()
    
    # Try words first
    wn = words_to_num(s_clean)
    if wn is not None:
        return float(wn)
        
    # Check lakh / lakhs notation
    m_lakh = re.match(r'^([\d\.]+)\s*lakh[s]?$', s_clean, re.I)
    if m_lakh:
        return float(m_lakh.group(1)) * 100000.0
        
    # Check k notation
    m_k = re.match(r'^([\d\.]+)\s*k$', s_clean, re.I)
    if m_k:
        return float(m_k.group(1)) * 1000.0
        
    # Direct float conversion
    try:
        return float(s_clean)
    except ValueError:
        return None

def segment_thread(thread_message: str) -> List[Dict[str, str]]:
    """Segments an email thread into ordered messages with sender and body."""
    pattern = r'\[(Earlier message|Latest message) — ([^\]]+)\]'
    splits = list(re.finditer(pattern, thread_message))
    if not splits:
        # Single message thread
        return [{'type': 'Latest message', 'sender': 'Supplier', 'body': thread_message.strip()}]
        
    messages = []
    for i, match in enumerate(splits):
        msg_type = match.group(1)
        sender_info = match.group(2)
        start_pos = match.end()
        end_pos = splits[i+1].start() if i+1 < len(splits) else len(thread_message)
        body = thread_message[start_pos:end_pos].strip()
        messages.append({
            'type': msg_type,
            'sender': sender_info,
            'body': body
        })
    return messages

def get_latest_message(thread_message: str) -> str:
    """Extracts the body of the latest message from a negotiation thread."""
    if '[Latest message' in thread_message:
        return thread_message.split('[Latest message')[-1].split(']', 1)[-1].strip()
    return thread_message.strip()

def extract_previous_quote(thread_message: str, supplier: str) -> Optional[float]:
    """Finds the supplier's previous numeric quote from earlier messages in the thread."""
    segments = segment_thread(thread_message)
    prev_quote = None
    
    for seg in segments:
        if seg['type'] == 'Earlier message' and supplier.lower() in seg['sender'].lower():
            # Extract price from this supplier segment
            m = re.search(r'(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)\s*([\d,]+(?:\.\d+)?)', seg['body'])
            if m:
                prev_quote = extract_raw_number(m.group(1))
    return prev_quote

class OfferExtractor:
    """Extracts the supplier's latest offer and normalizes it to INR per category unit, excl. GST."""

    STANDARD_RATES = {
        'USD': 84.5,
        'EUR': 91.0,
        'GBP': 106.0,
        'INR': 1.0
    }

    UNSUPPORTED_CURRENCIES = ['JPY', 'SGD', 'AED', 'AUD', 'CAD', 'CHF', 'CNY', 'NZD', 'SEK']

    def __init__(self, data_loader: Any):
        self.data_loader = data_loader

    def extract(self, thread_message: str, category: str, supplier: str, quantity: int, thread_date: str) -> Dict[str, Any]:
        """
        Extracts and normalizes the latest offer.
        Returns a dictionary containing:
        - normalized_price: float or None
        - error: Optional error code ('UNSUPPORTED_CURRENCY', 'NO_BILLING_PERIOD', 'NO_USABLE_PRICE')
        - currency: detected currency code
        - exchange_rate: applied exchange rate
        - is_gst_inclusive: bool
        - raw_quote: original extracted quote before normalization
        - method: extraction strategy applied
        """
        latest = get_latest_message(thread_message)
        cat_info = self.data_loader.categories[category]
        is_subscription = cat_info.get('is_subscription', False)
        
        result = {
            'normalized_price': None,
            'error': None,
            'currency': 'INR',
            'exchange_rate': 1.0,
            'is_gst_inclusive': False,
            'raw_quote': None,
            'method': 'unknown',
            'latest_message': latest
        }

        # 1. Check for unsupported currencies
        for unsupp in self.UNSUPPORTED_CURRENCIES:
            if re.search(rf'\b{unsupp}\b', latest, re.I):
                result['error'] = 'UNSUPPORTED_CURRENCY'
                return result

        # 2. Detect currency
        curr = 'INR'
        if re.search(r'\bUSD\b|\$', latest):
            curr = 'USD'
        elif re.search(r'\bEUR\b|€', latest):
            curr = 'EUR'
        elif re.search(r'\bGBP\b|£', latest):
            curr = 'GBP'
        elif re.search(r'\bINR\b|₹|\bRs\.?', latest):
            curr = 'INR'
        result['currency'] = curr

        # 3. Determine exchange rate (Contract rate overrides standard table rate)
        rate = 1.0
        if supplier in self.data_loader.suppliers:
            sup_info = self.data_loader.suppliers[supplier]
            if curr in sup_info['exchange_rates']:
                rate = sup_info['exchange_rates'][curr]
            elif curr in self.STANDARD_RATES:
                rate = self.STANDARD_RATES[curr]
            else:
                result['error'] = 'UNSUPPORTED_CURRENCY'
                return result
        elif curr in self.STANDARD_RATES:
            rate = self.STANDARD_RATES[curr]
        else:
            result['error'] = 'UNSUPPORTED_CURRENCY'
            return result
        result['exchange_rate'] = rate

        # 4. Check subscription billing period
        billing_mult = 1.0
        if is_subscription:
            cat_period = cat_info.get('billing_period', 'month')
            has_month = bool(re.search(r'\b(month|monthly|per month)\b', latest, re.I))
            has_year = bool(re.search(r'\b(year|annum|annual|annually|per year|per annum)\b', latest, re.I))
            
            # If "a further X% off our previous quote", check if previous quote has period
            m_prev_disc = re.search(r'(?:a further\s+)?(\d+)\s*%\s*off\s*our\s*previous\s*quote', latest, re.I)
            if not has_month and not has_year and not m_prev_disc:
                result['error'] = 'NO_BILLING_PERIOD'
                return result

            if cat_period == 'year' and has_month and not has_year:
                billing_mult = 12.0 # monthly to yearly: * 12
            elif cat_period == 'month' and has_year and not has_month:
                billing_mult = 1.0 / 12.0 # yearly to monthly: / 12

        # 5. Pack / sub-unit multipliers
        pack_mult = 1.0
        m_pack = re.search(r'per pack of (\d+)', latest, re.I)
        if m_pack:
            pack_mult = 1.0 / float(m_pack.group(1))
        elif re.search(r'per pack\b', latest, re.I):
            if category == 'led-lighting':
                pack_mult = 1.0 / 4.0 # pack of 4 fixtures
        elif re.search(r'per dozen\b', latest, re.I):
            pack_mult = 1.0 / 12.0
        elif re.search(r'per ream\b', latest, re.I):
            if category == 'printer-paper':
                pack_mult = 10.0 # 1 box = 10 reams

        raw_price = None

        # Pattern A: Discount on previous quote
        m_prev = re.search(r'(?:a further\s+)?(\d+)\s*%\s*off\s*our\s*previous\s*quote', latest, re.I)
        if m_prev:
            disc_pct = float(m_prev.group(1))
            prev_p = extract_previous_quote(thread_message, supplier)
            if prev_p is None:
                result['error'] = 'NO_USABLE_PRICE'
                return result
            raw_price = prev_p * (1.0 - disc_pct / 100.0)
            result['method'] = 'previous_quote_discount'

        # Pattern B: Correction
        if raw_price is None:
            m_corr = re.search(r'CORRECTION[^\n\r]*should read\s+(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)?\s*([0-9,]+(?:\.\d+)?|\b[a-zA-Z\s\-]+?\b)\s*(?:per|not|\.|$)', latest, re.I)
            if m_corr:
                raw_price = extract_raw_number(m_corr.group(1))
                result['method'] = 'correction'

        # Pattern C: Quoted range (Precedent P-01: take upper bound)
        if raw_price is None:
            m_range = re.search(r'between\s+(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)?\s*([\d,]+(?:\.\d+)?)\s+and\s+(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)?\s*([\d,]+(?:\.\d+)?)', latest, re.I)
            if m_range:
                raw_price = extract_raw_number(m_range.group(2))
                result['method'] = 'range_upper_bound'

        # Pattern D: Total amount for all N units
        if raw_price is None:
            m_total = re.search(r'(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)?\s*([\d,]+(?:\.\d+)?)\s+in total for all\s+(\d+)', latest, re.I)
            if m_total:
                tot_amount = extract_raw_number(m_total.group(1))
                n_units = float(m_total.group(2))
                if tot_amount is not None and n_units > 0:
                    raw_price = tot_amount / n_units
                    result['method'] = 'total_divided_by_quantity'

        # Pattern E: Tiered volume pricing
        if raw_price is None:
            m_tier = re.search(r'(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)?\s*([\d,]+(?:\.\d+)?)\s*per\s+\w+\s+for orders of up to\s+(\d+)[^,\n]*,?\s*and\s+(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)?\s*([\d,]+(?:\.\d+)?)\s*per\s+\w+\s+for larger orders', latest, re.I)
            if m_tier:
                threshold = int(m_tier.group(2))
                p_lower = extract_raw_number(m_tier.group(1))
                p_higher = extract_raw_number(m_tier.group(3))
                raw_price = p_lower if quantity <= threshold else p_higher
                result['method'] = 'tiered_volume_price'

        # Pattern F: List price discount
        if raw_price is None:
            m_list = re.search(r'(\d+)\s*%\s*discount on our list price of\s+(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)?\s*([\d,]+(?:\.\d+)?)', latest, re.I)
            if m_list:
                disc = float(m_list.group(1))
                list_p = extract_raw_number(m_list.group(2))
                if list_p is not None:
                    raw_price = list_p * (1.0 - disc / 100.0)
                    result['method'] = 'list_price_discount'

        # Pattern G: Standard quotes (digits, words, or currency symbols)
        if raw_price is None:
            m_std = re.search(r'(?:quote|offer|is|do|at)\s+(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)?\s*([\d,]+(?:\.\d+)?|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|lakh|and|-|\s)+?\b)\s*(?:rupees|per|\/|$)', latest, re.I)
            if m_std:
                raw_price = extract_raw_number(m_std.group(1))
                result['method'] = 'standard_quote'
            else:
                m_fallback = re.search(r'(?:₹|Rs\.?|INR|\$|USD|€|EUR|£|GBP)\s*([\d,]+(?:\.\d+)?)', latest)
                if m_fallback:
                    raw_price = extract_raw_number(m_fallback.group(1))
                    result['method'] = 'currency_symbol_fallback'
                else:
                    m_words = re.search(r'\b((?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|lakh|and|\s|-)+)\s+rupees', latest, re.I)
                    if m_words:
                        raw_price = extract_raw_number(m_words.group(1))
                        result['method'] = 'words_fallback'

        if raw_price is None:
            result['error'] = 'NO_USABLE_PRICE'
            return result

        result['raw_quote'] = raw_price

        # Pattern H: Free items concession (Precedents P-02, P-05)
        # e.g. "plus 1 free phone for every 12 you pay for" -> price * 12 / 13
        m_free = re.search(r'plus\s+(\d+)\s+free\s+\w+\s+for every\s+(\d+)\s+you pay for', latest, re.I)
        if m_free:
            free_n = float(m_free.group(1))
            paid_n = float(m_free.group(2))
            raw_price = raw_price * paid_n / (paid_n + free_n)
            result['method'] += '_with_free_items'

        # Apply multipliers
        normalized = raw_price * pack_mult * billing_mult * rate

        # GST normalization: If GST inclusive, divide by (1 + gst_rate)
        is_gst_inclusive = bool(re.search(r'incl(?:usive)?(?:\s+of)?\s+GST|GST\s+included|including\s+GST', latest, re.I))
        result['is_gst_inclusive'] = is_gst_inclusive
        if is_gst_inclusive:
            gst_rate = float(cat_info['gst'])
            normalized = normalized / (1.0 + gst_rate)

        result['normalized_price'] = normalized
        return result
