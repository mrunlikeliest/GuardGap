"""Create local configuration once. Never overwrites credentials."""
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hashlib
def password_hash(password):
    salt=secrets.token_hex(16)
    value=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return f"scrypt:{salt}:{value}"
p=Path('.env')
if p.exists():
    raise SystemExit('.env already exists; preserving current configuration.')
password=secrets.token_urlsafe(20)
p.write_text('GUARDGAP_ADMIN_PASSWORD_HASH='+password_hash(password)+'\nGUARDGAP_SECURE_COOKIE=false\nGUARDGAP_DEMO=true\n')
p.chmod(0o600)
print('Created local .env. Store this password now; it is shown only once:\n'+password)
print('Start with: docker compose up --build\nThen open http://localhost:8000')
