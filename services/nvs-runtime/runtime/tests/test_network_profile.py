from runtime.core.network_profile import load_network_profile


def test_local_profile_matches_exp_ubuntu010_baseline():
    profile = load_network_profile("local")
    assert profile.mode == "local"
    assert profile.base_rtt_ms == 2


def test_wan_profile_matches_exp_ubuntu010b_measurement():
    """EXP-Ubuntu010B measured ~155ms WAN RTT (Ubuntu -> GCP) — the WAN
    profile's base_rtt_ms must reflect that measurement, not a guess."""
    profile = load_network_profile("wan")
    assert profile.mode == "wan"
    assert profile.base_rtt_ms == 155
    assert profile.async_only is True
    assert profile.keep_alive is True
    assert profile.retry_count >= 1


def test_gcp_internal_profile_between_local_and_wan():
    profile = load_network_profile("gcp_internal")
    assert profile.mode == "gcp"
    local = load_network_profile("local")
    wan = load_network_profile("wan")
    assert local.base_rtt_ms < profile.base_rtt_ms < wan.base_rtt_ms


def test_unknown_profile_name_raises():
    import pytest

    with pytest.raises(ValueError):
        load_network_profile("nonexistent-profile")


def test_env_override_takes_precedence_over_active_profile(monkeypatch):
    monkeypatch.setenv("SENSOS_ENV", "wan")
    profile = load_network_profile()
    assert profile.mode == "wan"


def test_explicit_arg_takes_precedence_over_env(monkeypatch):
    monkeypatch.setenv("SENSOS_ENV", "wan")
    profile = load_network_profile("local")
    assert profile.mode == "local"
