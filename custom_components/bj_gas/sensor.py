from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
    SensorEntity,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import (
    UnitOfVolume,
    UnitOfElectricPotential,
    STATE_UNKNOWN
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

from .coord import BJRQCorrdinator
from .const import DOMAIN

GAS_SENSORS = {
    "balance": {
        "name": "燃气费余额",
        "icon": "hass:cash-100",
        "unit_of_measurement": "元",
        "device_class": SensorDeviceClass.MONETARY,
        "attributes": ["last_update"]
    },
    "current_level": {
        "name": "当前燃气阶梯",
        "icon": "hass:stairs"
    },
    "current_price": {
        "name": "当前气价",
        "icon": "hass:cash-100",
        "unit_of_measurement": "元/m³",
        "device_class": SensorDeviceClass.MONETARY
    },
    "current_level_remain": {
        "name": "当前阶梯剩余额度",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.MEASUREMENT
    },
    "year_consume": {
        "name": "本年度用气量",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.TOTAL_INCREASING
    },
    "month_reg_qty": {
        "name": "当月用气量",
        "device_class": SensorDeviceClass.GAS,
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS,
        "state_class": SensorStateClass.TOTAL_INCREASING
    },
    "battery_voltage": {
        "name": "气表电量",
        "device_class": SensorDeviceClass.VOLTAGE,
        "unit_of_measurement": UnitOfElectricPotential.VOLT
    },
    "mtr_status": {
        "name": "阀门状态",
        "icon": "hass:valve"
    }
}

async def async_setup_entry(hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback):
    sensors = []
    coordinator = BJRQCorrdinator(hass, config_entry.data)
    await coordinator.async_refresh()
    for user_code, data in coordinator.data.items():
        # 基础实时传感器
        for key in GAS_SENSORS.keys():
            if key in data.keys():
                sensors.append(GASSensor(coordinator, user_code, key))
        
        # 历史月度账单
        if "monthly_bills" in data:
            for month in range(len(data["monthly_bills"])):
                sensors.append(GASHistorySensor(coordinator, user_code, month))
        
        # 每日用量记录
        if "daily_bills" in data:
            for day in range(len(data["daily_bills"])):
                sensors.append(GASDailyBillSensor(coordinator, user_code, day))
    async_add_entities(sensors, True)

class GASBaseSensor(CoordinatorEntity, SensorEntity):
    """基础传感器类"""
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_should_poll = False

class GASSensor(GASBaseSensor):
    """实时状态传感器"""
    def __init__(self, coordinator, user_code, sensor_key):
        super().__init__(coordinator)
        self._user_code = user_code
        self._sensor_key = sensor_key
        config = GAS_SENSORS[self._sensor_key]
        
        self._attr_name = config.get("name")
        self._attr_icon = config.get("icon")
        self._attr_device_class = config.get("device_class")
        self._attr_unit_of_measurement = config.get("unit_of_measurement")
        self._attr_state_class = config.get("state_class")
        self._attributes_to_track = config.get("attributes", [])
        
        self._attr_unique_id = f"{DOMAIN}.{user_code}_{sensor_key}"
        self.entity_id = self._attr_unique_id
        
    @property
    def native_unit_of_measurement(self):
        return self._attr_unit_of_measurement

    @property
    def native_value(self):
        try:
            return self.coordinator.data[self._user_code].get(self._sensor_key)
        except (KeyError, TypeError):
            return STATE_UNKNOWN

    @property
    def extra_state_attributes(self):
        attrs = {}
        for attr in self._attributes_to_track:
            val = self.coordinator.data[self._user_code].get(attr)
            if val is not None:
                attrs[attr] = val
        return attrs

class GASHistorySensor(GASBaseSensor):
    """历史月度账单传感器"""
    def __init__(self, coordinator, user_code, index):
        super().__init__(coordinator)
        self._user_code = user_code
        self._index = index
        self._attr_device_class = SensorDeviceClass.GAS
        self._attr_unique_id = f"{DOMAIN}.{user_code}_monthly_{index + 1}"
        self.entity_id = self._attr_unique_id
        
    @property
    def native_unit_of_measurement(self):
        return UnitOfVolume.CUBIC_METERS

    @property
    def name(self):
        try:
            return self.coordinator.data[self._user_code]['monthly_bills'][self._index].get('mon')
        except (KeyError, IndexError):
            return STATE_UNKNOWN

    @property
    def native_value(self):
        try:
            return self.coordinator.data[self._user_code]["monthly_bills"][self._index].get("regQty")
        except (KeyError, IndexError):
            return STATE_UNKNOWN

    @property
    def extra_state_attributes(self):
        try:
            bill = self.coordinator.data[self._user_code]["monthly_bills"][self._index].get("amt", 0.0)
            return {"consume_bill": bill}
        except (KeyError, IndexError):
            return {"consume_bill": 0.0}

class GASDailyBillSensor(GASBaseSensor):
    """每日用量传感器"""
    def __init__(self, coordinator, user_code, index):
        super().__init__(coordinator)
        self._user_code = user_code
        self._index = index
        self._attr_device_class = SensorDeviceClass.GAS
        self._attr_unique_id = f"{DOMAIN}.{user_code}_daily_{index + 1}"
        self.entity_id = self._attr_unique_id

    @property
    def native_unit_of_measurement(self):
        return UnitOfVolume.CUBIC_METERS

    @property
    def name(self):
        try:
            return self.coordinator.data[self._user_code]["daily_bills"][self._index].get("day")[:10]
        except (KeyError, IndexError):
            return STATE_UNKNOWN

    @property
    def native_value(self):
        try:
            value = self.coordinator.data[self._user_code]["daily_bills"][self._index].get("regQty")
            return value if value is not None and value != "" else STATE_UNKNOWN
        except (KeyError, IndexError):
            return STATE_UNKNOWN
