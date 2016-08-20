import functools
import pprint
from contextlib import contextmanager

from graphql.core.error import GraphQLError
from graphql.core.execution import Executor
from graphql.core.execution.middlewares.sync import SynchronousExecutionMiddleware
from graphql.core.type import (
    GraphQLBoolean,
    GraphQLFloat,
    GraphQLID,
    GraphQLInt,
    GraphQLObjectType,
    GraphQLField,
    GraphQLArgument,
    GraphQLList,
    GraphQLSchema,
    GraphQLString,
)


class DjangoSchema(object):
    def __init__(self, registry, plugins=()):
        self.registry = registry
        self.plugins = plugins

        self.query_root = GraphQLObjectType(
            'QUERY_ROOT',
            fields=self._get_root_fields)
        # TODO: add mutation root to GraphQLSchema
        self.schema = GraphQLSchema(query=self.query_root)
        self.executor = Executor([SynchronousExecutionMiddleware()])

    def _get_root_fields(self):
        root_type_names = [
            name
            for name, entry in self.registry._types.iteritems()
            if isinstance(entry.graphql_type, GraphQLObjectType)
        ]
        root_spec = {}
        for name in root_type_names:
            root_spec.update(self.registry._get_root_spec(name))
        return root_spec

    @contextmanager
    def apply_plugins(self, request=None, root=None, schema=None):
        """
        Plugins must have an ``apply`` method and are assumed to
        take a dict of:
        {
            'request': (str),
            'root': (GraphQLObjectType),
            'schema': (GraphQLSchema)
        }

        Each plugin's ``apply`` method should return a new dict
        with those same keys.
        """
        plugin_kwargs = {
            'request': request,
            'root': root,
            'schema': schema
        }
        contexts = []
        # TODO: replace with backported ExitStack()
        for plugin in self.plugins:
            context = plugin.apply(**plugin_kwargs)
            plugin_kwargs = context.__enter__()
            contexts.append((context, plugin_kwargs))
        yield plugin_kwargs
        for context, kwargs in contexts[::-1]:
            context.__exit__(None, None, None)

    def execute(self, graphql_string):
        kwargs = {
            'request': graphql_string,
            'root': self.query_root,
            'schema': self.schema
        }
        with self.apply_plugins(**kwargs) as plugin_kwargs:
            schema = plugin_kwargs['schema']
            request = plugin_kwargs['request']
            root = plugin_kwargs['root']
            return self.executor.execute(schema, request=request, root=root)


class RegistryEntry(object):
    def __init__(self, graphql_type, django_type=None, name=None):
        self.name = name or graphql_type.name
        self.graphql_type = graphql_type
        self.django_type = django_type


class TypeRef(object):
    def __init__(self, typename, registry, is_list=False):
        self.typename = typename
        self.registry = registry
        self.is_list = is_list

    def __call__(self, typeref):
        """
        Enables parametrizing other `TypeRef`s, e.g. 'T.List'

        # TODO: add support for DictType
        """
        if self.typename == 'List':
            return type(self)(typeref.typename, self.registry, is_list=True)

    def __repr__(self):
        return 'TypeRef(%s)' % self.typename


class TypeRegistry(object):
    def __init__(self):
        self._root = None
        self._types = {}
        self._register(GraphQLList, name='List')
        for scalar in (
                GraphQLBoolean,
                GraphQLFloat,
                GraphQLID,
                GraphQLInt,
                GraphQLString):
            self._register(scalar)

    def _register(self, graphql_type, django_type=None, name=None):
        entry = RegistryEntry(graphql_type, django_type=django_type, name=name)
        if entry.name in self._types:
            raise ValueError(
                "Type '%s' is already in registered types: %s, and was registered again. "
                "Cannot register the same type more than once."
                % (name, self._types.keys()))
        self._types[entry.name] = entry

    def _validate_type(self, name):
        if name not in self._types:
            raise KeyError(
                "Expected type '%s' to be in registered types %s. "
                "You can register '%s' by referring to it in one of your "
                "DjangoType's fields, e.g. 'some_field = T.%s'"
                % (name, self._types.keys(), name, name))

    def _get_graphql_type(self, name):
        self._validate_type(name)
        return self._types[name].graphql_type

    def _get_django_type(self, name):
        self._validate_type(name)
        return self._types[name].django_type

    def _get_model(self, name):
        return self._get_django_type(name).Meta.model

    def _get_root_spec(self, name):
        return self._get_django_type(name).get_root_spec()

    def _get_type(self, entry):
        type_name = entry.name
        if type_name not in self._types:
            raise GraphQLError(
                "Expected '%s' to be in registered types:\n\n%s\n\n"
                "You may need to create a DjangoType subclass called '%s', "
                "or check your spelling." % (
                    type_name, pprint.pformat(self._types), type_name))
        return self._types[type_name]

    def __getattr__(self, typename):
        return TypeRef(typename=typename, registry=self)

    def __repr__(self):
        types = self._types.keys()
        types_str = ', '.join(types)
        return 'TypeRegistry(%s)' % types_str


def prefetch(*fields):
    def inner(fn):
        fn._is_prefetch = True
        fn._prefetch = fields

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper
    return inner


def mutation(fn):
    """
    Classmethod decorator that marks DjangoType methods as GraphQL mutations.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    wrapper._is_mutation = True
    return wrapper


class DjangoTypeMeta(type):
    def __init__(self, name, bases, attrs):
        """
        Store fields, query methods, and mutation methods on subclass.

        Register 'self' as a GraphQL object type in the global registry.

        Field types are resolved later by DjangoRoot once all DjangoTypes
        have registered themselves.
        """
        super(DjangoTypeMeta, self).__init__(name, bases, attrs)
        if self.__name__ == 'DjangoType':
            return

        self._fields = []
        self._list_fields = []
        self._queries = []
        self._prefetch = {}
        self._mutations = []
        registry_set = set()

        for attrname, attrvalue in attrs.iteritems():
            if isinstance(attrvalue, TypeRef):
                if attrvalue.is_list:
                    self._list_fields.append((attrname, attrvalue))
                else:
                    self._fields.append((attrname, attrvalue))
                registry_set.add(attrvalue.registry)

            elif getattr(attrvalue, '_is_prefetch', False):
                self._prefetch[attrname] = attrvalue._prefetch

            elif getattr(attrvalue, '_is_mutation', False):
                self._mutations.append(attrvalue)

        if len(registry_set) > 1:
            raise RuntimeError(
                "Expected a single registry instance to register %s's types, "
                "saw: %r" % (name, registry_set))

        object_type = GraphQLObjectType(
            self.__name__,
            description=self.__doc__,
            fields=self.get_fields)

        self.registry = registry_set.pop()
        self.registry._register(object_type, django_type=self)


class DjangoType(object):
    __metaclass__ = DjangoTypeMeta

    @classmethod
    def _get_resolver(cls, field_name):
        def default_resolver(self, obj, *args):
            return getattr(obj, field_name)
        resolver = getattr(cls, 'get_%s' % field_name, default_resolver)
        return functools.partial(resolver, cls())

    @classmethod
    def get_fields(cls):
        fields = {
            name: GraphQLField(
                cls.registry._get_graphql_type(typeref.typename),
                description=cls._get_resolver(name).__doc__,
                resolver=cls._get_resolver(name))
            for name, typeref in cls._fields
        }
        fields.update({
            name: GraphQLField(
                GraphQLList(cls.registry._get_graphql_type(typeref.typename)),
                description=cls._get_resolver(name).__doc__,
                resolver=cls._get_resolver(name))
            for name, typeref in cls._list_fields
        })
        return fields

    @classmethod
    def get_root_spec(cls):
        name = cls.__name__
        return {
            name.lower(): GraphQLField(
                cls.registry._get_graphql_type(name),
                description=cls.__doc__,
                args=cls.get_root_args(),
                resolver=cls.get_root_resolver()
            )
        }

    @classmethod
    def get_root_args(cls):
        return {
            field_name: GraphQLArgument(
                type=cls.registry._get_graphql_type(typeref.typename))
            for field_name, typeref in cls._fields
            if field_name in cls.Meta.filters
        }

    @classmethod
    def get_root_resolver(cls):
        """
        Call ``Model.objects.get()`` with arguments from GraphQL query.

        Allowable filter fields are specified in ``DjangoType.Meta.filters``.
        """
        def get_model(root, query_args, info):
            """
            Fetches model(s) with Django manager ``get`` or ``filter`` method,
            and prefetches related fields as specified by DjangoType
            @prefetch decorators.

            Args:
                root (GraphQLObjectType): GraphQL query root
                query_args (dict): args passed for field in GraphQL request
                info (graphql.core.execution.base.ResolveInfo): contains request
                    context and schema

            Returns:
                Single Django model or Django QuerySet.

            TODO: wrap prefetched object caches in PredicateQuerySets to allow
                calling manager methods inside resolvers w/o incurring queries.
            """
            root_fields = info.schema.get_type_map()['QUERY_ROOT'].get_fields()
            field = info.field_asts[0]
            graphql_type = root_fields[field.name.value].type
            prefetch = cls.prefetch_list(field, graphql_type, cls)
            model = cls.Meta.model

            if any(isinstance(values, list) for values in query_args.itervalues()):
                filter_kwargs = cls._format_list_fields(query_args)
                # Return QuerySet.
                return model.objects.filter(**filter_kwargs).prefetch_related(*prefetch)

            # Return single object, not QuerySet.
            obj_qs = model.objects.filter(**query_args).prefetch_related(*prefetch)
            if not obj_qs.exists():
                return None
            return obj_qs[0]

        return get_model

    @classmethod
    def _format_list_fields(cls, query_args):
        formatted = {}
        for field_name, value in query_args.iteritems():
            if isinstance(value, list):
                formatted['%s__in' % field_name] = value
            else:
                formatted[field_name] = value
        return formatted

    @classmethod
    def prefetch_list(cls, field, graphql_type, django_type):
        """
        Generates list to be passed to prefetch_related to minimize
        database queries incurred by GraphQL request.

        Args:
            types (OrderedDict): schema type map
            ast (graphql.core.language.ast.Field): AST of GraphQL request

        Returns:
            list of strings containing model + relation names
        """
        if field.selection_set is None:
            return []

        prefetch = []

        for nested_field in field.selection_set.selections:
            nested_prefetch = list(django_type._prefetch.get(
                'get_%s' % nested_field.name.value,
                []))

            if nested_field.selection_set:
                fields = graphql_type.get_fields()
                nested_graphql_type = fields[nested_field.name.value].type
                if isinstance(nested_graphql_type, GraphQLList):
                    nested_graphql_type = nested_graphql_type.of_type
                nested_django_type = cls.registry._get_django_type(nested_graphql_type.name)
                nested_prefetch.extend([
                    '%s__%s' % (np, pf)
                    for np in nested_prefetch
                    for pf in cls.prefetch_list(
                        nested_field,
                        nested_graphql_type,
                        nested_django_type)
                ])

            prefetch.extend(nested_prefetch)

        return prefetch
