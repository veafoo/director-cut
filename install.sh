#!/usr/bin/env bash
#
# Installe director-cut sur un Mac, y compris un Mac neuf où il n'y a rien.
#
#   ./install.sh
#
# Ou, sur une machine où le projet n'est même pas encore là :
#
#   curl -fsSL https://raw.githubusercontent.com/veafoo/director-cut/main/install.sh | bash
#
# Chaque étape regarde d'abord ce qu'il y a sur la machine : ce qui est déjà là
# est laissé tel quel, ce qui manque est installé. Le script peut être relancé
# autant de fois que voulu.
#
# À la fin, la commande `director-cut` est utilisable depuis n'importe où.

set -euo pipefail

DEPOT="https://github.com/veafoo/director-cut"
DOSSIER_PAR_DEFAUT="$HOME/director-cut"

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

trap 'printf "\n%s%sL'\''installation s'\''est arrêtée sur une erreur.%s\nRelance-la : les étapes déjà faites seront sautées.\n\n" "$GRAS" "$ROUGE" "$RAZ"' ERR

# Le script peut être lancé par `curl … | bash` : dans ce cas l'entrée standard
# est le script lui-même, pas le clavier. On parle alors directement au terminal.
if [ -t 0 ]; then
    CLAVIER="/dev/stdin"
elif [ -e /dev/tty ] && (exec 3<>/dev/tty) 2>/dev/null; then
    CLAVIER="/dev/tty"
else
    CLAVIER=""            # aucune interaction possible
fi

demander() {
    local question="$1" defaut="${2:-o}" reponse
    [ -n "$CLAVIER" ] || return 1
    if [ "$defaut" = "o" ]; then question="$question [O/n] "; else question="$question [o/N] "; fi
    printf '  %s' "$question"
    read -r reponse < "$CLAVIER" || reponse=""
    reponse="${reponse:-$defaut}"
    [[ "$reponse" =~ ^[oOyY] ]]
}

# ---------------------------------------------------- récupération du projet --
# Si le script tourne tout seul (téléchargé par curl), il n'a pas le projet
# autour de lui : il va le chercher, puis se relance depuis là.

# Lancé par `curl | bash`, BASH_SOURCE est vide : il n'y a pas de dossier autour.
ICI="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" 2>/dev/null && pwd || echo "")"

if [ -z "$ICI" ] || [ ! -f "$ICI/pyproject.toml" ]; then
    printf '\n%s%sInstallation de director-cut%s\n' "$GRAS" "$BLEU" "$RAZ"
    titre "Récupération du projet"
    CIBLE="$DOSSIER_PAR_DEFAUT"
    if [ -f "$CIBLE/pyproject.toml" ]; then
        ok "déjà présent dans $CIBLE"
    else
        info "Téléchargement dans $CIBLE"
        # Attention : sur un Mac neuf, /usr/bin/git EXISTE mais n'est qu'une
        # amorce qui réclame les outils Apple. `command -v git` répond donc oui
        # alors que git ne marche pas. On teste ce que git fait, pas sa présence,
        # et on retombe sur l'archive au moindre échec. curl et tar, eux, sont
        # livrés avec macOS et n'ont besoin de rien.
        if git --version >/dev/null 2>&1 &&
           git clone --depth 1 "$DEPOT" "$CIBLE" 2>/dev/null; then
            ok "projet récupéré (git clone — les mises à jour se feront par git pull)"
        else
            rm -rf "$CIBLE"
            mkdir -p "$CIBLE"
            curl -fsSL "$DEPOT/archive/refs/heads/main.tar.gz" \
                | tar -xz -C "$CIBLE" --strip-components=1
            [ -f "$CIBLE/pyproject.toml" ] || stop "le téléchargement du projet a échoué. Vérifier la connexion internet."
            ok "projet récupéré (archive, sans git)"
        fi
    fi
    exec bash "$CIBLE/install.sh"
fi

cd "$ICI"

printf '\n%s%sInstallation de director-cut%s\n' "$GRAS" "$BLEU" "$RAZ"
info "Dossier : $(pwd)"
[ -n "$CLAVIER" ] || info "Mode non interactif : toute question sera considérée comme un non."

# ------------------------------------------------------------------ système --

titre "Système"

case "$(uname -s)" in
    Darwin) ok "macOS $(sw_vers -productVersion 2>/dev/null || echo '')" ;;
    Linux)  ok "Linux — prévu pour macOS, ça devrait marcher quand même" ;;
    *)      stop "ce script est prévu pour macOS. Sur Windows, suivre la section Installation du README." ;;
esac

# ------------------------------------------------- outils de base d'un Mac --
# Sur un Mac neuf, git et les compilateurs n'existent pas : la première commande
# qui les appelle ouvre une fenêtre d'installation. Autant la provoquer nous-mêmes
# et attendre qu'elle soit finie, plutôt que de planter au milieu.

if [ "$(uname -s)" = "Darwin" ]; then
    titre "Outils de développement Apple"
    if xcode-select -p >/dev/null 2>&1; then
        ok "déjà installés"
    else
        info "Ils sont fournis par Apple et nécessaires à la suite."
        info "Une fenêtre va s'ouvrir : cliquer « Installer » et accepter."
        xcode-select --install >/dev/null 2>&1 || true
        printf '  %sEn attente de la fin de l'\''installation' "$GRIS"
        while ! xcode-select -p >/dev/null 2>&1; do printf '.'; sleep 20; done
        printf '%s\n' "$RAZ"
        ok "installés"
    fi
fi

# ------------------------------------------------------------------ Homebrew --
# Nécessaire seulement s'il manque ffmpeg ou un Python récent : on ne l'installe
# donc qu'au moment où on en a vraiment besoin.

activer_brew_existant() {
    command -v brew >/dev/null 2>&1 && return 0
    local candidat
    for candidat in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        [ -x "$candidat" ] && { eval "$("$candidat" shellenv)"; return 0; }
    done
    return 1
}

installer_homebrew() {
    activer_brew_existant && return 0
    alerte "Homebrew est absent — c'est lui qui installe ffmpeg et Python."
    info "L'installation demandera le mot de passe de la session."
    if ! demander "Installer Homebrew maintenant ?"; then
        stop "sans Homebrew, il manquera ffmpeg et/ou Python 3.10+."
    fi
    NONINTERACTIVE=1 /bin/bash -c \
        "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    activer_brew_existant || stop "Homebrew s'est installé mais reste introuvable. Ferme le Terminal, rouvre-le, et relance ./install.sh"
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
# version utilisable avant d'en installer une.

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

info "Installation des bibliothèques (torch, pyannote, whisper…)."
info "Compter plusieurs minutes et ~2 Go la première fois."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install -e .
ok "installé"

# ------------------------------------------------------------- la commande --
# Pour que `director-cut` marche depuis n'importe quel dossier, sans avoir à
# activer quoi que ce soit. Le lanceur se replace toujours dans le projet :
# c'est là que vivent l'empreinte vocale, le token et le dossier sortie/.

titre "La commande director-cut"

BIN="$HOME/.local/bin"
mkdir -p "$BIN"
cat > "$BIN/director-cut" <<LANCEUR
#!/usr/bin/env bash
# Écrit par install.sh. Se replace dans le projet, où qu'on l'appelle.
cd "$(pwd)" || exit 1
exec "$(pwd)/.venv/bin/director-cut" "\$@"
LANCEUR
chmod +x "$BIN/director-cut"
ok "commande installée dans $BIN"

# Rendre ce dossier visible par le terminal, une fois pour toutes.
MARQUEUR="# >>> director-cut >>>"
PATH_A_AJOUTER=false
for fichier in "$HOME/.zshrc" "$HOME/.bash_profile"; do
    case "$fichier" in
        *.zshrc) [ "$(basename "${SHELL:-/bin/zsh}")" = "zsh" ] || continue ;;
        *)       [ -f "$fichier" ] || continue ;;
    esac
    if [ -f "$fichier" ] && grep -q "$MARQUEUR" "$fichier"; then
        continue
    fi
    {
        printf '\n%s\n' "$MARQUEUR"
        printf 'export PATH="$HOME/.local/bin:$PATH"\n'
        printf '%s\n' "# <<< director-cut <<<"
    } >> "$fichier"
    PATH_A_AJOUTER=true
    ok "$(basename "$fichier") mis à jour"
done

case ":$PATH:" in
    *":$BIN:"*) COMMANDE_PRETE=true ;;
    *)          COMMANDE_PRETE=false ;;
esac

# --------------------------------------------------------------- token HF --
# Les modèles de reconnaissance de voix sont sous conditions : compte Hugging
# Face, trois pages à accepter, un token de lecture. C'est l'étape qui échoue le
# plus souvent, donc on la vérifie vraiment au lieu de la supposer.

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
       Ouvrir https://huggingface.co/$modele et cliquer « Agree and access »."
            return 1
        fi
    done
    return 0
}

titre "Accès aux modèles de reconnaissance de voix"

TOKEN_OK=false
JETON=""
[ -f .hf_token ] && JETON=$(tr -d '[:space:]' < .hf_token)

if [ -n "$JETON" ] && verifier_token "$JETON"; then
    ok "token déjà en place, et les 3 modèles sont accessibles"
    TOKEN_OK=true
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
    if [ -n "$CLAVIER" ] && command -v open >/dev/null 2>&1; then
        if demander "Ouvrir ces pages dans le navigateur ?"; then
            for modele in "${MODELES_HF[@]}"; do open "https://huggingface.co/$modele"; done
            open "https://huggingface.co/settings/tokens"
        fi
    fi
    while [ -n "$CLAVIER" ]; do
        printf '\n  Coller le token ici (commence par hf_), ou Entrée pour le faire plus tard : '
        read -r JETON < "$CLAVIER" || JETON=""
        JETON=$(printf '%s' "$JETON" | tr -d '[:space:]')
        [ -z "$JETON" ] && break
        if verifier_token "$JETON"; then
            printf '%s\n' "$JETON" > .hf_token
            chmod 600 .hf_token
            ok "token enregistré et vérifié sur les 3 modèles"
            TOKEN_OK=true
            break
        fi
        alerte "$RAISON"
    done
fi

# ------------------------------------------------------------ voix de départ --

titre "Extrait de voix"

VOIX_OK=false
if [ -d samples ] && [ -n "$(find samples -maxdepth 1 -type f \( -iname '*.mp4' -o -iname '*.wav' -o -iname '*.m4a' -o -iname '*.mp3' -o -iname '*.mkv' -o -iname '*.mov' \) 2>/dev/null | head -1)" ]; then
    ok "dossier samples/ trouvé"
    VOIX_OK=true
elif compgen -G "sample*" >/dev/null 2>&1; then
    ok "extrait $(compgen -G 'sample*' | head -1) trouvé"
    VOIX_OK=true
elif [ -f voix_ref.npz ]; then
    ok "empreinte vocale déjà fabriquée"
    VOIX_OK=true
else
    alerte "Aucun extrait de voix dans ce dossier."
    info "Déposer ici un fichier nommé sample.mp4 : un passage où on entend"
    info "beaucoup la voix à reconnaître (une chronique entière est idéale)."
    info "Peu importe qu'il y ait d'autres voix, l'outil repère la dominante."
    info "L'empreinte sera fabriquée toute seule au premier lancement."
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
    if demander "Les télécharger maintenant ?"; then
        .venv/bin/director-cut models
    else
        info "Plus tard :  director-cut models"
    fi
fi

# ---------------------------------------------------------------- vérification --

titre "Vérification"

.venv/bin/director-cut --help >/dev/null || stop "director-cut ne répond pas. Relance ./install.sh"
ok "director-cut répond"
ffmpeg -version >/dev/null 2>&1 && ok "ffmpeg répond"
[ "$TOKEN_OK" = true ] && ok "accès aux modèles de voix vérifié"

# ------------------------------------------------------------------- la fin --

if [ "$TOKEN_OK" = true ] && [ "$VOIX_OK" = true ]; then
    printf '\n%s%sTout est prêt.%s\n' "$GRAS" "$VERT" "$RAZ"
else
    printf '\n%s%sPresque prêt.%s\n' "$GRAS" "$ROUGE" "$RAZ"
    [ "$TOKEN_OK" = true ] || printf '  Il manque le token Hugging Face (relancer ./install.sh une fois créé).\n'
    [ "$VOIX_OK" = true ]  || printf '  Il manque un extrait de voix (sample.mp4) dans %s.\n' "$(pwd)"
fi

printf '\n'
if [ "$COMMANDE_PRETE" = false ] || [ "$PATH_A_AJOUTER" = true ]; then
    printf '  %sOuvrir une nouvelle fenêtre Terminal%s, puis taper :\n\n' "$GRAS" "$RAZ"
else
    printf '  Pour découper une vidéo, depuis n'\''importe où :\n\n'
fi
printf '      %sdirector-cut run "COLLER_L_ADRESSE_DU_REPLAY" --mode reportage%s\n\n' "$BLEU" "$RAZ"
printf '  Modes : %s--mode reportage%s (sujet en voix off), %s--mode chronique%s (plateau),\n' "$BLEU" "$RAZ" "$BLEU" "$RAZ"
printf '  %s--mode jt%s (toute l'\''édition).\n' "$BLEU" "$RAZ"
printf '  Les résultats sortent dans %s%s/sortie/%s.\n' "$BLEU" "$(pwd)" "$RAZ"
printf '  Le premier lancement télécharge encore ~2 Go de modèles, une seule fois.\n\n'
