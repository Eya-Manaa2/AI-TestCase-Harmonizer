# Sources publiques examinées

Recherche effectuée le 10 novembre 2026. Vérifier les licences et les révisions des sources avant toute réutilisation ou diffusion ; ce relevé ne constitue pas un avis juridique.

| Source | Contenu observé | Apport pour le projet | Limite pour l’évaluation | Licence / décision |
|---|---|---|---|---|
| [mfaisalkhatri/Manual_Testing](https://github.com/mfaisalkhatri/Manual_Testing) | Modèles Excel de tests manuels, dont `Templates/TestCases_for_ApiTesting.xlsx` (environ 49 ko au commit observé). Contient des colonnes Case No., Test Cases, Test Steps, Test Data, Expected Output et des lignes d’en-tête/sections. | Source pratique pour tester l’import Excel et constituer une première feuille d’annotation sur des cas fonctionnels. Une copie de ce classeur est fournie dans `data/`, avec sa licence et son attribution. | Pas de paires d’équivalence ni de labels de doublons. Les 62 cas extraits sont génériques ; la plupart n’ont pas de champ Test Steps renseigné et des exemples contiennent des placeholders. Ce n’est ni un jeu gold ni un dataset représentatif de Sagemcom. | Le dépôt déclare Apache-2.0. La provenance et la révision sont documentées ci-dessous. |
| [microsoft/methods2test](https://github.com/microsoft/methods2test) | Corpus de 780 944 méthodes de tests unitaires Java associées à des focal methods, réparties par dépôts ; données sous Git LFS. | Recherche complémentaire sur la structure du code de test ou la génération unitaire. | Tests unitaires source-code, pas scénarios fonctionnels en langage naturel ; les doublons exacts ont été retirés. Les dépôts source ont leurs propres droits et notices. Non retenu pour entraîner/évaluer la déduplication fonctionnelle de ce MVP. | Le dépôt annonce MIT, mais appliquer les notices/licences des dépôts sources et consulter `NOTICE`. Ne pas importer aveuglément. |
| [OS3Lab/crash_deduplication](https://github.com/OS3Lab/crash_deduplication) | Ground truth associée à des rapports de bugs/crash du noyau Linux, référencée par l’article NDSS « An In-depth Analysis of Duplicated Linux Kernel Bug Reports ». | Piste pour une expérience de transfert sur la déduplication de rapports de bugs. | Les unités sont des rapports de bugs/crash, pas des cas de test. L’équivalence de bugs ne prouve pas l’équivalence de comportements de tests ; aucune évaluation principale ne doit mélanger ces tâches. | Dépôt sous BSD-2-Clause. Utiliser uniquement comme benchmark séparé et conserver la licence/attribution. |
| `Lewis66/software-testing-dataset` sur Hugging Face | Le viewer consulté indiquait une seule ligne de sentiment sur avis de film. | Aucun pour ce besoin. | Malgré le nom, ce n’est pas un dataset de cas de test logiciel. | Écarté. |

## Utiliser le corpus manuel comme point de départ

L’importeur Excel prend en charge les feuilles avec un en-tête `Case No.`, `Test Cases`, `Test Steps`, `Expected Output` et ignore les lignes de section marquées `Header`. Pour préparer la feuille d’annotation à partir de la copie fournie :

```powershell
python scripts/prepare_annotations.py --dataset data/TestCases_for_ApiTesting.xlsx --output data/annotations_manual_api.csv
```

Le classeur de départ fournit des exemples de scénarios, pas leurs équivalences. Deux testeurs doivent annoter chaque paire indépendamment selon la grille `duplicate`, `equivalent`, `related`, `different`, `uncertain` ; arbitrer les désaccords avant d’utiliser `scripts/evaluate.py`. Signaler dans le mémoire que le corpus est générique et externe. Il ne remplace pas un échantillon de test métier réellement représentatif.

Copie retenue : `mfaisalkhatri/Manual_Testing`, révision `6be4a387c0628ccd2fe5a922ddeada1b9232e815`, fichier `Templates/TestCases_for_ApiTesting.xlsx`. Licence Apache-2.0 disponible dans `data/MANUAL_TESTING_LICENSE.txt`. Une feuille exhaustive non annotée de 1 891 paires est préparée dans `data/annotations_manual_api.csv`. Le classeur source contient aussi un onglet de métadonnées et un sommaire de cycle de test ; l’application importe uniquement la feuille de cas. Voir `data/ATTRIBUTION.md` pour le checksum et la provenance.

Pour le projet Sagemcom, le jeu final devrait venir de tests autorisés par l’entreprise, anonymisés selon ses règles de confidentialité et annotés par des personnes connaissant le produit. Ne pas téléverser de données internes vers des dépôts ou services externes non approuvés.
