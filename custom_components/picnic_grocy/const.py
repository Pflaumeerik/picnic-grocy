"""Constants for the Picnic → Grocy integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "picnic_grocy"

# Config entry data
CONF_COUNTRY: Final = "country"
CONF_AUTH_TOKEN: Final = "auth_token"
CONF_GROCY_URL: Final = "grocy_url"
CONF_GROCY_API_KEY: Final = "grocy_api_key"
CONF_2FA_CHANNEL: Final = "channel"
CONF_2FA_CODE: Final = "code"

COUNTRIES: Final = ["DE", "NL", "FR"]
DEFAULT_GROCY_URL: Final = "http://a0d7b954-grocy"

# Options
OPT_AUTO_IMPORT: Final = "auto_import"
OPT_DRY_RUN: Final = "dry_run"
OPT_CREATE_PRODUCTS: Final = "create_missing_products"
OPT_MATCH_BY_NAME: Final = "match_by_name"
OPT_LOCATION_ID: Final = "location_id"
OPT_LOCATION_CHILLED_ID: Final = "location_chilled_id"
OPT_FRESH_GROUP_ID: Final = "fresh_product_group_id"
OPT_QU_ID: Final = "quantity_unit_id"
OPT_BBD_PERISHABLE: Final = "best_before_days_perishable"
OPT_BBD_DURABLE: Final = "best_before_days_durable"
OPT_SKIP_KEYWORDS: Final = "skip_keywords"
OPT_DAILY_TIME: Final = "daily_time"
OPT_DELIVERY_SENSOR: Final = "delivery_sensor"
DEFAULT_DAILY_TIME: Final = "20:00:00"
OPT_FRESH_KEYWORDS: Final = "fresh_keywords"

DEFAULT_OPTIONS: Final = {
    OPT_AUTO_IMPORT: True,
    OPT_DRY_RUN: True,
    OPT_CREATE_PRODUCTS: True,
    OPT_MATCH_BY_NAME: True,
    OPT_BBD_PERISHABLE: 7,
    OPT_BBD_DURABLE: 180,
    OPT_SKIP_KEYWORDS: "Pfand, Tüte, Tasche",
    OPT_DAILY_TIME: DEFAULT_DAILY_TIME,
    OPT_FRESH_KEYWORDS: (
        "Tomate, Gurke, Paprika, Champignon, Pilz, Rucola, Salat, Spinat, "
        "Zucchini, Aubergine, Brokkoli, Blumenkohl, Möhre, Karotte, Lauch, "
        "Zwiebel, Kräuter, Banane, Apfel, Äpfel, Birne, Traube, Beere, Physalis, "
        "Zitrone, Limette, Orange, Mandarine, Clementine, Kiwi, Mango, Avocado, "
        "Ananas, Melone, Brot, Brötchen, "
        "-passiert, -getrocknet, -Saft, -Chips, -Dose, -in Öl, -Mark"
    ),
}

# After Picnic reports a delivery, the invoice e-mail (and with it the
# COMPLETED status) can take a while: check again after these delays.
FOLLOW_UP_DELAYS: Final = (
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=3),
    timedelta(hours=6),
)
PICNIC_DELIVERY_UNIQUE_SUFFIX: Final = ".last_order_delivery_time"

BARCODE_PREFIX: Final = "picnic:"

EVENT_IMPORTED: Final = f"{DOMAIN}_imported"

SERVICE_IMPORT_DELIVERY: Final = "import_delivery"
ATTR_DELIVERY_ID: Final = "delivery_id"
ATTR_DRY_RUN: Final = "dry_run"
ATTR_DEBUG: Final = "debug"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"

STORAGE_VERSION: Final = 1
