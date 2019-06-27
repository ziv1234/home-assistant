"""Support for Han solo sensor."""

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, CONF_NAME, CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
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
        self._unit_of_measurement = 'W'
        self._name = name

    async def async_added_to_hass(self):
        """Start subscribing to han solo."""
        self._sub_manager = SubscriptionManager(self.hass.loop,
                                                async_get_clientsession(self.hass),
                                                self._hostname)
        self._sub_manager.start()
        await self._sub_manager.subscribe(self._async_callback)
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.remove_from_hass)

    async def _async_callback(self, payload):
        """Handle received data."""
        self._state = payload.get('Effect')
        self.async_schedule_update_ha_state()

    async def remove_from_hass(self, _):
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
            'identifiers': {
                (DOMAIN, self.unique_id)
            },
            'name': self.name,
            'manufacturer': 'Tibber',
        }

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return 'mdi:power-plug'

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity."""
        return self._unit_of_measurement

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._name


################################


"""Subscription manager for Tibber Han Solo."""
import asyncio
import base64
import logging
import struct
from datetime import datetime
from time import time

import aiohttp
import crcmod

_LOGGER = logging.getLogger(__name__)

STATE_STARTING = "starting"
STATE_RUNNING = "running"
STATE_STOPPED = "stopped"

PORT = 9876
FEND = 126  # 7e


class SubscriptionManager:
    """Subscription manager."""

    # pylint: disable=too-many-instance-attributes

    def __init__(self, loop, session, hostname):
        """Create resources for websocket communication."""
        self.loop = loop
        self._url = "ws://{}:{}".format(hostname, PORT)
        self._session = session
        self.subscriptions = []
        self._state = None
        self.websocket = None
        self._retry_timer = None
        self._client_task = None
        self._wait_time_before_retry = 15
        self._show_connection_error = True
        self._is_running = False
        self._crc = crcmod.mkCrcFun(0x11021, rev=True, initCrc=0xffff, xorOut=0x0000)
        self._decoders = [decode_kaifa, decode_kamstrup, decode_aidon]
        self._default_decoder = self._decoders[0]
        self._last_data_time = None

    def start(self):
        """Start websocket."""
        _LOGGER.debug("Start state %s.", self._state)
        if self._state == STATE_RUNNING:
            return
        self._state = STATE_STARTING
        self._cancel_client_task()
        self._client_task = self.loop.create_task(self.running())

    @property
    def is_running(self):
        """Return if client is running or not."""
        return self._is_running

    async def running(self):
        """Start websocket connection."""
        # pylint: disable=too-many-branches, too-many-statements
        await self._close_websocket()
        try:
            _LOGGER.debug("Starting")
            self.websocket = await self._session.ws_connect(self._url)

            self._state = STATE_RUNNING
            _LOGGER.debug("Running")
            self._last_data_time = time()
            while self._state == STATE_RUNNING:
                try:
                    msg = await asyncio.wait_for(self.websocket.receive(), timeout=30)
                except asyncio.TimeoutError:
                    if (time() - self._last_data_time) > 2 * 60:
                        if self._show_connection_error:
                            _LOGGER.error("No data, reconnecting.")
                            self._show_connection_error = False
                        self._is_running = False
                        return
                    _LOGGER.debug(
                        "No websocket data in 30 seconds, checking the connection."
                    )
                    try:
                        pong_waiter = self.websocket.ping()
                        await asyncio.wait_for(pong_waiter, timeout=10)
                    except asyncio.TimeoutError:
                        if self._show_connection_error:
                            _LOGGER.error(
                                "No response to ping in 10 seconds, reconnecting."
                            )
                            self._show_connection_error = False
                        self._is_running = False
                        return
                    continue
                if msg.type in [aiohttp.WSMsgType.closed, aiohttp.WSMsgType.error]:
                    return
                self._last_data_time = time()
                self._is_running = True
                await self._process_msg(msg)
                self._show_connection_error = True
        except Exception:  # pylint: disable=broad-except
            _LOGGER.error("Unexpected error", exc_info=True)
        finally:
            await self._close_websocket()
            if self._state != STATE_STOPPED:
                _LOGGER.debug("Reconnecting")
                self._state = STATE_STOPPED
                self.retry()
            _LOGGER.debug("Closing running task.")

    async def stop(self, timeout=10):
        """Close websocket connection."""
        _LOGGER.debug("Stopping client.")
        start_time = time()
        self._cancel_retry_timer()
        self._state = STATE_STOPPED
        while (
                timeout > 0
                and self.websocket is not None
                and not self.websocket.closed
                and (time() - start_time) < timeout
        ):
            await asyncio.sleep(0.1, loop=self.loop)

        await self._close_websocket()
        self._cancel_client_task()
        _LOGGER.debug("Server connection is stopped")

    def retry(self):
        """Retry to connect to websocket."""
        _LOGGER.debug("Retry, state: %s", self._state)
        if self._state in [STATE_STARTING, STATE_RUNNING]:
            _LOGGER.debug("Skip retry since state: %s", self._state)
            return
        _LOGGER.debug("Cancel retry timer")
        self._cancel_retry_timer()
        self._state = STATE_STARTING
        _LOGGER.debug("Restart")
        self._retry_timer = self.loop.call_later(
            self._wait_time_before_retry, self.start
        )
        _LOGGER.debug(
            "Reconnecting to server in %i seconds.", self._wait_time_before_retry
        )

    async def subscribe(self, callback):
        """Add a new subscription."""
        if callback in self.subscriptions:
            return
        self.subscriptions.append(callback)

    async def unsubscribe(self, callback):
        """Unsubscribe."""
        if callback not in self.subscriptions:
            return
        self.subscriptions.remove(callback)

    async def _close_websocket(self):
        if self.websocket is None:
            return
        try:
            await self.websocket.close()
        finally:
            self.websocket = None

    async def _process_msg(self, msg):
        """Process received msg."""
        if msg.type != aiohttp.WSMsgType.BINARY:
            return

        decoded_data = self.decode(msg)

        if decoded_data is None:
            _LOGGER.error("Failed to decode data %s", msg)
            return

        for callback in self.subscriptions:
            await callback(decoded_data)

    def decode(self, msg, check_time=True):
        """Decode received msg."""
        data = msg.data
        if data is None:
            return None

        if (len(data) < 9
                or not data[0] == FEND
                or not data[-1] == FEND):
            _LOGGER.error("Invalid data %s", data)
            return None

        data = data[1:-1]
        crc = self._crc(data[:-2])
        crc ^= 0xffff
        if crc != struct.unpack("<H", data[-2:])[0]:
            _LOGGER.error("Invalid crc %s %s, %s", crc, struct.unpack("<H", data[-2:])[0],
                          ''.join('{:02x}'.format(x).upper() for x in data))
            return None

        buf = ''.join('{:02x}'.format(x).upper() for x in data)
        decoded_data = self._default_decoder(buf, log=True)
        if decoded_data is not None and (not check_time or valid_time(decoded_data.get('time_stamp'))):
            return decoded_data

        for decoder in self._decoders:
            decoded_data = decoder(buf)
            if decoded_data is not None and (not check_time or valid_time(decoded_data.get('time_stamp'))):
                self._default_decoder = decoder
                return decoded_data

        _LOGGER.error("Unknown data %s", data)
        return None

    def _cancel_retry_timer(self):
        if self._retry_timer is None:
            return
        try:
            self._retry_timer.cancel()
        finally:
            self._retry_timer = None

    def _cancel_client_task(self):
        if self._client_task is None:
            return
        try:
            self._client_task.cancel()
        finally:
            self._client_task = None


def valid_time(time_stamp):
    """Validate time stamp."""
    if time_stamp is None:
        return True
    if not isinstance(time_stamp, datetime):
        return False
    return abs((time_stamp - datetime.now()).total_seconds()) < 3600 * 3


def decode_kaifa(buf, log=False):
    """Decode kaifa."""
    # pylint: disable=too-many-instance-attributes, too-many-branches
    if buf[10:12] != '10':
        if log:
            _LOGGER.error("Unknown control field %s", buf[10:12])
        return None
    try:
        if int(buf[1:4], 16) * 2 != len(buf):
            if log:
                _LOGGER.error("Invalid length %s, %s", int(buf[1:4], 16) * 2, len(buf))
            return None

        buf = buf[32:]
        txt_buf = buf[28:]
        if txt_buf[:2] != '02':
            if log:
                _LOGGER.error("Unknown data %s", buf[0])
            return None

        year = int(buf[4:8], 16)
        month = int(buf[8:10], 16)
        day = int(buf[10:12], 16)
        hour = int(buf[14:16], 16)
        minute = int(buf[16:18], 16)
        second = int(buf[18:20], 16)
        date = "%02d%02d%02d_%02d%02d%02d" % (second, minute, hour, day, month, year)

        res = {}
        res['time_stamp'] = datetime.strptime(date, '%S%M%H_%d%m%Y')

        pkt_type = txt_buf[2:4]
        txt_buf = txt_buf[4:]
        if pkt_type == '01':
            res['Effect'] = int(txt_buf[2:10], 16)
        elif pkt_type in ['09', '0D', '12', '0E']:
            res['Version identifier'] = base64.b16decode(txt_buf[4:18]).decode("utf-8")
            txt_buf = txt_buf[18:]
            res['Meter-ID'] = base64.b16decode(txt_buf[4:36]).decode("utf-8")
            txt_buf = txt_buf[36:]
            res['Meter type'] = base64.b16decode(txt_buf[4:20]).decode("utf-8")
            txt_buf = txt_buf[20:]
            res['Effect'] = int(txt_buf[2:10], 16)
            if pkt_type in ['12', '0E']:
                txt_buf = txt_buf[10:]
                txt_buf = txt_buf[78:]
                res['Cumulative_hourly_active_import_energy'] = int(txt_buf[2:10], 16)
                txt_buf = txt_buf[10:]
                res['Cumulative_hourly_active_export_energy'] = int(txt_buf[2:10], 16)
                txt_buf = txt_buf[10:]
                res['Cumulative_hourly_reactive_import_energy'] = int(txt_buf[2:10], 16)
                txt_buf = txt_buf[10:]
                res['Cumulative_hourly_reactive_export_energy'] = int(txt_buf[2:10], 16)
        else:
            if log:
                _LOGGER.warning("Unknown type %s", pkt_type)
            return None
    except ValueError:
        if log:
            _LOGGER.error("Failed", exc_info=True)
        return None
    return res


def decode_aidon(buf, log=False):
    """Decode Aidon."""
    if buf[10:12] != '13':
        if log:
            _LOGGER.error("Unknown control field %s", buf[10:12])
        return None

    try:
        if int(buf[1:4], 16) * 2 != len(buf):
            if log:
                _LOGGER.error("Invalid length %s, %s", int(buf[1:4], 16) * 2, len(buf))
            return None

        res = {}
        res['time_stamp'] = None
        pkt_type = buf[36:38]
        if pkt_type == '01':
            res['Effect'] = int(buf[60:68], 16)
        elif pkt_type in ['09', '0C', '0D', '0E', '11', '12']:
            res['Effect'] = int(buf[194:202], 16)
        else:
            if log:
                _LOGGER.warning("Unknown type %s", pkt_type)
            return None
    except ValueError:
        if log:
            _LOGGER.error("Failed", exc_info=True)
        return None
    return res


def decode_kamstrup(buf, log=False):
    """Decode Kamstrup."""
    if buf[8:10] != '13':
        if log:
            _LOGGER.error("Unknown control field %s", buf[10:12])
        return None
    if len(buf) < 176:
        if log:
            _LOGGER.error("Data length %s", len(buf))
        return None
    buf = buf[32:]
    txt_buf = buf[26:]

    pkt_type = txt_buf[0:2]
    if pkt_type not in ['0F', '11', '1B', '17', '21', '19', '23']:
        if log:
            _LOGGER.warning("Unknown type %s", pkt_type)
        return None

    try:
        year = int(buf[0:4], 16)
        month = int(buf[4:6], 16)
        day = int(buf[6:8], 16)
        hour = int(buf[10:12], 16)
        minute = int(buf[12:14], 16)
        second = int(buf[14:16], 16)
        date = "%02d%02d%02d_%02d%02d%02d" % (second, minute, hour, day, month, year)

        res = {}
        res['time_stamp'] = datetime.strptime(date, '%S%M%H_%d%m%Y')
        res['Effect'] = int(txt_buf[160:168], 16)
    except ValueError:
        if log:
            _LOGGER.error("Failed", exc_info=True)
        return None
    return res
