"""Generic lock scopes; consumers supply namespace and identity semantics."""

from .database import Database


class LockScope:
    def __init__(self, database: Database, namespace: str, identity: str):
        self.database = database
        self.key = database.lock_key(namespace, identity)
        self.mutation_key = database.lock_key(namespace + ":mutation", identity)

    def gate(self, connection) -> None:
        self.database.transaction_lock(connection, self.key, shared=True)

    def serialize(self, connection) -> None:
        self.database.transaction_lock(connection, self.mutation_key)

    def try_exclusive(self, connection) -> bool:
        return self.database.try_lock(connection, self.key)

    def release_exclusive(self, connection) -> None:
        self.database.unlock(connection, self.key)
