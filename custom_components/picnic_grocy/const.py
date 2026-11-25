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
OPT_QU_ID: Final = "quantity_unit_id"
OPT_BBD_PERISHABLE: Final = "best_before_days_perishable"
OPT_BBD_DURABLE: Final = "best_before_days_durable"
OPT_SKIP_KEYWORDS: Final = "skip_keywords"

DEFAULT_OPTIONS: Final = {
    OPT_AUTO_IMPORT: True,
    OPT_DRY_RUN: True,
    OPT_CREATE_PRODUCTS: True,
    OPT_MATCH_BY_NAME: True,
    OPT_BBD_PERISHABLE: 7,
    OPT_BBD_DURABLE: 180,
    OPT_SKIP_KEYWORDS: "Pfand, Tüte, Tasche",
}

UPDATE_INTERVAL: Final = timedelta(minutes=30)

BARCODE_PREFIX: Final = "picnic:"

EVENT_IMPORTED: Final = f"{DOMAIN}_imported"

SERVICE_IMPORT_DELIVERY: Final = "import_delivery"
ATTR_DELIVERY_ID: Final = "delivery_id"
ATTR_DRY_RUN: Final = "dry_run"
ATTR_DEBUG: Final = "debug"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"

STORAGE_VERSION: Final = 1
