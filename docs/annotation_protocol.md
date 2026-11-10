# Protocole d’annotation des cas de test

## Objectif

Créer une référence humaine pour évaluer si deux cas de test vérifient le même comportement fonctionnel. La similarité de formulation, le même écran ou des étapes communes ne suffisent pas à établir l’équivalence.

## Grille de décision

Annoter chaque paire indépendamment, sans accès à la similarité du modèle ni à la réponse de l’autre annotateur :

- `duplicate` : même cas de test répété, à l’identique ou avec de simples variations de forme qui ne changent ni les données/conditions, ni les actions, ni l’oracle.
- `equivalent` : formulation ou chemin différent, mais même objectif fonctionnel, mêmes conditions déterminantes et même comportement attendu.
- `related` : cas reliés par la fonctionnalité, les étapes ou l’écran, mais qui couvrent un comportement, une condition, une donnée ou un risque différent.
- `different` : objectifs et comportement vérifié distincts.
- `uncertain` : informations manquantes ou ambiguës empêchant de décider. Donner une justification ; ne pas deviner.

Arbre de décision : si même cas avec différences purement rédactionnelles, `duplicate` ; si même objectif et oracle malgré une formulation ou un chemin différent, `equivalent` ; si seulement un lien de domaine ou de parcours, `related` ; sinon, `different`. Réserver `uncertain` aux preuves insuffisantes.

Enregistrer le champ `uncertain` comme une catégorie d’accord inter-annotateurs dans le κ de Cohen, mais l’exclure des métriques du détecteur. Pour les métriques binaires de redondance, `duplicate` et `equivalent` sont positifs ; `related` et `different` sont négatifs. Le détecteur courant ne distingue pas les deux types de redondance : rapporter également leur prévalence séparément et ne pas prétendre avoir évalué une classification à cinq classes.

Consigner une justification courte et les attributs fonctionnels déterminants. Ne pas déduire une information absente du cas.

## Procédure recommandée

1. Retirer les noms/identifiants sensibles et figer une version du référentiel.
2. Générer trois fichiers : deux feuilles distinctes pour préserver l’aveuglement et un modèle d’arbitrage. Limite de 200 cas par feuille :

   ```powershell
   python scripts/prepare_annotations.py --dataset data/cases_anonymized.csv --output data/annotations.csv --blind
   ```

   Cela génère `annotations_annotator_1.csv`, `annotations_annotator_2.csv` et `annotations_adjudication.csv`. Ne pas envoyer un fichier combiné aux deux testeurs. Pour des corpus plus larges, créer des lots documentés et garantir que le jeu d’évaluation contient toutes les paires positives nécessaires au calcul du rappel.
3. Fournir aux annotateurs le titre, les préconditions, les étapes et le résultat attendu, sans afficher le score du modèle ni la décision de l’autre annotateur.
4. Faire annoter chaque paire indépendamment avec une justification, puis calculer l’accord nominal à cinq classes avant arbitrage :

   ```powershell
   python scripts/merge_annotations.py `
     --annotator-1 data/annotations_annotator_1.csv `
     --annotator-2 data/annotations_annotator_2.csv `
     --adjudication data/annotations_adjudication.csv `
     --output data/annotations_merged.csv
   python scripts/annotation_report.py --annotations data/annotations_merged.csv
   ```

   Le rapport fournit l’accord brut et le κ de Cohen sur les cinq décisions ; les paires incomplètes ou invalides sont signalées.
5. Faire arbitrer les désaccords par un troisième testeur et remplir `adjudicated_decision` ainsi que sa justification. À la fusion, les décisions indépendantes identiques sont automatiquement reprises comme référence ; pour chaque désaccord, l’arbitre doit saisir le label final. Un désaccord sans arbitrage reste exclu des métriques.
6. Geler les annotations avant de mesurer les modèles ; décrire le nombre de cas et de paires par classe.

### Pilote et lots

Pour le corpus fourni, `scripts/split_annotation_batches.py` crée un pilote enrichi de 20 paires puis des lots de 100 sur le reste. Le pilote combine des paires très proches et des paires moins similaires pour exercer les différentes classes ; les prédictions/scores ne figurent pas dans les feuilles. Utiliser le pilote seulement pour clarifier la grille et vérifier le temps de travail, puis l’exclure des métriques finales. Les lots hors pilote partitionnent le reste sans doublons et sont communs aux deux annotateurs.

```powershell
python scripts/split_annotation_batches.py --dataset data/TestCases_for_ApiTesting.xlsx --output-dir data/annotation_batches --pilot-size 20 --batch-size 100
```

Compléter un même lot à la fois. Après les lots, fusionner tous les fichiers `batch_*` (pas `pilot_*`) avec `scripts/merge_annotations.py`; les arguments `--annotator-1`, `--annotator-2` et `--adjudication` acceptent plusieurs chemins. Le script refuse les identifiants de paires en double ou les feuilles dont les ensembles de paires diffèrent.

## Séparation des données et rapports

Séparer par famille fonctionnelle (et non par paire aléatoire) en jeux de calibration et de test afin d’éviter que des variantes d’une même famille ne fuient entre les deux. Choisir le seuil uniquement sur le jeu de calibration, puis le figer pour le test.

Rapporter précision, rappel, F1 pour la cible binaire `duplicate OR equivalent`, matrice de confusion, nombre de paires prédites et prévalence séparée des catégories `duplicate` et `equivalent`. Le script évalue les seules paires présentes et arbitrées ; le rappel ainsi calculé n’est interprétable comme rappel global que si le jeu de paires est exhaustif pour les positifs pertinents. Compléter les scores par des exemples de faux positifs/faux négatifs et un intervalle d’incertitude si la taille du jeu le permet. Présenter les résultats par moteur, modèle/version, seuil, date et données utilisées. Les paires `uncertain` doivent être exclues des métriques du détecteur et leur volume rapporté.

Ne pas considérer un petit jeu synthétique ou une similarité élevée comme une preuve de performance métier.
