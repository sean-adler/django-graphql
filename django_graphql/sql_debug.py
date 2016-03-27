from __future__ import absolute_import, unicode_literals

import json
from contextlib import contextmanager
from threading import local
from time import time

from django.db import connections
from django.utils import six
from django.utils.encoding import force_text

from debug_toolbar import settings as dt_settings
from debug_toolbar.utils import get_stack, get_template_info, tidy_stacktrace

from graphql.core.type import (
    GraphQLArgument,
    GraphQLField,
    GraphQLFloat,
    GraphQLInt,
    GraphQLList,
    GraphQLObjectType,
    GraphQLSchema,
    GraphQLString,
)


class SQLQueryTriggered(Exception):
    """Thrown when template panel triggers a query"""
    pass


class ThreadLocalState(local):
    def __init__(self):
        self.enabled = True

    @property
    def Wrapper(self):
        if self.enabled:
            return NormalCursorWrapper
        return ExceptionCursorWrapper

    def recording(self, v):
        self.enabled = v


state = ThreadLocalState()
recording = state.recording


def wrap_cursor(connection, panel):
    if not hasattr(connection, '_djdt_cursor'):
        connection._djdt_cursor = connection.cursor

        def cursor():
            return state.Wrapper(connection._djdt_cursor(), connection, panel)

        connection.cursor = cursor
        return cursor


def unwrap_cursor(connection):
    if hasattr(connection, '_djdt_cursor'):
        del connection._djdt_cursor
        del connection.cursor


class ExceptionCursorWrapper(object):
    """
    Wraps a cursor and raises an exception on any operation.
    Used in Templates panel.
    """
    def __init__(self, cursor, db, logger):
        pass

    def __getattr__(self, attr):
        raise SQLQueryTriggered()


class NormalCursorWrapper(object):
    """
    Wraps a cursor and logs queries.
    """

    def __init__(self, cursor, db, logger):
        self.cursor = cursor
        # Instance of a BaseDatabaseWrapper subclass
        self.db = db
        # logger must implement a ``record`` method
        self.logger = logger

    def _quote_expr(self, element):
        if isinstance(element, six.string_types):
            return "'%s'" % force_text(element).replace("'", "''")
        else:
            return repr(element)

    def _quote_params(self, params):
        if not params:
            return params
        if isinstance(params, dict):
            return dict((key, self._quote_expr(value))
                        for key, value in params.items())
        return list(map(self._quote_expr, params))

    def _decode(self, param):
        try:
            return force_text(param, strings_only=True)
        except UnicodeDecodeError:
            return '(encoded string)'

    def _record(self, method, sql, params):
        start_time = time()
        try:
            return method(sql, params)
        finally:
            stop_time = time()
            duration = (stop_time - start_time) * 1000
            if dt_settings.CONFIG['ENABLE_STACKTRACES']:
                stacktrace = tidy_stacktrace(reversed(get_stack()))
            else:
                stacktrace = []
            _params = ''
            try:
                _params = json.dumps(list(map(self._decode, params)))
            except Exception:
                pass  # object not JSON serializable

            template_info = get_template_info()

            alias = getattr(self.db, 'alias', 'default')
            conn = self.db.connection
            vendor = getattr(conn, 'vendor', 'unknown')

            params = {
                'vendor': vendor,
                'alias': alias,
                'sql': self.db.ops.last_executed_query(
                    self.cursor, sql, self._quote_params(params)),
                'duration': duration,
                'raw_sql': sql,
                'params': _params,
                'stacktrace': stacktrace,
                'start_time': start_time,
                'stop_time': stop_time,
                'is_select': sql.lower().strip().startswith('select'),
                'template_info': template_info,
            }

            if vendor == 'postgresql':
                # If an erroneous query was ran on the connection, it might
                # be in a state where checking isolation_level raises an
                # exception.
                try:
                    iso_level = conn.isolation_level
                except conn.InternalError:
                    iso_level = 'unknown'
                params.update({
                    'trans_id': self.logger.get_transaction_id(alias),
                    'trans_status': conn.get_transaction_status(),
                    'iso_level': iso_level,
                    'encoding': conn.encoding,
                })

            # We keep `sql` to maintain backwards compatibility
            self.logger.record(**params)

    def callproc(self, procname, params=()):
        return self._record(self.cursor.callproc, procname, params)

    def execute(self, sql, params=()):
        return self._record(self.cursor.execute, sql, params)

    def executemany(self, sql, param_list):
        return self._record(self.cursor.executemany, sql, param_list)

    def __getattr__(self, attr):
        return getattr(self.cursor, attr)

    def __iter__(self):
        return iter(self.cursor)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()


class WrappedRoot(object):
    def __init__(self, root):
        self.queries = []
        self.duration = 0
        self._last_query = time()
        self._root = root

    def record(self, **kwargs):
        self.queries.append(kwargs)
        now = time()
        self.duration += (now - self._last_query) * 1000
        self._last_query = now

# TODO: convenience 'ObjectType' class that auto-generates
# resolvers based on class-fields, and just assumes ``data`` is dict
# or in-memory object (so, traverse fields with __getitem__ or getattr)

DjangoDebugSQL = GraphQLObjectType(
    'DjangoDebugSQL',
    fields=lambda: {
        'vendor': GraphQLField(
            GraphQLString,
            description='VENDOR of sql db',
            resolver=lambda data, *args: data['vendor']),
        'name': GraphQLField(GraphQLString),
        'sql': GraphQLField(
            GraphQLString,
            resolver=lambda data, *args: data['sql']),
        'duration': GraphQLField(
            GraphQLFloat,
            resolver=lambda data, *args: data['duration']),
        'raw_sql': GraphQLField(
            GraphQLString,
            resolver=lambda data, *args: data['raw_sql']),
        'params': GraphQLField(GraphQLString),
        'stacktrace': GraphQLField(GraphQLList(GraphQLString)),
    })


DjangoDebug = GraphQLObjectType(
    'DjangoDebug',
    fields=lambda: {
        'queries': GraphQLField(
            GraphQLList(DjangoDebugSQL),
            description='SQL Debugging Data for Django',
            resolver=lambda data, *args: data['queries']),
        'query_count': GraphQLField(
            GraphQLInt,
            resolver=lambda data, *args: data['query_count']),
        'duration': GraphQLField(
            GraphQLFloat,
            resolver=lambda data, *args: data['duration'])
    })


class DjangoDebugPlugin(object):
    def enable_instrumentation(self, wrapped_root):
        for connection in connections.all():
            wrap_cursor(connection, wrapped_root)

    def disable_instrumentation(self):
        for connection in connections.all():
            unwrap_cursor(connection)

    @contextmanager
    def apply(self, request=None, root=None, schema=None):
        root_fields = root.get_fields()

        # TODO: convenience method for copying GraphQLFields
        # that maintains root spec.
        # ``get_fields()`` returns root args as list, not dict.

        field_spec = {
            name: GraphQLField(
                field.type,
                description=field.description,
                args={
                    arg.name: GraphQLArgument(type=arg.type)
                    for arg in field.args
                },
                resolver=field.resolver)
            for name, field in root.get_fields().iteritems()
        }

        def get_debug(_root, *args):
            return {
                'queries': _root.queries,
                'query_count': len(_root.queries),
                'duration': _root.duration
            }

        field_spec['__debug'] = GraphQLField(
            DjangoDebug,
            description=DjangoDebug.__doc__,
            args={},
            resolver=get_debug)
        root_with_debug = GraphQLObjectType(
            root.name,
            fields=field_spec)
        wrapped_root = WrappedRoot(root=root_with_debug)
        schema_with_debug = GraphQLSchema(query=root_with_debug)
        applied = {
            'request': request,
            'root': wrapped_root,
            'schema': schema_with_debug,
        }

        self.enable_instrumentation(wrapped_root)
        yield applied
        self.disable_instrumentation()
