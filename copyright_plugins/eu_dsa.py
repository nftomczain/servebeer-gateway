"""
EU DSA (Digital Services Act) Plugin
Regulation (EU) 2022/2065
"""

from typing import Dict, Optional, List
from .base import CopyrightPlugin


class EUDSAPlugin(CopyrightPlugin):
    """DSA compliance plugin for European Union"""
    
    @property
    def country_code(self) -> str:
        return "EU"
    
    @property
    def law_name(self) -> str:
        return "DSA (Digital Services Act)"
    
    @property
    def law_reference(self) -> str:
        return "Regulation (EU) 2022/2065"
    
    def get_required_fields(self) -> List[str]:
        return [
            'complainant_name',
            'complainant_email',
            'infringing_cid',
            'illegal_content_explanation',
            'good_faith_statement'
        ]
    
    def get_notice_template(self) -> str:
        return """
# DSA Notice and Action Mechanism

## Article 16 Requirements - Notification of Illegal Content

### 1. Complainant Information
- **Full Name or Company Name:** [Your name/company]
- **Email Address:** [your@email.com]
- **Phone Number (optional):** [Your phone]

### 2. Description of Illegal Content
- **IPFS CID:** `ipfs://...`
- **Gateway URL:** `https://gateway.example.com/ipfs/...`
- **Legal Basis:** [Which law/regulation is violated]
- **Explanation:** [Detailed explanation why this content is illegal]

### 3. Statement of Good Faith
*"I confirm that I have a good faith belief that the information and allegations in this notice are accurate and complete."*

☐ I agree to this statement

---

## Your Rights Under DSA

- **Article 20:** Right to complain about content moderation decisions
- **Article 23:** We will provide a Statement of Reasons for our decision
- **Transparency:** All takedown decisions are logged in our transparency report

**Response Time:** 24 hours for illegal content

**Appeal:** If you disagree with our decision, you can file a complaint within 6 months.
"""
    
    def validate_notice(self, notice_data: Dict) -> tuple[bool, Optional[str]]:
        """Validate DSA notice (less strict than DMCA)"""
        
        required = self.get_required_fields()
        for field in required:
            if not notice_data.get(field):
                return False, f"Missing required field: {field}"
        
        # Validate CID
        cid = notice_data.get('infringing_cid', '')
        if not (cid.startswith('Qm') or cid.startswith('bafy') or cid.startswith('k51')):
            return False, "Invalid IPFS CID format"
        
        # Validate email
        email = notice_data.get('complainant_email', '')
        if '@' not in email:
            return False, "Invalid email address"
        
        return True, None
    
    def get_sla_hours(self) -> int:
        return 24  # DSA requires faster response than DMCA
    
    def get_counter_notice_template(self) -> str:
        return """
# DSA Complaint (Article 20)

## Right to Complain About Content Moderation Decisions

### 1. Your Information
- **Name:** [Your name]
- **Email:** [your@email.com]
- **Reference ID:** [ID from takedown notice]

### 2. Content Reference
- **CID:** [The blocked CID]
- **Date of Removal:** [When it was blocked]
- **Original Decision:** [Copy of the Statement of Reasons you received]

### 3. Grounds for Complaint
[Explain why you believe the removal was unjustified or the decision was incorrect]

### 4. Supporting Evidence
[Attach any evidence supporting your complaint]

---

**Processing Time:** We will review your complaint within 7 days and provide a detailed Statement of Reasons for our final decision.

**Further Appeal:** If unsatisfied, you may submit the dispute to a certified out-of-court dispute settlement body.
"""
    
    def get_footer_html(self) -> str:
        return """
<div class="dsa-badge" style="background:#003399;color:white;padding:15px;border-radius:8px;text-align:center;margin:30px 0;border:2px solid #001a66;">
    🇪🇺 DSA Compliant Gateway (European Union)<br>
    <a href="/copyright/report" style="color:white;text-decoration:underline;">Report Illegal Content</a> | 
    <a href="/transparency" style="color:white;text-decoration:underline;">Transparency Report</a> | 
    <a href="/dsa-complaint" style="color:white;text-decoration:underline;">File Complaint</a><br>
    <small>Regulation (EU) 2022/2065 compliant</small>
</div>
"""
    
    def get_takedown_reasons(self) -> Dict[str, str]:
        return {
            'copyright': 'Copyright Infringement',
            'illegal_content': 'Illegal Content (DSA)',
            'hate_speech': 'Hate Speech',
            'csam': 'Child Sexual Abuse Material',
            'terrorism': 'Terrorist Content'
        }
    
    def get_blocked_page_text(self, reason: str, language: str = 'en') -> Dict[str, str]:
        if language == 'pl':
            return {
                'title': '451 - Treść niedostępna z przyczyn prawnych',
                'message': 'Ta treść została zablokowana zgodnie z Digital Services Act (DSA).',
                'reason': reason,
                'law': 'Rozporządzenie (UE) 2022/2065',
                'action': 'Jeśli uważasz, że usunięcie było błędne, możesz złożyć skargę.',
                'link': '/dsa-complaint'
            }
        else:
            return {
                'title': '451 - Content Unavailable For Legal Reasons',
                'message': 'This content has been blocked under the Digital Services Act (DSA).',
                'reason': reason,
                'law': 'Regulation (EU) 2022/2065',
                'action': 'If you believe this removal was incorrect, you may file a complaint.',
                'link': '/dsa-complaint'
            }
