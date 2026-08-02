from app.services.paper.analyzer import PaperAnalyzer


def test_analysis_normalizes_scalar_values_for_list_fields() -> None:
    normalized = PaperAnalyzer._normalize_analysis(
        {
            "summary": "Study summary",
            "research_problem": "Research question",
            "method_steps": ["Collect scans", "Fit model"],
            "datasets": "Not a public dataset.",
            "metrics": "AUC",
            "implementation_requirements": (
                "R version and package versions were not provided."
            ),
            "compute_requirements": (
                "A 320-detector-row scanner was used; compute was unspecified."
            ),
            "reproducibility_risks": None,
        }
    )

    assert normalized["datasets"] == ["Not a public dataset."]
    assert normalized["metrics"] == ["AUC"]
    assert normalized["implementation_requirements"] == [
        "R version and package versions were not provided."
    ]
    assert normalized["compute_requirements"] == [
        "A 320-detector-row scanner was used; compute was unspecified."
    ]
    assert normalized["reproducibility_risks"] == []


def test_analysis_normalizes_non_string_items_without_losing_content() -> None:
    normalized = PaperAnalyzer._normalize_analysis(
        {
            "summary": ["First finding", "Second finding"],
            "research_problem": {"task": "classification"},
            "method_steps": [{"step": 1, "action": "prepare data"}],
            "datasets": None,
            "metrics": [0.91],
            "implementation_requirements": [],
            "compute_requirements": [],
            "reproducibility_risks": [],
        }
    )

    assert normalized["summary"] == "First finding; Second finding"
    assert normalized["research_problem"] == '{"task": "classification"}'
    assert normalized["method_steps"] == [
        '{"step": 1, "action": "prepare data"}'
    ]
    assert normalized["metrics"] == ["0.91"]
