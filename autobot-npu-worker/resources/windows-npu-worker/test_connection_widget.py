"""Test Connection Info Widget in isolation"""
import sys
from PySide6.QtWidgets import QApplication
from gui.widgets.connection_info import ConnectionInfoWidget


def main():
    app = QApplication(sys.argv)

    print("Creating Connection Info Widget...")
    try:
        widget = ConnectionInfoWidget(worker_id="test-worker-001", port=8082)
        widget.setWindowTitle("Connection Info Test")
        widget.show()
        print("Widget created and shown successfully!")
        print("Click around to test - errors will appear in this console")
        sys.exit(app.exec())
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    main()
