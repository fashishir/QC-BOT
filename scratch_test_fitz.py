import time
import subprocess
import os
import fitz

# Test fitz merge
doc = fitz.open()
print("PyMuPDF available, doc:", doc)
doc.close()
