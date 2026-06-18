"""
app.py - QR Scanner V3
Basler camera, live feed, QR decode, NAS save, dark UI.
"""
import sys
import os
import cv2
import tempfile
import zxingcpp
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QHBoxLayout, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QStatusBar, QFrame, QSizePolicy,
    QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
from PyQt5.QtGui  import QImage, QPixmap, QFont, QColor, QPalette

from config_loader  import cfg
from db             import init_db, insert_scan, get_recent
from network_storage import save_image

# --------------------------------------------------------------------------- #
# Basler import (optional — app still launches if pypylon not installed)       #
# --------------------------------------------------------------------------- #
try:
    from pypylon import pylon
    PYLON_AVAILABLE = True
except ImportError:
    PYLON_AVAILABLE = False

# --------------------------------------------------------------------------- #
# Palette                                                                       #
# --------------------------------------------------------------------------- #
C_BG        = "#0D0D0D"
C_SURFACE   = "#161616"
C_PANEL     = "#1E1E1E"
C_BORDER    = "#2A2A2A"
C_ACCENT    = "#00C8FF"
C_ACCENT2   = "#005F78"
C_TEXT      = "#E8E8E8"
C_MUTED     = "#707070"
C_SUCCESS   = "#00E676"
C_WARN      = "#FFB300"
C_ERROR     = "#FF4444"

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {C_BG};
    color: {C_TEXT};
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}}
QFrame#sidebar {{
    background-color: {C_SURFACE};
    border-right: 1px solid {C_BORDER};
}}
QLabel#logo {{
    font-size: 20px;
    font-weight: 700;
    color: {C_ACCENT};
    letter-spacing: 2px;
    padding: 18px 0 4px 0;
}}
QLabel#sublabel {{
    font-size: 11px;
    color: {C_MUTED};
    padding-bottom: 18px;
}}
QPushButton.action {{
    background-color: {C_ACCENT};
    color: #000000;
    font-weight: 700;
    font-size: 13px;
    border: none;
    border-radius: 6px;
    padding: 10px 0;
    margin: 4px 0;
}}
QPushButton.action:hover {{
    background-color: #33D4FF;
}}
QPushButton.action:disabled {{
    background-color: {C_ACCENT2};
    color: {C_MUTED};
}}
QPushButton.secondary {{
    background-color: {C_PANEL};
    color: {C_TEXT};
    font-size: 13px;
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 8px 0;
    margin: 4px 0;
}}
QPushButton.secondary:hover {{
    background-color: {C_BORDER};
}}
QLabel#feed {{
    background-color: #050505;
    border: 1px solid {C_BORDER};
    border-radius: 4px;
}}
QLabel#status_badge {{
    font-size: 12px;
    font-weight: 600;
    padding: 4px 12px;
    border-radius: 4px;
}}
QTableWidget {{
    background-color: {C_SURFACE};
    border: 1px solid {C_BORDER};
    gridline-color: {C_BORDER};
    border-radius: 4px;
    font-size: 12px;
    selection-background-color: {C_ACCENT2};
}}
QTableWidget::item {{
    padding: 6px 8px;
    color: {C_TEXT};
}}
QHeaderView::section {{
    background-color: {C_PANEL};
    color: {C_MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid {C_BORDER};
}}
QStatusBar {{
    background-color: {C_SURFACE};
    color: {C_MUTED};
    font-size: 11px;
    border-top: 1px solid {C_BORDER};
}}
QSplitter::handle {{
    background-color: {C_BORDER};
    width: 1px;
}}
QLabel#section_title {{
    font-size: 11px;
    font-weight: 700;
    color: {C_MUTED};
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 8px 0 4px 0;
}}
"""

# --------------------------------------------------------------------------- #
# Camera worker thread                                                          #
# --------------------------------------------------------------------------- #
class CameraWorker(QThread):
    frame_ready   = pyqtSignal(object)   # numpy array
    camera_error  = pyqtSignal(str)
    camera_opened = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._running  = False
        self._camera   = None
        self._use_pylon = False

    def start_camera(self):
        self._running = True
        self.start()

    def stop_camera(self):
        self._running = False
        self.wait(2000)

    def run(self):
        # Try Basler first
        if PYLON_AVAILABLE:
            try:
                self._camera = pylon.InstantCamera(
                    pylon.TlFactory.GetInstance().CreateFirstDevice()
                )
                self._camera.Open()
                self._camera.ExposureTime.SetValue(cfg.CAMERA_EXPOSURE_US)
                self._camera.AcquisitionFrameRateEnable.SetValue(True)
                self._camera.AcquisitionFrameRate.SetValue(float(cfg.CAMERA_FPS))
                self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
                self._use_pylon = True
                self.camera_opened.emit()
                converter = pylon.ImageFormatConverter()
                converter.OutputPixelFormat = pylon.PixelType_BGR8packed
                converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
                while self._running and self._camera.IsGrabbing():
                    result = self._camera.RetrieveResult(
                        2000, pylon.TimeoutHandling_ThrowException
                    )
                    if result.GrabSucceeded():
                        img = converter.Convert(result)
                        frame = img.GetArray()
                        self.frame_ready.emit(frame)
                    result.Release()
                self._camera.StopGrabbing()
                self._camera.Close()
                return
            except Exception as e:
                self._use_pylon = False
                # Fall through to USB

        # Fallback: USB webcam (index 0)
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            self.camera_error.emit("No camera found (Basler not available, USB failed).")
            return
        cap.set(cv2.CAP_PROP_FPS, cfg.CAMERA_FPS)
        self.camera_opened.emit()
        while self._running:
            ret, frame = cap.read()
            if ret:
                self.frame_ready.emit(frame)
        cap.release()


# --------------------------------------------------------------------------- #
# Main Window                                                                   #
# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QR Scanner V3")
        self.setMinimumSize(1100, 680)
        self.resize(1280, 780)
        self.setStyleSheet(STYLESHEET)

        self._worker        = None
        self._latest_frame  = None    # last frame from camera (for capture)
        self._frame_count   = 0

        init_db()
        self._build_ui()
        self._refresh_table()

    # ---------------------------------------------------------------------- #
    # UI construction                                                          #
    # ---------------------------------------------------------------------- #
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Sidebar ---- #
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(20, 0, 20, 20)
        sb_layout.setSpacing(2)

        logo = QLabel("QR SCAN")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignCenter)
        sub  = QLabel("Samsung SIEL — Inspection")
        sub.setObjectName("sublabel")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)

        sb_layout.addWidget(logo)
        sb_layout.addWidget(sub)

        # Status badge
        self._cam_badge = QLabel("CAMERA OFF")
        self._cam_badge.setObjectName("status_badge")
        self._cam_badge.setAlignment(Qt.AlignCenter)
        self._set_badge(self._cam_badge, "off")
        sb_layout.addWidget(self._cam_badge)
        sb_layout.addSpacing(12)

        # Buttons
        lbl_cam = QLabel("CAMERA")
        lbl_cam.setObjectName("section_title")
        sb_layout.addWidget(lbl_cam)

        self._btn_connect = QPushButton("Connect Camera")
        self._btn_connect.setProperty("class", "action")
        self._btn_connect.setFixedHeight(40)
        self._btn_connect.clicked.connect(self._on_connect)

        self._btn_stop = QPushButton("Disconnect")
        self._btn_stop.setProperty("class", "secondary")
        self._btn_stop.setFixedHeight(36)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_disconnect)

        sb_layout.addWidget(self._btn_connect)
        sb_layout.addWidget(self._btn_stop)
        sb_layout.addSpacing(12)

        lbl_scan = QLabel("CAPTURE")
        lbl_scan.setObjectName("section_title")
        sb_layout.addWidget(lbl_scan)

        self._btn_capture = QPushButton("📷  Capture & Scan")
        self._btn_capture.setProperty("class", "action")
        self._btn_capture.setFixedHeight(48)
        self._btn_capture.setEnabled(False)
        self._btn_capture.clicked.connect(self._on_capture)

        sb_layout.addWidget(self._btn_capture)

        hint = QLabel("Camera connect karo, phir Capture dabao.\nQR auto-detect hoga.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{C_MUTED}; font-size:10px; padding-top:2px;")
        sb_layout.addWidget(hint)
        sb_layout.addSpacing(12)

        lbl_save = QLabel("LAST SAVE")
        lbl_save.setObjectName("section_title")
        sb_layout.addWidget(lbl_save)

        self._lbl_dest = QLabel("—")
        self._lbl_dest.setWordWrap(True)
        self._lbl_dest.setStyleSheet(f"color:{C_MUTED}; font-size:11px;")
        sb_layout.addWidget(self._lbl_dest)

        sb_layout.addStretch()

        # NAS info
        lbl_nas = QLabel("NAS TARGET")
        lbl_nas.setObjectName("section_title")
        sb_layout.addWidget(lbl_nas)
        nas_val = QLabel(cfg.REMOTE_SAVE_DIR or cfg.PRODUCTION_IP)
        nas_val.setWordWrap(True)
        nas_val.setStyleSheet(f"color:{C_MUTED}; font-size:11px;")
        sb_layout.addWidget(nas_val)

        root.addWidget(sidebar)

        # ---- Main area ---- #
        main_area = QWidget()
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(16, 16, 16, 8)
        main_layout.setSpacing(12)

        splitter = QSplitter(Qt.Vertical)

        # Feed
        feed_container = QWidget()
        feed_layout = QVBoxLayout(feed_container)
        feed_layout.setContentsMargins(0, 0, 0, 0)
        feed_layout.setSpacing(6)

        feed_hdr = QHBoxLayout()
        lbl_feed_title = QLabel("LIVE FEED")
        lbl_feed_title.setObjectName("section_title")
        self._lbl_fps = QLabel("— fps")
        self._lbl_fps.setStyleSheet(f"color:{C_MUTED}; font-size:11px;")
        self._lbl_qr_live = QLabel("")
        self._lbl_qr_live.setStyleSheet(
            f"color:{C_ACCENT}; font-size:13px; font-weight:700;"
        )
        feed_hdr.addWidget(lbl_feed_title)
        feed_hdr.addSpacing(16)
        feed_hdr.addWidget(self._lbl_qr_live)
        feed_hdr.addStretch()
        feed_hdr.addWidget(self._lbl_fps)
        feed_layout.addLayout(feed_hdr)

        self._lbl_feed = QLabel("No camera connected")
        self._lbl_feed.setObjectName("feed")
        self._lbl_feed.setAlignment(Qt.AlignCenter)
        self._lbl_feed.setMinimumHeight(360)
        self._lbl_feed.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._lbl_feed.setStyleSheet(
            f"background-color:#050505; border:1px solid {C_BORDER};"
            f"border-radius:4px; color:{C_MUTED}; font-size:16px;"
        )
        feed_layout.addWidget(self._lbl_feed)
        splitter.addWidget(feed_container)

        # Scan history table
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(6)

        lbl_hist = QLabel("SCAN HISTORY")
        lbl_hist.setObjectName("section_title")
        table_layout.addWidget(lbl_hist)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["QR Code", "Filename", "Saved To", "Timestamp"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(False)
        table_layout.addWidget(self._table)
        splitter.addWidget(table_container)

        splitter.setSizes([480, 220])
        main_layout.addWidget(splitter)
        root.addWidget(main_area)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready  |  config: " + os.path.dirname(
            os.path.abspath(__file__)
            if not getattr(sys, "frozen", False)
            else sys.executable
        ))

        # FPS timer
        self._fps_timer = QTimer()
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start(1000)

    # ---------------------------------------------------------------------- #
    # Badge helper                                                             #
    # ---------------------------------------------------------------------- #
    def _set_badge(self, label: QLabel, state: str):
        styles = {
            "off":      (C_PANEL,   C_MUTED,    "CAMERA OFF"),
            "on":       (C_SUCCESS, "#000000",  "CAMERA ON"),
            "scanning": (C_ACCENT,  "#000000",  "SCANNING"),
            "error":    (C_ERROR,   "#ffffff",  "ERROR"),
        }
        bg, fg, text = styles.get(state, styles["off"])
        label.setText(text)
        label.setStyleSheet(
            f"background-color:{bg}; color:{fg}; font-size:12px;"
            f"font-weight:600; padding:4px 12px; border-radius:4px;"
        )

    # ---------------------------------------------------------------------- #
    # Camera connect / disconnect                                              #
    # ---------------------------------------------------------------------- #
    def _on_connect(self):
        self._btn_connect.setEnabled(False)
        self._btn_connect.setText("Connecting...")
        self._status.showMessage("Camera connect ho raha hai...")

        self._worker = CameraWorker()
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.camera_error.connect(self._on_camera_error)
        self._worker.camera_opened.connect(self._on_camera_opened)
        self._worker.start_camera()

    def _on_camera_opened(self):
        self._set_badge(self._cam_badge, "on")
        self._btn_connect.setText("Connected ✓")
        self._btn_stop.setEnabled(True)
        self._btn_capture.setEnabled(True)
        self._status.showMessage("Camera connected — Capture dabane ke liye ready")

    def _on_camera_error(self, msg: str):
        self._set_badge(self._cam_badge, "error")
        self._btn_connect.setEnabled(True)
        self._btn_connect.setText("Connect Camera")
        self._btn_capture.setEnabled(False)
        self._status.showMessage(f"Camera error: {msg}")
        QMessageBox.critical(self, "Camera Error", msg)

    def _on_disconnect(self):
        if self._worker:
            self._worker.stop_camera()
            self._worker = None
        self._latest_frame = None
        self._set_badge(self._cam_badge, "off")
        self._btn_connect.setEnabled(True)
        self._btn_connect.setText("Connect Camera")
        self._btn_stop.setEnabled(False)
        self._btn_capture.setEnabled(False)
        self._lbl_feed.setText("No camera connected")
        self._lbl_feed.setPixmap(QPixmap())
        self._lbl_qr_live.setText("")
        self._status.showMessage("Camera disconnected")

    # ---------------------------------------------------------------------- #
    # Frame processing — sirf store + display, decode NAHI                    #
    # ---------------------------------------------------------------------- #
    def _on_frame(self, frame):
        self._frame_count += 1
        self._latest_frame = frame          # capture ke liye store

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pix  = QPixmap.fromImage(qimg).scaled(
            self._lbl_feed.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self._lbl_feed.setPixmap(pix)

    # ---------------------------------------------------------------------- #
    # CAPTURE button — yahan QR detect hota hai                               #
    # ---------------------------------------------------------------------- #
    def _on_capture(self):
        if self._latest_frame is None:
            self._show_error("Koi frame nahi mila. Camera connect hai?")
            return

        frame = self._latest_frame.copy()    # freeze current frame

        # Decode QR codes
        codes = self._decode_qr(frame)

        if not codes:
            # QR nahi mila -> error dikhao, SAVE MAT KARO
            self._show_error("QR code detect nahi hua. Image save nahi hui.")
            self._lbl_qr_live.setText("")
            return

        # QR mila -> save karo
        joined = ", ".join(codes)
        self._lbl_qr_live.setText(f"QR: {joined}")
        self._lbl_qr_live.setStyleSheet(
            f"color:{C_SUCCESS}; font-size:13px; font-weight:700;"
        )
        self._save_scan(frame, codes)

    def _decode_qr(self, frame) -> list:
        """Returns list of unique QR strings found in frame."""
        try:
            results = zxingcpp.read_barcodes(frame)
        except Exception as e:
            self._status.showMessage(f"Decode error: {e}")
            return []

        codes = []
        for r in results:
            text = r.text.strip()
            if text and text not in codes:
                codes.append(text)
        return codes

    def _show_error(self, msg: str):
        self._lbl_qr_live.setText(f"✕ {msg}")
        self._lbl_qr_live.setStyleSheet(
            f"color:{C_ERROR}; font-size:13px; font-weight:700;"
        )
        self._status.showMessage(msg)

    # ---------------------------------------------------------------------- #
    # Save (QR mile tabhi call hota hai)                                      #
    # ---------------------------------------------------------------------- #
    def _save_scan(self, frame, qr_codes: list):
        ts       = datetime.now()
        ts_str   = ts.strftime("%Y%m%d_%H%M%S")

        # Filename: pehle QR code se, multiple ho to joined
        primary  = qr_codes[0]
        safe_qr  = "".join(c if c.isalnum() or c in "-_" else "_" for c in primary)[:50]
        if len(qr_codes) > 1:
            safe_qr += f"_+{len(qr_codes)-1}more"
        filename = f"{safe_qr}_{ts_str}.jpg"

        # Temp file
        tmp = tempfile.mktemp(suffix=".jpg")
        cv2.imwrite(tmp, frame, [cv2.IMWRITE_JPEG_QUALITY, cfg.JPEG_QUALITY])

        # NAS / fallback
        saved_path, location = save_image(tmp, filename)
        try:
            os.remove(tmp)
        except Exception:
            pass

        # DB — saare codes comma-separated store
        all_codes = " | ".join(qr_codes)
        insert_scan(all_codes, filename, saved_path, ts.isoformat())

        # UI feedback
        color = C_SUCCESS if location == "NAS" else C_WARN
        self._lbl_dest.setText(f"[{location}]\n{saved_path}")
        self._lbl_dest.setStyleSheet(f"color:{color}; font-size:11px;")
        self._status.showMessage(
            f"✓ Saved [{location}]: {filename}  |  {len(qr_codes)} QR  |  {ts.strftime('%H:%M:%S')}"
        )
        self._refresh_table()

    # ---------------------------------------------------------------------- #
    # History table                                                            #
    # ---------------------------------------------------------------------- #
    def _refresh_table(self):
        rows = get_recent(100)
        self._table.setRowCount(len(rows))
        for i, (qr, fn, dest, ts) in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(qr))
            self._table.setItem(i, 1, QTableWidgetItem(fn))
            dest_item = QTableWidgetItem(dest)
            if dest.startswith("\\\\") or dest.startswith("//"):
                dest_item.setForeground(QColor(C_SUCCESS))
            else:
                dest_item.setForeground(QColor(C_WARN))
            self._table.setItem(i, 2, dest_item)
            self._table.setItem(i, 3, QTableWidgetItem(ts))

    # ---------------------------------------------------------------------- #
    # FPS counter                                                              #
    # ---------------------------------------------------------------------- #
    def _update_fps(self):
        self._lbl_fps.setText(f"{self._frame_count} fps")
        self._frame_count = 0

    def closeEvent(self, event):
        if self._worker:
            self._worker.stop_camera()
        event.accept()


# --------------------------------------------------------------------------- #
# Entry                                                                         #
# --------------------------------------------------------------------------- #
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
