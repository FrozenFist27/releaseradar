# Re-deploy new code to the VM without touching data/ or swap. Needs /tmp/radar-src.tgz.
set -e
sudo tar xzf /tmp/radar-src.tgz -C /opt/releaseradar
sudo /opt/releaseradar/.venv/bin/pip install --quiet --upgrade /opt/releaseradar
sudo chown -R radar:radar /opt/releaseradar
sudo cp /opt/releaseradar/deploy/radar-*.service /opt/releaseradar/deploy/radar-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
