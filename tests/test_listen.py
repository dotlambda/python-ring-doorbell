"""The tests for the Ring platform."""

import datetime
import json

import pytest
from ring_doorbell import Ring
from ring_doorbell.exceptions import RingError
from ring_doorbell.listen import can_listen

from tests.conftest import load_fixture

# test_module.py
pytestmark = pytest.mark.skipif(
    can_listen is False, reason=("requires the extra [listen] to be installed")
)

if can_listen:
    from ring_doorbell.listen import RingEventListener


async def test_listen(auth, mocker):
    import firebase_messaging

    ring = Ring(auth)
    listener = RingEventListener(ring)

    await listener.start()
    assert firebase_messaging.FcmPushClient.checkin_or_register.call_count == 1
    assert firebase_messaging.FcmPushClient.start.call_count == 1
    assert listener.subscribed is True
    assert listener.started is True

    with pytest.raises(RingError, match="ID 10 is not a valid callback id"):
        listener.remove_notification_callback(10)

    with pytest.raises(
        RingError,
        match="Cannot remove the default callback for ring-doorbell with value 1",
    ):
        listener.remove_notification_callback(1)

    cbid = listener.add_notification_callback(lambda: 2)
    del listener._callbacks[1]
    listener.remove_notification_callback(cbid)


async def test_active_dings(auth, mocker):
    import firebase_messaging

    ring = Ring(auth)
    listener = RingEventListener(ring)
    await listener.start()
    assert firebase_messaging.FcmPushClient.checkin_or_register.call_count == 1
    assert firebase_messaging.FcmPushClient.start.call_count == 1
    assert listener.subscribed is True
    assert listener.started is True
    num_active = len(ring.active_alerts())
    assert num_active == 0
    alertstoadd = 2
    for i in range(alertstoadd):
        msg = json.loads(load_fixture("ring_listen_fcmdata.json"))
        gcmdata_dict = json.loads(load_fixture("ring_listen_ding.json"))
        created_at = datetime.datetime.utcnow().isoformat(timespec="milliseconds") + "Z"  # noqa: DTZ003
        gcmdata_dict["ding"]["created_at"] = created_at
        gcmdata_dict["ding"]["id"] = gcmdata_dict["ding"]["id"] + i
        msg["data"]["gcmData"] = json.dumps(gcmdata_dict)
        listener._on_notification(msg, "1234567" + str(i))

    dings = ring.active_alerts()
    assert len(dings) == num_active + alertstoadd
    # Test with the same id which should overwrite
    # previous and keep the overall count the same
    for i in range(alertstoadd):
        msg = json.loads(load_fixture("ring_listen_fcmdata.json"))
        gcmdata_dict = json.loads(load_fixture("ring_listen_ding.json"))
        created_at = datetime.datetime.utcnow().isoformat(timespec="milliseconds") + "Z"  # noqa: DTZ003
        gcmdata_dict["ding"]["created_at"] = created_at
        gcmdata_dict["ding"]["id"] = gcmdata_dict["ding"]["id"] + 1
        msg["data"]["gcmData"] = json.dumps(gcmdata_dict)
        listener._on_notification(msg, "1234567" + str(i))

    dings = ring.active_alerts()
    assert len(dings) == num_active + alertstoadd
    await listener.stop()


async def test_intercom_unlock(auth, mocker):
    import firebase_messaging

    ring = Ring(auth)
    listener = RingEventListener(ring)
    await listener.start()
    assert firebase_messaging.FcmPushClient.checkin_or_register.call_count == 1
    assert firebase_messaging.FcmPushClient.start.call_count == 1
    assert listener.subscribed is True
    assert listener.started is True
    num_active = len(ring.active_alerts())
    assert num_active == 0
    alertstoadd = 2
    for i in range(alertstoadd):
        msg = json.loads(load_fixture("ring_listen_fcmdata.json"))
        gcmdata_dict = json.loads(load_fixture("ring_listen_intercom_unlock.json"))
        msg["data"]["gcmData"] = json.dumps(gcmdata_dict)
        listener._on_notification(msg, "1234567" + str(i))

    dings = ring.active_alerts()
    assert len(dings) == num_active + alertstoadd

    await listener.stop()


@pytest.mark.nolistenmock
async def test_listen_subscribe_fail(auth, mocker, caplog, putpatch_status_fixture):
    checkinmock = mocker.patch(
        "firebase_messaging.FcmPushClient.checkin_or_register", return_value="foobar"
    )
    connectmock = mocker.patch("firebase_messaging.FcmPushClient.start")
    mocker.patch("firebase_messaging.FcmPushClient.is_started", return_value=True)

    putpatch_status_fixture.overrides["https://api.ring.com/clients_api/device"] = 401

    ring = Ring(auth)
    listener = RingEventListener(ring)
    await listener.start()
    # Check in gets and error so register is called
    assert checkinmock.call_count == 1
    assert listener.subscribed is False
    assert listener.started is False
    assert connectmock.call_count == 0

    exp = (
        "Unable to checkin to listen service, "
        "response was 401 , event listener not started"
    )
    assert (
        len(
            [
                record
                for record in caplog.records
                if record.levelname == "ERROR" and record.message == exp
            ]
        )
        == 1
    )


@pytest.mark.nolistenmock
async def test_listen_gcm_fail(auth, mocker):
    # Check in gets and error so register is called, the subscribe gets an error
    credentials = json.loads(load_fixture("ring_listen_credentials.json"))
    checkinmock = mocker.patch(
        "firebase_messaging.fcmregister.FcmRegister.gcm_check_in", return_value=None
    )
    registermock = mocker.patch(
        "firebase_messaging.fcmregister.FcmRegister.register", return_value=credentials
    )
    connectmock = mocker.patch("firebase_messaging.FcmPushClient.start")
    mocker.patch("firebase_messaging.FcmPushClient.is_started", return_value=True)

    ring = Ring(auth)
    listener = RingEventListener(ring, credentials)
    await listener.start()
    # Check in gets and error so register is called
    assert checkinmock.call_count == 1
    assert registermock.call_count == 1
    assert listener.subscribed is True
    assert listener.started is True
    assert connectmock.call_count == 1


@pytest.mark.nolistenmock
async def test_listen_fcm_fail(auth, mocker, caplog):
    checkinmock = mocker.patch(
        "firebase_messaging.FcmPushClient.checkin_or_register", return_value=None
    )
    connectmock = mocker.patch("firebase_messaging.FcmPushClient.start")
    mocker.patch("firebase_messaging.FcmPushClient.is_started", return_value=True)

    ring = Ring(auth)
    listener = RingEventListener(ring)
    await listener.start()
    # Check in gets and error so register is called
    assert checkinmock.call_count == 1

    assert listener.subscribed is False
    assert listener.started is False
    assert connectmock.call_count == 0
    exp = "Ring listener unable to check in to fcm, event listener not started"
    assert (
        len(
            [
                record
                for record in caplog.records
                if record.levelname == "ERROR" and record.message == exp
            ]
        )
        == 1
    )
