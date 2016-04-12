from sqlalchemy import Column, String, PickleType, exists
from sqlalchemy.ext.mutable import Mutable
from ._init import Session
from itertools import chain


class DbSessionMixin:
    _uuid = Column(String(36), nullable=False, unique=True)
    _data = Column(PickleType, nullable=False)


class MutableDict(Mutable, dict):

    @classmethod
    def coerce(cls, key, value):
        "Convert plain dictionaries to MutableDict."

        if not isinstance(value, MutableDict):
            if isinstance(value, dict):
                return MutableDict(value)

            # this call will raise ValueError
            return Mutable.coerce(key, value)
        else:
            return value

    def __setitem__(self, key, value):
        "Detect dictionary set events and emit change events."

        dict.__setitem__(self, key, value)
        self.changed()

    def __delitem__(self, key):
        "Detect dictionary del events and emit change events."

        dict.__delitem__(self, key)
        self.changed()


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
                    _data=MutableDict()
                )
        return self.__db_object

    def _store(self):
        self._db_object._uuid = self.id
        self._db.add(self._db_object)

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
        return self._db_object[key]

    def _iter(self):
        return chain((col.name
                      for col in self._db_class.__table__.columns
                      if col.name not in ('_uuid', '_data')),
                     iter(self._db_object._data))
