"""
Base class for copyright compliance plugins.
Each country/region can implement its own plugin with specific legal requirements.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, List


class CopyrightPlugin(ABC):
    """Abstract base class for country-specific copyright compliance"""
    
    @property
    @abstractmethod
    def country_code(self) -> str:
        """ISO country code (e.g., 'US', 'PL', 'FR', 'EU')"""
        pass
    
    @property
    @abstractmethod
    def law_name(self) -> str:
        """Name of the copyright law/act (e.g., 'DMCA', 'DSA', 'Droit d'auteur')"""
        pass
    
    @property
    @abstractmethod
    def law_reference(self) -> str:
        """Legal reference (e.g., '17 U.S.C. § 512', 'Regulation 2022/2065')"""
        pass
    
    @abstractmethod
    def get_notice_template(self) -> str:
        """Return the copyright notice template in markdown format"""
        pass
    
    @abstractmethod
    def validate_notice(self, notice_data: Dict) -> tuple[bool, Optional[str]]:
        """
        Validate a copyright notice submission.
        Returns: (is_valid, error_message)
        """
        pass
    
    @abstractmethod
    def get_required_fields(self) -> List[str]:
        """Return list of required form fields for this jurisdiction"""
        pass
    
    @abstractmethod
    def get_sla_hours(self) -> int:
        """Return required response time in hours"""
        pass
    
    @abstractmethod
    def get_counter_notice_template(self) -> str:
        """Return counter-notice template for disputed takedowns"""
        pass
    
    @abstractmethod
    def get_footer_html(self) -> str:
        """Return HTML for website footer (compliance badge)"""
        pass
    
    @abstractmethod
    def get_takedown_reasons(self) -> Dict[str, str]:
        """
        Return dict of valid takedown reasons for this jurisdiction.
        Format: {'reason_code': 'Human-readable description'}
        """
        pass
    
    def format_notice_response(self, notice_data: Dict) -> str:
        """Format the response email/message for the complainant"""
        return f"""
Copyright Notice Received - {self.law_name}

Reference: {notice_data.get('reference_id', 'N/A')}
Jurisdiction: {self.country_code}
Response time: {self.get_sla_hours()} hours

We have received your notice and will review it according to {self.law_reference}.

You will receive a response within {self.get_sla_hours()} hours.
"""
    
    def get_blocked_page_text(self, reason: str, language: str = 'en') -> Dict[str, str]:
        """
        Get localized text for HTTP 451 blocked page.
        Returns dict with 'title', 'message', 'reason'
        """
        # Default English
        return {
            'title': '451 - Content Unavailable For Legal Reasons',
            'message': f'This content has been blocked under {self.law_name}.',
            'reason': reason,
            'law': self.law_reference
        }
