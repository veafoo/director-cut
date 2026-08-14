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

Ces trois fichiers sont ignorés par git : rien de personnel ne part dans le
dépôt.

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
| `--no-screens` / `--no-mkv` / `--no-transcript` | Désactive une sortie. |
| `--workers N` | Tâches en parallèle (défaut 3). |
| `--name X` | Variante de nom en plus de `names.txt` (répétable). |
| `--whisper-size` | `tiny`…`large-v3` pour la transcription. |
| `--out DOSSIER` | Dossier de sortie racine (défaut `sortie`). |
| `--ref FICHIER` | Emplacement de l'empreinte vocale (défaut `voix_ref.npz`). |

Commande annexe : `director-cut enroll <fichier…>` force la reconstruction de
l'empreinte vocale (un fichier = extrait brut multi-voix, plusieurs = extraits
déjà propres).

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
- Les screenshots 9:16 gardent l'image d'origine centrée sur un fond flou
  (logo et bandeaux restent lisibles) : ils ne recadrent pas intelligemment.
- Les fichiers de configuration (`sample.mp4`, `.hf_token`, `names.txt`) sont
  lus depuis le dossier courant.
