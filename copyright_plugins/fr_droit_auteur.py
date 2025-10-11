"""
France Droit d'auteur Plugin
Code de la propriété intellectuelle (CPI)
"""

from typing import Dict, Optional, List
from .base import CopyrightPlugin


class FranceDroitAuteurPlugin(CopyrightPlugin):
    """Plugin for French copyright law (droit d'auteur)"""
    
    @property
    def country_code(self) -> str:
        return "FR"
    
    @property
    def law_name(self) -> str:
        return "Droit d'auteur (CPI)"
    
    @property
    def law_reference(self) -> str:
        return "Code de la propriété intellectuelle (Articles L111-1 à L343-7)"
    
    def get_required_fields(self) -> List[str]:
        return [
            'author_name',
            'contact_email',
            'contact_address',
            'infringing_cid',
            'work_description',
            'moral_rights_statement',
            'economic_rights_statement',
            'good_faith_statement',
            'signature'
        ]
    
    def get_notice_template(self) -> str:
        return """
# Notification de violation du droit d'auteur

## Code de la propriété intellectuelle (France)

### 1. Identification de l'auteur
- **Nom de l'auteur:** [Votre nom]
- **Qualité:** ☐ Auteur ☐ Ayant droit ☐ Mandataire
- **Adresse:** [Votre adresse postale]
- **Email:** [votre@email.fr]
- **Téléphone:** [Votre numéro]

### 2. Description de l'œuvre protégée
- **Titre de l'œuvre:** [Titre]
- **Nature de l'œuvre:** [Livre, musique, image, vidéo, logiciel, etc.]
- **Date de création:** [Date]
- **Numéro de dépôt (si applicable):** [Numéro]
- **Description détaillée:** [Description de l'œuvre]

### 3. Localisation du contenu contrefaisant
- **CID IPFS:** `ipfs://...`
- **URL:** `https://gateway.example.com/ipfs/...`
- **Description de la contrefaçon:** [En quoi le contenu viole vos droits]

### 4. Droits patrimoniaux (Article L111-1)
*"Je suis titulaire des droits patrimoniaux sur cette œuvre, notamment les droits de reproduction et de représentation."*

☐ Je confirme être titulaire des droits patrimoniaux

### 5. Droits moraux (Article L121-1)
**Le droit moral comprend:**
- ☐ Droit de divulgation (L121-2)
- ☐ Droit au respect du nom (L121-1)
- ☐ Droit au respect de l'œuvre (L121-1)
- ☐ Droit de retrait ou de repentir (L121-4)

*"Je déclare que le contenu signalé porte atteinte à mes droits moraux sur l'œuvre."*

☐ Je confirme l'atteinte aux droits moraux

### 6. Déclaration de bonne foi
*"J'atteste sur l'honneur que les informations fournies sont exactes et que je suis bien titulaire des droits invoqués ou mandaté pour agir au nom du titulaire."*

☐ J'atteste de la véracité de ces informations

### 7. Signature
- **Signature:** [Signature électronique ou manuscrite]
- **Date:** [Date]
- **Lieu:** [Lieu]

---

**Important:** 

- **Droits moraux:** Contrairement au DMCA américain, le droit moral français est **perpétuel, inaliénable et imprescriptible** (Article L121-1).
- **Fausse déclaration:** Article 226-10 du Code pénal - la dénonciation calomnieuse est punissable.
- **Délai de traitement:** 48-72 heures

**Note:** Ce formulaire prend en compte les spécificités du droit français, notamment l'existence de droits moraux distincts des droits patrimoniaux.
"""
    
    def validate_notice(self, notice_data: Dict) -> tuple[bool, Optional[str]]:
        """Validate French copyright notice"""
        
        for field in self.get_required_fields():
            if not notice_data.get(field):
                return False, f"Champ requis manquant: {field}"
        
        # Validate CID
        cid = notice_data.get('infringing_cid', '')
        if not (cid.startswith('Qm') or cid.startswith('bafy') or cid.startswith('k51')):
            return False, "Format CID IPFS invalide"
        
        # Validate email
        email = notice_data.get('contact_email', '')
        if '@' not in email:
            return False, "Adresse email invalide"
        
        # Check moral rights statement (specific to French law)
        if not notice_data.get('moral_rights_statement'):
            return False, "La déclaration sur les droits moraux est requise (spécificité du droit français)"
        
        # Check economic rights
        if not notice_data.get('economic_rights_statement'):
            return False, "La déclaration sur les droits patrimoniaux est requise"
        
        return True, None
    
    def get_sla_hours(self) -> int:
        return 72  # 3 days - French law doesn't specify, but reasonable timeframe
    
    def get_counter_notice_template(self) -> str:
        return """
# Contestation de retrait - Droit d'auteur français

## Vous contestez un retrait de contenu

### 1. Vos informations
- **Nom:** [Votre nom]
- **Adresse:** [Votre adresse]
- **Email:** [votre@email.fr]
- **Téléphone:** [Votre numéro]

### 2. Contenu concerné
- **CID retiré:** [CID IPFS]
- **Date du retrait:** [Date]
- **Référence:** [Numéro de référence du retrait]

### 3. Motifs de contestation
[Expliquez pourquoi vous contestez ce retrait]

Vous pouvez invoquer:
- ☐ Exception de courte citation (Article L122-5)
- ☐ Exception pédagogique (Article L122-5)
- ☐ Parodie, pastiche, caricature (Article L122-5)
- ☐ Revue de presse (Article L122-5)
- ☐ Vous êtes l'auteur ou ayant droit
- ☐ Contenu dans le domaine public
- ☐ Autre: [Précisez]

### 4. Déclaration
*"J'atteste sur l'honneur de la véracité des informations communiquées et avoir un intérêt légitime à la publication de ce contenu."*

☐ J'atteste

### 5. Signature
- **Signature:** [Signature]
- **Date:** [Date]

---

**Délai de traitement:** 7 jours ouvrés

**Recours:** Si vous n'êtes pas satisfait de notre décision, vous pouvez saisir le tribunal judiciaire compétent.
"""
    
    def get_footer_html(self) -> str:
        return """
<div class="fr-copyright-badge" style="background:#0055A4;color:white;padding:15px;border-radius:8px;text-align:center;margin:30px 0;border:2px solid #003580;">
    🇫🇷 Conformité Droit d'auteur français<br>
    <a href="/copyright/report" style="color:white;text-decoration:underline;">Signaler une violation</a><br>
    <small>Code de la propriété intellectuelle - Articles L111-1 à L343-7</small><br>
    <small>Droits moraux: perpétuels, inaliénables et imprescriptibles</small>
</div>
"""
    
    def get_takedown_reasons(self) -> Dict[str, str]:
        return {
            'droit_auteur': 'Violation du droit d\'auteur',
            'droit_moral': 'Atteinte aux droits moraux',
            'contrefacon': 'Contrefaçon',
            'droit_voisin': 'Violation des droits voisins'
        }
    
    def get_blocked_page_text(self, reason: str, language: str = 'fr') -> Dict[str, str]:
        return {
            'title': '451 - Contenu indisponible pour des raisons légales',
            'message': 'Ce contenu a été bloqué en raison d\'une violation du droit d\'auteur français.',
            'reason': reason,
            'law': 'Code de la propriété intellectuelle',
            'action': 'Si vous pensez que ce retrait est erroné, vous pouvez contester la décision.',
            'link': '/copyright/counter-notice',
            'note': 'Note: Le droit moral français est perpétuel et inaliénable (Article L121-1 CPI)'
        }
