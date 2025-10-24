DOMAIN = "vikunja_voice_assistant"
OLD_DOMAIN = "vikunja"  # For migration from old installations
CONF_VIKUNJA_URL = "vikunja_url"
CONF_VIKUNJA_API_KEY = "vikunja_api_key"
CONF_OPENAI_API_KEY = "openai_api_key"
CONF_DUE_DATE = "default_due_date"
CONF_VOICE_CORRECTION = "voice_correction"
CONF_AUTO_VOICE_LABEL = "auto_voice_label"
CONF_ENABLE_USER_ASSIGN = "enable_user_assignment"
USER_CACHE_FILENAME = "vikunja_users.json"
USER_CACHE_REFRESH_HOURS = 24  # default refresh cadence
DUE_DATE_OPTIONS = ["none", "tomorrow", "end_of_week", "end_of_month"]
CONF_DETAILED_RESPONSE = "detailed_response"
"""When true, detailed voice responses will include project, labels, due date, assignee, priority and repeat info automatically."""


DUE_DATE_OPTION_LABELS = {
    "none": {
        "en": "No default",
        "fr": "Aucun",
        "es": "Sin predeterminado",
        "pt": "Sem padrão",
        "ru": "Нет по умолчанию",
        "hi": "कोई डिफ़ॉल्ट नहीं",
        "zh-Hans": "无默认",
        "ar": "بدون افتراضي",
        "bn": "কোনো ডিফল্ট নয়",
        "id": "Tidak ada default",
    },
    "tomorrow": {
        "en": "Tomorrow",
        "fr": "Demain",
        "es": "Mañana",
        "pt": "Amanhã",
        "ru": "Завтра",
        "hi": "कल",
        "zh-Hans": "明天",
        "ar": "غدًا",
        "bn": "আগামীকাল",
        "id": "Besok",
    },
    "end_of_week": {
        "en": "End of week",
        "fr": "Fin de semaine",
        "es": "Fin de la semana",
        "pt": "Fim da semana",
        "ru": "Конец недели",
        "hi": "सप्ताह का अंत",
        "zh-Hans": "本周末",
        "ar": "نهاية الأسبوع",
        "bn": "সপ্তাহের শেষ",
        "id": "Akhir minggu",
    },
    "end_of_month": {
        "en": "End of month",
        "fr": "Fin du mois",
        "es": "Fin de mes",
        "pt": "Fim do mês",
        "ru": "Конец месяца",
        "hi": "महीने का अंत",
        "zh-Hans": "月底",
        "ar": "نهاية الشهر",
        "bn": "মাসের শেষ",
        "id": "Akhir bulan",
    },
}
