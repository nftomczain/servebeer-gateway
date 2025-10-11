# Copyright Plugin System

Multi-jurisdiction copyright compliance system for IPFS gateways.

## Features

- 🌍 **Multi-jurisdiction support** - US (DMCA), EU (DSA), France, Poland
- 📋 **Jurisdiction-specific forms** - Tailored to local legal requirements
- ⚖️ **Automatic validation** - Ensures all required fields per jurisdiction
- 🔄 **Hot-swappable** - Change jurisdiction without restart
- 🌐 **Localized** - Country-specific language and requirements
- 📊 **Extensible** - Easy to add new countries

## Available Plugins

| Code | Jurisdiction | Law | SLA |
|------|-------------|-----|-----|
| **US** | United States | DMCA (17 U.S.C. § 512) | 48h |
| **EU** | European Union | DSA (Regulation 2022/2065) | 24h |
| **FR** | France | Code de la propriété intellectuelle | 72h |
| **PL** | Poland | Ustawa o prawie autorskim | 72h |

## Installation

The plugin system is included in the main application. No additional installation required.

```bash
# Ensure copyright_plugins directory exists
mkdir -p copyright_plugins

# All plugin files should be in copyright_plugins/
ls copyright_plugins/
# Output:
# __init__.py
# base.py
# manager.py
# us_dmca.py
# eu_dsa.py
# fr_droit_auteur.py
# pl_prawa_autorskie.py
```

## Configuration

Set your jurisdiction in `.env`:

```bash
# US (default)
COPYRIGHT_COUNTRY=US

# European Union
COPYRIGHT_COUNTRY=EU

# France
COPYRIGHT_COUNTRY=FR

# Poland
COPYRIGHT_COUNTRY=PL
```

## Usage

### Check Active Jurisdiction

```bash
curl https://ipfs.servebeer.com/health
```

Response includes:
```json
{
  "copyright_jurisdiction": "US",
  ...
}
```

### List Available Jurisdictions

```bash
curl https://ipfs.servebeer.com/admin/list-jurisdictions
```

Response:
```json
{
  "available": {
    "US": "DMCA (Digital Millennium Copyright Act)",
    "EU": "DSA (Digital Services Act)",
    "FR": "Droit d'auteur (CPI)",
    "PL": "Ustawa o prawie autorskim i prawach pokrewnych"
  },
  "active": "US"
}
```

### Change Jurisdiction (Admin)

```bash
# Switch to EU
curl -X POST https://ipfs.servebeer.com/admin/set-jurisdiction/EU

# Switch to France
curl -X POST https://ipfs.servebeer.com/admin/set-jurisdiction/FR
```

Response:
```json
{
  "status": "success",
  "country": "FR",
  "law": "Droit d'auteur (CPI)",
  "reference": "Code de la propriété intellectuelle (Articles L111-1 à L343-7)"
}
```

### View Copyright Policy

```bash
# Browser or curl
https://ipfs.servebeer.com/copyright
```

Shows jurisdiction-specific:
- Notice template
- Required fields
- Legal references
- Report form link

### Submit Copyright Report

```bash
https://ipfs.servebeer.com/copyright/report
```

Form adapts to active jurisdiction with proper required fields.

## Key Differences by Jurisdiction

### US (DMCA)
- **Focus:** Safe harbor protection
- **Requirements:** Strict field validation, under penalty of perjury
- **Unique:** Counter-notice system with 10-14 day restore period
- **False claims:** Civil liability under 17 U.S.C. § 512(f)

### EU (DSA)
- **Focus:** Illegal content transparency
- **Requirements:** Less strict than DMCA
- **Unique:** Statement of Reasons required, right to complain
- **False claims:** No specific penalty mentioned in template

### France
- **Focus:** Moral rights + economic rights
- **Requirements:** Separate declarations for moral/economic rights
- **Unique:** Moral rights are **perpetual, inalienable, and imprescriptible**
- **False claims:** Article 226-10 Penal Code (false denunciation)

### Poland
- **Focus:** Creator's personal and economic rights
- **Requirements:** Awareness of criminal liability statement
- **Unique:** Personal rights (prawa osobiste) are **non-transferable**
- **False claims:** Article 233 § 1 Criminal Code (up to 3 years imprisonment)

## Creating a New Plugin

To add support for a new country:

1. Create new file: `copyright_plugins/xx_name.py`
2. Inherit from `CopyrightPlugin`
3. Implement all required methods:

```python
from typing import Dict, Optional, List
from .base import CopyrightPlugin

class YourCountryPlugin(CopyrightPlugin):
    @property
    def country_code(self) -> str:
        return "XX"  # ISO code
    
    @property
    def law_name(self) -> str:
        return "Your Copyright Act"
    
    @property
    def law_reference(self) -> str:
        return "Legal citation"
    
    def get_required_fields(self) -> List[str]:
        return ['field1', 'field2', ...]
    
    def get_notice_template(self) -> str:
        return """
        # Your template in markdown
        """
    
    def validate_notice(self, notice_data: Dict) -> tuple[bool, Optional[str]]:
        # Validation logic
        return True, None
    
    def get_sla_hours(self) -> int:
        return 48
    
    # ... implement remaining methods
```

4. Plugin auto-loads on next restart

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/copyright` | GET | View policy for active jurisdiction |
| `/copyright/report` | GET/POST | Submit copyright report |
| `/admin/list-jurisdictions` | GET | List all available plugins |
| `/admin/set-jurisdiction/{code}` | POST | Change active jurisdiction |

## Testing

```bash
# Test US DMCA
curl -X POST https://ipfs.servebeer.com/admin/set-jurisdiction/US
curl https://ipfs.servebeer.com/copyright

# Test EU DSA
curl -X POST https://ipfs.servebeer.com/admin/set-jurisdiction/EU
curl https://ipfs.servebeer.com/copyright

# Test France
curl -X POST https://ipfs.servebeer.com/admin/set-jurisdiction/FR
curl https://ipfs.servebeer.com/copyright

# Test Poland
curl -X POST https://ipfs.servebeer.com/admin/set-jurisdiction/PL
curl https://ipfs.servebeer.com/copyright
```

Each should show different:
- Legal references
- Required fields
- Notice templates
- Footer badges

## Blocked Content

When content is blocked, the HTTP 451 page uses localized text from the active plugin:

```python
# Automatic language detection
blocked_text = plugin.get_blocked_page_text(reason, language='pl')
```

Returns jurisdiction-appropriate message with:
- Legal reference
- Reason for blocking
- Appeal/complaint procedure
- Contact information

## Legal Disclaimer

**Important:** This plugin system provides templates and validation logic based on our understanding of various copyright laws. However:

- We are not lawyers
- Laws change frequently
- Each deployment should be reviewed by a lawyer familiar with:
  - Your specific jurisdiction
  - Your hosting location
  - Your user base location
  - Applicable international treaties

**Operators are responsible for ensuring their deployment complies with applicable law.**

## Contributing

To contribute a new jurisdiction plugin:

1. Research the local copyright law thoroughly
2. Consult with a lawyer if possible
3. Create the plugin following the template above
4. Test all validation logic
5. Submit a pull request with:
   - Plugin code
   - Documentation of legal requirements
   - Example valid notice
   - Sources/references

## Support

- **Legal questions:** Consult a lawyer in your jurisdiction
- **Technical issues:** Open a GitHub issue
- **Plugin requests:** Open a GitHub issue with jurisdiction details

---

**Philosophy:** Global IPFS gateways need local copyright compliance. One size does not fit all.
