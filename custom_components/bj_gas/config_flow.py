
from typing import Any
import logging
import voluptuous as vol

from homeassistant.helpers.aiohttp_client import async_create_clientsession

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.storage import Store
from homeassistant.config_entries import ConfigEntry
from .gas import GASData, AuthFailed
from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("oauth_params"): str,
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    session = async_create_clientsession(hass)
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    gas = GASData(session, data, store)
    try:
        await gas.async_oauth_token()
        await gas.async_get_user_id()
    except AuthFailed as e:
        _LOGGER.error(f"Invalid oauthParams {e}")
        raise e
    return { "title": gas.mobile }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entries = self.hass.config_entries.async_entries(DOMAIN)
            if len(entries) > 0:
                for entity in entries:
                    oauth_params = entity.data.get("oauth_params")
                    if user_input["oauth_params"] == oauth_params:
                        return self.async_abort(reason="oauth_params_repeat")
            try:
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data=user_input)
            except AuthFailed:
                errors["base"] = "oauth_params_invalid"
            except Exception:
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"
        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return OptionsFlow(config_entry)

class OptionsFlow(config_entries.OptionsFlow):

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry
        
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                entries = self.hass.config_entries.async_entries(DOMAIN)
                for entity in entries:
                    if entity.entry_id == self.config_entry.entry_id:
                        continue
                    oauth_params = entity.data.get("oauth_params")
                    if user_input["oauth_params"] == oauth_params:
                        return self.async_abort(reason="oauth_params_repeat")
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data=user_input)
            except AuthFailed:
                errors["base"] = "oauth_params_invalid"
            except Exception:
                _LOGGER.exception("Unexpected error")
                errors["base"] = "unknown"
        return self.async_show_form(step_id="init", data_schema=DATA_SCHEMA, errors=errors)