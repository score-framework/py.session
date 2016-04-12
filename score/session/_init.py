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

import abc
from score.init import (
    ConfiguredModule, ConfigurationError, parse_bool, parse_time_interval,
    parse_dotted_path)
import uuid


defaults = {
    'db.class': None,
    'kvcache.container': 'score.session',
    'kvcache.livedata': 'false',
    'ctx.member': 'session',
    'cookie': 'session',
    'cookie.max_age': None,
    'cookie.path': '/',
    'cookie.domain': None,
    'cookie.secure': True,
    'cookie.httponly': True,
}


def init(confdict, db=None, kvcache=None, ctx=None):
    """
    Initializes this module acoording to :ref:`our module initialization
    guidelines <module_initialization>` with the following configuration keys:

    :confkey:`db.class` :faint:`[default=None]`
        The :func:`path <score.init.parse_dotted_path>` to the database class,
        that should be used as backend.

    :confkey:`kvcache.container` :faint:`[default=score.session]`
        The name of the :term:`cache container` to use for storing session
        data when using :mod:`score.kvcache` as backend.

    :confkey:`kvcache.livedata` :faint:`[default=false]`
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

    :confkey:`cookie.path` :faint:`[default=/]`
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
    ctx_member = None
    if ctx and conf['ctx.member'] not in (None, 'None'):
        ctx_member = conf['ctx.member']
    cookie_kwargs = parse_cookie_kwargs(conf)
    session = ConfiguredSessionModule(ctx, ctx_member, cookie_kwargs)
    session.Session = _init_db_backend(conf, session, db)
    if not session.Session:
        session.Session = _init_kvcache_backend(conf, session, kvcache)
        if not session.Session:
            import score.session
            raise ConfigurationError(
                score.session, 'Neither kvcache nor db backend configured')
    return session


def _init_db_backend(conf, session, db):
    if not db:
        return None
    if 'db.class' not in conf:
        return None
    if not conf['db.class'] or conf['db.class'] == 'None':
        return None
    from .db import DbSessionMixin, DbSession
    from zope.sqlalchemy import ZopeTransactionExtension
    class_ = parse_dotted_path(conf['db.class'])
    if not issubclass(class_, DbSessionMixin):
        import score.session
        raise ConfigurationError(
            score.session, 'Configured `db.class` must inherit DbSessionMixin')
    if db.ctx_member:
        def session(self):
            return getattr(self._ctx, db.ctx_member)
    else:
        def session(self):
            if not hasattr(self, '_db_session'):
                zope_tx = ZopeTransactionExtension(
                    transaction_manager=self._ctx.tx_manager)
                self._db_session = db.Session(extension=zope_tx)
            return self._db_session
    return type('ConfiguredDbSession', (DbSession,), {
        '_conf': session,
        '_db_class': class_,
        '_db': property(session),
    })


def _init_kvcache_backend(conf, session, kvcache):
    if not kvcache:
        return None
    from ._kvcache import KvcacheSession
    return type('ConfiguredKvcacheSession', (KvcacheSession,), {
        '_conf': session,
        '_livedata': parse_bool(conf['kvcache.livedata']),
        '_container': kvcache[conf['kvcache.container']],
    })


def parse_cookie_kwargs(conf):
    if not conf['cookie'] or conf['cookie'] == 'None':
        return None
    cookie_kwargs = {
        'name': conf['cookie'],
        'path': conf['cookie.path'],
        'domain': conf['cookie.domain'],
        'secure': parse_bool(conf['cookie.secure']),
        'httponly': parse_bool(conf['cookie.httponly']),
    }
    if conf['cookie.max_age']:
        cookie_kwargs['max_age'] = \
            parse_time_interval(conf['cookie.max_age'])
    return cookie_kwargs


class ConfiguredSessionModule(ConfiguredModule):
    """
    This module's :class:`configuration class
    <score.init.ConfiguredModule>`.
    """

    def __init__(self, ctx, ctx_member, cookie_kwargs):
        super().__init__(__package__)
        self.ctx = ctx
        self.ctx_member = ctx_member
        self.cookie_kwargs = cookie_kwargs
        if ctx and ctx_member:
            self.__register_ctx_member()
        if 'max_age' in cookie_kwargs:
            # keep the client's cookie alive by sending him the cookie with each
            # response
            id_member = self.ctx_member + '_id'

            @ctx.on_destroy
            def destructor(ctx, exception):
                if exception:
                    return
                if not hasattr(ctx, 'http'):
                    return
                if hasattr(ctx, self.ctx_member):
                    session_id = getattr(ctx, ctx_member).id
                elif hasattr(ctx, id_member):
                    session_id = getattr(ctx, id_member)
                elif self.cookie_kwargs and hasattr(ctx, 'http'):
                    session_id = ctx.http.request.cookies.get(
                        self.cookie_kwargs['name'], None)
                else:
                    return
                if not session_id:
                    return
                kwargs = self.cookie_kwargs.copy()
                kwargs['value'] = str(session_id)
                ctx.http.response.set_cookie(**kwargs)

    def __register_ctx_member(self):
        id_member = self.ctx_member + '_id'

        def constructor(ctx):
            if hasattr(ctx, id_member):
                return self.load(ctx, getattr(ctx, id_member))
            if self.cookie_kwargs and hasattr(ctx, 'http'):
                id = ctx.http.request.cookies.get(
                    self.cookie_kwargs['name'], None)
                return self.load(ctx, id)
            return self.create(ctx)

        def destructor(ctx, session, exception):
            setattr(ctx, id_member, session.id)
            if exception:
                session.revert()
            else:
                session.store()
            if 'max_age' in self.cookie_kwargs:
                # the next part is only relevant if we are not setting the
                # response cookie anyway in the global context destruction
                # listener (see __init__() of this class)
                return
            if self.cookie_kwargs and hasattr(ctx, 'http') and not exception:
                if session._original_id is None and session.id:
                    kwargs = self.cookie_kwargs.copy()
                    kwargs['value'] = session.id
                    ctx.http.response.set_cookie(**kwargs)

        self.ctx.register(self.ctx_member, constructor, destructor)

    def create(self, ctx):
        """
        Creates a new, empty :class:`.Session`.
        """
        return self.Session(ctx, None)

    def load(self, ctx, id):
        """
        Loads an existing session with given *id*.
        """
        return self.Session(ctx, id)


class Session(abc.ABC):
    """
    A dict-like object managing session data. The modified session information
    is persisted when this object is destroyed. You can also call
    :meth:`.store()` manually to make the data of this session available to
    other processes.
    """

    def __init__(self, ctx, id):
        self._ctx = ctx
        self._was_changed = False
        self._is_dirty = False
        if not id or not self._id_is_valid(id):
            id = None
        self.id = id
        self._original_id = id

    def __del__(self):
        self.store()

    def store(self):
        """
        Persists the information in this session instance.
        """
        if self._is_dirty:
            self._store()

    def revert(self):
        """
        Throws away all changes to the current session.
        """
        self._is_dirty = False
        self._revert()

    def was_changed(self):
        """
        Returns a `bool` indicating whether a modifying operation was
        performed on this session.
        """
        return self._was_changed

    def _mark_dirty(self):
        self._was_changed = True
        self._is_dirty = True

    # Functions, that need to be implemented by sub-classes

    @abc.abstractmethod
    def _id_is_valid(self, id):
        return False

    @abc.abstractmethod
    def _store(self):
        pass

    @abc.abstractmethod
    def _revert(self):
        pass

    @abc.abstractmethod
    def _contains(self, key):
        return False

    @abc.abstractmethod
    def _get(self, key):
        raise KeyError(key)

    @abc.abstractmethod
    def _set(self, key, value):
        pass

    @abc.abstractmethod
    def _del(self, key):
        raise KeyError(key)

    @abc.abstractmethod
    def _iter(self):
        raise StopIteration()

    # The rest of these functions implement the dict interface using the
    # abstract functions above.

    def __contains__(self, key):
        if self.id is None:
            return False
        return self._contains(key)

    def __getitem__(self, key):
        if self.id is None:
            raise KeyError(key)
        return self._get(key)

    def __setitem__(self, key, value):
        if self.id is None:
            self.id = str(uuid.uuid4())
        self._set(key, value)
        self._mark_dirty()

    def __delitem__(self, key):
        if self.id is None:
            return
        self._del(key)
        self._mark_dirty()

    def __iter__(self):
        return self._iter()

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def items(self):
        for key in self:
            yield (key, self[key])

    def keys(self):
        yield from self

    def values(self):
        for key in self:
            yield self[key]

    def pop(self, key, default=None):
        result = self.get(key, default)
        del self[key]
        return result

    def popitem(self):
        try:
            key = next(self)
        except StopIteration:
            raise KeyError()
        value = self[key]
        del(self[key])
        return value

    def setdefault(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            self[key] = default
            return default

    def update(self, other):
        for key, value in other:
            self[key] = value

    def clear(self):
        for key in self:
            del(self[key])


class DictSession(Session):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached_dict = None

    @abc.abstractmethod
    def _create_dict(self):
        return {}

    @property
    def _dict(self):
        if self._cached_dict is None:
            self._cached_dict = self._create_dict()
        return self._cached_dict

    def __iter__(self):
        return iter(self._dict)

    def items(self):
        return self._dict.items()

    def keys(self):
        return self._dict.keys()

    def values(self):
        return self._dict.values()

    def _contains(self, key):
        return key in self._dict

    def _get(self, key):
        return self._dict[key]

    def _set(self, key, value):
        self._dict[key] = value

    def _del(self, key):
        del self._dict[key]

    def _iter(self):
        # should actually not be here, as we have implemented __iter__()
        return iter(self._dict)
