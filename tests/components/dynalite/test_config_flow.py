"""Test Dynalite config flow."""
from unittest.mock import patch

import pytest

from homeassistant import config_entries
from homeassistant.components import dynalite
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry


@pytest.mark.parametrize(
    ("first_con", "second_con", "exp_result", "exp_state", "exp_reason"),
    [
        (True, True, True, config_entries.ConfigEntryState.LOADED, ""),
        (False, False, False, None, "cannot_connect"),
        (True, False, True, config_entries.ConfigEntryState.LOADED, ""),
    ],
)
async def test_flow(
    hass: HomeAssistant,
    first_con,
    second_con,
    exp_result,
    exp_state,
    exp_reason,
) -> None:
    """Run a flow with or without errors and return result."""
    host = "1.2.3.4"
    entry = MockConfigEntry(
        domain=dynalite.DOMAIN,
        data={
            dynalite.CONF_HOST: host,
            dynalite.schema.CONF_PORT: 123,
        },
        title="dynalite",
    )
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.dynalite.bridge.DynaliteDevices.async_setup",
        side_effect=[first_con, second_con],
    ):
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert result == exp_result
    if exp_state:
        assert entry.state == exp_state
    if exp_reason:
        assert entry.reason == exp_reason


async def test_two_entries(hass: HomeAssistant) -> None:
    """Test when two different entries exist with different hosts."""
    host1 = "1.2.3.4"
    host2 = "5.6.7.8"
    entry1 = MockConfigEntry(domain=dynalite.DOMAIN, data={dynalite.CONF_HOST: host1})
    entry2 = MockConfigEntry(domain=dynalite.DOMAIN, data={dynalite.CONF_HOST: host2})
    entry1.add_to_hass(hass)
    entry2.add_to_hass(hass)
    with patch(
        "homeassistant.components.dynalite.bridge.DynaliteDevices.async_setup",
        return_value=True,
    ):
        assert await hass.config_entries.async_setup(entry1.entry_id)
        await hass.async_block_till_done()
        assert await hass.config_entries.async_setup(entry2.entry_id)
        await hass.async_block_till_done()
    assert entry1.state == config_entries.ConfigEntryState.LOADED
    assert entry2.state == config_entries.ConfigEntryState.LOADED


async def test_setup_user(hass):
    """Test configuration via the user flow."""
    host = "3.4.5.6"
    port = 1234
    result = await hass.config_entries.flow.async_init(
        dynalite.DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"] is None

    with patch(
        "homeassistant.components.dynalite.bridge.DynaliteDevices.async_setup",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": host, "port": port},
        )

    assert result["type"] == "create_entry"
    assert result["result"].state == config_entries.ConfigEntryState.LOADED
    assert result["title"] == host
    assert result["data"] == {
        "host": host,
        "port": port,
    }


async def test_setup_user_existing_host(hass):
    """Test that when we setup a host that is defined, we get an error."""
    host = "3.4.5.6"
    MockConfigEntry(
        domain=dynalite.DOMAIN, data={dynalite.CONF_HOST: host}
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        dynalite.DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "homeassistant.components.dynalite.bridge.DynaliteDevices.async_setup",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": host, "port": 1234},
        )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
