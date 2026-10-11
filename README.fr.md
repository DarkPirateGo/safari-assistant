# Safari Assistant

<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/logo/safari-assistant-wordmark-dark.svg"><img src="docs/img/logo/safari-assistant-wordmark-light.svg" alt="Safari Assistant" width="420"></picture></p>

*Ce guide en : [English](README.md) · [Deutsch](README.de.md) · **Français** · [Español](README.es.md)*

**Un assistant IA de terrain, hors ligne, pour les voyages en overland en Afrique australe et orientale : des modules de chat sur des modèles locaux sur votre Mac, une carte hors ligne avec les saisons des pluies et les avertissements officiels aux voyageurs, une fiche d'urgence qui fonctionne sans IA, et une vue pour téléphone via votre propre Wi-Fi.**

Pour les Mac avec puce Apple Silicon. En anglais, allemand, français et espagnol. Gratuit pour un usage non commercial.

[![CI](https://github.com/DarkPirateGo/safari-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/DarkPirateGo/safari-assistant/actions/workflows/ci.yml)
[![Licence : PolyForm Noncommercial](https://img.shields.io/badge/License-PolyForm%20Noncommercial-blue.svg)](LICENSE)

> [!IMPORTANT]
> - **Uniquement pour les Mac Apple Silicon.**
> - **Quel Mac il vous faut :** voir [Quel modèle sur quel Mac](#quel-modèle-sur-quel-mac).
> - **État :** utilisé par l'auteur pour préparer son voyage. Pas encore éprouvé sur le terrain. Testé sur une seule machine (Apple Silicon, 36 Go).

<p align="center">
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/en/chat-dark.png"><img src="docs/img/en/chat-light.png" width="250" alt="Un chat avec l'un des modules de Safari Assistant"></picture>
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/en/map-dark.png"><img src="docs/img/en/map-light.png" width="250" alt="La carte hors ligne de Safari Assistant"></picture>
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/en/emergency-dark.png"><img src="docs/img/en/emergency-light.png" width="250" alt="La vue d'urgence de Safari Assistant"></picture>
</p>
<p align="center"><sub>Vue d'exemple avec des données de démonstration ·
<a href="https://darkpiratego.github.io/safari-assistant/">Site web</a></sub></p>

---

## Ce que fait Safari Assistant

### 14 modules de chat

Chaque module a son propre prompt système, son propre historique de chat et son propre modèle. 12 tournent sur des modèles locaux via [Ollama](https://ollama.com). 2 sont des modules en ligne optionnels qui nécessitent votre propre clé API Anthropic.

| Module (libellé dans l'interface) | Couvre | Modèle par défaut |
|---|---|---|
| 🔧 Mécanique | Diagnostic du véhicule et réparation sur le terrain, adapté au Toyota HZJ78 / diesel 1HZ | `qwen3.6:35b-a3b` |
| 🐘 Nature & faune | Faune et plantes, identification des espèces, évaluation du danger | `qwen3.6:35b-a3b` |
| 🏥 Médecine & premiers secours | Médecine tropicale et médecine en milieu isolé, premiers secours | `qwen3.6:35b-a3b` |
| 🗺️ Navigation & terrain | Itinéraires, terrain, passages à gué, postes-frontières | `qwen3.6:35b-a3b` |
| 🐕 Chien | Santé et sécurité du chien en route | `qwen3.6:35b-a3b` |
| 🌿 Survie & orientation | Eau, abri, orientation, signalisation | `qwen3.6:35b-a3b` |
| 📸 Photographie animalière | Photographie animalière | `qwen3.6:35b-a3b` |
| 🗣️ Langues | Expressions et traduction pour la région | `qwen3.6:35b-a3b` |
| 🚨 Chat d'urgence | Chat d'urgence, instructions calmes étape par étape | `qwen3.6:35b-a3b` |
| 🌦️ Météo & saisons des pluies | Saisons et périodes de pluie. Sur le Mac, il passe en ligne via Claude quand une clé API est enregistrée | `gemma4:e4b` |
| 🍳 Cuisine de camp | Cuisiner avec ce qu'il y a dans le véhicule | `gemma4:e4b` |
| 💪 Fitness | Entraînement sans matériel | `gemma4:e4b` |
| 🌍 Situation sécuritaire — en direct | Situation sécuritaire actuelle, avec recherche web (en ligne) | Claude, au choix |
| ✦ Claude — IA en ligne | Assistant en ligne généraliste avec recherche web (en ligne) | Claude, au choix |

- Un seul réglage fait passer tous les modules locaux à un autre modèle : ⚙️ Réglages → **Modèle global**.
- Le modèle en ligne se choisit dans ⚙️ Réglages → Claude API → **Charger la liste**, qui demande à Anthropic quels modèles votre clé peut utiliser.
- **Vos propres manuels :** importez des PDF, par exemple un manuel d'atelier, un livre de premiers secours ou un guide de voyage, et attribuez-les à un module (PyMuPDF requis, voir [Démarrage rapide](#démarrage-rapide)). Le module y fait ses recherches hors ligne et cite le document, le chapitre et la page.
- **Photos :** joignez une photo d'un panneau, d'une pièce, d'une plante ou d'un animal et posez votre question. Avec les modules locaux, le modèle l'examine sur votre Mac ; rien n'est envoyé.
- Les modules peuvent aussi faire des recherches dans une Wikipédia hors ligne, en option, et la citer.

### Carte hors ligne

- Carte vectorielle à partir de votre propre `karte.mbtiles` (construite une seule fois, voir [docs/SETUP.md](docs/SETUP.md#6-offline-map)), ou tuiles OpenStreetMap en ligne.
- 🌧️ **Pluie** : couche des saisons des pluies avec une frise jour par jour. Touchez une cellule pour voir, pour le mois choisi, les pluies mensuelles, les températures, l'humidité, le vent, le rayonnement solaire et la saison du paludisme. Elle montre des moyennes à long terme, pas une prévision.
- Panneau météo ℹ️ pour votre position ; en ligne et sur demande, une prévision à 7 jours d'Open-Meteo.
- 🛑 **Avertissements** : avertissements officiels aux voyageurs de l'Allemagne, du Royaume-Uni et des États-Unis, récupérés automatiquement dès que le Mac est en ligne et lisibles hors ligne. Les districts concernés sont dessinés sous forme de zones, et Safari Assistant vous indique si votre position se trouve dans l'une d'elles.
- 🦟 **Dangers** : zones de danger (paludisme, tsé-tsé, gros gibier, crocodiles), ainsi que les limites des parcs nationaux.
- **Environ 90 000 lieux** issus d'OpenStreetMap sont fournis avec l'app, un fichier par pays dans `POIs/`, à importer une fois sur la carte : campings, carburant, eau, ateliers, hôpitaux, vétérinaires et postes-frontières. Vos propres fichiers GPX, KML et GeoJSON peuvent aussi être importés.
- Recherche de lieux hors ligne ; recherche de rues en ligne uniquement quand vous appuyez sur Entrée.

### Fiche d'urgence (fonctionne sans IA)

- Numéros d'urgence par pays (cliquables) et numéros des ambassades d'Allemagne.
- Votre position en degrés décimaux, en degrés/minutes/secondes et en Plus Code, pour la radio ou un messager satellite.
- 8 protocoles de premiers secours sous forme de texte fixe (**Protocoles immédiats**), lisibles d'un seul toucher.
- Champs personnels (médical, documents, véhicule, contacts), taux de change, heures de lever et de coucher du soleil, échéances des documents.

### Outils de voyage

Listes de contrôle, échéances des documents, un plan d'entretien (modèle pour le Toyota HZJ78 / 1HZ, plus vos propres éléments), un journal de bord pour le carburant et l'entretien, des notes, des réponses enregistrées, l'historique des chats et des sauvegardes.

### Vue téléphone via votre propre Wi-Fi

`mobile.html` fonctionne sur un iPhone connecté au même Wi-Fi : les mêmes modules, un volet d'urgence 🚨 et la carte, le tout via le Mac, en HTTPS, avec un code d'accès. Voir [Mode iPhone](#mode-iphone).

### En option

- **Wikipédia hors ligne** via `kiwix-serve` (📚), aussi sur le téléphone.
- **Modules en ligne** avec votre propre clé API Anthropic.

Périmètre : 16 pays — Angola, Botswana, Burundi, Eswatini, Éthiopie, Kenya, Lesotho, Malawi, Mozambique, Namibie, Rwanda, Afrique du Sud, Tanzanie, Ouganda, Zambie, Zimbabwe.

---

## Prérequis

| | |
|---|---|
| **Mac** | Apple Silicon, macOS |
| **Mémoire** | Détermine le modèle que vous pouvez utiliser : voir [Quel modèle sur quel Mac](#quel-modèle-sur-quel-mac). Le modèle par défaut `qwen3.6:35b-a3b` a été mesuré sur un Mac de 36 Go (environ 22 Go utilisés). 32 Go ne suffisent probablement pas pour le faire tourner à pleine vitesse sur le GPU (estimation) |
| **Ollama** | 0.34 ou plus récent (testé avec 0.34.2), depuis [ollama.com](https://ollama.com) ou `brew install ollama` |
| **Python** | 3.9 ou plus récent. Lancée depuis le Finder, l'app tourne avec `/usr/bin/python3` |
| **Node.js** | uniquement pour la suite de tests |
| **Java 21+** | uniquement pour construire la carte hors ligne |
| **En option** | PyMuPDF (documents PDF), kiwix-tools (Wikipédia hors ligne), une clé API Anthropic (modules en ligne) |

| Téléchargement | Taille | Remarques |
|---|---|---|
| Modèles | 6,6–33,5 Go, selon votre Mac | Modèles par défaut (`qwen3.6:35b-a3b` et `gemma4:e4b`) : 29,6–33,5 Go, environ 1,5 heure à 50 Mbit/s |
| Carte hors ligne (`setup-offline-karte.sh`) | environ 8 Go au final, environ 80 Go d'espace libre pendant la construction | dure plusieurs heures |
| Wikipédia hors ligne (fichiers ZIM) | 2–55 Go, selon l'archive | en option |

Faites les gros téléchargements à la maison, avec une connexion rapide, bien avant le départ. L'index des lieux, les limites des parcs, les données climatiques et les POI sont fournis dans ce dépôt.

`server.py` est du Python ordinaire et peut tourner ailleurs, mais seul macOS sur Apple Silicon est testé, et les scripts du paquet d'application ne fonctionnent que sous macOS.

---

## Quel modèle sur quel Mac

Toute l'IA hors ligne tourne sur le Mac. L'iPhone ne fait qu'envoyer ses questions au Mac ; c'est donc la mémoire unifiée du Mac qui détermine les modèles que vous pouvez utiliser.

Vérifié le 4 octobre 2026. Les tailles de téléchargement proviennent de la bibliothèque Ollama. Ce sont des fourchettes, car Ollama n'indique pas si un Mac reçoit la version mlx ou la version llamacpp ; prévoyez avec le chiffre le plus élevé. Les valeurs **mesurées** proviennent d'un seul Mac : MacBook Pro M5 Max, 36 Go, Ollama 0.34.2, contexte de 16 384 tokens. Tout le reste est une **estimation** et n'a pas été testé avec Safari Assistant.

| Mémoire | Modèle de chat et de photo | Téléchargement total (avec `gemma4:e4b`) | Remarques |
|---|---|---|---|
| 8 Go | `gemma4:e4b` (profil léger) | 6,6–9,5 Go | Estimation. Très juste, peut être lent. Déconseillé pour le voyage |
| 16 Go | `gemma4:e4b` (profil léger) | 6,6–9,5 Go | Estimation. Un seul petit modèle pour tout : réponses moins détaillées (pas de benchmark) |
| 24 Go | `gemma4:12b` | 14,6–17,2 Go | Estimation, amélioration non testée. L'app elle-même propose ici le profil léger |
| 32 Go | `gemma4:26b` | environ 25,5 Go | Estimation, non testé. Le modèle par défaut ne tient probablement pas entièrement sur le GPU |
| 36–48 Go | `qwen3.6:35b-a3b` (par défaut) | 29,6–33,5 Go | **Mesuré sur 36 Go :** 22 Go utilisés, 100 % GPU, environ 92–98 tokens/s. 48 Go : estimation |
| 64 Go ou plus | `qwen3.6:35b-a3b` (par défaut) | 29,6–33,5 Go | Estimation : de la place pour les deux modèles. En option : `qwen3.6:35b-a3b-q8_0` (39 Go) pour plus de précision |

Chaque Mac a besoin de `gemma4:e4b` : le bouton ⚡ **Rapide**, les résumés de chat hors ligne et les termes de recherche Wikipédia l'utilisent toujours. Utilisez les noms de tag exacts : `gemma4:e4b`, et non une variante comme `gemma4:e4b-it-qat`.

Téléchargez les modèles une seule fois, avec Internet, dans le Terminal :

```bash
# 8 Go et 16 Go
ollama pull gemma4:e4b

# 24 Go
ollama pull gemma4:12b
ollama pull gemma4:e4b

# 32 Go
ollama pull gemma4:26b
ollama pull gemma4:e4b

# 36 Go ou plus (valeurs par défaut de l'app, aucun réglage nécessaire)
ollama pull qwen3.6:35b-a3b
ollama pull gemma4:e4b
```

Réglez ensuite le modèle dans Safari Assistant :

- **8 Go et 16 Go (profil léger) :** cliquez sur **Profil léger** dans le bandeau de démarrage, ou réglez ⚙️ Réglages → **Modèle global** sur `gemma4:e4b`.
- **24 Go et 32 Go :** réglez ⚙️ Réglages → **Modèle global** sur `gemma4:12b` ou `gemma4:26b`.
- **iPhone :** le téléphone a son propre réglage de modèle, qui n'est pas synchronisé avec le Mac. Réglez le même modèle dans ⚙️ Configuration → **Modèle Ollama**.
- **8 Go, si `gemma4:e4b` est trop lent :** téléchargez `gemma4:e2b` (4,6–7,5 Go) et définissez-le comme modèle global sur le Mac et sur l'iPhone. Le bouton ⚡, les résumés hors ligne et les termes de recherche Wikipédia utilisent toujours `gemma4:e4b`.

> [!TIP]
> Après une question dans Safari Assistant, lancez `ollama ps`. La colonne PROCESSOR doit afficher `100% GPU`. Toute autre valeur, comme `48%/52% CPU/GPU`, signifie que le modèle ne tient pas sur le GPU, et les réponses deviennent beaucoup plus lentes. Choisissez alors un modèle plus petit.

Bon à savoir :

- macOS ne laisse le GPU utiliser qu'une partie de la mémoire : environ 2/3 sur les petits Mac et environ 3/4 sur les plus gros. Ce sont des mesures de la communauté ; Apple ne publie aucune formule. C'est pourquoi 32 Go sont probablement trop peu pour le modèle par défaut (estimation).
- Avec le profil léger, les modules Médecine & premiers secours et Chat d'urgence répondent eux aussi avec le petit modèle. Les réponses sont plus courtes et moins fiables. Vérifiez tout ce qui compte.
- Non mesuré : si les deux modèles restent chargés ensemble sur 36 Go (sinon, le rechargement de `qwen3.6:35b-a3b` a pris environ 5–6 s), la vitesse sur d'autres puces, et la qualité des réponses et de l'analyse des photos de `gemma4:12b` et `gemma4:26b`. Les requêtes de l'iPhone peuvent utiliser un contexte plus long (jusqu'à 32 768 tokens), qui demande plus de mémoire que ce qui a été mesuré.

Sources : bibliothèque Ollama ([Qwen3.6](https://ollama.com/library/qwen3.6/tags), [Gemma 4](https://ollama.com/library/gemma4/tags)), [FAQ Ollama](https://docs.ollama.com/faq), [Apple : recommendedMaxWorkingSetSize](https://developer.apple.com/documentation/metal/mtldevice/recommendedmaxworkingsetsize).

---

## Démarrage rapide

**1. Installez Ollama** (0.34 ou plus récent) et vérifiez qu'il tourne. Téléchargez ensuite les modèles. Pour un Mac de 36 Go ou plus :

```bash
ollama pull qwen3.6:35b-a3b     # modèle par défaut, pour les Mac de 36 Go ou plus
ollama pull gemma4:e4b          # petit modèle : ⚡ Rapide, résumés, modules légers, termes de recherche Wikipédia
```

Moins de mémoire : téléchargez les modèles adaptés à votre Mac, indiqués dans [Quel modèle sur quel Mac](#quel-modèle-sur-quel-mac). Aucune variable d'environnement n'est nécessaire.

**2. Récupérez Safari Assistant et construisez l'app :**

```bash
git clone https://github.com/DarkPirateGo/safari-assistant.git && cd safari-assistant
./deploy.sh        # vérifie les bibliothèques de carte dans vendor/, lance les tests si Node est installé
./build-app.sh     # crée ~/Desktop/Safari Assistant.app
```

**3. Lancez** Safari Assistant en double-cliquant sur `Safari Assistant.app`. Le lanceur démarre Ollama s'il ne tourne pas déjà, démarre le serveur et ouvre `http://localhost:8765` dans votre navigateur. Si le serveur ne démarre pas, une alerte « Safari Assistant startet nicht » (en allemand) apparaît. Les journaux se trouvent dans `~/Library/Logs/Safari Assistant/`.

**Sans paquet d'application :** lancez `python3 server.py` dans le dossier du projet et ouvrez `http://localhost:8765`. Ollama doit déjà tourner.

Ce que font les deux scripts :

- `deploy.sh` télécharge les bibliothèques de carte dans `vendor/` uniquement si elles manquent, et vérifie leurs empreintes SHA-256 fixées. Il lance les tests si Node est installé (pour les sauter : `DEPLOY_OHNE_TESTS=1`). Il copie les fichiers de l'app dans un `Safari Assistant.app` existant s'il en trouve un, et le signale s'il n'en trouve pas. Il ne fait jamais de commit git, sauf si `DEPLOY_COMMIT=1` est défini ou si un fichier marqueur `.deploy-commit` existe ; cela ne concerne que le mainteneur.
- `build-app.sh` crée `~/Desktop/Safari Assistant.app` avec le serveur, les données et les bibliothèques. Le relancer met à jour le paquet sur place. Vos données à l'intérieur du paquet ne sont jamais supprimées : documents importés, `rag-store.json`, `karte.mbtiles`, `fonts/` et `data/warnzonen.geojson`.

**Mise à jour :** `git pull && ./deploy.sh`, puis redémarrez Safari Assistant.

**Documents PDF (en option) :** installez PyMuPDF pour le Python qui exécute le serveur. Pour l'app lancée depuis le Finder, c'est `/usr/bin/python3 -m pip install --user pymupdf`. Redémarrez Safari Assistant. Si un import échoue encore, le message d'erreur indique l'interpréteur exact.

La carte hors ligne, la Wikipédia hors ligne et tous les autres détails : [docs/SETUP.md](docs/SETUP.md) (en anglais).

---

## Mode iPhone

1. Sur le Mac : ⚙️ Réglages → **Mode iPhone** → **Activer**. Le Mac ouvre un second point d'écoute sur son adresse Wi-Fi, sur le même port 8765, en HTTPS. À la première utilisation, Safari Assistant crée pour cela une autorité de certification (CA) locale.
2. Une fois par iPhone, faites confiance à cette CA :
   - Les Réglages de Safari Assistant affichent le fichier du certificat avec un bouton **Afficher dans le Finder**. Envoyez le fichier à l'iPhone par AirDrop.
   - iPhone : Réglages → **Profil téléchargé** → Installer.
   - iPhone : Réglages → Général → Informations → **Réglages de confiance des certificats** → activez **« Safari Assistant lokale CA »** (anciennes installations : « DARK lokale CA » ou « Safari Assistent lokale CA ») ; le certificat porte ce nom allemand. C'est cette étape de confiance que l'on oublie.
3. Scannez le code QR affiché dans les Réglages avec l'appareil photo de l'iPhone, ou ouvrez `https://<your-mac>.local:8765/go/<code>` dans Safari. Cela enregistre le code d'accès et ouvre la vue téléphone.
4. Partager → **Sur l'écran d'accueil**.

Bon à savoir :

- Le mode iPhone est toujours désactivé après un démarrage. Il se désactive de lui-même après 12 heures sans requête du téléphone et quand Safari Assistant se ferme.
- **Ne l'activez jamais sur un Wi-Fi auquel vous ne faites pas confiance** (lodge, camp, frontière). Utilisez votre propre routeur ou le partage de connexion d'un téléphone.
- L'import, la suppression, l'arrêt et le changement de mode ne fonctionnent que sur le Mac lui-même.
- L'adresse contient le nom réseau du Mac, et le certificat aussi. Donnez d'abord au Mac un nom neutre : Réglages Système → Général → Partage → Nom d'hôte local.
- La CA est limitée aux noms `.local` et aux adresses privées. Ce que signifie lui faire confiance, et comment la supprimer : [SECURITY.md](SECURITY.md#the-local-certificate-authority).

---

## Ce qui passe par Internet

Hors ligne, rien ne quitte le Mac. Avec une connexion, voici tout ce que Safari Assistant envoie :

| Quoi | Quand | Vers où, ce qui est envoyé | Comment l'éviter |
|---|---|---|---|
| Avis aux voyageurs | À partir de 20 s après le démarrage : chaque fois que le cache a plus de 12 h, nouvel essai toutes les 15 min | Auswärtiges Amt, UK FCDO, US State Department. Aucune donnée personnelle | Pas encore d'interrupteur ([feuille de route](docs/ROADMAP.md)) |
| Zones d'avertissement | Après une récupération des avis, quand un texte d'avertissement a changé ou qu'aucune zone n'existe encore (au plus toutes les 6 h) | Overpass API (OpenStreetMap). Aucune donnée personnelle | `SAFARI_OHNE_WARNZONEN_AUTO=1` |
| Taux de change | À l'ouverture de la Fiche d'urgence (Mac) ou du volet 🚨 (téléphone) | open.er-api.com. Pas de position | Pas encore d'interrupteur ([feuille de route](docs/ROADMAP.md)) |
| Tuiles de carte | Tant que la carte affiche des tuiles en ligne, ce qui est le cas par défaut tant qu'il n'existe pas de `karte.mbtiles` hors ligne. Avec une carte hors ligne, quelques tuiles d'aperçu se chargent encore à chaque ouverture de la carte, avant qu'elle ne bascule | tile.openstreetmap.org. Les tuiles révèlent la zone que vous regardez | Construire la carte hors ligne |
| Glyphes des étiquettes de carte | Uniquement si `karte.mbtiles` existe mais que son dossier `fonts/` manque | fonts.openmaptiles.org | `setup-offline-karte.sh` installe `fonts/` |
| Bibliothèques de carte | Uniquement si des fichiers manquent dans `vendor/` | unpkg.com (la page de la carte se rabat sur le CDN) | Garder `vendor/` complet (`./deploy.sh`) |
| Recherche de lieux | Uniquement quand vous appuyez sur Entrée dans la recherche de la carte | nominatim.openstreetmap.org. Le texte recherché | Taper sans Entrée ne cherche que hors ligne |
| Panneau météo | Uniquement quand vous cliquez sur **Aujourd'hui** ou **🌐 charger** sur la carte | api.open-meteo.com. Position arrondie à environ 1 km | Ne pas cliquer |
| Anthropic | Avec une clé API : quand vous utilisez le module Claude ou Situation sécuritaire, ou le module Météo & saisons des pluies sur le Mac, et pour **Tester** / **Charger la liste** dans les Réglages | api.anthropic.com. La clé, votre question, une photo jointe, le contexte du chat et, si elle est enregistrée, votre position (±100 m) | Supprimer la clé |
| Scripts ponctuels | Uniquement quand vous les lancez | `deploy.sh` → unpkg.com (fichiers `vendor/` manquants uniquement ; avec `DEPLOY_LIZENZEN=1`, aussi raw.githubusercontent.com pour les textes de licence originaux). `fetch-*.py` → Overpass, GeoNames, NASA POWER. `fauna-gbif-check.py` → GBIF. Construction de la carte → GitHub, Geofabrik et les fichiers d'océans et de Natural Earth que Planetiler télécharge | Ne pas les lancer |
| Ollama | Jamais pour Safari Assistant | Le lanceur démarre Ollama avec `OLLAMA_NO_CLOUD=1` s'il ne tourne pas. Un Ollama que vous avez démarré vous-même garde ses propres réglages | – |

Pas de télémétrie, pas de mesure d'audience, pas de polices de Google.

---

## Sécurité et limites

Safari Assistant donne des conseils sur la médecine, les morsures de serpent, la réparation de véhicules, les passages à gué et les urgences. Les réponses viennent de modèles de langage qui peuvent se tromper avec assurance.

- Ce n'est **pas** un médecin, un mécanicien, un vétérinaire ni un guide. Il ne remplace ni une formation, ni une trousse de premiers secours, ni un communicateur satellite, ni le discernement.
- Vérifiez tout ce qui pourrait vous mettre en danger à l'aide d'un manuel imprimé, de la Wikipédia hors ligne ou d'une personne. Safari Assistant ne peut pas appeler à l'aide ; emportez un vrai communicateur d'urgence.
- **Aucune posologie de médicament**, à dessein. Les prompts demandent au modèle de ne pas indiquer ni inventer de doses, et de renvoyer vers un médecin, un vétérinaire ou la notice.
- Les **numéros d'urgence** ont été vérifiés en septembre 2026. Vérifiez-les avant le départ.
- Les **Protocoles immédiats** en anglais, français et espagnol sont des traductions du texte allemand, pas encore relues par des professionnels des premiers secours.
- La **colonne des ambassades liste les ambassades d'Allemagne**, pour les citoyens allemands. Toutes les autres personnes s'adressent à leur propre ambassade ou consulat.
- Les **zones d'avertissement aux voyageurs** sont une lecture automatisée du texte officiel, pas des frontières officielles. Le texte officiel fait toujours foi ; chaque entrée y renvoie par un lien.
- La **couche des pluies** est une climatologie 2001–2020 de NASA POWER, pas une prévision. Les saisons des pluies se décalent de plusieurs semaines d'une année à l'autre.
- Avec le **profil léger**, les réponses médicales et d'urgence viennent elles aussi du petit modèle `gemma4:e4b`. Les Mac de moins de 36 Go ne sont pas testés avec Safari Assistant ; voir [Quel modèle sur quel Mac](#quel-modèle-sur-quel-mac).
- Les prompts système ne sont pas traduits. Ils sont écrits pour un voyageur germanophone : par exemple, les numéros d'ambassade sont allemands, et le module Langues donne la prononciation pour des lecteurs germanophones. Les réponses arrivent malgré tout dans la langue que vous choisissez. Le module Mécanique et le plan d'entretien visent un seul véhicule. Un profil de voyage figure dans la [feuille de route](docs/ROADMAP.md). Les taux de change utilisent l'EUR comme devise de base.
- Les prompts système demandent au modèle d'exprimer son incertitude et de dire tôt quand une aide professionnelle est nécessaire. Cela réduit le risque ; cela ne le supprime pas.

---

## Langues

- **Interface :** anglais, allemand, français et espagnol. Tant que vous n'avez pas choisi, Safari Assistant utilise la langue de votre navigateur si c'est l'une de ces quatre, sinon l'anglais.
- **Changer de langue :** sur le Mac, avec les boutons **DE / EN / FR / ES** sous le nom de l'app dans la barre latérale, ou ⚙️ Réglages → **Langue de l'interface**. Sur l'iPhone : ⚙️ Configuration → **Langue de l'interface**. Sur la page de la carte : le menu des langues dans l'en-tête. Le choix est enregistré.
- **Les réponses de l'IA** suivent la langue de l'interface. La ligne 🌐 au-dessus du champ de saisie règle toutefois toujours la langue des réponses séparément : allemand, anglais, français, espagnol, portugais, swahili ou afrikaans.
- **L'allemand est la langue source.** Une couche de traduction (`i18n.js` avec `i18n/en.js`, `i18n/fr.js` et `i18n/es.js`) traduit l'interface pendant son exécution. Tout ce qui n'est pas encore traduit reste en allemand. Les prompts système ne sont pas traduits ; la langue des réponses indique au modèle dans quelle langue répondre.
- Les 8 **Protocoles immédiats** sont traduits eux aussi. La **Fiche d'urgence** a en plus sa propre ligne 🌐 (DE, EN, FR, PT, SW) pour ses libellés et ses en-têtes de tableau, à montrer à une personne qui vous vient en aide.
- Les archives de Wikipédia hors ligne sont généralement en anglais. Le petit modèle local transforme votre question en termes de recherche anglais.
- **Aide :** le **?** sur chaque page (barre latérale du Mac, barre des modules et Configuration sur l'iPhone, en-tête de la carte) ouvre ce guide dans la langue de l'interface, hors ligne. Le serveur de Safari Assistant l'affiche à l'adresse `/hilfe`. S'il manque une traduction, le guide anglais s'affiche.

Les traductions sont les bienvenues : [CONTRIBUTING.md](CONTRIBUTING.md#translations).

---

## Barrière de confidentialité

Le dépôt dispose d'une barrière de confidentialité (`tools/privacy_gate.py`) pour que personne ne publie de données personnelles par accident. Activez-la une fois après le clonage :

```bash
git config core.hooksPath .githooks
```

Elle s'exécute en pre-commit, commit-msg et pre-push, et à nouveau dans la CI. Elle bloque les exports de traces et de waypoints (GPX, KML), les sauvegardes de l'app, `rag-store.json`, les documents importés, `*.mbtiles` et `*.zim`, les clés et secrets, les chemins et noms d'hôte personnels, et les métadonnées d'images. Vous pouvez ajouter vos propres termes dans une liste locale, en dehors du dépôt.

Ne la contournez jamais avec `--no-verify`. Si elle signale quelque chose d'inoffensif, dites-le dans la pull request. Détails : [docs/PRIVACY-GATE.md](docs/PRIVACY-GATE.md).

---

## Développement et tests

```bash
node test-app.js
```

Node pur, sans dépendances, sans étape de build. Les tests lisent les fichiers sources comme du texte et vérifient que les correctifs et les fonctionnalités sont toujours là. Ils lancent aussi les tests Python (`test-reisewarnungen.py`, `test-tls.py`, `test-warngebiete.py`, `test-sicherheit.py`, `test-hilfe.py`), l'auto-test de la barrière de confidentialité (`tools/test_privacy_gate.py`) et le validateur de données OSM (`tools/validate_osm_exports.py`). Ceux-ci nécessitent `python3`, et `test-tls.py` nécessite `openssl` ; sans eux, ces tests sont sautés avec une remarque. La CI exécute la même suite à chaque push et à chaque pull request.

Règles, conventions et liste de contrôle pour les pull requests : [CONTRIBUTING.md](CONTRIBUTING.md). Comment les éléments s'articulent : [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Une remarque sur le nom.** Le nom s'écrit de la même façon dans toutes les langues : Safari Assistant. Pendant le développement, l'app s'appelait *Safari Assistent* (orthographe allemande), puis brièvement *DARK* juste avant la première publication. DARK n'est plus que le nom de son créateur. Les identifiants internes restent inchangés exprès, pour que les installations existantes gardent leurs données, leurs autorisations macOS et le certificat auquel l'iPhone fait confiance : les clés de stockage du navigateur `safari-*`, les bases IndexedDB `safari-docs` et `safari-pois-db`, le cookie `safari_zugang`, les fichiers `~/.safari-assistant-*`, les variables d'environnement `SAFARI_*`, le dossier du paquet `Contents/Resources/safari-assistant`, l'identifiant de bundle `com.safari-assistent.app`, le fichier du certificat `~/.safari-assistant-tls/safari-assistent-ca.crt` et la signature du serveur `safari-assistent` (renvoyée par `/api/ping`). Ces trois derniers gardent l'orthographe du développement, « assistent ». Conservés eux aussi exprès, de la brève période DARK : les variables globales JavaScript `window.DARK_I18N` et `window.__DARK_I18N_DATEN` (chaque dictionnaire de `i18n/` appelle cette dernière) et les variables d'environnement `DARK_APP` et `DARK_LOG_DIR`.

---

## Licences

- **Code :** [PolyForm Noncommercial License 1.0.0](LICENSE), © 2026 DARK (github.com/DarkPirateGo). Vous pouvez utiliser, modifier et partager Safari Assistant gratuitement pour tout usage non commercial ; c'est une licence « source-available » (code source consultable), pas une licence open source approuvée par l'OSI. Un usage commercial nécessite une licence distincte de DARK ; demandez-la dans une [issue](https://github.com/DarkPirateGo/safari-assistant/issues). Ce que la licence autorise : [NOTICE.md](NOTICE.md#safari-assistants-own-code).
- **Hors PolyForm Noncommercial :**
  - `POIs/*-osm.json` et `data/parks.geojson` : © contributeurs d'OpenStreetMap, ODbL 1.0
  - `data/orte.json` : GeoNames, CC BY 4.0
  - `data/klima.json` : projet POWER du NASA Langley Research Center
  - `vendor/` : Leaflet (BSD-2-Clause), Leaflet.markercluster (MIT), MapLibre GL JS (BSD-3-Clause)
  - Encodeur de codes QR : adapté de Project Nayuki, MIT
  - Les noms « Safari Assistant » et « DARK », le logo et l'icône de Safari Assistant (`docs/img/logo/`, `docs/img/social-preview.png`) et le logo DARK `dark-logo.jpg` : tous droits réservés. Les forks doivent les remplacer en tant que nom et logo de leur version. La ligne `Required Notice:` de [LICENSE](LICENSE), qui désigne DARK comme titulaire des droits d'auteur, reste : la licence exige de la transmettre.
- **Non inclus, volontairement :** exports iOverlander, manuels des constructeurs, copies de conseils aux voyageurs.

Liste complète et textes des licences : [NOTICE.md](NOTICE.md).

---

## Crédits

Créé par DARK ([github.com/DarkPirateGo](https://github.com/DarkPirateGo)).

Construit avec [Ollama](https://ollama.com), [Leaflet](https://leafletjs.com), [Leaflet.markercluster](https://github.com/Leaflet/Leaflet.markercluster), [MapLibre GL JS](https://maplibre.org), [Planetiler](https://github.com/onthegomap/planetiler), [OpenMapTiles](https://openmaptiles.org), [Kiwix](https://kiwix.org) et [PyMuPDF](https://pymupdf.readthedocs.io). Données des contributeurs d'[OpenStreetMap](https://www.openstreetmap.org/copyright), de [GeoNames](https://www.geonames.org), de [NASA POWER](https://power.larc.nasa.gov) et d'[Open-Meteo](https://open-meteo.com). Conseils aux voyageurs du ministère fédéral allemand des Affaires étrangères (Auswärtiges Amt), du FCDO britannique et du Département d'État américain. Encodeur de codes QR adapté de [Project Nayuki](https://www.nayuki.io/page/qr-code-generator-library).

<p align="center"><a href="https://github.com/DarkPirateGo"><img src="docs/img/dark-logo.jpg" alt="DARK" width="200"></a><br><sub>made by DARK</sub></p>
