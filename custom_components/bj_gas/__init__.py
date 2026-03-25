import logging
import asyncio
import async_timeout
import homeassistant.util.dt as dt_util
from homeassistant.helpers.event import async_track_point_in_utc_time
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers import discovery
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from .gas import GASData, AuthFailed, InvalidData
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=10)

STORAGE_KEY = "bj_gas.data"
STORAGE_VERSION = 1

async def async_setup(hass: HomeAssistant, hass_config):
    config = hass_config[DOMAIN]    
    coordinator = BJRQCorrdinator(hass, config)
    hass.data[DOMAIN] = coordinator

    async def async_load_entities(now):
        try:
            await coordinator.async_refresh()
            if coordinator.last_update_success:
                _LOGGER.debug("Successful to update data, now loading entities")
                hass.async_create_task(discovery.async_load_platform(
                    hass, "sensor", DOMAIN, config, hass_config))
                return
        except AuthFailed as e:
            _LOGGER.error(e)
            return
        except Exception:
            _LOGGER.error(f"Field to update data, retry after 30 seconds")
            pass
        async_track_point_in_utc_time(hass, async_load_entities, dt_util.utcnow() + timedelta(seconds=30))

    async_track_point_in_utc_time(hass, async_load_entities, dt_util.utcnow())
    return True


class BJRQCorrdinator(DataUpdateCoordinator):
    def __init__(self, hass, config):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL
        )
        self._hass = hass
        session = async_create_clientsession(hass)
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._gas = GASData(session, config, store)

    async def _async_update_data(self):
        try:
            async with async_timeout.timeout(60):
                data = await self._gas.async_get_data()
                if not data:
                    raise UpdateFailed("Failed to data update")
                return data
        except asyncio.TimeoutError:
            raise UpdateFailed("Data update timed out")
        except Exception as e:
            raise UpdateFailed(f"Failed to data update with unknown reason: {e}")
