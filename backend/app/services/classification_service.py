"""
Query classification service (Phase 7, spec sections 19-22; extended
in Phase 11 for Hindi/Kannada -- spec section 5: "The user can... Ask
in Kannada... Ask in Hindi" and section 47's multilingual retrieval-
parity requirement).

Produces the classifier output shape from spec section 19:

    {
        "language": "en",
        "domain": "contract",
        "jurisdiction": "India",
        "state": None,
        "court": None,
        "query_type": "section_lookup",
        "ambiguity": False,          # filled in by ambiguity_service.py
        "confidence": 0.94,
    }

Keyword-based, not ML-based: with no labeled Indian-legal-query training
set to fit a real classifier on (and Rule 4 forbidding fabricated
evaluation results), a transparent keyword/pattern scorer is the honest
choice for a project this size. It's also easy to audit and extend --
adding a domain means adding a keyword list, not retraining anything.
Domain match doubles as the metadata `where={"domain": ...}` filter
retrieval_service.py applies, so keywords here should track the same
domain names used in data/raw/<domain>/ and chunk metadata (spec
section 7).

Confidence is a normalized keyword-hit score, not a calibrated
probability -- Rule 4 (no fabricated evaluation results) means this
module must never claim more precision than "how many domain keywords
matched, roughly how unique was the query's phrasing to one domain".

Phase 11 note on the Hindi/Kannada keyword lists below: these are
common, everyday legal-question vocabulary (not exhaustive legal
dictionaries) chosen the same high-precision way as the English lists
-- Rule 3/4 apply equally here, so no keyword was invented without
being a real, ordinary word for that concept in the language. Coverage
is intentionally narrower than English's (this project's primary
legal-source documents are in English -- spec section 17 -- so English
keyword coverage will always be the deepest); a Hindi/Kannada query
that matches nothing still falls through safely to
`domain=None, confidence=0.0`, which retrieval_service.py already
treats as "search everything" rather than a hard failure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.language_service import detect_language

# Keyword -> domain, per language. Order doesn't matter; every domain's
# list is scanned. Kept short and high-precision (terms fairly specific
# to that area of law) rather than exhaustive, since false-positive
# domain matches are worse for retrieval precision than an occasional
# miss that falls through to "general" (spec section 21: only
# prioritize a domain "when domain information is reliable").
DOMAIN_KEYWORDS_EN: dict[str, list[str]] = {
    "consumer": [
        "consumer", "defective product", "deficiency in service", "refund",
        "warranty", "consumer forum", "consumer court", "unfair trade practice",
        "e-commerce complaint", "product liability",
    ],
    "contract": [
        "contract", "agreement", "breach of contract", "offer and acceptance",
        "consideration", "void agreement", "voidable contract", "damages",
        "specific performance", "indemnity", "guarantee", "rental agreement",
        "lease agreement", "termination clause", "notice period",
    ],
    "cyber": [
        "cyber", "hacking", "identity theft", "data breach", "phishing",
        "online fraud", "cyberstalking", "information technology act",
        "digital signature", "cybercrime", "social media harassment online",
        "otp fraud", "online scam",
    ],
    "family": [
        "family", "family law", "divorce", "marriage", "alimony", "maintenance",
        "custody", "child custody", "adoption", "domestic violence", "dowry",
        "matrimonial", "separation", "hindu marriage act", "muslim personal law",
        "women safety", "harassment of women", "domestic dispute",
    ],
    "property": [
        "property", "land", "sale deed", "title deed", "tenant", "landlord",
        "eviction", "encroachment", "partition", "inheritance", "succession",
        "registration of property", "mutation", "real estate", "rera",
    ],
    "employment": [
        "employment", "employee", "employer", "termination of employment",
        "wrongful termination", "wages", "salary", "provident fund", "gratuity",
        "workplace harassment", "labour law", "labor law", "resignation",
        "notice period employment", "industrial dispute",
    ],
    "criminal": [
        "criminal", "crime", "fir", "police complaint", "criminal case", "bail",
        "arrest", "ipc", "bharatiya nyaya sanhita", "theft", "assault", "murder",
        "criminal offence", "criminal offense", "chargesheet", "cognizable",
    ],
    "constitutional": [
        "fundamental right", "constitution", "article 21", "article 14",
        "writ petition", "habeas corpus", "public interest litigation", "pil",
        "directive principles", "constitutional amendment",
    ],
    "corporate": [
        "company law", "companies act", "director", "shareholder",
        "incorporation", "board resolution", "corporate governance",
        "winding up", "merger", "acquisition", "startup registration",
    ],
    "intellectual_property": [
        "trademark", "copyright", "patent", "intellectual property",
        "design registration", "trade secret", "infringement of copyright",
        "geographical indication",
    ],
    "taxation": [
        "income tax", "gst", "tax notice", "tax return", "tds",
        "capital gains tax", "tax exemption", "tax evasion", "tax appeal",
    ],
    "environmental": [
        "environment", "pollution", "environmental clearance",
        "forest rights", "wildlife protection", "environmental impact",
        "national green tribunal",
    ],
    "banking": [
        "bank loan", "loan default", "cheque bounce", "section 138",
        "banking dispute", "npa", "recovery of loan", "rbi", "credit card dispute",
    ],
}

# Phase 11: Hindi (Devanagari) keyword lists -- everyday words for each
# concept, not a legal dictionary (see module docstring).
DOMAIN_KEYWORDS_HI: dict[str, list[str]] = {
    "consumer": [
        "उपभोक्ता", "खराब सामान", "रिफंड", "वापसी", "वारंटी",
        "उपभोक्ता फोरम", "उपभोक्ता अदालत", "अनुचित व्यापार",
    ],
    "contract": [
        "अनुबंध", "करार", "समझौता", "अनुबंध का उल्लंघन", "हर्जाना",
        "किराया समझौता", "पट्टा", "नोटिस अवधि", "जमानत राशि",
    ],
    "cyber": [
        "साइबर", "हैकिंग", "पहचान की चोरी", "डेटा चोरी", "फिशिंग",
        "ऑनलाइन धोखाधड़ी", "साइबर अपराध", "सूचना प्रौद्योगिकी अधिनियम",
        "ओटीपी धोखाधड़ी",
    ],
    "family": [
        "तलाक", "विवाह", "गुजारा भत्ता", "भरण पोषण", "बच्चे की कस्टडी",
        "गोद लेना", "घरेलू हिंसा", "दहेज", "अलगाव", "हिंदू विवाह अधिनियम",
    ],
    "property": [
        "संपत्ति", "जमीन", "बिक्री विलेख", "किरायेदार", "मकान मालिक",
        "बेदखली", "अतिक्रमण", "बंटवारा", "विरासत", "उत्तराधिकार",
        "संपत्ति पंजीकरण",
    ],
    "employment": [
        "रोजगार", "कर्मचारी", "नियोक्ता", "नौकरी से निकालना", "वेतन",
        "भविष्य निधि", "ग्रेच्युटी", "कार्यस्थल उत्पीड़न", "श्रम कानून",
        "इस्तीफा",
    ],
    "criminal": [
        "प्राथमिकी", "एफआईआर", "पुलिस शिकायत", "आपराधिक मामला", "जमानत",
        "गिरफ्तारी", "चोरी", "हमला", "हत्या", "आपराधिक अपराध",
    ],
    "constitutional": [
        "मौलिक अधिकार", "संविधान", "अनुच्छेद 21", "अनुच्छेद 14",
        "रिट याचिका", "बंदी प्रत्यक्षीकरण", "जनहित याचिका",
    ],
    "corporate": [
        "कंपनी कानून", "कंपनी अधिनियम", "निदेशक", "शेयरधारक",
        "निगमन", "बोर्ड प्रस्ताव", "विलय", "अधिग्रहण",
    ],
    "intellectual_property": [
        "ट्रेडमार्क", "कॉपीराइट", "पेटेंट", "बौद्धिक संपदा",
        "डिजाइन पंजीकरण", "व्यापार रहस्य",
    ],
    "taxation": [
        "आयकर", "जीएसटी", "कर नोटिस", "कर रिटर्न", "पूंजीगत लाभ कर",
        "कर छूट", "कर चोरी",
    ],
    "environmental": [
        "पर्यावरण", "प्रदूषण", "पर्यावरण मंजूरी", "वन अधिकार",
        "वन्यजीव संरक्षण", "राष्ट्रीय हरित अधिकरण",
    ],
    "banking": [
        "बैंक ऋण", "ऋण चूक", "चेक बाउंस", "धारा 138",
        "बैंकिंग विवाद", "ऋण वसूली", "क्रेडिट कार्ड विवाद",
    ],
}

# Phase 11: Kannada keyword lists -- same everyday-vocabulary approach.
DOMAIN_KEYWORDS_KN: dict[str, list[str]] = {
    "consumer": [
        "ಗ್ರಾಹಕ", "ದೋಷಪೂರಿತ ಉತ್ಪನ್ನ", "ಮರುಪಾವತಿ", "ಖಾತರಿ",
        "ಗ್ರಾಹಕ ವೇದಿಕೆ", "ಗ್ರಾಹಕ ನ್ಯಾಯಾಲಯ", "ಅನ್ಯಾಯ ವ್ಯಾಪಾರ",
    ],
    "contract": [
        "ಒಪ್ಪಂದ", "ಒಪ್ಪಂದದ ಉಲ್ಲಂಘನೆ", "ಪರಿಹಾರ", "ಬಾಡಿಗೆ ಒಪ್ಪಂದ",
        "ಗುತ್ತಿಗೆ", "ನೋಟಿಸ್ ಅವಧಿ", "ಖಾತರಿ ಪತ್ರ",
    ],
    "cyber": [
        "ಸೈಬರ್", "ಹ್ಯಾಕಿಂಗ್", "ಗುರುತಿನ ಕಳ್ಳತನ", "ಡೇಟಾ ಸೋರಿಕೆ",
        "ಫಿಶಿಂಗ್", "ಆನ್‌ಲೈನ್ ವಂಚನೆ", "ಸೈಬರ್ ಅಪರಾಧ",
        "ಮಾಹಿತಿ ತಂತ್ರಜ್ಞಾನ ಕಾಯ್ದೆ", "ಒಟಿಪಿ ವಂಚನೆ",
    ],
    "family": [
        "ವಿಚ್ಛೇದನ", "ಮದುವೆ", "ಜೀವನಾಂಶ", "ಮಕ್ಕಳ ಪಾಲನೆ", "ದತ್ತು",
        "ಕೌಟುಂಬಿಕ ಹಿಂಸೆ", "ವರದಕ್ಷಿಣೆ", "ಪ್ರತ್ಯೇಕತೆ", "ಹಿಂದೂ ವಿವಾಹ ಕಾಯ್ದೆ",
    ],
    "property": [
        "ಆಸ್ತಿ", "ಭೂಮಿ", "ಮಾರಾಟ ಪತ್ರ", "ಬಾಡಿಗೆದಾರ", "ಮನೆ ಮಾಲೀಕ",
        "ಒಕ್ಕಲೆಬ್ಬಿಸುವಿಕೆ", "ಒತ್ತುವರಿ", "ಪಾಲು", "ಉತ್ತರಾಧಿಕಾರ",
        "ಆಸ್ತಿ ನೋಂದಣಿ",
    ],
    "employment": [
        "ಉದ್ಯೋಗ", "ನೌಕರ", "ಉದ್ಯೋಗದಾತ", "ವಜಾ", "ಸಂಬಳ",
        "ಭವಿಷ್ಯ ನಿಧಿ", "ಗ್ರಾಚ್ಯುಟಿ", "ಕಾರ್ಯಸ್ಥಳ ಕಿರುಕುಳ", "ಕಾರ್ಮಿಕ ಕಾನೂನು",
        "ರಾಜೀನಾಮೆ",
    ],
    "criminal": [
        "ಎಫ್‌ಐಆರ್", "ಪೊಲೀಸ್ ದೂರು", "ಕ್ರಿಮಿನಲ್ ಪ್ರಕರಣ", "ಜಾಮೀನು",
        "ಬಂಧನ", "ಕಳ್ಳತನ", "ಹಲ್ಲೆ", "ಕೊಲೆ", "ಕ್ರಿಮಿನಲ್ ಅಪರಾಧ",
    ],
    "constitutional": [
        "ಮೂಲಭೂತ ಹಕ್ಕು", "ಸಂವಿಧಾನ", "ವಿಧಿ 21", "ವಿಧಿ 14",
        "ರಿಟ್ ಅರ್ಜಿ", "ಸಾರ್ವಜನಿಕ ಹಿತಾಸಕ್ತಿ ಅರ್ಜಿ",
    ],
    "corporate": [
        "ಕಂಪನಿ ಕಾನೂನು", "ಕಂಪನಿ ಕಾಯ್ದೆ", "ನಿರ್ದೇಶಕ", "ಷೇರುದಾರ",
        "ವಿಲೀನ", "ಸ್ವಾಧೀನ",
    ],
    "intellectual_property": [
        "ಟ್ರೇಡ್‌ಮಾರ್ಕ್", "ಹಕ್ಕುಸ್ವಾಮ್ಯ", "ಪೇಟೆಂಟ್", "ಬೌದ್ಧಿಕ ಆಸ್ತಿ",
    ],
    "taxation": [
        "ಆದಾಯ ತೆರಿಗೆ", "ಜಿಎಸ್‌ಟಿ", "ತೆರಿಗೆ ನೋಟಿಸ್", "ತೆರಿಗೆ ರಿಟರ್ನ್",
        "ಬಂಡವಾಳ ಲಾಭ ತೆರಿಗೆ", "ತೆರಿಗೆ ವಂಚನೆ",
    ],
    "environmental": [
        "ಪರಿಸರ", "ಮಾಲಿನ್ಯ", "ಪರಿಸರ ಅನುಮತಿ", "ಅರಣ್ಯ ಹಕ್ಕುಗಳು",
        "ವನ್ಯಜೀವಿ ಸಂರಕ್ಷಣೆ",
    ],
    "banking": [
        "ಬ್ಯಾಂಕ್ ಸಾಲ", "ಸಾಲ ಬಾಕಿ", "ಚೆಕ್ ಬೌನ್ಸ್", "ಸೆಕ್ಷನ್ 138",
        "ಬ್ಯಾಂಕಿಂಗ್ ವಿವಾದ", "ಸಾಲ ವಸೂಲಾತಿ",
    ],
}

_DOMAIN_KEYWORDS_BY_LANGUAGE: dict[str, dict[str, list[str]]] = {
    "en": DOMAIN_KEYWORDS_EN,
    "hi": DOMAIN_KEYWORDS_HI,
    "kn": DOMAIN_KEYWORDS_KN,
}

# Kept as the original name for backward compatibility with anything
# (tests, other modules) that imported the Phase 7 English-only table
# directly.
DOMAIN_KEYWORDS = DOMAIN_KEYWORDS_EN

QUERY_TYPE_PATTERNS_EN: dict[str, list[str]] = {
    "section_lookup": [r"\bsection\s+\d", r"\bwhat is section\b", r"\bunder section\b"],
    "penalty": [r"\bpunishment\b", r"\bpenalty\b", r"\bfine\b", r"\bimprisonment\b", r"\bjail\b"],
    "rights": [r"\brights?\b", r"\bentitled to\b"],
    "duties": [r"\bduty\b", r"\bduties\b", r"\bobligations?\b"],
    "legal_procedure": [
        r"\bhow (do|can) i (file|register|apply)\b", r"\bprocedure\b",
        r"\bprocess for\b", r"\bsteps to\b",
    ],
    "case_law": [r"\bcase law\b", r"\bjudgment\b", r"\bjudgement\b", r"\bprecedent\b", r"\bv\.\s"],
    "document_analysis": [r"\bthis (document|agreement|contract|file)\b", r"\buploaded\b"],
    "contract_analysis": [r"\bthis contract\b", r"\bthis agreement\b", r"\bnotice period mentioned\b"],
    "legal_definition": [r"\bwhat is\b", r"\bdefine\b", r"\bmeaning of\b", r"\bwhat does .* mean\b"],
}

# Phase 11: Hindi/Kannada query-type patterns. Narrower than English's
# (fewer synonyms known to be common/high-precision) -- a query that
# matches none of these still safely falls through to
# "general_legal_information", the same default English gets.
QUERY_TYPE_PATTERNS_HI: dict[str, list[str]] = {
    "section_lookup": [r"धारा\s*\d", r"धारा\s+क्या है"],
    "penalty": [r"सजा", r"दंड", r"जुर्माना", r"कारावास"],
    "rights": [r"अधिकार"],
    "duties": [r"कर्तव्य", r"दायित्व"],
    "legal_procedure": [r"कैसे.*(दर्ज|आवेदन)", r"प्रक्रिया", r"तरीका"],
    "case_law": [r"मामला कानून", r"निर्णय", r"फैसला"],
    "document_analysis": [r"इस (दस्तावेज़|समझौते|अनुबंध)", r"अपलोड"],
    "legal_definition": [r"क्या है", r"मतलब", r"परिभाषा"],
}

QUERY_TYPE_PATTERNS_KN: dict[str, list[str]] = {
    "section_lookup": [r"ಸೆಕ್ಷನ್\s*\d", r"ಸೆಕ್ಷನ್\s+ಎಂದರೇನು"],
    "penalty": [r"ಶಿಕ್ಷೆ", r"ದಂಡ", r"ಜೈಲು"],
    "rights": [r"ಹಕ್ಕು"],
    "duties": [r"ಕರ್ತವ್ಯ", r"ಜವಾಬ್ದಾರಿ"],
    "legal_procedure": [r"ಹೇಗೆ.*(ದಾಖಲಿಸ|ಅರ್ಜಿ)", r"ಪ್ರಕ್ರಿಯೆ", r"ಕ್ರಮಗಳು"],
    "case_law": [r"ಪ್ರಕರಣ ಕಾನೂನು", r"ತೀರ್ಪು"],
    "document_analysis": [r"ಈ (ದಾಖಲೆ|ಒಪ್ಪಂದ)", r"ಅಪ್‌ಲೋಡ್"],
    "legal_definition": [r"ಎಂದರೇನು", r"ಅರ್ಥ"],
}

_QUERY_TYPE_PATTERNS_BY_LANGUAGE: dict[str, dict[str, list[str]]] = {
    "en": QUERY_TYPE_PATTERNS_EN,
    "hi": QUERY_TYPE_PATTERNS_HI,
    "kn": QUERY_TYPE_PATTERNS_KN,
}

QUERY_TYPE_PATTERNS = QUERY_TYPE_PATTERNS_EN  # backward-compat alias

INDIAN_STATES_EN = [
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya",
    "mizoram", "nagaland", "odisha", "punjab", "rajasthan", "sikkim",
    "tamil nadu", "telangana", "tripura", "uttar pradesh", "uttarakhand",
    "west bengal", "delhi",
]

# Phase 11: the states most likely to actually appear in an Indian-
# legal-assistant query (spec section 22's own example is Karnataka),
# not an exhaustive 28-state translation -- narrower coverage here
# falls through safely to `state=None`, same as an English query
# naming a state not in the English list would.
_INDIAN_STATES_HI: dict[str, str] = {
    "कर्नाटक": "Karnataka", "महाराष्ट्र": "Maharashtra", "दिल्ली": "Delhi",
    "तमिलनाडु": "Tamil Nadu", "उत्तर प्रदेश": "Uttar Pradesh",
    "पश्चिम बंगाल": "West Bengal", "गुजरात": "Gujarat", "राजस्थान": "Rajasthan",
    "केरल": "Kerala", "पंजाब": "Punjab", "बिहार": "Bihar",
    "तेलंगाना": "Telangana", "आंध्र प्रदेश": "Andhra Pradesh",
}

_INDIAN_STATES_KN: dict[str, str] = {
    "ಕರ್ನಾಟಕ": "Karnataka", "ಮಹಾರಾಷ್ಟ್ರ": "Maharashtra", "ದೆಹಲಿ": "Delhi",
    "ತಮಿಳುನಾಡು": "Tamil Nadu", "ಉತ್ತರ ಪ್ರದೇಶ": "Uttar Pradesh",
    "ಪಶ್ಚಿಮ ಬಂಗಾಳ": "West Bengal", "ಗುಜರಾತ್": "Gujarat",
    "ರಾಜಸ್ಥಾನ": "Rajasthan", "ಕೇರಳ": "Kerala", "ಪಂಜಾಬ್": "Punjab",
    "ಬಿಹಾರ": "Bihar", "ತೆಲಂಗಾಣ": "Telangana", "ಆಂಧ್ರ ಪ್ರದೇಶ": "Andhra Pradesh",
}


@dataclass
class QueryClassification:
    language: str
    domain: str | None
    domain_confidence: float
    jurisdiction: str
    state: str | None
    court: str | None
    query_type: str
    ambiguity: bool = False  # set by ambiguity_service.py, not here
    confidence: float = 0.0

    def as_dict(self) -> dict:
        return {
            "language": self.language,
            "domain": self.domain,
            "jurisdiction": self.jurisdiction,
            "state": self.state,
            "court": self.court,
            "query_type": self.query_type,
            "ambiguity": self.ambiguity,
            "confidence": self.confidence,
        }


def _classify_domain(text_lower: str, language: str) -> tuple[str | None, float]:
    keyword_table = _DOMAIN_KEYWORDS_BY_LANGUAGE.get(language, DOMAIN_KEYWORDS_EN)
    scores: dict[str, int] = {}
    for domain, keywords in keyword_table.items():
        hits = sum(1 for kw in keywords if kw in text_lower)
        if hits:
            scores[domain] = hits
    if not scores:
        return None, 0.0
    best_domain = max(scores, key=scores.get)
    top_hits = scores[best_domain]
    # Normalize against total keyword hits across all domains so a query
    # that clearly matches one domain and nothing else scores near 1.0,
    # while one that weakly matches several domains scores lower --
    # that lower score is exactly the "insufficient confidence" signal
    # ambiguity_service.py checks for a query mentioning e.g. both
    # "employment" and "contract" terms.
    total_hits = sum(scores.values())
    confidence = top_hits / total_hits if total_hits else 0.0
    return best_domain, round(confidence, 2)


def _classify_query_type(text: str, language: str) -> str:
    pattern_table = _QUERY_TYPE_PATTERNS_BY_LANGUAGE.get(language, QUERY_TYPE_PATTERNS_EN)
    # Hindi/Kannada patterns match against the original-case text (no
    # Devanagari/Kannada script has case), English patterns against
    # lowercased text as before.
    haystack = text.lower() if language == "en" else text
    for query_type, patterns in pattern_table.items():
        for pattern in patterns:
            if re.search(pattern, haystack):
                return query_type
    return "general_legal_information"


def _detect_jurisdiction(text: str, language: str) -> tuple[str, str | None, str | None]:
    """Returns (jurisdiction, state, court). Jurisdiction defaults to
    "India" (Rule: spec section 22 says never assume a specific state
    when none is mentioned, but every legal question in this project's
    scope is still within Indian jurisdiction generally)."""
    if language == "hi":
        state = next((v for k, v in _INDIAN_STATES_HI.items() if k in text), None)
        court = "Supreme Court" if "उच्चतम न्यायालय" in text else ("High Court" if "उच्च न्यायालय" in text else None)
        return "India", state, court
    if language == "kn":
        state = next((v for k, v in _INDIAN_STATES_KN.items() if k in text), None)
        court = "Supreme Court" if "ಸುಪ್ರೀಂ ಕೋರ್ಟ್" in text else ("High Court" if "ಹೈಕೋರ್ಟ್" in text else None)
        return "India", state, court

    text_lower = text.lower()
    state = next((s.title() for s in INDIAN_STATES_EN if s in text_lower), None)
    court = None
    if "supreme court" in text_lower:
        court = "Supreme Court"
    elif "high court" in text_lower:
        court = "High Court"
    return "India", state, court


def classify_query(message: str) -> QueryClassification:
    language = detect_language(message)
    text_lower = message.lower()
    domain, domain_confidence = _classify_domain(
        text_lower if language == "en" else message, language,
    )
    query_type = _classify_query_type(message, language)
    jurisdiction, state, court = _detect_jurisdiction(message, language)

    return QueryClassification(
        language=language,
        domain=domain,
        domain_confidence=domain_confidence,
        jurisdiction=jurisdiction,
        state=state,
        court=court,
        query_type=query_type,
        confidence=domain_confidence,
    )
