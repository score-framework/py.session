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

"""
This package :ref:`integrates <framework_integration>` the module with
pyramid_.

.. _pyramid: http://docs.pylonsproject.org/projects/pyramid/en/latest/
"""
from binascii import hexlify
from datetime import datetime
from pyramid.interfaces import ISession
import os
import score.session
from zope.interface import implementer


defaults = {
    'cookie': 'session',
}


def init(confdict, configurator, kvcache_conf, ctx_conf=None):
    """
    Apart from calling the :func:`base initializer <score.db.init>`, this
    function will


    function will also register a :ref:`reified request method
    <pyramid:adding_request_method>` called ``db`` on all :ref:`Request
    <pyramid:request_module>` objects that provides a session with the same
    lifetime as the request. Example use:

    >>> request.db.query(User).first()
    """
    session_conf = score.session.init(confdict, kvcache_conf, ctx_conf)
    session_conf.create = lambda: PyramidSession(session_conf)
    session_conf.load = lambda id: PyramidSession(session_conf, id)
    if session_conf.ctx_member:
        conf = defaults.copy()
        conf.update(confdict)
        member = session_conf.ctx_member
        id_member = member + '_id'
        changed_member = member + '_changed'
        def constructor(ctx):
            return ctx.request.cookies.get(conf['cookie'], None)
        def destructor(ctx, original_id, exception):
            if not getattr(ctx, 'response', None) or exception:
                return
            if not getattr(ctx, changed_member):
                return
            id = getattr(ctx, id_member)
            ctx.response.set_cookie(
                conf['cookie'],
                value=id,
                # TODO
                # max_age=self._cookie_max_age,
                # path=self._cookie_path,
                # domain=self._cookie_domain,
                # secure=self._cookie_secure,
                # httponly=self._cookie_httponly,
                )
        ctx_conf.register(id_member, constructor, destructor)
        def factory(request):
            return request.ctx.session
    else:
        def factory(request):
            # TODO
            pass
    configurator.set_session_factory(factory)
    return session_conf


@implementer(ISession)
class PyramidSession(score.session.Session):

    @property
    def created(self):
        try:
            return self['__created__']
        except KeyError:
            self['__created__'] = datetime.now().timestamp()
            return self['__created__']

    @property
    def new(self):
        return self._original_id is None

    def invalidate(self):
        self.clear()

    def changed(self):
        self._changed = True

    def flash(self, msg, queue='', allow_duplicate=True):
        key = '__flash(%s)__' % queue
        queue = self.get(key, [])
        if not allow_duplicate and msg in queue:
            return
        queue.append(msg)
        self[key] = queue

    def pop_flash(self, queue=''):
        key = '__flash(%s)__' % queue
        return self.pop(key, [])

    def peek_flash(self, queue=''):
        key = '__flash(%s)__' % queue
        return self.get(key, [])

    def new_csrf_token(self):
        self['__csrf_token__'] = hexlify(os.urandom(20)).decode('ascii')
        return self['__csrf_token__']

    def get_csrf_token(self):
        try:
            return self['__csrf_token__']
        except KeyError:
            return self.new_csrf_token()
