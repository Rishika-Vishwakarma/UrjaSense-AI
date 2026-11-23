"""Print model evaluation (hold-out MAE / R2 vs a naive baseline)."""
import json

from ai_ml.training import train

if __name__ == "__main__":
    print(json.dumps(train(save=False), indent=2))
