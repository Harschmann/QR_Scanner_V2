"""
network_storage.py - Save images to NAS (SMB) with local fallback.
"""
import os
import shutil
import sys
import socket
from config_loader import cfg


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _local_fallback_dir():
    path = os.path.join(_base_dir(), cfg.LOCAL_FALLBACK_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def _nas_reachable(timeout: float = 2.0) -> bool:
    """
    Fast check: try TCP connect to NAS on SMB port 445.
    Avoids the long Windows network-path timeout (can be 20-30s).
    """
    ip = cfg.PRODUCTION_IP
    for port in (445, 139):
        try:
            sock = socket.create_connection((ip, port), timeout=timeout)
            sock.close()
            return True
        except Exception:
            continue
    return False


def save_image(src_path: str, filename: str) -> tuple:
    """
    Try NAS first (with fast pre-check), fall back to local.
    Returns (saved_path, "NAS" | "LOCAL").
    """
    remote_dir = cfg.REMOTE_SAVE_DIR
    try:
        # Fast TCP pre-check before touching the network path
        if not _nas_reachable():
            raise OSError(f"NAS not reachable: {cfg.PRODUCTION_IP}")
        if not os.path.isdir(remote_dir):
            raise OSError(f"NAS path missing: {remote_dir}")
        dest = os.path.join(remote_dir, filename)
        shutil.copy2(src_path, dest)
        return dest, "NAS"
    except Exception:
        local_dir = _local_fallback_dir()
        dest = os.path.join(local_dir, filename)
        shutil.copy2(src_path, dest)
        return dest, "LOCAL"
