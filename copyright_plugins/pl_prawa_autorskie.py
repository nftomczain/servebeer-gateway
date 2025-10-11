"""
Poland Copyright Law Plugin
Ustawa o prawie autorskim i prawach pokrewnych
"""

from typing import Dict, Optional, List
from .base import CopyrightPlugin


class PolandCopyrightPlugin(CopyrightPlugin):
    """Plugin for Polish copyright law"""
    
    @property
    def country_code(self) -> str:
        return "PL"
    
    @property
    def law_name(self) -> str:
        return "Ustawa o prawie autorskim i prawach pokrewnych"
    
    @property
    def law_reference(self) -> str:
        return "Dz.U. 1994 nr 24 poz. 83 z późn. zm."
    
    def get_required_fields(self) -> List[str]:
        return [
            'complainant_name',
            'contact_address',
            'contact_email',
            'contact_phone',
            'work_description',
            'infringing_cid',
            'justification',
            'good_faith_statement',
            'signature'
        ]
    
    def get_notice_template(self) -> str:
        return """
# Zgłoszenie naruszenia praw autorskich

## Ustawa o prawie autorskim i prawach pokrewnych (Polska)

### 1. Dane zgłaszającego
- **Imię i nazwisko / Nazwa podmiotu:** [Twoje dane]
- **Adres:** [Ulica, kod, miasto]
- **Email:** [twoj@email.pl]
- **Telefon:** [Numer telefonu]
- **Działam jako:** ☐ Twórca ☐ Podmiot praw pokrewnych ☐ Pełnomocnik

### 2. Opis utworu chronionego
- **Tytuł utworu:** [Tytuł]
- **Rodzaj utworu:** [Literacki, muzyczny, plastyczny, fotograficzny, programu komputerowego, etc.]
- **Data powstania:** [Data]
- **Numer zgłoszenia (jeśli dotyczy):** [Numer]
- **Szczegółowy opis:** [Opis utworu]

### 3. Wskazanie naruszenia
- **CID IPFS:** `ipfs://...`
- **URL:** `https://gateway.example.com/ipfs/...`
- **Opis naruszenia:** [W jaki sposób doszło do naruszenia]

### 4. Podstawa prawna roszczenia
**Prawa majątkowe (Art. 17 i nast.):**
- ☐ Prawo do rozporządzania i korzystania z utworu
- ☐ Prawo do wynagrodzenia za korzystanie

**Prawa osobiste (Art. 16):**
- ☐ Prawo do autorstwa utworu
- ☐ Prawo do oznaczenia utworu swoim nazwiskiem lub pseudonimem
- ☐ Prawo do nienaruszalności treści i formy utworu
- ☐ Prawo do decydowania o pierwszym udostępnieniu utworu publiczności
- ☐ Prawo do nadzoru nad sposobem korzystania z utworu

### 5. Uzasadnienie
[Szczegółowe wyjaśnienie, dlaczego uważasz że doszło do naruszenia]

### 6. Oświadczenie
*"Oświadczam, że podane informacje są prawdziwe i działam w dobrej wierze. Jestem uprawniony do reprezentowania właściciela praw autorskich lub praw pokrewnych."*

☐ Potwierdzam prawdziwość oświadczenia

### 7. Świadomość odpowiedzialności karnej
*"Jestem świadomy odpowiedzialności karnej za złożenie fałszywego oświadczenia (Art. 233 § 1 Kodeksu karnego - do 3 lat pozbawienia wolności)."*

☐ Jestem świadomy odpowiedzialności

### 8. Podpis
- **Podpis:** [Podpis elektroniczny lub własnoręczny]
- **Data:** [Data]
- **Miejsce:** [Miasto]

---

**Ważne informacje:**

- **Prawa osobiste:** Zgodnie z polskim prawem, prawa osobiste twórcy są **niezbywalne** i **nieograniczone w czasie** (Art. 16 ust. 2).
- **Odpowiedzialność karna:** Świadome składanie fałszywych zgłoszeń podlega karze do 3 lat pozbawienia wolności (Art. 233 k.k.).
- **Czas reakcji:** 72 godziny robocze

**Podstawa prawna:** Ustawa z dnia 4 lutego 1994 r. o prawie autorskim i prawach pokrewnych (Dz.U. 1994 nr 24 poz. 83 z późn. zm.)
"""
    
    def validate_notice(self, notice_data: Dict) -> tuple[bool, Optional[str]]:
        """Validate Polish copyright notice"""
        
        required = self.get_required_fields()
        for field in required:
            if not notice_data.get(field):
                return False, f"Brak wymaganego pola: {field}"
        
        # Validate CID
        cid = notice_data.get('infringing_cid', '')
        if not (cid.startswith('Qm') or cid.startswith('bafy') or cid.startswith('k51')):
            return False, "Nieprawidłowy format CID IPFS"
        
        # Validate email
        email = notice_data.get('contact_email', '')
        if '@' not in email or '.' not in email:
            return False, "Nieprawidłowy adres email"
        
        # Check good faith statement
        if not notice_data.get('good_faith_statement'):
            return False, "Wymagane jest oświadczenie o działaniu w dobrej wierze"
        
        return True, None
    
    def get_sla_hours(self) -> int:
        return 72  # 3 business days
    
    def get_counter_notice_template(self) -> str:
        return """
# Sprzeciw wobec usunięcia treści

## Prawo autorskie i prawa pokrewne (Polska)

### 1. Twoje dane
- **Imię i nazwisko:** [Twoje dane]
- **Adres:** [Adres]
- **Email:** [email@domena.pl]
- **Telefon:** [Numer]

### 2. Treść, której dotyczy sprzeciw
- **CID usuniętej treści:** [CID]
- **Data usunięcia:** [Data]
- **Numer referencyjny:** [Numer z powiadomienia]

### 3. Uzasadnienie sprzeciwu
[Wyjaśnij dlaczego uważasz, że usunięcie było nieuzasadnione]

**Możesz powołać się na:**
- ☐ Użytek osobisty (Art. 23)
- ☐ Prawo cytatu (Art. 29)
- ☐ Użytek w celach dydaktycznych (Art. 27)
- ☐ Parodia (Art. 29 ust. 1)
- ☐ Jesteś twórcą lub posiadaczem praw
- ☐ Utwór w domenie publicznej
- ☐ Inne: [Określ podstawę prawną]

### 4. Dowody
[Załącz ewentualne dowody wspierające Twoje stanowisko]

### 5. Oświadczenie
*"Oświadczam, że przysługuje mi prawo do publikacji tej treści i że nie narusza ona cudzych praw autorskich ani praw pokrewnych. Jestem świadomy odpowiedzialności karnej za złożenie fałszywego oświadczenia (Art. 233 § 1 k.k.)."*

☐ Potwierdzam

### 6. Podpis
- **Podpis:** [Podpis]
- **Data:** [Data]

---

**Czas rozpatrzenia:** 7 dni roboczych

**Dalsze kroki:** W przypadku negatywnej decyzji możesz skierować sprawę do sądu powszechnego.
"""
    
    def get_footer_html(self) -> str:
        return """
<div class="pl-copyright-badge" style="background:#dc143c;color:white;padding:15px;border-radius:8px;text-align:center;margin:30px 0;border:2px solid #a00000;">
    🇵🇱 Zgodność z polskim prawem autorskim<br>
    <a href="/copyright/report" style="color:white;text-decoration:underline;">Zgłoś naruszenie praw autorskich</a><br>
    <small>Ustawa o prawie autorskim i prawach pokrewnych (Dz.U. 1994 nr 24 poz. 83)</small>
</div>
"""
    
    def get_takedown_reasons(self) -> Dict[str, str]:
        return {
            'naruszenie_praw_autorskich': 'Naruszenie praw autorskich',
            'naruszenie_praw_osobistych': 'Naruszenie praw osobistych twórcy',
            'naruszenie_praw_pokrewnych': 'Naruszenie praw pokrewnych',
            'plagiat': 'Plagiat'
        }
    
    def get_blocked_page_text(self, reason: str, language: str = 'pl') -> Dict[str, str]:
        return {
            'title': '451 - Treść niedostępna z przyczyn prawnych',
            'message': 'Ta treść została zablokowana z powodu naruszenia polskiego prawa autorskiego.',
            'reason': reason,
            'law': 'Ustawa o prawie autorskim i prawach pokrewnych (Dz.U. 1994 nr 24 poz. 83)',
            'action': 'Jeśli uważasz, że usunięcie było nieuzasadnione, możesz złożyć sprzeciw.',
            'link': '/copyright/counter-notice',
            'note': 'Prawa osobiste twórcy są niezbywalne i nieograniczone w czasie (Art. 16 ust. 2)'
        }
