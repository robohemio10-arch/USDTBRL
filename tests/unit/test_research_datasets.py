from smartcrypto.research.datasets import anchored_walkforward_splits, build_training_dataset
from tests.fixtures.sample_data import make_ohlcv


def sample_cfg() -> dict:
    return {
        "execution": {"fee_rate": 0.001},
        "research": {"label_horizon": 2, "shadow_slippage_bps": 8.0},
    }


def test_build_training_dataset_appends_labels() -> None:
    frame = build_training_dataset("USDT/BRL", make_ohlcv(120), sample_cfg())
    assert "dataset" in frame.columns
    assert "target_net_return_h" in frame.columns
    assert frame["dataset"].iloc[0] == "usdtbrl_dataset"


def test_anchored_walkforward_respects_purge_gap() -> None:
    frame = build_training_dataset("USDT/BRL", make_ohlcv(150), sample_cfg())
    splits = anchored_walkforward_splits(frame, folds=2, train_ratio=0.6, min_train_rows=40, min_test_rows=10, purge_gap=3)
    assert splits
    for split in splits:
        assert split["purge_gap"] == 3
        assert len(split["test"]) >= 10
