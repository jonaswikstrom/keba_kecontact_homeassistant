"""Config flow for Keba KeContact integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .keba_kecontact import KebaClient, KebaUdpManager

from .const import DOMAIN, CONF_RFID, CONF_RFID_CLASS

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

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> KebaKeContactOptionsFlow:
        """Get the options flow for this handler."""
        return KebaKeContactOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            ip_address = user_input[CONF_IP_ADDRESS]
            _LOGGER.debug("Attempting to configure Keba charger at %s", ip_address)

            await self.async_set_unique_id(ip_address)
            self._abort_if_unique_id_configured()

            manager = KebaUdpManager.get_instance()
            if not manager.is_started:
                _LOGGER.debug("Starting UDP manager for configuration")
                try:
                    await manager.start()
                    _LOGGER.debug("UDP manager started successfully")
                except Exception as err:
                    _LOGGER.error(
                        "Failed to start UDP manager during configuration: %s",
                        err,
                        exc_info=True,
                    )
                    errors["base"] = "cannot_connect"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=STEP_USER_DATA_SCHEMA,
                        errors=errors,
                    )
            else:
                _LOGGER.debug("UDP manager already running")

            client = KebaClient(ip_address, use_global_handler=True)

            try:
                _LOGGER.debug("Connecting to charger at %s", ip_address)
                await client.connect()

                _LOGGER.debug("Requesting product info from %s", ip_address)
                report1 = await client.get_report_1()

                _LOGGER.info(
                    "Successfully validated connection to %s (Serial: %s, Product: %s, Firmware: %s)",
                    ip_address,
                    report1.serial,
                    report1.product,
                    report1.firmware,
                )

                title = f"Keba KeContact ({report1.serial})"

                await client.disconnect()
                _LOGGER.debug("Disconnected from charger after successful validation")

                return self.async_create_entry(
                    title=title,
                    data={CONF_IP_ADDRESS: ip_address},
                )

            except TimeoutError:
                _LOGGER.error(
                    "Timeout connecting to charger at %s - charger did not respond within 2 seconds",
                    ip_address,
                )
                errors["base"] = "timeout_connect"
                await client.disconnect()
            except Exception as err:
                _LOGGER.error(
                    "Failed to connect to charger at %s: %s",
                    ip_address,
                    err,
                    exc_info=True,
                )
                errors["base"] = "cannot_connect"
                await client.disconnect()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class KebaKeContactOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Keba KeContact."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage RFID options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_RFID,
                    default=self.config_entry.options.get(
                        CONF_RFID,
                        self.config_entry.data.get(CONF_RFID, "")
                    ),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                    ),
                ),
                vol.Optional(
                    CONF_RFID_CLASS,
                    default=self.config_entry.options.get(
                        CONF_RFID_CLASS,
                        self.config_entry.data.get(CONF_RFID_CLASS, "")
                    ),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                    ),
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
