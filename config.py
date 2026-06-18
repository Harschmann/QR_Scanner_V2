# =============================================================================
# QR Scanner - Configuration File
# Edit with Notepad, save, restart app. No rebuild needed.
# =============================================================================

# --- NAS / Network Storage ---
PRODUCTION_IP        = "192.168.1.100"       # NAS server IP
SHARE_NAME           = "QRCaptures"          # SMB share name
SUBFOLDER            = "scans"               # Subfolder inside share
REMOTE_SAVE_DIR      = "\\\\192.168.1.100\\QRCaptures\\scans"  # Full UNC path (auto-built from above if blank)

# --- Local Fallback (used when NAS is unreachable) ---
LOCAL_FALLBACK_DIR   = "captures_local_backup"

# --- Basler Camera Settings ---
CAMERA_EXPOSURE_US   = 10000                 # Exposure in microseconds
CAMERA_FPS           = 30                    # Frames per second

# --- Database ---
DB_PATH              = "qr_scan.db"          # Relative to EXE folder

# --- Image Quality ---
JPEG_QUALITY         = 90                    # 1-100
