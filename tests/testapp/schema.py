from django_graphql.lib import (
    DjangoSchema,
    DjangoType,
    GraphQLObjectType,
    GraphQLArgument,
    GraphQLInt,
    GraphQLField,
    GraphQLSchema,
    prefetch,
    mutation,
    TypeRegistry,
)

import models


T = TypeRegistry()


class Container(DjangoType):
    """
    Contains zero or more Items at any given time.
    """
    id = T.Int
    name = T.String
    items = T.List(T.Item)
    current_items = T.List(T.Item)

    @prefetch('items')
    def get_items(self, obj, args, info):
        """
        All items in container.
        """
        return obj.items.all()

    @prefetch('items')
    def get_current_items(self, obj, args, info):
        """
        Current items in container.
        """
        return obj.items.filter(itemmovement__left__isnull=True)

    class Meta:
        model = models.Container
        filters = (
            'id',
            'name'
        )


class Item(DjangoType):
    """
    Occupies one or zero Containers at any given time.
    """
    id = T.Int
    name = T.String
    containers = T.List(T.Container)
    current_container = T.Container

    @prefetch('containers')
    def get_containers(self, obj, args, info):
        """
        All containers the item has been in.
        """
        return obj.containers.all()

    @prefetch('containers')
    def get_current_container(self, obj, args, info):
        """
        Current container the item is in.
        """
        return obj.current_container()

    class Meta:
        model = models.Item
        filters = (
            'id',
            'name'
        )


schema = DjangoSchema(T)
