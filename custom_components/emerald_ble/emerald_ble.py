"""BLE communication for Emerald Energy Monitor."""
import asyncio
import logging
from datetime import datetime
from typing import Callable

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback

from .const import (
    CHAR_BATTERY_READ_UUID,
    CHAR_TIME_READ_UUID,
    CHAR_TIME_WRITE_UUID,
    PULSE_MULTIPLIER_BASE,
    RESPONSE_30S_POWER,
    RESPONSE_EVERY_30S_POWER,
    RESPONSE_UPDATED_POWER,
)

_LOGGER = logging.getLogger(__name__)

# Protocol constants
COMMAND_HEADER_LENGTH = 5
DATE_FIELD_START = 5
TOTAL_HEADER_WITH_DATE_LENGTH = 9
POWER_NOTIFICATION_LENGTH = 11
CMD_AUTO_UPLOAD = bytearray([0x00, 0x01, 0x02, 0x0b, 0x01, 0x01])

# Energy calculation constants
MAX_TIME_DELTA_SECONDS = 3600  # Maximum time delta for energy accumulation (1 hour)
LIVE_APPROXIMATION_TIMEOUT = 60  # Stop approximating after 60 seconds without update


def get_command_from_notify(data: bytearray) -> int:
    """Extract command header from BLE notification data."""
    if len(data) < COMMAND_HEADER_LENGTH:
        return 0
    
    command_header = 0
    for i in range(COMMAND_HEADER_LENGTH):
        command_header += data[i] << (8 * (4 - i))
    return command_header


def get_date_from_notify(data: bytearray) -> int:
    """Extract date binary from BLE notification data."""
    if len(data) < TOTAL_HEADER_WITH_DATE_LENGTH:
        return 0
    
    command_date_bin = 0
    for i in range(DATE_FIELD_START, TOTAL_HEADER_WITH_DATE_LENGTH):
        command_date_bin += data[i] << (8 * (8 - i))
    return command_date_bin


def decode_emerald_date(command_date_bin: int) -> datetime | None:
    """Decode Emerald date format to datetime.
    
    Format: (6)year + (4)month + (5)days + (5)hours + (6)minutes + (6)seconds
    """
    try:
        year = 2000 + (command_date_bin >> 26)
        month = (command_date_bin >> 22) & 0b1111
        days = (command_date_bin >> 17) & 0b11111
        hours = (command_date_bin >> 12) & 0b11111
        minutes = (command_date_bin >> 6) & 0b111111
        seconds = command_date_bin & 0b111111
        
        return datetime(year, month, days, hours, minutes, seconds)
    except (ValueError, OverflowError) as err:
        _LOGGER.error("Failed to decode Emerald date: %s", err)
        return None


class EmeraldBLEDevice:
    """Representation of an Emerald Energy Monitor BLE device."""

    def __init__(
        self,
        hass: HomeAssistant,
        ble_device: BLEDevice,
        pin: int,
        pulses_per_kw: int,
    ) -> None:
        """Initialize the Emerald BLE device."""
        self._hass = hass
        self._ble_device = ble_device
        self._pin = pin
        self._pulses_per_kw = pulses_per_kw
        self._pulse_multiplier = PULSE_MULTIPLIER_BASE / pulses_per_kw
        
        self._client: BleakClient | None = None
        self._connected = False
        self._authenticated = False
        
        self._power_kw: float | None = None
        self._battery_level: int | None = None
        self._last_update: datetime | None = None
        self._energy_kwh: float = 0.0
        self._last_power_update: datetime | None = None
        self._last_actual_reading_time: datetime | None = None
        
        self._callbacks: list[Callable[[], None]] = []
        
        # Advertisement tracking
        self._advertisement_callback_cancel: Callable[[], None] | None = None
        self._connection_task: asyncio.Task | None = None
        self._reconnect_lock = asyncio.Lock()
        self._stopping = False

    @property
    def address(self) -> str:
        """Return the MAC address of the device."""
        return self._ble_device.address

    @property
    def is_connected(self) -> bool:
        """Return True if connected to the device."""
        return self._connected

    @property
    def power_kw(self) -> float | None:
        """Return the current power consumption in kW."""
        return self._power_kw

    @property
    def battery_level(self) -> int | None:
        """Return the battery level percentage."""
        return self._battery_level

    @property
    def last_update(self) -> datetime | None:
        """Return the timestamp of the last data update."""
        return self._last_update

    @property
    def energy_kwh(self) -> float:
        """Return the cumulative energy consumption in kWh."""
        return self._get_live_energy()

    def _get_live_energy(self) -> float:
        """Get live energy with approximation between readings."""
        base_energy = self._energy_kwh
        
        # If we don't have power data yet, return base energy
        if self._power_kw is None or self._last_actual_reading_time is None:
            return base_energy
        
        # Calculate time since last actual reading
        now = datetime.now()
        time_since_reading = (now - self._last_actual_reading_time).total_seconds()
        
        # Stop approximating after timeout (60 seconds)
        if time_since_reading > LIVE_APPROXIMATION_TIMEOUT:
            return base_energy
        
        # Add live approximation using current power
        time_delta_hours = time_since_reading / 3600.0
        live_energy_increment = self._power_kw * time_delta_hours
        
        return base_energy + live_energy_increment

    def set_energy_kwh(self, value: float) -> None:
        """Set the cumulative energy consumption in kWh (for state restoration)."""
        self._energy_kwh = value

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when data is updated."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove a previously registered callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def start(self) -> None:
        """Start the device by registering for advertisement callbacks."""
        _LOGGER.debug("Starting Emerald device at %s", self.address)
        
        self._stopping = False
        
        # Register callback to receive advertisements
        self._advertisement_callback_cancel = bluetooth.async_register_callback(
            self._hass,
            self._handle_advertisement,
            {"address": self._ble_device.address},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
        _LOGGER.info("Registered for advertisements from %s", self.address)

    async def stop(self) -> None:
        """Stop the device and clean up resources."""
        _LOGGER.debug("Stopping Emerald device at %s", self.address)
        
        # Set stopping flag to prevent new connections
        self._stopping = True
        
        # Cancel advertisement callback
        if self._advertisement_callback_cancel:
            self._advertisement_callback_cancel()
            self._advertisement_callback_cancel = None
        
        # Cancel any pending connection task
        if self._connection_task and not self._connection_task.done():
            self._connection_task.cancel()
            try:
                await self._connection_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect from device
        await self._disconnect_internal()

    @callback
    def _handle_advertisement(
        self, service_info: bluetooth.BluetoothServiceInfoBleak, change: bluetooth.BluetoothChange
    ) -> None:
        """Handle advertisement from the device."""
        _LOGGER.debug(
            "Advertisement received from %s, change: %s", 
            self.address, change
        )
        
        # If we're stopping, don't create new connection tasks
        if self._stopping:
            return
        
        # Update the BLE device with latest info
        self._ble_device = service_info.device
        
        # If we're already connected, nothing to do
        if self._connected:
            return
        
        # Acquire lock to prevent race conditions with stop() and multiple advertisements
        # Check if there's already a connection attempt in progress
        if self._connection_task and not self._connection_task.done():
            _LOGGER.debug("Connection attempt already in progress")
            return
        
        # Start connection attempt when we see an advertisement
        _LOGGER.info("Advertisement seen from %s, attempting connection", self.address)
        self._connection_task = self._hass.async_create_task(self._connect_with_retry())

    async def _connect_with_retry(self) -> None:
        """Attempt to connect to the device with retry logic."""
        async with self._reconnect_lock:
            # Double-check we're not already connected (race condition guard)
            if self._connected or self._stopping:
                return
            
            try:
                await self.connect()
            except asyncio.CancelledError:
                # Task was cancelled, don't log as error
                _LOGGER.debug("Connection attempt to %s was cancelled", self.address)
                raise
            except Exception as err:
                _LOGGER.warning(
                    "Failed to connect to %s after advertisement: %s",
                    self.address, err
                )

    async def connect(self) -> bool:
        """Connect to the Emerald BLE device."""
        # Return early if already connected
        if self._connected:
            _LOGGER.debug("Already connected to %s", self.address)
            return True
        
        try:
            _LOGGER.debug("Connecting to Emerald device at %s", self.address)
            self._client = await establish_connection(
                BleakClient, self._ble_device, self._ble_device.address
            )
            self._connected = True
            _LOGGER.info("Connected to Emerald device at %s", self.address)
            
            # Subscribe to characteristics
            await self._subscribe_to_notifications()
            
            # Enable auto upload
            await self._enable_auto_upload()
            
            return True
        except BleakError as err:
            _LOGGER.error("Failed to connect to device: %s", err)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from the BLE device."""
        await self._disconnect_internal()
        if not self._stopping:
            _LOGGER.info(
                "Disconnected from %s, will reconnect on next advertisement",
                self.address
            )

    async def _disconnect_internal(self) -> None:
        """Internal disconnect method without reconnection message."""
        if self._client and self._connected:
            try:
                await self._client.disconnect()
            except BleakError as err:
                _LOGGER.error("Error disconnecting: %s", err)
            finally:
                self._connected = False
                self._authenticated = False

    async def _subscribe_to_notifications(self) -> None:
        """Subscribe to BLE notifications."""
        if not self._client or not self._connected:
            return

        try:
            # Subscribe to time/power characteristic
            await self._client.start_notify(
                CHAR_TIME_READ_UUID, self._handle_power_notification
            )
            
            # Subscribe to battery characteristic
            await self._client.start_notify(
                CHAR_BATTERY_READ_UUID, self._handle_battery_notification
            )
            
            _LOGGER.debug("Subscribed to notifications")
        except BleakError as err:
            _LOGGER.error("Failed to subscribe to notifications: %s", err)

    async def _enable_auto_upload(self) -> None:
        """Enable auto upload mode on the device."""
        if not self._client or not self._connected:
            return

        try:
            # Send auto upload enable command
            await self._client.write_gatt_char(
                CHAR_TIME_WRITE_UUID, CMD_AUTO_UPLOAD, response=False
            )
            _LOGGER.debug("Enabled auto upload")
        except BleakError as err:
            _LOGGER.error("Failed to enable auto upload: %s", err)

    def _handle_power_notification(self, sender: int, data: bytearray) -> None:
        """Handle power consumption notifications."""
        _LOGGER.debug("Power notification: %s", data.hex())
        
        if len(data) < COMMAND_HEADER_LENGTH:
            _LOGGER.warning("Received short notification data")
            return

        command_header = get_command_from_notify(data)
        
        if command_header == RESPONSE_30S_POWER:
            if len(data) == POWER_NOTIFICATION_LENGTH:
                # Extract date
                command_date_bin = get_date_from_notify(data)
                timestamp = decode_emerald_date(command_date_bin)
                
                # Extract power
                msb = data[-2] << 8
                total_pulses = msb + data[-1]
                new_power_kw = total_pulses * self._pulse_multiplier
                
                # When actual reading arrives, correct the energy baseline
                # by incorporating any live approximation that was happening
                if self._last_actual_reading_time is not None and timestamp is not None:
                    time_since_reading = (timestamp - self._last_actual_reading_time).total_seconds()
                    # Only correct if within approximation timeout
                    if self._power_kw is not None and 0 < time_since_reading <= LIVE_APPROXIMATION_TIMEOUT:
                        # Calculate what was approximated
                        time_delta_hours = time_since_reading / 3600.0
                        actual_energy_increment = self._power_kw * time_delta_hours
                        self._energy_kwh += actual_energy_increment
                        _LOGGER.debug(
                            "Correcting energy with actual reading: %.6f kWh (%.2f kW × %.4f h)",
                            actual_energy_increment, self._power_kw, time_delta_hours
                        )
                
                # Update power and timestamps
                self._power_kw = new_power_kw
                self._last_update = timestamp
                self._last_power_update = timestamp
                self._last_actual_reading_time = datetime.now()  # Use current time for approximation
                
                _LOGGER.debug(
                    "Power update: %.2f kW at %s", self._power_kw, timestamp
                )
                
                # Notify callbacks
                for callback in self._callbacks:
                    callback()
            else:
                _LOGGER.warning("Unexpected data length for 30s power: %d", len(data))
        elif command_header == RESPONSE_UPDATED_POWER:
            _LOGGER.debug("Received updated power command")
        elif command_header == RESPONSE_EVERY_30S_POWER:
            _LOGGER.debug("Received every 30s power command")

    def _handle_battery_notification(self, sender: int, data: bytearray) -> None:
        """Handle battery level notifications."""
        _LOGGER.debug("Battery notification: %s", data.hex())
        
        if len(data) >= 1:
            self._battery_level = data[0]
            _LOGGER.debug("Battery level: %d%%", self._battery_level)
            
            # Notify callbacks
            for callback in self._callbacks:
                callback()
