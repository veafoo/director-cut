# director-cut

Récupère une vidéo (replay d'un JT, d'une matinale, d'une émission…) et découpe
**par la voix** les passages d'une personne — chronique, reportage, ou JT
complet. Aucune reconnaissance faciale.

Pour chaque passage, l'outil produit : la vidéo découpée, l'audio, des
sous-titres FR **et** EN, des screenshots recadrés en 9:16 (vignettes réseaux
sociaux), et un MKV avec les sous-titres embarqués — le tout rangé dans un
dossier propre au run.

---

## D'où ça vient

Ma copine est journaliste. Chaque semaine, ses reportages et ses chroniques
partent dans un replay de 40 minutes, quelque part au milieu du journal. Pour
alimenter son book et ses réseaux, il fallait à chaque fois : retrouver le
replay, le télécharger, scruter la timeline pour repérer où son sujet commence
et où il finit, découper à la main, réexporter en vertical, sous-titrer.

`director-cut` fait tout ça à sa place, avec **une seule commande**. Il
reconnaît sa voix, trouve ses passages, cale le début sur l'annonce du
présentateur et la fin sur le retour plateau, et sort le tout prêt à publier.
Elle n'est pas développeuse : c'est la contrainte de design principale du
projet — une commande, une URL, rien d'autre à comprendre.

---

## Pour la personne : une seule ligne

```bash
director-cut run "https://www.exemple.fr/…/replay.html" --mode reportage
```

L'empreinte de la voix est fabriquée automatiquement la première fois, le seuil
se calibre seul, et tout sort dans `sortie/extract_<mode>_<date>/`.

---

## Réglage initial (à faire UNE fois)

À la racine du dossier du projet, déposer :

1. **`sample.mp4`** — un extrait où on entend **beaucoup** la voix de la
   personne (peu importe qu'il y ait d'autres voix : l'outil repère le locuteur
   dominant). Le nom doit commencer par `sample`. Une chronique entière fait un
   très bon sample.
   *Variante :* un dossier `samples/` contenant des extraits déjà propres (sa
   voix seule) est prioritaire sur `sample.mp4` s'il existe.
2. **`.hf_token`** — un token Hugging Face gratuit (voir Installation).
3. **`names.txt`** *(optionnel, utile en chronique)* — le nom prononcé au
   lancement et ses variantes, une par ligne (la transcription écorche les noms
   propres, donc plusieurs orthographes). Sert uniquement à confirmer qu'un
   lancement a bien été capté ; ça ne change pas la découpe.
4. **`brands/<chaîne>.png`** *(optionnel)* — le logo à poser sur les vignettes
   9:16. S'il n'y en a qu'un, il est utilisé automatiquement. Voir Vignettes.

Ces fichiers sont ignorés par git : ni voix, ni token, ni logo de chaîne ne
partent dans le dépôt.

---

## Installation

Prérequis : **Python 3.10+**, **ffmpeg**, **curl** (présents par défaut sur Mac ;
sur Windows installer ffmpeg via `winget install Gyan.FFmpeg`).

```bash
cd director-cut
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

Premier lancement : les modèles (diarisation, empreinte vocale, Whisper) sont
téléchargés une fois et mis en cache. Compter quelques minutes et ~2 Go.

### Token Hugging Face (gratuit, une fois)

1. Compte sur huggingface.co, **e-mail confirmé**.
2. Accepter les conditions sur ces pages (bouton « Agree and access ») :
   - huggingface.co/pyannote/speaker-diarization-3.1
   - huggingface.co/pyannote/segmentation-3.0
   - huggingface.co/pyannote/speaker-diarization-community-1
3. Créer un token **Read** (huggingface.co/settings/tokens).
4. `echo "hf_xxx" > .hf_token`

Le token peut aussi être passé par la variable d'environnement `HF_TOKEN` ou
l'option `--hf-token`.

---

## Modes

- **`--mode reportage`** — un sujet réalisé en voix off. Début au retour plateau
  + annonce, tout le reportage (sons d'interview inclus), fin au retour plateau
  **sans montrer le présentateur**.
- **`--mode chronique`** — chronique sur le plateau. Début à l'annonce du sujet,
  toute la chronique (y compris l'échange de clôture avec le présentateur), fin
  au démarrage de l'annonce du sujet suivant.
- **`--mode jt`** — présentation de toute l'édition : on garde tout ce qu'elle
  dit, regroupé par blocs.

Plusieurs passages dans une même vidéo → chacun découpé et rangé à part.

---

## Ce qui sort (structure d'un run)

```
sortie/extract_reportage_2026-08-12/
├── passages/   passage_01.mp4, passage_02.mp4 …      (vidéos découpées)
├── audio/      passage_01.m4a …                      (audio par passage)
├── srt/        passage_01.fr.srt, passage_01.en.srt … (sous-titres FR + EN)
├── screens/    passage_01_01.jpg … (9:16)            (vignettes réseaux sociaux)
└── mkv/        passage_01.mkv …                      (vidéo + sous-titres embarqués)
```

Un dossier distinct est créé par run et par type (`extract_reportage_…`,
`extract_chronique_…`, `extract_jt_…`). La date est déduite de l'URL/fichier, à
défaut c'est celle du jour.

Les sous-titres de chaque passage sont recalés à zéro : ils sont directement
utilisables sur le mp4 découpé, sans décalage à corriger.

---

## Commandes toutes prêtes

Remplace `URL` par le lien (entre guillemets). Les réglages ci-dessous sont pour
`reportage` ; en chronique, remplacer par `chronique`.

Reportage / chronique / JT :
```bash
director-cut run "URL" --mode reportage
director-cut run "URL" --mode chronique
director-cut run "URL" --mode jt
```

Lien impossible à télécharger → fichier local :
```bash
director-cut run "video_du_jt.mp4" --mode reportage
```

Si le résultat n'est pas parfait :
```bash
# non reconnue / "Voix non reconnue"
director-cut run "URL" --mode reportage --threshold 0.20
# attrape une autre personne
director-cut run "URL" --mode reportage --threshold 0.35
# on voit le présentateur à la fin
director-cut run "URL" --mode reportage --end-trim 1.0
# début coupé, annonce incomplète
director-cut run "URL" --mode reportage --lookback 60
# reportage découpé en morceaux (interviews)
director-cut run "URL" --mode reportage --merge-gap 120
# plus de screenshots par passage
director-cut run "URL" --mode reportage --shots 6
# version rapide (coupe au plan près, moins précise)
director-cut run "URL" --mode reportage --fast
```

---

## Vignettes 9:16 *(optionnel, `--screens`)*

> **Désactivées par défaut, et c'est volontaire.** Une image de télévision est en
> 16:9 ; un recadrage 9:16 n'en garde que **32 % de la largeur**. Les bords
> sautent, la personne filmée est coupée, et le résultat est rarement publiable
> tel quel. La retouche IA qui l'accompagne charge par ailleurs lourdement la
> machine. Le cadrage reste un chantier ouvert : voir *Limites connues*.

Le rendu reprend celui des vignettes publiées par les chaînes : **image plein
cadre** (recadrage 9:16 centré, ni bandes noires ni fond flou) et **logo posé à
l'emplacement du gabarit de la chaîne**.

Un gabarit, c'est un logo plus trois nombres : marge gauche, marge haute,
hauteur du logo, exprimés en fraction de l'image de sortie (1080×1920). Les
gabarits fournis dans `brands.py` sont relevés au pixel près sur de vraies
vignettes publiées.

Pour l'utiliser : déposer le logo dans `brands/`, en PNG.

```
brands/
└── ma_chaine.png
```

Un seul fichier dans `brands/` → il est appliqué sans rien demander. Plusieurs →
préciser lequel avec `--brand ma_chaine`. Aucun → vignettes sans logo.

Pour caler un gabarit qui n'est pas fourni, poser un `brands/ma_chaine.json` à
côté du logo :

```json
{"left": 0.0759, "top": 0.1969, "height": 0.1151}
```

### Retouche IA

Un replay porte l'habillage antenne : logo de la chaîne, horloge, météo,
bandeau titre, bandeau déroulant, et le synthé qui nomme les interviewés. Un
recadrage 9:16 tombe forcément dedans et ressort avec du texte coupé en plein
mot. Le geste manuel — effacer ces éléments, puis retravailler la netteté —
est industrialisé ici, en local :

1. **Effacement.** Modèle LaMa (inpainting) : il *reconstruit le décor* derrière
   le graphisme au lieu de le recouvrir.
2. **Agrandissement.** La source est du 720p, la vignette du 1080×1920.
   Real-ESRGAN reconstruit ×4, puis on redescend à la taille cible — une
   réduction depuis une image sur-résolue est bien plus fine qu'un
   agrandissement direct.

```bash
director-cut models     # une fois : télécharge les deux modèles (260 Mo)
```

Ensuite c'est automatique à chaque run. `--sans-retouche` pour couper. Si les
modèles ne sont pas installés, la retouche est simplement ignorée : le reste du
run continue.

Rien ne sort de la machine : les deux modèles tournent en local, sur le torch
déjà installé pour la diarisation. Aucune clé d'API, aucun coût par image, et
un rendu reproductible. Compter ~13 s par vignette sur un Mac Apple Silicon.

**Ce que l'IA invente.** L'effacement reconstruit des pixels qui n'ont jamais
existé. Sur une zone entourée d'image réelle (le bandeau titre, le synthé) le
résultat est fidèle. Sur une bande qui touche le bord de l'image, le modèle n'a
de contexte que d'un côté et ça se voit — c'est pourquoi ces bandes-là sont
sorties du cadre plutôt que reconstruites (`--strip-furniture`, actif par
défaut avec la retouche puisque la super-résolution rattrape le zoom).

### Déclarer l'habillage d'une autre chaîne

L'emprise de chaque élément se déclare en fractions de l'image source, dans
`brands/<chaîne>.json` :

```json
{"furniture": [
  {"box": [0.0, 0.84, 1.0, 1.0]},
  {"box": [0.651, 0.211, 0.906, 0.511], "color": [49, 49, 109], "cover": 0.10}
]}
```

`box` = gauche, haut, droite, bas. Une boîte qui touche un bord doit aller
**jusqu'au** bord : un liseré de graphisme oublié et le modèle recopie sa
couleur sur toute la zone.

`color` rend l'élément **conditionnel** : il n'est effacé que si cette couleur
couvre au moins `cover` de la boîte. C'est indispensable pour les éléments
intermittents comme le synthé d'interview — sans ça, on effacerait de la vraie
image chaque fois qu'il n'est pas à l'antenne.

### Netteté du choix de frame

Indépendamment de l'IA : une frame prise en plein mouvement est floue quoi
qu'on fasse derrière. L'outil teste plusieurs frames autour de l'instant visé et
garde la plus nette (variance du laplacien). `--sharpen` règle le masque flou
final (0 pour couper).

---

## Options

| Option | Effet |
|---|---|
| `--mode chronique\|reportage\|jt` | Défaut `chronique`. |
| `--threshold X` | Force le seuil (sinon auto-calibré). |
| `--merge-gap S` | Regroupement des prises (défaut 20/60/300 s selon le mode). |
| `--lookback S` | Remontée max pour l'annonce (défaut 40 s). |
| `--precut S` | Fenêtre pour caler une borne sur un cut plateau (défaut 5 s). |
| `--end-trim S` | Marge de fin, jamais de retour plateau (défaut 0.5 s). |
| `--fast` | Coupe au plan près (défaut : à l'image près). |
| `--shots N` | Screenshots 9:16 par passage (défaut 4). |
| `--brand NOM` | Gabarit de vignette (`brands/NOM.png`). Auto s'il n'y en a qu'un. |
| `--sharpen X` | Force du masque flou sur les vignettes (défaut 0.8, 0 = coupé). |
| `--sans-retouche` | Coupe la retouche IA des vignettes. |
| `--strip-furniture` / `--no-strip-furniture` | Force le rognage des bandes d'habillage (défaut : actif avec la retouche). |
| `--screens` | Produit les vignettes 9:16 (désactivées par défaut, voir plus bas). |
| `--no-mkv` / `--no-transcript` | Désactive une sortie. |
| `--workers N` | Tâches en parallèle (défaut 3). |
| `--name X` | Variante de nom en plus de `names.txt` (répétable). |
| `--whisper-size` | `tiny`…`large-v3` pour la transcription. |
| `--out DOSSIER` | Dossier de sortie racine (défaut `sortie`). |
| `--ref FICHIER` | Emplacement de l'empreinte vocale (défaut `voix_ref.npz`). |

Commandes annexes :

- `director-cut models` — télécharge une fois les modèles de retouche.
- `director-cut enroll <fichier…>` — force la reconstruction de l'empreinte
  vocale (un fichier = extrait brut multi-voix, plusieurs = extraits déjà
  propres).

---

## Comment ça marche

1. **Téléchargement** — yt-dlp. Les sites qui hébergent sur Brightcove avec un
   extracteur cassé sont résolus en lisant la page (identifiant vidéo + compte,
   repli sur le flux HLS signé).
2. **Diarisation** — pyannote découpe l'audio en tours de parole : qui parle,
   quand.
3. **Identification** — chaque locuteur est comparé à l'empreinte vocale de
   référence (modèle wespeaker). Le seuil est calibré automatiquement à
   l'enrôlement, en séparant la distribution de sa voix de celle des autres.
4. **Détection de plans** — PySceneDetect liste les changements de plan.
5. **Bornage** — c'est le cœur du projet : le début remonte jusqu'au plan
   d'annonce du présentateur (sans jamais remonter à l'ouverture du journal), la
   fin se cale sur le retour plateau, juste avant que le présentateur ne
   réapparaisse.
6. **Sorties** — découpe à l'image près, transcription Whisper FR + traduction
   EN, screenshots 9:16, MKV sous-titré. Le post-traitement de chaque passage
   tourne en parallèle.

---

## Tests

```bash
pip install -e ".[dev]"
pytest
```

La suite couvre la logique pure — bornage des passages, fusion des segments,
calibration du seuil, découpage des sous-titres, compatibilité pyannote 3.x/4.x,
lecture des pages Brightcove, construction des commandes ffmpeg. Elle ne
télécharge rien et n'appelle ni ffmpeg ni les modèles : les sorties média
elles-mêmes se valident sur un run réel.

---

## Vie privée

- **Aucune reconnaissance faciale** : c'est la voix qui identifie la personne,
  et c'est un choix, pas une limite technique.
- L'empreinte vocale (`voix_ref.npz`) est un vecteur numérique calculé et
  stocké **en local**. Elle ne quitte jamais la machine et n'est pas versionnée.
- Les samples, les fichiers de sortie et le token sont ignorés par git.
- La transcription tourne en local (faster-whisper), rien n'est envoyé à un
  service tiers.

---

## Limites connues

- La qualité de la découpe dépend de la qualité du sample : une voix mal
  échantillonnée donne un seuil bancal (jouer sur `--threshold`).
- Un reportage entrecoupé de longues interviews peut ressortir en plusieurs
  passages → augmenter `--merge-gap`.
- **Cadrage des vignettes : chantier ouvert.** Le recadrage 9:16 est centré et
  ne suit pas le sujet. Surtout, il ne garde qu'un tiers de la largeur, ce qui
  serre trop l'image. La bonne réponse serait de garder l'image entière et de
  faire *générer* le haut et le bas manquants (outpainting), comme le font les
  outils grand public. Testé et écarté pour l'instant : un modèle de diffusion
  en local sature une machine portable, et la génération d'images de l'API
  Gemini n'existe pas en gratuit. D'où l'option, plutôt qu'un défaut bancal.
- Sur une source 720p, la vignette 1080×1920 est un agrandissement (×1.8, et
  ×4 avec `--strip-furniture`). Le masque flou compense, il ne crée pas du
  détail qui n'existe pas.
- Les fichiers de configuration (`sample.mp4`, `.hf_token`, `names.txt`) sont
  lus depuis le dossier courant.
