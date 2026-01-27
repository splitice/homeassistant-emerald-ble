"""Config flow for Emerald Energy Monitor integration."""
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_MAC_ADDRESS,
    CONF_DEVICE_NAME,
    CONF_PIN,
    CONF_PULSES_PER_KW,
    DEFAULT_PIN,
    DEFAULT_PULSES_PER_KW,
    DOMAIN,
    extract_serial_from_name,
)

_LOGGER = logging.getLogger(__name__)


class EmeraldBLEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Emerald Energy Monitor."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle the bluetooth discovery step."""
        # Use device name for unique ID if it matches the Emerald pattern,
        # otherwise fall back to MAC address
        device_serial = extract_serial_from_name(discovery_info.name)
        if device_serial:
            unique_id = f"emerald_{device_serial}"
        else:
            unique_id = discovery_info.address
        
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        
        self._discovery_info = discovery_info
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mac_address = user_input[CONF_MAC_ADDRESS]
            pin = user_input[CONF_PIN]
            pulses_per_kw = user_input[CONF_PULSES_PER_KW]

            # Get device name - try to get it from the discovered devices for this MAC
            device_name = None
            if mac_address in self._discovered_devices:
                device_name = self._discovered_devices[mac_address].name
            elif self._discovery_info and self._discovery_info.address == mac_address:
                device_name = self._discovery_info.name
            
            # Use serial-based unique ID if we have a valid device name
            device_serial = extract_serial_from_name(device_name)
            if device_serial:
                unique_id = f"emerald_{device_serial}"
                title = f"Emerald {device_serial}"
            else:
                unique_id = mac_address
                title = f"Emerald {mac_address[-8:]}"

            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            config_data = {
                CONF_MAC_ADDRESS: mac_address,
                CONF_PIN: pin,
                CONF_PULSES_PER_KW: pulses_per_kw,
            }
            
            # Store device name if available for fallback lookup
            if device_name:
                config_data[CONF_DEVICE_NAME] = device_name

            return self.async_create_entry(
                title=title,
                data=config_data,
            )

        # Get discovered bluetooth devices
        current_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(self.hass, False):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            
            # Check if device name contains "Emerald" or matches expected service UUIDs
            # For now, we'll allow manual entry
            self._discovered_devices[address] = discovery_info

        if self._discovery_info:
            mac_address = self._discovery_info.address
        else:
            mac_address = ""

        data_schema = vol.Schema(
            {
                vol.Required(CONF_MAC_ADDRESS, default=mac_address): str,
                vol.Required(CONF_PIN, default=DEFAULT_PIN): int,
                vol.Optional(
                    CONF_PULSES_PER_KW, default=DEFAULT_PULSES_PER_KW
                ): int,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
