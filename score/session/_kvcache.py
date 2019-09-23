# Copyright © 2015-2018 STRG.AT GmbH, Vienna, Austria
#
# This file is part of the The SCORE Framework.
#
# The SCORE Framework and all its parts are free software: you can redistribute
# them and/or modify them under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation which is in the
# file named COPYING.LESSER.txt.
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
# the discretion of STRG.AT GmbH also the competent court, in whose district the
# Licensee has his registered seat, an establishment or assets.

from ._init import DictSession
import score.kvcache as kvcache


class KvcacheSession(DictSession):
    """
    Session backend that makes use of a configured :mod:`score.kvcache`.
    """

    def _mark_dirty(self):
        super()._mark_dirty()
        if self._livedata:
            self._store()
            self._is_dirty = False

    def _create_dict(self):
        try:
            return self._container[self.id]
        except kvcache.NotFound:
            return {}

    def _id_is_valid(self, id):
        return id in self._container

    def _store(self):
        self._container[self.id] = self._cached_dict

    def _revert(self):
        self._cached_dict = None
