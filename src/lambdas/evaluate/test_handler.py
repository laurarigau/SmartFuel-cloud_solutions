
import importlib.util
from pathlib import Path


def test_evaluate_candidate():
    path = Path(__file__).with_name("handler.py")
    spec = importlib.util.spec_from_file_location(
        "phase_c_evaluate_handler", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    candidate = {
        "metrics": {
            "macro_f1": 0.4199,
            "baseline_macro_f1": 0.3084
        }
    }

    result = module.evaluate(candidate)

    assert result["status"] == "eligible_for_manual_review"
    assert result["production_promoted"] is False

