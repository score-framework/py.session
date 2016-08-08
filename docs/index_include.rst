.. module:: score.session
.. role:: default
.. role:: confkey

*************
score.session
*************

A small module for handling `sessions`_. Originally written for web usage, but
can be used outside of web environments without any constraints.

.. _sessions: https://en.wikipedia.org/wiki/Session_%28computer_science%29


.. _session_quickstart:

Quickstart
==========

For a quick integration of this module, just add it and :mod:`score.kvcache` to
your modules list. It also makes sense to disable the https-only flag during
development:

.. code-block:: ini
    :emphasize-lines: 4,5,8

    [score.init]
    modules =
        score.ctx
        score.session
        score.kvcache

    [session]
    # cookies are allowed on non-HTTPS sites during development:
    cookie.secure = False

    [kvcache]
    # default backend, we're configuring a sqlite file in
    # the same folder as this config file:
    backend.default = score.kvcache.backend.FileCache
    backend.default.path = ${here}/_cache.sqlite3
    # session cache:
    container.score.session.backend = default

You should now have a new :term:`context member` called *session*, which
behaves just like a regular `dict`. It will start out without an id, but will
gain a :func:`uuid4 <uuid.uuid4>` string once it contains something:

>>> ctx.session.id
>>> ctx.session['parrot'] = 'dead'
>>> ctx.session.id
b9a1aa34-e44a-4370-9d06-1431ab692b94

If you want to access a specific session, you have to set *ctx.session_id*
before accessing the session:

>>> ctx.session_id = 'b9a1aa34-e44a-4370-9d06-1431ab692b94'
>>> ctx.session['parrot']
'dead'

If you're using the :mod:`score.http` module, there is nothing more to do: The
module will automatically set appropriate session cookies and load the sessions
if it receives them back.


.. _session_configuration:

Configuration
=============

.. autofunction:: score.session.init


.. _session_details:

Details
=======

.. _session_loading:

Loading Sessions
----------------

Sessions can be accessed through the methods :meth:`create
<score.session.ConfiguredSessionModule.create>` and :meth:`load
<score.session.ConfiguredSessionModule.load>` on the configured module. If you
are using :mod:`score.ctx`, though, you can set the context's session id on the
context:

>>> ctx.session_id = 'b9a1aa34-e44a-4370-9d06-1431ab692b94'
>>> ctx.session['username']
'sirlancelot'

.. note::

    The name of the id-member is constructed using the configured context
    member. If you have configured your score.session to register its context
    member as ``storage``, the id-member will be ``storage_id``:

    >>> ctx.storage_id = 'b9a1aa34-e44a-4370-9d06-1431ab692b94'
    >>> ctx.storage['username']
    'sirlancelot'

You must take special care when using this approch, since the id-member will
only be read once: whenever you access the *ctx.session* for the first time.
The following corde leads to undefined behaviour:

.. code-block:: python

    # WARNING! Broken code! Always set ctx.session_id *before*
    # accessing ctx.session for the first time!
    ctx.session['parrot'] = 'passed on'
    ctx.session_id = 515


.. _session_backend:

Backends
--------

The module is capable of storing session data in either of two backends: a
:mod:`score.kvcache` :term:`container <cache container>`, or a :mod:`score.db`
table.

Using :mod:`score.kvcache` is much easier, but does not allow you to access all
sessions of a single user efficiently, for example. It merely stores a mapping
of session ids to session data. This should really not come as a big surprise
when using the key-value-cache as backend.

The alternative backend is :mod:`score.db`. Its usage requires a bit more
configuration. Not only in your configuration file …

.. code-block:: ini
    :emphasize-lines: 2

    [session]
    db.class = path.to.Session

… but also in your application: you will need a database class with an
additional mixin from this package:

.. code-block:: python

    from .storable import Storable
    from score.db import IdType
    from score.session.db import DbSessionMixin
    from sqlalchemy import Column, ForeignKey
    from sqlalchemy.orm import relationship


    class Session(Storable, DbSessionMixin):
        user_id = Column(IdType, ForeignKey('_user.id'))
        user = relationship('User', backref='sessions')

This approach has the advantage that you can operate on sessions just like any
other database entity. There is also a small drawback, however: You can no
longer delete the user_id on your sessions:

>>> ctx.session['user_id'] is None
True
>>> del(ctx.session['user_id'])
>>> ctx.session['user_id'] is None
True
>>> del(ctx.session['I-dont-exist'])
KeyError: 'I-dont-exist'

The mixin will allow you to write arbitrary values, just like before:

>>> ctx.session['actor_id'] = 14
>>> ctx.session['parrot'] = 'ceased to be'

These additional values will be stored as JSON value in the column ``_data``:

.. code-block:: sqlite3

    sqlite> .schema _session
    CREATE TABLE _session (
        _uuid VARCHAR(36) NOT NULL, 
        _data VARCHAR NOT NULL, 
        actor_id INTEGER, 
        _type VARCHAR(100) NOT NULL, 
        id INTEGER NOT NULL, 
        PRIMARY KEY (id), 
        UNIQUE (_uuid), 
        FOREIGN KEY(actor_id) REFERENCES _actor (id)
    );
    sqlite> select * from _session;
    a9fd7ad0-1ed0-45ab-bf5f-bb2b00741ded|{"parrot": "ceased to be"}|14|session|1

.. _session_api:

API
===

.. autoclass:: score.session.ConfiguredSessionModule

    .. attribute:: ctx_member

        Name of the registered :term:`context member`, or `None` if no context
        member was registered.

    .. automethod:: score.session.ConfiguredSessionModule.create

    .. automethod:: score.session.ConfiguredSessionModule.load

.. autoclass:: score.session.Session

    .. automethod:: score.session.Session.store

    .. automethod:: score.session.Session.revert

    .. automethod:: score.session.Session.was_changed
