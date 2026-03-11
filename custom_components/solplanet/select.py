"""Solplanet selects platform."""

import asyncio
from collections import abc
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SolplanetConfigEntry
from .const import BATTERY_IDENTIFIER, DOMAIN
from .coordinator import SolplanetDataUpdateCoordinator
from .entity import SolplanetEntity, SolplanetEntityDescription

_LOGGER = logging.getLogger(__name__)


class SolplanetSelectOption:
    """Representation of a Solplanet select option."""

    def __init__(self, label: str, value: Any) -> None:
        """Initialize the select option."""
        self.label = label
        self.value = value


@dataclass(frozen=True, kw_only=True)
class SolplanetSelectEntityDescription(
    SolplanetEntityDescription, SelectEntityDescription
):
    """Describe Solplanet select entity."""

    callback: abc.Callable[[SolplanetSelectOption], Any]
    get_options: abc.Callable[[], list[SolplanetSelectOption]]


class SolplanetSelect(SolplanetEntity, SelectEntity):
    """Representation of a Solplanet sensor."""

    entity_description: SolplanetSelectEntityDescription
    _attr_native_value: str | None
    _select_options: list[SolplanetSelectOption]

    def __init__(
        self,
        description: SolplanetSelectEntityDescription,
        isn: str,
        coordinator: SolplanetDataUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(description=description, isn=isn, coordinator=coordinator)
        self._refresh_options()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()
        self._refresh_options()

    def _set_native_value(self) -> None:
        super()._set_native_value()
        self._attr_current_option = self._attr_native_value

    async def async_select_option(self, option: str) -> None:
        """Handle the option selection."""
        item = next((x for x in self._select_options if x.label == option), None)

        if item is not None:
            await self.entity_description.callback(item)
            # Allow the dongle time to commit the register write before we re-read
            # the current mode back from the device. Without this delay, the immediate
            # coordinator poll can return the pre-write value (the dongle hasn't fully
            # committed the new mod_r yet), causing the HA entity to revert to the
            # previous option (e.g. "Custom mode" snapping back to "Self-consumption
            # mode" milliseconds after being set). Confirmed on Solplanet AI-Dongle
            # firmware V610-09578-02.013 — getdev.cgi?device=4 still returns the old
            # mod_r for ~2-3 seconds after a successful setting.cgi write.
            await asyncio.sleep(5)
            await self.coordinator.async_request_refresh()

    def _refresh_options(self) -> None:
        self._select_options = self.entity_description.get_options()
        self._attr_options = [x.label for x in self._select_options]


def create_battery_entites_description(
    coordinator: SolplanetDataUpdateCoordinator, isn: str
) -> list[SolplanetSelectEntityDescription]:
    """Create entities for battery."""
    LED_COLOR_MAP: dict[int, dict[str, str]] = {
        1: {"name": "Cyan", "hex": "#67F9FD"},
        2: {"name": "Mint", "hex": "#69F9CB"},
        3: {"name": "Lime", "hex": "#6CF86C"},
        4: {"name": "Pink", "hex": "#F3B0FC"},
        5: {"name": "Purple", "hex": "#C2B2FB"},
    }

    def _format_led_color_label(index: int) -> str:
        entry = LED_COLOR_MAP.get(index)
        if entry:
            return entry["name"]
        return f"Index {index}"

    def _get_led_color_options() -> list[SolplanetSelectOption]:
        # The device exposes a fixed LED palette (indices 1-5). Include the current value
        # if it ever reports something outside the known range.
        current = (
            coordinator.data.get(BATTERY_IDENTIFIER, {})
            .get(isn, {})
            .get("more_settings", {})
            .get("led_color_index")
        )

        indices = set(LED_COLOR_MAP.keys())
        if isinstance(current, int):
            indices.add(current)

        return [
            SolplanetSelectOption(label=_format_led_color_label(i), value=i)
            for i in sorted(indices)
        ]

    return [
        SolplanetSelectEntityDescription(
            key=f"{isn}_work_mode",
            name="Work mode",
            unique_id_suffix="work_mode",
            data_field_device_type=BATTERY_IDENTIFIER,
            data_field_data_type="work_modes",
            data_field_path=["selected", "name"],
            get_options=lambda: [
                SolplanetSelectOption(label=x.name, value=x)
                for x in coordinator.data[BATTERY_IDENTIFIER][isn]["work_modes"]["all"]
            ],
            callback=lambda option: coordinator.set_battery_work_mode(
                isn, option.value
            ),
        ),
        SolplanetSelectEntityDescription(
            key=f"{isn}_led_color",
            name="LED Color",
            icon="mdi:palette",
            unique_id_suffix="led_color",
            data_field_device_type=BATTERY_IDENTIFIER,
            data_field_data_type="more_settings",
            data_field_path=["led_color_index"],
            # Entity expects a string option; we store int in value and use label for display.
            get_options=_get_led_color_options,
            callback=lambda option: coordinator.set_battery_led_color_index(int(option.value)),
            data_field_value_mapper=lambda v: _format_led_color_label(int(v)) if v is not None else None,
            attributes_fn=lambda ms: {
                "index": ms.get("led_color_index") if isinstance(ms, dict) else None,
                "hex": (
                    LED_COLOR_MAP.get(ms.get("led_color_index"), {}).get("hex")
                    if isinstance(ms, dict)
                    else None
                ),
            },
        ),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolplanetConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities for Solplanet from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    sensors: list[SolplanetSelect] = []

    for isn in coordinator.data[BATTERY_IDENTIFIER]:
        sensors.extend(
            SolplanetSelect(
                description=entity_description,
                isn=isn,
                coordinator=coordinator,
            )
            for entity_description in create_battery_entites_description(
                coordinator, isn
            )
        )

    # Always add entities; values may be missing during startup/inverter sleep.
    async_add_entities(sensors)
