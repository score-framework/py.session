from sqlalchemy import Column, String, exists
from ._init import Session
from itertools import chain
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.types import TypeDecorator, VARCHAR
import json


class JSONDict(TypeDecorator):
    "Represents an immutable structure as a json-encoded string."

    impl = VARCHAR

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value


class DbSessionMixin:
    _uuid = Column(String(36), nullable=False, unique=True)
    _data = Column(JSONDict, nullable=False)


class DbSession(Session):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__db_object = None

    def _id_is_valid(self, id):
        return self._db.query(exists().where(self._db_class._uuid == id)).\
            scalar()

    @property
    def _db_object(self):
        if self.__db_object is None:
            if self._original_id:
                self.__db_object = self._db.query(self._db_class).\
                    filter(self._db_class._uuid == self._original_id).\
                    first()
            else:
                self.__db_object = self._db_class(
                    _data=dict()
                )
        return self.__db_object

    def _store(self):
        self._db_object._uuid = self.id
        self._db.add(self._db_object)
        flag_modified(self._db_object, '_data')

    def _revert(self):
        # will be handled by transaction rollback
        pass

    def _set(self, key, value):
        if hasattr(self._db_object, key):
            setattr(self._db_object, key, value)
        else:
            self._db_object._data[key] = value

    def _del(self, key):
        if hasattr(self._db_object, key):
            setattr(self._db_object, key, None)
        else:
            del(self._db_object._data[key])

    def _contains(self, key):
        return hasattr(self._db_object, key) or key in self._db_object._data

    def _get(self, key):
        if hasattr(self._db_object, key):
            return getattr(self._db_object, key)
        return self._db_object._data[key]

    def _iter(self):
        return chain((col.name
                      for col in self._db_class.__table__.columns
                      if col.name not in ('_uuid', '_data')),
                     iter(self._db_object._data))
