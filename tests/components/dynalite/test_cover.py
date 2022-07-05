"""Test Dynalite cover."""
from dynalite_devices_lib.cover import DynaliteTimeCoverWithTiltDevice
import pytest

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_CURRENT_TILT_POSITION,
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    SERVICE_CLOSE_COVER,
    SERVICE_CLOSE_COVER_TILT,
    SERVICE_OPEN_COVER,
    SERVICE_OPEN_COVER_TILT,
    SERVICE_SET_COVER_POSITION,
    SERVICE_SET_COVER_TILT_POSITION,
    SERVICE_STOP_COVER,
    SERVICE_STOP_COVER_TILT,
    STATE_CLOSED,
    STATE_CLOSING,
    STATE_OPEN,
    STATE_OPENING,
    Platform,
)
from homeassistant.exceptions import HomeAssistantError

from .common import (
    ATTR_ARGS,
    ATTR_METHOD,
    ATTR_SERVICE,
    create_entity_from_device,
    create_mock_device,
    run_service_tests,
)


@pytest.fixture
def mock_device():
    """Mock a Dynalite device."""
    mock_dev = create_mock_device(Platform.COVER, DynaliteTimeCoverWithTiltDevice)
    mock_dev.device_class = CoverDeviceClass.BLIND
    return mock_dev


async def test_cover_setup(hass, mock_device):
    """Test a successful setup."""
    await create_entity_from_device(hass, mock_device)
    entity_state = hass.states.get("cover.name")
    assert entity_state.attributes[ATTR_FRIENDLY_NAME] == mock_device.name
    assert (
        entity_state.attributes[ATTR_CURRENT_POSITION]
        == mock_device.current_cover_position
    )
    assert (
        entity_state.attributes[ATTR_CURRENT_TILT_POSITION]
        == mock_device.current_cover_tilt_position
    )
    assert entity_state.attributes[ATTR_DEVICE_CLASS] == mock_device.device_class
    await run_service_tests(
        hass,
        mock_device,
        Platform.COVER,
        [
            {ATTR_SERVICE: SERVICE_OPEN_COVER, ATTR_METHOD: "async_open_cover"},
            {ATTR_SERVICE: SERVICE_CLOSE_COVER, ATTR_METHOD: "async_close_cover"},
            {ATTR_SERVICE: SERVICE_STOP_COVER, ATTR_METHOD: "async_stop_cover"},
            {
                ATTR_SERVICE: SERVICE_SET_COVER_POSITION,
                ATTR_METHOD: "async_set_cover_position",
                ATTR_ARGS: {ATTR_POSITION: 50},
            },
            {
                ATTR_SERVICE: SERVICE_OPEN_COVER_TILT,
                ATTR_METHOD: "async_open_cover_tilt",
            },
            {
                ATTR_SERVICE: SERVICE_CLOSE_COVER_TILT,
                ATTR_METHOD: "async_close_cover_tilt",
            },
            {
                ATTR_SERVICE: SERVICE_STOP_COVER_TILT,
                ATTR_METHOD: "async_stop_cover_tilt",
            },
            {
                ATTR_SERVICE: SERVICE_SET_COVER_TILT_POSITION,
                ATTR_METHOD: "async_set_cover_tilt_position",
                ATTR_ARGS: {ATTR_TILT_POSITION: 50},
            },
        ],
    )


async def test_cover_without_tilt(hass, mock_device):
    """Test a cover with no tilt."""
    mock_device.has_tilt = False
    await create_entity_from_device(hass, mock_device)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            Platform.COVER,
            SERVICE_OPEN_COVER_TILT,
            {ATTR_ENTITY_ID: "cover.name"},
            blocking=True,
        )
    await hass.async_block_till_done()
    mock_device.async_open_cover_tilt.assert_not_called()


async def check_cover_position(
    hass, update_func, device, closing, opening, closed, expected
):
    """Check that a given position behaves correctly."""
    device.is_closing = closing
    device.is_opening = opening
    device.is_closed = closed
    update_func(device)
    await hass.async_block_till_done()
    entity_state = hass.states.get("cover.name")
    assert entity_state.state == expected


async def test_cover_positions(hass, mock_device):
    """Test that the state updates in the various positions."""
    update_func = await create_entity_from_device(hass, mock_device)
    await check_cover_position(
        hass, update_func, mock_device, True, False, False, STATE_CLOSING
    )
    await check_cover_position(
        hass, update_func, mock_device, False, True, False, STATE_OPENING
    )
    await check_cover_position(
        hass, update_func, mock_device, False, False, True, STATE_CLOSED
    )
    await check_cover_position(
        hass, update_func, mock_device, False, False, False, STATE_OPEN
    )
