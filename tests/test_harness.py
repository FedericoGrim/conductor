from conductor.config import HARNESS_NAMES, Profile, Provider
from conductor.harness import HARNESSES, OPENCODE, harness_for


def test_every_harness_name_has_a_harness() -> None:
    assert set(HARNESSES) == set(HARNESS_NAMES)
    assert all(harness.name == name for name, harness in HARNESSES.items())


def test_the_harness_comes_from_the_provider_of_the_model() -> None:
    profile = Profile(
        "medium",
        {"openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "K")},
        (("openrouter/a",),),
        ("openrouter/a",),
    )
    assert harness_for(profile, "openrouter/a") is OPENCODE
