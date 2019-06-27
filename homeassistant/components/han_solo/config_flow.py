"""Config flow to configure Han solo component."""
import voluptuous as vol

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import (CONF_HOST, CONF_NAME)
from homeassistant.core import callback

from .const import DOMAIN


@callback
def configured_instances(hass):
    """Return a set of configured SimpliSafe instances."""
    return set(
        entry.data[CONF_NAME]
        for entry in hass.config_entries.async_entries(DOMAIN))


@config_entries.HANDLERS.register(DOMAIN)
class HansoloFlowHandler(data_entry_flow.FlowHandler):
    """Config flow for Han solo component."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Init HansoloFlowHandler."""
        self._errors = {}

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        self._errors = {}

        if user_input is not None:
            if user_input[CONF_NAME] not in configured_instances(self.hass):
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

            self._errors[CONF_NAME] = 'name_exists'

        return await self._show_config_form(
            name='HanSolo',
            hostname='')

    async def _show_config_form(self, name=None, hostname=None):
        """Show the configuration form to edit configuration."""
        return self.async_show_form(
            step_id='user',
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=name): str,
                vol.Required(CONF_HOST, default=hostname): str,
            }),
            errors=self._errors,
        )

