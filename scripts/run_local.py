"""Cross-platform local runner. Reads the bootstrap .env without shell sourcing."""
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
for line in Path('.env').read_text().splitlines():
    if line and not line.startswith('#'):
        key,value=line.split('=',1)
        os.environ.setdefault(key,value)
from guardgap.cli import main
sys.argv=['guardgap','serve',*sys.argv[1:]]
raise SystemExit(main())
