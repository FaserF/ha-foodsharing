[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
# Foodsharing.de Homeassistant Sensor
Gets foodsharing baskets from the [foodsharing.de API](https://beta.foodsharing.de/api/doc/).

<img src="https://wiki.foodsharing.de/images/thumb/3/35/Foodsharinglogo_positiv.png/280px-Foodsharinglogo_positiv.png" alt="Foodsharing.de" width="300px">

<img src="images/sensor.png" alt="Foodsharing.de Sensor" width="300px">




This integration provides the following informations with a refresh rate of 30 minutes until now:


Sensors: 

- How many baskets are available within your distance range

Sensor Attributes: 

- Basket ID, Description, adress, available until time and a picture link

## Installation
### 1. Using HACS (recommended way)

Open your HACS Settings and add

https://github.com/faserf/ha-foodsharing

as custom repository URL.

Then install the "Foodsharing.de" integration.

If you use this method, your component will always update to the latest version.

### 2. Manual
Place a copy of:

[`__init__.py`](custom_components/foodsharing) at `<config>/custom_components/`  

where `<config>` is your Home Assistant configuration directory.

>__NOTE__: Do not download the file by using the link above directly. Rather, click on it, then on the page that comes up use the `Raw` button.

## Configuration 

Go to Configuration -> Integrations and click on "add integration". Then search for Foodsharing.de

### Configuration Variables
- **latitude**: Enter your Latitude
- **longitude**: Enter your Longitude
- **distance**: The search distance for baskets in kilometers
- **email**: Your Foodsharing.de E-Mail adress
- **password**: Your Foodsharing.de Password
- **Google Maps API Key**: Optional: Submit an GMaps API key to recieve human readable adress details ([More Details](https://webperfectapp.com/how-to-create-google-maps-api-key-for-free/)). (Leave it to "false" if you dont want to use it.)
- **refresh time**: Custom refresh time interval in minutes (doesnt work until now!!!)

### Basket URL
To use a basket URL in automations you can use the following code for example:

```yaml
message: >
{% if is_state('sensor.foodsharing_latitude', '1') %}
There is {{ states.sensor.foodsharing_latitude.state }} foodsharing basket available. 
{% else %}
There are {{ states.sensor.foodsharing_latitude.state }} foodsharing baskets available. 
{% endif %}

Newest one: {{ state_attr('sensor.foodsharing_latitude', 'baskets')[-1]['description'] }}

------------

Available until: {{ state_attr('sensor.foodsharing_latitude', 'baskets')[-1]['available until'] }}

Picture: {{ state_attr('sensor.foodsharing_latitude', 'baskets')[-1]['picture'] }}

Link: https://foodsharing.de/essenskoerbe/{{ state_attr('sensor.foodsharing_latitude', 'baskets')[-1]['id'] }}
```

## Bug reporting
Open an issue over at [github issues](https://github.com/FaserF/ha-foodsharing/issues). Please prefer sending over a log with debugging enabled.

To enable debugging enter the following in your configuration.yaml

```yaml
logs:
    custom_components.foodsharing: debug
```

## Thanks to
Huge thanks to [@knorr3](https://github.com/knorr3) for his help and the [coronavirus integration](https://github.com/knorr3/coronavirus_germany), where this integration structure is based on!