
from qfluentwidgets import ScrollArea
from PySide6.QtWidgets import QApplication
import inspect

app = QApplication([])
s = ScrollArea()

try:
    delegate = s.scrollDelegate
    print("Found scrollDelegate")
    print(dir(delegate))
except AttributeError:
    print("No scrollDelegate, trying scrollDelagate")
    try:
        delegate = s.scrollDelagate
        print("Found scrollDelagate")
        print(dir(delegate))
    except:
        print("No delegate found")

