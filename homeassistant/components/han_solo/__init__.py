"""The Han solo component."""
from homeassistant.core import Config, HomeAssistant
from .config_flow import HansoloFlowHandler  # noqa
from .const import DOMAIN # noqa


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up configured Han solo."""
    return True


async def async_setup_entry(hass, config_entry):
    """Set up Han solo as config entry."""
    hass.async_create_task(hass.config_entries.async_forward_entry_setup(
        config_entry, 'sensor'))
    return True

