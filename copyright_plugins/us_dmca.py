"""
USA DMCA (Digital Millennium Copyright Act) Plugin
17 U.S.C. § 512 - Safe Harbor Provisions
"""

from typing import Dict, Optional, List
from .base import CopyrightPlugin


class USDMCAPlugin(CopyrightPlugin):
    """DMCA compliance plugin for United States"""
    
    @property
    def country_code(self) -> str:
        return "US"
    
    @property
    def law_name(self) -> str:
        return "DMCA (Digital Millennium Copyright Act)"
    
    @property
    def law_reference(self) -> str:
        return "17 U.S.C. § 512"
    
    def get_required_fields(self) -> List[str]:
        return [
            'copyright_owner',
            'contact_email',
            'contact_address',
            'contact_phone',
            'infringing_cid',
            'copyrighted_work_description',
            'good_faith_statement',
            'accuracy_statement',
            'signature'
        ]
    
    def get_notice_template(self) -> str:
        return """
# DMCA Takedown Notice

## Required Information Under 17 U.S.C. § 512(c)(3)

### 1. Identification of Copyrighted Work
- **Title:** [Title of your copyrighted work]
- **Author:** [Author name]
- **Copyright Registration Number:** [If available]
- **Description:** [Detailed description of the copyrighted work]

### 2. Identification of Infringing Material
- **IPFS CID:** `ipfs://...`
- **Gateway URL:** `https://gateway.example.com/ipfs/...`
- **Description:** [How the material infringes your copyright]

### 3. Contact Information
- **Full Legal Name:** [Your name or company name]
- **Physical Address:** [Street address, city, state, ZIP]
- **Email Address:** [your@email.com]
- **Phone Number:** [Your phone number]

### 4. Good Faith Statement
*"I have a good faith belief that use of the copyrighted material described above in the manner complained of is not authorized by the copyright owner, its agent, or the law."*

☐ I agree to this statement

### 5. Accuracy Statement (Under Penalty of Perjury)
*"The information in this notification is accurate, and under penalty of perjury, I am the copyright owner or authorized to act on behalf of the owner of an exclusive right that is allegedly infringed."*

☐ I agree to this statement under penalty of perjury

### 6. Signature
- **Physical or Electronic Signature:** [Your signature]
- **Date:** [Date of submission]

---

**Important:** False claims may result in liability for damages, costs, and attorney's fees under 17 U.S.C. § 512(f).

**Response Time:** We will respond within 48 hours.
"""
    
    def validate_notice(self, notice_data: Dict) -> tuple[bool, Optional[str]]:
        """Validate DMCA notice requirements"""
        
        # Check all required fields
        for field in self.get_required_fields():
            if not notice_data.get(field):
                return False, f"Missing required field: {field}"
        
        # Validate CID format
        cid = notice_data.get('infringing_cid', '')
        if not (cid.startswith('Qm') or cid.startswith('bafy') or cid.startswith('k51')):
            return False, "Invalid IPFS CID format"
        
        # Validate email
        email = notice_data.get('contact_email', '')
        if '@' not in email or '.' not in email:
            return False, "Invalid email address"
        
        # Check good faith statement
        if not notice_data.get('good_faith_statement'):
            return False, "Good faith statement is required"
        
        # Check accuracy statement (under penalty of perjury)
        if not notice_data.get('accuracy_statement'):
            return False, "Accuracy statement under penalty of perjury is required"
        
        # Check signature
        if not notice_data.get('signature'):
            return False, "Physical or electronic signature is required"
        
        return True, None
    
    def get_sla_hours(self) -> int:
        return 48  # DMCA requires "expeditious" removal
    
    def get_counter_notice_template(self) -> str:
        return """
# DMCA Counter-Notice

## Under 17 U.S.C. § 512(g)

### 1. Identification of Removed Material
- **CID:** [The CID that was removed]
- **Original URL:** [Original gateway URL]
- **Date of Removal:** [When it was removed]

### 2. Your Contact Information
- **Name:** [Your full name]
- **Address:** [Your physical address]
- **Phone:** [Your phone number]
- **Email:** [Your email address]

### 3. Statement Under Penalty of Perjury
*"I swear, under penalty of perjury, that I have a good faith belief that the material was removed or disabled as a result of mistake or misidentification of the material to be removed or disabled."*

☐ I agree under penalty of perjury

### 4. Consent to Jurisdiction
*"I consent to the jurisdiction of Federal District Court for the judicial district in which my address is located, or if my address is outside of the United States, for any judicial district in which the service provider may be found, and I will accept service of process from the person who provided the original DMCA notice or an agent of such person."*

☐ I agree to this statement

### 5. Signature
- **Signature:** [Your signature]
- **Date:** [Date]

---

**Processing Time:** Content may be restored in 10-14 business days unless the original complainant files a court action.
"""
    
    def get_footer_html(self) -> str:
        return """
<div class="dmca-badge" style="background:#e74c3c;color:white;padding:15px;border-radius:8px;text-align:center;margin:30px 0;border:2px solid #c0392b;">
    📋 DMCA Compliant Gateway (USA)<br>
    <a href="/copyright/report" style="color:white;text-decoration:underline;font-weight:bold;">Report Copyright Infringement</a><br>
    <small>Protected by 17 U.S.C. § 512 Safe Harbor provisions</small>
</div>
"""
    
    def get_takedown_reasons(self) -> Dict[str, str]:
        return {
            'dmca': 'DMCA Takedown Notice',
            'copyright': 'Copyright Infringement',
            'trademark': 'Trademark Infringement'
        }
    
    def get_blocked_page_text(self, reason: str, language: str = 'en') -> Dict[str, str]:
        return {
            'title': '451 - Content Unavailable For Legal Reasons',
            'message': 'This content has been removed in response to a DMCA takedown notice.',
            'reason': reason,
            'law': '17 U.S.C. § 512',
            'action': 'If you believe this removal was in error, you may file a DMCA counter-notice.',
            'link': '/copyright/counter-notice'
        }
