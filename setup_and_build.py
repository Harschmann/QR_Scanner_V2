"""
setup_and_build.py
------------------
Ek command se poora kaam:
    python setup_and_build.py

Kya karega:
1. pip se sab dependencies install karega
2. PyInstaller se EXE build karega (--onedir)
3. config.py aur qr_scan.db dist folder mein copy karega
4. captures_local_backup folder banega
"""

import subprocess
import sys
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist", "QRScanner")

DEPENDENCIES = [
    "pyinstaller",
    "opencv-python",
    "zxingcpp",
    "PyQt5",
    "pypylon",
]

SPEC_CONTENT = """
import sys, os
ROOT = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(ROOT, 'app.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        'zxingcpp',
        'pypylon',
        'cv2',
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'sqlite3',
        'importlib.util',
        'network_storage',
        'db',
        'config_loader',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QRScanner',
    debug=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='QRScanner',
)
"""

def run(cmd, desc):
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"\n[ERROR] Failed: {desc}")
        print("Aage continue kar raha hoon...")
    return result.returncode == 0


def main():
    print("\n" + "="*60)
    print("  QR Scanner V3 - Setup & Build")
    print("="*60)

    # Step 1: Install deps
    print("\n[1/4] Dependencies install ho rahi hain...")
    for dep in DEPENDENCIES:
        run(f'"{sys.executable}" -m pip install {dep} --quiet', f"Installing {dep}")

    # Step 2: Write spec file
    spec_path = os.path.join(ROOT, "QRScanner.spec")
    with open(spec_path, "w") as f:
        f.write(SPEC_CONTENT)
    print("\n[2/4] QRScanner.spec ready")

    # Step 3: Build
    print("\n[3/4] EXE build ho raha hai (2-5 min lagenge)...")
    ok = run(
        f'"{sys.executable}" -m PyInstaller QRScanner.spec --distpath dist --workpath build_work --noconfirm',
        "PyInstaller build"
    )
    if not ok:
        print("\n[ERROR] Build fail hua. Upar ke errors dekho.")
        input("\nEnter press karo exit ke liye...")
        sys.exit(1)

    # Step 4: Copy external files
    print("\n[4/4] External files copy ho rahi hain...")
    os.makedirs(DIST, exist_ok=True)

    # config.py
    cfg_src = os.path.join(ROOT, "config.py")
    cfg_dst = os.path.join(DIST, "config.py")
    if os.path.exists(cfg_src):
        shutil.copy2(cfg_src, cfg_dst)
        print(f"  config.py  -> {cfg_dst}")
    else:
        print("  config.py source nahi mila, default banega jab app chalega")

    # qr_scan.db
    db_src = os.path.join(ROOT, "qr_scan.db")
    db_dst = os.path.join(DIST, "qr_scan.db")
    if os.path.exists(db_src):
        shutil.copy2(db_src, db_dst)
        print(f"  qr_scan.db -> {db_dst}")
    else:
        print("  qr_scan.db nahi mila, app khud banayegi")

    # local_backup folder
    backup_dir = os.path.join(DIST, "captures_local_backup")
    os.makedirs(backup_dir, exist_ok=True)
    print(f"  captures_local_backup/ -> {backup_dir}")

    print("\n" + "="*60)
    print("  BUILD COMPLETE!")
    print("="*60)
    print(f"\n  Output folder:")
    print(f"  {DIST}")
    print(f"\n  Ye poora folder kisi bhi PC pe copy karo aur")
    print(f"  QRScanner.exe chalao. Koi install nahi chahiye.")
    print(f"\n  Config change karna ho toh:")
    print(f"  {os.path.join(DIST, 'config.py')} Notepad se edit karo")
    print("="*60)
    input("\nEnter press karo exit ke liye...")


if __name__ == "__main__":
    main()
