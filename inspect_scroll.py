
from qfluentwidgets import ScrollArea
import inspect

print("Methods of ScrollArea:")
# List all methods that look like they might control scrolling
for name, _ in inspect.getmembers(ScrollArea):
    if 'scroll' in name.lower() or 'animation' in name.lower() or 'smooth' in name.lower():
        print(name)

print("\nAttributes of an instance:")
app = None
try:
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    s = ScrollArea()
    for name in dir(s):
         if 'scroll' in name.lower() or 'animation' in name.lower() or 'delegate' in name.lower():
             print(name)
except:
    pass
