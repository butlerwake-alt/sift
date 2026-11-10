#!/usr/bin/env bash
# Rebuild SIFT data.js from the paper-test records, check it, and push to GitHub Pages if it changed.
set -euo pipefail
cd "$(dirname "$0")"
python3 build_data.py
node -e "const fs=require('fs');eval(fs.readFileSync('data.js','utf8')+';if(!SIFT||!Array.isArray(SIFT.strategies)||SIFT.strategies.length<1)throw new Error(\"bad SIFT\");for(const s of SIFT.strategies){if(!s.planned&&!(s.points&&s.points.length))throw new Error(\"no points for \"+s.n)}console.log(\"data.js OK:\",SIFT.strategies.length,\"strategies, asOf\",SIFT.asOf)')"
git add -A
if git diff --cached --quiet -- data.js history.json app.js styles.css strategy.html build_data.py template.json README.md publish.sh .gitignore; then
  git reset -q
  echo "No data changes; nothing pushed."
  exit 0
fi
v="$(date +%Y%m%d%H%M)"
sed -i -E "s/\?v=[0-9a-z]+/?v=${v}/g" index.html strategy.html
git add -A
git commit -q -m "Paper results update $(date '+%Y-%m-%d %H:%M %Z')"
git push -q origin main
echo "Pushed $(git rev-parse --short HEAD)"
