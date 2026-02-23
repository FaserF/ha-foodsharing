[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# Foodsharing.de Home Assistant Sensor 🧺

Retrieve available food baskets from the [foodsharing.de API](https://foodsharing.de/).

<img src="https://wiki.foodsharing.de/images/thumb/3/35/Foodsharinglogo_positiv.png/280px-Foodsharinglogo_positiv.png" alt="Foodsharing.de" width="300px">
<img src="images/sensor.png" alt="Foodsharing.de Sensor" width="300px">

## Features ✨

- **Basket Monitoring**: See how many baskets are available nearby.
- **Detailed Attributes**: Basket description, pickup times, and images.

## Installation 🛠️

### 1. Using HACS (Recommended)

This integration can be added to HACS as a **Custom Repository**.

1.  Open HACS.
2.  Add Custom Repository: `https://github.com/FaserF/ha-foodsharing` (Category: Integration).
3.  Click **Download**.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=FaserF&repository=ha-foodsharing&category=integration)

### 2. Manual Installation

1.  Download the latest [Release](https://github.com/FaserF/ha-foodsharing/releases/latest).
2.  Extract the ZIP file.
3.  Copy the `foodsharing` folder to `<config>/custom_components/`.

## Configuration ⚙️

1.  Go to **Settings** -> **Devices & Services**.
2.  Click **Add Integration**.
3.  Search for "Foodsharing.de".

### Configuration Variables
- **latitude**: Enter your Latitude
- **longitude**: Enter your Longitude
- **distance**: The search distance for baskets in kilometers
- **email**: Your Foodsharing.de E-Mail address
- **password**: Your Foodsharing.de Password
- **update interval**: Custom refresh time interval in minutes (not working for the moment)

### Basket URL
To use a basket URL in automations you can use the following code for example:

```yaml
Link: https://foodsharing.de/essenskoerbe/{{ state_attr('sensor.foodsharing_latitude', 'baskets')[0]['id'] }}
```

A full automation example for HA would be:

```yaml
message: >
    {% if is_state('sensor.foodsharing_latitude', '1') %}
        There is {{ states.sensor.foodsharing_latitude.state }} foodsharing basket available.
    {% else %}
        There are {{ states.sensor.foodsharing_latitude.state }} foodsharing baskets available.
    {% endif %}

    Newest one: {{ state_attr('sensor.foodsharing_latitude', 'baskets')[0]['description'] }}

    ------------

    Available until: {{ state_attr('sensor.foodsharing_latitude', 'baskets')[0]['available_until'] }}

    {% if state_attr('sensor.foodsharing_latitude', 'baskets')[0]['picture'] %}
        [Picture]({{ state_attr('sensor.foodsharing_latitude', 'baskets')[0]['picture'] }})
    {% endif %}

    [Link](https://foodsharing.de/essenskoerbe/{{ state_attr('sensor.foodsharing_latitude', 'baskets')[0]['id'] }})

    {% if not state_attr('sensor.foodsharing_latitude', 'baskets')[0]['address'] == 'unavailable' %}
        address: {{ state_attr('sensor.foodsharing_latitude', 'baskets')[0]['address'] }}
    {% endif %}

    {% if not state_attr('sensor.foodsharing_latitude', 'baskets')[0]['maps'] == 'unavailable' %}
        [Google Maps Link]({{ state_attr('sensor.foodsharing_latitude', 'baskets')[0]['maps'] }})
    {% endif %}
```

## Bug reporting
Open an issue over at [github issues](https://github.com/FaserF/ha-foodsharing/issues). Please prefer sending over a log with debugging enabled.

To enable debugging enter the following in your configuration.yaml

```yaml
logger:
    logs:
        custom_components.foodsharing: debug
```

You can then find the log in the HA settings -> System -> Logs -> Enter "foodsharing" in the search bar -> "Load full logs"

## Thanks to
Huge thanks to [@knorr3](https://github.com/knorr3) for his help and the [coronavirus integration](https://github.com/knorr3/coronavirus_germany), where this integration structure is based on!