"""Test Dynalite switch."""

from dynalite_devices_lib.switch import DynalitePresetSwitchDevice
import pytest

from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    Platform,
)

from .common import (
    ATTR_METHOD,
    ATTR_SERVICE,
    create_entity_from_device,
    create_mock_device,
    run_service_tests,
)


@pytest.fixture
def mock_device():
    """Mock a Dynalite device."""
    return create_mock_device(Platform.SWITCH, DynalitePresetSwitchDevice)


async def test_switch_setup(hass, mock_device):
    """Test a successful setup."""
    await create_entity_from_device(hass, mock_device)
    entity_state = hass.states.get("switch.name")
    assert entity_state.attributes[ATTR_FRIENDLY_NAME] == mock_device.name
    await run_service_tests(
        hass,
        mock_device,
        "switch",
        [
            {ATTR_SERVICE: SERVICE_TURN_ON, ATTR_METHOD: "async_turn_on"},
            {ATTR_SERVICE: SERVICE_TURN_OFF, ATTR_METHOD: "async_turn_off"},
        ],
    )
