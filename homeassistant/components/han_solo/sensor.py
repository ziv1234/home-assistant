"""Support for Han solo sensor."""
from han_solo import SubscriptionManager

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, CONF_NAME, CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Han solo device."""


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Han solo from config entry."""
    config = entry.data
    async_add_entities([HanSoloEntity(config[CONF_NAME], config[CONF_HOST])], True)


class HanSoloEntity(Entity):
    """Representation of a Han solo device."""

    def __init__(self, name, hostname):
        """Initialize the sensor."""
        self._sub_manager = None
        self._hostname = hostname
        self._state = None
        self._unit_of_measurement = "W"
        self._name = name

    async def async_added_to_hass(self):
        """Start subscribing to han solo."""
        self._sub_manager = SubscriptionManager(
            self.hass.loop, async_get_clientsession(self.hass), self._hostname
        )
        self._sub_manager.start()
        await self._sub_manager.subscribe(self._async_callback)
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.remove_from_hass)

    async def _async_callback(self, payload):
        """Handle received data."""
        self._state = payload.get("Effect")
        self.async_schedule_update_ha_state()

    async def remove_from_hass(self, _):
        """Remove from hass."""
        await self._sub_manager.stop()

    @property
    def available(self):
        """Return True if entity is available."""
        if self._sub_manager is None:
            return False
        return self._sub_manager.is_running

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def device_info(self):
        """Return the device info."""
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": "Tibber",
        }

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return "mdi:power-plug"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity."""
        return self._unit_of_measurement

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._name
