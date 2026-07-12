# Maintainer: Project Syntropia Team <hello@project-syntropia.io>
pkgname=syntropia
pkgver=0.1.0
pkgrel=1
pkgdesc="A performance-tuned AI container overlay daemon for CachyOS"
arch=('any')
url="https://github.com/your-username/Project-Syntropia"
license=('MIT')
depends=('python' 'python-psutil' 'python-pydantic' 'python-cryptography' 'python-toml')
makedepends=('python-setuptools' 'python-build' 'python-installer' 'python-wheel')
source=("git+https://github.com/your-username/Project-Syntropia.git")
sha256sums=('SKIP')

package() {
  cd "$srcdir/Project-Syntropia"
  
  # Build and install the Python wheel (registers entry points in /usr/bin)
  python -m build --wheel --no-isolation
  python -m installer --destdir="$pkgdir" dist/*.whl

  # Deploy codebase to /opt/syntropia as expected by systemd services
  install -d -m755 "$pkgdir/opt/syntropia/src"
  cp -r src/* "$pkgdir/opt/syntropia/src/"
  install -d -m755 "$pkgdir/opt/syntropia/agents"
  cp -r agents/* "$pkgdir/opt/syntropia/agents/"

  # Install systemd services
  install -Dm644 systemd/syntropia.service "$pkgdir/usr/lib/systemd/system/syntropia.service"
  install -Dm644 systemd/syntropia-reaper.service "$pkgdir/usr/lib/systemd/system/syntropia-reaper.service"
  
  # Install default configuration
  install -Dm644 config.toml.example "$pkgdir/etc/syntropia/config.toml"
  
  # Create log and state directories
  install -d -m755 "$pkgdir/var/lib/syntropia"
  install -d -m755 "$pkgdir/var/log/syntropia"
}
