"""Config flow for Android Media Player integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_SECONDARY_HOST,
    CONF_PORT,
    DEFAULT_PORT,
    DEFAULT_NAME,
    CONNECTION_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_SECONDARY_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


async def validate_input(_hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    host = data[CONF_HOST]
    secondary_host = data.get(CONF_SECONDARY_HOST)
    port = data[CONF_PORT]
    hosts_to_try = [host]
    if secondary_host and secondary_host != host:
        hosts_to_try.append(secondary_host)

    last_error: Exception | None = None

    async with aiohttp.ClientSession() as session:
        for candidate_host in hosts_to_try:
            try:
                async with session.get(
                    f"http://{candidate_host}:{port}/",
                    timeout=aiohttp.ClientTimeout(total=CONNECTION_TIMEOUT),
                ) as response:
                    if response.status != 200:
                        _LOGGER.debug(
                            "Validation failed for %s:%s with status %s",
                            candidate_host,
                            port,
                            response.status,
                        )
                        continue

                    device_info = await response.json()
                    device_name = device_info.get("name", DEFAULT_NAME)
                    _LOGGER.debug(
                        "Validation succeeded for %s:%s",
                        candidate_host,
                        port,
                    )
                    return {
                        "title": device_name,
                        "device_type": device_info.get("type"),
                    }
            except aiohttp.ClientError as err:
                last_error = err
                _LOGGER.debug(
                    "Cannot connect to Android Media Player at %s:%s: %s",
                    candidate_host,
                    port,
                    err,
                )
            except Exception as err:
                last_error = err
                _LOGGER.debug(
                    "Unexpected validation error at %s:%s: %s (%s)",
                    candidate_host,
                    port,
                    err,
                    type(err).__name__,
                )

    if last_error is not None:
        raise CannotConnect from last_error
    raise CannotConnect


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Android Media Player."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check if already configured
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            )
            self._abort_if_unique_id_configured()

            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Use device name from Android
                user_input[CONF_NAME] = info["title"]

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Android Media Player options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        data = self._config_entry.data
        host_default = options.get(CONF_HOST, data.get(CONF_HOST, ""))
        secondary_host_default = options.get(
            CONF_SECONDARY_HOST,
            data.get(CONF_SECONDARY_HOST, ""),
        )
        port_default = options.get(CONF_PORT, data.get(CONF_PORT, DEFAULT_PORT))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=host_default): str,
                    vol.Optional(
                        CONF_SECONDARY_HOST,
                        default=secondary_host_default,
                    ): str,
                    vol.Required(CONF_PORT, default=port_default): int,
                }
            ),
            errors=errors,
        )
