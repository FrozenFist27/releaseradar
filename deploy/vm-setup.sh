set -e
sudo fallocate -l 1G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=1024
sudo chmod 600 /swapfile
sudo /sbin/mkswap /swapfile >/dev/null
sudo /sbin/swapon /swapfile
grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv >/dev/null
id radar >/dev/null 2>&1 || sudo useradd --system --home /opt/releaseradar --shell /usr/sbin/nologin radar
sudo mkdir -p /opt/releaseradar
sudo tar xzf /tmp/radar-src.tgz -C /opt/releaseradar
sudo python3 -m venv /opt/releaseradar/.venv
sudo /opt/releaseradar/.venv/bin/pip install --quiet --upgrade pip
sudo /opt/releaseradar/.venv/bin/pip install --quiet /opt/releaseradar
sudo mkdir -p /opt/releaseradar/data/logs
sudo chown -R radar:radar /opt/releaseradar
free -m | head -3
/opt/releaseradar/.venv/bin/radar --help | head -3
