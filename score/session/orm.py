# Copyright © 2015-2018 STRG.AT GmbH, Vienna, Austria
# Copyright © 2019 Necdet Can Ateşman <can@atesman.at>, Vienna, Austria
#
# This file is part of the The SCORE Framework.
#
# The SCORE Framework and all its parts are free software: you can redistribute
# them and/or modify them under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation which is in
# the file named COPYING.LESSER.txt.
#
# The SCORE Framework and all its parts are distributed without any WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. For more details see the GNU Lesser General Public
# License.
#
# If you have not received a copy of the GNU Lesser General Public License see
# http://www.gnu.org/licenses/.
#
# The License-Agreement realised between you as Licensee and STRG.AT GmbH as
# Licenser including the issue of its valid conclusion and its pre- and
# post-contractual effects is governed by the laws of Austria. Any disputes
# concerning this License-Agreement including the issue of its valid conclusion
# and its pre- and post-contractual effects are exclusively decided by the
# competent court, in whose district STRG.AT GmbH has its registered seat, at
# the discretion of STRG.AT GmbH also the competent court, in whose district
# the Licensee has his registered seat, an establishment or assets.

from itertools import chain
import uuid

from sqlalchemy import Column, exists
from sqlalchemy.dialects.postgresql import UUID as PSQL_UUID
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.types import TypeDecorator, CHAR, JSON

from ._init import Session


# this class is provided by the official sqlalchemy docs:
# https://docs.sqlalchemy.org/en/13/core/custom_types.html#backend-agnostic-guid-type
class UUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses PostgreSQL's UUID type, otherwise uses
    CHAR(32), storing as stringified hex values.

    """
    impl = CHAR

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PSQL_UUID())
        else:
            return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return "%.32x" % uuid.UUID(value).int
            else:
                # hexstring
                return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(value)
            return value


class OrmSessionMixin:
    id = Column(UUID, nullable=False, unique=True, primary_key=True)
    data = Column(JSON, nullable=False)


class OrmSession(Session):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__orm_object = None

    def _id_is_valid(self, id):
        return self._orm.query(exists().where(self._orm_class.id == id)).\
            scalar()

    @property
    def _orm_object(self):
        if self.__orm_object is None:
            if self._original_id:
                self.__orm_object = self._orm.query(self._orm_class).\
                    filter(self._orm_class.id == self._original_id).\
                    first()
            else:
                self.__orm_object = self._orm_class(
                    data=dict()
                )
        return self.__orm_object

    def _store(self):
        self._orm_object.id = self.id
        self._orm.add(self._orm_object)
        flag_modified(self._orm_object, 'data')
        if not self._has_ctx:
            self._orm.commit()

    def _revert(self):
        # the transaction will be rolled back
        # by score.ctx, if it was configured
        if not self._has_ctx:
            self._orm.rollback()

    def _set(self, key, value):
        if hasattr(self._orm_object, key):
            setattr(self._orm_object, key, value)
        else:
            self._orm_object.data[key] = value

    def _del(self, key):
        if hasattr(self._orm_object, key):
            setattr(self._orm_object, key, None)
        else:
            del(self._orm_object.data[key])

    def _contains(self, key):
        return (hasattr(self._orm_object, key)
                or key in self._orm_object.data)

    def _get(self, key):
        if hasattr(self._orm_object, key):
            return getattr(self._orm_object, key)
        return self._orm_object.data[key]

    def _iter(self):
        return chain((col.name
                      for col in self._orm_class.__table__.columns
                      if col.name not in ('id', 'data')),
                     iter(self._orm_object.data))
