"""Persistencia en memoria compartida: reglas y rollback, sin red ni MongoDB."""
import re
import sys
import threading
import types
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

from bson import ObjectId
from bson.decimal128 import Decimal128
from pymongo.errors import DuplicateKeyError


def values_at(document, path):
    current = [document]
    for part in path.split("."):
        found = []
        for item in current:
            if isinstance(item, list):
                found.extend(child.get(part) for child in item if isinstance(child, dict) and part in child)
            elif isinstance(item, dict) and part in item:
                found.append(item[part])
        current = found
    return current


def comparable(value):
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return value


def matches(document, query):
    for key, expected in query.items():
        if key in ("$and", "$or"):
            results = [matches(document, child) for child in expected]
            if not (all(results) if key == "$and" else any(results)):
                return False
            continue
        actuals = values_at(document, key)
        if isinstance(expected, dict):
            for operation, value in expected.items():
                if operation == "$ne":
                    valid = all(actual != value for actual in actuals)
                elif operation == "$exists":
                    valid = bool(actuals) == value
                elif operation == "$type":
                    valid = any(isinstance(actual, str) for actual in actuals) if value == "string" else False
                elif operation == "$options":
                    continue
                elif operation == "$regex":
                    valid = any(re.search(value, str(actual or ""), re.I) for actual in actuals)
                elif operation == "$in":
                    valid = any(actual in value for actual in actuals)
                elif operation == "$gte":
                    valid = any(actual is not None and comparable(actual) >= comparable(value) for actual in actuals)
                elif operation == "$gt":
                    valid = any(actual is not None and comparable(actual) > comparable(value) for actual in actuals)
                elif operation == "$lte":
                    valid = any(actual is not None and comparable(actual) <= comparable(value) for actual in actuals)
                elif operation == "$lt":
                    valid = any(actual is not None and comparable(actual) < comparable(value) for actual in actuals)
                else:
                    raise AssertionError("Operador de prueba no implementado: " + operation)
                if not valid:
                    return False
        elif not any(actual == expected for actual in actuals) and not (expected is None and not actuals):
            return False
    return True


def evaluate(expression, document):
    if isinstance(expression, str) and expression.startswith("$"):
        values = values_at(document, expression[1:])
        return comparable(values[0]) if values else None
    if isinstance(expression, dict):
        if "$eq" in expression:
            args = expression["$eq"]
            return evaluate(args[0], document) == evaluate(args[1], document)
        if "$and" in expression:
            return all(evaluate(arg, document) for arg in expression["$and"])
        if "$cond" in expression:
            args = expression["$cond"]
            return evaluate(args[1] if evaluate(args[0], document) else args[2], document)
        return {key: evaluate(value, document) for key, value in expression.items()}
    return expression


class MemoryCursor(list):
    def sort(self, fields):
        for field, direction in reversed(fields):
            super().sort(key=lambda row: (row.get(field) is not None, comparable(row.get(field))), reverse=direction == -1)
        return self

    def skip(self, amount):
        return MemoryCursor(self[amount:])

    def limit(self, amount):
        return MemoryCursor(self[:amount])


class Collection:
    def __init__(self, name="test"):
        self.full_name = "almacen." + name
        self.documents, self.indexes = [], []

    def create_index(self, keys, **options):
        if not any(item[1].get("name") == options.get("name") for item in self.indexes):
            self.indexes.append((keys, options))

    def _unique(self, document, skip=None):
        for keys, options in self.indexes:
            partial = options.get("partialFilterExpression", {})
            if options.get("unique") and matches(document, partial):
                for other in self.documents:
                    if other is skip:
                        continue
                    if matches(other, partial) and all(other.get(k) == document.get(k) for k, _ in keys):
                        raise DuplicateKeyError("Duplicado en la prueba")
        if any(other is not skip and other["_id"] == document["_id"] for other in self.documents):
            raise DuplicateKeyError("ID duplicado en la prueba")

    def find(self, query, projection=None, **kwargs):
        return MemoryCursor(deepcopy([doc for doc in self.documents if matches(doc, query)]))

    def find_one(self, query, projection=None, sort=None, **kwargs):
        rows = self.find(query)
        return next(iter(rows.sort(sort) if sort else rows), None)

    def count_documents(self, query, **kwargs):
        return len(self.find(query))

    def insert_one(self, document, **kwargs):
        document.setdefault("_id", ObjectId())
        self._unique(document)
        self.documents.append(deepcopy(document))
        return types.SimpleNamespace(inserted_id=document["_id"])

    def _update(self, document, update):
        def parent_and_key(path):
            parts = path.split(".")
            parent = document
            for part in parts[:-1]:
                parent = parent.setdefault(part, {})
            return parent, parts[-1]

        for key, value in update.get("$set", {}).items():
            parent, final_key = parent_and_key(key)
            parent[final_key] = deepcopy(value)
        for key, value in update.get("$inc", {}).items():
            parent, final_key = parent_and_key(key)
            parent[final_key] = parent.get(final_key, 0) + value
        for key, value in update.get("$push", {}).items():
            parent, final_key = parent_and_key(key)
            parent.setdefault(final_key, []).append(deepcopy(value))

    def find_one_and_update(self, query, update, upsert=False, **kwargs):
        for document in self.documents:
            if matches(document, query):
                changed = deepcopy(document)
                self._update(changed, update)
                self._unique(changed, document)
                document.update(changed)
                return deepcopy(document)
        if upsert:
            document = deepcopy(query)
            document.update(deepcopy(update.get("$setOnInsert", {})))
            self._update(document, update)
            self.insert_one(document)
            return deepcopy(document)
        return None

    def update_one(self, query, update, **kwargs):
        result = self.find_one_and_update(query, update, **kwargs)
        return types.SimpleNamespace(matched_count=int(result is not None), modified_count=int(result is not None))

    def find_one_and_delete(self, query, **kwargs):
        for doc in self.documents:
            if matches(doc, query):
                self.documents.remove(doc)
                return deepcopy(doc)
        return None

    def delete_one(self, query, **kwargs):
        deleted = self.find_one_and_delete(query, **kwargs)
        return types.SimpleNamespace(deleted_count=int(deleted is not None))

    def aggregate(self, pipeline, **kwargs):
        rows = self.find(pipeline[0]["$match"])
        group = pipeline[1]["$group"]
        groups = {}
        for row in rows:
            value = evaluate(group["_id"], row)
            key = repr(value)
            result = groups.setdefault(key, {"_id": value})
            for field, expression in group.items():
                if field != "_id":
                    result[field] = result.get(field, Decimal(0)) + Decimal(evaluate(expression["$sum"], row))
        return [{key: Decimal128(value) if isinstance(value, Decimal) else value
                 for key, value in group.items()} for group in groups.values()]


class MemoryClient:
    def __init__(self, collections):
        self.collections = collections
        self.lock = threading.RLock()
        self.transactions = 0

    def start_session(self):
        return MemorySession(self)


class MemorySession:
    def __init__(self, client):
        self.client = client

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def with_transaction(self, callback, **kwargs):
        with self.client.lock:
            self.client.transactions += 1
            snapshots = [deepcopy(collection.documents) for collection in self.client.collections]
            try:
                return callback(self)
            except BaseException:
                for collection, snapshot in zip(self.client.collections, snapshots):
                    collection.documents = snapshot
                raise


class MemoryDatabase:
    def __init__(self):
        names = {"authDb": "auth", "sellersDb": "salenMan", "providersDb": "providers", "expensesDb": "expenses",
                 "salesDb": "sales", "productsDb": "products", "cashRegistersDb": "cash_registers",
                 "cashJournalsDb": "cash_journals", "cashMovementsDb": "cash_movements",
                 "auth_liquorDb": "auth_liquor", "products_liquorDb": "products_liquor",
                 "sales_liquorDb": "sales_liquor", "providers_liquorDb": "providers_liquor",
                 "expenses_liquorDb": "expenses_liquor"}
        for attr, name in names.items():
            setattr(self, attr, Collection(name))
        self.client = MemoryClient([getattr(self, attr) for attr in names])


# Antes de importar la aplicación: no se ejecuta el ping ni la configuración real.
if "app.db.mongo" not in sys.modules:
    stub = types.ModuleType("app.db.mongo")
    stub.__dict__.update(MemoryDatabase().__dict__)
    sys.modules["app.db.mongo"] = stub


def database_patches(database):
    from unittest.mock import patch
    from app.services import cash_service, expenses_service, sales_service
    patches = []
    for module in (cash_service, expenses_service, sales_service):
        for attr, value in database.__dict__.items():
            if hasattr(module, attr):
                patches.append(patch.object(module, attr, value))
    return patches
