from importlib.metadata import EntryPoint
from unittest.mock import Mock

import pytest

from yamcps import connectors
from yamcps.connectors import ConnectorError
from yamcps.server import create_server


def test_discovery_does_not_import(monkeypatch):
    entry = Mock(name="entry")
    entry.name = "unused"
    monkeypatch.setattr(connectors, "entry_points", lambda **_: [entry])
    assert connectors.discover() == {"unused": entry}
    entry.load.assert_not_called()


def test_duplicate_entries(monkeypatch):
    entry = EntryPoint(name="demo", value="yamcps_demo:DemoConnector", group="yamcps.connectors")
    monkeypatch.setattr(connectors, "entry_points", lambda **_: [entry, entry])
    with pytest.raises(ConnectorError, match="Duplicate"):
        connectors.discover()


@pytest.mark.parametrize("names", [["missing"], ["demo", "demo"]])
def test_selection_errors(names):
    with pytest.raises(ConnectorError):
        create_server(names)


@pytest.mark.parametrize(
    "factory", [lambda: object(), lambda: Mock(id="wrong"), lambda: Mock(id="demo", register=None)]
)
def test_invalid_contract(monkeypatch, factory):
    entry = Mock()
    entry.load.return_value = factory
    monkeypatch.setattr(connectors, "discover", lambda: {"demo": entry})
    with pytest.raises(ConnectorError, match="demo"):
        create_server(["demo"])


def test_registration_failure(monkeypatch):
    plugin = Mock(id="demo", spec=["id", "register"])
    plugin.register.side_effect = RuntimeError("broken")
    entry = Mock()
    entry.load.return_value = lambda: plugin
    monkeypatch.setattr(connectors, "discover", lambda: {"demo": entry})
    with pytest.raises(ConnectorError, match="demo.*registration.*broken"):
        create_server(["demo"])


async def test_connector_without_skills(monkeypatch):
    plugin = Mock(id="demo", spec=["id", "register"])
    entry = Mock()
    entry.load.return_value = lambda: plugin
    monkeypatch.setattr(connectors, "discover", lambda: {"demo": entry})
    assert await create_server(["demo"]).list_resources() == []


def test_duplicate_tools():
    from yamcps.registry import StrictServer

    server = StrictServer(name="test")

    def echo(message: str) -> str:
        return message

    server.add_tool(echo)
    with pytest.raises(ValueError, match="Duplicate tool"):
        server.add_tool(echo)
