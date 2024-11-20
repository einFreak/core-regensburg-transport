# pylint: disable=duplicate-code
"""Dresden (VVO) transport integration."""

from __future__ import annotations

import logging

import requests
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
    SensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (  # pylint: disable=unused-import
    CONF_DEPARTURES,
    CONF_DEPARTURES_NAME,
    CONF_DEPARTURES_STOP_ID,
    CONF_DEPARTURES_WALKING_TIME,
    CONF_TYPE_BUS,
    CONF_TYPE_EXPRESS,
    CONF_TYPE_FERRY,
    CONF_TYPE_REGIONAL,
    CONF_TYPE_SUBURBAN,
    CONF_TYPE_SUBWAY,
    CONF_TYPE_TRAM,
    DEFAULT_ICON,
    DOMAIN,  # noqa: F401
    SCAN_INTERVAL,  # noqa: F401
)
from .stopEvent import StopEvent

_LOGGER = logging.getLogger(__name__)

TRANSPORT_TYPES_SCHEMA = {
    vol.Optional(CONF_TYPE_SUBURBAN, default=True): bool,
    vol.Optional(CONF_TYPE_SUBWAY, default=True): bool,
    vol.Optional(CONF_TYPE_TRAM, default=True): bool,
    vol.Optional(CONF_TYPE_BUS, default=True): bool,
    vol.Optional(CONF_TYPE_FERRY, default=True): bool,
    vol.Optional(CONF_TYPE_EXPRESS, default=True): bool,
    vol.Optional(CONF_TYPE_REGIONAL, default=True): bool,
}

SENSOR_PLATFORM_SCHEMA = SENSOR_PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_DEPARTURES): [
            {
                vol.Required(CONF_DEPARTURES_NAME): str,
                vol.Required(CONF_DEPARTURES_STOP_ID): int,
            }
        ]
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    _: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    if CONF_DEPARTURES in config:
        for departure in config[CONF_DEPARTURES]:
            add_entities([TransportSensor(hass, departure)], True)


class TransportSensor(SensorEntity):
    """Representation of a transport sensor."""

    stop_events: list[StopEvent] = []

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        """Initialize the TransportSensor.

        Args:
            hass (HomeAssistant): The Home Assistant instance.
            config (dict): The configuration dictionary.

        """
        self.hass: HomeAssistant = hass
        self.config: dict = config
        self.stop_id: int = config[CONF_DEPARTURES_STOP_ID]
        self.sensor_name: str | None = config.get(CONF_DEPARTURES_NAME)
        self.direction: str | None = "Test"
        self.walking_time: int = config.get(CONF_DEPARTURES_WALKING_TIME) or 1
        # we add +1 minute anyway to delete the "just gone" transport

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self.sensor_name or f"Stop ID: {self.stop_id}"

    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        next_departure = self.next_departure()
        if next_departure:
            return next_departure.icon
        return DEFAULT_ICON

    @property
    def unique_id(self) -> str:
        """Return a unique ID for the sensor."""
        return f"stop_{self.stop_id}_departures"

    # @property
    # def state(self) -> str:
    #     """Return the state of the sensor."""
    #     next_departure = self.next_departure()
    #     if next_departure:
    #         return f"Next {next_departure.transportation_nr} {next_departure.transportation_direction} at {next_departure.estimated}"
    #     return "N/A"

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        return {"departures": [event.to_dict() for event in self.stop_events or []]}

    async def async_update(self):
        """Update the sensor state."""
        self.stop_events = self.fetch_departures()

    def fetch_departures(self) -> list[StopEvent] | None:
        """Fetch the departures from the API and return a list of StopEvent objects."""
        try:
            response = requests.get(
                url="https://efa.rvv.de/efa/XML_DM_REQUEST",
                params={
                    "mode": "direct",
                    "outputFormat": "rapidJSON",
                    "type_dm": "any",
                    "useRealtime": "1",
                    "name_dm": "de:09362:12009",
                },
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as ex:
            _LOGGER.warning("API error: %s", ex)
            return []
        except requests.exceptions.Timeout as ex:
            _LOGGER.warning("API timeout: %s", ex)
            return []

        _LOGGER.debug("OK: departures for %s: %s", self.stop_id, response.text)

        # parse JSON response
        try:
            stopEvents = response.json().get("stopEvents")
        except requests.exceptions.InvalidJSONError as ex:
            _LOGGER.error("API invalid JSON: %s", ex)
            return []

        # convert api data into objects
        unsorted = [StopEvent.from_dict(departure) for departure in stopEvents]
        return sorted(unsorted, key=lambda d: d.planned)

    def next_departure(self):
        """Return the next departure event."""
        if self.stop_events and isinstance(self.stop_events, list):
            return self.stop_events[0]
        return None
