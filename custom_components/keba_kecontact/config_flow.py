"""Config flow for Keba KeContact integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .keba_kecontact import KebaClient, KebaUdpManager

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IP_ADDRESS): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.TEXT,
            ),
        ),
    }
)


class KebaKeContactConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Keba KeContact."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ip_address = user_input[CONF_IP_ADDRESS]

            await self.async_set_unique_id(ip_address)
            self._abort_if_unique_id_configured()

            manager = KebaUdpManager.get_instance()
            if not manager.is_started:
                try:
                    await manager.start()
                except Exception as err:
                    _LOGGER.error("Failed to start UDP manager: %s", err)
                    errors["base"] = "cannot_connect"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=STEP_USER_DATA_SCHEMA,
                        errors=errors,
                    )

            client = KebaClient(ip_address, use_global_handler=True)

            try:
                await client.connect()
                report1 = await client.get_report_1()

                _LOGGER.info(
                    "Successfully validated connection to %s (Serial: %s)",
                    ip_address,
                    report1.serial,
                )

                title = f"Keba KeContact ({report1.serial})"

                await client.disconnect()

                return self.async_create_entry(
                    title=title,
                    data={CONF_IP_ADDRESS: ip_address},
                )

            except TimeoutError:
                _LOGGER.error("Timeout connecting to charger at %s", ip_address)
                errors["base"] = "timeout_connect"
                await client.disconnect()
            except Exception as err:
                _LOGGER.error("Failed to connect to charger at %s: %s", ip_address, err)
                errors["base"] = "cannot_connect"
                await client.disconnect()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
