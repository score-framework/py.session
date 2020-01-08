# Copyright © 2015-2018 STRG.AT GmbH, Vienna, Austria
# Copyright © 2019-2020 Necdet Can Ateşman <can@atesman.at>, Vienna, Austria
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

import abc
import collections.abc
from copy import deepcopy
import uuid

from score.init import (
    ConfiguredModule, ConfigurationError, parse_bool, parse_time_interval,
    parse_dotted_path)
from transaction.interfaces import IDataManager
from zope.interface import implementer


defaults = {
    'orm.class': None,
    'kvcache.container': 'score.session',
    'kvcache.livedata': 'false',
    'ctx.member': 'session',
    'cookie': 'session',
    'cookie.max_age': None,
    'cookie.path': '/',
    'cookie.domain': None,
    'cookie.secure': True,
    'cookie.httponly': True,
    'cookie.samesite': None,
}


def init(confdict, orm=None, kvcache=None, ctx=None):
    """
    Initializes this module acoording to :ref:`our module initialization
    guidelines <module_initialization>` with the following configuration keys:

    :confkey:`orm.class` :faint:`[default=None]`
        The :func:`path <score.init.parse_dotted_path>` to the database class,
        that should be used as backend.

    :confkey:`kvcache.container` :faint:`[default=score.session]`
        The name of the :term:`cache container` to use for storing session
        data when using :mod:`score.kvcache` as backend.

    :confkey:`kvcache.livedata` :faint:`[default=false]`
        This value defines whether sessions must always pull the newest session
        data for every operation. This has the advantage that all session data
        will be immediately up-to-date across all processes using the same
        session, but also the disadvantage that it will make using the session
        a lot slower.

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

    :confkey:`cookie.samesite` :faint:`[default=None]`
        The SameSite parameter of the cookie, must be either 'Lax' or 'Strict'
        if set.

    """
    conf = defaults.copy()
    conf.update(confdict)
    ctx_member = None
    if ctx and conf['ctx.member'] not in (None, 'None'):
        ctx_member = conf['ctx.member']
    cookie_kwargs = parse_cookie_kwargs(conf)
    session = ConfiguredSessionModule(ctx, ctx_member, cookie_kwargs)
    session.Session = _init_orm_backend(conf, session, orm, ctx)
    if not session.Session:
        session.Session = _init_kvcache_backend(conf, session, kvcache)
        if not session.Session:
            import score.session
            raise ConfigurationError(
                score.session, 'Neither kvcache nor orm backend configured')
    return session


def _init_orm_backend(conf, session, orm, ctx):
    if 'orm.class' not in conf:
        return None
    if not conf['orm.class'] or conf['orm.class'] == 'None':
        return None
    if not orm:
        import score.session
        raise ConfigurationError(
            score.session,
            'Need score.sa.orm in order to use `orm.class`')
    if not ctx:
        import score.session
        raise ConfigurationError(
            score.session,
            'Need score.ctx in order to use `orm.class`')
    from .orm import OrmSessionMixin, OrmSession
    class_ = parse_dotted_path(conf['orm.class'])
    if not issubclass(class_, OrmSessionMixin):
        import score.session
        raise ConfigurationError(
            score.session,
            'Configured `orm.class` must inherit OrmSessionMixin')
    if not hasattr(orm, 'ctx'):
        import score.session
        raise ConfigurationError(
            score.session,
            'Configured score.sa.orm has not score.ctx configuration')
    if ctx != orm.ctx:
        import score.session
        raise ConfigurationError(
            score.session,
            'Configured score.sa.orm uses different score.ctx dependency')
    return type('ConfiguredOrmSession', (OrmSession,), {
        '_has_ctx': ctx is not None,
        '_conf': session,
        '_orm_conf': orm,
        '_orm_class': class_,
        '_orm': property(lambda self: orm.get_session(self._ctx)),
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
    samesite = conf['cookie.samesite']
    if samesite and samesite.strip().lower() != 'none':
        samesite = samesite.strip()
        samesite = samesite[0].upper() + samesite[1:].lower()
        if samesite not in ('Strict', 'Lax'):
            raise ValueError('cookie.samesite must be "Strict" or "Lax"')
    else:
        samesite = None
    cookie_kwargs = {
        'name': conf['cookie'],
        'path': conf['cookie.path'],
        'domain': conf['cookie.domain'],
        'secure': parse_bool(conf['cookie.secure']),
        'httponly': parse_bool(conf['cookie.httponly']),
        'samesite': samesite,
    }
    if conf['cookie.max_age']:
        cookie_kwargs['max_age'] = \
            parse_time_interval(conf['cookie.max_age'])
    return cookie_kwargs


@implementer(IDataManager)
class DataManager:

    revert_data = None

    def __init__(self, session_conf, ctx, session):
        self.session_conf = session_conf
        self.ctx = ctx
        self.session = session
        self.transaction_manager = session_conf.ctx.get_tx(ctx)

    def tpc_finish(self, transaction):
        pass

    def sortKey(self):
        return 'score.auth(%d)' % (id(self.ctx),)

    def tpc_abort(self, transaction):
        if self.revert_data is not None and self.session.id:
            self.session.clear()
            self.session.update(self.revert_data)
            self.revert_data = None

    def abort(self, transaction):
        self.session.revert()

    def tpc_begin(self, transaction):
        pass

    def commit(self, transaction):
        if self.session.id:
            revert_data = {}
            revert_data.update(self.session)
            revert_data.pop('id', None)
            self.session.store()
            self.revert_data = revert_data

    def tpc_vote(self, transaction):
        pass


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
        if ctx and cookie_kwargs and 'max_age' in cookie_kwargs:
            # keep the client's cookie alive by sending him the cookie with
            # each response
            id_member = self.ctx_member + '_id'

            @ctx.on_destroy
            def destructor(ctx, exception):
                if exception:
                    return
                if not hasattr(ctx, 'http'):
                    return
                ctx_meta = self.ctx.get_meta(ctx)
                if ctx_meta.member_constructed(ctx_member):
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
                session = self.load(getattr(ctx, id_member), ctx)
            elif self.cookie_kwargs and hasattr(ctx, 'http'):
                id = ctx.http.request.cookies.get(
                    self.cookie_kwargs['name'], None)
                session = self.load(id, ctx)
            else:
                session = self.create(ctx)
            tx = self.ctx.get_tx(ctx).get()
            tx.join(DataManager(self, ctx, session))
            return session

        def destructor(ctx, session, exception):
            setattr(ctx, id_member, session.id)
            if self.cookie_kwargs and 'max_age' in self.cookie_kwargs:
                # the next part is only relevant if we are not setting the
                # response cookie anyway in the global context destruction
                # listener (see __init__() of this class)
                return
            if self.cookie_kwargs and hasattr(ctx, 'http') and not exception:
                if session.id and session._original_id != session.id:
                    kwargs = self.cookie_kwargs.copy()
                    kwargs['value'] = session.id
                    ctx.http.response.set_cookie(**kwargs)

        self.ctx.register(self.ctx_member, constructor, destructor=destructor)

    def create(self, ctx=None):
        """
        Creates a new, empty :class:`.Session`.
        """
        return self.Session(ctx, None)

    def load(self, id, ctx=None):
        """
        Loads an existing session with given *id*.
        """
        return self.Session(ctx, id)


class Session(abc.ABC, collections.abc.MutableMapping):
    """
    A dict-like object managing session data. The modified session information
    is persisted when this object is destroyed. You can also call
    :meth:`.store` manually to make the data of this session available to
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
        if self._is_dirty:
            self._revert()
            self._is_dirty = False

    def was_changed(self):
        """
        Returns a `bool` indicating whether a modifying operation was
        performed on this session.
        """
        return self._was_changed

    def _mark_dirty(self):
        self._was_changed = True
        self._is_dirty = True

    # Functions that need to be implemented by sub-classes

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
    # functions above.

    def __contains__(self, key):
        if self.id is None:
            return False
        return self._contains(key)

    def __getitem__(self, key):
        if self.id is None:
            raise KeyError(key)
        return deepcopy(self._get(key))

    def __setitem__(self, key, value):
        if self.get(key, self) == value:
            return
        if self.id is None:
            self.id = str(uuid.uuid4())
        self._set(key, value)
        self._mark_dirty()

    def __delitem__(self, key):
        if key not in self:
            return
        self._del(key)
        self._mark_dirty()

    def __iter__(self):
        return self._iter()

    def __len__(self):
        return sum(1 for _ in self._iter())


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

    def __len__(self):
        return len(self._dict)
