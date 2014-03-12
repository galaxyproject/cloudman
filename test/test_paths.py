from cm.util.bunch import Bunch
from cm.util.paths import PathResolver


def test_ud_path_overrides():
    manager = Bunch(app=Bunch(ud={"galaxy_home": "/opt/galaxy/app", "other_path": "/opt/other_override"}))
    path_resolver = PathResolver(manager)
    assert path_resolver.galaxy_home == "/opt/galaxy/app"
    assert path_resolver._get_ud_path("other_path", "/opt/other_default") == "/opt/other_override"
