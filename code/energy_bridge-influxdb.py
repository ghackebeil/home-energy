import datetime
import json
import os

import dotenv
import paho.mqtt.client as mqtt
from influxdb import InfluxDBClient

TOPIC_MAP = {
    "event/metering/instantaneous_demand": lambda *, time, demand: {
        "time": datetime.datetime.fromtimestamp(
            time // 1000, datetime.timezone.utc
        ).isoformat(),
        "tags": {},
        "fields": {
            "value": int(demand),
        },
    },
    "event/metering/summation/minute": lambda *, type, time, local_time, value: {
        "time": datetime.datetime.fromtimestamp(
            time // 1000, datetime.timezone.utc
        ).isoformat(),
        "tags": {},
        "fields": {
            "value": float(value),
        },
    },
}


def on_message(influxdb_client):
    def process(mqtt_client, userdata, message):
        as_point = TOPIC_MAP.get(message.topic, None)
        if as_point is None:
            return
        point = as_point(**json.loads(message.payload))
        point["measurement"] = message.topic
        influxdb_client.write_points([point])

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
