PHRASES = {
    "en": {
        "why": "Why?",
        "language": "Language",
        "english": "English",
        "nepali": "नेपाली",

        "crisis_title": "Crisis Support",
        "crisis_msg": (
            "If you are in immediate danger, contact emergency services.\n"
            "Police: 100 | Ambulance: 102\n"
            "Please reach out to a trusted person."
        ),

        "translation_note": "Note: Automatic translation may not be perfect."
    },

    "ne": {
        "why": "किन?",
        "language": "भाषा",
        "english": "English",
        "nepali": "नेपाली",

        "crisis_title": "आपतकालीन सहयोग",
        "crisis_msg": (
            "यदि तपाईं तत्काल खतरामा हुनुहुन्छ भने आपतकालीन सेवामा सम्पर्क गर्नुहोस्।\n"
            "प्रहरी: 100 | एम्बुलेन्स: 102\n"
            "कृपया विश्वासिलो व्यक्तिसँग कुरा गर्नुहोस्।"
        ),

        "translation_note": "सूचना: स्वचालित अनुवाद १००% सही नहुन सक्छ।"
    }
}

def t(key: str, lang: str = "en") -> str:
    return PHRASES.get(lang, PHRASES["en"]).get(key, key)
