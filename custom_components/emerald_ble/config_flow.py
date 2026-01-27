"""Config flow for Emerald Energy Monitor integration."""
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_MAC_ADDRESS,
    CONF_PIN,
    CONF_PULSES_PER_KW,
    DEFAULT_PIN,
    DEFAULT_PULSES_PER_KW,
    DOMAIN,
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
        await self.async_set_unique_id(discovery_info.address)
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

            await self.async_set_unique_id(mac_address)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Emerald {mac_address[-8:]}",
                data={
                    CONF_MAC_ADDRESS: mac_address,
                    CONF_PIN: pin,
                    CONF_PULSES_PER_KW: pulses_per_kw,
                },
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
