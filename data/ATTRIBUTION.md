# Données de démonstration et provenance

`TestCases_for_ApiTesting.xlsx` provient de [`mfaisalkhatri/Manual_Testing`](https://github.com/mfaisalkhatri/Manual_Testing), révision `6be4a387c0628ccd2fe5a922ddeada1b9232e815`, fichier `Templates/TestCases_for_ApiTesting.xlsx`.

- Licence fournie avec le classeur : Apache License 2.0, copie dans `MANUAL_TESTING_LICENSE.txt`.
- SHA-256 du classeur : `8c964feefa03d9eb8411300ec71019f755c406ef049336ad859cac6031f0e973`.
- `annotations_manual_api.csv` est la feuille de comparaison exhaustive préparée à partir des 62 cas importables (1 891 paires). Les champs des deux annotateurs et l’arbitrage sont vides ; aucune vérité terrain n’est préremplie.
- `annotations_manual_api_annotator_1.csv`, `annotations_manual_api_annotator_2.csv` et `annotations_manual_api_adjudication.csv` sont les feuilles aveugles séparées pour annoter et arbitrer indépendamment. Les feuilles d’annotation contiennent les mêmes paires, mais pas les décisions de l’autre annotateur.
- `annotation_batches/` contient un pilote de 20 paires et 19 lots aveugles (maximum 100 paires chacun) couvrant les 1 871 paires restantes. Les mêmes identifiants de paires sont partagés entre les rôles ; le pilote doit être exclu de l’évaluation finale.
- Le CSV reprend le contenu du corpus source et doit conserver cette attribution/licence. Toute annotation ajoutée par les testeurs doit être identifiée comme telle et datée dans le rapport de recherche.

Ce corpus est un exemple générique de tests API. Il ne contient pas d’annotations d’équivalence, n’est pas représentatif de Sagemcom et ne doit pas servir à prétendre une validation métier avant son annotation indépendante.
