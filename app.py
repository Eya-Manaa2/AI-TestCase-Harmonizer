from __future__ import annotations

import json
from io import BytesIO
from importlib.util import find_spec
import os
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from harmonizer.analyzer import analyze_cases
from harmonizer.client import HarmonizerAPIError, analyze_via_api
from harmonizer.io import load_cases
from harmonizer.ollama import standardize_with_ollama
from harmonizer.readiness import assess_readiness
from harmonizer.standardizer import discover_keywords, standardize_case


st.set_page_config(page_title="AI Test Case Harmonizer", page_icon="🧪", layout="wide")


@st.cache_resource(show_spinner="Chargement du modèle d’embeddings local…")
def load_embedding_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


st.title("AI Test Case Harmonizer")
st.caption(
    "Analysez les redondances, harmonisez les scénarios et évaluez leur préparation "
    "à l’automatisation. Les suggestions restent à valider par un humain."
)

with st.sidebar:
    st.header("Référentiel")
    uploaded = st.file_uploader(
        "Importer un fichier",
        type=["csv", "xlsx", "json", "txt"],
        help="Colonnes conseillées : id, title, preconditions, steps, expected_result.",
    )
    threshold = st.slider("Seuil de similarité", 0.20, 0.95, 0.40, 0.05)
    embedding_available = find_spec("sentence_transformers") is not None
    engine_options = ["TF-IDF"]
    if embedding_available:
        engine_options.append("Sentence Transformers")
    analysis_engine = st.selectbox("Moteur de similarité", engine_options)
    embedding_name = ""
    if analysis_engine == "Sentence Transformers":
        embedding_name = st.text_input(
            "Modèle local",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
    elif not embedding_available:
        st.caption("Option embeddings : installez requirements-embeddings.txt.")
    standardization_engine = st.selectbox(
        "Standardisation", ["Règles locales", "Ollama (local)"]
    )
    ollama_url = "http://localhost:11434"
    ollama_model = "mistral"
    if standardization_engine == "Ollama (local)":
        ollama_url = st.text_input("URL du serveur Ollama", ollama_url)
        ollama_model = st.text_input("Modèle Ollama", ollama_model)
    if analysis_engine == "TF-IDF":
        st.caption(
            "La similarité TF-IDF (mots et caractères) est une aide à la revue, "
            "pas une preuve d’équivalence fonctionnelle."
        )
    else:
        st.caption(
            "Les embeddings apportent une similarité sémantique, mais ne prouvent pas "
            "l’équivalence fonctionnelle."
        )

if uploaded is None and "cases" not in st.session_state:
    st.info("Chargez un référentiel ou essayez le jeu de démonstration.")
    demo_col, public_col = st.columns(2)
    if demo_col.button("Charger le jeu synthétique", type="primary"):
        sample_path = Path(__file__).parent / "data" / "sample_test_cases.csv"
        st.session_state["cases"] = load_cases(sample_path.read_bytes(), sample_path.name)
        st.rerun()
    if public_col.button("Charger les cas API publics"):
        public_path = Path(__file__).parent / "data" / "TestCases_for_ApiTesting.xlsx"
        st.session_state["cases"] = load_cases(public_path.read_bytes(), public_path.name)
        st.rerun()
    st.stop()

if uploaded is not None:
    try:
        cases = load_cases(uploaded.getvalue(), uploaded.name)
        st.session_state["cases"] = cases
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        st.error(f"Impossible de lire ce référentiel : {exc}")
        st.stop()
else:
    cases = st.session_state["cases"]

if not cases:
    st.warning("Le fichier ne contient aucun cas de test exploitable.")
    st.stop()

api_url = os.environ.get("HARMONIZER_API_URL", "").strip()
embedding_model = None
if analysis_engine == "Sentence Transformers" and not api_url:
    try:
        embedding_model = load_embedding_model(embedding_name)
    except (ImportError, OSError) as exc:
        st.error(f"Impossible de charger le modèle d’embeddings : {exc}")
        st.stop()
standardizations: dict[str, dict[str, Any]] = {}
if api_url:
    try:
        api_result = analyze_via_api(
            api_url,
            cases,
            threshold=threshold,
            engine=(
                "sentence-transformers"
                if analysis_engine == "Sentence Transformers"
                else "tfidf"
            ),
            embedding_model=embedding_name,
        )
    except HarmonizerAPIError as exc:
        st.error(f"Échec de l’analyse via l’API configurée : {exc}")
        st.stop()
    case_indices = {case["id"]: index for index, case in enumerate(cases)}
    try:
        analysis = {
            "pairs": [
                {
                    "left": case_indices[pair["left_id"]],
                    "right": case_indices[pair["right_id"]],
                    "score": pair["similarity"],
                    "exact": pair["exact_duplicate"],
                }
                for pair in api_result["pairs"]
            ],
            "clusters": [
                [case_indices[case_id] for case_id in group]
                for group in api_result["clusters"]
            ],
        }
        readiness = api_result["readiness"]
        keywords = api_result["keywords"]
        standardizations = {
            item["id"]: {
                "standardized_steps": item["standardized_steps"],
                "unrecognized_steps": item["unrecognized_steps"],
                "missing_expected_result": item["missing_expected_result"],
            }
            for item in api_result["standardizations"]
        }
    except (KeyError, TypeError) as exc:
        st.error(f"Réponse API incomplète ou incohérente : {exc}")
        st.stop()
else:
    analysis = analyze_cases(cases, threshold, embedding_model=embedding_model)
    readiness = [assess_readiness(case) for case in cases]
    keywords = discover_keywords(cases)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Cas analysés", len(cases))
col2.metric("Paires candidates", len(analysis["pairs"]))
col3.metric("Groupes redondants", sum(len(group) > 1 for group in analysis["clusters"]))
col4.metric("Score moyen de préparation", f"{sum(x['score'] for x in readiness) / len(readiness):.0f}%")

tabs = st.tabs(["Vue d’ensemble", "Similarités", "Harmonisation", "Keywords", "Export"])

with tabs[0]:
    st.subheader("Préparation à l’automatisation")
    readiness_frame = pd.DataFrame(
        [
            {
                "ID": case["id"],
                "Cas de test": case["title"],
                "Score": result["score"],
                "Niveau": result["level"],
                "Recommandations": "; ".join(result["recommendations"]),
            }
            for case, result in zip(cases, readiness)
        ]
    )
    st.dataframe(
        readiness_frame,
        width="stretch",
        hide_index=True,
        column_config={"Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d%%")},
    )
    st.subheader("Référentiel chargé")
    st.dataframe(
        pd.DataFrame(
            [{key: value for key, value in case.items() if key != "raw"} for case in cases]
        ),
        width="stretch",
        hide_index=True,
    )

with tabs[1]:
    st.subheader("Paires à examiner")
    st.caption(
        "Les paires sont classées par score de similarité. Confirmez ou rejetez leur équivalence "
        "avant toute fusion de cas."
    )
    if not analysis["pairs"]:
        st.success("Aucune paire ne dépasse le seuil choisi.")
    else:
        for pair in analysis["pairs"]:
            left = cases[pair["left"]]
            right = cases[pair["right"]]
            duplicate_label = " — doublon normalisé" if pair["exact"] else ""
            with st.expander(
                f'{left["id"]} ↔ {right["id"]} — similarité {pair["score"]:.0%}{duplicate_label}'
            ):
                st.markdown(f'**{left["title"]}**  \n{left["steps"]}')
                st.markdown("---")
                st.markdown(f'**{right["title"]}**  \n{right["steps"]}')
                st.checkbox(
                    "Équivalence fonctionnelle confirmée par un humain",
                    key=f'equivalent-{left["id"]}-{right["id"]}',
                )
    st.subheader("Groupes proposés")
    non_singleton = [group for group in analysis["clusters"] if len(group) > 1]
    if non_singleton:
        for group in non_singleton:
            st.write(", ".join(cases[index]["id"] for index in group))
    else:
        st.write("Aucun groupe au seuil choisi.")

with tabs[2]:
    st.subheader("Propositions de standardisation")
    st.caption(
        "La proposition structure les actions détectables sans inventer les résultats attendus. "
        "Relisez et modifiez le scénario avant de l’approuver."
    )
    approved: list[dict[str, Any]] = []
    for case in cases:
        proposal = standardizations.get(case["id"])
        if proposal is None:
            proposal = standardize_case(case)
        with st.expander(f'{case["id"]} — {case["title"]}'):
            step_widget_key = f'steps-{case["id"]}'
            notes_key = f'llm-notes-{case["id"]}'
            if step_widget_key not in st.session_state:
                st.session_state[step_widget_key] = proposal["standardized_steps"]
            if standardization_engine == "Ollama (local)":
                if st.button(
                    "Générer une proposition avec Ollama",
                    key=f'generate-{case["id"]}',
                ):
                    try:
                        generated = standardize_with_ollama(
                            case, base_url=ollama_url, model=ollama_model
                        )
                        st.session_state[step_widget_key] = "\n".join(
                            f"{index}. {step}" for index, step in enumerate(generated["steps"], 1)
                        )
                        st.session_state[notes_key] = generated["notes"]
                    except (RuntimeError, ValueError) as exc:
                        st.error(f"Échec de la génération Ollama : {exc}")
            if st.session_state.get(notes_key):
                st.info("Notes du modèle : " + " ; ".join(st.session_state[notes_key]))
            st.write("**Préconditions**")
            st.text_area(
                "Préconditions normalisées",
                case["preconditions"],
                key=f'pre-{case["id"]}',
            )
            edited = st.text_area(
                "Scénario standardisé proposé",
                key=step_widget_key,
                height=150,
            )
            expected = st.text_area(
                "Résultat attendu",
                case["expected_result"],
                key=f'expected-{case["id"]}',
            )
            is_approved = st.checkbox("Approuver cette proposition", key=f'approve-{case["id"]}')
            if is_approved:
                approved.append(
                    {
                        "id": case["id"],
                        "title": case["title"],
                        "preconditions": st.session_state[f'pre-{case["id"]}'],
                        "steps": edited,
                        "expected_result": expected,
                        "approved": True,
                        "automation_score": assess_readiness(case)["score"],
                    }
                )
    st.metric("Propositions approuvées", len(approved))
    st.session_state["approved_cases"] = approved

with tabs[3]:
    st.subheader("Catalogue de keywords")
    if keywords:
        st.dataframe(pd.DataFrame(keywords), width="stretch", hide_index=True)
    else:
        st.info("Aucune action reconnue. Essayez des étapes telles que « Click login button » ou « Enter username ».")

with tabs[4]:
    st.subheader("Exporter")
    export_records = st.session_state.get("approved_cases", [])
    if not export_records:
        st.info("Approuvez au moins une proposition dans l’onglet Harmonisation pour exporter les cas standardisés.")
    else:
        approved_frame = pd.DataFrame(export_records)
        st.download_button(
            "Télécharger les cas approuvés (JSON)",
            data=json.dumps(export_records, ensure_ascii=False, indent=2),
            file_name="standardized_test_cases.json",
            mime="application/json",
        )
        st.download_button(
            "Télécharger les cas approuvés (CSV)",
            data=approved_frame.to_csv(index=False).encode("utf-8-sig"),
            file_name="standardized_test_cases.csv",
            mime="text/csv",
        )
        excel_buffer = BytesIO()
        approved_frame.to_excel(excel_buffer, index=False)
        st.download_button(
            "Télécharger les cas approuvés (Excel)",
            data=excel_buffer.getvalue(),
            file_name="standardized_test_cases.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    original_json = json.dumps(
        [{key: value for key, value in case.items() if key != "raw"} for case in cases],
        ensure_ascii=False,
        indent=2,
    )
    st.download_button(
        "Télécharger le référentiel analysé (JSON)",
        data=original_json,
        file_name="analyzed_test_cases.json",
        mime="application/json",
    )
