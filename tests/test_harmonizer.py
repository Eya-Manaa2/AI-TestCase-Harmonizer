from io import BytesIO
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts.annotation_report import cohen_kappa, summarize_annotations
from scripts.evaluate import evaluate_pair_annotations
from scripts.merge_annotations import merge_annotation_sheets, read_annotation_files
from scripts.profile_dataset import profile_cases
from scripts.prepare_annotations import build_annotation_rows
from scripts.split_annotation_batches import build_batches
from harmonizer.analyzer import analyze_cases
from harmonizer.client import analyze_via_api
from harmonizer.io import load_cases, records_to_cases
from harmonizer.ollama import standardize_with_ollama
from harmonizer.readiness import assess_readiness
from harmonizer.standardizer import discover_keywords, standardize_case


def test_loads_csv_and_normalizes_common_column_names():
    cases = load_cases(
        b"test_case_id,test_name,test_steps,expected_result\nT-1,Login,Click login,Dashboard shown\n",
        "tests.csv",
    )
    assert cases[0]["id"] == "T-1"
    assert cases[0]["title"] == "Login"
    assert cases[0]["steps"] == "Click login"


def test_loads_excel_workbook():
    buffer = BytesIO()
    pd.DataFrame(
        [{"id": "T-1", "title": "Login", "steps": "Click Login"}]
    ).to_excel(buffer, index=False)
    cases = load_cases(buffer.getvalue(), "tests.xlsx")
    assert cases[0]["title"] == "Login"


def test_invalid_excel_file_returns_actionable_error():
    try:
        load_cases(b"not an excel workbook", "broken.xlsx")
    except ValueError as exc:
        assert "Classeur Excel invalide" in str(exc)
    else:
        raise AssertionError("Expected malformed Excel workbook to be rejected")


def test_loads_manual_testing_workbook_with_offset_header_and_ignores_section_rows():
    buffer = BytesIO()
    source = pd.DataFrame(
        [
            ["", "API testing plan", "", "", "", "", ""],
            ["Case No.", "Description", "Menu Name", "Test Cases", "Test Steps", "Test Data", "Expected Output"],
            ["1", "Header", "", "Section title", "", "", ""],
            ["2", "Observation", "API", "Verify GET request", "", "valid token", "Status is 200"],
        ]
    )
    with pd.ExcelWriter(buffer) as writer:
        source.to_excel(writer, sheet_name="Test Cases", index=False, header=False)
    cases = load_cases(buffer.getvalue(), "manual_test_cases.xlsx")
    assert len(cases) == 1
    assert cases[0]["id"] == "2"
    assert cases[0]["title"] == "Verify GET request"
    assert cases[0]["steps"] == "Verify GET request"
    assert cases[0]["expected_result"] == "Status is 200"


def test_loads_included_public_manual_testing_corpus():
    dataset_path = Path(__file__).parent.parent / "data" / "TestCases_for_ApiTesting.xlsx"
    cases = load_cases(dataset_path.read_bytes(), dataset_path.name)
    assert len(cases) == 62
    assert cases[0]["title"].startswith("Verify by sending")
    assert cases[0]["steps"] == cases[0]["title"]


def test_profiles_literal_duplicate_groups_without_claiming_semantic_equivalence():
    cases = records_to_cases(
        [
            {"id": "A", "title": "Login!", "steps": "Click Login"},
            {"id": "B", "title": " login ", "steps": "Click Login"},
            {"id": "C", "title": "Logout", "steps": "Click Logout"},
        ]
    )
    result = profile_cases(cases)
    assert result["case_count"] == 3
    assert result["unique_normalized_cases"] == 2
    assert result["duplicate_pairs"] == 1
    assert [case["id"] for case in result["duplicate_groups"][0]] == ["A", "B"]


def test_rejects_duplicate_ids():
    try:
        records_to_cases([{"id": "T-1", "title": "A"}, {"id": "T-1", "title": "B"}])
    except ValueError as exc:
        assert "dupliqué" in str(exc)
    else:
        raise AssertionError("Expected duplicate IDs to be rejected")


def test_detects_paraphrased_login_cases():
    cases = records_to_cases(
        [
            {
                "id": "A",
                "title": "Login with valid credentials",
                "preconditions": "User account exists",
                "steps": "Open the login page; enter username and password; click Login",
                "expected_result": "Dashboard is displayed",
            },
            {
                "id": "B",
                "title": "Authenticate with correct details",
                "preconditions": "User account exists",
                "steps": "Navigate to authentication screen; type username and password; press login button",
                "expected_result": "Dashboard is displayed",
            },
        ]
    )
    result = analyze_cases(cases, threshold=0.55)
    assert len(result["pairs"]) == 1
    assert result["pairs"][0]["score"] >= 0.55


def test_finds_normalized_exact_duplicates_below_similarity_threshold():
    cases = records_to_cases(
        [
            {"id": "A", "title": "Login!", "steps": "Click the button."},
            {"id": "B", "title": " login ", "steps": "Click the button"},
        ]
    )
    result = analyze_cases(cases, threshold=0.95)
    assert len(result["pairs"]) == 1
    assert result["pairs"][0]["exact"] is True


def test_handles_text_without_indexable_characters():
    cases = records_to_cases([{"id": "A", "title": "😀"}, {"id": "B", "title": "✨"}])
    assert analyze_cases(cases)["pairs"] == []


def test_embeddings_are_used_even_when_tfidf_cannot_tokenize_source_text():
    cases = records_to_cases([{"id": "A", "title": "😀"}, {"id": "B", "title": "✨"}])

    class FakeEmbeddingModel:
        def encode(self, documents, **kwargs):
            assert len(documents) == 2
            assert all(any(symbol in document for symbol in ("😀", "✨")) for document in documents)
            return np.array([[1.0, 0.0], [0.98, 0.2]])

    result = analyze_cases(cases, threshold=0.9, embedding_model=FakeEmbeddingModel())
    assert len(result["pairs"]) == 1


def test_ollama_response_is_schema_validated():
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {"response": json.dumps({"steps": ["Click Login"], "notes": []})}
            ).encode()

    with patch("harmonizer.ollama.urlopen", return_value=FakeResponse()):
        result = standardize_with_ollama({"title": "Login"})
    assert result == {"steps": ["Click Login"], "notes": []}


def test_standardizes_actions_and_reports_missing_expected_result():
    case = records_to_cases([{"id": "T1", "title": "Login", "steps": "Open login page; click Login"}])[0]
    proposal = standardize_case(case)
    assert "NAVIGATE" in proposal["standardized_steps"]
    assert "CLICK" in proposal["standardized_steps"]
    assert proposal["missing_expected_result"] is True
    assert "NAVIGATE" in {row["Keyword"] for row in discover_keywords([case])}


def test_readiness_rewards_explicit_test_oracles():
    incomplete = {"title": "Test", "preconditions": "", "steps": "Click button", "expected_result": ""}
    complete = {
        "title": "Test",
        "preconditions": "User is signed in",
        "steps": "Open profile page\nClick Save",
        "expected_result": "Profile is saved",
    }
    assert assess_readiness(complete)["score"] > assess_readiness(incomplete)["score"]


def test_pairwise_evaluation_uses_only_adjudicated_pairs():
    cases = records_to_cases(
        [
            {"id": "A", "title": "Login", "steps": "Click Login"},
            {"id": "B", "title": " login ", "steps": "Click Login"},
            {"id": "C", "title": "Logout", "steps": "Click Logout"},
        ]
    )
    annotations = pd.DataFrame(
        [
            {"case_id_a": "A", "case_id_b": "B", "decision": "equivalent"},
            {"case_id_a": "A", "case_id_b": "C", "decision": "not_related"},
            {"case_id_a": "B", "case_id_b": "C", "decision": "insufficient_information"},
        ]
    )
    result = evaluate_pair_annotations(cases, annotations, [0.95])[0]
    assert result["annotated_pairs"] == 2
    assert result["true_positive"] == 1
    assert result["true_negative"] == 1


def test_pairwise_evaluation_uses_adjudications_and_excludes_pending_rows():
    cases = records_to_cases(
        [
            {"id": "A", "title": "Login", "steps": "Click Login"},
            {"id": "B", "title": " login ", "steps": "Click Login"},
            {"id": "C", "title": "Logout", "steps": "Click Logout"},
        ]
    )
    annotations = pd.DataFrame(
        [
            {
                "case_id_a": "A",
                "case_id_b": "B",
                "annotator_1_decision": "equivalent",
                "annotator_2_decision": "not_related",
                "adjudicated_decision": "equivalent",
            },
            {
                "case_id_a": "A",
                "case_id_b": "C",
                "annotator_1_decision": "not_related",
                "annotator_2_decision": "not_related",
                "adjudicated_decision": "not_related",
            },
            {
                "case_id_a": "B",
                "case_id_b": "C",
                "annotator_1_decision": "equivalent",
                "annotator_2_decision": "",
                "adjudicated_decision": "",
            },
        ]
    )
    result = evaluate_pair_annotations(cases, annotations, [0.95])[0]
    assert result["annotated_pairs"] == 2
    assert result["unresolved_pairs"] == 1
    assert result["true_positive"] == 1
    assert result["true_negative"] == 1


def test_five_class_labels_map_to_documented_binary_redundancy_target():
    cases = records_to_cases(
        [
            {"id": "D", "title": "Login", "steps": "Click Login"},
            {"id": "E", "title": " login ", "steps": "Click Login"},
            {"id": "R", "title": "Logout", "steps": "Click Logout"},
            {"id": "F", "title": "Profile", "steps": "Open profile"},
            {"id": "U", "title": "Missing oracle", "steps": "Update record"},
        ]
    )
    annotations = pd.DataFrame(
        [
            {"case_id_a": "D", "case_id_b": "E", "adjudicated_decision": "Duplicate"},
            {"case_id_a": "D", "case_id_b": "R", "adjudicated_decision": "equivalent"},
            {"case_id_a": "D", "case_id_b": "F", "adjudicated_decision": "related"},
            {"case_id_a": "R", "case_id_b": "F", "adjudicated_decision": "Different"},
            {"case_id_a": "E", "case_id_b": "U", "adjudicated_decision": "uncertain"},
        ]
    )
    result = evaluate_pair_annotations(cases, annotations, [0.95])[0]
    assert result["annotated_pairs"] == 4
    assert result["duplicate_pairs"] == 1
    assert result["equivalent_pairs"] == 1
    assert result["related_pairs"] == 1
    assert result["different_pairs"] == 1
    assert result["insufficient_information_pairs"] == 1
    assert result["uncertain_pairs"] == 1
    assert result["true_positive"] == 1
    assert result["false_negative"] == 1
    assert result["true_negative"] == 2


def test_pairwise_evaluation_reports_all_unannotated_pairs_without_fake_metrics():
    cases = records_to_cases(
        [
            {"id": "A", "title": "Login"},
            {"id": "B", "title": "Logout"},
        ]
    )
    annotations = pd.DataFrame(
        [
            {
                "case_id_a": "A",
                "case_id_b": "B",
                "annotator_1_decision": "",
                "annotator_2_decision": "",
                "adjudicated_decision": "",
            }
        ]
    )
    result = evaluate_pair_annotations(cases, annotations, [0.4])[0]
    assert result["annotated_pairs"] == 0
    assert result["unresolved_pairs"] == 1
    assert result["f1"] is None


def test_annotation_sheet_contains_independent_decisions_and_case_context():
    cases = records_to_cases(
        [
            {"id": "A", "title": "Login", "steps": "Click Login"},
            {"id": "B", "title": "Logout", "steps": "Click Logout"},
        ]
    )
    rows = build_annotation_rows(cases)
    assert len(rows) == 1
    assert rows[0]["case_id_a"] == "A"
    assert rows[0]["steps_b"] == "Click Logout"
    assert rows[0]["annotator_1_decision"] == ""
    assert rows[0]["adjudicated_decision"] == ""


def test_blinded_annotation_sheets_merge_only_after_independent_completion():
    cases = records_to_cases(
        [
            {"id": "A", "title": "Login"},
            {"id": "B", "title": "Logout"},
        ]
    )
    row = build_annotation_rows(cases)[0]
    key_columns = ["pair_id", "case_id_a", "case_id_b"]
    annotator_1 = pd.DataFrame(
        [{**{key: row[key] for key in key_columns}, "annotator_1_decision": "duplicate", "annotator_1_rationale": "same"}]
    )
    annotator_2 = pd.DataFrame(
        [
            {
                **{key: row[key] for key in key_columns},
                "annotator_2_decision": "duplicate",
                "annotator_2_rationale": "same case",
            }
        ]
    )
    adjudication = pd.DataFrame(
        [
            {
                **{key: row[key] for key in key_columns},
                "adjudicated_decision": "duplicate",
                "adjudicator_rationale": "agreement",
            }
        ]
    )
    merged = merge_annotation_sheets(annotator_1, annotator_2, adjudication)
    assert merged.loc[0, "annotator_1_decision"] == "duplicate"
    assert merged.loc[0, "annotator_2_decision"] == "duplicate"
    assert merged.loc[0, "adjudicated_decision"] == "duplicate"


def test_annotation_merge_uses_consensus_and_leaves_unresolved_disagreement_blank():
    cases = records_to_cases(
        [
            {"id": "A", "title": "Login"},
            {"id": "B", "title": "Logout"},
            {"id": "C", "title": "Profile"},
        ]
    )
    rows = build_annotation_rows(cases)
    keys = ["pair_id", "case_id_a", "case_id_b"]
    annotator_1 = pd.DataFrame(
        [
            {
                **{key: rows[index][key] for key in keys},
                "annotator_1_decision": decision,
                "annotator_1_rationale": "",
            }
            for index, decision in enumerate(("duplicate", "related", "different"))
        ]
    )
    annotator_2 = pd.DataFrame(
        [
            {
                **{key: rows[index][key] for key in keys},
                "annotator_2_decision": decision,
                "annotator_2_rationale": "",
            }
            for index, decision in enumerate(("duplicate", "different", "uncertain"))
        ]
    )
    adjudication = pd.DataFrame(
        [
            {
                **{key: row[key] for key in keys},
                "adjudicated_decision": "",
                "adjudicator_rationale": "",
            }
            for row in rows
        ]
    )
    merged = merge_annotation_sheets(annotator_1, annotator_2, adjudication)
    assert merged.loc[0, "adjudicated_decision"] == "duplicate"
    assert merged.loc[1, "adjudicated_decision"] == ""
    assert merged.loc[2, "adjudicated_decision"] == ""


def test_blinded_annotation_merge_rejects_mismatched_pair_lists():
    base = pd.DataFrame(
        [{"pair_id": "P1", "case_id_a": "A", "case_id_b": "B"}]
    )
    annotator_1 = base.assign(annotator_1_decision="duplicate", annotator_1_rationale="")
    annotator_2 = base.assign(pair_id="P2", annotator_2_decision="duplicate", annotator_2_rationale="")
    adjudication = base.assign(adjudicated_decision="", adjudicator_rationale="")
    try:
        merge_annotation_sheets(annotator_1, annotator_2, adjudication)
    except ValueError as exc:
        assert "même ensemble de paires" in str(exc)
    else:
        raise AssertionError("Expected mismatched annotator sheets to be rejected")


def test_annotation_batch_builder_preserves_shared_pair_ids_and_excludes_pilot():
    cases = records_to_cases(
        [
            {"id": f"T-{index}", "title": f"Case {index}", "steps": f"Verify action {index}"}
            for index in range(8)
        ]
    )
    batches = build_batches(cases, pilot_size=4, batch_size=5, seed=7)
    assert batches[0][0] == "pilot"
    assert len(batches[0][1]) == 4
    rest = [row for _, rows in batches[1:] for row in rows]
    all_rows = build_annotation_rows(cases)
    pilot_ids = {row["pair_id"] for row in batches[0][1]}
    remaining_ids = {row["pair_id"] for row in rest}
    assert pilot_ids.isdisjoint(remaining_ids)
    assert pilot_ids | remaining_ids == {row["pair_id"] for row in all_rows}
    assert all(len(rows) <= 5 for _, rows in batches[1:])


def test_read_annotation_files_concatenates_sequential_batches():
    with tempfile.TemporaryDirectory() as temp_dir:
        first = Path(temp_dir) / "first.csv"
        second = Path(temp_dir) / "second.csv"
        pd.DataFrame([{"pair_id": "P1", "decision": "duplicate"}]).to_csv(first, index=False)
        pd.DataFrame([{"pair_id": "P2", "decision": "different"}]).to_csv(second, index=False)
        combined = read_annotation_files([first, second])
    assert combined["pair_id"].tolist() == ["P1", "P2"]


def test_cohen_kappa_and_annotation_report():
    assert cohen_kappa(
        ["equivalent", "not_related"], ["equivalent", "not_related"]
    ) == 1
    assert cohen_kappa(["equivalent"], ["equivalent"]) is None
    assert cohen_kappa(
        ["equivalent", "equivalent", "not_related", "not_related"],
        ["equivalent", "not_related", "equivalent", "not_related"],
    ) == 0
    report = summarize_annotations(
        pd.DataFrame(
            [
                {
                    "annotator_1_decision": "equivalent",
                    "annotator_2_decision": "not_related",
                    "adjudicated_decision": "equivalent",
                },
                {
                    "annotator_1_decision": "not_related",
                    "annotator_2_decision": "not_related",
                    "adjudicated_decision": "not_related",
                },
                {
                    "annotator_1_decision": "",
                    "annotator_2_decision": "",
                    "adjudicated_decision": "",
                },
            ]
        )
    )
    assert report["double_annotated_pairs"] == 2
    assert report["incomplete_pairs"] == 1
    assert report["disagreements"] == 1
    assert report["unresolved_disagreements"] == 0


def test_agreement_report_accepts_five_class_grid_and_legacy_labels():
    report = summarize_annotations(
        pd.DataFrame(
            [
                {
                    "annotator_1_decision": "Duplicate",
                    "annotator_2_decision": "duplicate",
                    "adjudicated_decision": "duplicate",
                },
                {
                    "annotator_1_decision": "related_not_equivalent",
                    "annotator_2_decision": "related",
                    "adjudicated_decision": "related",
                },
                {
                    "annotator_1_decision": "uncertain",
                    "annotator_2_decision": "uncertain",
                    "adjudicated_decision": "uncertain",
                },
            ]
        )
    )
    assert report["double_annotated_pairs"] == 3
    assert report["raw_agreement"] == 1
    assert report["decision_counts_annotator_1"] == {
        "duplicate": 1,
        "related": 1,
        "uncertain": 1,
    }


def test_api_client_serializes_request_and_parses_response():
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"pairs": [], "clusters": []}'

    with patch("harmonizer.client.urlopen", return_value=FakeResponse()):
        result = analyze_via_api(
            "http://localhost:8000/",
            [{"id": "T1", "title": "Test"}],
            threshold=0.4,
            engine="tfidf",
        )
    assert result["pairs"] == []
