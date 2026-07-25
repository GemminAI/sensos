from runtime.services.crystallizer import (
    compute_epistemic_diffusion_state,
    crystallize_state_hash,
)


def test_crystallize_state_hash_deterministic():
    tags = {"T09": [0.1] * 6, "T10": 0.7, "T19": 0.2}
    h1 = crystallize_state_hash("narrative text", tags, "us")
    h2 = crystallize_state_hash("narrative text", tags, "us")
    assert h1 == h2
    assert len(h1) == 64


def test_epistemic_diffusion_state():
    assert compute_epistemic_diffusion_state({"T19": 0.7}) == "high_conflict"
    assert compute_epistemic_diffusion_state({"T10": 0.2, "T19": 0.1}) == "low_confidence"
    assert compute_epistemic_diffusion_state({"T10": 0.8, "T19": 0.1}) == "stable"
