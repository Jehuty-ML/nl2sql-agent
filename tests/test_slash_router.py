from app.core.routing.slash_router import normalize_slash, route_input


def test_fixed_slash_dau():
    r = route_input("/dau")
    assert r["execution_path"] == "fixed_slash"
    assert r["analysis_key"] == "dau"


def test_fixed_slash_alias():
    r = route_input("/today_dashboard")
    assert r["execution_path"] == "fixed_slash"
    assert r["resolved_command"] == "/overview"


def test_natural_language_goes_agent_loop():
    r = route_input("最近日活怎么样")
    assert r["execution_path"] == "agent_loop"


def test_unknown_slash():
    r = route_input("/not_exist")
    assert r["execution_path"] == "unknown_slash"


def test_normalize():
    assert normalize_slash("/Funnel extra") == "/funnel"
