#!/usr/bin/env bash
#
# Installe director-cut sur un Mac neuf, en une fois.
#
#   ./install.sh
#
# Le script est fait pour être relancé sans risque : chaque étape vérifie
# d'abord si elle a déjà été faite. Il ne touche à rien en dehors de ce dossier,
# de Homebrew, et du cache des modèles (~/.cache/director-cut).

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------- affichage --

if [ -t 1 ] && command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
    BLEU=$(tput setaf 4); GRAS=$(tput bold); ROUGE=$(tput setaf 1)
    VERT=$(tput setaf 2); GRIS=$(tput setaf 8); RAZ=$(tput sgr0)
else
    BLEU=""; GRAS=""; ROUGE=""; VERT=""; GRIS=""; RAZ=""
fi

titre()   { printf '\n%s%s» %s%s\n' "$GRAS" "$BLEU" "$1" "$RAZ"; }
ok()      { printf '  %s✓%s %s\n' "$VERT" "$RAZ" "$1"; }
info()    { printf '  %s%s%s\n' "$GRIS" "$1" "$RAZ"; }
alerte()  { printf '  %s!%s %s\n' "$ROUGE" "$RAZ" "$1"; }
stop()    { printf '\n%s%sArrêt :%s %s\n\n' "$GRAS" "$ROUGE" "$RAZ" "$1"; exit 1; }

trap 'printf "\n%s%sL'\''installation s'\''est arrêtée sur une erreur.%s\nRelance ./install.sh : les étapes déjà faites seront sautées.\n\n" "$GRAS" "$ROUGE" "$RAZ"' ERR

# Question oui/non. Hors terminal (script appelé par un autre script, ou sortie
# redirigée), on refuse : rien de lourd ni d'irréversible ne doit se lancer sans
# que quelqu'un ait dit oui.
demander() {
    local question="$1" defaut="${2:-o}" reponse
    if [ ! -t 0 ]; then return 1; fi
    if [ "$defaut" = "o" ]; then question="$question [O/n] "; else question="$question [o/N] "; fi
    read -r -p "  $question" reponse || reponse=""
    reponse="${reponse:-$defaut}"
    [[ "$reponse" =~ ^[oOyY] ]]
}

printf '\n%s%sInstallation de director-cut%s\n' "$GRAS" "$BLEU" "$RAZ"
info "Dossier : $(pwd)"

# ------------------------------------------------------------------ système --

titre "Système"

case "$(uname -s)" in
    Darwin) ok "macOS $(sw_vers -productVersion 2>/dev/null || echo '')" ;;
    Linux)  ok "Linux — prévu pour macOS, ça devrait marcher quand même" ;;
    *)      stop "ce script est prévu pour macOS. Sur Windows, suivre la section Installation du README." ;;
esac

# ------------------------------------------------------------------ Homebrew --
# Homebrew n'est nécessaire que s'il manque ffmpeg ou un Python récent. On ne
# l'installe donc qu'au moment où on en a vraiment besoin.

installer_homebrew() {
    if command -v brew >/dev/null 2>&1; then return 0; fi
    for candidat in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [ -x "$candidat" ]; then eval "$("$candidat" shellenv)"; return 0; fi
    done
    alerte "Homebrew est absent — c'est l'outil qui installe ffmpeg et Python."
    info "L'installation va demander le mot de passe de la session."
    if ! demander "Installer Homebrew maintenant ?"; then
        stop "sans Homebrew, il manquera ffmpeg et/ou Python 3.10+."
    fi
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    for candidat in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [ -x "$candidat" ]; then eval "$("$candidat" shellenv)"; fi
    done
    command -v brew >/dev/null 2>&1 || stop "Homebrew s'est installé mais reste introuvable. Ferme le Terminal, rouvre-le, et relance ./install.sh"
}

# -------------------------------------------------------------------- ffmpeg --

titre "ffmpeg"

if command -v ffmpeg >/dev/null 2>&1; then
    ok "déjà là ($(command -v ffmpeg))"
else
    info "ffmpeg découpe et réencode les vidéos : sans lui, rien ne marche."
    installer_homebrew
    brew install ffmpeg
    command -v ffmpeg >/dev/null 2>&1 || stop "ffmpeg ne répond toujours pas après installation."
    ok "installé"
fi

command -v curl >/dev/null 2>&1 || stop "curl est introuvable (il est normalement livré avec macOS)."

# -------------------------------------------------------------------- Python --
# macOS livre Python 3.9, or le projet demande 3.10 minimum. On cherche donc une
# version utilisable avant de se rabattre sur Homebrew.

titre "Python 3.10 ou plus récent"

trouver_python() {
    local candidat
    for candidat in python3.13 python3.12 python3.11 python3.10 python3; do
        command -v "$candidat" >/dev/null 2>&1 || continue
        if "$candidat" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
            PYTHON="$(command -v "$candidat")"
            return 0
        fi
    done
    return 1
}

if trouver_python; then
    ok "$("$PYTHON" -V) ($PYTHON)"
else
    info "Le Python livré avec macOS est trop ancien (3.9) pour ce projet."
    installer_homebrew
    brew install python@3.12
    hash -r
    trouver_python || stop "Python 3.10+ reste introuvable après installation."
    ok "$("$PYTHON" -V) ($PYTHON)"
fi

# --------------------------------------------------------- environnement pip --

titre "Environnement Python du projet"

if [ -x .venv/bin/python ] && .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    ok ".venv déjà en place"
else
    [ -e .venv ] && rm -rf .venv
    "$PYTHON" -m venv .venv
    ok ".venv créé"
fi

if .venv/bin/python -c 'import director_cut' 2>/dev/null && .venv/bin/director-cut --help >/dev/null 2>&1; then
    ok "director-cut déjà installé"
    info "Mise à jour des dépendances si besoin…"
fi

info "Téléchargement des bibliothèques (torch, pyannote, whisper…)."
info "Compter plusieurs minutes et ~2 Go la première fois."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install -e .
ok "installé"

# --------------------------------------------------------------- token HF --
# Les modèles de diarisation sont sous conditions : il faut un compte Hugging
# Face, avoir accepté les 3 pages, et un token de lecture. C'est l'étape qui
# échoue le plus souvent, donc on la vérifie vraiment au lieu de la supposer.

MODELES_HF=(
    "pyannote/speaker-diarization-3.1"
    "pyannote/segmentation-3.0"
    "pyannote/speaker-diarization-community-1"
)

verifier_token() {
    local jeton="$1" code modele
    code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $jeton" \
           https://huggingface.co/api/whoami-v2 || echo 000)
    if [ "$code" != "200" ]; then
        RAISON="le token n'est pas reconnu par Hugging Face (code $code)."
        return 1
    fi
    for modele in "${MODELES_HF[@]}"; do
        code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $jeton" \
               "https://huggingface.co/$modele/resolve/main/config.yaml" || echo 000)
        if [ "$code" != "200" ]; then
            RAISON="les conditions de $modele ne sont pas acceptées (code $code).
       Ouvre https://huggingface.co/$modele et clique « Agree and access »."
            return 1
        fi
    done
    return 0
}

titre "Accès aux modèles de reconnaissance de voix"

JETON=""
[ -f .hf_token ] && JETON=$(tr -d '[:space:]' < .hf_token)

if [ -n "$JETON" ] && verifier_token "$JETON"; then
    ok "token déjà en place, et les 3 modèles sont accessibles"
else
    [ -n "$JETON" ] && alerte "Le token présent ne suffit pas : $RAISON"
    cat <<'EXPLICATION'
  À faire une seule fois, dans le navigateur :
    1. Créer un compte sur huggingface.co et confirmer l'e-mail.
    2. Sur ces 3 pages, cliquer « Agree and access » :
         huggingface.co/pyannote/speaker-diarization-3.1
         huggingface.co/pyannote/segmentation-3.0
         huggingface.co/pyannote/speaker-diarization-community-1
    3. Créer un token de type « Read » : huggingface.co/settings/tokens
EXPLICATION
    if [ -t 0 ] && command -v open >/dev/null 2>&1; then
        if demander "Ouvrir ces pages dans le navigateur ?"; then
            for modele in "${MODELES_HF[@]}"; do open "https://huggingface.co/$modele"; done
            open "https://huggingface.co/settings/tokens"
        fi
    fi

    if [ ! -t 0 ]; then
        alerte "Pas de terminal interactif : impossible de demander le token."
        info "Fais-le à la main :  echo \"hf_xxx\" > .hf_token  puis relance ./install.sh"
        exit 1
    fi

    while true; do
        printf '\n'
        read -r -p "  Colle le token ici (commence par hf_), ou Entrée pour passer : " JETON
        JETON=$(printf '%s' "$JETON" | tr -d '[:space:]')
        if [ -z "$JETON" ]; then
            alerte "Étape sautée. director-cut ne pourra pas tourner tant que .hf_token est absent."
            break
        fi
        if verifier_token "$JETON"; then
            printf '%s\n' "$JETON" > .hf_token
            chmod 600 .hf_token
            ok "token enregistré dans .hf_token et vérifié sur les 3 modèles"
            break
        fi
        alerte "$RAISON"
    done
fi

# ------------------------------------------------------------ voix de départ --

titre "Extrait de voix"

if [ -d samples ] && [ -n "$(find samples -maxdepth 1 -type f \( -iname '*.mp4' -o -iname '*.wav' -o -iname '*.m4a' -o -iname '*.mp3' -o -iname '*.mkv' -o -iname '*.mov' \) 2>/dev/null | head -1)" ]; then
    ok "dossier samples/ trouvé"
elif compgen -G "sample*" >/dev/null 2>&1; then
    ok "extrait $(compgen -G 'sample*' | head -1) trouvé"
else
    alerte "Aucun extrait de voix dans ce dossier."
    info "Dépose ici un fichier nommé sample.mp4 : un passage où on entend"
    info "beaucoup ta voix (une chronique entière fait un très bon extrait)."
    info "Peu importe qu'il y ait d'autres voix, l'outil repère la dominante."
    info "L'empreinte vocale sera fabriquée toute seule au premier lancement."
fi

# ------------------------------------------------- modèles de retouche (opt) --

titre "Modèles de retouche des vignettes (optionnel)"

if .venv/bin/python -c '
from director_cut import enhance
import sys
sys.exit(0 if all(enhance.is_ready(n) for n in enhance.MODELS) else 1)' 2>/dev/null; then
    ok "déjà téléchargés"
else
    info "Ils effacent l'habillage de la chaîne sur les vignettes et agrandissent"
    info "l'image. Environ 500 Mo, une seule fois. Sans eux tout marche, les"
    info "vignettes sont juste moins propres."
    if demander "Les télécharger maintenant ?" "o"; then
        .venv/bin/director-cut models
    else
        info "Plus tard :  ./decoupe models"
    fi
fi

# ------------------------------------------------------------- raccourci --
# Pour éviter d'avoir à activer l'environnement Python à chaque fois.

cat > decoupe <<'LANCEUR'
#!/usr/bin/env bash
# Raccourci : évite d'avoir à activer l'environnement Python à chaque fois.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec .venv/bin/director-cut "$@"
LANCEUR
chmod +x decoupe

# ---------------------------------------------------------------- vérification --

titre "Vérification"

.venv/bin/director-cut --help >/dev/null || stop "director-cut ne répond pas. Relance ./install.sh"
ok "director-cut répond"
ffmpeg -version >/dev/null 2>&1 && ok "ffmpeg répond"
[ -s .hf_token ] && ok "token en place" || alerte "token manquant (.hf_token)"

printf '\n%s%sPrêt.%s\n\n' "$GRAS" "$VERT" "$RAZ"
printf '  Pour découper une vidéo, depuis ce dossier :\n\n'
printf '      %s./decoupe run "COLLER_L_ADRESSE_DU_REPLAY" --mode reportage%s\n\n' "$BLEU" "$RAZ"
printf '  Les résultats sortent dans %ssortie/%s.\n' "$BLEU" "$RAZ"
printf '  Le premier lancement télécharge encore ~2 Go de modèles, une seule fois.\n\n'
