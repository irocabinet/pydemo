#!/usr/bin/env sh
# Descarcă toate resursele frontend (jQuery, Bootstrap, AdminLTE, Font Awesome)
# în static/vendor/ pentru funcționare OFFLINE (fără internet).
# Rulează la build Docker sau manual: ./scripts/download_vendor_assets.sh

set -e
cd "$(dirname "$0")/.."
VENDOR="static/vendor"
mkdir -p "$VENDOR"/{jquery,bootstrap/css,bootstrap/js,adminlte/css,adminlte/js,fontawesome/css,fontawesome/webfonts}

echo "Downloading jQuery..."
curl -sL -o "$VENDOR/jquery/jquery.min.js" \
  "https://code.jquery.com/jquery-3.7.1.min.js"

echo "Downloading Bootstrap CSS..."
curl -sL -o "$VENDOR/bootstrap/css/bootstrap.min.css" \
  "https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css"

echo "Downloading Bootstrap JS..."
curl -sL -o "$VENDOR/bootstrap/js/bootstrap.bundle.min.js" \
  "https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/js/bootstrap.bundle.min.js"

echo "Downloading AdminLTE CSS..."
curl -sL -o "$VENDOR/adminlte/css/adminlte.min.css" \
  "https://cdn.jsdelivr.net/npm/admin-lte@3.2/dist/css/adminlte.min.css"

echo "Downloading AdminLTE JS..."
curl -sL -o "$VENDOR/adminlte/js/adminlte.min.js" \
  "https://cdn.jsdelivr.net/npm/admin-lte@3.2/dist/js/adminlte.min.js"

echo "Downloading Font Awesome CSS..."
curl -sL -o "$VENDOR/fontawesome/css/all.min.css" \
  "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"

# Font Awesome webfonts (all.min.css referă ../webfonts/)
for f in fa-solid-900 fa-regular-400 fa-brands-400; do
  echo "Downloading Font Awesome webfont: $f..."
  curl -sL -o "$VENDOR/fontawesome/webfonts/$f.woff2" \
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/$f.woff2" || true
done
# Ajustează calea în CSS: ../webfonts/ -> webfonts/ (sau folosim path relativ din fontawesome/css)
# all.min.css conține url(../webfonts/...) deci din fontawesome/css/ parent e fontawesome/ deci ../webfonts e corect
# Avem fontawesome/css/all.min.css și fontawesome/webfonts/ -> din css, ../webfonts/ e corect. OK.

echo "Done. Vendor assets in $VENDOR"
