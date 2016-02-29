# Copyright © 2015 STRG.AT GmbH, Vienna, Austria
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

import score.kvcache as kvcache
from score.init import ConfiguredModule, parse_bool, parse_time_interval
import uuid


defaults = {
    'livedata': 'false',
    'kvcache.container': 'score.session',
    'ctx.member': 'session',
    'cookie': 'session',
    'cookie.max_age': None,
    'cookie.path': None,
    'cookie.domain': None,
    'cookie.secure': True,
    'cookie.httponly': True,
}


def init(confdict, kvcache, ctx=None):
    """
    Initializes this module acoording to :ref:`our module initialization
    guidelines <module_initialization>` with the following configuration keys:

    :confkey:`kvcache.container` :faint:`[default=score.session]`
        The name of the :term:`cache container` to use for storing session
        data.

    :confkey:`livedata` :faint:`[default=false]`
        This value defines whether sessions must always pull the newest session
        data for every operation. This has the advantage that all session data
        will be immediately up-to-date across all processes using the same
        session, but also the disadvantage that it will make using the session a
        lot slower.

    :confkey:`ctx.member` :faint:`[default=session]`
        This is the name of the :term:`context member`, that should be
        registered with the configured :mod:`score.ctx` module (if there is
        one).

    :confkey:`cookie` :faint:`[default=session]`
        Name of the cookie to set when used in combination with the
        :mod:`score.http` module. It is recommended to provide a non-default,
        obscure value here.  Setting this value to the string `None` will
        disable setting cookies.

    :confkey:`cookie.max_age` :faint:`[default=None]`
        The max-age parameter of the cookie. The default value of `None` means
        that the cookie will be valid until the browser is closed.

    :confkey:`cookie.path` :faint:`[default=None]`
        The path parameter of the cookie.

    :confkey:`cookie.domain` :faint:`[default=None]`
        The domain parameter of the cookie.

    :confkey:`cookie.secure` :faint:`[default=True]`
        The secure parameter of the cookie. Please be aware that you are
        exposing your user sessions to man-in-the-middle__ attacks (like
        wireless sniffers), if you set this value to `False` in production.

        .. __: https://en.wikipedia.org/wiki/Man-in-the-middle_attack

    :confkey:`cookie.httponly` :faint:`[default=True]`
        The httponly parameter of the cookie. Please be aware that setting this
        value to `False` in production can lead to session hijacking, if an
        attacker manages to sneak in malicious javascript code into your
        application (using XSS_, for example).

        .. _XSS: https://en.wikipedia.org/wiki/Cross-site_scripting

    """
    conf = defaults.copy()
    conf.update(confdict)
    livedata = parse_bool(conf['livedata'])
    container = kvcache[conf['kvcache.container']]
    ctx_member = None
    if ctx and conf['ctx.member'] not in (None, 'None'):
        ctx_member = conf['ctx.member']
    cookie_kwargs = None
    if conf['cookie'] and conf['cookie'] != 'None':
        cookie_kwargs = {
            'name': conf['cookie'],
            'path': conf['cookie.path'],
            'domain': conf['cookie.domain'],
            'secure': parse_bool(conf['cookie.secure']),
            'httponly': parse_bool(conf['cookie.httponly']),
        }
        if conf['cookie.max_age']:
            cookie_kwargs['cookie.max_age'] = \
                parse_time_interval(conf['cookie.max_age'])
    return ConfiguredSessionModule(
        container, livedata, ctx, ctx_member, cookie_kwargs)


class ConfiguredSessionModule(ConfiguredModule):
    """
    This module's :class:`configuration class
    <score.init.ConfiguredModule>`.
    """

    def __init__(self, cache, livedata, ctx, ctx_member, cookie_kwargs):
        super().__init__(__package__)
        self.cache = cache
        self.livedata = livedata
        self.ctx = ctx
        self.ctx_member = ctx_member
        self.cookie_kwargs = cookie_kwargs
        if ctx and ctx_member:
            self.__register_ctx_member()

    def __register_ctx_member(self):
        id_member = self.ctx_member + '_id'

        def constructor(ctx):
            if hasattr(ctx, id_member):
                return self.load(getattr(ctx, id_member))
            if self.cookie_kwargs and hasattr(ctx, 'http'):
                return self.load(
                    ctx.http.request.cookies.get(self.cookie_kwargs['name'],
                                                 None))
            return self.create()

        def destructor(ctx, session, exception):
            setattr(ctx, id_member, session.id)
            if not self.livedata:
                if exception:
                    session.revert()
                else:
                    session.store()
            if self.cookie_kwargs and hasattr(ctx, 'http') and not exception:
                if session._original_id is None:
                    kwargs = self.cookie_kwargs.copy()
                    kwargs['value'] = session.id
                    ctx.http.response.set_cookie(**kwargs)

        self.ctx.register(self.ctx_member, constructor, destructor)

    def create(self):
        """
        Creates a new, empty :class:`.Session`.
        """
        return Session(self, None)

    def load(self, id):
        """
        Loads an existing session with given *id*.
        """
        return Session(self, id)


class Session:
    """
    A dict-like object managing session data. If the module was not configured
    to operate on up-to-date session data (see ``livedata`` setting of
    :func:`.init`), the modified session information is persisted when this
    object is destroyed. You can also call :meth:`.store()` manually to make the
    data of this session available to other processes.
    """

    def __init__(self, conf, id):
        self._conf = conf
        self.id = id
        self._original_id = id
        self._changed = False
        self.__data = None

    def __del__(self):
        self.store()

    def revert(self):
        """
        Throws away all changes to the current session. This will obviously not
        work, if the module was configured to operate on live data.
        """
        if self.__data is None or self._conf.livedata:
            return
        self._changed = False
        self.__data = None

    def store(self):
        """
        Persists the information in this session instance.
        """
        if not self._changed or self.__data is None:
            return
        self._conf.cache[self.id] = self.__data

    def __contains__(self, key):
        if self.id is None:
            return False
        return key in self._data

    def __getitem__(self, key):
        if self.id is None:
            raise KeyError(key)
        return self._data[key]

    def __setitem__(self, key, value):
        if self.id is None:
            self.id = str(uuid.uuid4())
        self._data[key] = value
        self._changed = True
        if self._conf.livedata:
            self.store()

    def __delitem__(self, key):
        if self.id is None:
            return
        if self._conf.livedata and key not in self._data:
            return
        # we could test if the key is actually present in the session _data, as
        # above, but that would mean we would miss an opportunity to persist
        # this session, although the develepor explicitly manipulated its
        # content by deleting a key. this might be relevant when multiple
        # processes access the same session.
        self._changed = True
        del self._data[key]

    def __iter__(self):
        return iter(self._data)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def items(self):
        return self._data.items()

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def pop(self, key, default=None):
        result = self.get(key, default)
        del self[key]
        return result

    def popitem(self):
        result = self._data.popitem()
        self._changed = True
        return result

    def setdefault(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            self[key] = default
            return default

    def update(self, other):
        self._data.update(other)

    def clear(self):
        self._changed = True
        self._data.clear()

    def was_changed(self):
        return self._changed

    @property
    def _data(self):
        if self.__data is None or self._conf.livedata:
            try:
                self.__data = self._conf.cache[self.id]
            except kvcache.NotFound:
                self.__data = {}
        return self.__data
