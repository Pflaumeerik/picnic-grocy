# Picnic → Grocy

Home Assistant integration that books your delivered [Picnic](https://picnic.app) groceries into [Grocy](https://grocy.info) – automatically, after every delivery.

> **Unofficial.** This project is not affiliated with Picnic. It uses Picnic's undocumented app API; if Picnic changes it, the import can stop working until the integration is updated.

🇩🇪 [Deutsche Anleitung weiter unten](#deutsch)

## How it works

1. Every 30 minutes the integration asks Picnic for **completed** deliveries. Picnic marks a delivery completed once the invoice e-mail is sent, so missing or substituted articles are already settled.
2. For each new delivery it reads the delivered articles and their quantities.
3. Each Picnic article is matched to a Grocy product via the barcode `picnic:<article id>`. If there is none yet, it optionally matches an existing product with exactly the same name, or creates a new product (storage location, quantity unit and default due days from the options).
4. The articles are added to stock as a purchase, with price and due date (today + the product's default due days).
5. A notification and the event `picnic_grocy_imported` report the result; the sensor *Last import* shows details.

Deliveries that already existed when you set up the integration are **not** imported automatically. Use the action below to import one manually.

**Dry run is on by default:** imports only report what would happen. Switch it off in the options once a test looks right.

## Installation

1. HACS / Marketplace → ⋮ → *Custom repositories* → `https://github.com/Pflaumeerik/picnic-grocy`, type *Integration* → download → restart Home Assistant.
2. *Settings → Devices & services → Add integration → Picnic → Grocy*.
3. Enter Picnic country, e-mail, password, the Grocy URL and a Grocy API key. Picnic usually asks for a second factor – choose SMS or e-mail and enter the code.

**Grocy add-on:** use `http://a0d7b954-grocy`. The add-on only serves its API when a host port is set in its network settings (e.g. `9192`).

## Action `picnic_grocy.import_delivery`

| Field | Meaning |
|---|---|
| `delivery_id` | Optional, default: latest completed delivery |
| `dry_run` | Default `true` – only report |

Returns the full result (all articles with status) as response data.

## Options

Auto import · dry run · create unknown products · match by exact name · storage location and quantity unit for new products · default due days for fresh and long-life products · keywords to skip (default: `Pfand, Tüte, Tasche`).

## Example automation: push message

```yaml
triggers:
  - trigger: event
    event_type: picnic_grocy_imported
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Picnic → Grocy"
      message: >
        {{ trigger.event.data.booked }} articles booked,
        {{ trigger.event.data.new_products }} new products.
```

---

## Deutsch

Bucht gelieferte Picnic-Einkäufe nach jeder Lieferung automatisch in Grocy ein.

> **Inoffiziell.** Kein Projekt von Picnic. Es nutzt die nicht dokumentierte App-Schnittstelle von Picnic. Ändert Picnic sie, funktioniert der Import erst nach einem Update wieder.

**Ablauf:** Alle 30 Minuten fragt die Integration bei Picnic nach **abgeschlossenen** Lieferungen. Abgeschlossen ist eine Lieferung erst, wenn die Rechnungsmail verschickt wurde, fehlende oder ersetzte Artikel sind dann also schon berücksichtigt. Jeder Picnic-Artikel wird über den Barcode `picnic:<Artikelnummer>` einem Grocy-Produkt zugeordnet. Gibt es keins, ordnet die Integration ein Produkt mit exakt gleichem Namen zu oder legt ein neues an. Danach bucht sie den Artikel als Einkauf ein, mit Preis und MHD (heute + Standard-MHD des Produkts).

Lieferungen, die es beim Einrichten schon gab, werden nicht automatisch importiert. Dafür gibt es die Aktion `picnic_grocy.import_delivery`.

**Der Probelauf ist anfangs eingeschaltet:** Die Integration zeigt nur an, was sie einbuchen würde. Schalte ihn in den Optionen aus, wenn ein Test passt.

**Installation:** HACS bzw. Marketplace → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/Pflaumeerik/picnic-grocy`, Typ *Integration* → herunterladen → HA neu starten → Integration „Picnic → Grocy“ hinzufügen. Gib Land, Picnic-Zugangsdaten, die Grocy-Adresse und einen Grocy-API-Schlüssel ein und bestätige dann den 2FA-Code.

**Grocy-App in HA:** Adresse `http://a0d7b954-grocy`. Die App liefert ihre API nur aus, wenn in ihren Netzwerk-Einstellungen ein Port eingetragen ist (z. B. `9192`).

## License

MIT
