[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
# Foodsharing.de Homeassistant Sensor
Gets foodsharing baskets from the [foodsharing.de API](https://beta.foodsharing.de/api/doc/).

<img src="https://wiki.foodsharing.de/images/thumb/3/35/Foodsharinglogo_positiv.png/280px-Foodsharinglogo_positiv.png" alt="Foodsharing.de" width="300px">

<img src="images/sensor.png" alt="Foodsharing.de Sensor" width="300px">




This integration provides the following informations with a refresh rate of 2 minutes until now:


Sensors:

- sensor.foodsharing_latitudeCoordinate: How many baskets are available within your distance range

Sensor Attributes:

- id: Basket ID
- description: Description text about the basket
- address: Human readable detailed address, fetched from coordinates (Not working anymore since 13th december 2024, as adress data has been removed from their API)
- maps: Google Maps Link to basket (Not working anymore since 13th december 2024, as adress data has been removed from their API)
- available until: time until basket creator says it could be available
- picture: link

## Installation
### 1. Using HACS (recommended way)

This integration is NO official HACS Integration right now.

Open HACS then install the "Foodsharing.de" integration or use the link below.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=FaserF&repository=ha-foodsharing&category=integration)

If you use this method, your component will always update to the latest version.

### 2. Manual

- Download the latest zip release from [here](https://github.com/FaserF/ha-foodsharing/releases/latest)
- Extract the zip file
- Copy the folder "foodsharing" from within custom_components with all of its components to `<config>/custom_components/`

where `<config>` is your Home Assistant configuration directory.

>__NOTE__: Do not download the file by using the link above directly, the status in the "master" branch can be in development and therefore is maybe not working.

## Configuration

Go to Configuration -> Integrations and click on "add integration". Then search for Foodsharing.de

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

    Available until: {{ state_attr('sensor.foodsharing_latitude', 'baskets')[0]['available until'] }}

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