# Queries DTE historical usage API for hourly data.

import datetime
import os

import dotenv
import pandas as pd
import requests
from influxdb import InfluxDBClient

# destination measurment for influxdb
MEASUREMENT = "dte/usage/report/electric"


def main():
    dotenv.load_dotenv()

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

    subscription_key = os.getenv("DTE_SUBSCRIPTION_KEY")
    login_data = {
        "username": os.getenv("DTE_USERNAME"),
        "password": os.getenv("DTE_PASSWORD"),
    }
    timezone = os.getenv("DTE_TIMEZONE")
    assert timezone is not None

    end_date = pd.Timestamp.utcnow().tz_convert(timezone).date()
    start_date = end_date - datetime.timedelta(days=30)

    with requests.Session() as s:
        r = s.post(
            "https://newlook.dteenergy.com/api/signIn",
            json=login_data,
        )
        assert r.ok

        r = s.get("https://newlook.dteenergy.com/api/getUserDetails")
        assert r.ok
        authorization = "Bearer " + r.text

        r = s.get(
            "https://newlook.dteenergy.com/api/accounts",
        )
        assert r.ok
        account_id = r.json()["accounts"][0]["accountNumber"]

        base_url = (
            "https://api.customer.sites.dteenergy.com/public/usage/authenticated/"
            + f"accounts/{account_id}/usage/report/electric"
        )
        r = s.get(
            base_url,
            params={
                "startDate": start_date,
                "endDate": end_date,
            },
            headers={
                "Ocp-Apim-Subscription-Key": subscription_key,
                "Authorization": authorization,
            },
        )
        assert r.ok
        data = r.json()

    points = []
    for day_data in data["usage"]:
        day_start_utc = pd.Timestamp.fromtimestamp(day_data["DAY_START_EPOCH"], "UTC")
        day_start_local = day_start_utc.tz_convert(timezone)
        date_local = day_data["DAY_START"]
        date_local = day_start_local.date()
        datetimes_utc = [day_start_utc]
        while (dt := datetimes_utc[-1] + pd.Timedelta(hours=1)).tz_convert(
            timezone
        ).date() == date_local:
            datetimes_utc.append(dt)

        for dt_utc in datetimes_utc:
            dt_local = dt_utc.tz_convert(timezone)
            key = "HR" + str(dt_local.hour + 1).zfill(2) + "_KWH"
            # save as Wh to match our energy-bridge readings
            value = day_data[key] * 1000.0
            if key in day_data:
                points.append(
                    {
                        "measurement": MEASUREMENT,
                        "time": dt_utc.isoformat(),
                        "tags": {},
                        "fields": {"value": value},
                    },
                )

    influxdb_client.write_points(points)


if __name__ == "__main__":
    main()
