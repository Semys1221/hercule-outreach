from instantly_client import instantly_name_from_config, instantly_resource_name


def test_instantly_resource_name_strips_hercule_and_france_suffix() -> None:
    assert instantly_resource_name("Hercule — Notaires (France)") == "Notaires"
    assert instantly_resource_name("Médecin esthétique (France)") == "Médecin esthétique"


def test_instantly_name_from_config_prefers_explicit() -> None:
    config = {"INSTANTLY_NAME": "Expert-comptable"}
    assert instantly_name_from_config(config, "Cabinets expertise comptable (France)") == "Expert-comptable"
