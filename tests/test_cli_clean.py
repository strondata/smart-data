
from typer.testing import CliRunner

from aptdata.cli.app import app

runner = CliRunner()

def test_mesh_clean():
    result = runner.invoke(app, ["mesh", "clean", "--json", "--dir", "aptdata/core"])
    assert result.exit_code == 0
    assert "mesh.clean.started" in result.stdout
    assert "mesh.clean.completed" in result.stdout
