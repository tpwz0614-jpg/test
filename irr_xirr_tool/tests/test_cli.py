import json

from irr_xirr_tool import cli


def test_irr_amounts_leading_dash(capsys):
    rc = cli.main(["--amounts", "-1000000,300000,300000,300000,300000,300000", "--rate", "0.08"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "15.23" in out or "15.24" in out
    assert "IRR: 15.2" in out


def test_json_output(capsys):
    rc = cli.main(["--amounts", "-1000000,300000,300000,300000,300000,300000", "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert data["mode"] == "irr"
    assert data["rate_result"]["status"] == "unique"


def test_multiple_roots_reported_exit_zero(capsys):
    rc = cli.main(["--amounts", "-1000,6000,-11000,6000"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "MULTIPLE SOLUTIONS" in out


def test_no_solution_input_error_exit_two(capsys):
    rc = cli.main(["--amounts", "1000,2000,3000"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "Error" in err


def test_dated_mode(capsys):
    rc = cli.main([
        "--dated",
        "2008-01-01:-10000,2008-03-01:2750,2008-10-30:4250,2009-02-15:3250,2009-04-01:2750",
        "--json",
    ])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert rc == 0
    assert data["mode"] == "xirr"
    assert abs(data["rate_result"]["roots"][0] * 100 - 37.34) < 0.01


def test_csv_input(tmp_path, capsys):
    p = tmp_path / "cf.csv"
    p.write_text("amount\n-1000000\n300000\n300000\n300000\n300000\n300000\n")
    rc = cli.main(["--csv", str(p)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "IRR: 15.2" in out
