import datetime
import json
import os
import typing

import dotenv
import paho.mqtt.client as mqtt
import pydantic
from influxdb import InfluxDBClient


class _Config:
    validate_all = True
    validate_assignment = True
    extra = "forbid"


@pydantic.dataclasses.dataclass(frozen=True, config=_Config)
class InstantaneousDemand:
    time: datetime.datetime
    demand: pydantic.conint(strict=True, ge=0)

    def as_point(self):
        return {
            "measurement": "event/metering/instantaneous_demand",
            "time": self.time.isoformat(),
            "tags": {},
            "fields": {
                "value": self.demand,
            },
        }


@pydantic.dataclasses.dataclass(frozen=True, config=_Config)
class MinutelyDemand:
    type: typing.Literal["minute"]
    time: datetime.datetime
    local_time: datetime.datetime
    value: pydantic.confloat(strict=True, ge=0)

    def as_point(self):
        return {
            "measurement": "event/metering/summation/minute",
            "time": self.time.isoformat(),
            "tags": {},
            "fields": {
                "value": self.value,
            },
        }


TOPIC_MAP = {
    "event/metering/instantaneous_demand": InstantaneousDemand,
    "event/metering/summation/minute": MinutelyDemand,
}


def on_message(influxdb_client):
    def process(mqtt_client, userdata, message):
        type_ = TOPIC_MAP.get(message.topic, None)
        if type_ is None:
            return
        data = type_(**json.loads(message.payload))
        influxdb_client.write_points([data.as_point()])

    return process


def main():
    dotenv.load_dotenv()
    mqtt_client = mqtt.Client("Energy Bridge")
    mqtt_client.connect(
        os.getenv("ENERGY_BRIDGE_IP"),
        int(os.getenv("ENERGY_BRIDGE_PORT")),
    )
    mqtt_client.subscribe("#")

    influxdb_client = InfluxDBClient(
        os.getenv("INFLUXDB_ADDRESS"),
        8086,
        os.getenv("INFLUXDB_USER"),
        os.getenv("INFLUXDB_PASSWORD"),
        None,
    )
    db_name = os.getenv("INFLUXDB_DATABASE")
    assert {"name": db_name} in influxdb_client.get_list_database()
    influxdb_client.switch_database(db_name)

    mqtt_client.on_message = on_message(influxdb_client)
    mqtt_client.loop_forever()


if __name__ == "__main__":
    main()
