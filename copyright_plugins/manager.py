"""
Copyright Plugin Manager
Automatically loads and manages country-specific copyright plugins.
"""

import os
import importlib
import logging
from typing import Dict, Optional
from .base import CopyrightPlugin


class CopyrightPluginManager:
    """Manages copyright compliance plugins for different jurisdictions"""
    
    def __init__(self, default_country: str = "US"):
        self.plugins: Dict[str, CopyrightPlugin] = {}
        self.active_plugin: Optional[CopyrightPlugin] = None
        self.default_country = default_country
        self.load_plugins()
        self.set_country(default_country)
    
    def load_plugins(self):
        """Automatically discover and load all plugins"""
        plugins_dir = os.path.dirname(__file__)
        
        for filename in os.listdir(plugins_dir):
            if filename.endswith('.py') and filename not in ['__init__.py', 'base.py', 'manager.py']:
                module_name = filename[:-3]
                
                try:
                    module = importlib.import_module(f'copyright_plugins.{module_name}')
                    
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, CopyrightPlugin) and 
                            attr != CopyrightPlugin):
                            
                            plugin = attr()
                            self.plugins[plugin.country_code] = plugin
                            logging.info(f"✅ Loaded copyright plugin: {plugin.country_code} ({plugin.law_name})")
                
                except Exception as e:
                    logging.error(f"❌ Failed to load plugin {module_name}: {e}")
    
    def set_country(self, country_code: str) -> bool:
        """Set the active country/jurisdiction"""
        country_code = country_code.upper()
        
        if country_code in self.plugins:
            self.active_plugin = self.plugins[country_code]
            logging.info(f"🌍 Active copyright jurisdiction: {country_code} - {self.active_plugin.law_name}")
            return True
        else:
            logging.warning(f"⚠️  No plugin for {country_code}, using default: {self.default_country}")
            if self.default_country in self.plugins:
                self.active_plugin = self.plugins[self.default_country]
                return False
            else:
                logging.error(f"❌ Default country {self.default_country} plugin not found!")
                return False
    
    def get_active(self) -> Optional[CopyrightPlugin]:
        """Get the currently active plugin"""
        return self.active_plugin
    
    def get_plugin(self, country_code: str) -> Optional[CopyrightPlugin]:
        """Get a specific plugin by country code"""
        return self.plugins.get(country_code.upper())
    
    def list_available(self) -> Dict[str, str]:
        """List all available jurisdictions"""
        return {
            code: plugin.law_name 
            for code, plugin in self.plugins.items()
        }
    
    def validate_notice(self, notice_data: Dict) -> tuple[bool, Optional[str]]:
        """Validate notice using active plugin"""
        if not self.active_plugin:
            return False, "No copyright plugin active"
        
        return self.active_plugin.validate_notice(notice_data)
    
    def get_notice_template(self) -> str:
        """Get notice template from active plugin"""
        if not self.active_plugin:
            return "No copyright plugin active"
        
        return self.active_plugin.get_notice_template()
    
    def get_footer_html(self) -> str:
        """Get footer HTML from active plugin"""
        if not self.active_plugin:
            return ""
        
        return self.active_plugin.get_footer_html()
