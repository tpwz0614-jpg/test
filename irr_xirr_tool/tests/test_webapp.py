import io

import pytest

from irr_xirr_tool.webapp import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_index_loads(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"IRR" in r.data


def test_manual_irr(client):
    r = client.post(
        "/calculate",
        data={
            "input_type": "manual",
            "manual_mode": "irr",
            "amount[]": ["-1000000", "300000", "300000", "300000", "300000", "300000"],
            "rate_pct": "8",
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    assert b"15.2382" in r.data


def test_manual_xirr(client):
    r = client.post(
        "/calculate",
        data={
            "input_type": "manual",
            "manual_mode": "xirr",
            "date[]": ["2008-01-01", "2008-03-01", "2008-10-30", "2009-02-15", "2009-04-01"],
            "amount[]": ["-10000", "2750", "4250", "3250", "2750"],
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    assert "37.336".encode() in r.data or "37.3362".encode() in r.data


def test_multiple_roots_warning(client):
    r = client.post(
        "/calculate",
        data={"input_type": "manual", "manual_mode": "irr", "amount[]": ["-1000", "6000", "-11000", "6000"]},
        content_type="multipart/form-data",
    )
    assert "複数解あり".encode() in r.data


def test_same_sign_shows_input_error(client):
    r = client.post(
        "/calculate",
        data={"input_type": "manual", "manual_mode": "irr", "amount[]": ["1000", "2000", "3000"]},
        content_type="multipart/form-data",
    )
    assert "入力エラー".encode() in r.data


def test_no_real_root_shows_message(client):
    r = client.post(
        "/calculate",
        data={"input_type": "manual", "manual_mode": "irr", "amount[]": ["-1", "3", "-3"]},
        content_type="multipart/form-data",
    )
    assert "実数解なし".encode() in r.data


def test_csv_upload(client):
    csv_bytes = b"amount\n-1000000\n300000\n300000\n300000\n300000\n300000\n"
    r = client.post(
        "/calculate",
        data={"input_type": "csv", "file": (io.BytesIO(csv_bytes), "cf.csv")},
        content_type="multipart/form-data",
    )
    assert b"15.2382" in r.data


def test_csv_missing_file_shows_error(client):
    r = client.post(
        "/calculate",
        data={"input_type": "csv"},
        content_type="multipart/form-data",
    )
    assert "入力エラー".encode() in r.data
