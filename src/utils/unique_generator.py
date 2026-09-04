
"""Geradores centralizados de dados unicos do Populador ECOCIENTE."""
import hashlib
import secrets
import uuid

class CollisionManager:
    def __init__(self):
        self.values = {
            "cpf": set(),
            "email": set(),
            "hash_foto": set(),
            "token": set(),
            "idempotency_key": set(),
        }

    def unique(self, kind, generator):
        while True:
            value = generator()
            if value not in self.values[kind]:
                self.values[kind].add(value)
                return value

    def uuid(self):
        return str(uuid.uuid4())

collision_manager = CollisionManager()

def cpf_unico(fake):
    return collision_manager.unique(
        "cpf", lambda: "".join(c for c in fake.cpf() if c.isdigit())[:11].zfill(11)
    )

def email_unico(fake, nome):
    return collision_manager.unique("email", lambda: fake.email(nome))

def hash_foto_unico(payload):
    def gen():
        return hashlib.sha256(
            (payload + secrets.token_hex(16)).encode("utf-8")
        ).hexdigest()
    return collision_manager.unique("hash_foto", gen)

def token_unico():
    return collision_manager.unique("token", lambda: secrets.token_urlsafe(64))

def idempotency_key_unica():
    return collision_manager.unique("idempotency_key", lambda: str(uuid.uuid4()))
