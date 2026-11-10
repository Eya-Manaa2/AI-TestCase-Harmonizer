# AI Test Case Harmonizer

Application de démonstration locale pour analyser et harmoniser des référentiels de tests fonctionnels. Elle propose des paires et groupes similaires, standardise les étapes avec des keywords, estime la préparation à l’automatisation et exige une approbation humaine avant l’export.

## Démarrer

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

Optionnel, pour activer les embeddings sémantiques multilingues :

```powershell
python -m pip install -r requirements-embeddings.txt
```

Le modèle d’embeddings est chargé localement au premier usage. L’application fonctionne aussi sans cette option avec le baseline TF-IDF.

Pour la génération LLM facultative, installez Ollama, démarrez son service, puis téléchargez le modèle configuré dans l’interface (par défaut `mistral`) :

```powershell
ollama pull mistral
```

La génération n’est exécutée qu’au clic sur le bouton d’un cas de test. Utilisez seulement un serveur Ollama de confiance.

Avec Docker Desktop sous Windows, le serveur Ollama installé sur l’hôte est généralement accessible depuis l’interface via `http://host.docker.internal:11434` plutôt que `localhost`.

## Démarrer avec Docker

Docker Compose lance l’interface et l’API :

```powershell
docker compose up --build
```

- Interface : <http://localhost:8501>
- Documentation interactive de l’API : <http://localhost:8000/docs>
- Santé de l’API : <http://localhost:8000/health>

Les ports Docker sont limités à la machine locale. L’API n’implémente pas d’authentification ni de gestion d’identités : ne l’exposez pas sur un réseau de production. Le champ `approved` est une confirmation applicative, pas une signature vérifiable de l’identité de l’approbateur.

Pour inclure Sentence Transformers dans les deux conteneurs (image plus volumineuse et téléchargement initial du modèle requis) :

```powershell
$env:INSTALL_EMBEDDINGS = "true"
docker compose up --build
```

## API

Démarrer l’API seule :

```powershell
uvicorn harmonizer.api:app --reload
```

Routes principales :

- `POST /analyze` : cas, seuil et moteur (`tfidf` ou optionnel `sentence-transformers`) ; retourne les paires candidates, groupes, readiness et keywords.
- `POST /standardize` : propose un scénario par cas, toujours avec `approved: false`.
- `POST /export` : export JSON/CSV/XLSX uniquement si chaque cas porte `approved: true`.
- `GET /health` : vérification de disponibilité.

Exemple PowerShell :

```powershell
$body = @{
  threshold = 0.4
  cases = @(
    @{ id = "T-1"; title = "Login"; steps = "Open login page; click Login"; expected_result = "Dashboard displayed" }
  )
} | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri http://localhost:8000/analyze -Method Post -ContentType "application/json" -Body $body
```

Le jeu d’exemple est disponible dans `data/sample_test_cases.csv`. Formats d’entrée : CSV, JSON, TXT et Excel (`.xlsx`). Les colonnes sont reconnues par alias ; les plus utiles sont `id`, `title`, `preconditions`, `steps` et `expected_result`.

## Fonctionnalités

- Détection des doublons après normalisation et similarité TF-IDF pondérée (n-grammes de mots et de caractères), avec propositions de groupes à seuil réglable.
- Option Sentence Transformers pour calculer des embeddings sémantiques multilingues localement.
- Normalisation légère de synonymes de formulation ; l’algorithme reste lexical et ne prouve pas une équivalence fonctionnelle.
- Standardisation explicable des étapes en `NAVIGATE`, `INPUT`, `CLICK`, `ASSERT_TEXT` et `WAIT`.
- Catalogue agrégé de keywords et paramètres indicatifs.
- Score de préparation sur 100, fondé sur la clarté, les préconditions, le résultat attendu, la reconnaissance des actions et leur précision.
- Révision/édition humaine et export CSV, JSON ou Excel des cas approuvés.
- Option de standardisation Ollama locale, appelée uniquement à la demande ; sa sortie doit être relue et approuvée.

## Évaluation

Le jeu d’exemple synthétique contient des groupes annotés pour vérifier le pipeline. Balayez des seuils avec :

```powershell
python scripts/evaluate.py --thresholds 0.2,0.3,0.4,0.5,0.6
```

Pour créer deux feuilles aveugles séparées et un modèle d’arbitrage (maximum 200 cas par feuille) :

```powershell
python scripts/prepare_annotations.py --dataset data/real_cases.csv --output data/annotations.csv --blind
```

Pour le corpus fourni, un pilote de 20 paires et des lots aveugles de 100 sont disponibles sous `data/annotation_batches/`. Pour les recréer :

```powershell
python scripts/split_annotation_batches.py --dataset data/TestCases_for_ApiTesting.xlsx --output-dir data/annotation_batches --pilot-size 20 --batch-size 100
```

Le pilote est enrichi de paires à similarité élevée et basse pour mettre la grille à l’épreuve ; **ne pas inclure ses annotations dans l’évaluation finale**. Les lots `batch_001` à `batch_019` contiennent les autres 1 871 paires, sans recouvrement. Pour fusionner tous les lots hors pilote après les avoir récupérés, PowerShell accepte plusieurs fichiers par argument :

```powershell
$a1 = @(Get-ChildItem data/annotation_batches/batch_*_annotator_1.csv | Sort-Object Name | ForEach-Object FullName)
$a2 = @(Get-ChildItem data/annotation_batches/batch_*_annotator_2.csv | Sort-Object Name | ForEach-Object FullName)
$adj = @(Get-ChildItem data/annotation_batches/batch_*_adjudication.csv | Sort-Object Name | ForEach-Object FullName)
python scripts/merge_annotations.py --annotator-1 $a1 --annotator-2 $a2 --adjudication $adj --output data/annotations_merged.csv
```

Fusionner plutôt uniquement les fichiers du pilote lors de la répétition de la grille, et garder cette sortie séparée.

La grille d’annotation distingue `duplicate`, `equivalent`, `related`, `different` et `uncertain`. Consulte [le protocole détaillé](docs/annotation_protocol.md) avant l’annotation. `duplicate` et `equivalent` comptent comme positifs pour l’évaluation de redondance ; `related` et `different` comme négatifs. `uncertain` est inclus dans l’accord inter-annotateurs mais écarté des métriques du détecteur.

Après l’annotation indépendante, fusionner les fichiers : les accords sont automatiquement utilisés comme labels finaux et l’arbitre ne remplit que les désaccords. Calculer ensuite l’accord brut et κ de Cohen :

```powershell
python scripts/merge_annotations.py `
  --annotator-1 data/annotations_annotator_1.csv `
  --annotator-2 data/annotations_annotator_2.csv `
  --adjudication data/annotations_adjudication.csv `
  --output data/annotations_merged.csv
python scripts/annotation_report.py --annotations data/annotations_merged.csv
```

Le profil du corpus et ses répétitions de texte littéralement identiques peuvent être examinés sans prétendre à des labels d’équivalence :

```powershell
python scripts/profile_dataset.py --dataset data/TestCases_for_ApiTesting.xlsx
```

Cette analyse trouve 6 groupes de texte répété (26 paires dans la copie fournie), mais ces copies peuvent provenir des mêmes modèles de requêtes répétés et ne prouvent pas l’équivalence fonctionnelle.

Après avoir rempli `adjudicated_decision` pour chaque paire utilisable, évaluer :

```powershell
python scripts/evaluate.py --dataset data/real_cases.csv --pair-annotations data/annotations_merged.csv --thresholds 0.2,0.3,0.4,0.5
```

Décisions attendues : `duplicate`, `equivalent`, `related`, `different`, `uncertain`. `uncertain` et les annotations en attente sont exclues des métriques binaires et comptabilisées. La cible évaluée est « duplicate ou equivalent » ; le détecteur ne distingue pas encore ces deux classes. Le rappel ne représente la couverture globale que si toutes les paires positives pertinentes sont annotées. Les résultats incluent précision, rappel, F1 et les comptes de la matrice de confusion. Pour comparer les embeddings :

```powershell
python -m pip install -r requirements-embeddings.txt
python scripts/evaluate.py --dataset data/real_cases.csv --pair-annotations data/annotations_merged.csv --engine sentence-transformers
```

Le protocole de collecte, d’arbitrage, de calcul d’accord et de séparation des données est dans [docs/annotation_protocol.md](docs/annotation_protocol.md). Pour une évaluation scientifique, séparer les familles fonctionnelles en calibration et test ; choisir le seuil sur la calibration puis ne le modifier qu’après avoir rapporté les résultats du test.

Une recherche de sources publiques et leur pertinence/limites est documentée dans [docs/public_datasets.md](docs/public_datasets.md). Un petit classeur Excel public de 62 cas API est fourni comme point de départ d’annotation dans `data/TestCases_for_ApiTesting.xlsx` (licence et provenance fournies). Ses données n’ont pas de labels d’équivalence, la plupart des étapes détaillées sont absentes et elles ne constituent pas une référence scientifique à elles seules.

Une feuille combinée vide de 1 891 paires est déjà disponible dans `data/annotations_manual_api.csv` pour inspection. Pour conduire une annotation aveugle, générer plutôt les trois feuilles séparées :

```powershell
python scripts/prepare_annotations.py --dataset data/TestCases_for_ApiTesting.xlsx --output data/annotations_manual_api.csv --blind
```

Faire compléter les fichiers par des annotateurs séparés, fusionner leurs réponses et arbitrages, puis lancer le rapport et l’évaluation. Tant qu’aucune décision humaine n’est renseignée, les métriques restent non calculables. Conserver l’attribution/licence pour les feuilles dérivées, voir `data/ATTRIBUTION.md`.

Exécuter les tests :

```powershell
python -m pytest -q
```

Un workflow GitHub Actions exécute les tests et l’évaluation de démonstration à chaque push et pull request.

## Limites et prochaine étape

Par défaut, aucune requête LLM n’est faite. L’option Ollama transmet le cas au serveur configuré uniquement après action explicite ; utilisez uniquement un serveur de confiance pour des données d’entreprise. Les suggestions et groupes ne sont jamais des décisions de fusion automatiques. Les métriques du jeu synthétique (au seuil 0,40 : précision 0,57, rappel 0,80, F1 0,67) sont un test de fonctionnement, pas une preuve de performance générale.

Ce dépôt fournit le prototype logiciel, une API, des tests et un protocole de recherche. Il ne contient pas de données Sagemcom ni d’évaluation par des experts du domaine. La validation métier, les résultats scientifiques, l’intégration aux outils de l’entreprise et la qualité réelle des reformulations restent à établir avec des données autorisées et des annotateurs compétents.
