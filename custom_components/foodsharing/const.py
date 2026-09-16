DOMAIN = "foodsharing"
ATTRIBUTION = "Data provided by Foodsharing"


CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_TOTP = "totp"
CONF_LOCATION = "location"
CONF_LATITUDE_FS = "latitude"
CONF_LONGITUDE_FS = "longitude"
CONF_DISTANCE = "distance"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_KEYWORDS = "keywords"
CONF_USE_BETA_API = "use_beta_api"
CONF_LOCATIONS = "locations"
CONF_DOMAIN = "domain"

# Backend session cookies (src/Lib/Session.php). The CSRF token cookie is not
# HttpOnly and must be echoed back as the X-CSRF-Token header on non-GET calls
# (src/EventSubscriber/CsrfEventSubscriber.php).
SESSION_COOKIE = "FS_SESSID"
CSRF_COOKIE = "FS_CSRF_TOKEN"
