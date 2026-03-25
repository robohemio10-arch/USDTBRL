from smartcrypto.research.optimizer import default_search_space, research_candidate_configs


def sample_cfg() -> dict:
    return {
        "strategy": {
            "take_profit_pct": 0.6,
            "first_buy_brl": 50.0,
            "trailing_activation_pct": 0.45,
            "trailing_callback_pct": 0.18,
        }
    }


def test_default_search_space_contains_core_parameters() -> None:
    payload = default_search_space()

    assert "take_profit_pct" in payload
    assert payload["first_buy_brl"][0] == 5.0


def test_research_candidate_configs_generates_variants() -> None:
    variants = research_candidate_configs(sample_cfg())

    assert variants
    assert "take_profit_pct" in variants[0][1]
