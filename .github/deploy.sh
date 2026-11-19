#!/usr/bin/env bash
set -euo pipefail

release=$1
cd ~/vibetalk
test "$(git branch --show-current)" = main
git fetch origin main
if [[ $(git rev-parse FETCH_HEAD) != "$release" ]]; then
    echo "A newer push superseded this release."
    exit 0
fi
git merge-base --is-ancestor HEAD "$release"
git diff --cached --quiet
git diff --quiet -- . ':(exclude)requirements.txt' ':(exclude)website/static/admin/**'
# collectstatic refreshes these tracked copies from the installed Django package.
# Leave them in place. An unrelated local edit still blocks deployment.
admin_prefix=website/static/admin/
if ! git diff --quiet -- "$admin_prefix"; then
    admin_source=$(venv/bin/python -c 'from pathlib import Path; import django; print(Path(django.__file__).parent / "contrib/admin/static/admin")')
    while IFS= read -r -d '' path; do
        if ! cmp -s -- "$path" "$admin_source/${path#"$admin_prefix"}"; then
            echo "Unexpected local change: $path" >&2
            exit 1
        fi
    done < <(git diff --name-only -z -- "$admin_prefix")
fi
if ! git diff --quiet -- requirements.txt; then
    # Adopt the VPS dependency snapshot only if the reviewed release contains it verbatim.
    git diff --quiet "$release" -- requirements.txt
    git add -- requirements.txt
fi
git merge --ff-only "$release"

python=venv/bin/python
"$python" -m pip install -r requirements.txt
"$python" -m pip check
"$python" manage.py check --deploy
"$python" manage.py migrate --noinput
"$python" manage.py collectstatic --noinput
sudo -n /usr/bin/systemctl restart vibetalk-daphne.service

for attempt in {1..15}; do
    if systemctl is-active --quiet vibetalk-daphne.service &&
        [[ $(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' \
            -H 'Host: vibetalk.online' -H 'X-Forwarded-Proto: https' \
            http://127.0.0.1:8001/login/) == 200 ]]; then
        exit 0
    fi
    sleep 1
done
echo "Daphne failed the /login/ readiness check." >&2
exit 1
