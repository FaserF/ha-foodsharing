[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/FaserF/ha-foodsharing?style=for-the-badge)](https://github.com/FaserF/ha-foodsharing/releases)

# Foodsharing.de Home Assistant Integration 🧺

A comprehensive [Home Assistant](https://www.home-assistant.io/) custom integration for [Foodsharing.de](https://foodsharing.de/) — monitor nearby food baskets, fairteiler locations, pickup schedules, messages, and notifications directly from your smart home dashboard.

<p align="center">
  <img src="https://upload.wikimedia.org/wikipedia/commons/1/16/Foodsharing-Logo_dunkel_Gabel.png" alt="Foodsharing.de" width="280">
  <br>
  <img src="images/sensor.png" alt="Foodsharing.de Sensor" width="300">
</p>

---

## Features ✨

| Feature | Description |
|---------|-------------|
| 🧺 **Basket Sensor** | Monitor the number of available food baskets near your location, with full details as attributes |
| 📍 **Geo-Location** | Baskets and Fairteiler points displayed on the HA map with calculated distances |
| 📅 **Pickup Calendar** | Your upcoming pickups shown as calendar events |
| 🔔 **Notifications Sensor** | Track unread bell notifications |
| 💬 **Messages Sensor** | Track unread conversation messages |
| 🔘 **Basket Buttons** | Request nearby baskets or close your own baskets with one tap |
| 🔧 **Service Calls** | `foodsharing.request_basket` service for use in automations |
| 🌍 **Multi-Location** | Add the integration multiple times with different search areas |
| 🔑 **Keyword Matching** | Filter baskets by keywords and get events when matches are found |
| 🩺 **HA Repairs** | Automatic repair notifications for authentication failures or API outages |
| 📊 **Diagnostics** | Built-in diagnostics support with automatic redaction of sensitive data |
| 🌐 **Translations** | Full English and German translations |

---

## Installation 🛠️

### 1. Using HACS (Recommended)

This integration is available in the **HACS Default Repository**.

1. Open HACS.
2. Search for **"Foodsharing"**.
3. Click **Download**.
4. Restart Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=FaserF&repository=ha-foodsharing&category=integration)

### 2. Manual Installation

1. Download the latest [Release](https://github.com/FaserF/ha-foodsharing/releases/latest).
2. Extract the ZIP file.
3. Copy the `foodsharing` folder to `<config>/custom_components/`.
4. Restart Home Assistant.

---

## Configuration ⚙️

1. Go to **Settings** → **Devices & Services**.
2. Click **Add Integration**.
3. Search for **"Foodsharing.de"**.
4. Enter your credentials and select a location on the map.

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| **Email** | Your Foodsharing.de account email | *required* |
| **Password** | Your Foodsharing.de account password | *required* |
| **Location** | Pin on the map to set your search center | HA home location |
| **Search Radius** | Derived from the map circle radius (in km) | 7 km |
| **Keywords** | Comma-separated filter keywords (optional) | *empty* |
| **Scan Interval** | How often to poll the API (in minutes) | 2 min |

> [!TIP]
> You can add the integration multiple times with different locations to monitor several areas at once.

All options can be changed later via **Settings → Devices & Services → Foodsharing → Configure**.

---

## Entities Created 📋

### Sensors

| Entity | Type | State | Attributes |
|--------|------|-------|------------|
| `sensor.foodsharing_baskets_*` | Sensor | Number of nearby baskets | `baskets` (list), `basket_count`, `latitude`, `longitude` |
| `sensor.foodsharing_unread_messages` | Sensor | Number of unread messages | — |
| `sensor.foodsharing_notifications` | Sensor | Number of unread bell notifications | — |

### Geo-Location Entities

| Entity | Type | State |
|--------|------|-------|
| `geo_location.basket_*` | Geo-Location | Distance from search center (km) |
| `geo_location.fairteiler_*` | Geo-Location | Distance from search center (km) |

### Calendar

| Entity | Type | Description |
|--------|------|-------------|
| `calendar.foodsharing_pickups` | Calendar | Your scheduled pickup events |

### Buttons

| Entity | Type | Description |
|--------|------|-------------|
| `button.request_*` | Button | Request a nearby basket |
| `button.close_own_basket_*` | Button | Close one of your own active baskets |

### Services

| Service | Description | Fields |
|---------|-------------|--------|
| `foodsharing.request_basket` | Request a basket by ID | `basket_id` (required) |

---

## Basket Sensor Attributes 📦

The basket sensor exposes the full list of baskets as the `baskets` attribute. Each basket in the list contains:

| Key | Description | Example |
|-----|-------------|---------|
| `id` | Basket ID | `123456` |
| `description` | Basket description text | `"Fresh bread and vegetables"` |
| `available_until` | When the basket expires | `"Sun Feb 23 18:00:00 2025"` |
| `picture` | Image URL (or `null`) | `"https://foodsharing.de/images/..."` |
| `latitude` | Basket latitude | `48.1234` |
| `longitude` | Basket longitude | `11.5678` |
| `maps` | Google Maps link | `"https://www.google.com/maps/..."` |
| `keyword_match` | Whether it matches your keywords | `true` / `false` |

---

## Events 🔔

The integration fires custom events that you can use as automation triggers:

| Event | Description | Data |
|-------|-------------|------|
| `foodsharing_keyword_match` | A new basket matches your keywords | Full basket data |
| `foodsharing_new_message` | A new unread message arrived | `conversation_id`, `message` |
| `foodsharing_new_bell` | A new bell notification | Bell data |
| `foodsharing_fairteiler_post` | New post on a fairteiler wall | `fairteiler_id`, `fairteiler_name`, `post` |

---

## Automation Examples 🤖

<details>
<summary><b>📬 Notify when new baskets are available</b></summary>

```yaml
automation:
  - alias: "Foodsharing: New baskets nearby"
    trigger:
      - platform: numeric_state
        entity_id: sensor.foodsharing_baskets_48_1180_11_6833
        above: 0
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "🧺 Foodsharing"
          message: >-
            {{ states('sensor.foodsharing_baskets_48_1180_11_6833') }} basket(s) available!
```

</details>

<details>
<summary><b>🔑 Notify on keyword match</b></summary>

```yaml
automation:
  - alias: "Foodsharing: Keyword match found"
    trigger:
      - platform: event
        event_type: foodsharing_keyword_match
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "🎯 Foodsharing Keyword Match!"
          message: >-
            {{ trigger.event.data.description }}

            Available until: {{ trigger.event.data.available_until }}

            Link: https://foodsharing.de/essenskoerbe/{{ trigger.event.data.id }}
```

</details>

<details>
<summary><b>📋 Detailed basket notification with image</b></summary>

```yaml
automation:
  - alias: "Foodsharing: Detailed basket alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.foodsharing_baskets_48_1180_11_6833
        above: 0
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "🧺 Foodsharing Basket Available"
          message: >-
            {% set baskets = state_attr('sensor.foodsharing_baskets_48_1180_11_6833', 'baskets') %}
            {% if baskets | length > 0 %}
              {% set b = baskets[0] %}
              {{ b.description }}

              Available until: {{ b.available_until }}

              {% if b.maps != 'unavailable' %}
              Maps: {{ b.maps }}
              {% endif %}

              Link: https://foodsharing.de/essenskoerbe/{{ b.id }}
            {% endif %}
          data:
            image: >-
              {% set baskets = state_attr('sensor.foodsharing_baskets_48_1180_11_6833', 'baskets') %}
              {% if baskets | length > 0 and baskets[0].picture %}
                {{ baskets[0].picture }}
              {% endif %}
```

</details>

<details>
<summary><b>💬 New message notification</b></summary>

```yaml
automation:
  - alias: "Foodsharing: New message received"
    trigger:
      - platform: event
        event_type: foodsharing_new_message
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "💬 Foodsharing Message"
          message: "You have a new unread message on Foodsharing.de!"
```

</details>

<details>
<summary><b>🔔 Bell notification</b></summary>

```yaml
automation:
  - alias: "Foodsharing: New notification"
    trigger:
      - platform: numeric_state
        entity_id: sensor.foodsharing_notifications
        above: 0
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "🔔 Foodsharing"
          message: >-
            You have {{ states('sensor.foodsharing_notifications') }} unread notification(s).
```

</details>

<details>
<summary><b>📅 Pickup reminder (1 hour before)</b></summary>

```yaml
automation:
  - alias: "Foodsharing: Pickup reminder"
    trigger:
      - platform: calendar
        event: start
        offset: "-01:00:00"
        entity_id: calendar.foodsharing_pickups
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "📅 Upcoming Pickup"
          message: >-
            Don't forget your bags! "{{ trigger.calendar_event.summary }}" starts in 1 hour.
```

</details>

<details>
<summary><b>🏪 New Fairteiler post</b></summary>

```yaml
automation:
  - alias: "Foodsharing: New Fairteiler post"
    trigger:
      - platform: event
        event_type: foodsharing_fairteiler_post
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "🏪 Fairteiler Update"
          message: >-
            New post at {{ trigger.event.data.fairteiler_name }}!
```

</details>

<details>
<summary><b>🔧 Request a basket via service call</b></summary>

```yaml
automation:
  - alias: "Foodsharing: Auto-request keyword match"
    trigger:
      - platform: event
        event_type: foodsharing_keyword_match
    action:
      - service: foodsharing.request_basket
        data:
          basket_id: "{{ trigger.event.data.id }}"
```

</details>

---

## Blueprints 📘

A ready-to-use **Pickup Reminder** blueprint is included in the `blueprints/` folder. To install it:

1. Copy `blueprints/automation/foodsharing/pickup_reminder.yaml` to your HA `blueprints/automation/` directory.
2. Go to **Settings → Automations → Blueprints** and configure it.

---

## HA Repairs 🩺

The integration uses Home Assistant's built-in **Repairs** system to notify you of problems:

| Issue | When it appears | What to do |
|-------|----------------|------------|
| **Authentication failed** | Your password was changed or credentials expired | Go to integration options and update email/password |
| **API offline** | Foodsharing.de returns a 503 error | Wait — data resumes automatically when the API recovers |

Repair items appear in **Settings → System → Repairs**.

---

## Bug Reporting 🐛

Open an issue at [GitHub Issues](https://github.com/FaserF/ha-foodsharing/issues). Please include a log with debugging enabled.

To enable debug logging, add this to your `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.foodsharing: debug
```

Then find the log at **Settings → System → Logs** → search for `foodsharing` → **Load full logs**.

---

## Thanks to 🙏

Huge thanks to [@knorr3](https://github.com/knorr3) for his help and the [coronavirus integration](https://github.com/knorr3/coronavirus_germany), where this integration structure is based on!