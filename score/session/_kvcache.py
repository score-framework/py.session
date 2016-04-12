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
