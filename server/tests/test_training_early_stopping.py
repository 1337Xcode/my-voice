"""The trainer's epoch loop: it keeps the best epoch by validation WER and stops only after PATIENCE epochs without a gain."""

import pytest

from voice.training import trainer


class FakeModel:
    """Stands in for the PEFT model: its weights are the number of the epoch that last trained it."""

    def __init__(self):
        self.epoch = 0
        self.loaded = None

    def state_dict(self):
        return {"lora_A": self.epoch}

    def load_state_dict(self, state, strict=True):
        self.loaded = state["lora_A"]


def run_with_val_wers(monkeypatch, wers: list[float], patience: int, max_epochs: int, budget_s: float = 1e9):
    """Runs the epoch loop with scripted validation WERs (one per epoch); returns (result, model)."""
    model, epochs = FakeModel(), iter(range(1, 100))

    def fake_train_epoch(model, *args):
        model.epoch = next(epochs)
        return 1.0

    monkeypatch.setattr(trainer, "train_epoch", fake_train_epoch)
    monkeypatch.setattr(trainer, "validate", lambda model, *args: (wers[model.epoch - 1], 1.0))
    monkeypatch.setattr(trainer, "adapter_state", lambda model: model.state_dict())
    monkeypatch.setattr(trainer, "PATIENCE", patience)
    monkeypatch.setattr(trainer, "MAX_EPOCHS", max_epochs)
    monkeypatch.setattr(trainer, "TRAIN_BUDGET_S", budget_s)
    result = trainer.run_epochs(model, None, None, None, [], [], [], None, "cpu", 4, lambda *args: None)
    return result, model


def test_defaults_are_patience_5_and_25_epochs():
    assert (trainer.PATIENCE, trainer.MAX_EPOCHS) == (5, 25)
    assert (trainer.HYPERPARAMETERS["patience"], trainer.HYPERPARAMETERS["max_epochs"]) == (5, 25)


def test_a_plateau_shorter_than_patience_does_not_stop_training(monkeypatch):
    # Four flat epochs after epoch 2, then a gain: patience 3 would stop at epoch 5 and miss it.
    wers = [50.0, 40.0, 45.0, 45.0, 45.0, 45.0, 30.0, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0]
    result, model = run_with_val_wers(monkeypatch, wers, patience=5, max_epochs=25)
    assert (result.best_epoch, result.best_val_wer) == (7, 30.0)
    assert model.loaded == 7


def test_training_stops_after_patience_epochs_without_gain(monkeypatch):
    wers = [50.0, 40.0] + [45.0] * 20
    result, _ = run_with_val_wers(monkeypatch, wers, patience=5, max_epochs=25)
    assert result.epochs_run == 7 and result.best_epoch == 2
    assert result.stopped == "no validation gain for 5 epochs"


def test_the_epoch_cap_ends_a_run_that_keeps_improving(monkeypatch):
    wers = [100.0 - epoch for epoch in range(30)]
    result, model = run_with_val_wers(monkeypatch, wers, patience=5, max_epochs=25)
    assert result.epochs_run == 25 and model.loaded == 25
    assert result.stopped == "25 epochs"


@pytest.mark.parametrize("patience", [3, 5])
def test_ties_in_wer_do_not_count_as_a_gain(monkeypatch, patience):
    wers = [40.0] * 20
    result, _ = run_with_val_wers(monkeypatch, wers, patience=patience, max_epochs=25)
    assert result.best_epoch == 1 and result.epochs_run == 1 + patience
