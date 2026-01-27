"""Sensor platform for Emerald Energy Monitor."""
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from datetime import timedelta

from .const import CONF_MAC_ADDRESS, DOMAIN
from .emerald_ble import EmeraldBLEDevice

_LOGGER = logging.getLogger(__name__)

# Update interval for live energy approximation
ENERGY_UPDATE_INTERVAL = timedelta(seconds=2)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Emerald Energy Monitor sensors from a config entry."""
    device: EmeraldBLEDevice = hass.data[DOMAIN][entry.entry_id]
    mac_address = entry.data[CONF_MAC_ADDRESS]

    sensors = [
        EmeraldPowerSensor(device, mac_address),
        EmeraldEnergySensor(device, mac_address),
        EmeraldBatterySensor(device, mac_address),
    ]

    async_add_entities(sensors)


class EmeraldSensorBase(SensorEntity):
    """Base class for Emerald sensors."""

    _attr_has_entity_name = True

    def __init__(self, device: EmeraldBLEDevice, mac_address: str) -> None:
        """Initialize the sensor."""
        self._device = device
        self._mac_address = mac_address
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac_address)},
            name=f"Emerald Energy Monitor",
            manufacturer="Emerald",
            model="Energy Monitor",
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        self._device.register_callback(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks when entity is removed."""
        self._device.remove_callback(self._handle_update)

    @callback
    def _handle_update(self) -> None:
        """Handle updated data from the device."""
        self.async_write_ha_state()


class EmeraldPowerSensor(EmeraldSensorBase):
    """Sensor for power consumption."""

    _attr_name = "Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, device: EmeraldBLEDevice, mac_address: str) -> None:
        """Initialize the power sensor."""
        super().__init__(device, mac_address)
        self._attr_unique_id = f"{mac_address}_power"

    @property
    def native_value(self) -> float | None:
        """Return the power consumption in kW."""
        return self._device.power_kw

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._device.is_connected and self._device.power_kw is not None


class EmeraldEnergySensor(EmeraldSensorBase, RestoreEntity):
    """Sensor for energy consumption."""

    _attr_name = "Energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, device: EmeraldBLEDevice, mac_address: str) -> None:
        """Initialize the energy sensor."""
        super().__init__(device, mac_address)
        self._attr_unique_id = f"{mac_address}_energy"
        self._remove_update_interval = None

    async def async_added_to_hass(self) -> None:
        """Register callbacks and restore state when entity is added."""
        await super().async_added_to_hass()

        # Restore previous energy value if available
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state not in (None, "unknown", "unavailable"):
                try:
                    restored_energy = float(last_state.state)
                    self._device.set_energy_kwh(restored_energy)
                    _LOGGER.info(
                        "Restored energy value: %.6f kWh", restored_energy
                    )
                except (ValueError, TypeError) as err:
                    _LOGGER.warning(
                        "Failed to restore energy value: %s", err
                    )

        # Set up periodic updates for live energy approximation
        self._remove_update_interval = async_track_time_interval(
            self.hass, self._async_update_energy, ENERGY_UPDATE_INTERVAL
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        await super().async_will_remove_from_hass()
        if self._remove_update_interval:
            self._remove_update_interval()

    @callback
    def _async_update_energy(self, now) -> None:
        """Update energy sensor with live approximation."""
        # This triggers a state update, which will call native_value
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        """Return the cumulative energy consumption in kWh."""
        return self._device.energy_kwh

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._device.is_connected


class EmeraldBatterySensor(EmeraldSensorBase):
    """Sensor for battery level."""

    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, device: EmeraldBLEDevice, mac_address: str) -> None:
        """Initialize the battery sensor."""
        super().__init__(device, mac_address)
        self._attr_unique_id = f"{mac_address}_battery"

    @property
    def native_value(self) -> int | None:
        """Return the battery level."""
        return self._device.battery_level

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._device.is_connected and self._device.battery_level is not None
