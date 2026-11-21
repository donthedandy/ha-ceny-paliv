import pytest
import custom_components
from homeassistant import loader
pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def _auto(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    hass.data[loader.DATA_CUSTOM_COMPONENTS] = {"ceny_paliv": loader.Integration.resolve_from_root(hass, custom_components, "ceny_paliv")}
    yield


@pytest.fixture
def expected_lingering_timers() -> bool:
    """Home Assistant's own storage helper can leave a delayed-write timer after a test (seen on GitHub only); it is not ours."""
    return True
